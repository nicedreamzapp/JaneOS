"""Generate a super-dope kid icon for Jane's Desktop launcher."""
import os
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).parent / "build" / "icon.iconset"
OUT.mkdir(parents=True, exist_ok=True)

SIZES = [16, 32, 64, 128, 256, 512, 1024]

# Fonts on macOS — try a few rounded/playful options
FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Marker Felt.ttc",
    "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf",
    "/System/Library/Fonts/Supplemental/Chalkboard SE Bold.ttc",
    "/System/Library/Fonts/Supplemental/Chalkboard SE.ttc",
    "/System/Library/Fonts/Avenir Next.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
]


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def draw_icon(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # rounded square background with diagonal pink → purple → blue gradient
    radius = int(size * 0.22)
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bgd = ImageDraw.Draw(bg)
    # gradient by horizontal lines
    for y in range(size):
        t = y / size
        # interpolate three stops: hot pink → purple → soft blue
        if t < 0.5:
            u = t * 2
            r = int(255 + (130 - 255) * u)
            g = int(58 + (78 - 58) * u)
            b = int(161 + (255 - 161) * u)
        else:
            u = (t - 0.5) * 2
            r = int(130 + (110 - 130) * u)
            g = int(78 + (180 - 78) * u)
            b = int(255 + (255 - 255) * u)
        bgd.line([(0, y), (size, y)], fill=(r, g, b, 255))
    # rounded mask
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    img.paste(bg, (0, 0), mask)

    # glow ring
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring)
    rd.rounded_rectangle(
        (int(size * 0.06), int(size * 0.06), int(size * 0.94), int(size * 0.94)),
        radius=int(radius * 0.8), outline=(255, 255, 255, 90), width=max(2, size // 80),
    )
    img = Image.alpha_composite(img, ring)

    # sparkle stars (fixed positions, scaled)
    def star(cx, cy, r, fill):
        pts = []
        for i in range(10):
            ang = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
        ImageDraw.Draw(img).polygon(pts, fill=fill)

    # 3 stars — top-right, top-left, bottom-right
    s = size
    star(s * 0.82, s * 0.18, s * 0.06, (255, 255, 255, 230))
    star(s * 0.18, s * 0.22, s * 0.045, (255, 240, 200, 220))
    star(s * 0.86, s * 0.78, s * 0.05, (255, 220, 240, 230))

    # small heart bottom-left
    def heart(cx, cy, r, fill):
        # two circles + triangle
        ImageDraw.Draw(img).ellipse(
            (cx - r, cy - r, cx, cy), fill=fill,
        )
        ImageDraw.Draw(img).ellipse(
            (cx, cy - r, cx + r, cy), fill=fill,
        )
        ImageDraw.Draw(img).polygon(
            [(cx - r, cy - r * 0.2), (cx + r, cy - r * 0.2), (cx, cy + r * 1.2)], fill=fill,
        )

    heart(s * 0.15, s * 0.78, s * 0.05, (255, 110, 160, 240))

    # The big "J" — playful, with pink highlight
    font_path = find_font()
    if font_path and size >= 64:
        try:
            font = ImageFont.truetype(font_path, int(size * 0.7))
        except Exception:
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()

    # Draw "J" with shadow
    text = "J"
    # measure
    bbox = ImageDraw.Draw(img).textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) // 2 - bbox[0]
    ty = (size - th) // 2 - bbox[1] - int(size * 0.04)

    # shadow
    shadow_layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_layer)
    sd.text((tx + max(2, size // 80), ty + max(2, size // 60)), text, font=font, fill=(0, 0, 0, 110))
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(max(1, size // 100)))
    img = Image.alpha_composite(img, shadow_layer)

    d2 = ImageDraw.Draw(img)
    # white fill J with subtle gradient effect via two passes
    d2.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))
    # cute accent bar at the bottom of J
    bar_h = max(3, size // 40)
    bar_y = int(size * 0.92)
    d2.rounded_rectangle(
        (int(size * 0.2), bar_y - bar_h, int(size * 0.8), bar_y),
        radius=bar_h // 2,
        fill=(255, 255, 255, 200),
    )

    # tiny "ane" subtitle below J? or "Jane" wordmark
    if size >= 128:
        try:
            sub_font = ImageFont.truetype(font_path, int(size * 0.10))
        except Exception:
            sub_font = ImageFont.load_default()
        sub = "Jane"
        sb = d2.textbbox((0, 0), sub, font=sub_font)
        sw = sb[2] - sb[0]
        d2.text(
            ((size - sw) // 2 - sb[0], int(size * 0.78)),
            sub, font=sub_font, fill=(255, 255, 255, 235),
        )

    return img


def main():
    # Apple iconset names
    targets = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    for name, sz in targets:
        img = draw_icon(sz)
        img.save(OUT / name)
        print(f"  {name} ({sz}x{sz})")
    print(f"iconset → {OUT}")


if __name__ == "__main__":
    main()
