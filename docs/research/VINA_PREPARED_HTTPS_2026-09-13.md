# Prepared-state HTTPS experiment — 2026-09-13

The prepared-state harness now requires native WebCrypto in its HTTPS experiment and records the actual hashing backend, secure-context status, transport, and response compression. The Vina engine, artifact, 256k units, raw-pool comparison and finalizer are unchanged. Physical iPhone HTTPS measurements are now complete; cached restoration improves substantially, while the forced-download cold path remains slow.

## Physical iPhone 15 results

Evidence: `device_1789322869662-3a3d228b.json` (Low Power Mode off) and `device_1789322937347-75e0342b.json` (on), in the same evaluation directory. Both reports are complete, have zero hidden events, use native WebCrypto, match the artifact/engine hashes, and independently match all eight reference raw pools and traces. Both fresh-worker cached paths explicitly hit IndexedDB. Phone finalization was not rerun; the existing three-target finalizer equivalence test remains the relevant evidence.

| Time to first 256k result | Power mode off | Power mode on |
|---|---:|---:|
| Forced-download restoration | 15.263 s | 17.211 s |
| Same-worker reuse | 0.964 s | 2.026 s |
| Fresh worker, cached artifact | 1.389 s | 2.559 s |
| Ordinary computation control | 6.814 s | 12.583 s |

| Phase | Power mode off | Power mode on |
|---|---:|---:|
| Cold asset acquisition | 12.757 s | 13.420 s |
| Cold integrity hashing | 42 ms | 40 ms |
| Cold restoration | 171 ms | 311 ms |
| Cached integrity hashing | 14 ms | 27 ms |
| Cached restoration | 165 ms | 315 ms |
| Cached molecular run | 956 ms | 1970 ms |

Compared with the earlier HTTP phone trials, cached hashing decreases from 1011 to 14 ms (off) and 2912 to 27 ms (on). Cached total time decreases from 2.244 to 1.389 s (38%) and 5.347 to 2.559 s (52%). These are observed cross-trial comparisons, not randomized causal estimates. The same-worker timings remain close to the earlier 0.955/2.022 s. Each power setting has only one ordered trial, with distinct seeds across paths and no controlled thermal state.

The cold asset phase accounts for about 84%/78% of total latency. It includes fetch, decoding and module import, so it is not an isolated network measurement. The prepared response is still 14,671,512 bytes gzip and reports Cloudflare DYNAMIC. The quick tunnel does not establish CDN edge delivery performance, and its network route differs from LAN. Normal compute is the last ordered path with previously fetched small assets, not an independently cold control. Recorded WASM allocation is 51.25 MiB cold/reused and 42.6875 MiB cached; these are not total Safari peak working-set measurements.

**Decision:** native hashing and cached state solve most repeat-contribution initialization overhead, with no observed scientific change. The cached normal-power result is about 0.43 s above its molecular run, and same-worker reuse remains about one second. A true first contribution near one second is not achieved. Cold delivery is now the priority: measure static edge delivery and lossless transport compression before claiming a cloud deployment fixes it. Retain worker reuse within a session and verified persistent state for later workers. Do not gate low-risk access on this 15-second cold artifact path; any provisional admission still needs the previously identified reputation and abuse controls. Background computation should mean a worker during active browsing; these visible-page trials do not establish execution while iOS has suspended a page.

The temporary Cloudflare tunnel forwards to a loopback-only origin on port 8770. This is a development transport experiment, not a production CDN benchmark. The allowlisted molecular inputs originate from the public [DUD-E FA10 benchmark](https://dude.docking.org/targets/fa10); the prepared artifact is their deterministic derived scoring state. Token-bearing URLs and tunnel logs remain outside the committed evidence.

## Desktop end-to-end check

Evidence: `docs/evaluation/vina_prepared_2026-09-13/device_1789322412706-a2f5fe14.json`. One ordered Chrome trial on Ryzen 7 7435HS; not an iPhone measurement.

| Path | Total to result | Hashing | Restore/init | Molecular run |
|---|---:|---:|---:|---:|
| Cold restoration | 9449 ms | 38.7 ms | 616.9 ms | 3087.4 ms |
| Same worker | 3425 ms | skipped | skipped | 3421.9 ms |
| IndexedDB restoration | 4176 ms | 34.4 ms | 779.2 ms | 3127.4 ms |
| Compute control | 11458 ms | 1.4 ms | 7596.4 ms | 3694.4 ms |

All four raw pools and traces match the frozen reference exactly. Both artifact and engine hashes match. The cached restoration reports an explicit IndexedDB hit. A separate deliberate corruption of the browser cache was rejected before restoration. Ten SHA-256 boundary vectors and the complete artifact also match Node's implementation.

Cold asset acquisition took 4925 ms; the prepared response used gzip with Content-Length 14,671,512 bytes. Cloudflare reported DYNAMIC, so this does not demonstrate an edge-cache hit. All work ran in a secure context using WebCrypto. The reuse row records backend availability but performs no hashing.

The molecular run itself was substantially slower than earlier desktop controls. Consequently, cross-trial total latency is not a controlled estimate of HTTPS benefit. The phone experiment must measure hashing and restoration separately from network delivery, using both power modes. The cold mode forces binary/input reload but is not a clean-browser/profile reset; the cached mode reuses IndexedDB in a new worker. Different modes retain the existing distinct seed indices.

## Reproduction

1. Set `VINA_PREPARED_HTTPS=1` and run `node scripts/serve_vina_prepared.mjs`.
2. Forward the loopback origin through an HTTPS tunnel. Keep its token URL in the local `tmp/vina-prepared-https-url.json` as the `url` property.
3. Run `node scripts/benchmark_vina_prepared_browser.cjs --https` for the desktop exactness/cache-corruption check.
4. On the actual phone, run all four modes once per reported power setting, keeping the page visible until upload completes.
5. Run `python scripts/analyze_vina_prepared.py` and compare actual `hash_backend`, integrity, cache source, phase times and total first-result times.

The endpoint deliberately fails when native WebCrypto is unavailable; silently falling back would invalidate the intended comparison. No conclusion that cold contributions approach the approximately one-second warm phone runtime is justified yet.
