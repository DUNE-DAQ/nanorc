from elisa_client_api.elisa import Elisa
from elisa_client_api.searchCriteria import SearchCriteria
from elisa_client_api.messageInsert import MessageInsert
from elisa_client_api.messageReply import MessageReply
from elisa_client_api.exception import *

import logging
import os.path
import subprocess
import copy
import time


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
        self.log = logging.getLogger(self.__class__.__name__)
        self._start_new_message_thread()

    def _start_new_message_thread(self):
        self.log.info("ELisA logbook: Next message will be a new thread")
        self.current_id = None
        self.current_run = None
        self.current_run_type = None


    def _generate_new_sso_cookie(self):
        self.log.info("ELisA logbook: Regenerating the SSO cookie?")
        SSO_COOKIE_TIMEOUT=3600.*2.
        SSO_COOKIE_PATH=os.path.expanduser("~/.sso_cookie.txt")
        max_tries = 3
        it_try = 0
        args=["cern-get-sso-cookie", "--krb", "-r", "-u", "https://np-vd-coldbox-elog.cern.ch", "-o", f"{SSO_COOKIE_PATH}"]
        if not os.path.isfile(SSO_COOKIE_PATH) or time.time() - os.path.getmtime(SSO_COOKIE_PATH)>SSO_COOKIE_TIMEOUT:
            while True:
                try:
                    self.log.info("ELisA logbook: Regenerating the SSO cookie!")
                    proc = subprocess.run(args)
                    if proc.returncode != 0:
                        self.log.error("ELisA logbook: Couldn't get SSO cookie!")
                        raise RuntimeError("ELisA logbook: Couldn't get SSO cookie!")
                    return SSO_COOKIE_PATH
                except Exception as e:
                    if it_try<max_tries:
                        self.log.error("ELisA logbook: Trying once more...")
                    else:
                        self.log.error(f"ELisA logbook: NanoRC couldn't execute\n{' '.join(args)}\nPlz try yourself in a different shell after doing a kinit.")
                        raise RuntimeError("ELisA logbook: Couldn't get SSO cookie!") from e
                it_try += 1



    def _respond_to(self, subject:str, body:str, author:str, mtype:str):
        elisa_arg = copy.deepcopy(self.elisa_arguments)
        sso = {"ssocookie": self._generate_new_sso_cookie()}
        elisa_arg.update(sso)

        if not self.current_id:
            self.log.info("ELisA logbook: Creating a new thread")
            elisa_inst = Elisa(**elisa_arg)
            message = MessageInsert()
            message.author = author
            message.subject = subject
            message.type = "Automatic"
            message.Automatic_Message_Type = mtype
            message.systemsAffected = ["DAQ"]
            message.body = body
            try:
                ret = elisa_inst.insertMessage(message)
            except ElisaError as ex:
                self.log.error(f"ELisA logbook: {str(ex)}")
                self.log.error(ret)
                raise ex
            self.current_id = ret.id
        else:
            self.log.info(f"ELisA logbook: Answering to message ID{self.current_id}")
            elisa_inst = Elisa(**elisa_arg)
            message = MessageReply(self.current_id)
            message.author = author
            message.systemsAffected = ["DAQ"]
            message.Automatic_Message_Type = mtype
            message.body = body
            try:
                ret = elisa_inst.replyToMessage(message)
            except ElisaError as ex:
                self.log.error(f"ELisA logbook: {str(ex)}")
                self.log.error(ret)
                raise ex
            ## store for next time around...
            self.current_id = ret.id
        self.log.info(f"ELisA logbook: Sent message (ID{self.current_id})")



    def message_on_start(self, message:str, run_num:int, run_type:str, user:str):
        self.current_run_num = run_num
        self.current_run_type = run_type

        text = f"<p>User {user} started run {self.current_run_num} of type {self.current_run_type}</p>"
        if message != "":
            text += "<p>"+user+": "+message+"</p>"
        else:
            text += "<p>log automatically generated by NanoRC.</p>"
        title = f"{user} started new run {self.current_run_num} ({self.current_run_type})"
        self._respond_to(subject=title, body=text, author=user, mtype="SoR")

    def add_message(self, message:str, user:str):
        if message != "":
            text = "<p>"+user+": "+message+"</p>"
            self._respond_to(subject="User comment", body=text, author=user, mtype="Alarm")

    def message_on_stop(self, message:str, user:str):
        if message!="":
            text = "<p>"+user+": "+message+"</p>"
        else:
            text += "<p>log automatically generated by NanoRC.</p>"
        text += f"<p>User {user} finished run {self.current_run_num}</p>"
        title = f"{user} ended run {self.current_run_num} ({self.current_run_type})"
        self._respond_to(subject=title, body=text, author=user, mtype="EoR")
        self._start_new_message_thread()