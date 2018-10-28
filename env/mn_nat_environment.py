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

        self.ipc = IndigoIpcWorkerView(worker_id)

        self.started = False

    def cleanup(self):
        pass # TODO stop sender

    def set_sample_action(self, sample_action):
        """Set the sender's policy. Must be called before calling reset()."""

        self.sample_action = sample_action

    def __run(self):
        if self.started:
            return

        # start sender:
        sys.stderr.write('Starting sender...\n')
        self.sender = Sender(self.ipc.get_port(), train=True)
        self.sender.set_sample_action(self.sample_action)

        ### FIXME check
        # sender completes the handshake sent from receiver
        self.sender.handshake()

        self.started = True

    def rollout(self):
        self.__run()

        print("MininetEnvironment.rollout")
        sys.stderr.write('Obtaining an episode from environment...\n')

        self.ipc.send_rollout_request()
        self.ipc.wait_for_rollout()
        print("wait_for_reset finished")
        sys.stdout.flush()

        self.sender.run()

    def get_best_cwnd(self):
        return self.ipc.get_cwnd()

    def idle(self):
        return self.ipc.get_idle_state()
