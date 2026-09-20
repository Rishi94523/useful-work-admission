"""G3: does the local toolchain reproduce the official binary's screening outcome?

Gates G1 and G2 establish that the split instrumentation and the harness driver
are exact against a same-toolchain reference. They say nothing about whether
this toolchain agrees with the official prebuilt binary, which is what makes the
distributed numbers comparable to the published stock campaign.

Trajectory-level agreement across toolchains is unattainable and irrelevant. The
claim that matters is that both builds rank the same panel the same way, so this
runs the stock reference R1 over a complete predeclared 96-compound panel and
requires its ROC-AUC to fall inside the bootstrap 95% interval already recorded
for that target in stock_gates.json.

Target selection is by SHA256 order under a fixed salt over the eligible
targets, not by inspection. See BUILD_EQUIVALENCE_PROTOCOL_2026-09-20.
"""
import hashlib,json,os,subprocess,sys,time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from run_stock_diagnostic import metrics

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'local-research/published-vina-validation-2026-09-15'
OUT=ROOT/'local-research/build-equivalence-2026-09-20'
WORK=ROOT/'tmp/vina-reference/panel'
EXE=ROOT/'tmp/vina-reference/vina_ref_stock.exe'
SALT='build-equivalence-2026-09-20:'
SEED=104729
WORKERS=14

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
 tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,indent=2));os.replace(tmp,p)
def read(p):return [json.loads(s) for s in p.read_text().splitlines()] if p.exists() else []
def append(p,x):
 with p.open('a') as f:f.write(json.dumps(x)+'\n');f.flush();os.fsync(f.fileno())

def normalize(source,dest):
 raw=Path(source).read_bytes();lf=raw.replace(b'\r\n',b'\n')
 assert raw.splitlines()==lf.splitlines(),'Line-ending normalisation changed content: '+str(source)
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(lf);return dest

def select(eligible):
 """Fixed-salt hash order, so the panel target is not chosen by outcome."""
 return min(eligible,key=lambda t:hashlib.sha256((SALT+t).encode()).hexdigest())

def job(t,l,receptor):
 folder=WORK/t['target']/l['id'];folder.mkdir(parents=True,exist_ok=True)
 record={'target':t['target'],'id':l['id'],'compound_id':l['compound_id'],'label':l['label'],'ok':False,'input_sha256':l['sha256']}
 begin=time.perf_counter()
 try:
  assert digest(ROOT/l['path'])==l['sha256']
  ligand=normalize(ROOT/l['path'],folder/'ligand.pdbqt');out=folder/'out.pdbqt'
  args=[str(EXE),'--receptor',str(receptor),'--ligand',str(ligand),'--cpu','1','--seed',str(SEED),
        '--exhaustiveness','32','--num_modes','9','--out',str(out)]
  for i,x in enumerate('xyz'):args+=['--center_'+x,str(t['center'][i]),'--size_'+x,str(t['size'][i])]
  r=subprocess.run(args,capture_output=True,text=True,timeout=3600)
  (folder/'run.log').write_text(r.stdout+r.stderr);record['returncode']=r.returncode
  assert r.returncode==0,'Reference docking failed'
  scores=[float(s.split(':')[1].split()[0]) for s in out.read_text().splitlines() if 'VINA RESULT' in s]
  assert scores,'No retained pose'
  record.update(ok=True,score=scores[0],pose_sha256=digest(out))
 except Exception as e:record['error']=str(e)
 record['wall_seconds']=time.perf_counter()-begin;return record

def main():
 OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
 assert EXE.exists(),'Run scripts/build_vina_reference.py first'
 equivalence=json.loads((OUT/'build_equivalence.json').read_text())
 assert equivalence['instrumentation_gate_passed'] and equivalence['driver_gate_passed'],'G1/G2 not satisfied; G3 is not meaningful yet'
 data=json.loads((BASE/'inputs.json').read_text())
 eligible=json.loads((BASE/'comparison_eligibility.json').read_text())['eligible_targets']
 gates={g['target']:g for g in json.loads((BASE/'stock_gates.json').read_text())}
 chosen=sys.argv[1] if len(sys.argv)>1 else select(eligible)
 assert chosen in eligible,'Target is not stock-eligible: '+chosen
 t=next(x for x in data['targets'] if x['target']==chosen)
 receptor=normalize(ROOT/t['receptor'],WORK/chosen/'receptor.pdbqt')
 path=OUT/('panel_'+chosen+'.jsonl');rows=read(path);done={r['id'] for r in rows}
 print('PANEL',chosen,'selected by salted hash order' if len(sys.argv)<2 else 'given explicitly',
       '|',len(t['ligands']),'states,',len(rows),'already recorded',flush=True)
 with ThreadPoolExecutor(max_workers=WORKERS) as pool:
  futures=[pool.submit(job,t,l,receptor) for l in t['ligands'] if l['id'] not in done]
  for n,future in enumerate(as_completed(futures),1):
   r=future.result();append(path,r);rows.append(r)
   if n%10==0 or not r['ok']:print(n,'/',len(futures),r['id'],r['ok'],r.get('score'),flush=True)
 compounds=[]
 for compound in t['compounds']:
  states=[r for r in rows if r['compound_id']==compound['id'] and r['label']!='crystal']
  ok=len(states)==compound['states'] and all(r['ok'] for r in states)
  row={'id':compound['id'],'label':compound['label'],'ok':ok,'required_states':compound['states'],'completed_states':len(states)}
  if ok:row['score']=min(r['score'] for r in states)
  compounds.append(row)
 m=metrics(compounds,5000);stock=gates[chosen];interval=stock['bootstrap95']
 complete=len(compounds)==96 and all(r['ok'] for r in compounds)
 inside=bool(complete and m['auc'] is not None and interval[0]<=m['auc']<=interval[1])
 result={'target':chosen,'selection':'SHA256 order under salt '+SALT,'complete_panel':complete,
         'incomplete_compounds':[r['id'] for r in compounds if not r['ok']],
         'reference_auc':m['auc'],'reference_ef10':m['ef10'],'reference_bootstrap95':m['bootstrap95'],
         'official_auc':stock['auc'],'official_ef10':stock['ef10'],'official_bootstrap95':interval,
         'auc_delta':None if m['auc'] is None else m['auc']-stock['auc'],
         'g3_passed':inside,
         'claim':'Panel-level screening concordance between the local toolchain and the official binary. Not trajectory equivalence, and not a full-library reproduction.'}
 save(OUT/('panel_concordance_'+chosen+'.json'),result)
 print(json.dumps(result,indent=2),flush=True);print('G3',inside,flush=True)
 return 0 if inside else 1

if __name__=='__main__':sys.exit(main())
