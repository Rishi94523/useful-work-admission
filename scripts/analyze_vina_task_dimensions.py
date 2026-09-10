"""Reaggregate identical measured units into ligand/run difficulty dimensions."""
import json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_tasks_2026-09-10'
rows=[json.loads(x) for x in (OUT/'campaign.jsonl').read_text().splitlines()];results=[]
def summary(values):return {'mean_ms':statistics.mean(values),'cv':statistics.pstdev(values)/statistics.mean(values),'min_ms':min(values),'max_ms':max(values)}
for target in ['fa10','hs90a','tryb1']:
 for cap in [0,16000,64000]:
  selected=[r for r in rows if r['target']==target and r['id']!='crystal' and r.get('cap')==cap and (r.get('method')=='matched' or r.get('method')=='normal' and r['runs']==8)]
  assert len(selected)==8 and all(len(r['unit_metrics'])>=8 for r in selected)
  matrix=[[m['ms'] for m in r['unit_metrics'][:8]] for r in selected]
  one=[sum(r) for r in matrix];many=[sum(r[i] for r in matrix) for i in range(8)]
  assert abs(sum(one)-sum(many))<1e-6
  results.append({'target':target,'cap':cap,'ligands':[r['id'] for r in selected],'one_ligand_eight_runs':summary(one),'eight_ligands_one_run':summary(many)})
(OUT/'dimensions.json').write_text(json.dumps({'scope':'Reaggregation of the same64 actually measured native MC units per target/budget into eight row-wise or eight column-wise batches. Not a new parallel/browser/network experiment. Identical total/mean compute by construction. CV measures variation within this fixed8-ligand panel, not prediction error for unseen ligands. Mixed batches supply one run toward each of eight pools, not eight fully validated docking results.','results':results},indent=2)+'\n');print('Compared',len(results),'ligand/run panels')
