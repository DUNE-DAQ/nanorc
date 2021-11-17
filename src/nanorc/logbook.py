from elisa_client_api.elisa import Elisa
from elisa_client_api.searchCriteria import SearchCriteria
from elisa_client_api.messageInsert import MessageInsert
from elisa_client_api.exception import *

import logging
import os.path
import subprocess
import copy

class FileLogbook:
    def __init__(self, path:str, console):
        self.path = path
        self.file_name = ""
        self.console = console

    def message_on_start(self, message:str, run_num:int, run_type:str, user:str):
        self.file_name = self.path+f"_{run_num}_{run_type}.txt"
        f = open(self.file_name, "w")
        f.write(f"-- User {user} started a run {run_num}, of type {run_type} --\n")
        f.write(user+": "+message+"\n")
        f.close()

    def add_message(self, message:str, user:str):
        if not (os.path.exists(self.file_name) and os.path.isfile(self.file_name)):
            raise RuntimeError("Cannot add a message if we haven't started the run")
        f = open(self.file_name, "a")
        f.write(user+": "+message+"\n")
        f.close()

    def message_on_stop(self, message:str, user:str):
        if not (os.path.exists(self.file_name) and os.path.isfile(self.file_name)):
            raise RuntimeError("Cannot add a message if we haven't started the run")
        f = open(self.file_name, "a")
        f.write(user+": "+message+"\n")
        f.close()


class ElisaLogbook:
    def __init__(self, connection:str, console):
        self.console = console
        self.elisa_arguments={"connection":connection}
        self.current_id = None
        self.current_run = None
        self.log = logging.getLogger(self.__class__.__name__)

    def _start_new_message_thread(self):
        self.current_id = None
        self.current_run = None


    def _generate_new_sso_cookie(self):
        SSO_COOKIE_PATH=os.path.expanduser("~/.sso_cookie.txt")
        args=["cern-get-sso-cookie", "--krb", "-r", "-u", "https://np-vd-coldbox-elog.cern.ch", "-o", f"{SSO_COOKIE_PATH}"]
        proc = subprocess.run(args)
        if proc.returncode != 0:
            self.log.error("Couldn't get SSO Cookie!")
            raise RuntimeError("Couldn't get SSO cookie!")
        return SSO_COOKIE_PATH

    def _respond_to(self, subject:str, body:str, author:str):
        elisa_arg = copy.deepcopy(self.elisa_arguments)
        sso = {"ssocookie": self._generate_new_sso_cookie()}
        elisa_arg.update(sso)
        
        if not self.original_id:
            elisa_inst = Elisa(**elisa_arg)
            message = MessageInsert()
            message.author = author
            message.subject = subject
            message.type = "Default"
            message.systemsAffected = ["DAQ"]
            message.body = body
            try:
                ret = self.elisa_instance.insertMessage(message)
            except ElisaError as ex:
                self.log.error(str(ex))
            self.current_id = ret.id
        else:
            ## hack in the connection for an reply to a message (why not?)
            ## according to https://atlasdaq.cern.ch/elisaAPIdoc/elisa-rest-api/protocol.html#reply-to-a-message
            ## if we post a message to messages/4442050 we should respond to message 4442050
            reply_arguments = elisa_arg
            reply_arguments["connection"] += f"/messages/{self.id}"
            elisa_inst = Elisa(**reply_arguments)
            message = MessageInsert()
            message.subject = subject
            message.author = author
            message.type = "Default"
            message.systemsAffected = ["DAQ"]
            message.body = body
            try:
                ret = self.elisa_instance.insertMessage(message)
            except ElisaError as ex:
                self.log.error(str(ex))
            ## store for next time around...
            self.current_id = ret.id



    def message_on_start(self, message:str, run_num:int, run_type:str, user:str):
        text = f"User {user} started run {run_num} of type {run_type}\n"
        if message != "":
            text += user+": "+message+"\n"
        title = f"{user} started new run {run_num} ({run_type})"
        self._respond_to(subject=title, body=text, author=user)

    def add_message(self, message:str, user:str):
        if message != "":
            text = user+": "+message+"\n"
            self._respond_to(subject="NanoRC comment", body=text, author=user)

    def message_on_stop(self, message:str, user:str):
        if message!="":
            text = user+": "+message+"\n"
        text += f"User {user} finished run {run_num}\n"
        title = f"{user} ended run {run_num} ({run_type})"
        self._respond_to(subject=title, body=text, author=user)
        self._start_new_message_thread()



