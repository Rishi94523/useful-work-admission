"""Build the Zenodo deposit for the manuscript: a code snapshot of HEAD and a
data bundle of the result ledgers behind every number in the paper.

Output: tmp/zenodo/ (ignored). Run from a clean tree at the commit the paper
cites; the script refuses a dirty tree so the archive matches the hash. The
data bundle is scanned for secrets before it is written.
"""
import hashlib,json,re,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];LR=ROOT/'local-research';OUT=ROOT/'tmp/zenodo'

# Result directory -> what it supports in the paper.
DATA={
 'published-vina-validation-2026-09-15':'Stock Vina qualification of the five targets (Section 5.1, Supplementary S1)',
 'build-equivalence-2026-09-20':'Build-equivalence gates G1-G3 (Section 3.2)',
 'published-matched-2026-09-20-samebuild':'Matched decomposition campaign, 2,073 paired state jobs; comparison.json supplies the matched-compute table (Section 5.1)',
 'published-matched-2026-09-20':'Preserved earlier matched attempt stopped by the parity gate (not used for results)',
 'published-matched-2026-09-20-spacing0375':'Preserved earlier matched attempt stopped by the parity gate (not used for results)',
 'adversarial-2026-09-23':'Unit-level attacks, admission economics, integrity experiments, puzzle baseline, identity cost (Sections 5.3-5.5, Supplementary S4)',
 'driver-v2-2026-09-23':'Rescoring (v2) driver verification (Section 5.4)',
 'device-timing':'First phone timing study, four phones (Section 5.2, Supplementary S2)',
 'device-timing-subpuzzle':'Second phone timing study with the subpuzzle baseline, five phones (Section 5.2)',
 'priority-admission-2026-09-24':'Original single-seed effort-priority results, amendment 9 (Supplementary S3)',
 'priority-admission-2026-09-24-patience':'Original single-seed full-patience results, amendment 9b (Supplementary S3)',
 'attested-admission-2026-09-25':'Original single-seed attested-lane results, amendment 10 (Supplementary S3)',
 'admission-amendment12-2026-09-25':'Corrected five-seed availability replication, 1,120 runs, amendment 12 (Section 5.5, Supplementary S3)',
 'admission-amendment13-2026-09-28':'Proof-of-work gate baseline, 360 runs, amendment 13 (Section 5.5, Figure 3, Supplementary S5)',
 'inference-leverage-2026-09-28':'Classifier verification leverage, trace sizes, perturbation checks and native scrypt reference, amendment 14 (Section 5.6, Table 8, Figure 5, Supplementary S6)',
 'device-inference-2026-09-28':'Phone classifier inference, SHA-256 and scrypt timing, four phones, amendment 14b (Section 5.6)',
 'admission-amendment14-2026-09-28':'Availability with classifier verification in place of replay, 1,800 runs, amendment 14 (Section 5.6)',
 'batched-leverage-2026-09-28':'Batched verification leverage with CPU and GPU central baselines, amendment 15',
 'native-dense-2026-09-28':'Native fused verification of dense networks, amendment 15b',
 'predeclaration-audit':'Check that every predeclared result set was produced after its governing amendment commit (Section 4.1; scripts/audit_predeclaration.py)',
 'ticket-prototype-2026-09-24':'Isolated ticket prototype over loopback HTTP (Section 6, Supplementary S3)',
 'ticket-prototype-2026-09-24-wide':'Ticket prototype, wider configuration (Supplementary S3)',
 'ticket-molecular-2026-09-24':'Ticket prototype two-bundle native smoke check with real replay (Supplementary S3)',
 'hashcash-batches-2026-09-24':'Desktop subpuzzle hashcash variance baseline',
 'capacity-review-2026-09-24':'Capacity review of the ticket prototype',
}
# Inputs outside local-research, stored under their own prefix in the data zip.
# The trained classifiers are included because retraining is not bit-exact and
# the reported accuracies and timings depend on these exact weights.
EXTRA={'data/inference-models':'models/inference-models'}
SECRETS=re.compile(rb'api[_-]?key|secret|password|bearer|PRIVATE KEY|UPLOAD_KEY|Users[\\/]+\w+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}',re.I)

def git(*a):return subprocess.check_output(['git',*a],cwd=ROOT,text=True).strip()

def main():
 if git('status','--porcelain') and '--allow-dirty' not in sys.argv:sys.exit('Working tree is dirty; commit first so the archive matches the cited hash.')
 # Validate all inputs before creating either archive. Never silently omit a
 # missing result directory or leave a partially written deposit after a scan.
 inputs=[]
 for d in DATA:
  folder=LR/d
  if not folder.is_dir():sys.exit('Missing required result directory: '+d)
  paths=sorted(f for f in folder.rglob('*') if f.is_file())
  if not paths:sys.exit('Empty required result directory: '+d)
  for f in paths:
   b=f.read_bytes()
   if SECRETS.search(b):sys.exit('Possible secret or personal data in '+str(f.relative_to(LR)))
   inputs.append((f,b,'results/'+f.relative_to(LR).as_posix()))
 for d,prefix in EXTRA.items():
  paths=sorted(f for f in (ROOT/d).rglob('*') if f.is_file())
  if not paths:sys.exit('Missing required input directory: '+d)
  for f in paths:
   b=f.read_bytes()
   if SECRETS.search(b):sys.exit('Possible secret or personal data in '+d+'/'+f.name)
   inputs.append((f,b,prefix+'/'+f.relative_to(ROOT/d).as_posix()))
 commit=git('rev-parse','HEAD');short=commit[:7];OUT.mkdir(parents=True,exist_ok=True)
 code=OUT/('useful-work-admission-code-'+short+'.zip')
 subprocess.check_call(['git','archive','--format=zip','--prefix=useful-work-admission-'+short+'/','-o',str(code),commit],cwd=ROOT)
 data=OUT/('useful-work-admission-results-'+short+'.zip');sums=[];files=0
 with zipfile.ZipFile(data,'w',zipfile.ZIP_DEFLATED) as z:
  for f,b,arc in inputs:
   z.writestr(arc,b);files+=1
   sums.append(hashlib.sha256(b).hexdigest()+'  '+arc)
  readme=['# Result ledgers for "The Price of Utility: Verification Leverage in Useful-Work Browser Admission"','',
   'Code commit: '+commit,'','Each directory under results/ is the unmodified local output of one experiment,',
   'with its execution manifest where the runner writes one. Earlier attempts and',
   'misses are preserved rather than removed. SHA256SUMS lists every result file.',
   'Repository: https://github.com/Rishi94523/useful-work-admission',
   'Release bundles are excluded from code snapshots via export-ignore.',
   '', 'Scope: recorded results and analysis inputs, not a self-contained molecular rerun.',
   'Full receptor/ligand libraries, native binaries, browser WASM/prepared assets,',
   'and the complete raw molecular pool/trace corpus are not included. Re-running',
   'molecular experiments requires the external inputs and build dependencies',
   'specified by the benchmark protocols. Included fixture outputs are only a smoke test.',
   '', '| Directory | Supports |','| --- | --- |']
  readme+=['| `%s` | %s |'%(d,v) for d,v in DATA.items()]
  readme+=['','`models/inference-models/` holds the four classifiers trained for amendment 14',
   '(seed 20260928, `scripts/train_inference_models.py`; training.json records accuracies).',
   'Place it at data/inference-models to rerun the leverage benchmark. VGG11-BN and the',
   'MNIST and CIFAR-10/10.1 datasets are public downloads pinned with hashes in research/inference/workload_provenance.json.']
  readme+=['','Regenerate the paper figures and PDFs from the matching code snapshot:',
   'place results/ at the repository root as local-research/, then run',
   '`python scripts/make_paper_figures.py` and `python scripts/build_manuscript.py --pdf`.',
   'Figure generation requires Python and matplotlib. PDF compilation additionally',
   'requires LaTeX, latexmk/Perl and the Springer template files described in',
   'docs/paper/README.md; these upstream template files are not bundled.',
   'Original execution manifests record historical source hashes. Re-analysis',
   'does not imply the current scripts match every historical execution manifest.']
  z.writestr('README.md','\n'.join(readme)+'\n');z.writestr('SHA256SUMS','\n'.join(sums)+'\n')
 digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
 (OUT/'MANIFEST.json').write_text(json.dumps({'commit':commit,'code_zip':{'file':code.name,'sha256':digest(code),'bytes':code.stat().st_size},
  'data_zip':{'file':data.name,'sha256':digest(data),'bytes':data.stat().st_size,'files':files}},indent=2),encoding='utf-8')
 print('commit',short,'| code',round(code.stat().st_size/1e6,2),'MB | data',round(data.stat().st_size/1e6,2),'MB,',files,'files ->',OUT)

if __name__=='__main__':main()
