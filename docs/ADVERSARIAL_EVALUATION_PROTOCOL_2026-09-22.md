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

## Amendment 2 — phase 2 admission economics, 23 September 2026

Recorded after phase 1 and before phase 2 was run or smoke-tested.

**Method.** Attackers drive the committed `PoolAdmission` scheduler under a
simulated clock. Audit verdicts are resampled from phase-1 replay records for
the kind of payload audited, not assumed. Headline metric: the attacker
discount factor, honest-unit work per successful admission divided by an honest
client's work per admission in the same tier. A hashcash puzzle has a factor of
1.0 by construction.

**Mapping to the grid above.** The scheduler has two tiers. The trusted tier
leases one unit and audits it with probability `p`; the protocol's `q` grid
{0.02, 0.05, 0.1, 0.25} is applied there. The bundle tier, used for any identity
without a trust grant, leases four units and always replays `q` of them; draws
of 1, 2 and 4 are evaluated. The deployed attempt cap per task is 3, not 4, so
the retry grid is realised as {1, 3, 16}; caps other than 3 and seed
invalidation run through a test-only subclass and are reported as
counterfactuals. E2's reference figure of about 1.73 corresponds to the bundle
tier with one draw.

**Structural facts the predictions rest on.** `commit()` reveals whether and
which units will be replayed before any output is uploaded. A computed result
remains valid if its task is leased again after expiry. Fresh identities are
free and always receive the bundle tier.

**Predictions (discount factor unless stated).**

- Q1. Deployed bundle tier, one draw, attacker computes k of 4 and abandons
  when a fabricated unit is drawn: k=1 about 0.43 (E2's 1.73 units per
  admission), k=2 about 0.57, k=3 about 0.76, k=4 exactly 1.0, k=0 never
  admitted. Each k=1 admission leaves three unreplayed fabricated units in
  provisional storage.
- Q2. Always submitting instead of abandoning gives the same factor, because a
  rejected identity costs nothing to replace.
- Q3. Seed invalidation after a failed or abandoned attempt, or an attempt cap
  of 1, restores a factor of 1.0 for every k. A cap of 16 lowers k=1 to about
  0.25.
- Q4. Two draws: k=2 about 1.19, k=3 about 0.86. Four draws: 1.0 at a verifier
  cost of all four units.
- Q5. Reduced-budget units under pool-only commitment: about 0.51 at 64k and
  0.60 at 128k evaluations. Under pool-and-trace commitment: never admitted.
- Q6. Trusted tier, fabricated units, trust granted after G honest admitted
  bundles (an assumed trusted-service policy; the scheduler leaves grants to an
  external service). Immediate policy with abandonment on selection: the
  attacker is never quarantined, factor about 0.5 at G=1 and p=0.1, and every
  admission retains one unreplayed fabricated unit. Deferred policy: first
  selection is detected after access is consumed, expected admissions per
  identity about (1-(1-p)^10)/p, factor about 4G p/(1-(1-p)^10), below 1.0 at
  G=1 for p up to 0.1.
- Q7. Cheap trust acquisition by the Q1 attack is exploratory: abandonments
  raise the identity's risk score, which may disqualify it from the trusted
  tier. No number is predicted.
- Q8. Disappearing workers holding leases without returning refuse honest
  arrivals at roughly D/16 for D holders, at zero attacker work.

**Falsification.** If any deployed configuration has a factor below 1.0, then
as deployed, cheating in that configuration is cheaper than honest work, which a
puzzle does not permit, and the paper must say so. Q1 and Q6 predict exactly
that. The evaluation then measures which of the counterfactual controls in Q3
and Q4 restore a factor of 1.0, and at what verifier cost.

## Amendment 3 — reseed on retry, 23 September 2026

Recorded before the change was implemented.

**Change.** When the scheduler re-issues a unit that previously expired or
failed an audit, it assigns a fresh child seed drawn by the server from a range
reserved for reseeding, records the old and new seed, and issues the unit with
the new specification. Registration rejects seeds in the reserved range, so a
reseeded seed cannot collide with a registered one. Units never previously
issued keep their registered seed. This is the only behavioural change.

The harness now treats an attacker's cached result as valid only for the same
task and seed, which is the true condition; behaviour on a scheduler that never
reseeds is unchanged.

**Predictions for the deployed bundle tier, one draw, rerun on the modified
scheduler.**

- R1. Attacker computing 1, 2 or 3 of 4 units: factor between 0.95 and 1.10,
  from 0.46, 0.57 and 0.76.
- R2. Honest client: exactly 1.0. Replayed units per admission unchanged at 1.
- R3. Fabricated units retained per admission unchanged at 3, 2 and 1.
  Reseeding fixes what cheating costs, not what an admitted cheat leaves behind.
- R4. Reduced-budget units under pool-only commitment rise above 1.0: about 1.25
  at 64k evaluations and 1.10 at 128k, because each attempt must be recomputed.
- R5. Existing scheduler tests pass unchanged, and new tests show a re-issued
  unit carries a new recorded seed, reseeds are unique, and registration rejects
  the reserved range.

## Amendment 4 — no audit reveal before upload, 23 September 2026

Recorded before the change was implemented.

**Change.** In the pool admission path, `commit()` returns only the challenge
identifier. Whether a replay is required, which units are drawn and whether the
policy is deferred are no longer disclosed before upload. A client learns only
the outcome of `submit()`: granted, or pending a replay of outputs the server
already holds. The trusted verifier reads the drawn units through a separate
server-side accessor. The draw is still made at commit and stored, so the
commitment binds outputs before selection exactly as before; it is only no
longer disclosed. The whole-run audit path, which opens only sampled runs and
therefore needs the challenge before upload, is unchanged.

**Why.** The pool path already requires every output at upload, so the early
reveal no longer saved bandwidth; its only remaining effect was letting a
selected client abandon instead of being audited.

**Predictions.**

- S1. Trusted tier, immediate policy, trust after one honest bundle: an attacker
  submitting fabricated units can no longer abandon on selection, so the first
  selection rejects it and quarantines the identity. Identities are now caught.
  Expected admissions per identity about (1-p)(1-(1-p)^10)/p, giving a factor of
  about 0.68 at p = 0.1, up from 0.60 but still below 1.0. Removing the reveal
  alone does not fix the trusted tier.
- S2. With trust after three honest bundles, the factor is at least 1.0 at every
  audit rate tested, as already measured with the reveal present.
- S3. Deferred policy is unchanged, since it never used the reveal to abandon.
- S4. Bundle-tier factors are unchanged from the reseeded values, since walking
  away was never the cause there.
- S5. All scheduler tests pass after replacing reads of the revealed fields with
  the submit outcome and the trusted accessor.

## Amendment 5 — enforced trust threshold, 23 September 2026

Recorded before the change was implemented.

**Change.** `grant_trust` refuses an identity until it has at least
`trust_bundles` bundle-tier admissions that were replayed and accepted, default
3. Quarantined identities remain refused. Callers that intend immediate trust,
such as control-plane fixtures, must pass `trust_bundles=0` explicitly.

**Predictions.**

- T1. A grant after one or two admitted bundles is refused; after three it
  succeeds; a quarantined identity is refused regardless of history.
- T2. An attacker whose plan grants trust after one bundle obtains no trusted
  admission, because every grant is refused.
- T3. An attacker that earns three bundles reproduces the three-bundle factor
  already measured, about 2.4 at p = 0.1 immediate.
- T4. All research tests pass, with fixtures that relied on immediate trust
  passing `trust_bundles=0` explicitly.

## Amendment 6 — scientific integrity, 23 September 2026

Recorded before phase 6 was implemented or run.

**Question.** At attacker cost parity, admitted fabricated units can still enter
storage unreplayed. This phase measures what they do to screening results, on
the 33 preserved corpus jobs with the original finalizer, then propagates the
measured damage onto the full five-target matched campaign.

**Hypothesis.** The finalizer recomputes energies from ligand conformations, and
a conformation of a fixed ligand topology is physically valid by construction.
If so, a fabricated unit can only omit a good minimum, never create a false one,
and its scientific damage is bounded by lost search effort.

**Experiments.**

- I-a. Stored coordinates of one unit's best minimum shifted 2 A while its
  conformation is untouched, and the reverse, to establish which the finalizer
  uses.
- I-b. A fraction f in {0.05, 0.10, 0.25, 0.50, 0.75} of a job's units, chosen by
  salted hash, replaced by copies of other units' valid pools, the cheapest
  fabrication that parses, then finalized.
- I-c. The same with every copied energy falsified to -20 kcal/mol.
- I-d. A unit whose atom count does not match the ligand.
- I-e. The per-state score change distribution at each f resampled onto every
  ligand state of the matched campaign's decomposed arm, compound scores and
  ROC-AUC recomputed per target and seed, with bootstrap intervals.

**Predictions.**

- I1. Coordinate-only tampering changes the final score by at most the phase-1
  merge-order noise of 0.12 kcal/mol; conformation-only tampering behaves like
  phase-1 A8c.
- I2. Under I-b, no job's final score improves by more than 0.12 kcal/mol at
  any f. The share of jobs whose score worsens grows with f; the median change
  is zero at f of 0.05 and 0.10.
- I3. I-c matches I-b within sampling noise: falsified energies are laundered at
  scale, not only for a single unit.
- I4. I-d is rejected when the pool is read, before finalization.
- I5. Propagated ROC-AUC changes lie within +/-0.01 on every target at f up to
  0.25. Larger f is reported without a prediction.

If I2 fails, fabricated units can create false positives, the omission-only
claim is false, and scientific integrity requires replaying every unit before
aggregation.

## Amendment 7 — trace-hash commitment, 23 September 2026

Recorded before implementation.

**Change.** A unit's submitted payload becomes its minima pool plus the SHA-256
of its per-step trace, instead of pool plus full trace. The verifier replays the
unit, hashes its own trace and requires both the pool and the hash to match.
Implemented as a protocol module; the browser worker is not changed, because the
device experiments compare full traces.

**Why no re-run.** Under SHA-256 collision resistance, hash equality is byte
equality, so phase 1's 0 of 198 partial-work acceptances and 99 of 99 honest
acceptances under pool-and-trace commitment carry over exactly. Re-executing
them would confirm a construction, not measure anything.

**Predictions.**

- H1. Tests show an honest payload verifies, and one with any altered pool byte,
  altered trace byte or truncated trace is rejected.
- H2. Median payload across all 4,397 corpus medium units falls from about
  167 KB to about 18 KB, a reduction near 90%.

## Amendment 8 — v2 driver, rescoring before merge, 23 September 2026

Recorded after v2 was built and before any check was run.

**Change.** v2 recomputes each minimum read from a submitted pool, energy and
heavy-atom coordinates, from its conformation before merging, using the same
calls the Monte Carlo search used when it saved the minimum. Client-reported
energies and coordinates no longer influence selection. Only `parallel_mc.cpp`
differs from v1, and only in the server finalization path. v1 is unchanged and
remains the historical baseline for every earlier result.

**Predictions.**

- V1. G1 on v2: the instrumented reference CLI built from v2 objects is
  coordinate-identical to the unpatched reference on every retained pose of all
  five crystal targets.
- V2. G2 on v2: the v2 driver's normal run is coordinate-identical to the same
  reference, and single-unit replay and re-finalization are byte-exact.
- V3. Honest pools: v2 finalization of all 33 corpus pools is byte-identical to
  v1's, because rescoring repeats the computation that produced each stored
  energy.
- V4. Merge hijack closed: repeating I-c on v2, no job improves by more than
  0.12 kcal/mol, the median change is zero at every fraction, and propagated
  ROC-AUC change lies within +/-0.01 on every target at f up to 0.25.
- V5. Coordinate-only tampering (I-a) has no effect at all on v2, since stored
  coordinates are discarded.
- V6. Rescoring adds under 100 ms per ligand state to server finalization,
  under 0.05% of the client work it finalizes.

If V3 fails, v2 changes honest science and cannot replace v1 without a new
matched campaign. If V4 fails, rescoring does not close the hijack.

## Amendment 9 — pricing newcomer admission under a CPU budget, 24 September 2026

Recorded before the mechanism below was implemented or run.

**Context.** The isolated ticket prototype (`research/ticket_admission.py`,
commit 7839c31) removed idle seats and protected established users, but fake
submissions paying a fixed 16-bit overload puzzle left 1 of 60 honest newcomers
served. A fake submission costs the attacker only its puzzle, while rejecting
it costs the verifier a full molecular replay. A proof-of-work CAPTCHA verifies
in microseconds and cannot be flooded this way, so this pressure is specific to
useful work.

**Mechanism.** An effort-priority queue on top of the ticket prototype: under
overload a newcomer proves effort as a count of small subpuzzles bound to its
ticket and commitment (10 bits each, following the subpuzzle result that
reduces latency variance); newcomer submissions are replayed in decreasing
effort; a full newcomer queue evicts its lowest-effort entry for a higher one;
and the server publishes a suggested effort that rises only while the queue is
full. Established users keep their reserved capacity.

**Experiment.** Queue, eviction, ordering, tickets and commitments run the real
prototype code. Arrivals, replay time (1.52 s), and all puzzle costs are
simulated: costs are accounted from measured hash rates rather than executed,
honest phones at the measured JavaScript rates of the budget, mid-range and
flagship devices, the attacker at the measured native rate of 1.25 M hashes/s
per core under load. Honest newcomers arrive at 0.5/s with 10 s of puzzle
patience. Grid: 1, 2, 4 and 8 newcomer verifier workers; attacker budgets of
0, 0.1, 0.25, 1, 4 and 16 cores; three mechanisms: the prototype's fixed 16-bit
FIFO puzzle, a fixed 18-bit FIFO puzzle (about 7.5 s on the budget phone), and
the priority queue. The attacker plays a best response: fake submissions each
outbidding the published suggestion, as many as its budget affords. Ticket
issuance rate limiting is disabled so this experiment isolates queue pricing.

**Predictions.** With R the verifier's audit rate and lambda the honest arrival
rate, honest users are outbid once the attacker's budget exceeds
(R - lambda) x (device hash rate) x (patience):

| Verifier workers | Budget phone | Mid-range | Flagship |
| --- | --- | --- | --- |
| 1 | 0.04 cores | 0.19 cores | 0.23 cores |
| 2 | 0.23 cores | 0.97 cores | 1.19 cores |
| 4 | 0.59 cores | 2.54 cores | 3.10 cores |
| 8 | 1.33 cores | 5.67 cores | 6.93 cores |

- C1. Priority queue: a device class keeps at least 90% of newcomers served when
  the attacker's budget is below half its threshold, and at most 50% above twice
  its threshold.
- C2. Fixed 16-bit FIFO, one worker: newcomers are at most 10% served at 0.1
  cores and above, reproducing the prototype's failure.
- C3. Fixed 18-bit FIFO: newcomers are denied once the attacker's budget
  exceeds R x 2^18 hashes/s (0.14 cores at one worker); honest phones pay the
  full puzzle whenever the queue is busy, attack or not, with exponential solve
  tails.
- C4. Under the priority queue honest phones pay nothing without an attack, and
  their solve times have a coefficient of variation near 1/sqrt(n) for n
  subpuzzles.

**Expected conclusion, unfavourable.** No puzzle pricing protects budget-phone
newcomers against an attacker with a few cores at modest verifier capacity. The
protection that holds is proportional to spare replay capacity, which the
defender pays for in real CPU. That cost, absent from proof-of-work, is to be
reported as a price of utility.

## Amendment 9b — full-patience honest bidding, 24 September 2026

Recorded after the amendment 9 grid, which is preserved unchanged, and before
this follow-up was run. It is a post-hoc follow-up and is labelled as such.

**What the amendment 9 run showed.** C3 held: a fixed 18-bit puzzle with eight
verifier workers kept 93-97% of newcomers served at one attacker core and failed
at four, matching a threshold of about 1.1 cores. C2 failed as stated: one
worker under the 16-bit puzzle served 17-38% of newcomers, not at most 10%.
C1 failed with 15 violations, and the priority queue behaved non-monotonically.
The cause was a mismatch between prediction and implementation: the threshold
assumed honest newcomers bid their full patience under pressure, while the
harness had them bid 1.25 times the published suggestion against an attacker
bidding 1.5 times it, so the attacker won every contest at low budgets.

**Change.** Honest newcomers who meet pressure bid their full patience, 10 s of
their own measured hash rate, instead of following the suggestion. Nothing else
changes: queue code, attacker strategy, grid and thresholds are identical, and
only the priority mechanism is rerun.

**Predictions.** C1 is re-tested unchanged against the same thresholds. In
addition, honest newcomers now pay close to their full 10 s whenever the queue
is under pressure, attack or not; this cost is reported, not hidden.

## Amendment 10 — an attested-newcomer lane, 25 September 2026

Recorded before the mechanism below was implemented or run.

**Context.** Amendments 9 and 9b showed that no pricing of a hash puzzle
protects budget-phone newcomers: a native core hashes about 36 times faster than
the budget phone's JavaScript. Because trust requires three audited bundles
(amendment 5), a newcomer that is outbid cannot earn trust either, so under a
sustained attack budget phones are locked out of the trusted lane. This
amendment tests whether a trust signal from outside the system, one that costs
an attacker something other than CPU, breaks that asymmetry.

**Mechanism.** A third lane between trusted users and anonymous newcomers. A
newcomer presenting a device-attestation token receives an attested ticket.
The token is modelled on Privacy Pass rate-limited tokens as used by Apple's
Private Access Tokens: the issuer attests a genuine device and caps tokens per
device per origin, and the origin sees an unlinkable, single-use,
origin-bound token. The prototype checks the token through an issuer
verification callback and stores a nullifier against double spending; the
blind-signature cryptography is not implemented, and a mock issuer with a
per-device limit stands in for the attester. Attested submissions pay no
puzzle, have their own seat and byte reservation, and are replayed first-come
first-served with strict priority over anonymous newcomers. If the attested
lane is full, the newcomer falls back to the anonymous effort-bidding lane of
amendment 9. Established users keep their reserved lane unchanged. Because
tokens are unlinkable, a device whose submission fails audit cannot be
penalised; only the issuer's per-device limit bounds abuse.

**Experiment.** The amendment 9b harness, unchanged in its measured rates,
1.52 s replay, 10 s patience, full-patience honest bidding and attacker best
response, with two additions. A share s of honest newcomers carries a token,
assigned in equal proportion within each device class; attested newcomers are
drawn from the same budget, mid-range and flagship classes. The attacker, in
addition to its CPU budget, obtains attestation tokens at a rate a per second,
standing for its cost of obtaining them: a = 0 (unobtainable), 0.1 (costly, 360
per hour, such as a farm of 360 devices at one token per device per hour), 1
(moderate) and 10 (cheap). It spends each token on a fake attested submission.

- E1, one-shot newcomers as in amendment 9: verifier workers 2 and 8; attacker
  cores 0, 1, 4 and 16; s = 0, 0.5 and 0.9; a = 0, 0.1, 1 and 10 (96 runs).
- E2, trust bootstrap: each honest newcomer keeps contributing until three
  bundles are granted, the trust threshold, preparing each bundle in four times
  its device's measured median unit time from the device-timing study (30.2 s
  budget, 8.1 s mid-range, 8.2 s flagship) and starting a new bundle after every
  outcome. The attack runs for the whole 390 s. Verifier workers 4 and 8;
  attacker cores 0 and 16; s = 0 and 0.9; a = 0, 0.1, 1 and 10 (32 runs).

**Predictions.** With R the verifier's replay rate, lambda = 0.5 honest
newcomers per second and lambda_A = s x lambda of them attested:

- A1. Attested honest newcomers of every device class are at least 90% served
  in E1 whenever lambda_A + a <= 0.8R, at every attacker CPU budget including
  16 cores.
- A2. Where lambda_A + a >= 1.25R, the attested lane saturates: attested honest
  newcomers are at most R/(lambda_A + a) + 0.1 served, and anonymous newcomers,
  starved by the attested lane's priority, at most 20%.
- A3. For anonymous newcomers the amendment 9 threshold becomes
  (R - lambda - a) x (device hash rate) x patience: fake attested submissions
  take replay capacity first. The C1 rule (at least 90% served below half the
  threshold, at most 50% above twice it) is tested for s = 0 and 0.5, where a
  class has at least 20 anonymous newcomers, and for attacker budgets above
  zero.
- A4. With s = 0 and a = 0 the lane is inert: service matches the amendment 9b
  results at the same cells within 0.10.
- A5. Trust bootstrap under a 16-core attack: with s = 0, at most 10% of any
  device class reaches trust, reproducing the lockout; with s = 0.9 and
  a <= 0.1, at least 90% of attested newcomers in every class reach trust,
  budget phones included; anonymous newcomers still reach trust at most 10%;
  and with a = 10 at most half of attested newcomers reach trust.
- A6. Attested honest newcomers pay no puzzle time except after falling back;
  the fallback share is reported.

**Expected conclusion.** Attestation replaces the CPU asymmetry with the
attacker's cost of obtaining tokens, so it protects budget phones that hold a
token at any CPU budget. It does nothing for anonymous visitors, whose
threshold falls when attestations are cheap, and it is only as strong as the
issuer's per-device limit. Its reach is limited by platform: Private Access
Tokens exist on Apple devices, while the Android equivalent, Play Integrity, is
not unlinkable, so a privacy-preserving token may be least available on the
budget Android phones it is meant to protect. That limitation is to be reported
with the result.
