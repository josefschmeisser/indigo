import sys
import libc
import posix_ipc
import struct
import os
import thread
import time

from ctypes import *
from mmap import PROT_WRITE, PROT_READ, MAP_SHARED
from env.sender import default_cwnd

class IpcData(Structure):
    _fields_ = [
        # set by the worker:
        ("port", c_uint16),
        ("min_rtt", c_uint32),
        ("flow_is_active", c_bool),
        # set by the mn controller
        ("cwnd", c_uint32),
        ("idle", c_bool),
        ("start_delay", c_uint32), # in ms
        ("task_id", c_uint32)]     # tensorflow task_id

shm_fmt_str = '=HI?I?II'

uint32_max = 2**32 - 1

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

        # set some initial values
        self.ipc_data.contents.cwnd = int(default_cwnd)
        self.ipc_data.contents.idle = False
        self.ipc_data.contents.start_delay = 0
        self.ipc_data.contents.task_id = uint32_max

        self.handler_thread = None

    def drain_queues(self):
        pass #TODO drain message queues

    def set_cwnd(self, cwnd):
        self.ipc_data.contents.cwnd = cwnd

    def set_idle_state(self, idle):
        self.ipc_data.contents.idle = idle

    def get_port(self):
        return self.ipc_data.contents.port
    
    def get_min_rtt(self):
        return self.ipc_data.contents.min_rtt

    def set_start_delay(self, delay):
        self.ipc_data.contents.start_delay = delay

    def get_flow_is_active(self):
        return self.ipc_data.contents.flow_is_active

    def handler_thread_fun(self, params):
        while True:
            print('handler_thread loop')
            if not self.handler_fun:
                self.handler_thread = None
                return
            msg = self.mn_msg_q.receive()
            print('handler_thread msg: %s', str(msg))
            try:
                self.handler_fun(msg[0], params)
            except:
                sys.stderr.write('handler_thread_fun: %s' % sys.exc_info()[0])

    def set_handler_fun(self, fun, params):
        self.handler_fun = fun
        if not self.handler_thread:
            print('starting thread...')
            self.handler_thread = thread.start_new_thread(self.handler_thread_fun, (params,))

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

        # set some initial values
        self.ipc_data.contents.port = 0
        self.ipc_data.contents.min_rtt = uint32_max
        self.ipc_data.contents.flow_is_active = False

        # message queues
        self.mn_msg_q = posix_ipc.MessageQueue('/indigo_mn_msg_q_worker_%d' % worker_id, posix_ipc.O_CREAT)
        self.worker_msq_q = posix_ipc.MessageQueue('/indigo_worker_msg_q_worker_%d' % worker_id, posix_ipc.O_CREAT)

    def get_cwnd(self):
        return self.ipc_data.contents.cwnd

    def get_task_id(self):
        return self.ipc_data.contents.task_id

    def get_idle_state(self):
        return self.ipc_data.contents.idle

    def set_port(self, port):
        self.ipc_data.contents.port = port

    def get_start_delay(self):
        return self.ipc_data.contents.start_delay

    def set_flow_is_active(self, is_active):
        self.ipc_data.contents.flow_is_active = is_active

    def set_min_rtt(self, min_rtt):
        self.ipc_data.contents.min_rtt = min_rtt

    def send_rollout_request(self):
        self.mn_msg_q.send('rollout')

    def wait_for_rollout(self):
        msg = self.worker_msq_q.receive()
        if msg[0] == 'rollout_done':
            return
        else:
            raise RuntimeError('IPC protocol violation; message: %s' % str(msg))
