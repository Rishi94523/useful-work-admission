"""Score amendment 15 (M1-M4) from the batched CPU benchmark and the GPU baseline."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'local-research/batched-leverage-2026-09-28'
AMENDMENT14_MAX_V = 5.691   # largest verification time per admission covered by the amendment-14 grid (ms)


def main():
    rows = json.loads((DIR / 'results.json').read_text(encoding='utf-8'))
    gpu = {(r['model'], r['batch']): r for r in json.loads((DIR / 'gpu_central.json').read_text(encoding='utf-8'))['rows']}
    by = {(r['model'], r['batch']): r for r in rows}; models = sorted({r['model'] for r in rows}, key=[r['model'] for r in rows].index)
    m1 = all(r['m1_rejected'] == r['m1_total'] and r['m1_equal_per_input'] for r in rows)
    ratio = {m: by[(m, 32)]['verify_per_input_ms'] / by[(m, 1)]['verify_per_input_ms'] for m in models}
    m2 = all(v <= 1 / 3 for v in ratio.values())
    region = [r for r in rows if r['batch'] == 32 and r['leverage_8pct'] >= 4 and r['verify_eff_ms'] < 10 and r['budget_phone_within_patience']]
    m3 = bool(region)
    for r in rows:
        g = gpu[(r['model'], r['batch'])]; r['gpu_central_ms'] = g['gpu_central_ms']; r['leverage_gpu_8pct'] = g['gpu_central_ms'] / r['verify_eff_ms']
    m4 = all(r['leverage_gpu_8pct'] < 1 for r in rows)
    over = [(r['model'], r['batch'], round(r['verify_eff_ms'], 2)) for r in rows if r['verify_eff_ms'] > AMENDMENT14_MAX_V]
    print('%-15s %5s %9s %9s %9s %7s %7s %8s %9s %8s' % ('model', 'B', 'C cpu', 'V eff', 'V/input', 'L0', 'L8', 'L8 gpu', 'trace KB', 'budget s'))
    for r in rows:
        print('%-15s %5d %9.3f %9.3f %9.4f %7.2f %7.2f %8.3f %9.1f %8.1f' % (r['model'], r['batch'], r['central_ms'], r['verify_eff_ms'], r['verify_per_input_ms'],
              r['leverage_no_audit'], r['leverage_8pct'], r['leverage_gpu_8pct'], r['trace_bytes'] / 1e3, r['budget_phone_s']))
    print('M1 all perturbations rejected and outputs equal per-input:', m1)
    print('M2 per-input V at B=32 <= 1/3 of B=1: %s %s' % (m2, {m: round(v, 3) for m, v in ratio.items()}))
    print('M3 some model at B=32 with L8 >= 4, V < 10 ms, budget phone within 10 s: %s %s' % (m3, [(r['model'], round(r['leverage_8pct'], 2)) for r in region]))
    print('M4 GPU baseline: no model reaches L8 >= 1 at any B:', m4, '| max', round(max(r['leverage_gpu_8pct'] for r in rows), 3))
    print('Availability: cells above the amendment-14 range (need the grid):', over or 'none')
    summary = {'M1': m1, 'M2': m2, 'M2_ratios': ratio, 'M3': m3, 'M3_points': [(r['model'], r['leverage_8pct'], r['verify_eff_ms']) for r in region],
               'M4': m4, 'max_gpu_leverage': max(r['leverage_gpu_8pct'] for r in rows), 'availability_grid_needed': over,
               'rows': [{k: v for k, v in r.items() if k != 'samples'} for r in rows]}
    (DIR / 'summary.json').write_text(json.dumps(summary, indent=1), encoding='utf-8')


if __name__ == '__main__': main()
