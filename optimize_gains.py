#!/usr/bin/env python3

"""
AGC 이득 값 최적화
각 트래픽 타입에 대한 최적 이득을 찾기
"""

import numpy as np
from agc_comparison import FixedLowPowerAGC, FixedHighPerformanceAGC
import matplotlib.pyplot as plt

def test_gain_performance(gain_db, traffic_type, snr_db=5.0, num_tests=10):
    """특정 이득에서의 BER 성능 측정"""

    # 테스트용 AGC 생성
    agc = FixedLowPowerAGC()

    # 이득 설정 변경
    agc.fsm.current_gain_index = 0
    agc.current_gain_linear = 10**(gain_db/20)

    ber_results = []

    for _ in range(num_tests):
        packet = agc.signal_generator.create_complete_packet(traffic_type)

        # 임시로 이득 적용
        original_gain = agc.current_gain_linear
        agc.current_gain_linear = 10**(gain_db/20)

        result = agc.process_packet(packet, snr_db)
        ber_results.append(result['final_ber']['ber'])

        agc.current_gain_linear = original_gain

    return np.mean(ber_results)

def optimize_gains_for_traffic():
    """각 트래픽 타입별 최적 이득 찾기"""

    print("="*60)
    print("Optimizing Gain Values for Each Traffic Type")
    print("="*60)

    # 테스트할 이득 범위
    gain_range = np.arange(0, 51, 5)  # 0dB ~ 50dB, 5dB 간격
    traffic_types = ['wake_up', 'sensor', 'voice', 'video']
    snr_values = [0, 5, 10]  # 다양한 SNR에서 테스트

    optimal_gains = {}

    for traffic in traffic_types:
        print(f"\nOptimizing for {traffic.upper()} traffic...")

        best_gain = None
        best_ber = 1.0

        gain_ber_results = []

        for gain in gain_range:
            # 여러 SNR에서의 평균 BER
            ber_sum = 0
            for snr in snr_values:
                ber = test_gain_performance(gain, traffic, snr, num_tests=5)
                ber_sum += ber

            avg_ber = ber_sum / len(snr_values)
            gain_ber_results.append((gain, avg_ber))

            if avg_ber < best_ber:
                best_ber = avg_ber
                best_gain = gain

            print(f"  Gain={gain:2d}dB: BER={avg_ber:.6f}")

        optimal_gains[traffic] = best_gain
        print(f"  → Optimal gain for {traffic}: {best_gain}dB (BER={best_ber:.6f})")

    print("\n" + "="*60)
    print("OPTIMIZATION RESULTS")
    print("="*60)
    print("\nOptimal gain values:")
    for traffic, gain in optimal_gains.items():
        print(f"  {traffic:10s}: {gain:2d} dB")

    print("\nSuggested config.py update:")
    print("GAIN_LEVELS = {")
    print(f'    "LOW_GAIN_LP": {optimal_gains["wake_up"]},   # wake_up')
    print(f'    "LOW_GAIN_HP": {optimal_gains["sensor"]},   # sensor')
    print(f'    "MEDIUM_GAIN": {optimal_gains["voice"]},    # voice')
    print(f'    "HIGH_GAIN": {optimal_gains["video"]},      # video')
    print("}")

    return optimal_gains

def test_fixed_agc_gains():
    """Fixed AGC들의 최적 이득 찾기"""

    print("\n" + "="*60)
    print("Finding Optimal Gains for Fixed AGCs")
    print("="*60)

    gain_range = np.arange(5, 46, 5)
    snr = 5.0

    # Low-Power AGC 최적 이득
    print("\nLow-Power AGC optimization (3-bit ADC):")
    best_lp_gain = None
    best_lp_ber = 1.0

    for gain in gain_range:
        ber_sum = 0
        for traffic in ['wake_up', 'sensor', 'voice', 'video']:
            ber = test_gain_performance(gain, traffic, snr, num_tests=3)
            ber_sum += ber
        avg_ber = ber_sum / 4

        print(f"  Gain={gain:2d}dB: Avg BER={avg_ber:.6f}")

        if avg_ber < best_lp_ber:
            best_lp_ber = avg_ber
            best_lp_gain = gain

    print(f"  → Optimal Low-Power gain: {best_lp_gain}dB")

    # High-Performance AGC는 10-bit ADC이므로 높은 이득 가능
    print("\nHigh-Performance AGC (10-bit ADC):")
    print("  Recommended: 30-40dB (based on 10-bit ADC dynamic range)")

    return best_lp_gain

if __name__ == "__main__":
    # 1. 각 트래픽별 최적 이득 찾기
    optimal_gains = optimize_gains_for_traffic()

    # 2. Fixed AGC들의 최적 이득 찾기
    best_lp_gain = test_fixed_agc_gains()

    print("\n" + "="*60)
    print("FINAL RECOMMENDATIONS")
    print("="*60)
    print(f"\n1. Update config.py with optimal gains above")
    print(f"\n2. Fixed AGC settings:")
    print(f"   - Low-Power AGC: {best_lp_gain}dB (3-bit ADC)")
    print(f"   - High-Perf AGC: 35-40dB (10-bit ADC)")
    print(f"\n3. Re-run comparison simulation with optimized values")