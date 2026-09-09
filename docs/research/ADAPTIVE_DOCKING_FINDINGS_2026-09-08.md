# Adaptive docking admission: implementation and measurements

Experiment begun 8 September; resumed 9 September 2026. **Checkpoint status: the adaptive controller and shared-preparation economics are measured; multi-target scientific evaluation is still running. No combined journal-readiness decision is claimed yet.**

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

The 90% attack illustrates why sampling does not certify every run. For fixed correct-record count k, `P(pass)=C(k,q)/C(N,q)`. The independent policy simulation includes ten trajectories per fraction/attack combination, honest behavior, abandonment and identity churn; its molecular costs are explicitly modeled from historical browser medians. A separate uniform-sampling simulation uses20,000 draws per tier/fraction. These simulations are not extra molecular benchmarks. Small actual attack counts must not be advertised as precise empirical pass probabilities.

Finite retries reduce cache exploitation, but do not make it impossible. Under a favorable-to-attacker homogeneous fixed-tier model with three chances and a reusable partial cache, minimizing historical work per expected credit yields ratios0.952/0.982/0.980 for low/medium/high versus completing every run. These are analytic examples of small remaining savings, not an implemented adaptive bypass; the real policy can change tier and seed coverage. They also show why a theorem claiming literally every imposed operation was performed would be too strong.

## Scientific quality evaluation

Pending completion. The predeclared suite uses FA10, HS90A and TRYB1, independently prepared conformers, 8 actives +8 presumed decoys per target, source/independent crystal redocking, nominally matched global budgets, longer crystal-only runs and bounded flexible local refinement. Stock Vina E8 controls use the same prepared inputs. HIVPR preparation failed on modified residues and remains a documented failure rather than a silently excluded success.

The local-refinement adapter initially failed because Vina's ensemble output wrappers were passed back into its single-ligand parser. The adapter now strips only `MODEL`/`ENDMDL` records while retaining coordinates and torsion metadata. Completed global-search rows are resumed without rerunning them. The science gates remain unchanged.

## Verification and paper boundary

The [verification analysis](DOCKING_VERIFICATION_ANALYSIS_2026-09-08.md) separates core computational shortcuts, outer retry/rate controls, provisional scientific trust and one-use historical work accounting, with primary-source prior art. A hash/fingerprint of invented states cannot authenticate molecular evaluations. The tested binary/base64 trace encoding was lossless but slightly **larger after gzip** (1,046,948 vs1,034,865 bytes for256 records); it is not adopted as an improvement. All256 shorter-run traces were prefixes of longer ones, while none were complete matching records. This reinforces the scheduler's ban on separately crediting nested budgets.

No docking-specific succinct verification construction or general computational lower bound has been established. Public accumulators, RNG evidence and disconnected local blocks have identifiable shortcomings. Sumcheck/GKR remains a possible future arithmetic-relation project, with unmeasured Vina overhead. Full Groth16 is not the default direction.

The current evidence supports continuing a systems investigation: preparation reuse materially repairs bulk economics, while the outer layer makes retry assumptions concrete. Scientific quality, cold/device latency, stronger adversarial cost analysis and a defensible contribution remain necessary before recommending journal submission. A final simultaneous-gate decision will follow the completed scientific controls.
