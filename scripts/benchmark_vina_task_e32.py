"""One full E32 same-build control and many-medium-run matched-budget comparison."""
import json,math,subprocess,time
from benchmark_vina_task_split import ROOT,OUT,BASE,OLD,start,call,stop,digest
t=next(t for t in json.loads((OLD/'science_inputs.json').read_text())['targets'] if t['target']=='fa10');ligand=ROOT/next(l for l in t['ligands'] if l['id']=='crystal')['source']['path'];previous=BASE/'campaign/fa10/crystal_source';folder=BASE/'e32';folder.mkdir(exist_ok=True);dest=OUT/'e32.json'
if dest.exists():print('Preserved completed E32 comparison');raise SystemExit(0)
p=start(t,ligand)
try:
 control=call(p,0,0,32,0,folder/'control',folder/'control.pdbqt')
 exact=[digest(folder/'control'/f'{i}.task')==digest(previous/'normal'/f'{i}.task') and digest(folder/'control'/f'{i}.task.trace')==digest(previous/'normal'/f'{i}.task.trace') for i in range(32)]
 assert all(exact) and (folder/'control.pdbqt').read_bytes()==(previous/'normal_32.pdbqt').read_bytes()
 metrics=[json.loads((folder/'control'/f'{i}.task.json').read_text()) for i in range(32)];budget=sum(m['evals'] for m in metrics);search=sum(m['ms'] for m in metrics);cap=256000;n=math.ceil(budget/cap)
 if n>512:raise RuntimeError('E32 matched comparison exceeds safety cap')
 bounded=call(p,0,0,n,cap,folder/'medium',folder/'medium.pdbqt');medium=[json.loads((folder/'medium'/f'{i}.task.json').read_text()) for i in range(n)];sums=[];v=0
 for m in medium:v+=m['ms'];sums.append(v)
 count=min(range(n),key=lambda i:abs(sums[i]-search))+1;wall=call(p,2,0,count,cap,folder/'medium',folder/'wallmatched.pdbqt')
 result={'scope':'FA10 source crystal only; same-build exact32-run decomposition, normal candidate pool9 and receptor finalizer. Many256k runs matched to actual E32 search evaluations; closest available prefix separately matched to MC time. Not a ranking or browser performance trial.','normal':control,'normal_search_ms':search,'normal_evals':budget,'normal_pose':(folder/'control.pdbqt').read_text(),'split_task_trace_exact':exact,'medium':bounded,'medium_runs':n,'medium_evals':sum(m['evals'] for m in medium),'medium_search_ms':sum(m['ms'] for m in medium),'medium_pose':(folder/'medium.pdbqt').read_text(),'wallmatched':wall,'wallmatched_runs':count,'wallmatched_search_ms':sums[count-1],'wallmatched_pose':(folder/'wallmatched.pdbqt').read_text()}
 args=[str(ROOT/'tmp/docking-pilot/native/vina_1.2.7_win.exe'),'--receptor',str(ROOT/t['receptor']),'--ligand',str(ligand),'--cpu','1','--seed','104729','--exhaustiveness','32','--num_modes','9','--energy_range','1000','--out',str(folder/'stock.pdbqt')]
 for axis,center in zip('xyz',t['center']):args+=['--center_'+axis,str(center),'--size_'+axis,'30']
 now=time.perf_counter()
 try:
  stock=subprocess.run(args,capture_output=True,text=True,timeout=900);result['stock']={'returncode':stock.returncode,'wall_ms':1000*(time.perf_counter()-now),'pose':(folder/'stock.pdbqt').read_text() if stock.returncode==0 else None,'error':stock.stderr if stock.returncode else None}
 except subprocess.TimeoutExpired:result['stock']={'returncode':None,'timeout_seconds':900,'wall_ms':1000*(time.perf_counter()-now)}
 dest.write_text(json.dumps(result,indent=2)+'\n');print('E32 task equality',all(exact),'medium runs',n,flush=True)
finally:stop(p)
