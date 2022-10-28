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
        self.website = self.file_name
        self.console = console
        self.run_num = ""
        self.run_type = ""

    def message_on_start(self, message:str, apparatus:str, run_num:int, run_type:str):
        self.run_num = run_num
        self.run_type = run_type
        self.file_name = self.path+f"_{apparatus}_{self.run_num}_{self.run_type}.txt"
        self.website = self.file_name
        f = open(self.file_name, "w")
        f.write(f"-- User {credentials.user} started a run {self.run_num}, of type {self.run_type} on {apparatus} --\n")
        f.write(credentials.user+": "+message+"\n")
        f.close()

    def add_message(self, message:str, apparatus:str):
        self.file_name = self.path+f"_{apparatus}_{self.run_num}_{self.run_type}.txt"
        f = open(self.file_name, "a")
        f.write(credentials.user+": "+message+"\n")
        f.close()

    def message_on_stop(self, message:str, apparatus:str):
        self.file_name = self.path+f"_{apparatus}_{self.run_num}_{self.run_type}.txt"
        f = open(self.file_name, "a")
        f.write(f"-- User {credentials.user} stopped the run {self.run_num}, of type {self.run_type} on {apparatus} --\n")
        f.write(credentials.user+": "+message+"\n")
        f.close()

class ElisaLogbook:
    def __init__(self, AID):
        self.socket = json.loads(resources.read_text(confdata, "elisa_service.json"))['socket']
        self.apparatus_id = AID
        self.run_num = ""
        self.run_type = ""

    def message_on_start(self, message:str, run_num:int, run_type:str):
        self.run_num = run_num
        self.run_type = run_type
        payload = {'apparatus_id': self.apparatus_id, 'author': credentials.user, 'message': message, 'run_num': self.run_num, 'run_type': self.run_type}
        address = self.socket + "/v1/elisaLogbook/message_on_start/"
        myauth = (credentials.get_login("logbook").user, credentials.get_login("logbook").password)
        r = requests.post(address, data=payload, auth=myauth)
        rtext = r.content
        self.message_thread_id = ((rtext.split())[-1]).strip()

    def add_message(self, message:str):
        payload = {'apparatus_id': self.apparatus_id, 'author': credentials.user, 'message': message, 'thread_id': self.message_thread_id}
        address = self.socket + "/v1/elisaLogbook/add_message/"
        myauth = (credentials.get_login("logbook").user, credentials.get_login("logbook").password)
        r = requests.put(address, data=payload, auth=myauth)

    def message_on_stop(self, message:str):
        payload = {'apparatus_id': self.apparatus_id, 'author': credentials.user, 'message': message, 'run_num': self.run_num, 'run_type': self.current_run_type, 'thread_id': self.message_thread_id}
        address = self.socket + "/v1/elisaLogbook/message_on_stop/"
        myauth = (credentials.get_login("logbook").user, credentials.get_login("logbook").password)
        r = requests.put(address, data=payload, auth=myauth)
