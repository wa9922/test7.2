# GNURadio 호환성 문서

## 개요
이 프로젝트는 GNURadio의 Signal Data Types 표준에 맞추어 데이터 타입을 명시적으로 정의했습니다.

## GNURadio 표준 데이터 타입

| GNURadio 타입 | 크기 | NumPy 타입 | 설명 |
|--------------|------|-----------|------|
| **Complex** | 64비트 | `np.complex64` | float32 실수부 + float32 허수부 |
| **Float** | 32비트 | `np.float32` | 32비트 부동소수점 |
| **Int** | 32비트 | `np.int32` | 32비트 정수 |
| **Short** | 16비트 | `np.int16` | 16비트 정수 |
| **Byte** | 8비트 | `np.uint8` | 8비트 부호 없는 정수 |

## 수정된 파일 및 변경 사항

### 1. **config.py**
- **BPSK_CONSTELLATION**: `complex` → `np.complex64`
```python
# 수정 전
BPSK_CONSTELLATION = {0: -1.0+0j, 1: +1.0+0j}

# 수정 후
BPSK_CONSTELLATION = {0: np.complex64(-1.0+0j), 1: np.complex64(+1.0+0j)}
```

### 2. **signal_generator.py**
#### 비트 데이터
- 모든 비트 배열: `int` → `np.uint8` (GNURadio Byte 타입)

```python
# 수정 전
self.stf_reference_bits = np.array(STF_BITS)

# 수정 후
self.stf_reference_bits = np.array(STF_BITS, dtype=np.uint8)
```

#### 복소수 신호
- BPSK 심볼: 암시적 complex → `np.complex64` (GNURadio Complex 타입)

```python
# 수정 전
symbols = np.array([BPSK_CONSTELLATION[bit] for bit in bits])

# 수정 후
symbols = np.array([BPSK_CONSTELLATION[bit] for bit in bits], dtype=np.complex64)
```

#### 비트 복조
- 복조된 비트: `int` → `np.uint8`

```python
# 수정 전
bits = (np.real(downsampled) > 0).astype(int)

# 수정 후
bits = (np.real(downsampled) > 0).astype(np.uint8)
```

### 3. **adc.py**
#### Float 출력
- 양자화된 신호: 암시적 float → `np.float32` (GNURadio Float 타입)

```python
# 수정 전
x_quantized = np.round(x_clipped / self.step) * self.step

# 수정 후
x_quantized = (np.round(x_clipped / self.step) * self.step).astype(np.float32)
```

#### Integer 출력
- 정수 레벨: `int` → `np.int16` (GNURadio Short 타입)

```python
# 수정 전
return x_int.astype(int)

# 수정 후
return x_int.astype(np.int16)
```

### 4. **ber_calculator.py**
- STF 참조 비트: `int` → `np.uint8`

```python
# 수정 전
self.stf_reference_bits = np.array(STF_BITS)

# 수정 후
self.stf_reference_bits = np.array(STF_BITS, dtype=np.uint8)
```

### 5. **simulation_utils.py**
- 복조 비트: `int` → `np.uint8`

```python
# 수정 전
demodulated_bits = (np.real(signal_field_signal) > 0).astype(int)

# 수정 후
demodulated_bits = (np.real(signal_field_signal) > 0).astype(np.uint8)
```

## 데이터 흐름 타입 명세

### 신호 생성 경로
```
비트 (uint8) → BPSK 변조 → 복소수 신호 (complex64)
```

### ADC 처리 경로
```
복소수 신호 (complex64) → ADC 양자화 → float32 또는 int16
```

### 복조 경로
```
복소수 신호 (complex64) → Hard Decision → 비트 (uint8)
```

## 호환성 이점

1. **GNURadio 블록과의 직접 연동 가능**
   - Python 시뮬레이션 결과를 GNURadio Companion에서 직접 사용 가능
   - 파일 소스/싱크를 통한 데이터 교환 시 타입 불일치 오류 방지

2. **메모리 효율성**
   - `float64` → `float32`: 메모리 사용량 50% 감소
   - `int`/`int64` → `uint8`: 비트 데이터 메모리 사용량 87.5% 감소

3. **표준 준수**
   - 무선통신 시뮬레이션 도구의 사실상 표준인 GNURadio 규격 준수
   - 타 연구자와의 코드/데이터 공유 시 호환성 보장

## 검증 방법

### 타입 확인 스크립트
```python
import numpy as np
from signal_generator import SignalGenerator

sg = SignalGenerator()
packet = sg.create_complete_packet('sensor')

print('=== GNURadio 타입 검증 ===')
print(f'비트 타입: {packet["complete_bits"].dtype} (예상: uint8)')
print(f'복소수 신호 타입: {packet["complete_signal"].dtype} (예상: complex64)')
print(f'비트 크기: {packet["complete_bits"].itemsize} bytes (예상: 1)')
print(f'복소수 크기: {packet["complete_signal"].itemsize} bytes (예상: 8)')
```

### 예상 출력
```
=== GNURadio 타입 검증 ===
비트 타입: uint8 (예상: uint8) ✓
복소수 신호 타입: complex64 (예상: complex64) ✓
비트 크기: 1 bytes (예상: 1) ✓
복소수 크기: 8 bytes (예상: 8) ✓
```

## 참고 자료
- GNURadio Wiki: Signal Data Types
- 스크린샷: `gnuradio_screenshot.jpeg`
- GNURadio 공식 문서: https://wiki.gnuradio.org/

## 작성일
2025-11-16

## 작성자
AGC 시스템 시뮬레이션 프로젝트 팀
