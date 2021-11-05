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
        trigger = ""
        etext = ""
        ssh_exit_code = ""
        if original_event: trigger = original_event.event.name

        if trigger != "unknown_command" and kwargs.get('command'):
            trigger = kwargs.get('command') 

        if excp: etext = f", an exception was thrown: {str(excp)},\ntrace: {trace}"

        if event.kwargs.get("ssh_exit_code"): ssh_exit_code = f", the following error code was sent from ssh: {event.kwargs['ssh_exit_code']}"

        self.log.error(f"while trying to \"{trigger}\" \"{self.name}\""+etext+ssh_exit_code)

    def send_to_process(self, *args, **kwargs):
        pass

    def _on_enter_callback(self, event):
        trigger = event.event.name
        print(trigger, self.name, self.state)

        still_to_exec = []
        for child in self.children:
            self.console.log(f"{self.name} is sending '{trigger}' to {child.name}")

            still_to_exec.append(child) # a record of which children still need to finish their task
            child.send_cmd(trigger) # send the commands

        failed_resp = []
        print(event.kwargs)
        for _ in range(event.kwargs["timeout"]):
            if not self.status_receiver_queue.empty():
                response = self.status_receiver_queue.get()

            for child in self.children:
                if response["node"] == child.name:
                    still_to_exec.remove(child)

                    if response["status_code"] != ErrorCode.Success:
                        failed_resp.append(response)
                    break

            if len(still_to_exec) == 0 or len(failed_resp)>0: # if all done, continue
                break
            time.sleep(1)

        timeout = []
        if len(still_to_exec) > 0:
            self.console.log(f"Sh*t the f*n... {self.name} can't {trigger} {[child.name for child in still_to_exec]}")
        timeout = still_to_exec

        for node in timeout:
            response = {
                "state": self.state,
                "command": event.event.name,
                "node": node.name,
                "failed": "",
                "error": "Timed out after waiting for too long, or because a sibling went on error",
            }
            node.to_error(response)

        for fail in failed_resp:
            self.console.log(f"Sh*t the f*n... {fail['node']} threw an error {fail['command']}")

        status = ErrorCode.Success
        if len(timeout)>0:
            status = ErrorCode.Timeout
        if len(failed_resp)>0:
            status = ErrorCode.Failed

        response = {
            "status_code" : status,
            "state": self.state,
            "command": event.event.name,
            "node": self.name,
            "failed": [n['node'] for n in failed_resp],
            "timeout": [n.name for n in timeout],
            "error": [n['error'] for n in failed_resp]
        }

        if response['status_code'] != ErrorCode.Success:
            self.to_error(response=response)
        else:
            # Initiate the transition on this node to say that we have finished
            finalisor = getattr(self, "end_"+event.event.name, None)
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

        self.log.debug(f"Sending {cmd} to {node.name}")

        if not node:
            ## Probably overkill
            raise RuntimeError(f"The node {'/'.join(path)} doesn't exist!")

        trigger = getattr(node, cmd, None)
        if not trigger:
            raise RuntimeError(f"{node.name} doesn't know how to execute {cmd}")

        try:
            trigger(raise_on_fail=raise_on_fail, timeout=timeout, *args, **kwargs)
        except MachineError as e:
            self.log.error(f"FSM Error: You are not allowed to send \"{cmd}\" to {node.name} as it is in \"{node.state}\" state. Error:\n{str(e)}")
            return 1
        except Exception as e:
            if raise_on_fail:
                self.return_code = ErrorCode.Failed
                raise RuntimeError(f"Execution of {cmd} failed on {node.name}") from e
            else:
                self.return_code = 10
                return self.return_code

        return 0

# Now on to useful stuff
class ApplicationNode(GroupNode):
    def __init__(self, name, sup, console, parent=None):
        # Absolutely no children for ApplicationNode
        super().__init__(name=name, console=console, parent=parent, children=None)
        self.sup = sup

class SubsystemNode(GroupNode):
    def __init__(self, name:str, cfgmgr, console, parent=None, children=None, fsm=None):
        super().__init__(name=name, console=console, parent=parent, children=children)
        self.cfgmgr = cfgmgr
        self.pm = None
        self.listener = None
        self.fsm = fsm

    def send_to_process(self, *args, **kwargs):
        pass


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
            self.to_error(response=response)
        else:
            self.end_boot(response=response)


    def on_enter_terminate_ing(self, _) -> NoReturn:
        if self.children:
            for child in self.children:
                child.sup.terminate()
                if child.parent.listener:
                    child.parent.listener.unregister(child.name)
                child.parent = None

        if self.listener:
            self.listener.terminate()
        if self.pm:
            self.pm.terminate()
        self.end_terminate()


    def send_to_process(self, cmd:str,
                        cfg_method:str=None, overwrite_data:dict={},
                        timeout:int=None) -> tuple:
        self.log.debug(f"Sending {cmd} to {self.name}")

        sequence = getattr(self.cfgmgr, cmd+'_order', None)

        appset = list(self.children)
        ok, failed = {}, {}

        if not sequence:
            # Loop over data keys if no sequence is specified or all apps, if data is empty

            for n in appset:
                # BERK I don't know how to sort this.
                # This is essntially calling cfgmgr.runtime_start(runtime_start_data)
                if cfg_method:
                    f=getattr(self.cfgmgr,cfg_method)
                    data = f(overwrite_data)
                else:
                    data = getattr(self.cfgmgr, cmd)

                n.sup.send_command(cmd, data[n.name] if data else {})#, self.state, state_exit)

            start = datetime.now()

            while(appset):
                done = []
                for n in appset:
                    try:
                        r = n.sup.check_response()
                    except NoResponse:
                        continue

                    done += [n]

                    (ok if r['success'] else failed)[n.name] = r

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
                            data = getattr(self.cfgmgr, cmd)
                        r = child_node.sup.send_command_and_wait(cmd, data[n] if data else {}) #,self.state, state_exit, timeout)
                        (ok if r['success'] else failed)[n] = r


        return (ok, failed)
