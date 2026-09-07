# Bounded search: scaling and audit evidence

Experiments on 7 September 2026, one Windows desktop (Ryzen 7 7435HS, 16 logical processors, about 23.7 GiB visible RAM; Python 3.14, Node 24.4.0, Chrome 152.0.7977.76). This directory extends the earlier docking pilot. The original integer contact circuit is **an arithmetic calibration, not scientifically validated docking**.

The [full investigation and recommendation](../../research/BOUNDED_SEARCH_DIFFICULTY_LADDER_2026-09-07.md) also covers implemented real-grid search, a new exact protein-design proof, alternative proof systems and the distinction between scientific validity, certified coverage and fresh attacker effort.

## Measured proof scaling

`node_scaling.json` contains three isolated processes per tier, 2/8/16/32/64 candidates. `browser_scaling.json` contains two fresh Chrome processes per tier, including loopback key/WASM fetching in `fullProve`. Node's plain reference timings exclude its one-time Poseidon construction. Warm server verification pools 20 samples per Node process; cold verification is separately recorded. Trial ranges are observations, not confidence intervals.

`setup.json` contains **actual compiled circuits through 256 candidates**, with constraints, sizes, hashes and compiler memory. Keys and proofs were generated only through 64. `summary.json` explicitly separates those measurements from 128/256 resource projections. The simple projection envelope is documented by the summarizer and is not a guaranteed bound. Memory extrapolation is particularly weak because fixed runtime costs and allocation cliffs are substantial.

| Candidates | Constraints | Chrome proof median | Node proof median | Warm Node verification median | Key MiB |
|---:|---:|---:|---:|---:|---:|
| 2 | 13,302 | 0.962 s | 1.130 s | 6.86 ms | 7.78 |
| 8 | 51,486 | 3.073 s | 4.296 s | 6.69 ms | 30.23 |
| 16 | 102,398 | 5.819 s | 7.383 s | 7.36 ms | 60.16 |
| 32 | 204,222 | 10.862 s | 11.301 s | 10.78 ms | 120.03 |
| 64 | 407,870 | 21.511 s | 39.283 s | 11.35 ms | 239.77 |

Public statement size is fixed at 51 field elements. The proof JSON is 720–726 bytes; this excludes the public statement, keys and protocol envelope. All 25 archived proofs pass independent verification; 75 altered statements and one wrong-tier attempt are rejected by `verify_docking_ladder_evidence.mjs`. These are regression diagnostics, not a formal circuit audit.

Peak memory is externally sampled every 50 ms over each process's full lifetime. Node covers reference construction, proving and verification. Browser figures sum the Node asset server and its Chrome process tree; shared pages can be counted more than once. They are **not proof-only WASM memory**. JS heap snapshots are not peak allocations. Full browser memory and public key downloads are important deployment costs.

Setup uses a public phase-one transcript from the current PSE mirror, plus independent random local phase-two contributions. `setup_download.json` records the canonical source, download size and our local fingerprint. It does not certify an independent audit of the entire ceremony. Keys are development-only; setup secret material and large binaries are excluded from Git.

## Random audits

`audits.json` records exact sampling-without-replacement probabilities, retry amplification, required sample counts, and a local Merkle implementation. A mathematical transition-splicing diagnostic demonstrates that one false edge can skip many steps while leaving an accepting suffix. This is a counterexample to a generic raw-audit claim, not a proposed scientific workload or a discovered Vina exploit. Merkle timings cover local path checks; projected 5 ms score checks are explicitly separate estimates from the previous native pilot.

## Reproduction

First follow the previous pilot's input/compiler/dependency instructions. From the repository root:

```powershell
npm.cmd ci --prefix research/docking-zk
python scripts/fetch_docking_ladder_setup.py
python scripts/prepare_docking_ladder.py
python scripts/benchmark_docking_ladder.py
# Set installed Playwright and Chrome paths as in the previous pilot README.
python scripts/benchmark_docking_ladder_browser.py
python scripts/analyze_docking_audits.py
python scripts/summarize_docking_ladder.py
python -m unittest research.tests.test_merkle_search_audit -v
```

To verify the published proof corpus without downloading setup/proving keys:

```powershell
npm.cmd ci --prefix research/docking-zk
node scripts/verify_docking_ladder_evidence.mjs
```

Reruns replace timing JSONs; copy this directory first when comparing experiments. The smaller 2/8 proving keys require the previous pilot's setup script when regenerating proofs. Downloaded inputs, keys, compilation outputs and logs live under ignored `tmp/`. No production deployment or admission-credit endpoint is included.

## Scientific search pilots

`rigid_grid.json` contains 12,288 fixed-conformer poses per real protein/ligand case, 75 independent native Vina grid checks, quantized/float comparisons and local prepared-input timing. `grid_build.json` pins the oracle wrapper; `grid_lookup_cost.json` measures one authenticated-lookup circuit and **projects**, rather than measures, naive full-pose lookup constraints. Sparse cubic rotations produce poor best energies here; matching scores/rankings is not evidence of successful virtual screening. This grid workload has no complete proof implementation.

`cpd_source.json` identifies the authors' published 1BK2 energy model. `cpd_restricted_model.json` contains an exact neighborhood restriction: the published first incumbent and feasible single-site alternatives, with one fixed site and 23 binary choices. It is not the full published optimization problem. Large integers in this file require an exact parser; the preparation script exports a separate string-encoded model for JavaScript BigInt arithmetic.

`cpd_16.circom`/`cpd_64.circom` are generated campaign-specific circuits; `cpd_setup.json` records sizes/hashes/setup. `cpd_proofs.json` archives six Node proofs plus their public verification keys, with timings and memory; `cpd_browser.json` contains four Chrome proofs. `scientific_summary.json` records the comparison and validation. All ten proofs pass, 30 statement changes fail, and wrong-tier use fails. Exact polynomial costs agree with direct WCSP evaluation on 1,002 states, plus two wraparound bounded searches. These are correctness diagnostics, not a hardness proof or biological discovery.

```powershell
python scripts/build_docking_grid_export.py
python scripts/benchmark_rigid_grid_search.py
python scripts/measure_grid_lookup_cost.py
python scripts/fetch_cpd_model.py
python scripts/prepare_cpd_search.py
python scripts/setup_cpd_search.py
python scripts/benchmark_cpd_search.py
# Requires the same Playwright/Chrome environment variables as above.
python scripts/benchmark_docking_ladder_browser.py --cpd --counts 16 64
python -m unittest research.tests.test_scientific_search research.tests.test_merkle_search_audit -v
node scripts/verify_docking_ladder_evidence.mjs
python scripts/summarize_scientific_search.py
```

The native oracle is a trusted local process with synchronous IPC, not an exposed API. The Python timing baseline uses NumPy; no Python timing is represented as a browser benchmark. CPD preparation intentionally targets the pinned 1BK2 instance and checks the source incumbent. Changing the campaign/model requires regenerating circuits and development keys. Production trusted setup, concurrency and lease binding are not supplied by these research scripts.

Attribution: grid potentials and source interfaces come from [AutoDock Vina](https://github.com/ccsb-scripps/AutoDock-Vina); public input pairs from [Webina](https://github.com/durrantlab/webina); CPD model and incumbent from the authors of [A New Framework for Computational Protein Design through Cost Function Network Optimization](https://web-genobioinfo.toulouse.inrae.fr/~tschiex/CPD/). Preserve upstream citation/license requirements for redistributed inputs or derived datasets. No third-party executable or proving key is included in Git.
