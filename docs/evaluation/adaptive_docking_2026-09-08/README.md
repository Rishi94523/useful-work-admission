# Adaptive docking evidence

Experiment begun 8 September and continued 9 September 2026. Read the [findings](../../research/ADAPTIVE_DOCKING_FINDINGS_2026-09-08.md), [frozen gates](../../research/ADAPTIVE_DOCKING_PLAN_2026-09-08.md), and [verification/threat analysis](../../research/DOCKING_VERIFICATION_ANALYSIS_2026-09-08.md). This is a local research prototype, not a public admission service or biological discovery claim.

Completed scientific evidence:4,173 unique bounded/refinement records (including retained failures),72 superseded local timing rows, and105 distinct stock-control attempts across original/corrected inputs. Stock succeeded in103 attempts; the same HS90A ligand timed out once in each preparation cohort. All16 scientific/input archives verify and restore, totaling2,963,066 compressed bytes. The declared science gates fail in both cohorts; this is a completed negative result, not an unfinished tuning run.

## Evidence map

- `adaptive_loop.json`: original Node-client v1 calibration. The low cap16k was too slow on varied ligands. All seven scenarios completed; a process-shutdown timeout occurred after results were saved. That timeout did not invalidate or duplicate the stored molecular runs.
- `adaptive_loop_calibrated.json`: real Chrome152 module-worker client, independent Node/WASM verifier and SQLite outer controller. Eight scenarios including90% partial work. The logical request clock models arrival behavior; it is intentionally distinct from molecular wall-clock time. CSPRNG challenge draws and actual outcomes are archived.
- `policy_simulation.json` / `policy_simulation_calibrated.json`: v1/v2 actual SQLite/CSPRNG policy transitions, with known correctness masks and **modeled** molecular costs from historical browser medians. These are105 stateful scenario trajectories each, not105 fresh Vina trials. The v2 identity-churn trial reaches the shared issuance budget; its first39 identities obtain credit.
- `cached_tier_economics.json`: three actual Chrome-client/Node-server bundles at each tier with shared XS scoring tables. Initial risk is set to a controlled tier value. This measures tier costs, not another end-to-end risk trajectory. All nine sampled audits passed.
- `build_wasm_adaptive.json`, `build_wasm_type_cache.json`: compiler options, exact upstream patch hashes and generated artifact hashes. Original `whole_run.wasm` remains separate. The refinement export changes the API, while table sharing changes storage/preparation; neither intentionally changes global-search arithmetic.
- `engine_equivalence.json`, `equivalence_*.json`:44 input/seed/budget cases run under each of three engine variants,132 executions. Score, pose and complete natural-trace serialized hashes match. Includes16 historical ranking ligands and source/independent crystal inputs for three targets. Finite regression evidence, not a proof over all inputs or engines.
- `science_inputs.json`: pre-outcome selection, provenance URLs/hashes, independent conformers, preparation status and maps for FA10/HS90A/TRYB1. HIVPR's modified-residue preparation failure is retained. There are8 actives+8 presumed decoys per prepared target, plus crystal redocking input. The benchmark is deliberately small and size-stratified, not a representative full DUD-E evaluation.
- `science_<target>.jsonl`: canonical Node/WASM scientific runs, poses, scores, counters, timing and trace digests. These are not browser latency measurements. Four local runs per conformer use short global generation followed by at most200 local steps. `cost_schema:2` includes reloading the source ligand, generation, reloading the generated pose, and refinement. Superseded same-key measurements remain in the raw log; the analyzer selects the latest. A failed local refinement remains failed rather than silently disappearing.
- `stock.jsonl`: official Vina1.2.7, CPU1, E8, nine modes and default explicit-receptor refinement on the same prepared ligand inputs. Three independent control processes run concurrently; their recorded wall times include contention and **are not isolated performance measurements**. Failures/timeouts are retained. Stock and canonical grid-only bounded search are distinct algorithms/settings; comparisons must say so. Use `--workers 1 --output stock_serial.jsonl` for a separately stored isolated replication.
- `science_summary.json`: score-selected and oracle symmetry-aware RMSD, independent-conformer ranking, bootstrap intervals, top-quartile enrichment, gate flags and failures. Incomplete configurations are not promoted to successful full evaluations. Long-run crystal results are not evidence of long-run ranking quality.
- `low_science_<target>.jsonl.gz`:288 records per target for the actual16×4k low tier on the original inputs. This follow-up was declared after the primary bounded outcomes and uses the shared-table engine. It is not part of the matched256k comparison.
- `converged_inputs.json`: further MMFF relaxation of all51 independent inputs, retaining original hashes, convergence statuses and energy changes. All51 converged. The original200-step preparation had44/48 non-converged ranking inputs; original crystal statuses were not recorded. This correction is post-hoc and was declared before the corrected docking outcomes.
- `converged_redocking_<target>.jsonl.gz`:45 runs per target:16×4k,16×16k,4×64k,1×256k,8×1M on the corrected crystal conformer. `converged_ranking_<target>.jsonl.gz` contains592 runs per target on the48 corrected ranking inputs, excluding1M. These use the equivalence-tested shared-table WASM; they are Node, not browser, quality runs.
- `stock_converged_all.jsonl.gz`:51 matched E8 control attempts, including the three earlier `stock_converged_crystal.jsonl.gz` controls exactly once. The two files overlap; do not count them as54 new attempts. `converged_summary.json` reports corrected rankings, redocking, failure bounds and gate counts separately from the original experiment.
- `audit_confidence.json`:three actual new256-run Chrome bundles, each committed before q8/16/27/40/57 complete-run replay. Every honest audit passed. This sweep has no risk/SQLite stage and issues no duplicate work credits. Its browser version is152.0.7977.83 versus152.0.7977.76 in the earlier optimized tier test; observed client time roughly doubled for an unproven reason. Cross-experiment faster-client/stronger-verifier ratios are sensitivity projections, not paired observations.
- `policy_simulation_stronger_audit.json`:105 further stateful SQLite/CSPRNG trajectories with trusted high-tier q27. Molecular costs remain modeled from historical browser medians. It is not another live molecular feedback loop.
- `conformer_geometry.json`:relaxed independent-rigid-fragment lower bounds, graph automorphisms and geometry sanity checks. Small lower bounds do not prove physical attainability or explain the redocking failures.
- `fingerprints.json`: archived-record diagnostics and lossless encoding tests, with explicit algebraic/local-splice counterexamples. Expected archived outputs are an oracle for these diagnostics; no new molecular replay time is claimed.
- `economics_summary.json`: observed costs, policy simulations, uniform sampling probabilities and fixed-cache/heterogeneous-cost sensitivity **separated by scope**. CPU fractions, correct-record fractions, provisional outputs and verified science are not interchangeable.
- `adaptive_economics`, `adaptive_science`, `converged_science`, `audit_confidence` `.png/.svg`:descriptive figures. Three bundle repetitions are not sufficient for robust tail-latency claims. Scientific confidence intervals reflect only resampling this small pilot.
- `transcripts.json` and `*.jsonl.gz`:archive and raw-content hashes. `prepared_inputs.json.gz` contains the prepared receptor PDBQT and source/independent/corrected ligand SDF/PDBQT files needed to reproduce RMSD analysis. Large maps and toolchains are omitted; the restore script reconstructs missing maps and requires exact manifest hashes. No raw large logs need to be tracked in Git.

No phone/Firefox/Safari, real participants, public network, production queue throughput, actual request-deadline loading, global chemical canonicalization, multi-region ledger, or generic Sybil resistance is established. Small summary/test activity occurred during some measurements; expensive benchmark stages ran sequentially. WASM heap capacity is reported, not whole-process peak RSS. Risk-processing timings include its SQL calls; remaining transaction/scheduler time is separate.

The stock-quality stage is the explicit exception to single-process scheduling: three independent CPU1 controls run concurrently, after the primary cost benchmarks and bounded-search stage. Those stock wall times must not be mixed into the isolated cost ratios.

The scientific comparison deliberately reuses seeds across caps to study search depth and uses known public benchmark molecules. These comparative reruns and engine-equivalence repetitions are **not newly credited scientific assignments**. Actual admission experiments use disjoint low/high seed ranges. Benchmark execution counts must not be conflated with a count of globally novel discoveries or redeemed production work.

Admission receives complete records in local harness memory and persists provisional verdict metadata, but durable scientific ingestion-before-credit and downstream aggregate repair are not integrated. Science benchmark poses are archived separately. The local server timings therefore exclude a production durable output store and later scientific repair.

## Reproduction

Use the [whole-run prerequisites](../docking_whole_runs_2026-09-08/README.md) to reconstruct pinned Vina source, Emscripten4.0.15, Boost, historical maps/ligands and archived browser records. Main software: Python3.14.4, Node24.4.0, Chrome152.0.7977.76, NumPy2.4.4, SciPy1.17.1, RDKit2025.9.6, Meeko0.7.1 and Gemmi0.7.5 on Windows11. Keep the pinned canonical WASM artifact for replay compatibility; native and WASM floating-point search are not interchangeable by assumption.

Preserve existing evidence before running commands that overwrite it. Scientific and stock scripts resume rows; the main driver intentionally reruns live loops unless `--science-only` is supplied. Use a separate output/workspace copy for independent replication. Machine-specific browser/Playwright defaults can be overridden by `CHROME_PATH` and `PLAYWRIGHT_MODULE`.

To inspect the completed release without redocking:

```powershell
python scripts/unpack_whole_run_evidence.py
python scripts/unpack_adaptive_evidence.py
python scripts/analyze_adaptive_science.py
python scripts/analyze_converged_redocking.py
python scripts/analyze_conformer_geometry.py
# Economics also needs the historical local grids/toolchain artifacts for asset sizes.
python scripts/analyze_adaptive_economics.py
python scripts/plot_adaptive_docking.py
```

The unpacker validates compressed/raw hashes and refuses to overwrite different files. Prepared inputs are restricted to `tmp/adaptive-docking`. `prepare_adaptive_science.py` preserves existing manifests and does not automatically recreate missing cached assets. After unpacking, use `python scripts/restore_adaptive_maps.py` to reconstruct missing maps from the pinned grid-worker executable and verify all60 map hashes. The present run checked existing hashes; this checkpoint does not claim a fresh independent clean-machine installation.

```powershell
python scripts/prepare_adaptive_science.py
python scripts/build_whole_run_vina.py --adaptive
python scripts/run_adaptive_science.py
# Resume only the science/stock stages after an interruption:
python scripts/run_adaptive_science.py --science-only
python scripts/analyze_adaptive_science.py
python scripts/analyze_adaptive_economics.py
python scripts/plot_adaptive_docking.py
python -m unittest research.tests.test_adaptive_admission research.tests.test_whole_run_campaign research.tests.test_docking_campaign
node scripts/test_whole_run_protocol.mjs
```

Run the declared follow-ups sequentially after the original suite; stock uses three independent CPU1 jobs and retains a600-second timeout per attempt:

```powershell
node scripts/benchmark_low_tier_science.mjs
python scripts/benchmark_audit_confidence.py
python scripts/prepare_converged_inputs.py
node scripts/benchmark_converged_redocking.mjs
python scripts/benchmark_adaptive_stock.py --converged-crystal --output stock_converged_crystal.jsonl
node scripts/benchmark_converged_ranking.mjs
python scripts/benchmark_adaptive_stock.py --converged-all --output stock_converged_all.jsonl
python scripts/evaluate_adaptive_policy.py --stronger-audit
python scripts/analyze_adaptive_science.py
python scripts/analyze_converged_redocking.py
python scripts/analyze_adaptive_economics.py
python scripts/plot_adaptive_docking.py
python scripts/package_adaptive_evidence.py
python scripts/unpack_adaptive_evidence.py
```

The controller's default remains q4/8/8. Trusted initialization with `audit_samples={'high':27}` selects the measured stronger high-tier sample count; leases store q and reject client overrides. Sampling/ledger tests and protocol regression commands above are required checks for this change. Gzip archives are deterministic (`mtime=0`); verify `transcripts.json` before consuming them.

`--legacy-calibration` on `benchmark_adaptive_loop.py` reproduces the original cap16k low-tier policy with a Node client. The default calibrated run uses Chrome. `benchmark_cached_admission.py` requires a successful `check_adaptive_engines.mjs` result and the separate shared-table build. The trusted local IPC adapter is an experiment harness; exposing its verdict or ledger-finalization methods to untrusted clients would break the trust boundary.

The source/input URLs and hashes are public scientific data. Toolchains, local package caches, credentials and personal project files are not part of this evidence release. Cold delivery is a separate deployment concern: loopback map-fetch time is not a prediction of internet download time.
