#!/usr/bin/env python2

import sys
import yaml
import argparse
import project_root
import numpy as np
import tensorflow as tf
from subprocess import check_call
from os import path
from dagger_local import DaggerLocal
from env.mn_client_environment import MininetEnvironment
from env.sender import Sender


def create_env():
    env = MininetEnvironment()
    return env


def run(args):
    """ For each worker/parameter server, starts the appropriate job
    associated with the cluster and server.
    """

    task_index = args.task_index
    sys.stderr.write('Starting task %d\n' % task_index)
    env = create_env()
    dagger = DaggerLocal(env, task_index)
    dagger.run(True)


def main():
    print("worker.py main()")
    parser = argparse.ArgumentParser()
    parser.add_argument('--task-index', metavar='N', type=int, required=True,
                        help='index of task')
    args = parser.parse_args()

    # run parameter servers and workers
    run(args)


if __name__ == '__main__':
    main()
