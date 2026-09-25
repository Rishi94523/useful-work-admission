"""Exact replay events between the availability harness's input ticks.

Input polling stays discrete. Only service completion and worker dispatch use
event time. The caller owns verdicts and the real queue implementation.
"""


class ReplayClock:
    def __init__(self, now, inflight, workers, duration, claim, finish):
        if workers < 1 or duration <= 0:
            raise ValueError('Positive worker count and service duration required')
        self.now, self.inflight = now, inflight
        self.workers, self.duration = workers, duration
        self.claim, self.finish = claim, finish
        self.started = self.completed = 0

    def fill(self):
        while len(self.inflight) < self.workers:
            row = self.claim()
            if row is None:
                break
            self.inflight.append((self.now[0] + self.duration, row))
            self.started += 1

    def advance(self, target):
        if target < self.now[0]:
            raise ValueError('Clock cannot move backwards')
        while self.inflight:
            due = min(job[0] for job in self.inflight)
            if due > target:
                break
            self.now[0] = due
            for job in list(self.inflight):
                if job[0] == due:
                    self.inflight.remove(job)
                    self.finish(job[1])
                    self.completed += 1
            self.fill()
        self.now[0] = target

    def metrics(self):
        return dict(mode='exact-replay-events', service_s=self.duration,
                    started=self.started, completed=self.completed,
                    input_tick_s=0.25)
