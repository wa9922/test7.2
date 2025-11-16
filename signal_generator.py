# signal_generator.py

"""
비트 단위로 PHY 계층 무선 패킷을 생성하는 모듈입니다.
프리앰블(STF + LTF), Signal Field, Payload를 포함하는 완전한 패킷을 
비트 레벨에서 BPSK 변조하여 생성합니다.
"""

import numpy as np
from config import (
    STF_BITS, LTF_BITS, SIGNAL_FIELD_BITS, PAYLOAD_BITS,
    BPSK_CONSTELLATION, SAMPLES_PER_SYMBOL, SAMPLING_RATE,
    TRAFFIC_INDICATION_MAPPING, SIGNAL_FIELD_STRUCTURE
)

class SignalGenerator:
    """비트 단위 신호 생성 및 BPSK 변조 클래스"""
    
    def __init__(self):
        """Signal Generator 초기화"""
        self.stf_reference_bits = np.array(STF_BITS)
        self.ltf_reference_bits = np.array(LTF_BITS)
        self.samples_per_symbol = SAMPLES_PER_SYMBOL  # 클래스 속성으로 추가
        self.sampling_rate = SAMPLING_RATE            # 클래스 속성으로 추가
        print(f"Signal Generator initialized")
        print(f"STF length: {len(self.stf_reference_bits)} bits")
        print(f"LTF length: {len(self.ltf_reference_bits)} bits")
        print(f"Samples per symbol: {self.samples_per_symbol}")
    
    def bits_to_bpsk(self, bits: np.ndarray) -> np.ndarray:
        """
        비트 시퀀스를 BPSK 변조된 복소수 신호로 변환합니다.
        
        Args:
            bits (np.ndarray): 입력 비트 시퀀스 (0 또는 1)
            
        Returns:
            np.ndarray: BPSK 변조된 복소수 신호
        """
        # 각 비트를 BPSK 심볼로 매핑
        symbols = np.array([BPSK_CONSTELLATION[bit] for bit in bits])
        
        # 업샘플링: 각 심볼을 samples_per_symbol만큼 반복
        upsampled_signal = np.repeat(symbols, self.samples_per_symbol)
        
        return upsampled_signal
    
    def bpsk_to_bits(self, signal: np.ndarray) -> np.ndarray:
        """
        BPSK 변조된 신호를 비트로 복조합니다.
        
        Args:
            signal (np.ndarray): BPSK 변조된 복소수 신호
            
        Returns:
            np.ndarray: 복조된 비트 시퀀스
        """
        # 다운샘플링: samples_per_symbol마다 샘플링
        downsampled = signal[::self.samples_per_symbol]
        
        # Hard decision: 실수부가 0보다 크면 1, 작으면 0
        bits = (np.real(downsampled) > 0).astype(int)
        
        return bits
    
    def generate_stf_signal(self) -> tuple:
        """
        STF(Short Training Field) 비트와 변조된 신호를 생성합니다.
        
        Returns:
            tuple: (STF 비트 시퀀스, STF BPSK 신호)
        """
        stf_signal = self.bits_to_bpsk(self.stf_reference_bits)
        print(f"Generated STF: {len(self.stf_reference_bits)} bits → {len(stf_signal)} samples")
        return self.stf_reference_bits.copy(), stf_signal
    
    def generate_ltf_signal(self) -> tuple:
        """
        LTF(Long Training Field) 비트와 변조된 신호를 생성합니다.
        
        Returns:
            tuple: (LTF 비트 시퀀스, LTF BPSK 신호)  
        """
        ltf_signal = self.bits_to_bpsk(self.ltf_reference_bits)
        print(f"Generated LTF: {len(self.ltf_reference_bits)} bits → {len(ltf_signal)} samples")
        return self.ltf_reference_bits.copy(), ltf_signal
    
    def generate_preamble(self) -> tuple:
        """
        프리앰블 = STF + LTF 를 생성합니다.
        
        Returns:
            tuple: (프리앰블 비트 시퀀스, 프리앰블 BPSK 신호)
        """
        stf_bits, stf_signal = self.generate_stf_signal()
        ltf_bits, ltf_signal = self.generate_ltf_signal()
        
        # STF + LTF 연결
        preamble_bits = np.concatenate([stf_bits, ltf_bits])
        preamble_signal = np.concatenate([stf_signal, ltf_signal])
        
        print(f"Generated Preamble: {len(preamble_bits)} bits → {len(preamble_signal)} samples")
        return preamble_bits, preamble_signal
    
    def generate_signal_field(self, traffic_type: str = "sensor") -> tuple:
        """
        Signal Field를 생성합니다. 트래픽 유형을 나타내는 indication을 포함합니다.
        
        Args:
            traffic_type (str): 트래픽 유형 ("sensor", "voice", "video", "wake_up")
            
        Returns:
            tuple: (Signal Field 비트 시퀀스, Signal Field BPSK 신호)
        """
        # 트래픽 타입을 2비트로 매핑
        traffic_mapping_reverse = {v: k for k, v in TRAFFIC_INDICATION_MAPPING.items()}
        traffic_bits_str = traffic_mapping_reverse.get(traffic_type, "00")
        
        # 2비트 트래픽 indication + 2비트 control bits (현재는 00으로 설정)
        signal_field_bits_str = traffic_bits_str + "00"
        signal_field_bits = np.array([int(bit) for bit in signal_field_bits_str])
        
        # 48비트까지 패딩 (실제 802.11 Signal Field 길이)
        padding_bits = np.zeros(SIGNAL_FIELD_BITS - len(signal_field_bits), dtype=int)
        full_signal_field_bits = np.concatenate([signal_field_bits, padding_bits])
        
        # BPSK 변조
        signal_field_signal = self.bits_to_bpsk(full_signal_field_bits)
        
        print(f"Generated Signal Field for '{traffic_type}': {len(full_signal_field_bits)} bits → {len(signal_field_signal)} samples")
        print(f"Traffic indication: {traffic_bits_str} (binary) → {traffic_type}")
        
        return full_signal_field_bits, signal_field_signal
    
    def generate_payload(self, payload_length: int = PAYLOAD_BITS) -> tuple:
        """
        랜덤 Payload 데이터를 생성합니다.
        
        Args:
            payload_length (int): Payload 길이 (비트)
            
        Returns:
            tuple: (Payload 비트 시퀀스, Payload BPSK 신호)
        """
        # 랜덤 비트 생성 (Monte Carlo 시뮬레이션을 위해 시드 고정 해제)
        payload_bits = np.random.randint(0, 2, payload_length)
        
        # BPSK 변조
        payload_signal = self.bits_to_bpsk(payload_bits)
        
        print(f"Generated Payload: {len(payload_bits)} bits → {len(payload_signal)} samples")
        return payload_bits, payload_signal
    
    def create_complete_packet(self, traffic_type: str = "sensor") -> dict:
        """
        완전한 무선 패킷을 생성합니다: Preamble + Signal Field + Payload
        
        Args:
            traffic_type (str): 트래픽 유형
            
        Returns:
            dict: 패킷 구성요소별 비트와 신호를 포함한 딕셔너리
        """
        print(f"\n=== Creating Complete Packet for '{traffic_type}' Traffic ===")
        
        # 1. 프리앰블 생성 (STF + LTF)
        preamble_bits, preamble_signal = self.generate_preamble()
        
        # 2. Signal Field 생성
        signal_field_bits, signal_field_signal = self.generate_signal_field(traffic_type)
        
        # 3. Payload 생성
        payload_bits, payload_signal = self.generate_payload()
        
        # 4. 전체 패킷 결합
        complete_packet_bits = np.concatenate([preamble_bits, signal_field_bits, payload_bits])
        complete_packet_signal = np.concatenate([preamble_signal, signal_field_signal, payload_signal])
        
        # 5. STF 부분만 별도로 추출 (BER 측정용)
        stf_bits, stf_signal = self.generate_stf_signal()
        
        packet_info = {
            # 개별 구성요소
            "stf_bits": stf_bits,
            "stf_signal": stf_signal,
            "preamble_bits": preamble_bits,
            "preamble_signal": preamble_signal,
            "signal_field_bits": signal_field_bits,
            "signal_field_signal": signal_field_signal,
            "payload_bits": payload_bits,
            "payload_signal": payload_signal,
            
            # 전체 패킷
            "complete_bits": complete_packet_bits,
            "complete_signal": complete_packet_signal,
            
            # 메타데이터
            "traffic_type": traffic_type,
            "total_bits": len(complete_packet_bits),
            "total_samples": len(complete_packet_signal),
            "stf_start_idx": 0,
            "stf_end_idx": len(stf_signal),
            "signal_field_start_idx": len(preamble_signal),
            "signal_field_end_idx": len(preamble_signal) + len(signal_field_signal),
            "payload_start_idx": len(preamble_signal) + len(signal_field_signal),
            "payload_end_idx": len(complete_packet_signal)
        }
        
        print(f"Complete packet created:")
        print(f"  - Total bits: {packet_info['total_bits']}")
        print(f"  - Total samples: {packet_info['total_samples']}")
        print(f"  - Duration: {packet_info['total_samples']/self.sampling_rate*1000:.2f} ms")
        
        return packet_info

# 테스트 함수
def test_signal_generator():
    """Signal Generator 테스트 함수"""
    print("=== Testing Signal Generator ===")
    
    generator = SignalGenerator()
    
    # 다양한 트래픽 타입으로 패킷 생성 테스트
    for traffic in ["sensor", "voice", "video", "wake_up"]:
        packet = generator.create_complete_packet(traffic)
        print(f"\nPacket for {traffic}: {packet['total_bits']} bits, {packet['total_samples']} samples")

if __name__ == "__main__":
    test_signal_generator()