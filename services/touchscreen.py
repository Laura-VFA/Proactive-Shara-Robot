import logging
import select
from threading import Thread, Event, Timer
from evdev import InputDevice, list_devices, ecodes


class TouchScreen:
    def __init__(self, callback):
        self.logger = logging.getLogger('TouchScreen')
        self.logger.setLevel(logging.DEBUG)

        self.callback = callback

        self.stopped = Event()
        self._thread = None

        self.device = self._find_touch_device()
        if self.device is None:
            self.logger.error("Cannot find touch device")
            raise Exception("Cannot find touch device")

        self.logger.info("Ready")
    
    def _find_touch_device(self):
        devices = [InputDevice(path) for path in list_devices()]

        touch_device = None
        for device in devices:
            # Set the touch device for Waveshare touchscreen
            if 'touch' in device.name.lower() or 'waveshare' in device.name.lower():
                touch_device = device
                break
    
        return touch_device

    def _run(self):
        self.logger.info("Started")

        active_touches = {} # Active touches by slot (fingers)
        current_slot = None  # Will be set by first ABS_MT_SLOT event
        hold_timer = None # Timer for holding fingers

        def trigger_event():
            nonlocal hold_timer
            if len(active_touches) == 3:
                self.logger.info("Three (3) fingers hold during 3 seconds. Triggering shutdown event")
                self.callback('shutdown') # Genetare a interrupt to main thread
            hold_timer = None

        try:
            while not self.stopped.is_set():
                r, _, _ = select.select([self.device.fd], [], [], 0.5) # Wait for reading events with timeout of 0.5 seconds

                if r:
                    for event in self.device.read():
                        if event.type == ecodes.EV_ABS:
                            if event.code == ecodes.ABS_MT_SLOT:
                                current_slot = event.value

                            elif event.code == ecodes.ABS_MT_TRACKING_ID:
                                if current_slot is None:
                                    self.logger.debug("Skipping event - slot not yet initialized")
                                    continue  # Skip if slot not set
                                    
                                if event.value == -1:
                                    # Remove touch since finger was lifted
                                    if current_slot in active_touches:
                                        del active_touches[current_slot]
                                        self.logger.debug(f"Finger lifted from slot {current_slot}. Active touches: {len(active_touches)}")
                                    
                                    # Cancel timer only when we no longer have 3 fingers
                                    if len(active_touches) != 3 and hold_timer is not None:
                                        self.logger.debug("Cancelling timer - not 3 fingers anymore")
                                        hold_timer.cancel()
                                        hold_timer = None
                                
                                else:
                                    # New finger touch: store the value
                                    active_touches[current_slot] = event.value
                                    self.logger.debug(f"New finger touch on slot {current_slot}. Active touches: {len(active_touches)}")
                                    
                                    # Start timer when we reach exactly 3 fingers
                                    if len(active_touches) == 3 and hold_timer is None:
                                        self.logger.info("Three fingers detected - starting 3 second timer")
                                        hold_timer = Timer(3, trigger_event)
                                        hold_timer.start()
    
        except Exception as e:
            self.logger.error(f"Event loop error: {e}")
        
        finally:
            if hold_timer is not None:
                hold_timer.cancel() # Cancel the timer if it's still running

            if self.device:
                try:
                    self.device.close() # Close the device
                except Exception:
                    pass

    def start(self):
        self.stopped.clear()
        self._thread = Thread(target=self._run)
        self._thread.start()

    def stop(self):
        self.stopped.set()

        if self._thread is not None and self._thread.is_alive():
            self._thread.join()

        self.logger.info("Stopped")
