"""Score amendment 13 (proof-of-work gate baseline) against P1 and P2."""
import json,statistics,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
A13=ROOT/'local-research/admission-amendment13-2026-09-28/results.jsonl'
A12=ROOT/'local-research/admission-amendment12-2026-09-25/memory-sqlite/results.jsonl'
CLASSES=('budget','mid','flagship')

def load(path,grids):
 rows=[json.loads(l) for l in path.read_text(encoding='utf-8').splitlines() if l.strip()]
 return [r for r in rows if r.get('grid') in grids]

def means(rows):
 cells={}
 for r in rows:
  cells.setdefault((r['grid'],r['mechanism'],r['workers'],r['attacker_cores']),[]).append(r)
 return {k:({c:statistics.mean(x['classes'][c]['served'] for x in v) for c in CLASSES},len(v)) for k,v in cells.items()}

def main():
 base=means(load(A13,('follow','patience')));useful=means(load(A12,('follow','patience')))
 print('cells',len(base),'runs',sum(n for _,n in base.values()))
 p1=[(k,min(v.values())) for k,(v,n) in base.items()]
 bad=[x for x in p1 if x[1]<0.9]
 print('P1 every class >= 0.90 in every cell: %s (%d/%d cells)'%(not bad,len(p1)-len(bad),len(p1)))
 for k,v in bad:print('  miss',k,round(v,3))
 p2=[]
 for k,(v,n) in useful.items():
  if k[3] in (4,16) and k in base and min(v.values())<0.2:
   p2.append((k,min(base[k][0].values()),min(v.values())))
 missed=[x for x in p2 if x[1]<0.9]
 print('P2 cells where useful work fell below 0.2: %d; baseline >= 0.90 in %d'%(len(p2),len(p2)-len(missed)))
 for k,b,u in sorted(p2):print('  %-8s %-9s w=%d cores=%-3g useful-work min %.3f  proof-of-work min %.3f'%(k[0],k[1],k[2],k[3],u,b))
 out={'P1_pass':not bad,'P1_cells':len(p1),'P1_misses':[[list(k),v] for k,v in bad],
      'P2_cells':[[list(k),b,u] for k,b,u in p2],'P2_pass':not missed}
 (A13.parent/'summary.json').write_text(json.dumps(out,indent=1),encoding='utf-8')

if __name__=='__main__':main()
