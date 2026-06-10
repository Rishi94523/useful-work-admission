# Paper Outline

## Working Title

Verifiable Useful-Work Rate Limiting for the Open Web

## Thesis

Traditional CAPTCHAs attempt to distinguish humans from bots with puzzle
solving, but modern AI agents increasingly bypass those puzzles. PoUW CAPTCHA
instead meters automated access by requiring browser-executed useful ML work,
then converts successful work into distributed inference and human-verified
label signals.

## Claimed Contributions

1. A proof-of-useful-work CAPTCHA/rate-limit architecture for browser clients.
2. Distributed dense-model inference where multiple sessions contribute
   consecutive verified layer segments.
3. A low-cost probabilistic verifier using task-bound commitments, secret
   projections, and spot audits.
4. A useful-value pipeline that turns completed runs and selective human checks
   into golden labels.
5. An evaluation of compute asymmetry, correctness, tamper rejection, and
   operational economics.

## Threat Model

- Bots are allowed to pass if they perform the assigned work.
- The objective is not perfect bot exclusion.
- The objective is to raise marginal automated request cost and capture useful
  compute/label value from that cost.
- Browser code is untrusted; server-side verification is authoritative.

## Evaluation Plan

- Verification asymmetry: client dense ops vs server projection ops.
- Correctness: distributed segmented labels vs direct full-model inference.
- Attack checks: fabricated outputs, tampering, wrong input, replay, audit drift.
- UX: browser latency across desktop/mobile devices.
- Economics: estimated compute imposed, labels produced, completion/failure rate.
- Ablations: projections only, projections plus audits, varied audit rate.

## Current Evidence

See `docs/evaluation/latest.md`.

Current `mnist-tiny` local evaluation reports:

- `23.171x` routine compute/verify asymmetry.
- `100%` distributed/direct label agreement over the latest local sample run.
- `100%` tamper rejection in the latest local sample run.
- `100%` audit drift rejection in the latest local sample run.

These are prototype-scale numbers, not final paper-scale measurements.
