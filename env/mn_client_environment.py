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
from helpers.ipc import IndigoIpcWorkerView

class MininetEnvironment(object):
    def __init__(self):
        if os.getuid() != 0:
            raise RuntimeError("root privileges required")

        self.state_dim = Sender.state_dim
        self.action_cnt = Sender.action_cnt

        self.converged = False

        self.ipc = IndigoIpcWorkerView()

        # variables below will be filled in during setup
        self.sender = None

    def set_sample_action(self, sample_action):
        """Set the sender's policy. Must be called before calling reset()."""

        self.sample_action = sample_action

    def reset(self):
        """Must be called before running rollout()."""
        print("MininetEnvironment.reset")
        self.cleanup()

        self.port = get_open_udp_port()
        print('open udp port: %d', self.port)
        sys.stdout.flush()

        self.ipc.send_reset_request(self.port)
        self.ipc.wait_for_reset()
        print("wait_for_reset finished")
        sys.stdout.flush()

        # start sender as an instance of Sender class
        sys.stderr.write('Starting sender...\n')
        self.sender = Sender(self.port, train=True)
        self.sender.set_sample_action(self.sample_action)

        sys.stderr.write('Starting receiver...\n')
        self.ipc.send_start_receiver_request()
        self.ipc.wait_for_receiver_start_finalization()

        # sender completes the handshake sent from receiver
        self.sender.handshake()

    def rollout(self):
        """Run sender in env, get final reward of an episode, reset sender."""
        print("MininetEnvironment.rollout")
        sys.stderr.write('Obtaining an episode from environment...\n')
        self.sender.run()

    def cleanup(self):
        if self.sender:
            self.sender.cleanup()
            self.sender = None

        self.ipc.send_stop_receiver_request()
        self.ipc.wait_for_receiver_stop_finalization()
        print("MininetEnvironment.cleanup finished")
        sys.stdout.flush()


    def get_best_cwnd(self):
        return self.ipc.get_cwnd()
