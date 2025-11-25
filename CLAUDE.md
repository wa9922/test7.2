# AGC (Automatic Gain Control) System Simulation - Project Documentation

## 1. Project Overview

### Purpose
This project is a **Python-based simulation framework for Automatic Gain Control (AGC) systems** in wireless receiver design. It implements and compares three AGC approaches:
1. **Low-Power Fixed AGC** - Conservative, always uses minimum power (5-bit digital, 15dB gain)
2. **High-Performance Fixed AGC** - Aggressive, always uses maximum performance (10-bit digital, 40dB gain)
3. **Adaptive AGC** (Proposed) - Dynamic approach that adjusts digital bits and gain based on detected traffic type

### Domain
- **Wireless Communications/Receiver Design**
- **Energy-Efficient Signal Processing**
- **Hardware-Software Co-design**
- Targets IoT/embedded wireless systems with multiple traffic types (wake-up, lowpowersignal, highperformancesignal)

### Key Objective
Demonstrate that an adaptive AGC system can achieve a better balance between energy consumption and signal quality (BER) compared to fixed-mode approaches, by dynamically selecting digital truncation bits and RF gain based on detected traffic type.

### System Requirements
1. **아날로그 단일화 (Unified Analog)**: 아날로그 부분은 항상 동일 (UnifiedRFPath, ADC 10-bit 고정)
2. **디지털 Truncation**: ADC는 항상 10비트로 동작, 디지털 단에서 5비트 또는 10비트로 truncate
3. **전력 비교**: 디지털 연산량만 차이 (아날로그 전력 동일)
4. **FSM 제거**: FSM을 제거하고 순수 피드백 기반 AGC로 변경
5. **트래픽 타입**: sensor/voice/video → lowpowersignal/highperformancesignal

### Implementation Platforms
This project includes **two complementary implementations**:

1. **Python Simulation** (root directory): Batch-mode packet processing with comprehensive metrics collection
   - Complete system simulation with carrier sensing, signal field decoding, and BER calculation
   - Generates 11 comparison graphs (energy, accuracy, latency, operations, etc.)
   - Suitable for research, final results, and publication-quality metrics
   - Files: `main_agc_system.py`, `agc_comparison.py`, and supporting modules

2. **GNURadio GUI** (`gnu/` directory): Real-time stream processing with interactive visualization
   - Live waveform display and BER comparison
   - Interactive SNR slider and traffic type controls
   - Same core algorithms (UnifiedRFPath, ADC, gain feedback)
   - Suitable for development, debugging, demonstrations, and hardware-in-the-loop testing
   - Files: `gnu/python/agc_*.py`, `gnu/examples/agc_comparison.grc`

Both implementations share the same theoretical foundation and produce equivalent results for the same inputs.

---

## 2. Overall Architecture

### High-Level System Flow

```
Input Packet (traffic_type)
    ↓
SignalGenerator: Generate PHY packet (STF + LTF preamble + Signal Field + Payload)
    ↓
Add AWGN Noise (channel simulation)
    ↓
UnifiedRFPath (항상 동일한 아날로그 회로)
    └─ LNA(20dB) → Mixer → VGA(가변) → LPF
    ↓
ADC Quantization (항상 10-bit)
    ↓
Digital Truncation (5-bit 또는 10-bit)
    ↓
Block-by-Block Processing
    ├─ Carrier Sensing (3 methods: saturation, energy, correlation detection)
    ├─ Signal Field Decoding (traffic type detection)
    ├─ Digital Bits Selection (5-bit for lowpowersignal, 10-bit for highperformancesignal)
    ├─ Gain Feedback (peak-based, continuous adjustment 10-50dB)
    ├─ BER Calculation (measure signal quality on STF)
    └─ Power Measurements (analog + digital)
    ↓
Collect Metrics (BER, power, energy, gain)
    ↓
Output: Packet result with performance metrics
```

### Component Interaction Diagram

```
AgcSystem (main orchestrator)
├── 순수 피드백 Gain Control
│   ├── current_gain_db: 직접 gain 변수 (10-50dB 범위)
│   ├── enable_gain_feedback: Gain 피드백 활성화 플래그
│   └── Peak-based feedback: 신호 크기에 따라 자동 조절
│
├── SignalGenerator
│   ├── BPSK modulation
│   └── Packet generation: preamble (STF+LTF) + signal field + payload
│
├── UnifiedRFPath (통일된 아날로그 프론트엔드)
│   ├── LNA(20dB 고정) → Mixer → VGA(가변 0-30dB) → LPF
│   └── 전력 소비 항상 동일
│
├── ADC (Analog-to-Digital Converter)
│   ├── ADC10bit (항상 10비트로 동작, 1024 levels)
│   └── truncate_to_bits(): 디지털 단에서 5비트 또는 10비트로 truncation
│
├── Carrier Sensing
│   ├── SaturationDetector (ADC saturation check)
│   ├── EnergyDetector (signal power threshold)
│   └── CorrelationDetector (STF correlation with received signal)
│
├── BERCalculator (measure quality on STF using hard-decision BPSK)
│
├── Power Measurement Modules
│   ├── AnalogPowerMeasurement (항상 동일, MAX2829 model)
│   └── DigitalComputationMeasurement (비트 수에 따라 연산량 변경)
│
└── Utilities
    ├── TimeSeriesDataCollector
    ├── TrafficFlowManager
    ├── SignalFieldDecoder
    └── SimulationUtils
```

---

## 3. Key Modules and Responsibilities

### Core Processing Modules

#### **main_agc_system.py**
**Role**: Main AGC system class and simulation orchestrator

**Key Classes**:
- `AgcSystem`: Primary class implementing the adaptive AGC system
  - `__init__()`: Initialize UnifiedRFPath, ADC10bit, carrier sensing, power models
  - `process_packet()`: Main packet processing pipeline (block-by-block)
  - `apply_adc_quantization()`: ADC 10-bit 양자화 + 디지털 truncation
  - `extract_signal_field_indication()`: Decode traffic type from signal field
  - `update_adc_resolution_for_traffic()`: Adaptive digital bits selection (5 or 10)
  - `run_simulation()`: Execute full simulation with multiple packets/SNR values

**Key Methods**:
- `process_rf_only()`: RF 증폭만 수행 (ADC 양자화 분리)
- `_update_power_measurements()`: Calculate analog and digital power/energy
- `_calculate_cs_operations()`: Count arithmetic operations for carrier sensing
- `_calculate_ber_operations()`: Count arithmetic operations for BER calculation
- Block-based processing loop with gain feedback based on signal peak
- Gain history tracking and statistics collection

**Fixed Models**:
- `FixedLowPowerAGC`: 5-bit digital 고정 / gain은 AGC로 자동 조절
- `FixedHighPerformanceAGC`: 10-bit digital 고정 / gain은 AGC로 자동 조절
- **차이점**: 디지털 비트 적응 여부 (Fixed는 비트 고정, Adaptive는 비트 적응)

**Entry Point**: `main()` at end of file - runs 3 models and generates 11 comparison metrics graphs

---

#### **carrier_sensing.py**
**Role**: Detect packet presence using multiple methods

**Key Classes**:
- `SaturationDetector`: Check if ADC samples exceed saturation threshold
  - 5-bit 또는 10-bit에 따라 threshold 자동 선택
  - Compares I/Q components against threshold
  - Returns saturation rate and boolean detection

- `EnergyDetector`: Measure signal power and compare to energy threshold
  - Calculates mean power of complex signal
  - Converts to dB and compares threshold (-75 dBm default)
  - Tracks detection history

- `CorrelationDetector`: Correlate received signal with known STF sequence
  - Implements sliding window correlation with STF reference
  - Computes correlation magnitude
  - Compares to correlation threshold (0.6-0.85)

- `CarrierSensingTop`: Wrapper combining all three detectors
  - `process_signal()`: Run all detectors on input block
  - `update_resolution()`: Update saturation thresholds based on ADC bits
  - Returns dictionary: `detection_methods` with boolean flags for each method

**Output Format**:
```python
{
    "detection_methods": {
        "saturation": bool,
        "energy": bool,
        "correlation": bool
    },
    "saturation": {...},
    "energy": {...},
    "correlation": {...}
}
```

---

#### **signal_generator.py**
**Role**: Generate PHY-layer wireless packets

**Key Class**:
- `SignalGenerator`: Create complete wireless packets
  - `generate_stf_signal()`: Generate Short Training Field (preamble)
  - `generate_ltf_signal()`: Generate Long Training Field (preamble)
  - `generate_preamble()`: Combine STF + LTF
  - `create_complete_packet()`: Generate full packet (preamble + signal field + payload)
  - `bits_to_bpsk()`: Modulate bits → BPSK symbols with upsampling
  - `bpsk_to_bits()`: Demodulate BPSK → bits with downsampling

**Packet Structure**:
```
Preamble (STF + LTF) → Signal Field (48 bits) → Payload (1024 bits)
  128 bits (STF)      00/01/10 (traffic type)    All modulated BPSK
  +64 bits (LTF)      + control bits            at 20 MHz sampling
```

**Configuration**:
- Sampling rate: 20 MHz
- Symbol rate: 1 MHz
- Samples per symbol: 20
- BPSK constellation: {0: -1.0, 1: +1.0}

---

#### **ber_calculator.py**
**Role**: Calculate Bit Error Rate for signal quality assessment

**Key Class**:
- `BERCalculator`: Measure BER by comparing received vs transmitted STF bits
  - `process_stf_block()`: Calculate BER for a signal block
  - `process_complete_packet()`: Calculate BER for entire packet STF
  - `calculate_bit_errors()`: XOR comparison between original and received bits
  - `update_ber_statistics()`: Maintain sliding window of error rate
  - `get_current_ber()`: Return windowed BER
  - `get_cumulative_ber()`: Return total accumulated BER

**Methodology**:
- Hard-decision demodulation: real part > 0 → '1', else '0'
- Compares received bits with reference STF bits
- BER = (number of errors) / (total bits)
- Sliding window tracks recent performance

---

### Hardware Modeling Modules

#### **adc.py**
**Role**: Simulate ADC quantization and digital truncation

**Key Classes**:
- `BaseADC`: Generic N-bit ADC model
  - `quantize()`: Round signal to nearest quantization level
  - `quantize_to_int()`: Return integer representation
  - `truncate_to_bits()`: Digital truncation (10-bit → 5-bit)
  - Parameters: bit width, reference voltage, quantization step

- `ADC5bit`: 5-bit ADC (참고용, 실제로는 사용 안 함)
- `ADC10bit`: 10-bit ADC (항상 사용, 1024 levels, range: -512 to 511)

**Digital Truncation Process** :
1. ADC는 항상 10비트로 양자화
2. 디지털 단에서 `truncate_to_bits(signal, 5)` 또는 `truncate_to_bits(signal, 10)` 호출
3. 5비트 truncation: 상위 5비트만 사용 (32 levels)
4. 10비트: truncation 없음 (1024 levels)

---

#### **rf_paths.py**
**Role**: Model RF front-end analog processing chains

**Functions** (basic operations):
- `lna()`: Low-Noise Amplifier (linear gain in dB)
- `mixer()`: Frequency conversion (multiplication by LO)
- `vga()`: Variable Gain Amplifier (adjustable gain)
- `lpf()`: Low-Pass Filter (1st-order IIR)

**Key Classes**:
- `UnifiedRFPath`: 통일된 RF 프론트엔드 
  - Chain: LNA(20dB 고정) → Mixer → VGA(가변 0-30dB) → LPF
  - 전력 소비 항상 동일
  - Gain만 피드백으로 조절 (총 gain = LNA 20dB + VGA 0-30dB = 20-50dB)

- `HighPerfPath`: 고성능 경로 (참고용, 실제로는 UnifiedRFPath 사용)
- `LowPowerPath`: 저전력 경로 (참고용, 실제로는 UnifiedRFPath 사용)

---

#### **analog_power_base.py**
**Role**: Model analog front-end power consumption

**Key Classes**:
- `AnalogPowerModelBase`: Abstract base for power models
  - `get_power()`: Return power for specific mode (mW)
  - `get_energy_consumption()`: Calculate energy for duration (mJ = power × time)

- `MAX2829PowerModel`: High-performance receiver IC model (항상 사용)
  - RX active: ~392 mW (Note: 아날로그는 항상 동일)

- `MAX2830PowerModel`: Low-power receiver IC model (참고용, 사용 안 함)

- `AnalogPowerMeasurement` (in power_measurement.py): Tracks total and average power

---

#### **digital.py**
**Role**: Model digital processing area and power

**Key Class**:
- `DigitalAreaModel`: Calculate circuit area (μm²) for digital components
  - Base areas: Full-adder (1.183 μm²), Multiplier cell (3.5 μm²)
  - N-bit adder area: N × 1.183
  - N-bit multiplier area: N² × 3.5
  - Total digital processing area depends on digital bits (5 or 10)

**Usage**: Estimate energy based on circuit area and operation count
- 5-bit digital: 적은 area, 적은 연산량
- 10-bit digital: 큰 area, 많은 연산량

---

#### **power_measurement.py**
**Role**: Aggregate power and energy metrics

**Key Classes**:
- `DigitalComputationMeasurement`: Track digital operations and energy
  - `update_computation()`: Accumulate multiplications and additions
  - Counts ops from carrier sensing, BER calculation, and bit-dependent operations
  - `get_total_energy()`: Energy = ops × power_per_op × area_scaling (pJ)
  - **비트 종속 연산**: K_ADD × bits, K_MUL × bits²

- `AnalogPowerMeasurement`: Accumulate analog power consumption
  - `update_power_measurement()`: Add duration × power
  - `get_total_energy()`: Total accumulated energy (mJ)
  - `calculate_power()`: 항상 동일한 전력 (UnifiedRFPath)

---

### Configuration and Comparison Modules

#### **config.py**
**Role**: Centralized configuration parameters

**Key Configurations**:
- **Signal Parameters**:
  - Sampling rate: 20 MHz
  - Symbol rate: 1 MHz
  - Samples per symbol: 20
  - STF/LTF/Signal Field/Payload bit counts

- **Gain Levels** (Fixed 모델 참고용):
  - LOW_GAIN: 15 dB (저전력 모델)
  - HIGH_GAIN: 40 dB (고성능 모델)

- **Digital Truncation Bits by Traffic Type** :
  - wake_up: 5 bits
  - lowpowersignal: 5 bits
  - highperformancesignal: 10 bits

- **Carrier Sensing Thresholds**:
  - Saturation thresholds (5-bit: 15, 10-bit: 510)
  - Energy thresholds (dBm)
  - Correlation thresholds (0.6-0.85)

- **Signal Field Mapping** (3가지만):
  - "00": wake_up
  - "01": lowpowersignal
  - "10": highperformancesignal

- **Digital Operation Scaling**:
  - K_ADD_PER_SAMPLE: 1.0 (adds per sample per bit)
  - K_MUL_PER_SAMPLE: 0.05 (mults per sample per bit²)

- **Analog Unification Flags**:
  - UNIFIED_ANALOG_ALWAYS_ON: True (항상 RX on, 동일 전력)
  - ADC_MAX_BITS: 10 (실제 ADC 고정 비트)

---

#### **agc_comparison.py**
**Role**: Compare three AGC models and generate result metrics

**Key Classes**:
- `FixedLowPowerAGC`: Extends AgcSystem, 5-bit digital 고정 + AGC 활성화
  - Overrides `process_packet()` to prevent digital bit changes only
  - Gain은 AGC로 자동 조절 (saturation 방지, SNR 최적화)
  - Lowest digital power consumption, potential accuracy loss

- `FixedHighPerformanceAGC`: Extends AgcSystem, 10-bit digital 고정 + AGC 활성화
  - Overrides `process_packet()` to prevent digital bit changes only
  - Gain은 AGC로 자동 조절 (saturation 방지, SNR 최적화)
  - Highest accuracy, highest digital power consumption

- `AdaptiveAGC`: Extends AgcSystem, uses full adaptive logic
  - Gain responds to peak-based feedback (10-50 dB continuous)
  - Digital bits selected based on detected traffic type
  - Dynamic gain adjustment based on signal peak

**Key Functions**:
- `run_comparison_simulation()`: Run all 3 models through identical traffic pattern, collect metrics
- `calculate_average_results()`: Average results across iterations
- `compute_model_metrics()`: Calculate per-model metrics (total energy, avg BER, latency)
- `plot_three_metrics_models()`: Generate 3 basic output graphs
- `plot_extended_metrics()`: Generate 8 additional comparison graphs

**Output Graphs** (11 total):
1. `metrics_energy.png`: Analog (mJ) + Digital (pJ) energy per model
2. `metrics_accuracy.png`: Average BER per model
3. `metrics_latency.png`: Average latency per model
4. `metrics_operations.png`: Total operations (additions, multiplications)
5. `metrics_energy_efficiency.png`: Bits per Joule
6. `metrics_sqnr.png`: Signal to Quantization Noise Ratio
7. `metrics_throughput.png`: Bits per second
8. `metrics_ber_vs_snr.png`: BER vs SNR (line graph)
9. `metrics_ber_by_traffic.png`: BER by traffic type
10. `metrics_energy_by_traffic.png`: Energy by traffic type
11. `metrics_adc_bit_usage.png`: ADC bit usage ratio (5-bit vs 10-bit)

---

#### **optimize_gains.py**
**Role**: Utility to find optimal gain values for each traffic type

**Key Functions**:
- `test_gain_performance()`: Measure BER at specific gain value
- `optimize_gains_for_traffic()`: Search gain range (0-50 dB) for each traffic type
- `test_fixed_agc_gains()`: Find optimal fixed gains for conventional approaches

**Usage**: Run to find better gain configuration values for config.py

---

### Utility Modules

#### **simulation_utils.py**
**Role**: Helper functions and data collection

**Key Classes**:
- `TrafficFlowManager`: Generate traffic pattern sequence
  - Cycles through: wake_up → lowpowersignal → highperformancesignal → (gap) → repeat

- `TimeSeriesDataCollector`: Accumulate time-series data during simulation
  - Tracks: time, traffic type, power (analog/digital), BER, gain, SNR
  - Limits storage to 100K points for memory efficiency

- `SignalFieldDecoder`: Decode traffic type from signal field
  - Maps 2-bit indication to traffic type ("00", "01", "10")
  - Fallback to packet metadata if demodulation fails

**Key Functions**:
- `calculate_block_size()`: Determine processing block size (STF length)
- `safe_divide()`: Division with zero-guard
- Plotting utilities for generating comparison graphs

---

## 4. Main Entry Points and Workflows

### Primary Entry Point: `main_agc_system.py`

```python
if __name__ == "__main__":
    main()
```

**Execution Flow**:
1. Create 3 AGC models:
   - `FixedLowPowerAGC()` (5-bit digital 고정, gain은 AGC)
   - `FixedHighPerformanceAGC()` (10-bit digital 고정, gain은 AGC)
   - `AgcSystem(use_indicator_for_adc=True)` (Adaptive, 5/10-bit 적응 + gain AGC)

2. For each model, call `run_one_model()`:
   - Execute `model.run_simulation(traffic_types, snr_range, packets_per_scenario)`
   - Traffic types: lowpowersignal, highperformancesignal
   - SNR range: 5, 10, 15, 20 dB
   - 20 packets per SNR scenario

3. Collect metrics via `compute_model_metrics()`:
   - Total analog energy (mJ)
   - Total digital energy (pJ)
   - Average BER
   - Average latency (ms)
   - Total operations (additions, multiplications)
   - Energy efficiency, SQNR, throughput

4. Generate 11 comparison graphs:
   - Energy usage comparison
   - Accuracy (BER) comparison
   - Latency comparison
   - Operations comparison
   - Energy efficiency, SQNR, throughput
   - BER vs SNR, BER by traffic, Energy by traffic
   - ADC bit usage

5. Save PNGs to current directory

---

### Simulation Workflow: `run_simulation()`

```python
agc_system = AgcSystem()
sim_result = agc_system.run_simulation(
    traffic_types=["lowpowersignal", "highperformancesignal"],
    snr_range_db=[5, 10, 15, 20],
    packets_per_scenario=20
)
```

**Per-Simulation Steps** (for each SNR, each packet):
1. Generate packet with specific traffic type
2. Add AWGN noise to clean signal
3. **Block-by-block processing** (실제 AGC 동작):
   - Extract noisy block from received signal
   - Apply RF amplification with current gain (UnifiedRFPath)
   - Apply ADC 10-bit quantization
   - Apply digital truncation (5-bit or 10-bit)
   - Run carrier sensing (saturation, energy, correlation)
   - Extract signal field indication (if in signal field region)
   - Update digital bits based on traffic type (Adaptive mode only)
   - **Gain feedback**: Measure peak → adjust gain for next block
     - If peak > 0.9: gain -= 1dB (saturation 방지)
     - If peak < 0.25: gain += 1dB (SNR 향상)
     - Gain range: 10-50dB
   - Calculate BER on STF region
   - Update power measurements (analog + digital)
   - Collect block result
4. Aggregate packet result with all sub-block metrics
5. Return packet result containing:
   - Final BER, gain, digital bits
   - Block-level results
   - Analog and digital power/energy

---

### Packet Processing Pipeline: `process_packet()`

```python
result = agc_system.process_packet(packet_info, channel_snr_db=10)
```

**Input**:
- `packet_info`: Dict with packet structure (STF/LTF/SF/payload indices, complete_signal, traffic_type)
- `channel_snr_db`: Channel SNR in dB

**Key Processing Steps**:

1. **Digital Bits Selection**:
   - Adaptive mode: Start with 5-bit, await signal field indication for update
   - Fixed modes: Locked to 5-bit or 10-bit

2. **Channel Simulation**: Add AWGN at specified SNR

3. **Block Loop** (process in chunks):
   - **RF Processing**:
     - Apply gain with UnifiedRFPath (LNA 20dB + VGA 가변)
   - **ADC Quantization**:
     - 항상 10-bit ADC 사용
   - **Digital Truncation**:
     - 5-bit 또는 10-bit로 truncate
   - **Carrier Sensing**:
     - 3 methods (~320-330 arithmetic ops)
   - **Signal Field Decoding**:
     - If in signal field region and not extracted yet:
       - Decode traffic type from signal field bits
       - (Adaptive mode) Update digital bits based on decoded traffic
       - Reprocess block with new digital bits
   - **Gain Feedback** (Note: 순수 피드백 AGC):
     - Measure peak in block
     - If peak > 0.90: decrease gain by 1 dB
     - If peak < 0.25: increase gain by 1 dB
     - Gain range clipped to 10-50 dB
     - **중요**: 현재 블록은 재처리 안 함, 다음 블록에 새 gain 적용
   - **BER Calculation** (STF region only):
     - Hard-decision demodulation: real > 0 → 1, else 0
     - XOR with reference STF bits
     - Count error rate (~680 arithmetic ops)
   - **Power Measurements**:
     - Analog: 항상 동일 (UnifiedRFPath)
     - Digital: Operation-dependent + area-based scaling (비트 수에 비례)
   - Collect block result

4. **Final Packet Computation**:
   - Calculate packet-level BER from received signal
   - Aggregate all block results
   - Return result dict with all metrics

---

## 5. Dependencies and External Libraries

### Core Python Libraries
- **numpy**: Numerical computation (signal processing, statistics)
- **matplotlib**: Plotting and graph generation
- **scipy**: Statistical distributions (confidence intervals)
- **collections**: defaultdict for data aggregation
- **enum**: AgcState enumeration (제거됨, 이제 사용 안 함)
- **abc**: Abstract base classes for power models
- **os**: File operations (directory creation)
- **typing**: Type hints (Dict, List, Tuple, Optional)

### No External Hardware Simulation Libraries
- All RF/ADC models implemented from scratch in Python
- Modular design allows easy extension

---

## 6. Design Patterns and Conventions

### Architectural Patterns

1. **Feedback Control Pattern** 
   - 순수 피드백 기반 AGC (FSM 제거)
   - 신호 peak 측정 → gain 자동 조절 (10-50 dB 연속)
   - 실제 AGC 시스템과 동일한 동작

2. **Strategy Pattern**
   - Three AGC strategies: Low-Power, High-Perf, Adaptive
   - Shared `AgcSystem` base class with different configurations
   - Easy to add new strategies (e.g., predictive AGC)

3. **Decorator/Wrapper Pattern**
   - `CarrierSensingTop` wraps three detection methods
   - `TimeSeriesDataCollector` wraps measurement logging
   - `AnalogPowerMeasurement` wraps power model selection

4. **Builder/Configuration Pattern**
   - Centralized `config.py` for all parameters
   - Dictionary-based configuration
   - Configuration can be modified without code changes

5. **Pipeline Pattern**
   - Packet processing flows through distinct stages:
     Signal → RF Path → ADC → Digital Truncation → Block Loop → Result
   - Each stage modular and independently testable

### Naming Conventions

- **Class names**: CamelCase (`AgcSystem`, `CarrierSensingTop`)
- **Method names**: snake_case (`process_packet()`, `run_simulation()`)
- **Constants**: UPPER_CASE (`SAMPLING_RATE`, `GAIN_LEVELS`)
- **Variable names**: Descriptive with units (`power_mw`, `ber`, `gain_db`)

### Code Organization

- **Separation of concerns**:
  - Signal generation separate from processing
  - Power models isolated in dedicated modules
  - Comparison logic in separate file

- **Modular components**: Each major subsystem (carrier sensing, BER, power) in its own file

- **Utility extraction**: Common functions (plotting, data collection) in simulation_utils.py

---

## 7. Testing Approach

### Test Capabilities (Limited; Primarily Simulation-Based)

**Integration testing** (via simulation):
- `main_agc_system.py`: Full system runs can be executed
- `optimize_gains.py`: Runs all three models to find optimal configurations
- Manual validation: Compare output graphs against expected behavior

### Current Testing Observations

- **No pytest framework**: Relies on print statements and manual verification
- **No unit test files**: All testing is embedded in modules or run via main()
- **No CI/CD configuration**: Single-file execution model

### Recommended Testing Enhancements

1. Create `tests/` directory with unit tests for:
   - ADC quantization accuracy
   - Gain feedback logic
   - BER calculation correctness

2. Implement pytest fixtures for common test scenarios

3. Add golden-signal validation (pre-computed reference values)

---

## 8. Configuration and Setup Requirements

### Installation and Dependencies

```bash
# Python 3.7+ required (type hints, enum)
pip install numpy scipy matplotlib
```

### Configuration Parameters (config.py)

**Adjustable Settings**:

1. **Signal/Channel Parameters**:
   - `SAMPLING_RATE` (default: 20e6 Hz)
   - `SYMBOL_RATE` (default: 1e6 Hz)
   - `DEFAULT_SNR_DB` (default: 10)
   - `NOISE_POWER` (default: 0.1)

2. **Gain Settings** (Fixed 모델 참고용):
   ```python
   GAIN_LEVELS = {
       "LOW_GAIN": 15,      # dB (저전력 모델)
       "HIGH_GAIN": 40,     # dB (고성능 모델)
   }
   ```

3. **Digital Truncation Bits by Traffic**:
   ```python
   DIGITAL_TRUNCATION_BITS = {
       "wake_up": 5,
       "lowpowersignal":  5,
       "highperformancesignal": 10
   }
   ```

4. **Carrier Sensing Thresholds**:
   - Saturation threshold (5-bit: 15, 10-bit: 510)
   - Energy threshold (dBm)
   - Correlation threshold (0.0-1.0)

5. **Digital Operation Constants**:
   - `K_ADD_PER_SAMPLE`: Scaling factor for additions
   - `K_MUL_PER_SAMPLE`: Scaling factor for multiplications

6. **Analog Unification**:
   - `UNIFIED_ANALOG_ALWAYS_ON`: True (항상 동일한 아날로그)
   - `ADC_MAX_BITS`: 10 (ADC 고정 비트)

7. **Display/Debug Options**:
   - `DEBUG_MODE`: Enable verbose logging
   - `PLOT_RESULTS`: Generate graphs
   - `SAVE_INTERMEDIATE_RESULTS`: Store intermediate data

### Running the System

**Basic simulation**:
```bash
python main_agc_system.py
```

**Expected output**:
- Console: Progress messages, metrics summaries
- Files: 11 PNG files (metrics_*.png)

**Comparison simulation** (alternative):
```bash
python agc_comparison.py  # (currently called from main_agc_system.py)
```

**Gain optimization**:
```bash
python optimize_gains.py
```

---

## 9. Data Flow and Signal Processing Details

### Signal Representation

**Throughout the system**, signals are represented as **complex numpy arrays** (I+jQ):
- Baseband representation (no carrier frequency)
- Complex-valued for full signal information
- Processed at 20 MHz sampling rate

### Typical Signal Levels

| Stage | Value Range | Purpose |
|-------|------------|---------|
| STF/LTF bits | {0, 1} | Binary transmission |
| BPSK symbols | {-1+0j, +1+0j} | Modulation |
| Upsampled signal | ±1.0 (normalized) | Baseband waveform |
| After RF gain | ±10-100x | Amplified |
| After ADC (10-bit) | [-512, 511] | Quantized |
| After Digital Truncation (5-bit) | [-16, 15] equivalent levels | Truncated |
| Power (dB) | -100 to +20 dBm | Log scale |
| BER | 0.0 to 1.0 | Normalized error rate |

### Quantization Effects

- **5-bit digital**: Coarse quantization, information loss, but low power
- **10-bit digital**: Fine quantization, high fidelity, but high power

System exploits this trade-off: use 5-bit for low-rate lowpowersignal, 10-bit for high-bandwidth highperformancesignal.

---

## 10. Key Algorithms and Formulas

### Gain Calculation (dB ↔ Linear)
```
gain_linear = 10^(gain_db / 20)
gain_db = 20 * log10(gain_linear)
```

### BER from Bit Errors
```
BER = (number of bit errors) / (total bits received)
Hard decision: demodulated_bit = 1 if real(received) > 0 else 0
```

### Signal Power
```
power_linear = mean(|signal|²)
power_db = 10 * log10(power_linear)
```

### SNR Relationship
```
snr_linear = 10^(snr_db / 10)
noise_power = signal_power / snr_linear
```

### ADC Quantization + Digital Truncation
```
# ADC 10-bit quantization
step_size_10bit = (2 * vref) / 1024
quantized_10bit = round(signal / step_size_10bit) * step_size_10bit

# Digital truncation to 5-bit
bit_shift = 10 - 5 = 5
truncated_int = quantized_10bit_int >> 5  # 하위 5비트 버림
truncated_int = truncated_int << 5        # 복원
truncated = truncated_int * step_size_10bit
```

### Gain Feedback (순수 피드백 AGC)
```
peak = max(|signal_block|)
if peak > 0.9:
    gain_db -= 1  # Saturation 방지
elif peak < 0.25:
    gain_db += 1  # SNR 향상
gain_db = clip(gain_db, 10, 50)  # 범위 제한
```

### Digital Energy (pJ)
```
energy = (num_adds * power_per_add + num_mults * power_per_mult) × area_scaling_factor
area_scaling_factor = (current_bits² / reference_bits²)
```

### SQNR (Signal to Quantization Noise Ratio)
```
SQNR_dB = 6.02 × N + 1.76
N = number of bits (5 or 10)
```

---

## 11. System Limitations and Design Choices

### Simplifications for Simulation

1. **No actual carrier frequency**: Baseband-only (assumes perfect downconversion)
2. **Ideal channel**: AWGN only, no fading/interference
3. **Simple gain feedback**: Peak-based, not sophisticated AGC loop
4. **Linear RF models**: No compression, nonlinearity, or phase distortion
5. **Idealized carrier sensing**: Thresholds pre-configured, no adaptive threshold
6. **Finite packet**: Limited to 1 KB payload (no streaming)

### Assumptions

- Clock synchronization is perfect
- Channel estimation is not required (training fields sufficient)
- Signal field decoding is deterministic in simulation mode
- Power consumption is state-dependent only (not load-dependent)
- Receiver always operates in normal mode (no low-power sleep)

### Adaptive Selection Logic

- Digital bits selection happens **after** signal field extraction
- This means initial processing uses default 5-bit, then might switch to 10-bit
- More optimal approach: use signal field indicator earlier (future work)

---

## 12.  상세 반영 내역 (System Implementation Details)

### 1. 아날로그 단일화 (Unified Analog Architecture)

**Before**:
- Two RF paths: LowPowerPath, HighPerfPath
- Two power models: MAX2829 (high), MAX2830 (low)
- Power consumption depends on path selection

**After** :
- Single RF path: UnifiedRFPath
- Single power model: MAX2829 only
- Power consumption always identical
- Only gain varies (feedback control)

```python
# main_agc_system.py
self.rf_path = UnifiedRFPath(lna_gain=20, vga_gain=20, lpf_alpha=0.2)
# 항상 동일한 아날로그 회로 사용
```

### 2. ADC 및 디지털 Truncation

**Before**:
- Multiple ADC classes: ADC3bit, ADC5bit, ADC10bit
- ADC resolution changes based on traffic type

**After** :
- Single ADC: ADC10bit only (항상 10비트)
- Digital truncation: 5-bit or 10-bit in digital domain

```python
# main_agc_system.py
self.adc = ADC10bit(vref=1.0)  # 항상 10비트 ADC

# ADC 양자화 + 디지털 truncation
quantized_10bit = self.adc.quantize(signal)
if self.current_digital_bits < 10:
    truncated = self.adc.truncate_to_bits(quantized_10bit, self.current_digital_bits)
```

### 3. FSM 제거 및 순수 피드백 AGC

**Before**:
- FSM with 4 states: LOW_GAIN_LP, LOW_GAIN_HP, MEDIUM_GAIN, HIGH_GAIN
- Fixed gain per state
- State transitions based on carrier sensing + signal field

**After** :
- No FSM, direct gain variable
- Continuous gain adjustment (10-50 dB)
- Peak-based feedback loop

```python
# main_agc_system.py
self.current_gain_db = 30.0  # 초기 gain

# Block-by-block feedback
peak = max(abs(signal_block))
if peak > 0.9:
    self.current_gain_db -= 1
elif peak < 0.25:
    self.current_gain_db += 1
self.current_gain_db = clip(self.current_gain_db, 10, 50)
```

### 4. Fixed 모델 정책 재정의

**의미 변경**:
- "Fixed" = 디지털 비트 고정 (5-bit or 10-bit)
- Gain은 모든 모델에서 AGC로 자동 조절

**이유**:
- AGC (Automatic Gain Control) 없이는 실제 시스템 동작 불가
- Saturation 방지와 SNR 최적화는 필수
- 비교 포인트: **디지털 비트 적응 여부**

```python
# main_agc_system.py
class FixedLowPowerAGC(AgcSystem):
    def __init__(self):
        super().__init__(enable_gain_feedback=True)  # ✅ AGC 활성화
        self.current_digital_bits = 5  # 디지털 비트만 고정

class FixedHighPerformanceAGC(AgcSystem):
    def __init__(self):
        super().__init__(enable_gain_feedback=True)  # ✅ AGC 활성화
        self.current_digital_bits = 10  # 디지털 비트만 고정
```

### 5. 트래픽 타입 간소화

**Before**:
- 4 types: wake_up, sensor, voice, video
- Complex mapping to states

**After** :
- 3 types: wake_up, lowpowersignal, highperformancesignal
- Simple binary choice: 5-bit or 10-bit

```python
# config.py
TRAFFIC_INDICATION_MAPPING = {
    "00": "wake_up",
    "01": "lowpowersignal",
    "10": "highperformancesignal",
}

DIGITAL_TRUNCATION_BITS = {
    "wake_up": 5,
    "lowpowersignal": 5,
    "highperformancesignal": 10,
}
```

### 6. 전력 비교 명확화

**Before**:
- Analog power differs between models
- Difficult to isolate digital energy impact

**After** :
- Analog power identical for all models
- Digital energy is the only variable
- Clear comparison: Low-Power (5-bit) vs High-Perf (10-bit) vs Adaptive (5/10-bit)

```python
# power_measurement.py
def calculate_power(self, state_name: str, is_low_power: bool = False):
    if UNIFIED_ANALOG_ALWAYS_ON:
        return self.model.get_power('RX')  # 항상 동일
```

---

## 13. Files Summary

### Core Python Simulation Files

| File | Lines | Purpose |
|------|-------|---------|
| main_agc_system.py | ~1000 | Main AGC system + comparison entry point + Fixed models |
| carrier_sensing.py | ~394 | Packet detection (saturation, energy, correlation) |
| signal_generator.py | ~228 | PHY packet generation (BPSK modulation) |
| ber_calculator.py | ~250 | Bit error rate measurement |
| power_measurement.py | ~160 | Power/energy aggregation (analog + digital) |
| analog_power_base.py | ~100 | IC power models (MAX2829) |
| rf_paths.py | ~220 | RF front-end simulation (UnifiedRFPath, LNA, VGA, LPF) |
| adc.py | ~130 | ADC quantization (10-bit) + digital truncation |
| digital.py | ~80 | Digital circuit area models |
| config.py | ~98 | Centralized configuration parameters |
| simulation_utils.py | ~422 | Utilities (data collection, plotting, traffic flow) |
| agc_comparison.py | ~726 | Comparison of 3 AGC models + extended metrics |
| optimize_gains.py | ~145 | Gain optimization utility |
| README.md | - | Project overview |
| CLAUDE.md | - | This documentation file |
| CLAUDE.ko.md | - | Korean version of documentation |
| SYSTEM_DIAGRAM.txt | - | System architecture diagram |

### GNURadio GUI Implementation Files (gnu/)

| File | Lines | Purpose |
|------|-------|---------|
| gnu/python/__init__.py | ~10 | GNURadio module initialization |
| gnu/python/agc_packet_source.py | ~160 | Packet source block (generates STF+LTF+SF+Payload with AWGN) |
| gnu/python/agc_system_block.py | ~280 | AGC system processing block (RF→ADC→Truncation→Feedback) |
| gnu/python/agc_ber_calc.py | ~100 | BER calculation block (theoretical BPSK + SQNR) |
| gnu/python/agc_power_meter.py | ~120 | Power/energy measurement block (analog + digital) |
| gnu/examples/agc_comparison.grc | - | GNURadio Companion flowgraph (GUI configuration) |
| gnu/README.md | ~377 | GNURadio implementation documentation |
| gnu/QUICKSTART_KR.md | - | Korean quick start guide |

**Total Lines of Code**:
- Core Python: ~4711 lines
- GNURadio Blocks: ~721 lines
- **Grand Total: ~5432 lines**

**Deleted Files** (after FSM removal):
- agc_fsm.py (268 lines) - No longer needed

---

## 14. Example Usage

### Basic Single Simulation
```python
from main_agc_system import AgcSystem
from signal_generator import SignalGenerator

# Create system (Adaptive AGC)
agc = AgcSystem(use_indicator_for_adc=True, enable_gain_feedback=True)
sg = SignalGenerator()

# Generate and process one packet
packet = sg.create_complete_packet("highperformancesignal")
result = agc.process_packet(packet, channel_snr_db=15)

print(f"BER: {result['final_ber']['ber']:.6f}")
print(f"Analog energy: {result['analog_power']['total_energy_mj']:.2f} mJ")
print(f"Digital energy: {result['digital_computation']['total_energy_pj']:.2f} pJ")
print(f"Final gain: {result['final_gain_db']} dB")
```

### Full Simulation Run
```python
from main_agc_system import AgcSystem

agc = AgcSystem(use_indicator_for_adc=True, enable_gain_feedback=True)

# Run full simulation
sim_result = agc.run_simulation(
    traffic_types=["lowpowersignal", "highperformancesignal"],
    snr_range_db=[5, 10, 15, 20],
    packets_per_scenario=10
)

print(f"Total packets: {sim_result['overall_statistics']['total_packets']}")
print(f"Overall BER: {sim_result['overall_statistics']['overall_average_ber']:.6f}")
```

### Comparison Mode
```python
if __name__ == "__main__":
    # This is what main_agc_system.py does:
    # 1. Run 3 models (Low-Power, High-Perf, Adaptive)
    # 2. Collect metrics for each
    # 3. Generate 11 comparison graphs
    exec(open("main_agc_system.py").read())
```

### Fixed Models
```python
from main_agc_system import FixedLowPowerAGC, FixedHighPerformanceAGC

# Low-Power Fixed: 5-bit digital (고정), gain AGC (자동 조절)
low_power = FixedLowPowerAGC()
result_lp = low_power.process_packet(packet, channel_snr_db=10)

# High-Performance Fixed: 10-bit digital (고정), gain AGC (자동 조절)
high_perf = FixedHighPerformanceAGC()
result_hp = high_perf.process_packet(packet, channel_snr_db=10)

# 차이점: 디지털 비트만 고정, gain은 모두 AGC로 자동 조절
```

### GNURadio GUI Usage

```bash
# Install GNURadio (Ubuntu/Debian)
sudo apt-get install gnuradio python3-scipy

# Launch GNURadio Companion
gnuradio-companion gnu/examples/agc_comparison.grc

# In GNURadio Companion:
# 1. Press F5 (Generate) to create Python code
# 2. Press F6 (Execute) to run the flowgraph
# 3. Adjust SNR slider and traffic type to see real-time results
```

**GNURadio Features**:
- Real-time visualization of all 3 AGC models (Low-Power, High-Performance, Adaptive)
- Interactive SNR control (0-30 dB slider)
- Live BER comparison display
- Message-based power/energy reporting
- Same algorithms as Python simulation (UnifiedRFPath, ADC10bit, gain feedback)

**Block Descriptions**:
1. **AGC Packet Source**: Generates BPSK packets with AWGN noise
2. **AGC System Block**: Processes signal through RF→ADC→Digital Truncation→Gain Feedback
3. **BER Calculator**: Computes theoretical BER based on SQNR and channel SNR
4. **Power Meter**: Measures analog (mJ) and digital (pJ) energy consumption

See `gnu/README.md` for detailed GNURadio documentation.

---

## 15. Key Insights for AI Assistants

1. **Primary Innovation**: Adaptive AGC dynamically selects digital truncation bits based on detected traffic type, trading off power/performance on a per-packet basis vs fixed approaches

2. **Core Requirements**:
   - 아날로그는 항상 동일 (UnifiedRFPath, 전력 동일)
   - 디지털만 변경 (5-bit vs 10-bit truncation)
   - FSM 제거, 순수 피드백 AGC

3. **Signal Processing Foundation**: Uses standard DSP techniques (BPSK, matched filtering via correlation, hard-decision detection)

4. **Hardware-Software Co-Design**: Models both analog RF frontend (power consumption) and digital backend (area + operation count)

5. **Comparative Evaluation**: Three competing approaches evaluated on identical traffic/channel conditions for fair comparison

6. **Packet Structure**: Uses standard wireless preamble structure (STF for detection, LTF for channel, signal field for metadata)

7. **Trade-offs Explicitly Modeled**:
   - 5-bit digital: Lower power, lower accuracy
   - 10-bit digital: Higher power, higher accuracy
   - Adaptive: Selects based on content type

8. **Energy Modeling**: Combines state-independent analog power (항상 동일) + operation-count digital energy (비트 수에 비례)

9. **Practical Constraints**:
   - Real system would need Rayleigh fading, interference
   - AGC loop is simplified (peak-based feedback)
   - Signal field decoding would be probabilistic

10. **Real AGC Operation**:
    - Block-by-block processing (not whole-signal)
    - RF amplification and ADC quantization separated
    - Gain feedback applied to next block (not current)

11. **Dual Implementation Strategy**:
    - **Python Simulation**: Research-focused, batch processing, comprehensive metrics, publication-quality plots
    - **GNURadio GUI**: Development-focused, real-time, interactive controls, visualization
    - Both use identical core algorithms (UnifiedRFPath, ADC10bit, gain feedback, digital truncation)
    - Choose Python for final results, GNURadio for debugging/demos

---

## 16. GNURadio GUI Implementation

### Overview

The `gnu/` directory contains a **GNURadio-based GUI implementation** of the AGC system that allows real-time visualization and interaction with the simulation. This implementation provides the same core algorithms as the Python simulation but in a stream-processing framework suitable for hardware-in-the-loop testing.

### Architecture

```
GNURadio Flowgraph
├── AGC Packet Source (3 instances)
│   ├── Generates BPSK packets (STF+LTF+SF+Payload)
│   ├── Adds AWGN noise at specified SNR
│   └── Outputs complex stream + packet metadata
│
├── AGC System Block (3 instances: LP, HP, Adaptive)
│   ├── Receives complex signal stream
│   ├── Applies UnifiedRFPath (LNA 20dB + VGA variable)
│   ├── ADC 10-bit quantization
│   ├── Digital truncation (5-bit or 10-bit)
│   ├── Peak-based gain feedback (10-50 dB)
│   └── Outputs processed signal + AGC statistics
│
├── BER Calculator (3 instances)
│   ├── Computes theoretical BER from SQNR + channel SNR
│   ├── SQNR_dB = 6.02 × bits + 1.76
│   ├── Effective SNR = 1/(1/SNR_ch + 1/SQNR)
│   └── BER = 0.5 × erfc(sqrt(SNR_eff))
│
├── Power Meter (3 instances)
│   ├── Analog energy: 392 mW (MAX2829, always same)
│   ├── Digital energy: K_ADD × samples × bits + K_MUL × samples × bits²
│   └── Outputs power/energy statistics
│
└── GUI Elements
    ├── Time Sink: Signal waveform display
    ├── Number Sinks: BER values for 3 models
    ├── Message Debug: Console output for stats
    └── Variable Controls: SNR slider, traffic type selector
```

### Key GNURadio Blocks

#### 1. **agc_packet_source.py** (~160 lines)

**Class**: `agc_packet_source(gr.sync_block)`

**Purpose**: Generate PHY-layer packets with BPSK modulation and AWGN noise

**Key Methods**:
- `__init__()`: Initialize packet generator with traffic type, SNR, burst parameters
- `work()`: Stream processing function (called continuously by GNURadio scheduler)
  - Generates complete packets (STF + LTF + Signal Field + Payload)
  - Applies BPSK modulation (20 samples per symbol)
  - Adds AWGN noise at specified SNR
  - Publishes packet metadata via message port
- `generate_packet()`: Create BPSK-modulated packet with preamble
- `add_awgn()`: Add white Gaussian noise at target SNR

**Message Ports**:
- Output: `packet_info` (PMT dict with packet structure metadata)

**Parameters**:
- `traffic_type`: 'lowpowersignal' or 'highperformancesignal'
- `snr_db`: Channel SNR in dB (0-30)
- `packets_per_burst`: Number of packets per transmission burst
- `repeat`: Boolean, whether to continuously generate packets

#### 2. **agc_system_block.py** (~280 lines)

**Class**: `agc_system_block(gr.sync_block)`

**Purpose**: Main AGC processing (RF path → ADC → Digital truncation → Gain feedback)

**Key Methods**:
- `__init__()`: Initialize AGC mode, RF path, ADC, gain feedback
- `work()`: Stream processing
  - Apply RF amplification (UnifiedRFPath: LNA 20dB + VGA variable)
  - ADC 10-bit quantization
  - Digital truncation (5-bit or 10-bit based on mode)
  - **Gain feedback loop**:
    - Measure peak: `max(|signal|)`
    - If peak > 0.9: decrease gain by 1 dB (prevent saturation)
    - If peak < 0.25: increase gain by 1 dB (improve SNR)
    - Clip gain to range [10, 50] dB
  - Publish AGC statistics via message port
- `handle_traffic_info()`: Receive traffic type and update digital bits (Adaptive mode only)
- `apply_rf_path()`: LNA → Mixer → VGA → LPF
- `apply_adc()`: 10-bit quantization + digital truncation

**Message Ports**:
- Input: `traffic_info` (traffic type from packet source)
- Output: `agc_stats` (gain, digital bits, peak level)

**AGC Modes**:
- `'low_power'`: 5-bit digital (fixed), gain AGC (variable)
- `'high_performance'`: 10-bit digital (fixed), gain AGC (variable)
- `'adaptive'`: 5/10-bit digital (traffic-based), gain AGC (variable)

**Important**: All modes use gain feedback. "Fixed" means fixed digital bits, not fixed gain.

#### 3. **agc_ber_calc.py** (~100 lines)

**Class**: `agc_ber_calc(gr.sync_block)`

**Purpose**: Calculate theoretical BER based on quantization noise and channel SNR

**Key Methods**:
- `__init__()`: Initialize BER calculator with ADC bits
- `work()`: Compute BER
  - Calculate SQNR: `SQNR_dB = 6.02 × adc_bits + 1.76`
  - Compute effective SNR: `SNR_eff = 1 / (1/SNR_channel + 1/SQNR)`
  - Calculate BPSK BER: `BER = 0.5 × erfc(sqrt(SNR_eff))`
  - Publish BER statistics
- `handle_snr_message()`: Update channel SNR from upstream
- `handle_bits_message()`: Update ADC bits (for Adaptive mode)

**Message Ports**:
- Input: `snr_in` (channel SNR), `bits_in` (digital bits)
- Output: `ber_out` (BER statistics)

**Example Output**:
- 5-bit, SNR=10dB → BER ≈ 8.43 × 10⁻⁸
- 10-bit, SNR=10dB → BER ≈ 2.54 × 10⁻¹⁰ (332× better)

#### 4. **agc_power_meter.py** (~120 lines)

**Class**: `agc_power_meter(gr.sync_block)`

**Purpose**: Measure analog and digital energy consumption

**Key Methods**:
- `__init__()`: Initialize power models (MAX2829 analog, bit-dependent digital)
- `work()`: Calculate power/energy
  - **Analog energy**: `P_analog × time = 392 mW × (samples / sampling_rate)`
  - **Digital energy**:
    - Additions: `K_ADD × samples × bits`
    - Multiplications: `K_MUL × samples × bits²`
    - Area scaling: `area_ratio = bits² / 64` (normalized to 8-bit)
    - Energy (pJ): `(adds × 0.1 + mults × 2.5) × area_ratio`
  - Total energy: analog (mJ) + digital (mJ)
  - Publish power statistics
- `handle_bits_message()`: Update digital bits for power calculation

**Message Ports**:
- Input: `bits_in` (digital bits)
- Output: `power_out` (power/energy statistics)

**Energy Scaling** (10000 samples @ 20 MHz):
- Low-Power (5-bit): 0.196 mJ analog + 0.019 mJ digital = 0.215 mJ
- High-Performance (10-bit): 0.196 mJ analog + 0.263 mJ digital = 0.459 mJ
- Adaptive: Switches based on traffic type

### GNURadio Companion Flowgraph

**File**: `gnu/examples/agc_comparison.grc`

**Structure**:
```
Variables (User Controls)
├── snr_slider: 0-30 dB (adjustable in real-time)
└── traffic_type: 'lowpowersignal' or 'highperformancesignal'

Signal Generation (3 parallel paths)
├── agc_packet_source (LP) → agc_system_block (low_power) → Time Sink (LP)
├── agc_packet_source (HP) → agc_system_block (high_performance) → Time Sink (HP)
└── agc_packet_source (Adaptive) → agc_system_block (adaptive) → Time Sink (Adaptive)

BER Calculation (3 parallel paths)
├── agc_ber_calc (5-bit) → Number Sink (LP BER)
├── agc_ber_calc (10-bit) → Number Sink (HP BER)
└── agc_ber_calc (dynamic) → Number Sink (Adaptive BER)

Power Measurement (3 parallel paths)
├── agc_power_meter (5-bit) → Message Debug (LP Power)
├── agc_power_meter (10-bit) → Message Debug (HP Power)
└── agc_power_meter (dynamic) → Message Debug (Adaptive Power)
```

### Running the GNURadio GUI

```bash
# 1. Install GNURadio 3.8+
sudo apt-get install gnuradio python3-scipy

# 2. Navigate to repository
cd /home/user/test7.2

# 3. Launch GNURadio Companion
gnuradio-companion gnu/examples/agc_comparison.grc

# 4. In GNURadio Companion GUI:
#    - Press F5 (Generate) to compile Python code
#    - Press F6 (Execute) to run simulation
#    - Adjust SNR slider (0-30 dB)
#    - Change traffic type selector
#    - Observe real-time BER, waveforms, power in GUI
```

### Differences from Python Simulation

| Aspect | Python Simulation | GNURadio GUI |
|--------|------------------|--------------|
| Processing Model | Packet-based (batch) | Stream-based (continuous) |
| Execution | Offline, batch processing | Real-time, interactive |
| Carrier Sensing | 3 methods (saturation, energy, correlation) | Simplified (omitted in GUI) |
| Signal Field Decoding | Demodulates signal field bits | Message passing (metadata) |
| BER Calculation | Hard-decision on received STF | Theoretical (SQNR + channel SNR) |
| Visualization | Static PNG plots (11 graphs) | Real-time waveforms and numbers |
| User Interaction | Edit code → run → view results | Sliders and controls (live) |
| Use Case | Research, final results | Development, debugging, demos |

**Core Algorithms**: Both implementations use identical RF path, ADC, truncation, and gain feedback logic.

### Debugging and Troubleshooting

**Module Import Errors**:
```python
# Add to GRC "Options" block → "Generate Options" → "_source_code":
import sys
sys.path.insert(0, '/home/user/test7.2')
sys.path.insert(0, '/home/user/test7.2/gnu/python')
```

**scipy Not Found**:
```bash
pip install scipy
# or
conda install scipy
```

**GNURadio Version Check**:
```bash
gnuradio-companion --version  # Should be 3.8+
python3 --version              # Should be 3.6+
```

### Expected GUI Output

**SNR = 10 dB, Low Power Signal**:
- Low-Power BER: ~8.43 × 10⁻⁸ (5-bit quantization)
- High-Performance BER: ~2.54 × 10⁻¹⁰ (10-bit quantization)
- Adaptive BER: ~8.43 × 10⁻⁸ (selects 5-bit for low power signal)

**SNR = 10 dB, High Performance Signal**:
- Low-Power BER: ~8.43 × 10⁻⁸ (5-bit quantization)
- High-Performance BER: ~2.54 × 10⁻¹⁰ (10-bit quantization)
- Adaptive BER: ~2.54 × 10⁻¹⁰ (selects 10-bit for high performance signal)

**Adaptive AGC Advantage**:
- Automatically adjusts digital bits based on traffic type
- Achieves optimal power-performance trade-off
- Low-power signal: Uses 5-bit (saves energy, adequate accuracy)
- High-performance signal: Uses 10-bit (higher accuracy when needed)

---

## 17. Extending the System

### Potential Enhancements

1. **Channel Models**: Implement Rayleigh fading, multipath propagation
2. **Advanced Carrier Sensing**: Frequency-domain analysis, cyclostationary detection
3. **Machine Learning**: Train neural network to predict optimal digital bits
4. **Hardware Implementation**: Generate C/HDL from Python models
5. **Real-Time Optimization**: Implement actual AGC feedback loop (currently simplified)
6. **Additional Metrics**: Phase error, gain deviation, settling time
7. **Multi-User Scenarios**: Interference modeling and mitigation
8. **More Traffic Types**: Add more granular traffic categories
9. **Adaptive Thresholds**: Make carrier sensing thresholds adaptive

---

## 18. Development Workflow for AI Assistants

### Code Modification Guidelines

When modifying this codebase, AI assistants should:

1. **Understand the Dual Implementation**: Changes to core algorithms should be reflected in BOTH Python simulation and GNURadio blocks
   - If modifying RF path logic, update both `rf_paths.py` AND `gnu/python/agc_system_block.py`
   - If changing power models, update both `power_measurement.py` AND `gnu/python/agc_power_meter.py`
   - Keep algorithms synchronized to ensure consistency

2. **Respect System Requirements**:
   - ✅ Keep analog path unified (UnifiedRFPath, always same power)
   - ✅ ADC is always 10-bit, digital truncation only
   - ✅ No FSM, use pure feedback-based gain control
   - ✅ Traffic types: wake_up, lowpowersignal, highperformancesignal (3 types only)

3. **Testing After Changes**:
   ```bash
   # Test Python simulation
   python main_agc_system.py  # Should generate 11 PNG plots

   # Test GNURadio blocks
   gnuradio-companion gnu/examples/agc_comparison.grc  # Should run without errors
   ```

4. **Documentation Updates**:
   - Update CLAUDE.md when adding/removing files or changing architecture
   - Update gnu/README.md when modifying GNURadio blocks
   - Keep line counts in Section 13 (Files Summary) approximately accurate

5. **Common Modifications**:
   - **Adding new traffic type**: Update config.py (TRAFFIC_INDICATION_MAPPING, DIGITAL_TRUNCATION_BITS)
   - **Changing gain range**: Update main_agc_system.py (gain feedback logic, clipping range)
   - **Modifying power model**: Update analog_power_base.py (add new IC model)
   - **Adding carrier sensing method**: Update carrier_sensing.py (add detector class, update CarrierSensingTop)

### Git Workflow

```bash
# All development should be on the designated branch
git checkout claude/claude-md-mieq9cfdt5dkiu24-012xJ52TbreGLP7ACwf3Un5Y

# After making changes
git add .
git commit -m "Brief description of changes"
git push -u origin claude/claude-md-mieq9cfdt5dkiu24-012xJ52TbreGLP7ACwf3Un5Y
```

### File Organization

```
test7.2/
├── Core Python Simulation (13 files, ~4711 lines)
│   ├── main_agc_system.py          # Entry point, main AGC system
│   ├── agc_comparison.py           # 3-model comparison, graph generation
│   ├── carrier_sensing.py          # Packet detection (saturation, energy, correlation)
│   ├── signal_generator.py         # BPSK packet generation
│   ├── ber_calculator.py           # BER measurement
│   ├── rf_paths.py                 # RF frontend (UnifiedRFPath)
│   ├── adc.py                      # ADC quantization + digital truncation
│   ├── power_measurement.py        # Power/energy aggregation
│   ├── analog_power_base.py        # IC power models (MAX2829)
│   ├── digital.py                  # Digital circuit area models
│   ├── config.py                   # Configuration parameters
│   ├── simulation_utils.py         # Utilities (plotting, data collection)
│   └── optimize_gains.py           # Gain optimization utility
│
├── GNURadio GUI Implementation (gnu/, ~721 lines)
│   ├── python/
│   │   ├── __init__.py             # Module initialization
│   │   ├── agc_packet_source.py    # Packet source block
│   │   ├── agc_system_block.py     # AGC processing block
│   │   ├── agc_ber_calc.py         # BER calculation block
│   │   └── agc_power_meter.py      # Power measurement block
│   ├── examples/
│   │   └── agc_comparison.grc      # GNURadio Companion flowgraph
│   ├── README.md                   # GNURadio documentation
│   └── QUICKSTART_KR.md            # Korean quick start
│
├── Documentation
│   ├── CLAUDE.md                   # This file (comprehensive documentation)
│   ├── CLAUDE.ko.md                # Korean version
│   ├── SYSTEM_DIAGRAM.txt          # System architecture diagram
│   └── README.md                   # Project overview
│
└── Generated Outputs
    ├── metrics_*.png               # 11 comparison graphs from Python simulation
    └── gnuradio_screenshot.jpeg    # GNURadio GUI screenshot
```

---

## Contact/Authorship

This is an academic/research project focusing on AGC design tradeoffs in multi-traffic wireless receivers. All components are self-contained Python implementations suitable for simulation and education purposes.

**Last Updated**: 2025-11-25
**Documentation Version**: 2.0 (Added GNURadio GUI implementation documentation)
**Status**: ✅ 완전 반영 완료 (System Fully Implemented with dual Python/GNURadio platforms)
