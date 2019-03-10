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
from env.mn_nat_environment import MininetNatEnvironment
from env.sender import Sender


def create_env(task_index, worker_id):
    env = MininetNatEnvironment(worker_id)
    return env


def run(args):
    """ For each worker/parameter server, starts the appropriate job
    associated with the cluster and server.
    """

    job_name = args.job_name
    task_index = args.task_index
    sys.stderr.write('Starting job %s task %d\n' % (job_name, task_index))

    ps_hosts = args.ps_hosts.split(',')
    worker_hosts = args.worker_hosts.split(',')
    num_workers = len(worker_hosts)

    cluster = tf.train.ClusterSpec({'ps': ps_hosts, 'worker': worker_hosts})
    server = tf.train.Server(cluster, job_name=job_name, task_index=task_index)

    if job_name == 'ps':
        # Sets up the queue, shared variables, and global classifier.
        worker_tasks = set([idx for idx in xrange(num_workers)])
        leader = DaggerLeader(cluster, server, worker_tasks)
        try:
            leader.run(debug=True)
        except KeyboardInterrupt:
            pass
        finally:
            leader.cleanup()

    elif job_name == 'worker':
        # Sets up the env, shared variables (sync, classifier, queue, etc)
        env = create_env(task_index, args.worker_id)
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
    parser.add_argument('--job-name', choices=['ps', 'worker'],
                        required=True, help='ps or worker')
    parser.add_argument('--task-index', metavar='N', type=int, required=True,
                        help='index of task')
    parser.add_argument('--worker-id', metavar='N', type=int, required=False,
                        help='id of worker')
    args = parser.parse_args()

    # run parameter servers and workers
    run(args)


if __name__ == '__main__':
    main()
