"""Score amendment 14b (D1-D3) from the phone inference reports.

Inputs: local-research/device-inference-2026-09-28/timing_*.json (downloaded
from the collector) and the exported models' expected trace hashes. D1 is
checked against the export, not the page's own flag. Medians pool every run
from a phone model across its reports; a warm-only median (first repetition of
each input dropped) is reported alongside as a sensitivity check. A measurement
is excluded if the page logged a visibility change while timing was running.
"""
import json
import statistics
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / 'local-research/device-inference-2026-09-28'
EXPORT = ROOT / 'tmp/vina-cdn/public/inference'
NATIVE_SHA = 1.25e6
NATIVE_SCRYPT_MS = json.loads((ROOT / 'local-research/inference-leverage-2026-09-28/native_scrypt.json').read_text(encoding='utf-8'))['median_ms']
BUDGET = 'Samsung M30s'
MODELS = ['mnist-mlp', 'mnist-cnn', 'cifar-cnn', 'mnist-wide-mlp', 'vgg11-bn']


def expected():
    out = {}
    for name in MODELS:
        m = json.loads((EXPORT / name / 'model.json').read_text(encoding='utf-8'))
        out[name] = {i['file']: i['trace_sha256'] for i in m['inputs']}
    return out


def main():
    exp = expected(); reports = [json.loads(f.read_text(encoding='utf-8')) for f in sorted(DIR.glob('timing_*.json'))]
    reports = [r for r in reports if r.get('page') == 'inference-v1' and not r.get('error')]
    assert all(not r['visibility'] for r in reports), 'A visibility change during timing needs per-measurement exclusion'
    phones = {}
    for r in reports: phones.setdefault(r['device_model'].strip(), []).append(r)
    assert len(phones) >= 3 and BUDGET in phones, 'Amendment 14b needs three phones including the budget phone'
    checked = mismatched = 0; rows = {}
    for phone, rs in phones.items():
        row = {'reports': len(rs), 'user_agent': rs[0]['user_agent'], 'cores': rs[0]['hardware_concurrency'], 'models': {}}
        for name in MODELS:
            runs = [x for r in rs for m in r['models'] if m['name'] == name for x in m['runs']]
            for x in runs:
                checked += 1; mismatched += x['trace_sha256'] != exp[name][x['input']]
            row['models'][name] = {'median_ms': statistics.median(x['ms'] for x in runs),
                                   'warm_median_ms': statistics.median(x['ms'] for x in runs if x['rep'] > 0), 'runs': len(runs)}
        sha = statistics.median(r['sha_rate'] for r in rs); scr = statistics.median(t for r in rs for t in r['scrypt_ms'])
        row.update(sha_rate=sha, scrypt_median_ms=scr, sha_ratio=NATIVE_SHA / sha, scrypt_ratio=scr / NATIVE_SCRYPT_MS)
        rows[phone] = row
    b = rows[BUDGET]; vgg = {p: r['models']['vgg11-bn'] for p, r in rows.items()}
    fastest = min(vgg, key=lambda p: vgg[p]['median_ms'])
    d1 = mismatched == 0; d2 = b['scrypt_ratio'] <= b['sha_ratio'] / 3
    d3 = vgg[BUDGET]['median_ms'] >= 3 * vgg[fastest]['median_ms']
    d3_warm = vgg[BUDGET]['warm_median_ms'] / min(v['warm_median_ms'] for v in vgg.values())
    out = {'D1': d1, 'traces_checked': checked, 'traces_mismatched': mismatched, 'D2': d2, 'D3': d3,
           'D3_ratio': vgg[BUDGET]['median_ms'] / vgg[fastest]['median_ms'], 'D3_warm_ratio': d3_warm, 'fastest_vgg_phone': fastest,
           'native_sha': NATIVE_SHA, 'native_scrypt_ms': NATIVE_SCRYPT_MS, 'phones': rows}
    (DIR / 'summary.json').write_text(json.dumps(out, indent=1), encoding='utf-8')
    print('%-20s %6s %8s %7s %8s %7s | %s' % ('phone', 'n', 'SHA/s', 'x nat', 'scrypt', 'x nat', ' / '.join(MODELS) + ' (median ms)'))
    for p, r in rows.items():
        print('%-20s %6d %8.0f %7.1f %8.0f %7.1f | %s' % (p, r['reports'], r['sha_rate'], r['sha_ratio'], r['scrypt_median_ms'], r['scrypt_ratio'],
              ' / '.join('%.1f' % r['models'][n]['median_ms'] for n in MODELS)))
    print('D1 all %d trace hashes match the export: %s' % (checked, d1))
    print('D2 budget scrypt ratio %.2f <= SHA ratio %.1f / 3 = %.2f: %s' % (b['scrypt_ratio'], b['sha_ratio'], b['sha_ratio'] / 3, d2))
    print('D3 budget VGG %.0f ms vs fastest (%s) %.0f ms = %.2fx (>= 3): %s; warm-only %.2fx' % (
        vgg[BUDGET]['median_ms'], fastest, vgg[fastest]['median_ms'], out['D3_ratio'], d3, d3_warm))


if __name__ == '__main__': main()
