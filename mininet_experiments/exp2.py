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

def perfTest():
    "Create network and run simple performance test"
    topo = TwoSwitchTopo()
    # TODO remove CPU limit?
    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()
    print "Dumping host connections"
    dumpNodeConnections( net.hosts )
    print "Testing network connectivity"
    net.pingAll()

    h1, h2 = net.get('h1', 'h2')

    # start monitors
    monitors = []
#    monitors.append(Process(target=monitor_qlen, args=('s1-eth1', 0.01, '/tmp/qlen_s1-eth1.txt')))
    monitors.append(Process(target=monitor_qlen, args=('s1-eth2', 0.01, '/tmp/qlen_s1-eth2.txt')))
#    monitors.append(Process(target=monitor_qlen, args=('s2-eth1', 0.01, '/tmp/qlen_s2-eth1.txt')))
#    monitors.append(Process(target=monitor_qlen, args=('s2-eth2', 0.01, '/tmp/qlen_s2-eth2.txt')))
#    monitors.append(Process(target=monitor_dropped, args=('s1-eth1', 0.01, '/tmp/dropped_s1-eth1.txt')))
    monitors.append(Process(target=monitor_dropped, args=('s1-eth2', 0.01, '/tmp/dropped_s1-eth2.txt')))
#    monitors.append(Process(target=monitor_dropped, args=('s2-eth1', 0.01, '/tmp/dropped_s2-eth1.txt')))
#    monitors.append(Process(target=monitor_dropped, args=('s2-eth1', 0.01, '/tmp/dropped_s2-eth2.txt')))
    for monitor in monitors:
        monitor.start()

    cmd = "from util.monitor import monitor_dropped; monitor_dropped(\"h2-eth0\", 0.01, \"/tmp/dropped_h2.txt\")"
    mp = h2.popen('python2', '-c', cmd)

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

    for monitor in monitors:
        monitor.terminate()
    mp.kill()

    net.stop()

if __name__ == '__main__':
    setLogLevel( 'info' )
    perfTest()
    
    # copy results
    results_path = './results/exp2/'
    if not os.path.exists(results_path):
        os.makedirs(results_path)
    files = os.listdir(results_path)
    for file_name in files:
        os.unlink(results_path + '/' + file_name)
    shutil.move('/tmp/indigo_dataset', results_path)
    shutil.move('/tmp/qlen_s1-eth2.txt', results_path)
    shutil.move('/tmp/dropped_s1-eth2.txt', results_path)
    shutil.move('/tmp/dropped_h2.txt', results_path)
