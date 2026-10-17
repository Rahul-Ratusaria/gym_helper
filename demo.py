"""Synthetic input for presentations; never presented as measured camera data."""
from math import cos, sin, pi, radians


def demo_pose(exercise, seconds, side="left"):
    coords = {
        0: (.48, .15), 11: (.46, .28), 12: (.54, .28),
        13: (.45, .45), 14: (.57, .45), 15: (.44, .61), 16: (.58, .61),
        23: (.47, .55), 24: (.53, .55), 25: (.44, .73), 26: (.57, .73),
        27: (.42, .92), 28: (.59, .92), 29: (.40, .94), 30: (.58, .94),
        31: (.46, .94), 32: (.64, .94),
    }
    low = 35 if exercise == "curl" else 75
    angle = low + (175 - low) * (1 + cos(seconds * 2 * pi / 4.8)) / 2
    offset = 0 if side == "left" else 1
    a, b, c = (23, 25, 27) if exercise in ("squat", "lunge") else (11, 13, 15)
    # In 16:9 pixel space, rotate the segment to match the intended angle.
    origin = coords[b + offset]
    coords[a + offset] = (origin[0], coords[a + offset][1])
    coords[c + offset] = (origin[0] + sin(radians(angle)) * .17 * 9 / 16,
                          origin[1] - cos(radians(angle)) * .17)
    points = [(0, 0, 0, 0)] * 33
    for index, (x, y) in coords.items():
        points[index] = (x, y, 0, .99)
    return points
