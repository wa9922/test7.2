#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GNURadio AGC System Block
Adaptive AGC 처리: RF path → ADC → Digital Truncation → Gain Feedback
"""

import numpy as np
from gnuradio import gr
import pmt

class agc_system_block(gr.sync_block):
    """
    AGC System 블록

    Parameters:
        agc_mode: 'adaptive', 'low_power', 'high_performance'
        enable_gain_feedback: Gain 피드백 활성화 여부
    """
    def __init__(self, agc_mode='adaptive', enable_gain_feedback=True):
        gr.sync_block.__init__(
            self,
            name="agc_system_block",
            in_sig=[np.complex64],
            out_sig=[np.complex64]
        )

        # AGC mode
        self.agc_mode = agc_mode
        self.enable_gain_feedback = enable_gain_feedback

        # RF parameters
        self.lna_gain_db = 20.0  # 고정 LNA gain
        self.vga_gain_db = 20.0  # 가변 VGA gain (초기값)
        self.lpf_alpha = 0.2     # LPF coefficient

        # ADC parameters
        self.adc_bits = 10       # ADC는 항상 10-bit
        self.adc_vref = 1.0
        self.adc_levels = 2**self.adc_bits
        self.adc_step = (2 * self.adc_vref) / self.adc_levels

        # Digital truncation bits
        if self.agc_mode == 'low_power':
            self.current_digital_bits = 5
            self.current_gain_db = 15.0  # 고정
        elif self.agc_mode == 'high_performance':
            self.current_digital_bits = 10
            self.current_gain_db = 40.0  # 고정
        else:  # adaptive
            self.current_digital_bits = 5  # 초기값
            self.current_gain_db = 30.0     # 초기값

        # Gain feedback parameters
        self.gain_min_db = 10.0
        self.gain_max_db = 50.0
        self.peak_high_threshold = 0.9
        self.peak_low_threshold = 0.25

        # LPF state (IIR filter)
        self.lpf_state_i = 0.0
        self.lpf_state_q = 0.0

        # Block processing
        self.block_size = 2560  # STF length (128 bits × 20 samples/symbol)
        self.sample_buffer = np.array([], dtype=np.complex64)

        # Message ports
        self.message_port_register_in(pmt.intern('traffic_info'))
        self.message_port_register_out(pmt.intern('agc_stats'))
        self.set_msg_handler(pmt.intern('traffic_info'), self.handle_traffic_info)

        # Statistics
        self.total_blocks = 0
        self.gain_history = []

    def handle_traffic_info(self, msg):
        """패킷 정보 수신 (traffic type에 따라 digital bits 조정)"""
        if pmt.is_dict(msg):
            traffic_type = pmt.to_python(pmt.dict_ref(msg, pmt.intern('traffic_type'),
                                                       pmt.PMT_NIL))
            if traffic_type and self.agc_mode == 'adaptive':
                # Adaptive mode: traffic type에 따라 digital bits 조정
                if traffic_type in ['wake_up', 'lowpowersignal']:
                    self.current_digital_bits = 5
                elif traffic_type == 'highperformancesignal':
                    self.current_digital_bits = 10

    def apply_rf_path(self, signal):
        """UnifiedRFPath: LNA → Mixer → VGA → LPF"""
        # LNA (고정 20dB)
        lna_gain_linear = 10**(self.lna_gain_db / 20)
        signal = signal * lna_gain_linear

        # Mixer (주파수 변환, 여기서는 baseband이므로 생략)
        # signal = signal * np.exp(1j * 2 * np.pi * f_lo * t)

        # VGA (가변 gain)
        vga_gain_linear = 10**(self.vga_gain_db / 20)
        signal = signal * vga_gain_linear

        # LPF (1st order IIR)
        output = np.zeros_like(signal)
        for i in range(len(signal)):
            self.lpf_state_i = (self.lpf_alpha * signal[i].real +
                               (1 - self.lpf_alpha) * self.lpf_state_i)
            self.lpf_state_q = (self.lpf_alpha * signal[i].imag +
                               (1 - self.lpf_alpha) * self.lpf_state_q)
            output[i] = self.lpf_state_i + 1j * self.lpf_state_q

        return output

    def apply_adc_quantization(self, signal):
        """ADC 10-bit 양자화 + 디지털 truncation"""
        # 10-bit ADC 양자화
        if np.iscomplexobj(signal):
            i_quantized = np.round(signal.real / self.adc_step) * self.adc_step
            q_quantized = np.round(signal.imag / self.adc_step) * self.adc_step
            quantized = np.clip(i_quantized, -self.adc_vref, self.adc_vref) + \
                       1j * np.clip(q_quantized, -self.adc_vref, self.adc_vref)
        else:
            quantized = np.round(signal / self.adc_step) * self.adc_step
            quantized = np.clip(quantized, -self.adc_vref, self.adc_vref)

        # Digital truncation
        if self.current_digital_bits < 10:
            quantized = self.truncate_to_bits(quantized, self.current_digital_bits)

        return quantized

    def truncate_to_bits(self, signal, target_bits):
        """디지털 truncation (5-bit 또는 10-bit)"""
        if target_bits >= 10:
            return signal

        target_levels = 2**target_bits
        target_step = (2 * self.adc_vref) / target_levels

        if np.iscomplexobj(signal):
            i_truncated = np.round(signal.real / target_step) * target_step
            q_truncated = np.round(signal.imag / target_step) * target_step
            truncated = np.clip(i_truncated, -self.adc_vref, self.adc_vref) + \
                       1j * np.clip(q_truncated, -self.adc_vref, self.adc_vref)
        else:
            truncated = np.round(signal / target_step) * target_step
            truncated = np.clip(truncated, -self.adc_vref, self.adc_vref)

        return truncated

    def update_gain_feedback(self, signal_block):
        """Gain 피드백 (peak-based)"""
        if not self.enable_gain_feedback:
            return  # Fixed 모드는 gain 고정

        if self.agc_mode in ['low_power', 'high_performance']:
            return  # Fixed 모드는 gain 고정

        # Peak 측정
        peak = np.max(np.abs(signal_block))

        # Gain 조정
        if peak > self.peak_high_threshold:
            self.vga_gain_db -= 1.0  # Saturation 방지
        elif peak < self.peak_low_threshold:
            self.vga_gain_db += 1.0  # SNR 향상

        # Gain 범위 제한 (총 gain = LNA 20dB + VGA)
        total_gain = self.lna_gain_db + self.vga_gain_db
        total_gain = np.clip(total_gain, self.gain_min_db, self.gain_max_db)
        self.vga_gain_db = total_gain - self.lna_gain_db

        # 현재 총 gain 저장
        self.current_gain_db = total_gain
        self.gain_history.append(total_gain)

    def process_block(self, signal_block):
        """블록 단위 처리"""
        # 1. RF path
        rf_output = self.apply_rf_path(signal_block)

        # 2. ADC + Digital truncation
        digital_output = self.apply_adc_quantization(rf_output)

        # 3. Gain feedback (다음 블록에 적용)
        self.update_gain_feedback(digital_output)

        self.total_blocks += 1

        # 통계 메시지 전송
        if self.total_blocks % 10 == 0:
            stats = pmt.make_dict()
            stats = pmt.dict_add(stats, pmt.intern('gain_db'),
                                pmt.from_double(self.current_gain_db))
            stats = pmt.dict_add(stats, pmt.intern('digital_bits'),
                                pmt.from_long(self.current_digital_bits))
            stats = pmt.dict_add(stats, pmt.intern('total_blocks'),
                                pmt.from_long(self.total_blocks))
            self.message_port_pub(pmt.intern('agc_stats'), stats)

        return digital_output

    def work(self, input_items, output_items):
        """GNURadio work function"""
        in0 = input_items[0]
        out = output_items[0]

        # 버퍼에 추가
        self.sample_buffer = np.concatenate([self.sample_buffer, in0])

        # 블록 단위로 처리
        output_samples = np.array([], dtype=np.complex64)
        while len(self.sample_buffer) >= self.block_size:
            block = self.sample_buffer[:self.block_size]
            self.sample_buffer = self.sample_buffer[self.block_size:]

            processed_block = self.process_block(block)
            output_samples = np.concatenate([output_samples, processed_block])

        # 출력
        n_output = min(len(output_samples), len(out))
        if n_output > 0:
            out[:n_output] = output_samples[:n_output]
            return n_output
        else:
            return 0
