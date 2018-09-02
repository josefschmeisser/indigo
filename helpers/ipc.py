import sys
import libc
import posix_ipc
import struct
import os
import thread
import time

from ctypes import *
from mmap import PROT_WRITE, PROT_READ, MAP_SHARED


class IpcData(Structure):
    _fields_ = [
        ("cwnd", c_uint32), # set by the mn controller
        ("port", c_uint16)] # set by the worker


class IndigoIpcMininetView(object):
    def __init__(self):
        # shared memory
        self.shm_fmt = '=IH?'
        self.shm_size = struct.calcsize(self.shm_fmt)
        self.memory = posix_ipc.SharedMemory('/indigo_shm', posix_ipc.O_CREAT, size=self.shm_size)
        self.semaphore = posix_ipc.Semaphore('/indigo_shm_sync', posix_ipc.O_CREAT)

        # mapping
        self.ptr = libc.mmap(None, self.memory.size, PROT_WRITE, MAP_SHARED, self.memory.fd, 0)
        os.close(self.memory.fd)

        # cast
        self.ipc_data = cast(self.ptr, POINTER(IpcData))

        # message queues
        self.mn_msg_q = posix_ipc.MessageQueue('/indigo_mn_msg_q', posix_ipc.O_CREAT)
        self.worker_msq_q = posix_ipc.MessageQueue('/indigo_worker_msg_q', posix_ipc.O_CREAT)
        self.drain_queues()

        # set initial values
        self.ipc_data.contents.cwnd = 5
        self.ipc_data.contents.port = 5555

        self.handler_thread = None

    def drain_queues(self):
        # TODO
        pass

    def set_cwnd(self, cwnd):
        self.ipc_data.contents.cwnd = cwnd

    def get_port(self):
        return self.ipc_data.contents.port

    """
    def set_handler_fun(self, fun, params):
        self.mn_msg_q.request_notification((fun, params))
    """

    def handler_thread_fun(self):
        while True:
            print('handler_thread loop')
            if not self.handler_fun:
                self.handler_thread = None
                return
            msg = self.mn_msg_q.receive()
            print('handler_thread msg: %s', str(msg))
            # TODO try
            self.handler_fun(msg[0])

    def set_handler_fun(self, fun, params):
        self.handler_fun = fun
        if not self.handler_thread:
            print('starting thread...')
            self.handler_thread = thread.start_new_thread(self.handler_thread_fun, ())

    def get_message(self):
        return self.mn_msg_q.receive()[0]

    def finalize_reset_request(self):
        self.worker_msq_q.send('reset_done')
    
    def finalize_start_receiver_request(self):
        self.worker_msq_q.send('receiver_started')

    def finalize_stop_receiver_request(self):
        self.worker_msq_q.send('receiver_stopped')

    def cleanup(self):
        raise RuntimeError('not implemented')


class IndigoIpcWorkerView(object):
    def __init__(self):
        # shared memory
        self.shm_fmt = '=IH?'
        self.shm_size = struct.calcsize(self.shm_fmt)
        self.memory = posix_ipc.SharedMemory('/indigo_shm', posix_ipc.O_CREAT, size=self.shm_size)
        self.semaphore = posix_ipc.Semaphore('/indigo_shm_sync', posix_ipc.O_CREAT)

        # mapping
        self.ptr = libc.mmap(None, self.memory.size, PROT_WRITE, MAP_SHARED, self.memory.fd, 0)
        os.close(self.memory.fd)

        # cast
        self.ipc_data = cast(self.ptr, POINTER(IpcData))

        # message queues
        self.mn_msg_q = posix_ipc.MessageQueue('/indigo_mn_msg_q', posix_ipc.O_CREAT)
        self.worker_msq_q = posix_ipc.MessageQueue('/indigo_worker_msg_q', posix_ipc.O_CREAT)

    def get_cwnd(self):
        return self.ipc_data.contents.cwnd

    def send_reset_request(self, new_port):
        self.ipc_data.contents.port = int(new_port)
        self.mn_msg_q.send('reset')

    def send_start_receiver_request(self):
        self.mn_msg_q.send('start_receiver')

    def send_stop_receiver_request(self):
        self.mn_msg_q.send('stop_receiver')

    def wait_for_reset(self):
        msg = self.worker_msq_q.receive()
        if msg[0] == 'reset_done':
            return
        else:
            raise RuntimeError('IPC protocol violation; message: %s' % str(msg))

    def wait_for_receiver_start_finalization(self):
        msg = self.worker_msq_q.receive()
        if msg[0] == 'receiver_started':
            return
        else:
            raise RuntimeError('IPC protocol violation; message: %s' % str(msg))

    def wait_for_receiver_stop_finalization(self):
        try:
            print('in wait_for_receiver_stop_finalization()')
            sys.stdout.flush()
            msg = self.worker_msq_q.receive()
            print('received: %s' % str(msg))
            if msg[0] == 'receiver_stopped':
                return
            else:
                raise RuntimeError('IPC protocol violation; message: %s' % str(msg))
        except:
            e = sys.exc_info()[0]
            print('exception in handle_request(): %s' % str(e))
            sys.stdout.flush()
