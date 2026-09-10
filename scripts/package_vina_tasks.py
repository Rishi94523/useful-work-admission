"""Compact evidence plus task-output hashes; full raw traces remain local."""
import gzip,hashlib,json,os,platform,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/evaluation/vina_tasks_2026-09-10';BASE=ROOT/'tmp/vina-tasks'
def sha(data):return hashlib.sha256(data).hexdigest()
files=[]
for name in ['campaign.jsonl','wallmatched.jsonl']:
 p=OUT/name;raw=p.read_bytes();compressed=gzip.compress(raw,mtime=0);dest=p.with_suffix(p.suffix+'.gz');dest.write_bytes(compressed);assert gzip.decompress(dest.read_bytes())==raw
 files.append({'path':dest.relative_to(ROOT).as_posix(),'sha256':sha(compressed),'uncompressed_sha256':sha(raw),'rows':len(raw.splitlines())})
manifest=[]
for parent in ['campaign','e32','equivalence_fa10','equivalence_hs90a','equivalence_tryb1']:
 for p in sorted((BASE/parent).rglob('*')):
  if p.is_file() and p.suffix in ['.task','.trace','.json','.pdbqt']:manifest.append({'path':p.relative_to(BASE).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())})
raw=json.dumps(manifest,separators=(',',':')).encode();dest=OUT/'raw_task_manifest.json.gz';dest.write_bytes(gzip.compress(raw,mtime=0));assert gzip.decompress(dest.read_bytes())==raw
files.append({'path':dest.relative_to(ROOT).as_posix(),'sha256':sha(dest.read_bytes()),'entries':len(manifest)})
metadata={'scope':'JSONL archives contain aggregate scientific outputs, run counters/timings and identities. Manifest hashes local raw candidate pools/traces for rerun comparison; full raw traces and executables are not included. Paths are repository-relative. Single-machine pilot, no independent device validation.','platform':platform.platform(),'python':platform.python_version(),'processor':platform.processor(),'logical_processors':os.cpu_count(),'compiler':subprocess.run(['g++','--version'],capture_output=True,text=True).stdout.splitlines()[0],'boost_version':re.search(r'#define BOOST_LIB_VERSION "([^"]+)"',(ROOT/'tmp/docking-pilot/boost/ucrt64/include/boost/version.hpp').read_text()).group(1),'emscripten_version':(ROOT/'tmp/docking-runs/emsdk/upstream/emscripten/emscripten-version.txt').read_text().strip(),'instrumented_source_hashes':{p.name:sha(p.read_bytes()) for p in sorted((BASE/'source').iterdir()) if p.suffix in ['.cpp','.h']},'archives':files}
(OUT/'reproducibility.json').write_text(json.dumps(metadata,indent=2)+'\n');print('Archived',len(manifest),'raw output hashes')
