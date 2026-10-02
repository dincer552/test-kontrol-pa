from pathlib import Path
from PIL import Image, ImageDraw

OUT_PNG = Path("app_icon.png")
OUT_ICO = Path("app_icon.ico")

BLUE = (0, 122, 255, 255)


def build_icon() -> None:
    # Transparent, high-resolution blue T used for both the application logo
    # and the Windows taskbar/start-menu icon.
    size = 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Bold geometric T, matching the approved transparent logo design.
    top = 180
    left = 210
    right = 814
    stem_left = 427
    stem_right = 597
    bottom = 820
    draw.rectangle((left, top, right, 277), fill=BLUE)
    draw.rectangle((stem_left, 277, stem_right, bottom), fill=BLUE)

    image.save(OUT_PNG, "PNG", optimize=True)
    image.save(
        OUT_ICO,
        "ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    build_icon()
