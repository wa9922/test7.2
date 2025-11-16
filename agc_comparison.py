#!/usr/bin/env python3

"""
AGC 방식 비교 시뮬레이션
- 종래 방식: 저전력 고정 AGC, 고성능 고정 AGC
- 제안 방식: Adaptive AGC
"""

import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple
import copy

from main_agc_system import AgcSystem
from agc_fsm import AgcFsm, AgcState
from config import TRAFFIC_ADC_RESOLUTION
from power_measurement import DigitalComputationMeasurement, AnalogPowerMeasurement


def calculate_average_results(accumulated_results: Dict, traffic_types: List[str], snr_values: List[float]) -> Dict:
    """1000회 반복 결과의 평균을 계산"""

    avg_results = {}

    for name in accumulated_results.keys():
        avg_results[name] = {
            'ber_by_traffic': {},
            'ber_by_snr': {},
            'power_by_traffic': {},
            'power_by_state': {},
            'time_series': {
                'ber': [],
                'analog_power': [],
                'digital_energy': []
            },
            'total_analog_energy': 0,
            'total_digital_energy': 0,
            'packet_count': 0
        }

        # BER by traffic type 평균
        for traffic in traffic_types:
            all_bers = []
            for iteration in accumulated_results[name]:
                if traffic in iteration['ber_by_traffic']:
                    all_bers.extend(iteration['ber_by_traffic'][traffic])
            if all_bers:
                avg_results[name]['ber_by_traffic'][traffic] = all_bers  # 전체 데이터 보관

        # BER by SNR 평균
        for snr in snr_values:
            all_bers = []
            for iteration in accumulated_results[name]:
                if snr in iteration['ber_by_snr']:
                    all_bers.extend(iteration['ber_by_snr'][snr])
            if all_bers:
                avg_results[name]['ber_by_snr'][snr] = all_bers

        # Power by traffic type 평균
        for traffic in traffic_types:
            all_analog = []
            all_digital = []
            for iteration in accumulated_results[name]:
                if traffic in iteration['power_by_traffic']:
                    all_analog.extend(iteration['power_by_traffic'][traffic]['analog'])
                    all_digital.extend(iteration['power_by_traffic'][traffic]['digital'])
            if all_analog:
                avg_results[name]['power_by_traffic'][traffic] = {
                    'analog': all_analog,
                    'digital': all_digital
                }

        # Power by state 평균
        states = set()
        for iteration in accumulated_results[name]:
            states.update(iteration['power_by_state'].keys())

        for state in states:
            all_analog = []
            all_digital = []
            total_count = 0
            for iteration in accumulated_results[name]:
                if state in iteration['power_by_state']:
                    all_analog.extend(iteration['power_by_state'][state]['analog'])
                    all_digital.extend(iteration['power_by_state'][state]['digital'])
                    total_count += iteration['power_by_state'][state]['count']
            if all_analog:
                avg_results[name]['power_by_state'][state] = {
                    'analog': all_analog,
                    'digital': all_digital,
                    'count': total_count
                }

        # Time series 평균 (모든 반복의 데이터를 합침)
        for iteration in accumulated_results[name]:
            avg_results[name]['time_series']['ber'].extend(iteration['time_series']['ber'])
            avg_results[name]['time_series']['analog_power'].extend(iteration['time_series']['analog_power'])
            avg_results[name]['time_series']['digital_energy'].extend(iteration['time_series']['digital_energy'])

        # Total energy 평균
        total_analog = sum(iteration['total_analog_energy'] for iteration in accumulated_results[name])
        total_digital = sum(iteration['total_digital_energy'] for iteration in accumulated_results[name])
        total_packets = sum(iteration['packet_count'] for iteration in accumulated_results[name])

        avg_results[name]['total_analog_energy'] = total_analog / len(accumulated_results[name])
        avg_results[name]['total_digital_energy'] = total_digital / len(accumulated_results[name])
        avg_results[name]['packet_count'] = total_packets / len(accumulated_results[name])

    return avg_results


class FixedLowPowerAGC(AgcSystem):
    """
    저전력 고정 AGC - 항상 최소 전력 모드 (교수님 피드백 반영)

    - 아날로그: UnifiedRFPath (항상 동일)
    - 디지털: 항상 5비트 truncation 사용
    """

    def __init__(self):
        # use_correlation_detection=False: 제안 기법 기능 비활성화
        # initial_digital_bits=5: 항상 5비트 사용
        super().__init__(initial_digital_bits=5, use_correlation_detection=False)
        self.mode_name = "Low-Power Fixed AGC (5-bit)"
        # 초기 상태를 저전력 모드로 설정 - 최적화된 이득
        self.fsm.current_state = AgcState.LOW_GAIN_LP
        self.fsm.current_gain_index = 0  # index for gain
        self.current_gain_linear = 10**(10/20)  # 10 dB linear gain (from config)

    def process_packet(self, packet_info: Dict, channel_snr_db: float = 15.0) -> Dict:
        """패킷 처리 - 항상 저전력 모드 유지 (5비트 디지털 truncation)"""
        # 매번 저전력 상태로 강제 설정 (config에서 10dB)
        self.fsm.current_state = AgcState.LOW_GAIN_LP
        self.fsm.current_gain_index = 0
        self.current_gain_linear = 10**(10/20)  # 10 dB (from config)

        # 디지털 비트 고정 (5-bit truncation) - 모든 트래픽에 대해
        # ADC 하드웨어는 여전히 10-bit
        self.current_digital_bits = 5

        # FSM의 process_indication을 오버라이드하여 상태 변경 막기
        original_process = self.fsm.process_indication
        self.fsm.process_indication = lambda *args, **kwargs: False

        # 디지털 비트 변경 막기
        original_update_adc = self.update_adc_resolution_for_traffic
        self.update_adc_resolution_for_traffic = lambda traffic_type: None

        try:
            # 부모 클래스의 처리 메서드 호출
            result = super().process_packet(packet_info, channel_snr_db)
        finally:
            # 원래 메서드 복구
            self.fsm.process_indication = original_process
            self.update_adc_resolution_for_traffic = original_update_adc

            # 상태가 변경되었을 수 있으므로 다시 강제 설정
            self.fsm.current_state = AgcState.LOW_GAIN_LP
            self.fsm.current_gain_index = 0
            self.current_digital_bits = 5

        return result


class FixedHighPerformanceAGC(AgcSystem):
    """
    고성능 고정 AGC - 항상 최고 성능 모드 (교수님 피드백 반영)

    - 아날로그: UnifiedRFPath (항상 동일)
    - 디지털: 항상 10비트 전부 사용
    """

    def __init__(self):
        # use_correlation_detection=False: 제안 기법 기능 비활성화
        # initial_digital_bits=10: 항상 10비트 사용
        super().__init__(initial_digital_bits=10, use_correlation_detection=False)
        self.mode_name = "High-Performance Fixed AGC (10-bit)"
        # 초기 상태를 고성능 모드로 설정 - 최적화된 이득
        self.fsm.current_state = AgcState.HIGH_GAIN
        self.fsm.current_gain_index = 3  # index for gain
        self.current_gain_linear = 10**(40/20)  # 40 dB linear gain (from config)

    def process_packet(self, packet_info: Dict, channel_snr_db: float = 15.0) -> Dict:
        """패킷 처리 - 항상 고성능 모드 유지 (10비트 디지털 전부 사용)"""
        # 매번 고성능 상태로 강제 설정 (config에서 40dB)
        self.fsm.current_state = AgcState.HIGH_GAIN
        self.fsm.current_gain_index = 3
        self.current_gain_linear = 10**(40/20)  # 40 dB (from config)

        # 디지털 비트 고정 (10-bit 전부 사용) - 모든 트래픽에 대해
        # ADC 하드웨어는 10-bit (truncation 없음)
        self.current_digital_bits = 10

        # FSM의 process_indication을 오버라이드하여 상태 변경 막기
        original_process = self.fsm.process_indication
        self.fsm.process_indication = lambda *args, **kwargs: False

        # 디지털 비트 변경 막기
        original_update_adc = self.update_adc_resolution_for_traffic
        self.update_adc_resolution_for_traffic = lambda traffic_type: None

        try:
            # 부모 클래스의 처리 메서드 호출
            result = super().process_packet(packet_info, channel_snr_db)
        finally:
            # 원래 메서드 복구
            self.fsm.process_indication = original_process
            self.update_adc_resolution_for_traffic = original_update_adc

            # 상태가 변경되었을 수 있으므로 다시 강제 설정
            self.fsm.current_state = AgcState.HIGH_GAIN
            self.fsm.current_gain_index = 3
            self.current_digital_bits = 10

        return result


class AdaptiveAGC(AgcSystem):
    """제안 방식: Adaptive AGC"""

    def __init__(self):
        # use_correlation_detection=True: 제안 기법 기능 활성화 (기본값)
        super().__init__(initial_adc_resolution=3, use_correlation_detection=True)
        self.mode_name = "Adaptive AGC (Proposed)"

    def process_packet(self, packet_info: Dict, channel_snr_db: float = 15.0) -> Dict:
        """패킷 처리 - 적응적 AGC (기본 시스템 동작 그대로 사용)"""
        # 부모 클래스의 기본 동작 그대로 사용
        # - FSM이 carrier sensing과 signal field에 따라 자동으로 상태 전이
        # - ADC 해상도가 트래픽 타입에 따라 자동으로 조정됨
        return super().process_packet(packet_info, channel_snr_db)


def run_comparison_simulation(num_packets: int = 20, snr_values: List[float] = [5, 10, 15, 20], num_iterations: int = 10) -> Dict:
    """
    세 가지 AGC 방식 비교 시뮬레이션 실행
    """
    print("=" * 80)
    print(f"AGC Comparison Simulation ({num_iterations} iterations)")
    print("=" * 80)

    # 결과 누적을 위한 초기화
    accumulated_results = {'low_power': [], 'high_perf': [], 'adaptive': []}

    print(f"\nRunning {num_iterations} iterations...")

    # 반복 시뮬레이션
    for iteration in range(num_iterations):
        if (iteration + 1) % 100 == 0:
            print(f"  Progress: {iteration + 1}/{num_iterations}")

        # 각 반복마다 새로운 AGC 시스템 초기화
        agc_systems = {
            'low_power': FixedLowPowerAGC(),
            'high_perf': FixedHighPerformanceAGC(),
            'adaptive': AdaptiveAGC()
        }

        iteration_results = {name: {
            'ber_by_traffic': {},
            'ber_by_snr': {},
            'power_by_traffic': {},
            'power_by_state': {},
            'time_series': {
                'ber': [],
                'analog_power': [],
                'digital_energy': []
            },
            'total_analog_energy': 0,
            'total_digital_energy': 0,
            'packet_count': 0
        } for name in agc_systems.keys()}

        traffic_types = ['wake_up', 'sensor', 'voice', 'video']

        # 각 SNR 값에 대해 시뮬레이션
        for snr in snr_values:
            for traffic_idx, traffic_type in enumerate(traffic_types * (num_packets // 4)):
                # 각 AGC 시스템에 대해 동일한 패킷 처리
                for name, agc in agc_systems.items():
                    # 패킷 생성
                    packet = agc.signal_generator.create_complete_packet(traffic_type)

                    # 패킷 처리
                    result = agc.process_packet(packet, snr)

                    # 디버깅 출력 제거 (1000회 반복이므로)

                    # 결과 수집
                    ber = result.get('final_ber', {}).get('ber', 0)

                    # BER by traffic type
                    if traffic_type not in iteration_results[name]['ber_by_traffic']:
                        iteration_results[name]['ber_by_traffic'][traffic_type] = []
                    iteration_results[name]['ber_by_traffic'][traffic_type].append(ber)

                    # BER by SNR
                    if snr not in iteration_results[name]['ber_by_snr']:
                        iteration_results[name]['ber_by_snr'][snr] = []
                    iteration_results[name]['ber_by_snr'][snr].append(ber)

                    # Power measurements
                    analog_power = agc.analog_power.calculate_power(
                        agc.fsm.current_state.value,
                        is_low_power_mode=(agc.fsm.current_state == AgcState.LOW_GAIN_LP)
                    )

                    # 디지털 에너지 차분 계산 (이전 값 저장)
                    if not hasattr(agc, '_prev_digital_energy'):
                        agc._prev_digital_energy = 0

                    # 연산량 통계 가져오기
                    ops_stats = agc.digital_computation.get_operation_stats()
                    current_digital_energy = ops_stats['total_energy_pj']
                    digital_energy_consumed = current_digital_energy - agc._prev_digital_energy
                    agc._prev_digital_energy = current_digital_energy

                    # 제안 기법인 경우 오버헤드 확인 (디버깅용)
                    if name == 'adaptive' and iteration == 0 and traffic_idx == 0 and snr == snr_values[0]:
                        print(f"\n[Adaptive AGC] Traffic: {traffic_type}")
                        print(f"  Common ops: {ops_stats.get('common_operations', 0):,}")
                        print(f"  Proposed ops: {ops_stats.get('proposed_operations', 0):,}")
                        print(f"  Overhead: {ops_stats.get('proposed_overhead_percent', 0):.1f}%")

                    # Power by traffic type
                    if traffic_type not in iteration_results[name]['power_by_traffic']:
                        iteration_results[name]['power_by_traffic'][traffic_type] = {
                            'analog': [],
                            'digital': []
                        }
                    iteration_results[name]['power_by_traffic'][traffic_type]['analog'].append(analog_power)
                    iteration_results[name]['power_by_traffic'][traffic_type]['digital'].append(digital_energy_consumed)

                    # Power by FSM state
                    state = agc.fsm.current_state.value
                    if state not in iteration_results[name]['power_by_state']:
                        iteration_results[name]['power_by_state'][state] = {
                            'analog': [],
                            'digital': [],
                            'count': 0
                        }
                    iteration_results[name]['power_by_state'][state]['analog'].append(analog_power)
                    iteration_results[name]['power_by_state'][state]['digital'].append(digital_energy_consumed)
                    iteration_results[name]['power_by_state'][state]['count'] += 1

                    # Time series
                    iteration_results[name]['time_series']['ber'].append(ber)
                    iteration_results[name]['time_series']['analog_power'].append(analog_power)
                    iteration_results[name]['time_series']['digital_energy'].append(digital_energy_consumed)

                    # Total energy
                    iteration_results[name]['total_analog_energy'] += analog_power * 10  # 10ms per packet
                    iteration_results[name]['total_digital_energy'] += digital_energy_consumed
                    iteration_results[name]['packet_count'] += 1

        # 각 반복 결과 저장
        for name in agc_systems.keys():
            accumulated_results[name].append(iteration_results[name])

    print("\n" + "=" * 80)
    print("Calculating averages...")
    print("=" * 80)

    # 평균 결과 계산
    results = calculate_average_results(accumulated_results, traffic_types, snr_values)

    # 마지막 반복의 AGC 시스템 반환 (그래프용)
    return results, agc_systems


def plot_comparison_results(results: Dict, agc_systems: Dict):
    """
    비교 결과를 개별 그래프로 저장
    """
    print("\nGenerating comparison graphs...")

    # 색상 설정
    colors = {
        'low_power': 'blue',
        'high_perf': 'red',
        'adaptive': 'green'
    }

    labels = {
        'low_power': 'Low-Power Fixed',
        'high_perf': 'High-Performance Fixed',
        'adaptive': 'Adaptive (Proposed)'
    }

    # 1. 트래픽 유형에 따른 BER
    fig, ax = plt.subplots(figsize=(10, 8))
    traffic_types = ['wake_up', 'sensor', 'voice', 'video']
    x_pos = np.arange(len(traffic_types))
    width = 0.25

    for i, (name, color) in enumerate(colors.items()):
        ber_means = []
        ber_stds = []
        for traffic in traffic_types:
            if traffic in results[name]['ber_by_traffic']:
                bers = results[name]['ber_by_traffic'][traffic]
                ber_means.append(np.mean(bers))
                ber_stds.append(np.std(bers))
            else:
                ber_means.append(0)
                ber_stds.append(0)

        # 에러바 없이 평균값만 표시
        ax.bar(x_pos + i*width, ber_means, width,
               label=labels[name], color=color, alpha=0.7)

    ax.set_xlabel('Traffic Type')
    ax.set_ylabel('Average BER')
    ax.set_title('BER Performance by Traffic Type')
    ax.set_xticks(x_pos + width)
    ax.set_xticklabels(traffic_types)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('comparison_01_ber_by_traffic.png', dpi=100, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: comparison_01_ber_by_traffic.png")

    # 2. SNR에 따른 BER
    fig, ax = plt.subplots(figsize=(10, 8))

    for name, color in colors.items():
        snrs = sorted(results[name]['ber_by_snr'].keys())
        ber_means = []
        ber_stds = []

        for snr in snrs:
            bers = results[name]['ber_by_snr'][snr]
            avg_ber = np.mean(bers)
            # BER이 0인 경우 로그 스케일을 위해 작은 값으로 대체
            if avg_ber == 0:
                avg_ber = 1e-6  # Floor value for visualization
            ber_means.append(avg_ber)
            ber_stds.append(np.std(bers))

        # 에러바 없이 평균값만 표시 (더 깔끔한 그래프)
        ax.plot(snrs, ber_means,
               label=labels[name], color=color,
               marker='o', linewidth=2, markersize=8)

    ax.set_xlabel('SNR (dB)')
    ax.set_ylabel('Average BER')
    ax.set_title('BER Performance vs SNR')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.set_yscale('log')
    ax.set_ylim([1e-6, 1e0])  # Y축 범위 명시적 설정
    plt.tight_layout()
    plt.savefig('comparison_02_ber_vs_snr.png', dpi=100, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: comparison_02_ber_vs_snr.png")

    # 3. 트래픽 유형에 따른 아날로그 전력
    fig, ax = plt.subplots(figsize=(10, 8))
    x_pos = np.arange(len(traffic_types))

    for i, (name, color) in enumerate(colors.items()):
        power_means = []
        power_stds = []
        for traffic in traffic_types:
            if traffic in results[name]['power_by_traffic']:
                powers = results[name]['power_by_traffic'][traffic]['analog']
                power_means.append(np.mean(powers))
                power_stds.append(np.std(powers))
            else:
                power_means.append(0)
                power_stds.append(0)

        # 에러바 없이 평균값만 표시
        ax.bar(x_pos + i*width, power_means, width,
               label=labels[name], color=color, alpha=0.7)

    ax.set_xlabel('Traffic Type')
    ax.set_ylabel('Average Analog Power (mW)')
    ax.set_title('Analog Power Consumption by Traffic Type')
    ax.set_xticks(x_pos + width)
    ax.set_xticklabels(traffic_types)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('comparison_03_analog_power_by_traffic.png', dpi=100, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: comparison_03_analog_power_by_traffic.png")

    # 4. 트래픽 유형에 따른 디지털 에너지
    fig, ax = plt.subplots(figsize=(10, 8))

    for i, (name, color) in enumerate(colors.items()):
        energy_means = []
        energy_stds = []
        for traffic in traffic_types:
            if traffic in results[name]['power_by_traffic']:
                energies = results[name]['power_by_traffic'][traffic]['digital']
                # 이미 패킷당 에너지가 저장되어 있음
                if len(energies) > 0:
                    energy_means.append(np.mean(energies))
                    energy_stds.append(np.std(energies))
                else:
                    energy_means.append(0)
                    energy_stds.append(0)
            else:
                energy_means.append(0)
                energy_stds.append(0)

        # 에러바 없이 평균값만 표시
        ax.bar(x_pos + i*width, energy_means, width,
               label=labels[name], color=color, alpha=0.7)

    ax.set_xlabel('Traffic Type')
    ax.set_ylabel('Average Digital Energy per Packet (pJ)')
    ax.set_title('Digital Energy Consumption by Traffic Type')
    ax.set_xticks(x_pos + width)
    ax.set_xticklabels(traffic_types)
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('comparison_04_digital_energy_by_traffic.png', dpi=100, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: comparison_04_digital_energy_by_traffic.png")

    # 5. FSM 상태에 따른 전력 (Adaptive AGC만)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    adaptive_states = results['adaptive']['power_by_state']
    states = list(adaptive_states.keys())

    # 아날로그 전력
    analog_means = [np.mean(adaptive_states[s]['analog']) for s in states]
    analog_stds = [np.std(adaptive_states[s]['analog']) for s in states]
    counts = [adaptive_states[s]['count'] for s in states]

    ax1.bar(states, analog_means, yerr=analog_stds, color='green', alpha=0.7)
    ax1.set_xlabel('FSM State')
    ax1.set_ylabel('Average Analog Power (mW)')
    ax1.set_title('Adaptive AGC: Analog Power by FSM State')
    ax1.grid(True, alpha=0.3)
    ax1.set_xticklabels(states, rotation=45)

    # 상태 분포
    ax2.pie(counts, labels=states, autopct='%1.1f%%', startangle=90)
    ax2.set_title('Adaptive AGC: FSM State Distribution')

    plt.tight_layout()
    plt.savefig('comparison_05_fsm_power.png', dpi=100, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: comparison_05_fsm_power.png")

    # 6. 시간에 따른 BER
    fig, ax = plt.subplots(figsize=(12, 6))

    for name, color in colors.items():
        time_steps = range(len(results[name]['time_series']['ber']))
        ax.plot(time_steps, results[name]['time_series']['ber'],
                label=labels[name], color=color, alpha=0.7, linewidth=1.5)

    ax.set_xlabel('Packet Index')
    ax.set_ylabel('BER')
    ax.set_title('BER Over Time')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('comparison_06_ber_over_time.png', dpi=100, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: comparison_06_ber_over_time.png")

    # 7. 시간에 따른 아날로그 전력
    fig, ax = plt.subplots(figsize=(12, 6))

    for name, color in colors.items():
        time_steps = range(len(results[name]['time_series']['analog_power']))
        ax.plot(time_steps, results[name]['time_series']['analog_power'],
                label=labels[name], color=color, alpha=0.7, linewidth=1.5)

    ax.set_xlabel('Packet Index')
    ax.set_ylabel('Analog Power (mW)')
    ax.set_title('Analog Power Over Time')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('comparison_07_analog_power_over_time.png', dpi=100, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: comparison_07_analog_power_over_time.png")

    # 8. 전체 에너지 비교 (막대 그래프)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # 아날로그 에너지
    analog_energies = [results[name]['total_analog_energy'] for name in colors.keys()]
    ax1.bar(labels.values(), analog_energies, color=list(colors.values()), alpha=0.7)
    ax1.set_ylabel('Total Analog Energy (mJ)')
    ax1.set_title('Total Analog Energy Consumption')
    ax1.grid(True, alpha=0.3)

    # 디지털 에너지
    digital_energies = [results[name]['total_digital_energy'] for name in colors.keys()]
    ax2.bar(labels.values(), digital_energies, color=list(colors.values()), alpha=0.7)
    ax2.set_ylabel('Total Digital Energy (pJ)')
    ax2.set_title('Total Digital Energy Consumption')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('comparison_08_total_energy.png', dpi=100, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: comparison_08_total_energy.png")

    # 9. 성능 요약 테이블
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.axis('tight')
    ax.axis('off')

    # 테이블 데이터 준비
    table_data = []
    headers = ['Metric', 'Low-Power Fixed', 'High-Perf Fixed', 'Adaptive (Proposed)']

    # 평균 BER
    row = ['Average BER']
    for name in ['low_power', 'high_perf', 'adaptive']:
        all_bers = []
        for traffic_bers in results[name]['ber_by_traffic'].values():
            all_bers.extend(traffic_bers)
        avg_ber = np.mean(all_bers) if all_bers else 0
        row.append(f'{avg_ber:.6f}')
    table_data.append(row)

    # 평균 아날로그 전력
    row = ['Avg Analog Power (mW)']
    for name in ['low_power', 'high_perf', 'adaptive']:
        avg_power = np.mean(results[name]['time_series']['analog_power'])
        row.append(f'{avg_power:.2f}')
    table_data.append(row)

    # 총 아날로그 에너지
    row = ['Total Analog Energy (mJ)']
    for name in ['low_power', 'high_perf', 'adaptive']:
        row.append(f'{results[name]["total_analog_energy"]:.2f}')
    table_data.append(row)

    # 총 디지털 에너지
    row = ['Total Digital Energy (pJ)']
    for name in ['low_power', 'high_perf', 'adaptive']:
        row.append(f'{results[name]["total_digital_energy"]:.2f}')
    table_data.append(row)

    # 패킷 수
    row = ['Packets Processed']
    for name in ['low_power', 'high_perf', 'adaptive']:
        row.append(str(results[name]['packet_count']))
    table_data.append(row)

    # 테이블 생성
    table = ax.table(cellText=table_data, colLabels=headers,
                     cellLoc='center', loc='center',
                     colWidths=[0.3, 0.23, 0.23, 0.24])
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1, 2)

    # 헤더 스타일
    for i in range(len(headers)):
        table[(0, i)].set_facecolor('#40466e')
        table[(0, i)].set_text_props(weight='bold', color='white')

    # Adaptive 열 강조
    for i in range(1, len(table_data) + 1):
        table[(i, 3)].set_facecolor('#90EE90')

    ax.set_title('Performance Comparison Summary', fontsize=14, fontweight='bold', pad=20)
    plt.tight_layout()
    plt.savefig('comparison_09_summary_table.png', dpi=100, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: comparison_09_summary_table.png")

    print("\nAll comparison graphs generated successfully!")


def main():
    """메인 함수"""
    # 시뮬레이션 실행 (10회 반복)
    results, agc_systems = run_comparison_simulation(
        num_packets=20,
        snr_values=[5, 10, 15, 20],
        num_iterations=10  # 10회 반복
    )

    # 결과 출력
    print("\n" + "=" * 80)
    print("Performance Summary")
    print("=" * 80)

    for name in ['low_power', 'high_perf', 'adaptive']:
        print(f"\n{agc_systems[name].mode_name}:")

        # 평균 BER 계산
        all_bers = []
        for traffic_bers in results[name]['ber_by_traffic'].values():
            all_bers.extend(traffic_bers)
        avg_ber = np.mean(all_bers) if all_bers else 0

        # 평균 전력
        avg_analog_power = np.mean(results[name]['time_series']['analog_power'])
        total_digital_energy = results[name]['total_digital_energy']

        print(f"  Average BER: {avg_ber:.6f}")
        print(f"  Average Analog Power: {avg_analog_power:.2f} mW")
        print(f"  Total Analog Energy: {results[name]['total_analog_energy']:.2f} mJ")
        print(f"  Total Digital Energy: {total_digital_energy:.2f} pJ")

    # 그래프 생성
    plot_comparison_results(results, agc_systems)

    # 개선율 계산
    print("\n" + "=" * 80)
    print("Improvement Analysis (Adaptive vs Fixed)")
    print("=" * 80)

    # BER 개선
    adaptive_ber = np.mean([b for bers in results['adaptive']['ber_by_traffic'].values() for b in bers])
    lowpower_ber = np.mean([b for bers in results['low_power']['ber_by_traffic'].values() for b in bers])
    highperf_ber = np.mean([b for bers in results['high_perf']['ber_by_traffic'].values() for b in bers])

    print(f"\nBER Improvement:")
    print(f"  vs Low-Power: {((lowpower_ber - adaptive_ber) / lowpower_ber * 100):.1f}% reduction")
    print(f"  vs High-Perf: {((highperf_ber - adaptive_ber) / highperf_ber * 100):.1f}% reduction")

    # 에너지 절약
    adaptive_energy = results['adaptive']['total_analog_energy']
    lowpower_energy = results['low_power']['total_analog_energy']
    highperf_energy = results['high_perf']['total_analog_energy']

    print(f"\nEnergy Savings:")
    print(f"  vs Low-Power: {((lowpower_energy - adaptive_energy) / lowpower_energy * 100):.1f}%")
    print(f"  vs High-Perf: {((highperf_energy - adaptive_energy) / highperf_energy * 100):.1f}%")


if __name__ == "__main__":
    main()