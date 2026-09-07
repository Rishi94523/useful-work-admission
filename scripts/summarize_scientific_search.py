"""Summarize measured scientific pilots without mixing their timing boundaries."""
import json
from pathlib import Path
import statistics as s
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/docking_ladder_2026-09-07'
node=json.loads((OUT/'cpd_proofs.json').read_text())['rows'];browser=json.loads((OUT/'cpd_browser.json').read_text())['rows'];setup=json.loads((OUT/'cpd_setup.json').read_text())['circuits']
rows=[]
for n in [16,64]:
    nr=[r for r in node if r['n']==n];br=[r for r in browser if r['n']==n]
    rows.append({'n':n,'constraints':setup[str(n)]['constraints'],'node_prove_ms_median':s.median(r['prove_ms'] for r in nr),'browser_prove_ms_median':s.median(r['prove_ms'] for r in br),'browser_prove_ms_range':[min(r['prove_ms'] for r in br),max(r['prove_ms'] for r in br)],'plain_bigint_search_ms_median':s.median(t for r in nr for t in r['plain_search_ms']),'warm_verify_ms_median':s.median(t for r in nr for t in r['warm_verify_ms']),'node_sampled_rss_mib_max':max(r['measurement']['sampled_peak_rss_bytes']/2**20 for r in nr),'browser_tree_sampled_rss_mib_max':max(r['measurement']['sampled_peak_rss_bytes']/2**20 for r in br),'key_mib':nr[0]['proving_key_bytes']/2**20,'public_fields':3})
evidence={'scope':'Measured exact bounded search over a restricted published CPD model. Fixed campaign-specific coefficients. No fresh-effort lower bound, real-device study, or prospective protein design. RSS includes process lifetime; browser RSS sums server and Chrome and can count shared pages twice.','cpd':rows,'validation':{'published_proofs_accepted':10,'changed_statements_rejected':30,'wrong_tier_rejected':True,'random_and_boundary_polynomial_vs_wcsp_cases':1002,'wraparound_search_cases':2,'scientific_and_merkle_unit_tests_passed':9},'rigid_grid':[{'case':r['case'],'poses':r['space'],'oracle_pose_checks':len(r['oracle']),'max_float_vs_native_error':r['max_oracle_error'],'max_quantization_error':r['max_quantization_error'],'top1_agrees':r['best_pose_agrees'],'top10_overlap':r['top10_overlap'],'full_bank_search_ms':r['timings'][-1]['median_search_ms'],'one_pose_check_ms':r['timings'][-1]['one_pose_check_ms_median'],'best_energy':r['timings'][-1]['best_quantized_energy']/10000,'map_mib':sum(m['bytes'] for m in r['map_files'])/2**20} for r in json.loads((OUT/'rigid_grid.json').read_text())['cases']]}
(OUT/'scientific_summary.json').write_text(json.dumps(evidence,indent=2)+'\n')
print(json.dumps(evidence,indent=2))
