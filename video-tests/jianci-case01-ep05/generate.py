"""One authorized episode-four repair; eight single-speaker submissions, no retries. References stay transient."""

import base64
import subprocess
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
    assert cfg["episode"] == 5 and cfg["duration_seconds"] == 60 and cfg["shots"] == 12
    assert len(cfg["clips"]) == 12
    assert all(len(c["prompt"]) < 7000 for c in cfg["clips"])
    return cfg


def main():
    cfg = config()
    if os.environ.get("JIANCI_EP05_EXECUTE") != "1":
        print("Validated: Episode 05, 12 x 5 sec, 12 planned shots, estimated USD 3. No API calls.")
        return
    if int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")) != 1:
        raise RuntimeError("No automatic rerun: could duplicate paid submissions.")
    out = Path("output/jianci-episode05")
    out.mkdir(parents=True, exist_ok=True)
    if (out / "report.json").exists():
        raise RuntimeError("Existing report: refusing duplicate generation.")
    sha = os.environ["GITHUB_SHA"]
    repo = os.environ["GITHUB_REPOSITORY"]
    assert re.fullmatch(r"[a-f0-9]{40}", sha)
    assert repo == "ellasam81-commits/comfy-cli"
    refs = {}
    scene_dir = Path(".runtime/episode04")
    for role, name, position, crop in [
        ("jian","04-raw.mp4",3.5,"crop=330:400:90:0"),
        ("lin","04-raw.mp4",3.5,"crop=340:400:380:60"),
        ("qi","03-raw.mp4",6.0,"crop=520:400:200:0"),
    ]:
        original=scene_dir/name
        frame=subprocess.check_output(["ffmpeg","-nostdin","-v","error","-ss",str(position),"-i",str(original),"-frames:v","1","-vf",crop,"-f","image2pipe","-vcodec","mjpeg","-q:v","3","-"])
        dims=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_entries","stream=width,height","-of","json","-i","pipe:0"],input=frame))["streams"][0]
        assert min(dims["width"],dims["height"])>=240
        assert len(frame)<350000
        refs[role]=["data:image/jpeg;base64,"+base64.b64encode(frame).decode("ascii")]
    def inspect_five(path):
        p=json.loads(subprocess.check_output(["ffprobe","-v","error","-show_streams","-show_format","-of","json",str(path)]))
        duration=float(p["format"]["duration"])
        assert 4.8<=duration<=5.3, "Unexpected generated duration"
        v=next(x for x in p["streams"] if x["codec_type"]=="video")
        assert any(x["codec_type"]=="audio" for x in p["streams"]), "No audio track"
        return {"duration":duration,"width":v["width"],"height":v["height"],"audio_track":True,"dialogue_accuracy":"requires QA"}
    shared.inspect_video=inspect_five
    gateway = shared.Gateway(os.environ.get("SEGMIND_API_KEY"))
    gateway.request("/v1/get-user-credits")
    report = {"episode": 5, "model": "wan3.0-video", "estimated_usd": 3, "clips": []}
    shared.save_report(out, report)
    pending = []
    for clip in cfg["clips"]:
        row = {"id": clip["id"], "state": "SUBMITTING"}
        report["clips"].append(row)
        shared.save_report(out, report)
        try:
            result = gateway.request(
                "/v2/wan3.0-video",
                {
                    "prompt": clip["prompt"],
                    "reference_images": refs[clip["role"]],
                    "duration": 5,
                    "resolution": "480P",
                    "aspect_ratio": "16:9",
                    "audio": True,
                    "watermark": False,
                    "prompt_extend": False,
                    "enable_thinking": True,
                    "seed": 908505,
                    "negative_prompt": "live action, 3D, subtitles, text, indoor stairs, railing, teleportation, floating objects, moving wardrobe, gore, extra dialogue, changing faces",
                },
            )
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
    print(f"Downloaded {count}/12 clips. No retries submitted.")
    if count != 12:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
