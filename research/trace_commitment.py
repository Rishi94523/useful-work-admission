"""Unit payload that binds the search trace by hash instead of carrying it.

Committing to the minima pool alone does not enforce work: retained minima often
stop changing before the evaluation budget is spent, so a truncated search can
reproduce the pool byte for byte (phase 1: 20% of quarter-budget and 45% of
half-budget units). Binding the per-step trace closes that, but the trace is
about eight times the size of the pool. The verifier replays the unit anyway and
obtains its own trace, so the client only needs to commit to the trace's hash.
"""
import hashlib,json

VERSION='pool+trace-sha256/1'

def payload(pool,trace):
 """Bytes a client uploads for one unit: its pool and the hash of its trace."""
 if not isinstance(pool,bytes) or not isinstance(trace,bytes) or not pool or not trace:raise ValueError('Pool and trace must be non-empty bytes')
 return json.dumps({'version':VERSION,'pool':pool.decode('ascii'),'trace_sha256':hashlib.sha256(trace).hexdigest()},separators=(',',':'),sort_keys=True).encode()

def verify(submitted,replayed_pool,replayed_trace):
 """Trusted replay verdict: pool and trace hash must both match exactly."""
 try:
  d=json.loads(submitted)
  if d.get('version')!=VERSION or set(d)!={'version','pool','trace_sha256'}:return False
  return d['pool'].encode('ascii')==replayed_pool and d['trace_sha256']==hashlib.sha256(replayed_trace).hexdigest()
 except (ValueError,UnicodeError,AttributeError,TypeError):return False
