import machine, neopixel, time

'''
library:
    neo_matrix
'''
class Np():
    def __init__(self, n, m, neo_pin):
        self.n = n # кількість рядків матриці
        self.m = m # кількість стовпців матриці
        self.np = neopixel.NeoPixel(machine.Pin(neo_pin), self.n * self.m) # примірник класу NeoPixel, neo_pin - вихід на LED
        # визначення кольорів:
        self.green = 0, 8, 0
        self.red = 8, 0, 0
        self.blue = 0, 0, 8
        self.magenta = 4, 0, 4
        self.yellow = 5, 3, 0
        self.teal = 0, 5, 3
        self.nothing = 0, 0, 0
        
    def clear(self):
        for i in range(len(self.np)):
            self.np[i] = 0, 0, 0
        self.np.write()  

    def write_led(self, l):
        for row in range(self.n):
            for col in range(self.m):
                self.np[self.koef_to_pix(row, col)] = l[row][col]
        self.np.write()

    def koef_to_pix(self, i, j):
        '''
        отримує коефіцієнти матриці (row x col) row = i, col =  j
        вертає neopixel-коефіцієнт LED-матриці
        '''
        return self.m * i + j if i % 2 else self.m-j-1 + self.m * i

class Pix():
    def __init__(self, x=0, y=0, run=True, cnt=0) -> None:
        self.x = x # координата х
        self.y = y # координата у
        self.run = run # True - рухається, False - стоїть
        self.cnt = cnt # лічильник стану, коли немає можливості рухатись
        
    def direction(self, where):
        if where == 'r':
            self.x += 1
            self.cnt = 0
        elif where == 'down':
            self.y += 1
            self.cnt = 0
        elif where == 'left':
            self.x -= 1
            self.cnt = 0
        elif where == 'up':
            self.y -= 1
            self.cnt = 0
        else:
            self.run = False
            self.cnt += 1
        
    def f_move(self, direction, l_ban):
        if direction == 'r':
            condition = (self.y, self.x + 1) not in l_ban
        elif direction == 'down':
            condition = (self.y + 1, self.x) not in l_ban
        elif direction == 'left':
            condition = (self.y, self.x - 1) not in l_ban
        elif direction == 'up':
            condition = (self.y - 1, self.x) not in l_ban    
        self.direction(direction) if condition else self.direction('not_run')
        
class Rectangles():
    def __init__(self, pix, n, m):
        self.pix = pix # примірник класу Pix
        self.n = n # кількість рядків
        self.m = m # кількість стовпців
    
    def gen_rect(self):
        def border(i, j):
            return i == -1 or i == self.n or j == -1 or j == self.m
        l_ban = [(i, j) for j in range(-1, self.m+1) for i in range(-1, self.n+1) if border(i, j)]
        l_move = []
        d_rect = {} # словник списків координат (i,j) квадратів
        key = 0
        t_move = ('r', 'down', 'left', 'up')

        def move_pix(direction, pix, l_ban, l_move):
            while pix.run:
                if (pix.y, pix.x) not in l_ban:
                    l_ban.append((pix.y, pix.x))
                    l_move.append((pix.y, pix.x))
                pix.f_move(direction, l_ban)
            pix.run = True
            return pix, l_ban, l_move
    
        # формуємо словник d_rect типу: {0:[(i1,j1),...], 1:[(i1,j1),...], ... }
        # послідовно обходимо матрицю координат n x m за напрямками 'r','down','left','up',
        # при цьому збільшуємо список заборонених координат l_ban (координати по яким вже рухались)
        # та формуємо список координат прямокутників l_move (контури прямокутників)
        while self.pix.cnt < 2:
            for el in t_move:
                self.pix, l_ban, d_rect[key] = move_pix(el, self.pix, l_ban, l_move)
            l_move = []
            key += 1
        
        # формуємо словник d_rect_fill - заповнені прямокутники
        d_rect_fill = {} 
        d_rect_fill[0] = d_rect[len(d_rect)-1]
        for i in range(1, len(d_rect)):
            d_rect_fill[i] = d_rect[len(d_rect)-1-i] + d_rect_fill[i-1]

        return d_rect, d_rect_fill
            
