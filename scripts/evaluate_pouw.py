"""
Evaluate PoUW CAPTCHA verification asymmetry and proof soundness.

This script is intentionally local and deterministic. It exercises the current
`mnist-tiny` model without a live API server and writes paper-friendly JSON and
Markdown artifacts.
"""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
sys.path.insert(0, str(SERVER_DIR))

from app.ml.model_store import get_model_store  # noqa: E402
from app.ml.proof_verifier import (  # noqa: E402
    NUM_PROJECTIONS,
    ProofVerifier,
    canonical_vector_hash,
    compute_proof_hash,
)

logging.getLogger("app.ml.proof_verifier").setLevel(logging.ERROR)


def client_compute(model, x, start: int, end: int) -> list[list[float]]:
    """Simulate browser Float32Array layer execution."""
    h = np.asarray(x, dtype=np.float32)
    pre_activations: list[list[float]] = []
    for layer in model.layers[start:end]:
        z = (
            h.astype(np.float64) @ layer.weights.astype(np.float64)
            + layer.biases.astype(np.float64)
        ).astype(np.float32)
        pre_activations.append([float(v) for v in z])
        h = model.apply_activation(z.astype(np.float64), layer.activation).astype(
            np.float32
        )
    return pre_activations


def build_proof(
    model,
    x,
    start: int,
    end: int,
    task_id: str,
    sample_id: str,
    prediction_hash: str = "",
):
    pre = client_compute(model, x, start, end)
    hashes = [canonical_vector_hash(z) for z in pre]
    proof_hash = compute_proof_hash(
        task_id,
        sample_id,
        start,
        len(pre),
        hashes,
        prediction_hash,
    )
    return pre, hashes, proof_hash


def random_input(rng: np.random.Generator, size: int) -> list[float]:
    return rng.uniform(0, 1, size).astype(np.float32).tolist()


def layer_ops(model, start: int, end: int) -> tuple[int, int]:
    compute_ops = 0
    verify_ops = 0
    for layer in model.layers[start:end]:
        compute_ops += layer.input_size * layer.output_size
        verify_ops += NUM_PROJECTIONS * (layer.input_size + layer.output_size)
    return compute_ops, verify_ops


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def run_evaluation(samples: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    model = get_model_store().get_default()
    verifier = ProofVerifier(audit_rate=0.0)
    auditing_verifier = ProofVerifier(audit_rate=1.0)

    full_compute_ops, full_verify_ops = layer_ops(model, 0, model.total_layers)
    segment_ops = [
        {
            "segment": [i, i + 1],
            "compute_ops": layer_ops(model, i, i + 1)[0],
            "projection_verify_ops": layer_ops(model, i, i + 1)[1],
            "asymmetry_ratio": round(
                layer_ops(model, i, i + 1)[0] / layer_ops(model, i, i + 1)[1],
                3,
            ),
        }
        for i in range(model.total_layers)
    ]

    direct_times: list[float] = []
    segmented_verify_times: list[float] = []
    labels_match = 0
    honest_passes = 0
    tamper_rejections = 0
    audit_rejections = 0

    for sample_index in range(samples):
        x = random_input(rng, model.input_size)

        start_time = time.perf_counter()
        direct_probs = model.predict(np.asarray(x, dtype=np.float64))
        direct_times.append((time.perf_counter() - start_time) * 1000)
        direct_label = model.labels[int(np.argmax(direct_probs))]

        activation = x
        final_report = None
        for layer_index in range(model.total_layers):
            pre, hashes, proof_hash = build_proof(
                model,
                activation,
                layer_index,
                layer_index + 1,
                task_id=f"honest-{sample_index}-{layer_index}",
                sample_id=f"sample-{sample_index}",
            )
            start_time = time.perf_counter()
            report = verifier.verify_segment(
                model,
                layer_index,
                activation,
                pre,
                hashes,
                proof_hash,
                f"honest-{sample_index}-{layer_index}",
                f"sample-{sample_index}",
            )
            segmented_verify_times.append((time.perf_counter() - start_time) * 1000)
            if report.valid:
                honest_passes += 1
            activation = [float(v) for v in report.final_activation]
            final_report = report

        if final_report and final_report.predicted_label == direct_label:
            labels_match += 1

        # Fabricated/tampered output should fail projection checks.
        pre, _, _ = build_proof(model, x, 0, 1, "tamper-task", f"sample-{sample_index}")
        pre[0][0] += 0.5
        tampered_hashes = [canonical_vector_hash(pre[0])]
        tampered_proof = compute_proof_hash(
            "tamper-task",
            f"sample-{sample_index}",
            0,
            1,
            tampered_hashes,
            "",
        )
        tamper_report = verifier.verify_segment(
            model,
            0,
            x,
            pre,
            tampered_hashes,
            tampered_proof,
            "tamper-task",
            f"sample-{sample_index}",
        )
        if not tamper_report.valid:
            tamper_rejections += 1

        # Full audit should catch small coherent drift.
        pre, _, _ = build_proof(model, x, 0, 1, "audit-task", f"sample-{sample_index}")
        pre[0] = [v + 0.002 for v in pre[0]]
        audit_hashes = [canonical_vector_hash(pre[0])]
        audit_proof = compute_proof_hash(
            "audit-task",
            f"sample-{sample_index}",
            0,
            1,
            audit_hashes,
            "",
        )
        audit_report = auditing_verifier.verify_segment(
            model,
            0,
            x,
            pre,
            audit_hashes,
            audit_proof,
            "audit-task",
            f"sample-{sample_index}",
        )
        if not audit_report.valid:
            audit_rejections += 1

    total_segments = samples * model.total_layers

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "samples": samples,
        "seed": seed,
        "model": {
            "name": model.name,
            "version": model.version,
            "layers": model.total_layers,
            "labels": model.labels,
            "checksum": model.checksum,
            "metrics": model.metrics,
        },
        "complexity": {
            "full_model_compute_ops": full_compute_ops,
            "full_model_projection_verify_ops": full_verify_ops,
            "full_model_asymmetry_ratio": round(full_compute_ops / full_verify_ops, 3),
            "num_secret_projections": NUM_PROJECTIONS,
            "segments": segment_ops,
        },
        "correctness": {
            "distributed_labels_matched_direct": labels_match,
            "label_match_rate": round(labels_match / samples, 4),
            "honest_segments_verified": honest_passes,
            "honest_segment_accept_rate": round(honest_passes / total_segments, 4),
        },
        "attack_checks": {
            "tamper_trials": samples,
            "tamper_rejections": tamper_rejections,
            "tamper_rejection_rate": round(tamper_rejections / samples, 4),
            "audit_trials": samples,
            "audit_rejections": audit_rejections,
            "audit_rejection_rate": round(audit_rejections / samples, 4),
        },
        "latency_ms": {
            "direct_full_inference_mean": round(statistics.mean(direct_times), 4),
            "direct_full_inference_p95": round(percentile(direct_times, 95), 4),
            "segment_projection_verify_mean": round(
                statistics.mean(segmented_verify_times), 4
            ),
            "segment_projection_verify_p95": round(
                percentile(segmented_verify_times, 95), 4
            ),
        },
    }


def render_markdown(results: dict) -> str:
    complexity = results["complexity"]
    correctness = results["correctness"]
    attacks = results["attack_checks"]
    latency = results["latency_ms"]
    model = results["model"]

    return f"""# PoUW CAPTCHA Evaluation Report

Generated: `{results['generated_at']}`

## Model

- Name: `{model['name']}`
- Version: `{model['version']}`
- Layers: `{model['layers']}`
- Checksum: `{model['checksum']}`
- Samples: `{results['samples']}`
- Seed: `{results['seed']}`

## Verification Asymmetry

| Metric | Value |
| --- | ---: |
| Full model client compute ops | {complexity['full_model_compute_ops']:,} |
| Full model routine projection verify ops | {complexity['full_model_projection_verify_ops']:,} |
| Compute / verify ratio | {complexity['full_model_asymmetry_ratio']}x |
| Secret projections per layer | {complexity['num_secret_projections']} |

## Correctness

| Metric | Value |
| --- | ---: |
| Distributed labels matched direct inference | {correctness['distributed_labels_matched_direct']} / {results['samples']} |
| Label match rate | {correctness['label_match_rate']:.2%} |
| Honest segment accept rate | {correctness['honest_segment_accept_rate']:.2%} |

## Attack Checks

| Check | Rejections |
| --- | ---: |
| Tampered segment outputs | {attacks['tamper_rejections']} / {attacks['tamper_trials']} |
| Audit drift checks | {attacks['audit_rejections']} / {attacks['audit_trials']} |

## Local Latency

| Metric | Milliseconds |
| --- | ---: |
| Direct full inference mean | {latency['direct_full_inference_mean']} |
| Direct full inference p95 | {latency['direct_full_inference_p95']} |
| Segment projection verify mean | {latency['segment_projection_verify_mean']} |
| Segment projection verify p95 | {latency['segment_projection_verify_p95']} |

## Interpretation

The current dense MNIST model is intentionally small. Even so, routine
projection verification is substantially cheaper than recomputing the full
dense model. The asymmetry should improve for larger dense layers because
client computation scales as `O(n * m)` while projection verification scales as
`O(k * (n + m))`.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--json-out",
        default=str(ROOT / "docs" / "evaluation" / "latest.json"),
    )
    parser.add_argument(
        "--md-out",
        default=str(ROOT / "docs" / "evaluation" / "latest.md"),
    )
    args = parser.parse_args()

    results = run_evaluation(samples=args.samples, seed=args.seed)

    json_path = Path(args.json_out)
    md_path = Path(args.md_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)

    json_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(results), encoding="utf-8")

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(
        "Asymmetry:",
        f"{results['complexity']['full_model_asymmetry_ratio']}x",
    )


if __name__ == "__main__":
    main()
