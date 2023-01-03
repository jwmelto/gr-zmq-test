#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#
# SPDX-License-Identifier: GPL-3.0
#
# GNU Radio Python Flow Graph
# Title: Sequence Generator Test
# GNU Radio version: 3.10.1.1

import datetime
import signal
import sys
import time
from argparse import ArgumentParser

import numpy as np
from gnuradio import blocks, gr, zeromq


class sequence_comparitor:
    """This is a reusable class that compares a value to an expected value, and complains about
       differences. If the actual value is less, it's assumed that the source restarted and the
       event is logged but ignored. If the actual value is later, it is logged, and after
       'max_err' occurrences, the process terminates.

    """

    def __init__(self, logger, **kw):
        self.seq = 0
        self.logger = logger
        self.init_metrics(0)

        self.dropped_count = 0
        self.max_err = kw.get('max_err', 10)

    def init_metrics(self, start):
        self.first_seen = start
        self.expected = start;
        self.start_time = time.time()

    def check(self, idx):
        self.seq += 1

        actual = idx

#        self.logger.info(f'[{self.seq}]: {actual=}, expected={self.expected}')
        if self.expected == 0:
            self.init_metrics(actual) # startup case

        elif (actual < self.expected):
            self.logger.warn(f'[{self.seq}]: Reset: {self.expected}, actual {idx}')
            self.init_metrics(actual)

        elif (actual > self.expected):
            self.logger.error(f'[{self.seq}]: dropped {actual-self.expected} Expected: {self.expected}, actual {actual}')
            self.dropped_count += 1

        if self.dropped_count > self.max_err:
            raise SystemExit(0)

        self.expected = actual + 1

    def rate(self):
        '''compute the observed data rate'''
        elapsed = time.time() - self.start_time
        received = (self.expected - self.first_seen)
        return received / elapsed


class seq_sink(gr.sync_block):
    """
    docstring for block seq_sink
    """
    def __init__(self, vlen=1):
        gr.sync_block.__init__(self,
            name="seq_sink",
            in_sig=[(np.uint64, vlen)],
            out_sig=None)

        self.vlen       = vlen
        self.calls_to_work = 0
        self.update_interval = 10_000_000
        self.my_log     = gr.logger(self.alias())
        self.tester     = sequence_comparitor(self.my_log)

    def work(self, input_items, output_items):
        self.calls_to_work += 1
        in0 = input_items[0]

        for idx in range(len(in0)):
            if (self.tester.seq * self.vlen) % self.update_interval == 0:
                self.my_log.info(f'{datetime.datetime.now().strftime("%H:%M:%S:")}[{self.calls_to_work}]<-{self.tester.expected} ({int(self.tester.rate())}/s) ({len(in0)=})')

            v = in0[idx]
            actual = v[0] if (self.vlen) > 1 else v # vector or scalar, depending on vlen size
            good = v[v == actual]                   # np.array of bool where the value matches the first value
            bad = v[v != actual]                    # np.array of bool where the value does not match the first value
            if bad.size > 0:
                # This has never been seen
                self.my_log.error(f'Data corruption: {bad.size} unexpected values ({good.size} consistent values)')

            # Check the received value vs expected
            self.tester.check(actual) 

        return len(in0)

class seq_gen_test(gr.top_block):

    def __init__(self, pub_ep='tcp://127.0.0.1:16199', vlen=1, hwm=-1):
        gr.top_block.__init__(self, "Sequence Generator Test", catch_exceptions=True)

        ##################################################
        # Parameters
        ##################################################
        self.pub_ep = pub_ep
        self.vlen = vlen
        pass_tags = False

        ##################################################
        # Blocks
        ##################################################
        self.sub_source = zeromq.sub_source(np.uint64().itemsize, vlen, pub_ep, 100, pass_tags, hwm, '')
        self.seq_sink = seq_sink(vlen=vlen)


        ##################################################
        # Connections
        ##################################################
        self.connect(self.sub_source, self.seq_sink)


    def get_pub_ep(self):
        return self.pub_ep

    def set_pub_ep(self, pub_ep):
        self.pub_ep = pub_ep

    def get_vlen(self):
        return self.vlen

    def set_vlen(self, vlen):
        self.vlen = vlen



def argument_parser():
    parser = ArgumentParser()
    parser.add_argument(
        "--pub-ep", dest="pub_ep", type=str, default='tcp://127.0.0.1:16199',
        help="Set pub_ep [default=%(default)r]")
    parser.add_argument(
        "--vlen", dest="vlen", type=int, default=1,
        help="Set vlen [default=%(default)r]")
    parser.add_argument(
        "--hwm", dest="hwm", type=int, default=-1,
        help="Set high-water mark [default=%(default)r]")
    return parser


def main(top_block_cls=seq_gen_test, options=None):
    if options is None:
        options = argument_parser().parse_args()
    tb = top_block_cls(pub_ep=options.pub_ep, vlen=options.vlen)

    def sig_handler(sig=None, frame=None):
        tb.stop()
        tb.wait()

        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    tb.start()

    tb.wait()


if __name__ == '__main__':
    main()
