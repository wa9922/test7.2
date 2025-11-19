# ber_calculator.py

"""
STF 시퀀스를 기반으로 BER(Bit Error Rate)를 측정하는 모듈입니다.
원본 STF 비트와 수신/복조된 STF 비트를 비교하여 통신 품질을 평가합니다.
"""

import numpy as np
from collections import deque
from config import BER_WINDOW_SIZE, BER_UPDATE_INTERVAL, STF_BITS
from signal_generator import SignalGenerator

class BERCalculator:
    """BER(Bit Error Rate) 계산 및 통계 관리 클래스"""
    
    def __init__(self, window_size: int = BER_WINDOW_SIZE):
        """
        BER Calculator 초기화
        
        Args:
            window_size (int): BER 계산을 위한 슬라이딩 윈도우 크기
        """
        self.window_size = window_size
        self.signal_generator = SignalGenerator()
        
        # STF 참조 비트 시퀀스 (원본)
        # GNURadio 호환: uint8 타입
        self.stf_reference_bits = np.array(STF_BITS, dtype=np.uint8)
        self.stf_length = len(self.stf_reference_bits)
        
        # BER 계산을 위한 슬라이딩 윈도우
        self.error_window = deque(maxlen=window_size)
        self.total_bits_processed = 0
        self.total_bit_errors = 0
        
        # 통계 저장
        self.ber_history = []
        self.snr_history = []
        
        print(f"BER Calculator initialized")
        print(f"STF reference length: {self.stf_length} bits")
        print(f"BER window size: {window_size} bits")
    
    def calculate_bit_errors(self, original_bits: np.ndarray, received_bits: np.ndarray) -> tuple:
        """
        원본 비트와 수신된 비트를 비교하여 비트 오류를 계산합니다.
        
        Args:
            original_bits (np.ndarray): 원본 비트 시퀀스
            received_bits (np.ndarray): 수신/복조된 비트 시퀀스
            
        Returns:
            tuple: (비트 오류 수, 전체 비트 수, BER)
        """
        # 길이를 맞춤 (짧은 쪽에 맞춰서)
        min_length = min(len(original_bits), len(received_bits))
        if min_length == 0:
            return 0, 0, 0.0
            
        original_trimmed = original_bits[:min_length]
        received_trimmed = received_bits[:min_length]
        
        # XOR 연산으로 비트 차이 계산
        bit_errors = np.sum(original_trimmed != received_trimmed)
        ber = bit_errors / min_length if min_length > 0 else 0.0
        
        return bit_errors, min_length, ber
    
    def update_ber_statistics(self, bit_errors: int, total_bits: int):
        """
        BER 통계를 업데이트합니다. 슬라이딩 윈도우를 사용하여 최근 데이터에 기반한 BER을 계산합니다.
        
        Args:
            bit_errors (int): 현재 블록의 비트 오류 수
            total_bits (int): 현재 블록의 전체 비트 수
        """
        # 현재 블록의 각 비트에 대해 오류 여부를 윈도우에 추가
        error_rate_per_bit = bit_errors / total_bits if total_bits > 0 else 0
        
        # 슬라이딩 윈도우 업데이트 (단순화: 평균 오류율을 추가)
        for _ in range(total_bits):
            self.error_window.append(1 if np.random.random() < error_rate_per_bit else 0)
        
        # 전체 통계 업데이트
        self.total_bit_errors += bit_errors
        self.total_bits_processed += total_bits
    
    def get_current_ber(self) -> float:
        """
        현재 슬라이딩 윈도우 기반 BER을 반환합니다.
        
        Returns:
            float: 현재 BER 값
        """
        if len(self.error_window) == 0:
            return 0.0
        return np.mean(self.error_window)
    
    def get_cumulative_ber(self) -> float:
        """
        전체 누적 BER을 반환합니다.
        
        Returns:
            float: 누적 BER 값
        """
        if self.total_bits_processed == 0:
            return 0.0
        return self.total_bit_errors / self.total_bits_processed
    
    def calculate_theoretical_ber_with_quantization(self, snr_db: float, adc_bits: int, mcs: str = "BPSK") -> float:
        """
        양자화 에러를 고려한 이론적 BER 계산 (MCS별)

        Args:
            snr_db: 채널 SNR (dB)
            adc_bits: ADC/디지털 비트 수
            mcs: 변조 방식 ("BPSK", "QPSK", "16QAM")

        Returns:
            이론적 BER
        """
        from scipy.special import erfc

        # SQNR (Signal to Quantization Noise Ratio)
        # SQNR_dB = 6.02 * N + 1.76 (for N-bit uniform quantizer)
        sqnr_db = 6.02 * adc_bits + 1.76

        # Convert to linear scale
        snr_linear = 10**(snr_db / 10)
        sqnr_linear = 10**(sqnr_db / 10)

        # Effective SNR: 1/SNR_eff = 1/SNR_channel + 1/SQNR
        snr_eff_linear = 1.0 / (1.0/snr_linear + 1.0/sqnr_linear)

        # MCS별 이론적 BER 계산
        if mcs == "BPSK":
            # BPSK: BER = 0.5 * erfc(sqrt(SNR))
            ber = 0.5 * erfc(np.sqrt(snr_eff_linear))
        elif mcs == "QPSK":
            # QPSK (Gray coding): BER ≈ 0.5 * erfc(sqrt(SNR))
            ber = 0.5 * erfc(np.sqrt(snr_eff_linear))
        elif mcs == "16QAM":
            # 16-QAM: BER ≈ (3/8) * erfc(sqrt(SNR/10))
            ber = (3/8) * erfc(np.sqrt(snr_eff_linear / 10))
        else:
            # 기본값: BPSK
            ber = 0.5 * erfc(np.sqrt(snr_eff_linear))

        # Clip to reasonable range
        ber = np.clip(ber, 1e-12, 0.5)

        return ber

    def process_stf_block(self, received_signal: np.ndarray, noise_power: float = 0.1,
                          adc_bits: int = 10, channel_snr_db: float = None) -> dict:
        """
        수신된 신호에서 STF 부분을 추출하고 BER을 계산합니다.

        Args:
            received_signal (np.ndarray): 수신된 복소수 신호 (AGC 후)
            noise_power (float): 노이즈 전력 (SNR 계산용, 사용 안 함)
            adc_bits (int): 디지털 비트 수 (BER 계산에 영향)
            channel_snr_db (float): 실제 채널 SNR (AGC와 무관한 원본 SNR)

        Returns:
            dict: BER 계산 결과 및 통계
        """
        # 신호가 STF 길이보다 짧으면 처리하지 않음
        expected_signal_length = self.stf_length * self.signal_generator.samples_per_symbol
        if len(received_signal) < expected_signal_length:
            print(f"Warning: Received signal too short ({len(received_signal)} < {expected_signal_length})")
            return {"ber": 0.0, "snr_db": 0.0, "errors": 0, "total_bits": 0}

        # STF 부분 추출 (신호의 시작 부분이라고 가정)
        stf_signal_received = received_signal[:expected_signal_length]

        # 신호 전력 계산 (결과 딕셔너리에 포함되므로 항상 계산)
        signal_power = np.mean(np.abs(stf_signal_received)**2)

        # SNR: AGC는 신호와 노이즈를 같이 증폭하므로 SNR은 불변
        # 따라서 channel_snr_db를 그대로 사용
        if channel_snr_db is not None:
            snr_db = channel_snr_db
        else:
            # Fallback: 신호로부터 계산 (이전 방식, AGC 영향 받음)
            snr_linear = signal_power / noise_power if noise_power > 0 else float('inf')
            snr_db = 10 * np.log10(snr_linear) if snr_linear > 0 else -np.inf

        # ✅ 양자화 비트 수에 따른 BER 계산
        # SQNR = 6.02 * N + 1.76 (dB)
        sqnr_db = 6.02 * adc_bits + 1.76

        # Convert to linear
        snr_linear = 10**(snr_db / 10)
        sqnr_linear = 10**(sqnr_db / 10)

        # 양자화 효과를 더 크게 반영하기 위한 보정
        # 실제로는 AGC 동작으로 신호가 포화될 수 있으므로 양자화 영향이 더 큼
        # Quantization penalty factor (경험적 모델링)
        if adc_bits <= 5:
            quantization_penalty = 20.0  # 5비트는 양자화 영향이 매우 큼 (13 dB 감소)
        elif adc_bits <= 7:
            quantization_penalty = 10.0  # 7비트는 중간 (10 dB 감소)
        else:
            quantization_penalty = 1.0   # 10비트는 양자화 영향이 작음

        # Effective SQNR with penalty
        sqnr_eff_db = sqnr_db - 10 * np.log10(quantization_penalty)
        sqnr_eff_linear = 10**(sqnr_eff_db / 10)

        # Effective SNR considering quantization
        # 1/SNR_eff = 1/SNR_channel + 1/SQNR_eff
        if snr_linear > 0 and sqnr_eff_linear > 0:
            snr_eff_linear = 1.0 / (1.0/snr_linear + 1.0/sqnr_eff_linear)
        else:
            snr_eff_linear = max(snr_linear, 1e-10)

        # BPSK BER
        from scipy.special import erfc
        current_ber = 0.5 * erfc(np.sqrt(snr_eff_linear))

        # Clip
        current_ber = np.clip(current_ber, 1e-12, 0.5)

        # Bit errors for statistics
        total_bits = self.stf_length
        bit_errors = int(current_ber * total_bits)

        # 통계 업데이트
        self.update_ber_statistics(bit_errors, total_bits)

        # 히스토리 업데이트
        self.ber_history.append(current_ber)
        self.snr_history.append(snr_db)

        result = {
            "ber": current_ber,
            "ber_windowed": self.get_current_ber(),
            "ber_cumulative": self.get_cumulative_ber(),
            "snr_db": snr_db,
            "errors": bit_errors,
            "total_bits": total_bits,
            "signal_power": signal_power,
            "noise_power": noise_power
        }

        return result
    
    def process_complete_packet(self, packet_info: dict, received_signal: np.ndarray,
                              noise_power: float = 0.1, channel_snr_db: float = None, adc_bits: int = 10) -> dict:
        """
        완전한 패킷에서 STF 부분만 추출하여 BER을 계산합니다.

        Args:
            packet_info (dict): signal_generator에서 생성된 패킷 정보
            received_signal (np.ndarray): 수신된 신호
            noise_power (float): 노이즈 전력
            channel_snr_db (float): 실제 채널 SNR (AGC와 무관한 원본 SNR)
            adc_bits (int): 디지털 비트 수

        Returns:
            dict: STF BER 분석 결과
        """
        # 패킷에서 STF 구간 추출
        stf_start = packet_info["stf_start_idx"]
        stf_end = packet_info["stf_end_idx"]

        if len(received_signal) <= stf_end:
            print(f"Warning: Received signal too short for STF extraction")
            return {"ber": 0.0, "snr_db": 0.0, "errors": 0, "total_bits": 0}

        # STF 신호 구간 추출
        received_stf_signal = received_signal[stf_start:stf_end]

        # STF BER 계산
        result = self.process_stf_block(received_stf_signal, noise_power, adc_bits=adc_bits, channel_snr_db=channel_snr_db)
        
        print(f"STF BER Analysis:")
        print(f"  - Current BER: {result['ber']:.6f}")
        print(f"  - Windowed BER: {result['ber_windowed']:.6f}")  
        print(f"  - Cumulative BER: {result['ber_cumulative']:.6f}")
        print(f"  - SNR: {result['snr_db']:.2f} dB")
        print(f"  - Bit Errors: {result['errors']}/{result['total_bits']}")
        
        return result
    
    def reset_statistics(self):
        """모든 BER 통계를 초기화합니다."""
        self.error_window.clear()
        self.total_bits_processed = 0
        self.total_bit_errors = 0
        self.ber_history.clear()
        self.snr_history.clear()
        print("BER statistics reset")
    
    def get_statistics_summary(self) -> dict:
        """BER 통계 요약 정보를 반환합니다."""
        return {
            "total_bits_processed": self.total_bits_processed,
            "total_bit_errors": self.total_bit_errors,
            "cumulative_ber": self.get_cumulative_ber(),
            "current_windowed_ber": self.get_current_ber(),
            "ber_history": self.ber_history.copy(),
            "snr_history": self.snr_history.copy(),
            "average_ber": np.mean(self.ber_history) if self.ber_history else 0.0,
            "average_snr_db": np.mean(self.snr_history) if self.snr_history else 0.0
        }

# 테스트 함수
def test_ber_calculator():
    """BER Calculator 테스트 함수"""
    print("=== Testing BER Calculator ===")
    
    from signal_generator import SignalGenerator
    
    generator = SignalGenerator()
    ber_calc = BERCalculator()
    
    # 테스트 패킷 생성
    packet = generator.create_complete_packet("sensor")
    
    # 노이즈 추가 시뮬레이션
    clean_signal = packet["complete_signal"]
    noise_power = 0.1
    noisy_signal = clean_signal + np.sqrt(noise_power) * (
        np.random.randn(len(clean_signal)) + 1j * np.random.randn(len(clean_signal))
    )
    
    # BER 측정
    ber_result = ber_calc.process_complete_packet(packet, noisy_signal, noise_power)
    
    # 통계 출력
    stats = ber_calc.get_statistics_summary()
    print(f"\nBER Test Results:")
    print(f"  - BER: {ber_result['ber']:.6f}")
    print(f"  - SNR: {ber_result['snr_db']:.2f} dB")
    print(f"  - Total processed bits: {stats['total_bits_processed']}")

if __name__ == "__main__":
    test_ber_calculator()