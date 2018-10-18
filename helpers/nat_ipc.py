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
        ("idle", c_bool),   # set by the mn controller
        ("task_id", c_uint32)]

shm_fmt_str = '=I?I'

class IndigoIpcMininetView(object):
    def __init__(self, worker_id):
        # shared memory
        self.shm_fmt = shm_fmt_str
        self.shm_size = struct.calcsize(self.shm_fmt)
        self.memory = posix_ipc.SharedMemory('/indigo_shm_worker_%d' % worker_id, posix_ipc.O_CREAT, size=self.shm_size)
        self.semaphore = posix_ipc.Semaphore('/indigo_shm_sync_worker_%d' % worker_id, posix_ipc.O_CREAT)

        # mapping
        self.ptr = libc.mmap(None, self.memory.size, PROT_WRITE, MAP_SHARED, self.memory.fd, 0)
        os.close(self.memory.fd)

        # cast
        self.ipc_data = cast(self.ptr, POINTER(IpcData))

        # message queues
        self.mn_msg_q = posix_ipc.MessageQueue('/indigo_mn_msg_q_worker_%d' % worker_id, posix_ipc.O_CREAT)
        self.worker_msq_q = posix_ipc.MessageQueue('/indigo_worker_msg_q_worker_%d' % worker_id, posix_ipc.O_CREAT)
        self.drain_queues()

        # set initial values
        self.ipc_data.contents.cwnd = 5
        self.ipc_data.contents.port = 5555

        self.handler_thread = None

    def drain_queues(self):
        pass #TODO drain message queues

    def set_cwnd(self, cwnd):
        self.ipc_data.contents.cwnd = cwnd

    def set_idle_state(self, idle):
        self.ipc_data.contents.idle = idle
    """
    def set_task_id(self, task_id):
        self.ipc_data.contents.task_id = task_id
    """
    def handler_thread_fun(self):
        while True:
            print('handler_thread loop')
            if not self.handler_fun:
                self.handler_thread = None
                return
            msg = self.mn_msg_q.receive()
            print('handler_thread msg: %s', str(msg))
            try:
                self.handler_fun(msg[0])
            except:
                sys.stderr.write('handler_thread_fun: %s' % sys.exc_info()[0])

    def set_handler_fun(self, fun, params):
        self.handler_fun = fun
        if not self.handler_thread:
            print('starting thread...')
            self.handler_thread = thread.start_new_thread(self.handler_thread_fun, ())

    def get_message(self):
        return self.mn_msg_q.receive()[0]

    def finalize_reset_request(self):
        self.worker_msq_q.send('reset_done')

    def finalize_rollout_request(self):
        self.worker_msq_q.send('rollout_done')

    def cleanup(self):
        raise RuntimeError('not implemented')


class IndigoIpcWorkerView(object):
    def __init__(self, worker_id):
        # shared memory
        self.shm_fmt = shm_fmt_str
        self.shm_size = struct.calcsize(self.shm_fmt)
        self.memory = posix_ipc.SharedMemory('/indigo_shm_worker_%d' % worker_id, posix_ipc.O_CREAT, size=self.shm_size)
        self.semaphore = posix_ipc.Semaphore('/indigo_shm_sync_worker_%d' % worker_id, posix_ipc.O_CREAT)

        # mapping
        self.ptr = libc.mmap(None, self.memory.size, PROT_WRITE, MAP_SHARED, self.memory.fd, 0)
        os.close(self.memory.fd)

        # cast
        self.ipc_data = cast(self.ptr, POINTER(IpcData))

        # message queues
        self.mn_msg_q = posix_ipc.MessageQueue('/indigo_mn_msg_q_worker_%d' % worker_id, posix_ipc.O_CREAT)
        self.worker_msq_q = posix_ipc.MessageQueue('/indigo_worker_msg_q_worker_%d' % worker_id, posix_ipc.O_CREAT)

    def get_cwnd(self):
        return self.ipc_data.contents.cwnd

    def get_task_id(self):
        return self.ipc_data.contents.task_id

    def get_idle_state(self):
        return self.ipc_data.contents.idle

    def send_rollout_request(self):
        self.mn_msg_q.send('rollout')

    def wait_for_rollout(self):
        msg = self.worker_msq_q.receive()
        if msg[0] == 'rollout_done':
            return
        else:
            raise RuntimeError('IPC protocol violation; message: %s' % str(msg))
