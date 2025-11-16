# 실제 AGC 동작 구현 (Real AGC Operation)

## 개요

교수님 피드백에 따라 시뮬레이션을 **실제 AGC 시스템처럼 동작**하도록 수정했습니다.

---

## 주요 변경 사항

### 1. 트래픽 타입 단순화

**이전**:
```python
sensor, voice, video (4가지 + wake_up)
```

**개선** (교수님 피드백):
```python
lowpowersignal, highperformancesignal (2가지 + wake_up)
```

**이유**:
- 신호는 저전력과 고성능 두 가지로 구분하는 것이 명확
- FSM 상태와 트래픽 타입이 1:1 매핑되지 않아도 됨
- Signal Field는 3가지만 필요: wake_up, lowpowersignal, highperformancesignal

---

### 2. 실제 AGC 동작으로 수정 (가장 중요!)

#### ❌ **이전 문제점**: 전체 신호를 한 번에 처리

```python
# 이전 코드 (잘못됨!)
received_signal = self.process_rf_signal(noisy_signal)  # 전체 신호를 한 번에 RF 증폭 + ADC
for block in received_signal:  # 이미 처리된 신호를 블록별로 분석만 함
    cs_result = carrier_sensing(block)
    gain_feedback()  # 하지만 gain 변경이 의미 없음 (이미 전체 처리 완료)
```

**문제**:
- 실제 AGC는 이렇게 동작하지 않음!
- 전체 신호를 한 번에 처리하면 gain 피드백이 무의미함
- Gain 조절이 다음 블록에 적용되지 않음

#### ✅ **개선**: 블록 단위로 실시간 처리

```python
# 개선된 코드 (실제 AGC!)
for each block in noisy_signal:  # 블록 단위로 순차 처리
    # 1. 현재 gain으로 RF 증폭
    amplified = process_rf_only(noisy_block)  # LNA + VGA

    # 2. ADC 양자화 (10비트 → 5 or 10비트 truncation)
    quantized = apply_adc(amplified)

    # 3. 신호 분석 (carrier sensing, BER 등)
    cs_result = carrier_sensing(quantized)

    # 4. Gain 피드백 계산
    if peak > 0.9:
        next_gain = current_gain - 1dB  # 다음 블록에 적용!
    elif peak < 0.25:
        next_gain = current_gain + 1dB  # 다음 블록에 적용!

    # 5. 다음 블록은 새로운 gain으로 증폭될 것!
```

---

### 3. RF 증폭과 ADC 양자화 분리

**이전**:
```python
def process_rf_signal(signal):
    amplified = rf_path.run(signal)  # RF 증폭
    return apply_adc(amplified)      # ADC 양자화
    # 문제: 두 개가 묶여 있어서 블록별 처리 불가
```

**개선**:
```python
def process_rf_only(signal):
    """RF 증폭만 수행 (ADC와 분리)"""
    amplified = rf_path.run(signal)  # LNA + VGA
    return amplified

def apply_adc_quantization(signal):
    """ADC 양자화만 수행"""
    quantized_10bit = adc.quantize(signal)  # 10-bit ADC
    truncated = truncate_to_bits(quantized_10bit, target_bits)  # 5 or 10-bit
    return truncated
```

**이유**:
- 실제 AGC에서는 RF와 ADC가 별도로 동작
- 블록 단위로 처리할 때 각 단계를 독립적으로 수행 가능
- Gain 변경 시 RF 증폭만 다시 수행하면 됨

---

## 실제 AGC 동작 흐름

```
수신 신호 (noisy_signal)
    │
    ▼
┌───────────────────────────────────┐
│  블록 단위 루프 (for each block)  │
└───────────────────────────────────┘
    │
    ├─ [1] 현재 블록 추출
    │   noisy_block = noisy_signal[idx:idx+block_size]
    │
    ├─ [2] RF 증폭 (현재 gain 사용)
    │   amplified_block = LNA(noisy_block, 20dB)
    │                    → VGA(amplified, current_gain-20dB)
    │
    ├─ [3] ADC 양자화
    │   quantized = ADC_10bit(amplified)
    │   truncated = truncate_to_bits(quantized, 5 or 10)
    │
    ├─ [4] Carrier Sensing
    │   cs_result = detect(truncated)
    │
    ├─ [5] Signal Field 디코딩 (필요시)
    │   traffic_type = decode_signal_field(received_signal)
    │   → lowpowersignal: 5-bit truncation
    │   → highperformancesignal: 10-bit (truncation 없음)
    │
    ├─ [6] FSM 상태 전환 (필요시)
    │   state_changed = fsm.process_indication(cs_result, traffic_type)
    │   if state_changed:
    │       new_gain = fsm.get_current_gain()
    │       (다음 블록에 적용됨!)
    │
    ├─ [7] Gain 피드백 (AGC의 핵심!)
    │   peak = max(abs(truncated))
    │   if peak > 0.9:
    │       next_gain = current_gain - 1dB  (Saturation 방지)
    │   elif peak < 0.25:
    │       next_gain = current_gain + 1dB  (SNR 향상)
    │
    │   fsm.set_gain(next_gain)  → 다음 블록에 적용!
    │
    ├─ [8] BER 계산 (STF 구간만)
    │   ber = calculate_ber(truncated, reference_stf)
    │
    └─ [9] 다음 블록으로 →
```

---

## 핵심 개선 포인트

### 1. 블록 단위 실시간 처리

**이전**: 전체 신호를 한 번에 처리 → Gain 피드백 무의미

**개선**: 각 블록을 순차 처리 → Gain 피드백이 다음 블록에 적용

### 2. Gain 피드백 루프

```python
# 실제 AGC의 피드백 루프
Block N:
  current_gain = 30 dB
  amplified = RF(signal, gain=30dB)
  quantized = ADC(amplified)
  peak = 0.95  (너무 큼!)
  next_gain = 29 dB  (1dB 감소)

Block N+1:
  current_gain = 29 dB  (←  피드백 적용!)
  amplified = RF(signal, gain=29dB)
  quantized = ADC(amplified)
  peak = 0.85  (적당함)
  next_gain = 29 dB  (유지)
```

### 3. 신호 경로의 실제성

```
안테나 수신
  ↓
AWGN 노이즈 추가 (채널)
  ↓
RF Frontend (아날로그)
  ├─ LNA (20 dB, 고정)
  ├─ Mixer (베이스밴드 가정)
  ├─ VGA (0~30 dB, 가변, AGC 피드백!)
  └─ LPF (IIR 필터)
  ↓
ADC (아날로그 → 디지털)
  ├─ 10-bit 양자화
  └─ Digital truncation (5 or 10-bit)
  ↓
디지털 처리
  ├─ Carrier Sensing
  ├─ Signal Field 디코딩
  ├─ BER 계산
  └─ Gain 피드백 계산 →  다음 블록에 적용!
```

---

## RF 증폭 실제 동작

### LNA (Low Noise Amplifier)
```python
def lna(x, gain_db):
    gain_linear = 10^(gain_db/20)  # dB → linear
    return x * gain_linear
```

**예**: gain=20dB → linear=10
- 입력: 0.1 V → 출력: 1.0 V

### VGA (Variable Gain Amplifier)
```python
def vga(x, gain_db):
    gain_linear = 10^(gain_db/20)
    return x * gain_linear
```

**AGC 피드백으로 가변**:
- gain_db = 0~30dB (피드백으로 조절)
- 신호가 크면 감소, 작으면 증가

### 전체 Gain
```
Total Gain = LNA (20dB) + VGA (0~30dB) = 20~50dB
```

---

## ADC 양자화 실제 동작

### 10-bit ADC
```python
# 1. 전압 클리핑
x_clipped = np.clip(x, -vref, vref)  # -1.0 ~ +1.0 V

# 2. 양자화 스텝 계산
step = 2*vref / 2^10 = 2.0 / 1024 ≈ 0.00195 V

# 3. 반올림
x_quantized = round(x_clipped / step) * step

# 예시:
입력: 0.123 V
양자화: round(0.123 / 0.00195) * 0.00195 = 0.12305 V
```

### Digital Truncation (5-bit)
```python
# 10-bit 정수: 0 ~ 1023
x_int_10bit = quantize_to_int(x)  # 예: 512

# 5-bit로 truncation (상위 5비트만 사용)
bit_shift = 10 - 5 = 5
x_int_5bit = x_int_10bit >> 5  # 512 >> 5 = 16 (5-bit 범위: 0~31)

# 다시 float로 변환
x_truncated = x_int_5bit * step_5bit  # step_5bit = 2.0 / 32
```

**효과**:
- 10-bit: 1024 레벨 (정밀)
- 5-bit: 32 레벨 (거칠음, 하지만 저전력)

---

## 검증

### 1. RF 증폭 검증
```python
input_signal = np.array([0.1])  # 0.1 V
gain_db = 20  # 20 dB

output = lna(input_signal, gain_db)
print(output)  # [1.0]  (0.1 × 10 = 1.0 V) ✓
```

### 2. ADC 양자화 검증
```python
input_signal = np.array([0.5])  # 0.5 V
adc = ADC10bit(vref=1.0)

output = adc.quantize(input_signal)
print(output)  # [0.5]  (양자화 오차 미미) ✓
```

### 3. Gain 피드백 검증
```python
# 블록 1
gain_before = 30
peak = 0.95  # 너무 큼!
gain_after = 29  # -1 dB

# 블록 2 (새 gain 적용)
assert current_gain == 29  # ✓ 피드백 적용됨!
```

---

## 결론

이제 시뮬레이션이 **실제 AGC 시스템처럼 동작**합니다:

1. ✅ **블록 단위 처리**: 전체 신호를 한 번에 처리하지 않음
2. ✅ **Gain 피드백**: 현재 블록의 peak를 측정하여 다음 블록 gain 조절
3. ✅ **RF/ADC 분리**: 각 단계를 독립적으로 수행
4. ✅ **실제 증폭**: LNA, VGA로 신호를 실제로 증폭함
5. ✅ **실제 양자화**: ADC로 신호를 실제로 양자화함
6. ✅ **트래픽 단순화**: lowpowersignal / highperformancesignal

**교수님 요구사항 모두 반영 완료!**
