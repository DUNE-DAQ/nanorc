from anytree import NodeMixin, RenderTree, PreOrderIter
from typing import Union, NoReturn
import logging
from enum import Enum
import threading
from queue import Queue
from transitions.core import MachineError
import time
from .fsm import FSM

class ErrorCode(Enum):
    Success=0
    Timeout=10
    Failed=20
    InvalidTransition=30

class GroupNode(NodeMixin):
    def __init__(self, name:str, console, fsm_conf, parent=None, children=None):
        self.console = console
        self.log = logging.getLogger(self.__class__.__name__+"_"+name)

        self.name = name

        self.parent = parent
        if children:
            self.children = children

        self.fsm_conf = fsm_conf
        self.fsm = FSM(fsm_conf)
        self.fsm.make_node_fsm(self)
        self.return_code = ErrorCode.Success
        self.status_receiver_queue = Queue()


    def on_enter_terminate_ing(self, _) -> NoReturn:
        if self.children:
            for child in self.children:
                child.terminate()
        self.end_terminate()


    def on_enter_error(self, event):
        kwargs = event.kwargs
        excp = kwargs.get("exception")
        trace = kwargs.get('trace')
        original_event = kwargs.get('event')
        command = ""
        etext = ""
        ssh_exit_code = ""
        if original_event: command = original_event.event.name

        if command == "" and kwargs.get('response'):
            command = kwargs.get('response')["command"]

        if excp: etext = f", an exception was thrown: {str(excp)},\ntrace: {trace}"

        if event.kwargs.get("ssh_exit_code"): ssh_exit_code = f", the following error code was sent from ssh: {event.kwargs['ssh_exit_code']}"

        self.log.error(f"while trying to \"{command}\" \"{self.name}\""+etext+ssh_exit_code)


    def _on_enter_callback(self, event):
        command = event.event.name
        self.log.info(f"{self.name} received command '{command}'")

        still_to_exec = []
        for child in self.children:
            still_to_exec.append(child) # a record of which children still need to finish their task
            child.trigger(command, **event.kwargs)

        failed_resp = []
        for _ in range(event.kwargs["timeout"]):
            response = self.status_receiver_queue.get()
            if response:
                for child in self.children:
                    if response["node"] == child.name:
                        still_to_exec.remove(child)

                        if response["status_code"] != ErrorCode.Success:
                            failed_resp.append(response)

            if len(still_to_exec) == 0 or len(failed_resp)>0: # if all done, continue
                break

            time.sleep(1)

        timeout = still_to_exec

        if len(still_to_exec) > 0:
            self.log.error(f"{self.name} can't {command} because following children timed out: {[n.name for n in timeout]}")

        ## We still need to do that manually, since they are still in their transitions
        for node in timeout:
            response = {
                "state": self.state,
                "command": event.event.name,
                "node": node.name,
                "failed": [n.name for n in timeout],
                "error": "Timed out after waiting for too long, or because a sibling went on error",
            }
            node.to_error(event=event, response=response)

        ## For the failed one, we have gone on error state already
        if failed_resp:
            self.log.error(f"{self.name} can't {command} because following children had error: {[n['node'] for n in failed_resp]}")

        status = ErrorCode.Success
        if len(still_to_exec)>0:
            status = ErrorCode.Timeout
        if len(failed_resp)>0:
            status = ErrorCode.Failed

        response = {
            "status_code" : status,
            "state": self.state,
            "command": event.event.name,
            "node": self.name,
            "timeouts": [n.name for n in timeout],
            "failed": [n['node'] for n in failed_resp],
            "error": [n['error'] for n in failed_resp]
        }

        if status != ErrorCode.Success:
            self.to_error(event=event, response=response)
        else:
            # Initiate the transition on this node to say that we have finished
            self.trigger("end_"+command, response=response)


    def _on_exit_callback(self, event):
        response = event.kwargs.get("response")
        if self.parent:
            self.parent.status_receiver_queue.put(response)
        if response:
            self.response = response
            return response['status_code']
        else:
            return ErrorCode.Success

