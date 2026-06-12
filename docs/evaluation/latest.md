# PoUW CAPTCHA Evaluation Report

Generated: `2026-06-12T13:39:26.886936+00:00`
Samples: `100` (mnist_test_set), seed `42`

## Model Comparison

| Model | Layers | Test acc | Compute ops | Verify ops | Asymmetry | Distributed = direct | Ground-truth acc | Tamper rejected |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `mnist-cnn` | 4 (conv2d+dense) | 0.9846 | 214,304 | 40,072 | 5.348x | 100.00% | 99.00% | 100.00% |
| `mnist-tiny` | 3 (dense) | 0.9809 | 109,184 | 4,712 | 23.171x | 100.00% | 100.00% | 100.00% |

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
| Segment projection verify mean / p95 (ms) | 0.6107 / 1.6242 |
| Direct full inference mean (ms) | 0.4912 |

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
| Segment projection verify mean / p95 (ms) | 0.0572 / 0.1151 |
| Direct full inference mean (ms) | 0.0985 |

## Interpretation

Routine verification cost is `O(k·(in + out))` per layer regardless of
layer type, while client compute is `O(in × out)` for dense layers and
`O(out × k² × in_ch)` for convolutions. The asymmetry therefore grows
with layer width (dense) and with kernel size × channel count (conv).
Small input convolutions (1→8 channels) are the worst case for the
verifier — their outputs are large relative to the work performed — 
while production-scale conv layers (32→64 channels and up) exceed 40x.
The same projection identity `r·z = (Lᵀr)·x + r·b` covers any affine
operator, so attention projections and other matmul-shaped layers
verify identically.
