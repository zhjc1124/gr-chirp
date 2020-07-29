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

def parify(nybble):
    result = 0
    while nybble:
        result = (nybble & 1) ^ result
        nybble = nybble >> 1
    return result

def hamming_encode(nybble):
    a3 = parify(nybble & 0b1110)
    a2 = parify(nybble & 0b1101)
    a1 = parify(nybble & 0b1011)
    code = nybble << 3 | \
           a3 << 2 | \
           a2 << 1 | \
           a1
    return code

def encode(byte, transfer=False):
    if transfer:
        byte = ord(byte)
    nybble1 = (byte & 0xF0) >> 4
    code1 = hamming_encode(nybble1)
    nybble2 = byte & 0x0F
    code2 = hamming_encode(nybble2)
    return code1, code2

class mod(gr.basic_block):
    """
    docstring for block mod
    """
    def __init__(self, BW, fs, hamming):
        gr.basic_block.__init__(self,
            name="chirp_mod",
            in_sig=None,
            out_sig=[np.complex64])
        self.BW = BW
        self.fs = fs
        self.hamming = hamming
        self.ts = 2.0 ** 7 / BW
        self.num = int(self.ts * fs)
        self.lut = self.get_lut()
        self.iq_out = np.array([], dtype=np.complex64)
        
        self.message_port_register_in(pmt.intern('in'))
        self.set_msg_handler(pmt.intern('in'), self.modulate)

    def get_lut(self):
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
        return np.concatenate((chirp_lut, chirp_lut))

    def chirp_mod(self, byte):
        num = self.num
        bais = int(1.0 * num * byte / 2.0 ** 7)
        return self.lut[bais: bais+num]        

    def modulate(self, msg):
        symbols = pmt.to_python(pmt.cdr(msg))
        
        if symbols.size > 1 and symbols[-1] == 10: # 换行符
        # preamble
            # print 'send: ', symbols

            for i in range(4):
                self.iq_out = np.concatenate((self.iq_out, self.lut))
            
            # self.iq_out = np.concatenate((self.iq_out, self.chirp_mod(0x10)))

            if self.hamming:
                encoded = np.zeros(symbols.size*2, dtype=symbols.dtype)
                for i in range(symbols.size):
                    code1, code2 = encode(symbols[i])
                    encoded[2*i] = code1 
                    encoded[2*i+1] = code2
                symbols = encoded                    
            for i in symbols:
                self.iq_out = np.concatenate((self.iq_out, self.chirp_mod(i)))

            self.iq_out = np.concatenate((self.iq_out, self.chirp_mod(0x01)))
            self.iq_out = np.concatenate((self.iq_out, np.zeros(1024*8, dtype=np.complex64)))
    def general_work(self, input_items, output_items):
        noutput = len(output_items[0])
        if noutput > self.iq_out.size:
            noutput = self.iq_out.size
        if noutput:
            output_items[0][:noutput] = self.iq_out[:noutput]
            self.iq_out = np.delete(self.iq_out, np.s_[:noutput])
        return noutput

    # def forecast(self, noutput_items, ninput_items_required):
    #     #setup size of input_items[i] for work call
    #     for i in range(len(ninput_items_required)):
    #         ninput_items_required[i] = noutput_items