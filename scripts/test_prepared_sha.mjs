import {sha256Fallback} from '../research/prepared_sha256.mjs';
import {createHash} from 'node:crypto';
import {readFile} from 'node:fs/promises';
for(const n of [0,1,3,55,56,63,64,65,1000,1048576]){
 const b=Uint8Array.from({length:n},(_,i)=>(i*31+17)&255);
 if(sha256Fallback(b)!==createHash('sha256').update(b).digest('hex'))throw Error('SHA mismatch '+n);
}
const artifact=await readFile('tmp/vina-prepared/artifacts/fa10.bin');
if(sha256Fallback(artifact)!==createHash('sha256').update(artifact).digest('hex'))throw Error('Artifact SHA mismatch');
console.log('10 boundary vectors and full prepared artifact match Node SHA-256');
