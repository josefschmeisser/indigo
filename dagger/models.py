import numpy as np
import tensorflow as tf
from tensorflow.contrib import layers, rnn


class DaggerTwoLayerLSTM(object):
    def __init__(self, state_dim, action_cnt):
        # dummy variable used to verify that sharing variables is working
        self.cnt = tf.get_variable(
            'cnt', [], tf.float32,
            initializer=tf.constant_initializer(0.0))
        self.add_one = self.cnt.assign_add(1.0)

        # not used
        self.dropout_rate = tf.placeholder_with_default(0.0, shape=())

        # self.input: [batch_size, max_time, state_dim]
        self.input = tf.placeholder(tf.float32, [None, None, state_dim], name='input')

        self.num_layers = 2
        self.lstm_dim = 32
        stacked_lstm = rnn.MultiRNNCell([rnn.BasicLSTMCell(self.lstm_dim, state_is_tuple=True)
            for _ in xrange(self.num_layers)])

        # self.state_in [num_layers, <lstm state>, batch_size, lstm_dim]
        self.state_in = tf.placeholder(tf.float32, [self.num_layers, 2, None, self.lstm_dim])
        state_tuple_in = []

        for layer_state in tf.unstack(self.state_in, axis=0):
            # fetch c_in and h_in
            state_tuple_in.append(rnn.LSTMStateTuple(layer_state[0], layer_state[1]))
        state_tuple_in = tuple(state_tuple_in)

        # self.output: [batch_size, max_time, lstm_dim]
        output, state_tuple_out = tf.nn.dynamic_rnn(
            stacked_lstm, inputs=self.input, initial_state=state_tuple_in)

        self.state_out = self.convert_state_out(state_tuple_out)

        # map output to scores
        self.action_scores = layers.linear(output, action_cnt)
        self.action_probs = tf.nn.softmax(self.action_scores)

        self.trainable_vars = tf.get_collection(
            tf.GraphKeys.TRAINABLE_VARIABLES, tf.get_variable_scope().name)

    def convert_state_out(self, state_tuple_out):
        state_out = []
        for lstm_state_tuple in state_tuple_out:
            state_out.append((lstm_state_tuple.c, lstm_state_tuple.h))

        return tuple(state_out)

    def zero_init_state(self, batch_size):
        return np.zeros((self.num_layers, 2, batch_size, self.lstm_dim))


class DaggerTwoLayerLSTMDropout(object):
    def __init__(self, state_dim, action_cnt):
        # dummy variable used to verify that sharing variables is working
        self.cnt = tf.get_variable(
            'cnt', [], tf.float32,
            initializer=tf.constant_initializer(0.0))
        self.add_one = self.cnt.assign_add(1.0)

        self.dropout_rate = tf.placeholder_with_default(0.0, shape=())
        self.keep_prob = 1.0 - self.dropout_rate

        # self.input: [batch_size, max_time, state_dim]
        self.input = tf.placeholder(tf.float32, [None, None, state_dim], name='input')

        self.num_layers = 2
        self.lstm_dim = 32
        lstm_cells = [self.construct_cell() for _ in range(self.num_layers)]
        stacked_lstm = rnn.MultiRNNCell(lstm_cells)

        # self.state_in [num_layers, <lstm state>, batch_size, lstm_dim]
        self.state_in = tf.placeholder(tf.float32, [self.num_layers, 2, None, self.lstm_dim])
        state_tuple_in = []

        for layer_state in tf.unstack(self.state_in, axis=0):
            # fetch c_in and h_in
            state_tuple_in.append(rnn.LSTMStateTuple(layer_state[0], layer_state[1]))
        state_tuple_in = tuple(state_tuple_in)

        # self.output: [batch_size, max_time, lstm_dim]
        output, state_tuple_out = tf.nn.dynamic_rnn(
            stacked_lstm, inputs=self.input, initial_state=state_tuple_in)

        self.state_out = self.convert_state_out(state_tuple_out)

        # map output to scores
        self.action_scores = layers.linear(output, action_cnt)
        self.action_probs = tf.nn.softmax(self.action_scores)

        self.trainable_vars = tf.get_collection(
            tf.GraphKeys.TRAINABLE_VARIABLES, tf.get_variable_scope().name)

    def construct_cell(self):
        cell = rnn.BasicLSTMCell(self.lstm_dim, state_is_tuple=True)
        cell = tf.nn.rnn_cell.DropoutWrapper(
            cell,
            input_keep_prob=1.0,
            output_keep_prob=self.keep_prob,
            state_keep_prob=self.keep_prob)
        return cell

    def convert_state_out(self, state_tuple_out):
        state_out = []
        for lstm_state_tuple in state_tuple_out:
            state_out.append((lstm_state_tuple.c, lstm_state_tuple.h))

        return tuple(state_out)

    def zero_init_state(self, batch_size):
        return np.zeros((self.num_layers, 2, batch_size, self.lstm_dim))


class DaggerLSTMDenseDropout(object):
    def __init__(self, state_dim, action_cnt):
        # dummy variable used to verify that sharing variables is working
        self.cnt = tf.get_variable(
            'cnt', [], tf.float32,
            initializer=tf.constant_initializer(0.0))
        self.add_one = self.cnt.assign_add(1.0)

        self.dropout_rate = tf.placeholder_with_default(0.0, shape=())

        # self.input: [batch_size, max_time, state_dim]
        self.input = tf.placeholder(tf.float32, [None, None, state_dim], name='input')

        self.num_layers = 1
        self.lstm_dim = 32
        stacked_lstm = rnn.MultiRNNCell([rnn.BasicLSTMCell(self.lstm_dim, state_is_tuple=True)
            for _ in range(self.num_layers)])

        # self.state_in [num_layers, <lstm state>, batch_size, lstm_dim]
        self.state_in = tf.placeholder(tf.float32, [self.num_layers, 2, None, self.lstm_dim])
        state_tuple_in = []

        for layer_state in tf.unstack(self.state_in, axis=0):
            # fetch c_in and h_in
            state_tuple_in.append(rnn.LSTMStateTuple(layer_state[0], layer_state[1]))
        state_tuple_in = tuple(state_tuple_in)

        # self.output: [batch_size, max_time, lstm_dim]
        lstm_output, state_tuple_out = tf.nn.dynamic_rnn(
            stacked_lstm, inputs=self.input, initial_state=state_tuple_in)

        self.state_out = self.convert_state_out(state_tuple_out)

        # dense1
        dense1 = tf.layers.dense(inputs=lstm_output, units=32, activation=tf.nn.relu)
        dropout1 = tf.layers.dropout(inputs=dense1, rate=self.dropout_rate)

        # map output to scores
        self.action_scores = layers.linear(dropout1, action_cnt)
        self.action_probs = tf.nn.softmax(self.action_scores)

        self.trainable_vars = tf.get_collection(
            tf.GraphKeys.TRAINABLE_VARIABLES, tf.get_variable_scope().name)

    def convert_state_out(self, state_tuple_out):
        state_out = []
        for lstm_state_tuple in state_tuple_out:
            state_out.append((lstm_state_tuple.c, lstm_state_tuple.h))

        return tuple(state_out)

    def zero_init_state(self, batch_size):
        return np.zeros((self.num_layers, 2, batch_size, self.lstm_dim))


class DaggerTwoLayerGRU(object):
    def __init__(self, state_dim, action_cnt):
        # dummy variable used to verify that sharing variables is working
        self.cnt = tf.get_variable(
            'cnt', [], tf.float32,
            initializer=tf.constant_initializer(0.0))
        self.add_one = self.cnt.assign_add(1.0)

        self.dropout_rate = tf.placeholder_with_default(0.0, shape=())
        self.keep_prob = 1.0 - self.dropout_rate

        # self.input: [batch_size, max_time, state_dim]
        self.input = tf.placeholder(tf.float32, [None, None, state_dim], name='input')

        self.num_layers = 2
        self.rnn_dim = 32
        gru_cells = [self.construct_cell() for _ in range(self.num_layers)]
        stacked_cells = rnn.MultiRNNCell(gru_cells)

        # self.state_in [num_layers, batch_size, rnn_dim]
        self.state_in = tf.placeholder(tf.float32, [self.num_layers, None, self.rnn_dim])

        # self.output: [batch_size, max_time, rnn_dim]
        output, current_state_out = tf.nn.dynamic_rnn(
            stacked_cells, inputs=self.input, initial_state=self.state_in)

        self.state_out = current_state_out

        # map output to scores
        self.action_scores = layers.linear(output, action_cnt)
        self.action_probs = tf.nn.softmax(self.action_scores)

        self.trainable_vars = tf.get_collection(
            tf.GraphKeys.TRAINABLE_VARIABLES, tf.get_variable_scope().name)

    def construct_cell(self):
        cell = rnn.GRUCell(self.rnn_dim)
        cell = tf.nn.rnn_cell.DropoutWrapper(
            cell,
            input_keep_prob=1.0,
            output_keep_prob=self.keep_prob,
            state_keep_prob=self.keep_prob)
        return cell

    def zero_init_state(self, batch_size):
        return np.zeros((self.num_layers, batch_size, self.rnn_dim))


def create_model(state_dim, action_cnt):
    return DaggerTwoLayerLSTM(state_dim, action_cnt)
