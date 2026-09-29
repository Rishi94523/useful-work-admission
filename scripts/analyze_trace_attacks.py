"""Score amendment 16 (Q1-Q4) from the adaptive-attack replay records."""
import json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'local-research/trace-attacks-2026-09-29'
VARIANTS=['v1_fastmath','v2_halflocal','v3_norefine']

def main():
 rows=[json.loads(l) for l in (DIR/'units.jsonl').read_text().splitlines() if l.strip()]
 by={v:[r for r in rows if r['variant']==v] for v in ['control',*VARIANTS]}
 control=by['control'];ctl={(r['id'],r['seed'],r['unit']):r for r in control}
 control_ok=len(control)==99 and all(r['accepted'] for r in control)
 out={'control_units':len(control),'control_reproduces':control_ok,'variants':{}}
 q1=q2=True;q3={}
 for v in VARIANTS:
  rs=by[v];acc=sum(r['accepted'] for r in rs)
  frac=[r['first_diff_step']/r['honest_steps'] for r in rs if r['first_diff_step'] is not None]
  early=all(r['first_diff_step'] is not None and r['first_diff_step']<=0.01*r['honest_steps'] for r in rs)
  eps_h=statistics.median(r['honest_evals']/r['honest_steps'] for r in rs)
  eps_v=statistics.median(r['variant_evals']/r['variant_steps'] for r in rs)
  ms_per_eval=statistics.median((r['wall_ms']/r['variant_evals'])/(ctl[(r['id'],r['seed'],r['unit'])]['wall_ms']/ctl[(r['id'],r['seed'],r['unit'])]['variant_evals']) for r in rs)
  saving=(1-ms_per_eval) if v=='v1_fastmath' else (1-eps_v/eps_h)
  need={'v1_fastmath':0.10,'v2_halflocal':0.25,'v3_norefine':0.05}[v]
  q1&=acc==0;q2&=early;q3[v]=saving>=need
  out['variants'][v]={'units':len(rs),'accepted':acc,'pool_equal':sum(r['pool_equal'] for r in rs),'all_within_1pct':early,
   'first_diff_step_median':statistics.median(r['first_diff_step'] for r in rs),'first_diff_step_max':max(r['first_diff_step'] for r in rs),
   'first_diff_fraction_max':max(frac),'evals_per_step_honest':eps_h,'evals_per_step_variant':eps_v,
   'wall_per_eval_ratio_vs_control':ms_per_eval,'saving':saving,'saving_needed':need}
  print('%-13s accepted %d/%d  first diff step median %s max %s (max %.4f of steps)  saving %.1f%% (need %.0f%%)'%(v,acc,len(rs),
   out['variants'][v]['first_diff_step_median'],out['variants'][v]['first_diff_step_max'],max(frac),100*saving,100*need))
 r1=json.loads((DIR/'reuse.json').read_text())
 out.update({'Q1':q1 and control_ok,'Q2':q2,'Q3':all(q3.values()),'Q3_by_variant':q3,'Q4':r1['fraction']<0.001,'reuse_fraction':r1['fraction'],
             'reuse_steps':r1['steps'],'reuse_jobs':len(r1['jobs']),'reuse_units':sum(j['units'] for j in r1['jobs'])})
 (DIR/'summary.json').write_text(json.dumps(out,indent=1))
 print('control reproduces honest output: %s (%d units)'%(control_ok,len(control)))
 print('Q1 no variant accepted:',out['Q1']);print('Q2 all diverge within first 1%% of steps:',q2)
 print('Q3 each variant saves work:',out['Q3'],q3)
 print('Q4 cross-unit recurrence %.6f over %d steps in %d units of %d jobs (< 0.001): %s'%(r1['fraction'],r1['steps'],out['reuse_units'],out['reuse_jobs'],out['Q4']))

if __name__=='__main__':main()
