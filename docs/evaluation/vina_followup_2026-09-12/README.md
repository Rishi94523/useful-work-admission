# Frozen Vina follow-up, 12 September 2026

This directory separates completed controls/models from an ongoing ranking
campaign. Absence of a gate or paired result is not a successful result.

Protocol: `docs/research/VINA_FOLLOWUP_PLAN_2026-09-12.md`, committed as
`269364263c9d390690fd602d4cca2f40d09f79b8` before new ranking outcomes.
Scientific architecture reference: `d25cca45c8212db8526fdc7ca0a1a8efe62a86be`.

## Inputs and ranking

- `*_selection.json`: sources, input hashes, outcome-blind selection, exclusions.
- `large_inputs.json`: 32 active + 64 decoy inputs for each of three targets.
- `input_verification.json`: independent graph, 3D, hash and overlap checks;
  tool versions and binary hashes. All 288 selected inputs passed.
- `large_stock.jsonl`: resumable official-stock results, including failures.
- `large_stock_gates.json`: written only after the stock stage completes.
- `large_matched.jsonl`: generated only for targets passing the declared gate.
- `tryb1_old_seed_diagnostic.jsonl`: original 4+4 inputs across three seeds;
  seed104729 reuses historical rehashed measurements, the others are new.
- `followup_summary.json`: analysis snapshot. Its completeness flags govern
  interpretation; repeated seeds are not independent compounds.

The JSONL files may be locally in progress and not yet part of a Git checkpoint.
Run `python scripts/analyze_vina_followup.py` to update the snapshot. Do not
calculate or publish AUC from an incomplete active/decoy panel.

Reproduction order:

```
python scripts/prepare_vina_large_panel.py
python scripts/verify_vina_followup_inputs.py
python scripts/run_vina_large_panel.py
python scripts/diagnose_vina_tryb1_seeds.py
python scripts/analyze_vina_followup.py
```

Preparation requires the existing local RDKit/Meeko dependency directory and
download access to DUD-E. The native reference and official Vina executables are
local build/download artifacts, identified by hashes, not distributed here.
The existing `scripts/build_vina_tasks.py` creates the instrumented reference;
the resource probe build creates the optimized WASM. Preserve their existing
build prerequisites and input manifests.

The official gate uses stock E8 at seed104729, nine modes, CPU1 and a 30A box.
The matched instrumented reference uses the unchanged original finalizer, E8
normal tasks and 256k medium tasks, at three parent seeds. Both search evaluations
and wall times are recorded; matching evaluation count is not a claim of identical
elapsed time. Four stock/matched workers can overlap the two old-panel diagnostic
workers. Concurrent timing is not an isolated speed benchmark.

## Admission

`admission_policy_comparison.json` contains analytic and Monte Carlo models,
including fresh identities, farming, immediate/deferred validation, predictable
audit evasion, partial bundles and capped cached retries. The figure is generated
from those models. `cached_retry_scheduler.json` exercises real SQLite and
challenge transitions but uses modeled replay verdicts: it is explicitly not a
molecular execution or Internet attack measurement.

```
python scripts/compare_vina_admission_policies.py
python scripts/benchmark_vina_cached_retries.py
python scripts/plot_vina_admission_policy.py
```

Interpretation and remaining integration requirements:
`docs/research/VINA_ADMISSION_POLICY_2026-09-12.md`.

## Physical device collection

```
node scripts/serve_vina_device_benchmark.mjs
```

The server prints a tokenized LAN URL. Open the full URL on the same network,
enter the device model and OS version, then explicitly start the six-run test.
Keep the tab visible. Reports are saved automatically as `device_<id>.json`.
Do not publish the active token URL or treat a self-reported device label as
hardware attestation. No remote device was controlled by this agent.

`device_reference.json` binds the WASM and input hashes to six Node output
hashes. The server checks uploaded raw pools/traces against that reference.
`device_1789185990203-16da6a2f.json` is the completed headless Chrome control on the
actual Ryzen laptop: 6/6 exact outputs, 3.023s initialization, 0.317–0.385s calls,
42.7MiB allocated heap. It is one physical host, not a simulated second device.

The `module_ms` field measures factory instantiation after the static module
import; it excludes some asset loading/compilation. Total elapsed time includes
more startup work and all six calls, but does not separate every network phase.
`heap` is allocated WASM linear memory, not peak resident memory. Frame gaps in
headless Chrome are diagnostic, not a real-user responsiveness study. The actual iPhone 15 report is now device_1789187835146-faaec61d.json: all six
outputs match, with 9.641s initialization and 0.498–0.553s calls. Run
python scripts/analyze_vina_devices.py to independently check hashes and
regenerate device_summary.json. See docs/research/VINA_IPHONE_15_2026-09-12.md
for interpretation and limitations.
