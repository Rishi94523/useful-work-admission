import copy,json,sys,time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.lightweight_docking import Assets
from research.lightweight_audit import verify
BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07'
a=Assets(BASE/'assets');results=[];tamper=[]
for runtime in sys.argv[1:] or ['node','chrome']:
    records=json.loads((BASE/f'{runtime}-transcripts.json').read_text())
    for r in records:
        t=time.perf_counter();result=verify(a,r['jobs'],r['binding'],r['headers'],r['root'],r['draws'],r['answers']);elapsed=(time.perf_counter()-t)*1000
        results.append({**{k:r[k] for k in ('runtime','mode','jobsCount','count','rep')},**result,'server_verify_ms':elapsed})
    r=records[0]
    for attack in ['binding','range','root','missing_chunk','duplicate_chunk','score_vector','oversized','wrong_path','changed_record','wrong_mode','null_headers','wrong_answer_type','missing_key']:
        s=copy.deepcopy(r)
        if attack=='binding':s['binding']='ff'*32
        elif attack=='range':s['jobs'][0]['start']+=1
        elif attack=='root':s['root']='00'*32
        elif attack=='missing_chunk':s['answers'][0].pop()
        elif attack=='duplicate_chunk':s['answers'][0].append(s['answers'][0][0])
        elif attack=='score_vector':s['headers'][0]['scores']='AAAA'+s['headers'][0]['scores'][4:]
        elif attack=='oversized':s['answers'][0][0]['data']+='A'*100000
        elif attack=='wrong_path':s['answers'][0][0]['path'][0]='00'*32
        elif attack=='changed_record':s['answers'][0][0]['data']='AAAA'+s['answers'][0][0]['data'][4:]
        elif attack=='wrong_mode':s['jobs'][0]['mode']='C' if s['jobs'][0]['mode']=='B' else 'B'
        elif attack=='null_headers':s['headers']=None
        elif attack=='wrong_answer_type':s['answers']=[1]
        elif attack=='missing_key':del s['headers'][0]['id']
        try:verify(a,s['jobs'],s['binding'],s['headers'],s['root'],s['draws'],s['answers']);raise AssertionError(f'Accepted {attack}')
        except ValueError:tamper.append({'runtime':runtime,'attack':attack,'rejected':True})
(OUT/'verification.json').write_text(json.dumps({'results':results,'tamper':tamper},indent=2)+'\n')
print(json.dumps({'verified':len(results),'tamper_rejected':len(tamper),'server_ms_median':float(np.median([r['server_verify_ms'] for r in results]))}))
