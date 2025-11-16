class DigitalAreaModel:
    # 단위: μm²
    def __init__(self):
        # 1-bit 기본 회로 면적 정보 (μm² 단위)
        self.base_area = {
            'FULL_ADDER': 1.183,   # 1-bit full-adder (28T)
            'MULTIPLIER_CELL': 3.5,   # 1-bit multiplier 기본 셀 (AND gate + partial product)
        }

    def get_nbit_adder_area(self, n_bits):
        """
        N-bit adder의 면적 계산
        N-bit ripple carry adder = N개의 full adder
        
        Args:
            n_bits: 비트 수
        Returns:
            면적 (μm²)
        """
        return n_bits * self.base_area['FULL_ADDER']
    
    def get_nbit_multiplier_area(self, n_bits):
        """
        N-bit × N-bit multiplier의 면적 계산
        Array multiplier 기준: N² 개의 기본 셀 필요
        
        Args:
            n_bits: 비트 수
        Returns:
            면적 (μm²)
        """
        return (n_bits ** 2) * self.base_area['MULTIPLIER_CELL']
    
    def calculate_digital_processing_area(self, adc_bits):
        """
        ADC 비트 수에 따른 디지털 처리부 총 면적 계산
        디지털 AGC = 이득 조정(multiplier) + 누적(adder) + FFT(mult+add)
        
        Args:
            adc_bits: ADC 비트 수
        Returns:
            dict: 각 컴포넌트별 면적 및 총 면적
        """
        # 기본 연산 유닛
        adder_area = self.get_nbit_adder_area(adc_bits)
        multiplier_area = self.get_nbit_multiplier_area(adc_bits)
        
        # 디지털 AGC 구성 (일반적 구조)
        # - 이득 조정: 1개 multiplier
        # - 누적기: 2개 adder  
        # - FFT butterfly: 2개 multiplier + 4개 adder (간단화)
        
        total_adders = 6  # 누적 + FFT
        total_multipliers = 3  # 이득 + FFT
        
        total_adder_area = adder_area * total_adders
        total_multiplier_area = multiplier_area * total_multipliers
        total_area = total_adder_area + total_multiplier_area
        
        return {
            'adc_bits': adc_bits,
            'single_adder_area': adder_area,
            'single_multiplier_area': multiplier_area,
            'total_adders': total_adders,
            'total_multipliers': total_multipliers,
            'total_adder_area': total_adder_area,
            'total_multiplier_area': total_multiplier_area,
            'total_area': total_area
        }
    
    def calculate_operations_for_bits(self, n_bits, num_samples=1):
        """
        비트 수에 따른 연산량 계산 (교수님 피드백 반영)

        Args:
            n_bits: 사용하는 비트 수 (5 또는 10)
            num_samples: 처리할 샘플 수

        Returns:
            dict: {
                'num_adds': 덧셈 연산 수,
                'num_mults': 곱셈 연산 수,
                'energy_pj': 총 에너지 (pJ)
            }
        """
        # 비트 수에 비례하는 연산량 (K_ADD, K_MUL 사용)
        # carrier sensing, BER 계산, 디지털 처리 포함
        from config import K_ADD_PER_SAMPLE, K_MUL_PER_SAMPLE

        # 샘플당 연산 수
        adds_per_sample = K_ADD_PER_SAMPLE * n_bits
        mults_per_sample = K_MUL_PER_SAMPLE * (n_bits ** 2)

        # 총 연산 수
        total_adds = adds_per_sample * num_samples
        total_mults = mults_per_sample * num_samples

        # 연산당 에너지 (면적 기반)
        adder_area = self.get_nbit_adder_area(n_bits)
        mult_area = self.get_nbit_multiplier_area(n_bits)

        # 에너지 = 연산 수 × 면적 (간단화된 모델)
        # 1 연산 × 1 μm² ≈ 0.01 pJ (가정)
        ENERGY_PER_AREA = 0.01  # pJ/μm²

        add_energy = total_adds * adder_area * ENERGY_PER_AREA
        mult_energy = total_mults * mult_area * ENERGY_PER_AREA

        return {
            'num_adds': int(total_adds),
            'num_mults': int(total_mults),
            'energy_pj': add_energy + mult_energy,
            'adder_area': adder_area,
            'mult_area': mult_area
        }

    def get_area(self, block_type, count=1):
        """
        레거시 함수 - 기존 코드 호환성 유지
        """
        if block_type.upper() == 'FULL_ADDER':
            return self.base_area['FULL_ADDER'] * count
        elif block_type.upper() == 'MULTIPLIER':
            # 기본 8-bit multiplier 가정 (레거시)
            return self.get_nbit_multiplier_area(8) * count
        return 0
