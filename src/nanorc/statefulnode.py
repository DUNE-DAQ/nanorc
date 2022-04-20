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
    def __init__(self, name:str, console, fsm_conf, parent=None, children=None, order=None, verbose=False):
        self.console = console
        self.log = logging.getLogger(self.__class__.__name__+"_"+name)

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
        self.enabled = True

    def disable(self):
        if not self.enabled:
            self.log.error(f'Cannot disable {self.name} as it is already disabled!')
            return
        self.enabled = False

    def enable(self):
        if self.enabled:
            self.log.error(f'Cannot enable {self.name} as it is already enabled!')
            return
        self.enabled = True

    def get_custom_commands(self):
        ret = {}
        for c in self.children:
            ret.update(c.get_custom_commands())
        return ret

    def send_custom_command(self, cmd, data) -> dict:
        ret = {}
        for c in self.children:
            if c.enabled:
                ret[c.name] = c.send_custom_command(cmd, data)
        return ret


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
        source_state = event.transition.source
        still_to_exec = []
        active_thread = []
        force = event.kwargs.get('force')
        if command in self.order:
            self.log.info(f'Propagating to the enabled children nodes in the order {self.order[command]}')

            for cn in self.order[command]:
                if not child.enabled: continue
                child = [c for c in self.children if c.name == cn][0]
                still_to_exec.append(child) # a record of which children still need to finish their task

                try:
                    child.trigger(command, **event.kwargs)
                except Exception as e:
                    if force:
                        self.log.error(f'Failed to send \'{command}\' to \'{child.name}\', --force was specified so continuing anyway')
                        continue
                    raise Exception from e
        else:
            self.log.info(f'{self.name} propagating to children nodes ({[c.name for c in self.children if c.enabled]}) simultaneously')
            for child in self.children:
                if not child.enabled: continue

                still_to_exec.append(child) # a record of which children still need to finish their task
                all_kwargs = {
                    "trigger_name":command,
                }
                all_kwargs.update(event.kwargs)
                thread = threading.Thread(target=child.trigger, kwargs=all_kwargs)
                thread.start()
                active_thread.append(thread)


        failed_resp = []
        aborted = False
        for _ in range(event.kwargs["timeout"]):
            response = self.status_receiver_queue.get()
            if response:
                for child in self.children:
                    if response["node"] == child.name:
                        still_to_exec.remove(child)

                        if response["status_code"] != ErrorCode.Success:
                            failed_resp.append(response)

                        if response['status_code'] == ErrorCode.Aborted:
                            aborted = True
                            break

            if aborted or len(still_to_exec) == 0 or len(failed_resp)>0: # if all done, continue
                break

            time.sleep(1)

        timeout = still_to_exec

        if len(still_to_exec) > 0 and not aborted:
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
        if failed_resp and not aborted:
            self.log.error(f"{self.name} can't {command} because following children had error: {[n['node'] for n in failed_resp]}")

        status = ErrorCode.Success
        if len(still_to_exec)>0:
            status = ErrorCode.Timeout
        if len(failed_resp)>0:
            status = ErrorCode.Failed
        if aborted:
            status = ErrorCode.Aborted

        response = {
            "status_code" : status,
            "state": self.state,
            "command": event.event.name,
            # "comment": [n.get('comment') for n in
            "node": self.name,
            "timeouts": [n.name for n in timeout],
            "failed": [n.get('node') for n in failed_resp],
            "error": [n.get('error') for n in failed_resp]
        }

        if aborted:
            self.log.info(f'Aborting command {command} on node {self.name}')
            self.trigger(f"to_{source_state}", response=response)
            self.return_code = ErrorCode.Aborted
            return

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
