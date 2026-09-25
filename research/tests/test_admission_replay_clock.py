from collections import deque

import unittest

from scripts.admission_replay_clock import ReplayClock
from scripts.build_manuscript import body


def clock_fixture(workers=1, duration=1.52, jobs=6):
    now, inflight, done = [0.0], [], []
    queue = deque(range(jobs))
    clock = ReplayClock(now, inflight, workers, duration,
                        lambda: queue.popleft() if queue else None,
                        lambda row: done.append((now[0], row)))
    clock.fill()
    return clock, done


def test_service_not_rounded_to_input_tick():
    clock, done = clock_fixture()
    for tick in range(1, 14):
        clock.advance(tick * .25)
    assert done == [(1.52, 0), (3.04, 1)]
    assert abs(clock.inflight[0][0] - 4.56) < 1e-12


def test_parallel_workers_and_multiple_events_between_ticks():
    clock, done = clock_fixture(workers=2, duration=.05)
    clock.advance(.25)
    assert all(abs(t-e) < 1e-12 for (t, _), e in zip(done, [.05, .05, .1, .1, .15, .15]))
    assert len({row for _, row in done}) == 6
    assert clock.metrics()['completed'] == 6


def test_idle_workers_start_at_arrival_not_next_tick():
    now, inflight, queue, done = [0.0], [], deque(), []
    clock = ReplayClock(now, inflight, 1, 1.52,
                        lambda: queue.popleft() if queue else None,
                        lambda row: done.append(now[0]))
    clock.advance(.25)
    queue.append('new arrival')
    clock.fill()
    clock.advance(2)
    assert done == [1.77]


def test_wrapped_year_remains_prose_but_ordered_lists_work():
    result = body('The proposal expired in\n2024. Apple states this.\n\n1. First\n2. Second')
    assert 'expired in 2024. Apple' in result
    assert result.count('\\begin{enumerate}') == 1
    assert '\\item First' in result and '\\item Second' in result


def test_ordered_list_can_start_after_paragraph_without_blank():
    assert '\\begin{enumerate}' in body('A list:\n1. One\n2. Two')


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(unittest.FunctionTestCase(fn) for name, fn in globals().items() if name.startswith("test_"))
