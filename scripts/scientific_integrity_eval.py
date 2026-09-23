"""Phase 6: what admitted fabricated units do to screening results (amendment 6).

Every experiment runs the original Vina finalizer, through the frozen driver,
over a pool in which some units have been replaced or altered, and compares the
final score with the same finalizer over the untouched pool. The measured
per-state change is then propagated onto the matched campaign's decomposed arm
to estimate the effect on ROC-AUC.
"""
import hashlib,json,os,random,shutil,statistics,sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from run_published_matched import Worker,digest
from adversarial_replay_eval import corpus_jobs,parse_record,best_index,final_score
from run_stock_diagnostic import auc

OUT=ROOT/'local-research/adversarial-2026-09-23'
WORK=ROOT/'tmp/adversarial/phase6'
INPUTS=ROOT/'local-research/published-vina-validation-2026-09-15/inputs.json'
MATCHED=ROOT/'local-research/published-matched-2026-09-20-samebuild/matched.jsonl'
PROTOCOL=ROOT/'docs/ADVERSARIAL_EVALUATION_PROTOCOL_2026-09-22.md'
SALT='scientific-integrity-2026-09-23:'
FRACTIONS=(0.05,0.10,0.25,0.50,0.75)
CAP=256000
SHIFT=2.0
FAKE_ENERGY=-20.0
THREADS=8
BOOTSTRAP=1000

def order(job,n):
 key='/'.join(job.parts[-3:])
 return sorted(range(n),key=lambda i:hashlib.sha256(f'{SALT}{key}/{i}'.encode()).hexdigest())

def rewrite(text,fn):
 lines=text.splitlines();return '\n'.join([lines[0]]+[fn(l) for l in lines[1:]])+'\n'

def shift_coords_only(line):
 e,conf,count,coords=parse_record(line)
 return ' '.join([e,*conf,count,*[repr(float(c)+SHIFT) if j%3==0 else c for j,c in enumerate(coords)]])

def shift_conf_only(line):
 e,conf,count,coords=parse_record(line);conf=list(conf);conf[0]=repr(float(conf[0])+SHIFT)
 return ' '.join([e,*conf,count,*coords])

def fake_energy(line):
 e,conf,count,coords=parse_record(line);return ' '.join([repr(FAKE_ENERGY),*conf,count,*coords])

def wrong_atom_count(line):
 e,conf,count,coords=parse_record(line);return ' '.join([e,*conf,str(int(count)-1),*coords[:-3]])

def job_eval(job,targets):
 tname,lid,seed=job.parts[-3],job.parts[-2],int(job.parts[-1])
 t=targets[tname];l=next(x for x in t['ligands'] if x['id']==lid)
 med=job/'medium';n=len(list(med.glob('*.task')));folder=WORK/tname/lid/str(seed)
 shutil.rmtree(folder,ignore_errors=True);folder.mkdir(parents=True)
 base={'target':tname,'id':lid,'label':l['label'],'seed':seed,'units':n};rows=[]
 w=Worker(t,l,folder)
 def finalize(name,edit):
  pool=folder/name;shutil.copytree(med,pool,ignore=shutil.ignore_patterns('*.trace','*.json'));edit(pool)
  try:w.run(2,0,seed,n,CAP,pool,pool/'final.pdbqt');return final_score(pool/'final.pdbqt'),digest(pool/'final.pdbqt'),None
  except Exception as e:return None,None,str(e)
  finally:shutil.rmtree(pool,ignore_errors=True)
 try:
  honest,honest_pose,err=finalize('honest',lambda p:None);assert err is None,err
  stored=final_score(job/'medium.pdbqt')
  rows.append({**base,'experiment':'baseline','final':honest,'matches_campaign':abs(honest-stored)<1e-9})
  best_unit=min(range(n),key=lambda i:min(float(x.split()[0]) for x in (med/f'{i}.task').read_text().splitlines()[1:]))
  def one_unit(fn):
   def edit(pool):
    p=pool/f'{best_unit}.task';lines=p.read_text().splitlines();k=best_index(lines);lines[k]=fn(lines[k]);p.write_text('\n'.join(lines)+'\n')
   return edit
  for name,fn in (('I-a_coords_only',shift_coords_only),('I-a_conf_only',shift_conf_only)):
   f,pose,err=finalize(name,one_unit(fn))
   rows.append({**base,'experiment':name,'unit':best_unit,'final':f,'delta':None if f is None else f-honest,'pose_changed':pose!=honest_pose,'error':err})
  ranked=order(job,n)
  for frac in FRACTIONS:
   m=max(1,round(frac*n));fake=ranked[:m];real=ranked[m:]
   for name,falsify in (('I-b_duplicate',False),('I-c_duplicate_fake_energy',True)):
    def edit(pool,fake=fake,real=real,falsify=falsify):
     for j,i in enumerate(fake):
      text=(med/f'{real[j%len(real)]}.task').read_text()
      (pool/f'{i}.task').write_text(rewrite(text,fake_energy) if falsify else text)
    f,pose,err=finalize(f'{name}_{frac}',edit)
    rows.append({**base,'experiment':name,'fraction':frac,'fabricated_units':m,'final':f,'delta':None if f is None else f-honest,'pose_changed':pose!=honest_pose,'error':err})
  f,pose,err=finalize('I-d_wrong_atoms',lambda pool:(pool/f'{ranked[0]}.task').write_text(rewrite((med/f'{ranked[0]}.task').read_text(),wrong_atom_count)))
  rows.append({**base,'experiment':'I-d_wrong_atom_count','final':f,'rejected':err is not None,'error':err})
 finally:w.close();shutil.rmtree(folder,ignore_errors=True)
 return rows

def propagate(rows):
 """I-e: resample measured per-state changes onto the matched campaign."""
 matched=[json.loads(s) for s in MATCHED.read_text().splitlines() if s.strip()]
 targets={t['target']:t for t in json.loads(INPUTS.read_text())['targets']}
 rng=random.Random(20260923);out=[]
 for frac in FRACTIONS:
  deltas=[r['delta'] for r in rows if r['experiment']=='I-b_duplicate' and r['fraction']==frac and r['delta'] is not None]
  for tname,t in targets.items():
   states=[r for r in matched if r['target']==tname and r['ok']]
   if not states:continue
   seeds=sorted({r['seed'] for r in states})
   def panel_auc(shift):
    aucs=[]
    for seed in seeds:
     comp={}
     for r in states:
      if r['seed']!=seed:continue
      s=r['medium']['score']+shift.get((r['id'],seed),0.0);comp.setdefault(r['compound_id'],(r['label'],[]))[1].append(s)
     a=[min(v) for lab,v in comp.values() if lab=='active'];d=[min(v) for lab,v in comp.values() if lab=='decoy']
     aucs.append(auc(a,d))
    return statistics.mean(aucs)
   clean=panel_auc({});draws=[]
   for _ in range(BOOTSTRAP):
    shift={(r['id'],r['seed']):rng.choice(deltas) for r in states};draws.append(panel_auc(shift)-clean)
   draws.sort()
   out.append({'fraction':frac,'target':tname,'clean_auc':clean,'mean_delta_auc':statistics.mean(draws),
               'delta_auc_95':[draws[int(.025*BOOTSTRAP)],draws[int(.975*BOOTSTRAP)-1]],'deltas_resampled_from':len(deltas)})
   print(json.dumps(out[-1]),flush=True)
 return out

def main():
 OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
 targets={t['target']:t for t in json.loads(INPUTS.read_text())['targets']};jobs=corpus_jobs()
 manifest={'protocol':digest(PROTOCOL),'runner':digest(Path(__file__)),'driver':digest(ROOT/'tmp/vina-published/vina_published_tasks_spacing0375.exe'),
  'matched':digest(MATCHED),'corpus':sorted('/'.join(j.parts[-3:]) for j in jobs),'salt':SALT,'fractions':list(FRACTIONS),'shift_A':SHIFT,'fake_energy':FAKE_ENERGY}
 mp=OUT/'phase6_manifest.json'
 if mp.exists():assert json.loads(mp.read_text())==manifest,'Immutable manifest changed: '+str(mp)
 else:mp.write_text(json.dumps(manifest,indent=2))
 ledger=OUT/'phase6.jsonl';recorded=[json.loads(s) for s in ledger.read_text().splitlines() if s.strip()] if ledger.exists() else []
 done={(r['target'],r['id'],r['seed']) for r in recorded}
 todo=[j for j in jobs if (j.parts[-3],j.parts[-2],int(j.parts[-1])) not in done]
 print('jobs: %d total, %d to run'%(len(jobs),len(todo)),flush=True)
 with ThreadPoolExecutor(max_workers=THREADS) as pool:
  futures={pool.submit(job_eval,j,targets):j for j in todo}
  for f in as_completed(futures):
   j=futures[f]
   try:rows=f.result()
   except Exception as e:rows=[{'target':j.parts[-3],'id':j.parts[-2],'seed':int(j.parts[-1]),'experiment':'job_error','error':str(e)}]
   with ledger.open('a') as h:
    for r in rows:h.write(json.dumps(r)+chr(10))
    h.flush();os.fsync(h.fileno())
   print(j.parts[-3],j.parts[-2],j.parts[-1],len(rows),'rows',flush=True)
 rows=[json.loads(s) for s in ledger.read_text().splitlines() if s.strip()]
 (OUT/'phase6_propagation.json').write_text(json.dumps(propagate(rows),indent=2))
 print('PHASE6 COMPLETE',flush=True)

if __name__=='__main__':main()
