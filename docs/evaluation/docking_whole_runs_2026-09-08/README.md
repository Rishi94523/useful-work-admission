# Bounded whole-run Vina evidence

Completed 8 September 2026 on one Windows desktop. [Decision report](../../research/WHOLE_RUN_DOCKING_2026-09-08.md), [timing table](tables.md), [figure](whole_run_tradeoffs.png). This is a research artifact, not production admission middleware or validated biological screening.

## Evidence boundaries

- `plan.json`: fixed molecular hashes, 20 maps, 32 ranking ligands plus a crystal ligand, seeds, caps and tiers. The executed honest audit sweep uses q=1/4/8 where possible; attacks also use q=16. These actual values supersede the plan's initial q list. The trace-binding change followed the final-output plateau diagnostic; the experiment is not claimed to be a fully preregistered study.
- `build_native_final_pose_control.json`, `build_wasm.json`, `build_wasm_no_trace.json`: compiler/options, upstream patch hashes and artifact hashes. Native science was collected before trace binding; canonical WASM science/audits use the traced engine. Native and WASM are not interchangeable exact replay backends.
- `native.json.gz`: 3,168 native science runs, final poses/scores/counts/times. `science_summary.json` derives ranking, symmetry-aware redocking, final-only shortcuts and resampled cost variance.
- `wasm_science.json.gz`: 2,112 canonical Node/WASM runs; full poses plus trace hashes/lengths. `science_wasm_summary.json` derives science results and both E8 redocking controls. Run traces themselves are retained in the separate browser corpus used for actual audit replay.
- `browser.json.gz`: 54 actual Chrome bundles, 2,646 runs, three repetitions per tier; full records, traces and commitments. Repeated benchmark seeds are diagnostics, not newly credited scientific units. No phone/Firefox/Safari, Internet, production queues or responsive background-worker UI were measured.
- `native_smoke.json`, `node_smoke.json`, `browser_smoke.json`: pre-trace exploratory runs, excluded from main counts. They expose native/WASM disagreement and same-WASM local replay agreement. Build hashes for the final WASM engine do not describe every earlier smoke artifact.
- `wasm_control.json.gz`: same-WASM uncapped E8 crystal control, one saved mode, no-refine maps; not stock default Vina. `stock_control.json`: official Vina 1.2.7 executable, CPU1, E8, nine modes, default explicit-receptor refinement, same prepared crystal/receptor. Stock ranking of all 32 molecules at E8 was not measured; the historical uncapped E1 control is separate.
- `audits.json`: 46 honest actual selected-run replay transcripts, 24 actual partial-work/control transcripts, two short-budget substitutions, a cache recommitment, six tamper cases and two later top-one repair attacks. The 10,000-trial entries sample correctness masks; they do not rerun Vina 10,000 times. CSPRNG draws and observed attack acceptance vary on rerun.
- `integration.json`: actual precomputation before a lease, commitment, CSPRNG challenge, Node/WASM replay and SQLite one-use credit, plus exhausted-pool and duplicate-credit checks. Separate initialization, computation and DB timing boundaries are reported.
- `retry_attack.json`: actual scheduler/CSPRNG retry grinding with a fixed half-correct mask, comparing unlimited legacy retries with a global three-challenge cap. Acceptance is calculated from the mask, not from physical replay. The legacy success on attempt 320 is one random realization, not an expected-value estimate.
- `trace_ablation.json`: 64 alternating-order traced/untraced Node/WASM pairs, one ligand, caps 4,000/16,000. Final score and pose equality checked for every pair.
- `economics.json`, `tables.md`, `whole_run_tradeoffs.png/.svg`: derived costs, theory and graphs. Browser values are three-repeat medians; each server challenge/tier is a single observation. Linear-memory capacity is reported, not process peak RSS. Transfer latency and resampling are explicitly projections/analysis.
- `transcripts.json`: reproducible gzip archive sizes and hashes of compressed/uncompressed content. Large raw JSON remains local; archive only public molecular data, no toolchains or credentials.

Warm timings exclude map/module startup, ligand preparation, network and DB unless a field explicitly includes one of them. Molecular fraction is not validated scientific-utility fraction. Early small browser tiers had some concurrent summary-analysis activity; later bulk measurements and subsequent heavy suites ran sequentially. Three repetitions are descriptive evidence, not stable production performance estimates. The currently prepared ligand and growing WASM heap persist between tiers, so these are not independent cold starts.

## Reproduce or inspect

Prerequisites are the [earlier pilot's source/Boost downloads](../docking_pilot_2026-09-06/README.md) and [lightweight campaign's ligand/receptor/maps preparation](../docking_lightweight_2026-09-07/README.md). These reconstruct public data under ignored `tmp/docking-pilot` and `tmp/docking-audit`. For scientific summaries install the pinned RDKit/Meeko/Gemmi dependencies from that README plus NumPy, SciPy and Matplotlib. Windows Python 3.14, Node 24.4, Chrome 152 and g++ 14.2 were used. Source pin: Vina `3c65c0b3e6c2c1d183f6a175ecb65e3c5ba91645`.

To inspect published transcripts without recomputing:

```powershell
python scripts/unpack_whole_run_evidence.py
# Reconstruct molecular reference inputs before running the RMSD analyzer.
python scripts/analyze_whole_run_science.py
python scripts/analyze_whole_run_science.py --wasm
python scripts/analyze_whole_run_economics.py
python scripts/plot_whole_run_findings.py
```

The unpacker checks both archive/raw hashes and refuses to replace different local results. Summaries require historical `uncapped_controls.json` and the prepared crystal SDF/PDBQT; economics also reads local maps to calculate compressed size. Existing derived summaries can be inspected without any dependencies.

For fresh computation, preserve a copy of the published evidence before running commands that overwrite results. The native and WASM science scripts resume existing entries; to obtain genuinely new timings, use a separate checkout/output copy rather than combining runs silently.

```powershell
git clone --depth 1 --branch 4.0.15 https://github.com/emscripten-core/emsdk.git tmp/docking-runs/emsdk
python tmp/docking-runs/emsdk/emsdk.py install 4.0.15
python tmp/docking-runs/emsdk/emsdk.py activate 4.0.15
python scripts/prepare_whole_run_plan.py
python scripts/build_whole_run_vina.py --native --no-trace
python scripts/benchmark_whole_run_native.py
python scripts/build_whole_run_vina.py
# Override these only if the defaults do not match your installation.
$env:PLAYWRIGHT_MODULE='C:\path\to\node_modules\playwright'
$env:CHROME_PATH='C:\Program Files\Google\Chrome\Application\chrome.exe'
node scripts/benchmark_whole_run_wasm.mjs --browser
python scripts/run_whole_run_remaining.py
python scripts/test_whole_run_retry_attack.py
python -m unittest research.tests.test_docking_campaign research.tests.test_whole_run_campaign -v
node scripts/test_whole_run_protocol.mjs
python scripts/analyze_whole_run_science.py
python scripts/analyze_whole_run_economics.py
python scripts/package_whole_run_evidence.py
python scripts/plot_whole_run_findings.py
```

The sequential driver performs canonical science, uncapped WASM and stock controls, actual audits, precomputation integration, untraced WASM build/ablation and derived summaries. Run heavy suites sequentially. Native science archives predate trace collection; rebuilding with `--no-trace` reproduces the final-only diagnostic relation, but current serialization/build paths can change binary hashes. Pinned input/engine identity is required for exact replay. The SDK is workspace-local; the scripts pass its configuration without permanently changing the global toolchain.

Scientific attribution: [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina), [DUD-E FA10](https://dude.docking.org/targets/fa10), and preparation software referenced in earlier manifests. Follow their citation/license requirements. Upstream inputs, dependency downloads, compiled executables and SDK files are reconstructed locally and are not bundled in this checkpoint.
