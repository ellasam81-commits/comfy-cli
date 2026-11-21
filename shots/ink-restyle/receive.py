"""Pass an encrypted starter frame to a single live Actions runner."""
import hashlib
import io
import zipfile
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import sys

folder = Path(os.environ["RUNNER_TEMP"])
key_file = folder / "frame-transfer.key"
context = b"xie-ink-gallop-v1"
TRANSFER_CHUNKS = 14
if sys.argv[1] == "open":
    key = X25519PrivateKey.generate()
    key_file.write_bytes(key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()))
    key_file.chmod(0o600)
    public_key = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
        print("public=" + public_key.hex(), file=handle)
    (folder / "receiver.txt").write_text("One-time frame receiver.")
else:
    key = X25519PrivateKey.from_private_bytes(key_file.read_bytes())
    run_id = os.environ["GITHUB_RUN_ID"]
    chunks = []
    for index in range(TRANSFER_CHUNKS):
        url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/contents/render-input/{run_id}-{index}.bin?ref={os.environ['GITHUB_REF_NAME']}"
        for attempt in range(60):
            try:
                request = Request(url, headers={"Accept": "application/vnd.github.raw+json", "Authorization": "Bearer " + os.environ["GITHUB_TOKEN"]})
                with urlopen(request, timeout=20) as response:
                    chunks.append(response.read())
                break
            except HTTPError as exc:
                if exc.code != 404:
                    raise
                time.sleep(10)
        else:
            raise RuntimeError("Timed out waiting for the starter frame")
    envelope = b"".join(chunks)
    shared = key.exchange(X25519PublicKey.from_public_bytes(envelope[:32]))
    aes_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=context).derive(shared)
    frame = AESGCM(aes_key).decrypt(envelope[32:44], envelope[44:], context)
    if hashlib.sha256(frame).hexdigest() != "96f32601d6000d804d667585c8bef4b3a81a4eeddf794331cf8a9e6c28918ac8":
        raise ValueError("Frame did not match this shot")
    with zipfile.ZipFile(io.BytesIO(frame)) as archive:
        for name in ("style.png", "source_video.mp4",):
            (Path("ComfyUI/input") / name).write_bytes(archive.read(name))
    key_file.unlink()
