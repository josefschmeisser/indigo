import numpy as np
import collections
#from recordtype import recordtype

from helpers.config import config, get_full_worker_list, get_our_worker_list, get_ps_host_list

packet_size = 1600 # (in bytes) TODO check
cwnd_correction_factor = 0.95
available_bandwidths = [5.0, 10.0, 12.0, 20.0]
iPerfFlow = collections.namedtuple('iPerfFlow', 'host_idx start_ts bw proto linux_congestion')
IndigoFlow = collections.namedtuple('IndigoFlow', 'host_idx active start_delay timeout initial_link_delay current_link_delay')

class Scenario(object):
    def __init__(self, worker_cnt):
        self.worker_cnt = worker_cnt

        self.scenario_config = config.get_our_section()['scenario']

        self.ts = 0
        self.bw = 12.0 # TODO
        self.loss_rate = 0.0
        self.queue_size = np.random.randint(500, 2000)
        # config
        self.enable_loss = False
        self.enable_iperf_flows = False
        self.enable_variational_delay = False

        self.active_flow_cnt = 0
        while True:
            self.worker_vec = np.random.choice(a=[False, True], size=(worker_cnt))
            self.active_flow_cnt = np.count_nonzero(self.worker_vec)
            if self.active_flow_cnt == 0:
                continue

        self.indigo_flows = []
        for worker_idx in range(worker_cnt):
            if not self.worker_vec[worker_idx]:
                self.indigo_flows.append(IndigoFlow(worker_idx, False, 0, 0, 0, 0, 0))
                continue

            # determine start delay
            start_delay = 0
            has_start_delay = 0.1 > np.random.random_sample()
            if has_start_delay:
                start_delay = np.random.exponential()

            # TODO set timeout

            # determine the initinal link delay
            initial_link_delay = np.random.randint(10, 200)

            self.indigo_flows.append(IndigoFlow(worker_idx, True, start_delay, initial_link_delay, initial_link_delay))

        ### TODO iperf flows
        self.iperf_flows = []
        iperf_flow_vec = np.random.choice(a=[False, True], size=(worker_cnt), p=(0.9, 0.1))
        iperf_flow_vec = np.logical_and(np.logical_not(self.worker_vec), iperf_flow_vec)
        iperf_flow_cnt = np.count_nonzero(iperf_flow_vec)
        assert(iperf_flow_cnt + self.active_flow_cnt <= worker_cnt)
        self.active_flow_cnt += iperf_flow_cnt
        per_flow_bw = self.bw / self.active_flow_cnt

        # create iperf flows
        for worker_idx in range(worker_cnt):
            if not iperf_flow_vec[worker_idx]:
                continue
            
            self.iperf_flows.append(iPerfFlow(worker_idx, 0, per_flow_bw))

    def step(self):
        self.ts += 1

        for worker_idx in range(self.worker_cnt):
            flow = self.indigo_flows[worker_idx]
            adjust_delay = 0.1 > np.random.random_sample()
            if adjust_delay:
                self.delay = np.random.normal(loc=flow.initial_link_delay, scale=0.1*flow.initial_link_delay)
                pass # TODO

        # TODO update iperf flows

    def get_active_iperf_flows(self):
        return self.iperf_flows

    # in Mbps
    def get_bandwidth(self):
        return self.bw

    def get_loss_rate(self):
        return self.loss_rate

    def get_active_worker_vector(self):
        return self.worker_vec

    def get_indigo_flows(self):
        return self.indigo_flows

    def get_queue_size(self):
        return self.queue_size

    def get_step_width(self):
        return self.scenario_config['step_width']


# TODO check
# min_rtt in ms
def calculate_cwnd(scenario, worker_idx, min_rtt):
    bw = scenario.get_bandwidth() * 1.e6 / 8. / 1.e3 # [bytes/ms]
    cwnd = bw*min_rtt
    cwnd *= cwnd_correction_factor
    cwnd = np.floor(cwnd)
    return cwnd
