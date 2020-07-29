#!/usr/bin/env python
# -*- coding: utf-8 -*-
# 
# Copyright 2020 SINC-lab.
# 
# This is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# This software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this software; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
# 

import numpy as np
from gnuradio import gr
import pmt
import os

def parify(nybble):
    result = 0
    while nybble:
        result = (nybble & 1) ^ result
        nybble = nybble >> 1
    return result

def hamming_decode(code):
    S1 = parify(code & 0b1110100)
    S2 = parify(code & 0b1101010)
    S3 = parify(code & 0b1011001)
    cor = S1 << 2 | S2 << 1 | S3
    nybble = code >> 3
    if cor == 0b111:
        nybble = nybble ^ 0b1000
    elif cor == 0b110:
        nybble = nybble ^ 0b100
    elif cor == 0b101:
        nybble = nybble ^ 0b10
    elif cor == 0b011:
        nybble = nybble ^ 0b1
    return nybble

def decode(code, transfer=False):
    code1 = code >> 8
    nybble1 = hamming_decode(code1)
    code2 = code & 0xFF
    nybble2 = hamming_decode(code2)
    byte = nybble1 << 4 | nybble2
    if transfer:
        byte = chr(byte)
    return byte

LISTENING = 0
SYNCING = 1
DEMODING = 2

class demod(gr.basic_block):
    """
    docstring for block demod
    """
    def __init__(self, BW, fs, hamming, threshold):
        gr.basic_block.__init__(self,
            name="demod",
            in_sig=[np.complex64],
            out_sig=None)
        self.BW = BW
        self.fs = fs
        self.hamming = hamming
        self.threshold = threshold
        self.ts = 2.0 ** 7 / BW
        self.num = int(self.ts * fs)
        self.upchirp = self.get_upchirp()
        self.downchirp = self.get_upchirp().conj()
        self.state = LISTENING
        self.match = 0
        self.iq_in = np.array([], dtype=np.complex64)
        self.symbols = np.array([], dtype=np.uint8)
        self.out_port = pmt.intern("out")
        self.message_port_register_out(self.out_port)
        self.backup = np.array([], dtype=np.complex64)
        
    def get_upchirp(self):
        BW = self.BW
        fs = self.fs
        ts = self.ts
        num = self.num
        chirp_lut = np.zeros(num, np.complex64)
        i = np.arange(num)
        t = i * 1.0 / fs
        chirp_rate = BW / ts
        theta = (-BW/2.0 + 0.5 *chirp_rate * t) * t
        chirp_lut.real = np.cos(2.0 * np.pi * theta)
        chirp_lut.imag = np.sin(2.0 * np.pi * theta)
        return chirp_lut

    def listen(self, signal):
        conv = self.conv(signal)
        ischirp = False
        # print "listen conv: ", conv.max()
        if conv.max() > self.threshold:
            ischirp = True
        return ischirp

    def conv(self, signal):   
        downchirp = self.downchirp
        conv = np.convolve(signal, downchirp)
        conv = np.abs(conv)
        return conv

    def dechirp(self, signal):
        num = self.num  
        conv = self.conv(signal)
        if conv.max() < self.threshold:
            return 0x02
        argmax = conv.argmax()
        index = (argmax-num) * 2.0 ** 7/ num
        index = np.int(np.around(index))
        lut = np.roll(np.arange(127,-1,-1), 1)
        return lut[index]
    def reset(self):
        self.symbols = np.array([], dtype=np.uint8)
        self.iq_in = np.array([], dtype=np.complex64)
        self.backup = np.array([], dtype=np.complex64)
        self.state = LISTENING
        self.match = 0
    def forecast(self, noutput_items, ninput_items_required):
        #setup size of input_items[i] for work call
        ninput_items_required[0] = noutput_items * 2 ** 7

    def general_work(self, input_items, output_items):

        in0 = input_items[0]
        num = self.num
        if self.state == LISTENING:
            # self.backup = np.concatenate((self.backup, in0))
            # np.save('/home/test/Documents/backup.npy', self.backup)
            if self.listen(in0):
                self.state = SYNCING
                self.iq_in = np.concatenate((self.iq_in, in0))
                print 'DETECTED'
                # self.backup = np.concatenate((self.backup, in0))
                # np.save('/home/test/Documents/backup.npy', self.self.backup)
        elif self.state == SYNCING:
            self.iq_in = np.concatenate((self.iq_in, in0))
            self.backup = np.concatenate((self.backup, in0))
            while self.iq_in.size >= num:
                if self.match >= 3:
                    self.state = DEMODING
                    # np.save('/home/test/Documents/sync.npy', self.backup)
                    # self.backup = np.array([], dtype=np.complex64)
                    # print "SYNSCED"
                    break
                conv = self.conv(self.iq_in[:num])
                if conv.max() > self.threshold:
                    argmax = conv.argmax()
                    bias = argmax
                    if argmax > num:
                        bias = argmax - num
                    if bias == 1024:
                        self.match += 1
                    self.iq_in = np.delete(self.iq_in, np.s_[:bias])             
                else:
                    self.iq_in = np.delete(self.iq_in, np.s_[:num])

        elif self.state == DEMODING:
            # print "DECODING"
            self.iq_in = np.concatenate((self.iq_in, in0))
            if self.backup.size:
                self.backup = np.concatenate((self.backup, in0))
            else:
                self.backup = self.iq_in
            while self.iq_in.size >= num:
                signal = self.iq_in[:num]
                symbol = self.dechirp(signal)
                if symbol == 0x02:
                    print "interuped"
                    # np.save('/home/test/Documents/2.npy', self.backup)
                    # os._exit(1)
                    # break
                    # print "too weak"
                    self.reset()
                    break
                elif symbol == 0x01:
                    print "SENDING"
                    symbols = self.symbols
                    print(symbols)
                    if self.hamming:
                        decoded = np.zeros(int(symbols.size/2), dtype=symbols.dtype)
                        for i in range(decoded.size):
                            code = symbols[2*i]<<8 | symbols[2*i+1]
                            decoded[i] = decode(code)
                        symbols = decoded
                    symbols = symbols[symbols!=0]
                    output = pmt.to_pmt(symbols)
                    output = pmt.cons(pmt.make_dict(), output)
                    self.message_port_pub(self.out_port, output)

                    self.reset()
                    # np.save('/home/test/Documents/1.npy', self.backup)
                    # os._exit(0)
                    break
                else:
                    self.symbols = np.append(self.symbols, np.uint8(symbol))                    
                    self.iq_in = np.delete(self.iq_in, np.s_[:num])

        self.consume_each(len(input_items[0]))
        return 0