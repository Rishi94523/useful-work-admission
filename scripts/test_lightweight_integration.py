import hashlib,json,shutil,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from research.lightweight_docking import Assets
from research.lightweight_audit import inspect_headers,required_indices,verify
from research.docking_campaign import Campaign
BASE=ROOT/'tmp/docking-audit';OUT=ROOT/'docs/evaluation/docking_lightweight_2026-09-07'
a=Assets(BASE/'assets');evidence=[]
with tempfile.TemporaryDirectory(dir=BASE) as tmp:
    campaign=Campaign(Path(tmp)/'campaign.sqlite')
    for l in a.meta['ligands'][:4]:
        spec={'model_version':a.meta['version'],'receptor':a.meta['map_sha256'],'ligand':l['id']+':'+l['pdbqt_sha256'],'conformer_bank':hashlib.sha256(json.dumps(l['conformers_milli']).encode()).hexdigest(),'region':'FA10 30A crystal-centered pocket','search_parameters':{'poses':'104729 affine permutation of fixed bank','rotation_bank':hashlib.sha256(json.dumps(a.meta['rotations']).encode()).hexdigest(),'ligand_asset':l['id']}}
        campaign.add('fa10-pilot',spec,8192,1024,l['heavy_atoms']*1024)
    p=subprocess.Popen([shutil.which('node'),str(ROOT/'scripts/lightweight_client_ipc.mjs')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def call(request):
        p.stdin.write(json.dumps(request)+'\n');p.stdin.flush();result=json.loads(p.stdout.readline())
        if 'error' in result:raise ValueError(result)
        return result
    try:
        for _ in range(2):
            t=time.perf_counter();lease=campaign.lease('fa10-pilot','research-owner',jobs=2,ttl=60);lease_ms=(time.perf_counter()-t)*1000
            jobs=[{'id':x['spec']['search_parameters']['ligand_asset'],'start':x['start'],'count':x['count'],'mode':'C'} for x in lease['tasks']]
            commit=call({'action':'commit','jobs':jobs,'binding':lease['binding']})
            t=time.perf_counter();scores=inspect_headers(a,jobs,lease['binding'],commit['headers'],commit['root']);challenge=campaign.commit(lease['lease'],'research-owner',lease['binding'],commit['root'],weighted=True);challenge_ms=(time.perf_counter()-t)*1000
            indices=required_indices(commit['headers'],scores,challenge['draws']);answer=call({'action':'open','indices':[sorted(x) for x in indices]})
            t=time.perf_counter();result=verify(a,jobs,lease['binding'],commit['headers'],commit['root'],challenge['draws'],answer['answers']);verify_ms=(time.perf_counter()-t)*1000
            t=time.perf_counter();campaign.finish(lease['lease'],'research-owner',lease['binding'],challenge['id'],commit['root'],True,result);credit_ms=(time.perf_counter()-t)*1000
            replay=False
            try:campaign.finish(lease['lease'],'research-owner',lease['binding'],challenge['id'],commit['root'],True,result)
            except ValueError:replay=True
            evidence.append({'jobs':jobs,'lease_ms':lease_ms,'validate_and_challenge_ms':challenge_ms,'verify_ms':verify_ms,'credit_ms':credit_ms,'client_kernel_ms':commit['kernel_ms'],'client_commit_ms':commit['commit_ms'],'replay_rejected':replay,**result})
        try:campaign.lease('fa10-pilot','research-owner',jobs=1);raise AssertionError('Completed work reissued')
        except LookupError:pass
        snapshot=campaign.snapshot()
    finally:p.stdin.write('{"action":"quit"}\n');p.stdin.flush();p.stdin.close();p.wait(timeout=10)
(OUT/'integration.json').write_text(json.dumps({'scope':'Local SQLite/Node/Python IPC; real molecular scoring and CSPRNG challenges. No network identity/admission service.','runs':evidence,'final_state':snapshot},indent=2)+'\n')
print(json.dumps({'accepted_bundles':len(evidence),'completed_jobs':snapshot['units'].get('COMPLETED'),'replays_rejected':sum(r['replay_rejected'] for r in evidence)}))
