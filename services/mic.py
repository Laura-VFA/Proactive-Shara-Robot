import logging
from collections import deque
from threading import Event, Thread

import pyaudio
import webrtcvad


class Recorder:
    def __init__(self, callback, chunk_size=2048, format=pyaudio.paInt16,
                 channels=1, rate=16000, prev_audio_size=1.0, vad_agressiveness=3) -> None:
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
        self.vad = webrtcvad.Vad(vad_agressiveness)
        self.stream = None

        self._thread = None
        self.stopped = Event()
        self.start_recording = Event()
        self.stop_recording = Event()
        self.callback = callback

        self.logger.info('Ready')
    
    def on_data(self, in_data, frame_count, time_info, flag): # Callback for recorded audio
        is_speech = False

        # Detect if voice in the audio chunk
        for frame in frame_generator(30, in_data, self.rate): # Vad requires audio frames of 10, 20 or 30 ms
            if self.vad.is_speech(frame, self.rate):
                is_speech = True
                break

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
                input_device_index=0, # remember to check which index device is Respeaker
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

def frame_generator(frame_duration_ms, audio, sample_rate):
    """Generates audio frames from PCM audio data.
    Takes the desired frame duration in milliseconds, the PCM data, and
    the sample rate.
    Yields Frames of the requested duration.

    https://github.com/wiseman/py-webrtcvad/blob/master/example.py
    """
    n = int(sample_rate * (frame_duration_ms / 1000.0) * 2)
    offset = 0
    while offset + n < len(audio):
        yield audio[offset:offset + n]
        offset += n
