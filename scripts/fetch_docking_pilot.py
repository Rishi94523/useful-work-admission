"""Fetch pinned public software/examples for a local, non-deployed docking pilot."""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'tmp' / 'docking-pilot'
OUT = ROOT / 'docs' / 'evaluation' / 'docking_pilot_2026-09-06'
WEBINA = '4230729e7dad197b4c77912dffe30c8bcdd492ba'
VINA = '3c65c0b3e6c2c1d183f6a175ecb65e3c5ba91645'


def main():
    files = []
    for name in ['Webina.ts', 'vina.js', 'vina.wasm', 'vina.worker.js']:
        files.append((f'webina/{name}', f'https://raw.githubusercontent.com/durrantlab/webina/{WEBINA}/src/Webina/{name}'))
    files.append(('webina/LICENSE.md', f'https://raw.githubusercontent.com/durrantlab/webina/{WEBINA}/LICENSE.md'))
    for case in [
        ('2P16', '2P16_ligand_apixaban.pdbqt', '2P16_receptor_factor-Xa.pdbqt'),
        ('4LL3', '4LL3_ligand_darunavir.pdbqt', '4LL3_receptor_HIV-protease.pdbqt'),
        ('4TZ4', '4TZ4_ligand_S-Lenalidomide.pdbqt', '4TZ4_receptor_cereblon.pdbqt'),
    ]:
        for name in [case[0] + '_docking_params.txt', case[1], case[2]]:
            files.append((f'inputs/{name}', f'https://raw.githubusercontent.com/durrantlab/webina/{WEBINA}/docking_files/benchmarks/{name}'))
    files.append(('native/vina_1.2.7_win.exe', 'https://github.com/ccsb-scripps/AutoDock-Vina/releases/download/v1.2.7/vina_1.2.7_win.exe'))
    files.append(('native/LICENSE', f'https://raw.githubusercontent.com/ccsb-scripps/AutoDock-Vina/{VINA}/LICENSE'))
    records = []
    for relative, url in files:
        dest = CACHE / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            with urllib.request.urlopen(url, timeout=60) as response:
                payload = response.read(20_000_001)
            if len(payload) > 20_000_000:
                raise ValueError('Download exceeds pilot file cap')
            dest.write_bytes(payload)
        payload = dest.read_bytes()
        records.append({'path': relative, 'url': url, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()})
        print(relative, len(payload), flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'inputs_manifest.json').write_text(json.dumps({'webina_commit': WEBINA, 'vina_source_commit': VINA, 'vina_release': 'v1.2.7', 'scope': 'Public benchmark inputs, not newly discovered or experimentally validated binding pairs.', 'files': records}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
