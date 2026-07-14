# PoUW CAPTCHA Evaluation Report

Generated: `2026-07-02T05:29:04.270588+00:00`
Samples: `100` (mnist_test_set), seed `42`

## Model Comparison

| Model | Layers | Test acc | Compute ops | Verify ops | Asymmetry | Distributed = direct | Ground-truth acc | Tamper rejected |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `mnist-attn` | 3 (token_dense+attention+dense) | 0.9472 | 210,144 | 25,896 | 8.115x | 100.00% | 97.00% | 100.00% |
| `mnist-cnn` | 4 (conv2d+dense) | 0.9846 | 214,304 | 40,072 | 5.348x | 100.00% | 99.00% | 100.00% |
| `mnist-cnn-q8` | 4 (conv2d+dense) | 0.984 | 214,304 | 40,072 | 5.348x | 100.00% | 99.00% | 100.00% |
| `mnist-tiny` | 3 (dense) | 0.9809 | 109,184 | 4,712 | 23.171x | 100.00% | 100.00% | 100.00% |
| `mnist-tiny-q8` | 3 (dense) | 0.9807 | 109,184 | 4,712 | 23.171x | 100.00% | 100.00% | 100.00% |

## mnist-attn v1.0.0

- Checksum: `54b2dc15380ad132446f0fe048c7861e305827a5cbbf218d2b5201a589c3e5ca`
- Layer types: token_dense, attention, dense

### Per-segment asymmetry

| Segment | Type | Client compute ops | Projection verify ops | Ratio |
| --- | --- | ---: | ---: | ---: |
| [0, 1] | token_dense | 37,632 | 6,208 | 6.062x |
| [1, 2] | attention | 172,032 | 19,456 | 8.842x |
| [2, 3] | dense | 480 | 232 | 2.069x |

### Correctness and attacks

| Metric | Value |
| --- | ---: |
| Distributed labels matched direct inference | 100 / 100 |
| Honest segment accept rate | 100.00% |
| Distributed labeling accuracy vs MNIST ground truth | 97.00% |
| Tampered segment outputs rejected | 100 / 100 |
| Audit drift rejected | 100 / 100 |
| Segment projection verify mean / p95 (ms) | 0.5677 / 1.4148 |
| Direct full inference mean (ms) | 0.1205 |

## mnist-cnn v1.0.0

- Checksum: `b76341374c39145d41ba99f80836eb2fb4888414d4eac5ce40dd042651a1ba83`
- Layer types: conv2d, conv2d, dense, dense

### Per-segment asymmetry

| Segment | Type | Client compute ops | Projection verify ops | Ratio |
| --- | --- | ---: | ---: | ---: |
| [0, 1] | conv2d | 48,672 | 24,768 | 1.965x |
| [1, 2] | conv2d | 139,392 | 13,152 | 10.599x |
| [2, 3] | dense | 25,600 | 1,856 | 13.793x |
| [3, 4] | dense | 640 | 296 | 2.162x |

### Correctness and attacks

| Metric | Value |
| --- | ---: |
| Distributed labels matched direct inference | 100 / 100 |
| Honest segment accept rate | 100.00% |
| Distributed labeling accuracy vs MNIST ground truth | 99.00% |
| Tampered segment outputs rejected | 100 / 100 |
| Audit drift rejected | 100 / 100 |
| Segment projection verify mean / p95 (ms) | 0.614 / 1.5681 |
| Direct full inference mean (ms) | 0.4736 |

## mnist-cnn-q8 v1.0.0

- Checksum: `0d568d38ff3f491263c7a95a0569bc281bef13cf56c08ed96284601ed783a098`
- Layer types: conv2d, conv2d, dense, dense

### Per-segment asymmetry

| Segment | Type | Client compute ops | Projection verify ops | Ratio |
| --- | --- | ---: | ---: | ---: |
| [0, 1] | conv2d | 48,672 | 24,768 | 1.965x |
| [1, 2] | conv2d | 139,392 | 13,152 | 10.599x |
| [2, 3] | dense | 25,600 | 1,856 | 13.793x |
| [3, 4] | dense | 640 | 296 | 2.162x |

### Correctness and attacks

| Metric | Value |
| --- | ---: |
| Distributed labels matched direct inference | 100 / 100 |
| Honest segment accept rate | 100.00% |
| Distributed labeling accuracy vs MNIST ground truth | 99.00% |
| Tampered segment outputs rejected | 100 / 100 |
| Audit drift rejected | 100 / 100 |
| Segment projection verify mean / p95 (ms) | 4.6334 / 12.0783 |
| Direct full inference mean (ms) | 1.432 |

## mnist-tiny v2.0.1

- Checksum: `c64988cfa8a084345c2fac4d7be804655287759aaa98c2c5db62bbc239532edc`
- Layer types: dense, dense, dense

### Per-segment asymmetry

| Segment | Type | Client compute ops | Projection verify ops | Ratio |
| --- | --- | ---: | ---: | ---: |
| [0, 1] | dense | 100,352 | 3,648 | 27.509x |
| [1, 2] | dense | 8,192 | 768 | 10.667x |
| [2, 3] | dense | 640 | 296 | 2.162x |

### Correctness and attacks

| Metric | Value |
| --- | ---: |
| Distributed labels matched direct inference | 100 / 100 |
| Honest segment accept rate | 100.00% |
| Distributed labeling accuracy vs MNIST ground truth | 100.00% |
| Tampered segment outputs rejected | 100 / 100 |
| Audit drift rejected | 100 / 100 |
| Segment projection verify mean / p95 (ms) | 0.1242 / 0.2488 |
| Direct full inference mean (ms) | 0.1963 |

## mnist-tiny-q8 v2.0.1

- Checksum: `67594c284779315ad5b6ff2d9190f013cc3b19ce782a9349c0f98876949beef4`
- Layer types: dense, dense, dense

### Per-segment asymmetry

| Segment | Type | Client compute ops | Projection verify ops | Ratio |
| --- | --- | ---: | ---: | ---: |
| [0, 1] | dense | 100,352 | 3,648 | 27.509x |
| [1, 2] | dense | 8,192 | 768 | 10.667x |
| [2, 3] | dense | 640 | 296 | 2.162x |

### Correctness and attacks

| Metric | Value |
| --- | ---: |
| Distributed labels matched direct inference | 100 / 100 |
| Honest segment accept rate | 100.00% |
| Distributed labeling accuracy vs MNIST ground truth | 100.00% |
| Tampered segment outputs rejected | 100 / 100 |
| Audit drift rejected | 100 / 100 |
| Segment projection verify mean / p95 (ms) | 0.6424 / 1.3253 |
| Direct full inference mean (ms) | 0.5294 |

## Interpretation

The operation tables count the K final projection identities and exclude HMAC
derivation and task-challenge basis mixing. With the current wider basis those
additions remain linear in vector size but must be included in production
wall-clock and throughput benchmarks. The projection identity cost is
`O(k·(in + out))` per layer regardless of
layer type, while client compute is `O(in × out)` for dense layers and
`O(out × k² × in_ch)` for convolutions. The asymmetry therefore grows
with layer width (dense) and with kernel size × channel count (conv).
Small input convolutions (1→8 channels) are the worst case for the
verifier — their outputs are large relative to the work performed — 
while production-scale conv layers (32→64 channels and up) exceed 40x.

**Exact verification (`-q8` models):** int8-quantized models run an
all-integer pipeline (every value < 2^53, bit-identical between
browsers and the server), so projection checks run over Z_p
(p = 2^31−1) with EXACT equality — no float tolerance and no spot
audits needed. Four task-derived checks are formed from a hidden
eight-vector field basis. A ±1 tamper is caught with overwhelming
probability; a formal adaptive soundness bound remains future work.

**Attention (`mnist-attn`):** transformer blocks verify with the same
machinery — Q/K/V/output projections as affine checks, the bilinear
products S = Q·Kᵀ and O = softmax(S)·V as Freivalds matrix-product
checks over the submitted (already-verified) intermediates, softmax
replayed server-side. This is the verification path that scales to
LLM-style distributed inference.
