import logging
from threading import Lock

import imutils
import numpy as np
import pyrealsense2.pyrealsense2 as rs


class Camera:
    def __init__(self) -> None:
        self.logger = logging.getLogger('Camera')
        self.logger.setLevel(logging.DEBUG)

        self.active_services = set() # set of services using the camera

        self.pipeline = rs.pipeline()
        self.config = rs.config()
        self.config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)

        self.lock = Lock()

        self.logger.info('Ready')

    def get_color_frame(self, resize_width: int = None):
        frames = self.pipeline.wait_for_frames()
        color_image = np.asanyarray(frames.get_color_frame().get_data())
        if resize_width:
            return imutils.resize(color_image, width=resize_width)
        return color_image
    
    def start(self, service):
        with self.lock: # exclusive access to set of services
            if not self.active_services:
                self.pipeline.start(self.config)
            
            self.active_services.add(service)
        
        self.logger.info(f'Service {service} enabled')

    def stop(self, service):
        with self.lock:
            if not self.active_services:
                return

            self.active_services.discard(service)

            if not self.active_services:
                self.pipeline.poll_for_frames() # clear last frame buffer
                self.pipeline.stop()
        
        self.logger.info(f'Service {service} disabled')
