// Post-hoc diagnostic of converged independent crystal inputs; no ranking claim.
import {readFile,appendFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import factory from '../tmp/docking-runs/whole_run_type_cache.mjs';
import {createEngine} from '../research/whole_run_engine.mjs';
import {sha,encode} from '../research/whole_run_protocol.mjs';
const folder='docs/evaluation/adaptive_docking_2026-09-08/';
const targets=JSON.parse(await readFile(folder+'science_inputs.json','utf8')).targets.filter(t=>!t.preparation_failed);
if(!process.argv[2]){
 for(const t of targets){const p=spawnSync(process.execPath,[process.argv[1],t.target],{stdio:'inherit'});if(p.status)throw Error('Converged redocking worker failed');}
}else{
 const target=targets.find(t=>t.target===process.argv[2]),input=JSON.parse(await readFile(folder+'converged_inputs.json','utf8')).rows.find(r=>r.target===target.target&&r.id==='crystal');if(!input.converged)throw Error('Crystal MMFF did not converge');
 const dest=folder+'converged_redocking_'+target.target+'.jsonl';let prior=[];try{prior=(await readFile(dest,'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);}catch(e){if(e.code!=='ENOENT')throw e;}
 if(prior.length===45){console.log(target.target,'converged diagnostic complete');process.exit(0);}
 const files=await Promise.all(target.maps.map(async m=>({name:m.name,data:await readFile(m.path)})));const engine=await createEngine(factory,files,await readFile(input.path,'utf8'));
 for(const [cap,runs] of [[4000,16],[16000,16],[64000,4],[256000,1],[1000000,8]])for(let i=0;i<runs;i++){
  const key=cap+':'+i;if(prior.some(r=>r.key===key))continue;const r=engine.run(104729+13007*i,cap),row={key,target:target.target,id:'crystal',conformer:'converged',cap,run:i,input_sha256:input.sha256,...r};
  if(row.trace){row.trace_sha256=await sha(encode(row.trace));row.trace_values=row.trace.length;delete row.trace;}
  await appendFile(dest,JSON.stringify(row)+'\n');prior.push(row);
 }
 console.log(target.target,prior.length,'converged diagnostic records');
}
