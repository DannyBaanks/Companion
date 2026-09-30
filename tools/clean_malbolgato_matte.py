"""Strip the chroma matte baked into packs/malbolge-cat.

The exported GIFs keep two leftovers that read as a colored border:
a cyan-screen fringe around the silhouette, and a purple checker
stuck on the ear. Neither color belongs to the black-and-neon cat.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "packs" / "malbolge-cat"
STATES = ("idle", "thinking", "working", "success", "error", "waiting")


def is_chroma_matte(r: int, g: int, b: int) -> bool:
    """True for cyan-screen fringe and the purple checker, not for neon green."""
    if r <= 45 and g >= 22 and b >= 22 and r + 8 < g and r + 8 < b and abs(g - b) <= 180 and b > g * 0.45:
        return True
    # Blue and lavender squares of the checker that the magenta pass leaves behind.
    if b >= 140 and b >= g + 20 and r <= 130 and b > r + 40:
        return True
    if r <= 8 and g >= 18 and b >= 18 and abs(g - b) <= 18:
        return True
    if b >= 70 and r <= 30 and g <= 50 and b > r + 40 and b > g + 20:
        return True
    if b >= 35 and r >= 18 and g <= 45 and b >= g + 18 and r >= g + 10 and b >= int(r * 0.65):
        return True
    if r >= 140 and b >= 140 and g + 25 < min(r, b):
        return True
    # Pure red specks and the brighter cyan key that survived the first cut.
    if r >= 140 and g <= 25 and b <= 25:
        return True
    if g >= 100 and b >= 100 and abs(g - b) <= 30 and r + 40 < g and r + 40 < b and r < 140:
        return True
    return False


def _cleaned_frames(source: Image.Image) -> tuple[list[Image.Image], list[int]]:
    frames: list[Image.Image] = []
    durations: list[int] = []
    for index in range(source.n_frames):
        source.seek(index)
        rgba = source.convert("RGBA")
        width, height = rgba.size
        src = rgba.load()
        kept: Counter[tuple[int, int, int]] = Counter()
        mask: list[tuple[int, int, int] | None] = []
        for y in range(height):
            for x in range(width):
                red, green, blue, alpha = src[x, y]
                if alpha < 128 or is_chroma_matte(red, green, blue):
                    mask.append(None)
                else:
                    color = (red, green, blue)
                    kept[color] += 1
                    mask.append(color)
        if len(kept) > 255:
            raise RuntimeError(f"frame {index} still has {len(kept)} colors after the matte cut")
        palette = [(255, 0, 255)] + list(kept)
        index_of = {color: slot for slot, color in enumerate(palette)}
        frame = Image.new("P", (width, height))
        frame.putpalette([channel for rgb in palette for channel in rgb] + [0] * ((256 - len(palette)) * 3))
        frame.putdata([0 if color is None else index_of[color] for color in mask])
        frames.append(frame)
        durations.append(int(source.info.get("duration", 100)))
    return frames, durations


def clean_gif(path: Path) -> None:
    source = Image.open(path)
    frames, durations = _cleaned_frames(source)
    loop = source.info.get("loop", 0)
    source.close()
    tmp = path.with_name(path.stem + ".cleaning.gif")
    frames[0].save(
        tmp,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=loop,
        disposal=2,
        transparency=0,
        optimize=False,
    )
    tmp.replace(path)


def main() -> None:
    for state in STATES:
        clean_gif(PACK / f"{state}.gif")
        print(state)


if __name__ == "__main__":
    main()
