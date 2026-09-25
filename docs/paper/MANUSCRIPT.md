# The Price of Utility: Scientific Computation as Browser Admission Work, Measured Under Attack

*Draft 1, 25 September 2026. Local only. Target: Cybersecurity (SpringerOpen),
Research article. Related work is kept in `RELATED_WORK.md` and merged at
build; references in `references.bib`. Every number below is taken from
`STATUS.md` at commit 22fa955 or later and must be re-checked against it before
submission. Items marked [TODO] need the author.*

---

## Title page

**Title.** The Price of Utility: Scientific Computation as Browser Admission
Work, Measured Under Attack

**Authors.** [TODO: full names, institutional addresses, corresponding author]

## Abstract

*(Target 150–250 words; currently about 245.)*

Proof-of-work challenges protect websites by making each visitor spend
computation that is discarded. We ask what happens when that computation is
useful instead: each admission requires one bounded unit of AutoDock Vina
molecular docking, 256,000 energy evaluations, whose output joins a virtual
screening campaign. Useful work gives up the two properties that make puzzles
safe, microsecond verification and guaranteed freshness, so we evaluate the
design under a protocol whose predictions were committed before each
experiment. Decomposing each docking search into independent units and merging
them with Vina's own finaliser changed screening ROC-AUC by at most ±0.017 on
five targets. Units replayed bit for bit across native code, iOS and Android,
so a server can verify a sampled unit exactly; binding the search trace, not
only its result, rejected all 198 truncated-work submissions. On the real
scheduler, reseeding retried units, withholding the audit draw until upload and
requiring three audited bundles before trust made every attack measured cost
at least as much as honest work, with identities free. We found an attack
specific to merged useful work: falsified energies in 5% of units lowered
screening accuracy by up to 0.034 AUC, removed by rescoring before merging.
The price is availability: every fake submission costs a full replay, so
honest newcomers stay served only while an attacker's hash rate is below
(R − λ) × device hash rate × patience, and budget phones lose first. Device
attestation restores them only where platforms support it.

**Keywords.** proof of work; useful work; admission control; CAPTCHA
alternatives; volunteer computing; denial of service; result verification;
molecular docking

---

## 1 Introduction

Websites that cannot tell people from programs increasingly ask the visitor's
browser to pay in computation. Proof-of-work CAPTCHAs, rate-limiting proxies
against AI crawlers, and Tor's onion-service defence all share one design: the
client searches for a hash below a target, the server checks it with a single
hash, and the work is thrown away [Back02, FriendlyCaptcha, Anubis, TorPoW23].
The waste is the point. Because a puzzle is freshly generated and verified in
microseconds, its security needs no trust in the client, no state beyond a
nonce and no model of what the client did.

This paper asks what the web gives up, and what it gains, when that discarded
computation is replaced by computation someone needs. Each admission in our
system requires one bounded unit of molecular docking with AutoDock Vina
[Trott10, Eberhardt21], and each accepted unit becomes part of a virtual
screening campaign. The idea is not new. reCAPTCHA turned human admission
effort into book digitisation [vonAhn08], Coinhive turned browser admission
into cryptocurrency mining [Rueth18], and a recent design proposes cracking
password hashes in place of hashcash [ChadamTopa23]. What has been missing is a
measured answer to whether such a gate can be made secure, and at what cost.

Useful work surrenders exactly the two properties that make a puzzle safe.
Verifying a docking unit requires re-running it, which is five orders of
magnitude more expensive than checking a nonce. And a correct result can be
computed once and replayed, so work is not automatically fresh. Our claim is
therefore deliberately narrow: that with exact task decomposition, commitment
to the search trace and sampled replay, an attacker pays at least as much per
admission as an honest visitor, and that the remaining price, which is real,
falls on the verifier's replay capacity and on the slowest devices.

We evaluate that claim under a protocol written before any attack was
implemented, amended eleven times with each amendment's predictions committed
to version control before the experiment it governs, and with every miss
reported. We make the following contributions.

1. **A measured useful-work admission system.** To our knowledge, the first
   browser admission gate whose work is a real scientific computation verified
   by deterministic replay, evaluated end to end: a decomposition that
   preserves screening results at matched compute (Section 5.1), and
   bitwise-reproducible execution across native code, iOS and Android (Section
   5.5).
2. **Admission economics with free identities.** On the committed scheduler,
   three structural flaws let an attacker be admitted for less than honest
   work; fixing them restores an attacker discount factor of at least 1.0
   without relying on the cost of identities (Section 5.3).
3. **An aggregation attack on merged useful work.** An attacker need not be
   admitted to damage the science: falsified energies displace honest results
   inside the merge. Rescoring before merging removes the effect at 0.046% of
   client work (Section 5.4).
4. **The availability price of utility.** Because every fake submission costs a
   replay, protection is bought with verifier CPU. We derive and test the
   threshold at which honest newcomers are denied, show why budget phones lose
   first, and measure how far an outside trust signal restores them (Section
   5.6).

We also report where the approach loses. A puzzle beats useful work on
verifier cost and freshness, as predicted. Identity cost matters in ways it
does not for proof of work. Availability under a sustained attacker with about
16 CPU cores is not solved by any configuration we tested, and the attestation
that helps most is unavailable in Android browsers.

## 2 Related work

*[Merged from `RELATED_WORK.md`, sections 2.1–2.7.]*

## 3 System and threat model

### 3.1 Workload and decomposition

The scientific workload is structure-based virtual screening with AutoDock
Vina 1.2.7. A Vina docking run at exhaustiveness 32 performs Monte Carlo
searches with local BFGS refinement and merges their minima through a
finaliser that clusters and refines the best candidates. We split each run into
independent units of 256,000 energy evaluations, each with its own
server-assigned seed, and merge the units' minima pools with Vina's original
finaliser. A ligand state requires a median of 140 units. Units are the
admission currency: a visitor's browser runs one or more units in WebAssembly
and uploads the resulting minima pool.

Prepared receptor and grid state is delivered through a content-addressed CDN,
so a warm browser runs a unit in about 2 s on a current phone and 7.5 s on a
2019 budget phone (Section 5.5).

### 3.2 Verification

Verification is replay. The server re-executes a sampled unit with the same
build, inputs and seed and compares output byte for byte. Three commitments
make that comparison meaningful:

- **Output commitment.** A client commits to the SHA-256 of its full output
  before the audit draw is derived, and the draw is computed server-side from a
  secret, so a client cannot learn which unit will be replayed before
  uploading.
- **Trace commitment.** The commitment covers a hash of the per-step search
  trace, not only the final minima pool. Section 5.2 shows why the pool alone is
  insufficient.
- **Fresh seeds.** Each unit's seed is drawn by the server, and a unit re-issued
  after expiry or failure receives a new seed, so an earlier answer is
  worthless.

Build equivalence was established before any security experiment: three
builds from the same sources and flags agreed coordinate for coordinate with an
uninstrumented reference on every retained pose, and divergence from the
official prebuilt binary was confined to last-bit C runtime differences
amplified by Monte Carlo search (protocol `docs/BUILD_EQUIVALENCE_PROTOCOL_2026-09-20.md` in the repository).

### 3.3 Admission tiers

Newcomers are admitted in bundles of four units, one of which is replayed, so
verifier cost is 25% of client work at one audit draw. An identity that has
had three bundles replayed and accepted may enter a trusted tier in which units
are audited at a rate p. Each admission grants one single-use credit.

For availability we evaluate, as isolated prototypes rather than the deployed
scheduler, stateless authenticated tickets with reserved capacity for
established users, an effort-priority queue for newcomers adopted from Tor's
onion-service defence [TorProp327], and an attested lane for newcomers holding
a Privacy Pass token [Davidson18, RFC9576].

### 3.4 Threat model

Identities are free. The attacker knows the protocol, submits arbitrary bytes,
keeps anything it has computed, coordinates across identities and may hold
native CPU cores. It cannot forge server commitments or read server secrets.
Trust grants and replay verdicts come from trusted server components. We
evaluate eight attacker behaviours, fixed in the protocol before any was
implemented: zero work (A1), partial work (A2), cached replay (A3), retry
grinding (A4), identity reset (A5), disappearing workers (A6), collusion (A7)
and subtle scientific corruption (A8). A8 is the attack that distinguishes
useful work from puzzles, because a plausible but wrong result cannot be
rejected by a cheap structural check.

Out of scope: attacks on the verifier's host, side channels, and compromise of
the attestation issuer.

## 4 Methodology

### 4.1 Predeclared protocol

The evaluation follows a written protocol dated 22 September 2026, before any
attack was implemented and before the matched scientific campaign completed.
Thresholds could not be revised after outcomes were seen; every change is a
dated amendment committed to version control before the experiment it
governs, with the original preserved. Eleven amendments cover phase
operationalisation, the three economic fixes, scientific integrity, trace
commitment, the rescoring driver, newcomer pricing, attestation and the
subpuzzle baseline. Where a prediction failed we report the failure, its cause
and any post-hoc diagnostic separately from the predeclared result.

### 4.2 Corpus and manifests

Attacks run on real molecular output, not synthetic records. The corpus is the
set of campaign jobs whose salted hash falls below 5% of the hash space, a rule
fixed before any attack was designed; 33 jobs across all five targets were
recovered, containing 4,397 units with raw minima pools, traces and metrics.
Every run writes a frozen execution manifest recording protocol, corpus, build
and runner hashes, and re-running with a changed input fails.

### 4.3 What is simulated

Unit-level attacks (Section 5.2) and integrity experiments (Section 5.4) use
real replay. Admission economics (Section 5.3) drive the committed scheduler
under a simulated clock with audit verdicts resampled from real replay records.
Availability experiments (Section 5.6) drive the real queue code with arrivals,
the 1.52 s replay and puzzle costs simulated, the latter accounted from hash
rates measured on phones and on native cores. Device timings (Section 5.5) are
real measurements on participants' phones.

### 4.4 Use of AI tools

[TODO — required by the journal. Draft for the author to confirm and edit:]
Large language model coding assistants (Anthropic Claude and OpenAI Codex)
were used to implement experiment code, analysis scripts and prototypes, and
to draft text, under the author's direction. All predictions were committed
before experiments ran; all numbers in this paper are produced by committed
scripts from recorded data, and the author reviewed the code, results and
text. The assistants are not authors.

## 5 Results

### 5.1 Decomposition preserves the science

Five targets from the DUD-E benchmark [Mysinger12], selected from published Vina results before any local run, each a panel of 32 actives
and 64 decoys, passed predeclared ranking and redocking gates with stock Vina
(ROC-AUC 0.87–0.99). In a matched comparison of 2,073 paired state jobs over
three seeds with no failures, every ligand state was docked both as one
exhaustiveness-32 run and as independent units merged by the original
finaliser, at matched evaluation budget.

| Target | Mean ΔAUC | Paired 95% interval | Evaluation ratio |
| --- | ---: | --- | ---: |
| WEE1 | −0.0003 | [−0.0015, +0.0000] | 1.0040 |
| PUR2 | +0.0033 | [−0.0067, +0.0164] | 1.0025 |
| FA7 | +0.0020 | [−0.0093, +0.0163] | 1.0034 |
| TGFR1 | −0.0008 | [−0.0060, +0.0036] | 1.0045 |
| KIF11 | +0.0003 | [−0.0042, +0.0049] | 1.0045 |

Every interval lies within ±0.017 and straddles or touches zero; EF10 was
identical on 14 of 15 target–seed pairs. Decomposition costs under 0.5% extra
evaluations and no extra search time. The predeclared non-inferiority margin of
−0.05 is generous relative to these effects, so we read the result from the
intervals, not the margin. These are 96-compound panels, not full-library
screens.

### 5.2 Unit-level attacks under real replay

693 trials on 99 units sampled by salted hash from the corpus, all five targets.

| Attack | Outcome |
| --- | --- |
| Honest unit | accepted 99/99 |
| A1 substitution of another unit's result | accepted 0/99 |
| A3 cached resubmission | accepted 99/99, by design; one-use credits refuse it |
| A2 quarter / half work, pool-only commitment | accepted 20/99 and 45/99 |
| A2 quarter / half work, pool and trace commitment | accepted 0/198 |
| A8 best energy falsified by 0.1–3.0 kcal/mol | falsified value never reached output |
| A8 best pose moved 0.1–2.0 Å | no effect at 0.1 and 0.5 Å |

Committing to the minima pool alone does not enforce work: the retained minima
of a Vina search often stabilise before its budget is spent, so a search
stopped at a quarter or half of its evaluations can reproduce the full pool
byte for byte. Binding the per-step trace closes this completely. Committing to
a hash of the trace preserves the guarantee exactly while cutting the median
upload from 163 KB to 19 KB.

### 5.3 Admission economics with free identities

We define the attacker discount factor as attacker work per admission divided
by honest work per admission in the same tier. A proof-of-work puzzle is 1.0 by
construction; below 1.0, cheating is cheaper than honesty. On the committed
scheduler, 118 configurations were run with audit verdicts resampled from real
replay records.

As first built, the scheduler had three flaws. Abandoned units returned with
the same seed, so an attacker who computed one of four units reused it until
the audit draw landed on it (factor 0.46). The audit draw was revealed before
upload, so a trusted identity could abandon exactly when selected and never be
caught. And trust was granted after one bundle. Each fix was predeclared and
measured separately.

| Configuration | Before | After | Predicted |
| --- | ---: | ---: | --- |
| Bundle tier, attacker computes 1 of 4 units | 0.46 | 0.96 | 0.95–1.10 |
| Bundle tier, attacker computes 2 of 4 | 0.57 | 1.03 | 0.95–1.10 |
| Bundle tier, attacker computes 3 of 4 | 0.76 | 1.00 | 0.95–1.10 |
| Trusted tier, p = 0.02–0.25, trust after 1 bundle, audit revealed | 0.44–1.19 | — | — |
| Same, reveal removed | — | 0.44–1.40 | analytic, matched |
| Same, trust after 3 audited bundles | — | 1.36–4.04 | ≥ 1.0 |

With reseeding, no reveal and a three-bundle threshold, every deployed
configuration measured costs an attacker at least as much as honest work. The
difference from proof of work is instructive. Before the fixes, parity would
have required each fresh identity to cost the attacker 0.5–5.1 honest units;
after them it holds with identities free. A puzzle's per-admission cost never
depended on identity at all. Useful work reaches the same property only after
closing structural leaks a puzzle does not have.

Capacity exhaustion by workers who accept units and disappear behaved as a
threshold rather than proportionally: holders of 4, 8 and 12 of 16 leases
caused no refusals, and 16 caused 81%. Stateless tickets that allocate seeds
without reserving queue seats removed the effect in the isolated prototype.

### 5.4 An aggregation attack on the science

An attacker need not be admitted to harm the campaign; it need only place
units in the pool. Running the original finaliser over the corpus with units
replaced or altered:

| Experiment | Measured |
| --- | --- |
| Units with the wrong atom count | rejected 33/33 |
| Honest duplication of units, 5–75% of units | best gain −0.10 kcal/mol; ROC-AUC within ±0.004 up to 25% |
| Duplicated units claiming −20 kcal/mol, 5% of units | 22 of 33 jobs worse, by up to 2.6 kcal/mol |

No falsified energy ever reached output: the finaliser recomputes every
reported energy. But its merge still ranks and clusters minima by the energies
clients report and keeps a bounded set for refinement, so fabricated minima
displace honest ones before refinement sees them. Propagated onto the campaign
(exploratory), ROC-AUC fell by up to 0.034 at 10% fabricated units. A revised
driver that rescores every submitted minimum from its conformation before
merging was verified against the same gates:

| Check | Original | Rescoring |
| --- | --- | --- |
| Build-equivalence gates and replay, five targets | pass | pass |
| Honest pools finalised | — | byte-identical, 33/33 |
| Falsified-energy attack, mean ΔAUC | as low as −0.034 | within ±0.0016 |
| Jobs worsened at 5% falsified units | 22/33 | 2/33, as honest duplication |
| Rescoring overhead per ligand state | — | +91 ms median, 0.046% of client work |

The original driver is retained as the historical baseline for every earlier
result.

### 5.5 Client cost and latency on phones

Against a hashcash puzzle calibrated natively to the same median time, a docking
unit had half the coefficient of variation (0.48 against 0.95) and a p99 of
3.38 s against 6.50 s. On four phones, a test page alternated real units with
puzzles calibrated on the device to its median unit.

| Device | Unit median / max | Puzzle median / p95 / max | Units exact |
| --- | --- | --- | --- |
| iPhone 15, Low Power Mode | 2.04 / 2.10 s | 1.85 / 6.57 / 8.24 s | 17/17 |
| Samsung Galaxy A57 | 2.02 / 2.10 s | 2.09 / 7.82 / 10.5 s | 17/17 |
| Moto Edge 50, Low Power Mode | 2.44 / 2.73 s | 1.86 / 8.83 / 10.4 s | 17/17 |
| Samsung Galaxy M30s (2019 budget) | 7.55 / 10.1 s | 5.86 / 36.1 / 53.2 s | 17/17 |

Scaled to each device's median, 21.9% of puzzle solves exceeded twice the
median and none of 64 units did. All 68 units were bitwise identical across iOS
and Android.

[PENDING amendment 11: the same comparison against a 64-subpuzzle puzzle.
Theory predicts subpuzzles close most of this gap (p95/median about 1.22). If
they do, the claim becomes parity with a well-designed puzzle, not an
advantage.]

The budget phone is 3.7 times slower than the iPhone at docking but 5.2 times
slower at JavaScript hashing, and its first contribution takes about 13 s
including asset delivery, a real accessibility cost.

### 5.6 The availability price of utility

A fake submission costs its sender only its entry price but costs the verifier
a 1.52 s replay. Replay capacity is therefore the scarce resource, a pressure
that proof of work, verified in microseconds, never faces. With R the
verifier's replay rate, λ the honest newcomer arrival rate, r a device's hash
rate and T a visitor's patience, an attacker outbids honest newcomers once its
hash budget exceeds (R − λ) · r · T.

We tested this with an effort-priority queue following Tor's design, driving
the real queue code with measured phone and native rates. With honest
newcomers bidding their full 10 s of patience, the rule held in 46 of 48
testable cells.

| Newcomers served, budget / mid / flagship | 0.25 cores | 1 core | 4 cores | 16 cores |
| --- | --- | --- | --- | --- |
| Fixed 18-bit puzzle, 8 workers | 0.97 / 1.00 / 1.00 | 0.95 / 0.93 / 0.97 | 0.15 / 0.25 / 0.42 | 0.07 / 0.17 / 0.12 |
| Priority queue, 8 workers | 0.90 / 0.88 / 0.93 | 0.95 / 0.95 / 1.00 | 0.05 / 0.95 / 1.00 | 0.05 / 0.03 / 0.05 |

The first run of this experiment failed its prediction with 15 violations:
honest clients followed the published price while the attacker outbid it, so
following a public price proved exploitable. Budget phones lose first because a
native core hashes about 36 times faster than their JavaScript, and no pricing
of a hash puzzle removes that ratio.

Because trust requires three audited bundles, a newcomer who is outbid cannot
earn trust either: under a 16-core attack no device class reached trust. An
attested lane, in which newcomers holding a device-attestation token skip the
puzzle and are replayed first, breaks this lockout while tokens are costly.

| 8 workers, 16-core attacker, budget / mid / flagship | Reached trust | Median time |
| --- | --- | --- |
| No attestation | 0.00 / 0.00 / 0.00 | — |
| 90% attested, attacker 0–1 tokens/s | 1.00 / 1.00 / 1.00 | 69 / 24 / 24 s |
| 90% attested, attacker 10 tokens/s | 0.92 / 0.89 / 0.97 | 112 / 100 / 100 s |
| Same, 4 workers | 0.08 / 0.44 / 0.42 | 278 / 123 / 142 s |

Four of six predictions held in every check. Two missed in stated cells: an
attested lane saturated by cheap tokens served more than predicted because
submissions that fell back to the anonymous lane drained after the attack
ended (confirmed by a post-hoc run with the attack continued), and persistent
retries converted a half-served lane into trust at eight workers where we had
predicted it would not. Cheap tokens starve anonymous visitors, because
attested replays take priority.

## 6 Discussion

**When is useful work worth it?** Only when someone needs the output and the
verifier can afford replay. A puzzle is strictly better on verifier cost and
freshness. Useful work matches it on attacker cost only after closing leaks a
puzzle does not have, and it pays in replay CPU for every fake submission. What
it buys is that the visitor's computation is not wasted: at the matched
campaign's scale, units a site would otherwise discard dock real ligands with
screening quality indistinguishable from monolithic runs.

**Identity cost.** Proof of work is indifferent to identities. Our first
scheduler was not: its security depended on identities costing between 0.5 and
5.1 honest units. We regard this as the most transferable lesson for any
useful-work admission design, whatever the workload: every retry, reveal and
trust path must be checked with identities priced at zero.

**Availability.** The threshold (R − λ) · r · T says protection is bought with
spare replay capacity. A defender facing a 16-core attacker needs more replay
workers than any configuration we tested, or an outside trust signal. The
attested lane is only as strong as the attester's per-device cap, which no
deployed issuer documents, and Android browsers have no deployed
privacy-preserving attestation at all [WEI23, PlayIntegrity].

**Consent.** Browser mining without consent became a documented abuse
[Eskandari18, Konoth18]. A useful-work gate spends visitors' energy; it must
say so, and it gives them a reason a puzzle cannot.

**Limitations.** Four phones, one workload and five 96-compound panels.
Availability mechanisms are isolated prototypes, not integrated into the
deployed scheduler, and their puzzle costs were accounted from measured rates
rather than executed. The trusted tier grants unaudited admissions on history,
not on the unit. Scientific quarantine after late detection is not
implemented. The rescoring driver is a verified candidate, not yet serving
traffic.

## 7 Conclusion

Scientific computation can replace proof of work at a browser gate without
making cheating cheaper than honesty, but only with exact decomposition, trace
commitment, fresh seeds, an audit draw withheld until upload, a trust threshold
and rescoring before merge. Each of these closed a failure we measured. The
price of utility is paid in verifier replay and falls hardest on the slowest
devices, and it is the price we set out to quantify.

---

## Declarations

**Availability of data and materials.** Project name: [TODO]. Project home
page: https://github.com/Rishi94523/Capstone. Archived version: [TODO: Zenodo
DOI of the submission commit]. Operating systems: Windows, Linux, iOS, Android
browsers. Languages: Python, C++, JavaScript/WebAssembly. Licence: [TODO].
Protocol amendments, runners, manifests and analysis scripts are in the
repository; raw result ledgers [TODO: deposit with DOI].

**Competing interests.** [TODO]

**Funding.** [TODO]

**Authors' contributions.** [TODO]

**Acknowledgements.** [TODO: participants who ran phone tests, with their
permission.]
