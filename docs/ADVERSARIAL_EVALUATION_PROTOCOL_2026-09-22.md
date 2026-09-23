# Adversarial evaluation protocol — 22 September 2026

Declared before any attack in this protocol has been implemented or run, and
before the matched campaign has completed. Thresholds stated here are not to be
revised after seeing outcomes; a revision must be recorded as a dated amendment
with its reason, and the original preserved.

## Why this protocol exists

Existing admission experiments exercise the real scheduler but supply molecular
verdicts from a model. `scripts/test_whole_run_retry_attack.py` states this in
its own docstring: *"Molecular replay outcomes are supplied by the model here,
not recomputed in this experiment."* Retry economics, exposure caps and audit
sampling have therefore been measured against assumed correctness rather than
against real docking output.

For a security claim this is the wrong side of the line. This protocol replaces
modelled verdicts with real molecular replay throughout, and adds the baseline
comparison the claim needs.

## The claim under test

Puzzle-based admission works because verification is O(1) and the work is
provably fresh. Substituting genuinely useful computation destroys both
properties: verification requires replay, and results can be precomputed or
cached. The system under test attempts to restore both through exact task
decomposition and post-commit challenge.

This evaluation measures how far that succeeds, at what verification cost, and
where it fails. A negative result is a valid outcome and will be reported.

## Honest-submission corpus

Attacks are evaluated against real molecular output, not synthetic records.

The corpus is the set of matched-campaign jobs whose key `(target, id, seed)`
satisfies `sha256("adversarial-corpus-2026-09-22:" + "target/id/seed")` having
its first four hex digits below 5% of 65536. The rule was fixed on 22 September
2026 at 11:40, before any attack was designed, so the corpus cannot be steered
by outcomes.

Jobs completed before that time had already had their task directories reclaimed
and are not recoverable; the corpus is therefore drawn from jobs completing
after it. Expected size is approximately 28 jobs, comprising roughly 900 normal
units and 4,000 medium units across all five targets and three seeds. Each
retained unit carries its raw minima pool, its per-step trace and its metrics.

## Threat model

Identities are cheap to create. The attacker sees the public protocol, can
submit arbitrary bytes, can retain anything it has previously computed, and can
coordinate across identities. It cannot forge server-side commitments or read
server secrets. Trust grants and replay verdicts come from trusted services, not
from client-supplied flags.

Attackers evaluated:

| Label | Behaviour |
| --- | --- |
| A1 zero-work | Submits a fabricated result without computing |
| A2 partial-work | Terminates search early and submits the truncated pool |
| A3 cached replay | Resubmits a result it computed for the same unit earlier |
| A4 retry grinding | Requests many units, abandons costly ones, completes cheap ones |
| A5 identity reset | Discards an identity on penalty and returns fresh |
| A6 disappearing worker | Accepts a unit and never returns |
| A7 collusion | Several identities share one computed result |
| A8 subtle corruption | Submits a scientifically plausible but wrong pose, small perturbation of a valid one |

A8 is the one that distinguishes useful work from puzzles: a wrong-but-plausible
scientific result is cheap to produce and cannot be rejected by a cheap
structural check. It is the attack most likely to succeed and must be reported
whether or not it does.

## Metrics

For every attacker, under audit probability `q` in {0.02, 0.05, 0.1, 0.25, 1.0}
and retry cap `N` in {1, 4, 16}:

- **Attacker cost per successful admission**, expressed in honest client units,
  including work discarded on abandoned or rejected attempts.
- **Probability of undetected admission**, measured over repeated trials, and
  compared against the analytic model.
- **Verifier cost per admission**: CPU seconds and bytes handled, including
  payload ingestion, not only replay kernel time.
- **Scientific damage**: the fraction of corrupted results entering the campaign
  and surviving to aggregation, and the ranking effect on the affected target.

## Baseline

A hashcash-style puzzle calibrated to the same median client wall time on the
same device, measured rather than assumed. The comparison reports, for both
systems under identical accounting: client cost, verifier cost, attacker cost
per admission, freshness guarantee and utility produced.

The expected outcome is that the puzzle wins on verifier cost and on freshness,
because those are exactly the properties useful work sacrifices. That result
will be reported plainly. The purpose of this paper is to quantify the price of
utility, not to argue it is free.

## Predeclared expectations

Stated now so that agreement or disagreement is informative:

- **E1.** A1 and A2 are detected whenever audited, because replay is exact.
  Undetected admission probability should track `(1-q)^k` for `k` audited
  opportunities, within sampling error.
- **E2.** A3 is not prevented by replay, since a cached result is genuinely
  correct. It is bounded only by one-use credit accounting. Attacker cost per
  admission under A3 and A4 combined is expected to fall below 2 honest units at
  `N=4, q=0.1`, consistent with the earlier figure of about 1.73.
- **E3.** A5 defeats per-identity exposure caps outright. No threshold is set;
  the measurement is the result.
- **E4.** Verifier cost per admission is expected to exceed 5% of client cost
  once payload handling is included, and therefore to compare unfavourably with
  the puzzle baseline. This is a predicted loss, recorded in advance.
- **E5.** A8 is exploratory. No prediction is made about the perturbation
  magnitude that survives audit, because no such measurement exists yet.

E4 and E2 are predictions of unfavourable results. They are recorded here so
that reporting them later cannot be read as post-hoc framing.

## What would falsify the approach

If attacker cost per successful admission does not exceed the puzzle baseline's
cost at equal client burden, while verification costs substantially more, then
useful-work admission is strictly worse than a puzzle on security grounds and
the paper must say so. The remaining contribution would then be the measurement
itself and the scientific output, not a security improvement.

## Execution constraints

Attacks run after the matched campaign completes, to avoid CPU contention that
would distort timing measurements. Client-side costs are measured on the same
physical devices used for earlier delivery measurements, and device identity is
recorded with every timing.

Every run writes a frozen execution manifest recording protocol, corpus, build
and runner hashes, in the same form as the campaign. Failures are preserved.

## Amendment 1 — phase 1 operationalization, 23 September 2026

Recorded before phase 1 was run. It narrows attackers already defined above into
concrete procedures and adds predictions; no threshold above is changed.

**Verifier soundness, established first.** Units at indices 0, 5, 82 and 164 of
a 165-unit job were replayed with the frozen driver and reproduced both the
minima pool and the per-step trace byte for byte. Replay of one unit is a
re-execution of that unit, so auditing a unit costs one unit by construction.

**Sampling.** Three units per preserved corpus job, chosen by salted SHA-256
order under `adversarial-units-2026-09-23:`. Timing runs at four concurrent
workers so client and verifier costs share load conditions; campaign timings,
taken under 14-way contention, are not used as client costs.

**Operational definitions.**

- A1 substitution: a valid result computed for a different unit of the same
  job is submitted as this unit's result.
- A2 partial work: the unit is genuinely searched at 64k and 128k evaluations
  instead of 256k and submitted. Judged twice, once when the client commits only
  to the minima pool and once when it commits to pool and trace, because the
  trace is 5x the size of the pool and whether clients must upload it is a real
  design choice.
- A3 cached: the true result resubmitted.
- A8e energy falsification: the best minimum of one unit is given an energy
  improved by 0.1, 1.0 or 3.0 kcal/mol, coordinates untouched, and the
  original finalizer is run over the tampered pool.
- A8c translation: the best minimum of one unit is translated by 0.1, 0.5 or
  2.0 A along x, and the original finalizer is run over the tampered pool.

**Predictions.**

- P1. Honest units are accepted in every case.
- P2. A1 is rejected in every case.
- P3. A2 is always rejected under pool-and-trace commitment. Under pool-only
  commitment a small nonzero acceptance rate is possible, for units whose
  retained minima stop changing before the reduced budget is exhausted. The
  rate is not predicted; it is the measurement.
- P4. A3 is accepted in every case, by design.
- P5. A8e does not improve the final reported score, because the finalizer
  re-refines poses and recomputes energies from coordinates. This is uncertain:
  a falsified energy could alter which minima survive merging and clustering.
- P6. A8c never produces a better final score than the honest run. With about
  140 independent units per state, the true best minimum is usually held by
  another unit, so a single corrupted unit is expected to be absorbed.

P5 and P6, if they hold, mean that energy falsification and single-unit
corruption of the unaudited kind are neutralized by the aggregation itself, a
property puzzle-based admission has no analogue for. If either fails, the
failure is reported with its magnitude.
