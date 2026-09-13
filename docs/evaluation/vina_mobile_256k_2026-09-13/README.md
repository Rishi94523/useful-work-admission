# Actual 256k unit, fresh and reused worker

Run `node scripts/serve_vina_medium_device_benchmark.mjs` and use the printed LAN
URL in Safari on the physical phone. The browser performs six actual 256k FA10
crystal-input Vina units: three after creating a fresh worker, a two-second
pause, then three more in the same initialized worker. No 64k units are run.
Keep the tab visible and wait for Saved. User stop and error reports are retained.

The server uses the unchanged compact-single WASM build and independently checks
each raw pool/trace against a newly computed 256k Node reference. It saves
`device_<timestamp>-<suffix>.json`. Analyze received results with:

```
python scripts/analyze_vina_devices.py --medium
```

`result_received_ms` is elapsed page time from Start to each result message,
including startup for the first result. `call_ms` times the actual synchronous
WASM run within the worker. `batch` is zero for the first three and one for the
reused batch. `init_count` should be one. Total elapsed includes the intentional
two-second pause. `module_ms` is factory instantiation after static import, not
complete network or compilation time. Cold means fresh worker state; it does
not imply a reboot, empty browser caches or cold OS caches.

This is the real medium evaluation cap used in ranking experiments, but one
FA10 source ligand is not representative of every ranking molecule. Per-unit
budget checks may slightly exceed 256000 evaluations at an outer-step boundary;
actual evaluation counts are retained. Linear-memory allocation is not process
resident memory or total device RAM use. No battery/thermal claim is made.

The first completed desktop control, `device_1789302544303-33114cc2.json`, matched
6/6 outputs with exactly one initialization. Calls took 1.288–1.531s; first result
arrived at 4.460s, initialization took 3.037s and maximum allocated WASM memory
was 51.25MiB. It is headless Chrome on the existing Ryzen host, not a phone
measurement. Physical phone results are pending collection.
