#!/usr/bin/env python3
"""Assemble verified S01E14 clips with author header and bilingual subtitles."""
from __future__ import annotations

import json
import os
from pathlib import Path

import assemble_s1e10_12_final as base


ROOT = Path.cwd()
PLAN = ROOT / "references" / "s1e14" / "production_plan.json"

ENGLISH_LINES = [
    "Jian Ci, the sample marked for disposal has lost its destination.",
    "Xu Wei, this was not applied by the person themselves.",
    "Lin Qian, the intervals look scheduled.",
    "Lin Qian, three stops form one night route.",
    "Zhou Qiao, this does not look like a clinic.",
    "Lin Qian, the passing result was added later.",
    "Jian Ci, a signature does not mean consent.",
    "Jian Ci, there is one more vehicle run tonight.",
    "Lin Qian, the cold cabinet is yours.",
    "Lin Qian, it changes people before it changes places.",
    "Lin Qian, save people first, then secure the evidence.",
    "Lin Qian, the van has entered the old warehouse.",
]


def runtime_plan() -> dict:
    raw = json.loads(PLAN.read_text(encoding="utf-8"))
    target = raw.get("runtime_target", {})
    if raw.get("season") != 1 or raw.get("episode") != 14:
        raise RuntimeError("S01E14 assembly source plan identity is invalid")
    if target.get("clips") != 12 or target.get("seconds_per_clip") != 5 or target.get("generate_audio") is not True:
        raise RuntimeError("S01E14 assembly runtime lock is invalid")
    clips = raw.get("clips")
    if not isinstance(clips, list) or [item.get("id") for item in clips] != list(range(1, 13)):
        raise RuntimeError("S01E14 assembly requires 12 locked clips")
    normalized = []
    for index, (source, en) in enumerate(zip(clips, ENGLISH_LINES), 1):
        speaker, marker, zh = str(source.get("audio", "")).partition("\uFF1A")
        if not marker or not speaker or not zh:
            raise RuntimeError(f"S01E14 dialogue format is invalid for clip {index:02d}")
        normalized.append({"id": f"{index:02d}", "dialogue": [{"speaker": speaker, "zh": zh, "en": en}]})
    return {
        "series_title_zh": raw["series"], "maker_zh": raw["author"],
        "episodes": [{"episode": "S01E14", "title_zh": raw["title_zh"], "title_en": "Healed Evidence", "clips": normalized}],
    }


def main() -> None:
    plan = runtime_plan()
    base.PLAN = PLAN
    base.RAW_ROOT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e14-all")
    base.OUT = ROOT / os.environ.get("FINAL_OUTPUT_DIR", "output/s1e14-final")
    base.OUT.mkdir(parents=True, exist_ok=True)
    episode = plan["episodes"][0]
    final = base.assemble_episode(plan, episode, base.font_dir())
    package = base.OUT / "S01E14_HealedEvidence_Final.zip"
    pending = base.OUT / "S01E14_HealedEvidence_Final.pending.zip"
    base.run(["zip", "-j", "-9", str(pending), str(final)])
    pending.replace(package)
    print(json.dumps({"final": str(final), "zip": str(package)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
