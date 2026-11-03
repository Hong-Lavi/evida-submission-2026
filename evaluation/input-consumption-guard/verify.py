"""Offline identity and observed-property checks for the F1 replay package."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_text())


def observed(rows):
    return [{k: row[k] for k in ("family", "status", "expected_publish", "actual_publish", "checks")}
            for row in rows]


def check_comparison(attempt, recorded):
    result = read(attempt / "comparison.json")
    equality = read(attempt / "input-equivalence.json")
    require(equality["status"] == "PASS" and equality["families"] == 5, "Input-equivalence check missing")
    for arm in ("current", "improved"):
        value = result["arms"][arm]
        require(value["denominator"] == 5 and len(value["rows"]) == 5, "A scenario is missing")
        require(value["passed"] == sum(r["status"] == "PASS" for r in value["rows"]), "Incorrect pass count")
        require(observed(value["rows"]) == observed(recorded["arms"][arm]["rows"]),
                "Observed properties differ from the recorded native comparison: " + arm)
        for relative, expected in value.get("native_modules_loaded", {}).items():
            require(sha(ROOT / "native" / arm / relative) == expected, "Loaded module identity differs")
    require(result["model_calls"] == result["network_calls"] == 0, "Unexpected external calls")
    return {arm: {key: result["arms"][arm][key] for key in ("passed", "denominator")}
            for arm in ("current", "improved")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, help="Also compare a completed fresh local replay")
    args = parser.parse_args()
    manifest = read(ROOT / "package-manifest.json")
    for name, expected in manifest["files"].items():
        path = ROOT / name
        require(path.resolve().is_relative_to(ROOT), "Nonlocal package path")
        require(path.is_file() and not path.is_symlink(), "Missing or linked file: " + name)
        require(path.stat().st_size == expected["bytes"] and sha(path) == expected["sha256"], "Changed package bytes: " + name)
    source_map = read(ROOT / "source-map.json")
    for entry in source_map["files"]:
        path = ROOT / entry["public_file"]
        require(sha(path) == entry["public_sha256"], "Changed source/observation identity")
        if entry["transformation"].startswith("unchanged"):
            require(entry["original_sha256"] == entry["public_sha256"], "An unchanged file has different hashes")
        if "unchanged_method_ast_sha256" in entry:
            cls = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.ClassDef))
            for node in cls.body:
                require(hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()
                        == entry["unchanged_method_ast_sha256"][node.name], "Changed native method body")
        if "full_ast_sha256" in entry:
            require(hashlib.sha256(ast.dump(ast.parse(path.read_text()), include_attributes=False).encode()).hexdigest()
                    == entry["full_ast_sha256"], "Changed executable AST in comment-only adaptation")
    recorded = read(ROOT / "recorded-run/comparison.json")
    original = check_comparison(ROOT / "recorded-run", recorded)
    portable = check_comparison(ROOT / "portable-check", recorded)
    extra = check_comparison(args.comparison.resolve(), recorded) if args.comparison else None
    result = {"status": "PASS", "package_files": len(manifest["files"]),
              "recorded_native_run": original, "portable_reproduction": portable,
              "fresh_local_reproduction": extra, "scope": "five deterministic software event families",
              "model_calls": 0, "network_calls": 0, "gpu_used": False}
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
