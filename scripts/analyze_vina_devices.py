"""Independently hash uploaded pools/traces; summarize measured device runs."""
import hashlib,json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/('docs/evaluation/vina_mobile_256k_2026-09-13' if '--medium' in sys.argv else 'docs/evaluation/vina_followup_2026-09-12')
reference=json.loads((OUT/'device_reference.json').read_text())
rows=[]
for path in sorted(OUT.glob('device_[0-9]*.json')):
    report=json.loads(path.read_text());runs=report['runs'];indices=[r['index'] for r in runs]
    matches=[]
    for r in runs:
        expected=next((e for e in reference['expected'] if e['index']==r['index']),None)
        matches.append(bool(expected) and all(hashlib.sha256(r[k].encode()).hexdigest()==expected[k] for k in ['pool','trace']))
    calls=[r['call_ms'] for r in runs]
    rows.append(dict(source=path.name,device_model=report['device_model'],reported_os=report['os_version'],
        user_agent=report['user_agent'],wasm_matches_reference=report['wasm_sha256']==reference['wasm_sha256'],
        complete=len(indices)==6 and sorted(indices)==list(range(6)) and not report.get('error') and not report.get('stopped'),
        exact_output_matches=sum(matches),factory_instantiation_ms=report.get('init',{}).get('module_ms'),
        initialization_ms=report.get('init',{}).get('init_ms'),run_count=len(runs),
        run_min_ms=min(calls) if calls else None,run_max_ms=max(calls) if calls else None,
        run_median_ms=statistics.median(calls) if calls else None,run_sum_ms=sum(calls),
        total_elapsed_ms=report['elapsed_ms'],task_call_fraction=sum(calls)/report['elapsed_ms'],
        max_allocated_wasm_mib=max([r['heap'] for r in runs]+[report.get('init',{}).get('heap',0)])/2**20,
        hidden_events=report['hidden_events'],max_frame_gap_ms=max(report['frame_gap_ms'],default=None),
        init_count=report.get('init_count'),cold_first_result_ms=runs[0].get('result_received_ms') if runs else None,
        reused_batch_median_ms=statistics.median([r['call_ms'] for r in runs if r.get('batch')==1]) if any(r.get('batch')==1 for r in runs) else None))
result=dict(cap=reference.get('cap',64000),devices=rows,scope='Desktop headless control and user-operated phone reports. No device-population estimate. Six FA10 crystal-input units. Medium test: two batches in one worker, separated by two seconds; cold means a fresh worker, not a rebooted browser or device. Factory timing excludes static import; heap is not resident memory; task-call fraction excludes reusable initialization and includes the medium test pause in its denominator. OS/device labels are reported, not attested.')
(OUT/'device_summary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
