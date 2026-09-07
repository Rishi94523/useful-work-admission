"""Generate descriptive summaries and figures from the completed local pilot."""
from pathlib import Path
import hashlib
import json
import os
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evaluation/docking_pilot_2026-09-06'

def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def stats(xs):return {'n':len(xs),'mean':statistics.mean(xs),'median':statistics.median(xs),'min':min(xs),'max':max(xs)}

def main():
    native=read('native_scaling.json')['rows'];verification=read('verification.json');browser=read('browser_scaling.json')['rows']
    if (OUT/'browser_full_search.json').exists():browser+=read('browser_full_search.json')['rows']
    lookup={r['parent']:r for r in native if r.get('parent')}
    summary={'scope':'Descriptive single-machine pilot, not production or newly useful scientific work. Timing paths and arithmetic workloads are explicitly different; no confidence claims from small browser samples.','cases':[],'groth16':[]}
    for case in verification['cases']:
        accepted=[r for r in case['verification'] if not r.get('native_rejected')]
        equivalent=[abs(r['recomputed']-lookup[r['id']]['score']) for r in accepted if r['engine']=='native' and lookup[r['id']]['score'] is not None]
        record={'case':case['case'],'setup_ms':case['setup']['setup_ms'],'complete_check_ms':stats([r['complete_check_ms'] for r in case['verification']]),'score_kernel_ms':stats([r['compute_ms'] for r in accepted]),'preflight_ms':stats([r['preflight_ms'] for r in accepted]),'stock_cli_agreement_max_abs':max(equivalent),'browser_claim_agreement_max_abs':max(r['error'] for r in accepted if r['engine']=='browser'),'native_rejected_count':case['native_rejected_count'],'warm_native_by_exhaustiveness':{},'browser_short_by_exhaustiveness':{}}
        for e in [1,2,4,8]:
            record['warm_native_by_exhaustiveness'][e]=stats([r['job_ms'] for r in case['warm_search'] if r['exhaustiveness']==e])
        for e in [1,4]:
            rows=[r for r in browser if r['case']==case['case'] and r['exhaustiveness']==e and r['max_evals']==1000]
            record['browser_short_by_exhaustiveness'][e]={'page_total_ms':stats([r['page_total_ms'] for r in rows]),'wasm_memory_bytes':max(r['wasm_memory_bytes'] for r in rows)}
        summary['cases'].append(record)
    full=[r for r in native if r['case']=='2P16' and r['mode']=='dock' and r['max_evals']==0]
    summary['native_full_search']={e:{'wall_ms':stats([r['wall_ms'] for r in full if r['exhaustiveness']==e]),'scores':[r['score'] for r in full if r['exhaustiveness']==e]} for e in [1,2,4]}
    summary['browser_full_search']=[{k:r[k] for k in ['case','page_total_ms','wasm_memory_bytes','pose_bytes']} for r in browser if r['max_evals']==0]
    summary['candidate_checks']={'total':sum(len(c['verification']) for c in verification['cases']),'native_grid_rejections':sum(c['native_rejected_count'] for c in verification['cases']),'attack_diagnostics':verification['attacks']}
    zk=read('zk_native.json');zk_browser=read('zk_browser.json')
    for n in [2,8]:
        rows=[r for r in zk['rows'] if r['n']==n];b=next(r for r in zk_browser['rows'] if r['n']==n)
        summary['groth16'].append({'candidate_count':n,'constraints':13302 if n==2 else 51486,'native_prove_ms':stats([r['prove_ms'] for r in rows]),'native_verify_ms':stats([x for r in rows for x in r['verify_ms']]),'plain_js_search_ms':stats([x for r in rows for x in r['plain_reference_ms']]),'browser_prove_ms':b['prove_ms'],'public_field_elements':rows[0]['public_field_elements'],'proving_key_bytes':rows[0]['key_bytes'],'witness_wasm_bytes':rows[0]['witness_wasm_bytes'],'proof_json_bytes':rows[0]['proof_json_bytes']})
    summary['groth16_negative_checks']=zk['attacks']
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    source_paths=['research/docking_pilot.py','research/docking_contract.py','research/docking_browser_worker.mjs','research/native/docking_worker.cpp','research/native/vina_pose_cache.cpp','research/tests/test_docking_contract.py','research/docking-zk/circuits/contact_search.circom','research/docking-zk/contribute.mjs','research/docking-zk/package-lock.json',*['scripts/'+x for x in ['fetch_docking_pilot.py','fetch_docking_build_deps.py','fetch_docking_circom.py','build_docking_worker.py','benchmark_docking_pilot.py','benchmark_docking_browser.mjs','verify_docking_pilot.py','archive_docking_poses.py','prepare_docking_zk.py','benchmark_docking_zk.mjs','benchmark_docking_zk_browser.mjs','verify_docking_zk_evidence.mjs','summarize_docking_pilot.py']]]
    source_records=[{'path':p,'sha256':hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),'sha256_with_lf_endings':hashlib.sha256((ROOT/p).read_bytes().replace(b'\r\n',b'\n')).hexdigest()} for p in source_paths]
    (OUT/'source_manifest.json').write_text(json.dumps(source_records,indent=2)+'\n',encoding='utf-8')
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),layout='constrained')
    colors=['#087E8B','#CB5A35','#6B5CA5']
    for case,color in zip(summary['cases'],colors):
        e=[1,2,4,8];y=[case['warm_native_by_exhaustiveness'][x]['median'] for x in e]
        axes[0].plot(e,y,'o-',label=case['case']+' search',color=color)
        axes[0].axhline(case['complete_check_ms']['median'],color=color,linestyle='--',alpha=.7,label=case['case']+' full check')
    axes[0].set(xlabel='Vina exhaustiveness (1,000-evaluation cap per run)',ylabel='Milliseconds',title='Real docking: warmed native search and checking',yscale='log',xticks=[1,2,4,8])
    axes[0].legend(fontsize=7,ncol=2,loc='upper left')
    labels=['Plain JS search','Native verify','Native prove','Browser prove']
    for i,row in enumerate(summary['groth16']):
        values=[row['plain_js_search_ms']['median'],row['native_verify_ms']['median'],row['native_prove_ms']['median'],row['browser_prove_ms']]
        axes[1].bar([j+(i-.5)*.35 for j in range(4)],values,width=.35,label=f"{row['candidate_count']} candidates",color=['#087E8B','#CB5A35'][i])
    axes[1].set(xticks=range(4),xticklabels=labels,yscale='log',ylabel='Milliseconds',title='Groth16 calibration: reduced contact model')
    axes[1].tick_params(axis='x',labelrotation=15);axes[1].legend(fontsize=8)
    fig.suptitle('Search cost, result checking and proof overhead are separate',fontsize=13)
    fig.savefig(OUT/'cost_comparison.png',dpi=180)
    fig.savefig(OUT/'cost_comparison.pdf')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['candidate_checks','groth16_negative_checks']},indent=2))

if __name__=='__main__':main()
