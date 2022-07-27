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
    Aborted=40

class StatefulNode(NodeMixin):
    def __init__(self, name:str, console, log, fsm_conf, parent=None, children=None, order=None, verbose=False):
        self.console = console
        self.log = log

        self.name = name

        self.parent = parent
        if children:
            self.children = children

        self.fsm_conf = fsm_conf
        self.fsm = FSM(self.console, fsm_conf, verbose)
        self.fsm.make_node_fsm(self)
        self.return_code = ErrorCode.Success
        self.status_receiver_queue = Queue()
        self.order = order if order else dict()
        self.included = True


    def can_execute_custom_or_expert(self, command, check_dead=True):
        disallowed_state = ['booted', 'none']
        if self.state in disallowed_state:
            self.log.error(f"Cannot send '{command}' to '{self.name}' as it should at least be initialised")
            return False

        is_include_exclude = cmd=='include' or cmd=='exclude'

        for c in self.children:
            if not c.included and not is_include_exclude: continue

            if not c.can_execute_custom_or_expert(command, check_dead):
                self.return_code = ErrorCode.Failed
                return False

        self.return_code = ErrorCode.Success
        return True


    def can_execute(self, command, quiet=False):
        can_transition = getattr(self, "can_"+command)
        if not can_transition:
            self.log.info(f"'{self.name}' cannot check if command '{command}' is possible")
        else:
            if not can_transition():
                if not quiet:
                    self.log.error(f"'{self.name}' cannot '{command}' as it is '{self.state}'")
                    self.return_code = ErrorCode.InvalidTransition
                return False

        for c in self.children:
            if not c.included: continue

            if not c.can_execute(command):
                self.return_code = ErrorCode.Failed
                return False

        self.return_code = ErrorCode.Success
        return True


    def exclude(self):
        if not self.included:
            self.log.error(f'Cannot exclude \'{self.name}\' as it is already excluded!')
            return 1

        ret = 0
        for child in self.children:
            ret += child.exclude()

        self.included = False
        return ret

    def include(self):
        if self.included:
            self.log.error(f'Cannot include \'{self.name}\' as it is already included!')
            return 1

        ret = 0
        for child in self.children:
            ret += child.include()

        self.included = True
        return 0

    def get_custom_commands(self):
        ret = {}
        for c in self.children:
            ret.update(c.get_custom_commands())
        return ret

    def send_custom_command(self, cmd, data, timeout) -> dict:
        ret = {}
        for c in self.children:
            if c.included:
                ret[c.name] = c.send_custom_command(cmd, data, timeout)
        return ret


    def on_enter_terminate_ing(self, _) -> NoReturn:
        if self.children:
            for child in self.children:
                # if child.included:
                child.terminate()
        self.end_terminate()

    def on_enter_abort_ing(self, _) -> NoReturn:
        if self.children:
            for child in self.children:
                child.abort()
        self.end_abort()


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

        self.log.error(f"while trying to '{command}' '{self.name}'"+etext+ssh_exit_code)


    def _on_enter_callback(self, event):
        command = event.event.name
        self.log.info(f"'{self.name}' received command '{command}'")
        source_state = event.transition.source
        force = event.kwargs.get('force')

        if command in self.order:
            self.log.info(f'Propagating to the included children nodes in the order {self.order[command]}')
        else:
            self.order[command] = [c.name for c in self.children]
            self.log.info(f'Propagating to children nodes in the figured out order: {self.order[command]}')

        status = ErrorCode.Success

        for cn in self.order[command]:
            child = [c for c in self.children if c.name == cn][0]
            if not child.included: continue

            try:
                child.trigger(command, **event.kwargs)
                for _ in range(event.kwargs["timeout"]):
                    response = self.status_receiver_queue.get()
                    if response:
                        if response["node"] == child.name:
                            if response["status_code"] != ErrorCode.Success:
                                raise RuntimeError(f"Failed to {command} {child.name}, error {str(response)}")
                            else:
                                break

                    time.sleep(1)

            except Exception as e:
                if force:
                    self.log.error(f'Failed to send \'{command}\' to \'{child.name}\', --force was specified so continuing anyway')
                    continue
                status = ErrorCode.Failed
                break



        response = {
            "status_code" : status,
            "state": self.state,
            "command": event.event.name,
            # "comment": [n.get('comment') for n in
            "node": self.name,
        }

        self.return_code = status

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
