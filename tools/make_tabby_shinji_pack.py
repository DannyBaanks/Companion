"""Build the tabby cat pack by painting the existing Malbolgato frames."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "packs" / "malbolge-cat"
TARGET = ROOT / "packs" / "tabby-shinji-cat"
STATES = ("idle", "thinking", "working", "success", "error", "waiting")


def paint_frame(image: Image.Image) -> Image.Image:
    image = image.convert("RGBA")
    draw = ImageDraw.Draw(image)

    # Warm gray-brown tabby markings on the forehead and cheeks.
    stripe = (137, 112, 101, 255)
    dark_stripe = (72, 57, 57, 255)
    for points in (
        [(73, 29), (77, 50)],
        [(84, 25), (86, 48)],
        [(95, 28), (92, 49)],
        [(62, 65), (74, 72)],
        [(58, 75), (71, 79)],
        [(103, 70), (116, 65)],
        [(105, 79), (120, 76)],
    ):
        draw.line(points, fill=stripe, width=2)
    draw.line([(78, 29), (81, 47)], fill=dark_stripe, width=2)
    draw.line([(89, 27), (89, 48)], fill=dark_stripe, width=2)

    # A pale school shirt with Shinji-inspired blue collar and red tie.
    shirt = (218, 224, 226, 255)
    shirt_shadow = (164, 180, 191, 255)
    blue = (49, 78, 119, 255)
    red = (170, 55, 61, 255)
    draw.polygon([(61, 101), (76, 96), (94, 98), (111, 101), (120, 132),
                  (113, 157), (66, 157), (57, 132)], fill=shirt)
    draw.polygon([(61, 101), (76, 96), (84, 108), (73, 116), (57, 109)], fill=shirt_shadow)
    draw.polygon([(94, 98), (111, 101), (120, 116), (106, 115), (84, 108)], fill=shirt_shadow)
    draw.line([(76, 97), (84, 108), (94, 98)], fill=blue, width=3)
    draw.line([(84, 108), (106, 115)], fill=blue, width=3)
    draw.polygon([(84, 108), (92, 110), (89, 134), (83, 134)], fill=red)
    draw.line([(66, 157), (113, 157)], fill=blue, width=2)

    # Small blue sleeve cuffs remain visible beside the front paws.
    draw.line([(56, 111), (64, 116)], fill=blue, width=3)
    draw.line([(112, 115), (120, 111)], fill=blue, width=3)
    return image


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    for state in STATES:
        source = Image.open(SOURCE / f"{state}.gif")
        frames = []
        durations = []
        for index in range(source.n_frames):
            source.seek(index)
            frames.append(paint_frame(source.copy()))
            durations.append(source.info.get("duration", 100))
        frames[0].save(
            TARGET / f"{state}.gif",
            save_all=True,
            append_images=frames[1:],
            duration=durations,
            loop=source.info.get("loop", 0),
            disposal=2,
            optimize=False,
        )


if __name__ == "__main__":
    main()
