#!/usr/bin/env python2

import argparse
import project_root
import numpy as np
import tensorflow as tf
#import pandas as pd
import time
from os import path
from env.sender import Sender
from models import DaggerLSTM
from helpers.helpers import normalize, one_hot, softmax, make_sure_path_exists


class StateLogger(object):
    def __init__(self, output_file, sender):
        self.output_file = output_file
        self.sender = sender

    def log(self, state, action):
        # defined in env/sender.py
        #state = [self.delay_ewma,
        #         self.delivery_rate_ewma,
        #         self.send_rate_ewma,
        #         self.cwnd]
#        ts = pd.Timestamp.now().value
        ts = time.time()
        log_data = [ts] + state + [action] + [self.sender.last_rtt]
        # we need a deliminter like ';' in order to detect unfinished writes
        # since pantheon simply kills our sending process
        line = "%f,%f,%f,%f,%d,%d,%f;\n" % tuple(log_data)
        self.output_file.write(line)


class DummyStateLogger(object):
    def log(self, state, action):
        pass


class DummyLearner(object):
    def __init__(self, state_logger, state_dim, action_cnt, restore_vars):
        self.state_logger = state_logger
        self.aug_state_dim = state_dim + action_cnt
        self.action_cnt = action_cnt
        self.prev_action = action_cnt - 1

        ### TODO
        self.max_patience = 10
        self.current_patience = self.max_patience
        ###

        with tf.variable_scope('global'):
            self.model = DaggerLSTM(
                state_dim=self.aug_state_dim, action_cnt=action_cnt)

        self.lstm_state = self.model.zero_init_state(1)

        self.sess = tf.Session()

        # restore saved variables
        saver = tf.train.Saver(self.model.trainable_vars)
        saver.restore(self.sess, restore_vars)

        # init the remaining vars, especially those created by optimizer
        uninit_vars = set(tf.global_variables())
        uninit_vars -= set(self.model.trainable_vars)
        self.sess.run(tf.variables_initializer(uninit_vars))

    def sample_action(self, state):
        norm_state = normalize(state)

        one_hot_action = one_hot(self.prev_action, self.action_cnt)
        aug_state = norm_state + one_hot_action

        # Get probability of each action from the local network.
        pi = self.model
        feed_dict = {
            pi.input: [[aug_state]],
            pi.state_in: self.lstm_state,
        }
        ops_to_run = [pi.action_probs, pi.state_out]
        action_probs, self.lstm_state = self.sess.run(ops_to_run, feed_dict)

        # Choose an action to take
        action = np.argmax(action_probs[0][0]) # the action index into Sender.action_mapping
        ### TODO
        """
        if action == 2 and action == self.prev_action:
            self.current_patience -= 1
            if self.current_patience < 1:
                action = 3
                self.current_patience = self.max_patience
        """
        ###
        self.prev_action = action
        self.state_logger.log(state, action)

        # action = np.argmax(np.random.multinomial(1, action_probs[0] - 1e-5))
        # temperature = 1.0
        # temp_probs = softmax(action_probs[0] / temperature)
        # action = np.argmax(np.random.multinomial(1, temp_probs - 1e-5))
        return action


def run(args, sender, logger):
    model_path = path.join(project_root.DIR, 'dagger', 'model', 'model')
    learner = DummyLearner(
        state_logger=logger,
        state_dim=Sender.state_dim,
        action_cnt=Sender.action_cnt,
        restore_vars=model_path)
    sender.set_sample_action(learner.sample_action)

    try:
        sender.handshake()
        sender.run()
    except KeyboardInterrupt:
        pass
    finally:
        sender.cleanup()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('port', type=int)
    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--logfile', required=False)
    args = parser.parse_args()

    sender = Sender(args.port, debug=args.debug)
    if args.logfile is not None:
        with open(args.logfile, 'w') as fd:
            logger = StateLogger(fd, sender)
            run(args, sender, logger)
    else:
        logger = DummyStateLogger()
        run(args, sender, logger)


if __name__ == '__main__':
    main()
