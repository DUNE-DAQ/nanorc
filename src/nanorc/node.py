from anytree import NodeMixin, RenderTree, PreOrderIter
from anytree.resolver import Resolver
import requests
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
from .statefulnode import StatefulNode, ErrorCode
from rich.progress import *

log = logging.getLogger("transitions.core")
log.setLevel(logging.ERROR)
log = logging.getLogger("transitions")
log.setLevel(logging.ERROR)

class ApplicationNode(StatefulNode):
    def __init__(self, name, sup, console, fsm_conf, parent=None):
        # Absolutely no children for ApplicationNode
        super().__init__(name=name, console=console, fsm_conf=fsm_conf, parent=parent, children=None)
        self.name = name
        self.sup = sup

    def on_enter_boot_ing(self, _):
        # all this is delegated to the subsystem
        self.log.info(f"Application {self.name} booted")

    def _on_enter_callback(self, event):
        pass

    def _on_exit_callback(self, event):
        pass

    def on_enter_terminate_ing(self, _):
        self.sup.terminate()
        self.end_terminate()

class SubsystemNode(StatefulNode):
    def __init__(self, name:str, ssh_conf, cfgmgr, fsm_conf, console, parent=None, children=None):
        super().__init__(name=name, console=console, fsm_conf=fsm_conf, parent=parent, children=children)
        self.name = name
        self.ssh_conf = ssh_conf

        self.cfgmgr = cfgmgr
        self.pm = None
        self.listener = None

    def send_custom_command(self, cmd, data) -> dict:
        ret = {}
        for c in self.children:
            ret[c.name] = c.sup.send_command_and_wait(cmd, cmd_data=data)
        return ret

    def send_expert_command(self, app, cmd) -> dict:
        cmd_name = cmd['name']
        cmd_payload = cmd['payload']
        cmd_entry_state = cmd['entry_state']
        cmd_exit_state = cmd_entry_state
        return app.sup.send_command_and_wait(cmd_name,
                                             cmd_data=cmd_payload,
                                             entry_state=cmd_entry_state,
                                             exit_state=cmd_exit_state)

    def get_custom_commands(self):
        return self.cfgmgr.get_custom_commands()

    def on_enter_boot_ing(self, event) -> NoReturn:
        self.log.info(f'Subsystem {self.name} is booting')
        try:
            if self.pm is None:
                self.pm = SSHProcessManager(self.console, self.ssh_conf)
            self.pm.boot(self.cfgmgr.boot, event.kwargs.get('log'))
        except Exception as e:
            self.console.print_exception()

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
                # nothing really happens in these 2:
                child.boot()
                child.end_boot()
                # ... but now the application is booted
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
        self.end_terminate()


    def _on_enter_callback(self, event):
        command = event.event.name
        origin = event.transition.source
        cfg_method = event.kwargs.get("cfg_method")
        timeout = event.kwargs["timeout"]
        force = event.kwargs.get('force')
        appfwk_state_dictionnary = { # !@#%&:(+_&||&!!!! (swears in raaawwww bits)
            "BOOTED": "NONE",
            "INITIALISED": "INITIAL",
        }

        exit_state = self.get_destination(command).upper()
        if exit_state  in appfwk_state_dictionnary: exit_state  = appfwk_state_dictionnary[exit_state]


        sequence = getattr(self.cfgmgr, command+'_order', None)
        log = f"Sending {command} to the subsystem {self.name}"
        if sequence: log+=f", in the order: {sequence}"
        self.log.info(log)
        appset = list(self.children)
        failed = []

        if not self.listener.flask_manager.is_alive():
            self.log.error('Response listener is not alive, trying to respawn it!!')
            self.listener.flask_manager = self.listener.create_manager()

        for n in appset:
            if not n.sup.desc.proc.is_alive() or not n.sup.commander.ping():
                text = f"'{n.name}' seems to be dead. So I cannot initiate transition '{command}'"
                if force:
                    self.log.error(text+f"\nBut! '--force' was specified, so I'll ignore '{n.name}'!")
                    appset.remove(n)
                    if sequence and n.name in sequence: sequence.remove(n.name)
                else:
                    self.log.error(text+"\nYou may be able to use '--force' if you want to 'stop' or 'scrap' the run.")
                    response = {
                        'node': self.name,
                        'status_code': ErrorCode.Aborted,
                        'comment': text+"\nYou may be able to use '--force' if you want to 'stop' or 'scrap' the run."
                    }
                    self.trigger("to_"+origin, response=response)
                    return

        if not sequence:
            # Loop over data keys if no sequence is specified or all apps, if data is empty

            for child_node in appset:
                # BERK I don't know how to sort this.
                # This is essntially calling cfgmgr.runtime_start(runtime_start_data)
                if cfg_method:
                    f=getattr(self.cfgmgr,cfg_method)
                    data = f(event.kwargs['overwrite_data'])
                else:
                    data = getattr(self.cfgmgr, command)
                entry_state = child_node.state.upper()
                if entry_state in appfwk_state_dictionnary: entry_state = appfwk_state_dictionnary[entry_state]

                child_node.trigger(command)
                ## APP now in *_ing

                child_node.sup.send_command(command, cmd_data=data[child_node.name] if data else {}, entry_state=entry_state, exit_state=exit_state)


            start = datetime.now()

            for _ in range(timeout*10):
                if len(appset)==0: break
                done = []
                for child_node in appset:
                    try:
                        r = child_node.sup.check_response()
                    except NoResponse:
                        continue

                    done += [child_node]
                    if r['success']:
                        child_node.trigger("end_"+command) # this is all dummy
                    else:
                        response = {
                            "node": child_node.name,
                            "status_code" : r,
                            "state": child_node.state,
                            "command": command,
                            "error": r,
                        }
                        failed.append(response)
                        child_node.to_error(event=event)

                for d in done:
                    appset.remove(d)

                time.sleep(0.1)

        else:
            for n in sequence:
                if n not in [cn.name for cn in appset]:
                    self.log.error(f'node \'{n}\' is not a child of the subprocess "{self.name}", check the order list for command "{command}"')
                    continue
                child_node = [cn for cn in appset if cn.name == n][0] # YUK
                entry_state = child_node.state.upper()
                if entry_state in appfwk_state_dictionnary: entry_state = appfwk_state_dictionnary[entry_state]


                if cfg_method:
                    f=getattr(self.cfgmgr,cfg_method)
                    data = f(event.kwargs['overwrite_data'])
                else:
                    data = getattr(self.cfgmgr, command)

                kwargs = {'wait': False,
                          'cmd_data': data}
                event.kwargs.update(kwargs)
                child_node.trigger(command)
                r = child_node.sup.send_command_and_wait(command, cmd_data=data[child_node.name] if data else {},
                                                         timeout=event.kwargs['timeout'],
                                                         entry_state=entry_state, exit_state=exit_state)
                if r['success']:
                    child_node.trigger("end_"+command)
                else:
                    response = {
                        "node":child_node.name,
                        "status_code" : r,
                        "state": child_node.state,
                        "command": command,
                        "error": r,
                    }
                    failed.append(response)
                    child_node.to_error(event=event, response=response)

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
            self.trigger("end_"+command, response=response)
