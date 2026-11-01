#!/usr/bin/env python3
"""
Convert a portrait photo into ASCII art sized for the SVG profile card.

Pipeline
  1. Load the photo (flatten transparency onto white).
  2. Detect the plain white background by flood-filling from the borders,
     so only the person is rendered (background becomes blank space).
  3. Crop to the subject, boost local contrast (CLAHE) and sharpen.
  4. Resize with a character-aspect correction and map brightness -> glyph.
  5. Write ascii.txt (+ an optional PNG preview).

Usage
  python ascii_convert.py photo.png                 # defaults: 40 cols x ~24 rows
  python ascii_convert.py photo.png --cols 44 --rows 25 --preview preview.png
"""
import argparse
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CANDIDATES = " .'`,:;-~\"_^!i+<>l/\\|()[]{}1?trcvuxzjfILJYUCXZOQ0o*adbkhpqwmBW8M&%$#@"


def build_ramp(candidates=CANDIDATES, size=24):
    """Order glyphs sparse -> dense by measured ink coverage in a monospace font."""
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", size)
    except OSError:
        return " .:-=+*#%@"
    scored = []
    for ch in dict.fromkeys(candidates):
        im = Image.new("L", (size, size * 2), 0)
        ImageDraw.Draw(im).text((2, 2), ch, font=font, fill=255)
        scored.append((np.asarray(im, dtype=np.float32).mean(), ch))
    scored.sort()
    # keep ~16 well-spaced levels so the output reads as smooth shading, not noise
    lo, hi = scored[0][0], scored[-1][0]
    levels, out = np.linspace(lo, hi, 16), []
    for t in levels:
        ch = min(scored, key=lambda s: abs(s[0] - t))[1]
        if ch not in out:
            out.append(ch)
    return "".join(out)


RAMP = build_ramp()


def load_rgb(path):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA", "P"):
        im = im.convert("RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        im = bg
    return np.array(im.convert("RGB"))


def subject_mask(rgb, bg_thresh=238):
    """True where the person is; background = near-white region touching the border."""
    near_white = (rgb.min(axis=2) >= bg_thresh).astype(np.uint8)
    n, labels = cv2.connectedComponents(near_white, connectivity=4)
    border = np.unique(np.concatenate(
        [labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1]]))
    bg = np.isin(labels, [b for b in border if b != 0]) & (near_white == 1)
    fg = (~bg).astype(np.uint8)
    # clean speckles and fill small holes (e.g. glasses glare)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, k)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (15, 15)))
    return fg.astype(bool)


def convert(path, cols, rows, cell_aspect, gamma, clip, invert, min_level):
    rgb = load_rgb(path)
    mask = subject_mask(rgb)
    ys, xs = np.where(mask)
    if len(ys) == 0:
        sys.exit("Could not find a subject - is the image blank?")
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    rgb, mask = rgb[y0:y1, x0:x1], mask[y0:y1, x0:x1]

    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(3, 3)).apply(gray)
    blur = cv2.GaussianBlur(gray, (0, 0), 2.0)
    gray = cv2.addWeighted(gray, 1.6, blur, -0.6, 0)  # unsharp mask

    h, w = gray.shape
    if rows is None:
        rows = max(1, round(cols * (h / w) * cell_aspect))
    g = cv2.resize(gray, (cols, rows), interpolation=cv2.INTER_AREA).astype(np.float32)
    m = cv2.resize(mask.astype(np.float32), (cols, rows), interpolation=cv2.INTER_AREA) > 0.5

    lo, hi = np.percentile(g[m], [clip, 100 - clip])
    g = np.clip((g - lo) / max(hi - lo, 1e-6), 0, 1) ** gamma
    if invert:
        g = 1 - g

    n = len(RAMP) - 1
    lines = []
    for r in range(rows):
        row = []
        for c in range(cols):
            if not m[r, c]:
                row.append(" ")
            else:
                # floor keeps dark regions (hair, shadows) visible as a silhouette
                idx = int(round(min_level + g[r, c] * (n - min_level)))
                row.append(RAMP[idx])
        lines.append("".join(row).rstrip())
    width = max(len(l) for l in lines)
    return [l.ljust(width) for l in lines]


def render_preview(lines, out):
    try:
        font = ImageFont.truetype("DejaVuSansMono.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    cw, ch = 9.6, 20
    img = Image.new("RGB", (int(len(lines[0]) * cw + 30), int(len(lines) * ch + 30)), "#161b22")
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text((15, 15 + i * ch), l, font=font, fill="#c9d1d9")
    img.save(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("-o", "--output", default="ascii.txt")
    ap.add_argument("--cols", type=int, default=40, help="character columns (default 40)")
    ap.add_argument("--rows", type=int, default=25, help="character rows (default: auto from aspect)")
    ap.add_argument("--cell-aspect", type=float, default=0.48,
                    help="char width / line height; 9.6px / 20px = 0.48")
    ap.add_argument("--gamma", type=float, default=1.35, help="<1 brighter, >1 darker")
    ap.add_argument("--clip", type=float, default=4.0, help="percentile clipping for contrast")
    ap.add_argument("--min-level", type=int, default=2, help="darkest glyph index used for the subject")
    ap.add_argument("--invert", action="store_true", help="dark = dense (use for light backgrounds)")
    ap.add_argument("--preview", help="write a PNG preview")
    a = ap.parse_args()

    lines = convert(a.image, a.cols, a.rows, a.cell_aspect, a.gamma, a.clip, a.invert, a.min_level)
    with open(a.output, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Wrote {a.output}: {len(lines[0])} cols x {len(lines)} rows")
    if a.preview:
        render_preview(lines, a.preview)
        print(f"Wrote {a.preview}")


if __name__ == "__main__":
    main()
