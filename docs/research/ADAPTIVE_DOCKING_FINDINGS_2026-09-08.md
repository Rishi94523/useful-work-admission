# Adaptive docking admission: implementation and measurements

Experiment begun 8 September; completed 9 September 2026. **Decision: retain independently auditable runs as a research baseline, but the complete useful-work admission architecture does not pass its declared gates.** The outer controller and bulk cost asymmetry work in the local prototype. Scientific quality remains inadequate across the tested targets, cold latency is too large, and record correctness is not a general computational lower bound. No journal-ready security/science contribution is claimed.

## Implemented architecture

The research path now executes `request -> server-side risk -> leased scientific ranges -> Chrome Web Worker -> score/pose/trace commitment -> unpredictable complete-run replay in a separate Node verifier -> atomic risk and scientific-credit update`. The controller is conventional, with transparent weights, SQLite state and fixed thresholds. It is not a bot classifier or a claim to solve Sybil resistance. There is no public HTTP deployment in this experiment.

See the [frozen plan and calibration amendments](ADAPTIVE_DOCKING_PLAN_2026-09-08.md) for the full formula. Low/medium/high assign respectively `1×16×4,000`, `4×16×16,000`, and `16×16×16,000` ligand/run/evaluation-cap bundles, with q=4/8/8 complete-run audits. Success reduces risk; failure, abandonment, retries and request velocity increase it; sufficiently high risk causes cooldown. One outstanding lease per identity, a shared outstanding-work limit, an issuance token bucket and three post-commit challenges per scientific range bound issuance and repeat opportunities. All low/high scientific seed ranges are disjoint.

The v1 low cap of 16,000 proved too slow on varied ligands. Its measurements remain in the evidence. V2 reduces the low cap to 4,000 using the previous browser measurements as a calibration anchor. Neither calibration is a guarantee across devices or molecules.

## Measured preparation optimization

The expensive ligand initialization repeatedly allocated/evaluated identical tables for atom pairs sharing XS atom types. The separate experimental engine shares these tables, keyed by scoring family, weights and table parameters. It preserves the upstream per-entry atom scoring and interpolation operations, uses copy-on-write if tables are widened, and excludes charge-dependent AD4 scoring. This is an engineering optimization, not a new scientific algorithm or proof system.

Across 22 ligand/conformer inputs and two seeded budgets, all **44 serialized score/pose/full-trace records** matched exactly between original, refinement-enabled and shared-table engines (132 executions). This is finite regression evidence, not a proof for every possible molecule or architecture. The original artifacts remain intact.

Real Chrome 152 module-worker clients and a separate Node/WASM verifier produced the following medians over **three optimized bundles per tier**. Client total includes ligand changes and commitment overhead, but excludes one-time cold initialization and internet transfer. The final column includes measured server IPC and SQLite controller/scheduler transactions.

| Tier | Useful molecular search | Client total | Server molecular/replay pipeline total, before IPC/DB | Molecular fraction of client total | Client / full server cost |
|---|---:|---:|---:|---:|---:|
| Low | 0.344 s | 0.355 s | 0.177 s | 97.0% | 1.84× |
| Medium | 6.331 s | 6.400 s | 1.344 s | 98.9% | 4.74× |
| High | 20.716 s | 20.984 s | 1.226 s | 98.7% | 16.39× |

Low client totals ranged **0.330–0.458 s**. High totals ranged **20.867–21.284 s**. The warm majority-molecular gate is met on these measured inputs. The high tier meets the frozen full-server≤20%-of-client gate; the medium tier's median narrowly misses it (about21.1%), and low has only modest asymmetry. Increasing ligand count improves aggregate cost asymmetry once reusable preparation is available; increasing each unit's depth would also lengthen its replay.

Cold initialization remains **10.245 s** in Chrome, plus0.290 s of loopback map fetch. This is not an internet or mobile latency measurement. The optimized WASM heap capacity was **192,872,448 bytes (~184 MiB)** in all nine bundles, versus approximately979 MB in the original larger-ligand worker. Heap capacity is not browser process RSS. Receptor maps remain a large delivery cost. A first-visit short-latency claim is not supported.

Risk timing includes the SQL executed by risk logic; remaining scheduler/transaction time is reported separately in `economics_summary.json`. It is not a fabricated pure CPU versus database split. Protocol commitments/openings, full scientific collection payloads, per-tier heap and cold asset sizes are retained there as distinct measures. Full scientific output upload is separate from the bytes needed to decide admission.

These browser economics use the historical16-ligand FA10 bundle. The new scientific panel uses a different size-stratified selection and adds two targets; its run timings are Node/WASM measurements. A passing science configuration and a passing browser ratio on different input panels are not a measured simultaneous system pass. In particular, molecular-kernel percentage measures where computation goes, not demonstrated downstream scientific value.

## Actual adaptive behavior and simulations

The calibrated actual Chrome loop observed:

| Scenario | Assigned bundles | Accepted | Outcome |
|---|---:|---:|---|
| Honest, normal rate | 3 | 3 | Remained low |
| Valid high-rate submissions | 17 | 17 | Escalated, then cooldown |
| 10% work | 3 | 0 | Cooldown |
| 25% work | 3 | 0 | Cooldown |
| 50% work | 3 | 0 | Cooldown |
| 75% work | 3 | 0 | Cooldown |
| 90% work | 5 | 3 | Experiment reached its five-assignment limit |
| Partial-cache retry | 3 | 0 | Cooldown |

The valid spammer performed **1,952 previously uncomputed seeded runs** in this experiment. Those records are computational outputs, not evidence of 1,952 scientifically valuable discoveries. Logical arrival spacing is controlled to model fast/precomputed submissions; measured serial compute time is not claimed as real high-rate throughput. The optimized engine has separate tier measurements and equivalence checks; the feedback trajectory was measured using the original engine.

Observed molecular cost per accepted request was0.371 s for the honest visitor,11.527 s for the valid spammer, and11.746 s for the90%-record attacker across its three successes. The10/25/50/75% and cached-retry trials spent2.953/7.284/14.218/23.763/16.125 s respectively with zero acceptances. Their observed cost-per-accept statistic is undefined, not proof that acceptance probability is zero. These search-only figures exclude preparation and belong to the original-engine loop; they are not q27 or optimized-tier measurements.

The 90% attack illustrates why sampling does not certify every run. For fixed correct-record count k, `P(pass)=C(k,q)/C(N,q)`. The independent policy simulation includes ten trajectories per fraction/attack combination, honest behavior, abandonment and identity churn; its molecular costs are explicitly modeled from historical browser medians. A separate uniform-sampling simulation uses20,000 draws per tier/fraction. These simulations are not extra molecular benchmarks. Small actual attack counts must not be advertised as precise empirical pass probabilities.

Finite retries reduce cache exploitation, but do not make it impossible. Under a favorable-to-attacker homogeneous fixed-tier model with three chances and a reusable partial cache, minimizing historical work per expected credit yields ratios0.952/0.982/0.980 for low/medium/high versus completing every run. These are analytic examples of small remaining savings, not an implemented adaptive bypass; the real policy can change tier and seed coverage. They also show why a theorem claiming literally every imposed operation was performed would be too strong.

## Stronger sampling: confidence costs real server work

Three additional browser bundles each committed256 runs before independent q=8/16/27/40/57 replay samples. Every selected honest record passed. Samples rotate q order across bundles. No extra credits are minted by this diagnostic. The table reports medians; probabilities are exact hypergeometric calculations for230 correct records out of256, not measured CPU fractions.

| Whole runs replayed q | P(pass with230 correct records) | Measured server replay + local IPC | Client/server ratio in this sweep, with historical DB allowance |
|---|---:|---:|---:|
| 8 | 41.920% | 1.278 s | 30.99× |
| 16 | 17.051% | 2.721 s | 15.38× |
| 27 | 4.694% | 4.095 s | 10.55× |
| 40 | 0.936% | 6.552 s | 6.51× |
| 57 | 0.0966% | 8.738 s | 4.86× |

The extra41.119 ms database allowance comes from the earlier high-tier experiment; the sweep does **not** freshly measure risk/SQLite costs. Its client median is42.493 s, versus20.984 s in the earlier tier test. Chrome changed from152.0.7977.76 to152.0.7977.83; this observation does not establish the cause of the slowdown. Cold browser initialization also rose to19.530 s. Do not combine the two experiments as an audit-induced speedup. As a clearly labeled cross-experiment sensitivity, charging q27 replay plus that DB allowance against the earlier faster client gives approximately5.07×, close to the20% server-cost gate; q40 gives only3.18×. Repeated pinned-browser/device measurements are needed before promising a robust operating point.

The controller now accepts trusted per-tier audit sample settings, including `audit_samples={'high':27}`. Each lease binds its server-chosen q, so the client cannot lower it. Existing defaults remain q4/8/8, keeping previous evidence reproducible. Increasing q addresses omitted records; it does not establish a lower bound on the cost of producing a correct record through another implementation.

The completed stronger-policy simulation adds105 actual SQLite/CSPRNG trajectories with modeled molecular costs. All100 partial-work/cache-attack trajectories reached cooldown. Across ten trajectories per cell, partial/cache admissions were0/0 at10%,25% and50%;8/5 at75%;18/16 at90%. Of47 total attack admissions,36 occurred at the unchanged low tier,10 at medium and one at high. Thus q27 does not silently eliminate lower-tier sampling risk. Modeled molecular cost per accepted request at90% was19.511 s for partial work and18.457 s for cached retries, versus10.869 s for valid high-rate traffic in that simulation. These are small stochastic experiments using homogeneous historical cost scaling, not fresh molecular timing or paired causal estimates of changing q.

## Scientific quality evaluation

The original suite completed **1,398 unique bounded/refinement records** across FA10, HS90A and TRYB1, plus864 actual low-tier follow-up records. FA10 retains72 superseded local timing rows, with corrected source-load/generation/pose-load/refinement costs selected by the analyzer. Each target has8 actives +8 presumed decoys, source/independent crystal redocking, nominally matched global budgets, longer crystal-only runs and bounded flexible local refinement. Stock Vina E8 controls use the same prepared inputs:53 of54 attempts succeeded; HS90A active_00054 timed out at600 s. HIVPR preparation failed on modified residues and remains documented rather than silently excluded.

Each cell below is **score-selected independent-conformer redocking RMSD in Å / ranking ROC-AUC**. A good oracle pose does not replace the actual score-selected result.

| Configuration per ligand | FA10 | HS90A | TRYB1 |
|---|---:|---:|---:|
| 16×4k, actual low tier | 13.025 /0.453 | 1.967 /0.297 | 5.004 /0.484 |
| 16×16k | 9.639 /0.766 | 0.710 /0.297 | 2.909 /0.688 |
| 4×64k | 8.449 /0.781 | 0.514 /0.172 | 10.645 /0.594 |
| 1×256k | 8.449 /0.609 | 0.655 /0.297 | 11.748 /0.641 |
| Four short global starts + local refinement | 13.046 /incomplete | 1.991 /0.266 | 8.671 /incomplete |
| Stock Vina E8, same inputs | 8.760 /0.875 | 0.633 /incomplete | 14.551 /0.656 |

The missing HS90A stock result bounds the completed16-ligand AUC to[0.250,0.375], whatever score the timed-out active would return. It is not defensible to discard the timeout and claim a successful ranking benchmark. Ranking confidence intervals are wide: stock FA10 AUC95% bootstrap interval is[0.641,1.000], TRYB1[0.344,0.891]. Full intervals and top-quartile enrichment are in the summaries. These size-stratified16-ligand pilots do not establish screening performance on full DUD-E.

None of the original configurations passes both frozen aggregate scientific gates: independent redocking≤2 Å on at least2/3 targets, and AUC≥0.65 within0.05 of matched stock on at least2/3. The low-tier pilot fails ranking on every target. The16×16k regime passes ranking only on TRYB1 and redocking only on HS90A. Local refinement retains four outside-grid failures and incomplete FA10/TRYB1 rankings.

Longer source-conformer runs can perform well: score-selected8×1M redocking reaches0.503 Å FA10 and0.206 Å TRYB1. Their independent-conformer counterparts remain8.746 Å and14.599 Å; HS90A is0.652 Å. FA10's independent8×1M pool contains a1.485 Å oracle pose, but its scoring selects a worse pose. Searching longer alone therefore does not guarantee a trustworthy best pose. The1M configurations were crystal-only and have no ranking-quality claim.

### Preparation correction, kept separate from the frozen study

An input audit found44/48 independently embedded ranking conformers had not converged after the original200 MMFF steps. A later, explicitly declared correction continued each of51 independent inputs for at most five2,000-step minimizations, stopping at convergence; all51 converged. A nonzero status requiring further minimization is documented by [RDKit](https://www.rdkit.org/docs/source/rdkit.Chem.rdForceFieldHelpers.html). This is a scientifically motivated post-hoc correction, not a new held-out validation or an excuse to erase the original outcomes.

The corrected-input study evaluates all48 ranking ligands at the same four global budgets, three crystal ligands at those budgets plus8×1M, and matched stock E8. Its final results are recorded separately in `converged_summary.json`. Independent-fragment geometry diagnostics yield relaxed RMSD lower bounds0.288/0.060/0.527 Å for FA10/HS90A/TRYB1. These small lower bounds do not prove attainability or identify the failure cause; they do not support blaming a demonstrated≥2 Å rigid-ring impossibility.

All1,776 corrected ranking runs and135 corrected redocking runs completed. Matched stock controls succeeded in50/51 attempts; HS90A active_00054 again timed out at600 s. The corrected results are:

| Configuration per ligand | FA10 RMSD / AUC | HS90A RMSD / AUC | TRYB1 RMSD / AUC |
|---|---:|---:|---:|
| 16×4k | 10.004 /0.594 | 9.648 /0.172 | 9.774 /0.781 |
| 16×16k | 8.768 /0.766 | 9.655 /0.219 | 12.777 /0.781 |
| 4×64k | **1.567** /0.766 | **0.656** /0.219 | 10.751 /0.547 |
| 1×256k | 8.774 /0.797 | **0.549** /0.281 | 11.380 /0.672 |
| Stock E8 | 8.764 /0.844 | **0.671** /incomplete | 9.402 /0.734 |

The incomplete corrected HS90A stock AUC is bounded by[0.219,0.344]. Corrected FA10 stock AUC95% bootstrap interval is[0.578,1.000], TRYB1[0.453,0.969]. Four64k runs pass redocking on2/3 targets, but pass the full ranking gate on0/3: FA10's0.766 AUC falls more than0.05 below its matched0.844 baseline. The other three budgets pass ranking on only1/3 and redocking on0/3,0/3 and1/3 respectively. **No configuration passes the two aggregate science gates, and no corrected configuration passes both metrics on even one same target.** Corrected8×1M crystal-only RMSDs remain8.774/0.554/8.493 Å, with no ranking experiment at that budget.

Correcting preparation changes outcomes substantially; it does not rescue the tested architecture. Stock shares FA10/TRYB1 independent-conformer failures, so these are not uniquely caused by bounding Vina. Likewise, bounded4×64k finds a much better FA10 pose than stock in this small experiment. The evidence supports a joint input/preparation/scoring/search-quality limitation, not a universal assertion that Vina, docking, or independently seeded search cannot work.

### Which difficulty dimension helps?

At matched nominal256k evaluations, corrected per-ligand median Node/WASM call times are3.04/3.06/2.97 s for FA10 at16×16k/4×64k/1×256k;2.74/2.67/2.41 s for HS90A;3.38/3.29/3.23 s for TRYB1. This supports roughly budget-proportional cost on these inputs, while the scientific outcomes differ markedly. Across individual molecules the same nominal budget takes1.33–5.55 s. A count of ligands or evaluations is not a universal latency or attacker-cost calibration.

The corrected runs also expose soft-cap overshoot: maximum excess evaluations were343/473/195/142 at nominal4k/16k/64k/256k. Vina checks its budget at search boundaries; the nominal cap is not an exact evaluation ceiling or a hard access deadline.

Once a scientifically validated minimum per-unit search budget exists, increasing independent ligand/run count is the preferable economic dimension: fixed q can keep replay roughly level while collecting more distinct outputs. Deepening each sampled unit makes its replay more expensive. However, simply multiplying poor short searches does not establish scientific marginal value. The16-ligand browser economics and the new three-target Node science panel must be jointly benchmarked before selecting production tiers. No valid short-latency scientific configuration is established here.

The local-refinement adapter initially failed because Vina's ensemble output wrappers were passed back into its single-ligand parser. The adapter now strips only `MODEL`/`ENDMDL` records while retaining coordinates and torsion metadata. Completed global-search rows are resumed without rerunning them. The science gates remain unchanged.

Scientific comparisons intentionally reuse some seeds across caps; they are diagnostic runs and do not earn separate campaign credits. Comparative execution counts are not counts of previously unexplored production science. Actual admission tiers use disjoint seed ranges.

## Verification and paper boundary

The [verification analysis](DOCKING_VERIFICATION_ANALYSIS_2026-09-08.md) separates core computational shortcuts, outer retry/rate controls, provisional scientific trust and one-use historical work accounting, with primary-source prior art. A hash/fingerprint of invented states cannot authenticate molecular evaluations. The tested binary/base64 trace encoding was lossless but slightly **larger after gzip** (1,046,948 vs1,034,865 bytes for256 records); it is not adopted as an improvement. All256 shorter-run traces were prefixes of longer ones, while none were complete matching records. This reinforces the scheduler's ban on separately crediting nested budgets.

A second representation preserves float64 energy bits and delta-encodes the exact integer evaluation counters. All256 round trips matched; the gzip payload fell to834,636 bytes, **19.3% below gzipped JSON**. This is an archived-data encoding experiment, not an integrated production transport or a reduction in replay cost. It adds no cryptographic soundness.

No docking-specific succinct verification construction or general computational lower bound has been established. Public accumulators, RNG evidence and disconnected local blocks have identifiable shortcomings. Sumcheck/GKR remains a possible future arithmetic-relation project, with unmeasured Vina overhead. Full Groth16 is not the default direction.

## Final simultaneous-gate decision

| Requirement | Decision and evidence |
|---|---|
| Honest warm execution around200 ms–1.5 s | **Measured on the historical browser panel:**0.330–0.458 s optimized low tier; not established for first visits, the corrected panel or other devices |
| Increasing risk imposes increasing attacker cost | **Implemented and observed conditionally:**valid spam progresses through tiers and cooldown; fractional-work simulations/actual attacks incur failures. No general lower bound against a cheaper correct-record algorithm |
| More than80–90% useful client computation | **97–99% molecular-kernel time measured; scientific usefulness not established.** These two percentages must not be equated |
| Verifier substantially cheaper than client | **High-tier local q8 pass:**16.39× full measured ratio. Medium narrowly misses20%; q27 adds meaningful replay cost and lacks a robust same-panel/device replication |
| Scientifically defensible bounded-search quality | **Fails the declared multi-target gates**, including the preparation correction and longer-run/local controls |
| Retry grinding becomes a bounded outer-policy problem | **Instantiated, not eliminated:**three range challenges, risk escalation, capacity limits and cooldown; trusted identity continuity and shared ledger assumed; identity churn/fairness remain open |
| Completed work cannot earn repeated credits | **Tests establish one-use accounting within the registered SQLite domain.** Chemical/engine equivalence, durable output availability and distributed deployment remain additional requirements |

**Recommendation:** keep whole-run auditing and the transparent controller as the experimental baseline; do not return to full Groth16 or claim the current implementation is a journal-ready useful-work CAPTCHA. The next worthwhile docking milestone is an independently validated, target-specific scientific campaign with defensible starting conformers/scoring and actual external demand. Only after it passes scientific gates should its exact inputs and search settings be used for new browser tier/audit/deadline measurements. This report stops the declared configuration search rather than continuing to tune until a pilot threshold passes.

For a security paper, the potential contribution is an evidence-backed systems study of adaptive one-use scientific work credit, confidence/cost tradeoffs and failure boundaries. Existing spot-checking/reputation mechanisms and the shared-table optimization are not new proof primitives. Novelty still needs a substantive improvement or generalizable result against that prior art; certified optimization is not automatically a stronger work-enforcement architecture merely because a returned witness is easy to verify.

Before a deployment or positive paper claim, integrate durable full-output ingestion-before-credit and later scientific repair, measure the cost of those stages, test faster/heterogeneous and shared-cache attackers, pin and replicate browser/device performance, and evaluate real network/concurrency/deadlines. The local admission harness currently receives full records in memory and stores provisional verdict metadata; it does not provide an operational scientific ingestion service. Human feedback and Cloudflare deployment remain deferred under the current scope.

Validation:19 controller/campaign tests and the whole-run protocol security regressions pass; all60 existing grid hashes verify;16 compressed scientific/input archives pass their hash and restore checks. Scientific logs, failures, confidence intervals, original and corrected cohorts, graphs and reproduction commands are published in the [evidence bundle](../evaluation/adaptive_docking_2026-09-08/README.md). These checks do not substitute for an independent clean-machine or production replication.
