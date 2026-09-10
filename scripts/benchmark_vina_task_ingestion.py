"""Real raw Vina pools through durable simulated visitor sessions and merge.

Consumes previously computed scientific work, deliberately measuring the one-use
credit model rather than claiming fresh client execution after lease issuance.
Selected runs really execute again after commitment; timing is native/local.
"""
import hashlib,json,sys,tempfile,time
from pathlib import Path
from benchmark_vina_task_split import ROOT,OUT,BASE,OLD,start,call,stop
sys.path.insert(0,str(ROOT))
from research.vina_pool_campaign import VinaPoolCampaign
from research.docking_campaign import canonical

def sha(data):return hashlib.sha256(data).hexdigest()
target=next(t for t in json.loads((OLD/'science_inputs.json').read_text())['targets'] if t['target']=='fa10')
ligand=next(l for l in target['ligands'] if l['id']=='crystal')['source']
seeds=json.loads((OUT/'browser.json').read_text())['seeds']
source=BASE/'campaign/fa10/crystal_source/16000'
spec={'model_version':sha((BASE/'vina_tasks.exe').read_bytes()),'receptor':sha((ROOT/target['receptor']).read_bytes()),'ligand':'fa10:crystal','conformer_bank':ligand['sha256'],'region':json.dumps(target['center']),'search_parameters':{'method':'native-mc-pool9','max_evals':16000}}
results=[]
with tempfile.TemporaryDirectory(dir=BASE) as temp:
 folder=Path(temp);p=start(target,ROOT/ligand['path'])
 try:
  reference=folder/'reference.pdbqt';call(p,2,0,32,16000,source,reference)
  for batch,q in [(1,1),(8,2),(32,4)]:
   db=folder/f'{batch}.sqlite';campaign=VinaPoolCampaign(db);campaign.register_pool('p',spec,seeds)
   replay_ms=0;protocol_ms=0;payload_bytes=0;verified=0
   for session in range(32//batch):
    begin=time.perf_counter();campaign=VinaPoolCampaign(db);owner=f'visitor-{session}';lease=campaign.lease('p',owner,jobs=batch)
    payloads={};leaves=[]
    for task in lease['tasks']:
     i=task['ordinal'];payload=canonical({'pool':(source/f'{i}.task').read_text(),'trace':(source/f'{i}.task.trace').read_text()})
     payloads[task['task']]=payload;leaves.append(sha(canonical([task,sha(payload)])));payload_bytes+=len(payload)
    root=sha(canonical([lease['binding'],leaves]));challenge=campaign.commit(lease['lease'],owner,lease['binding'],root,samples=q)
    protocol_ms+=1000*(time.perf_counter()-begin);audited=[]
    for index,_ in challenge['draws']:
     task=lease['tasks'][index];i=task['ordinal'];begin=time.perf_counter()
     call(p,1,i,32,16000,folder/'replay',folder/'unused.pdbqt')
     expected=canonical({'pool':(folder/'replay'/f'{i}.task').read_text(),'trace':(folder/'replay'/f'{i}.task.trace').read_text()})
     assert expected==payloads[task['task']]
     replay_ms+=1000*(time.perf_counter()-begin);audited.append(task['task']);verified+=1
    begin=time.perf_counter();campaign.finish_outputs(lease['lease'],owner,lease['binding'],challenge['id'],root,payloads,audited);protocol_ms+=1000*(time.perf_counter()-begin)
   coverage=campaign.coverage('p');ordered=campaign.ordered_outputs('p');merged=folder/f'merged{batch}';merged.mkdir()
   for item in ordered:
    data=json.loads(item['payload']);(merged/f"{item['ordinal']}.task").write_text(data['pool'])
   final=folder/f'{batch}.pdbqt';finalizer=call(p,2,0,32,16000,merged,final)
   assert final.read_bytes()==reference.read_bytes()
   try:campaign.lease('p','repeat');raise AssertionError('Duplicate reissued')
   except LookupError:pass
   results.append({'sessions':32//batch,'runs_per_session':batch,'q_per_session':q,'replayed_runs':verified,'coverage':coverage,'ordered_merge_exact':True,'replay_ms':replay_ms,'protocol_storage_ms':protocol_ms,'payload_bytes':payload_bytes,'database_bytes':db.stat().st_size,'finalizer':finalizer})
   (OUT/'ingestion.json').write_text(json.dumps({'scope':'Native local integration, real previously computed 16k-cap raw task outputs (not the normal E32 quality control); simulated visitor IDs, not humans. Replay after commitment. One-use work credit, not evidence of fresh client execution. Per-session challenge cannot be pooled across identities without weakening individual admission assurance.','results':results},indent=2)+'\n');print(batch,'runs/session',verified,'actual replays',flush=True)
 finally:stop(p)
