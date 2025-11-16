# AGC 시스템 시뮬레이션 - 팀원 공유 문서

## 📌 프로젝트 개요

무선 수신기의 **Adaptive AGC (Automatic Gain Control)** 시스템을 제안하고, 기존 Fixed AGC 방식과 에너지/성능 측면에서 비교하는 시뮬레이션입니다.

### 3가지 비교 모델
1. **Low-Power Fixed AGC** (종래 모델 1)
   - 항상 15dB gain + 5-bit 디지털 사용
   - 저전력이지만 성능(BER) 낮음

2. **High-Performance Fixed AGC** (종래 모델 2)
   - 항상 40dB gain + 10-bit 디지털 사용
   - 고성능이지만 전력 소모 큼

3. **Adaptive AGC** (우리 제안 모델)
   - 트래픽 타입에 따라 디지털 비트 동적 선택
   - 순수 피드백 기반 gain 자동 조절 (10-50dB)
   - **에너지 효율과 성능의 균형** 달성

---

## 🎯 핵심 아이디어

**기존 Fixed 방식**: 항상 동일한 설정 → 에너지 낭비 또는 성능 저하

**우리 제안 방식**:
- 수신한 신호의 트래픽 타입을 Signal Field에서 검출
- **lowpowersignal** → 5-bit 디지털 사용 (저전력)
- **highperformancesignal** → 10-bit 디지털 사용 (고성능)
- Gain은 신호 크기에 따라 실시간 피드백 조절

→ **필요한 만큼만 전력 사용**, 불필요한 성능 오버헤드 제거

---

## 🔧 교수님 피드백 반영 사항

### 1. 아날로그 단일화
- **이전**: LowPowerPath, HighPerfPath 2가지
- **현재**: **UnifiedRFPath** 하나만 사용 (아날로그 전력 항상 동일)

### 2. ADC 고정 + 디지털 Truncation
- **이전**: ADC를 3-bit/10-bit로 변경
- **현재**: **ADC는 항상 10-bit**, 디지털 단에서 5-bit 또는 10-bit로 truncate

### 3. FSM 제거
- **이전**: 4-state FSM (LOW_GAIN_LP, LOW_GAIN_HP, MEDIUM_GAIN, HIGH_GAIN)
- **현재**: **FSM 완전 제거**, 순수 피드백 기반 AGC로 변경
  - 실제 AGC처럼 신호 peak 측정 → gain 자동 조절

### 4. 트래픽 타입 간소화
- **이전**: wake_up, sensor, voice, video (4가지)
- **현재**: wake_up, **lowpowersignal**, **highperformancesignal** (3가지)

### 5. 전력 비교 명확화
- 아날로그 전력은 모든 모델에서 동일
- **디지털 연산량만 차이** (5-bit vs 10-bit)

---

## 🧮 제안 모델 알고리즘 (Adaptive AGC)

### 전체 흐름도

```
[패킷 수신]
    ↓
[1] 초기 설정: gain=30dB, digital=5-bit
    ↓
[2] 블록별 처리 루프 시작
    ↓
[3] RF 증폭 (UnifiedRFPath)
    │   - LNA 20dB (고정)
    │   - VGA 가변 (current_gain_db - 20)
    ↓
[4] ADC 10-bit 양자화
    ↓
[5] 디지털 Truncation
    │   - current_digital_bits가 5이면 → 5-bit로 truncate
    │   - current_digital_bits가 10이면 → truncation 없음
    ↓
[6] Carrier Sensing (패킷 검출)
    │   - Saturation Detection
    │   - Energy Detection
    │   - Correlation Detection
    ↓
[7] Signal Field 디코딩 (트래픽 타입 검출)
    │   - Signal Field 영역이면:
    │     • "01" → lowpowersignal → digital=5-bit
    │     • "10" → highperformancesignal → digital=10-bit
    ↓
[8] Gain 피드백 (순수 피드백 AGC)
    │   - peak = max(|신호 블록|)
    │   - if peak > 0.9:  gain -= 1dB  (포화 방지)
    │   - if peak < 0.25: gain += 1dB  (SNR 향상)
    │   - gain 범위: 10-50dB
    ↓
[9] BER 계산 (STF 영역에서만)
    ↓
[10] 전력 측정
    │   - 아날로그: 항상 동일 (UnifiedRFPath)
    │   - 디지털: 비트 수에 비례 (5-bit << 10-bit)
    ↓
다음 블록으로 (2번으로 돌아감)
```

### 핵심 알고리즘 의사코드

```python
# 초기화
current_gain_db = 30.0          # 초기 gain
current_digital_bits = 5        # 초기 디지털 비트
enable_gain_feedback = True     # 피드백 활성화

# 패킷 처리
for each block in received_packet:

    # (1) RF 증폭
    rf_output = UnifiedRFPath.process(block, current_gain_db)

    # (2) ADC 양자화 (항상 10-bit)
    adc_output = ADC10bit.quantize(rf_output)

    # (3) 디지털 Truncation
    if current_digital_bits < 10:
        digital_output = truncate_to_bits(adc_output, current_digital_bits)
    else:
        digital_output = adc_output

    # (4) Carrier Sensing
    cs_result = CarrierSensing(digital_output)

    # (5) Signal Field 디코딩 (트래픽 타입 검출)
    if in_signal_field_region and not decoded_yet:
        traffic_type = decode_signal_field(digital_output)

        if traffic_type == "lowpowersignal":
            current_digital_bits = 5
        elif traffic_type == "highperformancesignal":
            current_digital_bits = 10

        # 재처리: 새 디지털 비트로 다시 truncate
        if current_digital_bits < 10:
            digital_output = truncate_to_bits(adc_output, current_digital_bits)

    # (6) Gain 피드백 (실제 AGC 동작)
    if enable_gain_feedback:
        peak = max(abs(digital_output))

        if peak > 0.9:        # 포화 위험
            current_gain_db -= 1
        elif peak < 0.25:     # SNR 부족
            current_gain_db += 1

        # Gain 범위 제한
        current_gain_db = clip(current_gain_db, 10, 50)

    # (7) BER 계산 (STF 영역)
    if in_stf_region:
        ber = calculate_ber(digital_output, reference_stf)

    # (8) 전력 측정
    analog_power = MAX2829_RX_POWER  # 항상 동일 (~392mW)
    digital_energy = compute_energy(operations, current_digital_bits)
```

### 디지털 Truncation 상세

```python
def truncate_to_bits(signal_10bit, target_bits):
    """
    ADC 10-bit 출력을 디지털 단에서 target_bits로 truncate

    예시: 10-bit → 5-bit
    - 10-bit: -512 ~ 511 (1024 levels)
    - 5-bit:  -16 ~ 15 (32 levels)
    - 방법: 하위 5비트 버림 (bit shift)
    """
    if target_bits >= 10:
        return signal_10bit  # truncation 없음

    # Integer로 변환
    step_size_10bit = 2 * vref / 1024
    signal_int = round(signal_10bit / step_size_10bit)

    # 비트 시프트
    bit_shift = 10 - target_bits
    truncated_int = (signal_int >> bit_shift) << bit_shift

    # 다시 analog로 변환
    truncated_signal = truncated_int * step_size_10bit

    return truncated_signal
```

---

## 📊 비교 결과 (11가지 메트릭)

시뮬레이션 실행 시 다음 11개 그래프가 생성됩니다:

1. **metrics_energy.png**: 아날로그/디지털 에너지 소모 비교
2. **metrics_accuracy.png**: BER (Bit Error Rate) 비교
3. **metrics_latency.png**: 평균 지연 시간 비교
4. **metrics_operations.png**: 연산량 (덧셈, 곱셈) 비교
5. **metrics_energy_efficiency.png**: 에너지 효율 (bits per Joule)
6. **metrics_sqnr.png**: SQNR (Signal to Quantization Noise Ratio)
7. **metrics_throughput.png**: 처리량 (bits per second)
8. **metrics_ber_vs_snr.png**: SNR에 따른 BER 변화
9. **metrics_ber_by_traffic.png**: 트래픽 타입별 BER
10. **metrics_energy_by_traffic.png**: 트래픽 타입별 에너지
11. **metrics_adc_bit_usage.png**: 5-bit/10-bit 사용 비율

**기대 결과**:
- Adaptive AGC가 Low-Power보다 **BER 낮음** (더 정확함)
- Adaptive AGC가 High-Perf보다 **에너지 적게** 소모
- **에너지-성능 트레이드오프에서 최적 균형점** 달성

---

## 🚀 실행 방법

### 1. 의존성 설치
```bash
pip install numpy scipy matplotlib
```

### 2. 시뮬레이션 실행
```bash
python main_agc_system.py
```

### 3. 출력 파일
- **콘솔**: 진행 상황, 통계 요약
- **PNG 파일**: 11개 비교 그래프 (metrics_*.png)

### 4. 주요 설정 변경 (config.py)
```python
# SNR 범위
SNR_RANGE = [5, 10, 15, 20]

# 패킷 수
PACKETS_PER_SCENARIO = 20

# 트래픽 타입
TRAFFIC_TYPES = ["lowpowersignal", "highperformancesignal"]

# 디지털 비트 설정
DIGITAL_TRUNCATION_BITS = {
    "wake_up": 5,
    "lowpowersignal": 5,
    "highperformancesignal": 10,
}
```

---

## 📁 주요 파일 구조

```
test7.2/
├── main_agc_system.py          # 메인 시뮬레이션 + 3가지 모델 정의
├── agc_comparison.py           # 모델 비교 및 그래프 생성
├── carrier_sensing.py          # 패킷 검출 (saturation, energy, correlation)
├── signal_generator.py         # PHY 패킷 생성 (BPSK)
├── ber_calculator.py           # BER 계산
├── rf_paths.py                 # UnifiedRFPath (아날로그 프론트엔드)
├── adc.py                      # ADC 10-bit + 디지털 truncation
├── power_measurement.py        # 전력/에너지 측정
├── analog_power_base.py        # 아날로그 전력 모델 (MAX2829)
├── digital.py                  # 디지털 회로 area 모델
├── config.py                   # 설정 파일
├── simulation_utils.py         # 유틸리티 함수
├── optimize_gains.py           # Gain 최적화 도구
├── CLAUDE.md                   # 상세 기술 문서 (1135 lines)
└── SUMMARY.md                  # 이 문서 (팀원 공유용)
```

---

## 🔍 Fixed 모델 vs Adaptive 모델 차이점

### Fixed Low-Power AGC
```python
class FixedLowPowerAGC(AgcSystem):
    def __init__(self):
        super().__init__(
            initial_digital_bits=5,
            enable_gain_feedback=False  # Gain 고정
        )
        self.current_gain_db = 15.0     # 항상 15dB
```
- Gain 변경 ❌
- Digital bits 변경 ❌
- 항상 15dB + 5-bit 고정

### Fixed High-Performance AGC
```python
class FixedHighPerformanceAGC(AgcSystem):
    def __init__(self):
        super().__init__(
            initial_digital_bits=10,
            enable_gain_feedback=False  # Gain 고정
        )
        self.current_gain_db = 40.0     # 항상 40dB
```
- Gain 변경 ❌
- Digital bits 변경 ❌
- 항상 40dB + 10-bit 고정

### Adaptive AGC (제안)
```python
class AgcSystem:
    def __init__(self, enable_gain_feedback=True):
        self.enable_gain_feedback = True   # Gain 피드백 활성화
        self.current_gain_db = 30.0        # 초기 gain (변경 가능)
        self.current_digital_bits = 5      # 초기 digital (변경 가능)
```
- Gain 변경 ✅ (10-50dB, 피드백 기반)
- Digital bits 변경 ✅ (5 또는 10, 트래픽 기반)
- **동적 적응**

---

## 📌 주요 개념 정리

### 1. UnifiedRFPath (통일된 아날로그)
```
LNA(20dB 고정) → Mixer → VGA(가변 0-30dB) → LPF
```
- 모든 모델에서 동일한 회로 사용
- 전력 소모 항상 동일 (~392mW, MAX2829)
- **VGA gain만 변경** (total gain = 20 + VGA)

### 2. Digital Truncation
- **하드웨어 ADC**: 항상 10-bit (1024 levels)
- **디지털 처리**: 5-bit 또는 10-bit로 선택
- 5-bit truncation: 상위 5비트만 사용 (32 levels)
- **전력 차이**: 디지털 연산량에서만 발생

### 3. 순수 피드백 AGC
- FSM 없음, 직접 gain 변수 사용
- Peak 측정 → 실시간 조절
- 실제 AGC 시스템과 동일한 방식

### 4. Signal Field
- 패킷의 preamble 다음에 위치
- 2-bit indication으로 트래픽 타입 전달
  - "01": lowpowersignal
  - "10": highperformancesignal
- 수신기가 이를 디코딩하여 디지털 비트 결정

---

## 💡 연구 기여도

1. **적응형 디지털 해상도 선택**: 트래픽 타입 기반으로 동적 변경
2. **에너지-성능 균형**: Fixed 방식의 양극단 문제 해결
3. **실제 AGC 동작 반영**: FSM 대신 순수 피드백 사용
4. **명확한 전력 비교**: 아날로그 통일 → 디지털만 차이

---

## 📞 질문/문의

- 상세 기술 문서: `CLAUDE.md` 참고
- 코드 수정 시: `config.py`에서 파라미터 조정
- Gain 최적화: `python optimize_gains.py` 실행

---

**작성일**: 2025-11-16
**버전**: 1.0 (교수님 피드백 반영 완료)
