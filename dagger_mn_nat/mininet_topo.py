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
#from util.monitor import monitor_qlen, monitor_dropped # TODO


from helpers.nat_ipc import IndigoIpcMininetView

from dagger_mn_nat.scenarios import Scenario, calculate_cwnd


#port = 5555
number_of_episodes = 1000


class TrainingTopo(Topo):
    def build(self, worker_hosts, ps_hosts, nat_ip):
        s1 = self.addSwitch('s1') # nat switch
        s2 = self.addSwitch('s2') # workers are connected to this switch
        s3 = self.addSwitch('s3') # receiver are connected to this switch

        nat1 = self.addNode('nat1', cls=NAT, ip=nat_ip, inNamespace=False)
        self.addLink(nat1, s1)

        worker_cnt = len(worker_hosts)
        for i in range(worker_cnt):
#           worker_host = self.addHost('h{0}'.format(i), ip='{0}/8'.format(worker_hosts[i]), defaultRoute='via ' + nat_ip)
            worker_host = self.addHost('h{0}'.format(i), ip='{0}/8'.format(worker_hosts[i]))
            print(worker_host)
#            for ps_host in ps_hosts:
#                worker_host.cmd('ip route add {0} via {1}'.format(ps_host, nat_ip))
            self.addLink(worker_host, s1)
            self.addLink(worker_host, s2)
        for i in range(worker_cnt):
            receiver_host = self.addHost('h{0}'.format(worker_cnt - i))
            self.addLink(receiver_host, s3)

        # TODO
        # 12 Mbps, 5ms delay, 1000 packet queue
        self.addLink(s2, s3, bw=12, delay='5ms', max_queue_size=1000, use_htb=True)


def strip_port(arg):
    i = arg.rfind(':')
    return arg[0:i]


class Controller(object):
    def __init__(self, args):
        self.args = args
        self.worker_hosts = [strip_port(host) for host in args.local_worker_hosts.split(',')]
        self.ps_hosts = [strip_port(host) for host in args.ps_hosts.split(',')]
        print(self.worker_hosts)
        self.worker_cnt = len(self.worker_hosts)
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
        topo = TrainingTopo(self.worker_hosts, self.ps_hosts, self.args.nat_ip)
        self.net = Mininet(topo=topo, link=TCLink)
        # set up routing table
        for i in range(self.worker_cnt):
            worker_host = self.net.get('h{0}'.format(i))
#            worker_host.cmd('ip route add default gw ' + self.args.nat_ip)
#            for ps_host in self.ps_hosts:
#                worker_host.cmd('ip route add {0} via {1} h{2}-eth1'.format(ps_host, self.args.nat_ip, i))
            worker_host.cmd('ip route flush table main')
            worker_host.cmd('ip route add {0}/32 dev h{1}-eth0'.format(self.args.nat_ip, i))
            worker_host.cmd('ip route add 10.0.0.0/24 dev h{0}-eth1'.format(i)) # FIXME extract net address form self.args.nat_ip
            worker_host.cmd('ip route add default via {0}'.format(self.args.nat_ip))

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
        if self.current_indigo_flows is None:
            self.current_indigo_flows = scenario_indigo_flows
            return

        # update flows
        for worker_idx in range(self.worker_cnt):
            current_flow = self.current_indigo_flows[worker_idx]
            scenario_flow = scenario_indigo_flows[worker_idx]
            if current_flow == scenario_flow:
                continue
            # update current_link_delay (the only mutable attribute at the present time)
            if current_flow.current_link_delay != scenario_flow.current_link_delay:
                pass # TODO
            self.current_indigo_flows[worker_idx] = scenario_flow

    def adjust_network_parameters(self, scenario):
        new_bw = scenario.get_bandwidth()
        new_loss_rate = scenario.get_loss_rate()

        # tc qdisc add dev eth0 root tbf rate 1024kbit
        # limit the outgoing traffic on the worker side
        worker_switch = self.net.get('s2')
        worker_switch.cmd() # TODO

        receiver_switch = self.net.get('s3')
        receiver_switch.cmd() # TODO

        for i in range(self.worker_cnt):
            worker_host = self.net.get('h{0}'.format(i))
            current_flow = self.current_indigo_flows[worker_idx]
            # update individual delays
            worker_host.cmd('tc ...  h{0}-eth1'.format(i)) # TODO
            # TODO

        pass # TODO

    def update_cwnd_values(self, scenario):
        for worker_idx in range(self.worker_cnt):
            ipc = self.worker_ipc_objects[worker_idx]
            min_rtt = ipc.get_min_rtt()
            # min_rtt == 0 => min_rtt = initial_link_delay*2
            if min_rtt == 0:
                current_flow = self.current_indigo_flows[worker_idx]
                min_rtt = current_flow.initial_link_delay*2
            cwnd = calculate_cwnd(scenario, worker_idx, min_rtt)
            ipc.set_cwnd(cwnd)

    def scenario_loop(self, scenario):
        self.current_indigo_flows = None
        self.active_iperf_flows = []

        while not self.stop:
            scenario.step()

            new_flows = scenario.get_active_iperf_flows()
            self.udpate_iperf_flows(new_flows)

            scenario_indigo_flows = scenario.get_indigo_flows()
            self.update_indigo_flows(scenario_indigo_flows)

            self.adjust_network_parameters(scenario)

            self.update_cwnd_values(scenario)

# FIXME division by zero when idle==True
            time.sleep(0.5) # TODO

#            print('scenario_loop: checking rollout requests...')
            self.resume_cv.acquire()
            notify = self.rollout_requests == self.worker_cnt
#            print('scenario_loop: checking rollout requests - notify: %d' % notify)
            if notify:
                print('notifying workers...')
                self.rollout_requests = 0
                self.resume_cv.notify_all()
                self.resume_cv.release()
                return
            self.resume_cv.release()

    def run(self):
        self.net.start()

        CLI(self.net)

        self.start_workers()

        for _ in range(number_of_episodes):
            if self.stop:
                break
            scenario = Scenario(self.worker_cnt)
            # set up worker parameters
            active_workers = scenario.get_active_worker_vector()
            indigo_flows = scenario.get_indigo_flows()
            for i in range(self.worker_cnt):
                indigo_flow = indigo_flows[i]
                ipc = self.worker_ipc_objects[i]
                ipc.set_idle_state(not active_workers[i])
                ipc.set_start_delay(indigo_flow.start_delay)
            self.update_cwnd_values(scenario)

            self.scenario_loop(scenario)

#        CLI(self.net)

        print("run() stopping network")
        self.net.stop()

    def start_receiver(self, worker_idx):
        ipc = self.worker_ipc_objects[worker_idx]
        port = ipc.get_port()
        worker_host = self.net.get('h{0}'.format(worker_idx))
        receiver_host = self.net.get('h{0}'.format(self.worker_cnt - worker_idx))
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
        for i in range(self.worker_cnt):
            worker_host = self.net.get('h{0}'.format(i))
            full_worker_host_list = self.args.local_worker_hosts
            if self.args.remote_worker_hosts:
                full_worker_host_list += ',' + self.args.remote_worker_hosts
            worker_cmd = './worker.py ' \
                         '--job-name worker ' \
                         '--worker-id {0} ' \
                         '--task-index {1} ' \
                         '--ps-hosts {2} ' \
                         '--worker-hosts {3} >indigo-worker-out.txt 2>&1 &' \
                         .format(i, self.args.task_index, self.args.ps_hosts, full_worker_host_list)
            print("worker_cmd: {0}".format(worker_cmd))
            # start worker
            worker_host.cmd(worker_cmd)
            worker_pid = int(worker_host.cmd('echo $!'))
            self.worker_pids[i] = worker_pid
            print("worker started")

    def stop_receiver(self, worker_idx):
        if self.receiver_pids[worker_idx] is None:
            return
        receiver_host = self.net.get('h{0}'.format(self.worker_cnt - worker_idx))
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
        # TODO obtain a new scenario
        for ipc in self.worker_ipc_objects:
            ipc.finalize_rollout_request()

    def handle_rollout_request(self, worker_idx, ipc):
        self.resume_cv.acquire()
        self.rollout_requests += 1
        print('waiting on cv')
        self.resume_cv.wait()
        self.resume_cv.release()
        # clear receiver state
        self.restart_receiver(worker_idx)
        print('rollout request handler finished')
        ipc.finalize_rollout_request()

    def handle_cleanup_request(self):
        self.stop = True
        self.stop_workers()
        self.stop_receivers()

    def handle_request(self, request, params):
        try:
            worker_idx = params[0]
            worker_ipc = params[1]
            print('in handle_request() - params %s' % str(params))
            print("received request: %s" % str(request))
            if request == 'rollout':
                self.handle_rollout_request(worker_idx, worker_ipc)
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
        '--local-worker-hosts', required=True, metavar='[HOSTNAME:PORT, ...]',
        help='comma-separated list of hostname:port of workers')
    parser.add_argument(
        '--nat-ip', required=True, metavar='<IPv4 address>')
    parser.add_argument(
        '--remote-worker-hosts', required=False, metavar='[HOSTNAME:PORT, ...]',
        help='comma-separated list of hostname:port of workers')
    parser.add_argument('--task-index', metavar='N', type=int, required=True,
                        help='index of task')
    args = parser.parse_args()

    controller = Controller(args)
    controller.run()


if __name__ == '__main__':
    main()
