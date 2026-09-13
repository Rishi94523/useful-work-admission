# Lossless prepared-state restoration checkpoint

Update: both physical-phone trials have now completed. See
[Vina prepared iPhone results](VINA_PREPARED_IPHONE_RESULTS_2026-09-13.md). The
checkpoint timings below retain the original desktop evidence; phone cold
restoration did not meet the near1s goal.

The isolated restoration path passes exact scientific regression checks against
the existing compute-path WASM. It preserves binary64 grid samples and initialized
scoring tables, restores grid geometry using the original initialization formula,
and reconstructs the explicit-receptor state required by the original finalizer.
The search algorithm, budget, seeds, box, grid spacing, scheduler and audit remain
unchanged. The production/reference binary was not replaced.

Across FA10, HS90A and TRYB1 source-conformer inputs, each of three paths ran four
256k units: reference compute, new-build compute, and new-build restore. All raw
pool hashes, trace hashes and original-finalizer output hashes match exactly.
That is36 executions and nine finalizations. Coverage is these inputs and seeds,
not a proof of equivalence for every molecule. Malformed-header and truncated-file
checks reject invalid restoration; the browser additionally verifies artifact,
WASM, receptor and ligand SHA256 hashes before invoking the loader.

## What is serialized

VPS1 stores little-endian binary64 grid bounds, slope and sample values, integer
dimensions and initialized-map flags, and the initialized type-table fast and
smooth arrays. No decimal roundtrip, quantization, grid thinning or altered
floating-point flags is used. Scoring-function ownership/pointers are rebuilt
instead of serializing live addresses. Receptor/ligand parsing, ligand-specific
pair tables and explicit-receptor neighbor structures are still constructed
locally. Thus restoration eliminates the dominant map computation, not all
initialization.

Artifacts require the pinned build and manifest. The experimental format is
bounded to128 voxels per axis and the Vina XS scoring configuration used here.
It is not a generic interchange format or an unauthenticated public deserializer.
The LAN test is HTTP; production delivery requires a trusted manifest/transport.

## Size and local measurements

Sizes below use decimal MB. Gzip is the encoding served by the current test.
Brotli sizes were measured offline but are not the phone download encoding.

| Target | Raw MB | Gzip MB | Brotli MB | Node restore |
|---|---:|---:|---:|---:|
| FA10 | 27.746 | 14.672 | 10.907 | 0.746s |
| HS90A | 22.578 | 12.067 | 9.585 | 0.564s |
| TRYB1 | 18.304 | 10.004 | 7.655 | 0.678s |

These Node measurements come from a sequential multi-module correctness run;
they exclude network and browser integrity checking, and are not the preferred
user-experience measurements. The actual browser checks below include asset
fetch/decompression, hashing, WASM instantiation, file copying, restoration and
one256k contribution.

| Desktop browser trial | Forced-download restore | Same-worker reuse | Fresh-worker cached attempt | Normal compute control |
|---|---:|---:|---:|---:|
| LAN HTTP, ordinary HTTP cache | 2.336s | 1.355s | 2.215s, artifact cache miss | 4.615s |
| LAN HTTP, explicit IndexedDB | 2.483s | 1.402s | 2.168s, verified IDB hit | 4.592s |
| Localhost secure context, IndexedDB | 1.886s | 1.397s | 1.640s, verified IDB hit | 4.256s |

All twelve browser outputs match the reference hashes. These are single trials
on one physical laptop. LAN-address traffic from that same laptop does not
traverse the phone's Wi-Fi path and cannot substitute for a physical-phone or
WAN measurement. Localhost is a secure context supporting WebCrypto, not an
actual HTTPS/cloud deployment.

In the first LAN trial, restoring alone took293ms, but portable JS SHA256 took
543ms. That fallback exists because ordinary LAN HTTP does not expose WebCrypto.
The secure-context control illustrates the cost of that distinction without
claiming that the phone will achieve the same numbers. The fallback matches
Node SHA256 on ten boundary vectors and the full27.7MB artifact.

## Caching findings

Chrome cached the small assets but requested the large artifact twice despite
immutable cache headers. The first cached-attempt result is retained as a failure
of that caching approach. A requested cache mode is not evidence of a cache hit.

The optional IndexedDB path stores only a hash-verified artifact, keyed by its
content hash. A fresh worker reads it from browser storage and re-verifies the
hash before restoring. The cold measurement includes the initial cache write.
The desktop cache-hit record is explicit, and a deliberately poisoned entry was
rejected before restoration. Storage errors are recorded and fall back to normal
fetch; there is no silent claim of a hit. This prototype has no production
multi-artifact eviction policy yet. Same-worker reuse needs neither download nor
rehashing nor restoration.

## Physical-phone experiment

The cache-enabled test is running on the LAN at port8769; its complete tokenized
URL is in local `tmp/vina-prepared-idb-url.json`. The user must operate the phone.
The page collects four cases in order: forced download/restore, reused worker,
fresh-worker IndexedDB restore, and map computation. The initial scientific
artifact is14.7MB compressed. No64k unit is used.

Cold explicitly reloads WASM, receptor, ligand and artifact; the JS module cache
is not cleared. Each mode uses a different known seed index at the same256k cap.
The ordered trial does not isolate temperature, browser warmup or seed variance.
Phone results are pending at this checkpoint. Do not claim true cold iPhone
latency near1s until the received timings include the actual download and checks.

## Decision

Lossless restoration is scientifically viable on the tested cases and materially
reduces local startup. A fresh cached worker is close to warm contribution time
on the laptop when native WebCrypto is available. A truly uncached visit now has
a large download: at10Mbit/s the14.7MB artifact alone has an ideal transmission
floor of about11.7s, excluding every other cost. This is a bandwidth calculation,
not a measured mobile result. Even100Mbit/s gives about1.17s just for those bytes.

Consequently an unconditional1s cold result is not established. The architecture
can amortize preprocessing, but meeting the cold-visit goal depends on artifact
size, connection and secure-context hashing. Preserve the current result while
measuring the phone; do not shrink the validated box or approximate scores to
improve the headline number.

Reproduce with `scripts/build_vina_prepared.py`,
`scripts/validate_vina_prepared.mjs`, `scripts/test_prepared_sha.mjs`, and
`scripts/analyze_vina_prepared.py`. Start the cache-enabled server with
`VINA_PREPARED_IDB=1` in its process environment and
`node scripts/serve_vina_prepared.mjs`. Generated multi-megabyte artifacts stay
under `tmp/vina-prepared/artifacts`; committed manifests record their hashes.
