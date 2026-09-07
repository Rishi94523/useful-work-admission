// Verify checked-in public evidence without setup or witness/proving artifacts.
import fs from 'node:fs';
import {groth16} from '../research/docking-zk/node_modules/snarkjs/build/main.cjs';
const base=new URL('../docs/evaluation/docking_ladder_2026-09-07/',import.meta.url);
const node=JSON.parse(fs.readFileSync(new URL('node_scaling.json',base))).rows;
const browser=JSON.parse(fs.readFileSync(new URL('browser_scaling.json',base))).rows;
let accepted=0,rejected=0;
for(const row of [...node,...browser]){
  const vk=node.find(r=>r.n===row.n).verification_key;
  if(!await groth16.verify(vk,row.publicSignals,row.proof))throw Error('Published proof rejected');
  accepted++;
  for(const index of [0,2,27]){
    const changed=[...row.publicSignals];changed[index]=(BigInt(changed[index])+1n).toString();
    if(await groth16.verify(vk,changed,row.proof))throw Error('Changed statement accepted');
    rejected++;
  }
}
const wrongTier=node.find(r=>r.n===8).verification_key;
if(await groth16.verify(wrongTier,node[0].publicSignals,node[0].proof))throw Error('Wrong tier accepted');
console.log(JSON.stringify({accepted,rejected,wrong_tier_rejected:true}));
process.exit(0);
