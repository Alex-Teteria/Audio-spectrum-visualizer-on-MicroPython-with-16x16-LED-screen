# spectrum_to_neo.py
# 07.12.2023
# Обчислення FFT сигналу за допомогою алгоритму Кулі-Тьюкі: 
# http://forum.micropython.org/viewtopic.php?f=2&t=208&hilit=fft
# Виведення результату на LED-дисплей neo-16x16, 16 частотних смуг
# Released under the MIT license.
# реалізація на Pi Pico with RP2040
#-----------------------------------------------------------------------
# v0.1 додано пікові значення спектральних смуг та їх зміна із заниженою швидкістю
#-----------------------------------------------------------------------
# v0.2 додано поріг шумів та відображення спектра, коли рівень менше:
# зменшуються рівні спектральних смуг на одиницю за кожну ітерацію цикла (кожен кадр)
#-----------------------------------------------------------------------
# v0.4 знаходження FFT в другому потоці
#------------------------------------------------------------------------
from machine import ADC, Pin
import time, math
from neo_matrix import Np
import _thread
from algorithms_fft import fft, buildarrays

adc = ADC(26)
button_stop = Pin(5, Pin.IN, Pin.PULL_UP)

green = 0, 32, 0
green_yellow = 12, 20, 0
red = 32, 0, 0
orange = 24, 8, 0
blue = 0, 0, 32
blue_light = 0, 16, 16
magenta = 16, 0, 16
yellow = 24, 16, 0
teal = 0, 5, 3
white = 6, 6, 6
color_max = 10, 10, 6
nothing = 0, 0, 0

n = 16 # кількість рядків led-матриці
m = 16 # кількість стовпчиків led-матриці
np = Np(n, m, 28) # створюємо примірник класу Np (n=16, m=16, pin виходу на LED - 28)

def make_pattern():
    '''
    Вертає шаблон led-матриці (від червоного вгорі до світло-синього внизу) для подальшого накладання на нього спектру
    '''
    pattern = [[(0, 0, 0) for i in range(n)] for j in range(m)] # 0-шаблон led-матриці
    for i in range(n):
        for j in range(m):
            if 0 <= i < 3:
                pattern[i][j] = red
            elif 3 <= i< 6:
                pattern[i][j] = orange
            elif 6 <= i < 9:
                pattern[i][j] = yellow
            elif 9 <= i < 12:
                pattern[i][j] = green_yellow
            elif 12 <= i < 15:
                pattern[i][j] = green
            else:
                pattern[i][j] = blue_light
    return pattern

class Spectrum:
    def __init__(self):
        '''
        limits - межі коефіцієнтів у масиві значень fft,
        постійну складову (0-коеф.) та дзеркальну частину спектра (друга половина коефіцієнтів)
        не враховуємо, тому діапазон коефіцієнтів (1, num_read//2):
        '''
#        self.limits = (1, 2, 3, 4, 5, 7, 9, 12, 16, 20, 24, 30, 39, 51, 67, 86, 110)
#        self.limits = (1, 2, 3, 4, 5, 7, 9, 12, 16, 20, 24, 30, 38, 48, 60, 74, 90)
        self.limits = (1, 2, 3, 4, 5, 7, 9, 11, 14, 17, 21, 26, 32, 40, 51, 70, 100)
        # межі рівнів шуму в порядку спектральних смуг:
        self.noise_limits = (180, 180, 180, 180, 320, 320, 320, 400, 400, 500, 630, 760, 1000, 1400, 1800, 2400)
        self.noise_level = 180 # рівень шуму однієї спектральної складової
        self.max_level = 16 # кількість рівнів спектра для відображення
        self.threshold_plus = 5 # поріг (від максимального рівня), коли буде зростати підсилення (АРУ - automatic gain control (AGC) )
        self.num_read = 512 # величина масива значень fft (рівна кількості відліків при його обчисленні)
    
    def make_spectrum(self, nums, sensitivity, gain, spectrum_old):
        '''
        Формуємо список із сум спектральних складових списка nums, які знаходяться у визначених межах
        коефіцієнтів limits (частотні діапазони);
        обчислюємо спочатку abs() - модуль комплексних спектр. складових;
        виводити будемо у логарифмічних співвідношеннях, тому берем log,
        перед цим множимо на коеф. чутливості (sensitivity), встановлюємо цим нижній поріг чутливості, щоб дані були > 0 
        spectrum[0] = math.log(sum(nums[1:2])*sensitivity)
        spectrum[1] = math.log(sum(nums[2:3])*sensitivity)
        ......
        spectrum[15] = math.log(sum(nums[136:160])*sensitivity)
        Втановлює коефіцієнт підсилення gain в залежності від масимального рівня спектральних смуг:
        піднімає gain на 1, якщо макс. рівень спектральних смуг нижче заданого порогу (max_level - threshold_plus)
        та зменшує gain на 1, якщо макс. рівень вище заданого max_level (кількість led по висоті, висота led-матриці).
        Обмежує максимальні значення спектральних смуг висотою led-матриці (max_level)
        Вертає спектр для виведення його на led-матрицю та коеф. підсилення
        '''
        spectrum = []
        noise = True
        for i, el in zip(range(len(self.limits)-1), self.noise_limits):
            i_sum = 0
            for j in range(self.limits[i], self.limits[i+1]):
                level = abs(nums[j] / self.num_read)
                if level > self.noise_level:
                    i_sum += level
            if i_sum > el:
                noise = False
                i_sum *= sensitivity
                spectrum.append(int(round(math.log10(i_sum) * gain)) if i_sum > 1 else 0)
            else:
                spectrum.append(spectrum_old[i] - 1 if spectrum_old[i] > 0 else 0)
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
        return spectrum, gain, noise             

class Sens_control:
    '''
    sens_inc_threshold - поріг підвищення чутливості
    sens_reduct_threshold - поріг зменшення чутливості
    значення за замовчуванням підібрані з міркувань візуального сприйняття відображення спектру на led-матриці
    '''
    def __init__(self, sens_inc_threshold=176, sens_reduct_threshold=144, step_max=0.0005, step_min=0.0001):
        self.sens_inc_threshold = sens_inc_threshold
        self.sens_reduct_threshold = sens_reduct_threshold
        self.step_max = step_max
        self.step_min = step_min
        
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
            if nums > max_nums_sens:
                if  current_level >= self.sens_inc_threshold:
                    sens += step
                else:
                    sens -= step
                nums = 0
            return sens, nums

def run_fft():
    global toggle, nums_fft
    fft(nums_fft, roots, scaling=False)
    toggle = False

def main_run():
        global toggle, nums_fft, nums, sensitivity, gain, spectrum, max_spectr, nums_level, nums_sens
        nums_fft = list(nums_new) # масив для fft (обробка в другому потоці)
    
        _thread.start_new_thread(run_fft, ()) # стартуємо другий потік для розрахунку fft
        
        spectrum, gain, noise = sp.make_spectrum(nums, sensitivity, gain, spectrum)
        max_spectr = [max_level if level < max_level else level for max_level, level in zip(max_spectr, spectrum)]
        led = [list(row) for row in pattern] # копія шаблона (у тричі швидше ніж заново робити make_pattern())
        all_nothing = 0 # сума незасвічених led
        for j in range(n_freq):
            for i in range(n - spectrum[j]):
                led[i][j] = nothing 
                all_nothing += 1
            if max_spectr[j] > 1: # нижній ряд не підсвічуєм кольором color_max
                led[n - max_spectr[j]][j] = color_max

        np.write_led(led)        
        nums_level -= 1
        if not nums_level:
            nums_level = delay_max_level
            max_spectr = [level - 1 for level in max_spectr]
    #    print(gain, sensitivity, nums_sens)
        if not noise:
            sensitivity, nums_sens = sc.auto_sens_control(sensitivity, all_nothing, nums_sens, gain)
        
        for i in range(num_read):
            nums_new[i] = adc.read_u16()
        
        while toggle: # чекаємо результату з другого потоку (тупо, але працює :)
            pass
        
        nums = list(nums_fft)     # масив для виводу на led
        toggle = True

sc = Sens_control() # примірник класу Sens_control (розраховує поточну чутливість)
sp = Spectrum() # примірник класу Spectrum (обчислення рівнів спектральних смуг для виведення на led)

num_read = 256 # кількість відліків для обчислення fft
n_freq = 16 # кількість смуг по частоті
nums_new, roots = buildarrays(num_read) # шаблон для обчислень fft
pattern = make_pattern() # led pattern

max_nums_sens = 30 # затримка для зміни чутливості
nums_sens = 0 # поточне значення затримки для зміни чутливості (від 0 до max_nums_sens) 
max_spectr = [0] * n_freq # масив пікових рівнів спектру по смугах
delay_max_level = 4 # затримка зміни пікових значень спектральних складових ()
nums_level = delay_max_level # поточне значення числа затримки зміни пікових значень
gain = 20 # початкове значення коеф. підсилення, щоб вивести на led
sensitivity = 0.002 # початкове значення чутливості
spectrum = [0] * n_freq # 
toggle = True # прапорець роботи другого потоку
nums = list(nums_new) # масив для виводу на led

if __name__ == '__main__':
    while button_stop.value():
#    tick_1 = time.ticks_us()
        main_run()
#    print(time.ticks_us() - tick_1)
    np.clear()
