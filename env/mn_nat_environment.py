# requires root privileges

import os
from os import path
import threading
import time
import shutil
import sys
import signal
from subprocess import Popen
from sender import Sender
import project_root
from helpers.helpers import get_open_udp_port, curr_ts_ms
from helpers.nat_ipc import IndigoIpcWorkerView
import numpy as np
import collections
import itertools

SubEpisode = collections.namedtuple('SubEpisode', 'opt_rtt, opt_tput, ts_first, delivered_acc, rtt_buf')

def pairwise(iterable):
    "s -> (s0,s1), (s1,s2), (s2, s3), ..."
    a, b = itertools.tee(iterable)
    next(b, None)
    return itertools.izip(a, b)

class MininetNatEnvironment(object):
    current_opt_rtt = None
    current_opt_tput = None
    sub_episodes = []

    def __init__(self, worker_id):
        if os.getuid() != 0:
            raise RuntimeError("root privileges required")

        self.state_dim = Sender.state_dim
        self.action_cnt = Sender.action_cnt

        self.converged = False
        self.sender = None

        self.ipc = IndigoIpcWorkerView(worker_id)

    def __fetch_optimal_params(self):
        _, new_opt_rtt, new_opt_tput = self.ipc.get_optimal_params()
        if new_opt_rtt != self.current_opt_rtt or new_opt_tput != self.current_opt_tput:
            ts_first = curr_ts_ms()
            deliverd = self.sender.delivered # accumulated sum over all sub-episodes
            rtt_buf = self.sender.pass_rtt_buffer()
            self.sub_episodes.append(SubEpisode(new_opt_rtt, new_opt_tput, ts_first, deliverd, rtt_buf))
            self.current_opt_rtt = new_opt_rtt
            self.current_opt_tput = new_opt_tput

    def __compute_performance(self):
        perf_file = path.join(project_root.DIR, 'env', 'task_{}_perf'.format(self.ipc.get_task_id()))
        sub_episode = 0

        with open(perf_file, 'a', 0) as perf:
            for curr, nxt in pairwise(self.sub_episodes):
                end = nxt.ts_first if nxt is not None else curr_ts_ms()
                duration = end - curr.ts_first
                end_delivered = nxt.delivered_acc if nxt is not None else self.sender.delivered
                delivered = end_delivered - curr.delivered_acc

                perc_delay = float(np.percentile(curr.rtt_buf, 95))
                delay_err = abs(perc_delay - curr.opt_rtt) / curr.opt_rtt

                tput = 0.008 * delivered / duration
                print('tput: {} opt_tput: {}'.format(tput, curr.opt_tput))
                tput_err = abs(tput - curr.opt_tput) / curr.opt_tput

                if sub_episode > 0:
                    perf.write('; ')
                perf.write('%.2f,%.2f,%d,%.2f' % (tput, tput_err, perc_delay, delay_err))

                sub_episode += 1

            perf.write('\n')

        # reset
        self.opt_rtt = None
        self.opt_tput = None

    def __sample_action_hook(self, state):
        assert(self.sample_action)
        action = self.sample_action(state)
#        print('min rtt: {}'.format(self.sender.min_rtt))
        self.ipc.set_min_rtt(int(self.sender.min_rtt))
        self.__fetch_optimal_params()
        return action

    def set_sample_action(self, sample_action):
        """Set the sender's policy. Must be called before calling reset()."""

        self.sample_action = sample_action

    def cleanup(self):
        if self.sender is not None:
            self.sender.cleanup()
            self.sender = None

    def __start_sender(self):
        self.port = get_open_udp_port()
        self.ipc.set_port(self.port)

        # start sender:
        sys.stderr.write('Starting sender...\n')
        self.sender = Sender(self.port, train=True, debug=True)
        self.sender.set_sample_action(self.__sample_action_hook)

    def __run_sender(self):
        # sender completes the handshake sent from receiver
        self.sender.handshake()

        start_delay = self.ipc.get_start_delay()
        if start_delay > 0:
            time.sleep(1e-3*start_delay)
        self.ipc.set_flow_is_active(True)
        self.sender.run()
        self.ipc.set_flow_is_active(False)
        self.__compute_performance()

    def rollout(self):
        self.cleanup()
        self.__start_sender()

        print("MininetEnvironment.rollout")
        sys.stderr.write('Obtaining an episode from environment...\n')
        sys.stdout.flush()

        self.ipc.send_rollout_request()
        self.ipc.wait_for_rollout()
        print("wait_for_rollout finished")
        sys.stdout.flush()

        self.__run_sender()

    def get_best_cwnd(self):
        return self.ipc.get_cwnd()

    def idle(self):
        return self.ipc.get_idle_state()
