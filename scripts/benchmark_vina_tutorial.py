"""Exact official 20A tutorial inputs with the frozen search and finalizer."""
import hashlib,json,math,shutil,subprocess,time
from pathlib import Path
from benchmark_vina_task_split import ROOT,BASE,call,stop
from validate_vina_stock_controls import quality
OUT=ROOT/'docs/evaluation/vina_validation_2026-09-10';folder=ROOT/'tmp/vina-validation/tutorial_split';folder.mkdir(exist_ok=True)
dest=OUT/'tutorial_decomposition.json'
if dest.exists():print('preserved tutorial comparison');raise SystemExit()
t=next(t for t in json.loads((OUT/'inputs.json').read_text()) if t['target']=='1iep');controls=json.loads((OUT/'stock_controls.json').read_text());control=next(r for r in controls if r['target']=='1iep' and r['seed']==104729)
assert control['redocking_gate'] and control['hashes']==t['hashes'],'Stock first gate failed'
# Only the wrapper box arguments change. Link the unchanged native core objects.
source=(ROOT/'research/native/vina_task_worker.cpp').read_text().replace('if(argc!=7)','if(argc!=10)').replace('30,30,30);v.save_initial();','std::stod(argv[7]),std::stod(argv[8]),std::stod(argv[9]));v.save_initial();')
worker=folder/'worker.cpp';worker.write_text(source);obj=folder/'worker.o';exe=folder/'vina_tutorial.exe';compiler=shutil.which('g++')
flags=['-O3','-std=c++17','-DNDEBUG','-ffp-contract=off','-I'+str(BASE/'source'),'-I'+str(ROOT/'tmp/docking-pilot/boost/ucrt64/include')]
subprocess.run([compiler,*flags,'-c',str(worker),'-o',str(obj)],check=True)
objects=[p for p in (BASE/'build').glob('*.o') if p.stem!='vina_task_worker']
subprocess.run([compiler,*flags,*map(str,objects),str(obj),'-static-libgcc','-static-libstdc++','-o',str(exe)],check=True)
p=subprocess.Popen([str(exe),t['receptor'],'unused',t['ligand'],*map(str,t['center']),*map(str,t['size'])],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
assert p.stdout.readline().strip()=='READY'
try:
 normal=call(p,0,0,32,0,folder/'normal',folder/'normal.pdbqt');nm=[json.loads((folder/'normal'/f'{i}.task.json').read_text()) for i in range(32)]
 budget=sum(m['evals'] for m in nm);n=math.ceil(budget/256000);assert n<=512
 medium=call(p,0,0,n,256000,folder/'medium',folder/'medium.pdbqt');mm=[json.loads((folder/'medium'/f'{i}.task.json').read_text()) for i in range(n)]
 # Replay selected independent units against the monolithic task pools.
 exact=[]
 for index in [0,15,31]:
  call(p,1,index,32,0,folder/'replay',folder/'unused.pdbqt')
  exact.append(all((folder/'normal'/f'{index}.task{suffix}').read_bytes()==(folder/'replay'/f'{index}.task{suffix}').read_bytes() for suffix in ['', '.trace']))
 assert all(exact)
 result={'scope':'Official1iep prepared inputs/20A box; stock E32 gate precedes decomposition. Native original source objects with only configurable wrapper box. Single parent seed, source-conformer control. Timing not an isolated speedup experiment.','input_hashes':t['hashes'],'exe_sha256':hashlib.sha256(exe.read_bytes()).hexdigest(),'wrapper_sha256':hashlib.sha256(worker.read_bytes()).hexdigest(),'normal':normal,'normal_search_ms':sum(m['ms'] for m in nm),'normal_evals':budget,'normal_quality':quality(Path(t['ligand']),Path(t['sdf']),(folder/'normal.pdbqt').read_text()),'medium':medium,'medium_runs':n,'medium_search_ms':sum(m['ms'] for m in mm),'medium_evals':sum(m['evals'] for m in mm),'medium_quality':quality(Path(t['ligand']),Path(t['sdf']),(folder/'medium.pdbqt').read_text()),'selected_independent_task_replay_exact':exact,'normal_pose':(folder/'normal.pdbqt').read_text(),'medium_pose':(folder/'medium.pdbqt').read_text(),'normal_units':nm,'medium_units':mm}
 dest.write_text(json.dumps(result,indent=2)+'\n');print('tutorial',n,result['normal_quality'],result['medium_quality'],flush=True)
finally:stop(p)
