# main_agc_system.py
# -*- coding: utf-8 -*-
"""
메인 AGC(Automatic Gain Control) 시스템 시뮬레이션

교수님 피드백 반영 (Unified Analog Architecture):
- 아날로그: 항상 동일 (UnifiedRFPath, ADC 10-bit 고정)
- 디지털: Truncation으로 5비트 또는 10비트 선택
- 전력 비교는 디지털 연산량만 차이 (아날로그 전력 동일)

요약:
- 한 파일만 실행해서 모델 비교 그래프 3개만 저장
- 모델: 종래 2개(Fixed 5-bit, Fixed 10-bit) + 제안(Adaptive 5/10-bit)
- 제안모델: Signal Field indicator 디코딩 시점에 DIGITAL_TRUNCATION_BITS 기반으로 디지털 비트 선택
- 그래프:
  1) metrics_energy.png   : 아날로그(mJ) / 디지털(pJ) 에너지 사용량 (모델별)
  2) metrics_accuracy.png : 평균 BER (모델별)
  3) metrics_latency.png  : 평균 지연(패킷당) (모델별)
"""

import os
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from agc_fsm import AgcFsm, AgcState
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
    DEFAULT_BLOCK_DURATION_MS = 1.0  # 블록 처리 시간

    def __init__(self, initial_digital_bits: int = 10, use_correlation_detection: bool = True):
        """
        AGC 시스템 초기화 (교수님 피드백 반영: Unified Analog)

        Args:
            initial_digital_bits: 디지털 처리 시작 비트 수 (5 또는 10)
            use_correlation_detection: correlation detection 사용 여부
        """
        print("=" * 60)
        print("Initializing Adaptive AGC Control System (Unified Analog)")
        print("=" * 60)

        self.use_correlation_detection = use_correlation_detection

        self.fsm = AgcFsm()
        self.signal_generator = SignalGenerator()
        self.ber_calculator = BERCalculator()

        # 교수님 피드백 반영: 아날로그 단일화
        # ADC는 항상 10비트로 동작
        self.adc = ADC10bit(vref=1.0)  # Single 10-bit ADC (항상 고정)
        self.current_adc_resolution = 10  # ADC 하드웨어는 항상 10비트

        # RF 경로도 하나만 사용 (항상 동일한 아날로그 회로)
        self.rf_path = UnifiedRFPath(lna_gain=20, vga_gain=20, lpf_alpha=0.2)

        # 디지털 파트: truncation 비트 수만 변경 (5비트 또는 10비트)
        self.current_digital_bits = initial_digital_bits  # 디지털 처리에 사용할 비트 수
        self.digital_area_model = DigitalAreaModel()

        self.carrier_sensing = CarrierSensingTop(self.current_adc_resolution)  # 항상 10비트

        self.analog_power = AnalogPowerMeasurement()
        self.digital_computation = DigitalComputationMeasurement()

        self.time_series_collector = TimeSeriesDataCollector()
        self.signal_field_decoder = SignalFieldDecoder()

        self.current_gain_linear: float = 10**(self.fsm.get_current_gain() / 20.0)
        self.is_packet_detected: bool = False
        self.current_traffic_type: Optional[str] = None

        self.processing_history: List[Dict] = []
        self.gain_history: List[float] = []
        self.ber_history: List[float] = []
        self.state_history: List[str] = []
        self.power_history: List[float] = []

        self._signal_field_extracted: bool = False

        # 제안모델에서 켜짐: indicator 디코딩 후 ADC 비트 선택
        self.use_indicator_for_adc: bool = False

        print(f"AGC System initialized successfully")
        print(f"Initial state: {self.fsm.current_state.value}")
        print(f"Initial gain: {self.fsm.get_current_gain()} dB")
        print(f"ADC resolution (hardware): {self.current_adc_resolution} bits (always 10-bit)")
        print(f"Digital bits (processing): {self.current_digital_bits} bits (5 or 10)")

    def process_rf_signal(self, signal: np.ndarray) -> np.ndarray:
        """
        RF 신호 처리 (교수님 피드백 반영: 통일된 RF path)
        아날로그는 항상 동일하게 동작, gain만 피드백으로 조절
        """
        gain_db = self.fsm.get_current_gain()

        # LNA gain은 고정, VGA gain으로 전체 gain 조절
        lna_gain = 20
        vga_gain = max(0, gain_db - 20)  # VGA는 음수 불가

        self.rf_path.set_gains(lna_gain=lna_gain, vga_gain=vga_gain)
        processed_signal = self.rf_path.run(signal)

        return self.apply_adc_quantization(processed_signal)

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

    def update_system_configuration(self) -> None:
        try:
            new_gain_db = self.fsm.get_current_gain()
            self.current_gain_linear = 10**(new_gain_db / 20.0)
            self.gain_history.append(new_gain_db)
            self.state_history.append(self.fsm.current_state.value)
        except Exception as e:
            if DEBUG_MODE:
                print(f"Error updating system configuration: {e}")

    def process_packet(self, packet_info: Dict, channel_snr_db: float = 10) -> Dict:
        self.current_traffic_type = packet_info['traffic_type']

        # 제안모델: indicator 디코딩 전까지 3-bit로
        if self.use_indicator_for_adc:
            if self.current_adc_resolution != 3:
                self.current_adc_resolution = 3
                if hasattr(self.carrier_sensing, 'update_resolution'):
                    self.carrier_sensing.update_resolution(3)
                else:
                    self.carrier_sensing = CarrierSensingTop(3)
        else:
            # (종래/레거시) 메타 기반 설정
            self.update_adc_resolution_for_traffic(self.current_traffic_type)

        if DEBUG_MODE:
            print(f"\n--- Processing Packet: {packet_info['traffic_type']} ---")
            print(f"    ADC Resolution (start): {self.current_adc_resolution} bits")

        self._signal_field_extracted = False

        # 채널: AWGN
        clean_signal = packet_info["complete_signal"]
        signal_power = np.mean(np.abs(clean_signal)**2)
        snr_linear = 10**(channel_snr_db / 10)
        noise_power = signal_power / snr_linear
        noise = np.sqrt(noise_power / 2) * (np.random.randn(len(clean_signal)) + 1j * np.random.randn(len(clean_signal)))
        noisy_signal = clean_signal + noise

        # RF 경로
        received_signal = self.process_rf_signal(noisy_signal)

        # 블록 처리
        stf_length_samples = packet_info["stf_end_idx"]
        block_size = calculate_block_size(stf_length_samples)
        processing_results = []

        HIGH_THR = 0.90
        LOW_THR  = 0.25
        STEP_DB  = 1.0
        EPS      = 1e-12

        for block_idx in range(0, len(received_signal), block_size):
            block_end = min(block_idx + block_size, len(received_signal))
            signal_block = received_signal[block_idx:block_end]
            if len(signal_block) == 0:
                continue

            cs_result = self.carrier_sensing.process_signal(signal_block)
            cs_operations = self._calculate_cs_operations(len(signal_block))

            # indicator 첫 디코드 시점에 ADC 비트 확정
            signal_field_indication = None
            if (block_idx >= packet_info["signal_field_start_idx"] and not self._signal_field_extracted):
                signal_field_indication = self.extract_signal_field_indication(packet_info, received_signal)
                self._signal_field_extracted = True
                if self.use_indicator_for_adc and signal_field_indication:
                    self.update_adc_resolution_for_traffic(signal_field_indication)
                    self.current_traffic_type = signal_field_indication
                    if DEBUG_MODE:
                        print(f"[Indicator] traffic={signal_field_indication}, ADC={self.current_adc_resolution} bits")
                    signal_block = self.process_rf_signal(noisy_signal[block_idx:block_end])

            state_changed = self.fsm.process_indication(cs_result["detection_methods"], signal_field_indication)
            if state_changed:
                self.update_system_configuration()
                signal_block = self.process_rf_signal(noisy_signal[block_idx:block_end])

            # 피크 기반 간단 gain 피드백
            peak_blk = float(np.max(np.abs(signal_block))) if len(signal_block) > 0 else 0.0
            step_db = 0.0
            if peak_blk > HIGH_THR + EPS:
                step_db = -STEP_DB
            elif peak_blk < LOW_THR - EPS:
                step_db = +STEP_DB
            if step_db != 0.0:
                new_gain = self.fsm.get_current_gain() + step_db
                if hasattr(self.fsm, "set_gain_db"):
                    self.fsm.set_gain_db(new_gain)
                elif hasattr(self.fsm, "apply_gain_delta"):
                    self.fsm.apply_gain_delta(step_db)
                elif hasattr(self.fsm, "current_gain_db"):
                    self.fsm.current_gain_db = new_gain
                else:
                    self.fsm._current_gain_db = new_gain
                self.update_system_configuration()
                signal_block = self.process_rf_signal(noisy_signal[block_idx:block_end])

            # BER (STF 구간만)
            ber_result = None
            ber_operations = {'multiplications': 0, 'additions': 0}
            if block_idx < packet_info["stf_end_idx"]:
                ber_result = self.ber_calculator.process_stf_block(signal_block, noise_power)
                self.ber_history.append(ber_result["ber"])
                ber_operations = self._calculate_ber_operations()

            # 전력/로그
            block_power = np.mean(np.abs(signal_block)**2)
            block_power_db = 10 * np.log10(block_power) if block_power > 0 else -np.inf
            self.power_history.append(block_power_db)

            self._update_power_measurements(
                block_duration_ms=self.DEFAULT_BLOCK_DURATION_MS,
                block_size=len(signal_block),
                ber_result=ber_result,
                cs_operations=cs_operations,
                ber_operations=ber_operations
            )

            processing_results.append({
                "block_idx": block_idx,
                "carrier_sensing": cs_result,
                "fsm_state": self.fsm.current_state.value,
                "gain_db": self.fsm.get_current_gain(),
                "adc_resolution": self.current_adc_resolution,
                "ber": ber_result,
                "signal_power_db": block_power_db,
                "state_changed": state_changed,
                "time_ms": self.time_series_collector.get_current_time()
            })

        # 패킷 결과
        final_ber_result = self.ber_calculator.process_complete_packet(packet_info, received_signal, noise_power)
        packet_result = {
            "packet_info": packet_info,
            "channel_snr_db": channel_snr_db,
            "final_fsm_state": self.fsm.current_state.value,
            "final_gain_db": self.fsm.get_current_gain(),
            "final_adc_resolution": self.current_adc_resolution,
            "final_ber": final_ber_result,
            "block_results": processing_results,
            "processing_blocks": len(processing_results),
            "analog_power": {
                "total_energy_mj": self.analog_power.get_total_energy(),
                "average_power_mw": self.analog_power.get_average_power()
            },
            "digital_computation": self.digital_computation.get_operation_stats()
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
                                   block_duration_ms: float,
                                   block_size: int,
                                   ber_result: Optional[Dict],
                                   cs_operations: Optional[Dict] = None,
                                   ber_operations: Optional[Dict] = None) -> None:
        """
        전력 측정 업데이트 (교수님 피드백 반영)

        - 아날로그: 항상 동일 (UnifiedRFPath 사용)
        - 디지털: current_digital_bits에 따라 연산량 변경
        """
        # 아날로그는 항상 동일 (통일된 RF path)
        # is_low_power 플래그는 여전히 유지 (호환성)
        is_low_power = False  # 아날로그는 항상 high-perf 모드 (통일됨)

        self.analog_power.update_power_measurement(self.fsm.current_state.value, block_duration_ms, is_low_power)

        # 디지털 연산량은 current_digital_bits에 비례
        self.digital_computation.update_computation(
            self.fsm.current_state.value,
            block_size,
            self.current_digital_bits,  # 5비트 또는 10비트
            cs_operations,
            ber_operations,
            is_proposed_method=self.use_correlation_detection
        )

        current_analog_power = self.analog_power.calculate_power(self.fsm.current_state.value, is_low_power)
        current_time = self.time_series_collector.get_current_time()
        digital_power_avg = safe_divide(self.digital_computation.get_total_energy(), current_time, default=0.0)

        self.time_series_collector.add_data_point(
            traffic_type=self.current_traffic_type or "unknown",
            analog_power=current_analog_power,
            digital_power=digital_power_avg,
            ber=ber_result['ber'] if ber_result else 0,
            fsm_state=self.fsm.current_state.value,
            gain=self.fsm.get_current_gain(),
            duration_ms=block_duration_ms
        )

    def run_simulation(self,
                       traffic_types: List[str] = ["sensor", "voice", "video"],
                       snr_range_db: List[float] = [5, 10, 15, 20],
                       packets_per_scenario: int = 20) -> Dict:
        print("=" * 80)
        print("Starting AGC System Comprehensive Simulation")
        print(f"Traffic Pattern: wake_up -> {' -> '.join(traffic_types)} -> gap -> repeat")
        print(f"SNR Values: {snr_range_db} dB")
        print(f"Packets per scenario: {packets_per_scenario}")
        print("=" * 80)

        traffic_manager = TrafficFlowManager(traffic_types, gap_size=2)

        simulation_results = {
            "scenarios": [],
            "overall_statistics": {},
            "time_series_data": None
        }

        packet_counter = 0

        for snr_db in snr_range_db:
            scenario_results = []

            for _ in range(packets_per_scenario):
                traffic_type = traffic_manager.get_traffic_type(packet_counter)
                if traffic_type is None:
                    packet_counter += 1
                    continue

                current_time = self.time_series_collector.get_current_time()
                print(f"\n--- Time: {current_time:.1f}ms | Packet {packet_counter + 1}: "
                      f"{traffic_type.upper()} traffic at {snr_db} dB SNR ---")

                packet_info = self.signal_generator.create_complete_packet(traffic_type)
                result = self.process_packet(packet_info, snr_db)
                scenario_results.append(result)

                packet_counter += 1
                print(f"  Packet processed")
                print(f"    Current Analog Power: {self.analog_power.get_average_power():.2f} mW")
                print(f"    Digital Energy so far: {self.digital_computation.get_total_energy():.2f} pJ")

            if scenario_results:
                scenario_summary = self._calculate_scenario_statistics(scenario_results, snr_db)
                simulation_results["scenarios"].append(scenario_summary)
                self._print_scenario_summary(scenario_summary, snr_db)

        simulation_results["overall_statistics"] = self._calculate_overall_statistics(simulation_results["scenarios"])
        simulation_results["time_series_data"] = self.time_series_collector.get_data()
        self._print_simulation_summary(simulation_results)
        return simulation_results

    def _calculate_scenario_statistics(self, scenario_results: List[Dict], snr_db: float) -> Dict:
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

    def _print_scenario_summary(self, scenario_summary: Dict, snr_db: float) -> None:
        print(f"\n  SNR {snr_db} dB Scenario completed:")
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
# 종래모델 2개 (고정 동작)
# =========================
class FixedLowPowerAGC(AgcSystem):
    """저전력 고정 AGC - 항상 LOW_GAIN_LP / 3-bit"""

    def __init__(self):
        super().__init__(initial_adc_resolution=3, use_correlation_detection=False)
        self.fsm.current_state = AgcState.LOW_GAIN_LP
        self.current_gain_linear = 10**(10/20)

    def process_packet(self, packet_info: Dict, channel_snr_db: float = 15.0) -> Dict:
        # 고정 세팅
        self.fsm.current_state = AgcState.LOW_GAIN_LP
        self.current_adc_resolution = 3
        # 적응 차단
        original_ind = self.fsm.process_indication
        self.fsm.process_indication = lambda *a, **k: False
        original_update = self.update_adc_resolution_for_traffic
        self.update_adc_resolution_for_traffic = lambda *a, **k: None
        try:
            return super().process_packet(packet_info, channel_snr_db)
        finally:
            self.fsm.process_indication = original_ind
            self.update_adc_resolution_for_traffic = original_update


class FixedHighPerformanceAGC(AgcSystem):
    """고성능 고정 AGC - 항상 HIGH_GAIN / 10-bit"""

    def __init__(self):
        super().__init__(initial_adc_resolution=10, use_correlation_detection=False)
        self.fsm.current_state = AgcState.HIGH_GAIN
        self.current_gain_linear = 10**(40/20)

    def process_packet(self, packet_info: Dict, channel_snr_db: float = 15.0) -> Dict:
        # 고정 세팅
        self.fsm.current_state = AgcState.HIGH_GAIN
        self.current_adc_resolution = 10
        # 적응 차단
        original_ind = self.fsm.process_indication
        self.fsm.process_indication = lambda *a, **k: False
        original_update = self.update_adc_resolution_for_traffic
        self.update_adc_resolution_for_traffic = lambda *a, **k: None
        try:
            return super().process_packet(packet_info, channel_snr_db)
        finally:
            self.fsm.process_indication = original_ind
            self.update_adc_resolution_for_traffic = original_update


# =========================
# 플랫/집계 & 3개 그래프
# =========================
def _flatten_packets(sim_result: Dict) -> List[Dict]:
    flat: List[Dict] = []
    for scen in sim_result.get("scenarios", []):
        for p in scen.get("packet_results", []):
            flat.append({
                "traffic": p["packet_info"]["traffic_type"],
                "ber": float(p.get("final_ber", {}).get("ber", 0.0)),
                "analog_total_mj": float(p.get("analog_power", {}).get("total_energy_mj", 0.0)),
                "digital_total_pj": float(p.get("digital_computation", {}).get("total_energy_pj", 0.0)),
                "latency_ms": float(p.get("processing_blocks", 0)) * float(AgcSystem.DEFAULT_BLOCK_DURATION_MS),
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
    모델 단위(전체) 메트릭 산출:
      - total_analog_mj, total_digital_pj  (전체 누적)
      - avg_ber, avg_latency_ms           (패킷 평균)
    """
    rows = _flatten_packets(sim_result)
    if not rows:
        return dict(total_analog_mj=0.0, total_digital_pj=0.0, avg_ber=0.0, avg_latency_ms=0.0)

    # 누적 → 최종값(전체)
    total_analog_mj = rows[-1]["analog_total_mj"]
    total_digital_pj = rows[-1]["digital_total_pj"]

    avg_ber = float(np.mean([r["ber"] for r in rows]))
    avg_latency_ms = float(np.mean([r["latency_ms"] for r in rows]))

    return dict(
        total_analog_mj=total_analog_mj,
        total_digital_pj=total_digital_pj,
        avg_ber=avg_ber,
        avg_latency_ms=avg_latency_ms
    )

def plot_three_metrics_models(metrics_by_model: Dict[str, Dict[str, float]], outdir: str = "."):
    labels = list(metrics_by_model.keys())
    analog = [metrics_by_model[k]["total_analog_mj"] for k in labels]
    digital = [metrics_by_model[k]["total_digital_pj"] for k in labels]
    avg_ber = [metrics_by_model[k]["avg_ber"] for k in labels]
    avg_lat = [metrics_by_model[k]["avg_latency_ms"] for k in labels]

    # 1) 에너지
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12,5))
    ax1.bar(labels, analog)
    ax1.set_title('Analog Energy Usage (total)')
    ax1.set_ylabel('mJ')
    ax1.grid(True, alpha=0.3)

    ax2.bar(labels, digital)
    ax2.set_title('Digital Energy Usage (total)')
    ax2.set_ylabel('pJ')
    ax2.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_energy.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_energy.png")

    # 2) 정확도
    plt.figure(figsize=(8,6))
    plt.bar(labels, avg_ber)
    plt.title('Accuracy (Average BER)')
    plt.ylabel('Average BER (lower is better)')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_accuracy.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_accuracy.png")

    # 3) 지연
    plt.figure(figsize=(8,6))
    plt.bar(labels, avg_lat)
    plt.title('Latency (Average per-packet delay)')
    plt.ylabel('Latency (ms)')
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(outdir, "metrics_latency.png"), dpi=120, bbox_inches='tight')
    plt.close()
    print("  ✓ Saved: metrics_latency.png")


# =========================
# 메인: 세 모델을 각각 실행 → 비교 그래프 3개 저장
# =========================
def run_one_model(model_name: str, model_obj: AgcSystem) -> Dict[str, float]:
    print("\n" + "="*100)
    print(f"Running model: {model_name}")
    print("="*100)
    sim = model_obj.run_simulation(
        traffic_types=["sensor", "voice", "video"],
        snr_range_db=[5, 10, 15, 20],
        packets_per_scenario=20
    )
    return compute_model_metrics(sim)

def main():
    print("=" * 100)
    print("Python-based AGC Comparison (Conventional vs Proposed)")
    print("Single entrypoint, outputs 3 figures: energy/accuracy/latency (model-wise)")
    print("=" * 100)

    # 1) 종래 모델 - Low-Power Fixed
    low_power = FixedLowPowerAGC()
    metrics_lp = run_one_model("Low-Power Fixed", low_power)

    # 2) 종래 모델 - High-Perf Fixed
    high_perf = FixedHighPerformanceAGC()
    metrics_hp = run_one_model("High-Perf Fixed", high_perf)

    # 3) 제안 모델 - Adaptive (indicator 기반 비트 선택)
    # 5비트로 시작, signal field 디코딩 후 트래픽에 맞게 5/10비트 선택
    adaptive = AgcSystem(initial_digital_bits=5, use_correlation_detection=True)
    adaptive.use_indicator_for_adc = True
    metrics_ad = run_one_model("Adaptive (Proposed)", adaptive)

    # 모델별 메트릭 묶기 & 그래프 3종
    metrics_by_model = {
        "Low-Power Fixed": metrics_lp,
        "High-Perf Fixed": metrics_hp,
        "Adaptive (Proposed)": metrics_ad
    }
    if not os.path.exists(PLOTS_OUTDIR):
        os.makedirs(PLOTS_OUTDIR, exist_ok=True)
    plot_three_metrics_models(metrics_by_model, outdir=PLOTS_OUTDIR)

    # (이전 기타 그래프 호출은 주석 처리)
    # if PLOT_RESULTS:
    #     ...

    print(f"\nPlots saved to: {os.path.abspath(PLOTS_OUTDIR)}")
    print("\nDone.")

if __name__ == "__main__":
    main()
