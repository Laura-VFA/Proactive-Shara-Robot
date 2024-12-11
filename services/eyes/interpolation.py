import copy
import math


def get_in_between_faces(origin_face, target_face, steps=2) -> list:
    
    origin_points_list = dictface_to_list(origin_face)
    target_points_list = dictface_to_list(target_face)

    # Interpolate all corresponding points between both faces
    interpolated_points = []
    for a,b in zip(origin_points_list, target_points_list):
        interpolated_points.append(interpolate_points(a, b, steps))
        
    return list_to_dictfaces(interpolated_points, steps, target_face)

def get_module(vector) -> float:
    return math.sqrt(vector[0]*vector[0] + vector[1]*vector[1])

def dictface_to_list(dic) -> list:
    points = []
    points.extend(dic['eyebrows']['left'])
    points.extend(dic['eyebrows']['right'])

    points.append(dic['eyes']['left']['center'])
    points.append([dic['eyes']['left']['width'], dic['eyes']['left']['height']])
    points.append(dic['eyes']['left']['pupil']['offset'])
    points.append([dic['eyes']['left']['pupil']['width'], dic['eyes']['left']['pupil']['height']])
    points.append(dic['eyes']['left']['iris']['offset'])
    points.append([dic['eyes']['left']['iris']['width'], dic['eyes']['left']['iris']['height']])
    points.extend(dic['eyes']['left']['eyelid_top'])
    points.extend(dic['eyes']['left']['eyelid_bottom'])

    points.append(dic['eyes']['right']['center'])
    points.append([dic['eyes']['right']['width'], dic['eyes']['right']['height']])
    points.append(dic['eyes']['right']['pupil']['offset'])
    points.append([dic['eyes']['right']['pupil']['width'], dic['eyes']['right']['pupil']['height']])
    points.append(dic['eyes']['right']['iris']['offset'])
    points.append([dic['eyes']['right']['iris']['width'], dic['eyes']['right']['iris']['height']])
    points.extend(dic['eyes']['right']['eyelid_top'])
    points.extend(dic['eyes']['right']['eyelid_bottom'])


    return points

def list_to_dictfaces(list_points: list, steps: int, base_dict: dict) -> list:
    in_between_faces = []
    for i in range(steps):
        face_dict = copy.deepcopy(base_dict)
        face_dict['eyebrows']['left'] = [elem[i] for elem in list_points[0:3]]
        face_dict['eyebrows']['right'] = [elem[i] for elem in list_points[3:6]]

        face_dict['eyes']['left']['center'] = list_points[6][i]
        face_dict['eyes']['left']['width'] = list_points[7][i][0]
        face_dict['eyes']['left']['height'] = list_points[7][i][1]
        face_dict['eyes']['left']['pupil']['offset'] = list_points[8][i]
        face_dict['eyes']['left']['pupil']['width'] = list_points[9][i][0]
        face_dict['eyes']['left']['pupil']['height'] = list_points[9][i][1]
        face_dict['eyes']['left']['iris']['offset'] = list_points[10][i]
        face_dict['eyes']['left']['iris']['width'] = list_points[11][i][0]
        face_dict['eyes']['left']['iris']['height'] = list_points[11][i][1]
        face_dict['eyes']['left']['eyelid_top'] = [elem[i] for elem in list_points[12:15]]
        face_dict['eyes']['left']['eyelid_bottom'] = [elem[i] for elem in list_points[15:18]]

        face_dict['eyes']['right']['center'] = list_points[18][i]
        face_dict['eyes']['right']['width'] = list_points[19][i][0]
        face_dict['eyes']['right']['height'] = list_points[19][i][1]
        face_dict['eyes']['right']['pupil']['offset'] = list_points[20][i]
        face_dict['eyes']['right']['pupil']['width'] = list_points[21][i][0]
        face_dict['eyes']['right']['pupil']['height'] = list_points[21][i][1]
        face_dict['eyes']['right']['iris']['offset'] = list_points[22][i]
        face_dict['eyes']['right']['iris']['width'] = list_points[23][i][0]
        face_dict['eyes']['right']['iris']['height'] = list_points[23][i][1]
        face_dict['eyes']['right']['eyelid_top'] = [elem[i] for elem in list_points[24:27]]
        face_dict['eyes']['right']['eyelid_bottom'] = [elem[i] for elem in list_points[27:]]

        in_between_faces.append(face_dict)
    
    return in_between_faces

def interpolate_points(a, b, steps: int) -> list:
    interpolated_points = []

    if a == b:
        return [a] * steps

    vector = [b[0] - a[0], b[1] - a[1]] # Get the ab vector
    module = get_module(vector)
    unitary = [vector[0] / module, vector[1] / module] # Obtain the unitary vector

    module = module / (steps + 1) # Divide the distance between a and b in 'steps' fragments
    displacement_vector = [unitary[0] * module, unitary[1] * module] # Displacement to apply each time

    for index in range(1, steps + 1):
        new_point = [int(a[0] + displacement_vector[0] * index), int(a[1] + displacement_vector[1] * index)]
        interpolated_points.append(new_point)
    
    return interpolated_points
