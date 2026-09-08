"""Quality, coverage, budget variance and shortcut diagnostics from actual runs."""
import json,sys
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'tmp/docking-audit/deps'));OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
from rdkit import Chem
from rdkit.Chem import rdMolAlign
def auc(labels,energies):
    a=np.asarray(energies)[labels];d=np.asarray(energies)[~labels];return float(((a[:,None]<d[None,:])+.5*(a[:,None]==d[None,:])).mean())
def bootstrap(labels,energies):
    rng=np.random.default_rng(104729);a=np.flatnonzero(labels);d=np.flatnonzero(~labels);values=[]
    for _ in range(2000):
        ix=np.r_[rng.choice(a,len(a)),rng.choice(d,len(d))];values.append(auc(labels[ix],np.array(energies)[ix]))
    return np.percentile(values,[2.5,97.5]).tolist()
def heavy(text):return np.array([[float(line[k:k+8]) for k in [30,38,46]] for line in text.splitlines() if line.startswith(('ATOM','HETATM')) and line[77:].strip() not in ('H','HD','G0','G1','G2','G3')])
def main():
    wasm='--wasm' in sys.argv
    plan=json.loads((OUT/'plan.json').read_text());data=json.loads((OUT/('wasm_science.json' if wasm else 'native.json')).read_text());rows=data['rows'];ligands=plan['ligands'][:-1];labels=np.array([l['label']=='active' for l in ligands]);quality=[]
    caps=[4000,16000] if wasm else plan['caps']
    ref=Chem.RemoveHs(Chem.SDMolSupplier(str(ROOT/'tmp/docking-audit/ligands/crystal.sdf'),removeHs=False)[0]);xyz=np.array(ref.GetConformer().GetPositions());initial=heavy((ROOT/'tmp/docking-audit/ligands/crystal.pdbqt').read_text());_,order=linear_sum_assignment(np.linalg.norm(xyz[:,None,:]-initial[None,:,:],axis=-1))
    def rmsd(row):
        mol=Chem.Mol(ref)
        for i,p in enumerate(heavy(row['pose'])[order]):mol.GetConformer().SetAtomPosition(i,tuple(map(float,p)))
        return float(rdMolAlign.CalcRMS(mol,ref,maxMatches=10000))
    for cap in caps:
        crystal=[{**r,'rmsd_A':rmsd(r)} for r in rows if r['id']=='crystal' and r['cap']==cap and r['ok']]
        for n in [1,2,4,8,16,32]:
            selected=[];costs=[]
            for l in ligands:
                choices=[r for r in rows if r['id']==l['id'] and r['cap']==cap and r['run']<n]
                if len(choices)!=n:raise ValueError('Incomplete science evidence')
                selected.append(min(r['score'] for r in choices if r['ok']));costs.append(sum(r['search_ms'] for r in choices if r['ok']))
            cr=[r for r in crystal if r['run']<n];best=min(cr,key=lambda x:x['score'])
            quality.append({'cap':cap,'runs':n,'roc_auc':auc(labels,selected),'bootstrap95':bootstrap(labels,selected),'top4_actives':int(labels[np.argsort(selected)[:4]].sum()),'scores':selected,'median_search_ms':float(np.median(costs)),'redocking_selected_rmsd_A':best['rmsd_A'],'redocking_oracle_best_rmsd_A':min(x['rmsd_A'] for x in cr),'redocking_selected_score':best['score'],'redocking_selected_seed':best['seed'],'redocking_successful_runs':sum(x['rmsd_A']<2 for x in cr)})
    shortcuts=[]
    for low,high in ([(4000,16000)] if wasm else [(1000,4000),(4000,16000)]):
        matches=0;scores_close=0;total=0;ratios=[]
        for l in plan['ligands']:
            lo=[r for r in rows if r['id']==l['id'] and r['cap']==low and r['ok']];hi={r['seed']:r for r in rows if r['id']==l['id'] and r['cap']==high and r['ok']}
            for r in lo:
                h=hi[r['seed']];total+=1;matches+=int(r['pose']==h['pose'] and r['score']==h['score']);scores_close+=int(abs(r['score']-h['score'])<.001);ratios.append(r['search_ms']/h['search_ms'])
        shortcuts.append({'low_cap':low,'assigned_cap':high,'exact_records_matching':matches,'score_within_0_001':scores_close,'total':total,'median_cost_ratio':float(np.median(ratios))})
    runtime=[]
    for cap in caps:
        times_by_ligand=[[x['search_ms'] for x in rows if x['id']==l['id'] and x['cap']==cap and x['ok']] for l in ligands]
        for j,r in [(1,16),(4,4),(16,1),(1,32),(4,8),(16,2)]:
            rng=np.random.default_rng(134);samples=[]
            for _ in range(2000):
                group=rng.choice(len(ligands),j,replace=False);total=0
                for li in group:
                    total+=sum(rng.choice(times_by_ligand[li],r,replace=False))
                samples.append(total)
            runtime.append({'cap':cap,'ligands':j,'runs':r,'method':'Resampling sums of measured native runtimes; not new browser executions','mean_ms':float(np.mean(samples)),'cv':float(np.std(samples)/np.mean(samples)),'p05_p95_ms':np.percentile(samples,[5,95]).tolist()})
    old=json.loads((ROOT/'docs/evaluation/docking_lightweight_2026-09-07/uncapped_controls.json').read_text())
    output={'scope':'One FA10 target, same 16 active/16 presumed-decoy selection, fixed input conformer with flexible torsions. Redocking uses known bound input conformation but random initial placement/torsions.','backend':'wasm' if wasm else 'native','quality':quality,'shortcut_comparison':shortcuts,'runtime_resampling':runtime,'historical_uncapped_e1':{'roc_auc':old['roc_auc'],'bootstrap95':old['auc_bootstrap_95'],'redocking_e4_rmsd_A':old['redocking']['vina_selected_symmetry_rmsd_A']},'eval_count_range':{str(cap):[min(r['evals'] for r in rows if r['cap']==cap and r['ok']),max(r['evals'] for r in rows if r['cap']==cap and r['ok'])] for cap in caps},'failures':[r for r in rows if not r['ok']]}
    if wasm and (OUT/'wasm_control.json').exists():
        control=json.loads((OUT/'wasm_control.json').read_text())['rows'][0];output['same_wasm_uncapped_e8_redocking']={**{k:v for k,v in control.items() if k!='pose'},'rmsd_A':rmsd(control)}
    (OUT/('science_wasm_summary.json' if wasm else 'science_summary.json')).write_text(json.dumps(output,indent=2)+'\n');print(json.dumps([{k:r[k] for k in ['cap','runs','roc_auc','redocking_selected_rmsd_A']} for r in quality]))
if __name__=='__main__':main()
