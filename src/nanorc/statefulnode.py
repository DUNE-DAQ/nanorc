from anytree import NodeMixin, RenderTree, PreOrderIter
from typing import Union, NoReturn
import logging
from enum import IntEnum
import threading
from queue import Queue
from transitions.core import MachineError
import time
from .fsm import FSM

class ErrorCode(IntEnum):
    Success=0
    Timeout=10
    Failed=20
    InvalidTransition=30
    Aborted=40

class CanExecuteReturnVal(IntEnum):
    CanExecute=0
    InvalidTransition=1
    NotInitialised=2
    Dead=3
    InError=4

    def __str__(self):
        if   self.value == CanExecuteReturnVal.CanExecute       : return "CanExecute"
        elif self.value == CanExecuteReturnVal.InvalidTransition: return "InvalidTransition"
        elif self.value == CanExecuteReturnVal.NotInitialised   : return "NotInitialised"
        elif self.value == CanExecuteReturnVal.Dead             : return "Dead"
        elif self.value == CanExecuteReturnVal.InError          : return "InError"


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
        self.errored = False


    def can_execute_custom_or_expert(self, command, quiet=True, check_dead=True, check_inerror=True, only_included=True):
        disallowed_state = ['booted', 'none']
        if self.errored and check_inerror:
            return CanExecuteReturnVal.InError

        if self.state in disallowed_state:
            if not quiet:
                self.log.error(f"Cannot send '{command}' to '{self.name}' as it should at least be initialised")
            return CanExecuteReturnVal.NotInitialised

        if check_dead or check_inerror:
            for c in self.children:
                if not c.included and only_included: continue

                ret = c.can_execute_custom_or_expert(
                    command = command,
                    quiet = quiet,
                    check_dead = check_dead,
                    check_inerror = check_inerror,
                    only_included = only_included,
                )
                if ret!=CanExecuteReturnVal.CanExecute:
                    self.return_code = ErrorCode.Failed
                    return ret

        self.return_code = ErrorCode.Success
        return CanExecuteReturnVal.CanExecute


    def can_execute(self, command, quiet=False, check_dead=True, check_inerror=True, only_included=True):
        if self.errored and check_inerror:
            return CanExecuteReturnVal.InError

        can_transition = getattr(self, "can_"+command)
        if not can_transition:
            if not quiet:
                self.log.error(f"'{self.name}' cannot check if command '{command}' is possible")
        else:
            if not can_transition():
                if not quiet:
                    self.log.error(f"'{self.name}' cannot '{command}' as it is '{self.state}'")
                    self.return_code = ErrorCode.InvalidTransition
                return CanExecuteReturnVal.InvalidTransition

        if check_dead or check_inerror:
            for c in self.children:
                if not c.included and only_included: continue

                # How do I get rid of this enormity?
                if command=='terminate' and c.state=='none':
                    continue

                ret = c.can_execute(
                    command = command,
                    quiet = quiet,
                    check_dead = check_dead,
                    check_inerror = check_inerror,
                    only_included = only_included,
                )
                if ret != CanExecuteReturnVal.CanExecute:
                    self.return_code = ErrorCode.Failed
                    return ret

        self.return_code = ErrorCode.Success
        return CanExecuteReturnVal.CanExecute


    def exclude(self):
        if not self.included:
            self.log.error(f'Cannot exclude \'{self.name}\' as it is already excluded!')
            return 1

        self.log.info(f'Excluding \'{self.name}\'')
        ret = 0
        for child in self.children:
            ret += child.exclude()

        self.resolve_error()
        self.included = False
        return ret

    def include(self):
        if self.included:
            self.log.error(f'Cannot include \'{self.name}\' as it is already included!')
            return 1

        self.log.info(f'Including \'{self.name}\'')
        ret = 0
        for child in self.children:
            ret += child.include()

        self.resolve_error()
        self.included = True
        return 0

    def get_custom_commands(self):
        ret = {}
        for c in self.children:
            ret.update(c.get_custom_commands())
        return ret

    def send_custom_command(self, cmd, data, timeout) -> dict:
        ret = {}
        is_include_exclude = cmd=='include' or cmd=='exclude'

        for c in self.children:
            if not is_include_exclude and not c.included: continue
            self.console.log(f"Sending {cmd} to {c.name}")
            ret[c.name] = c.send_custom_command(cmd, data, timeout)
        self.resolve_error()
        return ret


    def on_enter_terminate_ing(self, _) -> NoReturn:
        if self.children:
            for child in self.children:
                if child.can_execute('terminate', quiet=True) == CanExecuteReturnVal.CanExecute:
                    child.terminate()
                else:
                    self.log.info(f'Force terminating on {child.name}')
                    child.to_terminate_ing()
        self.resolve_error()
        self.end_terminate()
        self.included = True

    def on_enter_abort_ing(self, _) -> NoReturn:
        if self.children:
            for child in self.children:
                child.abort()
        self.resolve_error()
        self.end_abort()

    def resolve_error(self):
        state=None
        errored=False
        self.log.debug(f'{self.name} resolve errors!')

        for child in self.children:
            if not child.included:
                continue
            child.resolve_error()
            if child.errored:
                errored=True

            if not state:
                state = child.state

            if state != child.state:
                errored=True

        self.log.debug(f'{self.name}: errored? {errored}')
        self.errored = errored


    def to_error(self, command="", exception=None, text=None, ssh_exit_code=None):
        etext = f'{self.name} went to error!\n'

        if text:
            etext += text+"\n"

        if command != "":
            etext += f"An error occured while executing {command}\n"

        if exception:
            etext += f"An exception was thrown: {str(exception)}\n"

        if ssh_exit_code:
            etext += f"The following error code was sent from ssh: {ssh_exit_code}"

        self.log.error(etext)
        self.errored = True

    def _on_enter_callback(self, event):
        command = event.event.name
        self.log.info(f"'{self.name}' received command '{command}'")
        source_state = event.transition.source
        force = event.kwargs.get('force')

        if command in self.order:
            self.log.info(f'Propagating to the included children nodes in the order {self.order[command]}')
        else:
            self.order[command] = [c.name for c in self.children]
            self.log.info(f'Propagating to children nodes in the order: {self.order[command]}')

        status = ErrorCode.Success
        failed = []

        for cn in self.order[command]:
            child = [c for c in self.children if c.name == cn][0]
            if not child.included: continue
            self.log.info(f'Sending {command} to {child.name}')
            try:
                child.trigger(command, **event.kwargs)
                for _ in range(event.kwargs["timeout"]):
                    response = self.status_receiver_queue.get()
                    if response:
                        if response["node"] == child.name:
                            if response["status_code"] != ErrorCode.Success:
                                failed+=[child.name]
                                raise RuntimeError(f"Failed to {command} {child.name}, error {str(response)}")
                            else:
                                break

                    time.sleep(1)

            except Exception as e:
                if force:
                    self.log.error(f'Failed to send \'{command}\' to \'{child.name}\', --force was specified so continuing anyway, {str(e)}')
                    continue
                status = ErrorCode.Failed

        response = {
            "status_code" : status,
            "state": self.state,
            "command": event.event.name,
            "node": self.name,
        }

        self.return_code = status

        if status != ErrorCode.Success:
            self.to_error(
                text=f'Children nodes {[f for f in failed]} failed to {command}',
                command=command,
            )
        # Initiate the transition on this node to say that we have finished
        self.resolve_error()
        self.trigger("end_"+command, response=response)

    def _on_exit_callback(self, event):
        response = event.kwargs.get("response")
        if self.parent:
            self.parent.status_receiver_queue.put(response)

        self.resolve_error()
        if response:
            self.response = response
            return response['status_code']
        else:
            return ErrorCode.Success
