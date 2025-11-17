# AGC 시스템 GNURadio GUI - 빠른 시작 가이드

## 1. 설치

```bash
# GNURadio 설치 (Ubuntu/Debian)
sudo apt-get install gnuradio python3-scipy

# 또는 conda 사용
conda install -c conda-forge gnuradio
```

## 2. 실행

```bash
# GNURadio Companion 실행
cd /home/user/test7.2
gnuradio-companion gnu/examples/agc_comparison.grc
```

## 3. GUI에서 실행

1. **Generate** 버튼 클릭 (F5) - Python 코드 생성
2. **Execute** 버튼 클릭 (F6) - 실행

## 4. 조작 방법

- **SNR 슬라이더**: 채널 SNR 조정 (0-30 dB)
- **Traffic Type 선택**:
  - Low Power Signal: 저전력 신호 (5-bit)
  - High Performance Signal: 고성능 신호 (10-bit)

## 5. 확인할 내용

### 시각화 창

1. **신호 파형**: 3가지 AGC 모델의 출력 신호
2. **BER 비교**: LP vs HP vs Adaptive
   - LP (5-bit): BER 높음 (에너지 낮음)
   - HP (10-bit): BER 낮음 (에너지 높음)
   - Adaptive: Traffic에 따라 자동 조정

### 콘솔 메시지

- AGC 통계 (gain, digital bits)
- 전력/에너지 측정
- BER 값

## 6. 예상 결과

### Low Power Signal 선택 시

| Model | Digital Bits | BER | Energy |
|-------|--------------|-----|---------|
| LP | 5-bit | 높음 | **낮음** ✅ |
| HP | 10-bit | 낮음 | 높음 |
| Adaptive | **5-bit** | 높음 | **낮음** ✅ |

→ **Adaptive가 LP와 동일** (저전력 최적화)

### High Performance Signal 선택 시

| Model | Digital Bits | BER | Energy |
|-------|--------------|-----|---------|
| LP | 5-bit | 높음 | 낮음 |
| HP | 10-bit | **낮음** ✅ | 높음 |
| Adaptive | **10-bit** | **낮음** ✅ | 높음 |

→ **Adaptive가 HP와 동일** (성능 최적화)

## 7. 주요 알고리즘

### AGC System Block

```python
# RF Path: UnifiedRFPath (항상 동일)
신호 → LNA (20dB) → Mixer → VGA (가변) → LPF

# ADC: 항상 10-bit
quantized = round(신호 / step) × step

# Digital Truncation: 5-bit 또는 10-bit
if traffic == 'lowpowersignal':
    bits = 5
elif traffic == 'highperformancesignal':
    bits = 10

# Gain Feedback (Adaptive만)
peak = max(|신호|)
if peak > 0.9:
    gain -= 1 dB  # Saturation 방지
elif peak < 0.25:
    gain += 1 dB  # SNR 향상
```

### BER Calculator

```python
# SQNR 계산
SQNR_dB = 6.02 × bits + 1.76

# Effective SNR
SNR_eff = 1 / (1/SNR_channel + 1/SQNR)

# BPSK BER
BER = 0.5 × erfc(sqrt(SNR_eff))
```

### Power Meter

```python
# 아날로그: MAX2829 기준 (항상 동일)
analog_energy = 392 mW × time

# 디지털: 비트 종속
digital_energy = (덧셈 × 0.1 + 곱셈 × 2.5) × (bits²/64)
```

## 8. 문제 해결

### 블록을 찾을 수 없음

GRC 파일에서 Python 경로 확인:
```python
sys.path.insert(0, '/home/user/test7.2/gnu/python')
```

### scipy 오류

```bash
pip install scipy
```

### 실행 오류

```bash
# GNURadio 버전 확인 (3.8+ 필요)
gnuradio-companion --version

# Python 버전 확인 (3.6+ 필요)
python3 --version
```

## 9. 파일 구조

```
gnu/
├── python/                    # Python 블록들
│   ├── agc_packet_source.py  # 패킷 생성
│   ├── agc_system_block.py   # AGC 메인 처리
│   ├── agc_ber_calc.py       # BER 계산
│   └── agc_power_meter.py    # 전력 측정
├── examples/
│   └── agc_comparison.grc    # GUI 플로우그래프
├── README.md                 # 상세 문서
└── QUICKSTART_KR.md          # 이 파일
```

## 10. Python 시뮬레이션과 차이

| 항목 | Python 시뮬레이션 | GNURadio GUI |
|------|-------------------|--------------|
| 실행 방식 | 배치 처리 | 실시간 스트림 |
| 시각화 | matplotlib 그래프 | 실시간 GUI |
| 알고리즘 | **동일** | **동일** |
| 결과 | PNG 파일 저장 | GUI 화면 표시 |

---

**완료!** 이제 GNURadio에서 AGC 시스템을 실시간으로 확인할 수 있습니다.
