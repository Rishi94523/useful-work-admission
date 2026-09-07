// Each benchmark run gets a fresh worker/runtime. These timings include Vina setup.
import WEBINA from '/webina/vina.js';
self.onmessage = async ({ data }) => {
  let stdout = '', stderr = '';
  const begin = performance.now();
  try {
    let finishExit;
    const exited = new Promise(resolve => { finishExit = resolve; });
    const module = await WEBINA({
      noInitialRun: true,
      locateFile: name => '/webina/' + name,
      print: line => { stdout += line + '\n'; },
      printErr: line => { stderr += line + '\n'; },
      onExit: code => finishExit(code),
    });
    const initialized = performance.now();
    module.FS.writeFile('/receptor.pdbqt', data.receptor);
    module.FS.writeFile('/ligand.pdbqt', data.ligand);
    const args = ['--receptor','/receptor.pdbqt','--ligand','/ligand.pdbqt','--cpu','1','--seed',String(data.seed),'--out','/result.pdbqt'];
    for (const [key,value] of Object.entries(data.params)) args.push('--'+key,String(value));
    if (data.mode === 'score') args.push('--score_only');
    else if (data.mode === 'local') args.push('--local_only');
    else args.push('--exhaustiveness',String(data.exhaustiveness),'--max_evals',String(data.max_evals),'--num_modes','1');
    const started = performance.now();
    let rc = 0;
    try { rc = module.callMain(args); }
    catch (err) { if (err.name !== 'ExitStatus' || err.status !== 0) throw err; }
    rc = await exited;
    const ended = performance.now();
    let pose = null;
    try { pose = module.FS.readFile('/result.pdbqt',{encoding:'utf8'}); } catch {}
    self.postMessage({ ok:rc===0 && (data.mode==='score' || Boolean(pose)), rc, stdout, stderr, pose, module_init_ms:initialized-begin, call_main_ms:ended-started, worker_total_ms:ended-begin, wasm_memory_bytes:module.wasmMemory.buffer.byteLength });
  } catch (err) { self.postMessage({ok:false,error:String(err),stdout,stderr}); }
};
