"""Actual SQLite policy/CSPRNG feedback, with explicitly modeled molecular costs."""
import json,math,random,sys,tempfile,time,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.adaptive_admission import AdaptiveAdmission
stronger='--stronger-audit' in sys.argv
policy_args={'audit_samples':{'high':27}} if stronger else {}
OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08';OUT.mkdir(parents=True,exist_ok=True)
old=json.loads((ROOT/'docs/evaluation/docking_whole_runs_2026-09-08/economics.json').read_text())
calibration={name:next(x for x in old['tiers'] if (x['ligands'],x['runs'],x['cap'])==spec[:3]) for name,spec in AdaptiveAdmission.TIERS.items()}
template_dir=tempfile.TemporaryDirectory(dir=ROOT/'tmp');template=Path(template_dir.name)/'template.sqlite'
base=AdaptiveAdmission(template,clock=lambda:0,**policy_args)
for li in range(16):
    for block in range(32):
        for cap,offset in [(4000,0),(16000,1000)]:base.register('science','engine','maps',str(li),'input'+str(li),'box',offset+16*block,16,cap,16)
db=base.connect();db.execute('PRAGMA wal_checkpoint(TRUNCATE)');db.close()

def run(name,fraction=1,rep=0):
    now=[0];rng=random.Random(5000+rep);rows=[];cache=set();attempted=set();science=0;accepted=0
    with tempfile.TemporaryDirectory(dir=ROOT/'tmp') as d:
        local=Path(d)/'policy.sqlite';shutil.copyfile(template,local)
        c=AdaptiveAdmission(local,clock=lambda:now[0],**policy_args)
        for step in range(64 if name=='identity-churn' else 32):
            owner='visitor'+str(step) if name=='identity-churn' else 'visitor'
            t=time.perf_counter();lease=c.request('science',owner);admission_ms=(time.perf_counter()-t)*1000
            row={'step':step,'time':now[0],'owner':owner,'status':lease['status'],'risk':lease.get('risk'),'admission_and_scheduler_ms':admission_ms}
            if lease['status']!='assigned':rows.append(row);break
            units=c.units(lease);keys=[(u['input'],u['seed'],u['cap']) for u in units];n=len(units);k=math.floor(n*fraction)
            chosen=set(rng.sample(range(n),k));new=[keys[i] for i in chosen if keys[i] not in (attempted if name=='retry-cache' else cache)]
            if name=='retry-cache':cache.update(new);attempted.update(keys);mask=[key in cache for key in keys]
            else:mask=[i in chosen for i in range(n)]
            cost=calibration[lease['tier']]['molecular_ms']*len(new)/n
            science+=cost
            row.update(tier=lease['tier'],assigned_runs=n,q=lease['q'],computed_runs=len(new),correct_records=sum(mask),modeled_new_molecular_ms=cost)
            if name in ('abandon-open','abandon-committed') and step==0:
                if name=='abandon-committed':c.commit(lease['lease'],owner,lease['binding'],'a'*64)
                row['outcome']='abandoned';now[0]+=121;rows.append(row);continue
            t=time.perf_counter();ch=c.commit(lease['lease'],owner,lease['binding'],'a'*64);draws=c.flat_draws(lease,ch)
            passed=all(mask[i] for i in draws);finish=c.finish(lease['lease'],owner,lease['binding'],ch['id'],'a'*64,passed,{'model_only':True})
            row.update(outcome=finish,draws=draws,commit_and_finish_db_ms=(time.perf_counter()-t)*1000,
                       conditional_pass_probability=math.comb(sum(mask),lease['q'])/math.comb(n,lease['q']) if sum(mask)>=lease['q'] else 0)
            accepted+=passed;rows.append(row)
            now[0]+=60 if name in ('honest','abandon-open','abandon-committed') else .1
        return {'scenario':name,'fraction':fraction,'repetition':rep,'rows':rows,'accepted':accepted,'modeled_total_molecular_ms':science,
                'modeled_molecular_ms_per_accepted':science/accepted if accepted else None,
                'credited_provisional_runs':sum(r.get('assigned_runs',0) for r in rows if isinstance(r.get('outcome'),dict) and r['outcome']['accepted']),
                'snapshot':c.snapshot()}

scenarios=[run(x) for x in ['honest','valid-spam','abandon-open','abandon-committed','identity-churn']]
for fraction in [.1,.25,.5,.75,.9]:
    for name in ['partial','retry-cache']:
        for rep in range(10):scenarios.append(run(name,fraction,rep))
output={'scope':'Actual SQLite policy, scheduler and CSPRNG challenges. Molecular outcomes use known masks; timing costs are scaled from historical browser tier medians, NOT new Vina runs. High-rate valid traffic models precomputed uncredited results or accelerated clients; zero post-request compute is not zero historical work.','policy':base.VERSION,'audit_samples':{t:base.TIERS[t][3] for t in base.TIERS},'calibration':calibration,'scenarios':scenarios}
(OUT/('policy_simulation_stronger_audit.json' if stronger else 'policy_simulation_calibrated.json')).write_text(json.dumps(output,indent=2)+'\n')
template_dir.cleanup()
print([{k:x[k] for k in ['scenario','fraction','accepted','modeled_total_molecular_ms']} for x in scenarios[:5]])
