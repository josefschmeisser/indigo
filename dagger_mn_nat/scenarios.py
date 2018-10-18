import numpy as np
import collections

#Scenario = collections.namedtuple('Scenario', 'bw delay worker_vec')
Flow = collections.namedtuple('Flow', 'host_name start_ts bw')

class Scenario(object):
    def __init__(self, bw, delay, worker_vec):
        self.bw = bw
        self.delay = delay
        self.initial_delay = delay
        self.worker_vec = worker_vec
        self.ts = 0

    def step(self):
        pass
        # TODO adjust delay based on initial_delay

    def get_cwnd(self):
        pass

    def get_active_flows(self):
        return None

    def get_delay(self):
        return self.delay

    def get_active_workers(self):
        return self.worker_vec

def obtain_scenario(worker_cnt):
    np.linspace(10, 200)
    bw = 12
    delay = 10

    while True:
        worker_vec = np.random.choice(a=[False, True], size=(worker_cnt))
        if np.count_nonzero(worker_vec) == 0:
            continue
        return Scenario(bw=bw, delay=delay, worker_vec=worker_vec)
