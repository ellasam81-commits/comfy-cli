"""Prepare the starter through ComfyUI and render one Wan 3.0 tracking shot."""
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests

workflow = {
    "1": {"class_type": "LoadImage", "inputs": {"image": "ink-gallop.jpg"}},
    "2": {
        "class_type": "ImageScale",
        "inputs": {"image": ["1", 0], "upscale_method": "lanczos", "width": 1280, "height": 720, "crop": "center"},
    },
    "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": "wan-starter"}},
}

if sys.argv[1] == "prepare":
    local = "http://127.0.0.1:8188"
    for _ in range(100):
        try:
            if requests.get(local + "/system_stats", timeout=2).ok:
                break
        except requests.ConnectionError:
            pass
        time.sleep(2)
    submitted = requests.post(local + "/prompt", json={"prompt": workflow}, timeout=20)
    submitted.raise_for_status()
    prompt_id = submitted.json()["prompt_id"]
    for _ in range(90):
        history = requests.get(local + "/history/" + prompt_id, timeout=4).json()
        if prompt_id in history:
            finished = history[prompt_id]
            if finished["status"]["status_str"] != "success":
                raise RuntimeError("ComfyUI image preparation failed")
            image = finished["outputs"]["3"]["images"][0]
            source = Path("ComfyUI/output") / image["subfolder"] / image["filename"]
            Path("starter.png").write_bytes(source.read_bytes())
            break
        time.sleep(1)
    else:
        raise TimeoutError("ComfyUI did not return its prepared frame")
    sys.exit()

from segmind import SegmindClient

frame = base64.b64encode(Path("starter.png").read_bytes()).decode("ascii")
uploaded = requests.post(
    "https://workflows-api.segmind.com/upload-asset",
    headers={"x-api-key": os.environ["SEGMIND_API_KEY"], "accept": "application/json, text/plain, */*"},
    json={"data_urls": ["data:image/png;base64," + frame]},
    timeout=90,
)
uploaded.raise_for_status()
first_frame = uploaded.json()["file_urls"][0]
prompt = (
    "One fluid uninterrupted lateral tracking shot, already moving at frame one. "
    "Animate the black horse galloping to screen right with repeated coordinated four-beat strides; "
    "show hindquarter push-off, suspension, extended foreleg landing and natural weight transfer. "
    "Keep the hooves readable. The lean masked general rides low; his hips and shoulders absorb each landing. "
    "Keep his eyes forward and the silver asymmetrical mask, armor and reins consistent. "
    "Ponytail, cloak and mane stream left and ripple at their ends. Camera tracks smoothly alongside: "
    "rider stays near center, foreground flag sweeps quickly left once, pale distant ink mountains drift slowly. "
    "Small ink spatters release backward only at hoof impact. Preserve the original 2D brush-and-ink look, "
    "paper whites, charcoal blacks and the small dark red flag. Audio: synchronized galloping hooves, "
    "soft tack and wind. No speech or music."
)
payload = {
    "image": first_frame, "prompt": prompt, "duration": 4, "resolution": "480P",
    "aspect_ratio": "16:9", "audio": True, "prompt_extend": False, "watermark": False,
    "negative_prompt": "static horse, sliding feet, floating horse, duplicate legs, drifting mask, new rider, camera cuts, captions, photorealism",
}
output_dir = Path("result")
output_dir.mkdir(exist_ok=True)
client = SegmindClient()
job = client.submit_async("wan3.0-video", **payload)
(output_dir / "request-id.txt").write_text(job.request_id + "\n")
print("Segmind accepted the shot.", flush=True)
result = job.wait(timeout=1500, interval=5)
def output_urls(value):
    if isinstance(value, str) and value.startswith("https://"):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from output_urls(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from output_urls(item)
for url in output_urls(result.get("output", result)):
    response = requests.get(url, timeout=100)
    response.raise_for_status()
    if response.content[4:8] == b"ftyp":
        (output_dir / "Xie_Queshan_Ink_Gallop_Wan3.mp4").write_bytes(response.content)
        break
else:
    raise RuntimeError("The completed request returned no MP4")
