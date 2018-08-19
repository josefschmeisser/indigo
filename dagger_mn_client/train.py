#!/usr/bin/env python2

import time
import os
import shutil

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import dumpNodeConnections, pmonitor
from mininet.log import setLogLevel

from multiprocessing import Process
from util.monitor import monitor_qlen, monitor_dropped

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

def setup():
    "Create network and run simple performance test"
    topo = TwoSwitchTopo()
    net = Mininet(topo=topo, link=TCLink)
    net.start()

    h1, h2 = net.get('h1', 'h2')


    # run indigo (sender first)
    port = 5432

    h1.cmd('../dagger/worker.py %d &' % port)
    dagger_pid = int(h1.cmd('echo $!')
    h2.cmd('../env/run_receiver.py %s %d &' % (str(h1.IP()), port))
    receiver_pid = int(h2.cmd('echo $!')

    net.stop()

if __name__ == '__main__':
    setup()
