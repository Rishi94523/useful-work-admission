// Whole-run attacks execute selected science; the separate replay process holds truth.
import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import factory from '../tmp/docking-runs/whole_run.mjs';
import {createEngine} from '../research/whole_run_engine.mjs';
import * as p from '../research/whole_run_protocol.mjs';
const out=path.resolve('docs/evaluation/docking_whole_runs_2026-09-08'),plan=JSON.parse(await readFile(path.join(out,'plan.json'),'utf8'));
const inputs=new Map(await Promise.all(plan.ligands.map(async l=>[l.id,await readFile(l.path,'utf8')])));
const files=await Promise.all(plan.maps.map(async m=>({name:m.name,data:await readFile(m.path)})));
const engine=await createEngine(factory,files,inputs.get(plan.ligands[0].id));
let ligandLoadMs=0;
function replay(u){ligandLoadMs+=engine.load(inputs.get(u.ligand));return engine.run(u.seed,u.cap);}
const result={scope:'Same pinned WASM replay. Actual attacks execute chosen units and commit outputs before CSPRNG samples. Empirical conditional-mask trials are separately labelled. Warm replay excludes per-ligand preparation; full costs include it.',honest:[],attacks:[],tamper:[]};
const browser=JSON.parse(await readFile(path.join(out,'browser.json'),'utf8'));
// One complete committed browser bundle per tier; other repetitions validate determinism.
for(const row of browser.rows.filter(r=>r.rep===0)){
 for(const q of [1,4,8].filter(q=>q<=row.units.length)){
  ligandLoadMs=0;const draws=p.sample(row.units.length,q),t=performance.now();
  const checked=await p.audit(row.commitment.binding,row.units,row.commitment,draws,draws.map(i=>row.records[i]),replay);
  result.honest.push({ligands:row.ligands,runs:row.runs,cap:row.cap,q,accepted:checked.accepted,reason:checked.reason,draws,total_ms:performance.now()-t,ligand_load_ms:ligandLoadMs,replay_including_load_ms:checked.replay_ms,replay_warm_ms:checked.replay_ms-ligandLoadMs,opening_bytes:p.encode(draws.map(i=>row.records[i])).length,wasm_memory_bytes:engine.memory()});
  console.log('honest',row.ligands,row.runs,row.cap,q,checked.accepted);
 }
 await writeFile(path.join(out,'audits.json'),JSON.stringify(result,null,2)+'\n');
}
const base=browser.rows.find(r=>r.ligands===4&&r.runs===16&&r.cap===4000&&r.rep===0),n=base.units.length;
// Retained truth from honest browser is used only by the evaluation harness to
// measure correctness masks. The partial attack below reads only chosen outputs.
for(const f of [.1,.25,.5,.75,.9,1]){
 const count=Math.max(1,Math.floor(n*f)),indices=[...Array(n).keys()].sort((a,b)=>(a%16)-(b%16)||a-b).slice(0,count),computed=new Map();
 let molecularMs=0;ligandLoadMs=0;const start=performance.now();
 for(const i of [...indices].sort((a,b)=>a-b)){const r=replay(base.units[i]);molecularMs+=r.search_ms;computed.set(i,p.record(r));}
 const records=base.units.map((u,i)=>computed.get(i)||computed.get(indices.find(j=>base.units[j].ligand===u.ligand))||computed.values().next().value);
 const c=await p.commit('partial-'+f,base.units,records),clientMs=performance.now()-start,prep=ligandLoadMs;
 const mask=records.map((r,i)=>JSON.stringify(r)===JSON.stringify(base.records[i])),correct=mask.filter(Boolean).length;
 const analytical=[],actual=[];
 for(const q of [1,4,8,16]){
  let passes=0;for(let trial=0;trial<10000;trial++)if(p.sample(n,q).every(i=>mask[i]))passes++;
  analytical.push({q,probability:p.passProbability(correct,n,q),simulated_passes:passes,trials:10000});
  const draws=p.sample(n,q);ligandLoadMs=0;const t=performance.now();const check=await p.audit(c.binding,base.units,c,draws,draws.map(i=>records[i]),replay);
  actual.push({q,draws,...check,total_ms:performance.now()-t,ligand_load_ms:ligandLoadMs});
 }
 result.attacks.push({kind:'partial-copy',requested_fraction:f,executed:count,total:n,correct_records:correct,molecular_ms:molecularMs,client_ms:clientMs,ligand_load_ms:prep,analytical,actual});
 console.log('partial',f,correct,actual.map(x=>x.accepted));await writeFile(path.join(out,'audits.json'),JSON.stringify(result,null,2)+'\n');
}
// Recommit cached scientific values; admitted under the new lease by design.
const t=performance.now(),cached=await p.commit('new-credit-binding',base.units,base.records),commitMs=performance.now()-t;
const draws=p.sample(n,8);ligandLoadMs=0;const cacheCheck=await p.audit(cached.binding,base.units,cached,draws,draws.map(i=>base.records[i]),replay);
result.attacks.push({kind:'precomputed-scientific-credit',new_molecular_ms:0,client_commit_ms:commitMs,...cacheCheck});
// Later top-one replay can repair a falsely promoted result; it cannot discover
// a true best result deliberately hidden by a false high score.
result.scientific_repair=[];
for(const kind of ['false-top','hidden-best']){
 const records=structuredClone(base.records),target=kind==='false-top'?0:base.records.reduce((best,r,i)=>r.score<base.records[best].score?i:best,0);
 records[target].score=kind==='false-top'?-1000:1000;
 const c=await p.commit('science-'+kind,base.units,records),draws=p.sample(n,8),admission=await p.audit(c.binding,base.units,c,draws,draws.map(i=>records[i]),replay);
 let repairs=0;const start=performance.now(),selected=[];
 for(const id of new Set(base.units.map(u=>u.ligand))){const indices=base.units.map((u,i)=>u.ligand===id?i:-1).filter(i=>i>=0),best=indices.reduce((b,i)=>records[i].score<records[b].score?i:b,indices[0]);selected.push(best);const checked=p.record(replay(base.units[best]));if(JSON.stringify(checked)!==JSON.stringify(records[best])){records[best]=checked;repairs++;}}
 result.scientific_repair.push({kind,target,admission_accepted:admission.accepted,admission_draws:draws,later_selected:selected,later_replay_ms:performance.now()-start,repaired_records:repairs,hidden_or_false_record_remaining:JSON.stringify(records[target])!==JSON.stringify(base.records[target]),scope:'Actual replay of each ligand reported top-one. Does not certify the true global minimum.'});
}
// A lower search budget cannot substitute solely by being a valid pose.
for(const cap of [100,1000]){
 const records=[];let cost=0;for(const u of base.units){const r=replay({...u,cap});cost+=r.search_ms;records.push(p.record(r));}
 const mask=records.map((r,i)=>JSON.stringify(r)===JSON.stringify(base.records[i])),c=await p.commit('short-budget-'+cap,base.units,records),draws=p.sample(n,8);
 const checked=await p.audit(c.binding,base.units,c,draws,draws.map(i=>records[i]),replay);
 result.attacks.push({kind:'short-budget',cap,assigned_cap:4000,molecular_ms:cost,correct_records:mask.filter(Boolean).length,total:n,...checked});
}
// Malformed/substitution cases must fail before science or on commitment check.
for(const kind of ['binding','leaf','root','opening','seed','duplicate-draw']){
 const c=structuredClone(base.commitment),units=structuredClone(base.units),draws=[0],opens=[structuredClone(base.records[0])];
 if(kind==='binding')c.binding='wrong';if(kind==='leaf')c.leaves[0]='0'.repeat(64);if(kind==='root')c.root='0'.repeat(64);if(kind==='opening')opens[0].score-=100;if(kind==='seed')units[0].seed++;
 if(kind==='duplicate-draw'){draws.push(0);opens.push(opens[0]);}
 let rejected=false;try{rejected=!(await p.audit(base.commitment.binding,units,c,draws,opens,replay)).accepted;}catch{rejected=true;}
 result.tamper.push({kind,rejected});
}
await writeFile(path.join(out,'audits.json'),JSON.stringify(result,null,2)+'\n');
