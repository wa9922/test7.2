#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GNURadio AGC Packet Source Block
패킷 생성 블록 (STF + LTF + Signal Field + Payload)
"""

import numpy as np
from gnuradio import gr
import pmt

class agc_packet_source(gr.sync_block):
    """
    AGC 패킷 생성 소스 블록

    Parameters:
        traffic_type: 트래픽 타입 ('lowpowersignal', 'highperformancesignal')
        snr_db: 채널 SNR (dB)
        packets_per_burst: 버스트당 패킷 수
        repeat: 반복 여부
    """
    def __init__(self, traffic_type='lowpowersignal', snr_db=10.0,
                 packets_per_burst=10, repeat=True):
        gr.sync_block.__init__(
            self,
            name="agc_packet_source",
            in_sig=None,  # Source block (no input)
            out_sig=[np.complex64]  # Complex output
        )

        # Parameters
        self.traffic_type = traffic_type
        self.snr_db = snr_db
        self.packets_per_burst = packets_per_burst
        self.repeat = repeat

        # Signal parameters
        self.sampling_rate = 20e6
        self.symbol_rate = 1e6
        self.samples_per_symbol = int(self.sampling_rate / self.symbol_rate)

        # Packet structure (bits)
        self.stf_bits = [1,0,1,1,0,1,0,0,1,0,1,1,0,1,0,0] * 8  # 128 bits
        self.ltf_bits = [1,1,0,1,1,0,0,1,0,1,1,1,0,0,0,1] * 4  # 64 bits
        self.signal_field_bits = 48
        self.payload_bits = 1024

        # BPSK constellation
        self.bpsk_map = {0: -1.0+0j, 1: +1.0+0j}

        # Traffic indication mapping
        self.traffic_indication = {
            'wake_up': '00',
            'lowpowersignal': '01',
            'highperformancesignal': '10'
        }

        # State
        self.packet_count = 0
        self.sample_index = 0
        self.current_packet = None
        self.finished = False

        # Message port for packet info
        self.message_port_register_out(pmt.intern('packet_info'))

    def bits_to_bpsk(self, bits):
        """비트를 BPSK 심볼로 변환하고 업샘플링"""
        symbols = np.array([self.bpsk_map[b] for b in bits], dtype=np.complex64)
        # Upsample: 각 심볼을 samples_per_symbol만큼 반복
        upsampled = np.repeat(symbols, self.samples_per_symbol)
        return upsampled

    def generate_signal_field(self):
        """Signal Field 생성 (traffic indication + control bits)"""
        # Traffic type indication (2 bits)
        indication = self.traffic_indication.get(self.traffic_type, '01')
        indication_bits = [int(b) for b in indication]

        # Control bits (나머지를 0으로 채움)
        control_bits = [0] * (self.signal_field_bits - 2)

        return indication_bits + control_bits

    def generate_packet(self):
        """완전한 패킷 생성"""
        # Preamble
        stf_signal = self.bits_to_bpsk(self.stf_bits)
        ltf_signal = self.bits_to_bpsk(self.ltf_bits)

        # Signal field
        signal_field_bits = self.generate_signal_field()
        signal_field_signal = self.bits_to_bpsk(signal_field_bits)

        # Payload
        payload_bits = np.random.randint(0, 2, self.payload_bits).tolist()
        payload_signal = self.bits_to_bpsk(payload_bits)

        # 결합
        complete_signal = np.concatenate([
            stf_signal, ltf_signal, signal_field_signal, payload_signal
        ])

        # AWGN 노이즈 추가
        signal_power = np.mean(np.abs(complete_signal)**2)
        snr_linear = 10**(self.snr_db / 10)
        noise_power = signal_power / snr_linear
        noise = np.sqrt(noise_power/2) * (
            np.random.randn(len(complete_signal)) +
            1j * np.random.randn(len(complete_signal))
        )
        noisy_signal = complete_signal + noise

        # 패킷 정보
        stf_samples = len(stf_signal)
        ltf_samples = len(ltf_signal)
        sf_samples = len(signal_field_signal)

        packet_info = {
            'traffic_type': self.traffic_type,
            'snr_db': self.snr_db,
            'stf_start_idx': 0,
            'stf_end_idx': stf_samples,
            'ltf_start_idx': stf_samples,
            'ltf_end_idx': stf_samples + ltf_samples,
            'signal_field_start_idx': stf_samples + ltf_samples,
            'signal_field_end_idx': stf_samples + ltf_samples + sf_samples,
            'stf_bits': self.stf_bits,
            'packet_length': len(noisy_signal)
        }

        return noisy_signal.astype(np.complex64), packet_info

    def work(self, input_items, output_items):
        """GNURadio work function"""
        out = output_items[0]
        noutput_items = len(out)

        # 완료 확인
        if self.finished and not self.repeat:
            return -1  # EOF

        # 새 패킷 생성 필요 시
        if self.current_packet is None:
            if self.packet_count >= self.packets_per_burst:
                if not self.repeat:
                    self.finished = True
                    return -1
                else:
                    self.packet_count = 0  # Reset for repeat

            self.current_packet, packet_info = self.generate_packet()
            self.sample_index = 0
            self.packet_count += 1

            # 패킷 정보 메시지 전송
            info_dict = pmt.make_dict()
            for key, value in packet_info.items():
                if isinstance(value, str):
                    info_dict = pmt.dict_add(info_dict, pmt.intern(key),
                                            pmt.intern(value))
                elif isinstance(value, (int, float)):
                    info_dict = pmt.dict_add(info_dict, pmt.intern(key),
                                            pmt.from_double(float(value)))
            self.message_port_pub(pmt.intern('packet_info'), info_dict)

        # 샘플 출력
        remaining = len(self.current_packet) - self.sample_index
        to_copy = min(noutput_items, remaining)

        out[:to_copy] = self.current_packet[self.sample_index:self.sample_index+to_copy]
        self.sample_index += to_copy

        # 패킷 완료 시
        if self.sample_index >= len(self.current_packet):
            self.current_packet = None

        return to_copy
