#!/usr/bin/env python2

import argparse
import numpy as np
from os import path
from helpers import make_sure_path_exists


def main_old():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bandwidth', metavar='Mbps', required=True,
                        help='constant bandwidth (Mbps)')
    parser.add_argument('--output-dir', metavar='DIR', required=True,
                        help='directory to output trace')
    args = parser.parse_args()

    # number of packets in 60 seconds
    num_packets = int(float(args.bandwidth) * 5000)
    ts_list = np.linspace(0, 60000, num=num_packets, endpoint=False)

    # trace path
    make_sure_path_exists(args.output_dir)
    trace_path = path.join(args.output_dir, '%smbps.trace' % args.bandwidth)

    # write timestamps to trace
    with open(trace_path, 'w') as trace:
        for ts in ts_list:
            trace.write('%d\n' % ts)


def main():
    # (num_flows, delta_t)
    flows = [(1, 30), (2, 30), (1, 30)]

    parser = argparse.ArgumentParser()
    parser.add_argument('--bandwidth', metavar='Mbps', required=True,
                        help='constant bandwidth (Mbps)')
    parser.add_argument('--output-dir', metavar='DIR', required=True,
                        help='directory to output trace')
    args = parser.parse_args()

    ts_list = np.empty(0)
    for num_flows, delta_t in flows:
        # number of packets in delta_t seconds
        scale = float(delta_t) / 60.0
        num_packets_per_flow = int(float(args.bandwidth) * 5000 * scale)
        num_packets = num_flows*num_packets_per_flow
        ts_seq = np.linspace(0, delta_t*1000, num=num_packets, endpoint=False)
        ts_list = np.append(ts_list, ts_seq)

    # trace path
    make_sure_path_exists(args.output_dir)
    trace_path = path.join(args.output_dir, '%smbps.trace' % args.bandwidth)

    # write timestamps to trace
    with open(trace_path, 'w') as trace:
        for ts in ts_list:
            trace.write('%d\n' % ts)


if __name__ == '__main__':
    main()
