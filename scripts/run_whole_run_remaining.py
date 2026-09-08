"""Sequential measurements; never overlap compute-heavy benchmark processes."""
import subprocess,sys
jobs=[
 ['node','scripts/benchmark_whole_run_science_wasm.mjs'],
 ['node','scripts/benchmark_whole_run_science_wasm.mjs','--control'],
 [sys.executable,'scripts/benchmark_whole_run_stock_control.py'],
 ['node','scripts/audit_whole_runs.mjs'],
 [sys.executable,'scripts/test_whole_run_integration.py'],
 [sys.executable,'scripts/build_whole_run_vina.py','--no-trace'],
 ['node','scripts/benchmark_whole_run_trace_ablation.mjs'],
 [sys.executable,'scripts/analyze_whole_run_science.py','--wasm'],
 [sys.executable,'scripts/analyze_whole_run_economics.py'],
]
for job in jobs:
 print('Starting '+ ' '.join(job),flush=True)
 subprocess.run(job,check=True)
