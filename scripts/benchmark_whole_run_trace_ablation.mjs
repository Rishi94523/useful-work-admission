import {readFile,writeFile} from 'node:fs/promises';
import yes from '../tmp/docking-runs/whole_run.mjs';
import no from '../tmp/docking-runs/whole_run_no_trace.mjs';
import {createEngine} from '../research/whole_run_engine.mjs';
const out='docs/evaluation/docking_whole_runs_2026-09-08/',plan=JSON.parse(await readFile(out+'plan.json','utf8'));
const files=await Promise.all(plan.maps.map(async m=>({name:m.name,data:await readFile(m.path)}))),text=await readFile(plan.ligands[0].path,'utf8');
const a=await createEngine(yes,files,text),b=await createEngine(no,files,text),rows=[];
for(const cap of [4000,16000])for(let i=0;i<32;i++){
 const seed=plan.seeds[i];let x,y;if(i%2){y=b.run(seed,cap);x=a.run(seed,cap);}else{x=a.run(seed,cap);y=b.run(seed,cap);}
 if(!x.ok||!y.ok||x.score!==y.score||x.pose!==y.pose)throw Error('Trace instrumentation changed scientific result');
 rows.push({seed,cap,trace_search_ms:x.search_ms,plain_search_ms:y.search_ms,trace_call_ms:x.call_ms,plain_call_ms:y.call_ms,trace_values:x.trace.length,pose_equal:true});
}
await writeFile(out+'trace_ablation.json',JSON.stringify({scope:'Paired alternating-order warm Node/WASM runs, same ligand and source except natural trace collection. Actual SHA commitment is measured separately in browser tiers. No browser ablation or independent hardware.',rows},null,2)+'\n');console.log('64 paired trace-ablation checks complete');
