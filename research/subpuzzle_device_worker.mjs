// Amendment 11 baseline: single hashcash puzzle and k-subpuzzle proof of work
// on the device, with the same synchronous pure-JS SHA-256 and 32-bit threshold
// as puzzle_device_worker.mjs, which stays unchanged for the first study.
// A k-subpuzzle solve needs k distinct nonces below the per-subpuzzle
// threshold, as deployed subpuzzle CAPTCHAs require.
import {sha256Fallback} from '/sha.mjs';
function hashOnce(buf,view,n){view.setUint32(16,n>>>0,true);view.setUint32(20,Math.floor(n/4294967296),true);return sha256Fallback(buf)}
function fresh(){const buf=new Uint8Array(24);buf.set(crypto.getRandomValues(new Uint8Array(16)));return [buf,new DataView(buf.buffer)]}
function spin(buf,view,ms){let n=0;const end=performance.now()+ms;while(performance.now()<end){hashOnce(buf,view,n);n++}return n}
onmessage=({data})=>{try{
 if(data.op==='rate'){
  const [buf,view]=fresh();spin(buf,view,1000);  // warm the JIT before measuring
  postMessage({rate:spin(buf,view,data.seconds*1000)/data.seconds});return;
 }
 if(data.op==='solve'){
  const k=data.k===undefined?1:data.k;if(!Number.isInteger(k)||k<1||k>1024)throw Error('k');
  const [buf,view]=fresh();const start=performance.now();let found=0;
  for(let n=0;;n++)if(parseInt(hashOnce(buf,view,n).slice(0,8),16)<data.threshold&&++found===k){
   postMessage({ms:performance.now()-start,hashes:n+1,threshold:data.threshold,k});return;
  }
 }
 throw Error('Unknown op');
}catch(e){postMessage({error:String(e)})}};
