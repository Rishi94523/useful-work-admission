// Follow-up: scientific quality of the actual cap4k low admission tier.
// Uses the equivalence-tested shared-table engine; no production work credits.
import {readFile,appendFile} from 'node:fs/promises';
import {spawnSync} from 'node:child_process';
import factory from '../tmp/docking-runs/whole_run_type_cache.mjs';
import {createEngine} from '../research/whole_run_engine.mjs';
import {sha,encode} from '../research/whole_run_protocol.mjs';
const folder='docs/evaluation/adaptive_docking_2026-09-08/';
const targets=JSON.parse(await readFile(folder+'science_inputs.json','utf8')).targets.filter(t=>!t.preparation_failed);
const hash=JSON.parse(await readFile(folder+'build_wasm_type_cache.json','utf8')).wasm_sha256;
if(!process.argv[2]){
 for(const t of targets){const p=spawnSync(process.execPath,[process.argv[1],t.target],{stdio:'inherit'});if(p.status)throw Error('Low-tier science worker failed');}
}else{
 const target=targets.find(t=>t.target===process.argv[2]),dest=folder+'low_science_'+target.target+'.jsonl';let rows=[];
 try{rows=(await readFile(dest,'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);}catch(e){if(e.code!=='ENOENT')throw e;}
 if(rows.length===288){console.log(target.target,'low-tier science complete');process.exit(0);}
 const files=await Promise.all(target.maps.map(async m=>({name:m.name,data:await readFile(m.path)})));
 const engine=await createEngine(factory,files,await readFile(target.ligands[0].independent.path,'utf8'));
 for(const l of target.ligands)for(const conf of (l.id==='crystal'?['source','independent']:['independent'])){
  const load=engine.load(await readFile(l[conf].path,'utf8'));
  for(let i=0;i<16;i++){
   const key=[l.id,conf,'global',4000,i].join(':');if(rows.some(r=>r.key===key))continue;
   const r=engine.run(104729+13007*i,4000),row={key,target:target.target,id:l.id,label:l.label,conformer:conf,method:'global',cap:4000,run:i,seed:104729+13007*i,input_sha256:l[conf].sha256,engine_sha256:hash,ligand_load_ms:load,...r};
   if(row.trace){row.trace_sha256=await sha(encode(row.trace));row.trace_values=row.trace.length;delete row.trace;}
   await appendFile(dest,JSON.stringify(row)+'\n');rows.push(row);
  }
 }
 console.log(target.target,rows.length,'low-tier records');
}
