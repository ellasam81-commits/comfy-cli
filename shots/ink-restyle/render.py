"""Restyle the uploaded video once while retaining original motion and audio."""
import base64
import json
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import time

import requests

IDENTITIES = ("style",)
if sys.argv[1] == "prepare":
    for _ in range(100):
        try:
            if requests.get("http://127.0.0.1:8188/system_stats", timeout=2).ok:
                break
        except requests.ConnectionError:
            pass
        time.sleep(2)
    graph = {}
    for index, name in enumerate(IDENTITIES):
        load, save = str(index * 2 + 1), str(index * 2 + 2)
        graph[load] = {"class_type": "LoadImage", "inputs": {"image": name + ".png"}}
        graph[save] = {"class_type": "SaveImage", "inputs": {
            "images": [load, 0], "filename_prefix": name}}
    workflow = Path("exact-original-identities.json")
    workflow.write_text(json.dumps(graph))
    subprocess.run(["comfy", "run", "--where", "local", "--host", "127.0.0.1",
                    "--port", "8188", "--workflow", str(workflow), "--wait"], check=True)
    for name in IDENTITIES:
        files = list(Path("ComfyUI/output").glob(name + "_*.png"))
        if len(files) != 1:
            raise RuntimeError("Expected exactly one original identity output")
        Path(name + ".png").write_bytes(files[0].read_bytes())
    Path("source_video.mp4").write_bytes(Path("ComfyUI/input/source_video.mp4").read_bytes())
    sys.exit()

from segmind import SegmindClient


def upload_assets(client, paths):
    try:
        urls = client.files.upload(paths)["file_urls"]
    except Exception as error:
        print("Switching media upload method:", type(error).__name__, flush=True)
        urls = []
        for filename in paths:
            mime = mimetypes.guess_type(filename)[0]
            if mime not in ("image/png", "video/mp4"):
                raise ValueError("Unexpected reference media type")
            encoded = base64.b64encode(Path(filename).read_bytes()).decode("ascii")
            response = requests.post("https://workflows-api.segmind.com/upload-asset",
                headers={"x-api-key": os.environ["SEGMIND_API_KEY"]},
                json={"data_urls": ["data:" + mime + ";base64," + encoded]}, timeout=180)
            response.raise_for_status()
            urls.append(response.json()["file_urls"][0])
    if len(urls) != len(paths) or not all(url.startswith("https://") for url in urls):
        raise RuntimeError("Expected one HTTPS media URL per asset")
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


prompt = json.loads(Path("shots/ink-restyle/prompts.json").read_text())["edit"]
assert isinstance(prompt, str) and prompt.strip()
client = SegmindClient()
urls = upload_assets(client, ["style.png", "source_video.mp4"])
payload = {
    "video": urls[1], "images": [urls[0]], "prompt": prompt,
    "draft": False, "prompt_upsampling": False, "save_audio": True,
}
output = Path("result")
output.mkdir(exist_ok=True)
receipt = output / "inkstyle-request-id.txt"
if receipt.exists():
    raise RuntimeError("A request is already recorded; never resubmit")
try:
    job = client.submit_async("p-video-edit", **payload)
    receipt.write_text(job.request_id + "\n")
    print("Accepted one full-quality original-video ink restyle", flush=True)
    result = job.wait(timeout=1800, interval=5)
    for url in output_urls(result.get("output", result)):
        response = requests.get(url, timeout=180)
        if response.ok and response.content[4:8] == b"ftyp":
            (output / "inkstyle-pvideo.mp4").write_bytes(response.content)
            print("Saved original-video ink restyle", flush=True)
            break
    else:
        raise RuntimeError("Completed request has no downloadable MP4")
except Exception as error:
    (output / "inkstyle-error.txt").write_text(type(error).__name__ + ": " + str(error))
    raise


