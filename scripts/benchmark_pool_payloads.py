"""Measure policy storage/hashing with real-sized archived molecular outputs.

Payloads are reused to time the control plane, not credited as new science.
"""
import hashlib,json,statistics,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.pool_admission import PoolAdmission
from research.docking_campaign import canonical
source=json.loads((ROOT/'docs/evaluation/vina_cdn_2026-09-14/desktop_identity-br9.json').read_text())
payloads=[canonical({'pool':r['pool'],'trace':r['trace']}) for r in source['runs']]
results=[]
for n in [1,2,4]:
 with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as tmp:
  clock=[0];c=PoolAdmission(Path(tmp)/'payload.sqlite',clock=lambda:clock[0],bundle=n,audit_probability=0,trust_bundles=0)
  timings=[]
  for i in range(20):
   clock[0]+=60;owner=str(i);spec=dict(model_version='payload-timing-fixture',receptor='r',ligand='l',conformer_bank=str(i),region='b',search_parameters={'max_evals':256000});c.register_pool(owner,spec,list(range(n)))
   if n==1:c.grant_trust(owner)
   start=time.perf_counter();l=c.request(owner,owner);outputs={t['task']:payloads[j] for j,t in enumerate(l['tasks'])};ch=c.commit(l['lease'],owner,l['binding'],c.output_root(l['binding'],outputs));c.submit(l['lease'],owner,l['binding'],ch['id'],outputs)
   targets=c.audit_targets(l['lease'])  # trusted verifier view; commit no longer reveals selection
   if targets:c.replay(l['lease'],{t:(hashlib.sha256(outputs[t]).hexdigest(),True) for t in targets})
   c.redeem(l['lease'],owner);timings.append(1000*(time.perf_counter()-start))
  results.append(dict(n=n,payload_bytes=sum(len(p) for p in payloads[:n]),trials=20,median_control_ms=statistics.median(timings),max_control_ms=max(timings),database_bytes=Path(c.path).stat().st_size,scope='Actual payload hash, SQLite persistence, credit and modeled trusted verdict. No molecular replay during this measurement. Grant-trust and campaign registration excluded.'))
out=ROOT/'local-research/admission-2026-09-14/payload_costs.json';out.write_text(json.dumps(results,indent=2)+'\n');print(json.dumps(results,indent=2))
