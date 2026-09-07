# Docking pilot: real search, cached rescoring and effort-cheating

Experiments began 6 September and completed 7 September 2026 on one Windows desktop. This directory contains measured research evidence, not a deployed admission service or a biological discovery. All three ligand/receptor pairs are existing public Webina benchmark examples.

## Real docking checkpoint

- `native_scaling.json`: 63 official Vina 1.2.7 searches and 63 independent CLI score attempts. Search varies exhaustiveness, evaluation cap and seed. Fresh process timings include preparation.
- `browser_scaling.json`: 12 actual Chromium runs using pinned Webina (Vina 1.2.3), at exhaustiveness 1/4 and a 1,000-evaluation cap. `browser_full_search.json` adds one uncapped E=1 run. Versions and timing boundaries differ from native: do not interpret their ratio as a WASM speedup.
- `verification.json`: full local warm checking of all 76 returned poses, three warmed native search baselines and explicit attack diagnostics. Includes input validation, canonical reconstruction, file/IPC transport, pose preparation and native scoring. It excludes HTTP, authentication and production queuing. One boundary pose is rejected by both stock Vina and our cache wrapper; it remains in the evidence.
- `pose_corpus.json`: all 76 generated pose serializations and SHA256 hashes, for independent rescoring without repeating every search. These are public benchmark derivatives, not new ligand/protein discoveries.
- `inputs_manifest.json`, `build_inputs.json`, `native_build.json`: pinned source/download references, hashes, compiler and cache patch identity.
- `native_smoke.json`, `browser_smoke.json`: preliminary smoke runs, excluded from main sample counts. `verification_rebuild_partial.json` preserves an earlier, slower implementation that rebuilt same-ligand pair tables.

The cache reuses Vina pair tables for the same ligand atom identities and rigid receptor. The Python envelope additionally binds atom identities, charges, torsion tree and approximate local geometry. All 62 valid native outputs agree with separate stock CLI rescoring within 0.0005 kcal/mol (the CLI prints three decimals). This does not establish complete chemical validation.

Correct scoring does **not** prove the assigned search occurred. All three low-effort substitutions pass the candidate predicate; tiny translations also pass while changing exact hashes. Invented scores and the tested malformed envelopes are rejected. This code must not mint admission credits from a claimed exhaustiveness value.

## Reproduce the real docking experiment

Run from the repository root. Requires Python with NumPy, Node, Chrome/Chromium and Playwright. Building the native wrapper currently targets Windows with a UCRT MinGW `g++`; the Boost archive extractor requires Python's Zstandard-capable tar support (tested on Python 3.14). Fetchers place public dependencies under ignored `tmp/docking-pilot`; no global environment changes are needed. Internet access is required for first downloads.

```powershell
python scripts/fetch_docking_pilot.py
python scripts/fetch_docking_build_deps.py
python scripts/build_docking_worker.py
python scripts/benchmark_docking_pilot.py
# Set these to installed locations on your machine:
$env:PLAYWRIGHT_MODULE='C:\path\to\node_modules\playwright'
$env:CHROME_PATH='C:\Program Files\Google\Chrome\Application\chrome.exe'
node scripts/benchmark_docking_browser.mjs
node scripts/benchmark_docking_browser.mjs --full-search
python scripts/verify_docking_pilot.py
python -m unittest research.tests.test_docking_contract -v
```

To rescore the published corpus, replace the two search benchmark steps and browser runs with `python scripts/archive_docking_poses.py` after fetching inputs and building the worker. The restore checks hashes and refuses to overwrite different local results. To archive newly generated runs, use `--export`. Reruns update timing JSONs; preserve a copy if comparing runs. The six unit tests require the downloaded reference and one generated/restored pose and otherwise report a skip.

The native scorer is a local trusted-process benchmark: shared temporary paths, synchronous IPC and no per-request hard timeout. It is not concurrency safe or suitable as an exposed API. The browser harness listens only on loopback and serves an explicit asset allowlist.

## Groth16 comparison

The [feasibility report](../../research/DOCKING_GROTH16_FEASIBILITY_2026-09-07.md) compares real docking with an actual proof experiment for a **reduced integer contact-search model**. It does not prove execution of Vina. Proof timing, scientific usefulness, candidate integrity and resistance to effort cheating are separate claims.

`zk_native.json` and `zk_browser.json` record final contributed-setup timings. `zk_public_proofs.json` includes the public verification keys and six proofs for independent checking. `zk_setup.json` records circuit/setup steps. `zk_degenerate_setup_diagnostic.json` is a deliberately retained failed earlier experiment: the original uncontributed setup accepted statement changes. Do not use its timings or apparent validity as final evidence. All keys are development-only.

To verify the published public proofs without performing setup:

```powershell
npm.cmd ci --prefix research/docking-zk
node scripts/verify_docking_zk_evidence.mjs
```

To regenerate proofs, after fetching the docking inputs:

```powershell
python scripts/fetch_docking_circom.py
python scripts/prepare_docking_zk.py
node scripts/benchmark_docking_zk.mjs
# Uses the same PLAYWRIGHT_MODULE and CHROME_PATH settings as above.
node scripts/benchmark_docking_zk_browser.mjs
python scripts/summarize_docking_pilot.py
```

Setup took several minutes on this machine, including about 402 seconds for phase-two preparation. New setup randomness produces different keys/proofs; the checked-in public corpus remains the original run. `source_manifest.json`, `environment.json`, `summary.json` and `cost_comparison.png`/`.pdf` support the final comparison. Downloaded dependencies, setup files and proving keys stay under ignored directories. No human or production website is deployed by these scripts.

## Attribution

Inputs and browser runtime come from [Webina](https://github.com/durrantlab/webina); native scoring/search uses [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina). Exact commits and upstream license download URLs are in the manifests. Follow upstream citation/license requirements when redistributing or publishing work using them. No third-party executable, proof setup secret or downloaded dependency directory is included in this checkpoint.
