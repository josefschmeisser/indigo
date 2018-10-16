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

        # variables below will be filled in during setup
        self.sender = None

    def set_sample_action(self, sample_action):
        """Set the sender's policy. Must be called before calling reset()."""

        self.sample_action = sample_action

    def rollout(self):
        print("MininetEnvironment.rollout")
        sys.stderr.write('Obtaining an episode from environment...\n')

        self.ipc.send_rollout_request()
        self.ipc.wait_for_rollout()
        print("wait_for_reset finished")
        sys.stdout.flush()

    def get_best_cwnd(self):
        return self.ipc.get_cwnd()

    def get_task_id(self):
        return self.ipc.get_task_id()
