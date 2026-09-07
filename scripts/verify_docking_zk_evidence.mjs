// Verify published public proofs and reject statement/tier substitutions.
import {createRequire} from 'node:module';
import {readFile} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const require=createRequire(path.resolve('research/docking-zk/package.json'));
const {groth16}=require('snarkjs');
const corpus=JSON.parse(await readFile('docs/evaluation/docking_pilot_2026-09-06/zk_public_proofs.json','utf8'));
async function valid(key,signals,proof){try{return await groth16.verify(key,signals,proof);}catch{return false;}}
let honest=0,negative=0;
for(const row of corpus.proofs){
 const key=corpus.verification_keys[row.n];
 assert(await valid(key,row.publicSignals,row.proof));honest++;
 for(const index of [0,2,27]){
  const changed=[...row.publicSignals];changed[index]=String(BigInt(changed[index])+1n);
  assert(!(await valid(key,changed,row.proof)));negative++;
 }
 const corrupt=structuredClone(row.proof);corrupt.pi_a[0]='0';
 assert(!(await valid(key,row.publicSignals,corrupt)));negative++;
 if(row.n===2){assert(!(await valid(corpus.verification_keys[8],row.publicSignals,row.proof)));negative++;}
}
console.log(JSON.stringify({honest_proofs_verified:honest,tamper_checks_rejected:negative,scope:'Public development proofs only; not production setup or proof of Vina.'}));
process.exit(0);
