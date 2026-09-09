"""Stock E8 control of every independently prepared pilot molecule, resumable."""
import json,re,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/adaptive_docking_2026-09-08';TMP=ROOT/'tmp/adaptive-docking'
targets=json.loads((OUT/'science_inputs.json').read_text())['targets'];dest=OUT/'stock.jsonl'
done={r['key'] for r in map(json.loads,dest.read_text().splitlines())} if dest.exists() else set()
for target in targets:
 if target.get('preparation_failed'):continue
 for ligand in target['ligands']:
  for conformer in (['source','independent'] if ligand['id']=='crystal' else ['independent']):
   key=':'.join([target['target'],ligand['id'],conformer]);
   if key in done:continue
   pose=TMP/target['target']/(ligand['id']+'_'+conformer+'_stock.pdbqt')
   args=[str(ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'),'--receptor',str(ROOT/target['receptor']),'--ligand',str(ROOT/ligand[conformer]['path']),'--cpu','1','--seed','104729','--exhaustiveness','8','--num_modes','9','--out',str(pose)]
   for axis,c in zip('xyz',target['center']):args+=['--center_'+axis,str(c),'--size_'+axis,'30']
   t=time.perf_counter();row={'key':key,'target':target['target'],'id':ligand['id'],'label':ligand['label'],'conformer':conformer,'input_sha256':ligand[conformer]['sha256']}
   try:
    p=subprocess.run(args,capture_output=True,text=True,timeout=600)
    if p.returncode:raise RuntimeError((p.stdout+p.stderr)[-1500:])
    text=pose.read_text().split('ENDMDL')[0]+'ENDMDL\n';row.update(ok=True,pose=text,score=float(re.search(r'REMARK VINA RESULT:\s+([-0-9.]+)',text).group(1)))
   except Exception as e:row.update(ok=False,error=str(e))
   row['wall_ms']=(time.perf_counter()-t)*1000
   with dest.open('a') as f:f.write(json.dumps(row)+'\n')
   print(key,row['ok'],round(row['wall_ms']),flush=True)
