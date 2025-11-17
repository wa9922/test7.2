#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GNURadio AGC Power Meter Block
아날로그 및 디지털 전력 측정
"""

import numpy as np
from gnuradio import gr
import pmt

class agc_power_meter(gr.sync_block):
    """
    AGC Power Meter 블록

    Parameters:
        sampling_rate: 샘플링 레이트 (Hz)
        adc_bits: 디지털 비트 수
    """
    def __init__(self, sampling_rate=20e6, adc_bits=10):
        gr.sync_block.__init__(
            self,
            name="agc_power_meter",
            in_sig=[np.complex64],
            out_sig=None  # Message output only
        )

        self.sampling_rate = sampling_rate
        self.adc_bits = adc_bits

        # Power parameters (MAX2829 기준)
        self.analog_power_mw = 392.0  # MAX2829 RX mode (mW)

        # Digital power parameters
        self.power_per_add = 0.1   # pJ/op
        self.power_per_mult = 2.5  # pJ/op
        self.k_add_per_sample = 5000.0
        self.k_mul_per_sample = 250.0

        # Energy accumulators
        self.total_analog_energy_mj = 0.0
        self.total_digital_energy_pj = 0.0
        self.total_samples = 0

        # Message ports
        self.message_port_register_in(pmt.intern('bits_in'))
        self.message_port_register_out(pmt.intern('power_out'))
        self.set_msg_handler(pmt.intern('bits_in'), self.handle_bits)

        # Update interval
        self.update_interval = 10000  # samples
        self.sample_count = 0

    def handle_bits(self, msg):
        """디지털 비트 수 수신"""
        if pmt.is_number(msg):
            self.adc_bits = int(pmt.to_long(msg))

    def calculate_analog_energy(self, n_samples):
        """
        아날로그 에너지 계산 (항상 동일)

        Energy = Power × Time
        Time = samples / sampling_rate
        """
        time_sec = n_samples / self.sampling_rate
        energy_mj = self.analog_power_mw * time_sec  # mJ

        return energy_mj

    def calculate_digital_energy(self, n_samples):
        """
        디지털 에너지 계산 (비트 종속)

        Energy = (덧셈 ops × power_per_add + 곱셈 ops × power_per_mult) × area_ratio
        덧셈 ops = K_ADD × samples × bits
        곱셈 ops = K_MUL × samples × bits²
        """
        b = self.adc_bits

        # 연산량 계산
        additions = self.k_add_per_sample * n_samples * b
        multiplications = self.k_mul_per_sample * n_samples * (b**2)

        # Area scaling (8-bit 기준)
        base_bits = 8
        area_ratio = (b**2) / (base_bits**2)

        # 에너지 계산 (pJ)
        energy_pj = (additions * self.power_per_add +
                    multiplications * self.power_per_mult) * area_ratio

        return energy_pj

    def work(self, input_items, output_items):
        """GNURadio work function"""
        in0 = input_items[0]
        n_samples = len(in0)

        # 아날로그 에너지 (항상 동일)
        analog_energy = self.calculate_analog_energy(n_samples)
        self.total_analog_energy_mj += analog_energy

        # 디지털 에너지 (비트 종속)
        digital_energy = self.calculate_digital_energy(n_samples)
        self.total_digital_energy_pj += digital_energy

        self.total_samples += n_samples
        self.sample_count += n_samples

        # 주기적으로 메시지 전송
        if self.sample_count >= self.update_interval:
            self.sample_count = 0

            # 총 에너지 계산
            total_energy_mj = self.total_analog_energy_mj + \
                            (self.total_digital_energy_pj / 1e9)  # pJ → mJ

            # 메시지 생성
            power_msg = pmt.make_dict()
            power_msg = pmt.dict_add(power_msg, pmt.intern('analog_energy_mj'),
                                    pmt.from_double(self.total_analog_energy_mj))
            power_msg = pmt.dict_add(power_msg, pmt.intern('digital_energy_pj'),
                                    pmt.from_double(self.total_digital_energy_pj))
            power_msg = pmt.dict_add(power_msg, pmt.intern('total_energy_mj'),
                                    pmt.from_double(total_energy_mj))
            power_msg = pmt.dict_add(power_msg, pmt.intern('adc_bits'),
                                    pmt.from_long(self.adc_bits))
            power_msg = pmt.dict_add(power_msg, pmt.intern('total_samples'),
                                    pmt.from_long(self.total_samples))

            self.message_port_pub(pmt.intern('power_out'), power_msg)

        return n_samples
