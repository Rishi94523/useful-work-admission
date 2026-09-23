import unittest
from research.trace_commitment import payload,verify

POOL=b'2\n-9.1 1 2 3 1 0 0 0 0.5 3 1 2 3 4 5 6 7 8 9\n-8.7 1 2 3 1 0 0 0 0.4 3 1 2 3 4 5 6 7 8 9\n'
TRACE=b''.join(b'%.17g\n%d\n'%(-7.0-i/100,i*50) for i in range(400))

class TraceCommitmentTests(unittest.TestCase):
 def test_honest_payload_verifies(self):
  self.assertTrue(verify(payload(POOL,TRACE),POOL,TRACE))
 def test_altered_pool_byte_rejected(self):
  bad=POOL.replace(b'-9.1',b'-9.2',1);self.assertFalse(verify(payload(bad,TRACE),POOL,TRACE))
 def test_altered_trace_byte_rejected(self):
  bad=TRACE[:-2]+b'1\n';self.assertFalse(verify(payload(POOL,bad),POOL,TRACE))
 def test_truncated_trace_rejected(self):
  # The partial-work signature: an identical pool from a shorter search.
  self.assertFalse(verify(payload(POOL,TRACE[:len(TRACE)//4]),POOL,TRACE))
 def test_malformed_or_foreign_payload_rejected(self):
  for junk in (b'',b'not json',b'{}',b'[]',payload(POOL,TRACE).replace(b'/1',b'/2')):
   self.assertFalse(verify(junk,POOL,TRACE))
 def test_payload_is_much_smaller_than_pool_plus_trace(self):
  self.assertLess(len(payload(POOL,TRACE)),len(POOL)+len(TRACE))

if __name__=='__main__':unittest.main()
