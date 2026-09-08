// Portable commitment and whole-output checks. No score/global-minimum certificate.
const enc=new TextEncoder();
export const encode=x=>enc.encode(JSON.stringify(x));
export async function sha(x){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',typeof x==='string'?enc.encode(x):x))].map(b=>b.toString(16).padStart(2,'0')).join('');}
export function record(run){
  if(!run.ok||typeof run.pose!=='string'||run.pose.length>65536||!Number.isFinite(run.score))throw Error('Invalid search output');
  // Exact JSON score and PDBQT text are deterministic in the pinned WASM relation.
  if(!Array.isArray(run.trace)||run.trace.length>1000000||run.trace.some(x=>!Number.isFinite(x)))throw Error('Invalid molecular trace');
  return {score:run.score,pose:run.pose,trace:run.trace};
}
export async function commit(binding,units,records){
 if(units.length!==records.length||!units.length||units.length>1024)throw Error('Bad assignment size');
 const leaves=[];
 for(let i=0;i<units.length;i++)leaves.push(await sha(encode([units[i],records[i]])));
 return {binding,leaves,root:await sha(encode(['whole-run-v1',binding,leaves]))};
}
export async function validateCommit(binding,units,c){
 if(c.binding!==binding||c.leaves.length!==units.length||c.leaves.some(h=>typeof h!=='string'||!/^[a-f0-9]{64}$/.test(h))||c.root!==await sha(encode(['whole-run-v1',binding,c.leaves])))throw Error('Bad commitment');
}
export async function audit(binding,units,c,draws,openings,replay){
 await validateCommit(binding,units,c);
 if(new Set(draws).size!==draws.length||draws.some(i=>!Number.isInteger(i)||i<0||i>=units.length)||openings.length!==draws.length)throw Error('Bad challenge');
 let replayMs=0;
 for(let j=0;j<draws.length;j++){
  const i=draws[j],o=openings[j];
  if(await sha(encode([units[i],o]))!==c.leaves[i])return {accepted:false,reason:'opening',replay_ms:replayMs};
  const t=performance.now(),expected=record(await replay(units[i]));replayMs+=performance.now()-t;
  if(JSON.stringify(expected)!==JSON.stringify(o))return {accepted:false,reason:'replay',replay_ms:replayMs};
 }
 return {accepted:true,replay_ms:replayMs};
}
export function sample(n,q){
 if(!Number.isInteger(q)||q<1||q>n)throw Error('Bad audit budget');
 const result=new Set(),b=new Uint32Array(1),limit=2**32-(2**32%n);
 while(result.size<q){crypto.getRandomValues(b);if(b[0]<limit)result.add(b[0]%n);}
 return [...result].sort((a,b)=>a-b);
}
export function passProbability(correct,n,q){let p=1;for(let i=0;i<q;i++)p*=Math.max(0,correct-i)/(n-i);return p;}
