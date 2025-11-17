# AGC System - GNURadio GUI Implementation

GNURadio 기반 Adaptive AGC 시스템 GUI 구현

## 개요

Python 기반 AGC 시스템을 GNURadio 블록으로 변환하여 GUI에서 실시간으로 동작을 확인할 수 있습니다.

### 주요 기능

- **3가지 AGC 모델 비교**:
  - Low-Power AGC (15dB gain, 5-bit digital)
  - High-Performance AGC (40dB gain, 10-bit digital)
  - Adaptive AGC (gain 피드백 + traffic-based digital bits)

- **실시간 시각화**:
  - 시간 영역 신호 파형
  - BER 비교 (3가지 모델)
  - 전력/에너지 측정

- **동일한 알고리즘**:
  - Python 시뮬레이션과 동일한 RF path
  - 동일한 ADC quantization + digital truncation
  - 동일한 gain feedback 로직

---

## 파일 구조

```
gnu/
├── python/
│   ├── __init__.py                # 패키지 초기화
│   ├── agc_packet_source.py       # 패킷 생성 블록
│   ├── agc_system_block.py        # AGC 시스템 블록 (메인)
│   ├── agc_ber_calc.py            # BER 계산 블록
│   └── agc_power_meter.py         # 전력 측정 블록
├── examples/
│   └── agc_comparison.grc         # GNURadio Companion 플로우그래프
└── README.md                      # 이 파일
```

---

## 설치 및 실행

### 1. GNURadio 설치 (Ubuntu/Debian)

```bash
# GNURadio 3.8+ 설치
sudo apt-get update
sudo apt-get install gnuradio python3-scipy

# 또는 conda 사용
conda install -c conda-forge gnuradio
```

### 2. Python 경로 설정

GRC 파일에서 블록들이 자동으로 `/home/user/test7.2/gnu/python` 경로를 참조합니다.
다른 경로에서 사용하는 경우 GRC 파일에서 `sys.path.insert(0, ...)` 부분을 수정하세요.

### 3. GNURadio Companion 실행

```bash
# GNURadio Companion 실행
gnuradio-companion

# 또는 직접 grc 파일 열기
gnuradio-companion gnu/examples/agc_comparison.grc
```

### 4. 플로우그래프 실행

GNURadio Companion에서:
1. 파일 열기: `gnu/examples/agc_comparison.grc`
2. Generate (F5) - Python 코드 생성
3. Execute (F6) - 실행

---

## 블록 설명

### 1. AGC Packet Source (`agc_packet_source`)

**기능**: STF + LTF + Signal Field + Payload 패킷 생성

**Parameters**:
- `traffic_type`: 'lowpowersignal' 또는 'highperformancesignal'
- `snr_db`: 채널 SNR (dB)
- `packets_per_burst`: 버스트당 패킷 수
- `repeat`: 반복 여부

**Outputs**:
- Complex stream: 노이즈가 추가된 패킷
- Message port `packet_info`: 패킷 메타데이터

**알고리즘**:
```python
# BPSK 변조
STF (128 bits) → BPSK → 2560 samples
LTF (64 bits)  → BPSK → 1280 samples
Signal Field (48 bits) → BPSK → 960 samples
Payload (1024 bits) → BPSK → 20480 samples

# AWGN 추가
noise_power = signal_power / (10^(SNR_dB/10))
noisy_signal = clean_signal + noise
```

---

### 2. AGC System Block (`agc_system_block`)

**기능**: RF path → ADC → Digital Truncation → Gain Feedback

**Parameters**:
- `agc_mode`: 'adaptive', 'low_power', 'high_performance'
- `enable_gain_feedback`: Gain 피드백 활성화 여부

**Inputs**:
- Complex stream: 입력 신호
- Message port `traffic_info`: 트래픽 타입 정보

**Outputs**:
- Complex stream: 처리된 신호
- Message port `agc_stats`: AGC 통계

**알고리즘**:

```python
# 1. RF Path (UnifiedRFPath)
signal → LNA (20dB) → Mixer → VGA (가변) → LPF

# 2. ADC 10-bit Quantization
step = (2 × Vref) / 1024
quantized = round(signal / step) × step

# 3. Digital Truncation (5-bit or 10-bit)
if digital_bits == 5:
    target_step = (2 × Vref) / 32
    truncated = round(quantized / target_step) × target_step

# 4. Gain Feedback (peak-based)
peak = max(|signal|)
if peak > 0.9:
    gain -= 1 dB  # Saturation 방지
elif peak < 0.25:
    gain += 1 dB  # SNR 향상
gain = clip(gain, 10, 50)  # 범위 제한
```

**모드별 동작**:

| Mode | Gain (dB) | Digital Bits | Gain Feedback |
|------|-----------|--------------|---------------|
| Low-Power | 15 (고정) | 5 (고정) | Disabled |
| High-Performance | 40 (고정) | 10 (고정) | Disabled |
| Adaptive | 10-50 (가변) | 5 or 10 (traffic 기반) | Enabled |

---

### 3. BER Calculator (`agc_ber_calc`)

**기능**: 이론적 BER 계산 (quantization error 포함)

**Parameters**:
- `adc_bits`: ADC/디지털 비트 수 (5 or 10)
- `update_interval`: BER 업데이트 주기 (samples)

**Inputs**:
- Complex stream: 수신 신호
- Message port `snr_in`: SNR 정보
- Message port `bits_in`: 디지털 비트 수

**Outputs**:
- Float stream: BER 값
- Message port `ber_out`: BER 통계

**알고리즘**:

```python
# SQNR (Signal to Quantization Noise Ratio)
SQNR_dB = 6.02 × adc_bits + 1.76

# Effective SNR (채널 SNR + 양자화 SNR)
SNR_eff = 1 / (1/SNR_channel + 1/SQNR)

# BPSK Theoretical BER
BER = 0.5 × erfc(sqrt(SNR_eff))
```

**예시**:
- 5-bit, SNR=10dB → BER ≈ 8.43 × 10⁻⁸
- 10-bit, SNR=10dB → BER ≈ 2.54 × 10⁻¹⁰ (332배 낮음)

---

### 4. Power Meter (`agc_power_meter`)

**기능**: 아날로그 및 디지털 에너지 측정

**Parameters**:
- `sampling_rate`: 샘플링 레이트 (Hz)
- `adc_bits`: 디지털 비트 수

**Inputs**:
- Complex stream: 신호
- Message port `bits_in`: 디지털 비트 수

**Outputs**:
- Message port `power_out`: 전력/에너지 통계

**알고리즘**:

```python
# 1. 아날로그 에너지 (항상 동일, MAX2829 기준)
analog_power = 392 mW  # MAX2829 RX mode
time_sec = samples / sampling_rate
analog_energy_mJ = analog_power × time_sec

# 2. 디지털 에너지 (비트 종속)
additions = K_ADD × samples × bits  # K_ADD = 5000
multiplications = K_MUL × samples × bits²  # K_MUL = 250
area_ratio = (bits² / 8²)
digital_energy_pJ = (additions × 0.1 + multiplications × 2.5) × area_ratio

# 3. 총 에너지
total_energy_mJ = analog_energy_mJ + (digital_energy_pJ / 1e9)
```

**예시** (10000 samples, 20MHz):
- LP (5-bit): analog 0.196 mJ + digital 0.019 mJ = 0.215 mJ
- HP (10-bit): analog 0.196 mJ + digital 0.263 mJ = 0.459 mJ
- Adaptive: traffic에 따라 동적 변경

---

## GUI 사용법

### 컨트롤 패널

1. **SNR (dB) 슬라이더**: 0-30 dB 범위에서 채널 SNR 조정
2. **Traffic Type 선택**:
   - Low Power Signal: 5-bit digital 사용 (저전력)
   - High Performance Signal: 10-bit digital 사용 (고성능)

### 시각화 창

1. **Time Sink**: 신호 파형 (실시간)
   - Low-Power, High-Performance, Adaptive 3개 병렬 표시

2. **BER Number Sink**: BER 값 비교
   - LP: 5-bit quantization BER
   - HP: 10-bit quantization BER
   - Adaptive: 동적 BER

3. **Message Debug**: 콘솔에 메시지 출력
   - AGC 통계 (gain, digital bits)
   - 전력/에너지 측정값
   - BER 통계

---

## 예상 결과

### SNR = 10 dB, Low Power Signal

| Model | Gain | Digital Bits | BER | Analog Energy | Digital Energy |
|-------|------|--------------|-----|---------------|----------------|
| Low-Power | 15 dB | 5-bit | 8.43×10⁻⁸ | 0.4949 mJ | 0.19 mJ |
| High-Performance | 40 dB | 10-bit | 2.54×10⁻¹⁰ | 0.4949 mJ | 2.63 mJ |
| Adaptive | 10-50 dB | 5-bit | 8.43×10⁻⁸ | 0.4949 mJ | 0.19 mJ |

### SNR = 10 dB, High Performance Signal

| Model | Gain | Digital Bits | BER | Analog Energy | Digital Energy |
|-------|------|--------------|-----|---------------|----------------|
| Low-Power | 15 dB | 5-bit | 8.43×10⁻⁸ | 0.4949 mJ | 0.19 mJ |
| High-Performance | 40 dB | 10-bit | 2.54×10⁻¹⁰ | 0.4949 mJ | 2.63 mJ |
| Adaptive | 10-50 dB | 10-bit | 2.54×10⁻¹⁰ | 0.4949 mJ | 2.63 mJ |

**Adaptive AGC 장점**:
- Low Power Signal: LP와 동일한 에너지 (저전력)
- High Performance Signal: HP와 동일한 BER (고성능)
- **최적의 trade-off**: Traffic에 맞춰 자동 조정

---

## Python 시뮬레이션과 비교

### 동일한 부분 ✅

1. **RF Path**: UnifiedRFPath (LNA 20dB + VGA 가변)
2. **ADC**: 항상 10-bit 양자화
3. **Digital Truncation**: 5-bit 또는 10-bit
4. **Gain Feedback**: Peak-based (threshold 0.9/0.25)
5. **BER Model**: Theoretical BPSK + SQNR
6. **Power Model**: MAX2829 아날로그 + 비트 종속 디지털

### 차이점 ⚠️

1. **블록 기반 처리**: GNURadio는 스트림 기반, Python은 패킷 기반
2. **실시간 동작**: GNURadio는 실시간 처리, Python은 배치 시뮬레이션
3. **Carrier Sensing**: GNURadio 버전에서는 생략 (단순화)
4. **Signal Field Decoding**: Message passing으로 대체

---

## 문제 해결

### GNURadio 블록을 찾을 수 없음

```bash
# Python 경로 확인
import sys
sys.path.insert(0, '/home/user/test7.2/gnu/python')
```

GRC 파일의 `_source_code` 섹션에서 경로가 올바른지 확인하세요.

### scipy 모듈 없음

```bash
# scipy 설치
pip install scipy
# 또는
conda install scipy
```

### 실행 시 에러

1. GNURadio 버전 확인: `gnuradio-companion --version` (3.8+ 필요)
2. Python 버전 확인: `python3 --version` (3.6+ 필요)
3. 로그 확인: 콘솔에 출력되는 에러 메시지 확인

---

## 추가 개발

### 새로운 블록 추가

1. `gnu/python/` 디렉토리에 새 블록 Python 파일 생성
2. `gnuradio.gr.sync_block` 또는 `gr.basic_block` 상속
3. `work()` 메서드 구현
4. `__init__.py`에 import 추가

### GRC 파일 수정

GNURadio Companion에서:
1. 블록 추가/삭제/수정
2. 파라미터 조정
3. 연결 변경
4. Save → Generate → Execute

---

## 참고자료

- [GNURadio Documentation](https://www.gnuradio.org/doc/)
- [Writing Python Blocks](https://wiki.gnuradio.org/index.php/Guided_Tutorial_GNU_Radio_in_Python)
- [GRC Tutorial](https://wiki.gnuradio.org/index.php/Guided_Tutorial_GRC)

---

## 라이선스

AGC System - Academic Research Project

---

## 연락처

프로젝트 관련 문의: [Your Contact]
