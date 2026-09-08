# Independently auditable bounded Vina runs: measured decision

Completed 8 September 2026. [Evidence and reproduction](../evaluation/docking_whole_runs_2026-09-08/README.md), [all timing tiers](../evaluation/docking_whole_runs_2026-09-08/tables.md), [previous investigation](LIGHTWEIGHT_DOCKING_FINDINGS_2026-09-08.md).

**Keep whole-run auditing as a research architecture, but this implementation does not satisfy all four requirements together.** Protocol overhead is small and warm replay can be much cheaper than a large batch. Bounded molecular searches still fail the redocking quality gate, preparation dominates complete costs, and work enforcement requires explicit assumptions and a bounded retry policy. This is not deployment-ready admission middleware or an established journal contribution. Returning to full Groth16 would not resolve these bottlenecks.

| Required property | Decision from this experiment |
|---|---|
| Acceptable scientific quality | **Not demonstrated.** Real flexible Vina search improves the rigid bank, but bounded WASM redocking remains at least 3.52 Å; stock Vina reaches 0.48 Å. Pilot AUC confidence intervals include chance. |
| Majority useful computation | **Yes for warm molecular execution; not generally for cold visits.** Search is 94.1–99.2% of warm client time. This is a compute-category fraction, not a fraction of scientifically validated discoveries. |
| Scalable attacker cost | **Conditional.** Disjoint assignments and trace checks reject tested substitutions. Unlimited retries of partial caches defeat the naive economic argument. A global attempt cap bounds that attack but creates recovery/availability costs. No unconditional CPU lower bound is established. |
| Verifier substantially cheaper | **For some warm large batches, not consistently end to end.** At 256 runs/cap 16,000, the molecular search/replay ratio is 14.7×; including ligand setup on both sides reduces it to 2.08×, before shared map initialization, networking and queues. |

## Implemented scientific unit and audit

Each unit fixes receptor/maps, prepared ligand/conformer, search region, exact engine artifact, server seed and evaluation cap. A single-thread Vina 1.2.7 Monte Carlo search performs BFGS optimization with flexible ligand torsions and returns its own best pose. Every run restores the same initial ligand state. Translation, orientation and torsions are searched, unlike the old rigid pose bank. Preprocessing remains outside the replayed search, and its cost is reported separately.

This uses the published Vina search/scoring method with precomputed maps and `no_refine=true`; see the [Vina 1.2 paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10683950/) and [official manual](https://vina.scripps.edu/manual/). The build pins [upstream commit 3c65c0b](https://github.com/ccsb-scripps/AutoDock-Vina/tree/3c65c0b3e6c2c1d183f6a175ecb65e3c5ba91645) and Emscripten 4.0.15. Changes expose reset/run APIs, remove unused dependencies, execute sequentially, collect a natural trace, and feed an E1 unit's positive server seed directly into the search RNG. This avoids compressing unit identities through upstream's smaller internal seed-splitting range. E8 controls preserve upstream seed splitting. Scoring, mutation and BFGS formulas are unchanged. The worker retains one saved pose; its E8 control is not stock default nine-mode Vina.

**Final pose alone has a shortcut.** In 1,056 paired canonical WASM runs, 108 cap-4,000 runs returned the exact same score and pose as cap-16,000 runs, at a median 26.6% of the time. Native controls found 59/1,056 matches for 1,000 versus 4,000 and 131/1,056 for 4,000 versus 16,000. These are final-output plateaus, not full-trace matches.

The committed record therefore contains score, pose, and the sequence of optimized candidate energies/evaluation counts after the first BFGS optimization of each Monte Carlo step. SHA-256 leaves bind units and records; a root binds the leaf vector and lease. **After commitment**, a server CSPRNG chooses distinct complete runs uniformly. Their openings are checked and the selected runs replayed in full, comparing score, pose and trace exactly. This is not sampling individual trace edges or certifying the global minimum.

The trace is an execution fingerprint, not a proof that no faster method can generate the correct record. It catches the measured early-stop shortcut and makes an arbitrary valid pose insufficient. It does not prove minimum CPU time, freshness or biological validity.

### Bounds and reproducibility

Vina checks `max_evals` between Monte Carlo steps. Each step can invoke two local optimizations. The implementation's BFGS limit L and ten line-search attempts give a conservative counted-search bound of cap + 2(1 + 10L), where L = floor((25 + movable atoms)/3). Initialization/postprocessing are separate. This is not a formal bound on every instruction or a wall-clock promise.

Measured WASM counts were 4,001–4,399 for cap 4,000 and 16,001–16,271 for cap 16,000. All scientific runs completed. Evaluation counters themselves are not trusted client testimony.

Native g++ and WASM returned different results for identical numerical seeds in the smoke test; the cause has not been isolated. Exact auditing consequently uses **the same pinned WASM artifact in Chrome and Node**. All 54 browser bundles reproduced identical records across three repetitions, and **46/46 honest selected-run audit transcripts passed**. This is local Chrome/Node evidence, not universal cross-device determinism. The [official FAQ](https://autodock-vina.readthedocs.io/en/latest/faq.html) also makes matching inputs/settings relevant to reproducibility.

## Scientific quality

The pilot uses one [DUD-E FA10 target](https://dude.docking.org/targets/fa10), 16 actives and 16 presumed decoys, selected before earlier docking outcomes by size strata from the first eligible inputs. Ligands contain 23–43 heavy atoms. A separate crystal ligand supplies redocking. Its known bound input conformer makes this an optimistic preparation control, although Vina randomizes placement and torsions; it is not blind cross-docking.

Measured science: **3,168 native runs** over caps 1,000/4,000/16,000 and **2,112 canonical Node/WASM runs** over caps 4,000/16,000, with 32 seeds per ligand including the crystal. Prefixes of 1/2/4/8/16/32 runs are aggregated by lowest score. Browser economics separately executed **2,646 runs over 54 bundles**. Benchmark repeats intentionally reuse work for measurement and are not counted as newly earned scientific credits.

| Runs per ligand | AUC, cap 4,000 | Selected redocking RMSD | AUC, cap 16,000 | Selected redocking RMSD |
|---:|---:|---:|---:|---:|
| 1 | 0.398 | 10.62 Å | 0.508 | 5.35 Å |
| 4 | 0.438 | 10.62 Å | 0.586 | 8.70 Å |
| 16 | 0.523 | 3.52 Å | 0.586 | 8.70 Å |
| 32 | 0.578 | 3.52 Å | 0.598 | 8.70 Å |

At 32 runs, bootstrap 95% AUC intervals are [0.367, 0.773] and [0.379, 0.789]. Both include 0.5. This small single-target pilot cannot establish screening utility across targets, superiority or equivalence to Vina.

No bounded WASM crystal run reached 2 Å. Oracle best RMSD across 32 seeds was 3.52 Å at cap 4,000 and 5.35 Å at cap 16,000. Optimizing an approximate score need not improve geometric quality. Native cap-16,000 prefixes found a 1.63 Å pose, then selected an 8.66 Å pose at longer prefixes. The canonical WASM results determine the deployment-relation conclusion.

Two longer redocking controls recovered the crystal pose:

- **Same WASM, uncapped E8, one saved mode, map/no-refine objective:** 0.443 Å, 96.49 s search, 9,160,224 counted evaluations.
- **Official Vina 1.2.7 executable, uncapped E8, default nine modes and explicit-receptor refinement:** 0.478 Å, 105.57 s total process/preparation/search, score −10.902.

The previous same-pilot native uncapped E1 ranking control had AUC 0.664, CI [0.465, 0.848], versus 0.352 for the old rigid bank. **Full 32-molecule stock-default E8 ranking was not measured.** Historical E1 ranking and new stock E8 redocking are different controls. Redocking uses symmetry-aware RDKit RMSD without pose alignment, with source atom mapping checked against input coordinates.

Combining bounded runs improves some results but does **not** approach conventional Vina redocking at tested budgets. Longer independent runs or scientifically justified local refinement may help; that remains an unmeasured next experiment.

## Economics and two-dimensional difficulty

Client times are medians of three local Chrome 152 repetitions. Warm time includes search/reset/serialization/commitment but excludes ligand and map/module preparation. Each server entry is one actual q=8 challenge, with a different selected ligand mix; it is not a median or throughput result.

| Cap | Ligands × runs | Warm client | Client + ligand setup | Warm molecular fraction | Server warm replay | Server check + ligand setup |
|---:|---:|---:|---:|---:|---:|---:|
| 4,000 | 1 × 16 | 0.332 s | 0.332 s | 97.0% | 0.282 s | 0.284 s |
| 4,000 | 4 × 16 | 1.893 s | 8.184 s | 97.9% | 0.541 s | 11.499 s |
| 4,000 | 16 × 16 | 6.354 s | 29.748 s | 97.6% | 0.193 s | 8.554 s |
| 16,000 | 1 × 16 | 1.348 s | 1.348 s | 98.9% | 0.809 s | 0.812 s |
| 16,000 | 4 × 16 | 7.448 s | 13.763 s | 99.2% | 0.824 s | 5.993 s |
| 16,000 | 16 × 16 | 24.563 s | 47.936 s | 99.0% | 1.659 s | 23.046 s |

The single-ligand tiers fit 200 ms–1.5 s **warm**, but q=8 replays half the 16 assigned runs and offers little margin. At 256 runs/cap 16,000, 24.318 s client molecular work versus 1.659 s replay gives 14.7×. Including ligand setup reduces full-client/full-check ratio to 2.08× and molecular-client/full-check to 1.06×. At cap 4,000, warm molecular ratio is 32.1× but molecular-client/full-check is 0.72×. No warm ratio alone represents the full architecture.

Commitment costs range from about 0.2 to 10.1 ms. In **64 paired alternating-order Node/WASM runs** with trace collection enabled/disabled, all final scores and poses matched. Median traced/plain search ratios were 1.014 at cap 4,000 and 0.986 at cap 16,000. The latter is timing noise, not an acceleration claim. This is a local Node ablation, not an independent-device/browser ablation.

Preparation, bandwidth and memory remain material:

- Maps: **78.68 MB raw / 24.93 MB gzip**. Idealized transfer alone is 19.94 s at 10 Mbps or 1.99 s at 100 Mbps; these are projections, not Internet measurements.
- Actual loopback fetch/import: 0.306 s; map/module/first-ligand initialization: **11.04 s**. The first prepared ligand is reused by small warm tiers.
- Cycling through 16 ligands adds roughly **23–24 s** in Chrome. Server replay also rebuilds selected ligand tables. Only the current ligand's prepared state is retained.
- WASM linear memory grows from **400.10 MB** to **979.37 MB**. This is heap capacity, not sampled peak browser RSS; JS copies and browser infrastructure add memory.
- Largest tier: **17,262 bytes** commitment, **86,486 bytes** for the measured q=8 openings, **2,799,124 bytes** for all scientific records. Full scientific collection is separate from admission openings.

Molecular work is approximately additive in number of ligands × runs per ligand. Resampling measured Node/WASM cap-4,000 runtimes for a fixed 16-unit budget gives cost CV 0.333 for 1×16, 0.160 for 4×4 and 0.071 for 16×1. These are resampling results, not fresh browser trials. Breadth reduces molecular-cost variance and supplies more ranking inputs; depth explores one molecule more. Neither guarantees a better selected pose. Ligand setup currently makes breadth costly for short visits.

For fixed q, molecular replay is O(q × run cost), leaf processing is O(N), and setup depends on up to min(q, number of ligands) distinct inputs. Verification is **not constant time**. A persistent receptor/ligand worker pool could amortize setup, but would incur memory/scheduling costs not measured here. Increasing q improves omission detection while increasing server cost. The browser harness uses synchronous work in a headless renderer; a responsive background-worker product, mobile behavior, production concurrency and deadlines are not implemented or measured.

## Partial work and conditional soundness

For k correct complete records among N committed units and q uniform distinct checks:

P(pass | k correct records) = C(k,q) / C(N,q).

This is **correct-record coverage**, not CPU-time fraction. Unequal ligand costs, choosing cheap units, caches and faster implementations break that identification. The finite attacks below do not establish a universal fastest-algorithm lower bound.

The implemented attacker executes selected real runs and fills omitted records with other computed outputs. The commitment is fixed before sampling. For N=64 and q=8:

| Requested execution fraction | Correct records | Theoretical pass probability | 10,000 mask trials |
|---:|---:|---:|---:|
| 10% | 6 | 0 | 0 |
| 25% | 16 | 0.00000291 | 0 |
| 50% | 32 | 0.002376 | 18 |
| 75% | 48 | 0.085254 | 865 |
| 90% | 57 | 0.373328 | 3,790 |
| 100% | 64 | 1 | 10,000 |

Mask trials resample correctness of actual attack outputs; they are not 10,000 physical molecular replays. Separately, **24 real replay transcripts** cover q=1/4/8/16 for these six fractions. Seven passed: four honest controls, two partial-work q=1 cases and the 90%-work q=16 case. Partial acceptance is expected behavior. One draw per case cannot estimate rare-event probabilities.

Cap-100 and cap-1,000 substitutions for cap-4,000 produced **0/64 matching trace-bound records each**, and both actual challenged transcripts were rejected. Six binding/leaf/root/opening/seed/duplicate-draw tamper cases were rejected. This finite suite does not eliminate all possible trace shortcuts.

### Partial-cache retry attack

An attacker can compute part of an uncompleted cohort once, recommit that cache under new leases, and retry random challenges. With unlimited retries and fixed p>0, eventual success approaches one with **zero additional molecular work per retry**. The usual relative-work expression f/p assumes new science each attempt and is invalid for same-cohort partial-cache retries.

The actual SQLite/CSPRNG retry-policy experiment reused a half-correct N=64 mask at q=8. The legacy policy accepted on **attempt 320**. It exercises real leases, owners, challenges and credit transitions; acceptance is computed from a known correctness mask, not 320 physical Vina replays.

The scheduler now persists a **three-challenge maximum per registered scientific range**, across identities, rejection and post-challenge abandonment. Exhausted uncompleted work leaves the access-credit pool and appears in a recovery queue; it is not falsely completed. The guarded run stopped after three failed challenges, with no credit. Pre-challenge abandonment reveals no random audit and consumes no challenge attempt.

For a fixed partial cache and K independent attempts, success is 1 − (1 − p)^K ≤ Kp. For half-correct N=64/q=8 and K=3 this is about **0.711%**; for 57/64 correct it is about **75.4%**. Under equal costs and new disjoint cohorts after exhaustion, relative science per accepted credit is (k/N) / [1 − (1 − p)^K]. This is not a theorem for adaptive changing bundles or all shortcuts. Small omissions can remain advantageous; not every accepted contributor necessarily executed every run.

The cap trades retry resistance for **work-pool exhaustion/recovery risk**. Anonymous lease flooding, queue overload and deliberately burning challenge budgets remain open. Recovery execution for exhausted uncompleted ranges is not implemented; `record_validation` handles later science for accepted ranges only. Replays after failed submissions themselves perform molecular work, but per-run salvage/accounting is not yet implemented. Global queue budgets and a recovery policy are still needed.

## Campaign identity, precomputation and sharing

The transactional campaign scheduler is retained. Identity binds engine, molecular input hashes, receptor/region and seed range. It rejects overlapping ranges even under changed budgets, campaign names or ligand display aliases, preventing deliberately charging twice for a shared search prefix. Accepted ranges are consumed once. Expired uncompleted ranges can be reassigned only while their challenge budget remains.

| Scenario | Established property or remaining limit |
|---|---|
| Old proof/lease replay | Binding, owner, challenge and state checks reject it. |
| Completed work under a new campaign/ligand label | Scientific identity and overlap checks block reissue. Eleven campaign tests include races, duplicate credit, aliases, expiry and attempt limits. |
| Future uncompleted work computed early | Allowed scientific credit; fresh post-issuance CPU lower bound is zero. Seeds are predictable and future work is precomputable. |
| Shared receptor/grid/ligand preprocessing | Reusable infrastructure, separately accounted; not newly billable independent output. |
| Collusion/shared output caches | One accepted credit per scientific range globally, but workers can split work and share preparation. Faster hardware and cross-identity partial caches are not prevented. |
| Different encodings of equivalent molecular inputs | Trusted preparation/campaign governance remains necessary. Byte hashes do not solve arbitrary semantic duplicate detection. |

A full integration experiment computed 16 runs over four ligands **before obtaining a lease**, then committed, passed q=4 real WASM replay and received one credit. Post-issuance molecular time was **0 ms**; recommitment took 7.58 ms. Pool exhaustion and duplicate-credit rejection were verified. This supports the proposed one-use historical scientific credit model without pretending it proves fresh CPU expenditure.

The candidate property is **one-use coverage credit for previously uncompleted, externally wanted scientific assignments, subject to probabilistic validation**. It is not identity proof or a guarantee of useful discoveries. Campaign demand must be real; repeatedly inventing seeds solely to charge visitors would weaken the scientific-usefulness claim.

## Admission assurance versus scientific trust

Admission sampling checks assigned-run record coverage at a chosen risk threshold. Scientific validation determines whether a screening aggregate is trustworthy. Neither requires proof of the continuous global minimum.

Two implemented attacks escaped their respective admission draws:

- A false score promoted one record to the reported top position. Later replay of each ligand's reported top-one repaired it: four selected replays, **9.59 s** including preparation.
- A true best record was hidden behind a false poor score. Reported-top-one replay selected other records and left the manipulation unrepaired: **10.33 s**.

Top-k validation can remove fabricated winners but cannot alone recover hidden good results. After q admission checks and r additional uniformly chosen distinct checks, a single hidden record is missed with probability 1 − (q+r)/N. Independent trusted replication certifies the replicated jobs; correlated malicious replicas do not. A future policy should iteratively validate reported leaders and randomly replicate other runs or fully replay selected ligand batches. Only the two top-one experiments and trusted validation records are implemented here.

Later validation and recovery cost belongs in overall utility accounting, even if excluded from access latency. Accepted outputs remain provisional. The scheduler's `COMPLETED` means consumed for credit, not that every result has been independently certified.

## Recommendation for the paper

**Whole-run auditing is salvageable as a conditional scientific work-credit research system; the tested bounded-search configuration fails the combined readiness gate.** It removes the large cryptographic client overhead while exposing scientific quality, preparation and retry-policy costs.

The next focused experiment should keep this audit fixed and test longer independent Vina runs or local flexible refinement from independently generated plausible poses. Predeclare quality gates, use multiple targets and independently prepared conformers, and compare stock Vina at matched total budgets. Count pose generation/preparation rather than treating good starting poses as free. Local refinement is defensible only when those refinements are genuinely wanted; it is not equivalent to blind docking.

A receptor-persistent worker pool with reusable ligand state must demonstrate its benefit under memory, cold-start, mobile and concurrent-load constraints. The current 11-second initialization and near-1-GB heap do not support an ordinary short anonymous visit. Specify omission probability, retry/abandonment policy, cost-aware sampling and recovery limits before a positive security claim. Attackers choosing cheap units and adaptive partial caches need evaluation beyond this fixed-mask pilot.

Whole-run spot checks, commitments and the probability formula are established ideas; [volunteer-computing cheat-detection literature](https://wander.science/paper/2011_Wander_CheatDetection.pdf) is relevant prior art. A possible contribution is the measured quality/economics/retry tradeoff and an improved bounded-credit policy, **not spot checking itself**. Novelty has not yet been demonstrated.

Certified optimization remains a comparison, not an automatically superior replacement: a certificate still does not force fresh work or a particular algorithm's cost, and the earlier exact-search proof prototype had unfavorable economics. No tested alternative currently establishes all four properties. Human feedback, participant recruitment and Cloudflare deployment remain deferred until a scientifically and economically credible main workload is demonstrated.
