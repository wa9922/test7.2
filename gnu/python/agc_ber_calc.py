#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GNURadio AGC BER Calculator Block
BER 계산 (이론적 모델 사용)
"""

import numpy as np
from gnuradio import gr
import pmt
from scipy.special import erfc

class agc_ber_calc(gr.sync_block):
    """
    BER Calculator 블록

    Parameters:
        adc_bits: ADC/디지털 비트 수 (5 or 10)
        update_interval: BER 업데이트 주기 (samples)
    """
    def __init__(self, adc_bits=10, update_interval=2560):
        gr.sync_block.__init__(
            self,
            name="agc_ber_calc",
            in_sig=[np.complex64],
            out_sig=[np.float32]  # BER output
        )

        self.adc_bits = adc_bits
        self.update_interval = update_interval

        # BER statistics
        self.sample_count = 0
        self.current_ber = 0.0

        # Message ports
        self.message_port_register_in(pmt.intern('snr_in'))
        self.message_port_register_in(pmt.intern('bits_in'))
        self.message_port_register_out(pmt.intern('ber_out'))
        self.set_msg_handler(pmt.intern('snr_in'), self.handle_snr)
        self.set_msg_handler(pmt.intern('bits_in'), self.handle_bits)

        self.current_snr_db = 10.0  # 기본값

    def handle_snr(self, msg):
        """SNR 정보 수신"""
        if pmt.is_number(msg):
            self.current_snr_db = pmt.to_double(msg)

    def handle_bits(self, msg):
        """디지털 비트 수 수신"""
        if pmt.is_number(msg):
            self.adc_bits = int(pmt.to_long(msg))

    def calculate_theoretical_ber(self, snr_db, adc_bits):
        """
        양자화 에러를 고려한 이론적 BPSK BER 계산

        BER = 0.5 * erfc(sqrt(SNR_eff))
        SNR_eff = 1 / (1/SNR_channel + 1/SQNR)
        SQNR = 6.02 * N + 1.76 (dB)
        """
        # SQNR (Signal to Quantization Noise Ratio)
        sqnr_db = 6.02 * adc_bits + 1.76

        # Convert to linear scale
        snr_linear = 10**(snr_db / 10)
        sqnr_linear = 10**(sqnr_db / 10)

        # Effective SNR
        snr_eff_linear = 1.0 / (1.0/snr_linear + 1.0/sqnr_linear)

        # BPSK theoretical BER
        ber = 0.5 * erfc(np.sqrt(snr_eff_linear))

        # Clip to reasonable range
        ber = np.clip(ber, 1e-12, 0.5)

        return ber

    def estimate_snr(self, signal):
        """신호로부터 SNR 추정"""
        # 신호 전력
        signal_power = np.mean(np.abs(signal)**2)

        # 간단한 노이즈 추정 (신호의 분산)
        noise_power = np.var(np.abs(signal) - np.mean(np.abs(signal)))

        if noise_power > 0:
            snr_linear = signal_power / noise_power
            snr_db = 10 * np.log10(snr_linear)
        else:
            snr_db = 30.0  # 기본값

        return snr_db

    def work(self, input_items, output_items):
        """GNURadio work function"""
        in0 = input_items[0]
        out = output_items[0]

        # SNR 추정 (매 update_interval마다)
        if self.sample_count % self.update_interval == 0:
            estimated_snr = self.estimate_snr(in0)
            # 추정값과 설정값 중 더 신뢰할 수 있는 값 사용
            # (여기서는 설정값을 우선 사용)
            # self.current_snr_db = estimated_snr

            # BER 계산
            self.current_ber = self.calculate_theoretical_ber(
                self.current_snr_db, self.adc_bits
            )

            # 메시지 전송
            ber_msg = pmt.make_dict()
            ber_msg = pmt.dict_add(ber_msg, pmt.intern('ber'),
                                  pmt.from_double(self.current_ber))
            ber_msg = pmt.dict_add(ber_msg, pmt.intern('snr_db'),
                                  pmt.from_double(self.current_snr_db))
            ber_msg = pmt.dict_add(ber_msg, pmt.intern('adc_bits'),
                                  pmt.from_long(self.adc_bits))
            self.message_port_pub(pmt.intern('ber_out'), ber_msg)

        self.sample_count += len(in0)

        # BER 값을 모든 샘플에 출력
        out[:] = self.current_ber

        return len(out)
