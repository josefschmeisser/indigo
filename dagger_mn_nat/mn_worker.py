#!/usr/bin/env python2

import sys
import yaml
import argparse
import project_root
import numpy as np
import tensorflow as tf
from subprocess import check_call
from os import path
from dagger import DaggerLeader, DaggerWorker
from env.environment import Environment
from env.sender import Sender


def create_env(task_index):
    env = MininetEnvironment()
    return env


def run(args):
    """ For each worker/parameter server, starts the appropriate job
    associated with the cluster and server.
    """

    task_index = args.task_index
    sys.stderr.write('Starting task %d\n' % task_index)

    ps_hosts = args.ps_hosts.split(',')
    worker_hosts = args.worker_hosts.split(',')

    cluster = tf.train.ClusterSpec({'ps': ps_hosts, 'worker': worker_hosts})
    server = tf.train.Server(cluster, job_name='worker', task_index=task_index)

    # Sets up the env, shared variables (sync, classifier, queue, etc)
    env = create_env(task_index)
    learner = DaggerWorker(cluster, server, task_index, env)
    try:
        learner.run(debug=True)
    except KeyboardInterrupt:
        pass
    finally:
        learner.cleanup()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--ps-hosts', required=True, metavar='[HOSTNAME:PORT, ...]',
        help='comma-separated list of hostname:port of parameter servers')
    parser.add_argument(
        '--worker-hosts', required=True, metavar='[HOSTNAME:PORT, ...]',
        help='comma-separated list of hostname:port of workers')
    parser.add_argument('--task-index', metavar='N', type=int, required=True,
                        help='index of task')
    args = parser.parse_args()

    # run parameter servers and workers
    run(args)


if __name__ == '__main__':
    main()
