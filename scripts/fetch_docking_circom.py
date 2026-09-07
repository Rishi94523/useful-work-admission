"""Fetch the pinned Windows Circom compiler and enforce the recorded checksum."""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
record=json.loads((ROOT/'docs/evaluation/docking_pilot_2026-09-06/circom_binary.json').read_text())
dest=ROOT/'tmp/docking-pilot/circom.exe'
if dest.exists():payload=dest.read_bytes()
else:
    with urllib.request.urlopen(record['url'],timeout=90) as response:payload=response.read(15_000_001)
if len(payload)!=record['bytes'] or hashlib.sha256(payload).hexdigest()!=record['sha256']:
    raise ValueError('Circom compiler checksum/size mismatch')
dest.parent.mkdir(parents=True,exist_ok=True)
if not dest.exists():dest.write_bytes(payload)
print('Pinned Circom compiler verified')
