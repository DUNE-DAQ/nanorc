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

class CommandSender(threading.Thread):
    '''
    A class to send command to the node
    '''
    STOP="COMMAND_QUEUE_STOP"

    def __init__(self, node):
        threading.Thread.__init__(self, name=f"command_sender_{node.name}")
        self.node = node
        self.queue = Queue()


    def add_command(self, cmd):
        self.queue.put(cmd)


    def run(self):
        while True:
            command = self.queue.get()
            if command == self.STOP:
                break
            if command:
                cmd = getattr(self.node, command, None)
                if not cmd:
                    raise RuntimeError(f"ERROR: {self.node.name}: I don't know of '{command}'")
                self.node.console.log(f"{self.node.name} Ack: executing '{command}'")
                cmd()
                self.node.console.log(f"{self.node.name} Finished '{command}'")


    def stop(self):
        self.queue.put_nowait(self.STOP)
        self.join()

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

        self.command_sender = CommandSender(self)
        self.command_sender.start()
        self.status_receiver_queue = Queue()

    def send_command(self, command):
        ## Use the command_sender to send commands
        self.command_sender.add_command(command)

    def on_enter_terminate_ing(self, _) -> NoReturn:
        if self.children:
            for child in self.children:
                child.terminate()
        self.command_sender.stop()
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
            if not self.status_receiver_queue.empty():
                response = self.status_receiver_queue.get()

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
            finalisor = getattr(self, "end_"+command, None)
            finalisor(response=response)


    def _on_exit_callback(self, event):
        response = event.kwargs.get("response")
        if self.parent:
            self.parent.status_receiver_queue.put(response)

    def send_cmd(self, cmd:str, path:[str]=None, raise_on_fail:bool=True, timeout=30, *args, **kwargs) -> int:

        if path:
            r = Resolver('name')
            prompted_path = "/".join(path)
            node = r.get(self, prompted_path)
        else:
            node = self

        self.log.info(f"Sending {cmd} to {node.name}, timeout={timeout}")

        if not node:
            ## Probably overkill
            raise RuntimeError(f"The node {'/'.join(path)} doesn't exist!")

        command = getattr(node, cmd, None)
        if not command:
            raise RuntimeError(f"{node.name} doesn't know how to execute {cmd}")

        try:
            command(raise_on_fail=raise_on_fail, timeout=timeout, *args, **kwargs)
        except MachineError as e:
            self.return_code = ErrorCode.InvalidTransition
            self.log.error(f"FSM Error: You are not allowed to send \"{cmd}\" to {node.name} as it is in \"{node.state}\" state. Error:\n{str(e)}")
            return self.return_code
        except Exception as e:
            self.return_code = ErrorCode.Failed
            if raise_on_fail:
                raise RuntimeError(f"Execution of {cmd} failed on {node.name}") from e
            else:
                return self.return_code

        return 0
