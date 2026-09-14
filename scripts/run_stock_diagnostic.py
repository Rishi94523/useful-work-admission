"""Stock-only development selection followed by immutable heldout validation."""
import hashlib,json,math,os,re,subprocess,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np
from validate_vina_stock_controls import quality

ROOT=Path(__file__).resolve().parents[1]
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def auc(a,d):
 a=np.asarray(a);d=np.asarray(d)
 return float(((a[:,None]<d)+.5*(a[:,None]==d)).mean())
def metrics(rows,bootstrap=0):
 good=[r for r in rows if r.get('ok')];a=[r['score'] for r in good if r['label']=='active'];d=[r['score'] for r in good if r['label']=='decoy']
 if not a or not d:return {'auc':None,'ef10':None,'bootstrap95':None}
 k=math.ceil(.1*len(good));cut=sorted(r['score'] for r in good)[k-1];lower=[r for r in good if r['score']<cut];ties=[r for r in good if r['score']==cut]
 hits=sum(r['label']=='active' for r in lower)+(k-len(lower))*sum(r['label']=='active' for r in ties)/len(ties)
 ci=None
 if bootstrap:
  rng=np.random.default_rng(104729);ci=np.percentile([auc(rng.choice(a,len(a)),rng.choice(d,len(d))) for _ in range(bootstrap)],[2.5,97.5]).tolist()
 return {'auc':auc(a,d),'ef10':hits/k/(len(a)/len(good)),'bootstrap95':ci}
def freeze(path,value):
 text=json.dumps(value,indent=2,sort_keys=True)+'\n'
 if path.exists():
  if path.read_text()!=text:raise ValueError('Immutable record mismatch: '+path.name)
 else:
  with path.open('x') as f:f.write(text);f.flush();os.fsync(f.fileno())
def main():
 protocol=ROOT/'benchmarks/vina_stock_diagnostic.json';cfg=json.loads(protocol.read_text());out=ROOT/cfg['output_directory'];inputs=out/'inputs.json';data=json.loads(inputs.read_text());exe=ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'
 assert data['protocol_sha256']==digest(protocol) and data['stock_sha256']==digest(exe)
 assert [t['target'] for t in data['targets']]==cfg['targets'],'Preparation incomplete'
 audit_path=out/'chemical_state_audit.json';audit=json.loads(audit_path.read_text());assert audit['inputs_sha256']==digest(inputs)
 invalid={(f['target'],f['split'],f['id']) for f in audit['input_validation_failures']}
 freeze(out/'execution_manifest.json',{'protocol':digest(protocol),'inputs':digest(inputs),'chemical_audit':digest(audit_path),'executable':digest(exe),'runner':digest(Path(__file__))})
 def key(r):return (r['target'],r['config'],r['split'],r['id'],r['seed'])
 path=out/'stock_jobs.jsonl';rows=[json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
 assert len({key(r) for r in rows})==len(rows)
 def run(t,c,split,l,seed):
  ligand=ROOT/l['path'];receptor=ROOT/t['receptors'][c['receptor']];assert digest(ligand)==l['sha256'];assert digest(receptor)==t['receptor_hashes'][c['receptor']]
  folder=ROOT/'tmp/vina-stock-diagnostic/jobs'/t['target']/c['id']/split;folder.mkdir(parents=True,exist_ok=True);dest=folder/(l.get('id','crystal')+'_'+str(seed)+'.pdbqt')
  args=[str(exe),'--receptor',str(receptor),'--ligand',str(ligand),'--cpu','1','--seed',str(seed),'--exhaustiveness',str(c['exhaustiveness']),'--num_modes','9','--out',str(dest)]
  box=t['boxes'][c['box']]
  for i,x in enumerate('xyz'):args+=['--center_'+x,str(box['center'][i]),'--size_'+x,str(box['size'][i])]
  row={'target':t['target'],'config':c['id'],'split':split,'id':l.get('id','crystal'),'label':l.get('label','crystal'),'seed':seed,'input_sha256':l['sha256'],'receptor_sha256':digest(receptor),'args':args,'ok':False};start=time.perf_counter()
  try:
   p=subprocess.run(args,capture_output=True,text=True,timeout=cfg['timeout_seconds']);row.update(returncode=p.returncode,stderr=p.stderr);dest.with_suffix('.log').write_text(p.stdout+p.stderr)
   if p.returncode==0:
    text=dest.read_text();row.update(score=float(re.search(r'REMARK VINA RESULT:\s+([-\d.]+)',text).group(1)),pose_sha256=digest(dest),pose_path=dest.relative_to(ROOT).as_posix())
    if split=='crystal':row.update(quality(ligand,ligand.with_suffix('.sdf'),text))
    row['ok']=True
  except Exception as e:row['error']=str(e)
  row['wall_ms']=1000*(time.perf_counter()-start);return row
 def phase(jobs):
  done={key(r) for r in rows}
  with ThreadPoolExecutor(max_workers=cfg['workers']) as pool:
   futures=[pool.submit(run,t,c,s,l,seed) for t,c,s,l,seed in jobs if (t['target'],c['id'],s,l.get('id','crystal'),seed) not in done and (t['target'],s,l.get('id','crystal')) not in invalid]
   for future in as_completed(futures):
    r=future.result()
    with path.open('a') as f:f.write(json.dumps(r)+'\n');f.flush();os.fsync(f.fileno())
    rows.append(r);print(*key(r),r['ok'],r.get('score'),r.get('top_rmsd_A'),flush=True)
 phase([(t,c,'crystal',t['crystal'],seed) for t in data['targets'] for c in cfg['configurations'] for seed in cfg['redocking_seeds']])
 phase([(t,c,'development',l,cfg['development_seed']) for t in data['targets'] for c in cfg['configurations'] for l in t['splits']['development']])
 development=[];selected=[]
 for t in data['targets']:
  eligible=[]
  for index,c in enumerate(cfg['configurations']):
   rs=[r for r in rows if r['target']==t['target'] and r['config']==c['id'] and r['split']=='development'];cr=[r for r in rows if r['target']==t['target'] and r['config']==c['id'] and r['split']=='crystal'];m=metrics(rs)
   complete=len(rs)==24 and all(r['ok'] for r in rs) and not any(f['split']=='development' for f in t['failures']);redock=len(cr)==3 and all(r['ok'] for r in cr) and sum(r.get('top_rmsd_A',float('inf'))<=2 for r in cr)>=2
   passed=bool(complete and redock and m['auc']>=.75 and m['ef10']>=1.5);development.append({'target':t['target'],'config':c['id'],**m,'complete':complete,'redocking_pass':redock,'eligible':passed,'crystal_top_rmsd_A':[r.get('top_rmsd_A') for r in sorted(cr,key=lambda r:r['seed'])]})
   if passed:eligible.append((-m['auc'],c['exhaustiveness'],index,c))
  chosen=min(eligible)[-1] if eligible else None;selected.append({'target':t['target'],'configuration':chosen})
 freeze(out/'development_decision.json',{'development':development,'selected':selected,'protocol_sha256':digest(protocol),'inputs_sha256':digest(inputs),'input_validation_failures':audit['input_validation_failures']})
 print('FROZEN SELECTION',selected,flush=True)
 phase([(t,s['configuration'],'heldout',l,cfg['heldout_seed']) for t in data['targets'] for s in selected if s['target']==t['target'] and s['configuration'] for l in t['splits']['heldout']])
 results=[]
 for s in selected:
  if not s['configuration']:results.append({'target':s['target'],'passed':False,'reason':'No development configuration qualified; heldout not docked'});continue
  t=next(t for t in data['targets'] if t['target']==s['target']);rs=[r for r in rows if r['target']==s['target'] and r['split']=='heldout'];m=metrics(rs,cfg['heldout_gate']['bootstrap_resamples']);complete=len(rs)==96 and all(r['ok'] for r in rs) and not any(f['split']=='heldout' for f in t['failures']);passed=bool(complete and m['auc']>=.75 and m['bootstrap95'][0]>.60 and m['ef10']>=1.5)
  results.append({'target':s['target'],'config':s['configuration']['id'],**m,'complete':complete,'passed':passed,'input_validation_failures':[f for f in audit['input_validation_failures'] if f['target']==s['target']]})
 freeze(out/'heldout_results.json',results);print('COMPLETE',results,flush=True)
if __name__=='__main__':main()
