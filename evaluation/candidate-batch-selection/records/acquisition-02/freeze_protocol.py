"""Root runs only after explicit review. Does not select or score."""
import argparse
from common import HERE, load, save, sha, verify_pins, utc


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root-review-reference", required=True)
    args = p.parse_args()
    draft = load(HERE / "protocol-draft.json")
    verify_pins(draft["source_pins"])
    verify_pins(draft["input_pins"])
    protocol = {**draft, "status": "FROZEN_AFTER_ROOT_REVIEW", "draft_sha256": sha(HERE / "protocol-draft.json")}
    save(HERE / "protocol.json", protocol)
    save(HERE / "protocol-receipt.json", {"at": utc(), "protocol_sha256": sha(HERE / "protocol.json"),
         "root_review_reference": args.root_review_reference, "real_selection_started": False, "gold_opened": False})


if __name__ == "__main__":
    main()
