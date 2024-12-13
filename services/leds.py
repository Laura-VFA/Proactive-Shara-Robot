import logging
import time
from abc import ABC
from math import pi, sin, floor
from threading import Event, Lock, Thread

import neopixel_spi
import board

NUM_PIXELS = 24
pixels = neopixel_spi.NeoPixel_SPI(board.SPI(), NUM_PIXELS)

class LedState(ABC):
    def __init__(self):
        self.initial_led_state = [(0,0,0)] * NUM_PIXELS

    def get_next_color(self):
        return None

    def __eq__(self, other):
        return self.__class__ == other.__class__


# Action leds
class Loop(LedState):
    def __init__(self, color: tuple):
        super().__init__()

        self.color = color

        # Calculate brightness levels for each LED
        self.brightness_levels = [
            i / NUM_PIXELS for i in range(NUM_PIXELS)
        ]

        self.led_colors = [
            self._apply_brightness(self.color, brightness)
            for brightness in self.brightness_levels
            ]

    def _apply_brightness(self, color, brightness):
        return tuple(floor(c * brightness) for c in color)

    def get_next_color(self):
        # Rotate colors to reproduce loop effect
        self.led_colors = [self.led_colors[-1]] + self.led_colors[:-1]

        return self.led_colors
    
    def __eq__(self, other):
        return super().__eq__(other) and self.color == other.color

class Progress(LedState):
    def __init__(self, color:tuple=(0,255,0), percentage=0):
        super().__init__()
        self.color = color
        self.percentage = percentage
        n_leds_light = int(percentage * NUM_PIXELS / 100)

        self.initial_led_state = [color]*n_leds_light + [(0,0,0)] * (NUM_PIXELS - n_leds_light) # Fill with black leds (closed ones)
    
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
    def __init__(self, color: tuple):
        super().__init__()
        self.initial_led_state = [color] * NUM_PIXELS
    
    def __eq__(self, other):
        return super().__eq__(other) and self.initial_led_state == other.initial_led_state

class Close(LedState):
    def __init__(self, color: tuple):
        super().__init__()
        self.color = color
        self.array = [color]*NUM_PIXELS
        self.initial_led_state = self.array

    def get_next_color(self):
        if self.array:
            self.array.pop()
            return self.array + [(0,0,0)] * (NUM_PIXELS - len(self.array)) # Fill with black leds (closed ones)
        return [(0,0,0)] * NUM_PIXELS
    
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


class ArrayLed:
    def __init__(self):
        self.logger = logging.getLogger('Leds')
        self.logger.setLevel(logging.DEBUG)

        self.state = StaticColor((0,0,0))
        pixels[:] = (self.state.initial_led_state)
        self.stopped = Event()
        self.lock = Lock()

        self.logger.info('Ready')

        self.start()
    
    def set(self, ledState:'LedState'):
        with self.lock: # exclusive access to neopixel led driver
            if self.state != ledState:
                self.logger.info(f'Changing leds from {self.state.__class__.__name__} to {ledState.__class__.__name__}')
                self.state = ledState
                pixels[:] = self.state.initial_led_state
    
    def _run(self):
        self.logger.info('Started')

        while not self.stopped.is_set():
            next_color = self.state.get_next_color()
            if next_color is not None:
                pixels[:] = next_color
            time.sleep(0.050)
        
    def start(self):
        self.thread = Thread(target = self._run)
        self.stopped.clear()
        self.thread.start()

    def stop(self):
        self.stopped.set()
        self.thread.join()
        pixels.fill((0,0,0))

        self.logger.info('Stopped')
