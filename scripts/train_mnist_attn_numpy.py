"""
Train a tiny vision-transformer on MNIST in pure NumPy.

This is the transformer entry in the plug-and-play model store and exists to
demonstrate that the projection-based proof of computation extends to
ATTENTION: Q/K/V/output projections verify as affine operators, and the
bilinear products S = Q·Kᵀ and O = P·V verify with Freivalds matrix-product
checks over the client-submitted (and already-verified) intermediates, with
softmax replayed server-side. This is the verification path that scales to
LLM-style distributed inference.

Architecture (seq = 16 patches of 7x7, d_model = 32):
    token_dense  49 -> 32 per patch, per-token bias (absorbs positional emb)
    attention    single head, residual, mean-pool over tokens
    dense        32 -> 10 (softmax)

Outputs (models/mnist-attn/):
    weights.npz     - trained float32 weights
    manifest.json   - manifest with REAL SHA-256 checksums over wire bytes

Usage:
    python scripts/train_mnist_attn_numpy.py [--epochs 12]
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
logger = logging.getLogger("train_mnist_attn")

SEQ = 16          # 4x4 grid of patches
PATCH = 7         # 7x7 pixels per patch
D_MODEL = 48
N_CLASSES = 10
TAU = 1.0 / np.sqrt(D_MODEL)  # attention scale; folded into Wq at export


def to_patches(x: np.ndarray) -> np.ndarray:
    """(N, 784) -> (N, 16, 49): 4x4 grid of 7x7 patches, row-major."""
    n = x.shape[0]
    return (
        x.reshape(n, 4, PATCH, 4, PATCH)
        .transpose(0, 1, 3, 2, 4)
        .reshape(n, SEQ, PATCH * PATCH)
    )


def init_params(rng: np.random.Generator) -> dict:
    def glorot(shape):
        limit = np.sqrt(6.0 / (shape[0] + shape[1]))
        return rng.uniform(-limit, limit, size=shape).astype(np.float32)

    return {
        "We": glorot((PATCH * PATCH, D_MODEL)),
        "B": (rng.normal(0, 0.02, size=(SEQ, D_MODEL))).astype(np.float32),
        "Wq": glorot((D_MODEL, D_MODEL)),
        "Wk": glorot((D_MODEL, D_MODEL)),
        "Wv": glorot((D_MODEL, D_MODEL)),
        "Wo": glorot((D_MODEL, D_MODEL)),
        "W3": glorot((D_MODEL, N_CLASSES)),
        "b3": np.zeros(N_CLASSES, dtype=np.float32),
    }


def softmax_rows(s: np.ndarray) -> np.ndarray:
    shifted = s - s.max(axis=-1, keepdims=True)
    e = np.exp(shifted)
    return e / e.sum(axis=-1, keepdims=True)


def forward(x: np.ndarray, p: dict):
    """Batched forward. x: (N, 784). Returns (probs, cache)."""
    x0 = to_patches(x)                       # (N, T, 49)
    zt = x0 @ p["We"] + p["B"]               # (N, T, d) pre-activation
    xt = np.maximum(zt, 0.0)                 # relu post-op on the embed

    q = xt @ p["Wq"]
    k = xt @ p["Wk"]
    v = xt @ p["Wv"]
    s = (q @ k.transpose(0, 2, 1)) * TAU     # (N, T, T)
    attn = softmax_rows(s)
    o = attn @ v                             # (N, T, d)
    z = o @ p["Wo"]
    xres = xt + z                            # residual
    pooled = xres.mean(axis=1)               # (N, d)

    logits = pooled @ p["W3"] + p["b3"]
    logits = logits - logits.max(axis=1, keepdims=True)
    e = np.exp(logits)
    probs = e / e.sum(axis=1, keepdims=True)

    cache = (x0, zt, xt, q, k, v, attn, o, pooled)
    return probs, cache


def backward(probs: np.ndarray, y: np.ndarray, p: dict, cache):
    x0, zt, xt, q, k, v, attn, o, pooled = cache
    n = len(y)

    dlogits = probs.copy()
    dlogits[np.arange(n), y] -= 1.0
    dlogits /= n

    grads = {}
    grads["W3"] = pooled.T @ dlogits
    grads["b3"] = dlogits.sum(axis=0)

    dpooled = dlogits @ p["W3"].T            # (N, d)
    dxres = np.repeat(dpooled[:, None, :], SEQ, axis=1) / SEQ

    dxt = dxres.copy()                        # residual branch
    dz = dxres
    grads["Wo"] = np.einsum("ntd,nte->de", o, dz)
    do = dz @ p["Wo"].T

    dattn = do @ v.transpose(0, 2, 1)         # (N, T, T)
    dv = attn.transpose(0, 2, 1) @ do

    # softmax backward (row-wise), including the TAU scale on s
    ds = attn * (dattn - (dattn * attn).sum(axis=-1, keepdims=True))
    ds *= TAU

    dq = ds @ k
    dk = ds.transpose(0, 2, 1) @ q

    grads["Wq"] = np.einsum("ntd,nte->de", xt, dq)
    grads["Wk"] = np.einsum("ntd,nte->de", xt, dk)
    grads["Wv"] = np.einsum("ntd,nte->de", xt, dv)
    dxt += dq @ p["Wq"].T + dk @ p["Wk"].T + dv @ p["Wv"].T

    dzt = dxt * (zt > 0)  # relu backward on the embed
    grads["We"] = np.einsum("nti,ntd->id", x0, dzt)
    grads["B"] = dzt.sum(axis=0)
    return grads


def evaluate(p, x, y, batch_size: int = 1024) -> float:
    correct = 0
    for start in range(0, len(x), batch_size):
        probs, _ = forward(x[start : start + batch_size], p)
        correct += int((probs.argmax(axis=1) == y[start : start + batch_size]).sum())
    return correct / len(x)


def train(p, x_train, y_train, x_val, y_val, epochs, batch_size, lr):
    rng = np.random.default_rng(7)
    n = len(x_train)
    m = {k: np.zeros_like(w) for k, w in p.items()}
    v = {k: np.zeros_like(w) for k, w in p.items()}
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    step = 0

    for epoch in range(1, epochs + 1):
        order = rng.permutation(n)
        epoch_loss, batches = 0.0, 0
        for start in range(0, n, batch_size):
            idx = order[start : start + batch_size]
            xb, yb = x_train[idx], y_train[idx]

            probs, cache = forward(xb, p)
            loss = -np.log(np.clip(probs[np.arange(len(xb)), yb], 1e-9, None)).mean()
            epoch_loss += loss
            batches += 1

            grads = backward(probs, yb, p, cache)

            step += 1
            for key in p:
                g = grads[key]
                m[key] = beta1 * m[key] + (1 - beta1) * g
                v[key] = beta2 * v[key] + (1 - beta2) * g * g
                m_hat = m[key] / (1 - beta1**step)
                v_hat = v[key] / (1 - beta2**step)
                p[key] = (p[key] - lr * m_hat / (np.sqrt(v_hat) + eps)).astype(
                    np.float32
                )

        val_acc = evaluate(p, x_val, y_val)
        logger.info(
            f"epoch {epoch:2d}/{epochs}  loss={epoch_loss / batches:.4f}  val_acc={val_acc:.4f}"
        )
    return p


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def sha256_bytes(*arrays) -> str:
    h = hashlib.sha256()
    for a in arrays:
        h.update(a.tobytes())
    return h.hexdigest()


def export(p: dict, output_dir: Path, test_accuracy: float, version: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)

    # Fold the attention scale into Wq so runtime S = Q'·Kᵀ needs no scaling.
    wq_folded = (p["Wq"] * TAU).astype(np.float32)

    weights = {
        "W0": p["We"].astype(np.float32),
        "b0": p["B"].astype(np.float32),          # per-token bias (T, d)
        "W1q": wq_folded,
        "W1k": p["Wk"].astype(np.float32),
        "W1v": p["Wv"].astype(np.float32),
        "W1o": p["Wo"].astype(np.float32),
        "W2": p["W3"].astype(np.float32),
        "b2": p["b3"].astype(np.float32),
    }
    weights_path = output_dir / "weights.npz"
    np.savez(weights_path, **weights)

    # Wire checksums: weights transposed to (out, in) row-major like dense,
    # biases in natural order, all float32 LE.
    checksum_l0 = sha256_bytes(
        np.ascontiguousarray(weights["W0"].T, dtype="<f4"),
        np.ascontiguousarray(weights["b0"], dtype="<f4"),
    )
    checksum_l1 = sha256_bytes(
        np.ascontiguousarray(weights["W1q"].T, dtype="<f4"),
        np.ascontiguousarray(weights["W1k"].T, dtype="<f4"),
        np.ascontiguousarray(weights["W1v"].T, dtype="<f4"),
        np.ascontiguousarray(weights["W1o"].T, dtype="<f4"),
    )
    checksum_l2 = sha256_bytes(
        np.ascontiguousarray(weights["W2"].T, dtype="<f4"),
        np.ascontiguousarray(weights["b2"], dtype="<f4"),
    )
    layer_checksums = [checksum_l0, checksum_l1, checksum_l2]
    model_checksum = hashlib.sha256("".join(layer_checksums).encode("ascii")).hexdigest()

    manifest = {
        "name": "mnist-attn",
        "version": version,
        "task_type": "image_classification",
        "labels": [str(i) for i in range(10)],
        "input": {
            "shape": [1, 28, 28],
            "preprocessing": (
                "grayscale 28x28, normalize /255, split into 4x4 grid of 7x7 "
                "patches row-major (handled by token_dense layer)"
            ),
        },
        "weights_file": "weights.npz",
        "checksum": model_checksum,
        "layers": [
            {
                "index": 0,
                "name": "patch_embed",
                "type": "token_dense",
                "seq": SEQ,
                "input_size": PATCH * PATCH,
                "output_size": D_MODEL,
                "activation": "relu",
                "post_ops": [{"op": "relu"}],
                "patchify": {"grid": [4, 4], "patch": [PATCH, PATCH]},
                "checksum": checksum_l0,
            },
            {
                "index": 1,
                "name": "self_attention",
                "type": "attention",
                "seq": SEQ,
                "d_model": D_MODEL,
                "activation": "linear",
                "post_ops": [
                    {"op": "residual_input"},
                    {"op": "mean_pool_tokens", "seq": SEQ, "dim": D_MODEL},
                ],
                "checksum": checksum_l1,
            },
            {
                "index": 2,
                "name": "dense_output",
                "type": "dense",
                "input_size": D_MODEL,
                "output_size": N_CLASSES,
                "activation": "softmax",
                "post_ops": [{"op": "softmax"}],
                "checksum": checksum_l2,
            },
        ],
        "metrics": {"test_accuracy": round(test_accuracy, 4)},
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "weights_file_sha256": hashlib.sha256(weights_path.read_bytes()).hexdigest(),
    }

    with open(output_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Train tiny MNIST ViT in pure NumPy")
    parser.add_argument("--output", default="models/mnist-attn")
    parser.add_argument("--data-dir", default="data/mnist")
    parser.add_argument("--epochs", type=int, default=12)
    parser.add_argument("--batch-size", type=int, default=256)
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
