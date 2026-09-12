"""Model-derived figure; no molecular or production throughput claims."""
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'docs/evaluation/vina_followup_2026-09-12'
data=json.loads((OUT/'admission_policy_comparison.json').read_text())
plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
fig,ax=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
for policy,lag,label in [('immediate_random',0,'Audit before selected access'),('deferred_random',0,'Access before audit'),('deferred_random',2,'Deferred + 2 later admissions')]:
    rows=[r for r in data['persistent_zero_work'] if r['policy']==policy and r['exposure_cap']==20 and r['verdict_lag_admissions']==lag]
    ax[0].plot([100*r['audit_probability'] for r in rows],[r['zero_work_bad_grants_exact'] for r in rows],marker='o',label=label)
ax[0].set(xscale='log',xlabel='Random audit probability (%)',ylabel='Expected fraudulent admissions',title='Zero-work identity, 20-attempt exposure cap')
ax[0].legend(fontsize=8);ax[0].grid(alpha=.2)
for retry,label in [(1,'Fresh bundle each attempt'),(3,'Same cached bundle, up to 3 challenges')]:
    rows=[r for r in data['cached_bundle_retries'] if r['q']==1 and r['correct_units']==1 and r['max_challenges']==retry]
    ax[1].plot([r['n'] for r in rows],[r['computed_units_per_success'] for r in rows],marker='o',label=label)
ax[1].set(xlabel='Assigned runs per bundle',ylabel='Computed units per successful admission',title='Attacker caches one correct run; q = 1')
ax[1].legend(fontsize=8);ax[1].grid(alpha=.2)
fig.suptitle('Admission economics under explicit equal-cost and identity assumptions',fontsize=12)
fig.savefig(OUT/'admission_policy.png',dpi=180)
fig.savefig(OUT/'admission_policy.svg')
svg=OUT/'admission_policy.svg'
svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
