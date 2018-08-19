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


def run(args):
    procs = []
    # ps
    cmd = ['perl', args.worker_src,
            '--ps-hosts', 'localhost:5000',
            '--worker-hosts', 'localhost:5001',
            '--job-name', 'ps',
            '--task-index', str(0)]
    print('$ %s\n' % ' '.join(cmd))
    ps_proc = Popen(cmd, preexec_fn=os.setsid)
    procs.append(ps_proc)

    # worker
    cmd = ['perl', args.worker_src,
            '--ps-hosts', 'localhost:5000',
            '--worker-hosts', 'localhost:5001',
            '--job-name', 'worker',
            '--task-index', str(0)]
    print('$ %s\n' % ' '.join(cmd))
    procs.append(Popen(cmd, preexec_fn=os.setsid))

    ps_proc.communicate()
    return procs


def cleanup(procs):
    for proc in procs:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except OSError as e:
            sys.stderr.write('%s\n' % e)

    print('\nAll cleaned up.\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--worker_src', required=True,
        help='path to worker.py')
    prog_args = parser.parse_args()

    # run worker.py on ps and worker hosts
    procs = None
    try:
        procs = run(prog_args)
    except KeyboardInterrupt:
        pass
    finally:
        cleanup(procs)


if __name__ == '__main__':
    main()
