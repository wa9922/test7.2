# main_agc_system.py
# -*- coding: utf-8 -*-
"""
메인 AGC(Automatic Gain Control) 시스템 시뮬레이션

교수님 피드백 반영 (Unified Analog Architecture):
- 아날로그: 항상 동일 (UnifiedRFPath, ADC 10-bit 고정)
- 디지털: Truncation으로 5비트 또는 10비트 선택
- 전력 비교는 디지털 연산량만 차이 (아날로그 전력 동일)

요약:
- 한 파일만 실행해서 모델 비교 그래프 8개 생성
- 모델: 종래 2개(Fixed 5-bit, Fixed 10-bit) + 제안(Adaptive 5/10-bit)
- 제안모델: Signal Field indicator 디코딩 시점에 DIGITAL_TRUNCATION_BITS 기반으로 디지털 비트 선택

- 그래프 (총 8개, X축은 모두 연속적 값):
  SNR 기반 선 그래프 (3개):
  1) metrics_energy.png    : Digital Energy vs SNR
  2) metrics_accuracy.png  : BER vs SNR (log scale)
  3) metrics_latency.png   : Latency vs SNR

  SNR 기반 연산량 (1개):
  4) metrics_operations.png : Additions & Multiplications vs SNR

  전체 평균값 막대 그래프 (4개):
  5) metrics_energy_efficiency.png : bits/Joule
  6) metrics_sqnr.png             : SQNR (dB)
  7) metrics_throughput.png       : bps
  8) metrics_adc_bit_usage.png    : 5-bit vs 10-bit 사용 비율
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from carrier_sensing import CarrierSensingTop
from signal_generator import SignalGenerator
from ber_calculator import BERCalculator
from config import SAMPLING_RATE, NOISE_POWER, DEBUG_MODE, PLOT_RESULTS, TRAFFIC_ADC_RESOLUTION, DIGITAL_TRUNCATION_BITS
from power_measurement import DigitalComputationMeasurement, AnalogPowerMeasurement
from adc import ADC5bit, ADC10bit
from rf_paths import UnifiedRFPath
from digital import DigitalAreaModel
from simulation_utils import (
    TrafficFlowManager,
    TimeSeriesDataCollector,
    SignalFieldDecoder,
    calculate_block_size,
    safe_divide,
    # plot_simulation_results as utils_plot_simulation_results,   # ← (요청) 사용 안 함
)

PLOTS_OUTDIR = "."   # 저장 경로(필요 시 변경)

# =========================
# 공통 AGC 시스템 (제안모델 로직 포함)
# =========================
class AgcSystem:
    BASE_BLOCK_DURATION_MS = 0.5  # 기본 블록 처리 시간 (5-bit 기준)

    def __init__(self, initial_digital_bits: int = 10, use_correlation_detection: bool = True, enable_gain_feedback: bool = True):
        """
        AGC 시스템 초기화 (교수님 피드백 반영: Unified Analog, FSM 제거)

        Args:
            initial_digital_bits: 디지털 처리 시작 비트 수 (5 또는 10)
            use_correlation_detection: correlation detection 사용 여부
            enable_gain_feedback: gain 피드백 활성화 여부 (Fixed 모델은 False)
        """
        print("=" * 60)
        print("Initializing Adaptive AGC Control System (Unified Analog, Pure Feedback)")
        print("=" * 60)

        self.use_correlation_detection = use_correlation_detection
        self.enable_gain_feedback = enable_gain_feedback  # Gain feedback 제어

        # 순수 피드백 기반 AGC: FSM 제거, 직접 gain 변수 사용
        # Multi-Stage AGC에서는 RF path의 총 gain을 추적
        self.current_gain_db: float = 35.0  # 초기 gain: LNA 15dB + VGA 20dB = 35 dB

        self.signal_generator = SignalGenerator()
        self.ber_calculator = BERCalculator()

        # 교수님 피드백 반영: 아날로그 단일화
        # ADC는 항상 10비트로 동작
        self.adc = ADC10bit(vref=1.0)  # Single 10-bit ADC (항상 고정)
        self.current_adc_resolution = 10  # ADC 하드웨어는 항상 10비트

        # RF 경로도 하나만 사용 (항상 동일한 아날로그 회로)
        # Multi-Stage AGC: LNA discrete + VGA continuous
        self.rf_path = UnifiedRFPath(lpf_alpha=0.2)

        # 디지털 파트: truncation 비트 수만 변경 (5비트 또는 10비트)
        self.current_digital_bits = initial_digital_bits  # 디지털 처리에 사용할 비트 수
        self.digital_area_model = DigitalAreaModel()

        self.carrier_sensing = CarrierSensingTop(self.current_adc_resolution)  # 항상 10비트

        self.analog_power = AnalogPowerMeasurement()
        self.digital_computation = DigitalComputationMeasurement()

        self.time_series_collector = TimeSeriesDataCollector()
        self.signal_field_decoder = SignalFieldDecoder()

        self.current_gain_linear: float = 10**(self.current_gain_db / 20.0)
        self.is_packet_detected: bool = False
        self.current_traffic_type: Optional[str] = None

        self.processing_history: List[Dict] = []
        self.gain_history: List[float] = []
        self.ber_history: List[float] = []
        self.power_history: List[float] = []

        self._signal_field_extracted: bool = False

        # 제안모델에서 켜짐: indicator 디코딩 후 ADC 비트 선택
        self.use_indicator_for_adc: bool = False

        print(f"AGC System initialized successfully")
        print(f"Initial gain: {self.current_gain_db} dB")
        print(f"ADC resolution (hardware): {self.current_adc_resolution} bits (always 10-bit)")
        print(f"Digital bits (processing): {self.current_digital_bits} bits (5 or 10)")

    def process_rf_only(self, signal: np.ndarray) -> np.ndarray:
        """
        RF 증폭만 수행 (ADC 양자화 분리)

        실제 AGC 동작: RF 증폭과 ADC 양자화를 분리하여
        블록 단위로 gain 피드백을 적용할 수 있도록 함

        Multi-Stage AGC:
        - LNA: discrete gain (0, 15, 30 dB)
        - VGA: continuous gain (0-40 dB)
        - RF path가 자체적으로 gain 관리
        """
        # RF path는 현재 LNA, VGA gain으로 신호 증폭
        amplified_signal = self.rf_path.run(signal)

        # 현재 총 gain 추적 (LNA + VGA)
        self.current_gain_db = self.rf_path.get_total_gain()

        return amplified_signal

    def process_rf_signal(self, signal: np.ndarray) -> np.ndarray:
        """
        RF 증폭 + ADC 양자화 (호환성용, 이전 코드와의 호환)
        """
        amplified = self.process_rf_only(signal)
        return self.apply_adc_quantization(amplified)

    def apply_adc_quantization(self, signal: np.ndarray) -> np.ndarray:
        """
        ADC 양자화 + 디지털 truncation (교수님 피드백 반영)

        1단계: 항상 10비트 ADC로 양자화
        2단계: 디지털 단에서 self.current_digital_bits로 truncate
        """
        # 1단계: 10-bit ADC 양자화 (항상)
        quantized_10bit = self.adc.quantize(signal)

        # 2단계: 디지털 truncation (5비트 또는 10비트로)
        if self.current_digital_bits < 10:
            # 5비트로 truncate
            truncated_signal = self.adc.truncate_to_bits(quantized_10bit, self.current_digital_bits)
            return truncated_signal
        else:
            # 10비트 그대로 사용
            return quantized_10bit

    def apply_agc_gain(self, signal: np.ndarray) -> np.ndarray:
        return self.process_rf_signal(signal)

    def extract_signal_field_indication(self, packet_info: Dict, received_signal: np.ndarray) -> str:
        sf_start = packet_info["signal_field_start_idx"]
        sf_end = packet_info["signal_field_end_idx"]
        if received_signal is None or len(received_signal) <= sf_end:
            return self.signal_field_decoder.decode_traffic_type(None, packet_info, use_simulation_mode=True)
        signal_field_signal = received_signal[sf_start:sf_end]
        return self.signal_field_decoder.decode_traffic_type(signal_field_signal, packet_info, use_simulation_mode=True)

    def update_adc_resolution_for_traffic(self, traffic_type: str) -> None:
        """
        트래픽 타입에 따라 디지털 처리 비트 수 업데이트 (교수님 피드백 반영)

        ADC 하드웨어는 항상 10비트, 디지털 truncation만 변경
        """
        if traffic_type in DIGITAL_TRUNCATION_BITS:
            new_digital_bits = DIGITAL_TRUNCATION_BITS[traffic_type]
            if new_digital_bits != self.current_digital_bits:
                old_bits = self.current_digital_bits
                self.current_digital_bits = new_digital_bits
                if DEBUG_MODE:
                    print(f"Digital bits updated: {old_bits} → {new_digital_bits} bits for {traffic_type} traffic")
                    print(f"  (ADC hardware remains 10-bit, digital truncation applied)")

    def calculate_block_processing_time(self, digital_bits: int) -> float:
        """
        디지털 비트 수에 따른 블록 처리 시간 계산

        처리 시간은 디지털 연산량에 비례 (비트²에 비례)
        5-bit: 기본 시간
        10-bit: 4배 시간 (10²/5² = 4)

        Args:
            digital_bits: 디지털 비트 수

        Returns:
            처리 시간 (ms)
        """
        # 처리 시간은 비트²에 비례 (연산량이 비트²에 비례하므로)
        time_ratio = (digital_bits / 5.0) ** 2
        return self.BASE_BLOCK_DURATION_MS * time_ratio

    def update_system_configuration(self) -> None:
        """순수 피드백 AGC: gain만 업데이트 (FSM 제거)"""
        try:
            self.current_gain_linear = 10**(self.current_gain_db / 20.0)
            self.gain_history.append(self.current_gain_db)
        except Exception as e:
            if DEBUG_MODE:
                print(f"Error updating system configuration: {e}")

    def process_packet(self, packet_info: Dict, channel_snr_db: float = 10) -> Dict:
        """
        패킷 처리 (교수님 피드백 반영: STF에서만 AGC 동작)

        동작 순서:
        1. 채널: AWGN 노이즈 추가
        2. STF 구간에서만 AGC 동작 (gain 결정)
        3. 결정된 gain으로 전체 패킷을 한 번에 RF 증폭
        4. ADC 양자화 + 디지털 truncation
        5. Signal field 디코딩 → 트래픽 타입 파악
        6. 트래픽 타입에 따라 디지털 비트 재선택 (Adaptive만)
        7. BER 계산 (STF 구간)
        8. 전력 측정
        """
        self.current_traffic_type = packet_info['traffic_type']

        # 제안모델: indicator 디코딩 전까지 5-bit digital로 시작
        if self.use_indicator_for_adc:
            # 초기에는 5-bit digital truncation
            self.current_digital_bits = 5
        else:
            # (종래/레거시) 메타 기반 설정
            self.update_adc_resolution_for_traffic(self.current_traffic_type)

        if DEBUG_MODE:
            print(f"\n--- Processing Packet: {packet_info['traffic_type']} ---")
            print(f"    ADC Resolution (hardware): {self.current_adc_resolution} bits (always 10-bit)")
            print(f"    Digital bits (start): {self.current_digital_bits} bits")

        # ========== 1. 채널: AWGN 노이즈 추가 ==========
        clean_signal = packet_info["complete_signal"]
        signal_power = np.mean(np.abs(clean_signal)**2)
        snr_linear = 10**(channel_snr_db / 10)
        noise_power = signal_power / snr_linear
        noise = np.sqrt(noise_power / 2) * (np.random.randn(len(clean_signal)) + 1j * np.random.randn(len(clean_signal)))
        noisy_signal = clean_signal + noise

        # ========== 2. STF 구간에서만 AGC 동작 (gain 결정) ==========
        # STF (Short Training Field)는 패킷 맨 앞에 위치, AGC용으로 사용
        stf_end_idx = packet_info["stf_end_idx"]
        stf_signal = noisy_signal[0:stf_end_idx]

        gain_info = None
        if self.enable_gain_feedback:
            # STF peak 기반 gain 조정 (Multi-Stage AGC)
            peak_stf = float(np.max(np.abs(stf_signal))) if len(stf_signal) > 0 else 0.0
            gain_info = self.rf_path.update_gain_hierarchical(peak_stf)
            self.current_gain_db = gain_info['total_gain_db']

            if DEBUG_MODE:
                print(f"  [STF-based AGC] Peak={peak_stf:.3f}, Final Gain={self.current_gain_db:.1f} dB")
                if gain_info['lna_changed']:
                    print(f"    LNA: {gain_info['old_lna_db']:.0f} → {gain_info['new_lna_db']:.0f} dB")
                if gain_info['vga_changed']:
                    print(f"    VGA: {gain_info['old_vga_db']:.1f} → {gain_info['new_vga_db']:.1f} dB")

        # ========== 3. 결정된 gain으로 전체 패킷을 한 번에 RF 증폭 ==========
        amplified_signal = self.process_rf_only(noisy_signal)

        # ========== 4. ADC 양자화 (10비트) + 디지털 truncation ==========
        quantized_signal = self.apply_adc_quantization(amplified_signal)

        # ========== 5. Signal field 디코딩 (트래픽 타입 파악) ==========
        signal_field_indication = self.extract_signal_field_indication(packet_info, quantized_signal)

        # ========== 6. 트래픽 타입에 따라 디지털 비트 재선택 (Adaptive만) ==========
        if self.use_indicator_for_adc and signal_field_indication:
            old_bits = self.current_digital_bits
            self.update_adc_resolution_for_traffic(signal_field_indication)
            self.current_traffic_type = signal_field_indication

            if DEBUG_MODE:
                print(f"[Signal Field] traffic={signal_field_indication}, digital_bits: {old_bits} → {self.current_digital_bits}")

            # 디지털 비트가 변경되었으면 재양자화
            if self.current_digital_bits != old_bits:
                quantized_signal = self.apply_adc_quantization(amplified_signal)

        # ========== 7. BER 계산 (STF 구간) ==========
        stf_quantized = quantized_signal[0:stf_end_idx]
        ber_result = self.ber_calculator.process_stf_block(
            stf_quantized, noise_power,
            adc_bits=self.current_digital_bits,
            channel_snr_db=channel_snr_db
        )
        self.ber_history.append(ber_result["ber"])

        # 전체 패킷 BER도 계산
        final_ber_result = self.ber_calculator.process_complete_packet(
            packet_info, quantized_signal, noise_power,
            channel_snr_db=channel_snr_db,
            adc_bits=self.current_digital_bits
        )

        # ========== 8. 전력 측정 ==========
        # Carrier sensing 연산량 (STF 구간 기준)
        cs_operations = self._calculate_cs_operations(len(stf_quantized))

        # BER 계산 연산량
        ber_operations = self._calculate_ber_operations()

        # 처리 시간 계산
        from config import SAMPLING_RATE

        # 아날로그: 실제 신호 시간 (모든 모델 동일)
        analog_duration_ms = (len(clean_signal) / SAMPLING_RATE) * 1000  # ms

        # 디지털: 비트 수에 비례하는 처리 시간
        digital_duration_ms = self.calculate_block_processing_time(self.current_digital_bits)

        # 전력 업데이트
        self._update_power_measurements(
            analog_duration_ms=analog_duration_ms,
            digital_duration_ms=digital_duration_ms,
            block_size=len(quantized_signal),
            ber_result=ber_result,
            cs_operations=cs_operations,
            ber_operations=ber_operations
        )

        # ========== 패킷 결과 반환 ==========
        packet_result = {
            "packet_info": packet_info,
            "traffic_type": self.current_traffic_type,
            "channel_snr_db": channel_snr_db,
            "final_gain_db": self.current_gain_db,
            "final_adc_resolution": self.current_adc_resolution,
            "final_digital_bits": self.current_digital_bits,
            "final_ber": final_ber_result,
            "stf_ber": ber_result,
            "total_latency_ms": digital_duration_ms,
            "analog_power": {
                "total_energy_mj": self.analog_power.get_total_energy(),
                "average_power_mw": self.analog_power.get_average_power()
            },
            "digital_computation": self.digital_computation.get_operation_stats(),
            "gain_info": gain_info
        }

        self.processing_history.append(packet_result)
        return packet_result

    def _calculate_cs_operations(self, block_size: int) -> Dict[str, int]:
        mults = 0
        adds = 0
        # Saturation
        adds += block_size * 2
        adds += 1
        mults += 1
        # Energy
        mults += block_size * 2
        adds += block_size
        adds += block_size - 1
        mults += 1
        mults += 1
        # Correlation
        if block_size >= 160:
            window_size = 160
            num_windows = max(1, (block_size - window_size) // 40 + 1)
            for _ in range(num_windows):
                mults += window_size * 2
                adds += window_size * 2 - 1
                mults += window_size * 2 * 2
                adds += window_size * 2
                mults += 2
                mults += 2
        return {'multiplications': mults, 'additions': adds}

    def _calculate_ber_operations(self) -> Dict[str, int]:
        mults = 0
        adds = 0
        stf_length = 16
        samples_per_symbol = 10
        for _ in range(stf_length):
            adds += samples_per_symbol - 1
            mults += 1
        adds += stf_length
        mults += 160 * 2
        adds += 160
        adds += 159
        mults += 1
        mults += 2
        return {'multiplications': mults, 'additions': adds}

    def _update_power_measurements(self,
                                   analog_duration_ms: float,  # 아날로그: 실제 신호 시간
                                   digital_duration_ms: float,  # 디지털: 처리 시간
                                   block_size: int,
                                   ber_result: Optional[Dict],
                                   cs_operations: Optional[Dict] = None,
                                   ber_operations: Optional[Dict] = None) -> None:
        """
        전력 측정 업데이트 (교수님 피드백 반영, FSM 제거)

        - 아날로그: 항상 동일 전력, 실제 신호 시간에만 비례
        - 디지털: current_digital_bits에 따라 연산량 변경, 처리 시간은 latency에만 반영
        """
        # 아날로그는 실제 신호 수신 시간에만 비례 (모든 모델 동일)
        is_low_power = False  # 아날로그는 항상 high-perf 모드 (통일됨)
        state_name = "RUNNING"  # FSM 제거: 단순 상태 문자열

        self.analog_power.update_power_measurement(state_name, analog_duration_ms, is_low_power)

        # 디지털 연산량은 current_digital_bits에 비례
        self.digital_computation.update_computation(
            state_name,
            block_size,
            self.current_digital_bits,  # 5비트 또는 10비트
            cs_operations,
            ber_operations,
            is_proposed_method=self.use_correlation_detection
        )

        current_analog_power = self.analog_power.calculate_power(state_name, is_low_power)
        current_time = self.time_series_collector.get_current_time()
        digital_power_avg = safe_divide(self.digital_computation.get_total_energy(), current_time, default=0.0)

        self.time_series_collector.add_data_point(
            traffic_type=self.current_traffic_type or "unknown",
            analog_power=current_analog_power,
            digital_power=digital_power_avg,
            ber=ber_result['ber'] if ber_result else 0,
            fsm_state=state_name,
            gain=self.current_gain_db,
            duration_ms=analog_duration_ms  # 아날로그 신호 시간 사용
        )

    def run_simulation(self,
                       traffic_types: List[str] = ["lowpowersignal", "highperformancesignal"],
                       snr_range_db: List[float] = None,  # Deprecated, uses TRAFFIC_SNR_RANGE
                       packets_per_scenario: int = 20) -> Dict:
        """
        AGC 시스템 시뮬레이션 실행 (교수님 피드백 반영: SNR은 주어진 채널 환경)

        Args:
            traffic_types: 시뮬레이션할 트래픽 타입 리스트
            snr_range_db: SNR 범위 (None이면 config.CHANNEL_SNR_RANGE 사용)
            packets_per_scenario: 각 (SNR, traffic) 시나리오당 패킷 수
        """
        from config import CHANNEL_SNR_RANGE

        # SNR 범위 결정
        if snr_range_db is None:
            snr_range_db = CHANNEL_SNR_RANGE

        print("=" * 80)
        print("Starting AGC System Comprehensive Simulation")
        print(f"Traffic Types: {', '.join(traffic_types)}")
        print(f"Channel SNR Range: {snr_range_db} dB (주어진 채널 환경)")
        print(f"Packets per scenario: {packets_per_scenario}")
        print("=" * 80)

        simulation_results = {
            "scenarios": [],
            "overall_statistics": {},
            "time_series_data": None
        }

        packet_counter = 0

        # SNR 우선 순회 (채널 환경이 먼저 주어짐)
        for snr_db in snr_range_db:
            # 각 SNR에서 모든 트래픽 타입 테스트
            for traffic_type in traffic_types:
                scenario_results = []

                for _ in range(packets_per_scenario):
                    current_time = self.time_series_collector.get_current_time()
                    print(f"\n--- Time: {current_time:.1f}ms | Packet {packet_counter + 1}: "
                          f"{traffic_type.upper()} at SNR {snr_db} dB (channel) ---")

                    packet_info = self.signal_generator.create_complete_packet(traffic_type)
                    result = self.process_packet(packet_info, snr_db)
                    scenario_results.append(result)

                    packet_counter += 1
                    print(f"  Processed - Digital bits: {result.get('final_digital_bits', 'N/A')}")
                    print(f"    Gain: {result.get('final_gain_db', 0):.1f} dB")
                    print(f"    Analog Power: {self.analog_power.get_average_power():.2f} mW")
                    print(f"    Digital Energy: {self.digital_computation.get_total_energy():.2f} pJ")

                if scenario_results:
                    scenario_summary = self._calculate_scenario_statistics(scenario_results, snr_db, traffic_type)
                    simulation_results["scenarios"].append(scenario_summary)
                    self._print_scenario_summary(scenario_summary, snr_db, traffic_type)

        simulation_results["overall_statistics"] = self._calculate_overall_statistics(simulation_results["scenarios"])
        simulation_results["time_series_data"] = self.time_series_collector.get_data()
        self._print_simulation_summary(simulation_results)
        return simulation_results

    def _calculate_scenario_statistics(self, scenario_results: List[Dict], snr_db: float, traffic_type: str = "unknown") -> Dict:
        scenario_bers = [r["final_ber"]["ber"] for r in scenario_results]
        scenario_gains = [r["final_gain_db"] for r in scenario_results]
        scenario_snrs = [r["final_ber"]["snr_db"] for r in scenario_results]

        mean_ber = np.mean(scenario_bers) if scenario_bers else 0
        std_ber = np.std(scenario_bers) if scenario_bers else 0

        if len(scenario_bers) > 1:
            confidence_interval = stats.t.interval(0.95, len(scenario_bers) - 1,
                                                   loc=mean_ber, scale=stats.sem(scenario_bers))
        else:
            confidence_interval = (mean_ber, mean_ber)

        scenario_powers = [r["analog_power"]["average_power_mw"] for r in scenario_results if "analog_power" in r]
        scenario_energies = [r["analog_power"]["total_energy_mj"] for r in scenario_results if "analog_power" in r]
        scenario_digital = [r["digital_computation"] for r in scenario_results if "digital_computation" in r]

        return {
            "traffic_type": traffic_type,
            "snr_db": snr_db,
            "packet_count": len(scenario_results),
            "average_ber": mean_ber,
            "std_ber": std_ber,
            "ber_confidence_interval": confidence_interval,
            "average_gain": np.mean(scenario_gains) if scenario_gains else 0,
            "std_gain": np.std(scenario_gains) if scenario_gains else 0,
            "average_snr": np.mean(scenario_snrs) if scenario_snrs else 0,
            "std_snr": np.std(scenario_snrs) if scenario_snrs else 0,
            "raw_ber_data": scenario_bers,
            "packet_results": scenario_results,
            "analog_power": {
                "average_power_mw": np.mean(scenario_powers) if scenario_powers else 0,
                "total_energy_mj": np.sum(scenario_energies) if scenario_energies else 0
            },
            "digital_computation": {
                "total_additions": sum(d['total_additions'] for d in scenario_digital) if scenario_digital else 0,
                "total_multiplications": sum(d['total_multiplications'] for d in scenario_digital) if scenario_digital else 0,
                "total_area_um2": scenario_digital[0]['total_area_um2'] if scenario_digital else 0,
                "total_energy_pj": sum(d['total_energy_pj'] for d in scenario_digital) if scenario_digital else 0
            }
        }

    def _calculate_overall_statistics(self, scenarios: List[Dict]) -> Dict:
        all_bers = [s["average_ber"] for s in scenarios]
        all_gains = [s["average_gain"] for s in scenarios]
        return {
            "total_scenarios": len(scenarios),
            "total_packets": int(sum(s["packet_count"] for s in scenarios)),
            "overall_average_ber": np.mean(all_bers) if all_bers else 0,
            "overall_std_ber": np.std(all_bers) if all_bers else 0,
            "overall_average_gain": np.mean(all_gains) if all_gains else 0,
        }

    def _print_scenario_summary(self, scenario_summary: Dict, snr_db: float, traffic_type: str = "unknown") -> None:
        print(f"\n  [{traffic_type.upper()}] SNR {snr_db} dB Scenario completed:")
        print(f"    Packets processed: {scenario_summary['packet_count']}")
        print(f"    BER: {scenario_summary['average_ber']:.6f} ± {scenario_summary['std_ber']:.6f}")
        print(f"    Gain: {scenario_summary['average_gain']:.1f} ± {scenario_summary['std_gain']:.1f} dB")
        print(f"    SNR: {scenario_summary['average_snr']:.1f} ± {scenario_summary['std_snr']:.1f} dB")

        if 'analog_power' in scenario_summary:
            print(f"    Analog Power: {scenario_summary['analog_power']['average_power_mw']:.2f} mW")
            print(f"    Total Energy: {scenario_summary['analog_power']['total_energy_mj']:.2f} mJ")

        if 'digital_computation' in scenario_summary:
            print(f"    Digital Operations: {scenario_summary['digital_computation']['total_additions']} adds, "
                  f"{scenario_summary['digital_computation']['total_multiplications']} mults")
            print(f"    Digital Energy: {scenario_summary['digital_computation']['total_energy_pj']:.2f} pJ")

    def _print_simulation_summary(self, simulation_results: Dict) -> None:
        print("\n" + "=" * 80)
        print("Simulation Completed Successfully")
        print("=" * 80)

        overall_stats = simulation_results['overall_statistics']
        print(f"Total scenarios: {overall_stats['total_scenarios']}")
        print(f"Total packets processed: {overall_stats['total_packets']}")
        print(f"Overall average BER: {overall_stats['overall_average_ber']:.6f}")
        print(f"Overall average gain: {overall_stats['overall_average_gain']:.1f} dB")


# =========================
# 종래모델 2개 (고정 동작, FSM 제거)
# =========================
class FixedLowPowerAGC(AgcSystem):
    """
    저전력 고정 AGC - 디지털 비트는 5-bit 고정, gain은 자동 조절

    특징:
    - Digital bits: 항상 5-bit (고정)
    - Gain control: AGC 피드백 활성화 (자동 조절)
    - 정책: 저전력 디지털 설정 유지
    """

    def __init__(self):
        super().__init__(initial_digital_bits=5, use_correlation_detection=False, enable_gain_feedback=True)
        self.current_digital_bits = 5  # 고정 5-bit
        print(f"Fixed Low-Power AGC: Digital=5-bit (fixed), Gain=AUTO (AGC enabled)")

    def process_packet(self, packet_info: Dict, channel_snr_db: float = 15.0) -> Dict:
        # 디지털 비트만 고정 (gain은 AGC로 자동 조절됨)
        self.current_digital_bits = 5

        # 디지털 비트 적응 차단 (항상 5-bit 유지)
        original_update = self.update_adc_resolution_for_traffic
        self.update_adc_resolution_for_traffic = lambda *a, **k: None
        try:
            return super().process_packet(packet_info, channel_snr_db)
        finally:
            self.update_adc_resolution_for_traffic = original_update


class FixedHighPerformanceAGC(AgcSystem):
    """
    고성능 고정 AGC - 디지털 비트는 10-bit 고정, gain은 자동 조절

    특징:
    - Digital bits: 항상 10-bit (고정)
    - Gain control: AGC 피드백 활성화 (자동 조절)
    - 정책: 고성능 디지털 설정 유지
    """

    def __init__(self):
        super().__init__(initial_digital_bits=10, use_correlation_detection=False, enable_gain_feedback=True)
        self.current_digital_bits = 10  # 고정 10-bit
        print(f"Fixed High-Performance AGC: Digital=10-bit (fixed), Gain=AUTO (AGC enabled)")

    def process_packet(self, packet_info: Dict, channel_snr_db: float = 15.0) -> Dict:
        # 디지털 비트만 고정 (gain은 AGC로 자동 조절됨)
        self.current_digital_bits = 10

        # 디지털 비트 적응 차단 (항상 10-bit 유지)
        original_update = self.update_adc_resolution_for_traffic
        self.update_adc_resolution_for_traffic = lambda *a, **k: None
        try:
            return super().process_packet(packet_info, channel_snr_db)
        finally:
            self.update_adc_resolution_for_traffic = original_update


# =========================
# 플랫/집계 & 3개 그래프
# =========================
def _flatten_packets(sim_result: Dict) -> List[Dict]:
    """
    패킷별 상세 데이터 추출 (확장됨)

    추가된 데이터:
    - SNR, 연산량, ADC 비트, 처리 블록 수
    - Latency는 연산 복잡도 기반으로 개선
    """
    flat: List[Dict] = []
    for scen in sim_result.get("scenarios", []):
        snr_db = scen.get("snr_db", 10)  # 시나리오의 SNR
        for p in scen.get("packet_results", []):
            digital_comp = p.get("digital_computation", {})

            # 연산량 추출
            total_adds = digital_comp.get("total_additions", 0)
            total_mults = digital_comp.get("total_multiplications", 0)
            total_ops = total_adds + total_mults

            # 개선된 Latency 계산: 연산 복잡도 기반
            # 가정: 1 addition = 0.001ms, 1 multiplication = 0.005ms
            TIME_PER_ADD = 0.001  # ms
            TIME_PER_MULT = 0.005  # ms
            latency_computation_ms = (total_adds * TIME_PER_ADD + total_mults * TIME_PER_MULT)
            latency_overhead_ms = float(p.get("processing_blocks", 0)) * 0.1  # 블록 처리 오버헤드
            latency_total_ms = latency_computation_ms + latency_overhead_ms

            # ADC 비트 추출 (digital_bits)
            adc_bits = digital_comp.get("current_adc_bits", 10)

            flat.append({
                "traffic": p["packet_info"]["traffic_type"],
                "snr_db": snr_db,
                "ber": float(p.get("final_ber", {}).get("ber", 0.0)),
                "analog_total_mj": float(p.get("analog_power", {}).get("total_energy_mj", 0.0)),
                "digital_total_pj": float(digital_comp.get("total_energy_pj", 0.0)),
                "latency_ms": latency_total_ms,
                "total_additions": total_adds,
                "total_multiplications": total_mults,
                "total_operations": total_ops,
                "adc_bits": adc_bits,
                "processing_blocks": float(p.get("processing_blocks", 0)),
            })
    return flat

def _per_packet_delta(seq: List[float]) -> List[float]:
    out, prev = [], 0.0
    for v in seq:
        d = max(0.0, float(v) - prev)
        out.append(d)
        prev = float(v)
    return out

def compute_model_metrics(sim_result: Dict) -> Dict[str, float]:
    """
    모델 단위(전체) 메트릭 산출 (확장됨)

    기본 메트릭:
      - total_analog_mj, total_digital_pj, avg_ber, avg_latency_ms

    추가 메트릭:
      - 연산량: total_operations, total_additions, total_multiplications
      - 에너지 효율성: energy_efficiency_bits_per_joule
      - SQNR: avg_sqnr_db
      - Throughput: throughput_bps
      - SNR별 BER: ber_by_snr
      - 트래픽별 분석: ber_by_traffic, energy_by_traffic
      - ADC 비트 선택: adc_bit_usage_ratio
    """
    rows = _flatten_packets(sim_result)
    if not rows:
        return dict(total_analog_mj=0.0, total_digital_pj=0.0, avg_ber=0.0, avg_latency_ms=0.0)

    # 기본 메트릭
    total_analog_mj = rows[-1]["analog_total_mj"]
    total_digital_pj = rows[-1]["digital_total_pj"]
    avg_ber = float(np.mean([r["ber"] for r in rows]))
    avg_latency_ms = float(np.mean([r["latency_ms"] for r in rows]))

    # 연산량 메트릭
    total_additions = rows[-1]["total_additions"]
    total_multiplications = rows[-1]["total_multiplications"]
    total_operations = total_additions + total_multiplications

    # 에너지 효율성: bits/Joule
    # 가정: 패킷당 1024 payload bits (config.py의 PAYLOAD_BITS)
    total_bits_transmitted = len(rows) * 1024  # 총 전송 비트
    total_energy_joule = (total_analog_mj / 1000.0) + (total_digital_pj / 1e12)  # mJ + pJ → Joule
    energy_efficiency = total_bits_transmitted / total_energy_joule if total_energy_joule > 0 else 0

    # SQNR: Signal to Quantization Noise Ratio
    # SQNR = 6.02 * N + 1.76 (dB), N = ADC 비트 수
    avg_adc_bits = float(np.mean([r["adc_bits"] for r in rows]))
    avg_sqnr_db = 6.02 * avg_adc_bits + 1.76

    # Throughput: bps (bits per second)
    # 총 전송 비트 / 총 시간 (latency 합)
    total_time_sec = sum(r["latency_ms"] for r in rows) / 1000.0  # ms → sec
    throughput_bps = total_bits_transmitted / total_time_sec if total_time_sec > 0 else 0

    # SNR별 분석 (BER, Energy, Latency, Operations)
    ber_by_snr = {}
    energy_by_snr = {}
    latency_by_snr = {}
    operations_by_snr = {}
    snr_values = sorted(set(r["snr_db"] for r in rows))
    for snr in snr_values:
        snr_rows = [r for r in rows if r["snr_db"] == snr]
        snr_key = f"snr_{int(snr)}db"
        ber_by_snr[snr_key] = float(np.mean([r["ber"] for r in snr_rows]))

        # SNR별 평균 디지털 에너지 (패킷당)
        snr_energies = [snr_rows[i]["digital_total_pj"] - (snr_rows[i-1]["digital_total_pj"] if i > 0 else 0)
                        for i in range(len(snr_rows))]
        energy_by_snr[snr_key] = float(np.mean(snr_energies)) if snr_energies else 0

        # SNR별 평균 레이턴시
        latency_by_snr[snr_key] = float(np.mean([r["latency_ms"] for r in snr_rows]))

        # SNR별 평균 연산량
        if snr_rows:
            operations_by_snr[snr_key] = {
                "additions": int(np.mean([r["total_additions"] for r in snr_rows])),
                "multiplications": int(np.mean([r["total_multiplications"] for r in snr_rows]))
            }

    # 트래픽 타입별 분석
    ber_by_traffic = {}
    energy_by_traffic = {}
    latency_by_traffic = {}
    traffic_types = set(r["traffic"] for r in rows)
    for traffic in traffic_types:
        traffic_rows = [r for r in rows if r["traffic"] == traffic]
        ber_by_traffic[traffic] = float(np.mean([r["ber"] for r in traffic_rows]))

        # 패킷 단위 에너지 (delta)
        traffic_energies = [traffic_rows[i]["digital_total_pj"] -
                           (traffic_rows[i-1]["digital_total_pj"] if i > 0 else 0)
                           for i in range(len(traffic_rows))]
        energy_by_traffic[traffic] = float(np.mean(traffic_energies)) if traffic_energies else 0

        # 트래픽별 평균 레이턴시
        latency_by_traffic[traffic] = float(np.mean([r["latency_ms"] for r in traffic_rows]))

    # ADC 비트 사용 비율 (5비트 vs 10비트)
    bit_5_count = sum(1 for r in rows if r["adc_bits"] == 5)
    bit_10_count = sum(1 for r in rows if r["adc_bits"] == 10)
    total_count = len(rows)
    adc_bit_5_ratio = (bit_5_count / total_count * 100) if total_count > 0 else 0
    adc_bit_10_ratio = (bit_10_count / total_count * 100) if total_count > 0 else 0

    return {
        # 기본 메트릭
        "total_analog_mj": total_analog_mj,
        "total_digital_pj": total_digital_pj,
        "avg_ber": avg_ber,
        "avg_latency_ms": avg_latency_ms,

        # 연산량 메트릭
        "total_operations": total_operations,
        "total_additions": total_additions,
        "total_multiplications": total_multiplications,

        # 효율성 메트릭
        "energy_efficiency_bits_per_joule": energy_efficiency,
        "avg_sqnr_db": avg_sqnr_db,
        "throughput_bps": throughput_bps,

        # 상세 분석 (SNR별)
        "ber_by_snr": ber_by_snr,
        "energy_by_snr": energy_by_snr,
        "latency_by_snr": latency_by_snr,
        "operations_by_snr": operations_by_snr,

        # 상세 분석 (Traffic별)
        "ber_by_traffic": ber_by_traffic,
        "energy_by_traffic": energy_by_traffic,
        "latency_by_traffic": latency_by_traffic,

        # ADC 비트 사용
        "adc_bit_5_ratio": adc_bit_5_ratio,
        "adc_bit_10_ratio": adc_bit_10_ratio,
        "avg_adc_bits": avg_adc_bits,
    }

def plot_three_metrics_models(metrics_by_model: Dict[str, Dict[str, float]], outdir: str = "."):
    """3개 주요 메트릭 그래프: Energy, BER, Latency (모델별 bar chart)"""
    model_names = list(metrics_by_model.keys())
    colors = ['blue', 'red', 'green']

    # 1) Digital Energy (bar chart)
    plt.figure(figsize=(10,6))
    energy_values = [metrics_by_model[model_name]["total_digital_pj"] for model_name in model_names]
    plt.bar(model_names, energy_values, color=colors, alpha=0.7, edgecolor='black')
    plt.title('Total Digital Energy per Model')
    plt.xlabel('AGC Model')
    plt.ylabel('Total Digital Energy (pJ)')
    plt.xticks(rotation=15, ha='right')
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_energy.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_energy.png")

    # 2) Average BER (bar chart)
    plt.figure(figsize=(10,6))
    ber_values = [metrics_by_model[model_name]["avg_ber"] for model_name in model_names]
    plt.bar(model_names, ber_values, color=colors, alpha=0.7, edgecolor='black')
    plt.title('Average BER per Model')
    plt.xlabel('AGC Model')
    plt.ylabel('Average BER (lower is better)')
    plt.yscale('log')  # Log scale for BER
    plt.xticks(rotation=15, ha='right')
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_accuracy.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_accuracy.png")

    # 3) Average Latency (bar chart)
    plt.figure(figsize=(10,6))
    latency_values = [metrics_by_model[model_name]["avg_latency_ms"] for model_name in model_names]
    plt.bar(model_names, latency_values, color=colors, alpha=0.7, edgecolor='black')
    plt.title('Average Latency per Model')
    plt.xlabel('AGC Model')
    plt.ylabel('Average Latency (ms)')
    plt.xticks(rotation=15, ha='right')
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_latency.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_latency.png")


def plot_extended_metrics(metrics_by_model: Dict[str, Dict], outdir: str = "."):
    """
    확장 메트릭 그래프

    생성 그래프 (모두 bar chart):
    1. Operations (Additions, Multiplications)
    2. Energy Efficiency (bar chart, aggregate)
    3. SQNR (bar chart, aggregate)
    4. Throughput (bar chart, aggregate)
    5. ADC Bit Usage (bar chart, model별 비율)
    """
    model_names = list(metrics_by_model.keys())
    colors = ['blue', 'red', 'green']

    # 4) Operations (Additions, Multiplications) - bar chart
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14,5))

    # Additions
    additions = [metrics_by_model[model_name]["total_additions"] for model_name in model_names]
    ax1.bar(model_names, additions, color=colors, alpha=0.7, edgecolor='black')
    ax1.set_title('Total Additions per Model')
    ax1.set_xlabel('AGC Model')
    ax1.set_ylabel('Total Additions')
    ax1.tick_params(axis='x', rotation=15)
    ax1.grid(True, alpha=0.3, axis='y')

    # Multiplications
    multiplications = [metrics_by_model[model_name]["total_multiplications"] for model_name in model_names]
    ax2.bar(model_names, multiplications, color=colors, alpha=0.7, edgecolor='black')
    ax2.set_title('Total Multiplications per Model')
    ax2.set_xlabel('AGC Model')
    ax2.set_ylabel('Total Multiplications')
    ax2.tick_params(axis='x', rotation=15)
    ax2.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_operations.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_operations.png")

    # 5) 에너지 효율성 (bits/Joule)
    eff = [metrics_by_model[k]["energy_efficiency_bits_per_joule"] for k in model_names]
    plt.figure(figsize=(8,6))
    plt.bar(model_names, eff, color='gold')
    plt.title('Energy Efficiency')
    plt.ylabel('bits/Joule (higher is better)')
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_energy_efficiency.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_energy_efficiency.png")

    # 6) SQNR
    sqnr = [metrics_by_model[k]["avg_sqnr_db"] for k in model_names]
    plt.figure(figsize=(8,6))
    plt.bar(model_names, sqnr, color='orchid')
    plt.title('Average SQNR (Signal to Quantization Noise Ratio)')
    plt.ylabel('SQNR (dB)')
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_sqnr.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_sqnr.png")

    # 7) Throughput
    throughput = [metrics_by_model[k]["throughput_bps"] for k in model_names]
    plt.figure(figsize=(8,6))
    plt.bar(model_names, throughput, color='cyan')
    plt.title('Throughput')
    plt.ylabel('bps (bits per second)')
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_throughput.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_throughput.png")

    # 8) ADC 비트 사용 비율 (5비트 vs 10비트) - Bar chart
    bit5_ratios = [metrics_by_model[k]["adc_bit_5_ratio"] for k in model_names]
    bit10_ratios = [metrics_by_model[k]["adc_bit_10_ratio"] for k in model_names]

    x_pos_models = np.arange(len(model_names))
    width = 0.35

    plt.figure(figsize=(10,6))
    plt.bar(x_pos_models - width/2, bit5_ratios, width, label='5-bit usage', color='lightblue')
    plt.bar(x_pos_models + width/2, bit10_ratios, width, label='10-bit usage', color='lightcoral')

    plt.title('ADC Bit Usage Ratio')
    plt.xlabel('Model')
    plt.ylabel('Usage Percentage (%)')
    plt.xticks(x_pos_models, model_names, rotation=15)
    plt.legend()
    plt.grid(True, alpha=0.3, axis='y')
    plt.ylim(0, 105)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_adc_bit_usage.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_adc_bit_usage.png")


def plot_all_metrics(metrics_by_model: Dict[str, Dict], outdir: str = "."):
    """모든 메트릭 그래프 생성 (주요 3개 + 확장 5개 = 총 8개)"""
    print("\n" + "="*80)
    print("Generating all comparison graphs...")
    print("="*80)

    # 주요 3개 그래프 (모델별 bar chart)
    plot_three_metrics_models(metrics_by_model, outdir)

    # 확장 5개 그래프
    plot_extended_metrics(metrics_by_model, outdir)

    print("\n" + "="*80)
    print(f"All graphs saved to: {outdir}/")
    print("Total: 8 comparison graphs generated")
    print("  - 3 model comparison bar charts (Energy, BER, Latency)")
    print("  - 1 operations comparison chart (Additions, Multiplications)")
    print("  - 4 aggregate bar charts (Efficiency, SQNR, Throughput, ADC Usage)")
    print("="*80)


# =========================
# 메인: 세 모델을 각각 실행 → 비교 그래프 3개 저장
# =========================
def run_one_model(model_name: str, model_obj: AgcSystem) -> Dict[str, float]:
    print("\n" + "="*100)
    print(f"Running model: {model_name}")
    print("="*100)
    sim = model_obj.run_simulation(
        traffic_types=["lowpowersignal", "highperformancesignal"],
        packets_per_scenario=20
    )
    return compute_model_metrics(sim)

def main(num_iterations: int = 1000):
    print("=" * 100)
    print("Python-based AGC Comparison (Conventional vs Proposed)")
    print(f"Comprehensive metrics with {num_iterations} iterations averaging")
    print("=" * 100)

    # Initialize results storage
    all_metrics_lp = []
    all_metrics_hp = []
    all_metrics_ad = []

    # Run iterations
    for iteration in range(num_iterations):
        if (iteration + 1) % 100 == 0:
            print(f"\nProgress: {iteration + 1}/{num_iterations} iterations completed")

        # 1) Low-Power Fixed
        low_power = FixedLowPowerAGC()
        metrics_lp = run_one_model("Low-Power Fixed (5-bit)", low_power)
        all_metrics_lp.append(metrics_lp)

        # 2) High-Perf Fixed
        high_perf = FixedHighPerformanceAGC()
        metrics_hp = run_one_model("High-Perf Fixed (10-bit)", high_perf)
        all_metrics_hp.append(metrics_hp)

        # 3) Adaptive
        adaptive = AgcSystem(initial_digital_bits=5, use_correlation_detection=True)
        adaptive.use_indicator_for_adc = True
        metrics_ad = run_one_model("Adaptive (Proposed)", adaptive)
        all_metrics_ad.append(metrics_ad)

    print(f"\n\nAll {num_iterations} iterations completed. Averaging results...")

    # Average metrics
    def average_metrics(metrics_list):
        """Average metrics across iterations"""
        avg_metrics = {}
        # Simple averages
        for key in ['total_analog_mj', 'total_digital_pj', 'avg_ber', 'avg_latency_ms',
                    'total_operations', 'total_additions', 'total_multiplications',
                    'energy_efficiency_bits_per_joule', 'avg_sqnr_db', 'throughput_bps',
                    'adc_bit_5_ratio', 'adc_bit_10_ratio', 'avg_adc_bits']:
            avg_metrics[key] = float(np.mean([m[key] for m in metrics_list]))

        # Dictionary averages (ber_by_snr, energy_by_snr, etc.)
        for dict_key in ['ber_by_snr', 'energy_by_snr', 'latency_by_snr']:
            avg_metrics[dict_key] = {}
            all_keys = set()
            for m in metrics_list:
                all_keys.update(m[dict_key].keys())
            for k in all_keys:
                values = [m[dict_key].get(k, 0) for m in metrics_list]
                avg_metrics[dict_key][k] = float(np.mean(values))

        # Operations by SNR (nested dict)
        avg_metrics['operations_by_snr'] = {}
        all_keys = set()
        for m in metrics_list:
            all_keys.update(m['operations_by_snr'].keys())
        for k in all_keys:
            avg_metrics['operations_by_snr'][k] = {
                'additions': int(np.mean([m['operations_by_snr'].get(k, {}).get('additions', 0) for m in metrics_list])),
                'multiplications': int(np.mean([m['operations_by_snr'].get(k, {}).get('multiplications', 0) for m in metrics_list]))
            }

        # Traffic metrics
        for dict_key in ['ber_by_traffic', 'energy_by_traffic', 'latency_by_traffic']:
            avg_metrics[dict_key] = {}
            all_keys = set()
            for m in metrics_list:
                all_keys.update(m[dict_key].keys())
            for k in all_keys:
                values = [m[dict_key].get(k, 0) for m in metrics_list]
                avg_metrics[dict_key][k] = float(np.mean(values))

        return avg_metrics

    metrics_lp_avg = average_metrics(all_metrics_lp)
    metrics_hp_avg = average_metrics(all_metrics_hp)
    metrics_ad_avg = average_metrics(all_metrics_ad)

    # 모델별 메트릭 묶기 & 그래프 8종 생성
    metrics_by_model = {
        "Low-Power Fixed (5-bit)": metrics_lp_avg,
        "High-Perf Fixed (10-bit)": metrics_hp_avg,
        "Adaptive (Proposed)": metrics_ad_avg
    }
    if not os.path.exists(PLOTS_OUTDIR):
        os.makedirs(PLOTS_OUTDIR, exist_ok=True)

    # 모든 메트릭 그래프 생성 (8개)
    plot_all_metrics(metrics_by_model, outdir=PLOTS_OUTDIR)

    print(f"\nPlots saved to: {os.path.abspath(PLOTS_OUTDIR)}")
    print(f"Results are averaged over {num_iterations} iterations")
    print("\nDone.")

if __name__ == "__main__":
    main()
