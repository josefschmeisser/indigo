#!/usr/bin/env python2

import argparse
import sys
import time
import os
import shutil
import threading
import project_root

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import dumpNodeConnections, pmonitor
from mininet.log import setLogLevel

from multiprocessing import Process
#from util.monitor import monitor_qlen, monitor_dropped # TODO


from helpers.nat_ipc import IndigoIpcMininetView

from dagger_mn_nat.scenarios import obtain_scenario, Scenario


port = 5000
number_of_episodes = 1000


class TwoSwitchTopo(Topo):
    def build(self, worker_hosts):
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')

        """
        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        self.addLink(h1, s1)
        self.addLink(s2, h2)
        """
        worker_cnt = len(worker_hosts)
        for i in range(worker_cnt):
            worker_host = self.addHost('h{0}'.format(i), ip=worker_hosts[i]) # TODO subnet?
            self.addLink(worker_host, s1)
            receiver_host = self.addHost('h{0}'.format(worker_cnt - i))
            self.addLink(receiver_host, s2)

        # TODO
        # 12 Mbps, 5ms delay, 1000 packet queue
        self.addLink(s1, s2, bw=12, delay='5ms', max_queue_size=1000, use_htb=True)


class Controller(object):
    def __init__(self, args):
        self.args = args
        self.worker_hosts = args.worker_hosts.split(',')
        self.worker_cnt = len(self.worker_hosts)
        self.worker_ipc_objects = []
        self.worker_pids = []
        self.receiver_pids = []

        self.active_flows = []

        for i in range(self.worker_cnt):
            ipc = IndigoIpcMininetView(i)
            ipc.set_handler_fun(self.handle_request, (i, ipc))
            self.worker_ipc_objects.append(ipc)

        self.lock = threading.Lock()
        self.resume_cv = threading.Condition()

        self.rollout_requests = 0
        self.stop = False

        self.setup_net()

    def setup_net(self):
        "Create network and run simple performance test"
        topo = TwoSwitchTopo(self.worker_hosts)
        self.net = Mininet(topo=topo, link=TCLink)

    def udpate_iperf_flows(self, new_flows):
        # terminate obsolete flows
        for flow, pid in self.active_flows:
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
            self.active_flows.append((flow, pid))

    def adjust_network_parameters(self, scenario):
        pass # TODO

    def scenario_loop(self, scenario):
        while not self.stop:
            scenario.step()

            new_flows = scenario.get_active_flows()
            self.udpate_iperf_flows(new_flows)

            self.adjust_network_parameters(scenario)

            active_workers = scenario.get_active_workers()
            for i in range(self.worker_cnt):
                ipc = self.worker_ipc_objects[i]
                ipc.set_cwnd(scenario.get_cwnd())
                ipc.set_idle_state(active_workers[i])

            time.sleep(0.5) # TODO

            notify = False
            with self.lock:
                notify = self.rollout_requests == self.worker_cnt
                if notify:
                    self.worker_cnt = 0
            if notify:
                self.resume_cv.notify_all()

    def run(self):
        self.net.addNAT().configDefault()
        self.net.start()

        self.start_workers()
        self.start_receivers()

        for _ in range(number_of_episodes):
            if self.stop:
                break
            scenario = obtain_scenario(self.worker_cnt)
            self.scenario_loop(scenario)

        print("run() stopping network")
        self.net.stop()

    def start_receivers(self):
        print("starting receivers...")
        for i in range(self.worker_cnt):
            worker_host =self.net.get('h{0}'.format(i))
            receiver_host = self.net.get('h{0}'.format(self.worker_cnt - i))
            receiver_cmd = '../env/run_receiver.py %s %d &' % (str(worker_host.IP()), port)
            receiver_host.cmd(receiver_cmd)
            receiver_pid = int(receiver_host.cmd('echo $!'))
            self.receiver_pids.append(receiver_pid)

    def start_workers(self):
        print("starting workers...")
        for i in range(self.worker_cnt):
            worker_host = self.net.get('h{0}'.format(i))
            worker_cmd = './worker ' \
                         '--job-name worker ' \
                         '--task-index {0} ' \
                         '--ps-hosts {1} ' \
                         '--worker-hosts {2}' \
                         .format(self.args.task_index, self.args.ps_hosts, self.args.worker_hosts)
            print("worker_cmd: {0}".format(worker_cmd))
            # start worker
            worker_host.cmd(worker_cmd)
            worker_pid = int(worker_host.cmd('echo $!'))
            self.worker_pids.append(worker_pid)
            print("worker started")

    def stop_receivers(self):
        for i in range(self.worker_cnt):
            receiver_host = self.net.get('h{0}'.format(self.worker_cnt - i))
            receiver_host.cmd('kill', self.receiver_pids[i])
        self.receiver_pids = []

    def stop_workers(self):
        for i in range(self.worker_cnt):
            worker_host = self.net.get('h{0}'.format(i))
            worker_host.cmd('kill', self.worker_pids[i])
        self.worker_pids = []

    def rollout(self):
        # TODO wait until the queues are empty
        # TODO obtain a new scenario
        for ipc in self.worker_ipc_objects:
            ipc.finalize_rollout_request()

    def handle_rollout_request(self):
        with self.lock:
            self.rollout_requests += 1
        self.resume_cv.wait()

    def handle_cleanup_request(self):
        self.stop = True
        self.stop_workers()
        self.stop_receivers()

    def handle_request(self, request):
        try:
            print('in handle_request()')
            print("received request: %s" % str(request))
            if request == 'rollout':
                self.handle_rollout_request()
            elif request == 'cleanup':
                self.handle_cleanup_request()
            else:
                print('unknown request: %s' % str(request))
        except:
            e = sys.exc_info()[0]
            print('exception in handle_request(): %s' % str(e))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--ps-hosts', required=True, metavar='[HOSTNAME:PORT, ...]',
        help='comma-separated list of hostname:port of parameter servers')
    parser.add_argument(
        '--worker-hosts', required=True, metavar='[HOSTNAME:PORT, ...]',
        help='comma-separated list of hostname:port of workers')
#    parser.add_argument('--job-name', choices=['ps', 'worker'],
#                        required=True, help='ps or worker')
    parser.add_argument('--task-index', metavar='N', type=int, required=True,
                        help='index of task')
    args = parser.parse_args()

    controller = Controller(args)
    controller.run()


if __name__ == '__main__':
    main()
