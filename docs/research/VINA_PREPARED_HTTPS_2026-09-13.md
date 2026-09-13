# Prepared-state HTTPS experiment — 2026-09-13

The prepared-state harness now requires native WebCrypto in its HTTPS experiment and records the actual hashing backend, secure-context status, transport, and response compression. The Vina engine, artifact, 256k units, raw-pool comparison and finalizer are unchanged. Physical iPhone HTTPS measurements are pending.

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
