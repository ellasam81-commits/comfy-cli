#!/usr/bin/env python3
"""Export the locked S01E10 triptychs as provider-safe 320x540 base64 references."""
from __future__ import annotations

import argparse
from base64 import b64encode
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "references/s1e10-12/storyboard_raw"
DEST = ROOT / "references/s1e10-12/storyboard_video_refs"


def encode_jpeg(image: Image.Image) -> str:
    stream = BytesIO()
    image.convert("RGB").save(stream, format="JPEG", quality=95, optimize=True)
    return b64encode(stream.getvalue()).decode("ascii")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="ascii")


def export_triptych(clip_id: str) -> None:
    source = RAW / f"S01E10_{clip_id}.png"
    with Image.open(source) as board:
        board = board.convert("RGB")
        third = board.width // 3
        for index in range(3):
            panel = board.crop((index * third, 0, (index + 1) * third if index < 2 else board.width, board.height))
            # 320px avoids the rejected 288px references from the first proof attempt.
            panel = ImageOps.fit(panel, (320, 540), Image.Resampling.LANCZOS)
            target = DEST / f"S01E10_{clip_id}_shot_{index + 1}.jpg.b64"
            write_text(target, encode_jpeg(panel))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--continuity", type=Path, required=True, help="Text-free raw last frame from accepted clip 01")
    args = parser.parse_args()
    if not args.continuity.is_file():
        raise SystemExit(f"Missing accepted clip-01 continuity frame: {args.continuity}")
    for value in range(2, 13):
        export_triptych(f"{value:02d}")
    with Image.open(args.continuity) as frame:
        width, height = frame.size
        if width < 300 or height < 300:
            raise SystemExit(f"Continuity frame is too small for provider: {width}x{height}")
        write_text(DEST / "S01E10_01_continuity.jpg.b64", encode_jpeg(frame))
    print("Exported 33 storyboard panels and one accepted clip-01 continuity reference.")


if __name__ == "__main__":
    main()
