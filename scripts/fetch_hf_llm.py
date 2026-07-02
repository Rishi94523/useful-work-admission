"""
Fetch a small open-source LLM from Hugging Face for the distributed-inference
PoC and store it under models/hf/<local_name>/ (gitignored — raw weights are
large and are not committed).

These are deliberately small, plain Llama-style transformers (RMSNorm, RoPE,
GQA attention, SwiGLU MLP) so they map cleanly onto the affine-operator +
server-replayed-post-op verification the pipeline already supports. Nothing
here wires them into the pipeline — that conversion/quantization step is done
separately (scripts/import_hf_llm.py, TODO). This only downloads and lays out
the raw checkpoint plus a small provenance record.

Usage:
    python scripts/fetch_hf_llm.py                 # default: qwen2.5-0.5b-instruct
    python scripts/fetch_hf_llm.py --model smollm2-360m-instruct
    python scripts/fetch_hf_llm.py --all
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import snapshot_download

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fetch_hf_llm")

ROOT = Path(__file__).resolve().parents[1]
HF_DIR = ROOT / "models" / "hf"

# Only pull what an inference/conversion pipeline needs: safetensors weights,
# config, and tokenizer. Skip .bin duplicates, ONNX, and demo assets.
ALLOW_PATTERNS = [
    "*.safetensors",
    "*.json",
    "*.txt",
    "tokenizer.model",
]
IGNORE_PATTERNS = [
    "*.bin",
    "*.onnx",
    "*.msgpack",
    "*.h5",
    "onnx/*",
    "original/*",
    "*.gguf",
]

MODELS = {
    "qwen2.5-0.5b-instruct": {
        "repo_id": "Qwen/Qwen2.5-0.5B-Instruct",
        "arch": "Qwen2 (Llama-style: RMSNorm, RoPE, GQA, SwiGLU)",
        "params": "0.5B",
        "note": "primary PoC target; instruct-tuned for prompt-based labeling",
    },
    "smollm2-360m-instruct": {
        "repo_id": "HuggingFaceTB/SmolLM2-360M-Instruct",
        "arch": "Llama (RMSNorm, RoPE, GQA, SwiGLU)",
        "params": "360M",
        "note": "smallest option; fastest per-block browser execution",
    },
}


def fetch(local_name: str) -> Path:
    spec = MODELS[local_name]
    target = HF_DIR / local_name
    target.mkdir(parents=True, exist_ok=True)

    logger.info("Downloading %s -> %s", spec["repo_id"], target)
    snapshot_download(
        repo_id=spec["repo_id"],
        local_dir=str(target),
        allow_patterns=ALLOW_PATTERNS,
        ignore_patterns=IGNORE_PATTERNS,
    )

    # Record provenance next to the weights for the wiring step to read.
    files = sorted(p.name for p in target.iterdir() if p.is_file())
    total_bytes = sum(p.stat().st_size for p in target.rglob("*") if p.is_file())
    provenance = {
        "local_name": local_name,
        "repo_id": spec["repo_id"],
        "arch": spec["arch"],
        "params": spec["params"],
        "note": spec["note"],
        "files": files,
        "total_mb": round(total_bytes / 1e6, 1),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    (target / "PROVENANCE.json").write_text(json.dumps(provenance, indent=2))
    logger.info("Saved %s (%.1f MB, %d files)", local_name, provenance["total_mb"], len(files))
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch a small HF LLM for the PoC")
    parser.add_argument("--model", default="qwen2.5-0.5b-instruct", choices=list(MODELS))
    parser.add_argument("--all", action="store_true", help="fetch every known model")
    args = parser.parse_args()

    names = list(MODELS) if args.all else [args.model]
    for name in names:
        fetch(name)

    logger.info("Done. Models under %s", HF_DIR)


if __name__ == "__main__":
    main()
