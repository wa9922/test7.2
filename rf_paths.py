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


class UnifiedRFPath:
    """
    통일된 RF 프론트엔드 경로 (Multi-Stage AGC)

    실제 AGC 시스템과 동일한 계층적 gain control:
    - LNA: Discrete gain levels (coarse adjustment)
    - VGA: Continuous gain (fine adjustment)
    - 전력 소비 항상 동일

    구조: [LNA] → [Mixer] → [VGA] → [LPF]
           ↑ discrete      ↑ continuous
           └───────────────┴─── Hierarchical Gain Control Feedback

    동작 방식:
    1. VGA 먼저 조절 (fine tuning, 빠른 응답)
    2. VGA 범위 초과 시 LNA 조절 (coarse tuning, 느린 응답)
    """

    def __init__(self, lpf_alpha: float = 0.2):
        """
        통일된 RF 경로 초기화

        Args:
            lpf_alpha: LPF 필터 계수
        """
        # LNA discrete gain levels (실제 RF 칩과 유사)
        # MAX2829 예시: Low=0dB, Mid=15dB, High=30dB
        self.lna_gains_db = [0, 15, 30]
        self.current_lna_index = 1  # Mid gain (15dB)에서 시작

        # VGA continuous gain range
        self.vga_gain_db = 20.0      # 초기값 (mid-range)
        self.vga_min_db = 0.0
        self.vga_max_db = 40.0

        # LPF 설정
        self.lpf_alpha = lpf_alpha

        # Gain transition thresholds
        self.vga_high_threshold = self.vga_max_db - 5  # VGA 35dB 넘으면 LNA 조절
        self.vga_low_threshold = self.vga_min_db + 5   # VGA 5dB 밑이면 LNA 조절

        print(f"Multi-Stage AGC initialized: LNA={self.lna_gains_db[self.current_lna_index]}dB (discrete), VGA={self.vga_gain_db}dB (continuous)")

    def run(self, x: np.ndarray) -> np.ndarray:
        """
        신호를 통일된 RF 경로로 처리

        Args:
            x: 입력 신호

        Returns:
            처리된 신호
        """
        # LNA → Mixer → VGA → LPF
        current_lna_gain = self.lna_gains_db[self.current_lna_index]
        x = lna(x, current_lna_gain)
        x = mixer(x, lo=1.0)
        x = vga(x, self.vga_gain_db)
        x = lpf(x, self.lpf_alpha)
        return x

    def update_gain_hierarchical(self, peak: float) -> dict:
        """
        계층적 AGC 업데이트 (Multi-Stage Gain Control)

        동작 순서:
        1. VGA fine adjustment (continuous, 빠름)
        2. VGA 범위 체크
        3. VGA 한계 도달 시 LNA coarse adjustment (discrete, 느림)

        Args:
            peak: 신호 peak 값 (0-1 normalized)

        Returns:
            dict: 변경 정보 {'lna_changed': bool, 'vga_changed': bool, 'total_gain_db': float}
        """
        lna_changed = False
        vga_changed = False
        old_lna_index = self.current_lna_index
        old_vga_gain = self.vga_gain_db

        # Step 1: VGA Fine Adjustment (연속 조절)
        if peak > 0.9:
            # 포화 방지: VGA 감소
            self.vga_gain_db -= 1.0
            vga_changed = True
        elif peak < 0.25:
            # SNR 향상: VGA 증가
            self.vga_gain_db += 1.0
            vga_changed = True

        # Step 2: VGA 범위 체크 후 LNA Coarse Adjustment (단계별 조절)
        if self.vga_gain_db > self.vga_high_threshold:
            # VGA가 최대 근처 → LNA 감소 (신호 강함)
            if self.current_lna_index > 0:
                self.current_lna_index -= 1  # LNA gain down (30→15 또는 15→0)
                self.vga_gain_db = 20.0      # VGA 중간값으로 리셋
                lna_changed = True
                print(f"  [LNA DOWN] {self.lna_gains_db[old_lna_index]}dB → {self.lna_gains_db[self.current_lna_index]}dB, VGA reset to {self.vga_gain_db}dB")

        elif self.vga_gain_db < self.vga_low_threshold:
            # VGA가 최소 근처 → LNA 증가 (신호 약함)
            if self.current_lna_index < len(self.lna_gains_db) - 1:
                self.current_lna_index += 1  # LNA gain up (0→15 또는 15→30)
                self.vga_gain_db = 20.0      # VGA 중간값으로 리셋
                lna_changed = True
                print(f"  [LNA UP] {self.lna_gains_db[old_lna_index]}dB → {self.lna_gains_db[self.current_lna_index]}dB, VGA reset to {self.vga_gain_db}dB")

        # Step 3: VGA 범위 제한 (clipping)
        self.vga_gain_db = np.clip(self.vga_gain_db, self.vga_min_db, self.vga_max_db)

        return {
            'lna_changed': lna_changed,
            'vga_changed': vga_changed,
            'old_lna_db': self.lna_gains_db[old_lna_index],
            'new_lna_db': self.lna_gains_db[self.current_lna_index],
            'old_vga_db': old_vga_gain,
            'new_vga_db': self.vga_gain_db,
            'total_gain_db': self.get_total_gain()
        }

    def set_vga_gain(self, gain_db: float):
        """
        VGA 이득 직접 설정 (호환성 유지)

        Args:
            gain_db: VGA 이득 (dB)
        """
        self.vga_gain_db = np.clip(gain_db, self.vga_min_db, self.vga_max_db)

    def get_total_gain(self) -> float:
        """
        총 이득 반환 (LNA + VGA)

        Returns:
            총 이득 (dB)
        """
        return self.lna_gains_db[self.current_lna_index] + self.vga_gain_db

    def set_total_gain(self, target_gain_db: float):
        """
        총 이득을 설정 (LNA + VGA 자동 분배)

        계층적 gain 분배:
        1. 가능한 한 VGA로 조절 (continuous, 빠름)
        2. VGA 범위 초과 시 LNA 조절 (discrete, 느림)

        Args:
            target_gain_db: 목표 총 이득 (dB)
        """
        # Range 체크
        min_total = self.lna_gains_db[0] + self.vga_min_db  # 0 + 0 = 0 dB
        max_total = self.lna_gains_db[-1] + self.vga_max_db  # 30 + 40 = 70 dB
        target_gain_db = np.clip(target_gain_db, min_total, max_total)

        # LNA 선택 (가능한 한 VGA 사용 우선)
        best_lna_index = 0
        best_vga_gain = 0.0

        for lna_index in range(len(self.lna_gains_db)):
            lna_gain = self.lna_gains_db[lna_index]
            required_vga_gain = target_gain_db - lna_gain

            # VGA 범위 내인 경우
            if self.vga_min_db <= required_vga_gain <= self.vga_max_db:
                best_lna_index = lna_index
                best_vga_gain = required_vga_gain
                break
        else:
            # 모든 LNA 레벨에서 VGA 범위 초과하는 경우
            # 가장 가까운 조합 선택
            if target_gain_db < self.lna_gains_db[0] + self.vga_min_db:
                # Too low
                best_lna_index = 0
                best_vga_gain = self.vga_min_db
            else:
                # Too high
                best_lna_index = len(self.lna_gains_db) - 1
                best_vga_gain = self.vga_max_db

        # 설정 적용
        self.current_lna_index = best_lna_index
        self.vga_gain_db = best_vga_gain

    def get_lna_gain(self) -> float:
        """현재 LNA 이득 반환"""
        return self.lna_gains_db[self.current_lna_index]

    def get_vga_gain(self) -> float:
        """현재 VGA 이득 반환"""
        return self.vga_gain_db