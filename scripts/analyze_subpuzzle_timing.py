"""Amendment 11: score phone timing reports from the subpuzzle page.

Fetches every stored timing report tagged page='subpuzzle-v1' from the
benchmark's KV namespace into local-research/device-timing-subpuzzle/ (reports
from the first study carry no page tag and are skipped), then scores S1-S4.
Measurements overlapping a hidden page are excluded, as in the first study.
"""
import json,math,statistics,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'local-research/device-timing-subpuzzle'
NS='0e88d0177dde4a31b21c844ff36bbbfd';WRANGLER=['npx','wrangler','kv','key']

def wrangler(*args):
 return subprocess.run(WRANGLER+list(args)+['--namespace-id='+NS,'--remote'],capture_output=True,text=True,check=True,shell=sys.platform=='win32').stdout

def fetch():
 OUT.mkdir(parents=True,exist_ok=True)
 keys=[k['name'] for k in json.loads(wrangler('list','--prefix=timing_'))]
 for key in keys:
  path=OUT/(key+'.json')
  if path.exists():continue
  report=json.loads(wrangler('get',key))
  if report.get('page')=='subpuzzle-v1':path.write_text(json.dumps(report,indent=1),encoding='utf-8')

def pct(values,q):
 s=sorted(values);return s[min(len(s)-1,int(math.ceil(q*len(s)))-1)]

def main():
 if '--no-fetch' not in sys.argv:fetch()
 reports=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(OUT.glob('timing_*.json'))]
 reports=[r for r in reports if not r.get('error') and r.get('server_checks',{}).get('exact_units')==len(r['units'])]
 pooled={'unit':[],'single':[],'sub':[]};devices=[]
 for r in reports:
  warm=[u['run_ms'] for u in r['units'] if u['mode']=='reuse' and not u.get('overlaps_hidden')]
  kinds={k:[p['ms'] for p in r['puzzles'] if p['kind']==k and not p.get('overlaps_hidden')] for k in ('single','sub')}
  m=statistics.median(warm)
  pooled['unit']+=[t/m for t in warm]
  for k in kinds:pooled[k]+=[t/m for t in kinds[k]]
  devices.append(dict(device=r.get('device_model') or r['user_agent'][:60],unit_median_ms=round(m),
   sub_median_ms=round(statistics.median(kinds['sub'])),single_median_ms=round(statistics.median(kinds['single'])),
   sub_over_unit=round(statistics.median(kinds['sub'])/m,3),hash_rate=round(r['calibration']['hash_rate_per_s']),
   excluded=sum(bool(u.get('overlaps_hidden')) for u in r['units'])+sum(bool(p.get('overlaps_hidden')) for p in r['puzzles'])))
 print('devices:',len(devices))
 for d in devices:print(' ',d)
 rows={}
 for k,v in pooled.items():
  if not v:continue
  med=statistics.median(v)
  rows[k]=dict(n=len(v),p95_over_median=pct(v,.95)/med,p99_over_median=pct(v,.99)/med,max_over_median=max(v)/med,
               over_2x=sum(t>2*med for t in v)/len(v),cv=statistics.pstdev(v)/statistics.mean(v))
  print('%-6s n=%3d p95/med %.2f p99/med %.2f max/med %.2f over2x %.1f%% cv %.2f'%(k,rows[k]['n'],rows[k]['p95_over_median'],
        rows[k]['p99_over_median'],rows[k]['max_over_median'],100*rows[k]['over_2x'],rows[k]['cv']))
 if len(devices)<3:print('Fewer than three devices: amendment 11 requires at least three, one a budget phone.')
 if rows:
  s=rows['sub'];print('S1 subpuzzle p95/median <= 1.35 and none over 2x:',s['p95_over_median']<=1.35 and s['over_2x']==0)
  print('S2 single over 2x >= 15%:',rows['single']['over_2x']>=0.15)
  print('S3 unit p95/median <= 1.35:',rows['unit']['p95_over_median']<=1.35)
  print('S4 every device sub median within 20% of unit median:',all(abs(d['sub_over_unit']-1)<=0.2 for d in devices))
 (OUT/'summary.json').write_text(json.dumps(dict(devices=devices,pooled=rows),indent=1),encoding='utf-8')

if __name__=='__main__':main()
