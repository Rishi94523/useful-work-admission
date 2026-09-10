# Resource use and risk-conditioned admission

The molecular search, seed stream, scheduler, one-use credits, raw minima pools,
and original merge/finalization remain unchanged. All storage experiments build
under `tmp/vina-resources`; the reference binaries remain under `tmp/vina-tasks`.

## Memory: the maps were not the main problem

The original FA10 build retains approximately 344.3 MiB of allocator-live data
after initialization. Its phase measurements attribute approximately 174.4 MiB
to per-atom-pair interaction tables and another 154.8 MiB to atom-type tables.
Grid storage is approximately 13.9 MiB. Temporary table and grid copies raise
observed live allocation to approximately 512.6 MiB. Emscripten then retains a
549.5 MiB linear memory allocation even after those temporaries are freed.

Each interaction table contains 12,803 distance samples at the unchanged
32-samples-per-squared-Angstrom resolution and 20 Angstrom maximum cutoff.
Each sample stores three doubles across the fast and smooth lookup arrays.
The full type table alone has 528 entries. The 20 Angstrom extent also supports
macrocycle glue potentials; reducing it indiscriminately would change semantics.

Three storage changes were investigated:

1. Move temporary tables and grids into persistent state. FA10 allocated memory
   falls from 549.5 to 381.6 MiB, but retained live data is unchanged.
2. Intern equivalent ligand XS atom types and construct receptor/type tables on
   first use. All original scoring values, interpolation, cutoffs and search
   parameters remain unchanged. The specialization rejects AD4, whose scoring
   depends on more than XS atom type. Lazy initialization is single-threaded.
3. In the single-task adapter, allocate only the selected task's model while
   still drawing the complete original seed sequence. Other modes continue to
   construct their original task containers. This is storage ownership, not a
   change in scientific decomposition.

Initial Chrome measurements, before the selected-task allocation improvement:

| Target | Original init | Compact init | Original heap after init | Compact heap after init | Original peak renderer working set | Compact peak renderer working set |
|---|---:|---:|---:|---:|---:|---:|
| FA10 | 4.61 s | 3.02 s | 549.5 MiB | 42.7 MiB | 608.5 MiB | 168.1 MiB |
| HS90A | 2.88 s | 2.67 s | 457.9 MiB | 35.6 MiB | 518.7 MiB | 152.2 MiB |
| TRYB1 | 3.41 s | 2.38 s | 457.9 MiB | 29.6 MiB | 548.3 MiB | 175.6 MiB |

These are measured individual runs, not timing confidence intervals. Some
scientific processes were running concurrently. Each probe includes four search
budgets followed by an N=128 selected-task call. That last call unnecessarily
copied 128 models in the earlier adapter, increasing compact heap to 74–89 MiB.
The selected-task allocation experiment addresses this separately.

The subsequent FA10 selected-task build stays at **51.2 MiB maximum observed
post-run heap**, including the N=128 call, with **133.1 MiB peak renderer working
set**. Its five raw outputs/traces match the original. All three storage variants
also pass the three-target original-finalizer regression. Startup remains 3.13 s
in this additional measurement; the memory win does not solve cold-start delay.

Working set comes from Windows `GetProcessMemoryInfo`, including its OS lifetime
peak counters, not JavaScript heap statistics. The sampler polls the isolated
benchmark browser's CDP-reported process IDs every approximately 25 ms. Renderer
working set includes Chrome overhead; it is not molecular allocation alone.
Private committed memory is recorded separately and is not private resident
memory. Summing browser process working sets double-counts shared pages, so these
numbers do not pretend to measure unique system-wide physical RAM. No sampling
access errors occurred in these initial probes.

All 15 tested Chrome raw-pool and trace comparisons across three targets match
between the original and compact builds. Separate same-runtime WASM tests also
match four complete pools per target and the original explicit-receptor final
poses. This is bounded regression evidence, not a proof covering every molecule,
macrocycle, flexible receptor, browser or compiler.

### Deployment implication

The original half-gigabyte heap is avoidable. The compact build is a credible
laptop candidate; it is no longer reasonable to reject browser docking solely
because of that original memory measurement. Phone feasibility remains
unmeasured: headless desktop Chrome is not an Android/iOS memory or thermal test.
Require physical-device tests before claiming normal-phone support.

Cold grid construction still dominates much of initialization after table
compaction. Reuse one worker/engine for repeated tasks on the same inputs,
preload assets when appropriate, and avoid concurrent duplicate workers. Module
loading was already much smaller than map/table setup; shrinking the roughly
half-megabyte WASM download alone will not eliminate multi-second initialization.
Changing 30A boxes to smaller boxes is a scientific parameter change and must be
validated against stock Vina on the same boxes. Maps loaded from disk also need
the explicit-receptor finalizer initialized correctly; the earlier direct
`load_maps` shortcut did not do that. These are separate experiments, not assumed
performance wins.

## Low-risk admission is a different guarantee

A deferred audit probability p makes expected replay work p times one complete
run, giving an approximate 1/p useful-client/replay-compute ratio before setup,
storage, queues and networking. It does **not** prove that a particular admitted
low-risk visitor performed work. A zero-work attacker can consume access before
the deferred verdict arrives, including when its result is eventually rejected.

The implemented policy simulation covers 72 probability/cap/lag combinations,
100,000 simulated identities each, plus 115 immediate-bundle settings. It leaves
the production and research admission implementations unchanged. For repeated
invalid submissions from one identity, let T be geometric(p), D the number of
additional admissions before a verdict, and K the identity exposure cap:

`bad_grants = min(T + D, K)`

`E[bad_grants] = sum((1-p)^max(0,k-D), k=0..K-1)`

At p=5%, D=2 and K=20, an attacker receives **14.06** bad admissions on average
before stopping, even though honest client/replay compute is approximately 20:1.
At K=5 it receives 4.85. A disposable identity used once receives its deferred
admission regardless of later punishment. Cheap unlimited fresh identities
therefore defeat this policy's per-identity economics. Global issuance limits
bound resource consumption, but attackers can still consume the allowed capacity.

Recommended division:

- **Established low-risk sessions:** bounded provisional access, one useful run,
  random deferred replay, small outstanding exposure, and explicit delayed-credit
  and scientific-validation state. Eligibility must come from a trusted outer
  policy; a fresh cookie or client-asserted user ID is insufficient.
- **Unknown or elevated-risk sessions:** complete multi-run bundles and the
  existing post-commit random replay before admission. Choose N and q from the
  explicit cheating curve, not from an informal label such as "high security".
- **Queue pressure or repeated failure:** reduce issuance or deny/defer access.
  Never silently reduce q or skip selected audits to keep the page responsive.

The current outer prototype starts new identities at risk zero and was written
for the earlier bounded-run campaign class. It must not be connected unchanged
to a reputation-only deferred path. Trusted low-risk eligibility and integration
with the newer pool scheduler are **not deployed** by this experiment.

For complete bundles with C correct outputs among N, the unchanged verifier gives
`P(pass)=choose(C,q)/choose(N,q)` under binding commitments and unpredictable draws.
That is conditional on correct output availability, not a universal lower bound
on work performed after issuance. One-use campaign credits prevent consuming the
same unit repeatedly; they do not make anonymous identity creation costly.

### Scientific trust is not admission trust

Random admission audits do not validate every unsampled scientific output. Keep
provisional pools out of definitive claims, replay candidates used for reported
top-ranked results, and replicate selected units to measure missed coverage and
fraud. Top-k checks help remove injected winning poses, but cannot recover all
good poses suppressed by malicious contributors. Verification also cannot undo
an admission already consumed.

The frozen pool scheduler has a replay-verified flag and digest-bound upgrades;
it does not yet have a full late-fraud revocation/quarantine workflow. A deferred
deployment needs that lifecycle. Invalid provisional work is not completed
scientific work; repair must not accidentally mint a second usable credit or
reissue an actually verified completed unit. This integration remains a concrete
engineering requirement, not an implemented feature of this report.

## Evidence and reproduction

- `scripts/build_vina_resource_probe.py`: isolated baseline/moves/compact builds.
- `scripts/benchmark_vina_resources.mjs`: Chrome runs and allocator phases.
- `scripts/sample_windows_working_set.py`: per-process OS memory counters.
- `scripts/validate_vina_resource_equivalence.mjs`: raw pools, traces, finalizer.
- `scripts/evaluate_deferred_vina_admission.py`: policy economics and attacks.
- Raw results: `docs/evaluation/vina_resources_2026-09-10/` and
  `docs/evaluation/vina_validation_2026-09-10/deferred_policy.json`.

## Primary references

- [Vina basic docking](https://autodock-vina.readthedocs.io/en/stable/docking_basic.html):
  official prepared 1iep inputs and 20A box used for the positive control.
- [Vina batch docking](https://autodock-vina.readthedocs.io/en/latest/docking_in_batch.html):
  serial ligand screening against a receptor is a supported scientific workflow.
- [DUD-E](https://dude.docking.org/): established active/decoy benchmark source.
  Our small subsets are not equivalent to reproducing its full target benchmark.
