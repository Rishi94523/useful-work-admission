"""Score amendment 21 (W1-W5) and add the budget-phone extrapolation."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'local-research/width-sweep-2026-09-29'
PHONES = json.loads((ROOT / 'local-research/device-inference-2026-09-28/summary.json').read_text(encoding='utf-8'))['phones']
WIDE_MACS = 784 * 2048 + 2048 * 2048 + 2048 * 10


def main():
    rows = json.loads((DIR / 'results.json').read_text(encoding='utf-8'))
    gpu = {r['width']: r['gpu_central_ms'] for r in json.loads((DIR / 'gpu.json').read_text(encoding='utf-8'))['rows']}
    ns_per_mac = PHONES['Samsung M30s']['models']['mnist-wide-mlp']['median_ms'] * 1e6 / WIDE_MACS
    for r in rows:
        r['central_all_ms'] = min(r['central_cpu_ms'], gpu[r['width']])
        r['leverage_all_8pct'] = r['central_all_ms'] / r['verify_eff_ms']
        r['budget_phone_ms_extrapolated'] = r['macs'] * ns_per_mac / 1e6
    w1 = all(r['w1_equal'] and r['w1_rejected'] == r['w1_total'] for r in rows)
    l0 = [r['leverage_cpu_no_audit'] for r in rows]
    w2 = all(b > a for a, b in zip(l0, l0[1:])) and next(r for r in rows if r['width'] == 4096)['leverage_cpu_no_audit'] >= 4
    w3 = all(r['leverage_cpu_8pct'] < 12.5 for r in rows)
    w4 = all(r['leverage_all_8pct'] < 4 for r in rows)
    first = next((r for r in rows if r['leverage_cpu_8pct'] >= 4), None)
    w5 = first is not None and first['weight_bytes'] > 4e6
    out = {'W1': w1, 'W2': w2, 'W3': w3, 'W4': w4, 'W5': w5, 'crossover_width': first and first['width'],
           'budget_phone_ns_per_mac': ns_per_mac, 'rows': [{k: v for k, v in r.items() if k != 'samples'} for r in rows]}
    (DIR / 'summary.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    print('%6s %9s %9s %7s %7s %8s %9s %10s' % ('width', 'C cpu', 'C gpu+', 'L0 cpu', 'L8 cpu', 'L8 +gpu', 'weights', 'phone ms*'))
    for r in rows:
        print('%6d %9.3f %9.3f %7.2f %7.2f %8.2f %8.1fMB %10.0f' % (r['width'], r['central_cpu_ms'], r['central_all_ms'], r['leverage_cpu_no_audit'],
              r['leverage_cpu_8pct'], r['leverage_all_8pct'], r['weight_bytes'] / 1e6, r['budget_phone_ms_extrapolated']))
    print('W1 exact:', w1, '| W2 L0 rises and >=4 at 4096:', w2, '| W3 L8 < 12.5:', w3, '| W4 with GPU L8 < 4:', w4,
          '| W5 crossover weights > 4 MB:', w5, '(width', out['crossover_width'], ')')


if __name__ == '__main__': main()
