import sys
import time
import project_root
import numpy as np
import tensorflow as tf
import datetime
from tensorflow import contrib
from os import path
from models import DaggerLSTM
from experts import TrueDaggerExpert
from env.sender import Sender
from helpers.helpers import (
    make_sure_path_exists, normalize, one_hot, curr_ts_ms)
from subprocess import check_output


class DaggerLocal(object):
    def __init__(self, env, task_idx):
        # old worker
        # tensorflow and logging related
        self.env = env
        self.task_idx = task_idx

        # Buffers and parameters required to train
        self.curr_ep = 0
        self.state_buf = []
        self.action_buf = []
        self.state_dim = env.state_dim
        self.action_cnt = env.action_cnt

        self.aug_state_dim = self.state_dim + self.action_cnt
        self.prev_action = self.action_cnt - 1

        self.expert = TrueDaggerExpert(env)
        # Must call env.set_sample_action() before env.rollout()
        env.set_sample_action(self.sample_action)

        # Set up Tensorflow for synchronization, training
#        self.setup_tf_ops()
#        self.sess = tf.Session()
#        self.sess.run(tf.global_variables_initializer())



        # old leader
        self.aggregated_states = []
        self.aggregated_actions = []
        self.checkpoint_delta = 10
        self.checkpoint = self.checkpoint_delta
        self.learn_rate = 0.01
        self.regularization_lambda = 1e-4
        self.train_step = 0

        self.state_dim = Sender.state_dim
        self.action_cnt = Sender.action_cnt
        self.aug_state_dim = self.state_dim + self.action_cnt

        # Create the master network and training/sync queues
        with tf.variable_scope('global'):
            self.global_network = DaggerLSTM(
                state_dim=self.aug_state_dim, action_cnt=self.action_cnt)

        """
        self.leader_device_cpu = '/job:ps/task:0/cpu:0'
        with tf.device(self.leader_device_cpu):
            with tf.variable_scope('global_cpu'):
                self.global_network_cpu = DaggerLSTM(
                    state_dim=self.aug_state_dim, action_cnt=self.action_cnt)

        cpu_vars = self.global_network_cpu.trainable_vars
        gpu_vars = self.global_network.trainable_vars
        self.sync_op = tf.group(*[v1.assign(v2) for v1, v2 in zip(
            cpu_vars, gpu_vars)])
        """

        self.default_batch_size = 300
        self.default_init_state = self.global_network.zero_init_state(
                self.default_batch_size)

        # Each element is [[aug_state]], [action]
        self.train_q = tf.FIFOQueue(
                1, [tf.float32, tf.int32],
                shared_name='training_feed')

        self.setup_tf_ops()
        self.sess = tf.Session()
        self.sess.run(tf.global_variables_initializer())

    def cleanup(self):
        self.save_model()
        self.env.cleanup()

    def save_model(self, checkpoint=None):
        """ Takes care of saving/checkpointing the model. """
        if checkpoint is None:
            model_path = path.join(self.logdir, 'model')
        else:
            model_path = path.join(self.logdir, 'checkpoint-%d' % checkpoint)

        # save parameters to parameter server
        saver = tf.train.Saver(self.global_network.trainable_vars)
        saver.save(self.sess, model_path)
        sys.stderr.write('\nModel saved to param. server at %s\n' % model_path)

    def setup_tf_ops(self):
        """ Sets up Tensorboard operators and tools, such as the optimizer,
        summary values, Tensorboard, and Session.
        """

        self.actions = tf.placeholder(tf.int32, [None, None])

        reg_loss = 0.0
        for x in self.global_network.trainable_vars:
            if x.name == 'global/cnt:0':
                continue
            reg_loss += tf.nn.l2_loss(x)
        reg_loss *= self.regularization_lambda

        cross_entropy_loss = tf.reduce_mean(
                tf.nn.sparse_softmax_cross_entropy_with_logits(
                    labels=self.actions,
                    logits=self.global_network.action_scores))

        self.total_loss = cross_entropy_loss + reg_loss

        optimizer = tf.train.AdamOptimizer(self.learn_rate)
        self.train_op = optimizer.minimize(self.total_loss)

        tf.summary.scalar('reduced_ce_loss', cross_entropy_loss)
        tf.summary.scalar('reg_loss', reg_loss)
        tf.summary.scalar('total_loss', self.total_loss)
        self.summary_op = tf.summary.merge_all()

        git_commit = check_output(
                'cd %s && git rev-parse @' % project_root.DIR, shell=True)
        date_time = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        log_name = date_time + '-%s' % git_commit.strip()
        self.logdir = path.join(project_root.DIR, 'dagger', 'logs', log_name)
        make_sure_path_exists(self.logdir)
        self.summary_writer = tf.summary.FileWriter(self.logdir)


        # worker related
        self.worker_init_state = self.global_network.zero_init_state(1)
        self.lstm_state = self.worker_init_state
        # Training data is [[aug_state]], [action]
        self.state_data = tf.placeholder(
                tf.float32, shape=(None, self.aug_state_dim))
        self.action_data = tf.placeholder(tf.int32, shape=(None))
        self.enqueue_train_op = self.train_q.enqueue(
                [self.state_data, self.action_data])




    def run_one_train_step(self, batch_states, batch_actions):
        """ Runs one step of the training operator on the given data.
        At times will update Tensorboard and save a checkpointed model.
        Returns the total loss calculated.
        """

        summary = True if self.train_step % 10 == 0 else False

        ops_to_run = [self.train_op, self.total_loss]

        if summary:
            ops_to_run.append(self.summary_op)

        pi = self.global_network

        start_ts = curr_ts_ms()
        ret = self.sess.run(ops_to_run, feed_dict={
            pi.input: batch_states,
            self.actions: batch_actions,
            pi.state_in: self.init_state})

        elapsed = (curr_ts_ms() - start_ts) / 1000.0
        sys.stderr.write('train step %d: time %.2f\n' %
                         (self.train_step, elapsed))

        if summary:
            self.summary_writer.add_summary(ret[2], self.train_step)

        return ret[1]

    def train(self):
        """ Runs the training operator until the loss converges.
        """
        curr_iter = 0

        min_loss = float('inf')
        iters_since_min_loss = 0

        batch_size = min(len(self.aggregated_states), self.default_batch_size)
        num_batches = len(self.aggregated_states) / batch_size

        print("DEBUG: batch_size != self.default_batch_size: %s" % str(batch_size != self.default_batch_size))
        print("DEBUG: batch_size: %d" % batch_size)
        if batch_size != self.default_batch_size:
            self.init_state = self.global_network.zero_init_state(batch_size)
        else:
            self.init_state = self.default_init_state

        while True:
            curr_iter += 1

            mean_loss = 0.0
            max_loss = 0.0

            for batch_num in xrange(num_batches):
                self.train_step += 1

                start = batch_num * batch_size
                end = start + batch_size

                batch_states = self.aggregated_states[start:end]
                batch_actions = self.aggregated_actions[start:end]

                loss = self.run_one_train_step(batch_states, batch_actions)

                mean_loss += loss
                max_loss = max(loss, max_loss)

            mean_loss /= num_batches

            sys.stderr.write('--- iter %d: max loss %.4f, mean loss %.4f\n' %
                             (curr_iter, max_loss, mean_loss))

            if max_loss < min_loss - 0.001:
                min_loss = max_loss
                iters_since_min_loss = 0
            else:
                iters_since_min_loss += 1

            if curr_iter > 50:
                break

            if iters_since_min_loss >= max(0.2 * curr_iter, 10):
                break

        self.sess.run(self.global_network.add_one)

        # copy trained variables from GPU to CPU
#        self.sess.run(self.sync_op)

        print 'DaggerLeader:global_network:cnt', self.sess.run(self.global_network.cnt)
#        print 'DaggerLeader:global_network_cpu:cnt', self.sess.run(self.global_network_cpu.cnt)
        sys.stdout.flush()

    def rollout(self):
        """ Start an episode/flow with an empty dataset/environment. """
        self.state_buf = []
        self.action_buf = []
        self.prev_action = self.action_cnt - 1
        self.lstm_state = self.worker_init_state
        print("DEBUG rollout init_state: %s" % self.worker_init_state)
        self.env.reset()
        self.env.rollout()

    def run(self, debug=False):
        print("DaggerLocal.run")
        while True:

            print("pi.action_probs: %s" % str(self.global_network.action_probs))
            print("pi.state_out: %s" % str(self.global_network.state_out))
            print("self.lstm_state: %s" % str(self.lstm_state))

            if debug:
                sys.stderr.write('[WORKER %d Ep %d] Starting...\n' %
                                 (self.task_idx, self.curr_ep))

#            print 'DaggerWorker:global_network_cpu:cnt', self.sess.run(self.global_network_cpu.cnt)
#            sys.stdout.flush()
            print("call rollout")
            sys.stdout.flush()
            # Start a single episode, populating state-action buffers.
            self.rollout()
            sys.stdout.flush()

            """
            if debug:
                queue_size = self.sess.run(self.train_q.size())
                sys.stderr.write(
                    '[WORKER %d Ep %d]: enqueueing a sequence of data '
                    'into queue of size %d\n' %
                    (self.task_idx, self.curr_ep, queue_size))
            """
            if debug:
#                queue_size = self.sess.run(self.train_q.size())
                queue_size = len(self.action_buf)
                sys.stderr.write(
                    '[WORKER %d Ep %d]: enqueueing a sequence of data '
                    'into queue of size %d\n' %
                    (self.task_idx, self.curr_ep, queue_size))

            # Enqueue a sequence of data into the training queue.
            self.sess.run(self.enqueue_train_op, feed_dict={
                self.state_data: self.state_buf,
                self.action_data: self.action_buf})

            while True:
                num_samples = self.sess.run(self.train_q.size())
                if num_samples == 0:
                    break

                data = self.sess.run(self.train_q.dequeue())
                self.aggregated_states.append(data[0])
                self.aggregated_actions.append(data[1])

            if debug:
                sys.stderr.write('[DAGGER]: start training\n')

            self.train()

            self.curr_ep += 1

            # Save the network model for testing every so often
            if self.curr_ep == self.checkpoint:
                self.save_model(self.curr_ep)
                self.checkpoint += self.checkpoint_delta


    def sample_action(self, state):
        """ Given a state buffer in the past step, returns an action
        to perform.

        Appends to the state/action buffers the state and the
        "correct" action to take according to the expert.
        """
#        print('[DAGGER]: sample_action()')
#        sys.stdout.flush()

        cwnd = state[self.state_dim - 1]
        expert_action = self.expert.sample_action(cwnd)

        # For decision-making, normalize.
        norm_state = normalize(state)

        one_hot_action = one_hot(self.prev_action, self.action_cnt)
        aug_state = norm_state + one_hot_action

        # Fill in state_buf, action_buf
        self.state_buf.append(aug_state)
        self.action_buf.append(expert_action)

        # Always use the expert on the first episode to get our bearings.
        if self.curr_ep == 0:
            self.prev_action = expert_action
            return expert_action

        # Get probability of each action from the local network.
        pi = self.global_network
        feed_dict = {
            pi.input: [[aug_state]],
            pi.state_in: self.lstm_state,
        }
        ops_to_run = [pi.action_probs, pi.state_out]
        action_probs, self.lstm_state = self.sess.run(ops_to_run, feed_dict)

        # Choose an action to take and update current LSTM state
        # action = np.argmax(np.random.multinomial(1, action_probs[0][0] - 1e-5))
        action = np.argmax(action_probs[0][0])
        self.prev_action = action

        return action
