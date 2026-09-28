"""Native scrypt rate on one core (OpenSSL via hashlib), the reference for the
memory-hard device-disparity comparison (amendment 14). Standard interactive
parameters N=16384, r=8, p=1 (16 MB). The SHA-256 native reference is the
existing 1.25 million hashes/s per core measured under campaign load.
"""
import hashlib
import json
from pathlib import Path
import platform
import time
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'local-research/inference-leverage-2026-09-28'


def main():
    for _ in range(3): hashlib.scrypt(b'warm', salt=b'up', n=16384, r=8, p=1, maxmem=64 * 2**20, dklen=64)
    times = []
    for i in range(40):
        t = time.perf_counter(); hashlib.scrypt(b'pleaseletmein', salt=b'salt%d' % i, n=16384, r=8, p=1, maxmem=64 * 2**20, dklen=64)
        times.append((time.perf_counter() - t) * 1000)
    times.sort(); med = times[len(times) // 2]
    row = {'n': 16384, 'r': 8, 'p': 1, 'memory_mb': 16, 'median_ms': med, 'rate_per_s': 1000 / med, 'samples_ms': times,
           'platform': platform.platform(), 'processor': platform.processor(), 'openssl': __import__('ssl').OPENSSL_VERSION}
    OUT.mkdir(parents=True, exist_ok=True); (OUT / 'native_scrypt.json').write_text(json.dumps(row, indent=1), encoding='utf-8')
    print('native scrypt median %.1f ms (%.2f/s per core)' % (med, 1000 / med))


if __name__ == '__main__': main()
