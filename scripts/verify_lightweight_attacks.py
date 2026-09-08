import json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.lightweight_docking import Assets
from research.lightweight_audit import verify
BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07'
a=Assets(BASE/'assets');results=[]
for r in json.loads((BASE/'attack-transcripts.json').read_text()):
    t=time.perf_counter();reason=None
    try:verify(a,r['jobs'],r['binding'],r['headers'],r['root'],r['draws'],r['answers']);accepted=True
    except ValueError as error:accepted=False;reason=str(error)
    results.append({**{k:r[k] for k in ('attack','id','mode','fraction')},'accepted':accepted,'reason':reason,'verify_ms':(time.perf_counter()-t)*1000})
    if (r['fraction']==1 and r['attack']=='partial_copy_worst') or r['attack']=='cached_science_fresh_commitment':assert accepted
(OUT/'attack_verification.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps({'transcripts':len(results),'partial_accepts':sum(r['accepted'] and r['fraction']<1 and r['attack']=='partial_copy_worst' for r in results),'cached_accepts':sum(r['accepted'] and r['attack']=='cached_science_fresh_commitment' for r in results)}))
