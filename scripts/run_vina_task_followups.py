"""Sequential follow-ups after all predeclared native campaign rows are durable."""
import json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_tasks_2026-09-10'
started=time.monotonic()
while True:
 try:rows=[json.loads(x) for x in (OUT/'campaign.jsonl').read_text().splitlines()]
 except (FileNotFoundError,json.JSONDecodeError):rows=[]
 if len({r['key'] for r in rows})==222:break
 if time.monotonic()-started>10800:raise RuntimeError('Campaign incomplete after bounded wait; inspect original process')
 time.sleep(10)
time.sleep(2)
steps=[('wallmatch',[sys.executable,'scripts/benchmark_vina_task_wallmatch.py']),('e32',[sys.executable,'scripts/benchmark_vina_task_e32.py']),('wasm-build',[sys.executable,'scripts/build_vina_tasks_wasm.py']),('browser',['node','scripts/benchmark_vina_tasks_browser.mjs']),('ingestion',[sys.executable,'scripts/benchmark_vina_task_ingestion.py']),('analysis',[sys.executable,'scripts/analyze_vina_tasks.py']),('dimensions',[sys.executable,'scripts/analyze_vina_task_dimensions.py']),('tables',[sys.executable,'scripts/write_vina_task_results.py']),('plots',[sys.executable,'scripts/plot_vina_tasks.py']),('package',[sys.executable,'scripts/package_vina_tasks.py'])]
for name,command in steps:
 print('START',name,flush=True);begin=time.time();result=subprocess.run(command,cwd=ROOT)
 with (OUT/'followups.jsonl').open('a') as f:f.write(json.dumps({'step':name,'started_unix':begin,'elapsed_seconds':time.time()-begin,'returncode':result.returncode})+'\n')
 if result.returncode:raise SystemExit(result.returncode)
 print('DONE',name,flush=True)
