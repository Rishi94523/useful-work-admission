# Startup cost and unobtrusive admission

The actual 256k iPhone test passed 6/6 independent raw-pool and trace hashes.
Warm calls took 1.009–1.035s, including a reused-worker second-batch median of
1.027s. Exactly one initialization occurred. Initialization took 5.149s; the
first result arrived 6.316s after Start. Maximum allocated WASM memory was
51.25MiB, not a measurement of resident memory. Total elapsed was 13.454s,
including an intentional two-second pause between batches.

The user suggests Low Power Mode explains the faster initialization compared
with the earlier 9.641s trial. That is plausible but unproven: mode, temperature,
browser compilation/cache state and background load were not controlled.
Factory instantiation also changed from 1.579s to 0.066s. Do not attribute the
whole difference to one cause or compare different work caps as a controlled
CPU-speed experiment. Apple documents reduced background activity in
[Low Power Mode](https://support.apple.com/en-la/101604).

## The measured initialization is not Wi-Fi waiting

The worker receives the receptor and ligand, constructs the WASM module and
writes inputs into its in-memory filesystem before timing `vt_init`. That
synchronous C++ call creates Vina, parses inputs, builds scoring structures,
computes affinity maps and saves the initial state. It contains no HTTP fetch.

In the new phone trial, first-result latency decomposes as:

| Component | Measured time |
|---|---:|
| Vina initialization | 5,149ms |
| First 256k call | 1,018ms |
| WASM factory instantiation | 66ms |
| Remaining startup/message overhead | 83ms |
| Total to first result | 6,316ms |

The remaining83ms is subtraction, not a dedicated network measurement: it
includes input transfer, module-import work and dispatch overhead. This test
does not provide uncached WAN latency, but the dominant5.149s is local compute.

## Largest initialization contributors

A new offline Node run uses the same WASM and inputs, loaded directly from disk
without HTTP. It takes 2.909s to initialize:

| Phase | Time | Approximate share |
|---|---:|---:|
| Maps and scoring setup | 2,697.7ms | 92.7% |
| Ligand parsing and pair tables | 112.9ms | 3.9% |
| Receptor parsing/setup | 96.0ms | 3.3% |
| Engine creation and initial-state save | 1.0ms | <0.1% |

This agrees with the earlier Chrome phase profile: about2.893s of3.126s lies
between `after_ligand` and `after_maps`. These are desktop phase measurements,
not measured per-phase iPhone percentages. The shared execution path makes this
the leading phone bottleneck hypothesis.

`compute_vina_maps` constructs scoring tables, populates a 30A box and prepares
explicit-receptor scoring. `cache::populate` traverses grid positions, nearby
receptor atoms and needed ligand atom types, evaluating and accumulating
interactions. This frozen browser build defaults to0.5A spacing: a60-voxel side has61
sample positions, giving226,981 positions per map. The phase includes lazy interaction tables and
`non_cache` setup; current markers do not isolate those from grid population.
The existing code already restricts maps to ligand atom types, so avoiding
unused maps is not a new unimplemented shortcut.

The WASM file is561,113bytes, receptor181,926bytes and ligand3,272bytes before
transport encoding. A large download of the executable is not the observed
five-second initialization bottleneck. The older549MiB allocation problem was
already reduced by compact tables; more memory reduction alone need not remove
grid construction time.

## What hosting can and cannot improve

Cloudflare static assets can deliver versioned WASM/JS/inputs through its cache
and configure browser caching. This improves repeat downloads and public-site
delivery, but it does not execute the browser's `vt_init` faster. There is no
evidence that moving the current LAN endpoint to the cloud would beat the LAN
for this phone. See [Cloudflare static assets](https://developers.cloudflare.com/workers/static-assets/)
and [cache headers](https://developers.cloudflare.com/workers/static-assets/headers/).

A browser Web Worker is a thread on the visitor's device; a Cloudflare Worker
runs server-side. Moving the assigned molecular search to Cloudflare would move
its cost away from the contributor. That does not meet the intended useful-work
admission property. Reusable preprocessing can instead be generated once and
served as immutable assets, while assigned seeded search stays on the client.

The highest-value optimization experiment is a lossless, versioned prepared
grid/scoring artifact, cached by receptor hash, box, spacing, scoring parameters,
required atom types and engine version. Measure download/decompression/hashing
and restoration against recomputation. Existing grids occupy much more memory
than the source PDBQT; precomputation trades CPU for transfer/storage and must be
benchmarked rather than assumed faster on all networks.

Simply replacing `compute_vina_maps` with stock `load_maps` is insufficient in
this build: the latter loads grids and sets the map flag but does not recreate
the scoring-table/explicit-receptor state established by the compute path.
Preserve that state and the original finalizer; require exact pool/trace and
finalization regression checks before adopting restoration. No prepared-state
optimization is implemented or claimed measured by this report.

Priorities: reuse the initialized worker within an active session; benchmark
lossless prepared-state restoration; cache versioned assets; then optimize
remaining local table/grid work. Shrinking the scientific box or coarsening the
grid would change the validated workload and is not the default optimization.

## The product should usually show no CAPTCHA page

Render useful page content immediately. After critical page work, use one
bounded browser worker to prepare and contribute while the visitor reads or
types. Keep completed, validated one-use admission credit available for the
next protected action; consume it atomically. Reuse the worker for later units
within the session, with pauses and a finite resource budget. Do not run an
endless compute loop merely because no overlay is visible.

For an immediate protected action before credit is ready, apply the existing
outer trust policy: trusted users may get the explicitly bounded provisional
path; risky users must still satisfy their required checks before the action.
Never manufacture verified credit or silently disable selected replay to avoid
displaying a wait. A page can usually remain usable while an individual action
is pending. Measure time-to-action and the percentage of actions that find
credit ready, rather than only whether a CAPTCHA overlay appeared.

Unobtrusive work in a visible page is feasible; reliable work after the phone is
locked or the tab hidden is not something to assume. WebKit documents that iOS
tabs can be suspended. Respect visibility/lifecycle changes, stop issuing new
units when hidden, and tolerate unfinished work without punishing normal users
as fraud. See [WebKit power guidance](https://webkit.org/blog/8970/how-web-content-can-affect-power-usage/).

Current `vt_run` is synchronous inside its worker. A stop message cannot pause
it midway until the call returns; the main page can terminate the worker, losing
that unfinished unit. Yielding between complete seeded units preserves the
existing decomposition. Mid-run cooperative checkpointing would require a
separate validated change and is not assumed here.

The goal is no puzzle and normally no interruption, with measurable limits on
delay and resource use. Zero delay for every anonymous first visit, guaranteed
work before every protected action, and no fallback cannot all be promised by
this architecture. The outer-layer policy must handle that remaining case.

Evidence: `scripts/profile_vina_startup_offline.mjs`,
`docs/evaluation/vina_startup_2026-09-13/offline_profile.json`, and the256k device
report `device_1789303164242-d149f892.json`. No extra64k test or scientific
architecture change was made.
