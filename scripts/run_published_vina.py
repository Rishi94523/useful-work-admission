"""Published-protocol stock validation; durable jobs and compound-state gates."""
import collections,json,os,re,subprocess,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from run_stock_diagnostic import ROOT,digest,freeze,metrics
from validate_vina_stock_controls import quality

def main():
 protocol=ROOT/'benchmarks/vina_published_validation.json';cfg=json.loads(protocol.read_text());out=ROOT/cfg['output_directory'];input_path=out/'inputs.json';data=json.loads(input_path.read_text());exe=ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'
 assert [t['target'] for t in data['targets']]==cfg['targets']
 assert digest(protocol)==data['protocol_sha256'] and digest(exe)==data['stock_sha256']
 freeze(out/'stock_execution_manifest.json',{'protocol':digest(protocol),'inputs':digest(input_path),'runner':digest(Path(__file__)),'stock':digest(exe),'preparation_manifest':digest(out/'preparation_manifest.json'),'preparation_compatibility':digest(out/'preparation_compatibility.json')})
 path=out/'stock_jobs.jsonl';rows=[json.loads(s) for s in path.read_text().splitlines()] if path.exists() else []
 def key(r):return r['target'],r['id'],r['seed']
 assert len({key(r) for r in rows})==len(rows)
 def job(t,l,seed):
  ligand=ROOT/l['path'];receptor=ROOT/t['receptor'];assert digest(ligand)==l['sha256'] and digest(receptor)==t['receptor_sha256'];folder=ROOT/'tmp/vina-published/jobs'/t['target'];folder.mkdir(parents=True,exist_ok=True);dest=folder/(l['id']+'_'+str(seed)+'.pdbqt')
  args=[str(exe),'--receptor',str(receptor),'--ligand',str(ligand),'--cpu','1','--seed',str(seed),'--exhaustiveness',str(cfg['stock']['exhaustiveness']),'--num_modes','9','--out',str(dest)]
  for i,x in enumerate('xyz'):args+=['--center_'+x,str(t['center'][i]),'--size_'+x,str(t['size'][i])]
  row={'target':t['target'],'id':l['id'],'compound_id':l['compound_id'],'label':l['label'],'seed':seed,'ok':False,'input_sha256':l['sha256'],'args':args};start=time.perf_counter()
  try:
   r=subprocess.run(args,capture_output=True,text=True,timeout=cfg['stock']['timeout_seconds']);row.update(returncode=r.returncode,stderr=r.stderr);dest.with_suffix('.log').write_text(r.stdout+r.stderr)
   if r.returncode==0:
    text=dest.read_text();row.update(score=float(re.search(r'REMARK VINA RESULT:\s+([-\d.]+)',text).group(1)),pose_path=dest.relative_to(ROOT).as_posix(),pose_sha256=digest(dest))
    if l['label']=='crystal':row.update(quality(ligand,ligand.with_suffix('.sdf'),text))
    row['ok']=True
  except Exception as e:row['error']=str(e)
  row['wall_ms']=1000*(time.perf_counter()-start);return row
 def execute(jobs):
  done={key(r) for r in rows}
  with ThreadPoolExecutor(max_workers=cfg['stock']['workers']) as pool:
   futures=[pool.submit(job,t,l,s) for t,l,s in jobs if (t['target'],l['id'],s) not in done]
   for f in as_completed(futures):
    r=f.result()
    with path.open('a') as handle:handle.write(json.dumps(r)+'\n');handle.flush();os.fsync(handle.fileno())
    rows.append(r);print(r['target'],r['id'],r['seed'],r['ok'],r.get('score'),r.get('top_rmsd_A'),flush=True)
    status={'saved_jobs':len(rows),'by_label':dict(collections.Counter(r['label'] for r in rows)),'execution_failures':sum(not r['ok'] for r in rows),'updated_unix':time.time(),'complete':False};tmp=out/'progress.tmp';tmp.write_text(json.dumps(status,indent=2));os.replace(tmp,out/'progress.json')
 valid_targets=[t for t in data['targets'] if t['crystal'] and not any(f['scope']=='receptor' for f in t['failures'])]
 execute([(t,t['crystal'],s) for s in cfg['redocking']['seeds'] for t in valid_targets])
 # Round-robin targets, so one expensive target does not monopolize the queue.
 execute([(t,t['ligands'][i],cfg['stock']['seed']) for i in range(max((len(t['ligands']) for t in valid_targets),default=0)) for t in valid_targets if i<len(t['ligands'])])
 gates=[];compounds=[]
 for t in data['targets']:
  target_rows=[]
  for compound in t['compounds']:
   states=[r for r in rows if r['target']==t['target'] and r['compound_id']==compound['id'] and r['label']!='crystal'];ok=len(states)==compound['states'] and all(r['ok'] for r in states) and not any(f.get('compound_id')==compound['id'] for f in t['failures']);row={'target':t['target'],'id':compound['id'],'label':compound['label'],'ok':ok,'required_states':compound['states'],'completed_states':len(states)}
   if ok:row['score']=min(r['score'] for r in states)
   target_rows.append(row);compounds.append(row)
  m=metrics(target_rows,cfg['stock_gate']['bootstrap_resamples']);complete=len(target_rows)==96 and all(r['ok'] for r in target_rows) and not t['failures'];cr=[r for r in rows if r['target']==t['target'] and r['label']=='crystal'];redock=len(cr)==3 and all(r['ok'] for r in cr) and sum(r.get('top_rmsd_A',999)<=2 for r in cr)>=2;ranking=bool(complete and m['auc']>=.75 and m['bootstrap95'][0]>.60 and m['ef10']>=1.5)
  gates.append({'target':t['target'],**m,'complete':complete,'ranking_pass':ranking,'redocking_pass':redock,'passed':ranking and redock,'redocking_rmsd_A':[r.get('top_rmsd_A') for r in cr],'preparation_failures':t['failures']})
 freeze(out/'stock_compounds.json',compounds);freeze(out/'stock_gates.json',gates);freeze(out/'comparison_eligibility.json',{'protocol_sha256':digest(protocol),'inputs_sha256':digest(input_path),'stock_gates_sha256':digest(out/'stock_gates.json'),'eligible_targets':[g['target'] for g in gates if g['passed']]});(out/'progress.json').write_text(json.dumps({'complete':True,'saved_jobs':len(rows),'gates':gates},indent=2));print('COMPLETE',gates,flush=True)
if __name__=='__main__':main()
