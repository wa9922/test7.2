# adc.py

"""
ADC (Analog-to-Digital Converter) 모델 구현
실제 양자화를 시뮬레이션하는 ADC 클래스들

GNURadio 호환:
- Short (int16): 16비트 정수
- Byte (uint8): 8비트 부호 없는 정수
"""

import numpy as np

class BaseADC:
    """
    기본 ADC 클래스
    N-bit ADC의 양자화 동작을 시뮬레이션
    """

    def __init__(self, n_bits: int, vref: float = 1.0):
        """
        ADC 초기화

        Args:
            n_bits: ADC 비트 수
            vref: 참조 전압 (양자화 범위: -vref ~ +vref)
        """
        self.n_bits = n_bits
        self.vref = vref
        self.levels = 2 ** n_bits
        self.step = (2 * vref) / self.levels

        # 양자화 레벨 계산
        self.max_value = 2**(n_bits-1) - 1
        self.min_value = -(2**(n_bits-1))

    def quantize(self, x: np.ndarray) -> np.ndarray:
        """
        신호를 양자화 (float 출력)

        Args:
            x: 입력 신호

        Returns:
            양자화된 신호 (float32, GNURadio Float 타입 호환)
        """
        # 입력을 vref 범위로 클리핑
        x_clipped = np.clip(x, -self.vref, self.vref)

        # 양자화 스텝으로 반올림 (GNURadio 호환: float32)
        x_quantized = (np.round(x_clipped / self.step) * self.step).astype(np.float32)

        return x_quantized

    def quantize_to_int(self, x: np.ndarray) -> np.ndarray:
        """
        신호를 정수 레벨로 양자화

        Args:
            x: 입력 신호

        Returns:
            정수 양자화 레벨 (int16, GNURadio Short 타입 호환)
        """
        # 입력을 vref 범위로 클리핑
        x_clipped = np.clip(x, -self.vref, self.vref)

        # 정수 레벨로 변환 (GNURadio 호환: int16)
        x_int = np.round(x_clipped / self.step)
        x_int = np.clip(x_int, self.min_value, self.max_value)

        return x_int.astype(np.int16)

    def convert(self, x: np.ndarray) -> np.ndarray:
        """
        quantize()의 별칭 (호환성용)
        """
        return self.quantize(x)


class ADC3bit(BaseADC):
    """
    3-bit ADC (저전력 모드용)
    8개 양자화 레벨 (-4 ~ 3)
    """

    def __init__(self, vref: float = 1.0):
        super().__init__(n_bits=3, vref=vref)


class ADC10bit(BaseADC):
    """
    10-bit ADC (고성능 모드용)
    1024개 양자화 레벨 (-512 ~ 511)
    """

    def __init__(self, vref: float = 1.0):
        super().__init__(n_bits=10, vref=vref)