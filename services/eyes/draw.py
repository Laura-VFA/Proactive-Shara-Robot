import cv2
import numpy as np

from .utils import draw_bezier, get_bezier_points, get_face_from_file


def draw_face(face_points, width=1080, height=1920):
    # Create a blank canvas 
    canvas = np.full((width, height, 3), 255, np.uint8)
    
    for side in ['left', 'right']:

        # Draw eyebrow
        eyebrow_pts = face_points['eyebrows'][side]
        canvas = draw_bezier(canvas, eyebrow_pts, (0,0,0), 5)

        # Get eye contour
        g_eye_center = np.array(face_points['eyes'][side]['center'])
        eye_axes = np.array([face_points['eyes'][side]['width']//2, face_points['eyes'][side]['height']//2])

        # Get eye region to draw the eye locally
        reg_offset = np.array([5, 5]) # Incrementation of the countour, for getting correct line thickness 
        eye_region = canvas[
            g_eye_center[1]- eye_axes[1] - reg_offset[1]: g_eye_center[1]+ eye_axes[1] + reg_offset[0], 
            g_eye_center[0]- eye_axes[0] - reg_offset[1]: g_eye_center[0]+ eye_axes[0] + reg_offset[0]
        ].copy()

        l_eye_center = eye_axes + reg_offset
        cv2.ellipse(eye_region, l_eye_center, eye_axes, 0, 0, 360, (0, 0, 0), 7, lineType=cv2.LINE_AA)

        # Draw the pupil and the iris
        pupil_center = l_eye_center + np.array(face_points['eyes'][side]['pupil']['offset'])
        pupil_axes = (face_points['eyes'][side]['pupil']['width']//2, face_points['eyes'][side]['pupil']['height']//2)
        iris_center = pupil_center + np.array(face_points['eyes'][side]['iris']['offset'])
        iris_axes = (face_points['eyes'][side]['iris']['width']//2, face_points['eyes'][side]['iris']['height']//2)
        cv2.ellipse(eye_region, iris_center, iris_axes, 0, 0, 360, face_points['eyes'][side]['iris']['color'], cv2.FILLED, lineType=cv2.LINE_AA)
        cv2.ellipse(eye_region, pupil_center, pupil_axes, 0, 0, 360, (0,0,0), cv2.FILLED, lineType=cv2.LINE_AA)

        # Create the mask eye for the eye lid
        eyelid_top_pts = [l_eye_center + np.array(pos) for pos in face_points['eyes'][side]['eyelid_top']]
        mask_lid_top = np.full(eye_region.shape[:2], 255, np.uint8)
        mask_lid_top_pts = [[0,0], *get_bezier_points(eyelid_top_pts),[eye_region.shape[1],0]]
        mask_lid_top = cv2.fillPoly(mask_lid_top, pts = [np.array(mask_lid_top_pts, dtype=np.int32)], color=0)

        eyelid_bottom_pts = [l_eye_center + np.array(pos) for pos in face_points['eyes'][side]['eyelid_bottom']]
        mask_lid_bottom = np.full(eye_region.shape[:2], 255, np.uint8)
        mask_lid_bottom_pts = [[0,eye_region.shape[0]], *get_bezier_points(eyelid_bottom_pts),[eye_region.shape[1],eye_region.shape[0]]]
        mask_lid_bottom = cv2.fillPoly(mask_lid_bottom, pts = [np.array(mask_lid_bottom_pts, dtype=np.int32)], color=0)

        mask_eye = np.zeros_like(mask_lid_top)
        mask_eye = cv2.ellipse(mask_eye, l_eye_center, eye_axes, 0, 0, 360, 255, cv2.FILLED, lineType=cv2.LINE_AA)

        mask_eye_contour = np.zeros_like(mask_lid_top)
        mask_eye_contour = cv2.ellipse(mask_eye_contour, l_eye_center, eye_axes, 0, 0, 360, 255, thickness=7, lineType=cv2.LINE_AA)
        mask_eye_contour = draw_bezier(mask_eye_contour, eyelid_bottom_pts, 255, 7)
        
        mask_lid = cv2.bitwise_or(mask_lid_top, mask_eye_contour)
        mask_lid = cv2.bitwise_and(mask_lid_bottom, mask_lid)
        mask_lid = cv2.bitwise_and(mask_lid, mask_eye)

        # Draw the eye lid lines (top and bottom)
        eye_region = draw_bezier(eye_region, eyelid_top_pts, (0,0,0), 7)
        eye_region = draw_bezier(eye_region, eyelid_bottom_pts, (0,0,0), 7)

        # Copy the eye region in the original face
        cv2.copyTo(eye_region, mask=mask_lid, dst=canvas[
            g_eye_center[1]- eye_axes[1] - reg_offset[1]: g_eye_center[1]+ eye_axes[1] + reg_offset[0], 
            g_eye_center[0]- eye_axes[0] - reg_offset[1]: g_eye_center[0]+ eye_axes[0] + reg_offset[0]
        ])

    return canvas

def draw_face_from_file(filename: str):  
    return draw_face(get_face_from_file(filename))
