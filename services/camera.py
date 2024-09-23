import logging
from threading import Lock

import imutils
import numpy as np

from jetcam.csi_camera import CSICamera


class Camera:
    def __init__(self) -> None:
        self.logger = logging.getLogger('Camera')
        self.logger.setLevel(logging.DEBUG)

        self.active_services = set() # set of services using the camera

        self.lock = Lock()

        self.cam_config = {
            'width': 400,
            'height': 300,
            'capture_width': 1080, # change this resolution for modify eyefish effect
            'capture_height': 720,
            'capture_fps': 30, 
            'flip_method': 2
        }

        self.camera = CSICamera(**self.cam_config)
        self.camera.running = True
        self.camera.observe(self._new_frame_callback, names='value')

        self.frame = None
        
        self.logger.info('Ready')

    def _new_frame_callback(self, change):
        with self.lock:
            self.frame = change['new']

    def get_color_frame(self, resize_width: int = None):
        with self.lock:
            if self.frame is None:
                return None
            color_image = self.frame.copy()

        if resize_width:
            return imutils.resize(color_image, width=resize_width)
        return color_image
    
    def start(self, service):
        with self.lock: # exclusive access to set of services
            if not self.active_services:
                self.camera.running = True
                self.camera.observe(self._new_frame_callback, names='value')
                pass

            self.active_services.add(service)           

        
        self.logger.info(f'Service {service} enabled')

    def stop(self, service):
        with self.lock:
            if not self.active_services:
                return

            self.active_services.discard(service)

            if not self.active_services:
                self.close()
        
        self.logger.info(f'Service {service} disabled')

    def close(self):
        if self.camera.running:
            self.camera.unobserve(self._new_frame_callback, names='value')
            self.camera.running = False
