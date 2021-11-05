from anytree import NodeMixin, RenderTree, PreOrderIter
from anytree.resolver import Resolver
from transitions import Machine
from transitions.core import MachineError
import time
import threading
from queue import Queue
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
import logging
from .sshpm import SSHProcessManager
from .appctrl import AppSupervisor, ResponseListener, ResponseTimeout, NoResponse
from typing import Union, NoReturn
from enum import Enum

log = logging.getLogger("transitions.core")
log.setLevel(logging.ERROR)
log = logging.getLogger("transitions")
log.setLevel(logging.ERROR)

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
    def __init__(self, name:str, console, parent=None, children=None):
        self.console = console
        self.name = name
        self.parent = parent
        self.log = logging.getLogger(self.__class__.__name__+"_"+self.name)
        if children:
            self.children = children
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


    def print_status(self, apparatus_id:str=None) -> int:
        if apparatus_id:
            table = Table(title=f"{apparatus_id} apps")
        else:
            table = Table(title=f"{apparatus_id} apps")
        table.add_column("name", style="blue")
        table.add_column("state", style="blue")
        table.add_column("host", style="magenta")
        table.add_column("alive", style="magenta")
        table.add_column("pings", style="magenta")
        table.add_column("last cmd")
        table.add_column("last succ. cmd", style="green")

        for pre, _, node in RenderTree(self):
            if isinstance(node, ApplicationNode):
                sup = node.sup
                alive = sup.desc.proc.is_alive()
                ping  = sup.commander.ping()
                last_cmd_failed = (sup.last_sent_command != sup.last_ok_command)
                table.add_row(
                    Text(pre)+Text(node.name),
                    Text(f"{node.state}", style=('bold red' if node.is_error() else "")),
                    sup.desc.host,
                    str(alive),
                    str(ping),
                    Text(str(sup.last_sent_command), style=('bold red' if last_cmd_failed else '')),
                    str(sup.last_ok_command)
                )

            else:
                table.add_row(Text(pre)+Text(node.name),
                              Text(f"{node.state}", style=('bold red' if node.is_error() else "")))

        self.console.print(table)

    def print(self, leg:bool=False) -> int:
        print_func = self.console.print
        rows = []
        try:
            for pre, _, node in RenderTree(self):
                if node == self:
                    # print_func(f"{pre}[red]{node.name}[/red]")
                    rows.append(f"{pre}[red]{node.name}[/red]")
                elif isinstance(node, SubsystemNode):
                    # print_func(f"{pre}[yellow]{node.name}[/yellow]")
                    rows.append(f"{pre}[yellow]{node.name}[/yellow]")
                elif isinstance(node, ApplicationNode):
                    # print_func(f"{pre}[blue]{node.name}[/blue]")
                    rows.append(f"{pre}[blue]{node.name}[/blue]")
                else:
                    rows.append(f"{pre}{node.name}")

            print_func(Panel.fit('\n'.join(rows)))

            if leg:
                print_func("\nLegend:")
                print_func(" - [red]top node[/red]")
                print_func(" - [yellow]subsystems[/yellow]")
                print_func(" - [blue]applications[/blue]\n")

        except Exception as ex:
            self.log.error(f"Tree is corrupted!")
            self.return_code = 14
            raise RuntimeError(f"Tree is corrupted")
        return 0

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

        still_to_exec = []
        for child in self.children:
            self.log.info(f"{self.name} is sending '{command}' to {child.name}")
            still_to_exec.append(child) # a record of which children still need to finish their task
            cmd_method = getattr(child, command, None)
            cmd_method(*event.args, **event.kwargs) # send the commands

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

# Now on to useful stuff
class ApplicationNode(GroupNode):
    def __init__(self, name, sup, console, parent=None):
        # Absolutely no children for ApplicationNode
        super().__init__(name=name, console=console, parent=parent, children=None)
        self.sup = sup

    def on_enter_boot_ing(self, _):
        # all this is delegated to the subsystem
        self.log.info(f"Booted {self.name}")


    def _on_enter_callback(self, event):
        comm = event.event.name
        self.log.info(f"{comm} to {self.name}")
        args = event.kwargs
        wait = args["wait"]
        data = args["data"]

        if wait:
            self.sup.send_command_and_wait(comm, data)
        else:
            self.sup.send_command(comm, data)

    def _on_exit_callback(self, event):
        # all this is delegated to the subsystem
        comm = event.event.name
        self.log.info(f"{comm} to {self.name}")

    def on_enter_terminate_ing(self, _):
        self.sup.terminate()
        self.command_sender.stop()

class SubsystemNode(GroupNode):
    def __init__(self, name:str, cfgmgr, console, parent=None, children=None, fsm=None):
        super().__init__(name=name, console=console, parent=parent, children=children)
        self.cfgmgr = cfgmgr
        self.pm = None
        self.listener = None
        self.fsm = fsm


    def on_enter_boot_ing(self, event) -> NoReturn:
        try:
            self.pm = SSHProcessManager(self.console)
            self.pm.boot(self.cfgmgr.boot)
        except Exception as e:
            self.console.print_exception()
            self.return_code = 11
            return

        self.listener = ResponseListener(self.cfgmgr.boot["response_listener"]["port"])
        children = []
        failed = []
        for n,d in self.pm.apps.items():
            child = ApplicationNode(name=n,
                                    console=self.console,
                                    sup=AppSupervisor(self.console, d, self.listener),
                                    parent=self)
            self.fsm.add_node(child)

            if child.sup.desc.proc.is_alive() and child.sup.commander.ping():
                child.to_booted()
            else:
                failed.append({
                    "node": child.name,
                    "status_code": 1,## I don't know
                    "command": "boot",
                    "error": "Not bootable",
                })
                child.to_error(event=event, command='boot')

            children.append(child)
        self.children = children
        status_code = ErrorCode.Success
        if failed:
           status_code = ErrorCode.Failed

        response = {
            "node": self.name,
            "status_code": status_code,
            "command": "boot",
            "failed": [f['node'] for f in failed],
            "error": failed,
        }
        if response['status_code'] != ErrorCode.Success:
            self.to_error(event=event, response=response)
        else:
            self.end_boot(response=response)


    def on_enter_terminate_ing(self, _) -> NoReturn:
        if self.children:
            for child in self.children:
                child.terminate()
                if child.parent.listener:
                    child.parent.listener.unregister(child.name)
                child.parent = None

        if self.listener:
            self.listener.terminate()
        if self.pm:
            self.pm.terminate()
        self.command_sender.stop()
        self.end_terminate()


    def _on_enter_callback(self, event):
        command = event.event.name
        cfg_method = event.kwargs.get("cfg_method")
        timeout = event.kwargs.get("timeout")
        self.log.info(f"Sending {command} to the subsystem {self.name}")

        sequence = getattr(self.cfgmgr, command+'_order', None)

        appset = list(self.children)
        failed = []

        if not sequence:
            # Loop over data keys if no sequence is specified or all apps, if data is empty

            for n in appset:
                # BERK I don't know how to sort this.
                # This is essntially calling cfgmgr.runtime_start(runtime_start_data)
                if cfg_method:
                    f=getattr(self.cfgmgr,cfg_method)
                    data = f(event.kwargs['overwrite_data'])
                else:
                    data = getattr(self.cfgmgr, command)

                child_command = getattr(n, command)
                child_command(wait=False, data=data[n.name] if data else {})

            start = datetime.now()

            while(appset):
                done = []
                for n in appset:
                    try:
                        r = n.sup.check_response()
                    except NoResponse:
                        continue

                    done += [n]

                    if r['success']:
                        child_end_command = getattr(n, "end_"+command)
                        child_end_command()
                    else:
                        response = {
                            "node":n.name,
                            "status_code" : r,
                            "state": n.state,
                            "command": command,
                            "error": r,
                        }
                        failed.append(response)

                        n.to_error(event=event, response=response)

                for d in done:
                    appset.remove(d)

                now = datetime.now()
                elapsed = (now - start).total_seconds()

                if elapsed > timeout:
                    raise RuntimeError("Send multicommand failed")

                time.sleep(0.1)
                self.log.debug("tic toc")

        else:
            # There probably is a way to do that in a much nicer, pythonesque, way
            for n in sequence:
                for child_node in appset:
                    if n == child_node.name:
                        if cfg_method:
                            f=getattr(self.cfgmgr,cfg_method)
                            data = f(overwrite_data)
                        else:
                            data = getattr(self.cfgmgr, command)

                        child_command = getattr(n, command)
                        child_command(wait=True, data=data[n.name] if data else {})
                        if r['success']:
                            child_end_command = getattr(n, "end_"+command)
                            child_end_command()
                        else:
                            response = {
                                "node":n.name,
                                "status_code" : r,
                                "state": n.state,
                                "command": command,
                                "error": r,
                            }
                            failed.append(response)
                            n.to_error(event=event, response=response)

        if failed:
            response = {
                "node":self.name,
                "status_code" : ErrorCode.Failed,
                "state": self.state,
                "command": command,
                "failed": [r['node'] for r in failed],
                "error": failed,
            }
            self.to_error(response=response, event=event)
        else:
            response = {
                "node":self.name,
                "status_code" : ErrorCode.Success,
                "state": self.state,
                "command": command,
            }
            end_command = getattr(self, "end_"+command)
            end_command(response=response)
