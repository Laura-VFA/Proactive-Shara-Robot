import logging
import queue
from collections import deque
from threading import Event, Thread

import pyaudio
import numpy as np
from silero_vad import get_speech_timestamps, load_silero_vad

class Recorder:
    def __init__(self, callback, chunk_size=2048, format=pyaudio.paInt16,
                 channels=1, rate=16000, prev_audio_size=2.5) -> None:
        self.logger = logging.getLogger('Mic')
        self.logger.setLevel(logging.DEBUG)

        self.chunk_size = chunk_size
        self.format = format
        self.channels = channels
        self.rate = rate
        self.prev_audio_size = prev_audio_size  # Previous audio (in seconds) to prepend. When noise
                                        # is detected, how much of previously recorded audio is
                                        # prepended. This helps to prevent chopping the beggining
                                        # of the phrase.
    
        self.audio2send = []
        self.prev_audio = deque(maxlen=int(prev_audio_size * rate/chunk_size)) 
        
        self.p = pyaudio.PyAudio()
        self.input_device_index = self._get_input_sound_index()

        self.model = load_silero_vad()  # Load Silero VAD model
        self.stream = None

        self._thread = None
        self.stopped = Event()
        self.start_recording = Event()
        self.stop_recording = Event()
        self.callback = callback

        self.audio_buffer = deque(maxlen=int(rate / chunk_size * 1.0))  # Buffer for 1 second of audio for faster detection
        self.process_every_n = 2  # Process every N chunks to reduce CPU load
        self.chunk_counter = 0
        self.min_buffer_size = int(rate / chunk_size * 0.5)  # Minimum 0.5 seconds for VAD processing

        # Streaming attributes
        self.streaming_enabled = False
        self.streaming_queue = None

        self.logger.info('Ready')
    
    def _get_input_sound_index(self, device_name="respeaker"):
        # Check all sound devices and return the index of the Respeaker device (or the looked device)
        for i in range(self.p.get_device_count()):
            dev_info = self.p.get_device_info_by_index(i)
            if device_name in dev_info.get("name", "").lower():
                self.logger.info(f"{device_name} detected in index {i}: {dev_info.get('name')}")
                return i
        self.logger.error(f"{device_name} not found")
        return 0
    
    def on_data(self, in_data, frame_count, time_info, flag): # Callback for recorded audio
        is_speech = False

        # Append incoming data to the buffer
        self.audio_buffer.append(in_data)
        
        # Process only every N chunks to reduce CPU usage
        self.chunk_counter += 1
        should_process = (self.chunk_counter % self.process_every_n == 0) or self.start_recording.is_set()

        # Process buffer if it contains enough data and it's time to process
        if should_process and len(self.audio_buffer) >= self.min_buffer_size:
            audio_chunk = np.frombuffer(b''.join(self.audio_buffer), dtype=np.int16).astype(np.float32) / 32768.0 # needed format for Silero VAD
            voiced_timestamps = get_speech_timestamps(audio_chunk, self.model, sampling_rate=self.rate)

            if voiced_timestamps:
                is_speech = True

        if is_speech:
            if not self.start_recording.is_set():
                self.audio2send = []
                self.start_recording.set()
                self.audio2send.extend(self.prev_audio)
                
                # If streaming is enabled, also send previous audio chunks to streaming queue
                if self.streaming_enabled and self.streaming_queue is not None:
                    for prev_chunk in self.prev_audio:
                        try:
                            self.streaming_queue.put_nowait(prev_chunk)
                        except queue.Full:
                            self.logger.warning('Streaming queue full while adding prev_audio, dropping chunk')
            
            self.audio2send.append(in_data)
            
            # If streaming is enabled, send chunks to streaming queue
            if self.streaming_enabled and self.streaming_queue is not None:
                try:
                    self.streaming_queue.put_nowait(in_data)
                except queue.Full:
                    self.logger.warning('Streaming queue full, dropping chunk')

        elif self.start_recording.is_set(): # Silence detected after voice activity
            self.start_recording.clear()
            self.stop_recording.set()
            
            # Signal end of streaming
            if self.streaming_enabled and self.streaming_queue is not None:
                try:
                    self.streaming_queue.put_nowait(None)  # Sentinel value
                except queue.Full:
                    pass
            
            self.prev_audio = deque(maxlen=int(self.prev_audio_size * self.rate/self.chunk_size)) 
            return (in_data, pyaudio.paComplete)
            
        else:
            self.prev_audio.append(in_data)
        
        return (in_data, pyaudio.paContinue)

    def start(self):

        self.stopped.clear()
        self.start_recording.clear() # Start recording event
        self.stop_recording.clear() # Stop recording event

        self.stream = self.p.open(format=self.format,
                channels=self.channels,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.chunk_size,
                input_device_index=self.input_device_index,
                stream_callback=self.on_data)
        
        self._thread = Thread(target=self._run)
        self._thread.start()

        self.logger.info('Mic opened')

    def _run(self):
        self.start_recording.wait()
        if self.stopped.is_set():
            return

        self.logger.info('Started recording')
        self.callback('start_recording')

        self.stop_recording.wait() # Pause until recording has finished
        if self.stopped.is_set():
            return

        self.logger.info('Stopped recording')
        self.callback('stop_recording', b''.join(self.audio2send))
        self.stream.close()
        self.stream = None

    def stop(self):
        self.logger.info("Mic closed")

        self.stopped.set()
        self.start_recording.set()
        self.stop_recording.set()
        
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()

        if self.stream is not None:
            self.stream.close()
        self.start_recording.clear()
        self.stop_recording.clear()
    
    def destroy(self):
        self.stop()
        self.p.terminate()


    def enable_streaming(self):
        # Enable streaming mode: audio chunks will be sent to streaming queue
        if not self.streaming_enabled:
            self.streaming_queue = queue.Queue(maxsize=100)
            self.streaming_enabled = True
            self.logger.info('Streaming enabled')
    
    def disable_streaming(self):
        # Disable streaming mode
        if self.streaming_enabled:
            self.streaming_enabled = False
            if self.streaming_queue is not None:
                # Clear the queue
                while not self.streaming_queue.empty():
                    try:
                        self.streaming_queue.get_nowait()
                    except queue.Empty:
                        break
            self.streaming_queue = None
            self.logger.info('Streaming disabled')
    
    def get_audio_generator(self):
        """
        Generator that yields audio chunks from the streaming queue.
        Used to feed the STT streaming API
        
        Yields:
            bytes: Audio chunks
        """
        if self.streaming_queue is None:
            self.logger.warning('Streaming queue not initialized')
            return
        
        while True:
            chunk = self.streaming_queue.get()
            if chunk is None:  # value to stop
                break
            yield chunk