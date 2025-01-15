import logging
import queue
from abc import ABC
from threading import Event, Thread

import cv2
import face_recognition
import numpy as np
import pandas as pd
from fdlite import FaceDetection, FaceDetectionModel, FaceIndex
from imutils.video import FPS
from PIL import Image
from tensorflow.keras.preprocessing.image import ImageDataGenerator

from .camera import Camera
from .presence_detector.object_detector import ObjectDetector


class FaceDB:
    encodings = None
    encodings_file = None

    @staticmethod
    def load(encodings_file='files/encodings.csv'):
        FaceDB.encodings_file = encodings_file

        try:
            df = pd.read_csv(FaceDB.encodings_file, sep=';', header=None)
            FaceDB.encodings = {
                'names': df[0].to_list(),
                'encodings': df.loc[:, 1:128].to_numpy()
            }
        except (pd.errors.EmptyDataError, FileNotFoundError):
            FaceDB.encodings = {'names': [], 'encodings': np.empty((0,128))}
    
    @staticmethod
    def append(name, new_encoding):
        FaceDB.encodings['names'].append(name)
        FaceDB.encodings['encodings'] = np.append(
            FaceDB.encodings['encodings'],
            np.expand_dims(new_encoding, axis=0),
            axis=0
        )
        
        with open(FaceDB.encodings_file, 'a') as f:
            f.write(';'.join([name, *[str(val) for val in new_encoding]]))
            f.write('\n')
    
    @staticmethod
    def dump():
        FaceDB.encodings.to_csv(FaceDB.encodings_file, sep=';')


class CameraService(ABC):
    camera = None
    def __init__(self) -> None:
        self.logger = logging.getLogger(type(self).__name__)
        self.logger.setLevel(logging.DEBUG)

        if not CameraService.camera:
            CameraService.camera = Camera()


class Wakeface(CameraService):
    
    def __init__(self, callback):
        super().__init__()

        self.callback = callback
        self.stopped = Event()
        self._thread_wakeface = None
        self._thread_recognizer = None

        self.face_queue = None # Faces to recognize
        
        # load detection models
        self.detect_faces = FaceDetection(model_type=FaceDetectionModel.FRONT_CAMERA) # BACK_CAMERA for more resolution
        
        self.logger.info('Ready')
        
    def start(self):

        self.stopped.clear()
        self._thread_wakeface = Thread(target=self._run_detector)
        self._thread_recognizer = Thread(target=self._run_recognize)

        self.face_queue = queue.Queue()

        self._thread_wakeface.start()
        self._thread_recognizer.start()
        
    
    def _run_detector(self):
        self.logger.info('Detector started')

        CameraService.camera.start(self.__class__.__name__)
        fps = FPS().start()

        while not self.stopped.is_set():
            # Get frame
            frame = CameraService.camera.get_color_frame(resize_width=500)
            h, w = frame.shape[:2]

            # Detect faces
            face_detections = self.detect_faces(
                Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            )
            
            if not face_detections :
                self.callback('not_faces')
                # Empty pending faces to recognize
                while not self.face_queue.empty(): self.face_queue.get(block=True) 
                self.face_queue.put((None, [])) # Notify recognition thread no faces detected

            else:
                bboxes_looking = [ # Filter looking faces
                    face.bbox.scale((w, h))
                    for face in face_detections
                    if Wakeface.check_looking(face)
                ]
  
                if not bboxes_looking : # No one looking
                    self.callback('face_not_listen') 
                    # Empty pending faces to recognize
                    while not self.face_queue.empty(): self.face_queue.get(block=False)
                    self.face_queue.put((None, [])) # Notify recognition thread no looking faces detected

                else:
                    self.callback('face_listen')

                    # Notify recognition thread about new looking faces detected
                    self.face_queue.put((frame, bboxes_looking))

            fps.update()

        fps.stop()
        self.logger.info(f"FPS: {fps.fps():.4f} (elapsed time: {fps.elapsed():.4f} s)")

    
    def stop(self):
        self.stopped.set()
        if self._thread_recognizer is not None and self._thread_recognizer.is_alive():
            self._thread_recognizer.join()
        
        if self._thread_wakeface is not None and self._thread_wakeface.is_alive():
            self._thread_wakeface.join()

        CameraService.camera.stop(self.__class__.__name__)

        self.logger.info('Stopped')

    @staticmethod
    def check_looking(face, incr=0.25):
        # WAKEFACE
        xr, _ = face[FaceIndex.RIGHT_EYE_TRAGION]
        xl, _ = face[FaceIndex.LEFT_EYE_TRAGION]
        _, ye1 = face[FaceIndex.LEFT_EYE]
        _, ye2 = face[FaceIndex.RIGHT_EYE]
        _, ym = face[FaceIndex.MOUTH]
        xn, yn = face[FaceIndex.NOSE_TIP]

        # Range mapping, normalize coordinates 
        # X axis
        xn = (xn - xl) / (xr - xl)

        # Y axis
        ye = (ye1 + ye2) / 2 # mean of both eyes
        yn = (yn - ye) / (ym - ye)


        # Interval checking
        return (incr <= xn <= (1 - incr)) and (incr <= yn <= (1 - incr))

    def _run_recognize(self):
        self.logger.info('Recognizer started')

        face_history = {} # Counter of previous recognized faces

        while not self.stopped.is_set():
            try:
                frame, bboxes = self.face_queue.get(timeout=.5)
            except queue.Empty:
                continue
            
            if not bboxes:
                face_history.clear()

            # Execute recognizer until a face is recognized or None at least 3 times
            elif not face_history or all(count < 3 if not name else False for name, count in face_history.items()):
                names = set(self.recognize(frame, bboxes)) # Remove duplicates
                face_history = {name: face_history.get(name, 0) + 1 for name in names} # Names counter
                self.callback('face_recognized', usernames=face_history)

                self.logger.info(f'Recognized history updated: {face_history}')
        
    def recognize(self, frame, bboxes_looking, tolerance=0.55):
        ''' https://pyimagesearch.com/2018/06/25/raspberry-pi-face-recognition/ '''
        boxes = [(int(box.ymin), int(box.xmax), int(box.ymax), int(box.xmin)) for box in bboxes_looking]
        
        encodings = face_recognition.face_encodings(frame, boxes)
        names = []

        for encoding in encodings:
            matches = face_recognition.compare_faces(FaceDB.encodings["encodings"],
                encoding, tolerance)
            name = None

            if any(matches):
                # find the indexes of all matched faces and initialize a
                # dictionary to count the total number of times each face
                # was matched
                matchedIdxs = [i for (i, b) in enumerate(matches) if b]
                counts = {}

                for i in matchedIdxs:
                    name = FaceDB.encodings["names"][i]
                    counts[name] = counts.get(name, 0) + 1
                # determine the recognized face with the largest number
                # of votes (note: in the event of an unlikely tie Python
                # will select first entry in the dictionary)
                name = max(counts, key=counts.get)

            names.append(name)
        
        return names
    


class RecordFace(CameraService):
    def __init__(self, callback):
        super().__init__()

        self.frames_to_encode = queue.Queue()

        self.callback = callback
        self.stopped = Event()
        self._thread_record = None
        self._thread_encoder = None
        
        # load detection models
        self.detect_faces = FaceDetection(model_type=FaceDetectionModel.FRONT_CAMERA)

        self.logger.info('Ready')

        
    def start(self, name):

        if self._thread_encoder is not None and self._thread_encoder.is_alive(): 
            self.stopped.set() # ensure that any previous encoding thread has finished
            while not self.frames_to_encode.empty(): self.frames_to_encode.get(block=False)
            self._thread_encoder.join()

        self.stopped.clear()
        self._thread_record = Thread(target=self._run_record, args=(name,))
        self._thread_encoder = Thread(target=self._run_encoder)
        self._thread_record.start()
        self._thread_encoder.start()
    
    def _run_record(self, name, n_frames=6):
        self.logger.info('Recorder started')

        CameraService.camera.start(self.__class__.__name__)

        frames_recorded = 0
        frames_without_faces = 0
        while frames_recorded < n_frames and not self.stopped.is_set():
            # Get frame
            frame = CameraService.camera.get_color_frame(resize_width=500)
            h, w = frame.shape[:2]

            # Detect faces
            face_detections = self.detect_faces(
                Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            )

            if not face_detections:
                frames_without_faces += 1
                if frames_without_faces == 10:
                    self.logger.info('10 consecutive frames without faces')

                    self.stopped.set()
                    break # Cancel face recording if there is no faces in 10 consecutive frames

            else:
                frames_without_faces = 0

                bboxes_looking = [ # Filter looking faces
                    face.bbox.scale((w, h))
                    for face in face_detections
                    if Wakeface.check_looking(face)
                ]
 
                if bboxes_looking:
                    self.frames_to_encode.put((name, frame, bboxes_looking))                        
                    frames_recorded += 1
                    
                    self.logger.info('Face frame recorded')
                    self.callback('recording_face', progress=frames_recorded*100/n_frames)
        
        CameraService.camera.stop(self.__class__.__name__)

        self.logger.info('Recorder stopped')

    def _run_encoder(self, n_augmented_images_per_frame=3):
        self.logger.info('Encoder started')

        augmenter = ImageDataGenerator(shear_range=0.1,
                               brightness_range=[0.5,1.5],
                               rotation_range=15,
                               width_shift_range=0.08,
                               height_shift_range=0.08
                               )

        while True:
            try:
                name, frame, bboxes_looking = self.frames_to_encode.get(timeout=0.1)
            except queue.Empty:
                if not self.stopped.is_set():
                    continue
                else:
                    break
                    
            self.logger.info('Encoding frame faces')

            # Get encodings 
            box = bboxes_looking[0] # take only the first box
            box_recog = (int(box.ymin), int(box.xmax), int(box.ymax), int(box.xmin)) # change format to (top, right, bottom, left)
            
            # Compute the facial embeddings for the face bounding box
            encoding = face_recognition.face_encodings(frame, [box_recog])[0]
            FaceDB.append(name, encoding)

            face_crop = frame[int(box.ymin):int(box.ymax) + 1, int(box.xmin):int(box.xmax)+1]

            # Apply data augmentation
            augmented_images = next(augmenter.flow(np.array([face_crop] * n_augmented_images_per_frame), batch_size=n_augmented_images_per_frame))
            for face in augmented_images:
                face = face.astype(np.uint8)
                shape = (0, face.shape[1] - 1, face.shape[0] - 1, 0)
                encoding = face_recognition.face_encodings(face, [shape])[0]
                FaceDB.append(name, encoding)

        self.logger.info('Encoder stopped')


    def stop(self):
        self.stopped.set()
        if self._thread_record is not None and self._thread_record.is_alive():
            self._thread_record.join()
        # Don't wait for _thread_encoder to avoid blocking. 
        # It will end itself when it finishes calculating embeddings

        
class PresenceDetector(CameraService):
    def __init__(self, callback, model_path='services/presence_detector/efficientdet_lite1.tflite', 
                    num_threads=1) -> None:
        super().__init__()

        self.callback = callback
        self.stopped = Event()
        self._thread = None

        self.detection_count = 0 # Number of consecutive presence detected frames

        # Initialize the object detection model
        self.detector = ObjectDetector(
            model_path = model_path,
            num_threads = num_threads,
            score_threshold = 0.3,
            objects_to_detect_id= [0] # 0 id means 'person'
        )

        self.logger.info('Ready')
    
    def start(self):
        self.detection_count = 0  # Reset counter at start
        self.stopped.clear()
        self._thread = Thread(target=self._run)
        self._thread.start()
    
    def _run(self):
        self.logger.info('Started')

        CameraService.camera.start(self.__class__.__name__)
        fps = FPS().start()

        while not self.stopped.is_set():
            frame = CameraService.camera.get_color_frame(resize_width=500)

            (h, w) = frame.shape[:2]
            if h * w == 0: # Check if image has 0 size
                continue

            # Run presence detection using the model
            detections = self.detector.detect(frame)

            if detections:
                self.detection_count += 1

                if self.detection_count >= 3: # 3 consecutive frames with presence detected
                    self.callback('person_detected')
                    self.detection_count = 0 # Reset counter

            else:
                self.detection_count = 0
                self.callback('empty_room')
            
            fps.update()

        fps.stop()
        self.logger.info(f"FPS: {fps.fps():.4f} (elapsed time: {fps.elapsed():.4f} s)")



    def stop(self):
        self.stopped.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join()
        
        CameraService.camera.stop(self.__class__.__name__)
        self.detection_count = 0  # Reset counter at stop

        self.logger.info('Stopped')
