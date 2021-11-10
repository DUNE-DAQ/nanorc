from elisa_client_api.elisa import Elisa
from elisa_client_api.messageInsert import MessageInsert

import os.path

class FileLogbook:
    def __init__(self, path:str, console):
        self.path = path
        self.file_name = ""
        self.console = console

    def message_on_start(self, message:str, run_num:int, run_type:str):
        self.file_name = self.path+f"_{run_num}_{run_type}.txt"
        f = open(self.file_name, "w")
        f.write(f"-- Starting run {run_num}, of type {run_type} --\n")
        f.write(message+"\n")
        f.close()

    def add_message(self, message:str):
        if not (os.path.exists(self.file_name) and os.path.isfile(self.file_name)):
            raise RuntimeError("Cannot add a message if we haven't started the run")
        f = open(self.file_name, "a")
        f.write(message+"\n")
        f.close()

    def message_on_stop(self, message:str):
        if not (os.path.exists(self.file_name) and os.path.isfile(self.file_name)):
            raise RuntimeError("Cannot add a message if we haven't started the run")
        f = open(self.file_name, "a")
        f.write(message+"\n")
        f.close()


class ElisaLogbook:
    def __init__(self, connection:str, cookie_path:str, console):
        self.console = console
        self.elisa_arguments={"connection":connection,
                              "ssocookie": os.path.expanduser(cookie_path)}
        self.current_id = None
        self.current_run = None

    def _start_new_thread(self):
        self.current_id = None
        self.current_run = None

    def _respond_to(self, subject:str, body:str):

        if not self.original_id:
            elisa_inst = Elisa(**self.arguments)
            message = MessageInsert()
            message.subject = subject
            message.type = "Default"
            message.systemsAffected = ["DAQ"]
            message.body = body
            ret = self.elisa_instance.insertMessage(message)
            self.current_id = ret.id
        else:
            ## hack in the connection for an reply to a message (why not?)
            ## according to https://atlasdaq.cern.ch/elisaAPIdoc/elisa-rest-api/protocol.html#reply-to-a-message
            ## if we post a message to messages/4442050 we should respond to message 4442050
            reply_arguments = self.elisa_arguments
            reply_arguments["connection"] += f"/messages/{self.id}"
            elisa_inst = Elisa(**reply_arguments)
            message = MessageInsert()
            message.subject = subject
            message.type = "Default"
            message.systemsAffected = ["DAQ"]
            message.body = body
            ret = self.elisa_instance.insertMessage(message)
            ## store for next time around...
            self.current_id = ret.id



    def message_on_start(self, message:str, run_num:int, run_type:str):
        text = f"Started run {run_num} of type {run_type}\n"
        text += message+"\n"
        title = f"New run {run_num} ({run_type})"
        self._respond_to(subject=title, body=text)

    def add_message(self, message:str):
        text = message+"\n"
        self._respond_to(subject="NanoRC comment", body=text)

    def message_on_stop(self, message:str):
        text = message+"\n"
        text += f"Finished run {run_num}\n"
        title = f"End run {run_num} ({run_type})"
        self._respond_to(subject=title, body=text)
        self._start_new_thread()
