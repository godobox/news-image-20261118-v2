#!/usr/bin/env python3
"""World news in one image -- Wednesday 18 November 2026 (v2, broadsheet).

Draws a 1024x1024 one-page news broadsheet with nothing but the Python
standard library: a hand-built vector stroke font, code-drawn icons and a
code-drawn world map, and a small PNG encoder. No network, no clock, no
randomness: two runs give byte-identical output.

Writes entry.png into $MAKEFUN_OUTPUT_DIR (default /output).
Set MAKEFUN_TEST=font to render a font specimen instead.
"""

import math
import os
import struct
import zlib

W = H = 1024

# --------------------------------------------------------------------------
# Colours
# --------------------------------------------------------------------------

PAPER = (247, 243, 234)
INK = (26, 26, 26)
MUTED = (92, 92, 92)
NAVY = (20, 33, 61)
NAVY2 = (28, 46, 84)
GOLD = (201, 162, 39)
GOLD_LT = (232, 205, 120)
WHITE = (255, 255, 255)
CARD = (255, 255, 255)
BORDER = (216, 210, 196)
RED = (192, 57, 43)
BLUE = (46, 111, 183)
ORANGE = (224, 120, 64)
PURPLE = (122, 79, 163)
GREEN = (30, 122, 76)
TEAL = (31, 138, 138)
GREY = (90, 90, 90)
SEA = (198, 222, 235)
LAND = (196, 214, 176)


def rgb(c):
    return (c[0], c[1], c[2])


# --------------------------------------------------------------------------
# Canvas
# --------------------------------------------------------------------------

class Canvas:
    def __init__(self, w, h, bg):
        self.w = w
        self.h = h
        self.px = bytearray(bytes(bg) * (w * h))

    def blend(self, x, y, color, a):
        if a <= 0 or x < 0 or y < 0 or x >= self.w or y >= self.h:
            return
        i = (y * self.w + x) * 3
        p = self.px
        if a >= 1:
            p[i] = color[0]
            p[i + 1] = color[1]
            p[i + 2] = color[2]
            return
        b = 1.0 - a
        p[i] = int(p[i] * b + color[0] * a + 0.5)
        p[i + 1] = int(p[i + 1] * b + color[1] * a + 0.5)
        p[i + 2] = int(p[i + 2] * b + color[2] * a + 0.5)

    def rect(self, x0, y0, x1, y1, color):
        x0 = max(0, int(x0))
        y0 = max(0, int(y0))
        x1 = min(self.w, int(x1))
        y1 = min(self.h, int(y1))
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for y in range(y0, y1):
            i = (y * self.w + x0) * 3
            self.px[i:i + len(row)] = row

    def hline(self, x0, x1, y, color, t=1):
        self.rect(x0, y, x1, y + t, color)

    def vline(self, x, y0, y1, color, t=1):
        self.rect(x, y0, x + t, y1, color)

    def disc(self, cx, cy, r, color, a=1.0):
        r = float(r)
        x0 = max(0, int(cx - r - 1))
        x1 = min(self.w - 1, int(cx + r + 1))
        y0 = max(0, int(cy - r - 1))
        y1 = min(self.h - 1, int(cy + r + 1))
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                cov = min(1.0, max(0.0, r + 0.6 - d))
                if cov > 0:
                    self.blend(x, y, color, a * cov)

    def _seg_dist(self, px, py, x0, y0, x1, y1):
        dx = x1 - x0
        dy = y1 - y0
        L2 = dx * dx + dy * dy
        if L2 == 0:
            return math.hypot(px - x0, py - y0)
        t = ((px - x0) * dx + (py - y0) * dy) / L2
        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
        return math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))

    def stroke_seg(self, x0, y0, x1, y1, color, half_w):
        """Anti-aliased thick segment, distance based."""
        pad = half_w + 1.2
        bx0 = max(0, int(min(x0, x1) - pad))
        bx1 = min(self.w - 1, int(max(x0, x1) + pad))
        by0 = max(0, int(min(y0, y1) - pad))
        by1 = min(self.h - 1, int(max(y0, y1) + pad))
        for y in range(by0, by1 + 1):
            for x in range(bx0, bx1 + 1):
                d = self._seg_dist(x + 0.5, y + 0.5, x0, y0, x1, y1)
                cov = min(1.0, max(0.0, (half_w + 0.7 - d) / 1.0))
                if cov > 0:
                    self.blend(x, y, color, cov)

    def polyline(self, pts, color, width, closed=False):
        hw = width / 2.0
        n = len(pts)
        if n < 2:
            if n == 1:
                self.disc(pts[0][0], pts[0][1], hw, color)
            return
        for i in range(n - 1):
            self.stroke_seg(pts[i][0], pts[i][1], pts[i + 1][0],
                            pts[i + 1][1], color, hw)
        if closed:
            self.stroke_seg(pts[-1][0], pts[-1][1], pts[0][0], pts[0][1],
                            color, hw)
        for (x, y) in pts:
            self.disc(x, y, hw * 0.7, color)

    def fill_poly(self, pts, color):
        """Even-odd scanline polygon fill."""
        if len(pts) < 3:
            return
        ys = [p[1] for p in pts]
        y0 = max(0, int(min(ys)))
        y1 = min(self.h - 1, int(max(ys)) + 1)
        n = len(pts)
        for y in range(y0, y1 + 1):
            yc = y + 0.5
            xs = []
            for i in range(n):
                x0, yy0 = pts[i]
                x1, yy1 = pts[(i + 1) % n]
                if (yy0 <= yc < yy1) or (yy1 <= yc < yy0):
                    t = (yc - yy0) / (yy1 - yy0)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                xa = max(0, int(xs[k]))
                xb = min(self.w, int(xs[k + 1]) + 1)
                if xb > xa:
                    row = bytes(color) * (xb - xa)
                    i = (y * self.w + xa) * 3
                    self.px[i:i + len(row)] = row

    def blit(self, bmp, bw, bh, ox, oy, color):
        """Blit a greyscale-alpha bitmap in the given colour."""
        for yy in range(bh):
            y = oy + yy
            if y < 0 or y >= self.h:
                continue
            base = yy * bw
            row0 = y * self.w * 3
            for xx in range(bw):
                a = bmp[base + xx] / 255.0
                if a <= 0:
                    continue
                x = ox + xx
                if x < 0 or x >= self.w:
                    continue
                self.blend(x, y, color, a)


# --------------------------------------------------------------------------
# PNG encoder (filter Up, zlib level 9)
# --------------------------------------------------------------------------

def _chunk(typ, data):
    c = struct.pack(">I", len(data)) + typ + data
    c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return c


def write_png(path, px, w, h):
    raw = bytearray()
    prev = bytes(w * 3)
    for y in range(h):
        row = bytes(px[y * w * 3:(y + 1) * w * 3])
        raw.append(2)
        raw.extend(bytes((a - b) & 255 for a, b in zip(row, prev)))
        prev = row
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    data = b"\x89PNG\r\n\x1a\n"
    data += _chunk(b"IHDR", ihdr)
    data += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += _chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(data)


# --------------------------------------------------------------------------
# Vector stroke font.
# Grid: x 0..6, y 0..10. Baseline y=8, cap top y=0, x-height top y=2.5,
# descender bottom y=10. Each glyph is a list of strokes; a stroke is a
# list of (x, y) points. A one-point stroke draws a dot.
# --------------------------------------------------------------------------

FONT = {
    "A": [[(0, 8), (3, 0), (6, 8)], [(1.5, 5), (4.5, 5)]],
    "B": [[(0, 8), (0, 0), (4, 0), (5.5, 1.5), (4, 3), (0, 3)],
          [(0, 3), (4, 3), (5.5, 4.5), (5, 6.5), (4, 8), (0, 8)]],
    "C": [[(5.5, 2), (4, 0), (1.5, 0), (0, 2), (0, 6), (1.5, 8), (4, 8), (5.5, 6)]],
    "D": [[(0, 8), (0, 0), (4, 0), (6, 2), (6, 6), (4, 8), (0, 8)]],
    "E": [[(5, 0), (0, 0), (0, 8), (5, 8)], [(0, 4), (3.5, 4)]],
    "F": [[(0, 8), (0, 0), (5, 0)], [(0, 4), (3.5, 4)]],
    "G": [[(5.5, 2), (4, 0), (1.5, 0), (0, 2), (0, 6), (1.5, 8), (4, 8),
           (5.5, 6), (5.5, 4), (3.5, 4)]],
    "H": [[(0, 0), (0, 8)], [(6, 0), (6, 8)], [(0, 4), (6, 4)]],
    "I": [[(3, 0), (3, 8)], [(1, 0), (5, 0)], [(1, 8), (5, 8)]],
    "J": [[(5, 0), (5, 6), (4, 8), (2, 8), (1, 6.5)]],
    "K": [[(0, 0), (0, 8)], [(5.5, 0), (1, 4)], [(2, 4.5), (5.5, 8)]],
    "L": [[(0, 0), (0, 8), (5.5, 8)]],
    "M": [[(0, 8), (0, 0), (3, 4.5), (6, 0), (6, 8)]],
    "N": [[(0, 8), (0, 0), (6, 8), (6, 0)]],
    "O": [[(4.5, 0), (1.5, 0), (0, 2), (0, 6), (1.5, 8), (4.5, 8),
           (6, 6), (6, 2), (4.5, 0)]],
    "P": [[(0, 8), (0, 0), (4, 0), (5.5, 1.5), (4, 3.5), (0, 3.5)]],
    "Q": [[(4.5, 0), (1.5, 0), (0, 2), (0, 6), (1.5, 8), (4.5, 8),
           (6, 6), (6, 2), (4.5, 0)], [(4, 5.5), (6.5, 9)]],
    "R": [[(0, 8), (0, 0), (4, 0), (5.5, 1.5), (4, 3.5), (0, 3.5)],
          [(2.5, 3.5), (6, 8)]],
    "S": [[(5, 1.5), (4, 0), (2, 0), (0.5, 1.5), (1, 3.5), (3, 4.5),
           (5, 5), (5.5, 6.5), (4, 8), (2, 8), (0.5, 6.5)]],
    "T": [[(0, 0), (6, 0)], [(3, 0), (3, 8)]],
    "U": [[(0, 0), (0, 6), (1.5, 8), (4.5, 8), (6, 6), (6, 0)]],
    "V": [[(0, 0), (3, 8), (6, 0)]],
    "W": [[(0, 0), (1.5, 8), (3, 4), (4.5, 8), (6, 0)]],
    "X": [[(0, 0), (6, 8)], [(6, 0), (0, 8)]],
    "Y": [[(0, 0), (3, 4), (6, 0)], [(3, 4), (3, 8)]],
    "Z": [[(0, 0), (6, 0), (0, 8), (6, 8)]],
    "a": [[(5, 3), (3.5, 2.5), (1.5, 2.5), (0, 4), (0, 6), (1.5, 8),
           (3.5, 8), (5, 6.5), (5, 4.5)], [(5.5, 2.5), (5.5, 8)]],
    "b": [[(0, 0), (0, 8)],
          [(0, 4.5), (2.5, 2.5), (4.5, 3.5), (4.5, 6), (2.5, 8), (0, 8)]],
    "c": [[(5, 4), (4, 2.5), (1.5, 2.5), (0, 4), (0, 6), (1.5, 8), (4, 8), (5, 6.5)]],
    "d": [[(6, 0), (6, 8)],
          [(6, 5), (3.5, 2.5), (1.5, 3.5), (1.5, 6), (3.5, 8), (6, 8)]],
    "e": [[(5.5, 6), (5, 8), (2.5, 8), (0.5, 6), (0.5, 4), (2, 2.5),
           (4.5, 2.5), (5.5, 4), (5.5, 5), (0.5, 5)]],
    "f": [[(4.5, 8), (4.5, 2.5), (3, 0), (1.5, 0.5)], [(0.5, 4.5), (5, 4.5)]],
    "g": [[(5.5, 4), (4, 2.5), (1.5, 2.5), (0, 4), (0, 6), (1.5, 8),
           (4, 8), (5.5, 6.5)],
          [(5.5, 6.5), (5.5, 8), (4, 10), (2, 10), (1, 9)]],
    "h": [[(0, 0), (0, 8)], [(0, 5), (2, 2.5), (4, 2.5), (5.5, 4), (5.5, 8)]],
    "i": [[(3, 2.5), (3, 8)], [(3, 0.5)]],
    "j": [[(4.5, 2.5), (4.5, 8), (3.5, 10), (2, 10)], [(4.5, 0.5)]],
    "k": [[(0, 0), (0, 8)], [(5, 2.5), (1, 5)], [(2.5, 5.5), (5, 8)]],
    "l": [[(2.5, 0), (2.5, 8)], [(2.5, 8), (4, 8)]],
    "m": [[(0, 8), (0, 2.5), (1.5, 2.5), (3, 4), (3, 8)],
          [(3, 4), (3.5, 2.5), (5, 2.5), (6, 4), (6, 8)]],
    "n": [[(0, 8), (0, 2.5), (2, 2.5), (4, 2.5), (5.5, 4), (5.5, 8)]],
    "o": [[(4, 2.5), (1.5, 2.5), (0, 4), (0, 6), (1.5, 8), (4, 8),
           (5.5, 6), (5.5, 4), (4, 2.5)]],
    "p": [[(0, 2.5), (0, 10)],
          [(0, 5), (2.5, 2.5), (4.5, 3.5), (4.5, 6), (2.5, 8), (0, 8)]],
    "q": [[(6, 2.5), (6, 10)],
          [(6, 5), (3.5, 2.5), (1.5, 3.5), (1.5, 6), (3.5, 8), (6, 8)]],
    "r": [[(0, 8), (0, 2.5), (2, 2.5), (4, 2.5), (5, 3.5)]],
    "s": [[(5, 3.5), (4, 2.5), (2, 2.5), (0.5, 4), (1, 5.5), (3, 6),
           (5, 6.5), (5, 7), (3.5, 8), (1.5, 8), (0.5, 7)]],
    "t": [[(3.5, 0), (3.5, 8)], [(1, 3.5), (5, 3.5)], [(3.5, 8), (5, 8)]],
    "u": [[(0, 2.5), (0, 6), (1.5, 8), (4, 8), (5.5, 6), (5.5, 2.5)]],
    "v": [[(0, 2.5), (2.5, 8), (5.5, 2.5)]],
    "w": [[(0, 2.5), (1.5, 8), (3, 5), (4.5, 8), (6, 2.5)]],
    "x": [[(0, 2.5), (5.5, 8)], [(5.5, 2.5), (0, 8)]],
    "y": [[(0, 2.5), (2.5, 6), (5.5, 2.5)],
          [(2.5, 6), (2.5, 8), (1.5, 10), (0.5, 10)]],
    "z": [[(0, 2.5), (5.5, 2.5), (0, 8), (5.5, 8)]],
    "0": [[(4.5, 0), (1.5, 0), (0, 2), (0, 6), (1.5, 8), (4.5, 8),
           (6, 6), (6, 2), (4.5, 0)], [(1.5, 2.5), (4.5, 6)]],
    "1": [[(1.5, 2), (3, 0), (3, 8)], [(1, 8), (5, 8)]],
    "2": [[(0.5, 2), (1.5, 0), (4, 0), (5.5, 1.5), (5, 3.5), (2, 6),
           (0, 8), (5.5, 8)]],
    "3": [[(0.5, 1.5), (2, 0), (4.5, 0), (5.5, 1.5), (4, 3), (5.5, 4.5),
           (5, 6.5), (4, 8), (1.5, 8), (0.5, 7)]],
    "4": [[(4.5, 0), (0.5, 5.5), (5.5, 5.5)], [(4.5, 0), (4.5, 8)]],
    "5": [[(5.5, 0), (0.5, 0), (0.5, 3.5), (4, 3.5), (5.5, 5), (5, 6.5),
           (4, 8), (1.5, 8), (0.5, 6.5)]],
    "6": [[(5, 1.5), (4, 0), (1.5, 0), (0, 2), (0, 6), (1.5, 8),
           (4.5, 8), (5.5, 6.5), (5, 4.5), (3.5, 3.5), (1.5, 3.5), (0.5, 5)]],
    "7": [[(0, 0), (6, 0), (2.5, 8)]],
    "8": [[(4, 0), (1.5, 0), (0, 1.5), (0, 3), (1.5, 4), (4, 4), (5.5, 3),
           (5.5, 1.5), (4, 0)],
          [(4, 4), (1.5, 4), (0, 5.5), (0, 7), (1.5, 8), (4, 8), (5.5, 7),
           (5.5, 5.5), (4, 4)]],
    "9": [[(0.5, 6.5), (1.5, 8), (4, 8), (5.5, 6), (5.5, 2), (4, 0),
           (1.5, 0), (0.5, 1.5), (0.5, 3.5), (2, 4.5), (4, 4.5), (5, 3.5)]],
    ".": [[(3, 8)]],
    ",": [[(3, 8), (3, 9.5), (2, 10.5)]],
    ":": [[(3, 3)], [(3, 8)]],
    ";": [[(3, 3)], [(3, 8), (3, 9.5), (2, 10.5)]],
    "!": [[(3, 0), (3, 6)], [(3, 8)]],
    "?": [[(1, 2), (2, 0), (4, 0), (5.5, 1.5), (5, 3), (3.5, 4.5), (3, 5.5)],
          [(3, 8)]],
    "'": [[(3, 0), (2, 2)]],
    '"': [[(2, 0), (1.5, 2)], [(4.5, 0), (4, 2)]],
    "-": [[(0, 5), (6, 5)]],
    "\u2013": [[(0, 4.5), (6, 4.5)]],
    "\u2014": [[(0, 4.5), (8, 4.5)]],
    "(": [[(4.5, 0), (2.5, 2), (2.5, 6), (4.5, 8)]],
    ")": [[(1.5, 0), (3.5, 2), (3.5, 6), (1.5, 8)]],
    "/": [[(5, 0), (1, 8)]],
    "&": [[(4, 0), (1.5, 0), (0, 1.5), (0, 3), (1.5, 4), (4, 4), (5.5, 3),
           (5.5, 1.5), (4, 0)], [(4, 4), (2, 6), (1, 8)],
          [(4, 4), (5.5, 6), (5, 8)]],
    "%": [[(1.5, 2)], [(4.5, 6)], [(5, 0), (1, 8)]],
    "$": [[(5, 2), (4, 0), (2, 0), (0.5, 1.5), (1, 3.5), (3, 4.5),
           (5, 5), (5, 6.5), (4, 8), (2, 8), (0.5, 6.5)], [(3, -0.5), (3, 9.5)]],
    "#": [[(2, 0), (2, 8)], [(4, 0), (4, 8)], [(0, 3), (6, 3)], [(0, 5.5), (6, 5.5)]],
    "+": [[(3, 1.5), (3, 6.5)], [(0.5, 4), (5.5, 4)]],
    "=": [[(0, 3), (6, 3)], [(0, 6), (6, 6)]],
    "*": [[(3, 1), (3, 7)], [(0.5, 2.5), (5.5, 5.5)], [(5.5, 2.5), (0.5, 5.5)]],
    "\u2022": [[(3, 4.5)]],
    "\u00b7": [[(3, 5)]],
    "\u00d7": [[(1, 2), (5, 6)], [(5, 2), (1, 6)]],
    "\u00b0": [[(3, 1)]],
    "[": [[(4, 0), (1, 0), (1, 8), (4, 8)]],
    "]": [[(2, 0), (5, 0), (5, 8), (2, 8)]],
    "<": [[(5, 0), (1, 4), (5, 8)]],
    ">": [[(1, 0), (5, 4), (1, 8)]],
}

_NARROW = set("ijl.,:;!'|()[]")
_WIDE = set("mMwW%@&#")
_ADV = {}


def _adv(ch):
    if ch in _ADV:
        return _ADV[ch]
    if ch == " ":
        a = 3.4
    elif ch == "\u2014":
        a = 9.0
    elif ch in _NARROW:
        a = 3.8
    elif ch in _WIDE:
        a = 7.6
    else:
        a = 6.6
    _ADV[ch] = a
    return a


_GLYPH_CACHE = {}


def _glyph_bitmap(ch, cap_h, bold):
    """Rasterise one glyph to a greyscale-alpha bitmap. Returns
    (bytes, width, height, y_offset) where y_offset is the bitmap row of
    the cap top (y=0 in glyph space)."""
    key = (ch, cap_h, bold)
    if key in _GLYPH_CACHE:
        return _GLYPH_CACHE[key]
    scale = cap_h / 8.0
    hw = max(0.8, cap_h * (0.09 if bold else 0.07))
    strokes = FONT.get(ch)
    if strokes is None:
        strokes = FONT["?"]
    adv = _adv(ch)
    bw = max(1, int(math.ceil(adv * scale)) + 2)
    bh = int(math.ceil(11.5 * scale)) + 2
    bmp = bytearray(bw * bh)
    ox = 1.0
    oy = 1.0
    for stroke in strokes:
        if len(stroke) == 1:
            cx = ox + stroke[0][0] * scale
            cy = oy + stroke[0][1] * scale
            r = hw + 0.9
            x0 = max(0, int(cx - r - 1))
            x1 = min(bw - 1, int(cx + r + 1))
            y0 = max(0, int(cy - r - 1))
            y1 = min(bh - 1, int(cy + r + 1))
            for yy in range(y0, y1 + 1):
                for xx in range(x0, x1 + 1):
                    d = math.hypot(xx + 0.5 - cx, yy + 0.5 - cy)
                    cov = min(1.0, max(0.0, r + 0.6 - d))
                    if cov > 0:
                        v = int(cov * 255)
                        if v > bmp[yy * bw + xx]:
                            bmp[yy * bw + xx] = v
            continue
        pts = [(ox + x * scale, oy + y * scale) for (x, y) in stroke]
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            pad = hw + 1.2
            bx0 = max(0, int(min(x0, x1) - pad))
            bx1 = min(bw - 1, int(max(x0, x1) + pad))
            by0 = max(0, int(min(y0, y1) - pad))
            by1 = min(bh - 1, int(max(y0, y1) + pad))
            dx = x1 - x0
            dy = y1 - y0
            L2 = dx * dx + dy * dy
            for yy in range(by0, by1 + 1):
                for xx in range(bx0, bx1 + 1):
                    px = xx + 0.5
                    py = yy + 0.5
                    if L2 == 0:
                        d = math.hypot(px - x0, py - y0)
                    else:
                        t = ((px - x0) * dx + (py - y0) * dy) / L2
                        t = 0.0 if t < 0 else (1.0 if t > 1 else t)
                        d = math.hypot(px - (x0 + t * dx), py - (y0 + t * dy))
                    cov = min(1.0, max(0.0, (hw + 0.7 - d) / 1.0))
                    if cov > 0:
                        v = int(cov * 255)
                        idx = yy * bw + xx
                        if v > bmp[idx]:
                            bmp[idx] = v
        for (x, y) in pts:
            r = hw * 0.7
            x0 = max(0, int(x - r - 1))
            x1 = min(bw - 1, int(x + r + 1))
            y0 = max(0, int(y - r - 1))
            y1 = min(bh - 1, int(y + r + 1))
            for yy in range(y0, y1 + 1):
                for xx in range(x0, x1 + 1):
                    d = math.hypot(xx + 0.5 - x, yy + 0.5 - y)
                    cov = min(1.0, max(0.0, r + 0.6 - d))
                    if cov > 0:
                        v = int(cov * 255)
                        idx = yy * bw + xx
                        if v > bmp[idx]:
                            bmp[idx] = v
    res = (bytes(bmp), bw, bh, 1)
    _GLYPH_CACHE[key] = res
    return res


# --------------------------------------------------------------------------
# 5x7 bitmap font for small text (cap_h <= 13).
# The vector stroke font above breaks at small sizes: its advance (6.6 grid
# units) barely exceeds the glyph body (0..6) and the stroke half-width
# (~1px) makes neighbouring glyphs merge, while thin stems ("i", "l")
# vanish between pixel centres. This bitmap font (proven in the 17 Nov
# entry) is crisp at integer scales: each glyph is 7 rows of 5 cells,
# advance 6 cells, scaled by 1 or 2. Descender glyphs have an 8th row.
# --------------------------------------------------------------------------

BITMAP_FONT = {
    "A": (" .###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", "#...#", ".#.#.", "..#..", ".#.#.", "#...#", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "a": (".....", ".....", ".####", "....#", ".####", "#...#", ".####"),
    "b": ("#....", "#....", "####.", "#...#", "#...#", "#...#", "####."),
    "c": (".....", ".....", ".####", "#....", "#....", "#....", ".####"),
    "d": ("....#", "....#", ".####", "#...#", "#...#", "#...#", ".####"),
    "e": (".....", ".....", ".###.", "#...#", "#####", "#....", ".###."),
    "f": ("..##.", ".#...", ".#...", "####.", ".#...", ".#...", ".#..."),
    "g": (".....", ".....", ".####", "#...#", "#...#", ".####", "....#"),
    "h": ("#....", "#....", "####.", "#...#", "#...#", "#...#", "#...#"),
    "i": ("..#..", ".....", ".##..", "..#..", "..#..", "..#..", ".###."),
    "j": ("...#.", ".....", "..##.", "...#.", "...#.", "...#.", "...#.",
          "##..."),
    "k": ("#....", "#....", "#..#.", "#.#..", "##...", "#.#..", "#..#."),
    "l": (".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "m": (".....", ".....", "##.#.", "#.#.#", "#.#.#", "#.#.#", "#.#.#"),
    "n": (".....", ".....", "####.", "#...#", "#...#", "#...#", "#...#"),
    "o": (".....", ".....", ".###.", "#...#", "#...#", "#...#", ".###."),
    "p": (".....", ".....", "####.", "#...#", "#...#", "####.", "#...."),
    "q": (".....", ".....", ".####", "#...#", "#...#", ".####", "....#"),
    "r": (".....", ".....", "#.##.", "##..#", "#....", "#....", "#...."),
    "s": (".....", ".....", ".####", "#....", ".###.", "....#", "####."),
    "t": (".#...", ".#...", "####.", ".#...", ".#...", ".#...", "..##."),
    "u": (".....", ".....", "#...#", "#...#", "#...#", "#...#", ".###."),
    "v": (".....", ".....", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "w": (".....", ".....", "#...#", "#...#", "#.#.#", "#.#.#", ".#.#."),
    "x": (".....", ".....", "#...#", ".#.#.", "..#..", ".#.#.", "#...#"),
    "y": (".....", ".....", "#...#", "#...#", ".####", "....#", ".###."),
    "z": (".....", ".....", "#####", "...#.", "..#..", ".#...", "#####"),
    "0": (".###.", "#..##", "#.#.#", "##..#", "#...#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "...#.", "..#..", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ",": (".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    ";": (".....", ".##..", ".##..", ".....", ".##..", ".##..", ".#..."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "...#.", "..#..", ".....", "..#.."),
    "-": (".....", ".....", ".....", ".###.", ".....", ".....", "....."),
    "(": ("...#.", "..#..", "..#..", "..#..", "..#..", "..#..", "...#."),
    ")": (".#...", "..#..", "..#..", "..#..", "..#..", "..#..", ".#..."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "%": ("##..#", "##.#.", "...#.", "..#..", ".#...", "#.##.", "#..##"),
    "&": (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
    "+": (".....", "..#..", "..#..", ".###.", "..#..", "..#..", "....."),
    "=": (".....", ".....", ".###.", ".....", ".###.", ".....", "....."),
    "@": (".###.", "#...#", "#.###", "#.#.#", "#.#..", "#....", ".###."),
    "#": (".#.#.", ".#.#.", "#####", ".#.#.", "#####", ".#.#.", ".#.#."),
    "$": ("..#..", ".####", "#.#..", ".###.", "..#.#", "####.", "..#.."),
    "*": (".....", ".#.#.", "..#..", "#####", "..#..", ".#.#.", "....."),
    "_": (".....", ".....", ".....", ".....", ".....", ".....", "#####"),
    '"': (".#.#.", ".#.#.", ".#.#.", ".....", ".....", ".....", "....."),
    "'": ("..#..", "..#..", ".#...", ".....", ".....", ".....", "....."),
    "\u00b7": (".....", ".....", ".....", "..#..", ".....", ".....", "....."),
    "\u2013": (".....", ".....", ".....", ".###.", ".....", ".....", "....."),
    "\u2014": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
}
# Descender glyphs need an 8th row (already 8 rows above for j; fix the rest).
BITMAP_FONT["g"] = (".....", ".....", ".####", "#...#", "#...#", ".####",
                    "....#", ".###.")
BITMAP_FONT["p"] = (".....", ".....", "####.", "#...#", "#...#", "####.",
                    "#....", "#....")
BITMAP_FONT["q"] = (".....", ".....", ".####", "#...#", "#...#", ".####",
                    "....#", "....#")
BITMAP_FONT["y"] = (".....", ".....", "#...#", "#...#", ".####", "....#",
                    "....#", ".###.")

_BITMAP_ADV = 6  # cells per character (5 + 1 gap)


def _bitmap_scale(cap_h):
    """Integer bitmap scale for a requested cap height: 2 for the larger
    small text (headlines, titles), 1 for body/briefs/labels."""
    return 2 if cap_h >= 11 else 1


def _draw_bitmap_text(c, x, y, s, scale, color, bold=False):
    """Draw bitmap text; (x, y) is the integer cap-top. Returns width."""
    x = int(round(x))
    y = int(round(y))
    cx = x
    for ch in s:
        glyph = BITMAP_FONT.get(ch)
        if glyph is not None:
            for ry, row in enumerate(glyph):
                for rx, cell in enumerate(row):
                    if cell == "#":
                        c.rect(cx + rx * scale, y + ry * scale,
                               cx + (rx + 1) * scale,
                               y + (ry + 1) * scale, color)
                        if bold:
                            c.rect(cx + rx * scale + 1, y + ry * scale,
                                   cx + (rx + 1) * scale + 1,
                                   y + (ry + 1) * scale, color)
        cx += _BITMAP_ADV * scale
    return cx - x


def text_width(s, cap_h, bold=False):
    if cap_h <= 13:
        return len(s) * _BITMAP_ADV * _bitmap_scale(cap_h)
    scale = cap_h / 8.0
    return sum(_adv(ch) * scale for ch in s)


def draw_text(c, x, y, s, cap_h, color, bold=False, align="left"):
    """Draw text; y is the cap-top. Returns the width drawn.
    Small text (cap_h <= 13) uses the bitmap font; large text keeps the
    vector stroke font."""
    if cap_h <= 13:
        scale = _bitmap_scale(cap_h)
        w = len(s) * _BITMAP_ADV * scale
        if align == "center":
            x -= w / 2.0
        elif align == "right":
            x -= w
        return _draw_bitmap_text(c, x, y, s, scale, color, bold)
    w = text_width(s, cap_h, bold)
    if align == "center":
        x -= w / 2.0
    elif align == "right":
        x -= w
    scale = cap_h / 8.0
    cx = x
    for ch in s:
        if ch == " ":
            cx += _adv(ch) * scale
            continue
        bmp, bw, bh, oy = _glyph_bitmap(ch, cap_h, bold)
        c.blit(bmp, bw, bh, int(round(cx)) - 1, int(round(y)) - oy, color)
        cx += _adv(ch) * scale
    return w


def wrap_text(s, cap_h, max_w, bold=False):
    """Greedy word wrap. Returns a list of lines."""
    lines = []
    for para in s.split("\n"):
        words = para.split(" ")
        cur = ""
        for wd in words:
            trial = wd if not cur else cur + " " + wd
            if text_width(trial, cap_h, bold) <= max_w or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = wd
        if cur:
            lines.append(cur)
    return lines


def draw_para(c, x, y, s, cap_h, max_w, color, bold=False, leading=None,
              align="left"):
    """Draw a wrapped paragraph. Returns the y just below the last line."""
    if leading is None:
        leading = cap_h * 1.32
    lines = wrap_text(s, cap_h, max_w, bold)
    for ln in lines:
        draw_text(c, x, y, ln, cap_h, color, bold, align)
        y += leading
    return y


# --------------------------------------------------------------------------
# Font specimen (MAKEFUN_TEST=font)
# --------------------------------------------------------------------------

def draw_specimen(c):
    c.rect(0, 0, W, H, PAPER)
    y = 30
    draw_text(c, 40, y, "FONT SPECIMEN", 26, INK, True)
    y += 52
    draw_text(c, 40, y, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", 22, INK, True)
    y += 34
    draw_text(c, 40, y, "abcdefghijklmnopqrstuvwxyz", 22, INK, False)
    y += 34
    draw_text(c, 40, y, "0123456789 . , : ; ! ? ' \" - / & % $ # + = *", 22, INK, False)
    y += 44
    draw_text(c, 40, y, "The quick brown fox jumps over the lazy dog.", 20, INK, False)
    y += 32
    draw_text(c, 40, y, "PACK MY BOX WITH FIVE DOZEN LIQUOR JUGS 1234567890", 20, INK, True)
    y += 32
    draw_text(c, 40, y, "Sphinx of black quartz, judge my vow. $3,730 gold", 16, INK, False)
    y += 30
    draw_text(c, 40, y, "Voyager 1 is one light-day from Earth — 25.9 billion km.", 14, MUTED, False)
    y += 26
    draw_text(c, 40, y, "WEDNESDAY, 18 NOVEMBER 2026", 30, NAVY, True)


# --------------------------------------------------------------------------
# Data — 42 stories, all Wednesday 18 November 2026.
# Region totals: Europe 10, Asia 8, Americas 7, Africa 6, Middle East 5,
# World 3, Oceania 3 = 42.
# Field totals: War & security 11, Politics & diplomacy 8, Economy & markets 5,
# Society & health 2, Disasters & weather 5, Technology 3, Climate & space 4,
# Justice & law 4 = 42.
# --------------------------------------------------------------------------

REGION_COLORS = {
    "Europe": BLUE, "Asia": ORANGE, "Americas": PURPLE, "Africa": RED,
    "Middle East": GREEN, "World": GREY, "Oceania": TEAL,
}
REGION_ORDER = ["Europe", "Asia", "Americas", "Africa", "Middle East",
                "World", "Oceania"]
FIELD_COLORS = {
    "War & security": RED, "Politics & diplomacy": NAVY,
    "Economy & markets": ORANGE, "Society & health": GREEN,
    "Disasters & weather": TEAL, "Technology": PURPLE,
    "Climate & space": BLUE, "Justice & law": GREY,
}

# (num, region, field, headline, summary, icon, lon, lat)
CARDS = [
    (1, "Asia", "Politics & diplomacy",
     "Trump, Xi, Putin meet in Shenzhen",
     "APEC opens as the three leaders prepare for Thursday's first-ever "
     "three-way talks.", "apec", 114, 22.5),
    (2, "Middle East", "War & security",
     "Iran strikes US bases in the Gulf",
     "Tehran hits Ali Al Salem base and Bahrain; Gulf air defences "
     "intercept drones.", "missile", 48, 29),
    (3, "Europe", "War & security",
     "Kerch Bridge span lies in the sea",
     "227 m road arch down after Ukrainian strikes; rail line damaged "
     "but trains run.", "bridge", 36.5, 45.3),
    (4, "Africa", "Society & health",
     "Ebola cases pass 11,000",
     "DR Congo toll nears 5,400 dead; WHO warns.", "virus", 23, 0),
    (5, "World", "Climate & space",
     "Voyager 1 one light-day out",
     "25.9 billion km out; signals take 24 hours.", "dish", -118, 34),
    (6, "Oceania", "Disasters & weather",
     "Cyclone Xavier hits Cook Islands",
     "Gusts to 315 km/h; shelters open, no deaths.", "cyclone", -160, -21),
    (7, "Middle East", "Politics & diplomacy",
     "Board of Peace faults both sides",
     "Both sides failed; truce at risk.", "branch", 34.5, 31.5),
    (8, "Europe", "Disasters & weather",
     "Toledo crash kills at least 64",
     "64 dead, 80+ hurt in Spain train collision.", "train", -4, 39.8),
    (9, "Africa", "War & security",
     "Ethiopia, Eritrea mass troops",
     "Build-up near Badme fuels fears of war.", "border", 39, 14.5),
    (10, "Americas", "Economy & markets",
     "Dow drops 560 as S&P slides again",
     "Wall Street falls 1.1%; Nasdaq steadies.", "chartdown", -74, 40.7),
    (11, "World", "Climate & space",
     "COP31 deadlocked; 21 issues open",
     "21 issues open; Stocktake launched in Antalya.", "globe", 30.7, 36.9),
    (12, "Europe", "Economy & markets",
     "Spain strike paralyses ports",
     "Stoppage halts ports and car plants.", "mega", -3.7, 40.4),
    (13, "Americas", "Technology",
     "Anthropic prices $1.4 trillion IPO",
     "825m shares at $70-$78; debut Thursday.", "chartup", -122.4, 37.8),
]

# (num, headline) — one-line briefs, stories 14-42
BRIEFS = [
    (14, "Peltola wins Alaska Senate seat"),
    (15, "Takaichi and Xi shake hands at APEC"),
    (16, "Seoul seeks China's help on Korea"),
    (17, "Bangladesh deploys paramilitaries"),
    (18, "ASEAN adopts child online safety rules"),
    (19, "Bhutan wins 2026 Earthshot Prize"),
    (20, "Sensex falls 500 points in Mumbai"),
    (21, "China building runway on Antelope Reef"),
    (22, "Nigeria busts cocaine gang via Sahara"),
    (23, "ECOWAS defence chiefs meet in Dakar"),
    (24, "Egypt court suspends Mada Masr trial"),
    (25, "Senegal ruling party expels Faye"),
    (26, "Hegseth's surprise Venezuela trip"),
    (27, "Gold below $3,800; Bitcoin at $62,300"),
    (28, "US outages blamed on AI patches"),
    (29, "Huawei trial closing arguments end"),
    (30, "Oceans enter COP31 draft deal"),
    (31, "Fiji declares disaster over drought"),
    (32, "6.0 quake strikes Papua New Guinea"),
    (33, "Prague protest for free media"),
    (34, "Estonia to close Russia border in Dec."),
    (35, "Finland approves nuclear waste site"),
    (36, "Lagarde to leave ECB in February 2027"),
    (37, "Woman charged as Russian spy in Berlin"),
    (38, "Hoax bomb threats hit Italy schools"),
    (39, "Romania quake felt across five nations"),
    (40, "Iran claims it downed US MQ-9 drone"),
    (41, "Saudi coalition downs Houthi missile"),
    (42, "Israeli strikes kill two Hamas leaders"),
]

NUMBERS = [
    ("64", "killed in the Toledo\ntrain crash, Spain"),
    ("6,300", "Italian schools hit by\nhoax bomb threats"),
    ("25.9bn km", "Voyager 1's distance\nfrom Earth today"),
    ("11,000+", "Ebola cases in\nDR Congo"),
    ("315 km/h", "Cyclone Xavier\nwind gusts"),
    ("$3,730", "gold per ounce,\n14-month low"),
]


def region_counts():
    counts = {r: 0 for r in REGION_ORDER}
    for s in CARDS:
        counts[s[1]] += 1
    brief_regions = {
        14: "Americas", 15: "Asia", 16: "Asia", 17: "Asia", 18: "Asia",
        19: "Asia", 20: "Asia", 21: "Asia", 22: "Africa", 23: "Africa",
        24: "Africa", 25: "Africa", 26: "Americas", 27: "Americas",
        28: "Americas", 29: "Americas", 30: "World", 31: "Oceania",
        32: "Oceania", 33: "Europe", 34: "Europe", 35: "Europe",
        36: "Europe", 37: "Europe", 38: "Europe", 39: "Europe",
        40: "Middle East", 41: "Middle East", 42: "Middle East",
    }
    for n, r in brief_regions.items():
        counts[r] += 1
    return counts


def field_counts():
    counts = {}
    for s in CARDS:
        counts[s[2]] = counts.get(s[2], 0) + 1
    brief_fields = {
        14: "Politics & diplomacy", 15: "Politics & diplomacy",
        16: "Politics & diplomacy", 17: "War & security",
        18: "Society & health", 19: "Climate & space",
        20: "Economy & markets", 21: "War & security",
        22: "Justice & law", 23: "War & security",
        24: "Justice & law", 25: "Politics & diplomacy",
        26: "Politics & diplomacy", 27: "Economy & markets",
        28: "Technology", 29: "Justice & law",
        30: "Climate & space", 31: "Disasters & weather",
        32: "Disasters & weather", 33: "Politics & diplomacy",
        34: "War & security", 35: "Technology",
        36: "Economy & markets", 37: "Justice & law",
        38: "War & security", 39: "Disasters & weather",
        40: "War & security", 41: "War & security",
        42: "War & security",
    }
    for n, f in brief_fields.items():
        counts[f] = counts.get(f, 0) + 1
    return counts


# --------------------------------------------------------------------------
# Vector icons. Each draws centred at (cx, cy) inside a square of size s.
# --------------------------------------------------------------------------

def _star(c, cx, cy, r, color, points=8):
    for i in range(points):
        a = math.pi * 2 * i / points
        x1 = cx + math.cos(a) * r
        y1 = cy + math.sin(a) * r
        x2 = cx + math.cos(a) * r * 0.35
        y2 = cy + math.sin(a) * r * 0.35
        c.polyline([(cx, cy), (x1, y1)], color, 2.5)
        c.polyline([(cx, cy), (x2, y2)], color, 1.5)


def _arrow_head(c, x, y, dx, dy, color, size=7):
    ang = math.atan2(dy, dx)
    for da in (2.5, -2.5):
        a = ang + da
        c.polyline([(x, y), (x - math.cos(a) * size, y - math.sin(a) * size)],
                   color, 3)


def draw_icon(c, kind, cx, cy, s):
    u = s / 64.0
    if kind == "apec":
        # three flags on poles
        for i, col in enumerate((BLUE, RED, GOLD)):
            x = cx - 18 * u + i * 18 * u
            c.vline(int(x), int(cy - 20 * u), int(cy + 20 * u), INK, max(1, int(2 * u)))
            c.fill_poly([(x, cy - 20 * u), (x + 15 * u, cy - 16 * u),
                         (x, cy - 12 * u)], col)
        c.hline(int(cx - 24 * u), int(cx + 24 * u), int(cy + 20 * u), INK, max(1, int(2 * u)))
    elif kind == "missile":
        c.polyline([(cx - 20 * u, cy + 16 * u), (cx + 8 * u, cy - 8 * u)],
                   INK, 7 * u)
        c.fill_poly([(cx + 8 * u, cy - 8 * u), (cx + 22 * u, cy - 14 * u),
                     (cx + 16 * u, cy + 2 * u)], RED)
        c.polyline([(cx - 22 * u, cy + 18 * u), (cx - 10 * u, cy + 6 * u)],
                   GOLD, 4 * u)
        _star(c, cx - 24 * u, cy + 20 * u, 7 * u, GOLD, 6)
    elif kind == "bridge":
        c.polyline([(cx - 26 * u, cy - 2 * u), (cx - 6 * u, cy - 2 * u)],
                   INK, 4 * u)
        c.polyline([(cx + 6 * u, cy - 2 * u), (cx + 26 * u, cy - 2 * u)],
                   INK, 4 * u)
        c.polyline([(cx - 26 * u, cy - 2 * u), (cx - 26 * u, cy + 12 * u)],
                   INK, 3 * u)
        c.polyline([(cx + 26 * u, cy - 2 * u), (cx + 26 * u, cy + 12 * u)],
                   INK, 3 * u)
        c.polyline([(cx - 20 * u, cy - 2 * u), (cx, cy + 8 * u),
                    (cx + 20 * u, cy - 2 * u)], RED, 3 * u)
        for dx in (-18, 0, 18):
            c.polyline([(cx + dx * u - 8 * u, cy + 20 * u),
                        (cx + dx * u, cy + 16 * u),
                        (cx + dx * u + 8 * u, cy + 20 * u)], BLUE, 2.5 * u)
    elif kind == "virus":
        c.disc(cx, cy, 12 * u, GREEN)
        for i in range(8):
            a = math.pi * 2 * i / 8
            x1 = cx + math.cos(a) * 12 * u
            y1 = cy + math.sin(a) * 12 * u
            x2 = cx + math.cos(a) * 19 * u
            y2 = cy + math.sin(a) * 19 * u
            c.polyline([(x1, y1), (x2, y2)], GREEN, 3 * u)
            c.disc(x2, y2, 2.5 * u, GREEN)
        c.disc(cx - 4 * u, cy - 3 * u, 2.5 * u, WHITE)
        c.disc(cx + 4 * u, cy + 3 * u, 2.5 * u, WHITE)
    elif kind == "dish":
        c.polyline([(cx - 18 * u, cy - 8 * u), (cx, cy + 6 * u),
                    (cx + 18 * u, cy - 8 * u)], NAVY, 3 * u)
        c.polyline([(cx, cy + 6 * u), (cx, cy + 20 * u)], INK, 3 * u)
        c.hline(int(cx - 10 * u), int(cx + 10 * u), int(cy + 20 * u), INK, 3)
        for r in (8, 14, 20):
            c.polyline([(cx + 14 * u + r * u * 0.4, cy - 18 * u + r * u * 0.2),
                        (cx + 18 * u + r * u * 0.5, cy - 12 * u + r * u * 0.3)],
                       GOLD, 2.5 * u)
        c.disc(cx - 22 * u, cy - 16 * u, 1.5 * u, GOLD)
        c.disc(cx + 22 * u, cy - 20 * u, 1.5 * u, GOLD)
    elif kind == "cyclone":
        pts = []
        for k in range(0, 100):
            t = k / 100.0 * 4.5 * math.pi
            r = 2 + t * 3.2
            pts.append((cx + math.cos(t) * r * u, cy + math.sin(t) * r * u))
        c.polyline(pts, TEAL, 3.5 * u)
        c.disc(cx, cy, 3 * u, RED)
    elif kind == "branch":
        c.polyline([(cx - 16 * u, cy + 18 * u), (cx + 14 * u, cy - 16 * u)],
                   GREEN, 3 * u)
        for i, (dx, dy) in enumerate(((-8, 8), (0, 0), (8, -8))):
            leaf_cx = cx + dx * u
            leaf_cy = cy + dy * u
            c.fill_poly([(leaf_cx - 8 * u, leaf_cy), (leaf_cx, leaf_cy - 5 * u),
                         (leaf_cx + 8 * u, leaf_cy), (leaf_cx, leaf_cy + 5 * u)],
                        GREEN)
        c.disc(cx + 18 * u, cy - 18 * u, 3 * u, GOLD)
    elif kind == "train":
        c.rect(int(cx - 18 * u), int(cy - 14 * u), int(cx + 18 * u),
               int(cy + 18 * u), NAVY)
        c.rect(int(cx - 12 * u), int(cy - 9 * u), int(cx + 12 * u),
               int(cy + 2 * u), (180, 220, 240))
        c.disc(cx - 10 * u, cy + 10 * u, 3 * u, GOLD)
        c.disc(cx + 10 * u, cy + 10 * u, 3 * u, GOLD)
        _star(c, cx + 22 * u, cy - 16 * u, 6 * u, RED, 6)
    elif kind == "border":
        for i, col in enumerate((RED, BLUE)):
            x = cx - 12 * u + i * 24 * u
            c.vline(int(x), int(cy - 18 * u), int(cy + 18 * u), INK, max(1, int(2 * u)))
            c.fill_poly([(x, cy - 18 * u), (x + 13 * u, cy - 14 * u),
                         (x, cy - 10 * u)], col)
        c.hline(int(cx - 22 * u), int(cx + 22 * u), int(cy + 18 * u), INK, max(1, int(2 * u)))
        for x in range(int(cx - 20 * u), int(cx + 22 * u), 8):
            c.vline(x, int(cy + 10 * u), int(cy + 18 * u), MUTED, 1)
    elif kind == "chartdown":
        c.hline(int(cx - 22 * u), int(cx + 24 * u), int(cy + 18 * u), INK, 2)
        c.vline(int(cx - 22 * u), int(cy - 20 * u), int(cy + 18 * u), INK, 2)
        pts = [(cx - 20 * u, cy - 16 * u), (cx - 8 * u, cy - 8 * u),
               (cx + 2 * u, cy - 12 * u), (cx + 12 * u, cy + 2 * u),
               (cx + 22 * u, cy + 14 * u)]
        c.polyline(pts, RED, 3.5 * u)
        _arrow_head(c, cx + 22 * u, cy + 14 * u, 1, 1, RED, 8 * u)
    elif kind == "globe":
        c.disc(cx, cy, 18 * u, BLUE)
        c.polyline([(cx, cy - 18 * u), (cx, cy + 18 * u)], WHITE, 2 * u)
        c.polyline([(cx - 18 * u, cy), (cx + 18 * u, cy)], WHITE, 2 * u)
        c.polyline([(cx - 12 * u, cy - 13 * u), (cx - 12 * u, cy + 13 * u)],
                   WHITE, 1.5 * u)
        c.polyline([(cx + 12 * u, cy - 13 * u), (cx + 12 * u, cy + 13 * u)],
                   WHITE, 1.5 * u)
        c.fill_poly([(cx + 4 * u, cy + 10 * u), (cx + 10 * u, cy + 18 * u),
                     (cx + 16 * u, cy + 8 * u), (cx + 10 * u, cy + 6 * u)],
                    GREEN)
    elif kind == "mega":
        c.fill_poly([(cx - 18 * u, cy + 6 * u), (cx + 12 * u, cy - 12 * u),
                     (cx + 18 * u, cy - 4 * u), (cx + 18 * u, cy + 6 * u),
                     (cx - 12 * u, cy + 14 * u)], ORANGE)
        c.rect(int(cx - 22 * u), int(cy - 2 * u), int(cx - 14 * u),
               int(cy + 12 * u), INK)
        for dx, dy in ((22, -16), (26, -8), (24, 0)):
            c.polyline([(cx + 16 * u, cy - 4 * u),
                        (cx + dx * u, cy + dy * u)], INK, 2 * u)
    elif kind == "chartup":
        c.hline(int(cx - 22 * u), int(cx + 24 * u), int(cy + 18 * u), INK, 2)
        c.vline(int(cx - 22 * u), int(cy - 20 * u), int(cy + 18 * u), INK, 2)
        pts = [(cx - 20 * u, cy + 14 * u), (cx - 8 * u, cy + 4 * u),
               (cx + 2 * u, cy + 8 * u), (cx + 12 * u, cy - 6 * u),
               (cx + 22 * u, cy - 16 * u)]
        c.polyline(pts, GREEN, 3.5 * u)
        _arrow_head(c, cx + 22 * u, cy - 16 * u, 1, -1, GREEN, 8 * u)
        c.disc(cx - 14 * u, cy - 12 * u, 6 * u, GOLD)
        draw_text(c, cx - 14 * u, cy - 17 * u, "$", 10, INK, True, "center")


# --------------------------------------------------------------------------
# World map (coarse continent outlines, equirectangular)
# --------------------------------------------------------------------------

EURASIA = [(-10, 36), (-9, 43), (-2, 48), (-2, 50), (0, 51), (3, 53), (8, 54),
           (8, 57), (10, 59), (5, 60), (5, 62), (12, 65), (18, 69), (25, 71),
           (30, 70), (40, 68), (50, 68), (60, 68), (70, 70), (80, 72),
           (90, 73), (100, 74), (110, 74), (120, 73), (130, 72), (140, 72),
           (150, 70), (158, 66), (162, 60), (158, 55), (150, 48), (142, 45),
           (140, 38), (135, 33), (130, 30), (127, 35), (122, 38), (120, 30),
           (115, 25), (110, 20), (108, 12), (105, 8), (100, 6), (98, 10),
           (95, 16), (92, 21), (88, 22), (85, 19), (80, 13), (77, 8),
           (75, 10), (72, 20), (68, 23), (64, 25), (60, 25), (56, 26),
           (52, 28), (50, 29), (48, 30), (44, 29), (42, 27), (40, 24),
           (38, 20), (36, 18), (34, 22), (33, 27), (34, 30), (36, 36),
           (33, 36), (30, 36), (27, 37), (24, 36), (22, 37), (20, 40),
           (18, 42), (15, 44), (12, 44), (8, 44), (3, 43), (0, 40), (-2, 37),
           (-6, 36), (-9, 37), (-10, 36)]
N_AMERICA = [(-168, 66), (-165, 60), (-158, 58), (-152, 60), (-140, 60),
             (-135, 58), (-130, 54), (-125, 49), (-124, 42), (-120, 34),
             (-114, 29), (-110, 24), (-105, 20), (-97, 16), (-94, 17),
             (-90, 14), (-86, 12), (-83, 9), (-79, 9), (-81, 13), (-84, 16),
             (-87, 21), (-90, 21), (-91, 19), (-97, 26), (-93, 30), (-89, 30),
             (-84, 30), (-81, 25), (-80, 32), (-76, 35), (-74, 40),
             (-70, 42), (-68, 45), (-65, 44), (-60, 47), (-55, 52),
             (-60, 55), (-65, 58), (-68, 58), (-75, 62), (-82, 66),
             (-92, 66), (-95, 69), (-110, 68), (-125, 70), (-140, 70),
             (-155, 71), (-165, 68), (-168, 66)]
S_AMERICA = [(-79, 9), (-77, 4), (-80, -3), (-81, -6), (-77, -12), (-72, -18),
             (-70, -23), (-70, -30), (-72, -37), (-73, -44), (-74, -50),
             (-70, -54), (-66, -55), (-68, -50), (-65, -45), (-62, -41),
             (-58, -35), (-57, -30), (-48, -28), (-41, -23), (-39, -17),
             (-35, -9), (-35, -6), (-40, -3), (-44, -2), (-50, 0), (-53, 4),
             (-58, 6), (-62, 9), (-68, 11), (-72, 12), (-77, 8), (-79, 9)]
AFRICA = [(-17, 15), (-17, 21), (-15, 27), (-10, 31), (-5, 35), (0, 36),
          (10, 37), (11, 34), (20, 32), (30, 31), (32, 31), (34, 28),
          (37, 22), (39, 18), (43, 12), (48, 11), (51, 12), (44, 5),
          (41, 0), (40, -5), (40, -10), (36, -18), (33, -26), (28, -33),
          (20, -35), (17, -32), (15, -27), (12, -18), (9, -2), (9, 4),
          (-8, 5), (-13, 8), (-17, 12), (-17, 15)]
AUSTRALIA = [(113, -22), (114, -30), (115, -35), (118, -35), (124, -33),
             (129, -32), (132, -32), (135, -35), (138, -35), (140, -38),
             (145, -38), (150, -37), (153, -32), (153, -27), (150, -23),
             (146, -19), (142, -15), (142, -11), (137, -12), (135, -15),
             (132, -12), (130, -13), (126, -14), (122, -17), (118, -20),
             (113, -22)]
UK = [(-3, 53), (-5, 50), (-2, 50), (-1, 53), (0, 54), (-2, 58), (-5, 58),
      (-3, 53)]
NZ = [(167, -45), (170, -42), (174, -39), (176, -38), (173, -41), (168, -46),
      (167, -45)]


def draw_map(c, x0, y0, w, h, pins, nudge=None):
    """pins: list of (num, lon, lat). nudge: {num: (dx, dy)} in px."""
    c.rect(x0, y0, x0 + w, y0 + h, SEA)
    lon0, lon1 = -170, 190
    lat0, lat1 = 84, -60

    def proj(lon, lat):
        x = x0 + (lon - lon0) / (lon1 - lon0) * w
        y = y0 + (lat0 - lat) / (lat0 - lat1) * h
        return (x, y)

    for poly in (EURASIA, N_AMERICA, S_AMERICA, AFRICA, AUSTRALIA, UK, NZ):
        c.fill_poly([proj(lon, lat) for lon, lat in poly], LAND)
    # graticule
    for lon in (-120, -60, 0, 60, 120):
        x, _ = proj(lon, 0)
        c.vline(int(x), y0, y0 + h, (255, 255, 255), 1)
    for lat in (60, 30, 0, -30):
        _, y = proj(0, lat)
        c.hline(x0, x0 + w, int(y), (255, 255, 255), 1)
    for num, lon, lat in pins:
        px, py = proj(lon, lat)
        dx, dy = (nudge or {}).get(num, (0, 0))
        if dx or dy:
            c.disc(px, py, 2, RED)
            c.polyline([(px, py), (px + dx, py + dy)], RED, 1.5)
            px, py = px + dx, py + dy
        c.disc(px, py, 8, RED)
        # cap_h 9 -> bitmap scale 1: 2-digit pins (12 px) fit the 16 px disc.
        draw_text(c, px, py - 3.5, str(num), 9, WHITE, True, "center")


# --------------------------------------------------------------------------
# Page layout
# --------------------------------------------------------------------------

MX = 24          # left/right margin
CW = W - 2 * MX  # content width = 976


def draw_masthead(c):
    c.rect(0, 0, W, 92, NAVY)
    c.rect(0, 92, W, 95, GOLD)
    draw_text(c, MX, 14, "THE WORLD IN ONE IMAGE", 12, GOLD_LT, True)
    draw_text(c, MX, 32, "WEDNESDAY, 18 NOVEMBER 2026", 33, WHITE, True)
    draw_text(c, W - MX, 12, "42", 40, GOLD, True, "right")
    draw_text(c, W - MX, 56, "STORIES  ·  7 REGIONS  ·  8 FIELDS", 9,
              WHITE, True, "right")


def draw_region_strip(c, y):
    counts = region_counts()
    assert sum(counts.values()) == 42, counts
    draw_text(c, MX, y, "BY REGION", 10, MUTED, True)
    draw_text(c, W - MX, y, "EACH STORY COUNTED ONCE", 10, MUTED, True,
              "right")
    bar_y = y + 16
    bar_h = 15
    total = 42
    x = MX
    for r in REGION_ORDER:
        n = counts[r]
        seg_w = CW * n / total
        col = REGION_COLORS[r]
        c.rect(int(x), bar_y, int(x + seg_w), bar_y + bar_h, col)
        draw_text(c, x + seg_w / 2, bar_y + 2, str(n), 11, WHITE, True,
                  "center")
        draw_text(c, x + seg_w / 2, bar_y + bar_h + 4, r.upper(), 8,
                  INK, True, "center")
        x += seg_w
    return bar_y + bar_h + 18


def draw_field_strip(c, y):
    counts = field_counts()
    assert sum(counts.values()) == 42, counts
    items = [(f, counts[f]) for f in
             ["War & security", "Politics & diplomacy", "Economy & markets",
              "Society & health", "Disasters & weather", "Technology",
              "Climate & space", "Justice & law"]]
    draw_text(c, MX, y, "BY FIELD", 10, MUTED, True)
    rows = [items[:4], items[4:]]
    yy = y + 15
    for row in rows:
        x = MX
        for name, n in row:
            c.disc(x + 5, yy + 5, 4, FIELD_COLORS[name])
            label = "%s %d" % (name.replace("&", "and"), n)
            draw_text(c, x + 13, yy, label, 10, INK, False)
            x += text_width(label, 10) + 34
        yy += 17
    return yy + 2


def draw_numbers(c, y):
    draw_text(c, MX, y, "THE DAY IN NUMBERS", 10, MUTED, True)
    cell_w = CW / 6.0
    top = y + 15
    for i, (num, label) in enumerate(NUMBERS):
        x = MX + i * cell_w
        if i > 0:
            c.vline(int(x), top, top + 34, BORDER, 1)
        # cap_h 12 -> bitmap scale 2: the vector font merges lowercase
        # ("25.9bn km", "315 km/h") at 19; 14 px bitmap stays clean.
        draw_text(c, x + 10, top, num, 12, NAVY, True)
        for j, ln in enumerate(label.split("\n")):
            draw_text(c, x + 10, top + 22 + j * 11, ln, 9, MUTED, False)
    return top + 44


def draw_card(c, story, x, y, w, h, wide):
    num, region, field, head, summ, icon, lon, lat = story
    rcol = REGION_COLORS[region]
    c.rect(int(x), int(y), int(x + w), int(y + h), CARD)
    c.rect(int(x), int(y), int(x + w), int(y + h), BORDER)  # border frame
    c.rect(int(x), int(y), int(x + w), int(y + 3), rcol)
    if wide:
        ix = x + 48
        iy = y + h / 2
        c.rect(int(x) + 1, int(y) + 4, int(x) + 96, int(y + h) - 1,
               (238, 240, 244))
        draw_icon(c, icon, ix, iy, 66)
        tx = x + 106
        tw = w - 116
        ty = y + 12
        draw_text(c, tx, ty, "%s  ·  %s" % (region.upper(),
                  field.upper().replace("&", "and")), 8, MUTED, True)
        ty += 14
        ty = draw_para(c, tx, ty, head, 13, tw, INK, True, leading=17)
        ty += 3
        draw_para(c, tx, ty, summ, 10, tw, MUTED, False, leading=13)
        c.disc(x + w - 14, y + 14, 10, RED)
        draw_text(c, x + w - 14, y + 8.5, str(num), 11, WHITE, True, "center")
    else:
        ih = 42
        c.rect(int(x) + 1, int(y) + 4, int(x + w) - 1, int(y) + ih,
               (238, 240, 244))
        draw_icon(c, icon, x + w / 2, y + 4 + ih / 2, 38)
        ty = y + ih + 8
        draw_text(c, x + 8, ty, region.upper(), 8, rcol, True)
        c.disc(x + w - 14, ty + 5, 9, RED)
        draw_text(c, x + w - 14, ty - 0.5, str(num), 10, WHITE, True,
                  "center")
        ty += 13
        ty = draw_para(c, x + 8, ty, head, 12, w - 16, INK, True, leading=14.5)
        ty += 2
        draw_para(c, x + 8, ty, summ, 9, w - 16, MUTED, False, leading=11)


def draw_cards(c, y):
    row1_h = 140
    row_h = 120
    gap = 8
    # row 1: 3 wide cards
    w1 = (CW - 2 * gap) / 3.0
    for i in range(3):
        draw_card(c, CARDS[i], MX + i * (w1 + gap), y, w1, row1_h, True)
    y += row1_h + gap
    # rows 2-3: 5 small cards each
    w2 = (CW - 4 * gap) / 5.0
    for r in range(2):
        for i in range(5):
            draw_card(c, CARDS[3 + r * 5 + i], MX + i * (w2 + gap), y, w2,
                      row_h, False)
        y += row_h + gap
    return y - gap


def draw_bottom(c, y):
    # left: map panel
    map_w = 308
    c.rect(MX, y, MX + map_w, y + 272, CARD)
    c.rect(MX, y, MX + map_w, y + 272, BORDER)
    draw_text(c, MX + 10, y + 8, "WHERE IT HAPPENED", 11, NAVY, True)
    draw_text(c, MX + 10, y + 22, "Pins are the 13 top stories", 9, MUTED,
              False)
    pins = [(s[0], s[6], s[7]) for s in CARDS]
    # nudge clustered pins so the numbers stay readable
    nudge = {2: (7, 9), 3: (9, -7), 5: (11, 11), 7: (-9, 7), 8: (-9, -7),
             11: (-7, -9), 12: (9, 7)}
    draw_map(c, MX + 10, y + 40, map_w - 20, 138, pins, nudge)
    # legend
    ly = y + 186
    lx = MX + 10
    for i, r in enumerate(REGION_ORDER):
        col = i % 2
        row = i // 2
        xx = lx + col * 150
        yy = ly + row * 15
        c.disc(xx + 4, yy + 4, 3.5, REGION_COLORS[r])
        draw_text(c, xx + 11, yy, r, 9, INK, False)
    draw_text(c, MX + 10, y + 244, "Map drawn from code; coastlines are",
              8, MUTED, False)
    draw_text(c, MX + 10, y + 255, "simplified, pins show story places.",
              8, MUTED, False)
    # right: briefs
    bx = MX + map_w + 12
    bw = W - MX - bx
    c.rect(bx, y, bx + bw, y + 272, CARD)
    c.rect(bx, y, bx + bw, y + 272, BORDER)
    draw_text(c, bx + 10, y + 8, "ALSO ON WEDNESDAY", 11, NAVY, True)
    draw_text(c, bx + 10, y + 22, "Stories 14-42 in one line each", 9,
              MUTED, False)
    col_w = (bw - 20 - 12) / 2.0
    for k, (n, head) in enumerate(BRIEFS):
        col = k // 15
        row = k % 15
        xx = bx + 10 + col * (col_w + 12)
        yy = y + 44 + row * 15
        draw_text(c, xx, yy, "%d." % n, 9, RED, True)
        draw_text(c, xx + 22, yy, head, 9, INK, False)
    return y + 272


def draw_footer(c, y):
    c.rect(MX, y, MX + 640, y + 56, (243, 232, 205))
    c.rect(MX, y, MX + 4, y + 56, RED)
    draw_text(c, MX + 12, y + 6, "DATE CHECK", 10, RED, True)
    draw_para(c, MX + 12, y + 19,
              "Stories first reported on 17 Nov were left out on purpose: "
              "Peltola's Alaska win, Nvidia's quarter, the Prague train "
              "crash, Mongolia's president resigning. The trilateral "
              "summit and Anthropic's debut are 19 Nov, not 18 Nov.", 9,
              616, INK, False, leading=12)
    fx = MX + 652
    draw_para(c, fx, y + 6,
              "Sources: Reuters, AP, AFP, Al Jazeera, Bloomberg, UN News, "
              "NASA/JPL, RNZ.", 9, W - MX - fx, MUTED, False, leading=12)
    draw_text(c, fx, y + 34, "Drawn entirely in code.", 9, MUTED, True)


def draw_page(c):
    c.rect(0, 0, W, H, PAPER)
    draw_masthead(c)
    y = draw_region_strip(c, 104)
    y = draw_field_strip(c, y + 6)
    y = draw_numbers(c, y + 8)
    y = draw_cards(c, y + 6)
    y = draw_bottom(c, y + 6)
    draw_footer(c, y + 6)


def main():
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    c = Canvas(W, H, PAPER)
    if os.environ.get("MAKEFUN_TEST") == "font":
        draw_specimen(c)
    else:
        draw_page(c)
    write_png(os.path.join(out_dir, "entry.png"), c.px, W, H)


if __name__ == "__main__":
    main()
