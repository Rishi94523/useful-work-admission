"""Check the predeclaration record: every result manifest that records the
protocol file's SHA-256 is matched to the commit whose protocol file has that
hash, and the manifest's file time must follow that commit.

Output: local-research/predeclaration-audit/audit.json and a printed table.
Manifest file times are local filesystem times, a weaker record than the
commit history; the table reports them as such.
"""
import argparse
import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = 'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'
LR = ROOT / 'local-research'


def git(*a): return subprocess.check_output(['git', *a], cwd=ROOT)


def protocol_versions():
    """SHA-256 of the protocol file at every commit that changed it -> (commit, commit time)."""
    out = {}
    for line in git('log', '--format=%H %cI', '--', PROTOCOL).decode().split('\n'):
        if not line.strip(): continue
        h, t = line.split()
        digest = hashlib.sha256(git('show', h + ':' + PROTOCOL)).hexdigest()
        out.setdefault(digest, (h, dt.datetime.fromisoformat(t)))   # log is newest first; keep the earliest below
        if dt.datetime.fromisoformat(t) < out[digest][1]: out[digest] = (h, dt.datetime.fromisoformat(t))
    return out


def find_protocol(d, path=''):
    if isinstance(d, dict):
        for k, v in d.items():
            if k in ('protocol', 'protocol_sha256', PROTOCOL) and isinstance(v, str) and len(v) == 64: yield path + k, v
            else: yield from find_protocol(v, path + k + '.')


# Runs whose manifests name the protocol commit rather than hash the file, and
# phone studies whose reports carry the collector's receipt time. Each is
# checked against the commit of the amendment that governs it.
BY_COMMIT = {'admission-amendment14-2026-09-28': '5105313', 'inference-leverage-2026-09-28': '5105313',
             'batched-leverage-2026-09-28': 'fbe767f', 'native-dense-2026-09-28': 'a1c1d83',
             'trace-attacks-2026-09-29': '599cc0f',
             'realtime-admission-2026-09-29': 'a2d2af1',
             'cost-aware-2026-09-29': 'a2d2af1',
             'inference-repetition-2026-09-29': 'a2d2af1',
             'portable-dense-2026-09-29': '83ac5f0',
             'screened-admission-2026-09-29': '4310d9e'}
PHONES = {'device-timing-subpuzzle': '5a19d42', 'device-inference-2026-09-28': '30992dc'}


def commit_time(c): return dt.datetime.fromisoformat(git('show', '-s', '--format=%cI', c).decode().strip())


def extra_rows():
    rows = []
    for d, c in BY_COMMIT.items():
        files = [f for f in (LR / d).iterdir() if f.is_file() and f.name != 'summary.json']
        first = min(dt.datetime.fromtimestamp(f.stat().st_mtime).astimezone() for f in files)
        rows.append((d + ' (earliest file)', c, first))
    for d, c in PHONES.items():
        times = [json.loads(f.read_text(encoding='utf-8')).get('received_at') for f in (LR / d).glob('timing_*.json')]
        first = min(dt.datetime.fromisoformat(t.replace('Z', '+00:00')) for t in times if t)
        rows.append((d + ' (first phone report received)', c, first))
    out = []
    for name, c, first in rows:
        ct = commit_time(c)
        out.append({'manifest': name, 'field': 'commit', 'protocol_sha256': None, 'protocol_commit': c, 'commit_time': ct.isoformat(),
                    'manifest_time': first.isoformat(timespec='seconds'), 'after_commit': first > ct,
                    'lag_min': round((first - ct).total_seconds() / 60, 1)})
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=LR / 'predeclaration-audit' / 'audit.json')
    args = parser.parse_args()
    versions = protocol_versions(); rows = []
    for f in sorted(LR.rglob('*manifest*.json')):
        try: m = json.loads(f.read_text(encoding='utf-8'))
        except Exception: continue
        for field, digest in find_protocol(m):
            commit, ctime = versions.get(digest, (None, None))
            mtime = dt.datetime.fromtimestamp(f.stat().st_mtime).astimezone()
            rows.append({'manifest': f.relative_to(LR).as_posix(), 'field': field, 'protocol_sha256': digest,
                         'protocol_commit': commit[:7] if commit else None, 'commit_time': ctime.isoformat() if ctime else None,
                         'manifest_time': mtime.isoformat(timespec='seconds'),
                         'after_commit': bool(ctime and mtime > ctime), 'lag_min': round((mtime - ctime).total_seconds() / 60, 1) if ctime else None})
    # Scientific-campaign manifests hash the benchmark protocol, not this one.
    rows = [r for r in rows if r['protocol_commit']] + extra_rows()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(rows, indent=1), encoding='utf-8')
    for r in rows:
        print('%-62s %-8s %-25s lag %8s min %s' % (r['manifest'][:62], r['protocol_commit'], (r['commit_time'] or '')[:19], r['lag_min'], 'ok' if r['after_commit'] else 'CHECK'))
    print('%d manifests with a protocol hash; %d matched a committed protocol version; %d written after that commit'
          % (len(rows), sum(r['protocol_commit'] is not None for r in rows), sum(r['after_commit'] for r in rows)))


if __name__ == '__main__': main()
