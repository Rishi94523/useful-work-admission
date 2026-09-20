"""Build-equivalence gate: separate instrumentation effects from toolchain effects.

Four executables dock the same crystal input under the same published protocol:

  O   official prebuilt AutoDock Vina 1.2.7 Windows binary (MSVC toolchain)
  R1  unpatched upstream library, official main, this machine's g++
  R2  split-task library objects, official main, this machine's g++
  D   the distributed harness driver, same split-task objects, C++ API

R1 vs R2 and R1 vs D are required to be coordinate-identical on every retained
pose. Those two comparisons carry the claims the distributed design depends on:
that the split instrumentation does not alter the search, and that the driver
reproduces the command-line protocol. Both are exact equalities, so neither
threshold can be fitted after the fact.

O vs R1 is reported, not gated. A prebuilt MSVC binary and a MinGW build of the
same source use different C runtime math; a last-bit difference reroutes a BFGS
step, which flips a Metropolis decision, which diverges the trajectory. This is
a property of chaotic stochastic search, not a defect, and no compiler flag
removes it. The concordance thresholds live in the protocol note, and failures
here are preserved rather than waived.

Inputs are copied with CRLF normalised to LF, per-line bytes asserted, exactly
as the distributed harness does; MinGW text-mode streams mis-parse the ADFR
files at buffer boundaries otherwise.
"""
import hashlib,json,math,os,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'local-research/published-vina-validation-2026-09-15'
OUT=ROOT/'local-research/build-equivalence-2026-09-20'
WORK=ROOT/'tmp/vina-reference/work'
REF=ROOT/'tmp/vina-reference'
SEED=104729

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2));os.replace(tmp,p)
def freeze(p,x):
 if p.exists():assert json.loads(p.read_text())==x,'Immutable manifest changed: '+str(p)
 else:save(p,x)

def normalize(source,dest):
 raw=Path(source).read_bytes();lf=raw.replace(b'\r\n',b'\n')
 assert raw.splitlines()==lf.splitlines(),'Line-ending normalisation changed content: '+str(source)
 dest.write_bytes(lf);return dest

def poses(path):
 """Every retained pose as ordered (atom name, element, x, y, z) records."""
 result=[]
 for block in Path(path).read_text().split('ENDMDL'):
  atoms=[l for l in block.splitlines() if l.startswith(('ATOM','HETATM'))]
  if atoms:result.append([(l[12:16],l[77:].strip(),*[float(l[i:i+8]) for i in (30,38,46)]) for l in atoms])
 return result

def energies(path):
 return [float(l.split(':')[1].split()[0]) for l in Path(path).read_text().splitlines() if 'VINA RESULT' in l]

def deviation(a,b):
 """Top-pose heavy-atom deviation; None when the pose records are not comparable."""
 if not a or not b or len(a[0])!=len(b[0]):return None
 d=[math.dist(x[2:],y[2:]) for x,y in zip(a[0],b[0]) if x[1]!='H' and y[1]!='H']
 if not d:return None
 return {'max_atom_A':max(d),'rmsd_A':(sum(v*v for v in d)/len(d))**.5}

def dock(exe,target,folder,args,split=None):
 folder.mkdir(parents=True,exist_ok=True);out=folder/'out.pdbqt'
 env=dict(os.environ)
 if split is not None:split.mkdir(parents=True,exist_ok=True);env['VINA_SPLIT_FOLDER']=str(split)
 begin=time.perf_counter()
 r=subprocess.run([str(exe),*args,'--out',str(out)],capture_output=True,text=True,env=env,timeout=14400)
 (folder/'run.log').write_text(r.stdout+r.stderr)
 assert r.returncode==0,target+' docking failed; see '+str(folder/'run.log')
 return {'pose_path':out,'wall_seconds':time.perf_counter()-begin}

def target_job(t,stock_row):
 name=t['target'];folder=WORK/name;inputs=folder/'inputs';inputs.mkdir(parents=True,exist_ok=True)
 l=t['crystal']
 assert digest(ROOT/t['receptor'])==t['receptor_sha256'] and digest(ROOT/l['path'])==l['sha256']
 receptor=normalize(ROOT/t['receptor'],inputs/'receptor.pdbqt')
 ligand=normalize(ROOT/l['path'],inputs/'ligand.pdbqt')
 args=['--receptor',str(receptor),'--ligand',str(ligand),'--cpu','1','--seed',str(SEED),
       '--exhaustiveness','32','--num_modes','9']
 for i,x in enumerate('xyz'):args+=['--center_'+x,str(t['center'][i]),'--size_'+x,str(t['size'][i])]
 r1=dock(REF/'vina_ref_stock.exe',name,folder/'r1_stock',args)
 r2=dock(REF/'vina_ref_instrumented.exe',name,folder/'r2_instrumented',args,split=folder/'r2_split')
 official=ROOT/stock_row['pose_path'];assert digest(official)==stock_row['pose_sha256']
 driver=ROOT/'tmp/vina-published/matched_spacing0375/parity_lf'/name/'normal.pdbqt'
 sets={'R1':poses(r1['pose_path']),'R2':poses(r2['pose_path']),'O':poses(official)}
 if driver.exists():sets['D']=poses(driver)
 def identical(a,b):
  n=min(len(sets[a]),len(sets[b]));return bool(n) and all(sets[a][i]==sets[b][i] for i in range(n))
 record={'target':name,'retained_poses':{k:len(v) for k,v in sets.items()},
         'top_scores':{'R1':energies(r1['pose_path'])[:1],'R2':energies(r2['pose_path'])[:1],'O':energies(official)[:1]},
         'wall_seconds':{'R1':r1['wall_seconds'],'R2':r2['wall_seconds']},
         'instrumentation_identical':identical('R1','R2'),
         'official_top_score_delta':energies(r1['pose_path'])[0]-energies(official)[0],
         'official_top_pose_deviation':deviation(sets['R1'],sets['O'])}
 if 'D' in sets:
  record['driver_identical']=identical('R1','D')
  record['top_scores']['D']=energies(driver)[:1]
 return record

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 for exe in ('vina_ref_stock.exe','vina_ref_instrumented.exe'):
  assert (REF/exe).exists(),'Run scripts/build_vina_reference.py first: missing '+exe
 build=json.loads((REF/'reference_build.json').read_text())
 data=json.loads((BASE/'inputs.json').read_text())
 eligible=json.loads((BASE/'comparison_eligibility.json').read_text())['eligible_targets']
 targets=[t for t in data['targets'] if t['target'] in eligible]
 stock=[json.loads(s) for s in (BASE/'stock_jobs.jsonl').read_text().splitlines()]
 rows={r['target']:r for r in stock if r['label']=='crystal' and r['seed']==SEED and r['ok']}
 freeze(OUT/'execution_manifest.json',{
  'inputs':digest(BASE/'inputs.json'),'eligibility':digest(BASE/'comparison_eligibility.json'),
  'build':digest(REF/'reference_build.json'),'runner':digest(Path(__file__)),
  'official_exe':build['official']['exe_sha256'],'seed':SEED,'targets':[t['target'] for t in targets],
  'input_transport':'CRLF to LF only, exact per-line bytes asserted; source files unchanged.',
  'scope':'Crystal redocking per eligible target at the published stock protocol. R1==R2 and R1==D are exact gates; O concordance is reported.'})
 results=[]
 with ThreadPoolExecutor(max_workers=5) as pool:
  futures={pool.submit(target_job,t,rows[t['target']]):t['target'] for t in targets if t['target'] in rows}
  for future in as_completed(futures):
   name=futures[future]
   try:r=future.result()
   except Exception as e:r={'target':name,'error':str(e)}
   results.append(r);print(json.dumps(r),flush=True)
 results.sort(key=lambda r:r['target'])
 failed=[r for r in results if 'error' in r]
 gated=[r for r in results if 'error' not in r]
 summary={'results':results,
          'instrumentation_gate_passed':bool(gated) and not failed and all(r['instrumentation_identical'] for r in gated),
          'driver_gate_passed':bool(gated) and not failed and all(r.get('driver_identical') for r in gated if 'driver_identical' in r),
          'targets_with_driver_output':sum('driver_identical' in r for r in gated),
          'execution_failures':[r['target'] for r in failed]}
 save(OUT/'build_equivalence.json',summary)
 print('INSTRUMENTATION GATE',summary['instrumentation_gate_passed'],flush=True)
 print('DRIVER GATE',summary['driver_gate_passed'],flush=True)
 return 0 if summary['instrumentation_gate_passed'] and summary['driver_gate_passed'] else 1

if __name__=='__main__':sys.exit(main())
