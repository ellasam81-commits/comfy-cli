"""Bounded three-model, two-scene Segmind test; no automatic submission retries."""

import hashlib
import json
import os
import re
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "https://api.segmind.com"
SLUGS = {"seedance-2.0-mini", "wan3.0-video", "minimax-h3-reference-to-video"}


def read_config(path=ROOT / "test.json"):
    cfg = json.loads(path.read_text(encoding="utf-8"))
    models = cfg["models"]
    if len(models) != 3 or {m["slug"] for m in models} != SLUGS:
        raise ValueError("Exactly the three requested models are required.")
    if cfg["episode_seconds"] != 60 or cfg["episode_shots"] != 12:
        raise ValueError("Episode format must be 60 seconds / 12 shots.")
    if cfg["duration_seconds"] != 10 or cfg["scene_cut_seconds"] != 5:
        raise ValueError("This test is limited to two 5-second scenes.")
    if len(cfg["reference_files"]) != 2:
        raise ValueError("Exactly two scene references are required.")
    expected = {
        "seedance-2.0-mini": ("480p", "aspect_ratio"),
        "wan3.0-video": ("480P", "aspect_ratio"),
        "minimax-h3-reference-to-video": ("768P", "ratio"),
    }
    for m in models:
        settings = m["settings"]
        resolution, ratio_field = expected[m["slug"]]
        if settings["duration"] != 10 or settings["resolution"] != resolution:
            raise ValueError("Unexpected duration or resolution; cost estimate no longer applies.")
        if settings[ratio_field] != "16:9":
            raise ValueError("Use the same landscape aspect ratio.")
        if m["slug"] == "seedance-2.0-mini" and settings.get("generate_audio") is not True:
            raise ValueError("Mini audio must be enabled.")
        if m["slug"] == "wan3.0-video" and settings.get("audio") is not True:
            raise ValueError("Wan audio must be enabled.")
    if len(cfg["prompt"]) > 7000:
        raise ValueError("H3 prompt limit exceeded.")
    return cfg


def check_images(cfg, root=ROOT):
    hashes = {}
    for name in cfg["reference_files"]:
        path = (root / name).resolve()
        if path.parent != root.resolve():
            raise ValueError("Reference must be directly inside the test directory.")
        data = path.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            raise ValueError("Reference must be a PNG.")
        width, height = struct.unpack(">II", data[16:24])
        if min(width, height) < 300 or abs(width / height - 16 / 9) > 0.01:
            raise ValueError("References must be landscape 16:9 and at least 300 pixels.")
        hashes[name] = hashlib.sha256(data).hexdigest()
    return hashes


def build_payload(model, cfg, references):
    return dict(model["settings"], prompt=cfg["prompt"], reference_images=list(references))


class NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("Authenticated API redirect refused.")


class Gateway:
    def __init__(self, key):
        if not key:
            raise RuntimeError("Missing repository Actions secret SEGMIND_API_KEY.")
        self.key = key
        self.opener = urllib.request.build_opener(NoAuthRedirect)

    def request(self, path, payload=None):
        if not path.startswith(("/v1/", "/v2/")):
            raise ValueError("Invalid Segmind API path.")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            API + path,
            data=body,
            headers={"x-api-key": self.key, "Content-Type": "application/json"},
            method="GET" if body is None else "POST",
        )
        try:
            with self.opener.open(req, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 422 and payload is None and path.endswith("/status"):
                return {"status": "FAILED"}
            raise RuntimeError(f"Segmind HTTP {exc.code}; no automatic resubmission.") from None
        except (urllib.error.URLError, TimeoutError):
            raise RuntimeError("Segmind network timeout/error; submission state may be unknown.") from None


def output_urls(value):
    found = []
    if isinstance(value, str) and value.startswith("https://"):
        found.append(value)
    elif isinstance(value, list):
        for child in value:
            found.extend(output_urls(child))
    elif isinstance(value, dict):
        for key in ("output", "video", "video_url", "url", "output_url", "data"):
            if key in value:
                found.extend(output_urls(value[key]))
    return list(dict.fromkeys(found))


def inspect_video(path):
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(proc.stdout)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    duration = float(info.get("format", {}).get("duration", 0))
    if video is None or not 9.5 <= duration <= 10.5:
        raise ValueError("Output is not a roughly 10-second video.")
    audio = any(s["codec_type"] == "audio" for s in info["streams"])
    audible = False
    if audio:
        analysis = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(path), "-vn", "-af", "volumedetect", "-f", "null", "-"],
            capture_output=True,
            text=True,
            check=True,
        )
        match = re.search(r"max_volume: (-?[\d.]+) dB", analysis.stderr)
        audible = bool(match and float(match.group(1)) > -60)
    return {
        "duration": duration,
        "width": video["width"],
        "height": video["height"],
        "audio_track": audio,
        "audible_signal": audible,
        "dialogue_accuracy": "requires_listening",
        "identity_and_transition": "requires_visual_review",
    }


def download_video(result, path):
    urls = output_urls(result.get("output", result))
    for url in urls:
        try:
            # Output media downloads never receive the Segmind API credential.
            with urllib.request.urlopen(url, timeout=180) as response:
                content = response.read(100 * 1024 * 1024 + 1)
            if len(content) > 100 * 1024 * 1024:
                continue
            path.write_bytes(content)
            return inspect_video(path)
        except (OSError, ValueError, subprocess.SubprocessError):
            path.unlink(missing_ok=True)
    raise RuntimeError("No valid 10-second video could be downloaded from the model output.")


def save_report(out, report):
    temporary = out / "report.tmp"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(out / "report.json")


def normalize_preview(raw, preview):
    # Retain the native audio, without replacing a missing voice with synthesized speech.
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(raw),
            "-vf",
            "scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-crf",
            "19",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(preview),
        ],
        check=True,
    )


def execute(cfg, references, hashes, out):
    out.mkdir(parents=True, exist_ok=True)
    if (out / "report.json").exists():
        raise RuntimeError("Existing run report found; refusing an automatic duplicate submission.")
    if int(os.environ.get("GITHUB_RUN_ATTEMPT", "1")) != 1:
        raise RuntimeError("Rerunning this job could duplicate charges; start a reviewed new test instead.")
    gateway = Gateway(os.environ.get("SEGMIND_API_KEY"))
    # Read-only authentication check. No model is invoked here.
    gateway.request("/v1/get-user-credits")
    report = {
        "test_id": cfg["test_id"],
        "estimated_total_usd": round(sum(m["estimated_usd"] for m in cfg["models"]), 3),
        "reference_sha256": hashes,
        "actual_billing": "check Segmind request history",
        "models": [],
    }
    pending = []
    save_report(out, report)
    for model in cfg["models"]:
        row = {"label": model["label"], "model": model["slug"], "state": "SUBMITTING"}
        report["models"].append(row)
        save_report(out, report)
        started = time.monotonic()
        try:
            result = gateway.request("/v2/" + model["slug"], build_payload(model, cfg, references))
            request_id = result["request_id"]
            if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", request_id):
                raise ValueError("Unexpected request ID.")
            row.update(state="QUEUED", request_id=request_id)
            pending.append((row, started))
        except (RuntimeError, KeyError, ValueError):
            row["state"] = "SUBMISSION_UNKNOWN_OR_FAILED"
            # Stop new submissions after an ambiguous POST; still retrieve accepted jobs.
            save_report(out, report)
            break
        save_report(out, report)
    deadline = time.monotonic() + 1500
    while pending and time.monotonic() < deadline:
        for row, started in list(pending):
            path = "/v2/requests/" + row["request_id"]
            try:
                status = gateway.request(path + "/status")["status"]
                if status == "FAILED":
                    row["state"] = "FAILED"
                    pending.remove((row, started))
                elif status == "COMPLETED":
                    result = gateway.request(path)
                    raw = out / (row["label"] + "-raw.mp4")
                    info = download_video(result, raw)
                    row.update(state="COMPLETED", media=info, elapsed_seconds=round(time.monotonic() - started, 1))
                    normalize_preview(raw, out / (row["label"] + "-preview.mp4"))
                    pending.remove((row, started))
                else:
                    row["state"] = status
            except (RuntimeError, KeyError, ValueError, subprocess.SubprocessError):
                row["last_poll_or_download_error"] = True
            save_report(out, report)
        if pending:
            time.sleep(5)
    for row, _ in pending:
        row["state"] = "TIMEOUT_RETAIN_REQUEST_ID"
    save_report(out, report)
    completed = [r for r in report["models"] if r["state"] == "COMPLETED"]
    print(f"Saved {len(completed)}/3 model outputs; visual and dialogue review still required.")
    all_audible = all(r["media"]["audible_signal"] for r in completed)
    return 0 if len(completed) == 3 and all_audible else 2


def main():
    cfg = read_config()
    hashes = check_images(cfg)
    repo = os.environ.get("GITHUB_REPOSITORY", "ellasam81-commits/comfy-cli")
    sha = os.environ.get("GITHUB_SHA", "0" * 40)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo) or not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Invalid GitHub repository or revision.")
    base = f"https://raw.githubusercontent.com/{repo}/{sha}/video-tests/jianci-transition/"
    references = [base + urllib.parse.quote(name) for name in cfg["reference_files"]]
    if os.environ.get("SEGMIND_TEST_EXECUTE") != "1":
        print("DRY RUN: 3 x 10 seconds; 2 x 5-second scenes each; estimated US$1.977.")
        print("Configuration and both reference files validated. No API calls were made.")
        return 0
    return execute(cfg, references, hashes, Path("output/jianci-transition"))


if __name__ == "__main__":
    raise SystemExit(main())
