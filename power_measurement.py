# power_measurement.py
import numpy as np
from typing import Dict, List, Optional
from analog_power_base import MAX2829PowerModel
from digital import DigitalAreaModel
from config import (UNIFIED_ANALOG_ALWAYS_ON, ADC_MAX_BITS,
                    K_ADD_PER_SAMPLE, K_MUL_PER_SAMPLE)

class DigitalComputationMeasurement:
    MAX_HISTORY_SIZE = 10000
    def __init__(self):
        self.area_model = DigitalAreaModel()
        self.power_per_op: Dict[str, float] = {'ADD': 0.1, 'MULTIPLY': 2.5}  # pJ/op
        self.operation_counts: Dict[str, int] = {
            'additions':0,'multiplications':0,
            'proposed_additions':0,'proposed_multiplications':0
        }
        self.computation_history: List[Dict] = []
        self.current_adc_bits = ADC_MAX_BITS  # 실제 ADC 최대 비트 (예: 10)

    def update_computation(self, state_name: str, block_size: int, adc_bits: int = None,
                           carrier_sensing_ops: Dict = None, ber_ops: Dict = None,
                           is_proposed_method: bool = True) -> None:
        if adc_bits is not None:
            self.current_adc_bits = adc_bits

        total_mults = 0; total_adds = 0
        proposed_mults = 0; proposed_adds = 0

        # ====== 공통(신호 경로) ======
        total_mults += block_size               # LNA
        total_mults += block_size               # Mixer
        total_mults += block_size               # VGA
        total_mults += block_size*2; total_adds += block_size   # LPF
        total_mults += block_size*3; total_adds += block_size*2  # ADC

        # CS & BER 연산량
        if carrier_sensing_ops:
            total_mults += carrier_sensing_ops.get('multiplications',0)
            total_adds  += carrier_sensing_ops.get('additions',0)
        if ber_ops:
            total_mults += ber_ops.get('multiplications',0)
            total_adds  += ber_ops.get('additions',0)

        # ====== 비트 종속 디지털 연산 (RF 신호 처리) ======
        # LNA/Mixer/VGA/LPF 디지털 처리 연산량
        # - LNA 출력 처리: b-bit 연산
        # - Mixer I/Q 복소 곱셈: O(b²) 연산
        # - VGA gain 적용: O(b²) 곱셈
        # - LPF 필터링: O(b) 덧셈
        b = self.current_adc_bits
        total_adds  += int(K_ADD_PER_SAMPLE * block_size * b)      # 덧셈: O(b)
        total_mults += int(K_MUL_PER_SAMPLE * block_size * (b**2))  # 곱셈: O(b²)

        # 제안 로직 추가 오버헤드(예: 탐지/상관 보조 연산)
        if is_proposed_method:
            proposed_adds += 30

        # 누적
        self.operation_counts['multiplications'] += total_mults
        self.operation_counts['additions']       += total_adds
        self.operation_counts['proposed_multiplications'] += proposed_mults
        self.operation_counts['proposed_additions']       += proposed_adds

        # 히스토리
        if len(self.computation_history) >= self.MAX_HISTORY_SIZE:
            self.computation_history.pop(0)
        self.computation_history.append({
            'state': state_name,'block_size': block_size,'adc_bits': self.current_adc_bits,
            'mults': self.operation_counts['multiplications'],
            'adds':  self.operation_counts['additions'],
            'proposed_mults': self.operation_counts['proposed_multiplications'],
            'proposed_adds':  self.operation_counts['proposed_additions'],
            'mults_delta': total_mults, 'adds_delta': total_adds
        })

    def get_total_area(self) -> float:
        area_info = self.area_model.calculate_digital_processing_area(self.current_adc_bits)
        return area_info['total_area']

    def get_total_energy(self) -> float:
        area_info = self.area_model.calculate_digital_processing_area(self.current_adc_bits)
        base_area = self.area_model.calculate_digital_processing_area(8)  # 기준 8bit
        area_ratio = area_info['total_area']/base_area['total_area'] if base_area['total_area']>0 else 1.0
        add_e  = self.operation_counts['additions']      * self.power_per_op['ADD']      * area_ratio
        mult_e = self.operation_counts['multiplications']* self.power_per_op['MULTIPLY'] * area_ratio
        return add_e + mult_e

    def get_operation_stats(self) -> Dict[str, float]:
        total_samples = max(1, sum(h['block_size'] for h in self.computation_history))
        common_adds = self.operation_counts['additions']
        common_mults= self.operation_counts['multiplications']
        proposed_adds= self.operation_counts['proposed_additions']
        proposed_mults= self.operation_counts['proposed_multiplications']
        return {
            'common_additions': common_adds,
            'common_multiplications': common_mults,
            'common_operations': common_adds + common_mults,
            'proposed_additions': proposed_adds,
            'proposed_multiplications': proposed_mults,
            'proposed_operations': proposed_adds + proposed_mults,
            'total_additions': common_adds + proposed_adds,
            'total_multiplications': common_mults + proposed_mults,
            'total_operations': common_adds + common_mults + proposed_adds + proposed_mults,
            'total_area_um2': self.get_total_area(),
            'total_energy_pj': self.get_total_energy(),
            'operations_per_sample': (common_adds+common_mults+proposed_adds+proposed_mults)/total_samples,
            'proposed_overhead_percent': (proposed_adds+proposed_mults)/max(1,common_adds+common_mults)*100,
            'current_adc_bits': self.current_adc_bits
        }

    def reset(self)->None:
        self.operation_counts = {'additions':0,'multiplications':0,'proposed_additions':0,'proposed_multiplications':0}
        self.computation_history = []


class AnalogPowerMeasurement:
    """
    아날로그 전력 단일화: 항상 RX on(동일 전력).
    main_agc_system.py의 호출 시그니처(state, block_duration_ms, is_low_power)를 지원.
    """
    def __init__(self):
        self.model = MAX2829PowerModel()  # 고성능 모델 하나만 사용
        self.total_energy_mj: float = 0.0
        self.total_time_ms:   float = 0.0
        self.power_history:   List[float] = []

    # ---- 신버전 시그니처 (권장) ----
    def update_power_measurement(self, state_or_duration, block_duration_ms: float = None, is_low_power: bool = False) -> None:
        """
        신버전: update_power_measurement(state: str, block_duration_ms: float, is_low_power: bool)
        구버전 호환: update_power_measurement(duration_ms: float)
        """
        # 구버전 형태로 들어오면 state_or_duration가 duration_ms 역할
        if block_duration_ms is None:
            duration_ms = float(state_or_duration)
            p_mw = self.calculate_power('RX', False)
        else:
            duration_ms = float(block_duration_ms)
            # 상태별로 바꾸고 싶다면 여기서 state_or_duration 사용 가능
            p_mw = self.calculate_power(str(state_or_duration), is_low_power)

        e_mj = p_mw * (duration_ms / 1000.0)
        self.total_energy_mj += e_mj
        self.total_time_ms   += duration_ms
        self.power_history.append(p_mw)

    def calculate_power(self, state_name: str, is_low_power: bool = False) -> float:
        # 현재 모델에서는 상태/저전력 여부와 무관하게 항상 RX 전력 사용(단일 AGC)
        if UNIFIED_ANALOG_ALWAYS_ON:
            return self.model.get_power('RX')
        return self.model.get_power('RX')

    def get_average_power(self)->float:
        if self.total_time_ms==0: return 0.0
        return (self.total_energy_mj / self.total_time_ms) * 1000.0

    def get_total_energy(self)->float:
        return self.total_energy_mj

    def reset(self)->None:
        self.total_energy_mj = 0.0
        self.total_time_ms   = 0.0
        self.power_history   = []
