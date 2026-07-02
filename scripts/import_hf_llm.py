"""
Convert a raw Hugging Face LLM checkpoint (fetched by fetch_hf_llm.py) into
the plug-and-play distributed-inference format under models/llm-<name>/.

Decomposition: each decoder block becomes two provable pipeline layers
(gqa_attention + swiglu_mlp, see app/ml/llm_layers.py); the final layer is a
candidate-logits head for zero-shot classification (labeling PoC — a single
forward pass, no autoregressive generation). RMSNorm weights travel as
input-ops; RoPE parameters live on the attention layers.

Weights are per-channel weight-only int8 (~lossless; both sides dequantize
identically). The tied embedding matrix is exported as a memory-mapped f16
.npy for server-side token embedding; the tokenizer.json is copied alongside.

Output dirs are gitignored (models/llm-*/) — rerun this script to recreate.

Usage:
    python scripts/import_hf_llm.py --model qwen2.5-0.5b-instruct
    python scripts/import_hf_llm.py --model smollm2-360m-instruct --seq 48
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import ml_dtypes  # noqa: F401 — registers the bfloat16 numpy dtype
import numpy as np
from safetensors import safe_open

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from app.ml.llm_layers import (  # noqa: E402
    CandidateLogitsLayer,
    GQAAttentionLayer,
    SwigluMlpLayer,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("import_hf_llm")

DEFAULT_LABELS = ["negative", "positive"]
DEFAULT_TEMPLATE = "Text: {text}\nThe sentiment of this text is"
DEFAULT_CANDIDATES = [" negative", " positive"]


def quantize_rows(w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-output-channel symmetric int8: scale[o] = max|W[o,:]| / 127."""
    scales = np.maximum(np.max(np.abs(w), axis=1), 1e-12) / 127.0
    w_q = np.clip(np.round(w / scales[:, None]), -127, 127).astype(np.int8)
    return w_q, scales.astype(np.float32)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import an HF LLM for the pipeline")
    parser.add_argument("--model", default="qwen2.5-0.5b-instruct")
    parser.add_argument("--seq", type=int, default=32)
    parser.add_argument("--labels", default=",".join(DEFAULT_LABELS))
    parser.add_argument("--candidates", default=",".join(DEFAULT_CANDIDATES))
    parser.add_argument("--template", default=DEFAULT_TEMPLATE)
    args = parser.parse_args()

    src = ROOT / "models" / "hf" / args.model
    config = json.loads((src / "config.json").read_text())
    seq = args.seq
    d = config["hidden_size"]
    ffn = config["intermediate_size"]
    n_layers = config["num_hidden_layers"]
    n_heads = config["num_attention_heads"]
    n_kv = config["num_key_value_heads"]
    head_dim = d // n_heads
    eps = config["rms_norm_eps"]
    theta = float(config["rope_theta"])

    short = args.model.split("-")[0].split(".")[0]  # qwen2 / smollm2
    out_name = f"llm-{short}-sentiment"
    out_dir = ROOT / "models" / out_name
    out_dir.mkdir(parents=True, exist_ok=True)

    labels = args.labels.split(",")
    candidates = args.candidates.split(",")
    assert len(labels) == len(candidates)

    logger.info(
        "Importing %s: %d blocks, d=%d, ffn=%d, heads %d/%d, seq=%d",
        args.model, n_layers, d, ffn, n_heads, n_kv, seq,
    )

    f = safe_open(src / "model.safetensors", "numpy")

    def tensor(key: str) -> np.ndarray:
        return f.get_tensor(key).astype(np.float32)

    def maybe_bias(key: str, size: int) -> np.ndarray:
        try:
            return tensor(key)
        except Exception:
            return np.zeros(size, dtype=np.float32)

    # --- tokenizer + candidate token rows --------------------------------
    shutil.copy(src / "tokenizer.json", out_dir / "tokenizer.json")
    from tokenizers import Tokenizer

    tok = Tokenizer.from_file(str(out_dir / "tokenizer.json"))
    candidate_ids = []
    for cand in candidates:
        ids = tok.encode(cand, add_special_tokens=False).ids
        candidate_ids.append(ids[0])
        logger.info("label %r -> candidate token %r (id %d, %d-token phrase)",
                    labels[len(candidate_ids) - 1], cand, ids[0], len(ids))

    # --- embeddings (mmap-able f16) --------------------------------------
    embed = tensor("model.embed_tokens.weight")  # (vocab, d)
    np.save(out_dir / "embed.npy", embed.astype(np.float16))
    candidate_rows = embed[candidate_ids].astype(np.float32)  # (n_labels, d)

    # --- blocks -----------------------------------------------------------
    weights_out: dict = {}
    layer_objs = []
    layer_entries = []
    index = 0
    for b in range(n_layers):
        prefix = f"model.layers.{b}."

        # attention unit
        wq, sq = quantize_rows(tensor(prefix + "self_attn.q_proj.weight"))
        wk, sk = quantize_rows(tensor(prefix + "self_attn.k_proj.weight"))
        wv, sv = quantize_rows(tensor(prefix + "self_attn.v_proj.weight"))
        wo, so = quantize_rows(tensor(prefix + "self_attn.o_proj.weight"))
        bq = maybe_bias(prefix + "self_attn.q_proj.bias", n_heads * head_dim)
        bk = maybe_bias(prefix + "self_attn.k_proj.bias", n_kv * head_dim)
        bv = maybe_bias(prefix + "self_attn.v_proj.bias", n_kv * head_dim)
        norm_in = tensor(prefix + "input_layernorm.weight")

        attn_input_ops = [
            {"op": "rmsnorm", "weight": norm_in.tolist(), "eps": eps, "seq": seq}
        ]
        attn = GQAAttentionLayer(
            index=index, name=f"block{b}_attn", seq=seq, d_model=d,
            n_heads=n_heads, n_kv_heads=n_kv, head_dim=head_dim, rope_theta=theta,
            wq=wq, sq=sq, wk=wk, sk=sk, wv=wv, sv=sv, wo=wo, so=so,
            bq=bq, bk=bk, bv=bv, checksum="",
            input_ops=attn_input_ops, post_ops=[{"op": "residual_input"}],
        )
        attn.checksum = attn.compute_checksum()
        weights_out.update({
            f"W{index}q": wq, f"S{index}q": sq, f"W{index}k": wk, f"S{index}k": sk,
            f"W{index}v": wv, f"S{index}v": sv, f"W{index}o": wo, f"S{index}o": so,
            f"b{index}q": bq, f"b{index}k": bk, f"b{index}v": bv,
        })
        layer_entries.append({
            "index": index, "name": attn.name, "type": "gqa_attention",
            "seq": seq, "d_model": d, "n_heads": n_heads, "n_kv_heads": n_kv,
            "head_dim": head_dim, "rope_theta": theta,
            "input_ops": attn_input_ops, "post_ops": attn.post_ops,
            "checksum": attn.checksum,
        })
        layer_objs.append(attn)
        index += 1

        # MLP unit
        wg, sg = quantize_rows(tensor(prefix + "mlp.gate_proj.weight"))
        wu, su = quantize_rows(tensor(prefix + "mlp.up_proj.weight"))
        wd, sd = quantize_rows(tensor(prefix + "mlp.down_proj.weight"))
        norm_post = tensor(prefix + "post_attention_layernorm.weight")

        mlp_input_ops = [
            {"op": "rmsnorm", "weight": norm_post.tolist(), "eps": eps, "seq": seq}
        ]
        mlp = SwigluMlpLayer(
            index=index, name=f"block{b}_mlp", seq=seq, d_model=d, ffn_dim=ffn,
            wg=wg, sg=sg, wu=wu, su=su, wd=wd, sd=sd, checksum="",
            input_ops=mlp_input_ops, post_ops=[{"op": "residual_input"}],
        )
        mlp.checksum = mlp.compute_checksum()
        weights_out.update({
            f"W{index}g": wg, f"S{index}g": sg, f"W{index}u": wu, f"S{index}u": su,
            f"W{index}d": wd, f"S{index}d": sd,
        })
        layer_entries.append({
            "index": index, "name": mlp.name, "type": "swiglu_mlp",
            "seq": seq, "d_model": d, "ffn_dim": ffn,
            "input_ops": mlp_input_ops, "post_ops": mlp.post_ops,
            "checksum": mlp.checksum,
        })
        layer_objs.append(mlp)
        index += 1

    # --- candidate-logits head --------------------------------------------
    final_norm = tensor("model.norm.weight")
    head_input_ops = [
        {"op": "last_token", "seq": seq, "dim": d},
        {"op": "rmsnorm", "weight": final_norm.tolist(), "eps": eps, "seq": 1},
    ]
    head = CandidateLogitsLayer(
        index=index, name="candidate_logits", seq=seq, d_model=d,
        weights=candidate_rows, checksum="",
        input_ops=head_input_ops, post_ops=[{"op": "softmax"}],
    )
    head.checksum = head.compute_checksum()
    weights_out[f"W{index}"] = candidate_rows
    layer_entries.append({
        "index": index, "name": head.name, "type": "candidate_logits",
        "seq": seq, "d_model": d,
        "input_ops": head_input_ops, "post_ops": head.post_ops,
        "checksum": head.checksum,
    })
    layer_objs.append(head)

    # --- export ------------------------------------------------------------
    weights_path = out_dir / "weights.npz"
    np.savez(weights_path, **weights_out)

    layer_checksums = [obj.checksum for obj in layer_objs]
    model_checksum = hashlib.sha256("".join(layer_checksums).encode("ascii")).hexdigest()

    manifest = {
        "name": out_name,
        "version": "1.0.0",
        "task_type": "text_classification",
        "labels": labels,
        "input": {
            "shape": [seq, d],
            "kind": "text",
            "preprocessing": f"prompt template + tokenize, left-pad/truncate to seq={seq}, embed server-side",
            "tokenizer_file": "tokenizer.json",
            "prompt_template": args.template,
            "embedding_file": "embed.npy",
        },
        "pipeline": {"auto_serve": False},
        "weights_file": "weights.npz",
        "checksum": model_checksum,
        "layers": layer_entries,
        "metrics": {},
        "source": {
            "hf_repo": json.loads((src / "PROVENANCE.json").read_text())["repo_id"],
            "quantization": "weight-only int8 per-channel (f32 scales)",
            "candidates": dict(zip(labels, candidates)),
            "candidate_token_ids": candidate_ids,
        },
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "weights_file_sha256": hashlib.sha256(weights_path.read_bytes()).hexdigest(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    total_mb = sum(p.stat().st_size for p in out_dir.iterdir()) / 1e6
    logger.info("Exported %s: %d provable layers, %.0f MB, checksum %s…",
                out_name, len(layer_objs), total_mb, model_checksum[:12])


if __name__ == "__main__":
    main()
