"""Derive reproducible tables/figures from measured files and label model bounds."""
import gzip,json,math,platform,statistics,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07';BASE=ROOT/'tmp/docking-audit'
def read(name):return json.loads((OUT/name).read_text())
def median(xs):return float(statistics.median(xs))
verification=read('verification.json')['results'];rows=[]
for runtime in ['chrome','node']:
    for suffix in ['', '-extended']:
        for row in read(runtime+suffix+'_bench.json')['summary']:
            runs=row['repeats'];v=[r for r in verification if r['runtime']==runtime and r['mode']==row['mode'] and r['jobsCount']==row['jobs'] and r['count']==row['poses_per_job']]
            rows.append({'runtime':runtime,'mode':row['mode'],'jobs':row['jobs'],'poses_per_job':row['poses_per_job'],**{key:median(r[key] for r in runs) for key in ['useful_ms','kernel_ms','commit_ms','opening_ms','client_ms','useful_work_fraction','owned_array_bytes']},'server_verify_ms':median(r['server_verify_ms'] for r in v),'checked_poses_median':median(r['checked_poses'] for r in v),'wire_bytes':median(r['commitment_wire_bytes']+r['opening_wire_bytes'] for r in runs),'client_to_verifier_ratio':median(r['client_ms'] for r in runs)/median(r['server_verify_ms'] for r in v)})
calibration=read('science.json')['calibration'];x=np.array([r['heavy_atoms'] for r in calibration]);y=np.array([median(r['batch_1024_ms']) for r in calibration]);pred=[]
for i in range(len(x)):
    mask=np.arange(len(x))!=i;slope=(x[mask]@y[mask])/(x[mask]@x[mask]);pred.append(slope*x[i])
calibration_result={'scope':'32 Python/NumPy batches, 1024 poses, atom-only through-origin predictor with leave-one-out fits. Not browser/device calibration.','median_absolute_percentage_error':float(np.median(abs(np.array(pred)-y)/y)),'maximum_absolute_percentage_error':float(np.max(abs(np.array(pred)-y)/y)),'min_ms':float(y.min()),'max_ms':float(y.max())}
probabilities=[]
for skipped in [.01,.1,.25,.5,.75,.9]:
    probabilities.append({'incorrect_fraction_assumed_equal_to_skipped':skipped,'q32_pass':(1-skipped)**32,'q64_pass':(1-skipped)**64,'q_for_1e_6':math.ceil(math.log(1e-6)/math.log(1-skipped))})
wire=(BASE/'assets/maps.bin').read_bytes();compressed=len(gzip.compress(wire,compresslevel=6,mtime=0))
native=read('native_kernel.json')['results'];cpd=json.loads((ROOT/'docs/evaluation/docking_ladder_2026-09-07/cpd_proofs.json').read_text());d=[r for r in cpd['rows'] if r['n']==64]
summary={'scope':'Measured medians unless explicitly labeled. useful_work_fraction is a paired molecular-kernel-time proxy; scientific utility is not established by this ratio. Warm checking excludes JSON parsing, campaign DB operations, network and asset loading.','host':{'python':platform.python_version(),'platform':platform.platform(),'processor':platform.processor()},'rows':rows,'calibration':calibration_result,'conditional_probability_table':probabilities,'asset_transfer':{'raw_map_bytes':len(wire),'gzip6_map_bytes':compressed,'gzip_10mbps_seconds':compressed*8/1e7,'gzip_100mbps_seconds':compressed*8/1e8,'scope':'Compressed size measured; network transfer times are bandwidth-only projections. Browser timings used uncompressed loopback assets.'},'native_integer_control':{'sum16_job4096_warm_ms':sum(median(r['ms'][1:]) for r in native if r['poses']==4096),'single_job32_warm_ms_range':[min(median(r['ms'][1:]) for r in native if r['poses']==32),max(median(r['ms'][1:]) for r in native if r['poses']==32)]},'historical_groth16_cpd64':{'scope':'Previously measured different scientific workload, not Groth16 over this docking bank; files inspected again, proving not rerun.','plain_bigint_ms':median(t for r in d for t in r['plain_search_ms']),'prove_node_ms':median(r['prove_ms'] for r in d),'verify_warm_ms':median(t for r in d for t in r['warm_verify_ms']),'proof_and_public_json_bytes':median(len(json.dumps({'proof':r['proof'],'publicSignals':r['publicSignals']},separators=(',',':')).encode()) for r in d),'proving_key_bytes':d[0]['proving_key_bytes']}}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
table=['| Protocol | Ligands × poses | Molecular kernel ms | Total client ms | Kernel fraction | Warm verifier ms | Client→server KiB |','|---|---:|---:|---:|---:|---:|---:|']
for r in rows:
    if r['runtime']=='chrome' and r['poses_per_job'] in [4096,16384]:table.append(f"| {r['mode']} | {r['jobs']} × {r['poses_per_job']} | {r['useful_ms']:.1f} | {r['client_ms']:.1f} | {100*r['useful_work_fraction']:.1f}% | {r['server_verify_ms']:.2f} | {r['wire_bytes']/1024:.1f} |")
(OUT/'tables.md').write_text('\n'.join(table)+'\n\nColumns are independently computed medians of three runs; the kernel fraction is the median paired ratio, so ratios of the other medians can differ. Verifier timings exclude JSON parsing, lease/challenge/credit transactions and network.\n',encoding='utf-8')
fig,axes=plt.subplots(1,3,figsize=(15,4.5),layout='constrained')
colors={'B':'#157F73','C':'#3561A7','E':'#BD592C'}
for mode in ['B','C','E']:
    data=[r for r in rows if r['runtime']=='chrome' and r['mode']==mode and r['poses_per_job']==4096]
    axes[0].plot([r['jobs'] for r in data],[r['client_ms'] for r in data],'-o',color=colors[mode],label=f'{mode} client')
    axes[0].plot([r['jobs'] for r in data],[r['server_verify_ms'] for r in data],'--o',color=colors[mode],label=f'{mode} checker')
axes[0].set(xlabel='Ligands (4,096 poses each)',ylabel='Milliseconds, log scale',yscale='log',xticks=[1,4,16],title='Measured Chrome and Python costs');axes[0].legend(fontsize=8,ncol=2)
f=np.linspace(.01,.99,200)
for q in [16,32,64,128]:axes[1].plot(100*(1-f),f**q,label=f'q={q}')
axes[1].set(xlabel='Incorrect committed records (%)',ylabel='Pass probability',yscale='log',ylim=(1e-12,1),xlim=(0,90),title='Analytical bound: incorrect records');axes[1].legend(fontsize=8)
science=read('science.json');control=read('uncapped_controls.json');comparisons=science['comparison']+[{'method':'vina uncapped','roc_auc':control['roc_auc'],'stratified_bootstrap_auc_95':control['auc_bootstrap_95']}]
ys=np.array([r['roc_auc'] for r in comparisons]);ci=np.array([r['stratified_bootstrap_auc_95'] for r in comparisons]);axes[2].errorbar(np.arange(6),ys,yerr=[ys-ci[:,0],ci[:,1]-ys],fmt='o',capsize=3,color='#3561A7');axes[2].axhline(.5,color='grey',linestyle=':');axes[2].set(xticks=np.arange(6),xticklabels=['bank\n4k','bank\n16k','bank\n64k','Vina\ncap E1','Vina\ncap E4','Vina\nuncap E1'],ylim=(0,1),ylabel='ROC-AUC with bootstrap 95% interval',title='Scientific pilot: 16 actives / 16 decoys')
for ax in axes:ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.2)
fig.savefig(OUT/'tradeoffs.png',dpi=180);fig.savefig(OUT/'tradeoffs.svg');plt.close(fig)
svg=OUT/'tradeoffs.svg';svg.write_text('\n'.join(line.rstrip() for line in svg.read_text(encoding='utf-8').splitlines())+'\n',encoding='utf-8')
print(json.dumps({'rows':len(rows),'calibration':calibration_result,'transfer':summary['asset_transfer']}))
