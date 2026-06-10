# PoUW CAPTCHA Evaluation Report

Generated: `2026-06-10T04:29:34.257325+00:00`

## Model

- Name: `mnist-tiny`
- Version: `2.0.1`
- Layers: `3`
- Checksum: `c64988cfa8a084345c2fac4d7be804655287759aaa98c2c5db62bbc239532edc`
- Samples: `30`
- Seed: `42`

## Verification Asymmetry

| Metric | Value |
| --- | ---: |
| Full model client compute ops | 109,184 |
| Full model routine projection verify ops | 4,712 |
| Compute / verify ratio | 23.171x |
| Secret projections per layer | 4 |

## Correctness

| Metric | Value |
| --- | ---: |
| Distributed labels matched direct inference | 30 / 30 |
| Label match rate | 100.00% |
| Honest segment accept rate | 100.00% |

## Attack Checks

| Check | Rejections |
| --- | ---: |
| Tampered segment outputs | 30 / 30 |
| Audit drift checks | 30 / 30 |

## Local Latency

| Metric | Milliseconds |
| --- | ---: |
| Direct full inference mean | 0.1654 |
| Direct full inference p95 | 0.3522 |
| Segment projection verify mean | 0.0999 |
| Segment projection verify p95 | 0.2893 |

## Interpretation

The current dense MNIST model is intentionally small. Even so, routine
projection verification is substantially cheaper than recomputing the full
dense model. The asymmetry should improve for larger dense layers because
client computation scales as `O(n * m)` while projection verification scales as
`O(k * (n + m))`.
