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
    "Thirty seconds of cinematic widescreen original 2D donghua. Sharp grey cel shadows, wet charcoal ink mountains, ragged brushstrokes, cool silver moonlight, one trace of vermilion silk. Match the supplied eye and final portrait. ONE fictional man Xie Queshan in the entire film. In the first act he wears black beast-head lamellar armor, an asymmetrical black-silver mask, high black ponytail, on one black horse. Even in the clash the unseen opponent is represented solely by a blade and a plain iron gauntlet entering from outside the frame. No visible opponent face or body. "
    "0–8s: start close on the red flag reflected in Xie's masked eye; open to the same red flag above the river gate. Silk lifts to uncover a pale gap in the clouds; the single black rider bursts out of the gap. Blades meet in tight POV, a pinpoint of silver releases a long dry-brush crescent that follows the blade's physical swing; cut on its direction to the knight riding free. His horse's mane draws a stroke toward the reeds, revealing the river and both banks. "
    "8–13s is a single smoothly animated uninterrupted side track. Never reset or jump again. Reeds bend on last stride. Hind hooves compress and extend, spitting grit; grit falls as forelegs tuck. Black mane and one narrow red ribbon stream backward; highlight at the apex slides off the ribbon onto the moon reflected below. The forelegs reach, one front hoof lands on the far bank's wet edge; as weight comes down, the reflection breaks. Keep camera rightward, one human, one proportional horse, no duplicate limbs or bodies, no cut to a second angle in the air. "
    "13–20.5s: landing throws water out in a crown, concentric lines split the silver moon reflection, not the real moon. Push into an individual bead. The moving black mane enters its outline; pigment spirals into the river. A brush stroke wipes the lens completely opaque black for a beat. No face or human is visible at the change of clothes. A narrow dry-brush seam gradually uncovers his same eye, now with loose dark hair, then a white collar and shoulder. White is seen on the hero only, after the full ink wipe. "
    "20.5–30s: cool gate mist opens onto the full figure at the gate. Close on the fingers brushing wet stone, little reflected flag wavers in the water. Damp hair grazes his brow, he looks down. He raises his eyes to the viewer; spare final hold with wind moving a few strands of hair. No lip movement. No titles. A low, unhurried Mandarin witness narrates at 1s ‘他让我们先走。’, at 13s ‘一蹄踏碎半河月。’, at 20s ‘墨尽，方知是故人。’, and at 27s ‘是他，谢却山。’ Sound: paired metal ring, breath of wind over water during the jump, one wet impact, fading paper-brush hiss. Accent every transition with the motivated motion of light, cloth, hooves, water, ink, or mist. Animators' continuous body motion, never a slide show. "
)
payload = {
    "image": upload_frame("opening"), "last_frame": upload_frame("reveal"), "prompt": prompt,
    "duration": 30, "resolution": "480P", "aspect_ratio": "16:9", "audio": True, "prompt_extend": False,
    "watermark": False, "negative_prompt": "second visible actor, visible white-robed enemy, clone, double exposure, double figure, parallel horse, second jump, broken anatomy, wrong screen direction, jump cuts during leap, slideshow, animated panel borders, captions, speaking rider, live action, celebrity likeness",
}
output_dir = Path("result")
output_dir.mkdir(exist_ok=True)
client = SegmindClient()
job = client.submit_async("wan3.0-video", **payload)
(output_dir / "request-id.txt").write_text(job.request_id + "\n")
print("Segmind accepted the 30-second shot. Waiting for the video.", flush=True)
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
        (output_dir / "Xie_Queshan_Ink_Gallop_Wan3.mp4").write_bytes(response.content)
        break
else:
    raise RuntimeError("The completed request returned no MP4")
