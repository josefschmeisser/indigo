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
    role = config.get_role()
    if role == 'ps':
        ps_section = config.get_our_section()
        ps_hosts = ','.join(get_ps_host_list())
        worker_hosts = ','.join(get_full_worker_list())
        cmd = ['perl', 'worker.py',
                '--ps-hosts', ps_hosts,
                '--worker-hosts', worker_hosts,
                '--job-name', ps_section['job_name'],
                '--task-index', ps_section['task_index']]
        sys.stderr.write('$ %s\n' % ' '.join(cmd))
        Popen(cmd, preexec_fn=os.setsid)
    elif role == 'mn':
        controller = mininet_topo.Controller()
        controller.run()


def main():
    parse_config_args()
    try:
        run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
