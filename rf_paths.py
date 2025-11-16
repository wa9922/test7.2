# rf_paths.py

"""
RF 프론트엔드 경로 구현
저전력 경로와 고성능 경로를 분리하여 모델링
"""

import numpy as np


def lna(x: np.ndarray, gain_db: float) -> np.ndarray:
    """
    Low Noise Amplifier (LNA)

    Args:
        x: 입력 신호
        gain_db: 이득 (dB)

    Returns:
        증폭된 신호
    """
    gain_linear = 10**(gain_db/20)
    return x * gain_linear


def mixer(x: np.ndarray, lo: float = 1.0) -> np.ndarray:
    """
    믹서 (주파수 변환)
    베이스밴드 가정으로 단순 곱셈

    Args:
        x: 입력 신호
        lo: Local Oscillator 신호 (기본값 1.0 = 베이스밴드)

    Returns:
        믹싱된 신호
    """
    return x * lo


def vga(x: np.ndarray, gain_db: float) -> np.ndarray:
    """
    Variable Gain Amplifier (VGA)

    Args:
        x: 입력 신호
        gain_db: 가변 이득 (dB)

    Returns:
        증폭된 신호
    """
    gain_linear = 10**(gain_db/20)
    return x * gain_linear


def lpf(x: np.ndarray, alpha: float = 0.2) -> np.ndarray:
    """
    Low Pass Filter (LPF)
    1차 IIR 필터 구현

    Args:
        x: 입력 신호
        alpha: 필터 계수 (0 < alpha < 1, 작을수록 더 많이 필터링)

    Returns:
        필터링된 신호
    """
    if len(x) == 0:
        return x

    y = np.zeros_like(x)
    y[0] = x[0]

    for i in range(1, len(x)):
        y[i] = (1-alpha) * y[i-1] + alpha * x[i]

    return y


class HighPerfPath:
    """
    고성능 RF 경로
    LNA → Mixer → VGA → LPF
    """

    def __init__(self, lna_gain: float = 20, vga_gain: float = 0, lpf_alpha: float = 0.2):
        """
        고성능 경로 초기화

        Args:
            lna_gain: LNA 이득 (dB)
            vga_gain: VGA 이득 (dB)
            lpf_alpha: LPF 필터 계수
        """
        self.lna_gain = lna_gain
        self.vga_gain = vga_gain
        self.lpf_alpha = lpf_alpha

    def run(self, x: np.ndarray) -> np.ndarray:
        """
        신호를 고성능 경로로 처리

        Args:
            x: 입력 신호

        Returns:
            처리된 신호
        """
        # LNA → Mixer → VGA → LPF
        x = lna(x, self.lna_gain)
        x = mixer(x, lo=1.0)
        x = vga(x, self.vga_gain)
        x = lpf(x, self.lpf_alpha)
        return x

    def set_gains(self, lna_gain: float = None, vga_gain: float = None):
        """
        경로 이득 설정

        Args:
            lna_gain: LNA 이득 (dB)
            vga_gain: VGA 이득 (dB)
        """
        if lna_gain is not None:
            self.lna_gain = lna_gain
        if vga_gain is not None:
            self.vga_gain = vga_gain


class LowPowerPath:
    """
    저전력 RF 경로
    LNA → Mixer → LPF (VGA 없음)
    coarse/fine gain을 LNA에서 처리
    """

    def __init__(self, coarse_gain: float = 6, fine_gain: float = 0, lpf_alpha: float = 0.2):
        """
        저전력 경로 초기화

        Args:
            coarse_gain: Coarse 이득 (dB)
            fine_gain: Fine 이득 (dB)
            lpf_alpha: LPF 필터 계수
        """
        self.coarse_gain = coarse_gain
        self.fine_gain = fine_gain
        self.lpf_alpha = lpf_alpha

    def run(self, x: np.ndarray) -> np.ndarray:
        """
        신호를 저전력 경로로 처리

        Args:
            x: 입력 신호

        Returns:
            처리된 신호
        """
        # 전체 이득 = coarse + fine
        total_gain_db = self.coarse_gain + self.fine_gain

        # LNA → Mixer → LPF (VGA 없음)
        x = lna(x, total_gain_db)
        x = mixer(x, lo=1.0)
        x = lpf(x, self.lpf_alpha)
        return x

    def set_gains(self, coarse_gain: float = None, fine_gain: float = None):
        """
        경로 이득 설정

        Args:
            coarse_gain: Coarse 이득 (dB)
            fine_gain: Fine 이득 (dB)
        """
        if coarse_gain is not None:
            self.coarse_gain = coarse_gain
        if fine_gain is not None:
            self.fine_gain = fine_gain