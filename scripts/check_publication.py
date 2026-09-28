"""Fail closed on accidental research-report/private-material commits.

This catches common mistakes, not every possible form of personal information.
Only paths and rule names are printed; never matched private values.
"""
import hashlib,json,re,subprocess,sys
from pathlib import PurePosixPath

def reviewed_archives(manifest):
 """Only the two explicitly reviewed Zenodo artifacts, at their exact hashes.

 The manifest is a publication review record, not a signature or a substitute
 for inspecting archive contents. Arbitrary binaries remain blocked.
 """
 commit=manifest['commit']
 if not re.fullmatch(r'[0-9a-f]{40}',commit):raise ValueError('Invalid source commit')
 result={}
 for key,kind in (('code_zip','code'),('data_zip','results')):
  item=manifest[key];name='useful-work-admission-'+kind+'-'+commit[:7]+'.zip'
  if item['file']!=name or not re.fullmatch(r'[0-9a-f]{64}',item['sha256']):raise ValueError('Invalid archive identity')
  result['releases/zenodo/'+name]=item['sha256']
 return result

def check(path,data,reviewed=None):
 p=path.lower();issues=[]
 if any(x in p for x in ('patent','private-record','aadhaar','aadhar','pan_card','pancard','passport','filing_packet')):issues.append('private-material-path')
 if p.startswith(('docs/evaluation/','docs/research/','tmp/','temp/','local-research/')):issues.append('local-report-or-generated-evidence')
 # Markdown is publishable when it is deliberately placed: a root-level file, a
 # README at any depth, or a curated note under docs/. Working notes live under
 # the generated-evidence prefixes above and are still blocked there.
 if PurePosixPath(p).suffix=='.md':
  name=PurePosixPath(p).name
  if not ('/' not in p or name=='readme.md' or p.startswith('docs/')):issues.append('unreviewed-markdown')
 if PurePosixPath(p).suffix in ('.pdf','.docx','.xlsx','.png','.jpg','.jpeg','.zip','.gz','.bin','.wasm'):
  if not reviewed or reviewed.get(path)!=hashlib.sha256(data).hexdigest():issues.append('binary-needs-explicit-publication-review')
 if PurePosixPath(p).name.startswith('.env') and not p.endswith('.example'):issues.append('environment-file')
 for name,pattern in [('possible-pan',rb'(?<![A-Za-z0-9])[A-Z]{5}[0-9]{4}[A-Z](?![A-Za-z0-9])'),('private-key',rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),('possible-aadhaar',rb'(?<![0-9A-Za-z])[2-9][0-9]{3} [0-9]{4} [0-9]{4}(?![0-9A-Za-z])')]:
  if re.search(pattern,data):issues.append(name)
 return issues

def main():
 paths=subprocess.check_output(['git','diff','--cached','--name-only','--diff-filter=ACMR','-z']).decode().split('\0');failures=[]
 reviewed={}
 record=subprocess.run(['git','show',':releases/zenodo/MANIFEST.json'],capture_output=True)
 if record.returncode==0:
  try:reviewed=reviewed_archives(json.loads(record.stdout))
  except (ValueError,KeyError,TypeError):failures.append(('releases/zenodo/MANIFEST.json',['invalid-publication-manifest']))
 for path in filter(None,paths):
  data=subprocess.check_output(['git','show',':'+path]);rules=check(path,data,reviewed)
  if rules:failures.append((path,rules))
 for path,rules in failures:print(path+': '+', '.join(rules))
 print('Publication check: '+('BLOCKED' if failures else 'passed'))
 return bool(failures)
if __name__=='__main__':sys.exit(main())
