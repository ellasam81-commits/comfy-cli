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
    for index in range(4):
        url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/contents/render-input/{run_id}-{index}.bin?ref={os.environ['GITHUB_REF_NAME']}"
        for attempt in range(60):
            try:
                request = Request(url, headers={"Accept": "application/vnd.github.raw+json"})
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
    if hashlib.sha256(frame).hexdigest() != "55b2cde458c67d5f91739a5b641bf0c91832b53f45043058ec884c0cbe1c9e1e":
        raise ValueError("Frame did not match this shot")
    with zipfile.ZipFile(io.BytesIO(frame)) as archive:
        (Path("ComfyUI/input") / "storyboard.jpg").write_bytes(archive.read("storyboard.jpg"))
        Path("motion.mp4").write_bytes(archive.read("motion.mp4"))
    key_file.unlink()
