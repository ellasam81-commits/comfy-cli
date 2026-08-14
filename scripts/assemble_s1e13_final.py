#!/usr/bin/env python3
"""Assemble verified S01E13 clips with bilingual subtitles."""
from __future__ import annotations

import json
import os
from pathlib import Path

import assemble_s1e10_12_final as base


ROOT = Path.cwd()
PLAN = ROOT / "references" / "s1e13" / "production_plan.json"


def main() -> None:
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    if [episode.get("episode") for episode in plan.get("episodes", [])] != ["S01E13"]:
        raise RuntimeError("S01E13 assembly plan must contain only S01E13")
    base.PLAN = PLAN
    base.RAW_ROOT = ROOT / os.environ.get("GENERATION_OUTPUT_DIR", "output/s1e13-all")
    base.OUT = ROOT / os.environ.get("FINAL_OUTPUT_DIR", "output/s1e13-final")
    base.OUT.mkdir(parents=True, exist_ok=True)
    final = base.assemble_episode(plan, plan["episodes"][0], base.font_dir())
    package = base.OUT / "S01E13_NoNeedleMarks_Final.zip"
    pending = base.OUT / "S01E13_NoNeedleMarks_Final.pending.zip"
    base.run(["zip", "-j", "-9", str(pending), str(final)])
    pending.replace(package)
    print(json.dumps({"final": str(final), "zip": str(package)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
