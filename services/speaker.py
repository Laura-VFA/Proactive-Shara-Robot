import logging
from contextlib import contextmanager
from ctypes import CFUNCTYPE, c_char_p, c_int, cdll
from threading import Thread

import pyaudio


@contextmanager
def supress_alsa_warnings():
    asound = cdll.LoadLibrary('libasound.so')
    asound.snd_lib_error_set_handler(
        CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)(
            lambda filename, line, function, err, fmt: None
        )
    )
    yield
    asound.snd_lib_error_set_handler(None)

class Speaker:
    def __init__(self, callback, chunk_size=2048,
                 format=pyaudio.paInt16, channels=1, rate=24000):
        self.logger = logging.getLogger('Speaker')
        self.logger.setLevel(logging.DEBUG)

        self.chunk_size = chunk_size
        self.format = format
        self.channels = channels
        self.rate = rate  

        self.callback = callback
        self._thread = None

        with supress_alsa_warnings():
            self.p = pyaudio.PyAudio() # Create an interface to PortAudio

        self.logger.info('Ready')
    
    def start(self, audio):
        self._thread= Thread(target=self.play, args=(audio,))
        self._thread.start()

    def play(self, audio):
        self.logger.info('Playing audio')

        stream = self.p.open(format = self.format,
                        channels = self.channels,
                        rate = self.rate,
                        output = True,
                        output_device_index=1
                        )

        stream.write(audio)
        stream.close()

        self.logger.info('Playing done')
        self.callback('finish_speak')
    
    def destroy(self):
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()

        self.p.terminate()

        self.logger.info('Stopped')
