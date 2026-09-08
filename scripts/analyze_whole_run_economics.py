"""Derive honest cost curves, conditional attacks and two-stage science policy."""
import json,math,gzip,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/docking_whole_runs_2026-09-08'
def main():
    b=json.loads((OUT/'browser.json').read_text());a=json.loads((OUT/'audits.json').read_text());rows=[]
    for key in sorted({(x['cap'],x['ligands'],x['runs']) for x in b['rows']}):
        cap,j,n=key;r=[x for x in b['rows'] if (x['cap'],x['ligands'],x['runs'])==key]
        item={'cap':cap,'ligands':j,'runs':n,'total_units':j*n,'repeats':len(r)}
        for name in ['molecular_ms','compute_call_ms','client_warm_ms','client_with_ligand_init_ms','commit_ms','load_ms','wasm_memory_bytes','full_scientific_bytes','commitment_bytes']:item[name]=float(np.median([x[name] for x in r]))
        item['molecular_fraction_warm']=float(np.median([x['molecular_ms']/x['client_warm_ms'] for x in r]));item['molecular_fraction_including_ligand_init']=float(np.median([x['molecular_ms']/x['client_with_ligand_init_ms'] for x in r]))
        item['repeat_outputs_equal']=all(r[0]['records']==x['records'] for x in r[1:])
        item['audit']=[{**x,'warm_client_to_warm_replay_ratio':item['molecular_ms']/max(.001,x['replay_warm_ms']),'warm_client_to_full_check_ratio':item['molecular_ms']/max(.001,x['total_ms']),'full_client_to_full_check_ratio':item['client_with_ligand_init_ms']/max(.001,x['total_ms'])} for x in a['honest'] if (x['cap'],x['ligands'],x['runs'])==key]
        rows.append(item)
    bounds=[]
    for n in [16,64,256,1024]:
        for f in [.1,.25,.5,.75,.9]:
            k=math.floor(n*f)
            for q in [1,4,8,16,32]:
                if q>n:continue
                p=math.comb(k,q)/math.comb(n,q) if k>=q else 0
                bounds.append({'n':n,'computed':k,'q':q,'pass_probability':p,'expected_relative_work_per_accept':(k/n)/p if p else None,'scope':'Conditional distinct-unit model with NEW science per attempt; this expected-cost column does NOT apply to retries of the same partially cached cohort. See retry_attack.json for that correction. Equal run cost; null when no acceptance possible.'})
    plan=json.loads((OUT/'plan.json').read_text());bytes_raw=sum(x['bytes'] for x in plan['maps']);compressed=sum(len(gzip.compress((ROOT/x['path']).read_bytes(),mtime=0)) for x in plan['maps'])
    # Later work repairs false highly ranked records, but top-k alone cannot reveal
    # an honestly computed optimum deliberately hidden among poor claimed results.
    aggregation=[]
    for n in [16,64,256]:
        for q in [4,8]:
            for later in [0,4,16]:
                if q+later>n:continue
                aggregation.append({'total_units':n,'admission_audits':q,'later_distinct_replays':later,'probability_one_hidden_record_missed':1-(q+later)/n,'scope':'Analytical uniform sampling, one bad record; targeted validation of reported top-k gives no guarantee of selecting a hidden true optimum.'})
    output={'scope':'Warm molecular-kernel ratios exclude reusable preparation, network/DB and production queues. Full measured check includes ligand switching; no all-ligand server cache implemented.','tiers':rows,'bounds':bounds,'map_bytes':bytes_raw,'map_gzip_bytes':compressed,'bandwidth_projection_seconds':{'10Mbps':compressed*8/10e6,'100Mbps':compressed*8/100e6},'browser_init':b['initialization'],'attacks':a['attacks'],'all_honest_audits_pass':all(x['accepted'] for x in a['honest']),'tamper':a['tamper'],'aggregate_sampling':aggregation}
    trace=json.loads((OUT/'trace_ablation.json').read_text())
    output['trace_ablation']={'scope':trace['scope'],'groups':[]}
    for cap in [4000,16000]:
        group=[x for x in trace['rows'] if x['cap']==cap]
        output['trace_ablation']['groups'].append({'cap':cap,'pairs':len(group),'all_pose_score_equal':all(x['pose_equal'] for x in group),'median_trace_to_plain_search_ratio':float(np.median([x['trace_search_ms']/x['plain_search_ms'] for x in group])),'aggregate_trace_to_plain_search_ratio':sum(x['trace_search_ms'] for x in group)/sum(x['plain_search_ms'] for x in group)})
    output['scientific_repair']=a['scientific_repair']
    output['honest_audit_transcripts']=len(a['honest'])
    if (OUT/'retry_attack.json').exists():
        retry=json.loads((OUT/'retry_attack.json').read_text())
        output['retry_policy']={'scope':retry['scope'],'limitation':retry['limitation'],'runs':[{'guarded':x['guarded'],'attempts':len(x['attempts']),'accepted':x['accepted'],'additional_science_per_retry':x['additional_science_per_retry']} for x in retry['runs']]}
    (OUT/'economics.json').write_text(json.dumps(output,indent=2)+'\n')
    lines=['# Whole-run measured cost table','','Times are local milliseconds; client with preparation excludes one-time map/module startup and Internet transfer. Server full checking includes selected ligand preparation.','', '| Cap | Ligands × runs | Molecular ms | Warm client ms | Client + ligand setup ms | Warm molecular fraction | Commit ms | q=8 warm/full check ms |', '|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in rows:
        z=next((z for z in x['audit'] if z['q']==8),None);check=f"{z['replay_warm_ms']:.1f} / {z['total_ms']:.1f}" if z else '—'
        lines.append(f"| {x['cap']} | {x['ligands']} × {x['runs']} | {x['molecular_ms']:.1f} | {x['client_warm_ms']:.1f} | {x['client_with_ligand_init_ms']:.1f} | {100*x['molecular_fraction_warm']:.1f}% | {x['commit_ms']:.2f} | {check} |")
    (OUT/'tables.md').write_text('\n'.join(lines)+'\n',encoding='utf-8');print('\n'.join(lines))
if __name__=='__main__':main()
