# Audio-spectrum-analyzer-on-ESP32-with-16x16-LED-screen
Calculation of the audio signal spectrum and its display on the WS2812B RGB LED panel using the ESP32 microcontroller under MicroPython.

## Зміст  

1. [Огляд](./README.md#1-огляд)
2. [Схема складання аналізатора](./README.md#2-Схема-складання-аналізатора)
3. [Приклад відображення аудіосигналу](./README.md#3-Приклад-відображення-аудіосигналу)
4. [Install](./README.md#4-install)
   
## 1. Огляд

Для розрахунку FFT використано алгоритм Кулі — Тьюкі, зокрема його реалізацію на MicroPython [algorithms](https://github.com/peterhinch/micropython-fourier). Модуль мікрофонного підсилювача має на виході постійну складову VCC / 2, тому сигнал на вхід АЦП подається через конденсатор. Резистори 110к та 20к забезпечують зміщення по постійному струму вхідного сигналу в середину діапазону роботи АЦП (0,5В при діапазоні перетворень від 0 до 1В).
При відображенні реалізовано логарифмічне співвідношення рівнів спектральних складових.


## 2. Схема складання аналізатора

![Microphone_to_fft](https://github.com/Alex-Teteria/Audio-spectrum-analyzer-on-ESP32-with-16x16-LED-screen/assets/94607514/c6ebc0d4-dcde-469f-9ded-90e17a0b98d9)  

## 3. Приклад відображення аудіосигналу

