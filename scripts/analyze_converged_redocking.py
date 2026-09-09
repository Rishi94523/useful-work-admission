"""Post-hoc convergence diagnostics, explicitly separate from the frozen study."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
from rdkit.Chem import rdMolAlign
OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08';inputs=json.loads((OUT/'science_inputs.json').read_text());converged=json.loads((OUT/'converged_inputs.json').read_text())['rows'];stockpath=OUT/('stock_converged_all.jsonl' if (OUT/'stock_converged_all.jsonl').exists() else 'stock_converged_crystal.jsonl');stock=[json.loads(x) for x in stockpath.read_text().splitlines()]
def quality(values):
 a=np.array([r['score'] for r in values if r['label']=='active']);d=np.array([r['score'] for r in values if r['label']=='decoy'])
 if len(a)!=8 or len(d)!=8:return None
 def auc(a,d):return float(((a[:,None]<d[None,:])+.5*(a[:,None]==d[None,:])).mean())
 rng=np.random.default_rng(104729);bootstrap=[auc(rng.choice(a,8),rng.choice(d,8)) for _ in range(2000)];hits=sum(r['label']=='active' for r in sorted(values,key=lambda r:r['score'])[:4])
 return {'auc':auc(a,d),'auc_bootstrap95':np.percentile(bootstrap,[2.5,97.5]).tolist(),'top_quartile_hits':hits,'top_quartile_enrichment':hits/2}
def xyz(text):return np.array([[float(x[k:k+8]) for k in [30,38,46]] for x in text.splitlines() if x.startswith(('ATOM','HETATM')) and x[77:].strip() not in ['H','HD','G0','G1','G2','G3']])
results=[]
for t in inputs['targets']:
 if t.get('preparation_failed'):continue
 refinput=next(l for l in t['ligands'] if l['id']=='crystal')['source'];ci=next(l for l in converged if l['target']==t['target'] and l['id']=='crystal');ip=ROOT/ci['path']
 ref=Chem.RemoveHs(Chem.SDMolSupplier(str((ROOT/refinput['path']).with_suffix('.sdf')))[0]);mol=Chem.RemoveHs(Chem.SDMolSupplier(str(ip.with_suffix('.sdf')))[0]);a=np.array(mol.GetConformer().GetPositions());b=xyz(ip.read_text());_,order=linear_sum_assignment(np.linalg.norm(a[:,None,:]-b[None,:,:],axis=-1));assert np.linalg.norm(a-b[order],axis=1).max()<.01
 def rmsd(r):
  probe=Chem.Mol(ref);points=xyz(r['pose'])[order]
  for i,p in enumerate(points):probe.GetConformer().SetAtomPosition(i,tuple(map(float,p)))
  return float(rdMolAlign.CalcRMS(probe,ref,maxMatches=10000))
 rows=[json.loads(x) for x in (OUT/('converged_redocking_'+t['target']+'.jsonl')).read_text().splitlines()];configs=[]
 for cap,count in [(4000,16),(16000,16),(64000,4),(256000,1),(1000000,8)]:
  values=[r for r in rows if r['cap']==cap and r.get('ok')];assert len(values)==count
  configs.append({'cap':cap,'runs':count,'selected_rmsd_A':rmsd(min(values,key=lambda r:r['score'])),'oracle_rmsd_A':min(map(rmsd,values)),'molecular_ms':sum(r['search_ms'] for r in values),'total_call_ms':sum(r['call_ms'] for r in values)})
 control=next(r for r in stock if r['target']==t['target'] and r['id']=='crystal');ranking_controls=[r for r in stock if r['target']==t['target'] and r['id']!='crystal'];valid_controls=[r for r in ranking_controls if r['ok']];stock_quality=quality(valid_controls)
 ca=[r['score'] for r in valid_controls if r['label']=='active'];cd=[r['score'] for r in valid_controls if r['label']=='decoy'];wins=sum((a<d)+.5*(a==d) for a in ca for d in cd);bounds=[wins/64,(wins+64-len(ca)*len(cd))/64]
 ranking_path=OUT/('converged_ranking_'+t['target']+'.jsonl');ranking_rows=[json.loads(x) for x in ranking_path.read_text().splitlines()] if ranking_path.exists() else []
 for config in configs:
  values=[];costs=[]
  if config['cap']!=1000000:
   for l in [l for l in t['ligands'] if l['id']!='crystal']:
    rs=[r for r in ranking_rows if r['id']==l['id'] and r['cap']==config['cap'] and r.get('ok')]
    if len(rs)==config['runs']:values.append({'label':l['label'],'score':min(r['score'] for r in rs)});costs.append(sum(r['call_ms'] for r in rs))
  config['ranking']=quality(values);config['ranking_complete']=len(values)==16;config['ranking_median_compute_ms']=float(np.median(costs)) if costs else None
  config['ranking_compute_ms']={'scope':'Observed Node/WASM per-ligand bundle call times; excludes one-time grids and ligand loading. Not browser or stock performance.','n':len(costs),'min':min(costs),'max':max(costs),'mean':float(np.mean(costs)),'total':sum(costs),'cv_population':float(np.std(costs)/np.mean(costs))} if costs else None
  config['redocking_gate']=config['selected_rmsd_A']<=2
  config['ranking_gate']=bool(config['ranking'] and stock_quality and config['ranking']['auc']>=.65 and config['ranking']['auc']>=stock_quality['auc']-.05)
 results.append({'target':t['target'],'convergence':{k:ci[k] for k in ['statuses','energy_before','energy_after']},'configs':configs,'ranking_rows':len(ranking_rows),'stock_ranking':stock_quality,'stock_ranking_attempts':len(ranking_controls),'stock_ranking_successes':len(valid_controls),'stock_auc_missing_result_bounds':bounds,'stock_failures':[{k:v for k,v in r.items() if k!='pose'} for r in ranking_controls if not r['ok']],'stock':{k:v for k,v in control.items() if k!='pose'}|({'rmsd_A':rmsd(control)} if control['ok'] else {})})
gate_counts=[]
for cap in [4000,16000,64000,256000,1000000]:
 cs=[next(c for c in t['configs'] if c['cap']==cap) for t in results]
 gate_counts.append({'cap':cap,'targets':len(cs),'redocking_passes':sum(c['redocking_gate'] for c in cs),'ranking_evaluated':cap!=1000000,'ranking_passes':sum(c['ranking_gate'] for c in cs) if cap!=1000000 else None,'both_on_same_target':sum(c['redocking_gate'] and c['ranking_gate'] for c in cs) if cap!=1000000 else None})
(OUT/'converged_summary.json').write_text(json.dumps({'scope':'Post-hoc convergence correction: three independent crystal ligands plus all48 ranking ligands when corresponding rows exist. Not a retroactive pass of the frozen study or a fresh held-out validation. Stock controls use three concurrent independent CPU1 jobs; their wall times are not isolated performance comparators. Completeness and missing-result bounds are explicit.','gate_counts':gate_counts,'targets':results},indent=2)+'\n');print([{ 'target':r['target'],'stock_rmsd':r['stock'].get('rmsd_A'),'ranking_rows':r['ranking_rows'],'bounded':[(c['cap'],c['selected_rmsd_A']) for c in r['configs']]} for r in results])
