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
