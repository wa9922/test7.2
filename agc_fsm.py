# agc_fsm.py

"""
AGC 제어를 위한 FSM(Finite State Machine)을 정의하는 모듈입니다.
트래픽 유형별 FSM 상태, 상태 전이 로직, LUT를 통한 이득 제어를 구현합니다.
"""

from enum import Enum, auto
import numpy as np
from config import GAIN_LEVELS, LUT_THRESHOLDS, TRAFFIC_ADC_RESOLUTION, TRAFFIC_INDICATION_MAPPING, FSM_STATE_TO_TRAFFIC

class AgcState(Enum):
    """
    AGC FSM의 2가지 상태를 정의합니다 (교수님 피드백: 간소화)
    """
    LOW_GAIN = "LOW_GAIN"      # wake_up + lowpowersignal
    HIGH_GAIN = "HIGH_GAIN"    # highperformancesignal

class AgcFsm:
    """AGC FSM 동작을 관리하는 클래스"""
    
    def __init__(self):
        """FSM 초기화 - 항상 LOW_GAIN 상태로 시작"""
        self.current_state = AgcState.LOW_GAIN
        self.previous_state = None
        
        # 상태 전이 히스토리
        self.state_history = [self.current_state]
        self.transition_count = 0
        
        # LUT에서 각 상태별 설정값을 가져옴
        self.lut = LUT_THRESHOLDS.copy()
        
        print(f"AGC FSM initialized")
        print(f"Initial state: {self.current_state.value}")
        print(f"Initial gain: {self.get_current_gain()} dB")
        print(f"Initial ADC resolution: {self.get_current_adc_resolution()} bits")
    
    def get_state_from_traffic_type(self, traffic_type: str) -> AgcState:
        """
        트래픽 유형에 따른 대상 FSM 상태를 결정합니다.
        
        Args:
            traffic_type (str): 트래픽 유형 ("sensor", "voice", "video", "wake_up")
            
        Returns:
            AgcState: 해당 트래픽에 적합한 FSM 상태
        """
        traffic_state_mapping = {
            "wake_up": AgcState.LOW_GAIN_LP,
            "sensor": AgcState.LOW_GAIN_HP, 
            "voice": AgcState.MEDIUM_GAIN,
            "video": AgcState.HIGH_GAIN
        }
        
        return traffic_state_mapping.get(traffic_type, AgcState.LOW_GAIN_LP)
    
    def should_transition(self, carrier_sensing_results: dict, signal_field_indication: str = None) -> bool:
        """
        Carrier Sensing 결과와 Signal Field indication을 바탕으로 상태 전이 여부를 결정합니다.
        
        Args:
            carrier_sensing_results (dict): CS 결과 (saturation, energy, correlation)
            signal_field_indication (str): Signal Field에서 추출한 트래픽 유형
            
        Returns:
            bool: 상태 전이가 필요하면 True, 아니면 False
        """
        current_lut = self.lut[self.current_state.value]
        
        # 1. Carrier Sensing 기준 확인
        saturation_detected = carrier_sensing_results.get("saturation", False)
        energy_detected = carrier_sensing_results.get("energy", False) 
        correlation_detected = carrier_sensing_results.get("correlation", False)
        
        # 2. Wake-up 감지 조건 (3가지 중 하나라도 임계값 초과)
        wake_up_detected = saturation_detected or energy_detected or correlation_detected
        
        # 3. 현재 상태가 Standby이고 wake-up이 감지되면 일단 전이 고려
        if self.current_state == AgcState.LOW_GAIN_LP and wake_up_detected:
            return True
            
        # 4. Signal Field indication이 있으면 해당 트래픽에 맞는 상태로 전이
        if signal_field_indication and signal_field_indication != "wake_up":
            target_state = self.get_state_from_traffic_type(signal_field_indication)
            return target_state != self.current_state
        
        # 5. 신호가 더 이상 감지되지 않으면 Standby로 복귀
        if not wake_up_detected and self.current_state != AgcState.LOW_GAIN_LP:
            return True
            
        return False
    
    def transition_to_state(self, target_state: AgcState, reason: str = ""):
        """
        지정된 상태로 전이를 수행합니다.
        
        Args:
            target_state (AgcState): 전이할 대상 상태
            reason (str): 전이 이유 (로깅용)
        """
        if target_state == self.current_state:
            return  # 동일한 상태면 전이하지 않음
            
        self.previous_state = self.current_state
        self.current_state = target_state
        self.transition_count += 1
        self.state_history.append(self.current_state)
        
        print(f"FSM Transition #{self.transition_count}: {self.previous_state.value} → {self.current_state.value}")
        if reason:
            print(f"  Reason: {reason}")
        print(f"  New gain: {self.get_current_gain()} dB")
        print(f"  New ADC resolution: {self.get_current_adc_resolution()} bits")
    
    def process_indication(self, carrier_sensing_results: dict, signal_field_indication: str = None) -> bool:
        """
        Carrier Sensing과 Signal Field 결과를 처리하여 상태 전이를 수행합니다.
        
        Args:
            carrier_sensing_results (dict): CS 결과
            signal_field_indication (str): 트래픽 유형 indication
            
        Returns:
            bool: 상태 전이가 발생했으면 True, 아니면 False
        """
        if not self.should_transition(carrier_sensing_results, signal_field_indication):
            return False
        
        # 전이 로직
        if signal_field_indication:
            # Signal Field indication에 따른 전이 (wake_up 포함)
            target_state = self.get_state_from_traffic_type(signal_field_indication)
            reason = f"Signal Field indication: {signal_field_indication}"

        elif self.current_state == AgcState.LOW_GAIN_LP:
            # Standby에서 신호 감지 시 indication을 기다림
            # indication 없이는 전이하지 않음 (wake_up 패킷일 수 있음)
            return False  # 전이하지 않음
            
        else:
            # 신호 미감지 시 Standby 복귀
            target_state = AgcState.LOW_GAIN_LP  
            reason = "No signal detected, return to Standby"
        
        self.transition_to_state(target_state, reason)
        return True
    
    def get_current_gain(self) -> float:
        """
        현재 FSM 상태에 맞는 이득 값을 반환합니다.
        
        Returns:
            float: 현재 적용해야 할 이득 값 (dB)
        """
        return GAIN_LEVELS[self.current_state.value]
    
    def get_current_adc_resolution(self) -> int:
        """
        현재 FSM 상태에 맞는 ADC 해상도를 반환합니다.
        트래픽 타입별 ADC 해상도를 사용합니다.
        
        Returns:
            int: 현재 사용해야 할 ADC 해상도 (bits)
        """
        # FSM 상태에서 트래픽 타입을 찾고, 해당 ADC 해상도 반환
        traffic_type = FSM_STATE_TO_TRAFFIC.get(self.current_state.value, "sensor")
        return TRAFFIC_ADC_RESOLUTION.get(traffic_type, 10)
    
    def get_current_gain_code(self) -> str:
        """
        현재 FSM 상태의 이득 제어 코드를 반환합니다.
        
        Returns:
            str: 이득 제어 코드 (예: "0100")
        """
        return self.lut[self.current_state.value]["gain_code"]
    
    def get_current_thresholds(self) -> dict:
        """
        현재 FSM 상태의 Carrier Sensing 임계값들을 반환합니다.
        
        Returns:
            dict: 현재 상태의 임계값 설정
        """
        return self.lut[self.current_state.value].copy()
    
    def xor_gain_comparison(self, measured_gain_code: str) -> tuple:
        """
        현재 이득 코드와 측정된 이득 코드의 XOR 비교를 수행합니다.
        (C++ 코드의 XOR 블록 기능을 Python으로 구현)
        
        Args:
            measured_gain_code (str): 측정된 이득 코드
            
        Returns:
            tuple: (XOR 결과, 차이 비트 수)
        """
        current_code = self.get_current_gain_code()
        
        # 길이를 맞춤
        max_len = max(len(current_code), len(measured_gain_code))
        current_padded = current_code.zfill(max_len)
        measured_padded = measured_gain_code.zfill(max_len)
        
        # XOR 연산 수행
        xor_result = ""
        diff_bits = 0
        
        for i in range(max_len):
            bit_xor = str(int(current_padded[i]) ^ int(measured_padded[i]))
            xor_result += bit_xor
            if bit_xor == "1":
                diff_bits += 1
        
        print(f"XOR Comparison: Current={current_code}, Measured={measured_gain_code}")
        print(f"XOR Result: {xor_result}, Difference: {diff_bits} bits")
        
        return xor_result, diff_bits
    
    def reset_to_standby(self):
        """FSM을 초기 Standby 상태로 리셋합니다."""
        self.transition_to_state(AgcState.LOW_GAIN_LP, "Manual reset to Standby")
    
    def get_state_statistics(self) -> dict:
        """FSM 상태 통계를 반환합니다."""
        # 각 상태별 머문 시간 계산
        state_counts = {}
        for state in self.state_history:
            state_counts[state.value] = state_counts.get(state.value, 0) + 1
        
        return {
            "current_state": self.current_state.value,
            "total_transitions": self.transition_count,
            "state_history_length": len(self.state_history),
            "state_distribution": state_counts,
            "state_history": [state.value for state in self.state_history[-10:]]  # 최근 10개
        }

# 테스트 함수
def test_agc_fsm():
    """AGC FSM 테스트 함수"""
    print("=== Testing AGC FSM ===")
    
    fsm = AgcFsm()
    
    # 테스트 시나리오 1: Wake-up 감지
    cs_results = {"saturation": False, "energy": True, "correlation": False}
    fsm.process_indication(cs_results)
    
    # 테스트 시나리오 2: Voice 트래픽 감지
    fsm.process_indication(cs_results, "voice")
    
    # 테스트 시나리오 3: Video 트래픽 감지  
    fsm.process_indication(cs_results, "video")
    
    # 테스트 시나리오 4: 신호 미감지 (Standby 복귀)
    no_signal = {"saturation": False, "energy": False, "correlation": False}
    fsm.process_indication(no_signal)
    
    # 통계 출력
    stats = fsm.get_state_statistics()
    print(f"\nFSM Statistics: {stats}")

if __name__ == "__main__":
    test_agc_fsm()