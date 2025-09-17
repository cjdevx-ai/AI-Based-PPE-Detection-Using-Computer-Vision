import pygame
import time

pygame.init()
pygame.mixer.init()

pygame.mixer.music.set_volume(1.0)
pygame.mixer.music.load('voices/1.mp3')
pygame.mixer.music.play()
while pygame.mixer.music.get_busy():
    time.sleep(0.1)
time.sleep(5)
pygame.mixer.music.load('voices/2.mp3')
pygame.mixer.music.play()
while pygame.mixer.music.get_busy():
    time.sleep(0.1)
