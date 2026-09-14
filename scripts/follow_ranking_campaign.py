"""One-shot completion watcher for an already running local ranking campaign."""
import argparse,json,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--protocol',required=True);args=p.parse_args()
protocol=json.loads(Path(args.protocol).read_text());out=Path(protocol['output_directory']);log=out/'campaign.log'
while True:
 text=log.read_text(errors='replace') if log.exists() else ''
 if 'Completed gated campaign' in text or 'Traceback (most recent call last)' in text:
  r=subprocess.run([sys.executable,'scripts/analyze_vina_followup.py','--protocol',args.protocol],capture_output=True,text=True)
  (out/'completion_analysis.log').write_text(r.stdout+r.stderr)
  (out/'completion.json').write_text(json.dumps({'campaign_completed':'Completed gated campaign' in text,'analyzer_returncode':r.returncode,'finished_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'scope':'Local numerical analysis only; no Git commit, push or claim of scientific success is automatic.'},indent=2)+'\n')
  break
 time.sleep(30)
