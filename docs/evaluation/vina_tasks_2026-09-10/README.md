# Distributed Vina task evidence

Read the [findings](../../research/VINA_TASK_DECOMPOSITION_2026-09-10.md), [measured tables](../../research/VINA_TASK_MEASUREMENTS_2026-09-10.md), [security model](../../research/VINA_TASK_SECURITY_MODEL_2026-09-10.md) and [reproduction instructions](../../research/VINA_TASK_REPRODUCIBILITY_2026-09-10.md).

- `campaign.jsonl.gz`: 222 aggregate configurations, including reused prefixes. Contains full output poses and individual task metrics.
- `wallmatched.jsonl.gz`: 90 closest-available-MC-time prefix comparisons, using existing task outputs.
- `summary.json`: redocking, best retained pose, ranking and uncertainty, missing-stock bounds, and decomposition checks.
- `split_equivalence.json`, `e32.json`: same-build split/monolithic equality and separate downloaded-stock controls.
- `browser.json`: corrected real Chrome/same-WASM Node measurements, including the short-run substitution attack.
- `browser_superseded_timer.json`, `corrections.json`: retained earlier measurement and precise reason for replacement. Do not use the superseded single-run total timer.
- `ingestion.json`: real bounded molecular outputs stored across simulated sessions, with actual postcommit replay and exact ordered aggregation.
- `dimensions.json`: regrouping identical measured units by ligand versus run. This is not fresh parallel or browser timing.
- `audit_sampling.json`: 54 settings with 20,000 sampling trials each, substituting actual low-budget outputs under normal-run assignments. Molecular replay verdicts are represented by reference hashes in these statistical trials; actual replay is measured separately.
- `build.json`, `build_wasm.json`, `reproducibility.json`: engine identity, build settings, dependency versions, source and archive hashes.
- `raw_task_manifest.json.gz`: 11,752 hashes of local raw task/trace/pose/metric files. Full raw traces and executables are not bundled; regenerate them using the scripts and pinned source.
- `followups.jsonl`: sequential-driver execution log, before the separately documented browser timer correction and ingestion rerun.
- `aggregate_quality.png` / `.svg`: visual summary of the small native quality pilot. Numerical uncertainty is in `summary.json`; points sharing inputs/prefixes are not independent replicates.

Only the gzip JSONL archives are versioned; decompress to the corresponding uncompressed names for analysis. Integrity checks decode the archives and compare their SHA-256 values with `reproducibility.json`. The reference-input provenance and prepared files are inherited from the adaptive-docking artifact; this is not a new independent target cohort.
