// Archive-backed protocol diagnostics, not new molecular executions or a proof.
import {readFile,writeFile} from 'node:fs/promises';
import {gzipSync} from 'node:zlib';
import assert from 'node:assert/strict';
import * as p from '../research/whole_run_protocol.mjs';
const corpus=JSON.parse(await readFile('docs/evaluation/docking_whole_runs_2026-09-08/browser.json','utf8'));
const high=corpus.rows.find(r=>r.cap===16000&&r.ligands===16&&r.runs===16&&r.rep===0),low=corpus.rows.find(r=>r.cap===4000&&r.ligands===16&&r.runs===16&&r.rep===0);
let prefixes=0,exact=0,sameFinal=0;const distinct=new Set();
for(let i=0;i<high.records.length;i++){
 const a=low.records[i],b=high.records[i];if(a.trace.every((v,j)=>v===b.trace[j]))prefixes++;
 if(JSON.stringify(a)===JSON.stringify(b))exact++;
 if(a.score===b.score&&a.pose===b.pose)sameFinal++;
 distinct.add(await p.sha(p.encode(b.trace)));
}
const records=high.records,raw=p.encode(records),gz=gzipSync(raw),binary=[];
// Exact IEEE754 encoding of the trace; no lossy energy quantization.
for(const r of records){const buf=Buffer.alloc(r.trace.length*8);r.trace.forEach((v,i)=>buf.writeDoubleLE(v,i*8));const restored=Array.from({length:r.trace.length},(_,i)=>buf.readDoubleLE(i*8));assert.deepEqual(restored,r.trace);binary.push({score:r.score,pose:r.pose,trace:buf.toString('base64')});}
const binaryJson=p.encode(binary),cases=[];
for(const kind of ['zero-trace','copied-other-seed','short-prefix-padding']){
 const forged=records.map((r,i)=>kind==='zero-trace'?{...r,trace:r.trace.map(()=>0)}:kind==='copied-other-seed'?records[(i+1)%records.length]:{...low.records[i],trace:[...low.records[i].trace,...Array(Math.max(0,r.trace.length-low.records[i].trace.length)).fill(0)]});
 const c=await p.commit('new-binding',high.units,forged);await p.validateCommit('new-binding',high.units,c);
 const correct=forged.filter((r,i)=>JSON.stringify(r)===JSON.stringify(records[i])).length;
 const checked=await p.audit('new-binding',high.units,c,[0],[forged[0]],()=>({ok:true,...records[0]}));
 cases.push({kind,self_consistent_commitment:true,correct_records:correct,total:records.length,archive_oracle_rejected:!checked.accepted});
}
const field=2305843009213693951n,alpha=1234567n;
const sum=xs=>xs.reduce((s,x,i)=>(s+BigInt(x)*(i===0?1n:alpha))%field,0n);
// A public linear checksum can be preserved by compensating alterations.
const original=[3n,7n],forged=[(3n+alpha)%field,6n];assert.equal(sum(original),sum(forged));
const output={scope:'Compression and counterexamples use archived actual Vina records. No new Vina timing, no general cryptographic construction, no novelty claim.',records:records.length,short_run_prefix_matches:prefixes,exact_short_full_records:exact,short_final_pose_score_matches:sameFinal,distinct_cross_seed_trace_hashes:distinct.size,json_bytes:raw.length,json_gzip_bytes:gz.length,base64_binary_trace_json_bytes:binaryJson.length,base64_binary_trace_gzip_bytes:gzipSync(binaryJson).length,lossless_roundtrips:records.length,attacks:cases,public_linear_checksum_collision:{field:field.toString(),alpha:alpha.toString(),original:original.map(String),forged:forged.map(String),checksum:sum(original).toString()},block_splicing_model:[16,64,256].map(blocks=>({blocks,q:4,invalid_boundaries:1,skip_fraction:(blocks-1)/blocks,pass_probability:1-4/blocks,scope:'Theoretical checkpoint-splicing counterexample: cached valid suffix with one invalid transition from seeded prefix. Assumes local checks trust unverified committed entry state. Not an implemented Vina checkpoint attack.'}))};
await writeFile('docs/evaluation/adaptive_docking_2026-09-08/fingerprints.json',JSON.stringify(output,null,2)+'\n');console.log(output);
