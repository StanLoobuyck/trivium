# /// script
# requires-python = ">=3.11"
# dependencies = ["pymupdf>=1.24"]
# ///
"""Cut a figure out of a slide PDF page as a vector \\includegraphics, plus a PNG preview to check the crop.

The box is given as fractions of the page (0 = left/top, 1 = right/bottom), read off the preview PNG:
  uv run crop.py SLIDES.pdf PAGE X0 Y0 X1 Y1 [--width 0.7] [--preview out.png]
Prints the LaTeX line; the PDF path in it is relative to the course folder (copy the PDF to slides/ there).
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    import pymupdf as fitz

    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", type=Path)
    ap.add_argument("page", type=int)
    ap.add_argument("box", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
    ap.add_argument("--width", type=float, default=0.7, help="figure width as fraction of \\linewidth")
    ap.add_argument("--preview", type=Path)
    a = ap.parse_args()
    x0, y0, x1, y1 = a.box
    if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
        ap.error("box must satisfy 0 <= X0 < X1 <= 1 and 0 <= Y0 < Y1 <= 1")
    page = fitz.open(a.pdf)[a.page - 1]
    w, h = page.rect.width, page.rect.height
    # trim = left bottom right top, in bp (PDF points), measured from the page edges
    trim = (x0 * w, (1 - y1) * h, (1 - x1) * w, y0 * h)
    clip = fitz.Rect(x0 * w, y0 * h, x1 * w, y1 * h)
    preview = a.preview or Path(f"crop_p{a.page:03d}.png")
    page.get_pixmap(dpi=110, clip=clip).save(preview)
    print(f"\\includegraphics[page={a.page}, trim={trim[0]:.0f} {trim[1]:.0f} {trim[2]:.0f} {trim[3]:.0f}, clip, "
          f"width={a.width:g}\\linewidth]{{slides/{a.pdf.name}}}")
    print(f"preview: {preview}")


if __name__ == "__main__":
    main()
