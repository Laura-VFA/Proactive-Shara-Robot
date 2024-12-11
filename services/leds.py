import logging
import time
from abc import ABC
from math import pi, sin
from threading import Event, Lock, Thread

from matrix_lite import led


class LedState(ABC):
    def __init__(self):
        self.initial_led_state = 'black'

    def get_next_color(self):
        return None

    def __eq__(self, other):
        return self.__class__ == other.__class__


# Action leds
class Loop(LedState):
    def __init__(self, rgbw_color):
        super().__init__()

        if isinstance(rgbw_color, str): # Allow single or multichannel colors
            self.rgbw_color = [rgbw_color] # Single channel
        else:
            self.rgbw_color = rgbw_color # Multiple channels in list/tuple
        self.index = 0
        interval = int(255 / led.length)

        self.bright = [
            {component: 255 - i * interval for component in self.rgbw_color} 
            for i in range(led.length)
        ] * 2

    def get_next_color(self):
        next = self.bright[self.index : self.index + led.length]
        self.index = (self.index + 1) % led.length 

        return next
    
    def __eq__(self, other):
        return super().__eq__(other) and self.rgbw_color == other.rgbw_color

class Progress(LedState):
    def __init__(self, color:str='green', percentage=0):
        super().__init__()
        self.color = color
        self.percentage = percentage
        n_leds_light = int(percentage * led.length / 100)

        self.initial_led_state = [color]*n_leds_light
    
    def __eq__(self, other):
        return super().__eq__(other) and self.color == other.color and self.percentage == other.percentage

class Breath(LedState):
    def __init__(self, rgbw_color):
        super().__init__()

        if isinstance(rgbw_color, str): # Allow single or multichannel colors
            self.rgbw_color = [rgbw_color] # Single channel
        else:
            self.rgbw_color = rgbw_color # Multiple channels in list/tuple
        self.interval = int(255 / led.length)
        self.bright = [255 - i*self.interval for i in range(led.length)]
        self.bright.extend(self.bright[::-1])
        self.index = 0

    def get_next_color(self):
        next = {component: self.bright[self.index] for component in self.rgbw_color}
        self.index = (self.index + 1) % len(self.bright)

        return next
    
    def __eq__(self, other):
        return super().__eq__(other) and self.rgbw_color == other.rgbw_color

class StaticColor(LedState):
    def __init__(self, color: str):
        super().__init__()
        self.initial_led_state = color
    
    def __eq__(self, other):
        return super().__eq__(other) and self.initial_led_state == other.initial_led_state

class Close(LedState):
    def __init__(self, color: str):
        super().__init__()
        self.color = color
        self.array = [color]*led.length
        self.initial_led_state = self.array

    def get_next_color(self):
        if self.array:
            self.array.pop()
            return self.array
        return 'black'
    
    def __eq__(self, other):
        return super().__eq__(other) and self.color == other.color

class Rainbow(LedState):
    def __init__(self):
        self.everloop = ['black'] * led.length
        self.initial_led_state = self.everloop

        self.ledAdjust = 1.01 # MATRIX Voice

        self.frequency = 0.375
        self.counter = 0.0

    def get_next_color(self):
        for i in range(len(self.everloop)):
            r = round(max(0, (sin(self.frequency*self.counter+(pi/180*240))*155+100)/10))
            g = round(max(0, (sin(self.frequency*self.counter+(pi/180*120))*155+100)/10))
            b = round(max(0, (sin(self.frequency*self.counter)*155+100)/10))

            self.counter += self.ledAdjust

            self.everloop[i] = {'r':r, 'g':g, 'b':b}

        return self.everloop


class MatrixLed:
    def __init__(self):
        self.logger = logging.getLogger('Leds')
        self.logger.setLevel(logging.DEBUG)

        self.state = StaticColor('black')
        led.set(self.state.initial_led_state)
        self.stopped = Event()
        self.lock = Lock()

        self.logger.info('Ready')

        self.start()
    
    def set(self, ledState:'LedState'):
        with self.lock: # exclusive access to matrix led driver
            if self.state != ledState:
                self.logger.info(f'Changing leds from {self.state.__class__.__name__} to {ledState.__class__.__name__}')
                self.state = ledState
                led.set(self.state.initial_led_state)
    
    def _run(self):
        self.logger.info('Started')

        while not self.stopped.is_set():
            next_color = self.state.get_next_color()
            if next_color is not None:
                led.set(next_color)
            time.sleep(0.050)
        
    def start(self):
        self.thread = Thread(target = self._run)
        self.stopped.clear()
        self.thread.start()

    def stop(self):
        self.stopped.set()
        self.thread.join()
        led.set('black')

        self.logger.info('Stopped')
