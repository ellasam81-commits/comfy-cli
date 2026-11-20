"""Prepare the starter through ComfyUI and render one Wan 3.0 tracking shot."""
import base64
import json
import os
import sys
import subprocess
import time
from pathlib import Path

import requests

# Both 608 × 342 crops sit inside the panel gutters. The opening crop
# keeps the horse's grounded forehoof; the final crop keeps the hero's eyes.
workflow = {"1": {"class_type": "LoadImage", "inputs": {"image": "storyboard.jpg"}}}
for node, prefix, x, y in [(2, "opening", 9, 52), (5, "reveal", 630, 849)]:
    workflow[str(node)] = {
        "class_type": "ImageCrop",
        "inputs": {"image": ["1", 0], "width": 608, "height": 342, "x": x, "y": y},
    }
    workflow[str(node + 1)] = {
        "class_type": "ImageScale",
        "inputs": {"image": [str(node), 0], "upscale_method": "lanczos", "width": 1024, "height": 576, "crop": "disabled"},
    }
    workflow[str(node + 2)] = {
        "class_type": "SaveImage", "inputs": {"images": [str(node + 1), 0], "filename_prefix": prefix},
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
    graph_path = Path("ink-starter-workflow.json")
    graph_path.write_text(json.dumps(workflow))
    subprocess.run(
        ["comfy", "run", "--where", "local", "--host", "127.0.0.1", "--port", "8188",
         "--workflow", str(graph_path), "--wait"],
        check=True,
    )
    for prefix in ("opening", "reveal"):
        frames = list(Path("ComfyUI/output").glob(prefix + "_*.png"))
        if len(frames) != 1:
            raise RuntimeError("Missing ComfyUI output for " + prefix)
        Path(prefix + ".png").write_bytes(frames[0].read_bytes())
    sys.exit()

from segmind import SegmindClient

def upload_frame(prefix):
    encoded = base64.b64encode(Path(prefix + ".png").read_bytes()).decode("ascii")
    uploaded = requests.post(
        "https://workflows-api.segmind.com/upload-asset",
        headers={"x-api-key": os.environ["SEGMIND_API_KEY"]},
        json={"data_urls": ["data:image/png;base64," + encoded]},
        timeout=90,
    )
    uploaded.raise_for_status()
    return uploaded.json()["file_urls"][0]

prompt = (
    "Single uninterrupted side tracking shot, exquisite cel-drawn wuxia on warm xuan paper. "
    "Same masked young general and one black horse moving left to right. Preserve silver armor, red flag and ink mountains. "
    "0–0.65s approach the near riverbank at a gallop; 0.65–1.15s hindquarters push off once, "
    "rider folds over neck with soft reins. 1.15–1.9s a single clear flight arc over the brook with all four hooves airborne. "
    "1.9–2.35s extend forelegs and land forefeet first on the far bank, then the hind feet, audible wet hoof thud. "
    "At contact a dense stroke of black ink sweeps diagonally right up across the lens. Bristles and droplets on paper. "
    "2.35–2.95s the black ink opens onto one unmasked eye, ivory collar, and a restrained cinnabar flag. "
    "2.95–4s hold the same general unmasked, now in white robes, loose black hair lifting, calmly looking up. "
    "End on the supplied white-robed frame. Keep eyes and nose clearly drawn in anime style. "
    "Sound: hoofbeats, hush while airborne, brush swish, then a low offscreen Mandarin narrator says exactly "
    "‘是他，谢却山。’ as his unmasked face appears. His mouth stays still."
)
payload = {
    "image": upload_frame("opening"), "last_frame": upload_frame("reveal"), "prompt": prompt,
    "duration": 4, "resolution": "480P", "aspect_ratio": "16:9", "audio": True, "prompt_extend": False,
    "watermark": False, "negative_prompt": "extra jumps, second horse, wrong screen direction, missing feet, slideshow, panels, captions, speaking rider, photorealistic celebrity",
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
