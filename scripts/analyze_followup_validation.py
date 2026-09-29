"""Read-only analysis of amendments 17-19b; optionally compare a second host."""
import argparse
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
LR=ROOT/'local-research'


def read(p):return json.loads(p.read_text())


def portable_summary(report):
    assert len(report['rows'])==12
    out={}
    for name in ('mnist-mlp','mnist-wide-mlp'):
        for batch in (1,32):
            rows=[r for r in report['rows'] if r['model']==name and r['batch']==batch]
            assert sorted(r['session'] for r in rows)==[0,1,2]
            assert all(r['tested_perturbations']==r['rejected'] and r['reference_traces_verified']==128 for r in rows)
            out[name+':'+str(batch)]=statistics.median(r['native_reference_leverage']['0.08'] for r in rows)
    return out


def analyze(second=None):
    folder=LR/'realtime-admission-2026-09-29'
    cases=[read(p) for p in folder.glob('*.json') if p.name not in ('manifest.json','summary.json','calibration.json')]
    assert len(cases)==18 and not any(c['errors'] for c in cases)
    table=[]
    for factor in (0,.75,2):
        for mode in ('replay','pow'):
            rows=[c for c in cases if c['mode']==mode and c['attack_factor']==factor]
            assert len(rows)==3
            table.append(dict(mode=mode,factor=factor,
                deadline={k:dict(successes=sum(r['summary'][k]['deadline_success'] for r in rows),
                                 offered=sum(r['summary'][k]['offered'] for r in rows)) for k in ('new','trusted')},
                native_cpu_s=sum(sum(r['native_cpu_s'].values()) for r in rows),
                harness_cpu_s=sum(r['harness_cpu_s'] for r in rows),
                max_queue=max(r['queue_peak'] for r in rows)))
    events=[e for c in cases if c['mode']=='replay' for e in c['events']]
    local=read(LR/'portable-dense-2026-09-29/ryzen7.json');portable={'local':portable_summary(local),'second_host':'pending'}
    if second:
        remote=read(second)
        assert remote['package_sha256']==local['package_sha256'],'Package mismatch; results are not paired'
        ratios={k:v/portable['local'][k] for k,v in portable_summary(remote).items()}
        portable.update(second_host=remote['cpu'],remote=portable_summary(remote),ratios=ratios,
                        PH1=bool(local['PH1'] and remote['PH1']),PH2=all(.5<v<2 for v in ratios.values()))
    return dict(realtime=dict(cases=18,table=table,replays=len(events),honest=sum(e['accepted'] for e in events),
        rejected=sum(not e['accepted'] for e in events),median_service_s=statistics.median(e['service_s'] for e in events),
        median_native_cpu_s=statistics.median(e['native_cpu_s'] for e in events),
        native_peak_mib=max(v for c in cases for v in c['native_peak_rss'].values())/2**20,
        queued_payload_peak_bytes=max(c['queued_payload_peak'] for c in cases),
        upload_bytes=sum(c['upload_bytes'] for c in cases),
        useful_units=sum(c['scientific_units_persisted'] for c in cases)),
        cost_aware=read(LR/'cost-aware-2026-09-29/summary.json'),
        inference=read(LR/'inference-repetition-2026-09-29/summary.json'),portable=portable)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--second-host',type=Path);ap.add_argument('--output',type=Path);args=ap.parse_args()
    result=analyze(args.second_host);data=json.dumps(result,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(data)
    print(data)


if __name__=='__main__':main()
