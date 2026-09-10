"""Exact task-boundary split/merge against same-build monolithic Vina and CLI."""
import hashlib,json,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_tasks_2026-09-10';BASE=ROOT/'tmp/vina-tasks'
OLD=ROOT/'docs/evaluation/adaptive_docking_2026-09-08'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def start(t,ligand):
 p=subprocess.Popen([str(BASE/'vina_tasks.exe'),str(ROOT/t['receptor']),str(ROOT/Path(t['maps'][0]['path']).parent/'fa10'),str(ligand),*map(str,t['center'])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 line=p.stdout.readline()
 if line.strip()!='READY':raise RuntimeError(line+p.stderr.read())
 return p
def call(p,mode,index,e,cap,folder,pose):
 folder.mkdir(parents=True,exist_ok=True);p.stdin.write(f'{mode} {index} 104729 {e} {cap} 9 {folder.as_posix()} {pose.as_posix()}\n');p.stdin.flush();line=p.stdout.readline()
 if not line:raise RuntimeError(p.stderr.read())
 return json.loads(line)
def stop(p):
 if p.poll() is None:p.stdin.write('QUIT\n');p.stdin.flush();p.communicate(timeout=15)
if __name__=='__main__':
 results=[]
 for t in json.loads((OLD/'science_inputs.json').read_text())['targets']:
  if t.get('preparation_failed'):continue
  ligand=ROOT/next(l for l in t['ligands'] if l['id']=='crystal')['source']['path'];folder=BASE/('equivalence_'+t['target']);folder.mkdir(exist_ok=True)
  p=start(t,ligand)
  try:
   for cap in [16000,0]:
    prefix=folder/str(cap);mono=call(p,0,0,4,cap,prefix/'mono',prefix/'mono.pdbqt');units=[]
    for i in range(4):units.append(call(p,1,i,4,cap,prefix/'split',prefix/'unused.pdbqt'))
    merged=call(p,2,0,4,cap,prefix/'split',prefix/'split.pdbqt')
    matches=[digest(prefix/'mono'/f'{i}.task')==digest(prefix/'split'/f'{i}.task') and digest(prefix/'mono'/f'{i}.task.trace')==digest(prefix/'split'/f'{i}.task.trace') for i in range(4)]
    pose_equal=(prefix/'mono.pdbqt').read_bytes()==(prefix/'split.pdbqt').read_bytes()
    assert all(matches) and pose_equal and mono['score']==merged['score'],'Task decomposition changed outputs'
    row={'target':t['target'],'cap':cap,'runs':4,'pool':9,'input_sha256':digest(ligand),'task_trace_exact':matches,'final_pose_exact':pose_equal,'monolithic':mono,'split_calls':units,'finalizer':merged,'tasks':[json.loads((prefix/'split'/f'{i}.task.json').read_text()) for i in range(4)]}
    # A separate official binary, with maps computed from the same receptor/ligand/box.
    dest=prefix/'stock.pdbqt';args=[str(ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'),'--receptor',str(ROOT/t['receptor']),'--maps',str(ROOT/Path(t['maps'][0]['path']).parent/'fa10'),'--ligand',str(ligand),'--cpu','1','--seed','104729','--exhaustiveness','4','--num_modes','9','--energy_range','1000','--max_evals',str(cap),'--out',str(dest)]
    pos=args.index('--maps');del args[pos:pos+2]
    for axis,center in zip('xyz',t['center']):args+=['--center_'+axis,str(center),'--size_'+axis,'30']
    before=time.perf_counter();r=subprocess.run(args,capture_output=True,text=True,timeout=600);row['stock']={'returncode':r.returncode,'wall_ms':1000*(time.perf_counter()-before),'pose':dest.read_text() if r.returncode==0 else None,'error':r.stderr if r.returncode else None};row['split_pose']=(prefix/'split.pdbqt').read_text()
    results.append(row);(OUT/'split_equivalence.json').write_text(json.dumps(results,indent=2)+'\n');print(t['target'],cap,'exact split/merge',round(sum(u['ms'] for u in units)),flush=True)
  finally:stop(p)
