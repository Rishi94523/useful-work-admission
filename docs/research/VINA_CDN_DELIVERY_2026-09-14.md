# Cold prepared-state delivery: static edge experiment

The unchanged FA10 scientific artifact is now hosted on Cloudflare infrastructure. The local computer and quick tunnel are no longer in the asset or result-upload path. Three physical iPhone 15 CDN sessions now demonstrate a few-second first contribution under the tested connection and warm-edge conditions. Browser cache was empty at each session's start, as confirmed by the user; this is distinct from the CDN edge cache.

## Physical iPhone results received

All three sessions used ordinary Brotli quality 9. There is no phone gzip/shuffle comparison. All 12 raw pools and traces independently match the frozen reference, and all three reported original-finalization digests match. All artifact/engine hashes match, all reports are complete, and no hidden-tab events were recorded.

| Measurement | Normal power, trial 1 | Normal power, trial 2 | Low Power Mode |
|---|---:|---:|---:|
| Cold result from Start | 2.512 s | 2.458 s | 3.814 s |
| Cold navigation-to-result, excluding form dwell | 3.996 s | 3.282 s | 4.710 s |
| Existing-worker result | 0.959 s | 0.943 s | 2.034 s |
| After page navigation, HTTP-only restore | 3.054 s | 2.323 s | 3.574 s |
| Persistent-cache restore, separate worker | 1.270 s | 1.299 s | 2.928 s |
| Cold asset acquisition | 1.235 s | 1.174 s | 1.288 s |
| Cold integrity hashes | 22 ms | 25 ms | 37 ms |
| Cold restore | 160 ms | 162 ms | 321 ms |
| Cold molecular run | 946 ms | 930 ms | 2029 ms |

Trial 1 is `device_57a384a8-4cac-4a22-86d2-ad6fdf032380.json`; trial 2 is `device_0703803a-38bb-4f5c-92a8-15ea2d7c9814.json`; Low Power Mode is `device_c865ec6c-6e8f-4040-b68b-8eca4d928614.json`. All three have `prior_visit_marker=false`. Trial 1's fresh-cache checkbox is false, but the user subsequently confirmed every session was uncached. That clarification is recorded in `phone_session_confirmation.json`; the original report is preserved without rewriting its fields.

All cold artifact requests report `CF-Cache-Status: HIT` and `X-Delivery-Cache: HIT`, with ages of 884, 2902 and 2066 seconds respectively at the MAA edge. These are browser-cold, edge-warm trials. HTTP-only restoration on the second page re-fetches the artifact: its CF-Ray and Age change, and acquisition remains about 1.1–1.6 s. Safari's resource byte counts are zero, which does not establish a browser-cache hit. Explicit IndexedDB reads do avoid the artifact request. The persistent-cache row occurs after the HTTP-only control on that second page; it is not itself a measured navigation-first persistent-cache policy or evidence of survival after Safari closes.

Start-to-result includes manifest retrieval, worker startup, download/decode, hashing, cache write, restoration and a 256k run. The adjusted navigation figure adds page startup and subtracts the measured pause at the form (9.683, 8.321 and 48.105 s). It is a sum of observed phases, not an uninterrupted auto-start navigation experiment: the pause can affect connection state and caching of page resources. The scientific artifact itself is not requested until Start. Report both timing definitions, rather than labelling 2.46 s as full navigation latency.

**Decision:** a few-second cold contribution is demonstrated on this iPhone 15 and connection, without changing the scientific workload. The earlier 15–17 s tunnel bottleneck is no longer present in this delivery path. Normal-power repeat workers remain around one second, and persistent restoration around 1.3 s. The 11.23 MB transfer remains substantial; three sessions on one phone with a warm edge do not establish performance on slower links, cold edges, other devices, or reliable background operation under OS suspension. Keep this architecture and prioritize the outstanding multi-target ranking and low-risk admission evidence rather than redesigning molecular computation. A navigation-first persistent-cache policy and longer-lived session reuse are implementation follow-ups, not reasons to repeat the codec search now.

## Artifact and delivery

The decoded artifact remains 27,746,024 bytes, SHA-256 `6112b5ab3fec5c3cbc539d6db2b07b6f0a18bebe8a3871614b6849ad43d3dd3e`. The Vina WASM hash remains `12726267cd75f4c461031e7f0efd71996cfdcbd9d16b188bedb129c73003aad3`. No molecular code, search budget, scheduler, scoring, or finalizer changes were made.

Compression was measured locally, and every decoded variant was independently hashed against the original:

| Encoding | Identity bytes | Reversible byte-shuffle bytes |
|---|---:|---:|
| gzip level 9 | 14,671,512 | 13,221,971 |
| Brotli quality 5 | 11,344,156 | 11,626,290 |
| Brotli quality 9 | **11,232,116** | 11,581,528 |

Ordinary Brotli quality 9 is 23.4% smaller than the original gzip delivery. Byte rearrangement offers no advantage over ordinary Brotli on this blob. Quality 5 is only about 1% larger than quality 9 and substantially faster to package; packaging is offline, so quality 9 is selected for this fixed artifact. Encode/decode timings are in `compression.json`; these are Node timings, not Safari decoding measurements.

Cloudflare [static assets](https://developers.cloudflare.com/workers/static-assets/) supply hosted storage and tiered caching. Content-addressed executable/input assets use immutable browser-cache headers. A small streaming Worker route for the precompressed artifact sets the exact Content-Encoding and uses the edge Cache API. It does not buffer the scientific artifact, recompute it, or execute Vina. This route incurs a Worker invocation even on a cache hit; it is not a claim of static-only request billing. Reports go to a dedicated KV namespace behind an upload secret, with bounded report size. Static benchmark inputs are public DUD-E data; no project secrets or unrelated workspace files are published.

The first deployment exposed a real transport bug: Content-Encoding overrides on static files were not preserved as expected, and an initial edge-cache-hit path also omitted encoding. Integrity checks rejected both before the affected work ran. The final route sets encoding explicitly on both misses and hits. Incomplete failed reports are retained separately in the evaluation directory; they must not be counted as successful trials.

## Measured desktop checks

Three fresh Chrome contexts, one ordered trial per compression variant, four actual 256k units each. All **12 pools and traces and all three original finalizations match** the frozen reference. Finalization is performed after the timed contributions, with all four pools assembled in the current worker. This tests fidelity, not a malicious-client proof system. The pinned three-target reference equivalence remains unchanged.

| Variant | Cold from Start | Existing worker | Second-page HTTP path | Second-page IndexedDB path |
|---|---:|---:|---:|---:|
| Ordinary Brotli 9 | 3.309 s | 2.695 s | 4.531 s | 3.411 s |
| Ordinary gzip 9 | 7.176 s | 2.556 s | 4.917 s | 3.790 s |
| Shuffled Brotli 9 | 5.989 s | 3.077 s | 4.782 s | 3.576 s |

These total times are not controlled codec speedup estimates: CPU/network state and edge warmness vary, and each mode uses its own fixed seed index. In the ordinary Brotli cold run, asset acquisition was 1.113 s, restoration 284 ms, and molecular work 1.700 s. Later molecular runs on the same machine took about 2.6–3.1 s. The incoming artifact response records `CF-Cache-Status: HIT`, `X-Delivery-Cache: HIT`, Age and the MAA edge identifier. Browser-cold and edge-cold are distinct conditions; this trial establishes the former with the latter warm.

HTTP caching alone did not eliminate the second-page artifact request in this control: its new CF-Ray and resource timing show another network fetch. A fresh worker reading verified IndexedDB did avoid the artifact download. Cached response headers alone are not proof that the browser used its HTTP cache. All persistent artifact bytes are rehashed before restoration.

## Range, chunks and the first-result constraint

A range probe against the delivered Brotli object returned 200 with no Content-Range. This route does not provide usable partial-object/resume semantics. Do not claim range support or use that response as an independently decodable chunk. Its headers differ from the normal GET path, so scientific correctness is validated on ordinary complete GETs, not range responses.

The current lossless loader and hash gate require the complete artifact before a unit starts. Splitting the download cannot produce an earlier scientific result from only a partial map. Independent chunks could help retry/resume or some network paths, but incur more requests and lose cross-chunk compression. No chunking speedup is measured here. Given a 1.113 s desktop asset phase, measure the phone's complete Brotli path first; introduce chunking only if that identifies a transport problem it can solve. Changing the loader to use incomplete maps would be outside this experiment's frozen scientific scope.

## Physical-phone protocol

Use the new site in a fresh Safari session with no prior data/cache for this origin, and mark that condition explicitly. Private browsing alone is not enough if another private tab already used this origin. The page records the reported condition and a prior-visit marker; it cannot independently certify that Safari's HTTP cache is empty. No query-string cache busting, forced reload or service-worker interception is used for assets.

Select ordinary Brotli 9 and the actual power setting. Keep the page visible. The first page measures a cold restoration and existing-worker contribution; an automatic full navigation then measures HTTP-only restoration and a separate persistent-cache restoration. The page checks all pool/trace signatures and the original aggregate before saving. It records navigation, Start-to-result, and navigation-to-result excluding time spent reading the form; do not conflate them. Initial controls preceded addition of the last timing field and retain their original Start-based scope.

The three physical-phone measurements above complete this initial protocol. Cross-session persistence after closing Safari and OS eviction remain separate longer-term tests; the automatic second navigation only demonstrates persistence across page/worker replacement.

## Reproduction

- `node scripts/package_vina_cdn.mjs` builds only allowlisted public assets and verifies all six lossless round trips.
- `wrangler deploy --config cloudflare/vina-cdn/wrangler.json` deploys them; configure `UPLOAD_KEY` as a secret, never in source. The namespace ID is an identifier, not a credential.
- `node scripts/benchmark_vina_cdn.cjs` tests three codecs in fresh Chrome contexts, using the local secret file under ignored `tmp/vina-cdn`.
- `python scripts/analyze_vina_cdn.py --pull` retrieves KV reports and independently hashes raw outputs, checks completeness and finalization against the reference. Failed uploads/trials remain visible.

The few-second target is now observed on the physical phone under the stated conditions. The larger ranking and low-risk admission integration requirements remain unchanged.
