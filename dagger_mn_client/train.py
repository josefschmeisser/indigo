#!/usr/bin/env python2

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


from helpers.ipc import IndigoIpcMininetView


class TwoSwitchTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')

        h1 = self.addHost('h1')
        h2 = self.addHost('h2')

        self.addLink(h1, s1)
        self.addLink(s2, h2)

        # 12 Mbps, 5ms delay, 2% loss, 1000 packet queue
        self.addLink(s1, s2, bw=12, delay='10ms', max_queue_size=1000, use_htb=True)


class Controller(object):
    def __init__(self):
        self.ipc = IndigoIpcMininetView()
        self.ipc.set_handler_fun(self.handle_request, None)

        self.sem = threading.Semaphore(value=0)

        self.worker_pid = None
        self.receiver_pid = None

        self.setup_net()

    def setup_net(self):
        "Create network and run simple performance test"
        topo = TwoSwitchTopo()
        self.net = Mininet(topo=topo, link=TCLink)

    def run(self):
        self.net.start()
#        h1, h2 = self.net.get('h1', 'h2')
        h1 = self.net.get('h1')
#        port = self.ipc.get_port()
        print("starting worker.py...")
#        h1.cmd('./worker.py %d &' % port)
        task_index = 1 # TODO
        h1.cmd('./worker.py --task-index %d > indigo-worker-out.txt' % task_index)
        self.worker_pid = int(h1.cmd('echo $!'))
        print("worker started")

        # wait
        self.sem.acquire()

        print("run() stopping network")
        self.net.stop()

    def start_receiver(self):
        h1, h2 = self.net.get('h1', 'h2')
        port = self.ipc.get_port()
        h2.cmd('../env/run_receiver.py %s %d &' % (str(h1.IP()), port))
        self.receiver_pid = int(h2.cmd('echo $!'))

    def cleanup(self):
        self.sem.release()

    def handle_reset_request(self):
        time.sleep(2.0) # FIXME use queue monitor
        self.ipc.finalize_reset_request()

    def handle_start_receiver_request(self):
        self.start_receiver()
        self.ipc.finalize_start_receiver_request()

    def handle_request(self, request):
        print("received request: %s" % request)
        if request == 'reset':
            self.handle_reset_request()
        elif request == 'start_receiver':
            self.handle_start_receiver_request()
        else:
            print('unknown request: %s' % request)


if __name__ == '__main__':
    controller = Controller()
    controller.run()
