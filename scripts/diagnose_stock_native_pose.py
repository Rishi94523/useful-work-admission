"""Exploratory crystal-only scoring; never used for configuration selection."""
import json,re,subprocess,time
from pathlib import Path
from validate_vina_stock_controls import ROOT,digest,quality

def main():
 out=ROOT/'local-research/stock-diagnostic-2026-09-14';data=json.loads((out/'inputs.json').read_text());exe=ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe';assert digest(exe)==data['stock_sha256'];rows=[]
 for t in data['targets']:
  ligand=ROOT/t['crystal']['path'];receptor=ROOT/t['receptors']['source_state'];assert digest(ligand)==t['crystal']['sha256'] and digest(receptor)==t['receptor_hashes']['source_state']
  for mode in ['score_only','local_only']:
   dest=ROOT/'tmp/vina-stock-diagnostic'/t['target']/('native_'+mode+'.pdbqt');args=[str(exe),'--receptor',str(receptor),'--ligand',str(ligand),'--cpu','1','--seed','104729','--'+mode,'--out',str(dest)]
   for i,x in enumerate('xyz'):args+=['--center_'+x,str(t['boxes']['crystal_site']['center'][i]),'--size_'+x,str(t['boxes']['crystal_site']['size'][i])]
   start=time.perf_counter();row={'target':t['target'],'mode':mode,'args':args,'scope':'Exploratory crystal-only diagnostic. Not a selection criterion. No evaluation molecules.'}
   try:
    p=subprocess.run(args,capture_output=True,text=True,timeout=300);row.update(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
    if p.returncode==0:
     score=float(re.search(r'Estimated Free Energy of Binding\s*:\s*([-\d.]+)',p.stdout).group(1));row['score']=score
     # local_only writes coordinates without a VINA RESULT remark; use its
     # reported stdout energy only for the existing RMSD parser's header.
     if mode=='local_only':row.update(quality(ligand,ligand.with_suffix('.sdf'),f'REMARK VINA RESULT: {score} 0 0\n'+dest.read_text()))
   except Exception as e:row['error']=str(e)
   row['wall_ms']=1000*(time.perf_counter()-start);rows.append(row);(out/'native_pose_diagnostic.json').write_text(json.dumps(rows,indent=2)+'\n');print(t['target'],mode,row.get('score'),row.get('top_rmsd_A'),flush=True)
if __name__=='__main__':main()
