// Actual partial scoring, then fabrication/commitment; truth generated separately.
import fs from 'node:fs';import path from 'node:path';import {fileURLToPath} from 'node:url';
import {randomBytes,randomInt} from 'node:crypto';
import {score,commitJob,bundleCommitment,openings} from '../research/lightweight_docking.mjs';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..'),base=path.join(root,'tmp/docking-audit');
const meta=JSON.parse(fs.readFileSync(path.join(base,'assets/assets.json'))),raw=fs.readFileSync(path.join(base,'assets/maps.bin'));
const maps=new Int32Array(raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength)),n=4096,start=8192;
const ids=[meta.ligands[0].id,meta.ligands[16].id,meta.ligands[7].id,meta.ligands[23].id],results=[],transcripts=[];
for(const id of ids){
 const truth=score(meta,maps,id,start,n),A=truth.atoms;
 for(const mode of ['B','C','E'])for(const f of [.1,.25,.5,.75,.9,1]){
  const indices=[];for(let b=0;b<n;b+=64)for(let i=b;i<b+Math.max(1,Math.floor(64*f));i++)indices.push(i);
  const performed=new Set(indices),sample=score(meta,maps,id,start,n,{indices}),kernelMs=sample.kernel_ms;
  // High-scoring padding ensures each block's selected winner is a genuine
  // evaluated anchor, evading winner-only checks without querying all poses.
  const t=performance.now();let worst=indices[0];for(const i of indices)if(sample.scores[i]>sample.scores[worst])worst=i;
  for(let p=0;p<n;p++)if(!performed.has(p)){sample.scores[p]=sample.scores[worst];sample.values.set(sample.values.subarray(worst*A,(worst+1)*A),p*A);}
  const fabricateMs=performance.now()-t,binding=randomBytes(32).toString('hex'),job={id,start,count:n,mode};
  const state=await commitJob(binding,job,sample,mode),rootHash=await bundleCommitment(binding,[state]);
  const correct=[];for(let i=0;i<n;i++){
   let ok=sample.scores[i]===truth.scores[i];if(mode!=='B')for(let a=0;a<A&&ok;a++)ok=sample.values[i*A+a]===truth.values[i*A+a];correct.push(ok);
  }
  const fixed=new Set();let best=0;for(let i=1;i<n;i++)if(sample.scores[i]<sample.scores[best])best=i;fixed.add(best);
  if(mode==='E')for(let b=0;b<n;b+=64){let best=b;for(let i=b+1;i<b+64;i++)if(sample.scores[i]<sample.scores[best])best=i;fixed.add(best);}
  const fixedPass=[...fixed].every(i=>correct[i]);let passed=0;
  for(let trial=0;trial<10000;trial++){let ok=fixedPass;for(let q=0;q<32&&ok;q++)ok=correct[randomInt(n)];if(ok)passed++;}
  const draws=Array.from({length:32},()=>[0,randomInt(n)]),needed=[...fixed,...draws.map(x=>x[1])],ot=performance.now(),answers=[openings(state,needed)],openingMs=performance.now()-ot;
  const fractionCorrect=correct.filter(Boolean).length/n;
  results.push({id,mode,requested_fraction:f,computed_poses:indices.length,computed_fraction:indices.length/n,kernel_ms:kernelMs,full_kernel_ms:truth.kernel_ms,fabrication_ms:fabricateMs,commit_ms:state.commit_ms,opening_ms:openingMs,attacker_client_ms:kernelMs+fabricateMs+state.commit_ms+openingMs,correct_records:correct.filter(Boolean).length,unchecked_correct_guesses:correct.filter((ok,i)=>ok&&!performed.has(i)).length,selected_winners_correct:fixedPass,with_replacement_pass_probability:fixedPass?fractionCorrect**32:0,simulated_passes:passed,simulated_trials:10000});
  transcripts.push({attack:'partial_copy_worst',id,mode,fraction:f,jobs:[job],binding,headers:[state.header],root:rootHash,draws,answers});
 }
 // Scientific sabotage is different from saving work: hide just the true best
 // pose. Even block-winner checks inspect the newly claimed winners, not the
 // hidden optimum, so random checking is still unlikely to detect one bad row.
 for(const mode of ['B','C','E']){
  const forged={...truth,scores:truth.scores.slice(),values:truth.values.slice()};let best=0,worst=0;
  for(let i=1;i<n;i++){if(truth.scores[i]<truth.scores[best])best=i;if(truth.scores[i]>truth.scores[worst])worst=i;}
  forged.scores[best]=truth.scores[worst];forged.values.set(truth.values.subarray(worst*A,(worst+1)*A),best*A);
  const binding=randomBytes(32).toString('hex'),job={id,start,count:n,mode},state=await commitJob(binding,job,forged,mode),rootHash=await bundleCommitment(binding,[state]);
  let claimed=0;for(let i=1;i<n;i++)if(forged.scores[i]<forged.scores[claimed])claimed=i;
  const draws=Array.from({length:32},()=>[0,randomInt(n)]),needed=[claimed,...draws.map(x=>x[1])];
  if(mode==='E')for(let b=0;b<n;b+=64){let k=b;for(let i=b+1;i<b+64;i++)if(forged.scores[i]<forged.scores[k])k=i;needed.push(k);}
  transcripts.push({attack:'hide_true_minimum',id,mode,fraction:1,jobs:[job],binding,headers:[state.header],root:rootHash,draws,answers:[openings(state,needed)]});
  results.push({attack:'hide_true_minimum',id,mode,true_minimum:truth.scores[best],claimed_minimum:forged.scores[claimed],changed_records:1,pass_probability:(1-1/n)**32});
 }
 const coarse=score(meta,maps,id,start,n,{coarse:true});let scalarMatches=0,atomMatches=0;
 for(let i=0;i<n;i++){if(coarse.scores[i]===truth.scores[i])scalarMatches++;let good=true;for(let a=0;a<A&&good;a++)good=coarse.values[i*A+a]===truth.values[i*A+a];if(good)atomMatches++;}
 results.push({attack:'nearest_grid_corner',id,kernel_ms:coarse.kernel_ms,full_kernel_ms:truth.kernel_ms,scalar_matches:scalarMatches,atom_record_matches:atomMatches,total:n});
 // Recommit already computed answers under a fresh lease binding: replay of
 // the old Merkle proof fails, but the scientific cache remains usable.
 const binding=randomBytes(32).toString('hex'),job={id,start,count:n,mode:'C'},t=performance.now(),state=await commitJob(binding,job,truth,'C'),rootHash=await bundleCommitment(binding,[state]);
 const draws=Array.from({length:32},()=>[0,randomInt(n)]);let best=0;for(let i=1;i<n;i++)if(truth.scores[i]<truth.scores[best])best=i;
 transcripts.push({attack:'cached_science_fresh_commitment',id,mode:'C',fraction:0,jobs:[job],binding,headers:[state.header],root:rootHash,draws,answers:[openings(state,[best,...draws.map(x=>x[1])])]});
 results.push({attack:'cached_science_fresh_commitment',id,new_scientific_kernel_ms:0,client_recommit_and_open_ms:performance.now()-t});
 console.log(id,'attacks done');
}
fs.writeFileSync(path.join(base,'attack-transcripts.json'),JSON.stringify(transcripts));
// Heterogeneous bundle attack: finish the eight smallest ligands, compute only
// a real winner anchor for each remaining job, then fabricate their other rows.
const chosen=[...meta.ligands.slice(0,8),...meta.ligands.slice(16,24)].sort((a,b)=>a.heavy_atoms-b.heavy_atoms),costs=[];
for(let j=0;j<chosen.length;j++){
 const l=chosen[j],count=j<8?n:1,result=score(meta,maps,l.id,start,n,{fraction:count/n});
 costs.push({id:l.id,heavy_atoms:l.heavy_atoms,computed:count,kernel_ms:result.kernel_ms});
}
const correctCount=costs.reduce((s,r)=>s+r.computed,0),weightedCorrect=costs.reduce((s,r)=>s+r.computed*r.heavy_atoms,0),weightedTotal=costs.reduce((s,r)=>s+n*r.heavy_atoms,0);
results.push({attack:'heterogeneous_cheap_half_plus_winner_anchors',jobs:16,poses_per_job:n,actual_kernel_ms:costs.reduce((s,r)=>s+r.kernel_ms,0),costs,uniform_record_pass_probability:(correctCount/(16*n))**32,cost_weighted_record_pass_probability:(weightedCorrect/weightedTotal)**32,scope:'Actual selected-kernel timings; probabilities assume all other records incorrect and weights proportional to atoms. This row is not a full wire attack.'});
fs.writeFileSync(path.join(root,'docs/evaluation/docking_lightweight_2026-09-07/attacks.json'),JSON.stringify({scope:'Actual Node partial computation. Simulation samples committed correctness masks using 10000 trials; theoretical probabilities concern incorrect records, not universal CPU lower bounds. Prior truth generated independently and unavailable to partial attacker. Fresh-commit cache attack intentionally receives prior answers.',results},null,2)+'\n');
