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

import posix_ipc
import mmap
import struct

class MininetEnvironment(object):
    def __init__(self):
        if os.getuid() != 0:
            raise RuntimeError("root privileges required")

        self.state_dim = Sender.state_dim
        self.action_cnt = Sender.action_cnt

        self.converged = False

        # variables below will be filled in during setup
        self.sender = None
        self.receiver = None

        # shared memory
        self.mem = posix_ipc.SharedMemory('/indigo', posix_ipc.O_RDWR, size=32)
        self.fd = mmap.mmap(self.mem.fd, self.mem.size, prot=mmap.PROT_WRITE)

    def set_sample_action(self, sample_action):
        """Set the sender's policy. Must be called before calling reset()."""

        self.sample_action = sample_action

    def reset(self):
        """Must be called before running rollout()."""

        self.cleanup()

#        self.port = get_open_udp_port()

        # TODO block until buffers are empty

        # sender completes the handshake sent from receiver
        self.sender.handshake()

    def rollout(self):
        """Run sender in env, get final reward of an episode, reset sender."""

        sys.stderr.write('Obtaining an episode from environment...\n')
        self.sender.run()

    def cleanup(self):
        if self.sender:
            self.sender.cleanup()
            self.sender = None

        if self.receiver:
            try:
                os.killpg(os.getpgid(self.receiver.pid), signal.SIGTERM)
            except OSError as e:
                sys.stderr.write('%s\n' % e)
            finally:
                self.receiver = None

    def get_best_cwnd(self):
        cwnd_bytes = fd.read(32)
        cwnd = struct.unpack("<L", cwnd_bytes)[0]
        return cwnd
