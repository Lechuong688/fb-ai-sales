import math


def tile_windows(profiles, x, y, width, height):
    """Return evenly sized window bounds for profiles in stable order."""
    profiles = list(profiles)
    count = len(profiles)
    if not count or width <= 0 or height <= 0:
        return {}

    if count <= 3:
        columns = count
    else:
        columns = min(count, max(1, round(math.sqrt(count * width / height))))
    rows = math.ceil(count / columns)

    bounds = {}
    for index, profile in enumerate(profiles):
        row, column = divmod(index, columns)
        left = x + column * width // columns
        top = y + row * height // rows
        right = x + (column + 1) * width // columns
        bottom = y + (row + 1) * height // rows
        bounds[profile] = {
            "x": left,
            "y": top,
            "width": right - left,
            "height": bottom - top,
            "maximized": count == 1,
        }
    return bounds
