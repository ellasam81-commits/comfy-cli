"""Generate only the approved first episode, with a six-submission hard limit."""

import importlib.util
import json
import os
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("transition", ROOT.parent / "jianci-transition" / "run_test.py")
shared = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared)


def config():
    cfg = json.loads((ROOT / "episode.json").read_text())
    assert cfg["episode"] == 1 and cfg["duration_seconds"] == 60 and cfg["shots"] == 12
    assert len(cfg["clips"]) == 6 and [c["id"] for c in cfg["clips"]] == [f"{i:02d}" for i in range(1, 7)]
    assert len(cfg["subtitles"]) == 12
    assert all(0 <= s["start"] < s["end"] <= 60 for s in cfg["subtitles"])
    assert all(len(c["prompt"]) < 7000 for c in cfg["clips"])
    return cfg


def main():
    cfg = config()
    if os.environ.get("JIANCI_EP01_EXECUTE") != "1":
        print("Validated: Episode 01 only, 6 x 10 sec, 12 shots, estimated USD 3. No API calls.")
        return
    if int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")) != 1:
        raise RuntimeError("No automatic rerun: could duplicate paid submissions.")
    out = Path("output/jianci-episode01")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "report.json").exists():
        raise RuntimeError("Existing report: refusing duplicate generation.")
    sha = os.environ["GITHUB_SHA"]
    repo = os.environ["GITHUB_REPOSITORY"]
    assert re.fullmatch(r"[a-f0-9]{40}", sha)
    assert repo == "ellasam81-commits/comfy-cli"
    reference = f"https://raw.githubusercontent.com/{repo}/{sha}/video-tests/jianci-transition/modern.png"
    gateway = shared.Gateway(os.environ.get("SEGMIND_API_KEY"))
    gateway.request("/v1/get-user-credits")
    report = {"episode": 1, "model": "wan3.0-video", "estimated_usd": 3, "clips": []}
    shared.save_report(out, report)
    pending = []
    for clip in cfg["clips"]:
        row = {"id": clip["id"], "state": "SUBMITTING"}
        report["clips"].append(row)
        shared.save_report(out, report)
        try:
            result = gateway.request("/v2/wan3.0-video", {
                "prompt": clip["prompt"], "reference_images": [reference],
                "duration": 10, "resolution": "480P", "aspect_ratio": "16:9",
                "audio": True, "watermark": False, "prompt_extend": False,
                "enable_thinking": True, "seed": 906101,
                "negative_prompt": "live action, 3D, subtitles, text, office, dissolves, extra cuts, gore, changing faces",
            })
            request_id = result["request_id"]
            assert re.fullmatch(r"[A-Za-z0-9_-]+", request_id)
            row.update(state="QUEUED", request_id=request_id)
            pending.append(row)
            print("Accepted clip", clip["id"], flush=True)
        except Exception as exc:
            row.update(state="SUBMISSION_UNKNOWN_OR_FAILED", error_type=type(exc).__name__)
            shared.save_report(out, report)
            break
        shared.save_report(out, report)
    deadline = time.monotonic() + 1500
    while pending and time.monotonic() < deadline:
        for row in list(pending):
            try:
                path = "/v2/requests/" + row["request_id"]
                status = gateway.request(path + "/status")["status"]
                row["state"] = status
                if status == "FAILED":
                    pending.remove(row)
                elif status == "COMPLETED":
                    result = gateway.request(path)
                    row["media"] = shared.download_video(result, out / (row["id"] + "-raw.mp4"))
                    pending.remove(row)
                    print("Downloaded clip", row["id"], flush=True)
            except Exception as exc:
                row["last_poll_error_type"] = type(exc).__name__
            shared.save_report(out, report)
        if pending:
            time.sleep(5)
    for row in pending:
        row["state"] = "TIMEOUT_RETAIN_REQUEST_ID"
    shared.save_report(out, report)
    count = sum(c["state"] == "COMPLETED" and "media" in c for c in report["clips"])
    print(f"Downloaded {count}/6 clips. No retries submitted.")
    if count != 6:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
