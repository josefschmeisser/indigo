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


from helpers.ipc import IndigoIpcMininetView


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
        h1.cmd('./worker.py --task-index %d >indigo-worker-out.txt 2>&1' % task_index)
        self.worker_pid = int(h1.cmd('echo $!'))
        print("worker started")

        self.ipc.set_cwnd(5) # TODO adjust

        # wait
        self.sem.acquire()

        print("run() stopping network")
        self.net.stop()

    def start_receiver(self):
        h1, h2 = self.net.get('h1', 'h2')
        port = self.ipc.get_port()
        h2.cmd('../env/run_receiver.py %s %d &' % (str(h1.IP()), port))
        self.receiver_pid = int(h2.cmd('echo $!'))

    def stop_receiver(self):
        if self.receiver_pid is None:
            return
        h2 = self.net.get('h2')
        h2.cmd('kill', self.receiver_pid)
        self.receiver_pid = None

    def cleanup(self):
        self.sem.release()

    def handle_reset_request(self):
        print('sleeping')
        time.sleep(2.0) # FIXME use queue monitor
        self.ipc.finalize_reset_request()

    def handle_start_receiver_request(self):
        self.start_receiver()
        self.ipc.finalize_start_receiver_request()

    def handle_stop_receiver_request(self):
        self.stop_receiver()
        print('receiver stopped')
        self.ipc.finalize_stop_receiver_request()

    def handle_request(self, request):
        try:
            print('in handle_request()')
#            request = self.ipc.get_message()
            print("received request: %s" % str(request))
            if request == 'reset':
                self.handle_reset_request()
            elif request == 'start_receiver':
                self.handle_start_receiver_request()
            elif request == 'stop_receiver':
                self.handle_stop_receiver_request()
            else:
                print('unknown request: %s' % str(request))
        except:
            e = sys.exc_info()[0]
            print('exception in handle_request(): %s' % str(e))


#my_controller = Controller()
#ipc = IndigoIpcMininetView()

"""
def request_handler(params):
    print('in request_handler()')
#    my_controller.handle_request(None)
    request = ipc.mn_msg_q.receive()
    print(request)
    print("received request: %s" % request)
"""
# TODO exception handling
if __name__ == '__main__':
    controller = Controller()
#    global my_controller
#    my_controller.ipc.set_handler_fun(request_handler, None)
#    ipc.set_handler_fun(request_handler, None)
    controller.run()
