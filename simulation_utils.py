# simulation_utils.py

"""
시뮬레이션 유틸리티 함수들을 정의하는 모듈입니다.
트래픽 흐름 관리, 시간 추적, 데이터 수집, 플로팅 유틸을 제공합니다.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np


# -------------------------------
# 1) 트래픽/시간/디코딩 유틸
# -------------------------------

class TrafficFlowManager:
    """트래픽 흐름 패턴을 관리하는 클래스"""

    def __init__(self, traffic_types: List[str], gap_size: int = 2):
        """
        Args:
            traffic_types: 기본 트래픽 타입 리스트 (wake_up 제외)
            gap_size: 사이클 간 gap 크기 (패킷 수)
        """
        self.base_traffic_types = traffic_types
        self.gap_size = gap_size
        # 전체 트래픽 흐름: wake_up으로 시작
        self.traffic_flow = ["wake_up"] + traffic_types
        self.cycle_length = len(self.traffic_flow) + gap_size

    def get_traffic_type(self, packet_counter: int) -> Optional[str]:
        """
        패킷 번호에 따른 트래픽 타입 반환

        Args:
            packet_counter: 현재 패킷 번호

        Returns:
            트래픽 타입 문자열 또는 None (gap인 경우)
        """
        cycle_position = packet_counter % self.cycle_length

        if cycle_position < len(self.traffic_flow):
            return self.traffic_flow[cycle_position]
        else:
            # 트래픽 갭 (쉬는 시간)
            return None


class TimeSeriesDataCollector:
    """시간별 데이터를 수집하고 관리하는 클래스"""

    # 메모리 효율성을 위한 최대 데이터 포인트 수
    MAX_DATA_POINTS = 100000

    def __init__(self):
        """데이터 수집기 초기화"""
        self.data: Dict[str, List] = {
            'time': [],
            'traffic_type': [],
            'analog_power': [],
            'digital_power': [],
            'ber': [],
            'fsm_state': [],
            'gain': [],
            'snr': [],
            'signal_power': []
        }
        self.current_time_ms: float = 0.0

    def add_data_point(self,
                       traffic_type: str,
                       analog_power: float,
                       digital_power: float,
                       ber: float,
                       fsm_state: str,
                       gain: float,
                       duration_ms: float = 1.0,
                       snr: Optional[float] = None,
                       signal_power: Optional[float] = None) -> None:
        """
        새로운 데이터 포인트 추가
        """
        # 메모리 관리: 최대 크기 초과 시 오래된 데이터 제거
        if len(self.data['time']) >= self.MAX_DATA_POINTS:
            for key in self.data:
                if self.data[key]:
                    self.data[key].pop(0)

        self.current_time_ms += duration_ms

        self.data['time'].append(self.current_time_ms)
        self.data['traffic_type'].append(traffic_type)
        self.data['analog_power'].append(analog_power)
        self.data['digital_power'].append(digital_power)
        self.data['ber'].append(ber)
        self.data['fsm_state'].append(fsm_state)
        self.data['gain'].append(gain)
        self.data['snr'].append(snr if snr is not None else 0)
        self.data['signal_power'].append(signal_power if signal_power is not None else -np.inf)

    def get_data(self) -> Dict[str, List]:
        """수집된 데이터 반환"""
        return self.data

    def reset(self) -> None:
        """데이터 초기화"""
        for key in self.data:
            self.data[key] = []
        self.current_time_ms = 0.0

    def get_current_time(self) -> float:
        """현재 시간 반환 (ms)"""
        return self.current_time_ms


class SignalFieldDecoder:
    """Signal Field 디코딩 및 트래픽 타입 추출을 담당하는 클래스"""

    def __init__(self):
        """디코더 초기화"""
        self.traffic_mapping = {
            "00": "sensor",
            "01": "voice",
            "10": "video",
            "11": "wake_up"
        }

    def decode_traffic_type(self,
                            signal_field_signal: np.ndarray,
                            packet_info: Dict,
                            use_simulation_mode: bool = True) -> str:
        """
        Signal Field에서 트래픽 타입을 디코딩
        """
        if use_simulation_mode:
            # 시뮬레이션 모드: 원본 트래픽 타입 사용
            return packet_info.get('traffic_type', 'wake_up')

        # 실제 BPSK 복조 시도
        try:
            if signal_field_signal is None or len(signal_field_signal) < 2:
                return packet_info.get('traffic_type', 'wake_up')

            # BPSK 복조: 실수부의 부호로 비트 판정
            demodulated_bits = (np.real(signal_field_signal) > 0).astype(int)

            # 앞 2비트로 트래픽 타입 결정
            if len(demodulated_bits) >= 2:
                traffic_bits = "".join(str(bit) for bit in demodulated_bits[:2])
                return self.traffic_mapping.get(traffic_bits,
                                                packet_info.get('traffic_type', 'wake_up'))
        except Exception as e:
            # 복조 실패 시 fallback
            if hasattr(self, 'debug_mode') and self.debug_mode:
                print(f"Signal Field decoding failed: {e}")

        return packet_info.get('traffic_type', 'wake_up')


def calculate_block_size(stf_length_samples: int, min_block_ratio: float = 0.25) -> int:
    """
    처리 블록 크기 계산
    - STF 전체 길이를 한 블록으로 처리
    """
    return stf_length_samples


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """
    안전한 나눗셈 수행 (0으로 나누기 방지)
    """
    if denominator == 0:
        return default
    return numerator / denominator


# -------------------------------
# 2) 플로팅 유틸
# -------------------------------
import os
import matplotlib.pyplot as plt
from collections import defaultdict


def _ensure_dir(path: str):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def _per_packet_digital_energy(results: List[Dict]) -> List[float]:
    """
    results[i]['digital']['total_energy_pj']가 누적값인 경우,
    패킷별 디지털 에너지는 차분으로 계산한다.
    """
    out = []
    prev = 0.0
    for r in results:
        tot = float(r.get('digital', {}).get('total_energy_pj', 0.0))
        delta = max(0.0, tot - prev)
        out.append(delta)
        prev = tot
    return out


def plot_ber_by_traffic(results: List[Dict], outdir: str = "."):
    by_t = defaultdict(list)
    for r in results:
        t = r.get('traffic', 'unknown')
        ber = float(r.get('final_ber', {}).get('ber', 0.0))
        by_t[t].append(ber)
    traffic = sorted(by_t.keys())
    avg_ber = [sum(by_t[t]) / max(1, len(by_t[t])) for t in traffic]

    _ensure_dir(outdir)
    plt.figure(figsize=(8, 6))
    plt.bar(traffic, avg_ber)
    plt.title("BER Performance by Traffic Type")
    plt.xlabel("Traffic Type")
    plt.ylabel("Average BER")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "comparison_01_ber_by_traffic.png"))
    plt.close()


def plot_ber_vs_snr(results: List[Dict], outdir: str = "."):
    by_s = defaultdict(list)
    for r in results:
        snr = float(r.get('snr_db', r.get('snr', 0.0)))
        ber = float(r.get('final_ber', {}).get('ber', 0.0))
        by_s[snr].append(ber)
    snrs = sorted(by_s.keys())
    avg_ber = [sum(by_s[s]) / max(1, len(by_s[s])) for s in snrs]

    _ensure_dir(outdir)
    plt.figure(figsize=(8, 6))
    plt.semilogy(snrs, avg_ber, marker='o')
    plt.grid(True, which='both', ls=':')
    plt.title("BER Performance vs SNR")
    plt.xlabel("SNR (dB)")
    plt.ylabel("Average BER")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "comparison_02_ber_vs_snr.png"))
    plt.close()


def plot_analog_power_by_traffic(results: List[Dict], outdir: str = "."):
    by_t = defaultdict(list)
    for r in results:
        t = r.get('traffic', 'unknown')
        ap = float(r.get('analog_power', {}).get('avg_mw', 0.0))
        by_t[t].append(ap)
    traffic = sorted(by_t.keys())
    avg_pwr = [sum(by_t[t]) / max(1, len(by_t[t])) for t in traffic]

    _ensure_dir(outdir)
    plt.figure(figsize=(8, 6))
    plt.bar(traffic, avg_pwr)
    plt.title("Analog Power Consumption by Traffic Type")
    plt.xlabel("Traffic Type")
    plt.ylabel("Average Analog Power (mW)")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "comparison_03_analog_power_by_traffic.png"))
    plt.close()


def plot_digital_energy_by_traffic(results: List[Dict], outdir: str = "."):
    per_pkt = _per_packet_digital_energy(results)
    by_t = defaultdict(list)
    for r, e in zip(results, per_pkt):
        t = r.get('traffic', 'unknown')
        by_t[t].append(e)
    traffic = sorted(by_t.keys())
    avg_e = [sum(by_t[t]) / max(1, len(by_t[t])) for t in traffic]

    _ensure_dir(outdir)
    plt.figure(figsize=(8, 6))
    plt.bar(traffic, avg_e)
    plt.title("Digital Energy Consumption by Traffic Type")
    plt.xlabel("Traffic Type")
    plt.ylabel("Average Digital Energy per Packet (pJ)")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "comparison_04_digital_energy_by_traffic.png"))
    plt.close()


def plot_fsm_power(results: List[Dict], outdir: str = "."):
    by_state = defaultdict(list)
    for r in results:
        st = r.get('final_state', 'UNKNOWN')
        ap = float(r.get('analog_power', {}).get('avg_mw', 0.0))
        by_state[st].append(ap)

    states = sorted(by_state.keys())
    avg_p = [sum(by_state[s]) / max(1, len(by_state[s])) for s in states]

    _ensure_dir(outdir)
    plt.figure(figsize=(10, 5))
    plt.bar(states, avg_p)
    plt.title("Adaptive AGC: Analog Power by FSM State")
    plt.xlabel("FSM State")
    plt.ylabel("Average Analog Power (mW)")
    plt.xticks(rotation=30, ha='right')
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "comparison_05_fsm_power.png"))
    plt.close()

    counts = [len(by_state[s]) for s in states]
    if sum(counts) > 0:
        plt.figure(figsize=(6, 6))
        plt.pie(counts, labels=states, autopct="%0.1f%%", startangle=90)
        plt.axis('equal')
        plt.title("Adaptive AGC: FSM State Distribution")
        plt.tight_layout()
        plt.savefig(os.path.join(outdir, "comparison_05_fsm_power_pie.png"))
        plt.close()


def plot_ber_over_time(results: List[Dict], outdir: str = "."):
    xs = list(range(len(results)))
    ys = [float(r.get('final_ber', {}).get('ber', 0.0)) for r in results]
    _ensure_dir(outdir)
    plt.figure(figsize=(12, 6))
    plt.plot(xs, ys, lw=1)
    plt.title("BER Over Time")
    plt.xlabel("Packet Index")
    plt.ylabel("BER")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "comparison_06_ber_over_time.png"))
    plt.close()


def plot_analog_power_over_time(results: List[Dict], outdir: str = "."):
    xs = list(range(len(results)))
    ys = [float(r.get('analog_power', {}).get('avg_mw', 0.0)) for r in results]
    _ensure_dir(outdir)
    plt.figure(figsize=(12, 6))
    plt.plot(xs, ys, lw=1)
    plt.title("Analog Power Over Time")
    plt.xlabel("Packet Index")
    plt.ylabel("Analog Power (mW)")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "comparison_07_analog_power_over_time.png"))
    plt.close()


def plot_total_energy(results: List[Dict], outdir: str = "."):
    total_analog_mj = float(results[-1].get('analog_power', {}).get('total_mj', 0.0)) if results else 0.0
    total_digital_pj = float(results[-1].get('digital', {}).get('total_energy_pj', 0.0)) if results else 0.0

    _ensure_dir(outdir)
    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    plt.bar(['Adaptive'], [total_analog_mj])
    plt.title("Total Analog Energy Consumption")
    plt.ylabel("Total Analog Energy (mJ)")

    plt.subplot(1, 2, 2)
    plt.bar(['Adaptive'], [total_digital_pj])
    plt.title("Total Digital Energy Consumption")
    plt.ylabel("Total Digital Energy (pJ)")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "comparison_08_total_energy.png"))
    plt.close()


def plot_summary_table(results: List[Dict], outdir: str = "."):
    if not results:
        return
    avg_ber = sum(float(r.get('final_ber', {}).get('ber', 0.0)) for r in results) / len(results)
    avg_analog_pwr = sum(float(r.get('analog_power', {}).get('avg_mw', 0.0)) for r in results) / len(results)
    total_analog_mj = float(results[-1].get('analog_power', {}).get('total_mj', 0.0))
    total_digital_pj = float(results[-1].get('digital', {}).get('total_energy_pj', 0.0))
    pkts = len(results)

    _ensure_dir(outdir)
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.axis('off')
    table = ax.table(
        cellText=[
            ["Average BER", f"{avg_ber:.6f}"],
            ["Avg Analog Power (mW)", f"{avg_analog_pwr:.2f}"],
            ["Total Analog Energy (mJ)", f"{total_analog_mj:.2f}"],
            ["Total Digital Energy (pJ)", f"{total_digital_pj:.2f}"],
            ["Packets Processed", f"{pkts}"],
        ],
        colLabels=["Metric", "Adaptive (Proposed)"],
        loc='center', cellLoc='center'
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 1.5)
    plt.title("Performance Summary")
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "comparison_09_summary_table.png"))
    plt.close()


def plot_simulation_results(results: List[Dict], outdir: str = ".", show: bool = False):
    """
    메인에서 수집한 results(list of dict])를 받아 일괄 그래프 저장
      comparison_01_...png ~ comparison_09_...png
    각 원소는 최소한 다음 키를 포함해야 함:
      - 'traffic': str
      - 'snr_db': float
      - 'final_ber': {'ber': float, ...}
      - 'analog_power': {'avg_mw': float, 'total_mj': float}
      - 'digital': {'total_energy_pj': float}
      - 'final_state': str
    """
    _ensure_dir(outdir)
    plot_ber_by_traffic(results, outdir)
    plot_ber_vs_snr(results, outdir)
    plot_analog_power_by_traffic(results, outdir)
    plot_digital_energy_by_traffic(results, outdir)
    plot_fsm_power(results, outdir)
    plot_ber_over_time(results, outdir)
    plot_analog_power_over_time(results, outdir)
    plot_total_energy(results, outdir)
    plot_summary_table(results, outdir)
    if show:
        plt.show()
