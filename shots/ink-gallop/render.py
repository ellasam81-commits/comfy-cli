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
    "30s cinematic Chinese ink-wash anime, 16:9. Warm rice paper, charcoal, moon silver, and vermilion silk. "
    "Fictional ordinary donghua face, black beast-head armor, asymmetric silver half mask, black ponytail and horse. "
    "Give every transition a motivated visual transformation. Keep the moon, the red flag and the hero's eye as recurring anchors. "
    "0–8s: a red flag reflected in his masked pupil swells to a real silk flag. Hem lifts to expose the closing gate; "
    "two civilians slip inside as he stays out. Mist divides in the shape of the gate and reveals the black rider. "
    "First clash with an opposing rider: the metallic contact opens a hairline silver crescent in the fog; briefly see "
    "both riders through the crescent, it lengthens into the glint on the hero's mask. Second rider crosses foreground, "
    "cape covers lens momentarily, torn flag tip separates into two swallow-shaped red scraps, one unfurls back to a ribbon. "
    "Follow its curve into the bent rushes to reveal both banks of the river. Riders separate visibly after each clash. "
    "8–12.5s: uninterrupted side track, complete horse and all hooves visible, screen direction always right, one jump only. "
    "Rushes bow to expose the bank, silver rim travels over hind hoof as it pushes, flying grit falls away from rising hooves, "
    "a thin mane strand trails on the edge of frame. At apex ribbon and red reflection briefly align like two wings under horse, "
    "no wing attaches to horse. Wind rush drops to hush. On descent reflection and real forehoof approach. Forehoof lands on "
    "far bank's wet edge before the hind hooves. Only the reflected white moon fractures, the actual moon remains whole. "
    "12.5–20.5s: wet hoof thud. Water beads magnify tiny upside-down flags, then reflected crescent fragments dissolve to ink; "
    "ink wave swings from lower right to upper left across the lens. Vermilion silk bleeds into the ink as a cinnabar vein, "
    "black pigment feathers into paper fibers. A dry-brush slit opens on the same eye as the first frame, now unmasked. "
    "The taper of the brush becomes a strand of hair, flying whites of the stroke become folds of an ivory robe. "
    "20.5–30s: from white robe to a long shot at the city gate, pale paper margins become gate mist. Red ribbon brushes past "
    "his shoulder, its edge aligns with his sleeve seam. A lifted lock of hair reveals his eye; close-up on both eyes, then widen "
    "to the white-robed portrait. The tiny flag reflected in his eye aligns with the real distant flag in the final frame. "
    "Hold the final two seconds on his calm face, a breath of wind in loose hair. Unobtrusive mist, no cuts during leap, "
    "no text or graphic overlays. Mandarin offscreen witness: early '他让我们先走。' After landing '一蹄踏碎半河月。' "
    "At the reveal '墨尽，方知是故人。' As he lifts his eyes, after a half beat '是他，谢却山。' His lips stay closed. "
    "Sound design: silver chime, torn silk, wind suspended midair, wet hoof impact, brush dragging over paper, hush."
)
payload = {
    "image": upload_frame("opening"), "last_frame": upload_frame("reveal"), "prompt": prompt,
    "duration": 30, "resolution": "480P", "aspect_ratio": "16:9", "audio": True, "prompt_extend": False,
    "watermark": False, "negative_prompt": "extra jumps, cloned protagonist, cloned foreground horse, wrong screen direction, missing feet, slideshow, panels, captions, speaking rider, photorealistic celebrity",
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
