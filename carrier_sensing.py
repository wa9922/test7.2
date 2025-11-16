# carrier_sensing.py

"""
Carrier Sensing (CS) 관련 기능들을 정의하는 모듈입니다.
수신 신호로부터 패킷의 존재 여부를 판단하는 세 가지 주요 방법을 구현합니다.
1. Saturation Detection: ADC 포화 여부 감지
2. Energy Detection: 신호 에너지 기반 감지  
3. Correlation Detection: 알려진 시퀀스(STF)와의 상관관계 기반 감지

C++ 코드의 ah_cs_*.cpp 파일들을 Python으로 포팅했습니다.
"""

import numpy as np
from config import ENERGY_DETECTION_THRESHOLD, CORRELATION_THRESHOLD, SATURATION_THRESHOLD, STF_BITS
from signal_generator import SignalGenerator

class SaturationDetector:
    """
    ADC 포화 감지 클래스 (ah_cs_sat.cpp 포팅)
    디지털 신호가 ADC의 최대/최소 값에 도달하여 포화되는 현상을 감지합니다.
    """
    
    def __init__(self, adc_resolution: int = 10):
        """
        Saturation Detector 초기화
        
        Args:
            adc_resolution (int): ADC 해상도 (bits)
        """
        self.adc_resolution = adc_resolution
        self.max_value = 2**(adc_resolution-1) - 1  # 예: 10bit → 511
        self.min_value = -(2**(adc_resolution-1))   # 예: 10bit → -512
        
        # 임계값 설정 (C++ 코드의 cs_thr에 해당)
        if adc_resolution == 3:
            self.threshold = SATURATION_THRESHOLD["3bit"]
        else:
            self.threshold = SATURATION_THRESHOLD["10bit"]
        
        self.detection_count = 0
        self.total_samples = 0
        
        print(f"Saturation Detector initialized")
        print(f"ADC resolution: {adc_resolution} bits")
        print(f"Range: [{self.min_value}, {self.max_value}]")
        print(f"Saturation threshold: ±{self.threshold}")
    
    def check(self, signal: np.ndarray) -> dict:
        """
        입력 신호의 포화 여부를 확인합니다.
        
        Args:
            signal (np.ndarray): 검사할 신호 샘플 (복소수)
            
        Returns:
            dict: 포화 감지 결과 및 통계
        """
        # 복소수 신호를 실수와 허수로 분리
        real_part = np.real(signal)
        imag_part = np.imag(signal)
        
        # 포화 감지 (절대값이 임계값 이상인 샘플 수 계산)
        real_saturated = np.sum(np.abs(real_part) >= self.threshold)
        imag_saturated = np.sum(np.abs(imag_part) >= self.threshold)
        total_saturated = real_saturated + imag_saturated
        
        # 포화율 계산
        total_samples = len(signal) * 2  # I/Q 각각
        saturation_rate = total_saturated / total_samples if total_samples > 0 else 0
        
        # 포화 감지 여부 결정 (C++ 로직 따라 설정 가능)
        is_saturated = total_saturated > 0
        
        # 통계 업데이트
        self.detection_count += int(is_saturated)
        self.total_samples += len(signal)
        
        result = {
            "detected": is_saturated,
            "real_saturated_samples": real_saturated,
            "imag_saturated_samples": imag_saturated,
            "total_saturated_samples": total_saturated,
            "saturation_rate": saturation_rate,
            "threshold": self.threshold
        }
        
        return result

class EnergyDetector:
    """
    신호 에너지 기반 감지 클래스 (ah_cs_acrpwr*.cpp 포팅)
    수신 신호의 평균 전력을 계산하여 임계값과 비교합니다.
    """
    
    def __init__(self, threshold_db: float = ENERGY_DETECTION_THRESHOLD):
        """
        Energy Detector 초기화
        
        Args:
            threshold_db (float): 에너지 감지 임계값 (dBm)
        """
        self.threshold_db = threshold_db
        self.threshold_linear = 10**(threshold_db / 10)  # dBm을 선형 스케일로 변환
        
        self.detection_count = 0
        self.total_measurements = 0
        self.energy_history = []
        
        print(f"Energy Detector initialized")
        print(f"Threshold: {threshold_db} dBm ({self.threshold_linear:.6f} linear)")
    
    def check(self, signal: np.ndarray) -> dict:
        """
        입력 신호의 에너지가 임계값을 넘는지 확인합니다.
        
        Args:
            signal (np.ndarray): 검사할 신호 샘플 (복소수)
            
        Returns:
            dict: 에너지 감지 결과 및 통계
        """
        if len(signal) == 0:
            return {"detected": False, "power_db": -np.inf, "power_linear": 0}
        
        # 신호 전력 계산 (평균 제곱)
        power_linear = np.mean(np.abs(signal)**2)
        
        # dB 변환
        power_db = 10 * np.log10(power_linear) if power_linear > 0 else -np.inf
        
        # 임계값 비교
        is_detected = power_db > self.threshold_db
        
        # 통계 업데이트
        self.total_measurements += 1
        self.detection_count += int(is_detected)
        self.energy_history.append(power_db)
        
        # 히스토리 길이 제한 (메모리 절약)
        if len(self.energy_history) > 1000:
            self.energy_history.pop(0)
        
        result = {
            "detected": is_detected,
            "power_db": power_db,
            "power_linear": power_linear,
            "threshold_db": self.threshold_db,
            "margin_db": power_db - self.threshold_db,
            "detection_rate": self.detection_count / self.total_measurements
        }
        
        return result

class CorrelationDetector:
    """
    상관관계 기반 감지 클래스 (ah_cs_xcor*.cpp 포팅)
    수신 신호와 미리 알려진 STF 시퀀스 간의 상관관계를 계산합니다.
    """
    
    def __init__(self, threshold: float = CORRELATION_THRESHOLD):
        """
        Correlation Detector 초기화
        
        Args:
            threshold (float): 상관관계 임계값 (0~1)
        """
        self.threshold = threshold
        
        # STF 참조 신호 생성
        self.signal_generator = SignalGenerator()
        self.stf_reference_bits, self.stf_reference_signal = self.signal_generator.generate_stf_signal()
        
        self.detection_count = 0
        self.total_measurements = 0
        self.correlation_history = []
        
        print(f"Correlation Detector initialized")
        print(f"STF reference length: {len(self.stf_reference_signal)} samples")
        print(f"Correlation threshold: {threshold}")
    
    def compute_normalized_correlation(self, signal1: np.ndarray, signal2: np.ndarray) -> float:
        """
        두 신호 간의 정규화된 상호 상관관계를 계산합니다.
        
        Args:
            signal1 (np.ndarray): 첫 번째 신호
            signal2 (np.ndarray): 두 번째 신호
            
        Returns:
            float: 정규화된 상관관계 값 (0~1)
        """
        if len(signal1) == 0 or len(signal2) == 0:
            return 0.0
        
        # 길이를 맞춤
        min_len = min(len(signal1), len(signal2))
        s1_trimmed = signal1[:min_len]
        s2_trimmed = signal2[:min_len]
        
        # 상호 상관관계 계산 (내적)
        cross_correlation = np.abs(np.vdot(s1_trimmed, s2_trimmed))
        
        # 정규화 (각 신호의 에너지로 나눔)
        norm1 = np.linalg.norm(s1_trimmed)
        norm2 = np.linalg.norm(s2_trimmed)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        normalized_correlation = cross_correlation / (norm1 * norm2)
        
        return np.real(normalized_correlation)  # 실수 부분만 반환
    
    def check(self, signal: np.ndarray) -> dict:
        """
        입력 신호와 STF 참조 신호 간의 상관관계가 임계값을 넘는지 확인합니다.
        
        Args:
            signal (np.ndarray): 검사할 신호 샘플 (복소수)
            
        Returns:
            dict: 상관관계 감지 결과 및 통계
        """
        if len(signal) < len(self.stf_reference_signal):
            return {
                "detected": False,
                "correlation": 0.0,
                "threshold": self.threshold,
                "signal_too_short": True
            }
        
        # 슬라이딩 윈도우로 최대 상관관계 찾기
        max_correlation = 0.0
        best_position = 0
        
        window_size = len(self.stf_reference_signal)
        step_size = max(1, window_size // 4)  # 계산량 줄이기 위해 스텝 크기 설정
        
        for i in range(0, len(signal) - window_size + 1, step_size):
            signal_window = signal[i:i + window_size]
            correlation = self.compute_normalized_correlation(signal_window, self.stf_reference_signal)
            
            if correlation > max_correlation:
                max_correlation = correlation
                best_position = i
        
        # 임계값 비교
        is_detected = max_correlation > self.threshold
        
        # 통계 업데이트
        self.total_measurements += 1
        self.detection_count += int(is_detected)
        self.correlation_history.append(max_correlation)
        
        # 히스토리 길이 제한
        if len(self.correlation_history) > 1000:
            self.correlation_history.pop(0)
        
        result = {
            "detected": is_detected,
            "correlation": max_correlation,
            "threshold": self.threshold,
            "margin": max_correlation - self.threshold,
            "best_position": best_position,
            "detection_rate": self.detection_count / self.total_measurements,
            "signal_too_short": False
        }
        
        return result

class CarrierSensingTop:
    """
    전체 Carrier Sensing 시스템 통합 클래스 (ah_cs_top.cpp 포팅)
    3가지 감지 방법을 조합하여 최종 패킷 감지 결정을 내립니다.
    """
    
    def __init__(self, adc_resolution: int = 10):
        """
        Carrier Sensing 통합 시스템 초기화
        
        Args:
            adc_resolution (int): ADC 해상도
        """
        self.saturation_detector = SaturationDetector(adc_resolution)
        self.energy_detector = EnergyDetector()
        self.correlation_detector = CorrelationDetector()
        
        self.detection_history = []
        
        print(f"Carrier Sensing Top initialized with {adc_resolution}-bit ADC")
    
    def process_signal(self, signal: np.ndarray) -> dict:
        """
        입력 신호를 3가지 방법으로 분석하여 최종 감지 결과를 제공합니다.
        
        Args:
            signal (np.ndarray): 분석할 신호
            
        Returns:
            dict: 종합 감지 결과
        """
        # 개별 감지 결과 수집
        sat_result = self.saturation_detector.check(signal)
        energy_result = self.energy_detector.check(signal)  
        corr_result = self.correlation_detector.check(signal)
        
        # 종합 감지 결정 (OR 로직: 하나라도 감지되면 패킷 존재)
        # C++ 코드의 정확한 로직에 따라 수정 가능
        overall_detected = (
            sat_result["detected"] or 
            energy_result["detected"] or 
            corr_result["detected"]
        )
        
        # 신뢰도 점수 계산 (감지된 방법의 수)
        confidence_score = sum([
            sat_result["detected"],
            energy_result["detected"], 
            corr_result["detected"]
        ])
        
        combined_result = {
            "overall_detected": overall_detected,
            "confidence_score": confidence_score,
            "saturation": sat_result,
            "energy": energy_result,
            "correlation": corr_result,
            "detection_methods": {
                "saturation": sat_result["detected"],
                "energy": energy_result["detected"],
                "correlation": corr_result["detected"]
            }
        }
        
        # 히스토리 저장
        self.detection_history.append({
            "detected": overall_detected,
            "confidence": confidence_score,
            "timestamp": len(self.detection_history)
        })
        
        return combined_result
    
    def get_detection_statistics(self) -> dict:
        """Carrier Sensing 통계를 반환합니다."""
        if not self.detection_history:
            return {"no_data": True}
        
        total_detections = sum(1 for h in self.detection_history if h["detected"])
        
        return {
            "total_measurements": len(self.detection_history),
            "total_detections": total_detections,
            "detection_rate": total_detections / len(self.detection_history),
            "saturation_rate": self.saturation_detector.detection_count / self.saturation_detector.total_samples if self.saturation_detector.total_samples > 0 else 0,
            "energy_rate": self.energy_detector.detection_count / self.energy_detector.total_measurements if self.energy_detector.total_measurements > 0 else 0,
            "correlation_rate": self.correlation_detector.detection_count / self.correlation_detector.total_measurements if self.correlation_detector.total_measurements > 0 else 0
        }

# 테스트 함수
def test_carrier_sensing():
    """Carrier Sensing 모듈 테스트 함수"""
    print("=== Testing Carrier Sensing ===")
    
    from signal_generator import SignalGenerator
    
    generator = SignalGenerator()
    cs_system = CarrierSensingTop()
    
    # 테스트 신호 생성
    packet = generator.create_complete_packet("voice")
    test_signal = packet["complete_signal"]
    
    # 노이즈 추가
    noise_power = 0.05
    noisy_signal = test_signal + np.sqrt(noise_power) * (
        np.random.randn(len(test_signal)) + 1j * np.random.randn(len(test_signal))
    )
    
    # Carrier Sensing 실행
    result = cs_system.process_signal(noisy_signal)
    
    print(f"\nCarrier Sensing Results:")
    print(f"Overall detected: {result['overall_detected']}")
    print(f"Confidence score: {result['confidence_score']}/3")
    print(f"Saturation: {result['detection_methods']['saturation']}")
    print(f"Energy: {result['detection_methods']['energy']}")  
    print(f"Correlation: {result['detection_methods']['correlation']}")
    
    # 통계 출력
    stats = cs_system.get_detection_statistics()
    print(f"\nDetection Statistics: {stats}")

if __name__ == "__main__":
    test_carrier_sensing()