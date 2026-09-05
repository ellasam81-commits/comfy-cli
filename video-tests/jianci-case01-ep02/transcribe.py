"""Independent speech recognition for dialogue QA; never generate replacement speech."""

import json
from pathlib import Path

from faster_whisper import WhisperModel

out = Path("output/jianci-episode02")
model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
rows = []
for path in sorted(out.glob("*-raw.mp4")):
    segments, info = model.transcribe(str(path), language="zh", beam_size=5, word_timestamps=True)
    row = {"clip": path.name, "segments": [s._asdict() for s in segments]}
    rows.append(row)
    print(path.name, " ".join(s["text"] for s in row["segments"]), flush=True)
(out / "transcription.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
