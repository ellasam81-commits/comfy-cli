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
for node, prefix, x, y in [(2, "rider", 0, 0), (5, "shield", 0, 432)]:
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
    for prefix in ("rider", "shield"):
        frames = list(Path("ComfyUI/output").glob(prefix + "_*.png"))
        if len(frames) != 1:
            raise RuntimeError("Missing ComfyUI output for " + prefix)
        Path(prefix + ".png").write_bytes(frames[0].read_bytes())
    sys.exit()

from segmind import SegmindClient

def upload_assets(client, names):
    try:
        return client.files.upload(names)["file_urls"]
    except Exception as error:
        print("Switching asset upload method:", type(error).__name__, flush=True)
        urls = []
        for name in names:
            mime = "video/mp4" if name.endswith(".mp4") else "image/png"
            encoded = base64.b64encode(Path(name).read_bytes()).decode("ascii")
            uploaded = requests.post(
                "https://workflows-api.segmind.com/upload-asset",
                headers={"x-api-key": os.environ["SEGMIND_API_KEY"]},
                json={"data_urls": [f"data:{mime};base64,{encoded}"]}, timeout=100,
            )
            uploaded.raise_for_status()
            urls.append(uploaded.json()["file_urls"][0])
        return urls

prompt = (
    "A SIX SECOND single wuxia anime fight shot on the rain-wet causeway at moonrise. Match the masked rider, black horse, helmeted foot guard and ROUND STEEL SHIELD in the two reference stills. "
    "Use the supplied video ONLY for the fluid body weight, lateral tracking, and speed of a mounted swing. In this film the focal object is the raised shield and the sword light skimming its circumference. "
    "0–1.4s: dynamic three-quarter side angle at the shield's height; mounted Xie rides in from left, leans into the blow. Stocky guard on the right raises the large circular shield, rim visible to camera. "
    "1.4–3.1s: silver sword makes a single sharp grazing contact at the upper outside rim. THE SHIELD JOLTS AND TURNS AT THAT SAME INSTANT, forearm bends, cloak snaps, guard slides one foot back in the wet stone spray. "
    "Keep the actual sword, wrist and shield visible together. Follow the bright pinpoint of contact: a THIN LIVELY SILVER STROKE travels clockwise along the actual turned metal edge in close perspective, hugs the near half of the elliptical rim, briefly vanishes BEHIND its far edge, catches light on the lower edge and breaks away. "
    "This is specular light written by the passing blade around the shield; it is always the size of that shield. One incomplete sweep, with a short frayed black ink tail rising into the air only when the sword departs. "
    "3.1–6s: the rider's sword and shoulder finish the stroke; guard regains his footing as the shield dips, rider and black horse carry through toward screen right, falling droplets and light fade. One readable counterpressure and release. "
    "Polished hand-drawn donghua action timing, crisp silver-on-indigo, lyrical moon mist, distinct red scarf. Silent picture. No extra characters, graphics or lettering."
)
client = SegmindClient()
names = ["rider.png", "shield.png", "motion.mp4"]
urls = upload_assets(client, names)
payload = {
    "reference_images": urls[:2], "reference_videos": [urls[2]], "prompt": prompt,
    "duration": 6, "resolution": "480P", "aspect_ratio": "16:9", "audio": False,
    "prompt_extend": False, "watermark": False,
    "negative_prompt": "giant circle in front of both actors, separate glowing hoop, floating halo, energy shield bubble, looping rings, five swipes, delayed reaction, distant crowd, green robe, chestnut horse, duplication, frozen tableau, contact sheet, subtitles, graphic injury",
}
output_dir = Path("result")
output_dir.mkdir(exist_ok=True)
job = client.submit_async("wan3.0-video", **payload)
(output_dir / "request-id.txt").write_text(job.request_id + "\n")
print("Segmind accepted the 6-second shield strike. Waiting for the video.", flush=True)
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
    if not response.ok:
        continue
    if response.content[4:8] == b"ftyp":
        (output_dir / "Xie_Queshan_Silver_Shield_Wan3.mp4").write_bytes(response.content)
        break
else:
    raise RuntimeError("The completed request returned no MP4")
