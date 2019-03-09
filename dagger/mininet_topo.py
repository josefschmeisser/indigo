#!/usr/bin/env python2

import argparse
import sys
import time
import os
import shutil
import threading
import project_root

from mininet.cli import CLI
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.nodelib import NAT
from mininet.link import TCLink
from mininet.util import dumpNodeConnections, pmonitor
from mininet.log import setLogLevel
from multiprocessing import Process
from dagger.scenarios import Scenario, calculate_cwnd
from helpers.config import config, get_full_worker_list, get_our_worker_list, get_ps_list
from helpers.nat_ipc import IndigoIpcMininetView

number_of_episodes = 1000
burst_rate = 2000


class TrainingTopo(Topo):
    def build(self, worker_hosts, nat_ip):
        s1 = self.addSwitch('s1') # nat switch
        s2 = self.addSwitch('s2') # workers are connected to this switch
        s3 = self.addSwitch('s3') # receiver are connected to this switch

        nat1 = self.addNode('nat1', cls=NAT, ip=nat_ip, inNamespace=False)
        self.addLink(nat1, s1)
        self.addLink(s2, s3)

        worker_cnt = len(worker_hosts)
        for i in range(worker_cnt):
            worker_host = self.addHost('h{0}'.format(i), ip='{0}/8'.format(worker_hosts[i]))
            print(worker_host)
            self.addLink(worker_host, s1)
            self.addLink(worker_host, s2)
        for i in range(worker_cnt):
            receiver_host = self.addHost('h{0}'.format(2*worker_cnt - i))
            self.addLink(receiver_host, s3)


def strip_port(arg):
    i = arg.rfind(':')
    return arg[0:i]


class Controller(object):
    def __init__(self):
        self.config_section = config.get_our_section()
        self.nat_ip = self.config_section['nat_ip']

        self.our_worker_list = get_our_worker_list()
        self.full_worker_list = get_full_worker_list()
        self.worker_hosts_arg = ','.join([worker['address'] for worker in self.full_worker_list])
        print('worker_hosts_arg:', self.worker_hosts_arg)
        self.ps_list = get_ps_list()
        self.ps_hosts_arg = ','.join([ps['address'] for ps in self.ps_list])
        print('ps_hosts_arg:', self.ps_hosts_arg)

        self.worker_cnt = len(self.our_worker_list)
        self.worker_ipc_objects = []
        self.worker_pids = [None] * self.worker_cnt
        self.receiver_pids = [None] * self.worker_cnt

        for i in range(self.worker_cnt):
            ipc = IndigoIpcMininetView(i)
            ipc.set_handler_fun(self.handle_request, (i, ipc))
            self.worker_ipc_objects.append(ipc)

        self.resume_cv = threading.Condition()

        self.rollout_requests = 0
        self.stop = False

        self.setup_net()

    def setup_net(self):
        "Create network and run simple performance test"
        worker_ip_list = [strip_port(worker['address']) for worker in self.our_worker_list]
        topo = TrainingTopo(worker_ip_list, self.nat_ip)
        self.net = Mininet(topo=topo, link=TCLink)
        # set up routing table
        for i in range(self.worker_cnt):
            internal = '.'.join(self.nat_ip.split('.')[0:-1]) + '.0/24'
            worker_host = self.net.get('h{0}'.format(i))
            worker_host.cmd('ip route flush table main')
            worker_host.cmd('ip route add {0}/32 dev h{1}-eth0'.format(self.nat_ip, i))
            worker_host.cmd('ip route add {0} dev h{1}-eth1'.format(internal, i))
            worker_host.cmd('ip route add default via {0}'.format(self.nat_ip))

    def udpate_iperf_flows(self, new_flows):
        # terminate obsolete flows
        for flow, pid in self.active_iperf_flows:
            if not flow in new_flows:
                host = self.net.get(flow.host_name)
                host.cmd('kill', pid)
            else:
                new_flows.remove(flow)
        # start new flows
        for flow in new_flows:
            host = self.net.get(flow.host_name)
            perf_cmd = '' # TODO cmd
            host.cmd(perf_cmd)
            pid = int(host.cmd('echo $!'))
            self.active_iperf_flows.append((flow, pid))

    def update_indigo_flows(self, scenario_indigo_flows):
        update_all = False
        if self.current_indigo_flows is None:
            self.current_indigo_flows = scenario_indigo_flows
            update_all = True

        # update flows
        for worker_idx in range(self.worker_cnt):
            current_flow = self.current_indigo_flows[worker_idx]
            scenario_flow = scenario_indigo_flows[worker_idx]
            # update current_link_delay (the only mutable attribute at the present time)
            if update_all or (current_flow.current_link_delay != scenario_flow.current_link_delay):
                worker_host = self.net.get('h{0}'.format(worker_idx))
                tc_cmd = 'tc qdisc change dev h{0}-eth1 root netem delay {1}ms'
                tc_cmd = tc_cmd.format(worker_idx, scenario_flow.current_link_delay)
                worker_host.cmd(tc_cmd)
            # remember the current state
            self.current_indigo_flows[worker_idx] = scenario_flow

    def initialize_network_parameters(self):
        worker_switch = self.net.get('s2')
        worker_switch.cmd('tc qdisc add dev s2-eth1 root tbf rate 10mbit burst {0} limit 10000'.format(burst_rate))
        for worker_idx in range(self.worker_cnt):
            worker_host = self.net.get('h{0}'.format(worker_idx))
            worker_host.cmd('tc qdisc add dev h{0}-eth1 root netem delay 5ms'.format(worker_idx))

    def adjust_global_network_parameters(self, scenario):
        new_bw = scenario.get_bandwidth() # [Mbps]

        new_loss_rate = scenario.get_loss_rate()
        loss_arg = 'loss 0%' # TODO
        if new_loss_rate > 0.0:
            loss_arg = 'loss {0}%'.format(new_loss_rate*100.0)

        # limit the outgoing traffic on the worker side
        worker_switch = self.net.get('s2')
#        worker_switch.cmd('tc qdisc add dev eth0 root netem {0}'.format(loss_arg))
        limit = scenario.get_queue_size() # in bytes
        worker_switch.cmd('tc qdisc change dev s2-eth1 root tbf rate {0}mbit burst {1} limit {2}'.format(new_bw, burst_rate, limit))

    def count_active_indigo_flows(self):
        cnt = 0
        for worker_idx in range(self.worker_cnt):
            ipc = self.worker_ipc_objects[worker_idx]
            cnt += int(ipc.get_flow_is_active())
        return cnt

    def count_initial_indigo_flows(self, flows):
        cnt = 0
        for flow in flows:
            cnt += int(flow.active and flow.start_delay == 0)
        return cnt

    def wait_for_first_indigo_flow(self):
        while True:
            for worker_idx in range(self.worker_cnt):
                ipc = self.worker_ipc_objects[worker_idx]
                if ipc.get_flow_is_active():
                    return

    def update_cwnd_values(self, scenario, flow_cnt):
        for worker_idx in range(self.worker_cnt):
            current_flow = self.current_indigo_flows[worker_idx]
            if not current_flow.active:
                continue
            ipc = self.worker_ipc_objects[worker_idx]

            # calculate new cwnd
            cwnd = calculate_cwnd(scenario, current_flow.current_link_delay, flow_cnt)
            print('worker {} new cwnd: {} min_rtt: {} theoretical rtt: {}'.format(worker_idx, cwnd, ipc.get_min_rtt(), current_flow.current_link_delay))
            bw = scenario.get_bandwidth() # [Mbps]
            assert(flow_cnt > 0)
            opt_tput = bw / float(flow_cnt)
            ipc.update_optimal_params(cwnd, current_flow.current_link_delay, opt_tput)

    def perform_initialization(self, scenario):
        scenario_indigo_flows = scenario.get_indigo_flows()
        initial_indigo_flow_cnt = self.count_initial_indigo_flows(scenario_indigo_flows)
        active_iperf_flows = scenario.get_active_iperf_flows()
        flow_cnt = initial_indigo_flow_cnt + len(active_iperf_flows)

        # update parameters
        self.adjust_global_network_parameters(scenario)
        self.udpate_iperf_flows(active_iperf_flows)
        self.update_indigo_flows(scenario_indigo_flows)
        self.update_cwnd_values(scenario, flow_cnt)

    def perform_step(self, scenario):
        active_indigo_flow_cnt = self.count_active_indigo_flows()
        state_update = scenario.step(active_indigo_flow_cnt)

        scenario_indigo_flows = scenario.get_indigo_flows()
        active_indigo_flow_cnt = self.count_active_indigo_flows()

        active_iperf_flows = scenario.get_active_iperf_flows()
        flow_cnt = active_indigo_flow_cnt + len(active_iperf_flows)

        # update parameters
        if state_update.new_bw:
            self.adjust_global_network_parameters(scenario)
        if state_update.iperf_flows_udpate:
            self.udpate_iperf_flows(active_iperf_flows)
        if state_update.indigo_flows_update:
            self.update_indigo_flows(scenario_indigo_flows)
        if flow_cnt > 0:
            self.update_cwnd_values(scenario, flow_cnt)

    def waiting_for_rollout(self):
        self.resume_cv.acquire()
        notify = self.rollout_requests == self.worker_cnt
        if notify:
            self.rollout_requests = 0
        self.resume_cv.release()
        return notify

    def wait_for_rollout(self):
        while True:
            if self.waiting_for_rollout():
                return

    def execute_scenario(self, scenario):
        # reset
        self.active_iperf_flows = []
        self.current_indigo_flows = None

        # set up worker parameters
        active_workers = scenario.get_worker_vector()
        indigo_flows = scenario.get_indigo_flows()
        for i in range(self.worker_cnt):
            indigo_flow = indigo_flows[i]
            ipc = self.worker_ipc_objects[i]
            ipc.set_idle_state(not active_workers[i])
            ipc.set_start_delay(indigo_flow.start_delay)

        # update parameters
        self.perform_initialization(scenario)

        # finalize rollout
        print('notifying workers...')
        self.resume_cv.acquire()
        self.resume_cv.notify_all()
        self.resume_cv.release()

        self.wait_for_first_indigo_flow()

        step_width = scenario.get_step_width()
        while not self.stop:
            time.sleep(step_width)
            print 'execute_scenario() new step'
            self.perform_step(scenario)

            """
            if scenario.ts == 10:
                CLI(self.net)
            """
            """
            if scenario.ts > 10 and scenario.current_bw == 15:
                self.stop_workers()
                CLI(self.net)
                exit(0)
            """

            if self.waiting_for_rollout():
                return


            """
            self.resume_cv.acquire()
            notify = self.rollout_requests == self.worker_cnt
            if notify:
                print('starting new episode; notifying workers...')
                self.rollout_requests = 0
                self.resume_cv.notify_all()
                self.resume_cv.release()
                return
            self.resume_cv.release()
            """


    def run(self):
        self.net.start()

#        CLI(self.net)

        self.initialize_network_parameters()
        self.start_workers()

        self.wait_for_rollout()

        scenario = Scenario()
        for _ in range(number_of_episodes):
            if self.stop:
                break
            scenario.set_up_new_epoch(self.worker_cnt)
            self.execute_scenario(scenario)

#        CLI(self.net)

        print("run() stopping network")
        self.net.stop()

    def start_receiver(self, worker_idx):
        ipc = self.worker_ipc_objects[worker_idx]
        port = ipc.get_port()
        worker_host = self.net.get('h{0}'.format(worker_idx))
        receiver_host = self.net.get('h{0}'.format(2*self.worker_cnt - worker_idx))
        receiver_cmd = '../env/run_receiver.py %s %d &' % (str(worker_host.IP()), port)
        receiver_host.cmd(receiver_cmd)
        receiver_pid = int(receiver_host.cmd('echo $!'))
        self.receiver_pids[worker_idx] = receiver_pid

    def start_receivers(self):
        print("starting receivers...")
        for i in range(self.worker_cnt):
            self.start_receiver(i)

    def start_workers(self):
        print("starting workers...")
        worker_idx = 0
        for worker_desc in self.our_worker_list:
            worker_host = self.net.get('h{0}'.format(worker_idx))
            """
            worker_cmd = './worker.py ' \
                         '--job-name worker ' \
                         '--worker-id {0} ' \
                         '--task-index {1} ' \
                         '--ps-hosts {2} ' \
                         .format(worker_idx, worker_desc['task_index'], self.ps_hosts_arg, self.worker_hosts_arg)
            """
            worker_cmd = './worker.py ' \
                         '--job-name worker ' \
                         '--worker-id {0} ' \
                         '--task-index {1} ' \
                         '--ps-hosts {2} ' \
                         '--worker-hosts {3} >worker{0}-out.txt 2>&1 &' \
                         .format(worker_idx, worker_desc['task_index'], self.ps_hosts_arg, self.worker_hosts_arg)
            print("worker_cmd: {0}".format(worker_cmd))
            # start worker
            worker_host.cmd(worker_cmd)
            worker_pid = int(worker_host.cmd('echo $!'))
            self.worker_pids[worker_idx] = worker_pid
            print("worker started")

            worker_idx += 1

    def stop_receiver(self, worker_idx):
        if self.receiver_pids[worker_idx] is None:
            return
        receiver_host = self.net.get('h{0}'.format(2*self.worker_cnt - worker_idx))
        receiver_host.cmd('kill', self.receiver_pids[worker_idx])
        self.receiver_pids[worker_idx] = None

    def stop_receivers(self):
        for i in range(self.worker_cnt):
            self.stop_receiver(i)

    def stop_workers(self):
        for i in range(self.worker_cnt):
            worker_host = self.net.get('h{0}'.format(i))
            worker_host.cmd('kill', self.worker_pids[i])
            self.worker_pids[i] = None

    def restart_receiver(self, worker_idx):
        self.stop_receiver(worker_idx)
        self.start_receiver(worker_idx)

    def rollout(self):
        # TODO wait until the queues are empty
        for ipc in self.worker_ipc_objects:
            ipc.finalize_rollout_request()

    def handle_rollout_request(self, worker_idx, ipc):
        self.resume_cv.acquire()
        self.rollout_requests += 1
#        print('waiting on cv')
        self.resume_cv.wait()
        self.resume_cv.release()
        # clear receiver state
        self.restart_receiver(worker_idx)
#        print('rollout request handler finished')
        ipc.finalize_rollout_request()

    def handle_cleanup_request(self):
        self.stop = True
        self.stop_workers()
        self.stop_receivers()

    def handle_request(self, request, params):
        try:
            worker_idx = params[0]
            worker_ipc = params[1]
#            print('in handle_request() - params %s' % str(params))
#            print("received request: %s" % str(request))
            if request == 'rollout':
                self.handle_rollout_request(worker_idx, worker_ipc)
            elif request == 'cleanup':
                self.handle_cleanup_request()
            else:
                print('unknown request: %s' % str(request))
        except:
            e = sys.exc_info()[0]
            print('exception in handle_request(): %s' % str(e))
