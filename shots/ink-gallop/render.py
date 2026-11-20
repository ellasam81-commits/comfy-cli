"""Prepare a contact-first starter with ComfyUI, then generate one 6-second shot."""
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import requests

NAMES = ("spear",)
if sys.argv[1] == "prepare":
    local = "http://127.0.0.1:8188"
    for _ in range(100):
        try:
            if requests.get(local + "/system_stats", timeout=2).ok:
                break
        except requests.ConnectionError:
            pass
        time.sleep(2)
    graph = {}
    for index, name in enumerate(NAMES):
        node = index * 3 + 1
        graph[str(node)] = {"class_type": "LoadImage", "inputs": {"image": name + ".jpg"}}
        graph[str(node + 1)] = {"class_type": "ImageScale", "inputs": {
            "image": [str(node), 0], "upscale_method": "lanczos", "width": 1024,
            "height": 576, "crop": "disabled"}}
        graph[str(node + 2)] = {"class_type": "SaveImage", "inputs": {
            "images": [str(node + 1), 0], "filename_prefix": name}}
    graph_path = Path("contact-first-starter.json")
    graph_path.write_text(json.dumps(graph))
    subprocess.run(["comfy", "run", "--where", "local", "--host", "127.0.0.1",
                    "--port", "8188", "--workflow", str(graph_path), "--wait"], check=True)
    for name in NAMES:
        frames = list(Path("ComfyUI/output").glob(name + "_*.png"))
        if len(frames) != 1:
            raise RuntimeError("Expected one prepared reference for " + name)
        Path(name + ".png").write_bytes(frames[0].read_bytes())
    sys.exit()

from segmind import SegmindClient


def upload_assets(client, names):
    try:
        return client.files.upload(names)["file_urls"]
    except Exception as error:
        print("Switching asset upload method:", type(error).__name__, flush=True)
        urls = []
        for name in names:
            encoded = base64.b64encode(Path(name).read_bytes()).decode("ascii")
            response = requests.post("https://workflows-api.segmind.com/upload-asset",
                headers={"x-api-key": os.environ["SEGMIND_API_KEY"]},
                json={"data_urls": ["data:image/png;base64," + encoded]}, timeout=100)
            response.raise_for_status()
            urls.append(response.json()["file_urls"][0])
        return urls


def output_urls(value):
    if isinstance(value, str) and value.startswith("https://"):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from output_urls(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from output_urls(item)


prompts = json.loads(Path("shots/ink-gallop/prompts.json").read_text())
output_dir = Path("result")
output_dir.mkdir(exist_ok=True)
client = SegmindClient()
urls = upload_assets(client, [name + ".png" for name in NAMES])
failures = []
for name, url in zip(NAMES, urls):
    payload = {
        "image": url, "prompt": prompts[name], "duration": 6, "resolution": "480P",
        "aspect_ratio": "16:9", "audio": False, "prompt_extend": False,
        "watermark": False,
        "negative_prompt": "rider dismounting, hero on foot, teleportation, spear through horse, duplicated weapons, missed contact, weapons passing through each other, weapons merging, horse colliding with soldier, frozen pose, time reversal, repeated attack cycle, extra limbs, duplicated character, multiple camera cuts, panel grid, captions, text, logo, graphic injury",
    }
    try:
        # A single accepted request per shot. Record before waiting; never resubmit a paid request.
        job = client.submit_async("wan3.0-video", **payload)
        (output_dir / (name + "-request-id.txt")).write_text(job.request_id + "\n")
        print("Accepted", name, str(payload["duration"]) + "-second shot", flush=True)
        result = job.wait(timeout=1500, interval=5)
        for video_url in output_urls(result.get("output", result)):
            response = requests.get(video_url, timeout=100)
            if response.ok and response.content[4:8] == b"ftyp":
                (output_dir / (name + "-wan3.mp4")).write_bytes(response.content)
                print("Saved", name, flush=True)
                break
        else:
            raise RuntimeError("Completed request had no downloadable MP4")
    except Exception as error:
        failures.append(name)
        (output_dir / (name + "-error.txt")).write_text(type(error).__name__ + ": " + str(error))
        print("Shot failed:", name, type(error).__name__, flush=True)
if failures:
    raise RuntimeError("Unfinished shots: " + ", ".join(failures))
