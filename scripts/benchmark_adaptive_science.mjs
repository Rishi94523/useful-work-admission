// Canonical WASM science: bounded global searches and local-refinement control.
import {readFile,appendFile,mkdir} from 'node:fs/promises';
import factory from '../tmp/docking-runs/whole_run_adaptive.mjs';
import {createEngine} from '../research/whole_run_engine.mjs';
import {sha,encode} from '../research/whole_run_protocol.mjs';
const folder='docs/evaluation/adaptive_docking_2026-09-08/',targetName=process.argv[2];
const target=JSON.parse(await readFile(folder+'science_inputs.json','utf8')).targets.find(t=>t.target===targetName);
if(!target||target.preparation_failed)throw Error('Target not prepared');
const output=folder+'science_'+targetName+'.jsonl';let prior=[];
try{prior=(await readFile(output,'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);}catch(e){if(e.code!=='ENOENT')throw e;}
const files=await Promise.all(target.maps.map(async m=>({name:m.name,data:await readFile(m.path)})));
const engine=await createEngine(factory,files,await readFile(target.ligands[0].independent.path,'utf8'));
for(const ligand of target.ligands)for(const conformer of (ligand.id==='crystal'?['source','independent']:['independent'])){
 const input=await readFile(ligand[conformer].path,'utf8');const loadMs=engine.load(input);
 for(const [cap,runs] of [[16000,16],[64000,4],[256000,1],...(ligand.id==='crystal'?[[1000000,8]]:[])])for(let i=0;i<runs;i++){
  const key=[ligand.id,conformer,'global',cap,i].join(':');if(prior.some(r=>r.key===key))continue;
  engine.load(input);const result=engine.run(104729+i*13007,cap,1);
  const row={key,target:targetName,id:ligand.id,label:ligand.label,conformer,method:'global',cap,run:i,seed:104729+i*13007,input_sha256:ligand[conformer].sha256,ligand_load_ms:loadMs,...result};
  if(result.trace){row.trace_sha256=await sha(encode(result.trace));row.trace_values=result.trace.length;delete row.trace;}
  await appendFile(output,JSON.stringify(row)+'\n');prior.push(row);
 }
 // Real Vina local optimization of a plausible pose produced by short global
 // search. Charge seed search plus PDBQT reload and local optimization.
 for(let i=0;i<4;i++){
  const key=[ligand.id,conformer,'local',200,i].join(':');if(prior.some(r=>r.key===key&&r.source_reload_ms!==undefined))continue;
  const sourceReload=engine.load(input);const generated=engine.run(104729+i*13007,4000,1);let row={key,target:targetName,id:ligand.id,label:ligand.label,conformer,method:'local',cost_schema:2,source_reload_ms:sourceReload,steps:200,run:i,seed:104729+i*13007,input_sha256:ligand[conformer].sha256,generation_ms:generated.call_ms,generation_score:generated.score};
  if(generated.ok){
   // Vina's single-ligand parser accepts the ROOT/BRANCH ligand body, while its
   // pose writer adds MODEL/ENDMDL ensemble wrappers. Preserve all coordinates,
   // atom metadata and torsion records; strip only those output wrappers.
   const ligandPose=generated.pose.split('\n').filter(line=>!line.startsWith('MODEL ')&&line.trim()!=='ENDMDL').join('\n');
   row.pose_load_ms=engine.load(ligandPose);const t=performance.now();const refined=JSON.parse(engine.module.ccall('wr_refine','string',['number'],[200]));row={...row,...refined,call_ms:performance.now()-t};row.total_compute_ms=row.source_reload_ms+row.generation_ms+row.pose_load_ms+row.call_ms;
  }
  else row={...row,...generated};
  await appendFile(output,JSON.stringify(row)+'\n');prior.push(row);
 }
 console.log(targetName,ligand.id,conformer,prior.length,'rows',engine.memory(),'heap bytes');
}
await appendFile(folder+'science_initialization.jsonl',JSON.stringify({target:targetName,init_ms:engine.init_ms,heap_bytes:engine.memory(),scope:'One Node/WASM worker per target; not a browser runtime measurement.'})+'\n');
