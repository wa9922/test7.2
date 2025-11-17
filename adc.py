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
            x: 입력 신호 (real 또는 complex)

        Returns:
            양자화된 신호 (float32 또는 complex64, GNURadio 호환)
        """
        # Complex 신호 처리: I/Q 각각 양자화
        if np.iscomplexobj(x):
            i_quantized = self.quantize(x.real)
            q_quantized = self.quantize(x.imag)
            return (i_quantized + 1j * q_quantized).astype(np.complex64)

        # Real 신호 처리
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

    def truncate_to_bits(self, x: np.ndarray, target_bits: int) -> np.ndarray:
        """
        디지털 신호를 더 낮은 비트로 잘라내기 (Digital Truncation)

        예: 10비트 신호 (0~1023) → 5비트 (0~31)로 상위 비트만 사용

        ⚠️ 중요: truncation 시 실제 양자화 에러 반영
        - 5-bit: 32 levels → 큰 양자화 에러 → 높은 BER
        - 10-bit: 1024 levels → 작은 양자화 에러 → 낮은 BER

        Args:
            x: 입력 신호 (이미 양자화된, real 또는 complex)
            target_bits: 목표 비트 수

        Returns:
            truncated 신호 (float32 또는 complex64, 더 적은 레벨만 사용)
        """
        if target_bits >= self.n_bits:
            # truncation 불필요
            if np.iscomplexobj(x):
                return x.astype(np.complex64)
            return x.astype(np.float32)

        # Complex 신호 처리: I/Q 각각 truncate
        if np.iscomplexobj(x):
            i_truncated = self.truncate_to_bits(x.real, target_bits)
            q_truncated = self.truncate_to_bits(x.imag, target_bits)
            return (i_truncated + 1j * q_truncated).astype(np.complex64)

        # Real 신호 처리
        # target_bits에 해당하는 양자화 스텝 계산 (현실적 양자화)
        target_levels = 2**target_bits
        target_step = (2 * self.vref) / target_levels

        # 입력을 target_bits 해상도로 직접 양자화
        x_clipped = np.clip(x, -self.vref, self.vref)
        x_truncated = np.round(x_clipped / target_step) * target_step

        # vref 범위로 다시 클리핑 (오버플로우 방지)
        x_truncated = np.clip(x_truncated, -self.vref, self.vref)

        return x_truncated.astype(np.float32)


class ADC5bit(BaseADC):
    """
    5-bit ADC (저전력 모드용)
    32개 양자화 레벨 (-16 ~ 15)
    """

    def __init__(self, vref: float = 1.0):
        super().__init__(n_bits=5, vref=vref)


class ADC10bit(BaseADC):
    """
    10-bit ADC (고성능 모드용, 항상 사용)
    1024개 양자화 레벨 (-512 ~ 511)
    """

    def __init__(self, vref: float = 1.0):
        super().__init__(n_bits=10, vref=vref)