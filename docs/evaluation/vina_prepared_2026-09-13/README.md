# Prepared-state evidence

`build.json` binds the new isolated WASM to the untouched reference hash.
`equivalence.json` contains all three target comparisons, artifact sizes/hashes,
36 exact256k pool/trace comparisons and nine original-finalizer hashes.
`device_manifest.json` binds the browser artifact to the receptor, ligand and
engine; it contains relative asset URLs, not the private LAN access token.
`device_*.json` preserves actual uploaded browser timings and raw outputs.
`summary.json` independently recomputes output hashes and distinguishes a real
IndexedDB hit from an HTTP cache miss. Hardware/browser labels are self-reported.

Build and regenerate artifacts using:

```
python scripts/build_vina_prepared.py
node scripts/validate_vina_prepared.mjs
node scripts/test_prepared_sha.mjs
```

This requires the existing Emscripten, Boost and reference source dependencies
under `tmp`, as in the earlier resource builds. Generated artifacts and binaries
are not committed. Their integrity hashes and lossless gzip/Brotli sizes are.
The current test serves gzip; Brotli sizes are offline measurements only.

In PowerShell, start the explicit-cache test with:

```
$env:VINA_PREPARED_IDB='1'
node scripts/serve_vina_prepared.mjs
```

Use the printed full LAN URL on the phone. Leave that process running. No desktop
tool controls the phone. To run the automated desktop control separately:

```
node scripts/benchmark_vina_prepared_browser.cjs
node scripts/benchmark_vina_prepared_browser.cjs --secure
python scripts/analyze_vina_prepared.py
```

The benchmark script uses this workstation's installed Chrome/Playwright paths;
adapt those paths on another host. `--secure` uses localhost's secure-context
WebCrypto, not HTTPS or a remote deployment. HTTP LAN uses the tested portable
SHA256 fallback. The desktop script poisons its isolated context's cache after
the successful benchmark and verifies rejection before restoring anything.

The ordinary HTTP-cache control is retained: the artifact was downloaded twice.
Only the explicit-storage trials demonstrated fresh-worker artifact reuse on
this desktop. Storage write/read failures remain visible. Different seed indices
and ordered single trials limit causal timing comparisons. See
`docs/research/VINA_PREPARED_RESTORATION_2026-09-13.md` for conclusions and pending
physical-phone evidence.

Physical iPhone results are now received for both reported power modes. All
eight outputs match and both explicit-cache reads hit. See
`docs/research/VINA_PREPARED_IPHONE_RESULTS_2026-09-13.md` for the measured cold
latency failure and successful restoration/reuse results.
