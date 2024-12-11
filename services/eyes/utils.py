import json

import cv2
import numpy as np


def get_face_from_file(filename: str) -> dict:
    with open(filename, 'r') as f:
        face_points = json.load(f)
    
    return face_points

def make_bezier(xys):
    """Code extracted from: https://stackoverflow.com/questions/246525/how-can-i-draw-a-bezier-curve-using-pythons-pil"""

    # xys should be a sequence of 2-tuples (Bezier control points)
    n = len(xys)
    combinations = pascal_row(n-1)
    def bezier(ts):
        # This uses the generalized formula for bezier curves
        # http://en.wikipedia.org/wiki/B%C3%A9zier_curve#Generalization
        result = []
        for t in ts:
            tpowers = (t**i for i in range(n))
            upowers = reversed([(1-t)**i for i in range(n)])
            coefs = [c*a*b for c, a, b in zip(combinations, tpowers, upowers)]
            result.append(
                tuple(sum([coef*p for coef, p in zip(coefs, ps)]) for ps in zip(*xys)))
        return result
    return bezier

def pascal_row(n, memo={}):
    """Code extracted from: https://stackoverflow.com/questions/246525/how-can-i-draw-a-bezier-curve-using-pythons-pil"""
    # This returns the nth row of Pascal's Triangle
    if n in memo:
        return memo[n]
    result = [1]
    x, numerator = 1, n
    for denominator in range(1, n//2+1):
        # print(numerator,denominator,x)
        x *= numerator
        x /= denominator
        result.append(x)
        numerator -= 1
    if n&1 == 0:
        # n is even
        result.extend(reversed(result[:-1]))
    else:
        result.extend(reversed(result))
    memo[n] = result
    return result

def get_bezier_points(points: list, resolution=100) -> list:
    bezier = make_bezier(points)
    return bezier([t/resolution for t in range(resolution+1)])  # Steps of interpolation (100 steps by default)
    
def draw_bezier(img, points, color, thickness, lineType=cv2.LINE_AA, resolution=100):
    points = get_bezier_points(points, resolution)
    return cv2.polylines(img, [np.array(points).reshape((-1, 1, 2)).astype(np.int32)], False, color, thickness, lineType)
