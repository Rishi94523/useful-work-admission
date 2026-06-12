"""
Evaluate PoUW CAPTCHA verification asymmetry and proof soundness.

This script is intentionally local and deterministic. It exercises EVERY model
in the plug-and-play store (dense MLP, CNN, …) without a live API server and
writes paper-friendly JSON and Markdown artifacts.

Per model it measures:
  - compute/verify op asymmetry per layer and overall (layer-type-generic)
  - distributed (segment-by-segment, verified) labels vs direct inference
  - end-to-end labeling accuracy against MNIST ground truth (real test images)
  - tamper and audit-drift rejection rates
  - wall-clock verification latency
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import statistics
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
sys.path.insert(0, str(SERVER_DIR))

from app.ml.model_store import apply_post_ops, get_model_store  # noqa: E402
from app.ml.proof_verifier import (  # noqa: E402
    NUM_PROJECTIONS,
    ProofVerifier,
    canonical_vector_hash,
    compute_proof_hash,
)

logging.getLogger("app.ml.proof_verifier").setLevel(logging.ERROR)


def client_compute(model, x, start: int, end: int) -> list[list[float]]:
    """Simulate browser Float32Array layer execution (any layer type)."""
    h = np.asarray(x, dtype=np.float32)
    pre_activations: list[list[float]] = []
    for layer in model.layers[start:end]:
        z = layer.forward(h.astype(np.float64)).astype(np.float32)
        pre_activations.append([float(v) for v in z])
        h = apply_post_ops(z.astype(np.float64), layer.post_ops).astype(np.float32)
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


def load_mnist_inputs(samples: int) -> tuple[list[list[float]], list[str]] | None:
    """Real MNIST test images + ground-truth labels, if downloaded."""
    images_path = ROOT / "data" / "mnist" / "t10k-images-idx3-ubyte.gz"
    labels_path = ROOT / "data" / "mnist" / "t10k-labels-idx1-ubyte.gz"
    if not images_path.exists() or not labels_path.exists():
        return None
    with gzip.open(images_path, "rb") as f:
        magic, count, rows, cols = struct.unpack(">IIII", f.read(16))
        data = np.frombuffer(f.read(samples * rows * cols), dtype=np.uint8)
    images = (data.reshape(samples, rows * cols).astype(np.float32) / 255.0).tolist()
    with gzip.open(labels_path, "rb") as f:
        f.read(8)
        labels = [str(v) for v in np.frombuffer(f.read(samples), dtype=np.uint8)]
    return images, labels


def layer_ops(model, start: int, end: int) -> tuple[int, int]:
    compute_ops = 0
    verify_ops = 0
    for layer in model.layers[start:end]:
        compute_ops += layer.compute_ops
        verify_ops += NUM_PROJECTIONS * layer.projection_ops
    return compute_ops, verify_ops


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def evaluate_model(model, inputs, ground_truth, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    verifier = ProofVerifier(audit_rate=0.0)
    auditing_verifier = ProofVerifier(audit_rate=1.0)
    samples = len(inputs)

    full_compute_ops, full_verify_ops = layer_ops(model, 0, model.total_layers)
    segment_ops = []
    for i in range(model.total_layers):
        compute, verify = layer_ops(model, i, i + 1)
        segment_ops.append(
            {
                "segment": [i, i + 1],
                "layer_type": model.layers[i].layer_type,
                "compute_ops": compute,
                "projection_verify_ops": verify,
                "asymmetry_ratio": round(compute / verify, 3),
            }
        )

    direct_times: list[float] = []
    segmented_verify_times: list[float] = []
    labels_match = 0
    ground_truth_match = 0
    honest_passes = 0
    tamper_rejections = 0
    audit_rejections = 0

    for sample_index, x in enumerate(inputs):
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
        if (
            final_report
            and ground_truth is not None
            and final_report.predicted_label == ground_truth[sample_index]
        ):
            ground_truth_match += 1

        # Fabricated/tampered output should fail projection checks.
        tamper_layer = int(rng.integers(0, model.total_layers))
        tamper_input = (
            x
            if tamper_layer == 0
            else [
                float(v)
                for v in model.forward_segment(
                    np.asarray(x, dtype=np.float64), 0, tamper_layer
                )[1]
            ]
        )
        pre, _, _ = build_proof(
            model, tamper_input, tamper_layer, tamper_layer + 1,
            "tamper-task", f"sample-{sample_index}",
        )
        pre[0][int(rng.integers(0, len(pre[0])))] += 0.5
        tampered_hashes = [canonical_vector_hash(pre[0])]
        tampered_proof = compute_proof_hash(
            "tamper-task", f"sample-{sample_index}", tamper_layer, 1, tampered_hashes, ""
        )
        tamper_report = verifier.verify_segment(
            model, tamper_layer, tamper_input, pre, tampered_hashes,
            tampered_proof, "tamper-task", f"sample-{sample_index}",
        )
        if not tamper_report.valid:
            tamper_rejections += 1

        # Full audit should catch small coherent drift.
        pre, _, _ = build_proof(model, x, 0, 1, "audit-task", f"sample-{sample_index}")
        pre[0] = [v + 0.002 for v in pre[0]]
        audit_hashes = [canonical_vector_hash(pre[0])]
        audit_proof = compute_proof_hash(
            "audit-task", f"sample-{sample_index}", 0, 1, audit_hashes, ""
        )
        audit_report = auditing_verifier.verify_segment(
            model, 0, x, pre, audit_hashes, audit_proof,
            "audit-task", f"sample-{sample_index}",
        )
        if not audit_report.valid:
            audit_rejections += 1

    total_segments = samples * model.total_layers

    result = {
        "model": {
            "name": model.name,
            "version": model.version,
            "layers": model.total_layers,
            "layer_types": [layer.layer_type for layer in model.layers],
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
    if ground_truth is not None:
        result["correctness"]["distributed_labels_matched_ground_truth"] = (
            ground_truth_match
        )
        result["correctness"]["ground_truth_accuracy"] = round(
            ground_truth_match / samples, 4
        )
    return result


def run_evaluation(samples: int, seed: int) -> dict:
    mnist = load_mnist_inputs(samples)
    if mnist is not None:
        inputs, ground_truth = mnist
        input_source = "mnist_test_set"
    else:
        rng = np.random.default_rng(seed)
        inputs = [
            rng.uniform(0, 1, 784).astype(np.float32).tolist() for _ in range(samples)
        ]
        ground_truth = None
        input_source = "uniform_random"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "samples": samples,
        "seed": seed,
        "input_source": input_source,
        "models": [
            evaluate_model(model, inputs, ground_truth, seed)
            for model in get_model_store().list_models()
        ],
    }


def render_markdown(results: dict) -> str:
    lines = [
        "# PoUW CAPTCHA Evaluation Report",
        "",
        f"Generated: `{results['generated_at']}`",
        f"Samples: `{results['samples']}` ({results['input_source']}), "
        f"seed `{results['seed']}`",
        "",
        "## Model Comparison",
        "",
        "| Model | Layers | Test acc | Compute ops | Verify ops | Asymmetry | "
        "Distributed = direct | Ground-truth acc | Tamper rejected |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for entry in results["models"]:
        model = entry["model"]
        complexity = entry["complexity"]
        correctness = entry["correctness"]
        attacks = entry["attack_checks"]
        gt = correctness.get("ground_truth_accuracy")
        lines.append(
            f"| `{model['name']}` "
            f"| {model['layers']} ({'+'.join(dict.fromkeys(model['layer_types']))}) "
            f"| {model['metrics'].get('test_accuracy', '—')} "
            f"| {complexity['full_model_compute_ops']:,} "
            f"| {complexity['full_model_projection_verify_ops']:,} "
            f"| {complexity['full_model_asymmetry_ratio']}x "
            f"| {correctness['label_match_rate']:.2%} "
            + (f"| {gt:.2%} " if gt is not None else "| — ")
            + f"| {attacks['tamper_rejection_rate']:.2%} |"
        )

    for entry in results["models"]:
        model = entry["model"]
        complexity = entry["complexity"]
        correctness = entry["correctness"]
        attacks = entry["attack_checks"]
        latency = entry["latency_ms"]
        lines += [
            "",
            f"## {model['name']} v{model['version']}",
            "",
            f"- Checksum: `{model['checksum']}`",
            f"- Layer types: {', '.join(model['layer_types'])}",
            "",
            "### Per-segment asymmetry",
            "",
            "| Segment | Type | Client compute ops | Projection verify ops | Ratio |",
            "| --- | --- | ---: | ---: | ---: |",
        ]
        for seg in complexity["segments"]:
            lines.append(
                f"| {seg['segment']} | {seg['layer_type']} "
                f"| {seg['compute_ops']:,} | {seg['projection_verify_ops']:,} "
                f"| {seg['asymmetry_ratio']}x |"
            )
        lines += [
            "",
            "### Correctness and attacks",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Distributed labels matched direct inference "
            f"| {correctness['distributed_labels_matched_direct']} / {results['samples']} |",
            f"| Honest segment accept rate "
            f"| {correctness['honest_segment_accept_rate']:.2%} |",
        ]
        if "ground_truth_accuracy" in correctness:
            lines.append(
                f"| Distributed labeling accuracy vs MNIST ground truth "
                f"| {correctness['ground_truth_accuracy']:.2%} |"
            )
        lines += [
            f"| Tampered segment outputs rejected "
            f"| {attacks['tamper_rejections']} / {attacks['tamper_trials']} |",
            f"| Audit drift rejected "
            f"| {attacks['audit_rejections']} / {attacks['audit_trials']} |",
            f"| Segment projection verify mean / p95 (ms) "
            f"| {latency['segment_projection_verify_mean']} / "
            f"{latency['segment_projection_verify_p95']} |",
            f"| Direct full inference mean (ms) "
            f"| {latency['direct_full_inference_mean']} |",
        ]

    lines += [
        "",
        "## Interpretation",
        "",
        "Routine verification cost is `O(k·(in + out))` per layer regardless of",
        "layer type, while client compute is `O(in × out)` for dense layers and",
        "`O(out × k² × in_ch)` for convolutions. The asymmetry therefore grows",
        "with layer width (dense) and with kernel size × channel count (conv).",
        "Small input convolutions (1→8 channels) are the worst case for the",
        "verifier — their outputs are large relative to the work performed — ",
        "while production-scale conv layers (32→64 channels and up) exceed 40x.",
        "The same projection identity `r·z = (Lᵀr)·x + r·b` covers any affine",
        "operator, so attention projections and other matmul-shaped layers",
        "verify identically.",
        "",
    ]
    return "\n".join(lines)


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
    for entry in results["models"]:
        print(
            f"{entry['model']['name']}: "
            f"asymmetry {entry['complexity']['full_model_asymmetry_ratio']}x, "
            f"distributed=direct {entry['correctness']['label_match_rate']:.2%}, "
            + (
                f"ground truth {entry['correctness']['ground_truth_accuracy']:.2%}, "
                if "ground_truth_accuracy" in entry["correctness"]
                else ""
            )
            + f"tamper rejected {entry['attack_checks']['tamper_rejection_rate']:.2%}"
        )


if __name__ == "__main__":
    main()
