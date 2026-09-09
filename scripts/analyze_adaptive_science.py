"""Evaluate predeclared gates; preserve unsuccessful targets and configurations."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'))
from rdkit import Chem
from rdkit.Chem import rdMolAlign
OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'
inputs=json.loads((OUT/'science_inputs.json').read_text());stock=list(map(json.loads,(OUT/'stock.jsonl').read_text().splitlines())) if (OUT/'stock.jsonl').exists() else []
def auc(labels,scores):
    a=np.asarray(scores)[labels];d=np.asarray(scores)[~labels]
    return float(((a[:,None]<d[None,:])+.5*(a[:,None]==d[None,:])).mean())
def quality(labels,scores):
    labels=np.asarray(labels);scores=np.asarray(scores);rng=np.random.default_rng(104729);a=np.flatnonzero(labels);d=np.flatnonzero(~labels);values=[]
    for _ in range(2000):
        ix=np.r_[rng.choice(a,len(a)),rng.choice(d,len(d))];values.append(auc(labels[ix],scores[ix]))
    k=max(1,len(scores)//4);hits=int(labels[np.argsort(scores)[:k]].sum())
    return {'auc':auc(labels,scores),'auc_bootstrap95':np.percentile(values,[2.5,97.5]).tolist(),'top_quartile_hits':hits,'top_quartile_size':k,'top_quartile_enrichment':(hits/k)/float(labels.mean())}
def heavy(text):return np.array([[float(line[k:k+8]) for k in [30,38,46]] for line in text.splitlines() if line.startswith(('ATOM','HETATM')) and line[77:].strip() not in ['H','HD','G0','G1','G2','G3']])
results=[]
for target in inputs['targets']:
    if target.get('preparation_failed'):results.append(target);continue
    path=OUT/('science_'+target['target']+'.jsonl')
    if not path.exists():results.append({'target':target['target'],'pending':True});continue
    raw_rows=list(map(json.loads,path.read_text().splitlines()));rows=list({r['key']:r for r in raw_rows}.values());crystal=next(x for x in target['ligands'] if x['id']=='crystal')
    ref=Chem.RemoveHs(Chem.SDMolSupplier(str((ROOT/crystal['source']['path']).with_suffix('.sdf')))[0]);orders={}
    for conf in ['source','independent']:
        m=Chem.RemoveHs(Chem.SDMolSupplier(str((ROOT/crystal[conf]['path']).with_suffix('.sdf')))[0]);xyz=np.array(m.GetConformer().GetPositions());initial=heavy((ROOT/crystal[conf]['path']).read_text());_,order=linear_sum_assignment(np.linalg.norm(xyz[:,None,:]-initial[None,:,:],axis=-1))
        if np.linalg.norm(xyz-initial[order],axis=1).max()>.01:raise ValueError('Atom map mismatch')
        orders[conf]=order
    def rmsd(row):
        m=Chem.Mol(ref);points=heavy(row['pose'])[orders[row['conformer']]]
        for i,p in enumerate(points):m.GetConformer().SetAtomPosition(i,tuple(map(float,p)))
        return float(rdMolAlign.CalcRMS(m,ref,maxMatches=10000))
    controls=[r for r in stock if r['target']==target['target']];rank_control=[r for r in controls if r['label']!='redocking' and r['ok']]
    control_quality=quality([r['label']=='active' for r in rank_control],[r['score'] for r in rank_control]) if len(rank_control)==16 else None
    configs=[]
    for method,bound,count in [('global',16000,16),('global',64000,4),('global',256000,1),('local',200,4)]:
        group=[r for r in rows if r['method']==method and r.get('cap',r.get('steps'))==bound];scores=[];labels=[];costs=[];complete=True
        for l in [x for x in target['ligands'] if x['label']!='redocking']:
            values=[r for r in group if r['id']==l['id'] and r['conformer']=='independent' and r.get('ok')]
            if len(values)!=count:complete=False;continue
            labels.append(l['label']=='active');scores.append(min(r['score'] for r in values));costs.append(sum(r['call_ms'] if method=='global' else r['total_compute_ms'] for r in values))
        q=quality(labels,scores) if len(scores)==16 else None;redocking={}
        for conf in ['source','independent']:
            values=[r for r in group if r['id']=='crystal' and r['conformer']==conf and r.get('ok')]
            if values:
                best=min(values,key=lambda r:r['score']);redocking[conf]={'selected_rmsd_A':rmsd(best),'oracle_rmsd_A':min(map(rmsd,values)),'successful_runs':sum(rmsd(r)<=2 for r in values),'runs':len(values)}
        configs.append({'method':method,'bound':bound,'runs':count,'nominal_eval_budget':bound*count if method=='global' else None,'ranking':q,'ranking_complete':complete and len(scores)==16,'cost_accounting_complete':method!='local' or all('source_reload_ms' in r for r in group),'median_total_compute_ms':float(np.median(costs)) if costs else None,'redocking':redocking,
                        'ranking_gate':bool(q and control_quality and q['auc']>=.65 and q['auc']>=control_quality['auc']-.05),'redocking_gate_independent':redocking.get('independent',{}).get('selected_rmsd_A',float('inf'))<=2})
    long=[]
    for conf in ['source','independent']:
        for n in [1,2,4,8]:
            r=[x for x in rows if x['id']=='crystal' and x['conformer']==conf and x.get('cap')==1000000 and x['run']<n and x.get('ok')]
            if r:long.append({'conformer':conf,'runs':len(r),'selected_rmsd_A':rmsd(min(r,key=lambda x:x['score'])),'oracle_rmsd_A':min(map(rmsd,r)),'total_compute_ms':sum(x['call_ms'] for x in r)})
    results.append({'target':target['target'],'rows':len(rows),'superseded_measurements':len(raw_rows)-len(rows),'failures':[{k:v for k,v in r.items() if k!='pose'} for r in rows if not r.get('ok')],'ligand_preparation_failures':target['failures'],'stock_ranking':control_quality,'stock_completed':len(controls),'stock_redocking':[{k:r[k] for k in ['conformer','score','wall_ms']}|{'rmsd_A':rmsd(r)} for r in controls if r['id']=='crystal' and r['ok']],'configs':configs,'long_redocking':long})
output={'scope':'Predeclared exploratory gates on three prepared targets; HIVPR preparation failure retained. Independent-conformer ranking, source and independent redocking. Nominal global budgets match; actual compute differs. Local refinement includes generation/reload and is not equal-budget global search.','targets':results}
(OUT/'science_summary.json').write_text(json.dumps(output,indent=2)+'\n');print([{k:t.get(k) for k in ['target','rows','stock_completed','preparation_failed']} for t in results])
