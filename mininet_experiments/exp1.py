#!/usr/bin/env python2

import time

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import dumpNodeConnections
from mininet.log import setLogLevel

from multiprocessing import Process
from util.monitor import monitor_qlen

"""
s1 ...(12.00Mbit 5ms delay) (12.00Mbit 5ms delay) 
Dumping host connections
h1 h1-eth0:s1-eth1
h2 h2-eth0:s1-eth2
"""

class SingleSwitchTopo(Topo):
    "Single switch connected to n hosts."
    def build(self, n=2):
        switch = self.addSwitch('s1')
        for h in range(n):
            # Each host gets 50%/n of system CPU
            host = self.addHost('h%s' % (h + 1), cpu=.5/n)
            # 12 Mbps, 5ms delay, 2% loss, 1000 packet queue
            #self.addLink(host, switch, bw=12, delay='5ms', loss=2, max_queue_size=1000, use_htb=True)
            self.addLink(host, switch, bw=12, delay='5ms', max_queue_size=1000, use_htb=True)

def perfTest():
    "Create network and run simple performance test"
#    topo = SingleSwitchTopo(n=4)
    topo = SingleSwitchTopo(n=2)
    # TODO remove CPU limit?
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()
    print "Dumping host connections"
    dumpNodeConnections( net.hosts )
    print "Testing network connectivity"
    net.pingAll()
    print "Testing bandwidth between h1 and h4"
#    h1, h4 = net.get( 'h1', 'h4' )
#    net.iperf( (h1, h4) )
    h1, h2 = net.get('h1', 'h2')
#    net.iperf((h1, h2))

    # start qlen monitor
    monitor = Process(target=monitor_qlen, args=('s1-eth1', 0.01, '/tmp/qlen_s1-eth1.txt'))
    monitor.start()

    # activate conda env
    h1.cmd('export PATH=/home/josef/opt/anaconda2/bin:$PATH && source activate idp-python2-env')
    h2.cmd('export PATH=/home/josef/opt/anaconda2/bin:$PATH && source activate idp-python2-env')

    # run indigo (sender first)
    port = 5432
    """
    # usage: run_sender.py [-h] [--debug] port
    inst1 = h1.popen('perl', '../dagger/run_sender.py', port)
    # usage: run_receiver.py [-h] IP port
    inst2 = h2.popen('perl', '../env/run_receiver.py', h1.IP(), port)

    time.sleep(60)

    inst1.terminate()
    inst2.terminate()
    """
    h1.cmd('../dagger/run_sender.py %d &' % port)
    # remove the conda prompt e.g. '29836\r\n(idp-python2-env) '
    sender_pid = int(h1.cmd('echo $!').splitlines()[0])
    h2.cmd('../env/run_receiver.py %s %d &' % (str(h1.IP()), port))
    receiver_pid = int(h2.cmd('echo $!').splitlines()[0])

    time.sleep(30)
    net.iperf(hosts=(h1, h2), l4Type='UDP', udpBw='6M', seconds=30)
    time.sleep(30)

    h1.cmd('kill %d' % sender_pid)
    h2.cmd('kill %d' % receiver_pid)
#    net.iperf()

    monitor.terminate()


    net.stop()

if __name__ == '__main__':
    setLogLevel( 'info' )
    perfTest()
    # TODO copy results
