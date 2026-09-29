# Useful Work Admission

Research code and results for *The Price of Utility: Verification Leverage in
Useful-Work Browser Admission*.

Proof-of-work challenges admit browser visitors by making them spend
computation that is then discarded. This repository measures what it costs to
make that computation useful instead, on two workload classes:

- **Molecular docking.** Each admission carries bounded AutoDock Vina units
  (256,000 energy evaluations) whose outputs join a virtual screening
  campaign. Results are verified by exactly replaying one secretly drawn unit
  per four-unit bundle, bound by a committed search trace.
- **Image classification for data labelling.** Five small classifiers run in
  exact integer arithmetic; each layer is verified algebraically with secret
  Freivalds projections instead of by replay.

The paper's finding is a trade-off. Docking buys four to ten units of useful
work per unit of verification but needs replay, so verifier capacity decides
who is admitted under attack. The classifiers verify in milliseconds and stay
available, but the server can compute their answers almost as cheaply as it
checks them. Batching and an optimised native verifier did not change this.

## Predeclared protocol

Every experiment follows
[`docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md`](docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md).
Its nineteen amendments (1–16, with 9b, 14b and 15b) each record predictions
and thresholds and were committed before the experiment they govern; failed
predictions are reported, not removed. Run manifests record the protocol
version they ran under, and

```bash
python scripts/audit_predeclaration.py
```

checks that every predeclared result set was produced after its amendment's
commit. [`STATUS.md`](STATUS.md) summarises what each experiment established
and what it did not.

## Where each result comes from

| Paper section | Experiment | Runner / analysis |
| --- | --- | --- |
| 5.1 Decomposition preserves screening | Stock Vina qualification; matched split vs. monolithic campaign | `run_published_vina.py`, `run_published_matched.py`, `benchmark_vina_matched_ranking.py` |
| 3.2 Build equivalence | Instrumented driver vs. reference builds | `verify_build_equivalence.py`, `verify_panel_concordance.py` |
| 5.2 Phones reproduce units | Browser WebAssembly timing studies | `research/*_device_page.html`, `analyze_vina_devices.py`, `analyze_subpuzzle_timing.py` |
| 5.3 Faking the work | Unit-level attacks under replay; admission economics | `adversarial_replay_eval.py` |
| 5.4 Corrupting the science | Pool tampering, poisoning projection, rescoring driver | `scientific_integrity_eval.py`, `verify_driver_v2.py` |
| 5.5 Availability vs. proof of work | Priority queue, attested lane, corrected replication, PoW gate baseline | `evaluate_priority_admission.py`, `evaluate_attested_admission.py`, `evaluate_admission_amendment12.py`, `evaluate_admission_amendment13.py` and their `analyze_*` scripts |
| 5.6 Verification leverage | Classifier leverage, availability grid, phones, batching, native verifier | `train_inference_models.py`, `benchmark_inference_leverage.py`, `evaluate_admission_amendment14.py`, `analyze_inference_leverage.py`, `analyze_device_inference.py`, `benchmark_batched_leverage.py`, `benchmark_gpu_central.py`, `benchmark_native_dense.py` and their `analyze_*` scripts |

All runners are in `scripts/`. The inference verifier is in
`research/inference/` (`quantized_net.py`, `batched.py`, and native kernels in
`research/inference/native/`).

## Results data

Result ledgers are not tracked in git. They are published as a separate data
archive (withheld during anonymous review, cited in the final paper). Place its
`results/` directory at the repository root as `local-research/`, and its
`models/inference-models/` at `data/inference-models/`.

## Rebuilding the figures and paper

```bash
python scripts/make_paper_figures.py
```

```bash
python scripts/build_manuscript.py --pdf
```

Figures need Python with matplotlib; the PDF build needs LaTeX, latexmk and the
Springer Nature template files described in `docs/paper/README.md`.

## Rerunning experiments

Requirements:
- Python 3.11+ with NumPy and PyTorch (the inference study used PyTorch 2.14, CPU build; the GPU baseline a separate CUDA build).
- Node.js 18+.
- For docking: a C++17 compiler, Boost, and the upstream Vina sources and official binary staged under `tmp/` with the hashes pinned in `benchmarks/`.
- Public datasets (DUD-E panels, MNIST, CIFAR-10, CIFAR-10.1, the pretrained VGG11-BN), pinned by hash in `benchmarks/` and `research/inference/workload_provenance.json`.

The native verifiers are built with:

```bash
gcc -std=c11 -O3 -march=native -Wall -Wextra -Werror -shared -o tmp/native-verifier/dense_check.dll research/inference/native/dense_check.c
```

Lightweight scheduler and admission tests (no docking campaign):

```bash
python -m unittest research.tests.test_pool_admission research.tests.test_vina_pool_campaign research.tests.test_published_matched research.tests.test_publication_guard
```

This is a research prototype, not a deployable admission service. Some browser
experiment scripts assume a local Playwright installation and need path
configuration on another machine.

## Layout

```text
benchmarks/          predeclared benchmark protocols, hash-pinned
docs/                adversarial protocol and manuscript sources
research/            admission, campaign and verification modules
research/inference/  exact-integer classifiers and verifiers
research/native/     instrumented Vina drivers and task transport
research/tests/      scheduler, admission and validation tests
scripts/             experiment runners, analyses, figure and paper builders
cloudflare/          static delivery configuration for the phone studies
```

## License

MIT. AutoDock Vina and other upstream components are fetched and patched at
build time rather than redistributed, and keep their own licences.
