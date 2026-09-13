# Prepared-state iPhone results: power mode comparison

Update: the subsequent [HTTPS iPhone experiment](VINA_PREPARED_HTTPS_2026-09-13.md) is complete. Native hashing reduces cached total time to 1.389 s normally / 2.559 s in Low Power Mode. Forced-download startup through the temporary tunnel remains 15.263 / 17.211 s. The measurements below are the earlier LAN HTTP trials, retained as the comparison baseline.

Both user-operated iPhone15 trials completed without hidden-tab events. All
eight raw pools and traces independently match the compute reference; artifact
and WASM hashes match the pinned manifest. Both cached-restoration trials
explicitly read the artifact from IndexedDB. Power mode is user-reported.

| Time to one256k result | Low Power Mode off | Low Power Mode on |
|---|---:|---:|
| Forced-download prepared restoration | 9.703s | 15.448s |
| Same-worker reuse | 0.955s | 2.022s |
| Fresh worker, IndexedDB artifact | 2.244s | 5.347s |
| Normal map-computation control | 6.806s | 12.282s |

These are one ordered trial per mode on the same phone. They are consistent with
slower execution in Low Power Mode, but do not isolate battery mode from trial
order, temperature or browser/network state. Each path uses a different seeded
unit at the same256k cap. The compute control follows the other paths and has
cached small input/executable assets; it is not an independently randomized,
fully uncached control.

## The computation bottleneck was removed

With Low Power Mode off, restore took159ms in the cold path and168ms in the
cached path; recomputing maps took5,336ms. With Low Power Mode on, restore took
317ms cold and314ms cached versus9,604ms for recomputation. Thus the measured
restoration phase is about30–34 times faster in these trials. The remaining
phase still parses receptor/ligand data, reconstructs pair tables and prepares
explicit-receptor scoring; it is not a raw file-copy-only measurement.

Original scientific behavior remains verified on the tested units. The earlier
three-target exact finalizer regression still applies; these phone uploads check
raw pools/traces against that reference, not a newly executed phone finalization.

## The cold visit now pays for transfer and hashing

| Cold-path component | Power mode off | Power mode on |
|---|---:|---:|
| Asset loading, including decoding/import overhead | 7.291s | 9.719s |
| Asset integrity hashes | 1.042s | 2.958s |
| IndexedDB cache write | 0.174s | 0.339s |
| Restore | 0.159s | 0.317s |
| Actual256k search | 0.934s | 2.011s |

Factory creation, copying and dispatch account for the remainder. The artifact
is27.746MB raw and14.672MB gzip. Safari reports zero byte counts in these resource
timing entries, so those zeros are not treated as evidence of an HTTP cache hit.
The cold path requests reload; server counters record the artifact requests.
The asset timer is fetch-plus-decoding/import time, not a pure network timer.

The fresh-worker IndexedDB path cuts asset loading to25ms off /49ms on, but
rehashing still costs1.011s off /2.912s on. Actual search takes0.950s off /1.992s
on. Hashing is now the largest removable cost for cached fresh workers.

The LAN page uses ordinary HTTP, so the browser uses the tested JavaScript
SHA256 fallback rather than WebCrypto. The earlier desktop secure-context
control supports testing HTTPS/native hashing next, but no HTTPS iPhone latency
has been measured. Do not subtract this overhead and report the result as an
observed phone speedup. Do not skip integrity verification to improve latency.

## Decision and next steps

**Scientific fidelity passes on the tested cases. Same-worker reuse is near1s
with power mode off. The true cold near1s objective fails in this experiment.**
The cold prepared path is slower than the compute control in both phone trials.
Persistent-cache restoration is useful, but transfers the largest remaining
cached-path cost to integrity hashing.

The next experiment should use HTTPS/native WebCrypto on the same phone and
retain forced-download, explicit-cache and same-worker cases. Brotli compressed
size is10.907MB offline versus14.672MB gzip, but transfer/decode latency on the
phone remains unmeasured. Neither change alone makes a10MB cold download free.

For the background-first product, initialize after critical page work and keep
the worker for bounded contributions within the active session. Preloading can
hide work from later actions, but must not be counted as a faster true cold
start. A tested bandwidth-aware choice between local map computation and cached
restoration may be preferable to always downloading the full artifact. Avoid
changing scientific precision, search box or the validated workload to meet a
timing target.

The local implementation is a measured research prototype, not a claim that
every fresh visitor can receive immediate computation-backed access. Ranking
coverage and trusted-tier/audit/quarantine integration remain separate blockers.

Evidence:
- `docs/evaluation/vina_prepared_2026-09-13/device_1789321525293-37be510a.json`: power mode on.
- `docs/evaluation/vina_prepared_2026-09-13/device_1789321574131-14f79825.json`: power mode off.
- `scripts/analyze_vina_prepared.py`: independent hashes, completion and cache-hit checks.
