# Core Workflow: Distributed PoUW CAPTCHA

End-to-end description of the production core built around a **real trained
model**, **verifiable computation**, and a **distributed labeling pipeline**.

## 1. The models (plug-and-play, multi-architecture)

Models live in `models/<name>/`:

```
models/mnist-tiny/      # dense MLP  784→128→64→10        (98.09% test acc)
models/mnist-cnn/       # conv net   conv(1→8)→conv(8→16)→400→64→10 (98.46%)
├── manifest.json       # layers, labels, post-ops, REAL SHA-256 checksums
└── weights.npz         # trained float32 weights
```

- Both are trained on real MNIST in pure NumPy (`scripts/train_mnist_numpy.py`
  and `scripts/train_mnist_cnn_numpy.py` — the CNN trains with im2col
  convolution + backprop in ~2 minutes).
- A model is a sequence of **provable affine layers** (`dense`, `conv2d`)
  each followed by a chain of cheap **post-ops** (`relu`, `softmax`,
  `maxpool2d`, `flatten`) that the server replays itself during verification.
- **Checksums are real and layered**: each layer's checksum is SHA-256 over
  the exact float32 bytes a browser receives (dense: weights flattened
  (out, in); conv: (oc, ic, kh, kw)); the model checksum is a hash of the
  layer checksums. A client holding only a *segment* of the model can
  therefore still verify integrity (`crypto.subtle.digest` over the
  `Float32Array` bytes) before executing anything.
- Adding a new dataset/model = dropping a new manifest + weights directory
  into `models/`. The server (`app/ml/model_store.py`) loads and
  integrity-verifies everything at startup; the pipeline rotates new runs
  across all loaded models. No code changes needed for any mix of dense and
  conv2d layers.

## 2. Distributed inference pipeline (the "piecing together")

Each unlabeled sample flows through a **pipeline run** (`pipeline_runs`
table). Solvers compute *segments* of layers, sized by risk tier:

| Risk tier  | Layers per CAPTCHA | Rationale                       |
|------------|--------------------|---------------------------------|
| normal     | 1                  | fastest UX, few hundred ms      |
| suspicious | 2                  | more work for risky traffic     |
| bot_like   | all remaining      | maximum cost for bots           |

The server stores the verified **post-activation** of each completed segment
and hands it to the next solver as their input. When the final layer
completes, the softmax output becomes the sample's machine label — one
inference pieced together from multiple users' partial computations
(`app/core/pipeline.py`). Claims have a 90s TTL so abandoned segments get
reassigned.

## 3. Verifiable computation (verify WITHOUT recomputing)

The crucial mechanism (`app/ml/proof_verifier.py`). The client submits the
**pre-activation vector** of every computed layer plus commitment hashes.
The server verifies three ways, cheapest first:

1. **Commitment hashes** — each vector is hashed (canonical 4-decimal form)
   and bound with the task id, sample id, and segment position into a single
   proof hash. Proofs can't be replayed across tasks or detached from data.

2. **Freivalds-style secret projections** — every provable layer is an
   affine operator `z = L·x + b` (dense matmul OR convolution). The server
   holds K=4 secret random vectors `r` per layer and the precomputed
   `s = Lᵀ·r` (once per model load, never per request — for conv layers `s`
   is the transposed convolution of `r` with the kernels). It checks

   ```
   r · z  ≈  s · x  +  r · b
   ```

   which costs **O(in + out)** multiplications versus the **O(in × out)**
   (dense) or **O(out × k² × in_ch)** (conv) the client had to spend. `r` is
   derived from the server secret key (so workers agree and clients can't
   reconstruct it). A fabricated `z` passes 4 independent secret projections
   with negligible probability. The layer input `x` is always known
   server-side: the sample input at segment 0, or the previous solver's
   verified activation afterward. Post-ops (activation, pooling, flatten)
   are recomputed server-side from submitted pre-activations (O(n), cheap).

3. **Probabilistic spot audits** — ~8% of submissions get a full segment
   recompute, bounding any adaptive attack on the projection checks.

The asymmetry follows a scaling law: it grows with layer width for dense
layers (~27× for 784×128) and with kernel² × channels for convolutions
(1.97× for the 1→8-channel input layer, 10.6× for 8→16, >40× for
production-scale 32→64 layers). Tests in `server/tests/test_proof_verifier.py`
cover honest clients on both architectures (including multi-user piecing and
a real MNIST digit), fabricated outputs, single-value tampering, wrong-input
precompute attacks, replays, hash mismatches, audit catches, and the
asymmetry scaling law.

## 4. Human verification → golden dataset → retraining

- When a pipeline run completes, the solver is sometimes asked to verify the
  pieced-together label (always for bot_like, 50% suspicious, ~20% normal).
- Verified labels accumulate; 3-way consensus (reputation-weighted) promotes
  a label into the **golden dataset** (`app/services/golden_dataset.py`).
- `scripts/retrain_from_golden.py` fine-tunes the model on verified labels
  (mixed with replay data to prevent forgetting), bumps the version, and
  regenerates all checksums. In-flight tasks pin the model checksum at
  assignment, so version rotation is race-free; pipeline runs are isolated
  per model version.

## 5. Quality controls

- **Honeypots**: ~10% of seeded samples keep their true label hidden
  (`known_label`); completed runs are checked against it.
- **Timing plausibility**: submissions faster than 10% of the expected
  compute time are rejected.
- **Server-derived labels are authoritative**: the final label comes from
  the verified final-layer output, not from anything the client claims.

## Running it

```bash
# 1. Train the models (downloads MNIST; MLP ~30s, CNN ~2min)
server/venv/Scripts/python scripts/train_mnist_numpy.py
server/venv/Scripts/python scripts/train_mnist_cnn_numpy.py

# 2. Seed real samples
cd server && venv/Scripts/python ../scripts/seed_data.py --count 200

# 3. Start the server
venv/Scripts/python -m uvicorn app.main:app --port 8000

# 4. Demo at http://localhost:8000/demo, dashboard at /dashboard
#    Pipeline state: GET /api/v1/pipeline/runs
#    Economics/research metrics: GET /api/v1/metrics/economics

# 5. Simulate solvers (watch runs get pieced together across both models)
venv/Scripts/python ../scripts/e2e_client.py --solves 12

# 6. Retrain from human-verified labels
venv/Scripts/python ../scripts/retrain_from_golden.py --min-verifications 1

# 7. Regenerate the evaluation report (docs/evaluation/latest.md)
venv/Scripts/python ../scripts/evaluate_pouw.py --samples 100
```

Measured on this machine: 30 live distributed solves across both models, all
verified; **46/46 completed pipeline-run labels matched the true MNIST
labels** (40 dense + 6 CNN); offline evaluation on 100 real MNIST test images
shows 100% distributed/direct agreement for both architectures and 100%/99%
ground-truth labeling accuracy (dense/CNN). Retraining on human-verified
labels took the dense model 97.53% → 98.09% (v2.0.0 → v2.0.1).
