import numpy as np
import collections

#Scenario = collections.namedtuple('Scenario', 'bw delay worker_vec')
Flow = collections.namedtuple('Flow', 'host_name start_ts bw')

class Scenario(object):
    def __init__(self, bw, loss_rate, delay, queue_size, worker_vec):
        self.bw = bw
        self.loss_rate = loss_rate
        self.delay = delay
        self.queue_size = queue_size
        self.initial_delay = delay
        self.worker_vec = worker_vec
        self.ts = 0

    def step(self):
        self.ts += 1
        # TODO adjust flows
        adjust_delay = 0.1 > np.random.random_sample()
        if adjust_delay:
            self.delay = np.random.normal(loc=self.initial_delay, scale=0.1*self.initial_delay)

    def get_cwnd(self):
        pass

    def get_active_flows(self):
        return [] # TODO

    def get_delay(self):
        return self.delay

    def get_loss_rate(self):
        return self.loss_rate

    def get_active_workers(self):
        return self.worker_vec

def obtain_scenario(worker_cnt):
    bw = 12 # TODO
    loss_rate = 0.0
    delay = np.random.randint(10, 200)
    queue_size = 1000

    while True:
        worker_vec = np.random.choice(a=[False, True], size=(worker_cnt))
        if np.count_nonzero(worker_vec) == 0:
            continue
        return Scenario(bw=bw, loss_rate=loss_rate, delay=delay, queue_size=queue_size, worker_vec=worker_vec)
