"""Prepare the starter through ComfyUI and render one Wan 3.0 tracking shot."""
import base64
import json
import os
import sys
import subprocess
import time
from pathlib import Path

import requests

# Opening and final frames are stacked vertically in the private input.
workflow = {"1": {"class_type": "LoadImage", "inputs": {"image": "storyboard.jpg"}}}
for node, prefix, x, y in [(2, "opening", 0, 0), (5, "reveal", 0, 432)]:
    workflow[str(node)] = {
        "class_type": "ImageCrop",
        "inputs": {"image": ["1", 0], "width": 768, "height": 432, "x": x, "y": y},
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
    "Thirty-second widescreen 2D anime wuxia film on xuan paper. Use precise ink linework, warm ivory paper, "
    "black silver beast-head armor, asymmetric silver mask, black ponytail; only accent is a torn red flag. "
    "Opening 0–8s: extreme close-up masked eye reflecting vermilion, flag on the city gate, armored rider "
    "emerging from mist, black-gloved fingers gathering reins, hooves drumming dry ground, wide view of both banks. "
    "8–12s keep one continuous lateral tracking shot, full horse and rider always moving left to right. "
    "Collect at the near bank, push from hind legs, ascend, float at apex, extend front legs and land once "
    "on the far bank. Show a clear gap under all four hooves. Only ONE jump across the stream. "
    "12–20s: close hoof impact throws droplets. Wet black ink sweeps diagonally from actual point of contact, "
    "wipes across the lens, briefly covers the full frame, capillaries spread on paper. An iris of white paper "
    "reveals one unmasked eye, then loose hair and the fold of white robes. "
    "20–30s: before the misty gate, white-robed figure and crimson silk, sleeve detail, lowered chin, eyes "
    "lifting, full unmasked hero portrait, then settle in the final wide chest-up composition, quiet wind. "
    "Ordinary fictional anime face. Restrained offscreen Mandarin storyteller at end says ‘是他，谢却山。’ "
    "The character stays silent. Hoofbeats, hush when airborne, damp hoof strike and paper-brush swish. "
    "No titles or captions."
)
payload = {
    "image": upload_frame("opening"), "last_frame": upload_frame("reveal"), "prompt": prompt,
    "duration": 30, "resolution": "480P", "aspect_ratio": "16:9", "audio": True, "prompt_extend": False,
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
