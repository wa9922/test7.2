# AGC 시스템 구성도 및 실험 환경 설명

## 1. 전체 시스템 블록 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          INPUT: Wireless Packet                              │
│                    (STF + LTF + Signal Field + Payload)                      │
└─────────────────────────────┬───────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────────┐
                    │   Channel (AWGN)    │
                    │   SNR 조정 가능     │
                    │   (5, 10, 15, 20 dB)│
                    └─────────┬───────────┘
                              │ Noisy Signal
                              ▼
        ╔═════════════════════════════════════════════════════════════╗
        ║              AGC FEEDBACK LOOP (STF 구간에서만)              ║
        ╠═════════════════════════════════════════════════════════════╣
        ║                                                             ║
        ║  ┌──────────────────────────────────────────────┐          ║
        ║  │ 1. STF 신호 추출 (128 bits, 2560 samples)   │          ║
        ║  └────────────────┬─────────────────────────────┘          ║
        ║                   │                                         ║
        ║                   ▼                                         ║
        ║  ┌───────────────────────────────────────────────────┐     ║
        ║  │ 2. RF Path (UnifiedRFPath)                        │     ║
        ║  │    - LNA: 20 dB (고정)                            │     ║
        ║  │    - Mixer                                        │     ║
        ║  │    - VGA: 0~30 dB (가변)                         │◄────╫─┐
        ║  │    - LPF (Low-Pass Filter)                        │     ║ │
        ║  │    Total Gain = current_gain_db (10~50 dB)       │     ║ │
        ║  └────────────────┬──────────────────────────────────┘     ║ │
        ║                   │ Amplified STF                          ║ │
        ║                   ▼                                         ║ │
        ║  ┌─────────────────────────────────────────┐               ║ │
        ║  │ 3. Power Measurement                    │               ║ │
        ║  │    P_measured = 10*log10(mean(|STF|²))  │               ║ │
        ║  │    (단위: dBFS)                         │               ║ │
        ║  └────────────────┬──────────────────────────┘             ║ │
        ║                   │ P_measured                              ║ │
        ║                   ▼                                         ║ │
        ║  ┌──────────────────────────────────────────────┐          ║ │
        ║  │ 4. Gain Adjustment Logic                     │          ║ │
        ║  │                                              │          ║ │
        ║  │  P_target = -3.0 dBFS  (목표 전력)          │          ║ │
        ║  │  P_error = P_target - P_measured            │          ║ │
        ║  │                                              │          ║ │
        ║  │  if |P_error| > tolerance (0.5 dB):         │          ║ │
        ║  │      gain_adj = P_error (최대 ±5 dB step)   │          ║ │
        ║  │      new_gain = current_gain + gain_adj     │          ║ │
        ║  │  else:                                       │          ║ │
        ║  │      new_gain = current_gain (변경 없음)     │          ║ │
        ║  │                                              │          ║ │
        ║  │  new_gain = clip(new_gain, 10, 50) dB       │          ║ │
        ║  └────────────────┬───────────────────────────────┘        ║ │
        ║                   │ new_gain_db                             ║ │
        ║                   └─────────────────────────────────────────╫─┘
        ║                                                 Feedback    ║
        ╚═════════════════════════════════════════════════════════════╝
                              │
                              │ Final Gain 결정 (STF에서 한 번만)
                              ▼
        ┌──────────────────────────────────────────────────────┐
        │  전체 패킷 처리 (결정된 gain으로 한 번에 증폭)      │
        └────────────────┬─────────────────────────────────────┘
                         │ Amplified Full Packet
                         ▼
        ┌───────────────────────────────────────────────────┐
        │  ADC 10-bit Quantization (항상)                  │
        │  - Resolution: 1024 levels                        │
        │  - Range: -Vref ~ +Vref                           │
        │  - Step: 2*Vref / 1024                            │
        └────────────────┬──────────────────────────────────┘
                         │ Quantized Signal (10-bit)
                         ▼
        ┌───────────────────────────────────────────────────┐
        │  Digital Truncation (트래픽 타입에 따라)          │
        │                                                   │
        │  Signal Field Decoding:                          │
        │  - "01" → lowpowersignal → 5-bit truncation      │
        │  - "10" → highperformancesignal → 10-bit (유지)  │
        │                                                   │
        │  Truncation 방법 (5-bit 예시):                   │
        │  - 10-bit 정수 >> 5 (하위 5비트 버림)            │
        │  - 결과 << 5 (복원)                              │
        │  - 실질적으로 32 levels 사용                     │
        └────────────────┬──────────────────────────────────┘
                         │ Final Digital Signal
                         ▼
        ┌──────────────────────────────────────────┐
        │  BER Calculation (STF 구간)             │
        │  - Hard-decision demodulation            │
        │  - XOR with reference STF                │
        │  - BER = errors / total_bits             │
        └────────────────┬─────────────────────────┘
                         │
                         ▼
        ┌──────────────────────────────────────────┐
        │  OUTPUT: Performance Metrics             │
        │  - BER                                   │
        │  - Final Gain (dB)                       │
        │  - Analog Energy (mJ)                    │
        │  - Digital Energy (pJ)                   │
        │  - Digital Bits Used (5 or 10)           │
        └──────────────────────────────────────────┘
```

---

## 2. AGC 피드백 루프 상세 동작 원리

### 2.1 피드백 루프 동작 시점

**중요**: AGC 피드백은 **STF (Short Training Field) 구간에서만** 동작합니다.

- **STF**: 패킷의 첫 128 bits (2560 samples @ 20MHz)
- **LTF**: Gain 조정 없음 (채널 추정 용도로만 사용)
- **Signal Field + Payload**: 확정된 gain으로 처리

### 2.2 피드백 메커니즘

```python
# 1단계: STF 전력 측정
stf_signal = noisy_signal[0:2560]  # STF 추출
stf_amplified = rf_path.process(stf_signal, current_gain_db)  # 현재 gain으로 증폭
P_measured = 10 * log10(mean(|stf_amplified|²))  # dBFS 단위

# 2단계: 목표 전력과 비교
P_target = -3.0  # dBFS (ADC full-scale 대비 -3dB)
P_error = P_target - P_measured

# 3단계: Gain 조정 결정
tolerance = 0.5  # dB
coarse_step = 5.0  # dB (최대 조정량)

if |P_error| > tolerance:
    gain_adjustment = P_error
    # Step size 제한
    if |gain_adjustment| > coarse_step:
        gain_adjustment = ±coarse_step

    new_gain_db = current_gain_db + gain_adjustment
else:
    new_gain_db = current_gain_db  # 허용 범위 내, 조정 안 함

# 4단계: Gain 범위 제한
new_gain_db = clip(new_gain_db, 10.0, 50.0)  # dB

# 5단계: RF Path에 새 gain 적용
rf_path.set_total_gain(new_gain_db)
current_gain_db = new_gain_db
```

---

## 3. 큰 신호 vs 작은 신호 처리 예시

### 3.1 큰 신호가 들어온 경우 (High Power Signal)

**시나리오**: 송신기가 가까이 있거나 채널 상태가 좋은 경우

```
초기 상태:
- current_gain = 30 dB
- 채널 SNR = 20 dB (높음)

Step 1: STF 증폭
- Input STF power: -5 dBFS (큰 신호)
- Amplified: -5 + 30 = +25 dBFS (포화 위험!)

Step 2: 전력 측정
- P_measured = +25 dBFS (목표보다 훨씬 큼)

Step 3: Gain 조정
- P_target = -3 dBFS
- P_error = -3 - 25 = -28 dB (큼)
- gain_adjustment = -28 dB
- BUT: coarse_step = 5 dB 제한
- gain_adjustment = -5 dB (감소)

Step 4: 새로운 Gain 적용
- new_gain = 30 - 5 = 25 dB
- 다음 iteration에서 계속 감소 가능

결과:
✅ AGC가 큰 신호를 감지하고 gain을 줄여서 ADC 포화 방지
✅ 최종적으로 P_measured ≈ -3 dBFS로 수렴
```

### 3.2 작은 신호가 들어온 경우 (Low Power Signal)

**시나리오**: 송신기가 멀거나 채널 상태가 나쁜 경우

```
초기 상태:
- current_gain = 30 dB
- 채널 SNR = 5 dB (낮음)

Step 1: STF 증폭
- Input STF power: -35 dBFS (작은 신호)
- Amplified: -35 + 30 = -5 dBFS (여전히 낮음)

Step 2: 전력 측정
- P_measured = -5 dBFS (목표보다 낮음)

Step 3: Gain 조정
- P_target = -3 dBFS
- P_error = -3 - (-5) = +2 dB (양수)
- gain_adjustment = +2 dB (증가)

Step 4: 새로운 Gain 적용
- new_gain = 30 + 2 = 32 dB

결과:
✅ AGC가 작은 신호를 감지하고 gain을 올려서 SNR 향상
✅ 최종적으로 P_measured ≈ -3 dBFS로 수렴
```

---

## 4. 실험 환경 세부 사항

### 4.1 실험 파라미터

| 항목 | 값 | 설명 |
|------|-----|------|
| **채널 SNR** | 5, 10, 15, 20 dB | 4가지 채널 조건 |
| **트래픽 타입** | lowpowersignal, highperformancesignal | 2가지 |
| **패킷 수** | 20 per scenario | 총 160 packets (4 SNR × 2 traffic × 20) |
| **초기 Gain** | 30 dB | 중간값 |
| **Gain 범위** | 10 ~ 50 dB | 40 dB 동적 범위 |
| **목표 전력** | -3 dBFS | ADC full-scale 대비 |
| **Coarse Step** | 5 dB | 최대 조정량 |
| **Tolerance** | 0.5 dB | 허용 오차 |

### 4.2 AGC 동작 타이밍

```
Packet Timeline:
┌──────┬──────┬────────────┬──────────────────┐
│ STF  │ LTF  │Signal Field│    Payload       │
│128bit│64bit │  48 bit    │   1024 bit       │
└──────┴──────┴────────────┴──────────────────┘
   ↑        ↑         ↑              ↑
   │        │         │              │
 AGC ON   AGC OFF  Digital Bits  Process with
 (측정 +   (고정)    Selection    Final Gain
  조정)                           + Final Bits
```

**Gain 조정**: STF에서 **1회**만 수행
**Digital Bits 조정**: Signal Field 디코딩 후 **1회**만 수행

### 4.3 3가지 AGC 모델 비교

#### Model 1: **Fixed Low-Power AGC**
```
Digital Bits: 5-bit (고정)
Gain: STF에서 AGC로 자동 조정 (10~50 dB)

특징:
- 낮은 디지털 연산량
- 낮은 BER 정확도
- 모든 트래픽에 5-bit 사용
```

#### Model 2: **Fixed High-Performance AGC**
```
Digital Bits: 10-bit (고정)
Gain: STF에서 AGC로 자동 조정 (10~50 dB)

특징:
- 높은 디지털 연산량
- 높은 BER 정확도
- 모든 트래픽에 10-bit 사용
```

#### Model 3: **Adaptive AGC** (제안)
```
Digital Bits: 트래픽 타입에 따라 적응
  - lowpowersignal → 5-bit
  - highperformancesignal → 10-bit
Gain: STF에서 AGC로 자동 조정 (10~50 dB)

특징:
- 적응형 디지털 연산량
- 트래픽별 최적 정확도
- 에너지 효율성 향상
```

---

## 5. 실험 결과 검증 방법

### 5.1 Gain 조정 확인

각 패킷 처리 후 다음 정보를 수집:

```python
result = {
    'initial_gain_db': 30.0,           # 시작 gain
    'stf_power_db': -5.2,              # 측정된 STF 전력
    'final_gain_db': 32.1,             # 조정된 gain
    'gain_adjustment': +2.1,           # 변화량
    'saturation_detected': False,       # 포화 여부
}
```

### 5.2 디지털 Bits 선택 확인

```python
result = {
    'traffic_type': 'lowpowersignal',
    'initial_digital_bits': 5,
    'signal_field_indication': '01',    # 디코딩 결과
    'final_digital_bits': 5,            # 최종 선택
    'bits_changed': False,
}
```

### 5.3 에너지 측정 확인

```python
result = {
    'analog_energy_mj': 0.4949,        # 항상 동일 (MAX2829)
    'digital_energy_pj': 19.2,         # 5-bit 사용 시
    'total_energy_mj': 0.4949,         # analog dominant
    'digital_operations': {
        'additions': 128000,
        'multiplications': 3200,
    }
}
```

---

## 6. 핵심 검증 포인트

### ✅ 1. AGC가 큰 신호를 올바르게 처리하는가?

**검증 방법**:
- 높은 SNR (20 dB) 시나리오 확인
- `stf_power_db`가 높게 측정되는지
- `gain_adjustment`가 음수인지 (감소)
- 최종 `stf_power_db`가 `-3 dBFS` 근처로 수렴하는지

**예상 결과**:
```
SNR=20dB, Initial Gain=30dB
→ STF Power = +15 dBFS (매우 높음)
→ Gain Adjustment = -5 dB (최대 감소)
→ New Gain = 25 dB
→ 다음 패킷에서 계속 감소하여 최종 ~20 dB 수렴
```

### ✅ 2. AGC가 작은 신호를 올바르게 처리하는가?

**검증 방법**:
- 낮은 SNR (5 dB) 시나리오 확인
- `stf_power_db`가 낮게 측정되는지
- `gain_adjustment`가 양수인지 (증가)
- 최종 `stf_power_db`가 `-3 dBFS` 근처로 수렴하는지

**예상 결과**:
```
SNR=5dB, Initial Gain=30dB
→ STF Power = -25 dBFS (매우 낮음)
→ Gain Adjustment = +5 dB (최대 증가)
→ New Gain = 35 dB
→ 다음 패킷에서 계속 증가하여 최종 ~45 dB 수렴
```

### ✅ 3. Gain이 실험에 어떻게 반영되는가?

**반영 경로**:

1. **STF 측정** → `measure_signal_power_db(stf_amplified)`
2. **Gain 조정** → `adjust_gain_based_on_power(P_measured, P_target, step)`
3. **RF Path 업데이트** → `rf_path.set_total_gain(new_gain_db)`
4. **전체 패킷 처리** → `process_rf_only(full_packet)` with new gain
5. **메트릭 수집** → `final_gain_db` 기록

**검증 파일**:
- `metrics_*.png`: Gain history 그래프
- Simulation log: Gain adjustment 추적

---

## 7. 결론

### AGC 피드백 루프 요약

1. **측정**: STF 전력 측정 (`P_measured`)
2. **비교**: 목표 전력과 차이 계산 (`P_error = P_target - P_measured`)
3. **조정**: Gain 증감 결정 (`gain_adj = P_error`, ±5 dB step 제한)
4. **적용**: RF Path에 새 gain 설정
5. **수렴**: 반복을 통해 `-3 dBFS` 목표로 수렴

### 큰 신호 처리

- **검출**: `P_measured > P_target` (예: +25 dBFS > -3 dBFS)
- **동작**: Gain 감소 (예: 30 dB → 25 dB)
- **효과**: ADC 포화 방지, 양자화 품질 유지

### 작은 신호 처리

- **검출**: `P_measured < P_target` (예: -25 dBFS < -3 dBFS)
- **동작**: Gain 증가 (예: 30 dB → 35 dB)
- **효과**: SNR 향상, 노이즈 대비 신호 증폭

### 실험 검증 가능성

✅ **Gain 변화 추적**: 각 패킷의 `gain_history` 기록
✅ **전력 측정 확인**: `stf_power_db` 값 확인
✅ **포화 방지**: `saturation_detected` 플래그
✅ **에너지 효율성**: Adaptive가 Fixed 대비 개선

---

**작성일**: 2025-11-28
**버전**: 1.0
**목적**: 교수님 발표 자료 (시스템 구성도 + 실험 환경 설명)
