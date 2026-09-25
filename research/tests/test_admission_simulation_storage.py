import random
import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from research.ticket_admission import TicketAdmission
from scripts.admission_simulation_storage import memory_sqlite
from scripts import evaluate_priority_admission as priority
from scripts import evaluate_attested_admission as attested


class SimulationStorageTests(unittest.TestCase):
    def run_cell(self, fn, item, memory):
        rng = random.Random(17)
        def token_bytes(n):
            return rng.randbytes(n)
        with patch('secrets.token_bytes', token_bytes), patch('secrets.token_hex', lambda n: token_bytes(n).hex()):
            with memory_sqlite() if memory else nullcontext():
                return fn(item, exact_replay=True)

    def test_disk_and_memory_match_with_overload(self):
        for module, item in ((priority, ('priority', 2, 16, 17, 'patience')),
                             (priority, ('fixed18', 1, 16, 17, 'follow')),
                             (attested, ('oneshot', 2, 16, .5, 10, 17)),
                             (attested, ('bootstrap', 4, 16, .9, 1, 17))):
            with self.subTest(item=item), patch.multiple(module, ARRIVE_S=12, DRAIN_S=8, ATTACK_CAP_PER_TICK=2):
                self.assertEqual(self.run_cell(module.run, item, False), self.run_cell(module.run, item, True))

    def test_rollback_and_context_restoration(self):
        original = TicketAdmission.db
        with tempfile.TemporaryDirectory(dir='tmp') as folder, memory_sqlite():
            c = TicketAdmission(Path(folder)/'unused.sqlite', bytes(32), {'campaign':'test'})
            with self.assertRaises(RuntimeError), c.db() as db:
                db.execute('UPDATE counters SET next_seed=123')
                raise RuntimeError('rollback test')
            with c.db() as db:
                self.assertEqual(db.execute('SELECT next_seed FROM counters').fetchone()[0], 0)
        self.assertIs(TicketAdmission.db, original)


if __name__ == '__main__':
    unittest.main()
