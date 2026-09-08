// Local benchmark client; IPC actions separate commit from server challenge.
import fs from 'node:fs';import readline from 'node:readline';
import {score,commitJob,bundleCommitment,openings} from '../research/lightweight_docking.mjs';
const base=new URL('../tmp/docking-audit/assets/',import.meta.url),meta=JSON.parse(fs.readFileSync(new URL('assets.json',base))),raw=fs.readFileSync(new URL('maps.bin',base));
const maps=new Int32Array(raw.buffer.slice(raw.byteOffset,raw.byteOffset+raw.byteLength));let states;
for await(const line of readline.createInterface({input:process.stdin})){
 try{
  const request=JSON.parse(line);
  if(request.action==='commit'){
   states=[];let kernelMs=0,commitMs=0;
   for(const job of request.jobs){const values=score(meta,maps,job.id,job.start,job.count);kernelMs+=values.kernel_ms;const state=await commitJob(request.binding,job,values,job.mode);commitMs+=state.commit_ms;states.push(state);}
   console.log(JSON.stringify({headers:states.map(s=>s.header),root:await bundleCommitment(request.binding,states),kernel_ms:kernelMs,commit_ms:commitMs}));
  }else if(request.action==='open')console.log(JSON.stringify({answers:states.map((s,j)=>openings(s,request.indices[j]))}));
  else if(request.action==='quit')break;else throw Error('Bad IPC action');
 }catch(error){console.log(JSON.stringify({error:String(error)}));}
}
