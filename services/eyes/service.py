import logging
import os
import queue
import random
import time
from pathlib import Path
from threading import Event, Lock, Thread

import cv2

from .draw import draw_face, get_face_from_file
from .interpolation import get_in_between_faces


class Eyes():

    def __init__(self, faces_dir='files/faces', face_cache='files/face_cache', sc_width=1080, sc_height=1920):
        self.logger = logging.getLogger('Eyes')
        self.logger.setLevel(logging.DEBUG)

        self.faces_dir = Path(faces_dir)
        self.face_cache = Path(face_cache)
        self.screen_width = sc_width
        self.screen_heigth = sc_height

        self.transition_faces = queue.Queue() # Queue for managing and processing the canvas face re-drawings

        self.current_face = 'neutral'
        self.current_face_points = get_face_from_file(self.faces_dir/'neutral.json')
        self.transition_faces.put((self.current_face, self.current_face_points)) # Introduce the first state face in the queue

        self.stopped = Event()
        self.lock = Lock() # Semaphore for concurrent variables access control

        self.logger.info('Ready')

        self.start()
    
    def _set(self, face, steps=3):
        if self.current_face != face:
            target_face = get_face_from_file(self.faces_dir/f'{face}.json')

            in_between_faces = get_in_between_faces(self.current_face_points, target_face, steps)
            
            for index, face_points in enumerate(in_between_faces):
                self.transition_faces.put((f'{self.current_face}TO{face}_{index+1}of{steps}', face_points))

            self.transition_faces.put((face,target_face))

            self.logger.info(f'Queued transitions from {self.current_face} to {face}')

            # Update current face
            self.current_face_points = target_face
            self.current_face = face 
    
    def set(self, face):
        with self.lock:
            self._set(face)

    def _run(self):

        # Initialize the windows
        cv2.namedWindow("window", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("window",cv2.WND_PROP_FULLSCREEN,cv2.WINDOW_FULLSCREEN)

        next_blink = time.time() + random.randint(4,7) # Time of blink

        while not self.stopped.is_set():
            try:
                name_transition, new_face = self.transition_faces.get(timeout=0.1) # get face to draw from queue
                
                face_file = str(self.face_cache/f'{name_transition}.png')
                if os.path.exists(face_file):
                    canvas = cv2.imread(face_file) # Read the face from cache
                else:
                    canvas = draw_face(new_face, self.screen_width, self.screen_heigth) # Draw it
                    cv2.imwrite(face_file, canvas) 
                cv2.imshow("window", canvas)

            except queue.Empty: # "A lot" of time without new transitions/faces in the queue
                if time.time() > next_blink and '_closed' not in self.current_face: # blink time (if the face is not a closed face)
                    current_face = self.current_face

                    with self.lock:
                        self._set(f'{current_face}_closed', 1) # Make the blink
                        self._set(current_face, 1)

                    next_blink = time.time() + random.randint(4,7) # Calculate next blink time
                continue
            
            finally:
                if cv2.waitKey(1) == ord('q'): # Close the window
                    break    
                pass

        cv2.destroyAllWindows()
        
    def start(self):
        self.thread = Thread(target = self._run)
        self.stopped.clear()
        self.thread.start()

    def stop(self):
        self.stopped.set()
        self.thread.join()

        self.logger.info('Stopped')
