"""
End-to-end client simulator: behaves exactly like the browser shard engine.

Runs N CAPTCHA solves against a live server, verifying shard checksums,
computing assigned segments in float32, submitting pre-activation proofs, and
answering human-verification prompts. Prints pipeline progress so you can
watch distributed runs get pieced together.

Usage (server must be running):
    python scripts/e2e_client.py [--solves 8] [--api http://localhost:8000/api/v1]
"""

import argparse
import base64
import hashlib
import struct
import sys
import time

import numpy as np
import httpx


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def hash_tensor(values) -> str:
    return hash_text(",".join(f"{float(v):.4f}" for v in values))


def verify_shard_checksum(shard) -> bool:
    layer = shard["layers"][0]
    w = np.asarray(layer["weights"], dtype="<f4").tobytes()
    b = np.asarray(layer["biases"], dtype="<f4").tobytes()
    return hashlib.sha256(w + b).hexdigest() == shard["checksum"]


def apply_activation(values: np.ndarray, activation: str) -> np.ndarray:
    if activation == "relu":
        return np.maximum(values, 0.0).astype(np.float32)
    if activation == "softmax":
        shifted = values.astype(np.float64) - np.max(values)
        e = np.exp(shifted)
        return (e / e.sum()).astype(np.float32)
    if activation == "sigmoid":
        return (1.0 / (1.0 + np.exp(-values.astype(np.float64)))).astype(np.float32)
    if activation == "tanh":
        return np.tanh(values).astype(np.float32)
    return values.astype(np.float32)


def apply_post_ops(values: np.ndarray, layer: dict) -> np.ndarray:
    """Post-op chain after the affine computation, like the browser client."""
    ops = layer.get("postOps") or []
    if not ops and layer.get("activation") not in (None, "", "linear"):
        ops = [{"op": layer["activation"]}]
    current = values
    for op in ops:
        kind = op["op"]
        if kind == "maxpool2d":
            c, h, w = op["shape"]
            pool = op.get("pool") or 2
            oh, ow = h // pool, w // pool
            t = current.reshape(c, h, w)[:, : oh * pool, : ow * pool]
            t = t.reshape(c, oh, pool, ow, pool)
            current = t.max(axis=(2, 4)).reshape(-1).astype(np.float32)
        elif kind in ("flatten", "linear"):
            pass
        else:
            current = apply_activation(current, kind)
    return current


def forward_pre_activation(current: np.ndarray, layer: dict) -> np.ndarray:
    """Affine layer compute (dense or conv2d), float32 like the browser."""
    if layer["type"] == "conv2d":
        in_ch, in_h, in_w = layer["inputShape"]
        out_ch, out_h, out_w = layer["outputShape"]
        kh, kw = layer["kernel"]
        w = np.asarray(layer["weights"], dtype=np.float32).reshape(
            out_ch, in_ch, kh, kw
        )
        b = np.asarray(layer["biases"], dtype=np.float32)
        x3 = current.astype(np.float64).reshape(in_ch, in_h, in_w)
        z = np.zeros((out_ch, out_h, out_w))
        for u in range(kh):
            for v in range(kw):
                z += np.tensordot(
                    w[:, :, u, v].astype(np.float64),
                    x3[:, u : u + out_h, v : v + out_w],
                    axes=(1, 0),
                )
        z += b.astype(np.float64)[:, None, None]
        return z.reshape(-1).astype(np.float32)

    in_size = layer["inputShape"][-1]
    out_size = layer["outputShape"][-1]
    w = np.asarray(layer["weights"], dtype=np.float32).reshape(out_size, in_size)
    b = np.asarray(layer["biases"], dtype=np.float32)
    return (current.astype(np.float64) @ w.T.astype(np.float64) + b).astype(
        np.float32
    )


def solve_once(client: httpx.Client, api: str, solver_id: int) -> dict:
    init = client.post(
        f"{api}/captcha/init",
        json={
            "siteKey": "pk_demo_1234567890",
            "clientMetadata": {
                "userAgent": f"e2e-client/{solver_id}",
                "language": "en-US",
                "timezone": "UTC",
                "screenWidth": 1920,
                "screenHeight": 1080,
            },
        },
    )
    init.raise_for_status()
    data = init.json()
    task = data["task"]

    # Verify shard integrity like the browser does
    for shard in task["shards"]:
        assert verify_shard_checksum(shard), f"checksum failed for {shard['name']}"

    # Decode input and compute the segment (float32, like Float32Array)
    raw = base64.b64decode(task["inputData"])
    x = np.array(struct.unpack(f"<{len(raw) // 4}f", raw), dtype=np.float32)

    segment_start = task["segmentStart"]
    total_layers = task["totalLayers"]
    layers = [l for shard in task["shards"] for l in shard["layers"]]
    is_final = segment_start + len(layers) >= total_layers

    start = time.time()
    pre_activations = []
    current = x
    for layer in layers:
        z = forward_pre_activation(current, layer)
        pre_activations.append(z)
        current = apply_post_ops(z, layer)
    compute_ms = max(15, int((time.time() - start) * 1000))

    prediction = None
    prediction_hash = ""
    if is_final:
        probs = current.astype(np.float64)
        order = np.argsort(probs)[::-1][:5]
        top_k = [
            {"label": task["labels"][i], "confidence": round(float(probs[i]), 3)}
            for i in order
        ]
        prediction = {
            "label": top_k[0]["label"],
            "confidence": top_k[0]["confidence"],
            "topK": top_k,
        }
        canonical_topk = ",".join(
            f"{t['label']}:{t['confidence']:.4f}" for t in top_k
        )
        prediction_hash = hash_text(
            "|".join(
                [prediction["label"], f"{prediction['confidence']:.4f}", canonical_topk]
            )
        )

    output_hashes = [hash_tensor(z) for z in pre_activations]
    proof_hash = hash_text(
        ":".join(
            [
                task["taskId"],
                task["sampleId"],
                str(segment_start),
                str(len(pre_activations)),
                *output_hashes,
                prediction_hash,
            ]
        )
    )

    now = int(time.time() * 1000)
    submit = client.post(
        f"{api}/captcha/submit",
        json={
            "sessionId": data["sessionId"],
            "taskId": task["taskId"],
            "prediction": prediction,
            "proof": {
                "taskId": task["taskId"],
                "sampleId": task["sampleId"],
                "segmentStart": segment_start,
                "layerCount": len(pre_activations),
                "preActivations": [z.tolist() for z in pre_activations],
                "outputHashes": output_hashes,
                "predictionHash": prediction_hash,
                "proofHash": proof_hash,
                "timestamp": now,
            },
            "timing": {
                "modelLoadMs": 5,
                "inferenceMs": max(compute_ms, 20),
                "totalMs": max(compute_ms, 20) + 30,
                "startedAt": now - 100,
                "completedAt": now,
            },
        },
    )
    submit.raise_for_status()
    result = submit.json()

    # Answer human verification if asked (confirm the model's label)
    if result.get("requiresVerification") and result.get("verification"):
        verification = result["verification"]
        verify = client.post(
            f"{api}/captcha/verify",
            json={
                "sessionId": data["sessionId"],
                "verificationId": verification["verificationId"],
                "response": "confirm",
                "responseTimeMs": 900,
            },
        )
        verify.raise_for_status()
        result["captchaToken"] = verify.json().get("captchaToken")
        result["humanVerified"] = True

    return {
        "difficulty": data["difficulty"],
        "model": task.get("modelName", "?"),
        "segment": [segment_start, segment_start + len(pre_activations)],
        "success": result["success"],
        "token": bool(result.get("captchaToken")),
        "pipeline": result.get("pipeline"),
        "human_verified": result.get("humanVerified", False),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--solves", type=int, default=8)
    parser.add_argument("--api", default="http://localhost:8000/api/v1")
    args = parser.parse_args()

    failures = 0
    completed_runs = 0
    with httpx.Client(timeout=30) as client:
        for i in range(args.solves):
            try:
                outcome = solve_once(client, args.api, i)
            except Exception as exc:
                print(f"solve {i + 1}: ERROR {exc}")
                failures += 1
                continue
            p = outcome["pipeline"] or {}
            status = (
                f"run {p.get('runId', '?')[:8]} layers {p.get('layersDone')}/"
                f"{p.get('totalLayers')}"
            )
            if p.get("completed"):
                completed_runs += 1
                status += f" -> COMPLETED: '{p.get('predictedLabel')}'"
                status += f" ({p.get('contributors')} contributors)"
            if outcome["human_verified"]:
                status += " [human verified]"
            ok = outcome["success"] and outcome["token"]
            if not ok:
                failures += 1
            print(
                f"solve {i + 1}: {'OK ' if ok else 'FAIL'} "
                f"[{outcome['difficulty']}] {outcome['model']} "
                f"segment {outcome['segment']} | {status}"
            )

    print(f"\n{args.solves - failures}/{args.solves} solves OK, "
          f"{completed_runs} pipeline runs completed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
