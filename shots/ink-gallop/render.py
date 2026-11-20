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
for node, prefix, x, y in [(2, "arrival", 0, 0), (5, "parry", 0, 432), (8, "buckler", 0, 864), (11, "crescent", 0, 1296)]:
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
    for prefix in ("arrival", "parry", "buckler", "crescent"):
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
    "Create a 12-second animated action sequence in TWO scenes, a 6-second spear exchange followed by a 6-second shield exchange. "
    "Interpret the reference video as a compact ordered combat storyboard. Expand the actions into fluent new animated footage, with weight, footwork, galloping strides and clear bodily reactions. "
    "Original hand-drawn Chinese wuxia anime. Cool moonlit stone causeway, silver river, dark gate, realistic wet reflections in watercolor. Single lead: slim masked black-armored rider Xie, black horse, red hair ribbon. His opponents are helmeted foot soldiers with red scarves. "
    "FIRST SCENE 0-6 sec: start wide in profile, black rider at left, spear guard at right. The horse gallops toward the guard, muscle and leg motion clearly visible. "
    "The guard rushes forward and brings his long pole across the rider's path; Xie leans down, intercepts it. Close dynamic angle at the instant the shafts visibly cross with a pinpoint of amber sparks. "
    "Follow through: the rider turns, redirects the pole and rides past. The guard stumbles back, a thin silver-rimmed ink brush continues the direction of the sword. "
    "At precisely six seconds, the guard's red scarf whips across the lens and cuts into the NEXT distinct encounter. "
    "SECOND SCENE 6-12 sec: low angle. A DIFFERENT helmeted foot guard in the rider's path braces a large circular steel shield; keep the shield big and legible. Xie approaches from screen left. "
    "His shoulders rotate, his sword draws a low sweeping arc; blade visibly strikes the round shield, we see point of contact, then the guard's elbow gives and the shield tilts. "
    "The sword's follow-through paints a huge ragged black crescent with a shining silver edge over both bodies. Shield spins free, hits the wet stone, guard steps back and black horse runs out to screen right. "
    "Snappy cadence, brief held contact followed immediately by explosive release. Exactly one masked general. Full movie frame, ordinary anime faces. Natural synced foley: hooves, metal ringing, dull shield strike, hissing ink. No speech, singing or music."
)
client = SegmindClient()
names = ["arrival.png", "parry.png", "buckler.png", "crescent.png", "motion.mp4"]
urls = upload_assets(client, names)
payload = {
    "reference_images": urls[:-1], "reference_videos": [urls[-1]], "prompt": prompt,
    "duration": 12, "resolution": "480P", "aspect_ratio": "16:9", "audio": False,
    "prompt_extend": False, "watermark": False,
    "negative_prompt": "contact sheet, frozen slideshow, repeated still frames, panel grid, dissolve between poses, clone rider, second black horse, broken weapons, glued blades, graphic injury, subtitles, logo, text, dialogue, music, white robe",
}
output_dir = Path("result")
output_dir.mkdir(exist_ok=True)
job = client.submit_async("wan3.0-video", **payload)
(output_dir / "request-id.txt").write_text(job.request_id + "\n")
print("Segmind accepted the 12-second two-scene sequence. Waiting for the video.", flush=True)
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
        (output_dir / "Xie_Queshan_Two_Fights_Wan3.mp4").write_bytes(response.content)
        break
else:
    raise RuntimeError("The completed request returned no MP4")
