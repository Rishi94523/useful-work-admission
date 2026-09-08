// Portable browser/Node deterministic molecular scoring and block commitments.
export const bytes = a => new Uint8Array(a.buffer, a.byteOffset, a.byteLength);
const enc=new TextEncoder();
export const hex=a=>Array.from(a,x=>x.toString(16).padStart(2,'0')).join('');
export const unhex=s=>Uint8Array.from(s.match(/../g)||[],x=>parseInt(x,16));
export const sha=async a=>new Uint8Array(await crypto.subtle.digest('SHA-256',a));
function concat(...as){const out=new Uint8Array(as.reduce((n,a)=>n+a.length,0));let p=0;for(const a of as){out.set(a,p);p+=a.length;}return out;}
export function b64(a){let s='';for(let i=0;i<a.length;i+=16384)s+=String.fromCharCode(...a.subarray(i,i+16384));return btoa(s);}

export function score(meta,maps,id,start,count,{records=true,fraction=1,coarse=false,indices=null}={}){
 const l=meta.ligands.find(x=>x.id===id), A=l.types.length, C=l.conformers_milli.length, R=meta.rotations.length;
 const total=C*R*512;if(start<0||count<1||start+count>total)throw Error('Bad bank range');
 const scores=new Int32Array(count),values=records?new Int32Array(count*A):null;
 const [T,Z,Y,X]=meta.map_shape,origin=meta.origin_micro,center=meta.center_milli;
 const upto=indices?indices.length:Math.floor(count*fraction),t0=performance.now();
 for(let it=0;it<upto;it++){
  const p=indices?indices[it]:it;
  if(!Number.isInteger(p)||p<0||p>=count)throw Error('Bad selected index');
  const ix=((start+p)*104729+l.offset)%total,tr=ix%512,ri=Math.floor(ix/512)%R,ci=Math.floor(ix/(512*R)),rot=meta.rotations[ri],conf=l.conformers_milli[ci];
  const shift=[tr%8*375-1312,Math.floor(tr/8)%8*375-1312,Math.floor(tr/64)%8*375-1312];let sum=0;
  for(let a=0;a<A;a++){
   const xyz=conf[a],cell=[0,0,0],f=[0,0,0];
   for(let k=0;k<3;k++){
    const pos=Math.floor((rot[k][0]*xyz[0]+rot[k][1]*xyz[1]+rot[k][2]*xyz[2]+500000)/1000000)+center[k]+shift[k];
    const delta=pos*1000-origin[k];cell[k]=Math.floor(delta/375000);f[k]=Math.floor(((delta-cell[k]*375000)*256+187500)/375000);
   }
   if(cell[0]<0||cell[1]<0||cell[2]<0||cell[0]>=X-1||cell[1]>=Y-1||cell[2]>=Z-1)throw Error('Out of box pose');
   let val=0;
   if(coarse)val=maps[((l.types[a]*Z+cell[2])*Y+cell[1])*X+cell[0]]*16777216;
   else for(let z=0;z<2;z++)for(let y=0;y<2;y++)for(let x=0;x<2;x++){
    const w=(x?f[0]:256-f[0])*(y?f[1]:256-f[1])*(z?f[2]:256-f[2]);
    val+=maps[((l.types[a]*Z+cell[2]+z)*Y+cell[1]+y)*X+cell[0]+x]*w;
   }
   val=Math.floor((val+8388608)/16777216);
   if(val>0)val=Math.floor((val*10000000+Math.floor((10000000+val)/2))/(10000000+val));
   if(!Number.isSafeInteger(val)||Math.abs(val)>2147483647)throw Error('Numeric bounds');
   if(records)values[p*A+a]=val;sum+=val;
  }
  if(Math.abs(sum)>2147483647)throw Error('Score bounds');scores[p]=sum;
 }
 return {scores,values,kernel_ms:performance.now()-t0,computed:upto,atoms:A};
}

export async function commitJob(binding,job,computed,mode='C',block=64){
 const begin=performance.now(),data=mode==='B'?computed.scores:computed.values;
 const width=mode==='B'?1:computed.atoms,chunks=[],levels=[[]];
 for(let i=0;i<job.count;i+=block){
  const raw=bytes(data.subarray(i*width,Math.min(i+block,job.count)*width));chunks.push(raw);
  levels[0].push(await sha(concat(enc.encode(JSON.stringify([binding,job.id,job.start,job.count,mode,block,i/block])+'\n'),raw)));
 }
 const actual=levels[0].length;let power=1;while(power<actual)power*=2;
 while(levels[0].length<power)levels[0].push(await sha(enc.encode('padding-v1')));
 while(levels.at(-1).length>1){const prev=levels.at(-1),next=[];for(let i=0;i<prev.length;i+=2)next.push(await sha(concat(new Uint8Array([1]),prev[i],prev[i+1])));levels.push(next);}
 const scoreHash=hex(await sha(bytes(computed.scores)));
 const header={...job,mode,block,root:hex(levels.at(-1)[0]),score_hash:scoreHash,scores:b64(bytes(computed.scores))};
 return {header,chunks,levels,commit_ms:performance.now()-begin};
}

export async function bundleCommitment(binding,states){return hex(await sha(enc.encode(JSON.stringify([binding,states.map(s=>{const h=s.header;return[h.id,h.start,h.count,h.mode,h.block,h.root,h.score_hash];})]))));}

export function openings(state,indices){
 const chosen=[...new Set(indices.map(i=>Math.floor(i/state.header.block)))].sort((a,b)=>a-b),out=[];
 for(const block of chosen){let i=block;const path=[];for(const level of state.levels.slice(0,-1)){path.push(hex(level[i^1]));i>>=1;}out.push({block,data:b64(state.chunks[block]),path});}
 return out;
}

export function winners(state){const h=state.header,s=Int32Array.from(atob(h.scores).match(/[\s\S]{4}/g)||[],x=>new DataView(Uint8Array.from(x,c=>c.charCodeAt(0)).buffer).getInt32(0,true));let best=0;for(let i=1;i<s.length;i++)if(s[i]<s[best])best=i;return best;}
