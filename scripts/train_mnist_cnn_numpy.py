"""
Train a real convolutional MNIST model for PoUW CAPTCHA in pure NumPy.

This is the first non-dense architecture in the plug-and-play model store and
exists to demonstrate that the projection-based proof of computation extends
to ANY affine layer (conv2d here), not just dense matmuls:

    conv2d  1->8  3x3 valid  (relu, maxpool 2)   28x28 -> 26x26 -> 13x13
    conv2d  8->16 3x3 valid  (relu, maxpool 2, flatten)  13x13 -> 11x11 -> 5x5
    dense   400 -> 64        (relu)
    dense    64 -> 10        (softmax)

Clients compute and submit the pre-activation of each provable (affine) layer;
relu/maxpool/flatten are cheap post-ops the server replays during verification.

Outputs (models/mnist-cnn/):
    weights.npz     - trained float32 weights (W0,b0..W3,b3)
    manifest.json   - manifest with REAL SHA-256 checksums over wire bytes

Usage:
    python scripts/train_mnist_cnn_numpy.py [--epochs 4] [--output models/mnist-cnn]
"""

import argparse
import hashlib
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_mnist_numpy import download_mnist, load_idx_images, load_idx_labels  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_mnist_cnn")

# Provable layers + their server-side post-op chains. Shapes are (C, H, W).
LAYER_SPECS = [
    {
        "name": "conv_1",
        "type": "conv2d",
        "in_channels": 1,
        "out_channels": 8,
        "kernel": [3, 3],
        "input_shape": [1, 28, 28],
        "activation": "relu",
        "post_ops": [
            {"op": "relu"},
            {"op": "maxpool2d", "pool": 2, "shape": [8, 26, 26]},
        ],
    },
    {
        "name": "conv_2",
        "type": "conv2d",
        "in_channels": 8,
        "out_channels": 16,
        "kernel": [3, 3],
        "input_shape": [8, 13, 13],
        "activation": "relu",
        "post_ops": [
            {"op": "relu"},
            {"op": "maxpool2d", "pool": 2, "shape": [16, 11, 11]},
            {"op": "flatten"},
        ],
    },
    {
        "name": "dense_hidden",
        "type": "dense",
        "input_size": 400,
        "output_size": 64,
        "activation": "relu",
        "post_ops": [{"op": "relu"}],
    },
    {
        "name": "dense_output",
        "type": "dense",
        "input_size": 64,
        "output_size": 10,
        "activation": "softmax",
        "post_ops": [{"op": "softmax"}],
    },
]


# ---------------------------------------------------------------------------
# Batched conv / pool primitives (im2col)
# ---------------------------------------------------------------------------

def im2col(x: np.ndarray, kh: int, kw: int) -> np.ndarray:
    """(N,C,H,W) -> (N, OH*OW, C*kh*kw) patch matrix for valid stride-1 conv."""
    n, c, h, w = x.shape
    oh, ow = h - kh + 1, w - kw + 1
    cols = np.empty((n, c, kh, kw, oh, ow), dtype=x.dtype)
    for u in range(kh):
        for v in range(kw):
            cols[:, :, u, v] = x[:, :, u : u + oh, v : v + ow]
    return cols.transpose(0, 4, 5, 1, 2, 3).reshape(n, oh * ow, c * kh * kw)


def conv_forward(x: np.ndarray, w: np.ndarray, b: np.ndarray):
    n = x.shape[0]
    oc, _, kh, kw = w.shape
    oh, ow = x.shape[2] - kh + 1, x.shape[3] - kw + 1
    cols = im2col(x, kh, kw)
    z = cols @ w.reshape(oc, -1).T + b  # (N, OH*OW, OC)
    return z.transpose(0, 2, 1).reshape(n, oc, oh, ow), cols


def conv_backward(dz: np.ndarray, x_shape, cols: np.ndarray, w: np.ndarray):
    n, c, h, wd = x_shape
    oc, _, kh, kw = w.shape
    oh, ow = h - kh + 1, wd - kw + 1
    dz2 = dz.reshape(n, oc, oh * ow).transpose(0, 2, 1)  # (N, P, OC)
    dw = np.einsum("npo,npk->ok", dz2, cols).reshape(w.shape)
    db = dz.sum(axis=(0, 2, 3))
    dcols = dz2 @ w.reshape(oc, -1)  # (N, P, C*kh*kw)
    d6 = dcols.reshape(n, oh, ow, c, kh, kw).transpose(0, 3, 4, 5, 1, 2)
    dx = np.zeros(x_shape, dtype=dz.dtype)
    for u in range(kh):
        for v in range(kw):
            dx[:, :, u : u + oh, v : v + ow] += d6[:, :, u, v]
    return dx, dw, db


def pool_forward(x: np.ndarray, pool: int = 2):
    n, c, h, w = x.shape
    oh, ow = h // pool, w // pool
    xc = x[:, :, : oh * pool, : ow * pool].reshape(n, c, oh, pool, ow, pool)
    return xc.max(axis=(3, 5)), xc


def pool_backward(
    dout: np.ndarray, xc: np.ndarray, out: np.ndarray, x_shape, pool: int = 2
):
    n, c, h, w = x_shape
    oh, ow = dout.shape[2], dout.shape[3]
    mask = xc == out[:, :, :, None, :, None]
    counts = np.maximum(mask.sum(axis=(3, 5), keepdims=True), 1)
    dxc = mask * dout[:, :, :, None, :, None] / counts
    dx = np.zeros(x_shape, dtype=dout.dtype)
    dx[:, :, : oh * pool, : ow * pool] = dxc.reshape(n, c, oh * pool, ow * pool)
    return dx


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

def init_params(rng: np.random.Generator) -> list:
    """He-initialised weights (float32) for conv and dense layers."""
    params = []
    for spec in LAYER_SPECS:
        if spec["type"] == "conv2d":
            kh, kw = spec["kernel"]
            fan_in = spec["in_channels"] * kh * kw
            w = rng.normal(
                0.0,
                np.sqrt(2.0 / fan_in),
                size=(spec["out_channels"], spec["in_channels"], kh, kw),
            )
            b = np.zeros(spec["out_channels"])
        else:
            fan_in = spec["input_size"]
            w = rng.normal(
                0.0, np.sqrt(2.0 / fan_in), size=(fan_in, spec["output_size"])
            )
            b = np.zeros(spec["output_size"])
        params.append([w.astype(np.float32), b.astype(np.float32)])
    return params


def forward(x: np.ndarray, params: list):
    """Batched forward pass. Returns (probs, cache for backprop)."""
    n = x.shape[0]
    x0 = x.reshape(n, 1, 28, 28)

    z0, cols0 = conv_forward(x0, *params[0])
    a0 = np.maximum(z0, 0.0)
    p0, xc0 = pool_forward(a0)  # (N,8,13,13)

    z1, cols1 = conv_forward(p0, *params[1])
    a1 = np.maximum(z1, 0.0)
    p1, xc1 = pool_forward(a1)  # (N,16,5,5)
    flat = p1.reshape(n, -1)  # (N,400)

    z2 = flat @ params[2][0] + params[2][1]
    a2 = np.maximum(z2, 0.0)

    z3 = a2 @ params[3][0] + params[3][1]
    z3 = z3 - z3.max(axis=1, keepdims=True)
    e = np.exp(z3)
    probs = e / e.sum(axis=1, keepdims=True)

    cache = (x0, z0, cols0, a0, p0, xc0, z1, cols1, a1, p1, xc1, flat, z2, a2)
    return probs, cache


def backward(probs: np.ndarray, y: np.ndarray, params: list, cache):
    (x0, z0, cols0, a0, p0, xc0, z1, cols1, a1, p1, xc1, flat, z2, a2) = cache
    n = len(y)

    dz3 = probs.copy()
    dz3[np.arange(n), y] -= 1.0
    dz3 /= n

    g3 = [a2.T @ dz3, dz3.sum(axis=0)]
    da2 = dz3 @ params[3][0].T
    dz2 = da2 * (z2 > 0)

    g2 = [flat.T @ dz2, dz2.sum(axis=0)]
    dflat = dz2 @ params[2][0].T
    dp1 = dflat.reshape(p1.shape)

    da1 = pool_backward(dp1, xc1, p1, a1.shape)
    dz1 = da1 * (z1 > 0)
    dp0, dw1, db1 = conv_backward(dz1, p0.shape, cols1, params[1][0])
    g1 = [dw1, db1]

    da0 = pool_backward(dp0, xc0, p0, a0.shape)
    dz0 = da0 * (z0 > 0)
    _, dw0, db0 = conv_backward(dz0, x0.shape, cols0, params[0][0])
    g0 = [dw0, db0]

    return [g0, g1, g2, g3]


def evaluate(params, x, y, batch_size: int = 512) -> float:
    correct = 0
    for start in range(0, len(x), batch_size):
        probs, _ = forward(x[start : start + batch_size], params)
        correct += int((probs.argmax(axis=1) == y[start : start + batch_size]).sum())
    return correct / len(x)


def train(params, x_train, y_train, x_val, y_val, epochs, batch_size, lr):
    """Mini-batch Adam training with cross-entropy loss."""
    rng = np.random.default_rng(7)
    n = len(x_train)
    m = [[np.zeros_like(w), np.zeros_like(b)] for w, b in params]
    v = [[np.zeros_like(w), np.zeros_like(b)] for w, b in params]
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    step = 0

    for epoch in range(1, epochs + 1):
        order = rng.permutation(n)
        epoch_loss, batches = 0.0, 0
        for start in range(0, n, batch_size):
            idx = order[start : start + batch_size]
            xb, yb = x_train[idx], y_train[idx]

            probs, cache = forward(xb, params)
            loss = -np.log(np.clip(probs[np.arange(len(xb)), yb], 1e-9, None)).mean()
            epoch_loss += loss
            batches += 1

            grads = backward(probs, yb, params, cache)

            step += 1
            for i in range(len(params)):
                for j in range(2):
                    g = grads[i][j]
                    m[i][j] = beta1 * m[i][j] + (1 - beta1) * g
                    v[i][j] = beta2 * v[i][j] + (1 - beta2) * g * g
                    m_hat = m[i][j] / (1 - beta1**step)
                    v_hat = v[i][j] / (1 - beta2**step)
                    params[i][j] = (
                        params[i][j] - lr * m_hat / (np.sqrt(v_hat) + eps)
                    ).astype(np.float32)

        val_acc = evaluate(params, x_val, y_val)
        logger.info(
            f"epoch {epoch:2d}/{epochs}  loss={epoch_loss / batches:.4f}  val_acc={val_acc:.4f}"
        )
    return params


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def layer_checksum(spec: dict, w: np.ndarray, b: np.ndarray) -> str:
    """
    Canonical layer checksum: sha256 over float32 little-endian bytes in WIRE
    order. Dense: weights flattened (output, input) row-major. Conv2d: weights
    flattened (out_ch, in_ch, kh, kw) row-major. Biases follow in both cases.
    This is exactly the byte sequence a browser rebuilds from the JSON shard
    payload via Float32Array.
    """
    h = hashlib.sha256()
    if spec["type"] == "dense":
        h.update(np.ascontiguousarray(w.T, dtype="<f4").tobytes())
    else:
        h.update(np.ascontiguousarray(w, dtype="<f4").tobytes())
    h.update(np.ascontiguousarray(b, dtype="<f4").tobytes())
    return h.hexdigest()


def export(params, output_dir: Path, test_accuracy: float, version: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    weights = {}
    for i, (w, b) in enumerate(params):
        weights[f"W{i}"] = w
        weights[f"b{i}"] = b
    weights_path = output_dir / "weights.npz"
    np.savez(weights_path, **weights)

    layer_checksums = [
        layer_checksum(spec, w, b) for spec, (w, b) in zip(LAYER_SPECS, params)
    ]
    model_checksum = hashlib.sha256("".join(layer_checksums).encode("ascii")).hexdigest()

    layer_entries = []
    for i, spec in enumerate(LAYER_SPECS):
        entry = {
            "index": i,
            "name": spec["name"],
            "type": spec["type"],
            "activation": spec["activation"],
            "post_ops": spec["post_ops"],
            "checksum": layer_checksums[i],
        }
        if spec["type"] == "conv2d":
            entry.update(
                in_channels=spec["in_channels"],
                out_channels=spec["out_channels"],
                kernel=spec["kernel"],
                input_shape=spec["input_shape"],
            )
        else:
            entry.update(
                input_size=spec["input_size"], output_size=spec["output_size"]
            )
        layer_entries.append(entry)

    manifest = {
        "name": "mnist-cnn",
        "version": version,
        "task_type": "image_classification",
        "labels": [str(i) for i in range(10)],
        "input": {
            "shape": [1, 28, 28],
            "preprocessing": "grayscale 28x28, normalize /255, flatten row-major",
        },
        "weights_file": "weights.npz",
        "checksum": model_checksum,
        "layers": layer_entries,
        "metrics": {"test_accuracy": round(test_accuracy, 4)},
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "weights_file_sha256": hashlib.sha256(weights_path.read_bytes()).hexdigest(),
    }

    with open(output_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Train MNIST CNN in pure NumPy")
    parser.add_argument("--output", default="models/mnist-cnn")
    parser.add_argument("--data-dir", default="data/mnist")
    parser.add_argument("--epochs", type=int, default=4)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--version", default="1.0.0")
    args = parser.parse_args()

    paths = download_mnist(Path(args.data_dir))
    x_train = load_idx_images(paths["train_images"])
    y_train = load_idx_labels(paths["train_labels"])
    x_test = load_idx_images(paths["test_images"])
    y_test = load_idx_labels(paths["test_labels"])

    x_val, y_val = x_train[-5000:], y_train[-5000:]
    x_train, y_train = x_train[:-5000], y_train[:-5000]
    logger.info(f"train={len(x_train)} val={len(x_val)} test={len(x_test)}")

    params = init_params(np.random.default_rng(42))
    start = time.time()
    params = train(
        params, x_train, y_train, x_val, y_val, args.epochs, args.batch_size, args.lr
    )
    logger.info(f"Training took {time.time() - start:.1f}s")

    test_acc = evaluate(params, x_test, y_test)
    logger.info(f"Test accuracy: {test_acc:.4f}")

    manifest = export(params, Path(args.output), test_acc, args.version)
    logger.info(f"Model checksum: {manifest['checksum']}")
    logger.info(f"Saved model to {args.output}")


if __name__ == "__main__":
    main()
