# The Price of Utility: Scientific Computation as Browser Admission Work, Measured Under Attack

**Short title.** The Price of Utility

*Draft 3, 25 September 2026. Source of truth for `manuscript.tex`, which
`scripts/build_manuscript.py` generates. Related work is included from
`RELATED_WORK.md`. Every number is taken from `STATUS.md` or from the recorded
ledgers by committed scripts; re-check before submission. [TODO] marks items
for the author.*

## Authors

- Rishi | D V | rishidv2005@gmail.com | 1 | 0000-0003-1868-639X | corresponding
- Ram Ganesh | Vemula | ramganeshvemula@gmail.com | 1 | - | author
- Sanjay | D M | sanjaydm23072005@gmail.com | 1 | - | author
- Rithik Madhav | V | rithik7680@gmail.com | 1 | - | author
- Jayashree | R | jayashree@pes.edu | 2 | - | author
- 1: ; PES University; Bengaluru; Karnataka; India
- 2: Department of Computer Science and Engineering (AI & ML); PES University; Bengaluru; Karnataka; India

## Abstract

Proof-of-work admission spends client computation on puzzles. We investigate
replacing that work with bounded AutoDock Vina searches whose outputs join a
virtual-screening campaign. The evaluation combines molecular replay, phone
measurements and admission simulations under a versioned protocol.
Across five preselected 96-compound panels and 2,073 paired state jobs,
decomposition changed mean ROC-AUC by −0.0008 to +0.0033; paired 95% intervals
lay within ±0.017. Tested browser units reproduced reference pool and trace
hashes. Committing to the trace rejected all 198 tested truncated-work
submissions, whereas result-only commitments accepted some. Scheduler fixes
removed large attacker discounts observed with free identities; remaining
bundle-tier estimates were near parity under the evaluated cost model,
without establishing a general work lower bound. Fabricated energies in 5%
of units worsened 22 of 33 re-finalised jobs. An exploratory resampling
projection at 10% corruption estimated ROC-AUC losses up to 0.034; rescoring
before merge reduced this effect in the tested corpus. Phone measurements
showed no general latency-variability advantage over a 64-subpuzzle baseline.
Availability simulations expose the principal cost: a structurally admissible
fake selected for audit consumes a molecular replay. We evaluate a conditional
capacity model and a mock-attestation lane whose benefits depend on assumed
issuer quotas and attacker token supply. Useful-work admission can preserve
scientific screening performance on these panels, but trades cheap
verification for replay capacity and imposes unequal costs across devices.

**Keywords.** proof of work; useful work; admission control; CAPTCHA alternatives; volunteer computing; denial of service; result verification; molecular docking

## 1 Introduction

Websites that cannot tell people from programs increasingly ask the visitor's
browser to pay in computation. Proof-of-work CAPTCHAs, rate-limiting proxies
against AI crawlers, and Tor's onion-service defence charge computation before
admitting requests [Back02, FriendlyCaptcha, Anubis, TorPoW23]. Their puzzle
constructions differ, but verification is much cheaper than solving and the
output is not a scientific result. Fresh challenge binding limits answer
reuse; admission still requires expiry, replay protection and a cost model.

This paper asks what the web gives up, and what it gains, when that discarded
computation is replaced by computation someone needs. An admission in our
system uses one or more bounded units of molecular docking with AutoDock Vina
[Trott10, Eberhardt21], and each accepted unit becomes part of a virtual
screening campaign. The idea is not new. reCAPTCHA turned human admission
effort into book digitisation [vonAhn08], Coinhive turned browser admission
into cryptocurrency mining [Rueth18], and a recent design proposes cracking
password hashes in place of hashcash [ChadamTopa23]. What has been missing is a
measured answer to whether such a gate can be made secure, and at what cost.

Useful work changes both verification cost and answer reuse. Verifying a
docking unit requires replay, far more expensive than checking a hash-puzzle
solution. Scientific inputs may recur, so assignments and one-use credits
must prevent repeated redemption of the same result. We investigate whether
decomposition, trace commitment and sampled replay preserve useful output
while removing exploitable discounts in admission cost. The tested fixes
remove large observed discounts; they do not establish a lower bound against
all algorithms, hardware or strategies. Replay capacity and device disparity
remain material costs.

This paper is organised around one thesis: useful computation can replace
discarded proof of work at a browser gate, but verification changes the
economics of admission. We test it through five questions, each answered by a
separate experiment under a protocol written before any attack was
implemented. The protocol was amended twelve times, each amendment's
predictions committed to version control before the experiment it governs,
and every miss is reported. The measured answers are our contributions.

1. **Can a docking search be split into admission-sized units without changing the science?** On five qualified panels, screening results are preserved at matched evaluation counts (Section 5.1).
2. **Can browsers reproduce those units exactly?** Every tested unit on five phone models reproduced the reference output bit for bit; unit latency is as predictable as a 64-subpuzzle puzzle, not more (Section 5.2).
3. **Can clients fake the work cheaply?** Some strategies initially could. Trace commitment and three scheduler fixes remove the large measured discounts, leaving estimates near parity with free identities; no general lower bound is established (Sections 5.3 and 6).
4. **Can fabricated outputs corrupt the scientific aggregate?** Yes, once included in the candidate pools: offline pool modification exposes a merge failure that rescoring mitigates. This experiment does not demonstrate an admission bypass (Section 5.4).
5. **Is useful work better than proof of work?** Not universally. Replay turns fake submissions into verifier load, device disparity decides who is denied first, and an outside trust signal helps only under stated issuer assumptions (Section 5.5).

We also report where the approach loses. A puzzle beats useful work on
verifier cost and freshness, as predicted. Identity cost matters in ways it
does not for proof of work. Availability under a sustained attacker with about
16 CPU cores is not solved by any configuration we tested, and the attestation
that helps most is unavailable in Android browsers.

## 2 Related work

<!-- include RELATED_WORK -->

## 3 System and threat model

### 3.1 Workload and decomposition

The scientific workload is structure-based virtual screening with AutoDock
Vina 1.2.7. A Vina docking run at exhaustiveness 32 performs Monte Carlo
searches with local BFGS refinement and merges their minima through a
finaliser that clusters and refines the best candidates. We split each run
into independent units of 256,000 energy evaluations, each with its own
server-assigned seed, and merge the units' minima pools with Vina's original
finaliser (Figure 1). A ligand state requires a median of 140 units. Units are
the admission currency: a visitor's browser runs one or more units in
WebAssembly and uploads the resulting minima pool.

Prepared receptor and grid state is delivered through a content-addressed CDN,
so a warm browser runs a unit in about 2 s on a current phone and 7.5 s on a
2019 budget phone (Section 5.2).

```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}[font=\footnotesize,node distance=4mm and 7mm,
  box/.style={draw,rounded corners=2pt,align=center,minimum height=8mm,inner sep=3pt},
  arr/.style={-{Stealth[length=2mm]}}]
\node[box] (queue) {Campaign queue\\ligand state $\rightarrow$ units};
\node[box,right=of queue] (ticket) {Ticket\\seeds drawn by server};
\node[box,right=of ticket] (browser) {Visitor's browser\\WebAssembly Vina unit};
\node[box,below=of browser] (commit) {Commit\\SHA-256 of output\\and search trace};
\node[box,left=of commit] (draw) {Secret audit draw\\after upload};
\node[box,left=of draw] (replay) {Replay one unit\\byte-for-byte check};
\node[box,below=of replay] (admit) {Admit\\one-use credit};
\node[box,right=of admit] (rescore) {Rescore minima\\from conformations};
\node[box,right=of rescore] (final) {Vina finaliser\\screening result};
\draw[arr] (queue)--(ticket);\draw[arr] (ticket)--(browser);\draw[arr] (browser)--(commit);
\draw[arr] (commit)--(draw);\draw[arr] (draw)--(replay);\draw[arr] (replay)--(admit);
\draw[arr] (admit)--(rescore);\draw[arr] (rescore)--(final);
\end{tikzpicture}
\caption{Admission with useful work. The server assigns units with fresh seeds; the browser runs one or more units and commits to their outputs and search traces before learning which unit will be replayed; a secretly drawn unit is replayed exactly; accepted units are rescored and merged by Vina's own finaliser.}
\label{fig:system}
\end{figure}
```

### 3.2 Verification

Verification is replay. The server re-executes a sampled unit with the same
build, inputs and seed and compares output byte for byte. Three measures make
that comparison meaningful.

- **Output commitment.** A client commits to the SHA-256 of its full output before the audit draw is derived, and the draw is computed server-side from a secret, so a client cannot learn which unit will be replayed before uploading.
- **Trace commitment.** The commitment covers a hash of the per-step search trace, not only the final minima pool. Section 5.3 shows why the pool alone is insufficient.
- **Fresh seeds.** Each unit's seed is drawn by the server, and a unit re-issued after expiry or failure receives a new seed, so an earlier answer cannot satisfy that new assignment. This prevents ordinary duplicate-answer caching, not every form of precomputation or algorithmic shortcut.

Build equivalence was established before any security experiment: three
builds from the same sources and flags agreed coordinate for coordinate with
an uninstrumented reference on every retained pose, and divergence from the
official prebuilt binary was confined to last-bit C runtime differences
amplified by Monte Carlo search.

### 3.3 Admission tiers

Newcomers are admitted in bundles of four units, one of which is replayed, so
verifier cost is 25% of client work at one audit draw. An identity that has
had three bundles replayed and accepted may enter a trusted tier in which
units are audited at a rate p. Each admission grants one single-use credit.

For availability we evaluate, as isolated prototypes rather than the deployed
scheduler, stateless authenticated tickets with reserved capacity for
established users, an effort-priority queue for newcomers adopted from Tor's
onion-service defence [TorProp327], and an attested lane for newcomers holding
token from a mock issuer inspired by Privacy Pass [Davidson18, RFC9576].
The mock assumes an origin-bound, single-use token with a per-device quota;
it does not implement blind signatures or integrate a deployed issuer.

### 3.4 Threat model

Identities are free. The attacker knows the protocol, submits arbitrary bytes,
keeps anything it has computed, coordinates across identities and may hold
native CPU cores. It cannot forge server commitments or read server secrets.
Trust grants and replay verdicts come from trusted server components. We
evaluate eight attacker behaviours, fixed in the protocol before any was
implemented: zero work (A1), partial work (A2), cached replay (A3), retry
grinding (A4), identity reset (A5), disappearing workers (A6), collusion (A7)
and subtle scientific corruption (A8). A8 distinguishes useful work from
puzzles, because a plausible but wrong result cannot be rejected by a cheap
structural check. Attacks on the verifier's host, side channels and
compromise of the attestation issuer are out of scope.

## 4 Methodology

### 4.1 Predeclared protocol

The evaluation follows a written protocol dated 22 September 2026, before any
attack was implemented and before the matched scientific campaign completed.
Thresholds could not be revised after outcomes were seen; every change is a
dated amendment committed to version control before the experiment it
governs, with the original preserved. Twelve amendments cover phase
operationalisation, the three economic fixes, scientific integrity, trace
commitment, the rescoring driver, newcomer pricing, attestation and the
subpuzzle baseline, and a post-review replay-timing correction with five-seed
replication. Where a prediction failed we report the failure, its
cause and any post-hoc diagnostic separately from the predeclared result.

### 4.2 Corpus, manifests and statistics

Attacks run on real molecular output, not synthetic records. The corpus is the
set of campaign jobs whose salted hash falls below 5% of the hash space, a rule
fixed before any attack was designed; 33 jobs across all five targets were
recovered, containing 4,397 units with raw minima pools, traces and metrics.
Every run writes a frozen execution manifest recording protocol, corpus, build
and runner hashes, and re-running with a changed input fails. Proportions are
reported with exact (Clopper–Pearson) 95% intervals. Attacker discount factors
are ratios of attempt counts; we report 95% intervals from the geometric
distribution of attempts per admission, treating attempts as independent.


### 4.3 Measurement boundaries and reproducible methods

Table: Evidence supporting the claims and what each experiment does not establish.

| Claim | Evidence | Boundary |
| --- | --- | --- |
| Screening preservation | Actual native paired docking and finalisation, five panels | Qualified 96-compound panels, not full libraries or prospective biological validation |
| Trace-bound replay | Actual unit re-execution and byte/hash comparison | Tested builds, inputs and attacks; not a computational lower bound |
| Admission economics | Committed scheduler with simulated time and replay-derived verdicts | Specified strategies and cost model; not production traffic |
| Scientific poisoning | Actual corpus re-finalisation; separately, score-shift resampling | Whole-panel AUC effects are exploratory projections |
| Browser feasibility | Real phone execution and reference hash checks | Cooperative sessions, selected repeated units; not client attestation |
| Overload and trust bootstrap | Real queue SQL with modeled arrivals, replay and puzzle costs | Conditional finite-horizon simulations; not measured HTTP throughput |
| Attestation benefit | Mock issuer, token checks and one-use nullifiers | Assumed quota and token supply; no deployed issuer or blind-signature integration |

Supplementary Section S1 gives the complete protocols: target selection and
input preparation, compute matching and the paired bootstrap, the poisoning
projection, and the availability simulator. The availability results use
exact replay-event timing and five seeds (amendment 12). That amendment
corrected an earlier discretisation which, by noticing completions only on
250 ms ticks, lengthened each simulated 1.52 s replay to 1.75 s; the original
single-seed results are preserved and compared in Supplementary Section S3.


### 4.4 Use of AI tools

Large language model coding assistants
(Anthropic Claude and OpenAI Codex) were used to implement experiment code,
analysis scripts and prototypes, to search and verify literature, and to draft
text, under the author's direction. All predictions were committed to version
control before the experiments they govern ran; every number in this paper is
produced by committed scripts from recorded data; and the author reviewed the
code, results and text and takes responsibility for them. The assistants are
not authors.

## 5 Results

### 5.1 Can docking be decomposed without changing the science?

Five targets from the DUD-E benchmark [Mysinger12], selected from published
Vina results before any local run and each a panel of 32 actives and 64
decoys, passed predeclared ranking and redocking gates with stock Vina
(ROC-AUC 0.87–0.99). In a matched comparison of 2,073 paired state jobs over
three seeds with no failures, every ligand state was docked both as one
exhaustiveness-32 run and as independent units merged by the original
finaliser, at matched evaluation budget.

Table: Matched comparison of decomposed and monolithic docking: change in screening ROC-AUC, three seeds, 96-compound panels.

| Target | Mean ΔAUC | Paired 95% interval | Evaluation ratio |
| --- | ---: | --- | ---: |
| WEE1 | −0.0003 | [−0.0015, +0.0000] | 1.0040 |
| PUR2 | +0.0033 | [−0.0067, +0.0164] | 1.0025 |
| FA7 | +0.0020 | [−0.0093, +0.0163] | 1.0034 |
| TGFR1 | −0.0008 | [−0.0060, +0.0036] | 1.0045 |
| KIF11 | +0.0003 | [−0.0042, +0.0049] | 1.0045 |

Every interval lies within ±0.017 and straddles or touches zero; EF10 was
identical on 14 of 15 target–seed pairs. Decomposition costs under 0.5% extra
evaluations and no extra search time. The predeclared non-inferiority margin
of −0.05 is generous relative to these effects, so we read the result from the
intervals, not the margin. These are 96-compound panels, not full-library
screens.

### 5.2 Can browsers reproduce the units, and at what latency?

In a first study on four phones, all 68 executions of four distinct reference
units were bitwise identical to the native reference output across iOS and
Android. Against a single
hashcash puzzle calibrated on each device to its median unit, 21.9% of puzzle
solves exceeded twice the median and none of 64 warm units did
(Supplementary Section S2). Natively, a docking unit also had half the
coefficient of variation of a median-matched hashcash puzzle (0.48 against
0.95).

A single hash puzzle is not the strongest baseline: deployed proof-of-work
CAPTCHAs split the work into many small puzzles [FriendlyCaptcha], and the
sum of 64 geometric solve counts is far narrower than one. We therefore ran a
second page on five phones, interleaving each unit with two single puzzles and
two 64-subpuzzle puzzles, all calibrated on the device to its median unit
(amendment 11).

Table: Five phones, 16 warm units and 24 solves of each puzzle type per phone, pooled by each device's median unit time as predeclared.

| Kind | n | p95/median | Over 2× median |
| --- | ---: | ---: | ---: |
| Docking unit | 80 | 1.15 | 0% |
| Single puzzle | 120 | 4.40 | 25.8% |
| 64-subpuzzle puzzle | 120 | 2.02 | 5.8% |

Two of four predictions held: single puzzles again had a long tail, and units
stayed within 1.35 times their median at the 95th percentile. The prediction
that subpuzzles would too failed, and so did the calibration check that
explains it: on-device calibration missed by up to a factor of 1.66 (Moto Edge
50) and 0.70 (Galaxy M30s), so pooling by unit time mixes shifted
distributions. Measured within each device instead, a post-hoc analysis,
subpuzzle solves had p95/median 1.14–1.40 and none exceeded twice their own
median; pooled, 1.21 against 1.15 for units (Figure 2). As stated before the
experiment, lower latency variance is therefore not an advantage of useful work
over a well-designed puzzle. It is an advantage only over a single puzzle.

```latex
\begin{figure}[htbp]
\centering
\includegraphics[width=0.6\textwidth]{figures/device_latency.pdf}
\caption{Solve time on five phones for docking units, single puzzles and 64-subpuzzle puzzles run in the same sessions. Each time is divided by its device's median for that kind, so the curves compare distribution shape; the dotted line marks twice the median. Calibration error, which this scaling removes, is reported in the text.}
\label{fig:latency}
\end{figure}
```

The budget phone is 3.7 times slower than the iPhone at docking but 5.2 times
slower at JavaScript hashing, and its first contribution takes about 13 s
including asset delivery, a real accessibility cost.

All 85 executions in this second study also matched the reference output
exactly. These repeat four distinct reference units across the five phones;
they are not 85 distinct molecular workloads.


### 5.3 Can clients fake the work cheaply?

**Unit-level attacks under real replay.** We ran 693 trials on 99 units sampled by salted hash from the corpus, across
all five targets.

Table: Unit-level attacks judged by exact replay, 99 corpus units.

| Attack | Accepted | 95% interval |
| --- | ---: | --- |
| Honest unit | 99/99 | [0.96, 1.00] |
| A1 substitution of another unit's result | 0/99 | [0.00, 0.04] |
| A3 cached resubmission | 99/99 | by design; one-use credits refuse it |
| A2 quarter work, pool-only commitment | 20/99 | [0.13, 0.30] |
| A2 half work, pool-only commitment | 45/99 | [0.35, 0.56] |
| A2 quarter or half work, pool and trace commitment | 0/198 | [0.00, 0.02] |

Committing to the minima pool alone does not enforce work: the retained
minima of a Vina search often stabilise before its budget is spent, so a
search stopped at a quarter or half of its evaluations can reproduce the full
pool byte for byte. Binding the per-step trace rejected every tested quarter-
and half-budget submission. This tests those truncation strategies, not a
general computational lower bound. Hashing the trace preserves the tested
replay check, subject to collision resistance, while cutting median upload
from 163 KB to 19 KB. Falsifying the best energy by
0.1–3.0 kcal/mol never changed any output, because the finaliser recomputes
energies; moving the best pose by 0.1 or 0.5 Å had no effect.

**Admission economics with free identities.** We define the attacker discount factor as attacker work per admission divided
by honest work per admission in the same tier. A hash puzzle is normalised to
1.0 under a common hardware and expected-hash cost model; that is not a claim
of equal wall time or energy across hardware. Below 1.0, the modeled attacker
cost is lower than the honest cost. On the committed
scheduler, 118 configurations were run with audit verdicts resampled from real
replay records.

As first built, the scheduler had three flaws. Abandoned units returned with
the same seed, so an attacker who computed one of four units reused it until
the audit draw landed on it. The audit draw was revealed before upload, so a
trusted identity could abandon exactly when selected and never be caught. And
trust was granted after one bundle. Each fix was predeclared and measured
separately.

Table: Attacker discount factor on the committed scheduler before and after the three fixes.

| Configuration | Before | After, 95% interval | Predicted |
| --- | ---: | --- | --- |
| Bundle tier, attacker computes 1 of 4 units | 0.46 | 0.96 ± 0.09 | 0.95–1.10 |
| Bundle tier, attacker computes 2 of 4 units | 0.57 | 1.03 ± 0.08 | 0.95–1.10 |
| Bundle tier, attacker computes 3 of 4 units | 0.76 | 1.00 ± 0.06 | 0.95–1.10 |
| Trusted tier, trust after 1 bundle, p = 0.02–0.25 | 0.44–1.19 | 0.44–1.40, reveal removed | analytic, matched |
| Trusted tier, trust after 3 audited bundles | — | 1.36–4.04 | at least 1.0 |

With reseeding, no reveal and a three-bundle threshold, the large observed
bundle-tier discounts (0.46–0.76) disappear: tested estimates become
0.96–1.03. These are consistent with parity under the evaluated cost model.
The lowest interval, 0.96 ± 0.09, also permits a modest attacker advantage;
containing 1.0 does not establish equality or a lower bound of 1.0. The
trusted-tier strategies tested after the threshold change cost 1.36–4.04.
Identities are free in these experiments, but results apply to the specified
strategies, attempt model and workload costs, not every possible adversary.
Before the fixes, compensating for the measured discounts would have required
an identity price of 0.5–5.1 honest units. The fixes remove the particular
reuse, disclosure and early-trust paths responsible for those discounts.

Capacity exhaustion by workers who accept units and disappear behaved as a
threshold rather than proportionally: holders of 4, 8 and 12 of 16 leases
caused no refusals, and 16 caused 81%. Stateless tickets that allocate seeds
without reserving queue seats removed the effect in the isolated prototype.

Every behaviour in the threat model is covered, though not all by a
dedicated experiment. Zero work (A1), partial work (A2) and cached replay (A3)
are the unit-level attacks above. Retry grinding (A4) and identity reset (A5)
are the retry, cap and fresh-identity strategies of the admission experiments,
all run with identities free. Disappearing workers (A6) are the lease-exhaustion
result. Collusion (A7), identities sharing one computed result, was not run
separately: a result computed for another unit fails replay like substitution
(0 of 99 accepted), and resubmitting the same result for the same unit is
refused by one-use credits. Subtle corruption (A8) is Section 5.4.
Supplementary Section S4 lists the further scheduler configurations: attempt
caps, two audit draws, reduced-budget units and trust acquisition.

Section 6 discusses what trace commitment does and does not establish about
the work an accepted unit requires.


### 5.4 Can fabricated work corrupt the science?

We ran the original finaliser over saved corpus pools with units replaced or
altered. This offline experiment measures damage conditional on malicious
outputs entering the aggregate; it does not demonstrate a way to bypass the
admission scheduler. In the scheduler, a bundle rejected by immediate audit
does not enter the scientific pool. Unaudited outputs in accepted bundles
and outputs admitted before deferred audit are distinct exposure paths.

Table: Corpus re-finalisation measurements; the ROC-AUC entry is a separate exploratory projection.

| Experiment | Measured |
| --- | --- |
| Units with the wrong atom count | rejected 33/33 |
| Stored coordinates moved 2 Å, conformation untouched | −0.10 to +0.02 kcal/mol, within the predicted 0.12 |
| Conformation moved 2 Å, coordinates untouched | −0.42 to +1.37 kcal/mol; the prediction of no gain failed |
| Honest duplication of 5–75% of units | measured best gain −0.10 kcal/mol; projected ROC-AUC within ±0.004 up to 25% |
| Duplicated units claiming −20 kcal/mol, 5% of units | 22 of 33 jobs worse (95% interval 0.48–0.82), by up to 1.859 kcal/mol |

In these tests, fabricated reported energies did not survive final rescoring:
the finaliser recomputed the output energies from conformations. This does
not establish biological validity or rule out false positives in screening.
The largest score improvement across these pool-tampering experiments was
0.466 kcal/mol, in the 5% fabricated-energy condition. The largest worsening
was 2.632 kcal/mol at 10% corruption, compared with 1.859 at 5%.
The merge still ranks and clusters minima by the
energies clients report and keeps a bounded set for refinement, so fabricated
minima displace honest ones before refinement sees them. In an exploratory,
non-predeclared resampling projection, mean ROC-AUC changes reached about
−0.016 at 5% and −0.034 at 10% fabricated units. These are not measured
whole-panel poisoning outcomes: corpus score shifts were resampled onto
otherwise unchanged campaign scores (Supplementary Section S1). A revised driver that rescores every submitted minimum from
its conformation before merging was verified against the same gates.

Table: Rescoring driver against the original driver.

| Check | Original | Rescoring |
| --- | --- | --- |
| Build-equivalence gates and replay, five targets | pass | pass |
| Honest pools finalised | — | byte-identical, 33/33 |
| Falsified-energy attack, projected mean ΔAUC | as low as −0.034 | within ±0.0016 |
| Jobs worsened at 5% falsified units | 22/33 | 2/33, as honest duplication |
| Jobs changed by coordinate-only tampering | 16/33 | 0/33 |
| Rescoring overhead per ligand state | — | +91 ms median; 0.046% relative to calibrated client work |

The original driver is retained as the historical baseline for every earlier
result. The relative overhead denominator is number of units multiplied by a
calibrated 1,520 ms per unit, not measured client time for each attacked job.
The ±0.0016 AUC range is also a projection. Rescoring addresses fabricated
energy ordering; it does not certify that unaudited pools contain all minima
that honest search would have found.

### 5.5 What does useful work cost compared with proof of work?

A hashcash puzzle calibrated natively to a similar median client time (1.38 s
against 1.52 s for a unit) verifies in 0.77 µs. Verifying useful work costs a
replay of 1.52 s for each audited unit, a fraction q of client work: about
five orders of magnitude more at q = 0.1. The puzzle also guarantees
freshness, which useful work must restore with assignment seeds and one-use
credits. The rest of this section asks what that verification cost does
under attack.

A structurally admissible fake selected for audit consumes a modeled 1.52 s
replay, whereas hash-puzzle verification is comparatively cheap. Let R be
replay service capacity, λ the honest newcomer arrival rate, r a device's
hash rate and T its bidding budget. Under full-patience bidding, an honest
bid is approximately rT hashes. Buying the spare R − λ replay slots per
second at that price gives the budget scale (R − λ) · r · T. This is a
conditional capacity model, not a universal threshold: finite queues,
transient prices, device mixtures, randomized solve times and the attack/drain
horizon can change observed service. The predeclared C1 test checks only
budgets below half or above twice this scale, leaving the intermediate band
untested.

**Historical results and correction.** The original follow-price experiment
passed 33/48 C1 checks; the full-patience follow-up passed 46/48. Both used
one seed and rounded replay completion to the next 250 ms tick, giving 1.75 s
service rather than the assumed 1.52 s. Amendment 12 preserves those results
and repeats all four grids with exact replay events and five seeds, 1,120
runs in total. The corrected full-patience experiment passes 230/240 eligible
checks: 46/48 in each seed. The same two directional misses recur at one
worker: budget-phone service at 0.1 attacker cores and flagship service at
one core exceed the predicted upper limit. These are not 240 independent
traffic scenarios or validation of an exact cutoff (Figure 3).

Supplementary Table S2 lists every prediction check, original and corrected.

At eight replay workers the priority mechanism still discriminates sharply by
device under a four-core attack. Corrected service means are 0.070, 0.965
and 1.000 for budget, mid-range and flagship devices. At sixteen attacker
cores they are 0.110, 0.135 and 0.130. Service is measured within the finite
observation window, including post-attack draining; it is not a ten-second
admission guarantee.

```latex
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/served_vs_cores.pdf}
\caption{Corrected full-patience simulation: mean service across five seeds, with shading for the observed minimum--maximum range. Dashed lines mark the conditional budget scale $(R-\lambda)\,r\,T$, not a guaranteed cutoff. Input polling remains discrete; replay completion uses exact event times.}
\label{fig:served}
\end{figure}
```

A native core's measured hash rate is about 36 times the budget phone's
JavaScript rate. Pricing alone does not remove that disparity. Under the
sixteen-core bootstrap attack, without attestation, no budget or mid-range
users reach trust in the corrected runs; flagship users reach trust at a mean
of 0.030 (range 0–0.050) with eight workers. The historical single-seed
statement that no device class ever reached trust is therefore too strong.

**Conditional mock-attestation result.** If an issuer supplies origin-bound,
one-use tokens with an effective per-device quota, a separate replay lane
can help token holders earn trust without winning the hash auction. This is
an experiment with MockAttester, not a deployed Privacy Pass integration.
At an assumed 90% honest token coverage, every attested group reaches trust
in all five seeds at attacker supply 0, 0.1 or 1 tokens/s with eight workers.
At zero attacker tokens, mean within-seed median trust times are about
66 / 23 / 23 s, conditional on success and excluding the initial bundle's
molecular work, which is already available at first arrival in this harness.
Later bundles include device-calibrated work time.
At ten attacker tokens per second, trust fractions fall and vary across
seeds and device classes (Supplementary Table S4).

```latex
\begin{figure}[htbp]
\centering
\includegraphics[width=\textwidth]{figures/trust_bootstrap.pdf}
\caption{Corrected mock-attestation simulation under sixteen attacker cores. Bars show five-seed mean trust fractions; whiskers show observed minimum--maximum ranges. Left of the grey line: no attestation. Right: 90\% honest token coverage as assumed attacker token supply rises. The issuer and token-acquisition budgets are modeled.}
\label{fig:trust}
\end{figure}
```

T1, T3, T4 and T6 pass every corrected eligible check; T2 and T5 retain
misses. The original post-hoc drain diagnostic and saturation failures remain
in the archive. One-shot traffic drains after attack cessation; bootstrap
attacks continue throughout the observation window, with repeated attempts
until three grants. Consequently, one-shot service ratios and eventual trust
fractions answer different questions. Token availability and issuer quotas
are assumptions, and cheap attacker tokens consume capacity ahead of
anonymous users. No conclusion here establishes production availability or
an implementable quota from a deployed issuer.

## 6 Discussion

**When is useful work worth it?** Only when someone needs the output and the
verifier can afford replay. A puzzle is strictly better on verifier cost and
freshness. Useful work removes large observed attacker discounts only after
closing the tested reuse and trust leaks, it is no more predictable for the
visitor than a subpuzzle puzzle, and it pays in replay CPU for every fake
submission. What it buys is that the visitor's computation is not wasted: the
units a site would otherwise discard dock real ligands with screening differences
small on the five qualified panels, within the reported uncertainty.

**What trace commitment does and does not establish.** The committed trace
records, for every Monte Carlo step, the refined candidate's energy at full
double precision and the cumulative number of energy evaluations. A matching
trace binds these recorded per-step values, which replay compares byte for
byte. It does not record every intermediate energy evaluation, coordinate or
gradient, and therefore does not uniquely establish the internal sequence of
computations. Two routes to a cheaper
accepted trace remain open. Faster hardware or a faster implementation of the
same operations, such as native code, vectorisation or a GPU, is not a
shortcut in the security sense: it is the same hardware disparity proof of
work already has, and Section 5.5 prices it. Avoiding evaluations is the real
question. Approximate energies, reordered arithmetic or incremental updates
can change floating-point rounding and hence the committed bytes; fresh
server-drawn seeds make one unit's intermediate states unlikely to recur in
another. We know of no method that yields a matching trace with fewer
evaluations than the honest search, but we have not proved that none exists.
A lower bound of that kind, for example showing that any accepted trace of N
steps requires Ω(N) evaluations under stated assumptions about the scoring
function, remains open.

**Identity cost.** Proof of work is indifferent to identities. Our first
scheduler was not: its security depended on identities costing between 0.5
and 5.1 honest units. We regard this as the most transferable lesson for any
useful-work admission design, whatever the workload: every retry, reveal and
trust path must be checked with identities priced at zero.

**Reputation under load.** Verifying reputed submitters first protects them.
In the isolated ticket prototype, a flood of fake submissions paying a 16-bit
puzzle cut newcomers to 1 of 60 served while established users, who hold
reserved replay capacity, stayed at 60 of 60 (arrivals and replay simulated).
A failed audit quarantines the identity, so a reputed submitter who turns
malicious is caught at the trusted tier's audit rate. Reputation cannot, however,
rescue honest newcomers. A surge in new identities reveals that an attack is
under way but not which newcomers are attackers; both have no history.
Deprioritising all new identities under load therefore denies honest
newcomers as well, which is the trust-bootstrap lockout of Section 5.5.
Separating them requires an outside signal, such as the attestation modelled
there or the cross-site behavioural signals of deployed challenge services
[Turnstile22], which trade privacy for discrimination. The standard attack on
reputation is the sleeper identity: identities aged during quiet periods and
spent together in an attack [Douceur02]. Useful-work admission changes the
price of that strategy. Earning trust here requires three replayed and
accepted bundles, so an attacker who pre-builds reputation must first perform
real, audited docking. Aged identities still gain admission, but the work that
bought them is useful. We have not measured a sleeper-identity attack; its
cost and yield are a natural next experiment.

**Availability.** The conditional budget scale (R − λ) · r · T exposes the
cost of replay capacity under the modeled attack. Corrected five-seed results
retain substantial anonymous-newcomer denial at sixteen attacker cores. A
mock-attestation lane improves outcomes only under assumed honest coverage
and attacker token budgets; issuer quotas and platform availability remain
external requirements, not properties established by our prototype.

**Consent.** Browser mining without consent became a documented abuse
[Eskandari18, Konoth18]. A useful-work gate spends visitors' energy; it must
say so, and it gives them a reason a puzzle cannot.

**Limitations.** Five phone models, one workload and five 96-compound panels.
Availability mechanisms are isolated prototypes, not integrated into the
deployed scheduler, and their puzzle costs were accounted from measured rates
rather than executed. Discount-factor intervals assume independent attempts.
The trusted tier grants unaudited admissions on history, not on the unit.
The scheduler quarantines contributors after failed replay and blocks
aggregate-output retrieval when their contributions are present. A dedicated
late-failure test covers this guard; automatic campaign repair and retraction
of already-produced scientific results have not been demonstrated. The rescoring
driver is a verified candidate, not yet serving traffic. Pool poisoning AUCs
are projections based on exchangeable corpus score shifts. The availability
replication measures five-seed variability but keeps arrival rates, device
speeds, replay cost and attacker strategies fixed. Puzzle RNGs are seeded;
prototype ticket identifiers and their tie-breaking remain cryptographically
random. The initial bootstrap bundle is assumed ready at arrival. There is
no integrated production traffic or energy-cost validation.


## 7 Conclusion

Useful computation can stand in for discarded proof of work at a browser gate,
but verification changes the economics of admission. On five qualified panels,
bounded Vina units preserve screening performance and reproduce exactly on
phones. Trace commitment, fresh assignment seeds, concealed audit draws and a
trust threshold remove the large discounts found in tested attacks; the
remaining estimates are near parity under the cost model, not a proof that
cheating cannot be cheaper. Rescoring mitigates a measured merge failure.
Verification still consumes replay capacity, overload falls unequally on
devices, and any benefit from external attestation depends on issuer and
token-supply assumptions. These results quantify the practical costs and limits
of useful-work admission rather than establish a universal replacement for
proof of work.


## Declarations

### Supplementary information

Additional file 1 (PDF): Supplementary Information. Complete experimental
methods (S1), the first four-phone timing study (S2), and all availability
prediction checks, five-seed service and trust tables and historical
comparisons (S3), and further admission-economics configurations (S4).

### Availability of data and materials

Project name: Capstone useful-work admission research prototype. Project home page: https://github.com/Rishi94523/Capstone.
Archived version: [TODO: Zenodo DOI of the submission commit and result
bundle]. Operating systems: Windows, Linux, and iOS and Android browsers.
Programming languages: Python, C++, JavaScript and WebAssembly. Licence:
MIT; AutoDock Vina and other upstream components, fetched and patched at build
time rather than redistributed, keep their own licences (Vina: Apache 2.0).
Protocol amendments, runners, manifests, analysis scripts and the
figure and manuscript builders are in the repository.

### Ethics approval and consent to participate

Not applicable. All phone timing tests were run by the authors on phones they
own. The test page submitted the device model and operating system as entered,
the browser user agent and performance measurements; the study stored no
names, contact details or location data.

### Competing interests

The authors declare that they have no competing interests.

### Funding

Not applicable.

### Authors' contributions

RDV conceived and designed the study, implemented the system, ran the
experiments, analysed the results and wrote the manuscript. RGV, SDM and RMV
ran the device experiments and reviewed and edited the manuscript. JR
supervised the work and revised the manuscript. All authors read and approved
the final manuscript.

### Acknowledgements

Not applicable.
