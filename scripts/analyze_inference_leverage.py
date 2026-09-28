"""Score amendment 14 (L1-L5) from the leverage benchmark and availability grid."""
import json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LEV=ROOT/'local-research/inference-leverage-2026-09-28/results.json'
AV=ROOT/'local-research/admission-amendment14-2026-09-28/results.jsonl'
CLASSES=('budget','mid','flagship')
DOCKING={'verify_ms':1520.0,'leverage':4.0,'leverage_trusted':10.0}   # one replay per four-unit bundle; 1/p at p = 0.1
POW={'verify_ms':0.77e-3}

def main():
 rows=json.loads(LEV.read_text(encoding='utf-8'))
 l1=all(r['perturbations_rejected']==3*len(r['operators']) for r in rows)
 ordinary=[r for r in rows if r['model']!='mnist-wide-mlp'];wide=next(r for r in rows if r['model']=='mnist-wide-mlp')
 l2=all(r['leverage_8pct']<1.5 for r in ordinary)
 l3=wide['leverage_no_audit']>=10 and wide['leverage_8pct']>=2.5
 points=[(r['verify_eff_ms'],r['leverage_8pct']) for r in rows]+[(DOCKING['verify_ms'],DOCKING['leverage'])]
 l5=not any(v<10 and l>4 for v,l in points)
 print('L1 every perturbation rejected:',l1)
 print('L2 ordinary models leverage(8%%) < 1.5: %s %s'%(l2,[(r['model'],round(r['leverage_8pct'],2)) for r in ordinary]))
 print('L3 wide MLP >=10 no audit and >=2.5 at 8%%: %s (%.2f, %.2f)'%(l3,wide['leverage_no_audit'],wide['leverage_8pct']))
 print('L5 no workload with V<10 ms and L>4:',l5)
 out={'L1':l1,'L2':l2,'L3':l3,'L5':l5}
 if AV.exists():
  av=[json.loads(l) for l in AV.read_text(encoding='utf-8').splitlines() if l.strip()]
  cells={}
  for r in av:cells.setdefault((r['workload'],r['grid'],r['mechanism'],r['workers'],r['attacker_cores']),[]).append(r)
  low={k:min(statistics.mean(x['classes'][c]['served'] for x in v) for c in CLASSES) for k,v in cells.items()}
  misses=[(k,round(v,3)) for k,v in low.items() if v<0.9]
  out['L4']=not misses;out['L4_cells']=len(low);out['L4_runs']=len(av);out['L4_misses']=misses
  print('L4 every class >= 0.90 in every cell: %s (%d cells, %d runs)'%(not misses,len(low),len(av)))
  for m in misses[:20]:print('  miss',m)
 (LEV.parent/'summary.json').write_text(json.dumps(out,indent=1),encoding='utf-8')

if __name__=='__main__':main()
