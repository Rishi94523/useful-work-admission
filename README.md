# Useful Work Admission

Repository: https://github.com/Rishi94523/useful-work-admission

A browser admission system in which the work a visitor performs is **real
scientific computation** rather than an artificial puzzle. A visitor's browser
executes a bounded unit of AutoDock Vina molecular docking; the server verifies
that unit far more cheaply than producing it; and the scientific results are
aggregated across contributors into usable virtual-screening output.

The research question is whether anonymous browsers can contribute useful work
that is verified cheaply, within a bounded access delay, even when some
contributors submit malicious results or disappear.

See [STATUS.md](STATUS.md) for what is currently established and what is not.

## Why docking

A useful-work admission scheme needs a workload that is genuinely wanted by
someone, expensive to produce, cheap to check, and safe to hand to an untrusted
client. Molecular docking fits: each ligand state is an independent search, the
result is verifiable by replay, and a wrong answer degrades a screening campaign
rather than corrupting a shared model.

The workload is scientific computation, not ML inference. An earlier MNIST-based
demonstrator explored the same admission question with distributed inference;
that phase is retained in git history and a separate local legacy archive.
Its inference server, widget,
SDK, models and training tools are not part of the current system.

## Design

**Independent units.** A browser need not complete an entire ligand docking job.
Vina's exhaustiveness-32 search decomposes into 32 independently executable
tasks whose merged result reproduces the monolithic run exactly, including raw
minima and search traces.

**Post-commit challenge.** A client commits to its output; the server may then
demand a complete replay of any assigned unit. Honest clients always pass.
Replay costs the server one unit, not the whole campaign.

**One-use credits.** Completed units cannot earn duplicate credit within the
trusted identity domain. Historical precomputation is accepted as one-use
scientific credit rather than misclassified as fresh CPU work.

**Prepared-state delivery.** Grid map computation dominates cold start, so
browsers restore a losslessly serialised prepared state from a CDN and verify it
against a hash, instead of recomputing maps.

**Risk-tiered admission.** Server-side risk scoring, work tiers, abandonment
penalties, retry limits and cooldown. This is an admission-cost mechanism, not a
general bot-detection or Sybil-resistance solution.

## Verification and its limits

Verification rests on exact replay of independent units and on sampled whole-run
audits, not on a cryptographic proof of effort. Two limits are load-bearing and
stated up front:

- Sampled auditing bounds an attacker's expected cost; it does not prove that
  every admitted request performed work. At a 0.1 audit probability, zero-work
  requests in a trusted tier can pass unaudited.
- Cheap identity resets defeat per-identity exposure caps. New identities must
  not inherit trusted eligibility merely because their initial risk score is
  zero.

## Scientific validation

Five DUD-E targets were selected from published Vina results *before* any local
docking, with the protocol, panel-selection rule, gates and known deviations
frozen in [`benchmarks/vina_published_validation.json`](benchmarks/vina_published_validation.json).
All 706 stock jobs completed and all five targets passed their predeclared
ranking and redocking gates. Preserved negative results are not removed.

Build equivalence is gated separately: the instrumented split driver must be
coordinate-identical to an uninstrumented reference built from the same sources
with the same compiler, and agreement with the official prebuilt binary is
established at panel level rather than by trajectory comparison. Cross-toolchain
trajectory equality is unattainable for a Monte Carlo search and is not required.

## Layout

```text
benchmarks/          predeclared protocol definitions, hash-pinned
scripts/             campaign runners, verification gates, analysis
research/native/     instrumented Vina drivers and task transport
research/            campaign and admission-policy modules
research/tests/      scheduler, admission and validation tests
cloudflare/vina-cdn/ prepared-state static delivery configuration
```

Working reports, generated evidence and raw device logs are kept locally and are
not tracked.

## Reproducing the validation

Requires a C++17 compiler, Boost, and the upstream Vina sources and official
binary staged under `tmp/` (see the protocol file for the pinned hashes).

```bash
python scripts/build_vina_reference.py
```

```bash
python scripts/verify_build_equivalence.py
```

```bash
python scripts/verify_panel_concordance.py
```

Every runner writes a frozen execution manifest recording protocol, input,
build and runner hashes, and refuses to continue if a manifest would change.

## Development

Run commands from the repository root with Python 3.11+ and Node.js 18+.
The current implementation is a research prototype; the archived inference
API and its npm workspace are not a docking deployment entry point.

Lightweight scheduler, admission and analysis checks (no docking campaign):

```bash
python -m unittest research.tests.test_pool_admission research.tests.test_vina_pool_campaign research.tests.test_published_matched research.tests.test_publication_guard
```

Molecular builds and experiments require the dependencies and pinned inputs
specified by their benchmark protocols. Browser automation also requires
Playwright; several experiment scripts still reference a local installation
and need path configuration on another machine. Optional proof experiments
have their own npm package under `research/docking-zk/`.

## License

MIT
