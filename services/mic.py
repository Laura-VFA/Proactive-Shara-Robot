import logging
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
            self.audio2send.append(in_data)

        elif self.start_recording.is_set():
            self.start_recording.clear()
            self.stop_recording.set()
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
