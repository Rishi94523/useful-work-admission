// Same WASM module in Chrome and Node; synchronous search belongs in a worker.
export async function createEngine(factory,files,ligand){
 let currentLigand=ligand;
 const t=performance.now(),module=await factory({print:()=>{},printErr:()=>{}}),compiled=performance.now();
 module.FS.mkdir('/maps');
 for(const f of files)module.FS.writeFile('/maps/'+f.name,f.data);
 const reply=JSON.parse(module.ccall('wr_init','string',['string','string'],['/maps/fa10',ligand]));
 if(!reply.ok)throw Error(JSON.stringify(reply));
 for(const f of files)module.FS.unlink('/maps/'+f.name);
 return {module,init_ms:performance.now()-t,module_ms:compiled-t,
  load(text){if(text===currentLigand)return 0;const t=performance.now(),r=JSON.parse(module.ccall('wr_ligand','string',['string'],[text]));if(!r.ok)throw Error(JSON.stringify(r));currentLigand=text;return performance.now()-t;},
  run(seed,cap,e=1){const t=performance.now(),r=JSON.parse(module.ccall('wr_run','string',['number','number','number'],[seed,cap,e]));return {...r,call_ms:performance.now()-t};},
  memory(){return module.ccall('wr_memory','number',[],[]);}
 };
}
