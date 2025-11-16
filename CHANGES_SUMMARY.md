# AGC 시스템 수정 사항 요약

## 교수님 피드백 반영

### 주요 변경 사항

## 1. 3비트 → 5비트 변경 (Quantization Noise 개선)

**이유**: 3비트는 quantization noise가 너무 크다는 교수님 피드백

**변경 파일**: `config.py`
```python
# 변경 전
DIGITAL_TRUNCATION_BITS = {
    "wake_up": 3,
    "sensor":  4,
}

# 변경 후
DIGITAL_TRUNCATION_BITS = {
    "wake_up": 5,  # ✓ 5비트로 변경
    "sensor":  5,  # ✓ 5비트로 변경
}
```

## 2. 아날로그 부분 통일

**이유**: 아날로그는 항상 동일하게 동작, 전력 비교는 디지털만

**변경 파일**: `rf_paths.py`
- **추가**: `UnifiedRFPath` 클래스
  - 항상 같은 LNA, VGA, LPF 사용
  - Gain만 피드백으로 조절
  - 전력 소비 항상 동일

```python
class UnifiedRFPath:
    """
    통일된 RF 프론트엔드:
    [LNA] → [Mixer] → [VGA] → [LPF]
     ↑                ↑
     └────────────────┴─── Gain Feedback
    """
```

## 3. ADC 단일화 + 디지털 Truncation

**이유**: ADC는 항상 10비트로 동작, 디지털 단에서 5비트/10비트로 선택

**변경 파일**: `adc.py`
- **추가**: `ADC5bit` 클래스
- **추가**: `truncate_to_bits()` 메서드

```python
def truncate_to_bits(self, x, target_bits):
    """
    10비트 신호를 5비트로 잘라내기
    예: 1010110011 (683) → 10101 (21)
    """
```

## 4. 디지털 연산량 계산

**변경 파일**: `digital.py`
- **추가**: `calculate_operations_for_bits()` 메서드
- 5비트 사용: 적은 adder/multiplier
- 10비트 사용: 많은 adder/multiplier

## 5. 시스템 구조

### 변경 전 (잘못됨)
```
아날로그 선택:
├─ LowPowerPath + ADC3bit
└─ HighPerfPath + ADC10bit
```

### 변경 후 (올바름)
```
아날로그 (통일):
UnifiedRFPath + ADC10bit (항상 동일)
        ↓
디지털 (선택):
├─ 5비트 truncation (저전력)
└─ 10비트 사용 (고성능)
```

## 6. 3가지 비교 모델

| 모델 | 아날로그 | ADC | 디지털 비트 |
|------|---------|-----|-----------|
| **종래1 (저전력)** | UnifiedRFPath | 10비트 | **항상 5비트** |
| **종래2 (고성능)** | UnifiedRFPath | 10비트 | **항상 10비트** |
| **제안 (적응형)** | UnifiedRFPath | 10비트 | **5비트 또는 10비트** |

## 7. BPSK 신호 처리 흐름 (검증됨 ✓)

```
1. 비트 생성 (uint8)
   ↓
2. BPSK 변조 (complex64)
   비트 0 → -1+0j
   비트 1 → +1+0j
   ↓
3. 업샘플링 (20 samples/symbol)
   ↓
4. AWGN 채널 (complex64에 노이즈 추가)
   ↓
5. RF 증폭 (UnifiedRFPath)
   [LNA] → [Mixer] → [VGA] → [LPF]
   ↓
6. ADC 양자화 (10비트, 1024 레벨)
   complex64 → float32
   ↓
7. 디지털 Truncation
   ├─ 5비트: 32 레벨만 사용
   └─ 10비트: 1024 레벨 사용
   ↓
8. BPSK 복조 (hard decision)
   real > 0 → 1
   real ≤ 0 → 0
   ↓
9. BER 계산
   원본 비트와 비교
```

## 8. GNURadio 호환성 (유지 ✓)

모든 데이터 타입이 GNURadio 표준 준수:
- **Bits**: `uint8`
- **Complex**: `complex64` (float32 × 2)
- **Float**: `float32`
- **ADC Integer**: `int16`

## 다음 단계

⚠️ **main_agc_system.py 전면 수정 필요**
- ADC 하나만 사용
- RF path 하나만 사용
- 디지털 truncation 로직 추가
- 3가지 모델 모두 동일한 아날로그 사용

⚠️ **agc_comparison.py 수정 필요**
- FixedLowPowerAGC: 항상 5비트 truncation
- FixedHighPerformanceAGC: 항상 10비트 사용
- AdaptiveAGC: 트래픽 따라 5/10비트 선택

## 파일 수정 현황

- ✅ config.py (완료)
- ✅ adc.py (완료)
- ✅ digital.py (완료)
- ✅ rf_paths.py (완료)
- ⏳ main_agc_system.py (진행중 - 매우 복잡)
- ⏳ agc_comparison.py (대기)
- ✅ BPSK 신호 처리 (검증 완료)
