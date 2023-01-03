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


class seq_gen(gr.sync_block):
    """This class generates sequences of 'vlen' "samples". Each sample in a given vector is the
    same. Each vector is sequentially increasing from the previous one. The values are
    np.uint64, as they are representative for I/Q data that might be sent/received.

    """
    def __init__(self, vlen=1):
        super().__init__(
            name="seq_gen",
            in_sig=None,
            out_sig=[(np.uint64, vlen)])

        self.vlen  = vlen
        self.index = 0
        self.my_log = gr.logger(self.alias())
        self.once = True
        self.start_time = time.time()
        self.update_interval = 10_000_000 # drives logging frequency
        self.rate = 0
        self.my_log.info('Created')

    def work(self, input_items, output_items):
        out = output_items[0]

        # Addressing:
        #  output_items[n]    - buffer for port n -> out
        #  output_items[n][m] - the mth output item (vector) for port n
        #
        # Fortunately, output_items is a list of np.ndarray, and it handles assignment in a
        # mutating fashion

        for idx in range(len(out)):
            # Numpy broadcasting simplifies this a lot
            out[idx] = np.uint64(self.index)

            self.index += 1
            if (self.index*self.vlen) % self.update_interval == 0:
                self.my_log.info(f'{datetime.datetime.now().strftime("%H:%M:%S:")}[{self.index}]-> ({int(self.rate)}/s)')

        elapsed = time.time() - self.start_time
        self.rate = self.index / elapsed

        return len(out)


class seq_gen_test(gr.top_block):

    def __init__(self, pub_ep='tcp://127.0.0.1:16199', vlen=1, samp_rate=8_000_000):
        gr.top_block.__init__(self, "Sequence Generator Test", catch_exceptions=False)

        ##################################################
        # Parameters
        ##################################################
        self.pub_ep = pub_ep
        self.vlen = vlen
        self.samp_rate = samp_rate

        ##################################################
        # Blocks
        ##################################################
        self.seq_gen = seq_gen(vlen)
        self.throttle = blocks.throttle(np.uint64().itemsize*vlen, samp_rate/vlen,True)
        self.pub_sink = zeromq.pub_sink(np.uint64().itemsize, vlen, pub_ep, 100, False, -1, '')

        ##################################################
        # Connections
        ##################################################
        self.connect(self.seq_gen, self.throttle, self.pub_sink)


    def get_pub_ep(self):
        return self.pub_ep

    def set_pub_ep(self, pub_ep):
        self.pub_ep = pub_ep

    def get_vlen(self):
        return self.vlen

    def set_vlen(self, vlen):
        self.vlen = vlen
        self.throttle.set_sample_rate(self.samp_rate/self.vlen)

    def get_samp_rate(self):
        return self.samp_rate

    def set_samp_rate(self, samp_rate):
        self.samp_rate = samp_rate
        self.throttle.set_sample_rate(self.samp_rate/self.vlen)



def argument_parser():
    parser = ArgumentParser()
    parser.add_argument(
        "--pub-ep", dest="pub_ep", type=str, default='tcp://127.0.0.1:16199',
        help="Set pub_ep [default=%(default)r]")
    parser.add_argument(
        "--vlen", dest="vlen", type=int, default=1,
        help="Set vlen [default=%(default)r]")
    parser.add_argument(
        "--samp-rate", dest="samp_rate", type=int, default=8_000_000,
        help="Set sample rate [default=%(default)r]")
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
