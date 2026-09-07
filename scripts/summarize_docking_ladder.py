"""Summarize measured data; extrapolations are explicitly separate artifacts."""
import json
import math
from pathlib import Path
import statistics as st

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/evaluation/docking_ladder_2026-09-07'


def main():
    node = json.loads((OUT / 'node_scaling.json').read_text())['rows']
    browser = json.loads((OUT / 'browser_scaling.json').read_text())['rows']
    setup = json.loads((OUT / 'setup.json').read_text())['circuits']
    rows = []
    for n in [2, 8, 16, 32, 64]:
        nr = [r for r in node if r['n'] == n]
        br = [r for r in browser if r['n'] == n]
        rows.append(dict(n=n, status='measured', constraints=6364*n+574,
            node_prove_s_median=st.median(r['prove_ms']/1000 for r in nr),
            node_prove_s_range=[min(r['prove_ms']/1000 for r in nr), max(r['prove_ms']/1000 for r in nr)],
            browser_prove_s_median=st.median(r['prove_ms']/1000 for r in br),
            browser_prove_s_range=[min(r['prove_ms']/1000 for r in br), max(r['prove_ms']/1000 for r in br)],
            warm_server_verify_ms_median=st.median(t for r in nr for t in r['warm_verify_ms']),
            cold_server_verify_ms_range=[min(r['cold_verify_ms'] for r in nr), max(r['cold_verify_ms'] for r in nr)],
            plain_js_search_ms_median=st.median(t for r in nr for t in r['plain_search_ms']),
            node_sampled_rss_mib_max=max(r['measurement']['sampled_peak_rss_bytes']/2**20 for r in nr),
            browser_tree_sampled_rss_mib_max=max(r['measurement']['sampled_peak_rss_bytes']/2**20 for r in br),
            key_mib=nr[0]['proving_key_bytes']/2**20,
            proof_json_bytes_range=[min(r['proof_json_bytes'] for r in nr), max(r['proof_json_bytes'] for r in nr)]))
    # A model envelope, not a confidence/prediction interval: linear to C log2 C
    # growth, calibrated against all individual N=16,32,64 runs.
    projections=[]
    for n in [128, 256]:
        c=setup[str(n)]['constraints']
        estimate={'n':n,'constraints_measured':c,'status':'compiled only; all run-resource values below are projections',
                  'key_mib_linear_projection':(3923516*n+310088)/2**20}
        for name, data in [('node',node),('browser',browser)]:
            samples=[r for r in data if r['n']>=16]
            lows=[r['prove_ms']/1000*c/(6364*r['n']+574) for r in samples]
            highs=[r['prove_ms']/1000*c*math.log2(c)/((6364*r['n']+574)*math.log2(6364*r['n']+574)) for r in samples]
            estimate[name+'_prove_s_model_envelope']=[min(lows),max(highs)]
            # Memory is runtime-dependent. Show linear scaling of observed
            # whole-process RSS/constraint, not a predicted allocation limit.
            estimates=[r['measurement']['sampled_peak_rss_bytes']/2**30*c/(6364*r['n']+574) for r in samples]
            estimate[name+'_rss_gib_linear_model_envelope']=[min(estimates),max(estimates)]
        projections.append(estimate)
    evidence={'scope':'Original synthetic contact circuit, single desktop. Three Node and two Chrome trials per tier. Public inputs fixed at 51. RSS includes process lifecycle; browser RSS sums Chrome plus Node asset server, may double-count shared pages. Ranges are observations, not confidence intervals.',
              'measured':rows,'projections':projections,
              'projection_method':'Time envelope = min observed seconds/constraint times target constraints, through max observed seconds/(C log2 C) times target C log2 C, using individual 16/32/64 trials. Memory = range of observed RSS/C times target C. Key size affine fit to measured 16/32/64. Not measured at 128/256; allocation cliffs, paging and setup may break these models.'}
    (OUT/'summary.json').write_text(json.dumps(evidence,indent=2)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(10,4.1),layout='constrained')
    for label,key in [('Chrome proving','browser_prove_s_median'),('Node proving','node_prove_s_median')]:
        axes[0].plot([r['n'] for r in rows],[r[key] for r in rows],'o-',label=label)
    axes[0].axhspan(.2,1.5,color='#38a169',alpha=.12,label='Normal-user target')
    axes[0].set(xscale='log',yscale='log',xlabel='Candidates (measured)',ylabel='Seconds',title='Proof generation, calibration circuit')
    axes[0].legend(fontsize=8)
    axes[1].plot([r['n'] for r in rows],[r['warm_server_verify_ms_median'] for r in rows],'o-',color='#805ad5')
    axes[1].set(xscale='log',xlabel='Candidates (measured)',ylabel='Milliseconds',ylim=(0,20),title='Warm Node verification, 51 public fields')
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle('One Windows desktop; not a proof of scientific docking or attacker effort',fontsize=10)
    fig.savefig(OUT/'scaling.png',dpi=170);fig.savefig(OUT/'scaling.pdf')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':main()
