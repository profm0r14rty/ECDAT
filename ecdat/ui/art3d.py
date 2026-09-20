"""Pure ASCII 3D renderers — deterministic, dependency-free, unit-testable."""
from __future__ import annotations

import math

Cell = tuple[str, int]        # (character, level) — level 0 means "empty"
Frame = list[list[Cell]]      # frame[row][col]

BLANK: Cell = (" ", 0)
TORUS_CHARS = ".,-~:;=!*#$@"  # 12 shades, dark -> bright
TORUS_LEVELS = len(TORUS_CHARS)
GLOBE_LEVELS = 12
HEX = "0123456789ABCDEF"


def blank_frame(width: int, height: int) -> Frame:
    return [[BLANK] * max(width, 0) for _ in range(max(height, 0))]


def frame_to_rows(frame: Frame) -> list[str]:
    return ["".join(ch for ch, _ in row) for row in frame]


def render_torus(a: float, b: float, width: int, height: int, *,
                 step_theta: float = 0.07, step_phi: float = 0.04) -> Frame:
    """Classic spinning donut. a, b are rotation angles in radians."""
    frame = blank_frame(width, height)
    if width < 8 or height < 4:
        return frame
    r1, r2, k2 = 1.0, 2.0, 5.0
    k1 = min(width, 2 * height) * k2 * 3.0 / (8.0 * (r1 + r2))
    zbuf = [[0.0] * width for _ in range(height)]
    ca, sa, cb, sb = math.cos(a), math.sin(a), math.cos(b), math.sin(b)
    two_pi = 2.0 * math.pi
    theta = 0.0
    while theta < two_pi:
        ct, st = math.cos(theta), math.sin(theta)
        circle_x, circle_y = r2 + r1 * ct, r1 * st
        phi = 0.0
        while phi < two_pi:
            cp, sp = math.cos(phi), math.sin(phi)
            x = circle_x * (cb * cp + sa * sb * sp) - circle_y * ca * sb
            y = circle_x * (sb * cp - sa * cb * sp) + circle_y * ca * cb
            z = k2 + ca * circle_x * sp + circle_y * sa
            ooz = 1.0 / z
            xp = int(width / 2 + k1 * ooz * x)
            yp = int(height / 2 - k1 * ooz * y * 0.5)      # 0.5 = terminal cell aspect ratio
            if 0 <= xp < width and 0 <= yp < height and ooz > zbuf[yp][xp]:
                lum = cp * ct * sb - ca * ct * sp - sa * st + cb * (ca * st - ct * sa * sp)
                if lum > 0:
                    idx = min(int(lum * 8), TORUS_LEVELS - 1)
                    zbuf[yp][xp] = ooz
                    frame[yp][xp] = (TORUS_CHARS[idx], idx + 1)
            phi += step_phi
        theta += step_theta
    return frame


def _star(col: int, row: int, t: float) -> Cell | None:
    h = (col * 73856093) ^ (row * 19349663)
    if h % 61 != 0:
        return None
    phase = (int(t * 2.5) + (h >> 7)) % 3
    return (".", 1) if phase == 0 else (("+", 2) if phase == 1 else ("'", 1))


def render_globe(t: float, width: int, height: int, *, ring: bool = True, stars: bool = True) -> Frame:
    """A sphere whose surface is hex digits glued to it (they rotate with t), lit from the upper-left,
    with a lat/long grid, an orbit ring precessing around it and three satellites."""
    frame = blank_frame(width, height)
    if width < 16 or height < 8:
        return frame
    cx, cy = (width - 1) / 2.0, (height - 1) / 2.0
    rx = min(width / 2.8, height * 0.85)                   # sphere radius in x-cells; y radius = rx / 2
    lx, ly, lz = -0.45, 0.55, 0.70
    n = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / n, ly / n, lz / n
    ct, st = math.cos(t), math.sin(t)
    two_pi = 2.0 * math.pi
    for row in range(height):
        ny = -(row - cy) * 2.0 / rx
        for col in range(width):
            nx = (col - cx) / rx
            d2 = nx * nx + ny * ny
            if d2 > 1.0:
                if stars:
                    s = _star(col, row, t)
                    if s:
                        frame[row][col] = s
                continue
            nz = math.sqrt(1.0 - d2)
            shade = 0.12 + 0.78 * max(0.0, nx * lx + ny * ly + nz * lz) + 0.25 * (1.0 - nz) ** 2
            level = max(1, min(GLOBE_LEVELS, 1 + int(shade * (GLOBE_LEVELS - 1))))
            sx = nx * ct - nz * st
            sz = nx * st + nz * ct
            lon = math.atan2(sx, sz)
            lat = math.asin(max(-1.0, min(1.0, ny)))
            qi = int((lon + math.pi) / two_pi * 96) % 96
            qj = min(int((lat + math.pi / 2) / math.pi * 48), 47)
            grid = qi % 12 == 0 or qj % 8 == 0
            if level <= 2:
                ch = "."
            elif level <= 4:
                ch = "+" if grid else ":"
            else:
                ch = HEX[(((qi * 73856093) ^ (qj * 19349663)) >> 3) % 16]
            frame[row][col] = (ch, min(GLOBE_LEVELS, level + (1 if grid else 0)))
    if ring:
        cr, sr = math.cos(0.42), math.sin(0.42)            # ring tilt about X
        yaw = t * 1.7 + 0.6
        cyw, syw = math.cos(yaw), math.sin(yaw)            # ring precession about Y
        rr = 1.28 * rx

        def project(phi: float) -> tuple[int, int, bool]:
            px, py, pz = math.cos(phi), 0.0, math.sin(phi)
            py, pz = py * cr - pz * sr, py * sr + pz * cr
            px, pz = px * cyw + pz * syw, -px * syw + pz * cyw
            return int(round(cx + px * rr)), int(round(cy - py * rr / 2.0)), pz > 0

        def visible(col: int, row: int, front: bool) -> bool:
            if not (0 <= col < width and 0 <= row < height):
                return False
            if front:
                return True
            dx, dy = (col - cx) / rx, (row - cy) * 2.0 / rx
            return dx * dx + dy * dy > 1.0                 # behind the globe: hidden where the disc covers it

        for i in range(240):
            col, row, front = project(two_pi * i / 240)
            if visible(col, row, front):
                frame[row][col] = ("o", GLOBE_LEVELS) if front else (".", 5)
        for k in range(3):                                  # satellites
            col, row, front = project(t * 2.2 + k * 2.0944)
            if visible(col, row, front):
                frame[row][col] = ("@", GLOBE_LEVELS)
    return frame
