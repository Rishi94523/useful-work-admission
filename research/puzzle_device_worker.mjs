// Hashcash baseline on the device: find a nonce such that the first 32 bits of
// SHA-256(challenge||nonce) fall below a threshold. A threshold rather than a
// whole number of leading zero bits lets difficulty be set continuously, so the
// median solve can be matched to the median docking unit instead of landing up
// to a factor of 1.4 away. Synchronous pure-JS SHA-256, as a browser
// proof-of-work solver runs.
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
  const [buf,view]=fresh();const start=performance.now();
  for(let n=0;;n++)if(parseInt(hashOnce(buf,view,n).slice(0,8),16)<data.threshold){postMessage({ms:performance.now()-start,hashes:n+1,threshold:data.threshold});return}
 }
 throw Error('Unknown op');
}catch(e){postMessage({error:String(e)})}};
