from anytree import NodeMixin, RenderTree, PreOrderIter
from anytree.resolver import Resolver
from transitions import Machine
import time
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
import logging
from .sshpm import SSHProcessManager
from .appctrl import AppSupervisor, ResponseListener, ResponseTimeout, NoResponse
from typing import Union, NoReturn
from .fsm import FSM
from .groupnode import GroupNode, ErrorCode
from rich.progress import *

log = logging.getLogger("transitions.core")
log.setLevel(logging.ERROR)
log = logging.getLogger("transitions")
log.setLevel(logging.ERROR)

class ApplicationNode(GroupNode):
    def __init__(self, name, sup, console, fsm_conf, parent=None):
        # Absolutely no children for ApplicationNode
        super().__init__(name=name, console=console, fsm_conf=fsm_conf, parent=parent, children=None)
        self.sup = sup

    def on_enter_boot_ing(self, _):
        # all this is delegated to the subsystem
        self.log.info(f"Application {self.name} booted")
        self.end_boot()

    def _on_enter_callback(self, event):
        pass

    def _on_exit_callback(self, event):
        pass

    def on_enter_terminate_ing(self, _):
        self.sup.terminate()
        self.command_sender.stop()
        self.end_terminate()

class SubsystemNode(GroupNode):
    def __init__(self, name:str, cfgmgr, console, fsm_conf, parent=None, children=None):
        super().__init__(name=name, console=console, fsm_conf=fsm_conf, parent=parent, children=children)
        self.cfgmgr = cfgmgr
        self.pm = None
        self.listener = None


    def on_enter_boot_ing(self, event) -> NoReturn:
        self.log.info(f'Subsystem {self.name} is booting')
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
                                    parent=self,
                                    fsm_conf=self.fsm_conf)

            if child.sup.desc.proc.is_alive() and child.sup.commander.ping():
                child.boot()
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
        timeout = event.kwargs["timeout"]
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

                n.trigger(command)
                ## APP now in *_ing
                n.sup.send_command(command, cmd_data=data)

            start = datetime.now()

            with Progress(SpinnerColumn(),
                          TextColumn("[progress.description]{task.description}"),
                          BarColumn(),
                          TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                          TimeRemainingColumn(),
                          TimeElapsedColumn(),
                          console=self.console,
                          ) as progress:
                apps_tasks = {
                    c.name: progress.add_task(f"[blue]{c.name}", total=1) for c in self.children
                }
                waiting = progress.add_task("[yellow]timeout", total=timeout)
                for _ in range(timeout*10):
                    progress.update(waiting, advance=0.1)
                    if len(appset)==0: break
                    done = []
                    for n in appset:
                        try:
                            r = n.sup.check_response()
                        except NoResponse:
                            continue

                        done += [n]
                        progress.update(apps_tasks[n.name], completed=1)
                        if r['success']:
                            n.trigger("end_"+command)
                        else:
                            response = {
                                "node":n.name,
                                "status_code" : r,
                                "state": n.state,
                                "command": command,
                                "error": r,
                            }
                            failed.append(response)
                            n.to_error(event=event)

                    for d in done:
                        appset.remove(d)

                    time.sleep(0.1)

        else:
            # There probably is a way to do that in a much nicer, pythonesque, way
            for n in sequence:
                # YUK
                child_node = [cn for cn in appset if cn.name == n][0]
                if cfg_method:
                    f=getattr(self.cfgmgr,cfg_method)
                    data = f(overwrite_data)
                else:
                    data = getattr(self.cfgmgr, command)

                kwargs = {'wait': False,
                          'cmd_data': data}
                event.kwargs.update(kwargs)
                child_node.sup.send_command_and_wait(comm, cmd_data=data)
                for _ in range(event.kwargs['timeout']):
                    try:
                        r = child_node.sup.check_response()
                    except NoResponse:
                        time.sleep(1)
                        continue
                    if r['success']:
                        child_end_command = getattr(child_node, "end_"+command)
                        child_end_command()
                        break
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
                        break

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
