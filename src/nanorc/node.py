from anytree import NodeMixin, RenderTree, PreOrderIter
from anytree.resolver import Resolver
import requests
import time
import json
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich.panel import Panel
import copy as cp
import logging
from .pmdesc import PMFactory
from .appctrl import AppSupervisor, ResponseListener, ResponseTimeout, NoResponse
from typing import Union, NoReturn
from .fsm import FSM
import os.path
from .statefulnode import StatefulNode, ErrorCode, CanExecuteReturnVal

log = logging.getLogger("transitions")
log.setLevel(logging.ERROR)

class ApplicationNode(StatefulNode):
    def __init__(self, name, sup, console, log, fsm_conf, parent=None):
        # Absolutely no children for ApplicationNode
        super().__init__(name=name, log=log, console=console, fsm_conf=fsm_conf, parent=parent, children=None)
        self.name = name
        self.sup = sup

    def on_enter_boot_ing(self, _):
        # all this is delegated to the subsystem
        self.log.info(f"Application {self.name} booted")

    def _on_enter_callback(self, event):
        pass

    def _on_exit_callback(self, event):
        pass

    def resolve_error(self):
        # Since app node doesn't have children, statefulnode's resolve_error always gives error free...
        pass

    def on_enter_terminate_ing(self, _):
        self.sup.terminate()
        self.end_terminate()
        self.included = False

    def on_enter_abort_ing(self, _):
        self.sup.terminate()
        self.end_abort()

class SubsystemNode(StatefulNode):
    def __init__(self, name:str, log, cfgmgr, fsm_conf, console, parent=None, children=None):
        super().__init__(name=name, log=log, console=console, fsm_conf=fsm_conf, parent=parent, children=children)
        self.name = name

        self.cfgmgr = cfgmgr
        self.pm = None
        self.listener = None

    def can_execute_custom_or_expert(self, command, quiet=False, check_dead=True, check_inerror=True, only_included=True):
        ret = super().can_execute_custom_or_expert(
            command = command,
            quiet = quiet,
            check_dead = check_dead,
            check_inerror = check_inerror,
            only_included = only_included,
        )
        if ret != CanExecuteReturnVal.CanExecute:
            return ret

        for c in self.children:
            if not c.included and only_included: continue

            if check_dead and not (c.sup.desc.proc.is_alive() and c.sup.commander.ping()):
                self.return_code = ErrorCode.Failed
                self.log.error(f'{c.name} is dead, cannot send {command}')
                return CanExecuteReturnVal.Dead

        self.return_code = ErrorCode.Success
        return CanExecuteReturnVal.CanExecute

    def can_execute(self, command, quiet=False, check_dead=True, check_inerror=True, only_included=True):
        ret = super().can_execute(
            command = command,
            quiet = quiet,
            check_dead = check_dead,
            check_inerror = check_inerror,
            only_included = only_included,
        )

        if ret != CanExecuteReturnVal.CanExecute:
            return ret

        for c in self.children:
            if not c.included and only_included: continue

            if not (c.sup.desc.proc.is_alive() and c.sup.commander.ping()):
                self.return_code = ErrorCode.Failed
                self.log.error(f'{c.name} is dead, cannot send {command} unless you disable it or --force')
                return CanExecuteReturnVal.Dead

        self.return_code = ErrorCode.Success
        return CanExecuteReturnVal.CanExecute

    def send_custom_command(self, cmd, data, timeout, app=None) -> dict:
        ret = {}
        if not self.listener.flask_manager.is_alive():
            self.log.error('Response listener is not alive, trying to respawn it!!')
            self.listener.flask_manager = self.listener.create_manager()

        if cmd == 'scripts': # unfortunately I don't see how else to do this
            scripts = self.cfgmgr.boot.get('scripts')
            script = cp.deepcopy(scripts.get(data['script_name'])) if scripts else None

            if not script:
                self.log.error(f"no {data['script_name']} script data in boot.json")
                return {self.name : f"no {data['script_name']} script data in boot.json"}

            try:
                del data['script_name']
                for key, val in data.items():
                    script[key].update(val)
                self.pm.execute_script(script)

            except Exception as e:
                self.log.error(f'Couldn\'t execute the thread pinning scripts: {str(e)}')
            return ret

        is_include_exclude = cmd=='include' or cmd=='exclude'

        cmd_dict = getattr(self.cfgmgr, cmd, None)

        if cmd_dict:
            for app_name, cmd_data in cmd_dict.items():
                for c in self.children:
                    # selects the app matching the data (if app is specified)
                    if app_name and c.name!=app_name: continue

                    if app:
                        # selects the app matching the argument
                        if c.name!=app: continue
                    else:
                        if not is_include_exclude and not c.included: continue

                    if not (c.sup.desc.proc.is_alive() and c.sup.commander.ping()):
                        self.log.error(f'{c.name} is dead, cannot send {cmd} to the app')
                        continue

                    cmd_data2 = cp.deepcopy(cmd_data)
                    for m in cmd_data2['modules']:
                        if m.get("data"):
                            m['data'].update(data)

                    ret[c.name] = c.sup.send_command_and_wait(cmd, cmd_data=cmd_data2, timeout=timeout)
        else:
            for c in self.children:
                if app:
                    if c.name!=app: continue
                else:
                    if not is_include_exclude and not c.included: continue

                if not (c.sup.desc.proc.is_alive() and c.sup.commander.ping()):
                    self.log.error(f'{c.name} is dead, cannot send {cmd} to the app')
                    continue
                cmd_data = {
                    "modules": [{
                        "data": data,
                        "match": ""
                    }]
                }
                ret[c.name] = c.sup.send_command_and_wait(cmd, cmd_data=cmd_data, timeout=timeout)
        return ret

    def send_expert_command(self, app, cmd, timeout) -> dict:
        if not self.listener.flask_manager.is_alive():
            self.log.error('Response listener is not alive, trying to respawn it!!')
            self.listener.flask_manager = self.listener.create_manager()

        cmd_name = cmd['id']
        cmd_payload = cmd['data']
        cmd_entry_state = cmd['entry_state']
        cmd_exit_state = cmd_entry_state
        node_state = app.state.upper()

        if cmd_entry_state != node_state:
            self.log.error(f'The node is in \'{node_state}\' so I cannot send \'{cmd_name}\', which requires the app to be \'{cmd_entry_state}\'.')
            return {'Failed': 'App in wrong state, cmd not sent'}
        return app.sup.send_command_and_wait(cmd_name,
                                             cmd_data=cmd_payload,
                                             entry_state=cmd_entry_state,
                                             exit_state=cmd_exit_state,
                                             timeout=timeout)

    def get_custom_commands(self):
        return self.cfgmgr.get_custom_commands()

    def on_enter_boot_ing(self, event) -> NoReturn:
        partition = event.kwargs["partition"]
        self.log.info(f'Subsystem {self.name} is booting partition {partition}')
        response = {
            "node": self.name,
            "command": "boot",
        }
        try:
            if self.pm is None:
                fact = PMFactory(self.cfgmgr, self.console)
                self.pm = fact.get_pm(event)

            timeout = event.kwargs["timeout"]
            boot_info = cp.deepcopy(self.cfgmgr.boot)
            boot_info['env']['DUNEDAQ_PARTITION'] = partition

            self.pm.boot(
                boot_info = boot_info,
                timeout = timeout,
                conf_loc = self.cfgmgr.get_conf_location(for_apps=True)
            )

        except Exception as e:
            self.log.exception(e)
            self.to_error(
                text=f'Couldn\'t boot {self.name}',
                command='boot',
                exception=e,
            )
            return

        try:
            self.listener = ResponseListener(self.cfgmgr.boot["response_listener"]["port"])
        except Exception as e:
            self.log.exception(str(e))
            self.to_error(
                text=f'Couldn\'t create a response listener for {self.name}',
                command='boot',
                exception=e,
            )
            return

        children = []
        failed = []
        for n,d in self.pm.apps.items():

            response_host = None
            proxy = None
            if event.kwargs['pm'].use_k8spm():
                response_host = self.pm.nanorc_responder
                proxy = (event.kwargs['pm'].address, event.kwargs['pm'].port)

            child = ApplicationNode(
                name=n,
                console=self.console,
                log=self.log,
                sup=AppSupervisor(self.console, d, self.listener, response_host, proxy),
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
                etext=''
                if not child.sup.desc.proc.is_alive():
                    etext='Process isn\'t alive! '
                if not child.sup.commander.ping():
                    etext='Cannot ping the app!'
                child.to_error(
                    text=etext,
                    command='boot'
                )

            children.append(child)

        self.children = children

        status_code = ErrorCode.Success
        if failed:
           status_code = ErrorCode.Failed

        response["status_code"] = status_code
        response["failed"] = [f['node'] for f in failed]
        response["error"] =  failed

        if response['status_code'] != ErrorCode.Success:
            etext = f"children node {[f['node'] for f in failed]} failed to boot"
            self.to_error(
                text=etext,
                command='boot'
            )
        self.end_boot(response=response)


    def on_exit_conf_ing(self, event) -> NoReturn:
        scripts = self.cfgmgr.boot.get('scripts')
        thread_pinning = scripts.get('thread_pinning') if scripts else None
        if thread_pinning:
            try:
                self.pm.execute_script(thread_pinning)
            except Exception as e:
                self.log.error(f'Couldn\'t execute the thread pinning scripts: {str(e)}')
        super()._on_exit_callback(event)


    def terminate_logic(self) -> NoReturn:
        self.log.debug(f"Terminate logic of {self.name}")
        if self.listener:
            self.listener.terminate()
        if self.pm:
            self.pm.terminate()
            self.pm = None
        self.log.debug(f"DONE Terminate logic of {self.name}")

    def on_enter_terminate_ing(self, _) -> NoReturn:
        self.log.debug(f"Terminating {self.name}")
        if self.children:
            for child in self.children:
                if child.can_execute('terminate', quiet=True) == CanExecuteReturnVal.CanExecute:
                    child.terminate()
                else:
                    self.log.info(f'Force terminating on {child.name}')
                    child.to_terminate_ing()
                if child.parent.listener:
                    child.parent.listener.unregister(child.name)
                child.parent = None
        self.terminate_logic()
        self.end_terminate()
        self.errored = False
        self.included = True

    def on_enter_abort_ing(self, _) -> NoReturn:
        self.log.debug(f"Aborting {self.name}")
        if self.children:
            for child in self.children:
                child.abort()
                if child.parent.listener: # isn't child.parent==self?? confusing...
                    child.parent.listener.unregister(child.name)
                child.parent = None # abandon your child
        self.terminate_logic()
        self.end_abort()
        self.included = True
        self.errored = False
        self.log.debug(f"DONE Aborting {self.name}")

    def _on_enter_callback(self, event):
        command = event.event.name
        origin = event.transition.source
        cfg_method = event.kwargs.get("cfg_method")
        timeout = event.kwargs["timeout"]
        force = event.kwargs.get('force')

        exit_state = self.get_destination(command).upper()

        log = f"Sending {command} to the subsystem {self.name}"
        self.log.info(log)

        appset = list(self.children)
        failed = []

        if not self.listener.flask_manager.is_alive():
            self.log.error('Response listener is not alive, trying to respawn it!!')
            self.listener.flask_manager = self.listener.create_manager()

        to_chuck = []
        for i, n in enumerate(appset):
            if not n.included:
                self.log.info(f'Node {n.name} is excluded! NOT sending {command} to it!')
                to_chuck.append(n.name)
                continue

            if not n.sup.desc.proc.is_alive() or not n.sup.commander.ping():
                text = f"'{n.name}' seems to be dead. So I cannot initiate transition '{command}'"
                if force:
                    self.log.error(text+f"\nBut! '--force' was specified, so I'll ignore '{n.name}'!")
                    to_chuck.append(n.name)
                    # if sequence and n.name in sequence: sequence.remove(n.name)
                else:
                    self.log.error(text+"\nYou may be able to use '--force' if you want to 'stop' or 'scrap' the run.")
                    response = {
                        'node': self.name,
                        'status_code': ErrorCode.Aborted,
                        'comment': text+"\nYou may be able to use '--force' if you want to 'stop' or 'scrap' the run."
                    }
                    self.trigger("to_"+origin, response=response)
                    return

        for chuck in to_chuck:
            for i, app in enumerate(appset):
                if chuck == app.name:
                    del appset[i]

        for child_node in appset:
            data = self.cfgmgr.generate_data_for_module(event.kwargs.get('overwrite_data'))
            if not child_node.included:
                self.log.info(f'Node {child_node.name} is excluded! NOT sending {command} to it!')
                continue
            self.log.debug(f'Sending {command} to {child_node.name}')


            entry_state = child_node.state.upper()

            child_node.trigger(command)
            ## APP now in *_ing

            child_node.sup.send_command(
                cmd_id = command,
                cmd_data = data,
                entry_state=entry_state,
                exit_state=exit_state
            )

        start = datetime.now()

        for _ in range(timeout*10):
            if len(appset)==0: break
            done = []
            for child_node in appset:
                if not child_node.included: continue

                if not child_node.sup.desc.proc.is_alive() or not child_node.sup.commander.ping():
                    failed.append(child_node.name)
                    child_node.to_error(
                        command = command,
                    )
                    done += [child_node]
                    break

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
                    failed.append(child_node.name)
                    child_node.to_error(
                        command=command,
                        text=r['result']
                    )

            for d in done:
                appset.remove(d)

            time.sleep(0.1)

        response= {}
        if failed:
            response = {
                "node":self.name,
                "status_code" : ErrorCode.Failed,
                "state": self.state,
                "command": command,
                "failed": [r for r in failed],
                "error": failed,
            }
            self.to_error(
                text=f"Children nodes{[r for r in failed]} failed to {command}",
                command=command
            )
        else:
            response = {
                "node":self.name,
                "status_code" : ErrorCode.Success,
                "state": self.state,
                "command": command,
            }

        self.resolve_error()
        self.trigger("end_"+command, response=response)
