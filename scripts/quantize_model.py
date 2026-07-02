"""
Post-training quantization: float model -> exact-integer int8 model.

Takes a trained float model from the store and produces a `<name>-q8` variant
whose ENTIRE forward pass is integer arithmetic:

    z_int = x_q · W_q + b_q            (int8 weights, int32 bias, exact)
    a_q   = min(255, (relu(z_int)·mult) >> shift)   (integer requantize)

Every intermediate value stays below 2^53, so browsers (whose numbers are
IEEE float64) reproduce the computation bit-for-bit — no float drift, no
verification tolerance. The proof verifier checks quantized layers with
Freivalds over Z_p (p = 2^31-1): soundness error 1/p per secret projection
and zero need for spot audits.

Usage:
    python scripts/quantize_model.py --model mnist-tiny
    python scripts/quantize_model.py --model mnist-cnn
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.ml.model_store import (  # noqa: E402
    Conv2DLayer,
    DenseLayer,
    QuantizedConv2DLayer,
    QuantizedDenseLayer,
)
from app.ml.model_store import ModelStore  # noqa: E402
from train_mnist_numpy import download_mnist, load_idx_images, load_idx_labels  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("quantize_model")

CALIBRATION_SAMPLES = 2000
ACT_MAX = 255  # activations requantized into [0, 255]


def choose_requant(m_real: float, z_max: int) -> tuple[int, int]:
    """
    Integer multiplier/shift with mult/2^shift ≈ m_real, mult in [2^14, 2^15)
    for precision, and (z_max*mult + half) safely below 2^52.
    """
    shift = int(np.ceil(np.log2(2**14 / m_real)))
    mult = int(round(m_real * 2**shift))
    if mult >= 2**15:
        shift -= 1
        mult = int(round(m_real * 2**shift))
    assert 0 < mult < 2**15, f"mult {mult} out of range"
    assert z_max * mult + 2 ** (shift - 1) < 2**52, "requantize overflow risk"
    return mult, shift


def requant_int(z: np.ndarray, mult: int, shift: int, max_val: int = ACT_MAX) -> np.ndarray:
    return np.minimum((z * mult + 2 ** (shift - 1)) >> shift, max_val)


def batch_forward_layer(layer, x: np.ndarray) -> np.ndarray:
    """Batched exact integer pre-activation for a quantized layer spec dict."""
    w = layer["weights"].astype(np.int64)
    b = layer["biases"].astype(np.int64)
    if layer["type"] == "dense":
        return x @ w + b
    # conv2d
    c, height, width = layer["input_shape"]
    oc, _, kh, kw = w.shape
    oh, ow = height - kh + 1, width - kw + 1
    x4 = x.reshape(len(x), c, height, width)
    z = np.zeros((len(x), oc, oh, ow), dtype=np.int64)
    for u in range(kh):
        for v in range(kw):
            z += np.einsum(
                "oi,niyx->noyx", w[:, :, u, v], x4[:, :, u : u + oh, v : v + ow]
            )
    z += b[None, :, None, None]
    return z.reshape(len(x), -1)


def apply_int_post_ops(z: np.ndarray, post_ops: list[dict]) -> np.ndarray:
    """Batched integer post-ops (relu/maxpool/flatten/requantize)."""
    h = z
    for op in post_ops:
        kind = op["op"]
        if kind == "relu":
            h = np.maximum(h, 0)
        elif kind == "maxpool2d":
            c, height, width = op["shape"]
            pool = int(op.get("pool", 2))
            oh, ow = height // pool, width // pool
            t = h.reshape(len(h), c, height, width)[:, :, : oh * pool, : ow * pool]
            t = t.reshape(len(h), c, oh, pool, ow, pool)
            h = t.max(axis=(3, 5)).reshape(len(h), -1)
        elif kind == "flatten":
            h = h.reshape(len(h), -1)
        elif kind == "requantize":
            h = requant_int(h, int(op["mult"]), int(op["shift"]), int(op.get("max", ACT_MAX)))
        elif kind in ("dequantize", "softmax"):
            pass  # final layer: label decided by integer argmax
        else:
            raise ValueError(f"unsupported post-op in quantized pipeline: {kind}")
    return h


def quantize(model, calib_x: np.ndarray):
    """
    Progressively quantize each layer, calibrating activation ranges on the
    quantized pipeline itself (so requant scales see real integer stats).
    """
    q_layers = []
    x_scale = 1.0 / 255.0
    acts = np.round(calib_x * 255.0).astype(np.int64)  # x_q for layer 0

    for i, layer in enumerate(model.layers):
        is_final = i == model.total_layers - 1
        w = layer.weights.astype(np.float64)
        b = layer.biases.astype(np.float64)

        w_scale = float(np.max(np.abs(w))) / 127.0
        w_q = np.clip(np.round(w / w_scale), -127, 127).astype(np.int8)
        b_q = np.round(b / (w_scale * x_scale)).astype(np.int64)
        assert np.all(np.abs(b_q) < 2**24), "bias exceeds float32-exact range"

        entry = {
            "type": layer.layer_type,
            "weights": w_q,
            "biases": b_q.astype(np.int32),
            "w_scale": w_scale,
            "x_scale": x_scale,
        }
        if layer.layer_type == "conv2d":
            entry["input_shape"] = tuple(layer.input_shape)
            entry["kernel"] = tuple(layer.kernel)
            entry["out_channels"] = layer.out_channels
            entry["in_channels"] = layer.in_channels

        z_int = batch_forward_layer(entry, acts)
        logit_scale = w_scale * x_scale

        # Non-requantize structural post-ops copied from the float layer
        post_ops = [
            dict(op) for op in layer.post_ops if op["op"] in ("relu", "maxpool2d", "flatten")
        ]

        if is_final:
            post_ops.append({"op": "dequantize", "scale": logit_scale})
            post_ops.append({"op": "softmax"})
            entry["post_ops"] = post_ops
            q_layers.append(entry)
            break

        structural = apply_int_post_ops(z_int, post_ops)
        a_max = int(np.percentile(structural, 99.99))
        a_max = max(a_max, 1)
        m_real = ACT_MAX / a_max
        mult, shift = choose_requant(m_real, int(structural.max()))
        post_ops.append({"op": "requantize", "mult": mult, "shift": shift, "max": ACT_MAX})
        entry["post_ops"] = post_ops
        q_layers.append(entry)

        acts = apply_int_post_ops(z_int, post_ops)
        # true activation value per integer unit after requant
        x_scale = logit_scale * (2**shift) / mult

    return q_layers


def evaluate_quantized(q_layers, x: np.ndarray, y: np.ndarray, batch: int = 1000) -> float:
    correct = 0
    for start in range(0, len(x), batch):
        acts = np.round(x[start : start + batch] * 255.0).astype(np.int64)
        for i, layer in enumerate(q_layers):
            z = batch_forward_layer(layer, acts)
            acts = apply_int_post_ops(z, layer["post_ops"])
        correct += int((acts.argmax(axis=1) == y[start : start + batch]).sum())
    return correct / len(x)


def export(model, q_layers, output_dir: Path, q_accuracy: float) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    weights = {}
    layer_objs = []
    for i, entry in enumerate(q_layers):
        weights[f"W{i}"] = entry["weights"]
        weights[f"b{i}"] = entry["biases"]
        if entry["type"] == "dense":
            obj = QuantizedDenseLayer(
                index=i,
                name=model.layers[i].name,
                activation=model.layers[i].activation,
                input_size=entry["weights"].shape[0],
                output_size=entry["weights"].shape[1],
                weights=entry["weights"],
                biases=entry["biases"],
                checksum="",
                w_scale=entry["w_scale"],
                x_scale=entry["x_scale"],
                post_ops=entry["post_ops"],
            )
        else:
            obj = QuantizedConv2DLayer(
                index=i,
                name=model.layers[i].name,
                activation=model.layers[i].activation,
                in_channels=entry["in_channels"],
                out_channels=entry["out_channels"],
                kernel=entry["kernel"],
                input_shape=entry["input_shape"],
                weights=entry["weights"],
                biases=entry["biases"],
                checksum="",
                w_scale=entry["w_scale"],
                x_scale=entry["x_scale"],
                post_ops=entry["post_ops"],
            )
        obj.checksum = obj.compute_checksum()
        layer_objs.append(obj)

    weights_path = output_dir / "weights.npz"
    np.savez(weights_path, **weights)

    layer_checksums = [obj.checksum for obj in layer_objs]
    model_checksum = hashlib.sha256("".join(layer_checksums).encode("ascii")).hexdigest()

    layer_entries = []
    for i, (entry, obj) in enumerate(zip(q_layers, layer_objs)):
        manifest_entry = {
            "index": i,
            "name": obj.name,
            "type": entry["type"],
            "quantized": True,
            "activation": obj.activation,
            "post_ops": entry["post_ops"],
            "w_scale": entry["w_scale"],
            "x_scale": entry["x_scale"],
            "checksum": obj.checksum,
        }
        if entry["type"] == "dense":
            manifest_entry["input_size"] = obj.input_size
            manifest_entry["output_size"] = obj.output_size
        else:
            manifest_entry.update(
                in_channels=entry["in_channels"],
                out_channels=entry["out_channels"],
                kernel=list(entry["kernel"]),
                input_shape=list(entry["input_shape"]),
            )
        layer_entries.append(manifest_entry)

    manifest = {
        "name": f"{model.name}-q8",
        "version": model.version,
        "task_type": model.task_type,
        "labels": model.labels,
        "input": {
            "shape": model.input_shape,
            "quantized": True,
            "preprocessing": (
                "grayscale 28x28, integer pixels 0..255 "
                "(exact integer pipeline, no normalization)"
            ),
        },
        "weights_file": "weights.npz",
        "checksum": model_checksum,
        "layers": layer_entries,
        "metrics": {
            "test_accuracy": round(q_accuracy, 4),
            "float_test_accuracy": model.metrics.get("test_accuracy"),
        },
        "quantization": {
            "scheme": "int8-symmetric-weights, uint8 activations, exact integer requantize",
            "verification": "Freivalds over Z_p, p = 2^31 - 1, exact equality",
        },
        "quantized_at": datetime.now(timezone.utc).isoformat(),
        "weights_file_sha256": None,  # filled below
    }
    manifest["weights_file_sha256"] = hashlib.sha256(weights_path.read_bytes()).hexdigest()

    with open(output_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Post-training int8 quantization")
    parser.add_argument("--model", required=True, help="float model name to quantize")
    parser.add_argument("--models-dir", default=str(ROOT / "models"))
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "mnist"))
    args = parser.parse_args()

    store = ModelStore(Path(args.models_dir))
    model = store.get(args.model)
    if model is None:
        raise SystemExit(f"model {args.model} not found")
    if not all(isinstance(l, (DenseLayer, Conv2DLayer)) for l in model.layers):
        raise SystemExit("only dense/conv2d float models can be quantized")

    paths = download_mnist(Path(args.data_dir))
    x_train = load_idx_images(paths["train_images"])
    x_test = load_idx_images(paths["test_images"])
    y_test = load_idx_labels(paths["test_labels"])

    rng = np.random.default_rng(0)
    calib = x_train[rng.choice(len(x_train), CALIBRATION_SAMPLES, replace=False)]

    logger.info("Quantizing %s (float acc %s)", model.name, model.metrics.get("test_accuracy"))
    q_layers = quantize(model, calib)

    q_acc = evaluate_quantized(q_layers, x_test, y_test)
    logger.info("Quantized test accuracy: %.4f", q_acc)

    output_dir = Path(args.models_dir) / f"{model.name}-q8"
    manifest = export(model, q_layers, output_dir, q_acc)
    logger.info("Model checksum: %s", manifest["checksum"])
    logger.info("Saved quantized model to %s", output_dir)


if __name__ == "__main__":
    main()
