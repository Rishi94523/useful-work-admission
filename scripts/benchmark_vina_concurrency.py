"""Replay identical stock jobs to select execution concurrency, then resume stock.

Scientific inputs and the frozen stock runner are never edited. Benchmark poses
are separate from the campaign ledger. Requires psutil in tmp/throughput-deps.
"""
import concurrent.futures as cf
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tmp/throughput-deps'))
import psutil

OUT = ROOT / 'local-research/vina-concurrency'
CAMPAIGN = ROOT / 'local-research/published-vina-validation-2026-09-15'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2))
    os.replace(temp, path)


def run_campaign(workers):
    # Override executor capacity only; the original runner, scientific config,
    # job arguments, ledger and original execution-manifest checks stay intact.
    import run_published_vina as runner
    original = runner.ThreadPoolExecutor
    runner.ThreadPoolExecutor = lambda max_workers: original(max_workers=workers)
    runner.main()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / 'panel.json'
    if not manifest_path.exists():
        rows = [json.loads(s) for s in (CAMPAIGN / 'stock_jobs.jsonl').read_text().splitlines()]
        panel = []
        targets = ['wee1', 'pur2', 'fa7', 'tgfr1', 'kif11']
        for target in targets:
            eligible = sorted([r for r in rows if r['ok'] and r['target'] == target and r['label'] != 'crystal'], key=lambda r: (r['wall_ms'], r['id']))
            for quantile in (.1, .5, .9):
                panel.append(eligible[round((len(eligible)-1)*quantile)])
        extra = next(r for r in rows if r['ok'] and r['label'] != 'crystal' and (r['target'], r['id']) not in {(x['target'], x['id']) for x in panel})
        panel.append(extra)
        # Fixed workload at every count; outcomes are never a selection input.
        save(manifest_path, {'panel': panel, 'counts': [2, 4, 8, 12, 16], 'order': [4, 8, 2, 16, 12], 'selection': '10th/50th/90th runtime percentile per target plus first unused saved screening state; available completed panel is mostly actives, not full-library representative.', 'minimum_available_bytes': 3*1024**3, 'created': time.time(), 'runner_sha256': sha(ROOT/'scripts/run_published_vina.py')})
    manifest = json.loads(manifest_path.read_text())
    assert sha(ROOT/'scripts/run_published_vina.py') == manifest['runner_sha256']
    save(OUT/f'environment-{int(time.time())}.json', {'logical_cpus':psutil.cpu_count(), 'physical_cpus':psutil.cpu_count(logical=False), 'total_ram_bytes':psutil.virtual_memory().total, 'available_ram_bytes':psutil.virtual_memory().available, 'controller_sha256':sha(Path(__file__))})
    # Stop only this exact campaign process tree; completed fsynced jobs survive.
    interrupted = []
    for proc in psutil.process_iter(['name', 'cmdline']):
        cmd = proc.info['cmdline'] or []
        if proc.pid != os.getpid() and proc.info['name'] == 'python.exe' and len(cmd) == 2 and Path(cmd[1]).name == 'run_published_vina.py':
            children = proc.children(recursive=True)
            interrupted += [{'pid': c.pid, 'command': c.cmdline()} for c in children]
            proc.terminate()
            for child in children:
                try: child.terminate()
                except psutil.NoSuchProcess: pass
            psutil.wait_procs(children + [proc], timeout=10)
    if interrupted: save(OUT/f'interruption-{int(time.time())}.json', interrupted)
    other_vina = [p.pid for p in psutil.process_iter(['name']) if p.info['name']=='vina_1.2.7_win.exe']
    assert not other_vina, f'Competing Vina processes still running: {other_vina}'
    results_path = OUT/'results.json'
    results = json.loads(results_path.read_text()) if results_path.exists() else []
    try:
        for count in manifest['order']:
            if any(r['workers'] == count for r in results): continue
            if psutil.virtual_memory().available < manifest['minimum_available_bytes'] + count*600*1024**2:
                results.append({'workers': count, 'safe': False, 'reason': 'Insufficient available memory before launch'})
                save(results_path, results)
                continue
            stop = threading.Event();memory_abort = threading.Event()
            resource = {'peak_children_rss_bytes': 0, 'minimum_available_bytes': psutil.virtual_memory().available}
            def monitor():
                while not stop.wait(.5):
                    rss = 0
                    for child in psutil.Process().children(recursive=True):
                        try: rss += child.memory_info().rss
                        except psutil.NoSuchProcess: pass
                    resource['peak_children_rss_bytes'] = max(resource['peak_children_rss_bytes'], rss)
                    resource['minimum_available_bytes'] = min(resource['minimum_available_bytes'], psutil.virtual_memory().available)
                    if resource['minimum_available_bytes'] < manifest['minimum_available_bytes']:
                        memory_abort.set()
                        for child in psutil.Process().children(recursive=True):
                            try:
                                if child.name()=='vina_1.2.7_win.exe': child.terminate()
                            except psutil.NoSuchProcess: pass
            watcher = threading.Thread(target=monitor, daemon=True);watcher.start()
            folder = OUT/str(count);folder.mkdir(exist_ok=True)
            save(OUT/'progress.json', {'phase':'benchmark','workers':count,'completed':0,'total':len(manifest['panel']),'updated':time.time()})
            def job(pair):
                index, reference = pair
                if memory_abort.is_set(): return {'index':index, 'seconds':0, 'returncode':-1, 'exact_pose_file':False}
                args = list(reference['args']);dest = folder/f'{index}.pdbqt';args[args.index('--out')+1] = str(dest)
                begin = time.perf_counter()
                run = subprocess.run(args, capture_output=True, text=True, timeout=7200)
                (folder/f'{index}.log').write_text(run.stdout+run.stderr)
                return {'index': index, 'seconds': time.perf_counter()-begin, 'returncode': run.returncode, 'exact_pose_file': dest.exists() and sha(dest)==reference['pose_sha256']}
            begin = time.perf_counter()
            jobs = []
            try:
                with cf.ThreadPoolExecutor(max_workers=count) as pool:
                    futures = [pool.submit(job, pair) for pair in enumerate(manifest['panel'])]
                    for future in cf.as_completed(futures):
                        jobs.append(future.result())
                        save(OUT/'progress.json', {'phase': 'benchmark', 'workers': count, 'completed': len(jobs), 'total': len(futures), 'updated': time.time()})
                seconds = time.perf_counter()-begin
            finally:
                stop.set();watcher.join()
            safe = all(j['returncode']==0 and j['exact_pose_file'] for j in jobs) and resource['minimum_available_bytes']>=manifest['minimum_available_bytes']
            result = {'workers': count, 'safe': safe, 'seconds': seconds, 'jobs_per_hour': len(jobs)*3600/seconds, 'jobs': jobs, **resource}
            results.append(result);save(results_path, results);print(json.dumps(result), flush=True)
        valid = [r for r in results if r['safe']]
        assert valid, 'No concurrency passed safety and exact-pose checks'
        winner = max(valid, key=lambda r: r['jobs_per_hour'])
        save(OUT/'decision.json', {'workers': winner['workers'], 'results_sha256': sha(results_path), 'scope': 'Highest measured throughput on the fixed replay panel; no claim of universal optimum. Single sweep; mixed runtime and predominantly active panel limit precision.', 'campaign_scientific_settings_unchanged': True})
    except BaseException:
        save(OUT/'failure.json', {'time': time.time(), 'action': 'Resume campaign at original 4 workers'})
        raise
    finally:
        decision = json.loads((OUT/'decision.json').read_text()) if (OUT/'decision.json').exists() else {'workers': 4}
        save(OUT/'progress.json', {'phase': 'campaign_resumed', 'workers': decision['workers'], 'updated': time.time()})
        run_campaign(decision['workers'])


if __name__ == '__main__':
    main()
