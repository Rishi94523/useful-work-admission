"""
Plug-and-play model store.

Loads trained models from ``models/<name>/manifest.json`` + ``weights.npz``.
Each model declares its layers, labels, preprocessing and REAL SHA-256
checksums (one per layer over the exact wire bytes, plus a model checksum
that is a hash of the layer checksums, so clients holding only a segment of
the model can still verify integrity).

Layer model
-----------
A model is a sequence of PROVABLE layers. Each provable layer is an affine
operator ``z = L·x + b`` — dense (L = matmul) or conv2d (L = convolution) —
followed by a chain of cheap, server-applied POST-OPS (relu, softmax,
maxpool2d, flatten). Clients compute and submit the pre-activation ``z`` of
each provable layer; the server verifies ``z`` with secret projections (see
proof_verifier) and applies the post-ops itself to produce the next layer's
input. Because every provable layer is affine, the same projection identity

    r · z  =  (Lᵀ r) · x  +  r · b

verifies dense and convolutional work alike, so new architectures only need
to implement ``forward`` and ``project``.

Adding a new dataset/model to the system means dropping a new manifest +
weights directory into ``models/`` — no code changes required for any
combination of dense and conv2d layers.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# models/ directory at the repository root (server/ is the CWD in dev)
DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[3] / "models"


# ---------------------------------------------------------------------------
# Post-ops: cheap O(n) transforms the server applies between provable layers
# ---------------------------------------------------------------------------

def apply_post_ops(z: np.ndarray, post_ops: Sequence[dict]) -> np.ndarray:
    """
    Apply a layer's post-op chain to its flat pre-activation vector.

    Every op is O(n) — orders of magnitude cheaper than the affine layer the
    client computed — so the server can run them during verification without
    giving up the compute asymmetry. Mirrored exactly by the browser client.
    """
    h = np.asarray(z, dtype=np.float64)
    for op in post_ops:
        kind = op["op"]
        if kind == "relu":
            h = np.maximum(h, 0.0)
        elif kind == "softmax":
            shifted = h - np.max(h)
            e = np.exp(shifted)
            h = e / e.sum()
        elif kind == "sigmoid":
            h = 1.0 / (1.0 + np.exp(-h))
        elif kind == "tanh":
            h = np.tanh(h)
        elif kind == "maxpool2d":
            c, height, width = op["shape"]
            pool = int(op.get("pool", 2))
            oh, ow = height // pool, width // pool
            t = h.reshape(c, height, width)[:, : oh * pool, : ow * pool]
            t = t.reshape(c, oh, pool, ow, pool)
            h = t.max(axis=(2, 4)).reshape(-1)
        elif kind == "flatten":
            h = h.reshape(-1)
        elif kind == "linear":
            pass
        else:
            raise ValueError(f"unknown post-op {kind!r}")
    return h


def post_ops_output_size(input_size: int, post_ops: Sequence[dict]) -> int:
    """Flat size after applying a post-op chain to ``input_size`` elements."""
    size = input_size
    for op in post_ops:
        if op["op"] == "maxpool2d":
            c, height, width = op["shape"]
            pool = int(op.get("pool", 2))
            size = c * (height // pool) * (width // pool)
    return size


# ---------------------------------------------------------------------------
# Provable layers
# ---------------------------------------------------------------------------

@dataclass
class DenseLayer:
    """A dense affine layer ``z = x·W + b`` with its wire-format checksum."""

    index: int
    name: str
    activation: str
    input_size: int
    output_size: int
    weights: np.ndarray  # shape (input_size, output_size), float32
    biases: np.ndarray  # shape (output_size,), float32
    checksum: str
    post_ops: List[dict] = field(default_factory=list)

    layer_type = "dense"

    def __post_init__(self) -> None:
        if not self.post_ops and self.activation and self.activation != "linear":
            self.post_ops = [{"op": self.activation}]

    @property
    def compute_ops(self) -> int:
        """Multiply-accumulates the client spends on this layer."""
        return self.input_size * self.output_size

    @property
    def projection_ops(self) -> int:
        """Multiplications per secret-projection check (O(in + out))."""
        return self.input_size + self.output_size

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Reference pre-activation (float64). Used for audits/tests only."""
        return np.asarray(x, dtype=np.float64) @ self.weights.astype(
            np.float64
        ) + self.biases.astype(np.float64)

    def project(self, r: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Freivalds precomputation: return (s, r·b) with s = Lᵀr = W·r so that
        r·z = s·x + r·b for any honest z = x·W + b.
        """
        w = self.weights.astype(np.float64)
        b = self.biases.astype(np.float64)
        return w @ r, float(r @ b)

    def wire_payload(self) -> dict:
        """
        JSON payload the browser executes. Weights are flattened in
        (output, input) row-major order to match the client's
        ``weights[o * inputSize + i]`` indexing.
        """
        return {
            "name": self.name,
            "type": "dense",
            "weights": np.ascontiguousarray(self.weights.T, dtype=np.float32)
            .flatten()
            .tolist(),
            "biases": self.biases.astype(np.float32).tolist(),
            "inputShape": [1, self.input_size],
            "outputShape": [1, self.output_size],
            "activation": self.activation,
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        """SHA-256 over the exact float32 LE bytes a client receives."""
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.weights.T, dtype="<f4").tobytes())
        h.update(np.ascontiguousarray(self.biases, dtype="<f4").tobytes())
        return h.hexdigest()


@dataclass
class Conv2DLayer:
    """
    A valid (no padding), stride-1 2D convolution ``z = W * x + b``.

    Tensors are flattened channel-major (C, H, W) row-major on the wire and in
    pipeline handoffs. Weights are stored (out_ch, in_ch, kh, kw); the wire
    flattening ``weights[((oc*inCh + ic)*kh + u)*kw + v]`` matches the dense
    layer's output-major convention.
    """

    index: int
    name: str
    activation: str
    in_channels: int
    out_channels: int
    kernel: Tuple[int, int]
    input_shape: Tuple[int, int, int]  # (in_ch, H, W)
    weights: np.ndarray  # (out_ch, in_ch, kh, kw), float32
    biases: np.ndarray  # (out_ch,), float32
    checksum: str
    post_ops: List[dict] = field(default_factory=list)

    layer_type = "conv2d"

    def __post_init__(self) -> None:
        if not self.post_ops and self.activation and self.activation != "linear":
            self.post_ops = [{"op": self.activation}]

    @property
    def output_shape(self) -> Tuple[int, int, int]:
        _, height, width = self.input_shape
        kh, kw = self.kernel
        return (self.out_channels, height - kh + 1, width - kw + 1)

    @property
    def input_size(self) -> int:
        return int(np.prod(self.input_shape))

    @property
    def output_size(self) -> int:
        return int(np.prod(self.output_shape))

    @property
    def compute_ops(self) -> int:
        oc, oh, ow = self.output_shape
        kh, kw = self.kernel
        return oh * ow * oc * self.in_channels * kh * kw

    @property
    def projection_ops(self) -> int:
        return self.input_size + self.output_size

    def forward(self, x: np.ndarray) -> np.ndarray:
        """Reference pre-activation (float64, flat). Audits/tests only."""
        c, height, width = self.input_shape
        oc, oh, ow = self.output_shape
        kh, kw = self.kernel
        x3 = np.asarray(x, dtype=np.float64).reshape(c, height, width)
        w = self.weights.astype(np.float64)
        z = np.zeros((oc, oh, ow))
        for u in range(kh):
            for v in range(kw):
                patch = x3[:, u : u + oh, v : v + ow]
                z += np.tensordot(w[:, :, u, v], patch, axes=(1, 0))
        z += self.biases.astype(np.float64)[:, None, None]
        return z.reshape(-1)

    def project(self, r: np.ndarray) -> Tuple[np.ndarray, float]:
        """
        Freivalds precomputation for convolution: s = Lᵀr is the transposed
        convolution of r with the kernels (computed ONCE per model version),
        after which each verification is a single O(in)+O(out) dot product —
        the asymmetry grows with kernel size × channels.
        """
        c, height, width = self.input_shape
        oc, oh, ow = self.output_shape
        kh, kw = self.kernel
        r3 = np.asarray(r, dtype=np.float64).reshape(oc, oh, ow)
        w = self.weights.astype(np.float64)
        s3 = np.zeros((c, height, width))
        for u in range(kh):
            for v in range(kw):
                s3[:, u : u + oh, v : v + ow] += np.tensordot(
                    w[:, :, u, v], r3, axes=(0, 0)
                )
        r_dot_b = float(
            np.sum(self.biases.astype(np.float64) * r3.sum(axis=(1, 2)))
        )
        return s3.reshape(-1), r_dot_b

    def wire_payload(self) -> dict:
        return {
            "name": self.name,
            "type": "conv2d",
            "weights": np.ascontiguousarray(self.weights, dtype=np.float32)
            .flatten()
            .tolist(),
            "biases": self.biases.astype(np.float32).tolist(),
            "inputShape": list(self.input_shape),
            "outputShape": list(self.output_shape),
            "kernel": list(self.kernel),
            "activation": self.activation,
            "postOps": list(self.post_ops),
        }

    def compute_checksum(self) -> str:
        """SHA-256 over the exact float32 LE bytes a client receives."""
        h = hashlib.sha256()
        h.update(np.ascontiguousarray(self.weights, dtype="<f4").tobytes())
        h.update(np.ascontiguousarray(self.biases, dtype="<f4").tobytes())
        return h.hexdigest()


ProvableLayer = DenseLayer  # legacy alias; layers are duck-typed


# ---------------------------------------------------------------------------
# Model spec
# ---------------------------------------------------------------------------

@dataclass
class ModelSpec:
    """A loaded, integrity-verified model."""

    name: str
    version: str
    task_type: str
    labels: List[str]
    input_shape: List[int]
    preprocessing: str
    checksum: str
    layers: List = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def total_layers(self) -> int:
        return len(self.layers)

    @property
    def input_size(self) -> int:
        return int(np.prod(self.input_shape))

    @property
    def total_compute_ops(self) -> int:
        return sum(layer.compute_ops for layer in self.layers)

    def shard_payloads(self, start: int, end: int) -> List[dict]:
        """Wire payloads (with checksums) for the layer segment [start, end)."""
        payloads = []
        for layer in self.layers[start:end]:
            wire = layer.wire_payload()
            payloads.append(
                {
                    "index": layer.index,
                    "name": layer.name,
                    "layerType": layer.layer_type,
                    "inputShape": wire["inputShape"],
                    "outputShape": wire["outputShape"],
                    "activation": layer.activation,
                    "checksum": layer.checksum,
                    "layers": [wire],
                }
            )
        return payloads

    def apply_activation(self, z: np.ndarray, activation: str) -> np.ndarray:
        """Apply a single named activation (legacy dense path)."""
        return apply_post_ops(z, [{"op": activation}] if activation else [])

    def apply_layer_post_ops(self, z: np.ndarray, layer_index: int) -> np.ndarray:
        """Apply layer ``layer_index``'s post-op chain to its pre-activation."""
        return apply_post_ops(z, self.layers[layer_index].post_ops)

    def forward_segment(
        self, x: np.ndarray, start: int, end: int
    ) -> tuple[List[np.ndarray], np.ndarray]:
        """
        Reference forward pass over layers [start, end).

        Returns (pre_activations per layer, final post-op output). Used only
        for spot audits and tests — routine validation uses the projection
        checks in proof_verifier, which never run this.
        """
        pre_activations: List[np.ndarray] = []
        h = np.asarray(x, dtype=np.float64)
        for layer in self.layers[start:end]:
            z = layer.forward(h)
            pre_activations.append(z)
            h = apply_post_ops(z, layer.post_ops)
        return pre_activations, h

    def predict(self, x: np.ndarray) -> np.ndarray:
        """Full forward pass returning class probabilities."""
        _, h = self.forward_segment(x, 0, self.total_layers)
        return h

    def preprocess_sample(
        self, sample_blob: Optional[bytes], sample_url: Optional[str] = None
    ) -> List[float]:
        """Convert raw sample bytes into the model's input vector."""
        if sample_blob:
            try:
                if len(self.input_shape) == 3:
                    _, height, width = self.input_shape
                else:
                    height = width = int(np.sqrt(self.input_size))
                image = (
                    Image.open(io.BytesIO(sample_blob))
                    .convert("L")
                    .resize((width, height))
                )
                pixels = np.asarray(image, dtype=np.float32) / 255.0
                return pixels.flatten().tolist()
            except Exception:
                pass  # non-image blob: fall through to raw bytes

        source = sample_blob or (sample_url.encode("utf-8") if sample_url else b"")
        values = [byte / 255.0 for byte in source[: self.input_size]]
        values.extend([0.0] * (self.input_size - len(values)))
        return values


def encode_input_data(input_data: Sequence[float]) -> str:
    """Encode float32 input data as base64 for the browser shard engine."""
    packed = struct.pack(f"<{len(input_data)}f", *input_data)
    return base64.b64encode(packed).decode("ascii")


def decode_input_data(encoded: str) -> List[float]:
    """Decode base64 float32 data back to a list."""
    raw = base64.b64decode(encoded)
    return list(struct.unpack(f"<{len(raw) // 4}f", raw))


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def _load_layer(layer_manifest: dict, weights: np.lib.npyio.NpzFile):
    i = layer_manifest["index"]
    layer_type = layer_manifest.get("type", "dense")
    post_ops = list(layer_manifest.get("post_ops", []))

    if layer_type == "dense":
        return DenseLayer(
            index=i,
            name=layer_manifest["name"],
            activation=layer_manifest["activation"],
            input_size=layer_manifest["input_size"],
            output_size=layer_manifest["output_size"],
            weights=weights[f"W{i}"].astype(np.float32),
            biases=weights[f"b{i}"].astype(np.float32),
            checksum=layer_manifest["checksum"],
            post_ops=post_ops,
        )
    if layer_type == "conv2d":
        return Conv2DLayer(
            index=i,
            name=layer_manifest["name"],
            activation=layer_manifest.get("activation", "linear"),
            in_channels=layer_manifest["in_channels"],
            out_channels=layer_manifest["out_channels"],
            kernel=tuple(layer_manifest["kernel"]),
            input_shape=tuple(layer_manifest["input_shape"]),
            weights=weights[f"W{i}"].astype(np.float32),
            biases=weights[f"b{i}"].astype(np.float32),
            checksum=layer_manifest["checksum"],
            post_ops=post_ops,
        )
    raise ValueError(f"unknown layer type {layer_type!r}")


class ModelStore:
    """Loads and serves all models found under the models directory."""

    def __init__(self, models_dir: Optional[Path] = None):
        self.models_dir = Path(models_dir) if models_dir else DEFAULT_MODELS_DIR
        self._models: Dict[str, ModelSpec] = {}
        self._loaded = False

    def load(self) -> None:
        if self._loaded:
            return
        for manifest_path in sorted(self.models_dir.glob("*/manifest.json")):
            try:
                spec = self._load_model(manifest_path)
                self._models[spec.name] = spec
                logger.info(
                    "Loaded model %s v%s (%d layers, checksum %s…)",
                    spec.name,
                    spec.version,
                    spec.total_layers,
                    spec.checksum[:12],
                )
            except Exception as exc:
                logger.error("Failed to load model at %s: %s", manifest_path, exc)
        self._loaded = True
        if not self._models:
            raise RuntimeError(
                f"No models found in {self.models_dir}. "
                "Run scripts/train_mnist_numpy.py first."
            )

    def _load_model(self, manifest_path: Path) -> ModelSpec:
        with open(manifest_path) as f:
            manifest = json.load(f)

        model_dir = manifest_path.parent
        weights_path = model_dir / manifest["weights_file"]

        # Verify the weights file is exactly the one the manifest was built from
        actual_file_hash = hashlib.sha256(weights_path.read_bytes()).hexdigest()
        expected_file_hash = manifest.get("weights_file_sha256")
        if expected_file_hash and actual_file_hash != expected_file_hash:
            raise ValueError(f"weights file hash mismatch for {manifest['name']}")

        weights = np.load(weights_path)
        layers = []
        for layer_manifest in manifest["layers"]:
            layer = _load_layer(layer_manifest, weights)
            # Verify each layer's declared checksum against the actual weights
            actual = layer.compute_checksum()
            if actual != layer.checksum:
                raise ValueError(
                    f"layer checksum mismatch for {manifest['name']} "
                    f"layer {layer.index}"
                )
            layers.append(layer)

        # Model checksum = hash of layer checksums (verify it too)
        expected_model_checksum = hashlib.sha256(
            "".join(l.checksum for l in layers).encode("ascii")
        ).hexdigest()
        if expected_model_checksum != manifest["checksum"]:
            raise ValueError(f"model checksum mismatch for {manifest['name']}")

        return ModelSpec(
            name=manifest["name"],
            version=manifest["version"],
            task_type=manifest["task_type"],
            labels=manifest["labels"],
            input_shape=manifest["input"]["shape"],
            preprocessing=manifest["input"].get("preprocessing", ""),
            checksum=manifest["checksum"],
            layers=layers,
            metrics=manifest.get("metrics", {}),
        )

    def get(self, name: str) -> Optional[ModelSpec]:
        self.load()
        return self._models.get(name)

    def get_default(self) -> ModelSpec:
        self.load()
        if "mnist-tiny" in self._models:
            return self._models["mnist-tiny"]
        return next(iter(self._models.values()))

    def list_models(self) -> List[ModelSpec]:
        self.load()
        return list(self._models.values())


_store: Optional[ModelStore] = None


def get_model_store() -> ModelStore:
    """Get or create the global model store."""
    global _store
    if _store is None:
        _store = ModelStore()
        _store.load()
    return _store


def reset_model_store() -> None:
    """Reset the global store (for tests)."""
    global _store
    _store = None
