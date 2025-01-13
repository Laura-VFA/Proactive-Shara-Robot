import logging
import json
import serial
from dataclasses import dataclass
from threading import Event, Lock, Thread


@dataclass
class LedState:
    color: tuple
    fx: int = 0
    sx: int = None
    ix: int = None
    brightness: int = None
    command: dict = None

    def __post_init__(self):
        if self.command is None:
            self.command = {
                "seg":[
                    {
                        "fx": self.fx
                    }],
            }

            if self.sx is not None:
                self.command["seg"][0]["sx"] = self.sx

            if self.ix is not None:
                self.command["seg"][0]["ix"] = self.ix

            if self.color is not None:
                self.command["seg"][0]["col"] = [self.color]
        
            if self.brightness is not None:
                self.command["bri"] =  self.brightness
        
    @classmethod
    def breath(cls, color):
        return cls(color, fx=2)

    @classmethod
    def loop(cls, color):
        return cls(color, fx=41, sx=200)
    
    @classmethod
    def static_color(cls, color):
        return cls(color, fx=0)

    @classmethod
    def progress(cls, color, percentage):
        return cls(color, fx=98, ix=percentage)
    
    @classmethod
    def rainbow(cls):
        return cls(None, fx=9)

    
class ArrayLed:
    def __init__(self, port: str = '/dev/ttyAMA0'):
        self.logger = logging.getLogger('Leds')
        self.logger.setLevel(logging.DEBUG)
        
        self.port = port

        self.state_changed = Event()
        self.stopped = Event()
        self.lock = Lock()

        self.logger.info('Ready')

        self.start()
    
    def set(self, ledState:'LedState'):
        with self.lock: # exclusive access to led driver
            if self.state != ledState:
                self.logger.info(f'Changing leds from {self.state.__class__.__name__} to {ledState.__class__.__name__}')
                self.state = ledState

                self.state_changed.set()
    
    def _run(self):
        self.logger.info('Started')
        with serial.Serial(self.port, 115200, timeout=1) as s:
            s.write(f'{json.dumps({"on": True})}\n'.encode()) # Turn on leds for first time

            while not self.stopped.is_set():
                if not self.state_changed.wait(1):
                    continue

                self.state_changed.clear()

                command = self.state.command
                s.write(f'{json.dumps(command)}\n'.encode())
            
            s.write(f'{json.dumps({"on": False})}\n'.encode()) # Shutdown leds for closing
    
    def start(self):
        self.thread = Thread(target = self._run)

        # shutdown leds at the beginning
        self.state = LedState.static_color((0, 0, 0)) 
        self.state_changed.set() 

        self.stopped.clear()
        self.thread.start()

    def stop(self):
        self.state_changed.clear()
        self.stopped.set()
        self.thread.join()

        self.logger.info('Stopped')
    