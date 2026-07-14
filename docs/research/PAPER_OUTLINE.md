# Paper Outline

Patent scope, implementation status, prior-art pressure, and filing priorities
are maintained in [Patent and Invention Strategy](PATENT_DISCLOSURE_DRAFT.md).
This paper outline is not a novelty or freedom-to-operate conclusion.

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
   verified layer segments — architecture-generic, demonstrated on dense
   MLPs, convolutional networks, AND a single-block vision transformer from
   the same plug-and-play model store.
3. A low-cost probabilistic verifier for ANY affine layer operator
   (dense matmul, conv2d, per-token projections) using task-bound
   commitments, secret projections precomputed as `s = Lᵀr`, and spot
   audits. Routine verification is `O(k·(in+out))` per layer independent of
   the operator's compute cost.
4. **Exact verification for quantized models**: int8 models run an
   all-integer pipeline (every value < 2^53, bit-identical between browser
   float64 arithmetic and the server), so Freivalds runs over Z_p
   (p = 2^31−1) with exact equality — zero float tolerance, soundness error
   ~1/p per secret projection (~2^-124 with K=4), no spot audits needed, and
   the entire adaptive-drift attack class (hiding inside the tolerance band)
   is structurally eliminated. Quantization costs ≤0.06pp accuracy.
5. **Attention verification**: transformer blocks verify with the same
   primitive composed — Q/K/V/output projections as affine checks, the
   bilinear products S = Q·Kᵀ and O = softmax(S)·V as Freivalds
   matrix-product checks over submitted-and-verified intermediates, with
   softmax/normalization replayed server-side at O(seq²) cost.
5b. **Distributed verified LLM inference (demonstrated)**: a real
   Qwen2.5-0.5B-Instruct source graph of 49 operators expands into 433 runtime
   microstages (two GQA head-group parts, sixteen SwiGLU FFN-axis parts per
   block, and a candidate head). The server retains the source activation and
   verified output-projection accumulator until each residual is complete.
   The live zero-shot labeling run accepted 431/431 assignments with p50 134
   ms, p95 165 ms, and maximum 223 ms on the tested machine. The prototype
   demonstrates an LLM forward pass distributed across mutually-untrusted
   anonymous sessions with per-assignment algebraic verification; any claim
   that it is the first such system requires a formal prior-art review and
   should not be made before that review.
6. A useful-value pipeline that turns completed runs and selective human
   checks into golden labels and periodic retraining (the model improves from
   the human feedback it harvests: 97.53% → 98.09% measured on mnist-tiny).
7. An evaluation of compute asymmetry across layer types, end-to-end
   distributed labeling accuracy against ground truth, tamper rejection
   (including exact off-by-one detection), and operational economics.

## Threat Model

- Bots are allowed to pass if they perform the assigned work.
- The objective is not perfect bot exclusion.
- The objective is to raise marginal automated request cost and capture useful
  compute/label value from that cost.
- Browser code is untrusted; server-side verification is authoritative.

## Verification Primitive (core claim)

Every provable layer is an affine operator `z = L·x + b`. The server holds an
eight-vector secret basis with `s_j = Lᵀr_j` precomputed once per model
version (for conv layers, `s_j` is the transposed convolution of `r_j` with
the kernels). Each assignment's task id, nonce, and the server secret
HMAC-derive K=4 hidden linear combinations `(r,s)` from that basis. A submitted
pre-activation `z` is accepted iff

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

Latest local evaluation, 100 real MNIST test images, five models:

| | mnist-tiny | mnist-tiny-q8 | mnist-cnn | mnist-cnn-q8 | mnist-attn |
| --- | ---: | ---: | ---: | ---: | ---: |
| Architecture | 3 dense | 3 dense int8 | 2 conv + 2 dense | int8 | ViT (token embed + attention + dense) |
| Model test accuracy | 98.09% | 98.07% | 98.46% | 98.40% | 94.72% |
| Verification | float, rtol 1e-3 | **exact mod-p** | float | **exact mod-p** | float + product checks |
| Compute/verify asymmetry | 23.2x | 23.2x | 5.3x | 5.3x | 8.1x |
| Distributed = direct label | 100% | 100% | 100% | 100% | 100% |
| Ground-truth labeling accuracy | 100% | 100% | 99% | 99% | 97% |
| Tamper rejection | 100% | 100% (exact, incl. ±1) | 100% | 100% | 100% (all six blocks + skipped-softmax) |

Live end-to-end (browser-protocol client against the running server): 36/36
solves verified across all five architectures in one mixed session; 65/65
completed pipeline-run labels matched MNIST ground truth cumulatively; runs
pieced from up to 4 independent contributors.

Notes for honest reporting:
- CNN asymmetry (5.3x) is dominated by the 1→8-channel input layer (1.97x),
  the structural worst case; the 8→16 conv layer reaches 10.6x and a
  production-scale 32→64 conv layer exceeds 40x
  (`test_conv_asymmetry_scales_with_channels`). It is a scaling law, not a
  flat number.
- Quantized models eliminate the float-tolerance attack surface entirely:
  fractional perturbations are rejected structurally and ±1 integer tampering
  fails the exact mod-p equality.
- The attention model is a deliberately minimal single-block ViT (94.72%);
  its purpose is demonstrating the verification protocol, not SOTA accuracy.

These are prototype-scale numbers, not final paper-scale measurements.
