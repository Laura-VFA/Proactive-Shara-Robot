import logging
from threading import Thread

import simpleaudio as sa


class Speaker:
    def __init__(self, callback, chunk_size=2048, channels=1, sample_width=2, rate = 24000):
        self.logger = logging.getLogger('Speaker')
        self.logger.setLevel(logging.DEBUG)

        self.chunk_size = chunk_size
        self.format = format
        self.channels = channels
        self.rate = rate  
        self.sample_width=sample_width

        self.callback = callback
        self._thread = None

        self.logger.info('Ready')
    
    def start(self, audio):
        self._thread= Thread(target=self.play, args=(audio,))
        self._thread.start()

    def play(self, audio):
        self.logger.info('Playing audio')

        audio_object = sa.WaveObject(audio, self.channels, self.sample_width, self.rate)

        play_object = audio_object.play()
        play_object.wait_done()

        self.logger.info('Playing done')
        self.callback('finish_speak')
    
    def destroy(self):
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()

        self.logger.info('Stopped')
