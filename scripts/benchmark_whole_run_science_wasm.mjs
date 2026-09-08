import {readFile,writeFile,appendFile} from 'node:fs/promises';
import path from 'node:path';
import factory from '../tmp/docking-runs/whole_run.mjs';
import {createEngine} from '../research/whole_run_engine.mjs';
import {sha,encode} from '../research/whole_run_protocol.mjs';
const out=path.resolve('docs/evaluation/docking_whole_runs_2026-09-08'),plan=JSON.parse(await readFile(path.join(out,'plan.json'),'utf8'));
const control=process.argv.includes('--control');
const file=path.resolve('tmp/docking-runs/'+(control?'wasm_control':'wasm_science')+'.jsonl');
let rows=[];try{rows=(await readFile(file,'utf8')).trim().split('\n').filter(Boolean).map(JSON.parse);}catch(e){if(e.code!=='ENOENT')throw e;}
const files=await Promise.all(plan.maps.map(async m=>({name:m.name,data:await readFile(m.path)}))),ligands=control?plan.ligands.slice(-1):plan.ligands;
const engine=await createEngine(factory,files,await readFile(ligands[0].path,'utf8'));
for(const l of ligands){
 const load=engine.load(await readFile(l.path,'utf8'));
 for(const cap of (control?[0]:[4000,16000]))for(let i=0;i<(control?1:32);i++){
  if(rows.some(r=>r.id===l.id&&r.cap===cap&&r.run===i))continue;
  const r=engine.run(plan.seeds[i],cap,control?8:1);if(!r.ok)throw Error(JSON.stringify(r));
  const row={id:l.id,label:l.label,seed:plan.seeds[i],cap,run:i,exhaustiveness:control?8:1,ligand_load_ms:load,...r,trace_hash:await sha(encode(r.trace)),trace_values:r.trace.length};delete row.trace;
  rows.push(row);await appendFile(file,JSON.stringify(row)+'\n');
 }
 console.log(l.id,rows.length,rows.at(-1).score);
}
await writeFile(path.join(out,control?'wasm_control.json':'wasm_science.json'),JSON.stringify({scope:'Actual Node execution of the same canonical WASM engine as the browser. Trace hash retained; science comparison uses final poses/scores. Not native replay.',init_ms:engine.init_ms,rows},null,2)+'\n');
