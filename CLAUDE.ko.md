# AGC (Automatic Gain Control) 시스템 시뮬레이션 - 프로젝트 문서

## 1. 프로젝트 개요

### 목적
이 프로젝트는 **무선 수신기 설계를 위한 Python 기반 자동 이득 제어(AGC) 시스템 시뮬레이션 프레임워크**입니다. 세 가지 AGC 접근 방식을 구현하고 비교합니다:
1. **저전력 고정 AGC** - 보수적, 항상 최소 전력 사용 (3비트 ADC, 10dB 이득)
2. **고성능 고정 AGC** - 공격적, 항상 최대 성능 사용 (10비트 ADC, 40dB 이득)
3. **적응형 AGC** (제안) - 감지된 트래픽 유형에 따라 ADC 해상도와 이득을 동적으로 조정

### 적용 분야
- **무선 통신/수신기 설계**
- **에너지 효율적인 신호 처리**
- **하드웨어-소프트웨어 협업 설계**
- 다중 트래픽 유형(wake-up, 센서, 음성, 비디오)을 가진 IoT/임베디드 무선 시스템 대상

### 핵심 목표
적응형 AGC 시스템이 감지된 트래픽 유형에 따라 ADC 해상도와 RF 이득을 동적으로 선택함으로써, 고정 모드 접근 방식 대비 에너지 소비와 신호 품질(BER) 사이의 더 나은 균형을 달성할 수 있음을 입증합니다.

---

## 2. 전체 아키텍처

### 상위 수준 시스템 흐름

```
입력 패킷 (traffic_type)
    ↓
SignalGenerator: PHY 패킷 생성 (STF + LTF 프리앰블 + 신호 필드 + 페이로드)
    ↓
AWGN 노이즈 추가 (채널 시뮬레이션)
    ↓
RF 프론트엔드 경로 선택
    ├─ LowPowerPath (LOW_GAIN_LP 상태) → 제한된 이득, 저전력
    └─ HighPerfPath (기타 상태) → 전체 이득, 고전력
    ↓
ADC 양자화 (ADC 해상도에 따라 3비트 또는 10비트)
    ↓
블록별 처리
    ├─ 캐리어 센싱 (3가지 방법: 포화, 에너지, 상관 검출)
    ├─ BER 계산 (STF에서 신호 품질 측정)
    ├─ FSM 상태 전환 (캐리어 센싱 + 신호 필드 표시 기반)
    ├─ 동적 이득 조정 (피크 기반 피드백)
    └─ 전력 측정 (아날로그 + 디지털)
    ↓
메트릭 수집 (BER, 전력, 에너지, 이득, FSM 상태)
    ↓
출력: 성능 메트릭이 포함된 패킷 결과
```

### 컴포넌트 상호작용 다이어그램

```
AgcSystem (메인 오케스트레이터)
├── AgcFsm (유한 상태 기계)
│   ├── 상태: LOW_GAIN_LP, LOW_GAIN_HP, MEDIUM_GAIN, HIGH_GAIN
│   ├── LUT: 상태별 임계값
│   └── 출력: current_state, gain_db, adc_resolution
│
├── SignalGenerator (신호 생성기)
│   ├── BPSK 변조
│   └── 패킷 생성: 프리앰블(STF+LTF) + 신호 필드 + 페이로드
│
├── RF Paths (아날로그 프론트엔드)
│   ├── LowPowerPath: LNA(고정) → Mixer → LPF
│   └── HighPerfPath: LNA(고정) → Mixer → VGA → LPF
│
├── ADC (아날로그-디지털 변환기)
│   ├── ADC3bit (저전력 모드, 8 레벨)
│   └── ADC10bit (고성능 모드, 1024 레벨)
│
├── CarrierSensing (캐리어 센싱)
│   ├── SaturationDetector (ADC 포화 확인)
│   ├── EnergyDetector (신호 전력 임계값)
│   └── CorrelationDetector (수신 신호와 STF 상관)
│
├── BERCalculator (비트 오류율 계산)
│   └── STF에서 하드 결정 BPSK 사용하여 품질 측정
│
├── Power Measurement Modules (전력 측정 모듈)
│   ├── AnalogPowerMeasurement (MAX2829/MAX2830 모델)
│   └── DigitalComputationMeasurement (면적 기반 에너지 추정)
│
└── Utilities (유틸리티)
    ├── TimeSeriesDataCollector
    ├── TrafficFlowManager
    ├── SignalFieldDecoder
    └── SimulationUtils
```

---

## 3. 주요 모듈 및 역할

### 핵심 처리 모듈

#### **main_agc_system.py** (713줄)
**역할**: 메인 AGC 시스템 클래스 및 시뮬레이션 오케스트레이터

**주요 클래스**:
- `AgcSystem`: 적응형 AGC 시스템을 구현하는 주 클래스
  - `__init__()`: FSM, RF 경로, ADC, 캐리어 센싱, 전력 모델 초기화
  - `process_packet()`: 메인 패킷 처리 파이프라인
  - `apply_adc_quantization()`: ADC 양자화 시뮬레이션
  - `extract_signal_field_indication()`: 신호 필드에서 트래픽 유형 디코딩
  - `update_adc_resolution_for_traffic()`: 트래픽 기반 적응형 ADC 선택
  - `run_simulation()`: 다중 패킷/SNR 값으로 전체 시뮬레이션 실행

**주요 메서드**:
- `process_rf_signal()`: RF 경로 이득 및 필터링 적용
- `_update_power_measurements()`: 아날로그 및 디지털 전력/에너지 계산
- `_calculate_cs_operations()`: 캐리어 센싱을 위한 산술 연산 카운트
- `_calculate_ber_operations()`: BER 계산을 위한 산술 연산 카운트
- 신호 피크 기반 이득 피드백이 있는 블록 기반 처리 루프
- 상태 히스토리 추적 및 통계 수집

**진입점**: 파일 끝의 `main()` - 3개 모델을 실행하고 3개의 비교 메트릭 그래프 생성

---

#### **agc_fsm.py** (268줄)
**역할**: AGC 제어를 위한 유한 상태 기계

**주요 클래스**:
- `AgcState` (열거형): 4가지 상태
  - `LOW_GAIN_LP`: 대기/wake-up (10 dB, 3비트 ADC)
  - `LOW_GAIN_HP`: 센서 데이터 (25 dB, 4비트 ADC)
  - `MEDIUM_GAIN`: 음성 (35 dB, 8비트 ADC)
  - `HIGH_GAIN`: 비디오 (40 dB, 10비트 ADC)

- `AgcFsm`: 상태 기계 구현
  - `process_indication()`: 캐리어 센싱 결과 및 신호 필드 표시를 기반으로 상태 전환 필요 여부 결정
  - `should_transition()`: 결정 로직 (wake-up 검출, 신호 필드 매칭, 신호 없음 폴백)
  - `transition_to_state()`: 로깅과 함께 상태 변경 수행
  - `get_current_gain()`: 현재 상태의 dB 이득 반환
  - `get_current_adc_resolution()`: 현재 상태의 ADC 비트 수 반환
  - `xor_gain_comparison()`: 예상 대 측정 이득 코드 비교
  - `get_state_statistics()`: 전환 히스토리 반환

**전환 로직**:
1. LOW_GAIN_LP 상태에서 신호 감지 시 → 신호 필드 표시 대기
2. 신호 필드가 특정 트래픽 표시 시 → 해당 상태로 전환
3. 모든 상태에서 신호 없음 시 → LOW_GAIN_LP(대기)로 복귀
4. 각 상태는 포화, 에너지, 상관 검출을 위한 임계값이 있는 조회 테이블(LUT) 보유

---

#### **carrier_sensing.py** (394줄)
**역할**: 다중 방법을 사용한 패킷 존재 검출

**주요 클래스**:
- `SaturationDetector`: ADC 샘플이 포화 임계값 초과 여부 확인
  - I/Q 컴포넌트를 임계값과 비교
  - 포화율 및 불린 검출 반환

- `EnergyDetector`: 신호 전력 측정 및 에너지 임계값 비교
  - 복소 신호의 평균 전력 계산
  - dB로 변환하고 임계값 비교 (기본값 -75 dBm)
  - 검출 히스토리 추적

- `CorrelationDetector`: 수신 신호와 알려진 STF 시퀀스 상관
  - STF 참조와 슬라이딩 윈도우 상관 구현
  - 상관 크기 계산
  - 상관 임계값 비교 (상태에 따라 0.6-0.85)

- `CarrierSensingTop`: 3가지 검출기를 결합하는 래퍼
  - `process_signal()`: 입력 블록에서 모든 검출기 실행
  - `update_resolution()`: ADC 비트에 따라 포화 임계값 업데이트
  - 각 방법에 대한 불린 플래그가 있는 `detection_methods` 딕셔너리 반환

**출력 형식**:
```python
{
    "detection_methods": {
        "saturation": bool,
        "energy": bool,
        "correlation": bool
    },
    "saturation": {...},
    "energy": {...},
    "correlation": {...}
}
```

---

#### **signal_generator.py** (228줄)
**역할**: PHY 계층 무선 패킷 생성

**주요 클래스**:
- `SignalGenerator`: 완전한 무선 패킷 생성
  - `generate_stf_signal()`: Short Training Field (프리앰블) 생성
  - `generate_ltf_signal()`: Long Training Field (프리앰블) 생성
  - `generate_preamble()`: STF + LTF 결합
  - `create_complete_packet()`: 전체 패킷 생성 (프리앰블 + 신호 필드 + 페이로드)
  - `bits_to_bpsk()`: 비트 → 업샘플링과 함께 BPSK 심볼로 변조
  - `bpsk_to_bits()`: 다운샘플링과 함께 BPSK → 비트로 복조

**패킷 구조**:
```
프리앰블(STF + LTF) → 신호 필드(48비트) → 페이로드(1024비트)
  128비트 (STF)      48비트(트래픽 유형)    모두 BPSK로 변조
  +64비트 (LTF)      + 제어 비트            20 MHz 샘플링
```

**설정**:
- 샘플링 레이트: 20 MHz
- 심볼 레이트: 1 MHz
- 심볼당 샘플: 20
- BPSK 성좌: {0: -1.0, 1: +1.0}

---

#### **ber_calculator.py** (250줄)
**역할**: 신호 품질 평가를 위한 비트 오류율 계산

**주요 클래스**:
- `BERCalculator`: 수신 대 전송 STF 비트 비교로 BER 측정
  - `process_stf_block()`: 신호 블록에 대한 BER 계산
  - `process_complete_packet()`: 전체 패킷 STF에 대한 BER 계산
  - `calculate_bit_errors()`: 원본과 수신 비트 간 XOR 비교
  - `update_ber_statistics()`: 오류율의 슬라이딩 윈도우 유지
  - `get_current_ber()`: 윈도우 BER 반환
  - `get_cumulative_ber()`: 총 누적 BER 반환

**방법론**:
- 하드 결정 복조: 실수부 > 0 → '1', 그렇지 않으면 '0'
- 수신 비트를 참조 STF 비트와 비교
- BER = (오류 비트 수) / (총 비트 수)
- 슬라이딩 윈도우로 최근 성능 추적

---

### 하드웨어 모델링 모듈

#### **adc.py** (93줄)
**역할**: ADC 양자화 시뮬레이션

**주요 클래스**:
- `BaseADC`: 일반 N비트 ADC 모델
  - `quantize()`: 신호를 가장 가까운 양자화 레벨로 반올림
  - `quantize_to_int()`: 정수 표현 반환
  - 매개변수: 비트 폭, 기준 전압, 양자화 스텝

- `ADC3bit`: 저전력 변형 (8 레벨, 범위: -4 ~ 3)
- `ADC10bit`: 고성능 변형 (1024 레벨, 범위: -512 ~ 511)

**양자화 프로세스**:
1. 신호를 전압 기준 범위로 클립
2. 가장 가까운 스텝으로 반올림 (스텝 = 2*Vref / 2^비트)
3. 양자화된 값 반환

---

#### **rf_paths.py** (179줄)
**역할**: RF 프론트엔드 아날로그 처리 체인 모델링

**함수** (기본 연산):
- `lna()`: 저잡음 증폭기 (dB 단위 선형 이득)
- `mixer()`: 주파수 변환 (LO와 곱셈)
- `vga()`: 가변 이득 증폭기 (조정 가능한 이득)
- `lpf()`: 저역 통과 필터 (1차 IIR)

**주요 클래스**:
- `HighPerfPath`: 고성능 수신 경로
  - 체인: LNA(20dB) → Mixer → VGA(가변) → LPF
  - 높은 이득이지만 높은 전력 소비

- `LowPowerPath`: 저전력 수신 경로
  - 체인: LNA(coarse+fine) → Mixer → LPF (VGA 없음)
  - 제한된 이득이지만 최소 전력 소비

---

#### **analog_power_base.py** (100줄)
**역할**: 아날로그 프론트엔드 전력 소비 모델링

**주요 클래스**:
- `AnalogPowerModelBase`: 전력 모델을 위한 추상 베이스
  - `get_power()`: 특정 모드에 대한 전력 반환 (mW)
  - `get_energy_consumption()`: 기간에 대한 에너지 계산 (mJ = 전력 × 시간)

- `MAX2829PowerModel`: 고성능 수신기 IC 모델
  - 대기: ~184 mW
  - RX 활성: ~392 mW

- `MAX2830PowerModel`: 저전력 수신기 IC 모델
  - 대기: ~78.4 mW
  - RX 활성: ~173.6 mW

- `AnalogPowerMeasurement` (power_measurement.py에 있음): 총 및 평균 전력 추적

---

#### **digital.py** (80줄)
**역할**: 디지털 처리 면적 및 전력 모델링

**주요 클래스**:
- `DigitalAreaModel`: 디지털 컴포넌트의 회로 면적(μm²) 계산
  - 기본 면적: 전가산기 (1.183 μm²), 곱셈기 셀 (3.5 μm²)
  - N비트 가산기 면적: N × 1.183
  - N비트 곱셈기 면적: N² × 3.5
  - 총 디지털 처리 면적은 ADC 비트 폭에 따라 달라짐

**용도**: 회로 면적과 연산 수를 기반으로 에너지 추정

---

#### **power_measurement.py** (159줄)
**역할**: 전력 및 에너지 메트릭 집계

**주요 클래스**:
- `DigitalComputationMeasurement`: 디지털 연산 및 에너지 추적
  - `update_computation()`: 곱셈 및 덧셈 누적
  - 캐리어 센싱, BER 계산 및 비트 종속 연산의 연산 수 카운트
  - `get_total_energy()`: 에너지 = 연산 × 연산당_전력 × 면적_스케일링 (pJ)

- `AnalogPowerMeasurement`: 아날로그 전력 소비 누적
  - `update_power_measurement()`: 기간 × 전력 추가
  - `get_total_energy()`: 총 누적 에너지 (mJ)
  - `calculate_power()`: 특정 상태에 대한 전력

---

### 구성 및 비교 모듈

#### **config.py** (93줄)
**역할**: 중앙 집중식 구성 매개변수

**주요 구성**:
- **신호 매개변수**:
  - 샘플링 레이트: 20 MHz
  - 심볼 레이트: 1 MHz
  - 심볼당 샘플: 20
  - STF/LTF/신호 필드/페이로드 비트 수

- **AGC 이득 레벨** (dB 단위):
  - LOW_GAIN_LP: 10 dB (wake-up)
  - LOW_GAIN_HP: 25 dB (센서)
  - MEDIUM_GAIN: 35 dB (음성)
  - HIGH_GAIN: 40 dB (비디오)

- **트래픽 유형별 ADC 해상도**:
  - wake_up: 3비트
  - sensor: 4비트
  - voice: 8비트
  - video: 10비트

- **캐리어 센싱 임계값** (FSM 상태별):
  - 포화 임계값 (ADC 레벨 종속)
  - 에너지 임계값 (dBm)
  - 상관 임계값 (0.6-0.85)
  - 이득 코드 (이진 문자열)

- **채널 및 BER 매개변수**:
  - 기본 SNR: 10 dB
  - 노이즈 전력: 0.1
  - BER 윈도우 크기: 128비트
  - BER 업데이트 간격: 100 샘플

- **디지털 연산 스케일링**:
  - K_ADD_PER_SAMPLE: 1.0 (샘플당 비트당 덧셈)
  - K_MUL_PER_SAMPLE: 0.05 (샘플당 비트²당 곱셈)

---

#### **agc_comparison.py** (726줄)
**역할**: 3가지 AGC 모델 비교 및 결과 메트릭 생성

**주요 클래스**:
- `FixedLowPowerAGC`: AgcSystem 확장, LOW_GAIN_LP 상태 + 3비트 ADC 항상 강제
  - FSM 전환을 방지하기 위해 `process_packet()` 오버라이드
  - 최저 전력 소비, 잠재적 정확도 손실

- `FixedHighPerformanceAGC`: AgcSystem 확장, HIGH_GAIN 상태 + 10비트 ADC 항상 강제
  - FSM 전환을 방지하기 위해 `process_packet()` 오버라이드
  - 최고 정확도, 최고 전력 소비

- `AdaptiveAGC`: AgcSystem 확장, 전체 적응 로직 사용
  - FSM이 캐리어 센싱 및 신호 필드 표시에 반응
  - 감지된 트래픽 유형에 따라 ADC 해상도 선택
  - 신호 피크에 기반한 동적 이득 조정

**주요 함수**:
- `run_comparison_simulation()`: 3개 모델 모두 동일한 트래픽 패턴으로 실행, 메트릭 수집
- `calculate_average_results()`: 반복에 걸쳐 결과 평균화
- `compute_model_metrics()`: 모델별 메트릭 계산 (총 에너지, 평균 BER, 지연)
- `plot_three_metrics_models()`: 3개 출력 그래프 생성

**출력 그래프**:
1. `metrics_energy.png`: 모델별 아날로그(mJ) + 디지털(pJ) 에너지
2. `metrics_accuracy.png`: 모델별 평균 BER
3. `metrics_latency.png`: 모델별 평균 지연

---

#### **optimize_gains.py** (145줄)
**역할**: 각 트래픽 유형에 대한 최적 이득 값을 찾는 유틸리티

**주요 함수**:
- `test_gain_performance()`: 특정 이득 값에서 BER 측정
- `optimize_gains_for_traffic()`: 각 트래픽 유형에 대해 이득 범위(0-50 dB) 검색
- `test_fixed_agc_gains()`: 기존 접근 방식에 대한 최적 고정 이득 찾기

**용도**: config.py에 대한 더 나은 이득 구성 값을 찾기 위해 실행

---

### 유틸리티 모듈

#### **simulation_utils.py** (422줄)
**역할**: 헬퍼 함수 및 데이터 수집

**주요 클래스**:
- `TrafficFlowManager`: 트래픽 패턴 시퀀스 생성
  - 순환: wake_up → sensor → voice → video → (갭) → 반복

- `TimeSeriesDataCollector`: 시뮬레이션 중 시계열 데이터 누적
  - 추적: 시간, 트래픽 유형, 전력(아날로그/디지털), BER, FSM 상태, 이득, SNR
  - 메모리 효율성을 위해 저장을 100K 포인트로 제한

- `SignalFieldDecoder`: 신호 필드에서 트래픽 유형 디코딩
  - 2비트 표시를 트래픽 유형에 매핑
  - 복조 실패 시 패킷 메타데이터로 폴백

**주요 함수**:
- `calculate_block_size()`: 처리 블록 크기 결정 (STF 길이)
- `safe_divide()`: 0으로 나누기 방지
- 비교 그래프 생성을 위한 플로팅 유틸리티

---

## 4. 메인 진입점 및 워크플로

### 주 진입점: `main_agc_system.py`

```python
if __name__ == "__main__":
    main()
```

**실행 흐름**:
1. 3개 AGC 모델 생성:
   - `FixedLowPowerAGC()`
   - `FixedHighPerformanceAGC()`
   - `AgcSystem(use_indicator_for_adc=True)` (적응형)

2. 각 모델에 대해 `run_one_model()` 호출:
   - `model.run_simulation(traffic_types, snr_range, packets_per_scenario)` 실행
   - 트래픽 유형: sensor, voice, video
   - SNR 범위: 5, 10, 15, 20 dB
   - SNR 시나리오당 20개 패킷

3. `compute_model_metrics()`를 통해 메트릭 수집:
   - 총 아날로그 에너지 (mJ)
   - 총 디지털 에너지 (pJ)
   - 평균 BER
   - 평균 지연 (ms)

4. 3개 비교 그래프 생성:
   - 에너지 사용 비교
   - 정확도(BER) 비교
   - 지연 비교

5. 현재 디렉토리에 PNG 저장

---

### 시뮬레이션 워크플로: `run_simulation()`

```python
agc_system = AgcSystem()
sim_result = agc_system.run_simulation(
    traffic_types=["sensor", "voice", "video"],
    snr_range_db=[5, 10, 15, 20],
    packets_per_scenario=20
)
```

**시뮬레이션별 단계** (각 SNR, 각 패킷):
1. 특정 트래픽 유형으로 패킷 생성
2. 깨끗한 신호에 AWGN 노이즈 추가
3. RF 경로를 통해 처리 (현재 FSM 상태에 따라 선택)
4. ADC 양자화 적용
5. **블록별 처리**:
   - 캐리어 센싱 실행 (포화, 에너지, 상관)
   - CS 연산 수 계산
   - 신호 필드 표시 추출 (신호 필드 영역에 있는 경우)
   - ADC 해상도 업데이트 확인 (적응 모드)
   - FSM 상태 전환 확인
   - STF 영역에서 BER 계산
   - 피크 기반 이득 조정 피드백
   - 전력 측정 업데이트
6. 모든 하위 블록 메트릭으로 패킷 결과 집계
7. 다음을 포함하는 패킷 결과 반환:
   - 최종 BER, FSM 상태, 이득, ADC 해상도
   - 블록 수준 결과
   - 아날로그 및 디지털 전력/에너지

---

### 패킷 처리 파이프라인: `process_packet()`

```python
result = agc_system.process_packet(packet_info, channel_snr_db=10)
```

**입력**:
- `packet_info`: 패킷 구조가 있는 딕셔너리 (STF/LTF/SF/페이로드 인덱스, complete_signal, traffic_type)
- `channel_snr_db`: dB 단위 채널 SNR

**주요 처리 단계**:

1. **ADC 해상도 선택**:
   - 적응 모드: 3비트로 시작, 신호 필드 표시 대기 후 업데이트
   - 고정 모드: 3비트 또는 10비트로 고정

2. **채널 시뮬레이션**: 지정된 SNR에서 AWGN 추가

3. **RF 처리**:
   - 경로 선택: LowPowerPath(LOW_GAIN_LP) 또는 HighPerfPath(기타 상태)
   - 이득 및 필터링 적용

4. **블록 루프** (청크로 처리):
   - 캐리어 센싱 (3가지 방법, ~320-330 산술 연산)
   - 신호 필드 영역 확인:
     - 신호 필드 영역에 있고 아직 추출되지 않은 경우:
       - 신호 필드 비트에서 트래픽 유형 디코딩
       - (적응 모드) 디코딩된 트래픽에 따라 ADC 해상도 업데이트
       - 새 ADC로 블록 재처리
   - FSM 표시 처리:
     - 상태 변경 필요 여부 확인
     - 변경된 경우 새 구성으로 블록 재처리
   - 이득 피드백:
     - 블록의 피크 측정
     - 피크 > 0.90: 이득 1 dB 감소
     - 피크 < 0.25: 이득 1 dB 증가
     - 이득 변경 시 블록 재처리
   - BER 계산 (STF 영역만):
     - 하드 결정 복조: real > 0 → 1, 그렇지 않으면 0
     - 참조 STF 비트와 XOR
     - 오류율 카운트 (~680 산술 연산)
   - 전력 측정:
     - 아날로그: 상태 종속 (저전력 또는 고성능 IC 모델)
     - 디지털: 연산 종속 + 면적 기반 스케일링
   - 블록 결과 수집

5. **최종 패킷 계산**:
   - 수신 신호에서 패킷 수준 BER 계산
   - 모든 블록 결과 집계
   - 모든 메트릭이 포함된 결과 딕셔너리 반환

---

## 5. 종속성 및 외부 라이브러리

### 핵심 Python 라이브러리
- **numpy**: 수치 계산 (신호 처리, 통계)
- **matplotlib**: 플로팅 및 그래프 생성
- **scipy**: 통계 분포 (신뢰 구간)
- **collections**: 데이터 집계를 위한 defaultdict
- **enum**: AgcState 열거형
- **abc**: 전력 모델을 위한 추상 베이스 클래스
- **os**: 파일 연산 (디렉토리 생성)
- **typing**: 타입 힌트 (Dict, List, Tuple, Optional)

### 외부 하드웨어 시뮬레이션 라이브러리 없음
- 모든 RF/ADC 모델은 Python으로 처음부터 구현
- 모듈식 설계로 쉬운 확장 가능

---

## 6. 설계 패턴 및 규칙

### 아키텍처 패턴

1. **상태 기계 패턴**
   - `AgcFsm`은 이산 상태를 가진 FSM 구현
   - 각 상태는 특정 이득/ADC 구성에 매핑
   - 캐리어 센싱 및 신호 필드 표시를 기반으로 전환
   - 상태 종속 임계값을 위한 LUT (조회 테이블)

2. **전략 패턴**
   - 3가지 AGC 전략: 저전력, 고성능, 적응형
   - 다른 `process_packet()` 구현을 가진 공유 `AgcSystem` 베이스 클래스
   - 새 전략 추가 용이 (예: 예측 AGC)

3. **데코레이터/래퍼 패턴**
   - `CarrierSensingTop`이 3가지 검출 방법 래핑
   - `TimeSeriesDataCollector`가 측정 로깅 래핑
   - `AnalogPowerMeasurement`가 전력 모델 선택 래핑

4. **빌더/구성 패턴**
   - 모든 매개변수에 대한 중앙 집중식 `config.py`
   - 상태 임계값을 위한 딕셔너리 기반 LUT
   - 코드 변경 없이 구성 수정 가능

5. **파이프라인 패턴**
   - 패킷 처리는 별개의 단계를 통해 흐름:
     신호 → RF 경로 → ADC → 블록 루프 → 결과
   - 각 단계 모듈식이고 독립적으로 테스트 가능

### 명명 규칙

- **클래스 이름**: CamelCase (`AgcSystem`, `CarrierSensingTop`)
- **메서드 이름**: snake_case (`process_packet()`, `run_simulation()`)
- **상수**: UPPER_CASE (`SAMPLING_RATE`, `GAIN_LEVELS`)
- **FSM 상태**: 컴포넌트가 있는 설명적 (`LOW_GAIN_LP`, `HIGH_GAIN`)
- **변수 이름**: 단위가 있는 설명적 (`power_mw`, `ber`, `gain_db`)

### 코드 구성

- **관심사 분리**:
  - 신호 생성을 처리와 분리
  - 전용 모듈에 전력 모델 격리
  - 별도 파일에 비교 로직

- **모듈식 컴포넌트**: 각 주요 하위 시스템(FSM, 캐리어 센싱, BER, 전력)은 자체 파일에

- **유틸리티 추출**: 공통 함수(플로팅, 데이터 수집)는 simulation_utils.py에

---

## 7. 테스트 접근 방식

### 테스트 기능 (제한적; 주로 시뮬레이션 기반)

**단위 수준 자체 테스트** (모듈 내):
- `agc_fsm.py`: 끝에 `test_agc_fsm()` 함수
  - 다양한 캐리어 센싱 시나리오에 대한 상태 전환 테스트
  - 출력 통계 검증

**통합 테스트** (시뮬레이션을 통해):
- `main_agc_system.py`: 전체 시스템 실행 가능
- `optimize_gains.py`: 최적 구성을 찾기 위해 3개 모델 모두 실행
- 수동 검증: 출력 그래프를 예상 동작과 비교

### 현재 테스트 관찰

- **pytest 프레임워크 없음**: print 문 및 수동 검증에 의존
- **단위 테스트 파일 없음**: 모든 테스트가 모듈에 포함되거나 main()을 통해 실행
- **CI/CD 구성 없음**: 단일 파일 실행 모델

### 권장 테스트 개선 사항

1. 다음을 위한 단위 테스트가 있는 `tests/` 디렉토리 생성:
   - ADC 양자화 정확도
   - FSM 상태 전환 로직
   - BER 계산 정확성

2. 일반적인 테스트 시나리오를 위한 pytest fixture 구현

3. 골든 신호 검증 추가 (사전 계산된 참조 값)

---

## 8. 구성 및 설정 요구 사항

### 설치 및 종속성

```bash
# Python 3.7+ 필요 (타입 힌트, enum)
pip install numpy scipy matplotlib
```

### 구성 매개변수 (config.py)

**조정 가능한 설정**:

1. **신호/채널 매개변수**:
   - `SAMPLING_RATE` (기본값: 20e6 Hz)
   - `SYMBOL_RATE` (기본값: 1e6 Hz)
   - `DEFAULT_SNR_DB` (기본값: 10)
   - `NOISE_POWER` (기본값: 0.1)

2. **이득 설정** (GAIN_LEVELS):
   ```python
   GAIN_LEVELS = {
       "LOW_GAIN_LP": 10,      # dB
       "LOW_GAIN_HP": 25,      # dB
       "MEDIUM_GAIN": 35,      # dB
       "HIGH_GAIN": 40,        # dB
   }
   ```

3. **트래픽별 ADC 해상도**:
   ```python
   TRAFFIC_ADC_RESOLUTION = {
       "wake_up": 3,
       "sensor":  4,
       "voice":   8,
       "video":   10
   }
   ```

4. **캐리어 센싱 임계값** (상태별):
   - 포화 임계값 (ADC 카운트)
   - 에너지 임계값 (dBm)
   - 상관 임계값 (0.0-1.0)

5. **디지털 연산 상수**:
   - `K_ADD_PER_SAMPLE`: 덧셈에 대한 스케일링 계수
   - `K_MUL_PER_SAMPLE`: 곱셈에 대한 스케일링 계수

6. **표시/디버그 옵션**:
   - `DEBUG_MODE`: 자세한 로깅 활성화
   - `PLOT_RESULTS`: 그래프 생성
   - `SAVE_INTERMEDIATE_RESULTS`: 중간 데이터 저장

### 시스템 실행

**기본 시뮬레이션**:
```bash
python main_agc_system.py
```

**예상 출력**:
- 콘솔: 진행 메시지, 메트릭 요약
- 파일: `metrics_energy.png`, `metrics_accuracy.png`, `metrics_latency.png`

**비교 시뮬레이션** (대안):
```bash
python agc_comparison.py  # (현재 main_agc_system.py에서 호출됨)
```

**이득 최적화**:
```bash
python optimize_gains.py
```

---

## 9. 데이터 흐름 및 신호 처리 세부 사항

### 신호 표현

**시스템 전체**에서 신호는 **복소수 numpy 배열** (I+jQ)로 표현됩니다:
- 기저대역 표현 (반송파 주파수 없음)
- 전체 신호 정보를 위한 복소수 값
- 20 MHz 샘플링 레이트에서 처리

### 일반적인 신호 레벨

| 단계 | 값 범위 | 목적 |
|------|---------|------|
| STF/LTF 비트 | {0, 1} | 이진 전송 |
| BPSK 심볼 | {-1+0j, +1+0j} | 변조 |
| 업샘플링된 신호 | ±1.0 (정규화) | 기저대역 파형 |
| RF 이득 후 | ±10-100x | 증폭 |
| ADC 후 (3비트) | [-4, 3] | 양자화 |
| ADC 후 (10비트) | [-512, 511] | 양자화 |
| 전력 (dB) | -100 ~ +20 dBm | 로그 스케일 |
| BER | 0.0 ~ 1.0 | 정규화된 오류율 |

### 양자화 효과

- **3비트 ADC**: 거친 양자화, 정보 손실, 하지만 저전력
- **10비트 ADC**: 미세 양자화, 높은 충실도, 하지만 고전력

시스템은 이 트레이드오프를 활용: 저속 wake-up 신호에는 3비트, 고대역폭 비디오에는 10비트 사용.

---

## 10. 주요 알고리즘 및 공식

### 이득 계산 (dB ↔ 선형)
```
gain_linear = 10^(gain_db / 20)
gain_db = 20 * log10(gain_linear)
```

### 비트 오류에서 BER
```
BER = (비트 오류 수) / (수신한 총 비트)
하드 결정: demodulated_bit = 1 if real(received) > 0 else 0
```

### 신호 전력
```
power_linear = mean(|signal|²)
power_db = 10 * log10(power_linear)
```

### SNR 관계
```
snr_linear = 10^(snr_db / 10)
noise_power = signal_power / snr_linear
```

### ADC 양자화 스텝
```
step_size = (2 * vref) / (2^bits)
quantized = round(signal / step) * step
```

### FSM 임계값 (캐리어 센싱)
```
saturation: |real| >= threshold OR |imag| >= threshold
energy: power_db > threshold_db
correlation: max_correlation > threshold (0.6-0.85)
```

### 디지털 에너지 (pJ)
```
energy = (num_adds * power_per_add) + (num_mults * power_per_mult)
         × area_scaling_factor
```

---

## 11. 시스템 제한 및 설계 선택

### 시뮬레이션을 위한 단순화

1. **실제 반송파 주파수 없음**: 기저대역만 (완벽한 하향 변환 가정)
2. **이상적인 채널**: AWGN만, 페이딩/간섭 없음
3. **단순 이득 피드백**: 피크 기반, 정교한 AGC 루프 아님
4. **선형 RF 모델**: 압축, 비선형성 또는 위상 왜곡 없음
5. **이상화된 캐리어 센싱**: 임계값 사전 구성, 적응형 임계값 없음
6. **유한 패킷**: 1 KB 페이로드로 제한 (스트리밍 없음)

### 가정

- 클럭 동기화가 완벽함
- 채널 추정이 필요하지 않음 (훈련 필드로 충분)
- 신호 필드 디코딩이 시뮬레이션 모드에서 결정적
- 전력 소비가 상태 종속만 (부하 종속 아님)
- 수신기가 항상 정상 모드에서 작동 (저전력 절전 없음)

### 적응형 선택 로직 제한

- ADC 해상도 선택이 신호 필드 추출 **후**에 발생
- 이는 초기 처리가 기본 3비트를 사용한 다음 전환할 수 있음을 의미
- 더 최적의 접근 방식: 신호 필드 표시를 더 일찍 사용 (향후 작업)

---

## 12. 파일 요약

| 파일 | 줄 수 | 목적 |
|------|------|------|
| main_agc_system.py | 713 | 메인 AGC 시스템 + 비교 진입점 |
| agc_fsm.py | 268 | 이득/ADC 제어를 위한 유한 상태 기계 |
| carrier_sensing.py | 394 | 패킷 검출 (포화, 에너지, 상관) |
| signal_generator.py | 228 | PHY 패킷 생성 (BPSK 변조) |
| ber_calculator.py | 250 | 비트 오류율 측정 |
| power_measurement.py | 159 | 전력/에너지 집계 |
| analog_power_base.py | 100 | IC 전력 모델 (MAX2829/MAX2830) |
| rf_paths.py | 179 | RF 프론트엔드 시뮬레이션 (LNA, mixer, VGA, LPF) |
| adc.py | 93 | ADC 양자화 (3비트 및 10비트) |
| digital.py | 80 | 디지털 회로 면적 모델 |
| config.py | 93 | 중앙 집중식 구성 매개변수 |
| simulation_utils.py | 422 | 유틸리티 (데이터 수집, 플로팅, 트래픽 흐름) |
| agc_comparison.py | 726 | 3개 AGC 모델 비교 |
| optimize_gains.py | 145 | 이득 최적화 유틸리티 |
| README.md | - | 프로젝트 개요 |

---

## 13. 사용 예제

### 기본 단일 시뮬레이션
```python
from main_agc_system import AgcSystem
from signal_generator import SignalGenerator

# 시스템 생성
agc = AgcSystem()
sg = SignalGenerator()

# 패킷 생성 및 처리
packet = sg.create_complete_packet("video")
result = agc.process_packet(packet, channel_snr_db=15)

print(f"BER: {result['final_ber']['ber']:.6f}")
print(f"아날로그 에너지: {result['analog_power']['total_energy_mj']:.2f} mJ")
print(f"디지털 에너지: {result['digital_computation']['total_energy_pj']:.2f} pJ")
print(f"최종 상태: {result['final_fsm_state']}")
print(f"최종 이득: {result['final_gain_db']} dB")
```

### 전체 시뮬레이션 실행
```python
from main_agc_system import AgcSystem

agc = AgcSystem(use_correlation_detection=True)  # 적응형

# 전체 시뮬레이션 실행
sim_result = agc.run_simulation(
    traffic_types=["sensor", "voice", "video"],
    snr_range_db=[5, 10, 15, 20],
    packets_per_scenario=10
)

print(f"총 패킷: {sim_result['overall_statistics']['total_packets']}")
print(f"전체 BER: {sim_result['overall_statistics']['overall_average_ber']:.6f}")
```

### 비교 모드
```python
if __name__ == "__main__":
    # main_agc_system.py가 수행하는 작업:
    # 1. 3개 모델 실행 (저전력, 고성능, 적응형)
    # 2. 각각에 대한 메트릭 수집
    # 3. 비교 그래프 생성
    exec(open("main_agc_system.py").read())
```

---

## 14. AI 어시스턴트를 위한 주요 통찰

1. **주요 혁신**: 적응형 AGC는 감지된 트래픽 유형에 따라 ADC 해상도를 동적으로 선택하여, 고정 접근 방식 대비 패킷별로 전력/성능 트레이드오프 수행

2. **신호 처리 기반**: 표준 DSP 기법 사용 (BPSK, 상관을 통한 정합 필터링, 하드 결정 검출)

3. **하드웨어-소프트웨어 협업 설계**: 아날로그 RF 프론트엔드(전력 소비)와 디지털 백엔드(면적 + 연산 수) 모두 모델링

4. **비교 평가**: 공정한 비교를 위해 동일한 트래픽/채널 조건에서 3가지 경쟁 접근 방식 평가

5. **패킷 구조**: 표준 무선 프리앰블 구조 사용 (검출용 STF, 채널용 LTF, 메타데이터용 신호 필드)

6. **명시적으로 모델링된 트레이드오프**:
   - 3비트 ADC: 낮은 전력, 낮은 정확도
   - 10비트 ADC: 높은 전력, 높은 정확도
   - 적응형: 콘텐츠 유형에 따라 선택

7. **에너지 모델링**: 상태 종속 아날로그 전력(IC 모델) + 연산 수 디지털 에너지(면적 기반 스케일링) 결합

8. **실용적 제약**:
   - 실제 시스템은 레일리 페이딩, 간섭 필요
   - AGC 루프는 이산 상태가 아닌 연속적
   - 신호 필드 디코딩은 확률적

---

## 15. 시스템 확장

### 잠재적 개선 사항

1. **채널 모델**: 레일리 페이딩, 다중 경로 전파 구현
2. **고급 캐리어 센싱**: 주파수 영역 분석, 순환 정상성 검출
3. **머신 러닝**: 최적 ADC 해상도 예측을 위한 신경망 훈련
4. **하드웨어 구현**: Python 모델에서 C/HDL 생성
5. **실시간 최적화**: 실제 AGC 피드백 루프 구현 (현재는 피크 기반만)
6. **추가 메트릭**: 위상 오류, 이득 편차, 정착 시간
7. **다중 사용자 시나리오**: 간섭 모델링 및 완화

---

## 연락처/저자

이것은 다중 트래픽 무선 수신기의 AGC 설계 트레이드오프에 초점을 맞춘 학술/연구 프로젝트입니다. 모든 컴포넌트는 시뮬레이션 및 교육 목적에 적합한 자체 포함된 Python 구현입니다.
