"""Score amendment 15b (N1-N4) from the native dense benchmark."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'local-research/native-dense-2026-09-28'
AMENDMENT15_WIDE_VERIFY_B1 = 0.352   # ms, batched numpy verifier at B = 1 (amendment 15)


def main():
    rows = json.loads((DIR / 'results.json').read_text(encoding='utf-8')); by = {(r['model'], r['batch']): r for r in rows}
    n1 = all(r['n1_rejected'] == r['n1_total'] and r['n1_equal'] for r in rows)
    wide = by[('mnist-wide-mlp', 1)]
    n2 = wide['verify_ms'] * 5 <= AMENDMENT15_WIDE_VERIFY_B1
    n3 = wide['leverage_8pct'] >= 4 and wide['verify_eff_ms'] < 10
    n4 = all(by[('mnist-mlp', b)]['leverage_8pct'] < 4 for b in (1, 32))
    cpu_only = min(wide['median_ms']['fp32'], wide['median_ms']['int8'], wide['median_ms']['native_forward'])
    out = {'N1': n1, 'N2': n2, 'N2_speedup': AMENDMENT15_WIDE_VERIFY_B1 / wide['verify_ms'], 'N3': n3, 'N3_leverage': wide['leverage_8pct'],
           'N3_leverage_cpu_only': cpu_only / wide['verify_eff_ms'], 'N4': n4,
           'rows': [{k: v for k, v in r.items() if k != 'samples'} for r in rows]}
    (DIR / 'summary.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    print('N1 exact, all perturbations rejected:', n1)
    print('N2 wide verify %.4f ms, %.2fx faster than 0.352 ms (>= 5x): %s' % (wide['verify_ms'], out['N2_speedup'], n2))
    print('N3 wide B=1 L8 %.2f against %s (CPU-only best %.2f), >= 4: %s' % (wide['leverage_8pct'], wide['central_backend'], out['N3_leverage_cpu_only'], n3))
    print('N4 MNIST perceptron L8 %s < 4: %s' % ([round(by[('mnist-mlp', b)]['leverage_8pct'], 2) for b in (1, 32)], n4))


if __name__ == '__main__': main()
