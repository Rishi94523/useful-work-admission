// One isolated Node prover per sample; timings have an external memory observer.
import {createRequire} from 'node:module';
import {readFile,writeFile,stat} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {makeContactReference} from '../research/docking-zk/contact_reference.mjs';
const require=createRequire(path.resolve('research/docking-zk/package.json'));
const {groth16}=require('snarkjs');
const [count,seed,target]=process.argv.slice(2);const n=Number(count);
const root=path.resolve(n<=8?'tmp/docking-pilot/zk':'tmp/docking-ladder');const base=path.join(root,String(n));
const data={...JSON.parse(await readFile(path.join(root,'input.json'),'utf8')),seed};
const search=await makeContactReference();const ordinary=[];let reference;
for(let i=0;i<12;i++){const begin=performance.now();reference=search(data,n);if(i>=2)ordinary.push(performance.now()-begin);}
const key=JSON.parse(await readFile(path.join(base,'verification_key.json'),'utf8'));
const started=performance.now();
const {proof,publicSignals}=await groth16.fullProve(data,path.join(base,`contact_${n}_js/contact_${n}.wasm`),path.join(base,'DEVELOPMENT_ONLY.zkey'),undefined,undefined,{singleThread:true});
const proveMs=performance.now()-started;
assert.deepEqual(publicSignals,[reference.bestScore,reference.bestIndex,seed,...data.ligand.flat(),...data.receptor.flat()].map(String));
const verifyTimes=[];let cold;
for(let i=0;i<22;i++){const begin=performance.now();assert(await groth16.verify(key,publicSignals,proof));const ms=performance.now()-begin;if(i===0)cold=ms;if(i>=2)verifyTimes.push(ms);}
const attacks=[];
for(const index of [0,2,27]){const signals=[...publicSignals];signals[index]=String(BigInt(signals[index])+1n);const rejected=!(await groth16.verify(key,signals,proof));assert(rejected);attacks.push({index,rejected});}
const row={n,seed,prove_ms:proveMs,plain_search_ms:ordinary,cold_verify_ms:cold,warm_verify_ms:verifyTimes,proof_json_bytes:Buffer.byteLength(JSON.stringify(proof)),public_field_elements:publicSignals.length,proving_key_bytes:(await stat(path.join(base,'DEVELOPMENT_ONLY.zkey'))).size,js_heap_snapshot_bytes:process.memoryUsage().heapUsed,attacks,proof,publicSignals,verification_key:key};
await writeFile(target,JSON.stringify(row,null,2)+'\n');
console.log(JSON.stringify({n,seed,prove_ms:proveMs,verify_ms:verifyTimes.reduce((a,b)=>a+b)/verifyTimes.length}));
process.exit(0);
