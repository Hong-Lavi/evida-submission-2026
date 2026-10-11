import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASE = HERE.parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open("x") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def utc():
    return datetime.now(timezone.utc).isoformat()


def verify_pins(pins):
    for path, expected in pins.items():
        if sha(path) != expected:
            raise ValueError("Pinned file changed: " + path)


def frozen_protocol():
    path = HERE / "protocol.json"
    receipt = load(HERE / "protocol-receipt.json")
    if receipt["protocol_sha256"] != sha(path) or not receipt["root_review_reference"]:
        raise ValueError("Protocol lacks reviewed freeze")
    protocol = load(path)
    verify_pins(protocol["source_pins"])
    verify_pins(protocol["input_pins"])
    return protocol
