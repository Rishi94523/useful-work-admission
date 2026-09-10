# Reproducing the Vina task-decomposition pilot

Run commands from the repository root. This extends the downloaded/prepared Vina and molecular inputs documented in the earlier adaptive-docking artifact; it does not fetch new targets. Required local inputs are `tmp/docking-pilot/source/src/lib` (Vina 1.2.7), Boost headers under `tmp/docking-pilot/boost/ucrt64/include`, the downloaded stock Windows Vina executable, the molecular files referenced by `science_inputs.json` and `converged_inputs.json`, and Emscripten under `tmp/docking-runs/emsdk`. Native compilation uses g++; the recorded build/patch hashes and compiler version identify the measured implementation.

The dependencies are not bundled in Git. The analysis needs NumPy, SciPy, RDKit (the existing local RDKit path is configured in the script), and Matplotlib. Browser measurement uses the installed Chrome and Playwright; override `CHROME_PATH` and `PLAYWRIGHT_MODULE` for another installation. This is the actual Windows experiment harness, not a claim of a portable one-command artifact.

Run sequentially so compiler or other molecular jobs do not compete with the timing experiment:

```powershell
python scripts/build_vina_tasks.py
python scripts/benchmark_vina_task_split.py
python scripts/benchmark_vina_task_campaign.py
python scripts/benchmark_vina_task_wallmatch.py
python scripts/benchmark_vina_task_e32.py
python scripts/build_vina_tasks_wasm.py
node scripts/benchmark_vina_tasks_browser.mjs
python scripts/benchmark_vina_task_ingestion.py
python scripts/quantify_vina_task_audits.py
python scripts/analyze_vina_tasks.py
python scripts/plot_vina_tasks.py
python scripts/package_vina_tasks.py
python -m unittest research.tests.test_vina_pool_campaign research.tests.test_adaptive_admission research.tests.test_whole_run_campaign research.tests.test_docking_campaign
```

`run_vina_task_followups.py` is a local sequential driver that waits for the 222 predeclared campaign keys and executes the wall-time-prefix, E32, browser, ingestion and reporting stages. It stops at the first failing command. It is not a scheduled service. Do not launch it alongside another copy of those follow-up stages.

The campaign resumes from existing aggregate keys and native per-task metrics; the E32 comparison preserves an existing completed result. For a genuinely independent rerun, use a separate checkout/output directory with freshly generated outputs. Do not mix raw outputs from different engine hashes. JSONL gzip archives can be decompressed to the same uncompressed filenames for analysis, but they do not contain the raw task pools required to redo finalization. Regenerate those with the native campaign, checking the raw-task manifest where numerical compatibility permits. Exact numerical comparisons are same-build guarantees; changing compiler, architecture or math implementation may change trajectories.

## What each measurement includes

Native `search_ms` sums the Monte Carlo sections, including light trace instrumentation. It excludes model copies, file writes, map initialization and final aggregation. The campaign records actual evaluation counts and finalizer times where separately measured. An evaluation cap can overshoot at the next outer-loop check; it is not a hard millisecond deadline. Equal evaluation counts and equal elapsed time are separately reported. Wall-matched arms select the available prefix nearest the reference's measured MC time without consulting quality, and can still overshoot/undershoot. This is not an exact end-to-end resource match or repeated thermal-controlled timing trial.

Browser measurements execute the same task source in a Chrome module worker and replay in Node using the same WASM. They report map initialization separately, along with pure MC timing and the enclosing task/serialization timing. Commitments in this harness are constructed by host Node after receiving Chrome outputs: those numbers must not be described as browser commitment timings. No network, production database, mobile device, real participant, energy or abandonment experiment is implied.

The ingestion experiment uses actual previously computed 16k-cap molecular task outputs with simulated visitor IDs and a reopened SQLite ledger per session. It replays challenged units after commitment and compares the canonically merged stored result against the direct merge. It tests durable one-use credit and aggregation, not that all work was fresh after assignment, and not the scientific quality of 16k-cap work. The normal E32 control separately tests the scientifically faithful decomposition.

The sampling experiment compares fixed lower-budget substitution commitments to reference-output hashes over 20,000 trials per setting. Those hashes model replay verdicts; it does not rerun molecular search millions of times. Actual replay timing comes from the browser and ingestion experiments. No experiment proves a general computational lower bound against a better docking implementation.
