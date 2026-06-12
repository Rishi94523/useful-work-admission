# Paper Outline

## Working Title

Verifiable Useful-Work Rate Limiting for the Open Web

## Thesis

Traditional CAPTCHAs attempt to distinguish humans from bots with puzzle
solving, but modern AI agents increasingly bypass those puzzles. PoUW CAPTCHA
instead meters automated access by requiring browser-executed useful ML work,
then converts successful work into distributed inference and human-verified
label signals — mirroring the human-in-the-loop labeling pipelines that
commercial data-labeling vendors (ScaleAI-style) run at large scale, but
sourced from CAPTCHA traffic.

## Claimed Contributions

1. A proof-of-useful-work CAPTCHA/rate-limit architecture for browser clients.
2. Distributed model inference where multiple sessions contribute consecutive
   verified layer segments — architecture-generic, demonstrated on dense MLPs
   and convolutional networks from the same plug-and-play model store.
3. A low-cost probabilistic verifier for ANY affine layer operator
   (dense matmul, conv2d; attention projections by extension) using
   task-bound commitments, secret projections precomputed as `s = Lᵀr`,
   and spot audits. Routine verification is `O(k·(in+out))` per layer
   independent of the operator's compute cost.
4. A useful-value pipeline that turns completed runs and selective human
   checks into golden labels and periodic retraining (the model improves from
   the human feedback it harvests: 97.53% → 98.09% measured on mnist-tiny).
5. An evaluation of compute asymmetry across layer types, end-to-end
   distributed labeling accuracy against ground truth, tamper rejection, and
   operational economics.

## Threat Model

- Bots are allowed to pass if they perform the assigned work.
- The objective is not perfect bot exclusion.
- The objective is to raise marginal automated request cost and capture useful
  compute/label value from that cost.
- Browser code is untrusted; server-side verification is authoritative.

## Verification Primitive (core claim)

Every provable layer is an affine operator `z = L·x + b`. The server holds K
secret random vectors `r` per layer with `s = Lᵀr` precomputed once per model
version (for conv layers, `s` is the transposed convolution of `r` with the
kernels). A submitted pre-activation `z` is accepted iff

    r · z  ≈  s · x  +  r · b      (for all K projections)

Costs O(in + out) per check; the client paid O(in × out) (dense) or
O(out × k² × in_ch) (conv). Nonlinearities (relu, softmax) and structural ops
(maxpool, flatten) are cheap O(n) "post-ops" the server replays itself, so the
chain of custody between provable layers never leaves the server.

## Evaluation Plan

- Verification asymmetry: client compute ops vs server projection ops, per
  layer type; show the asymmetry law (grows with width / kernel²·channels,
  worst case = small-channel input convolutions).
- Correctness: distributed segmented labels vs direct full-model inference,
  AND vs ground truth (true labeling accuracy of the pipeline).
- Attack checks: fabricated outputs, tampering at random layers, wrong input,
  replay, audit drift.
- Human-in-the-loop: golden-label consensus, retraining lift across versions.
- UX: browser latency across desktop/mobile devices.
- Economics: estimated compute imposed, labels produced, completion/failure rate.
- Ablations: projections only, projections plus audits, varied audit rate,
  varied projection count K.

## Current Evidence

See `docs/evaluation/latest.md` (regenerate with `scripts/evaluate_pouw.py`).

Latest local evaluation, 100 real MNIST test images, both models:

| | mnist-tiny (3 dense) | mnist-cnn (2 conv + 2 dense) |
| --- | ---: | ---: |
| Model test accuracy | 98.09% | 98.46% |
| Compute/verify asymmetry | 23.2x | 5.3x |
| Distributed = direct label | 100% | 100% |
| Distributed labeling accuracy vs ground truth | 100% | 99% |
| Tamper rejection | 100% | 100% |
| Audit drift rejection | 100% | 100% |

Live end-to-end (browser-protocol client against the running server): 30/30
solves verified across both architectures; 46/46 completed pipeline-run labels
matched MNIST ground truth; runs pieced from up to 4 independent contributors.

Note on the CNN asymmetry: 5.3x is dominated by the 1→8-channel input layer
(ratio 1.97x), the structural worst case. The deeper 8→16 conv layer reaches
10.6x and a production-scale 32→64 conv layer exceeds 40x (see
`test_conv_asymmetry_scales_with_channels`). Report this honestly as a
scaling law rather than a flat number.

These are prototype-scale numbers, not final paper-scale measurements.
