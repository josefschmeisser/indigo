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
from helpers.helpers import get_open_udp_port
from helpers.nat_ipc import IndigoIpcWorkerView

class MininetNatEnvironment(object):
    def __init__(self, worker_id):
        if os.getuid() != 0:
            raise RuntimeError("root privileges required")

        self.state_dim = Sender.state_dim
        self.action_cnt = Sender.action_cnt

        self.converged = False
        self.sender = None

        self.ipc = IndigoIpcWorkerView(worker_id)

    def __sample_action_hook(self, state):
        if self.sample_action:
            self.sample_action(state)
        self.ipc.set_min_rtt(self.sender.min_rtt)

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
        self.sender.set_sample_action(self.sample_action)

    def __run_sender(self):
        # sender completes the handshake sent from receiver
        self.sender.handshake()

        start_delay = self.ipc.get_start_delay()
        if start_delay > 0:
            time.sleep(1e-3*start_delay)
        self.sender.run(training_timeout_ms=self.ipc.get_timeout())

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
