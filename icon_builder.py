from pathlib import Path
from PIL import Image

SOURCE = Path("app_icon.png")
OUT_ICO = Path("app_icon.ico")


def build_icon() -> None:
    image = Image.open(SOURCE).convert("RGBA")
    image.save(
        OUT_ICO,
        "ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


if __name__ == "__main__":
    build_icon()

# Approved transparent blue T artwork is stored in app_icon.png.
