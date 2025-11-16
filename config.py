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

# --- FSM 이득 레벨(그대로 두되, 아날로그 단일화 이후에도 동작) ---
GAIN_LEVELS = {
    "LOW_GAIN_LP": 10,
    "LOW_GAIN_HP": 25,
    "MEDIUM_GAIN": 35,
    "HIGH_GAIN": 40,
}

# (기존) 트래픽별 ADC 해상도 정의는 더 이상 실제 ADC 비트 선택에 쓰지 않음.
# 대신, 아래 DIGITAL_TRUNCATION_BITS로 디지털 파이프라인에서 '잘라 쓰기'를 함.
TRAFFIC_ADC_RESOLUTION = {
    "wake_up": 5,   # 3비트 → 5비트로 변경 (quantization noise 감소)
    "sensor":  5,
    "voice":   10,
    "video":   10,
}

# 디지털 파이프라인에서 사용할 "트렁케이션 비트 수"
# ADC는 항상 10비트로 동작, 디지털 단에서 5비트 또는 10비트로 truncate
DIGITAL_TRUNCATION_BITS = {
    "wake_up": 5,   # 저전력: 5비트 사용
    "sensor":  5,   # 저전력: 5비트 사용
    "voice":   10,  # 고성능: 10비트 전부 사용
    "video":   10   # 고성능: 10비트 전부 사용
}

# FSM 상태 ↔ 트래픽 타입 매핑
FSM_STATE_TO_TRAFFIC = {
    "LOW_GAIN_LP": "wake_up",
    "LOW_GAIN_HP": "sensor",
    "MEDIUM_GAIN": "voice",
    "HIGH_GAIN":   "video",
}

# --- Signal Field 매핑 ---
TRAFFIC_INDICATION_MAPPING = {"00":"sensor","01":"voice","10":"video","11":"wake_up"}
SIGNAL_FIELD_STRUCTURE = {"traffic_type":2,"control_bits":2,"total_bits":4}

# --- Carrier sensing ---
SATURATION_THRESHOLD = {"5bit":15, "10bit":510}  # 5비트: 32레벨 중 15, 10비트: 1024레벨 중 510
ENERGY_DETECTION_THRESHOLD = -75
CORRELATION_THRESHOLD = 0.6

# --- LUT ---
LUT_THRESHOLDS = {
    "LOW_GAIN_LP": {"saturation_th":SATURATION_THRESHOLD["5bit"],
                    "energy_th":0.01,"corr_th":0.6,"gain_code":"0100"},
    "LOW_GAIN_HP": {"saturation_th":SATURATION_THRESHOLD["10bit"]//4,
                    "energy_th":0.05,"corr_th":0.7,"gain_code":"0110"},
    "MEDIUM_GAIN": {"saturation_th":SATURATION_THRESHOLD["10bit"]//2,
                    "energy_th":0.1,"corr_th":0.8,"gain_code":"1010"},
    "HIGH_GAIN":   {"saturation_th":SATURATION_THRESHOLD["10bit"],
                    "energy_th":0.2,"corr_th":0.85,"gain_code":"1110"},
}

# --- BER ---
BER_WINDOW_SIZE = 128
BER_UPDATE_INTERVAL = 100

# --- 채널 ---
DEFAULT_SNR_DB = 10
NOISE_POWER    = 0.1

# --- 디지털 더미 연산(비트 기반) 스케일 상수 ---
# adds_per_sample ≈ K_ADD * bits
# mults_per_sample ≈ K_MUL * bits^2
K_ADD_PER_SAMPLE  = 1.0
K_MUL_PER_SAMPLE  = 0.05

# --- 옵션 ---
DEBUG_MODE = False
SAVE_INTERMEDIATE_RESULTS = True
PLOT_RESULTS = True

# --- 아날로그 단일화 플래그 ---
UNIFIED_ANALOG_ALWAYS_ON = True    # 항상 RX on(동일 전력)
ADC_MAX_BITS             = 10      # 실제 ADC 고정 비트
