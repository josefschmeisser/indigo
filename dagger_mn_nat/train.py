#!/usr/bin/env python2

import os
import sys
import time
import signal
import argparse
import project_root
from os import path
from subprocess import Popen, call
from helpers.helpers import get_open_udp_port

from helpers.config import *

import mininet_topo

def run():
    section = config.get_our_section()
    role_type = section['role_type']
    if role_type == 'ps':
        ps_section = config.get_our_section()

        worker_hosts_arg = ','.join([worker['address'] for worker in get_full_worker_list()])
#        print('worker_hosts_arg:', worker_hosts_arg)
        ps_hosts_arg = ','.join([ps['address'] for ps in get_ps_list()])
#        print('ps_hosts_arg:', ps_hosts_arg)

        cmd = ['perl', 'worker.py',
                '--ps-hosts', ps_hosts_arg,
                '--worker-hosts', worker_hosts_arg,
                '--job-name', 'ps',
                '--task-index', str(ps_section['task_index'])]
        sys.stderr.write('$ %s\n' % ' '.join(cmd))

        p = Popen(cmd, preexec_fn=os.setsid)
        try:
            p.wait()
        except KeyboardInterrupt:
            p.terminate()

#        p.wait()
#        call(cmd)
    elif role_type == 'mn':
        controller = mininet_topo.Controller()
        controller.run()
    else:
        sys.stderr.write('unknown role_type: %s\n' % role_type)


def main():
    parse_config_args()
#    try:
    run()
#    except KeyboardInterrupt:
#        pass


if __name__ == '__main__':
    main()
