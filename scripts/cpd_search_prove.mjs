import fs from 'node:fs';
import path from 'node:path';
import {performance} from 'node:perf_hooks';
import {groth16} from '../research/docking-zk/node_modules/snarkjs/build/main.cjs';
import {makeCPDReference} from '../research/docking-zk/cpd_reference.mjs';
const [count,seed,output]=process.argv.slice(2),n=Number(count),start=Number(seed);
const base=path.resolve('tmp/docking-ladder/cpd'),d=path.join(base,count);
const model=JSON.parse(fs.readFileSync(path.join(base,'model_exact.json'))),reference=makeCPDReference(model);
let plain=[];let expected;
for(let i=0;i<12;i++){const t=performance.now();expected=reference(n,start);if(i>1)plain.push(performance.now()-t);}
const begin=performance.now();
const {proof,publicSignals}=await groth16.fullProve({start:String(start)},path.join(d,'main_js/main.wasm'),path.join(d,'DEVELOPMENT_ONLY.zkey'),undefined,undefined,{singleThread:true});
const prove_ms=performance.now()-begin,vk=JSON.parse(fs.readFileSync(path.join(d,'verification_key.json')));
if(JSON.stringify(publicSignals)!==JSON.stringify([expected.score,expected.index,String(start)]))throw Error('Independent reference differs');
const verify=[];for(let i=0;i<22;i++){const t=performance.now();if(!await groth16.verify(vk,publicSignals,proof))throw Error('Invalid proof');verify.push(performance.now()-t);}
let rejected=0;for(let i=0;i<3;i++){const changed=[...publicSignals];changed[i]=(BigInt(changed[i])+1n).toString();if(await groth16.verify(vk,changed,proof))throw Error('Tamper passed');rejected++;}
fs.writeFileSync(output,JSON.stringify({n,start,model_sha256:model.model_sha256,plain_search_ms:plain,prove_ms,cold_verify_ms:verify[0],warm_verify_ms:verify.slice(2),proving_key_bytes:fs.statSync(path.join(d,'DEVELOPMENT_ONLY.zkey')).size,feasible_candidates:expected.feasible,proof,publicSignals,verification_key:vk,tampered_statements_rejected:rejected},null,2));
process.exit(0);
