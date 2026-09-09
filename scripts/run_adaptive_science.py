"""Sequential compute-heavy science stages. Every stage persists progress."""
import json,subprocess,sys
from pathlib import Path
folder=Path('docs/evaluation/adaptive_docking_2026-09-08')
if '--science-only' not in sys.argv:
    subprocess.run([sys.executable,'scripts/benchmark_adaptive_loop.py','--calibrated'],check=True)
    subprocess.run([sys.executable,'scripts/evaluate_adaptive_policy.py'],check=True)
    subprocess.run(['node','scripts/investigate_trace_fingerprints.mjs'],check=True)
    subprocess.run([sys.executable,'scripts/build_whole_run_vina.py','--type-cache'],check=True)
    subprocess.run(['node','scripts/check_adaptive_engines.mjs'],check=True)
    subprocess.run([sys.executable,'scripts/benchmark_cached_admission.py'],check=True)
for t in json.loads((folder/'science_inputs.json').read_text())['targets']:
    if not t.get('preparation_failed'):
        subprocess.run(['node','scripts/benchmark_adaptive_science.mjs',t['target']],check=True)
subprocess.run([sys.executable,'scripts/benchmark_adaptive_stock.py'],check=True)
subprocess.run([sys.executable,'scripts/analyze_adaptive_science.py'],check=True)
subprocess.run([sys.executable,'scripts/analyze_adaptive_economics.py'],check=True)
