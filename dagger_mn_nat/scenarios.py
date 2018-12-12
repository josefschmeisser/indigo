import numpy as np
import collections
from helpers.config import config

packet_size = 1600 # (in bytes) TODO check
cwnd_correction_factor = 0.95
iPerfFlow = collections.namedtuple('iPerfFlow', 'host_idx start_ts bw proto linux_congestion')
IndigoFlow = collections.namedtuple('IndigoFlow', 'host_idx active start_delay timeout initial_link_delay current_link_delay')

class Scenario(object):
    def __init__(self, worker_cnt):
        self.worker_cnt = worker_cnt
        self.ts = 0
        self.queue_size = 100000*np.random.randint(1, 100) # in bytes

        # config
        self.scenario_config = config.get_our_section()['scenario']
        self.available_bandwidths = self.scenario_config['available_bandwidths']
        self.current_bw = self.available_bandwidths[0]
        self.bandwidth_change_probability = self.scenario_config['bandwidth_change_probability']
        self.delay_change_probability = self.scenario_config['delay_change_probability']
        self.loss_rate = self.scenario_config['loss_rate']
        self.enable_iperf_flows = self.scenario_config['enable_iperf_flows']
        self.enable_variational_delay = self.scenario_config['enable_variational_delay']
        self.worker_timeout = self.scenario_config['worker_timeout']

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

            # determine the initinal link delay
            initial_link_delay = np.random.randint(10, 200)

            self.indigo_flows.append(IndigoFlow(worker_idx, True, start_delay, self.worker_timeout, initial_link_delay, initial_link_delay))

        # initialize iperf flows (if enabled)
        if self.enable_iperf_flows:
            self.iperf_flows = []
            iperf_flow_vec = np.random.choice(a=[False, True], size=(worker_cnt), p=(0.9, 0.1))
            iperf_flow_vec = np.logical_and(np.logical_not(self.worker_vec), iperf_flow_vec)
            iperf_flow_cnt = np.count_nonzero(iperf_flow_vec)
            assert(iperf_flow_cnt + self.active_flow_cnt <= worker_cnt)
            self.active_flow_cnt += iperf_flow_cnt
            per_flow_bw = self.current_bw / self.active_flow_cnt

            # create iperf flows
            for worker_idx in range(worker_cnt):
                if not iperf_flow_vec[worker_idx]:
                    continue
                self.iperf_flows.append(iPerfFlow(worker_idx, 0, per_flow_bw))

    def step(self):
        self.ts += 1

        # update bandwidth
        adjust_bw = self.bandwidth_change_probability > np.random.random_sample()
        if adjust_bw:
            self.current_bw = np.random.choice(self.available_bandwidths, size=1)[0]

        # update workers
        for worker_idx in range(self.worker_cnt):
            flow = self.indigo_flows[worker_idx]
            new_link_delay = flow.current_link_delay
            adjust_delay = self.enable_variational_delay and (self.delay_change_probability > np.random.random_sample())
            if adjust_delay:
                new_link_delay = np.random.normal(loc=flow.initial_link_delay, scale=0.1*flow.initial_link_delay)
            # create the new tuple (https://stackoverflow.com/a/40980990)
            self.indigo_flows[worker_idx] = IndigoFlow(current_link_delay=new_link_delay, **flow._asdict())

        # TODO update iperf flows
        if self.enable_iperf_flows:
            pass

    def get_active_iperf_flows(self):
        return self.iperf_flows

    # in Mbps
    def get_bandwidth(self):
        return self.current_bw

    def get_loss_rate(self):
        return self.loss_rate

    def get_active_worker_vector(self):
        return self.worker_vec

    def get_indigo_flows(self):
        return self.indigo_flows

    # in bytes
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
    pkt_cwnd = np.floor(cwnd/packet_size)
    return pkt_cwnd
