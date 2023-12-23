# spectrum_to_neo.py
# Author: Alex Teteria
# v0.12
# 21.12.2023
# Обчислення fft, 512 відліків  
# Виведення результату на LED-дисплей neo-16x16, 16 частотних смуг
# Released under the MIT license.
# реалізація на Pi Pico with RP2040
#-----------------------------------------------------------------------
# для fft використано бібліотеку ulab
# змінено частоту CPU: 140МГц
# частота дискретизації АЦП приблизно 39,6kHz (із затримкою 2uc при зчитуванні з АЦП)
#--------------------------------------------------------------------------
# вивід спектра на led у другому потоці
#--------------------------------------------------------------------------
# Починаючи з 5-ї гармоніки частотні діапазони розбито наближено до функції sqrt(2) ** x,
# тобто кожних два діапазони - октава
# -------------------------------------------------------------------------
from machine import ADC, Pin, freq
import time, math, neopixel
import _thread
import ulab
from ulab import numpy as np

freq(140_000_000) # set the CPU frequency to 140 MHz
print(freq())
adc = ADC(26)
button_stop = Pin(15, Pin.IN, Pin.PULL_UP)


class Nm():
    def __init__(self, row, col, neo_pin):
        self.n = row # кількість рядків матриці
        self.m = col # кількість стовпців матриці
        self.np = neopixel.NeoPixel(machine.Pin(neo_pin), self.n * self.m) # примірник класу NeoPixel, neo_pin - вихід на LED
        # визначення кольорів:
        self.green = 0, 32, 0
        self.green_yellow = 12, 20, 0
        self.red = 32, 0, 0
        self.orange = 24, 8, 0
        self.blue = 0, 0, 32
        self.blue_light = 0, 16, 16
        self.magenta = 16, 0, 16
        self.yellow = 24, 16, 0
        self.white = 10, 10, 6
        self.color_max = 22, 0, 10
        self.nothing = 0, 0, 0

    def clear(self):
        for i in range(len(self.np)):
            self.np[i] = 0, 0, 0
        self.np.write()  

    def write_led(self, l):
        global exit_request # прапорець роботи другого потоку
        for row in range(self.n):
            for col in range(self.m):
                self.np[self.koef_to_pix(row, col)] = l[row][col]
        self.np.write()
        exit_request = True # дозволяємо вихід із основного циклу

    def koef_to_pix(self, i, j):
        '''
        отримує коефіцієнти матриці (row x col) row = i, col =  j
        вертає neopixel-коефіцієнт LED-матриці
        '''
        return self.m * i + j if i % 2 else self.m-j-1 + self.m * i

    def make_pattern(self):
        '''
        Вертає шаблон led-матриці (від червоного вгорі до світло-синього внизу) для подальшого накладання на нього спектру
        '''
        pattern = [[(0, 0, 0) for j in range(self.m)] for i in range(self.n)] # 0-шаблон led-матриці
        for i in range(self.n):
            for j in range(self.m):
                if 0 <= i < 3:
                    pattern[i][j] = self.red
                elif 3 <= i< 6:
                    pattern[i][j] = self.orange
                elif 6 <= i < 9:
                    pattern[i][j] = self.yellow
                elif 9 <= i < 12:
                    pattern[i][j] = self.green_yellow
                elif 12 <= i < 15:
                    pattern[i][j] = self.green
                else:
                    pattern[i][j] = self.blue_light
        return pattern

    def calculate_led(self, n_freq, led, spectrum, max_spectr):
        '''
        В масиві led значення стовпців > за значення в масиві spectrum змінює на колір nothing;
        максимальні значення - змінює колір на color_max;
        вертає загальну кількість незасвічених led
        '''
        all_nothing = 0 # сума незасвічених led
        for j in range(n_freq):
            for i in range(self.n - spectrum[j]):
                led[i][j] = self.nothing 
                all_nothing += 1
            if max_spectr[j] > 1: # нижній ряд не підсвічуєм кольором color_max
                led[self.n - max_spectr[j]][j] = self.color_max
        return all_nothing            


class Spectrum:
    def __init__(self, max_level, num_read):
        '''
        limits - межі коефіцієнтів у масиві значень fft,
        постійну складову (0-коеф.) та дзеркальну частину спектра (друга половина коефіцієнтів)
        не враховуємо, тому діапазон коефіцієнтів (1, num_read//2):
        '''
        self.limits = (1, 2, 3, 4, 5, 7, 9, 12, 17, 24, 34, 47, 66, 92, 130, 182, 257)
        self.noise_levels = (120, 110, 100, 100, 100, 100, 100, 100, 85, 75, 70, 35, 20, 15, 8, 5)
        self.max_level = max_level # кількість рівнів спектра для відображення
        self.threshold_plus = 4 # поріг (від максимального рівня), коли буде зростати підсилення (АРУ - automatic gain control (AGC) )
        self.num_read = num_read # величина масива значень fft (рівна кількості відліків при його обчисленні)
    
    def make_spectrum(self, nums, sensitivity, gain, spectrum):
        '''
        Формує список із сум спектральних складових списка nums, які знаходяться у визначених межах
        коефіцієнтів limits (частотні діапазони);
        виводить у логарифмічних співвідношеннях, тому обчислює log,
        Перед цим множимо на коеф. чутливості (sensitivity), встановлюємо цим нижній поріг чутливості, щоб дані були > 0 
        spectrum[0] = math.log(sum(nums[1:2])*sensitivity)
        spectrum[1] = math.log(sum(nums[2:3])*sensitivity)
        ......
        spectrum[15] = math.log(sum(nums[182:257])*sensitivity)
        Втановлює коефіцієнт підсилення gain в залежності від масимального рівня спектральних смуг:
        піднімає gain на 1, якщо макс. рівень спектральних смуг нижче заданого порогу (max_level - threshold_plus)
        та зменшує gain на 1, якщо макс. рівень вище заданого max_level (кількість led по висоті, висота led-матриці).
        Обмежує максимальні значення спектральних смуг висотою led-матриці (max_level)
        Змінює значення spectrum для виведення його на led-матрицю
        Вертає поточне значення коеф. підсилення (gain) та ознаку відсутності сигналу (noise)
        '''
        noise = True
        for i in range(len(self.limits)-1):
            i_sum = 0
            for j in range(self.limits[i], self.limits[i+1]):
                level = nums[j] / self.num_read
                if level > self.noise_levels[i]:
                    i_sum += level
            if i_sum > 0:
                noise = False
                i_sum *= sensitivity
                if i_sum > 1:
                    spectrum[i] = int(round(math.log10(i_sum) * gain))
                else:
                    spectrum[i] = spectrum[i] - 1 if spectrum[i] > 0 else 0
            else:
                spectrum[i] = spectrum[i] - 1 if spectrum[i] > 0 else 0
        if not noise:
            if max(spectrum) < self.max_level - self.threshold_plus:
                gain += 0.5
            elif (max(spectrum) - self.max_level) >= 4:
                gain -= 2
            elif 1 < (max(spectrum) - self.max_level) < 4:
                gain -= 1
            elif 0 < (max(spectrum) - self.max_level) <= 1:
                gain -= 0.5
            for i in range(len(spectrum)):
                if spectrum[i] > self.max_level:
                    spectrum[i] = self.max_level
        return gain, noise             


class Sens_control:
    '''
    sens_inc_threshold - поріг підвищення чутливості
    sens_reduct_threshold - поріг зменшення чутливості
    значення за замовчуванням підібрані з міркувань візуального сприйняття відображення спектру на led-матриці
    '''
    def __init__(self, max_nums_sens, sens_inc_threshold=176, sens_reduct_threshold=144, step_max=0.0005, step_min=0.0001):
        self.sens_inc_threshold = sens_inc_threshold
        self.sens_reduct_threshold = sens_reduct_threshold
        self.step_max = step_max
        self.step_min = step_min
        self.max_nums_sens = max_nums_sens
        
    def auto_sens_control(self, sens, current_level, nums, gain):
        '''
        Вертає поточне значення чутливості для обчислення спектральних складових у наступній ітерації та
        поточне значення затримки зміни чутливості (0 <= nums < max_nums_sens)
        sens_reduct_threshold, sens_inc_threshold - глобальні значення порогів зміни чутливості;
        max_nums_sens - глобальне максимальне значення затримки зміни чутливості (в кількості циклів обчислення спектру)
        '''
        step = self.step_max if sens > 0.001 else self.step_min # крок зміни чутливості
        
        if gain > 35:
            sens += step
        elif gain < 12:
            sens -= step
            
        if self.sens_reduct_threshold < current_level < self.sens_inc_threshold:
            return sens, 0 # чутливість не змінюється, обнуляємо лічильник затримки (nums = 0)
        else:
            nums += 1
            if nums > self.max_nums_sens:
                if  current_level >= self.sens_inc_threshold:
                    sens += step
                else:
                    sens -= step
                nums = 0
            return sens, nums


def main_run():
    global exit_request # прапорець роботи другого потоку, необхідний для коректного виходу з основного циклу
    n = 16 # кількість рядків матриці
    m = 16 # кількість стовпців матриці
    nm = Nm(row=n, col=m, neo_pin=28) # створюємо примірник класу Nm (n=16, m=16, pin виходу на LED - 28)
    num_read = 512 # кількість відліків для обчислення fft
    n_freq = 16 # кількість спектральних смуг (частотних діапазонів)
    max_nums_sens = 30 # затримка для зміни чутливості (в кількості кадрів)
    sc = Sens_control(max_nums_sens) # примірник класу Sens_control (розраховує поточну чутливість)
    sp = Spectrum(n, num_read) # примірник класу Spectrum (обчислення рівнів спектральних смуг для виведення на led)
    nums = [0] * num_read # масив відліків та результату fft
    pattern = nm.make_pattern() # led pattern
    nums_sens = 0 # поточне значення затримки для зміни чутливості (від 0 до max_nums_sens) 
    max_spectr = [0] * n_freq # масив пікових рівнів спектру по смугах
    delay_max_level = 4 # затримка зміни пікових значень спектральних складових (в кількості кадрів)
    nums_level = delay_max_level # поточне значення числа затримки зміни пікових значень
    gain = 20 # початкове значення коеф. підсилення, щоб вивести на led
    sensitivity = 0.002 # початкове значення чутливості
    spectrum = [0] * n_freq # масив рівнів спектру по смугах
    while button_stop.value():
        for i in range(num_read):
            nums[i] = adc.read_u16()
            time.sleep_us(2)
        nums = list(ulab.utils.spectrogram(np.array(nums)))
        gain, noise = sp.make_spectrum(nums, sensitivity, gain, spectrum)
        max_spectr = [max_level if level < max_level else level for max_level, level in zip(max_spectr, spectrum)]
        led = [list(row) for row in pattern] # копія шаблона (у тричі швидше ніж заново робити make_pattern())
        all_nothing = nm.calculate_led(n_freq, led, spectrum, max_spectr)
        nums_level -= 1
        if not nums_level:
            nums_level = delay_max_level
            max_spectr = [level - 1 for level in max_spectr]
        if not noise:
            sensitivity, nums_sens = sc.auto_sens_control(sensitivity, all_nothing, nums_sens, gain)
        _thread.start_new_thread(nm.write_led, (led,))
        exit_request = False
    while not exit_request: # для виходу чекаємо поки не закінчиться виконання у другому потоці
        pass
    nm.clear()

if __name__ == '__main__':
    main_run()

    
