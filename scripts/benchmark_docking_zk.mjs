// Actual Groth16 calibration on a reduced contact-search circuit, not Vina.
import {createRequire} from 'node:module';
import {readFile,writeFile,stat} from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
const root=path.resolve('.');
const require=createRequire(path.join(root,'research/docking-zk/package.json'));
const snarkjs=require('snarkjs');
const {buildPoseidon}=require('circomlibjs');
const dir=path.join(root,'tmp/docking-pilot/zk');
const poseidon=await buildPoseidon();
const input=JSON.parse(await readFile(path.join(dir,'input.json'),'utf8'));
function search(data,n) {
  let bestScore=1048575,bestIndex=0;const candidates=[];
  for(let i=0;i<n;i++){
    const hash=poseidon.F.toObject(poseidon([BigInt(data.seed),BigInt(i)]));
    const shift=[0,1,2].map(k=>3*Number((hash>>BigInt(k*6))&63n)-94);
    let score=160000;
    for(const a of data.ligand)for(const b of data.receptor){
      const d2=a.reduce((sum,x,k)=>sum+(x+shift[k]-b[k])**2,0);
      score+=10*Math.max(0,900-d2)-Math.max(0,2500-d2);
    }
    if(score<bestScore){bestScore=score;bestIndex=i;}
    candidates.push({shift,score});
  }
  return {bestScore,bestIndex,candidates};
}
async function verify(vk,signals,proof){try{return await snarkjs.groth16.verify(vk,signals,proof);}catch{return false;}}
const evidence={scope:'Groth16 calibration using single-party DEVELOPMENT_ONLY setup with random phase-one and phase-two contributions. Integer contact potential, 8 ligand and 8 receptor atoms, translations only. This is not Vina, scientific docking validation, proof of physical CPU time or production cryptographic security.',node:process.version,prover_options:{singleThread:true},rows:[],attacks:[]};
const proofs=new Map();
for(const n of [2,8]){
  const base=path.join(dir,String(n));
  const vk=JSON.parse(await readFile(path.join(base,'verification_key.json'),'utf8'));
  for(const seed of ['20260906','20260907']){
    const data={...input,seed};
    const referenceTimes=[];let reference;
    for(let repeat=0;repeat<12;repeat++){const t=performance.now();reference=search(data,n);if(repeat>1)referenceTimes.push(performance.now()-t);}
    const start=performance.now();
    const {proof,publicSignals}=await snarkjs.groth16.fullProve(data,path.join(base,`contact_${n}_js/contact_${n}.wasm`),path.join(base,'DEVELOPMENT_ONLY.zkey'),undefined,undefined,{singleThread:true});
    const proveMs=performance.now()-start;
    const expected=[reference.bestScore,reference.bestIndex,data.seed,...data.ligand.flat(),...data.receptor.flat()].map(String);
    assert.deepEqual(publicSignals,expected,'Circuit must match independent JS search and all public inputs');
    const checkTimes=[];
    for(let repeat=0;repeat<12;repeat++){const t=performance.now();assert(await verify(vk,publicSignals,proof));if(repeat>1)checkTimes.push(performance.now()-t);}
    for(const [label,index] of [['changed_best_score',0],['changed_seed',2],['changed_receptor_coordinate',27]]){
      const altered=[...publicSignals];altered[index]=String(BigInt(altered[index])+1n);
      evidence.attacks.push({n,seed,test:label,rejected:!(await verify(vk,altered,proof))});
    }
    const forged=structuredClone(proof);forged.pi_a[0]='0';
    evidence.attacks.push({n,seed,test:'corrupted_proof',rejected:!(await verify(vk,publicSignals,forged))});
    const row={n,seed,prove_ms:proveMs,verify_ms:checkTimes,plain_reference_ms:referenceTimes,public_field_elements:publicSignals.length,proof_json_bytes:Buffer.byteLength(JSON.stringify(proof)),key_bytes:(await stat(path.join(base,'DEVELOPMENT_ONLY.zkey'))).size,witness_wasm_bytes:(await stat(path.join(base,`contact_${n}_js/contact_${n}.wasm`))).size,result:reference,node_rss_snapshot_bytes:process.memoryUsage().rss};
    evidence.rows.push(row);proofs.set(n,{vk,proof,publicSignals});
    await writeFile(path.join(base,`proof_${seed}.json`),JSON.stringify({proof,publicSignals},null,2)+'\n');
    console.log(JSON.stringify({n,seed,prove_ms:proveMs,verify_mean_ms:checkTimes.reduce((a,b)=>a+b)/checkTimes.length,plain_mean_ms:referenceTimes.reduce((a,b)=>a+b)/referenceTimes.length,key_bytes:row.key_bytes}));
    await writeFile('docs/evaluation/docking_pilot_2026-09-06/zk_native.json',JSON.stringify(evidence,null,2)+'\n');
  }
}
const low=proofs.get(2),high=proofs.get(8);
evidence.attacks.push({test:'two_candidate_proof_against_eight_candidate_key',rejected:!(await verify(high.vk,low.publicSignals,low.proof))});
assert(evidence.attacks.every(x=>x.rejected));
await writeFile('docs/evaluation/docking_pilot_2026-09-06/zk_native.json',JSON.stringify(evidence,null,2)+'\n');
process.exit(0);
