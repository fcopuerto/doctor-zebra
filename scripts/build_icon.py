"""Generate the Doctor Zebra logo and platform icon files.

Outputs:
    static/icon.png   – 1024×1024 master PNG
    static/icon.ico   – Windows multi-resolution icon (16/24/32/48/64/128/256)
    static/icon.icns  – macOS bundle icon (built via `iconutil`)
    static/logo.svg   – clean SVG for web / README

The artwork is drawn directly with Pillow so the build has no SVG-renderer
dependency. The SVG is hand-written to mirror the raster design.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / 'static'
STATIC.mkdir(exist_ok=True)

# ---- Palette ---------------------------------------------------------------
BG_NAVY = (13, 27, 42, 255)        # deep navy background
LABEL_WHITE = (255, 255, 255, 255)
BAR_DARK = (13, 27, 42, 255)        # zebra bars (same navy for cohesion)
CROSS_RED = (220, 38, 38, 255)      # medical cross
SHADOW = (0, 0, 0, 60)              # subtle drop shadow under the label

SIZE = 1024  # master canvas


def draw_master() -> Image.Image:
    img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Background: rounded square
    bg_radius = 200
    d.rounded_rectangle(
        [(0, 0), (SIZE, SIZE)],
        radius=bg_radius,
        fill=BG_NAVY,
    )

    # White "label" centered, rotated slightly for character
    label_margin = 130
    label_box = (label_margin, label_margin + 30,
                 SIZE - label_margin, SIZE - label_margin - 30)
    label_radius = 60

    # Drop shadow (offset down-right)
    shadow = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        [(label_box[0] + 14, label_box[1] + 22),
         (label_box[2] + 14, label_box[3] + 22)],
        radius=label_radius,
        fill=SHADOW,
    )
    img = Image.alpha_composite(img, shadow)
    d = ImageDraw.Draw(img)

    # Label
    d.rounded_rectangle(label_box, radius=label_radius, fill=LABEL_WHITE)

    # ---- Zebra bars (barcode style) on the left half ---------------------
    bar_left_pad = 60
    bar_right_pad = 40
    bar_area_left = label_box[0] + bar_left_pad
    bar_area_top = label_box[1] + 90
    bar_area_bottom = label_box[3] - 90
    bar_area_right = label_box[0] + (label_box[2] - label_box[0]) // 2 - bar_right_pad

    # Variable-width bars, mimicking a barcode
    widths = [22, 10, 30, 14, 8, 36, 12, 18, 28]  # alternating bar/gap visually
    gap = 14
    x = bar_area_left
    for i, w in enumerate(widths):
        if x + w > bar_area_right:
            break
        # Skip every other for the "gap" feel
        if i % 2 == 0:
            d.rounded_rectangle(
                [(x, bar_area_top), (x + w, bar_area_bottom)],
                radius=4,
                fill=BAR_DARK,
            )
        x += w + gap

    # ---- Medical cross on the right half ----------------------------------
    cross_cx = label_box[0] + 3 * (label_box[2] - label_box[0]) // 4
    cross_cy = (label_box[1] + label_box[3]) // 2
    arm_len = 150
    arm_thick = 56
    arm_radius = 16

    # Vertical bar
    d.rounded_rectangle(
        [(cross_cx - arm_thick // 2, cross_cy - arm_len),
         (cross_cx + arm_thick // 2, cross_cy + arm_len)],
        radius=arm_radius,
        fill=CROSS_RED,
    )
    # Horizontal bar
    d.rounded_rectangle(
        [(cross_cx - arm_len, cross_cy - arm_thick // 2),
         (cross_cx + arm_len, cross_cy + arm_thick // 2)],
        radius=arm_radius,
        fill=CROSS_RED,
    )

    return img


def export_png_sizes(master: Image.Image, sizes: list[int], outdir: Path) -> dict[int, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    paths: dict[int, Path] = {}
    for s in sizes:
        im = master.resize((s, s), Image.LANCZOS)
        p = outdir / f'icon_{s}.png'
        im.save(p, 'PNG')
        paths[s] = p
    return paths


def build_ico(master: Image.Image, out: Path) -> None:
    sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    master.save(out, format='ICO', sizes=sizes)


def build_icns(master: Image.Image, out: Path, work: Path) -> bool:
    """Use macOS `iconutil` to build an .icns from a generated .iconset."""
    iconset = work / 'icon.iconset'
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True)

    # macOS expects these specific names: icon_16x16.png, icon_16x16@2x.png, etc.
    spec = [
        (16, 'icon_16x16.png'),
        (32, 'icon_16x16@2x.png'),
        (32, 'icon_32x32.png'),
        (64, 'icon_32x32@2x.png'),
        (128, 'icon_128x128.png'),
        (256, 'icon_128x128@2x.png'),
        (256, 'icon_256x256.png'),
        (512, 'icon_256x256@2x.png'),
        (512, 'icon_512x512.png'),
        (1024, 'icon_512x512@2x.png'),
    ]
    for size, name in spec:
        master.resize((size, size), Image.LANCZOS).save(iconset / name, 'PNG')

    res = subprocess.run(
        ['iconutil', '-c', 'icns', str(iconset), '-o', str(out)],
        capture_output=True, text=True,
    )
    shutil.rmtree(iconset, ignore_errors=True)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        return False
    return True


SVG_TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" role="img" aria-label="Doctor Zebra logo">
  <defs>
    <clipPath id="bg-clip">
      <rect x="0" y="0" width="1024" height="1024" rx="200" ry="200"/>
    </clipPath>
  </defs>
  <g clip-path="url(#bg-clip)">
    <rect width="1024" height="1024" fill="#0d1b2a"/>
    <!-- shadow -->
    <rect x="144" y="182" width="754" height="682" rx="60" ry="60" fill="#000" opacity="0.18"/>
    <!-- label -->
    <rect x="130" y="160" width="754" height="682" rx="60" ry="60" fill="#ffffff"/>
    <!-- zebra bars -->
    <g fill="#0d1b2a">
      <rect x="190" y="250" width="22" height="510" rx="4"/>
      <rect x="246" y="250" width="30" height="510" rx="4"/>
      <rect x="298" y="250" width="8"  height="510" rx="4"/>
      <rect x="328" y="250" width="12" height="510" rx="4"/>
      <rect x="362" y="250" width="28" height="510" rx="4"/>
    </g>
    <!-- medical cross -->
    <g fill="#dc2626">
      <rect x="676" y="351" width="56" height="300" rx="16"/>
      <rect x="554" y="473" width="300" height="56" rx="16"/>
    </g>
  </g>
</svg>
"""


def main() -> int:
    master = draw_master()

    # Master PNG (handy for README, OG image, etc.)
    master_png = STATIC / 'icon.png'
    master.save(master_png, 'PNG')
    print(f'wrote {master_png.relative_to(ROOT)}')

    # Windows .ico
    ico_path = STATIC / 'icon.ico'
    build_ico(master, ico_path)
    print(f'wrote {ico_path.relative_to(ROOT)}')

    # macOS .icns
    icns_path = STATIC / 'icon.icns'
    work = ROOT / 'build_icons'
    work.mkdir(exist_ok=True)
    if build_icns(master, icns_path, work):
        print(f'wrote {icns_path.relative_to(ROOT)}')
    shutil.rmtree(work, ignore_errors=True)

    # SVG
    svg_path = STATIC / 'logo.svg'
    svg_path.write_text(SVG_TEMPLATE, encoding='utf-8')
    print(f'wrote {svg_path.relative_to(ROOT)}')

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
