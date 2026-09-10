"""Near-equal measured MC cost; no quality-dependent selection or new search."""
import json
from benchmark_vina_task_split import ROOT,OUT,BASE,OLD,start,call,stop
rows=[json.loads(x) for x in (OUT/'campaign.jsonl').read_text().splitlines()];targets=json.loads((OLD/'science_inputs.json').read_text())['targets'];converged=json.loads((OLD/'converged_inputs.json').read_text())['rows'];dest=OUT/'wallmatched.jsonl'
done={r['key'] for r in map(json.loads,dest.read_text().splitlines())} if dest.exists() else set()
for reference in [r for r in rows if r.get('method')=='normal' and r['runs']==1]:
 t=next(t for t in targets if t['target']==reference['target']);l=next(l for l in t['ligands'] if l['id']==reference['id']);source=l['source'] if reference['conformer']=='source' else next(r for r in converged if r['target']==t['target'] and r['id']==l['id']);prefix=':'.join(reference['key'].split(':')[:3]);folder=BASE/'campaign'/t['target']/(l['id']+'_'+reference['conformer']);pending=[cap for cap in [16000,64000,256000] if prefix+':wallmatched:'+str(cap) not in done]
 if not pending:continue
 p=start(t,ROOT/source['path'])
 try:
  for cap in pending:
   original=next(r for r in rows if r['key']==prefix+':matched:'+str(cap))
   if 'error' in original:continue
   metrics=original['unit_metrics'];sums=[];s=0
   for r in metrics:s+=r['ms'];sums.append(s)
   index=min(range(len(sums)),key=lambda i:abs(sums[i]-reference['search_ms']));n=index+1;pose=folder/f'wallmatched_{cap}.pdbqt';final=call(p,2,0,n,cap,folder/str(cap),pose)
   row={**{k:reference[k] for k in ['target','id','label','conformer','input_sha256']},'key':prefix+':wallmatched:'+str(cap),'method':'wallmatched','cap':cap,'runs':n,'search_ms':sums[index],'reference_search_ms':reference['search_ms'],'search_ratio':sums[index]/reference['search_ms'],'available_runs':len(metrics),'finalizer':final,'pose':pose.read_text()}
   with dest.open('a') as f:f.write(json.dumps(row)+'\n')
   print(row['key'],n,round(row['search_ratio'],3),flush=True)
 finally:stop(p)
