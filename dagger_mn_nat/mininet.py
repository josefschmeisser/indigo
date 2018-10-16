#!/usr/bin/env python2

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


class TwoSwitchTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')

        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        self.addLink(h1, s1)
        self.addLink(s2, h2)

        # 12 Mbps, 5ms delay, 1000 packet queue
        self.addLink(s1, s2, bw=12, delay='5ms', max_queue_size=1000, use_htb=True)


class Controller(object):
    def __init__(self, worker_cnt):
        self.worker_cnt = worker_cnt
        self.worker_ipc_objects = []
        self.worker_pids = []
        self.receiver_pids = []

        for i in range(worker_cnt):
            ipc = IndigoIpcMininetView(i)
            ipc.set_handler_fun(self.handle_request, (i, ipc))
            self.worker_ipc_objects.append(ipc)

#        self.sem = threading.Semaphore(value=0)

        self.lock = threading.Lock()

        self.resume_cv = threading.Condition()

        self.change_scenario = True
        self.rollout_requests = 0


        self.setup_net()

    def setup_net(self):
        "Create network and run simple performance test"
        topo = TwoSwitchTopo()
        self.net = Mininet(topo=topo, link=TCLink)

    def scenario_loop(self):
        pass # TODO
        while True:
            # do some stuff

            # TODO write cwnds

            time.sleep(0.5) # TODO

            notify = False
            with self.lock:
                notify = self.rollout_requests == self.worker_cnt
                if notify:
                    self.worker_cnt = 0
            if notify:
                self.resume_cv.notify_all()

    def run(self):
        self.net.start()

        h1 = self.net.get('h1')

        print("starting worker.py...")

        task_index = 1 # TODO
        worker_cmd = './mn_worker ...' # TODO
        h1.cmd('./worker.py --task-index %d >indigo-worker-out.txt 2>&1' % task_index)
        self.worker_pid = int(h1.cmd('echo $!'))
        print("worker started")

#        self.ipc.set_cwnd(5) # TODO adjust

        # wait
#        self.sem.acquire()

        self.scenario_loop()

        print("run() stopping network")
        self.net.stop()

    def start_receivers(self):
        for i in range(self.worker_cnt):
            pass
            # TODO
        """
        h1, h2 = self.net.get('h1', 'h2')
        port = self.ipc.get_port()
        h2.cmd('../env/run_receiver.py %s %d &' % (str(h1.IP()), port))
        self.receiver_pid = int(h2.cmd('echo $!'))
        """

    def stop_receivers(self):
        pass
        # TODO
        """
        if self.receiver_pid is None:
            return
        h2 = self.net.get('h2')
        h2.cmd('kill', self.receiver_pid)
        self.receiver_pid = None
        """

    def rollout(self):
        # TODO wait until the queues are empty
        # TODO obtain a new 
        for ipc in self.worker_ipc_objects:
            ipc.finalize_rollout_request()

    def handle_rollout_request(self):
        with self.lock:
            self.rollout_requests += 1
        self.resume_cv.wait()

        pass

    """
    def cleanup(self):
        self.sem.release()
    """
    """
    def handle_reset_request(self):
        print('sleeping')
        time.sleep(2.0) # FIXME use queue monitor
        self.ipc.finalize_reset_request()
    """

    def handle_request(self, request):
        try:
            print('in handle_request()')
#            request = self.ipc.get_message()
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

# TODO exception handling
if __name__ == '__main__':
    controller = Controller(worker_cnt = 5)
    controller.run()
