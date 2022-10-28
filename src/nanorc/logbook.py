import logging
import os.path
import subprocess
import copy
import time
from .credmgr import credentials

class FileLogbook:
    def __init__(self, path:str, console):
        self.path = path
        self.file_name = ""
        self.console = console
        self.run_num = ""
        self.run_type = ""

    def message_on_start(self, message:str, run_num:int, run_type:str):
        self.run_num = run_num
        self.run_type = run_type
        self.file_name = self.path+f"_{self.run_num}_{self.run_type}.txt"
        f = open(self.file_name, "w")
        f.write(f"-- User {credentials.user} started a run {self.run_num}, of type {self.run_type} --\n")
        f.write(credentials.user+": "+message+"\n")
        f.close()

    def add_message(self, message:str):
        self.file_name = self.path+f"_{self.run_num}_{self.run_type}.txt"
        f = open(self.file_name, "a")
        f.write(credentials.user+": "+message+"\n")
        f.close()

    def message_on_stop(self, message:str):
        self.file_name = self.path+f"_{self.run_num}_{self.run_type}.txt"
        f = open(self.file_name, "a")
        f.write(f"-- User {credentials.user} stopped the run {self.run_num}, of type {self.run_type} --\n")
        f.write(credentials.user+": "+message+"\n")
        f.close()
