import numpy as np
import collections
import sys
import os
import time
import project_root
from helpers.config import config
from helpers.helpers import make_sure_path_exists
from env.sender import default_cwnd

# TODO what about the CRC checksum?
packet_size = 1478 # (in bytes) (MAC header + IPv4 + UDP header + payload = 14 + 20 + 8 + 1436 = 1478)
cwnd_correction_factor = 0.95
iPerfFlow = collections.namedtuple('iPerfFlow', 'host_idx start_ts bw proto linux_congestion')
IndigoFlow = collections.namedtuple('IndigoFlow', 'host_idx active start_delay initial_link_delay current_link_delay')
StateUpdate = collections.namedtuple('StateUpdate', 'new_bw, indigo_flows_update, iperf_flows_udpate')


class Event:
    NEW_BW = 0
    NEW_DELAY = 1
    NEW_BUFFER_SIZE = 2


class Scenario(object):
    def __init__(self):
        # read config
        self.scenario_config = config.get_our_section()['scenario']
        self.available_bandwidths = self.scenario_config['available_bandwidths']
        self.bandwidth_change_probability = self.scenario_config['bandwidth_change_probability']
        self.delay_change_probability = self.scenario_config['delay_change_probability']
        self.loss_rate = self.scenario_config['loss_rate']
        self.enable_iperf_flows = self.scenario_config['enable_iperf_flows']
        self.enable_variational_delay = self.scenario_config['enable_variational_delay']
        self.enable_worker_idling = self.scenario_config['enable_worker_idling']
        self.enable_worker_start_delay = self.scenario_config['enable_worker_start_delay']

        if self.enable_iperf_flows and self.enable_worker_start_delay:
            sys.exit('enable_iperf_flows and enable_worker_start_delay are incompatible')

        # initialize log file
        log_dir = os.path.join(project_root.DIR, 'mn_logs')
        make_sure_path_exists(log_dir)
        timestr = time.strftime("%Y%m%d-%H%M%S")
        log_file_name = timestr + '_' + config.get_role() + '.log'
        self.log_file = os.path.join(log_dir, log_file_name)

    def set_up_new_epoch(self, worker_cnt):
        self.ts = 0
        self.worker_cnt = worker_cnt

        self.queue_size = 100000*np.random.randint(1, 100) # in bytes
        self.log(Event.NEW_BUFFER_SIZE, self.queue_size)

        self.current_bw = np.random.choice(self.available_bandwidths, size=1)[0]
        self.log(Event.NEW_BW, self.current_bw)

        if self.enable_worker_idling:
            while True:
                self.worker_vec = np.random.choice(a=[False, True], size=(worker_cnt))
                cnt = np.count_nonzero(self.worker_vec)
                if cnt > 0:
                    break
        else:
            self.worker_vec = np.ones(worker_cnt, dtype=bool)

        self.indigo_flows = []
        for worker_idx in range(worker_cnt):
            if not self.worker_vec[worker_idx]:
                self.indigo_flows.append(IndigoFlow(worker_idx, False, 0, 0, 0))
                continue

            # determine start delay
            start_delay = 0
            has_start_delay = self.enable_worker_start_delay and (0.1 > np.random.random_sample())
            if has_start_delay:
                start_delay = int(np.random.exponential())

            # determine the initinal link delay
            initial_link_delay = np.random.randint(10, 100)

            self.indigo_flows.append(IndigoFlow(worker_idx, True, start_delay, initial_link_delay, initial_link_delay))

        self.iperf_flows = []
        # initialize iperf flows (if enabled)
        if self.enable_iperf_flows:
            iperf_flow_vec = np.random.choice(a=[False, True], size=(worker_cnt), p=(0.9, 0.1))
            iperf_flow_vec = np.logical_and(np.logical_not(self.worker_vec), iperf_flow_vec)
            iperf_flow_cnt = np.count_nonzero(iperf_flow_vec)
            indigo_flow_cnt = np.count_nonzero(self.worker_vec)
            assert(iperf_flow_cnt + indigo_flow_cnt <= worker_cnt)
            flow_cnt = indigo_flow_cnt + iperf_flow_cnt
            per_flow_bw = self.current_bw / float(flow_cnt)

            # create iperf flows
            for worker_idx in range(worker_cnt):
                if not iperf_flow_vec[worker_idx]:
                    continue
                self.iperf_flows.append(iPerfFlow(worker_idx, 0, per_flow_bw))

    def step(self, running_indigo_flow_cnt):
        """
        if self.ts == 0:
            self.ts += 1
            return StateUpdate(True, True, True)
        self.ts += 1
        """

        new_bw = False
        indigo_flows_update = False
        iperf_flows_udpate = False

        # update bandwidth
        adjust_bw = self.bandwidth_change_probability > np.random.random_sample()
        if adjust_bw:
            new_bw = True
            self.current_bw = np.random.choice(self.available_bandwidths, size=1)[0]
            print('new bw: {}'.format(self.current_bw))
            self.log(Event.NEW_BW, self.current_bw)

        # update workers
        for worker_idx in range(self.worker_cnt):
            flow = self.indigo_flows[worker_idx]
            if not flow.active:
                continue
            new_link_delay = flow.current_link_delay
            adjust_delay = self.enable_variational_delay and (self.delay_change_probability > np.random.random_sample())
            if adjust_delay:
                indigo_flows_update = True
                new_link_delay = np.random.normal(loc=flow.initial_link_delay, scale=0.1*flow.initial_link_delay)
                new_link_delay = max(flow.initial_link_delay, new_link_delay)
                print('worker {} new delay: {}'.format(worker_idx, new_link_delay))
                self.log(Event.NEW_DELAY, new_link_delay, worker=worker_idx)
            # create the new tuple
            self.indigo_flows[worker_idx] = IndigoFlow(worker_idx, True, flow.start_delay, flow.initial_link_delay, new_link_delay)

        # TODO update iperf flows
        if self.enable_iperf_flows:
            pass

        return StateUpdate(new_bw, indigo_flows_update, iperf_flows_udpate)

    def log(self, event, value, worker=-1):
        ts = time.time()
        with open(self.log_file, 'a', 0) as fd:
            fd.write('%.3f,%d,%d,%s\n' % (ts, event, worker, str(value)))

    def get_active_iperf_flows(self):
        return self.iperf_flows

    # in Mbps
    def get_bandwidth(self):
        return self.current_bw

    def get_loss_rate(self):
        return self.loss_rate

    def get_worker_vector(self):
        return self.worker_vec

    def get_indigo_flows(self):
        return self.indigo_flows

    # in bytes
    def get_queue_size(self):
        return self.queue_size

    def get_step_width(self):
        return self.scenario_config['step_width']


# min_rtt in ms
def calculate_cwnd(scenario, min_rtt, flow_cnt):
    if flow_cnt < 1:
        return int(default_cwnd)
    bw = scenario.get_bandwidth() * 1.e6 / 8. / 1.e3 # [bytes/ms]
    per_flow_bw = bw / float(flow_cnt)
    print('min_rtt: {} [ms] per_flow_bw: {} [bytes/ms]'.format(min_rtt, per_flow_bw))
    cwnd = per_flow_bw*min_rtt
    cwnd *= cwnd_correction_factor
    pkt_cwnd = int(cwnd / packet_size)
    return pkt_cwnd
