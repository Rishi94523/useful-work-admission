# Lightweight docking evidence

Investigation started 7 September 2026 and completed 8 September local time. Directory names retain the starting date. See the [report](../../research/LIGHTWEIGHT_DOCKING_WORK_2026-09-07.md), [derived tables](tables.md), [figure](tradeoffs.png), and [source ledger](../../research/LIGHTWEIGHT_DOCKING_SOURCES_2026-09-07.json).

This is a research artifact, not deployed admission middleware. Molecular-kernel time is only a proxy for useful time; the current coarse bank fails scientific quality checks. Post-commit sampling limits acceptance of many incorrect records under stated assumptions. It does not prove fresh CPU expenditure or an exact global minimum.

## Files

- `sources.json`, `ligands.json`, `assets.json`, `native_build.json`: downloaded inputs, pre-outcome selection, preparation and build provenance. PDBQT hashes in ligand records hash canonical LF text produced by Meeko; map and receptor hashes are file-byte hashes.
- `science.json`: 32 molecules, 4,096/16,384/65,536-pose banks, capped Vina E1/E4, 128 independent native floating-grid checks, integer quantization error and atom-count calibration.
- `uncapped_controls.json`: same 32 molecules with uncapped Vina E1; known-bound-conformer redocking compared with Vina E4. The latter is explicitly an optimistic redocking control.
- `node_bench.json`, `chrome_bench.json`, `node-extended_bench.json`, `chrome-extended_bench.json`: three repetitions per architecture/tier, 1/4/16 ligands, 256/1,024/4,096 poses, plus 16,384 for B/C. E is not extended because its extra checking/transfer already performs poorly.
- `verification.json`: 198 real committed audit transcripts verified across Node/Chrome; 52 malformed/tampered variants rejected. This count is transcripts, not 198 complete bank recomputations.
- `attacks.json`, `attack_verification.json`: actual partial scoring and wire attacks, 10,000-trial simulations of correctness masks, coarse-corner guessing, fresh-commit cache reuse and hiding a true minimum. The 16-ligand partial-cost row is kernel measurement plus an analytical bound, not a complete wire attack.
- `native_kernel.json`: optimized C++ control for the same integer scoring objective. All output atom records agree with Python for 16 ligands at 32/4,096 poses; six warm repeats after one cold repeat.
- `integration.json`: real Node computation, Python verification and SQLite lease/challenge/credit flow for two bundles/four jobs, with replay rejection and pool exhaustion.
- `cache.json`: exact pose and interpolation-query overlap across two disjoint ranges for four ligands. Zero observed hits does not establish a universal anti-cache guarantee.
- `process_memory*.json`: 50 ms process-tree memory samples for complete benchmark suites. Includes the Node harness retaining transcripts and Chrome infrastructure; not per-task peak memory. Owned typed-array sizes are separately recorded per tier.
- `summary.json`, `tables.md`, `tradeoffs.png`, `tradeoffs.svg`: derived results and conditional analytical bounds. Network transfer times are projections from measured compressed sizes.

## Reproduction

The native Vina build reuses the pinned Vina 1.2.7 source/Boost objects from the [earlier pilot](../docking_pilot_2026-09-06/README.md). This artifact assumes that prerequisite has been built. Large third-party inputs, maps, dependency wheels, binaries and raw transcript bodies live under ignored `tmp/docking-audit/`; they are reconstructed, not published here. No secrets or personal participant data are required.

Environment used: Windows x64, Python 3.14, Node 24.4, Chrome 152, g++ 14.2; isolated RDKit 2025.9.6, Meeko 0.7.1, Gemmi 0.7.5. Native build flags and binary/source hashes are recorded. Python NumPy/SciPy and Matplotlib are required. Browser scripts currently reference this machine's installed Chrome and bundled Playwright paths; adapt those two paths on another machine.

```powershell
python scripts/fetch_lightweight_docking_data.py
python -m pip install --target tmp/docking-audit/deps --only-binary=:all: --no-deps rdkit==2025.9.6 meeko==0.7.1 gemmi==0.7.5
python scripts/prepare_lightweight_ligands.py
$env:PYTHONPATH=(Resolve-Path tmp/docking-audit/deps).Path
python -m meeko.cli.mk_prepare_receptor --read_pdb tmp/docking-audit/receptor_heavy.pdb -o tmp/docking-audit/receptor -p
python scripts/build_campaign_grid_worker.py
python scripts/build_lightweight_assets.py
python scripts/evaluate_lightweight_science.py --fresh
python scripts/evaluate_lightweight_controls.py
python scripts/run_lightweight_benchmarks.py
python scripts/run_lightweight_benchmarks.py --extended
python scripts/verify_lightweight_bench.py node chrome node-extended chrome-extended
node scripts/attack_lightweight_docking.mjs
python scripts/verify_lightweight_attacks.py
python scripts/test_lightweight_integration.py
python scripts/analyze_lightweight_cache.py
python scripts/benchmark_lightweight_native.py
python -m unittest research.tests.test_docking_campaign -v
python scripts/analyze_lightweight_results.py
```

Run timing suites sequentially. Uncapped Vina takes several minutes. Its script resumes completed entries from `uncapped_progress.json` if present; those progress files are local intermediate files and not release evidence. Random challenges are freshly generated, so individual attack successes/timings and transcript roots vary on rerun. Preparation timings embedded in metadata also make the overall metadata hash run-specific; molecular inputs, numeric specification and map hashes provide the reproducibility anchors.

Client timing separates a three-run score-only reference median from the actual scoring/commit/open path. The reference reruns are diagnostic and excluded from reported deployed-client cost. Client cost excludes asset loading, job dispatch and network RTT. Server timings cover already-parsed Python verification; SQLite operations are separately measured. New website/HTTP production behavior, devices, GPU performance and human participants were not measured.
