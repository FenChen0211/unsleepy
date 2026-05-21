#!/usr/bin/python3
# coding: utf-8

from os import path, system
from sys import argv, executable
from time import sleep

SERVER_PATH = 'main.py'  # main.py 相对路径
WAIT_TIME = 5  # 等待时间 (s)

c = 0  # count
selfn = argv[0]  # self
dirn = path.dirname(selfn)  # self dir
server = path.join(dirn, SERVER_PATH)  # main.py path
print(f'[Start] Server path: {server}')
while True:
    c += 1
    print(f'[Start] Starting server #{c}')
    r = system(f'"{executable}" "{server}"')
    print(f'[Start] #{c} exited with code {r}')
    print(f'[Start] wait {WAIT_TIME}s')
    sleep(WAIT_TIME)
