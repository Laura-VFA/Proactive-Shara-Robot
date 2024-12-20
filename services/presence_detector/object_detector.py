import tensorflow as tf
import numpy as np
import cv2

class ObjectDetector:
    def __init__(self, model_path, num_threads=1, score_threshold=0.3, objects_to_detect_id=None):
        if objects_to_detect_id is None:
            objects_to_detect_id = [0]  # Default to detect persons if not provided

        self.score_threshold = score_threshold
        self.objects_to_detect_id = objects_to_detect_id

        # Load the TFLite model
        self.interpreter = tf.lite.Interpreter(model_path=model_path, num_threads=num_threads)
        self.interpreter.allocate_tensors()

        # Get input and output details
        self.input_details = self.interpreter.get_input_details()
        self.output_details = self.interpreter.get_output_details()
        self.input_shape = self.input_details[0]['shape']

    def preprocess_image(self, frame):
        resized_frame = cv2.resize(frame, (self.input_shape[1], self.input_shape[2]))
        return resized_frame.astype(np.uint8)  # Ensure frame is uint8

    def detect(self, frame):
        # Preprocess the frame for the model
        input_tensor = self.preprocess_image(frame)

        # Set the input tensor
        self.interpreter.set_tensor(self.input_details[0]['index'], np.expand_dims(input_tensor, axis=0))

        # Run inference
        self.interpreter.invoke()

        # Get detection results
        classes = self.interpreter.get_tensor(self.output_details[1]['index'])[0]  # Class index
        scores = self.interpreter.get_tensor(self.output_details[2]['index'])[0]  # Confidence scores

        # Filter results based on score threshold and target object IDs
        detections = [
            (int(classes[i]), scores[i])
            for i in range(len(scores))
            if scores[i] > self.score_threshold and int(classes[i]) in self.objects_to_detect_id
        ]

        # Return filtered detections
        return detections