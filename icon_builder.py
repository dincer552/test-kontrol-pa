from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


SIZE = 512
OUT_PNG = Path("app_icon.png")
OUT_ICO = Path("app_icon.ico")


def build_icon() -> None:
    image = Image.new("RGBA", (SIZE, SIZE), (248, 251, 255, 255))
    draw = ImageDraw.Draw(image)

    # Soft white/blue rounded app tile.
    draw.rounded_rectangle(
        (28, 28, SIZE - 28, SIZE - 28),
        radius=72,
        fill=(250, 252, 255, 255),
        outline=(190, 215, 250, 255),
        width=3,
    )

    # Shadow behind the blue T.
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((100, 116, 412, 432), radius=42, fill=(0, 64, 160, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(14))
    image.alpha_composite(shadow)

    # Bold blue T, matching the approved design.
    t = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    td = ImageDraw.Draw(t)
    td.rounded_rectangle((94, 100, 418, 222), radius=38, fill=(31, 154, 246, 255))
    td.rounded_rectangle((190, 190, 322, 418), radius=34, fill=(7, 83, 210, 255))
    td.rectangle((190, 178, 322, 232), fill=(12, 112, 230, 255))

    # Diagonal highlight.
    highlight = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    hd = ImageDraw.Draw(highlight)
    hd.polygon([(94, 100), (418, 100), (322, 190), (190, 418), (190, 190), (94, 190)], fill=(74, 205, 255, 85))
    t = Image.alpha_composite(t, highlight)

    # Cyan edge.
    td = ImageDraw.Draw(t)
    td.rounded_rectangle((94, 100, 418, 222), radius=38, outline=(53, 205, 255, 220), width=6)
    td.rounded_rectangle((190, 190, 322, 418), radius=34, outline=(20, 150, 255, 180), width=6)

    image.alpha_composite(t)

    image.save(OUT_PNG, "PNG", optimize=True)
    image.save(
        OUT_ICO,
        "ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    build_icon()
