"""Summarize measured controls and paired exploratory ranking uncertainty."""
import gzip,hashlib,json
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_validation_2026-09-10'
stock=json.loads((OUT/'stock_controls.json').read_text());ranking=json.loads((OUT/'matched_ranking.json').read_text());rng=np.random.default_rng(104729)
assert len(stock)==12 and all(r.get('redocking_gate') for r in stock)
assert len(ranking)==16
summaries=[]
for target in ['fa10','tryb1']:
 rs=[r for r in ranking if r['target']==target];a=[r for r in rs if r['label']=='active'];d=[r for r in rs if r['label']=='decoy'];assert len(a)==len(d)==4
 def auc(a,d,key):return float(np.mean([[float(x[key]<y[key])+.5*float(x[key]==y[key]) for y in d] for x in a]))
 old=auc(a,d,'normal_score');new=auc(a,d,'medium_score');deltas=[]
 for _ in range(10000):
  aa=[a[i] for i in rng.integers(0,4,4)];dd=[d[i] for i in rng.integers(0,4,4)]
  deltas.append(auc(aa,dd,'medium_score')-auc(aa,dd,'normal_score'))
 summaries.append({'target':target,'normal_E8_auc':old,'medium_auc':new,'delta':new-old,'paired_compound_bootstrap95_delta':np.percentile(deltas,[2.5,97.5]).tolist(),'evaluation_ratio_range':[min(r['medium_evals']/r['reference_evals'] for r in rs),max(r['medium_evals']/r['reference_evals'] for r in rs)],'scope':'Fixed prior4+4 subset, one parent seed, paired resampling within active/decoy classes. Descriptive pilot interval, not a population or multi-seed noninferiority test.'})
source=ROOT/'docs/evaluation/adaptive_docking_2026-09-08/stock_converged_all.jsonl';data=source.read_bytes();archive=OUT/'historical_stock_ranking.jsonl.gz';archive.write_bytes(gzip.compress(data,mtime=0));assert gzip.decompress(archive.read_bytes())==data
result={'completed_stock_controls':len(stock),'all_stock_redocking_gates_passed':True,'stock_RMSD_ranges':{t:[min(r['top_rmsd_A'] for r in stock if r['target']==t),max(r['top_rmsd_A'] for r in stock if r['target']==t)] for t in ['1iep','fa10','hs90a','tryb1']},'matched_ranking':summaries,'historical_ranking_archive':{'path':archive.name,'uncompressed_sha256':hashlib.sha256(data).hexdigest()},'scope':'New stock controls, new medium-run redocking/ranking, and explicitly labeled historical controls. No new architecture or production deployment.'}
(OUT/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(summaries)
