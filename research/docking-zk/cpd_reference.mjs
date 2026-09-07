// Exact BigInt reference; cannot lose WCSP costs above Number.MAX_SAFE_INTEGER.
export function makeCPDReference(model){
  const width=model.positions,upper=BigInt(model.upper),constant=BigInt(model.constant);
  const linear=model.linear.map(BigInt),pairs=model.pairs.map(r=>r.map(BigInt));
  return (n,start)=>{
    let best=upper,index=0,feasible=0;
    for(let c=0;c<n;c++){
      const id=(start+65537*c)%(2**width),bits=Array.from({length:width},(_,i)=>BigInt((id>>i)&1));
      let value=constant;
      for(let i=0;i<width;i++){
        value+=linear[i]*bits[i];
        for(let j=i+1;j<width;j++)value+=pairs[i][j]*bits[i]*bits[j];
      }
      if(value<upper)feasible++;
      if(value<best){best=value;index=c;}
    }
    return {score:best.toString(),index:String(index),feasible};
  };
}
