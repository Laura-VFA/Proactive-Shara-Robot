import logging
from threading import Lock

import imutils
import numpy as np
from picamera2 import Picamera2

class Camera:
    def __init__(self, resolution=(1280,720)) -> None:
        self.logger = logging.getLogger('Camera')
        self.logger.setLevel(logging.DEBUG)

        self.active_services = set() # set of services using the camera

        self.camera = Picamera2()
        # Configure resolution and format
        self.camera_config = self.camera.create_preview_configuration(
            main={"size": resolution, "format": "RGB888"}
        )
        self.camera.configure(self.camera_config)

        self.lock = Lock()

        self.logger.info('Ready')

    def get_color_frame(self, resize_width: int = None):
        with self.lock:
            frame = self.camera.capture_array().astype(np.uint8)
        if resize_width:
            return imutils.resize(frame, width=resize_width)
        return frame
    
    def start(self, service):
        with self.lock: # exclusive access to set of services
            if not self.active_services:
                self.camera.start()
            
            self.active_services.add(service)
        
        self.logger.info(f'Service {service} enabled')

    def stop(self, service):
        with self.lock:
            if not self.active_services:
                return

            self.active_services.discard(service)

            if not self.active_services:
                self.camera.stop()
        
        self.logger.info(f'Service {service} disabled')
