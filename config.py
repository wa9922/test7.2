# /mnt/data/config.py
import numpy as np

# --- 시뮬레이션 기본 설정 ---
SAMPLING_RATE = 20e6
SYMBOL_RATE   = 1e6
SAMPLES_PER_SYMBOL = int(SAMPLING_RATE / SYMBOL_RATE)

# --- 패킷 구조 설정(비트 단위) ---
STF_BITS = [1,0,1,1,0,1,0,0,1,0,1,1,0,1,0,0]*8
LTF_BITS = [1,1,0,1,1,0,0,1,0,1,1,1,0,0,0,1]*4
SIGNAL_FIELD_BITS = 48
PAYLOAD_BITS      = 1024

# --- BPSK ---
# GNURadio 호환: Complex는 float32 실수부 + float32 허수부 = 64비트
BPSK_CONSTELLATION = {0: np.complex64(-1.0+0j), 1: np.complex64(+1.0+0j)}

# --- Gain 레벨 (FSM 제거됨, 참고용 설정만 남음) ---
# 참고: 실제로는 모든 모델이 AGC를 사용하여 gain을 자동 조절합니다.
# Fixed 모델은 디지털 비트만 고정, gain은 동적으로 변경됩니다.
GAIN_LEVELS = {
    "LOW_GAIN": 15,   # dB (참고용, 더 이상 고정값으로 사용 안 함)
    "HIGH_GAIN": 40,  # dB (참고용, 더 이상 고정값으로 사용 안 함)
}

# (기존) 트래픽별 ADC 해상도 정의는 더 이상 실제 ADC 비트 선택에 쓰지 않음.
# 대신, 아래 DIGITAL_TRUNCATION_BITS로 디지털 파이프라인에서 '잘라 쓰기'를 함.
TRAFFIC_ADC_RESOLUTION = {
    "wake_up": 5,                    # wake-up 신호
    "lowpowersignal":  5,            # 저전력 신호
    "highperformancesignal": 10,     # 고성능 신호
}

# 디지털 파이프라인에서 사용할 "트렁케이션 비트 수"
# ADC는 항상 10비트로 동작, 디지털 단에서 5비트 또는 10비트로 truncate
DIGITAL_TRUNCATION_BITS = {
    "wake_up": 5,                    # wake-up: 5비트
    "lowpowersignal":  5,            # 저전력 신호: 5비트
    "highperformancesignal": 10,     # 고성능 신호: 10비트
}

# --- Signal Field 매핑 (교수님 피드백: 3가지만, 중복 제거) ---
TRAFFIC_INDICATION_MAPPING = {
    "00": "wake_up",
    "01": "lowpowersignal",
    "10": "highperformancesignal",
}
SIGNAL_FIELD_STRUCTURE = {"traffic_type":2,"control_bits":2,"total_bits":4}

# --- Carrier sensing ---
SATURATION_THRESHOLD = {"5bit":15, "10bit":510}  # 5비트: 32레벨 중 15, 10비트: 1024레벨 중 510
ENERGY_DETECTION_THRESHOLD = -75
CORRELATION_THRESHOLD = 0.6

# --- LUT (Look-Up Table) - Carrier Sensing 임계값 (참고용, FSM 제거됨) ---
# 각 gain 레벨에서의 carrier sensing 임계값 설정
LUT_THRESHOLDS = {
    "LOW_GAIN": {
        "saturation_th": SATURATION_THRESHOLD["5bit"],
        "energy_th": 0.05,
        "corr_th": 0.7,
        "gain_code": "0100"
    },
    "HIGH_GAIN": {
        "saturation_th": SATURATION_THRESHOLD["10bit"],
        "energy_th": 0.2,
        "corr_th": 0.85,
        "gain_code": "1110"
    },
}

# --- BER ---
BER_WINDOW_SIZE = 128
BER_UPDATE_INTERVAL = 100

# --- 채널 ---
DEFAULT_SNR_DB = 10
NOISE_POWER    = 0.1

# --- 채널 SNR 범위 (교수님 피드백 반영) ---
# SNR은 주어진 채널 환경 (트래픽 타입과 무관)
# 시스템은 SNR에 맞게 MCS를 선택하고, 수신 신호에 따라 디지털 비트 선택
CHANNEL_SNR_RANGE = [5, 10, 15, 20, 25]  # 다양한 채널 환경 (dB)

# --- 디지털 더미 연산(비트 기반) 스케일 상수 ---
# adds_per_sample ≈ K_ADD * bits
# mults_per_sample ≈ K_MUL * bits^2
# 값을 크게 증가시켜 디지털 에너지 차이를 명확하게 표현
K_ADD_PER_SAMPLE  = 5000.0  # 1.0 → 5000.0 (5000배 증가)
K_MUL_PER_SAMPLE  = 250.0   # 0.05 → 250.0 (5000배 증가)

# --- 옵션 ---
DEBUG_MODE = False
SAVE_INTERMEDIATE_RESULTS = True
PLOT_RESULTS = True

# --- 아날로그 단일화 플래그 ---
UNIFIED_ANALOG_ALWAYS_ON = True    # 항상 RX on(동일 전력)
ADC_MAX_BITS             = 10      # 실제 ADC 고정 비트
