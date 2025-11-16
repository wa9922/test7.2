# AGC (Automatic Gain Control) System Simulation - Project Documentation

## 1. Project Overview

### Purpose
This project is a **Python-based simulation framework for Automatic Gain Control (AGC) systems** in wireless receiver design. It implements and compares three AGC approaches:
1. **Low-Power Fixed AGC** - Conservative, always uses minimum power (3-bit ADC, 10dB gain)
2. **High-Performance Fixed AGC** - Aggressive, always uses maximum performance (10-bit ADC, 40dB gain)
3. **Adaptive AGC** (Proposed) - Dynamic approach that adjusts ADC resolution and gain based on detected traffic type

### Domain
- **Wireless Communications/Receiver Design**
- **Energy-Efficient Signal Processing**
- **Hardware-Software Co-design**
- Targets IoT/embedded wireless systems with multiple traffic types (wake-up, sensor, voice, video)

### Key Objective
Demonstrate that an adaptive AGC system can achieve a better balance between energy consumption and signal quality (BER) compared to fixed-mode approaches, by dynamically selecting ADC resolution and RF gain based on detected traffic type.

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
RF Frontend Path Selection
    ├─ LowPowerPath (LOW_GAIN_LP state) → Limited gain, low power
    └─ HighPerfPath (other states) → Full gain, high power
    ↓
ADC Quantization (3-bit or 10-bit based on ADC resolution)
    ↓
Block-by-Block Processing
    ├─ CarrierSensing (3 methods: saturation, energy, correlation detection)
    ├─ BER Calculation (measure signal quality on STF)
    ├─ FSM State Transitions (based on carrier sensing + signal field indication)
    ├─ Dynamic Gain Adjustment (peak-based feedback)
    └─ Power Measurements (analog + digital)
    ↓
Collect Metrics (BER, power, energy, gain, FSM state)
    ↓
Output: Packet result with performance metrics
```

### Component Interaction Diagram

```
AgcSystem (main orchestrator)
├── AgcFsm (Finite State Machine)
│   ├── States: LOW_GAIN_LP, LOW_GAIN_HP, MEDIUM_GAIN, HIGH_GAIN
│   ├── LUT: Thresholds per state
│   └── Output: current_state, gain_db, adc_resolution
│
├── SignalGenerator
│   ├── BPSK modulation
│   └── Packet generation: preamble (STF+LTF) + signal field + payload
│
├── RF Paths (Analog Frontend)
│   ├── LowPowerPath: LNA(fixed) → Mixer → LPF
│   └── HighPerfPath: LNA(fixed) → Mixer → VGA → LPF
│
├── ADC (Analog-to-Digital Converter)
│   ├── ADC3bit (low-power mode, 8 levels)
│   └── ADC10bit (high-perf mode, 1024 levels)
│
├── CarrierSensing
│   ├── SaturationDetector (ADC saturation check)
│   ├── EnergyDetector (signal power threshold)
│   └── CorrelationDetector (STF correlation with received signal)
│
├── BERCalculator (measure quality on STF using hard-decision BPSK)
│
├── Power Measurement Modules
│   ├── AnalogPowerMeasurement (MAX2829/MAX2830 models)
│   └── DigitalComputationMeasurement (area-based energy estimation)
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

#### **main_agc_system.py** (713 lines)
**Role**: Main AGC system class and simulation orchestrator

**Key Classes**:
- `AgcSystem`: Primary class implementing the adaptive AGC system
  - `__init__()`: Initialize FSM, RF paths, ADC, carrier sensing, power models
  - `process_packet()`: Main packet processing pipeline
  - `apply_adc_quantization()`: ADC quantization simulation
  - `extract_signal_field_indication()`: Decode traffic type from signal field
  - `update_adc_resolution_for_traffic()`: Adaptive ADC selection based on traffic
  - `run_simulation()`: Execute full simulation with multiple packets/SNR values

**Key Methods**:
- `process_rf_signal()`: Apply RF path gain and filtering
- `_update_power_measurements()`: Calculate analog and digital power/energy
- `_calculate_cs_operations()`: Count arithmetic operations for carrier sensing
- `_calculate_ber_operations()`: Count arithmetic operations for BER calculation
- Block-based processing loop with gain feedback based on signal peak
- State history tracking and statistics collection

**Entry Point**: `main()` at end of file - runs 3 models and generates 3 comparison metrics graphs

---

#### **agc_fsm.py** (268 lines)
**Role**: Finite State Machine for AGC control

**Key Classes**:
- `AgcState` (Enum): Four states
  - `LOW_GAIN_LP`: Standby/wake-up (10 dB, 3-bit ADC)
  - `LOW_GAIN_HP`: Sensor data (25 dB, 4-bit ADC)
  - `MEDIUM_GAIN`: Voice (35 dB, 8-bit ADC)
  - `HIGH_GAIN`: Video (40 dB, 10-bit ADC)

- `AgcFsm`: State machine implementation
  - `process_indication()`: Determine if state transition needed based on carrier sensing results and signal field indication
  - `should_transition()`: Decision logic (wake-up detection, signal field matching, no-signal fallback)
  - `transition_to_state()`: Perform state change with logging
  - `get_current_gain()`: Return dB gain for current state
  - `get_current_adc_resolution()`: Return ADC bits for current state
  - `xor_gain_comparison()`: Compare expected vs measured gain codes
  - `get_state_statistics()`: Return transition history

**Transition Logic**:
1. If in LOW_GAIN_LP and signal detected → await signal field indication
2. If signal field indicates specific traffic → transition to matching state
3. If in any state and no signal → return to LOW_GAIN_LP (standby)
4. Each state has lookup table (LUT) with thresholds for saturation, energy, correlation detection

---

#### **carrier_sensing.py** (394 lines)
**Role**: Detect packet presence using multiple methods

**Key Classes**:
- `SaturationDetector`: Check if ADC samples exceed saturation threshold
  - Compares I/Q components against threshold
  - Returns saturation rate and boolean detection

- `EnergyDetector`: Measure signal power and compare to energy threshold
  - Calculates mean power of complex signal
  - Converts to dB and compares threshold (-75 dBm default)
  - Tracks detection history

- `CorrelationDetector`: Correlate received signal with known STF sequence
  - Implements sliding window correlation with STF reference
  - Computes correlation magnitude
  - Compares to correlation threshold (0.6-0.85 depending on state)

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

#### **signal_generator.py** (228 lines)
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
  128 bits (STF)      48 bits (traffic type)    All modulated BPSK
  +64 bits (LTF)      + control bits            at 20 MHz sampling
```

**Configuration**:
- Sampling rate: 20 MHz
- Symbol rate: 1 MHz
- Samples per symbol: 20
- BPSK constellation: {0: -1.0, 1: +1.0}

---

#### **ber_calculator.py** (250 lines)
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

#### **adc.py** (93 lines)
**Role**: Simulate ADC quantization

**Key Classes**:
- `BaseADC`: Generic N-bit ADC model
  - `quantize()`: Round signal to nearest quantization level
  - `quantize_to_int()`: Return integer representation
  - Parameters: bit width, reference voltage, quantization step

- `ADC3bit`: Low-power variant (8 levels, range: -4 to 3)
- `ADC10bit`: High-performance variant (1024 levels, range: -512 to 511)

**Quantization Process**:
1. Clip signal to voltage reference range
2. Round to nearest step (step = 2*Vref / 2^bits)
3. Return quantized value

---

#### **rf_paths.py** (179 lines)
**Role**: Model RF front-end analog processing chains

**Functions** (basic operations):
- `lna()`: Low-Noise Amplifier (linear gain in dB)
- `mixer()`: Frequency conversion (multiplication by LO)
- `vga()`: Variable Gain Amplifier (adjustable gain)
- `lpf()`: Low-Pass Filter (1st-order IIR)

**Key Classes**:
- `HighPerfPath`: High-performance receiver path
  - Chain: LNA(20dB) → Mixer → VGA(variable) → LPF
  - High gain but high power consumption

- `LowPowerPath`: Low-power receiver path
  - Chain: LNA(coarse+fine) → Mixer → LPF (no VGA)
  - Limited gain but minimal power consumption

---

#### **analog_power_base.py** (100 lines)
**Role**: Model analog front-end power consumption

**Key Classes**:
- `AnalogPowerModelBase`: Abstract base for power models
  - `get_power()`: Return power for specific mode (mW)
  - `get_energy_consumption()`: Calculate energy for duration (mJ = power × time)

- `MAX2829PowerModel`: High-performance receiver IC model
  - Standby: ~184 mW
  - RX active: ~392 mW

- `MAX2830PowerModel`: Low-power receiver IC model
  - Standby: ~78.4 mW
  - RX active: ~173.6 mW

- `AnalogPowerMeasurement` (in power_measurement.py): Tracks total and average power

---

#### **digital.py** (80 lines)
**Role**: Model digital processing area and power

**Key Class**:
- `DigitalAreaModel`: Calculate circuit area (μm²) for digital components
  - Base areas: Full-adder (1.183 μm²), Multiplier cell (3.5 μm²)
  - N-bit adder area: N × 1.183
  - N-bit multiplier area: N² × 3.5
  - Total digital processing area depends on ADC bit width

**Usage**: Estimate energy based on circuit area and operation count

---

#### **power_measurement.py** (159 lines)
**Role**: Aggregate power and energy metrics

**Key Classes**:
- `DigitalComputationMeasurement`: Track digital operations and energy
  - `update_computation()`: Accumulate multiplications and additions
  - Counts ops from carrier sensing, BER calculation, and bit-dependent operations
  - `get_total_energy()`: Energy = ops × power_per_op × area_scaling (pJ)

- `AnalogPowerMeasurement`: Accumulate analog power consumption
  - `update_power_measurement()`: Add duration × power
  - `get_total_energy()`: Total accumulated energy (mJ)
  - `calculate_power()`: Power for specific state

---

### Configuration and Comparison Modules

#### **config.py** (93 lines)
**Role**: Centralized configuration parameters

**Key Configurations**:
- **Signal Parameters**:
  - Sampling rate: 20 MHz
  - Symbol rate: 1 MHz
  - Samples per symbol: 20
  - STF/LTF/Signal Field/Payload bit counts

- **AGC Gain Levels** (in dB):
  - LOW_GAIN_LP: 10 dB (wake-up)
  - LOW_GAIN_HP: 25 dB (sensor)
  - MEDIUM_GAIN: 35 dB (voice)
  - HIGH_GAIN: 40 dB (video)

- **ADC Resolution by Traffic Type**:
  - wake_up: 3 bits
  - sensor: 4 bits
  - voice: 8 bits
  - video: 10 bits

- **Carrier Sensing Thresholds** (per FSM state):
  - Saturation thresholds (ADC level dependent)
  - Energy thresholds (dBm)
  - Correlation thresholds (0.6-0.85)
  - Gain codes (binary strings)

- **Channel & BER Parameters**:
  - Default SNR: 10 dB
  - Noise power: 0.1
  - BER window size: 128 bits
  - BER update interval: 100 samples

- **Digital Operation Scaling**:
  - K_ADD_PER_SAMPLE: 1.0 (adds per sample per bit)
  - K_MUL_PER_SAMPLE: 0.05 (mults per sample per bit²)

---

#### **agc_comparison.py** (726 lines)
**Role**: Compare three AGC models and generate result metrics

**Key Classes**:
- `FixedLowPowerAGC`: Extends AgcSystem, forces LOW_GAIN_LP state + 3-bit ADC always
  - Overrides `process_packet()` to prevent FSM transitions
  - Lowest power consumption, potential accuracy loss

- `FixedHighPerformanceAGC`: Extends AgcSystem, forces HIGH_GAIN state + 10-bit ADC always
  - Overrides `process_packet()` to prevent FSM transitions
  - Highest accuracy, highest power consumption

- `AdaptiveAGC`: Extends AgcSystem, uses full adaptive logic
  - FSM responds to carrier sensing and signal field indication
  - ADC resolution selected based on detected traffic type
  - Dynamic gain adjustment based on signal peak

**Key Functions**:
- `run_comparison_simulation()`: Run all 3 models through identical traffic pattern, collect metrics
- `calculate_average_results()`: Average results across iterations
- `compute_model_metrics()`: Calculate per-model metrics (total energy, avg BER, latency)
- `plot_three_metrics_models()`: Generate 3 output graphs

**Output Graphs**:
1. `metrics_energy.png`: Analog (mJ) + Digital (pJ) energy per model
2. `metrics_accuracy.png`: Average BER per model
3. `metrics_latency.png`: Average latency per model

---

#### **optimize_gains.py** (145 lines)
**Role**: Utility to find optimal gain values for each traffic type

**Key Functions**:
- `test_gain_performance()`: Measure BER at specific gain value
- `optimize_gains_for_traffic()`: Search gain range (0-50 dB) for each traffic type
- `test_fixed_agc_gains()`: Find optimal fixed gains for conventional approaches

**Usage**: Run to find better gain configuration values for config.py

---

### Utility Modules

#### **simulation_utils.py** (422 lines)
**Role**: Helper functions and data collection

**Key Classes**:
- `TrafficFlowManager`: Generate traffic pattern sequence
  - Cycles through: wake_up → sensor → voice → video → (gap) → repeat

- `TimeSeriesDataCollector`: Accumulate time-series data during simulation
  - Tracks: time, traffic type, power (analog/digital), BER, FSM state, gain, SNR
  - Limits storage to 100K points for memory efficiency

- `SignalFieldDecoder`: Decode traffic type from signal field
  - Maps 2-bit indication to traffic type
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
   - `FixedLowPowerAGC()`
   - `FixedHighPerformanceAGC()`
   - `AgcSystem(use_indicator_for_adc=True)` (Adaptive)

2. For each model, call `run_one_model()`:
   - Execute `model.run_simulation(traffic_types, snr_range, packets_per_scenario)`
   - Traffic types: sensor, voice, video
   - SNR range: 5, 10, 15, 20 dB
   - 20 packets per SNR scenario

3. Collect metrics via `compute_model_metrics()`:
   - Total analog energy (mJ)
   - Total digital energy (pJ)
   - Average BER
   - Average latency (ms)

4. Generate 3 comparison graphs:
   - Energy usage comparison
   - Accuracy (BER) comparison
   - Latency comparison

5. Save PNGs to current directory

---

### Simulation Workflow: `run_simulation()`

```python
agc_system = AgcSystem()
sim_result = agc_system.run_simulation(
    traffic_types=["sensor", "voice", "video"],
    snr_range_db=[5, 10, 15, 20],
    packets_per_scenario=20
)
```

**Per-Simulation Steps** (for each SNR, each packet):
1. Generate packet with specific traffic type
2. Add AWGN noise to clean signal
3. Process through RF path (select based on current FSM state)
4. Apply ADC quantization
5. **Block-by-block processing**:
   - Run carrier sensing (saturation, energy, correlation)
   - Calculate CS operations count
   - Extract signal field indication (if in signal field region)
   - Check for ADC resolution update (adaptive mode)
   - FSM state transition check
   - Calculate BER on STF region
   - Peak-based gain adjustment feedback
   - Update power measurements
6. Aggregate packet result with all sub-block metrics
7. Return packet result containing:
   - Final BER, FSM state, gain, ADC resolution
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

1. **ADC Resolution Selection**:
   - Adaptive mode: Start with 3-bit, await signal field indication for update
   - Fixed modes: Locked to 3-bit or 10-bit

2. **Channel Simulation**: Add AWGN at specified SNR

3. **RF Processing**:
   - Select path: LowPowerPath (LOW_GAIN_LP) or HighPerfPath (other states)
   - Apply gains and filtering

4. **Block Loop** (process in chunks):
   - Carrier sensing (3 methods, ~320-330 arithmetic ops)
   - Check signal field region:
     - If in signal field region and not extracted yet:
       - Decode traffic type from signal field bits
       - (Adaptive mode) Update ADC resolution based on decoded traffic
       - Reprocess block with new ADC
   - FSM indication processing:
     - Check if state change needed
     - If changed, reprocess block with new configuration
   - Gain feedback:
     - Measure peak in block
     - If peak > 0.90: decrease gain by 1 dB
     - If peak < 0.25: increase gain by 1 dB
     - Reprocess block if gain changed
   - BER calculation (STF region only):
     - Hard-decision demodulation: real > 0 → 1, else 0
     - XOR with reference STF bits
     - Count error rate (~680 arithmetic ops)
   - Power measurements:
     - Analog: State-dependent (low-power or high-perf IC model)
     - Digital: Operation-dependent + area-based scaling
   - Collect block result

5. **Final Packet Computation**:
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
- **enum**: AgcState enumeration
- **abc**: Abstract base classes for power models
- **os**: File operations (directory creation)
- **typing**: Type hints (Dict, List, Tuple, Optional)

### No External Hardware Simulation Libraries
- All RF/ADC models implemented from scratch in Python
- Modular design allows easy extension

---

## 6. Design Patterns and Conventions

### Architectural Patterns

1. **State Machine Pattern**
   - `AgcFsm` implements FSM with discrete states
   - Each state maps to specific gain/ADC configuration
   - Transitions based on carrier sensing and signal field indication
   - LUT (Look-Up Table) for state-dependent thresholds

2. **Strategy Pattern**
   - Three AGC strategies: Low-Power, High-Perf, Adaptive
   - Shared `AgcSystem` base class with different `process_packet()` implementations
   - Easy to add new strategies (e.g., predictive AGC)

3. **Decorator/Wrapper Pattern**
   - `CarrierSensingTop` wraps three detection methods
   - `TimeSeriesDataCollector` wraps measurement logging
   - `AnalogPowerMeasurement` wraps power model selection

4. **Builder/Configuration Pattern**
   - Centralized `config.py` for all parameters
   - Dictionary-based LUT for state thresholds
   - Configuration can be modified without code changes

5. **Pipeline Pattern**
   - Packet processing flows through distinct stages:
     Signal → RF Path → ADC → Block Loop → Result
   - Each stage modular and independently testable

### Naming Conventions

- **Class names**: CamelCase (`AgcSystem`, `CarrierSensingTop`)
- **Method names**: snake_case (`process_packet()`, `run_simulation()`)
- **Constants**: UPPER_CASE (`SAMPLING_RATE`, `GAIN_LEVELS`)
- **FSM states**: Descriptive with component (`LOW_GAIN_LP`, `HIGH_GAIN`)
- **Variable names**: Descriptive with units (`power_mw`, `ber`, `gain_db`)

### Code Organization

- **Separation of concerns**:
  - Signal generation separate from processing
  - Power models isolated in dedicated modules
  - Comparison logic in separate file
  
- **Modular components**: Each major subsystem (FSM, carrier sensing, BER, power) in its own file

- **Utility extraction**: Common functions (plotting, data collection) in simulation_utils.py

---

## 7. Testing Approach

### Test Capabilities (Limited; Primarily Simulation-Based)

**Unit-level self-tests** (in modules):
- `agc_fsm.py`: `test_agc_fsm()` function at end
  - Tests state transitions for various carrier sensing scenarios
  - Validates output statistics

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
   - FSM state transition logic
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

2. **Gain Settings** (GAIN_LEVELS):
   ```python
   GAIN_LEVELS = {
       "LOW_GAIN_LP": 10,      # dB
       "LOW_GAIN_HP": 25,      # dB
       "MEDIUM_GAIN": 35,      # dB
       "HIGH_GAIN": 40,        # dB
   }
   ```

3. **ADC Resolution by Traffic**:
   ```python
   TRAFFIC_ADC_RESOLUTION = {
       "wake_up": 3,
       "sensor":  4,
       "voice":   8,
       "video":   10
   }
   ```

4. **Carrier Sensing Thresholds** (per state):
   - Saturation threshold (ADC counts)
   - Energy threshold (dBm)
   - Correlation threshold (0.0-1.0)

5. **Digital Operation Constants**:
   - `K_ADD_PER_SAMPLE`: Scaling factor for additions
   - `K_MUL_PER_SAMPLE`: Scaling factor for multiplications

6. **Display/Debug Options**:
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
- Files: `metrics_energy.png`, `metrics_accuracy.png`, `metrics_latency.png`

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
| After ADC (3-bit) | [-4, 3] | Quantized |
| After ADC (10-bit) | [-512, 511] | Quantized |
| Power (dB) | -100 to +20 dBm | Log scale |
| BER | 0.0 to 1.0 | Normalized error rate |

### Quantization Effects

- **3-bit ADC**: Coarse quantization, information loss, but low power
- **10-bit ADC**: Fine quantization, high fidelity, but high power

System exploits this trade-off: use 3-bit for low-rate wake-up signals, 10-bit for high-bandwidth video.

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

### ADC Quantization Step
```
step_size = (2 * vref) / (2^bits)
quantized = round(signal / step) * step
```

### FSM Thresholds (Carrier Sensing)
```
saturation: |real| >= threshold OR |imag| >= threshold
energy: power_db > threshold_db
correlation: max_correlation > threshold (0.6-0.85)
```

### Digital Energy (pJ)
```
energy = (num_adds * power_per_add) + (num_mults * power_per_mult)
         × area_scaling_factor
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

### Adaptive Selection Logic Limitation

- ADC resolution selection happens **after** signal field extraction
- This means initial processing uses default 3-bit, then might switch
- More optimal approach: use signal field indicator earlier (future work)

---

## 12. Files Summary

| File | Lines | Purpose |
|------|-------|---------|
| main_agc_system.py | 713 | Main AGC system + comparison entry point |
| agc_fsm.py | 268 | Finite state machine for gain/ADC control |
| carrier_sensing.py | 394 | Packet detection (saturation, energy, correlation) |
| signal_generator.py | 228 | PHY packet generation (BPSK modulation) |
| ber_calculator.py | 250 | Bit error rate measurement |
| power_measurement.py | 159 | Power/energy aggregation |
| analog_power_base.py | 100 | IC power models (MAX2829/MAX2830) |
| rf_paths.py | 179 | RF front-end simulation (LNA, mixer, VGA, LPF) |
| adc.py | 93 | ADC quantization (3-bit and 10-bit) |
| digital.py | 80 | Digital circuit area models |
| config.py | 93 | Centralized configuration parameters |
| simulation_utils.py | 422 | Utilities (data collection, plotting, traffic flow) |
| agc_comparison.py | 726 | Comparison of 3 AGC models |
| optimize_gains.py | 145 | Gain optimization utility |
| README.md | - | Project overview |

---

## 13. Example Usage

### Basic Single Simulation
```python
from main_agc_system import AgcSystem
from signal_generator import SignalGenerator

# Create system
agc = AgcSystem()
sg = SignalGenerator()

# Generate and process one packet
packet = sg.create_complete_packet("video")
result = agc.process_packet(packet, channel_snr_db=15)

print(f"BER: {result['final_ber']['ber']:.6f}")
print(f"Analog energy: {result['analog_power']['total_energy_mj']:.2f} mJ")
print(f"Digital energy: {result['digital_computation']['total_energy_pj']:.2f} pJ")
print(f"Final state: {result['final_fsm_state']}")
print(f"Final gain: {result['final_gain_db']} dB")
```

### Full Simulation Run
```python
from main_agc_system import AgcSystem

agc = AgcSystem(use_correlation_detection=True)  # Adaptive

# Run full simulation
sim_result = agc.run_simulation(
    traffic_types=["sensor", "voice", "video"],
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
    # 3. Generate comparison graphs
    exec(open("main_agc_system.py").read())
```

---

## 14. Key Insights for AI Assistants

1. **Primary Innovation**: Adaptive AGC dynamically selects ADC resolution based on detected traffic type, trading off power/performance on a per-packet basis vs fixed approaches

2. **Signal Processing Foundation**: Uses standard DSP techniques (BPSK, matched filtering via correlation, hard-decision detection)

3. **Hardware-Software Co-Design**: Models both analog RF frontend (power consumption) and digital backend (area + operation count)

4. **Comparative Evaluation**: Three competing approaches evaluated on identical traffic/channel conditions for fair comparison

5. **Packet Structure**: Uses standard wireless preamble structure (STF for detection, LTF for channel, signal field for metadata)

6. **Trade-offs Explicitly Modeled**:
   - 3-bit ADC: Lower power, lower accuracy
   - 10-bit ADC: Higher power, higher accuracy
   - Adaptive: Selects based on content type

7. **Energy Modeling**: Combines state-dependent analog power (IC model) + operation-count digital energy (area-based scaling)

8. **Practical Constraints**:
   - Real system would need Rayleigh fading, interference
   - AGC loop would be continuous, not discrete states
   - Signal field decoding would be probabilistic

---

## 15. Extending the System

### Potential Enhancements

1. **Channel Models**: Implement Rayleigh fading, multipath propagation
2. **Advanced Carrier Sensing**: Frequency-domain analysis, cyclostationary detection
3. **Machine Learning**: Train neural network to predict optimal ADC resolution
4. **Hardware Implementation**: Generate C/HDL from Python models
5. **Real-Time Optimization**: Implement actual AGC feedback loop (currently just peak-based)
6. **Additional Metrics**: Phase error, gain deviation, settling time
7. **Multi-User Scenarios**: Interference modeling and mitigation

---

## Contact/Authorship

This is an academic/research project focusing on AGC design tradeoffs in multi-traffic wireless receivers. All components are self-contained Python implementations suitable for simulation and education purposes.

