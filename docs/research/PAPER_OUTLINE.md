# Paper Outline

Patent scope, implementation status, prior-art pressure, and filing priorities
are maintained in [Patent and Invention Strategy](PATENT_DISCLOSURE_DRAFT.md).
This paper outline is not a novelty or freedom-to-operate conclusion.

## Working Title

Verifiable Machine-First CAPTCHA Labeling with Sparse Human Auditing

## Thesis

Traditional CAPTCHAs spend human attention on puzzles or primary annotations,
while hash-based client puzzles spend computation without producing a reusable
result. PoUW CAPTCHA instead meters access with verified browser-executed ML
inference. Successful work produces machine pseudo-labels, and a sparse,
quality-aware subset receives independent human auditing before consensus,
golden promotion, and retraining. The system is computational admission
control: bots may pass if they perform the assigned useful work.

## Claimed Contributions

1. An access-control architecture in which untrusted browser computation
   produces provenance-bearing machine pseudo-labels rather than disposable
   hashes.
2. Latency-aware execution that assigns a complete compact model or consecutive
   verified segments under a bounded visitor-compute budget.
3. A low-cost probabilistic verifier for affine layer operators
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
5. **Selective human auditing and feedback**: completed pseudo-labels are
   sampled using confidence, risk, honeypot, and baseline audit signals;
   model-specific, non-anchoring responses feed duplicate-filtered,
   reputation-weighted consensus and version-safe retraining.
6. An end-to-end evaluation of actual server verification cost, browser UX,
   labeling accuracy, human-work reduction, poisoning resistance, golden-label
   quality, and retraining lift.

### Secondary generality result

**Attention verification**: transformer blocks verify with the same
   primitive composed — Q/K/V/output projections as affine checks, the
   bilinear products S = Q·Kᵀ and O = softmax(S)·V as Freivalds
   matrix-product checks over submitted-and-verified intermediates, with
   softmax/normalization replayed server-side at O(seq²) cost.

**Distributed verified LLM classification (demonstrated)**: a real
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

This result supports generality but is not the paper's central thesis. It may
be shortened to a case study or appendix if its evaluation remains shallower
than the small-model labeling pipeline.

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
- Human-in-the-loop: audit-rate versus label quality, independent-voter
  consensus, honeypot-calibrated reputation, and retraining lift.
- UX: warm/cold browser latency across desktop/mobile devices, accessibility,
  and the additional burden of sampled human audits.
- Economics: actual verifier versus direct-inference wall time, useful labels
  per challenge, human work avoided, and completion/failure rate.
- Ablations: projections only, projections plus audits, varied audit rate,
  uncertainty versus random audit selection, and varied projection count K.

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
