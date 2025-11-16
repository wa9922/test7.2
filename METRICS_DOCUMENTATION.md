# AGC 시스템 비교 메트릭 문서

## 개요

이 문서는 AGC (Automatic Gain Control) 시스템의 3가지 모델을 비교하기 위한 메트릭과 그래프를 설명합니다.

## 비교 모델

1. **Low-Power Fixed (5-bit)**: 항상 5비트 digital truncation 사용
2. **High-Perf Fixed (10-bit)**: 항상 10비트 전부 사용
3. **Adaptive (Proposed)**: 트래픽 타입에 따라 5/10비트 적응적 선택

## 측정 메트릭

### 1. 기본 메트릭 (기존)

#### 1.1 에너지 (Energy)
- **Analog Energy**: 아날로그 프론트엔드 에너지 소비 (mJ)
  - 모든 모델 동일 (UnifiedRFPath 사용)
- **Digital Energy**: 디지털 처리 에너지 소비 (pJ)
  - 5비트 < Adaptive < 10비트 (비트 수에 비례)

#### 1.2 정확도 (Accuracy)
- **Average BER**: 평균 비트 오류율
  - 낮을수록 좋음
  - 5비트 > Adaptive > 10비트 (오류)

#### 1.3 지연 (Latency)
- **Average Latency**: 평균 패킷 처리 지연 (ms)
  - **개선됨**: 연산 복잡도 기반 계산
  - 계산식: `latency = (adds × 0.001ms) + (mults × 0.005ms) + overhead`
  - 5비트 < Adaptive < 10비트 (연산량에 비례)

---

### 2. 연산량 메트릭 (신규 ⭐)

#### 2.1 총 연산량 (Total Operations)
- **Total Additions**: 총 덧셈 연산 수
- **Total Multiplications**: 총 곱셈 연산 수
- **Total Operations**: 총 연산 수 (additions + multiplications)

**중요성**:
- 디지털 에너지 소비의 직접적인 원인
- 5비트 vs 10비트 차이가 명확히 드러남
- 곱셈은 비트 수²에 비례해서 차이가 큼

**그래프**: `metrics_operations.png` (3개 막대 그래프)

---

### 3. 효율성 메트릭 (신규 ⭐⭐⭐)

#### 3.1 에너지 효율성 (Energy Efficiency)
- **공식**: `(총 전송 비트 수) / (총 에너지 Joule)`
- **단위**: bits/Joule (높을수록 좋음)
- **의미**: 에너지 대비 전송 효율

**중요성**:
- 에너지와 성능을 한눈에 비교
- Adaptive 모델의 우수성을 증명하는 핵심 메트릭
- IoT/임베디드 시스템에서 가장 중요한 지표

**그래프**: `metrics_energy_efficiency.png`

#### 3.2 SQNR (Signal to Quantization Noise Ratio)
- **공식**: `SQNR = 6.02 × N + 1.76 (dB)`, N = ADC 비트 수
- **이론값**:
  - 5비트: ~31.86 dB
  - 10비트: ~61.96 dB
- **의미**: ADC 양자화 품질의 이론적 한계

**중요성**:
- 5비트 vs 10비트 품질 차이 정량화
- 신호 품질의 이론적 상한선

**그래프**: `metrics_sqnr.png`

#### 3.3 Throughput (처리량)
- **공식**: `(총 전송 비트 수) / (총 처리 시간)`
- **단위**: bps (bits per second)
- **의미**: 초당 처리 가능한 데이터량

**중요성**:
- 시스템 성능 지표
- Latency와 상호 관련

**그래프**: `metrics_throughput.png`

---

### 4. SNR별 분석 (신규 ⭐⭐)

#### 4.1 SNR vs BER 성능
- **X축**: SNR 값 (5, 10, 15, 20 dB)
- **Y축**: BER (로그 스케일)
- **라인**: 각 모델별로 별도 라인

**중요성**:
- 낮은 SNR에서 5비트 vs 10비트 성능 차이가 더 큼
- 채널 조건에 따른 모델 성능 비교
- Adaptive 모델이 어떤 SNR에서 유리한지 확인

**그래프**: `metrics_ber_vs_snr.png` (라인 그래프)

---

### 5. 트래픽 타입별 분석 (신규 ⭐⭐)

#### 5.1 트래픽별 BER
- **트래픽 타입**: sensor, voice, video
- **각 모델별**: BER 비교

**중요성**:
- Adaptive 모델이 트래픽에 맞게 비트 선택하는지 확인
- 트래픽별 요구사항과 실제 성능 비교
- 예: sensor는 5비트로 충분, video는 10비트 필요

**그래프**: `metrics_ber_by_traffic.png` (그룹 막대 그래프)

#### 5.2 트래픽별 에너지
- **트래픽 타입**: sensor, voice, video
- **각 모델별**: 패킷당 디지털 에너지 (pJ)

**중요성**:
- 트래픽별 에너지 소비 패턴 확인
- Adaptive 모델의 에너지 절약 효과 증명
- 예: sensor 트래픽에서 Adaptive가 5비트 사용 → 에너지 절약

**그래프**: `metrics_energy_by_traffic.png` (그룹 막대 그래프)

---

### 6. ADC 비트 사용 분석 (신규 ⭐⭐, Adaptive만 해당)

#### 6.1 ADC 비트 선택 비율
- **5-bit usage**: 5비트 사용 비율 (%)
- **10-bit usage**: 10비트 사용 비율 (%)

**모델별 예상값**:
- Low-Power Fixed: 100% 5비트, 0% 10비트
- High-Perf Fixed: 0% 5비트, 100% 10비트
- Adaptive: 트래픽 분포에 따라 변동

**중요성**:
- Adaptive 모델의 동작 증명
- 트래픽 분포에 따른 적응성 확인
- 에너지 절약 원리 설명

**그래프**: `metrics_adc_bit_usage.png` (스택 막대 그래프)

---

## 그래프 목록

### 기존 그래프 (3개)
1. `metrics_energy.png` - 아날로그/디지털 에너지
2. `metrics_accuracy.png` - 평균 BER
3. `metrics_latency.png` - 평균 지연

### 신규 그래프 (8개)
4. `metrics_operations.png` - 연산량 (additions, multiplications, total)
5. `metrics_energy_efficiency.png` - 에너지 효율성 (bits/Joule)
6. `metrics_sqnr.png` - SQNR
7. `metrics_throughput.png` - Throughput
8. `metrics_ber_vs_snr.png` - SNR별 BER 성능 (라인 그래프)
9. `metrics_ber_by_traffic.png` - 트래픽별 BER
10. `metrics_energy_by_traffic.png` - 트래픽별 에너지
11. `metrics_adc_bit_usage.png` - ADC 비트 사용 비율

**총 11개 그래프 생성**

---

## 주요 개선 사항

### 1. Latency 계산 개선
**이전**:
```python
latency = 블록 개수 × 1.0ms
```
- 문제: 모든 모델이 같은 블록 개수 → latency 동일
- 연산 복잡도 반영 안 함

**개선 후**:
```python
latency = (total_adds × 0.001ms) + (total_mults × 0.005ms) + overhead
```
- 연산 복잡도 반영
- 5비트 < Adaptive < 10비트 차이 명확

### 2. 연산량 그래프 추가
**이전**: 측정만 하고 그래프 없음

**개선 후**:
- Additions, Multiplications, Total Operations 그래프 생성
- 디지털 에너지의 직접적인 원인 시각화

### 3. 효율성 메트릭 추가
**신규**: Energy Efficiency (bits/Joule)
- 에너지와 성능을 통합한 지표
- Adaptive 모델의 우수성 증명

---

## 코드 수정 사항

### 1. `_flatten_packets()` 확장
- SNR, 연산량, ADC 비트 추가 추출
- Latency 계산 개선

### 2. `compute_model_metrics()` 확장
```python
return {
    # 기본 메트릭
    "total_analog_mj", "total_digital_pj", "avg_ber", "avg_latency_ms",

    # 연산량 메트릭
    "total_operations", "total_additions", "total_multiplications",

    # 효율성 메트릭
    "energy_efficiency_bits_per_joule", "avg_sqnr_db", "throughput_bps",

    # 상세 분석
    "ber_by_snr", "ber_by_traffic", "energy_by_traffic",

    # ADC 비트 사용
    "adc_bit_5_ratio", "adc_bit_10_ratio", "avg_adc_bits"
}
```

### 3. 그래프 함수 추가
- `plot_three_metrics_models()`: 기존 3개 그래프
- `plot_extended_metrics()`: 신규 8개 그래프 (신규)
- `plot_all_metrics()`: 모든 그래프 생성 래퍼 (신규)

---

## 사용 방법

### 시뮬레이션 실행
```bash
python main_agc_system.py
```

### 출력
```
Python-based AGC Comparison (Conventional vs Proposed)
Comprehensive metrics: energy, accuracy, latency, operations, efficiency, SQNR, throughput, etc.
==================================================

Running model: Low-Power Fixed (5-bit)
...

Running model: High-Perf Fixed (10-bit)
...

Running model: Adaptive (Proposed)
...

Generating all comparison graphs...
  ✓ Saved: metrics_energy.png
  ✓ Saved: metrics_accuracy.png
  ✓ Saved: metrics_latency.png
  ✓ Saved: metrics_operations.png
  ✓ Saved: metrics_energy_efficiency.png
  ✓ Saved: metrics_sqnr.png
  ✓ Saved: metrics_throughput.png
  ✓ Saved: metrics_ber_vs_snr.png
  ✓ Saved: metrics_ber_by_traffic.png
  ✓ Saved: metrics_energy_by_traffic.png
  ✓ Saved: metrics_adc_bit_usage.png

All graphs saved to: ./
Total: 11 comparison graphs generated
```

---

## 예상 결과

### Energy Efficiency 비교
- **Low-Power (5-bit)**: 낮음 (낮은 에너지, 하지만 높은 BER로 재전송 필요)
- **High-Perf (10-bit)**: 중간 (높은 에너지, 낮은 BER)
- **Adaptive**: 가장 높음 ⭐ (트래픽에 맞게 최적화)

### BER vs SNR
- **낮은 SNR (5 dB)**: 5비트와 10비트 차이 큼
- **높은 SNR (20 dB)**: 5비트도 충분히 좋은 성능
- **Adaptive**: 중간 성능, SNR에 따라 적응

### 트래픽별 분석
- **sensor**: 5비트로 충분 → Adaptive가 5비트 선택 → 에너지 절약
- **voice/video**: 10비트 필요 → Adaptive가 10비트 선택 → 품질 보장

### ADC 비트 사용
- **Adaptive**: 약 50% 5비트, 50% 10비트 (트래픽 분포에 따라 변동)
- 이것이 에너지 절약과 품질 보장의 균형점!

---

## 결론

새로운 메트릭 시스템은:
1. ✅ **연산량을 시각화**해서 디지털 에너지 차이의 원인 설명
2. ✅ **에너지 효율성**으로 Adaptive 모델의 우수성 증명
3. ✅ **개선된 Latency**로 연산 복잡도 차이 반영
4. ✅ **SNR별/트래픽별 분석**으로 모델의 적응성 증명
5. ✅ **ADC 비트 사용 비율**로 Adaptive 동작 원리 설명

**총 11개 그래프로 종합적인 성능 비교 가능!**
