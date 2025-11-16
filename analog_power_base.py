# analog_power_base.py
"""
아날로그 전력 모델의 공통 베이스 클래스
MAX2829(고성능)과 MAX2830(저전력) 모델의 공통 인터페이스 제공
"""

import numpy as np
from abc import ABC, abstractmethod
class LNA:
    def __init__(self, gain_dB=15.0, nf_dB=3.0, seed=12345):
        self.gain_lin = 10 ** (gain_dB / 20.0)
        self.nf_lin = 10 ** (nf_dB / 10.0) if nf_dB > 0 else 0.0
        self.rng = np.random.default_rng(seed)

    def process(self, in_signal: np.ndarray):
        """
        복소 입력 신호 (I/Q 통합된 complex array)에 대해
        LNA gain + noise 적용
        """
        out_signal = in_signal * self.gain_lin
        if self.nf_lin > 0:
            noise_std = np.sqrt(self.nf_lin / 2.0)
            noise = (self.rng.normal(0, noise_std, size=in_signal.shape) +
                     1j * self.rng.normal(0, noise_std, size=in_signal.shape))
            out_signal += noise
        return out_signal
    
class AnalogPowerModelBase(ABC):
    """아날로그 전력 모델 추상 베이스 클래스"""
    
    def __init__(self, vcc: float):
        """
        Args:
            vcc: 공급 전압 (V)
        """
        self.VCC = vcc
        self.power_map = {}
        self._initialize_power_map()
    
    @abstractmethod
    def _initialize_power_map(self):
        """전력 맵을 초기화하는 추상 메소드"""
        pass
    
    def get_power(self, mode: str) -> float:
        """
        특정 모드의 전력 소비를 반환
        
        Args:
            mode: 동작 모드 ('STANDBY', 'RX' 등)
            
        Returns:
            전력 소비량 (mW)
        """
        return self.power_map.get(mode.upper(), 0)
    
    def get_energy_consumption(self, mode: str, duration_ms: float) -> float:
        """
        특정 모드에서의 에너지 소비량 계산
        
        Args:
            mode: 동작 모드
            duration_ms: 모드 유지 시간 (ms)
            
        Returns:
            소비 에너지 (mJ)
        """
        power_mw = self.get_power(mode)
        return power_mw * (duration_ms / 1000)
    
    def get_supported_modes(self) -> list:
        """지원하는 모드 목록 반환"""
        return list(self.power_map.keys())


class MAX2829PowerModel(AnalogPowerModelBase):
    """MAX2829 고성능 AGC 전력 모델"""
    
    def __init__(self, vcc: float = 2.7):
        super().__init__(vcc)
    
    def _initialize_power_map(self):
        """MAX2829 전력 맵 초기화"""
        self.power_map = {
            'STANDBY': 68e-3 * self.VCC * 1000,   # ≈ 184 mW
            'RX':     145e-3 * self.VCC * 1000,   # ≈ 392 mW
        }


class MAX2830PowerModel(AnalogPowerModelBase):
    """MAX2830 저전력 AGC 전력 모델"""
    
    def __init__(self, vcc: float = 2.8):
        super().__init__(vcc)
    
    def _initialize_power_map(self):
        """MAX2830 전력 맵 초기화"""
        self.power_map = {
            'STANDBY': 28e-3 * self.VCC * 1000,   # ≈ 78.4 mW
            'RX':      62e-3 * self.VCC * 1000,   # ≈ 173.6 mW
        }