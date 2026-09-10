"""Aggregate-level quality and measured budgets; never require each run to win."""
import json,sys,re
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
from rdkit.Chem import rdMolAlign
OUT=ROOT/'docs/evaluation/vina_tasks_2026-09-10';OLD=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'
inputs=json.loads((OLD/'science_inputs.json').read_text())['targets'];corrected=json.loads((OLD/'converged_inputs.json').read_text())['rows']
rows=[json.loads(x) for x in (OUT/'campaign.jsonl').read_text().splitlines()]
if (OUT/'wallmatched.jsonl').exists():rows += [json.loads(x) for x in (OUT/'wallmatched.jsonl').read_text().splitlines()]
stock=[json.loads(x) for x in (OLD/'stock_converged_all.jsonl').read_text().splitlines()]
def pose_score(p):return float(re.search(r'REMARK VINA RESULT:\s+([-\d.]+)',p).group(1))
def result_score(r):return r['finalizer']['score'] if 'finalizer' in r else r.get('score',pose_score(r['pose']))
def coords(p):return np.array([[float(x[k:k+8]) for k in [30,38,46]] for x in p.split('ENDMDL')[0].splitlines() if x.startswith(('ATOM','HETATM')) and x[77:].strip() not in ['H','HD','G0','G1','G2','G3']])
def topology(m):return ([a.GetAtomicNum() for a in m.GetAtoms()],sorted((min(b.GetBeginAtomIdx(),b.GetEndAtomIdx()),max(b.GetBeginAtomIdx(),b.GetEndAtomIdx()),str(b.GetBondType())) for b in m.GetBonds()))

def quality(rs):
 a=np.array([r['score'] for r in rs if r['label']=='active']);d=np.array([r['score'] for r in rs if r['label']=='decoy'])
 if len(a)!=4 or len(d)!=4:return None
 def auc(a,d):return float(((a[:,None]<d)+.5*(a[:,None]==d)).mean())
 rng=np.random.default_rng(104729);ci=np.percentile([auc(rng.choice(a,4),rng.choice(d,4)) for _ in range(2000)],[2.5,97.5]).tolist()
 return {'auc':auc(a,d),'bootstrap95':ci,'top2_enrichment':sum(r['label']=='active' for r in sorted(rs,key=lambda r:r['score'])[:2])}
def missing_auc_bounds(rs):
 a=np.array([r['score'] for r in rs if r['label']=='active']);d=np.array([r['score'] for r in rs if r['label']=='decoy']);known=float(((a[:,None]<d)+.5*(a[:,None]==d)).sum());return [known/16,(known+16-len(a)*len(d))/16]

results=[];e32_quality=None
for t in inputs:
 if t.get('preparation_failed'):continue
 crystal=next(l for l in t['ligands'] if l['id']=='crystal');ref=Chem.RemoveHs(Chem.SDMolSupplier(str((ROOT/crystal['source']['path']).with_suffix('.sdf')))[0]);orders={}
 for conf in ['source','converged']:
  source=crystal['source'] if conf=='source' else next(r for r in corrected if r['target']==t['target'] and r['id']=='crystal');path=ROOT/source['path'];m=Chem.RemoveHs(Chem.SDMolSupplier(str(path.with_suffix('.sdf')))[0]);assert topology(m)==topology(ref),'Conformer atom order/topology differs from reference';xyz=np.array(m.GetConformer().GetPositions());initial=coords(path.read_text());_,order=linear_sum_assignment(np.linalg.norm(xyz[:,None,:]-initial[None,:,:],axis=-1));assert np.linalg.norm(xyz-initial[order],axis=1).max()<.01;orders[conf]=order
 def rmsd(pose,conf):
  probe=Chem.Mol(ref);positions=coords(pose)[orders[conf]]
  for i,p in enumerate(positions):probe.GetConformer().SetAtomPosition(i,tuple(map(float,p)))
  return float(rdMolAlign.CalcRMS(probe,ref,maxMatches=10000))
 def pose_quality(r):
  poses=[part for part in r['pose'].split('ENDMDL') if 'ATOM' in part];distances=[rmsd(part,r['conformer']) for part in poses];best=min(range(len(poses)),key=lambda i:distances[i])
  return {'rmsd_A':distances[0],'best_returned_pose_rmsd_A':distances[best],'best_returned_pose_rank':best+1,'returned_poses':len(poses),'best_rmsd_pose_score':pose_score(poses[best]),'top_pose_score':pose_score(poses[0])}
 if t['target']=='fa10' and (OUT/'e32.json').exists():
  experiment=json.loads((OUT/'e32.json').read_text());e32_quality={k:rmsd(experiment[k],'source') for k in ['normal_pose','medium_pose','wallmatched_pose']}
  if experiment.get('stock',{}).get('pose'):e32_quality['downloaded_stock_pose']=rmsd(experiment['stock']['pose'],'source')
 selected=[l['id'] for label in ['active','decoy'] for i,l in enumerate([l for l in t['ligands'] if l['label']==label]) if i in [0,2,5,7]]
 controls=[r for r in stock if r['target']==t['target'] and r['id'] in selected];valid=[r for r in controls if r['ok']];configs=[]
 for method,points in [('normal',[1,2,4,8,16,32]),('matched',[16000,64000,256000]),('wallmatched',[16000,64000,256000])]:
  for point in points:
   rs=[r for r in rows if r['target']==t['target'] and r.get('method')==method and r['runs' if method=='normal' else 'cap']==point];ranking=[{'label':r['label'],'score':result_score(r)} for r in rs if r['id']!='crystal'];redocking=[{'conformer':r['conformer'],**pose_quality(r),'search_ms':r['search_ms'],'runs':r['runs'],'finalizer_ms':r.get('finalizer',{}).get('ms'),'search_ratio':r.get('search_ratio'),'eval_ratio':r.get('evals',0)/r['reference_evals'] if r.get('reference_evals') else None} for r in rs if r['id']=='crystal']
   configs.append({'method':method,'point':point,'ranking_complete':len(ranking)==8,'ranking':quality(ranking),'redocking':redocking,'ranking_median_search_ms':float(np.median([r['search_ms'] for r in rs if r['id']!='crystal'])) if ranking else None})
 results.append({'target':t['target'],'selected_ranking_ids':selected,'stock_subset_quality':quality(valid),'stock_subset_auc_bounds':missing_auc_bounds(valid),'stock_subset_successes':len(valid),'stock_missing_ids':[r['id'] for r in controls if not r['ok']],'configs':configs})
eq=json.loads((OUT/'split_equivalence.json').read_text());comparison=[]
for r in eq:
 comparison.append({'target':r['target'],'cap':r['cap'],'same_build_exact':r['final_pose_exact'] and all(r['task_trace_exact']),'stock_score':pose_score(r['stock']['pose']) if r['stock']['pose'] else None,'split_score':r['monolithic']['score'],'split_run_ms':[t['ms'] for t in r['tasks']],'aggregation_ms':r['finalizer']['ms'],'official_binary_pose_exact':r['split_pose']==r['stock']['pose']})
(OUT/'summary.json').write_text(json.dumps({'scope':'Small preselected4-active/4-decoy subset per target. Aggregate-level scientific quality. Native same-build decomposition equality is distinct from downloaded-binary agreement and from browser evidence. Historical stock E8 quality controls use identical corrected inputs but concurrent wall times are not matched performance.','rows':len(rows),'errors':[r for r in rows if 'error' in r],'equivalence':comparison,'targets':results,'e32_score_selected_rmsd_A':e32_quality},indent=2)+'\n')
print('Analyzed',len(rows),'aggregate results')
