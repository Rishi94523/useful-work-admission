import {buildPoseidon} from 'circomlibjs';
export async function makeContactReference(){
 const poseidon=await buildPoseidon();
 return function search(data,n){
  let bestScore=1048575,bestIndex=0;
  for(let i=0;i<n;i++){
   const hash=poseidon.F.toObject(poseidon([BigInt(data.seed),BigInt(i)]));
   const shift=[0,1,2].map(k=>3*Number((hash>>BigInt(k*6))&63n)-94);
   let score=160000;
   for(const a of data.ligand)for(const b of data.receptor){
    const d2=a.reduce((sum,x,k)=>sum+(x+shift[k]-b[k])**2,0);
    score+=10*Math.max(0,900-d2)-Math.max(0,2500-d2);
   }
   if(score<bestScore){bestScore=score;bestIndex=i;}
  }
  return {bestScore,bestIndex};
 };
}
