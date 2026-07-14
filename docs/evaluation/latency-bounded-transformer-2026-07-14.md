# Latency-Bounded Transformer Validation

Date: 2026-07-14

This report records the local production-widget validation of the Qwen2.5-0.5B
sentiment pipeline after vertical attention and MLP microsharding. It is an
engineering measurement, not a mobile-browser guarantee or a throughput claim.

## Configuration

- Source graph: 24 Qwen decoder blocks (GQA + SwiGLU) and one candidate-logits
  head, 49 source operators.
- Runtime graph: two GQA head-group parts and sixteen SwiGLU FFN-axis parts per
  decoder block, plus the head, 433 stages.
- Custody state between partials: `[source_hidden | verified_partial_sum]`.
- Assignment budgets: normal 200 ms, suspicious 250 ms, bot-like 280 ms.
- Large-model fallback: if any indivisible stage is predicted above 300 ms for
  the client calibration, the server assigns an auto-served small model.
- Client: production TypeScript widget engine, CPU loops under `vite-node` on
  the local development machine.
- Server: local FastAPI/SQLite development server with proof verification.

## Failed configurations retained as evidence

- Unsplit GQA: one measured assignment reached 322 ms.
- Eight-way SwiGLU split: seven measured parts were 103-292 ms, but one tail
  assignment reached 372 ms.

Those results caused the move to two-way GQA and sixteen-way SwiGLU; they are
not presented as passing configurations.

## Passing full run

- Run ID: `64bb9b6a-1505-4436-a74e-4af29cd3b8a0`
- Assignments accepted: 431/431.
- Runtime stages covered: 433/433.
- Final label: `positive`.
- Confidence: `0.9746583143462941`.
- Aggregate widget work: approximately 58.3 seconds.
- Contributors: 431 API sessions in one local runner process, not 431 physical
  devices.

| Assignment inference timing | Result |
| --- | ---: |
| Minimum | 53 ms |
| p50 | 134 ms |
| p95 | 165 ms |
| p99 | 181 ms |
| Maximum | 223 ms |

The timing distribution was calculated from the server's 431 accepted
inference-log records for the run. Two assignments packed a second adjacent
stage, which is why 431 assignments cover 433 stages.

## Small-model behavior

The scheduler does not add dummy loops to reach the budget. It packs all
remaining useful layers when the complete model fits:

| Model | Stages assigned | Widget time |
| --- | ---: | ---: |
| `mnist-tiny` | 3/3 | 8 ms |
| `mnist-tiny-q8` | 3/3 | 9 ms |
| `mnist-cnn` | 4/4 | 20 ms |
| `mnist-cnn-q8` | 4/4 | 16 ms |
| `mnist-attn` | 3/3 | 11 ms |

## What this proves and does not prove

The run proves that the implemented widget/server protocol can verify,
aggregate, hand off, and complete every partial on this local machine while
keeping recorded assignment inference below 300 ms. It does not prove a hard
bound on slower phones, cached-weight delivery, WebGPU performance, wide-area
latency, 30 tokens/s, or 30 completed inferences/s.
