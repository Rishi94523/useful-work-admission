# Bounded search: scaling and audit evidence

Experiments on 7 September 2026, one Windows desktop (Ryzen 7 7435HS, 16 logical processors, about 23.7 GiB visible RAM; Python 3.14, Node 24.4.0, Chrome 152.0.7977.76). This directory extends the earlier docking pilot. The original integer contact circuit is **an arithmetic calibration, not scientifically validated docking**.

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
