// Native Node/OpenSSL solver microbenchmark, NOT new browser/device evidence.
// Same expected total hashes, independent domain-separated subpuzzles.
import {createHash,randomBytes} from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
const out=path.resolve(process.argv[2]||'local-research/hashcash-batches-2026-09-24');
const root=path.resolve('local-research');
assert(out.startsWith(root+path.sep));
fs.mkdirSync(out,{recursive:false});
const trials=96,totalHashes=65536,counts=[1,16,64];
fs.writeFileSync(path.join(out,'manifest.json'),JSON.stringify({trials,totalHashes,counts,node:process.version,
  runner_sha256:createHash('sha256').update(fs.readFileSync(new URL(import.meta.url))).digest('hex'),
  design:'Rotate configurations per trial. Random challenge per solve, subpuzzle index bound in input. Fixed expected total hash count; not median matched.',
  limitations:'Single local Node process; native OpenSSL SHA-256. Not WASM, phone, cold-start or HTTP measurements.'},null,2));
const digest=b=>createHash('sha256').update(b).digest();
function solve(challenge,k){
 const b=Buffer.alloc(28);challenge.copy(b);const threshold=2**32*k/totalHashes;
 let hashes=0;const nonces=[];
 for(let i=0;i<k;i++){
  b.writeUInt32LE(i,16);
  for(let n=0;;n++){
   b.writeBigUInt64LE(BigInt(n),20);hashes++;
   if(digest(b).readUInt32BE(0)<threshold){nonces.push(n);break;}
  }
 }
 return {nonces,hashes};
}
function verify(challenge,k,nonces){
 if(nonces.length!==k)return false;
 const b=Buffer.alloc(28);challenge.copy(b);const threshold=2**32*k/totalHashes;
 return nonces.every((n,i)=>{b.writeUInt32LE(i,16);b.writeBigUInt64LE(BigInt(n),20);return digest(b).readUInt32BE(0)<threshold;});
}
solve(randomBytes(16),16); // warm before timed trials
const rows=[];
for(let i=0;i<trials;i++)for(let j=0;j<counts.length;j++){
 const k=counts[(i+j)%counts.length],challenge=randomBytes(16),start=performance.now();
 const s=solve(challenge,k),ms=performance.now()-start;
 assert(verify(challenge,k,s.nonces));assert(!verify(challenge,k,s.nonces.slice(1)));
 const begin=performance.now();for(let n=0;n<100;n++)assert(verify(challenge,k,s.nonces));
 rows.push({trial:i,subpuzzles:k,hashes:s.hashes,ms,verify_us:(performance.now()-begin)*10});
 if(j===0&&i%24===0)console.log('trial',i,'/',trials);
}
const quantile=(xs,p)=>{const a=[...xs].sort((a,b)=>a-b),x=p*(a.length-1),lo=Math.floor(x);return a[lo]+(a[Math.ceil(x)]-a[lo])*(x-lo);};
const summaries=counts.map(k=>{const r=rows.filter(x=>x.subpuzzles===k),ms=r.map(x=>x.ms),median=quantile(ms,.5);
 return {subpuzzles:k,n:r.length,median_ms:median,p95_ms:quantile(ms,.95),p99_ms:quantile(ms,.99),
 p95_over_median:quantile(ms,.95)/median,p99_over_median:quantile(ms,.99)/median,
 mean_hashes:r.reduce((s,x)=>s+x.hashes,0)/r.length,median_verify_us:quantile(r.map(x=>x.verify_us),.5)};});
fs.writeFileSync(path.join(out,'results.json'),JSON.stringify({summaries,rows},null,2));
console.log(JSON.stringify(summaries,null,2));
