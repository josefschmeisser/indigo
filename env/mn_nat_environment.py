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

    def set_sample_action(self, sample_action):
        """Set the sender's policy. Must be called before calling reset()."""

        self.sample_action = sample_action

    def __cleanup(self):
        if self.sender:
            self.sender.cleanup()
            self.sender = None

    def __start_sender(self):
        self.port = get_open_udp_port()
        self.ipc.set_port(port)

        # start sender:
        sys.stderr.write('Starting sender...\n')
        self.sender = Sender(self.port, train=True, debug=True)
        self.sender.set_sample_action(self.sample_action)

        # sender completes the handshake sent from receiver
        self.sender.handshake()

    def rollout(self):
        self.__cleanup()
        self.__start_sender()

        print("MininetEnvironment.rollout")
        sys.stderr.write('Obtaining an episode from environment...\n')

        self.ipc.send_rollout_request()
        self.ipc.wait_for_rollout()
        print("wait_for_reset finished")
        sys.stdout.flush()

        start_delay = self.ipc.get_start_delay()
        if start_delay > 0:
            time.sleep(1e-3*start_delay)
        self.sender.run()

    def get_best_cwnd(self):
        return self.ipc.get_cwnd()

    def idle(self):
        return self.ipc.get_idle_state()
