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

log = logging.getLogger("transitions.core")
log.setLevel(logging.ERROR)
log = logging.getLogger("transitions")
log.setLevel(logging.ERROR)


class GroupNode(NodeMixin):
    def __init__(self, name:str, console, parent=None, children=None):
        # loggers = [logging.getLogger(name) for name in logging.root.manager.loggerDict]
        # print(loggers)
        # exit(1)
        self.console = console
        self.name = name
        self.parent = parent
        self.log = logging.getLogger(self.__class__.__name__+"_"+self.name)
        if children:
            self.children = children

    def print_status(self, apparatus_id:str=None) -> int:
        if apparatus_id:
            table = Table(title=f"{apparatus_id} apps")
        else:
            table = Table(title=f"{apparatus_id} apps")
        table.add_column("name", style="blue")
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
                    pre+node.name+f" ({node.state})",
                    sup.desc.host,
                    str(alive),
                    str(ping),
                    Text(str(sup.last_sent_command), style=('bold red' if last_cmd_failed else '')),
                    str(sup.last_ok_command)
                )

            else:
                table.add_row(pre+node.name+f" ({node.state})",)

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
        print(kwargs)
        if excp:
            self.log.error(f"Upon trying to  on {self.name}, an excption was thrown: {str(excp)}")

    def send_to_process(self, *args, **kwargs):
        pass

    def _on_enter_callback(self, event):
        trigger = event.event.name
        
        raise_on_fail = event.kwargs['raise_on_fail']
        del event.kwargs['raise_on_fail']
        try:
            self.send_to_process(trigger, *event.args, **event.kwargs)
        except Exception as e:
            self.log.error(e)
            self.to_error(raise_on_fail, exception=e, event=event)
        
        finalisor = getattr(self, "end_"+trigger)
        finalisor()
        
    def _on_exit_callback(self, event):
        trigger = event.event.name
        # self.log.info(f"Finished to {trigger} on {self.name}")
        
    def send_cmd(self, cmd:str, path:[str]=None, raise_on_fail:bool=True, *args, **kwargs) -> int:
        
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

        # we need to save the children _before_ the trigger, because boot and terminate spawn application children on subsystems!
        children = self.children
        
        try:
            trigger(raise_on_fail=raise_on_fail, *args, **kwargs)
        except Exception as e:
            raise RuntimeError(f"Execution of {cmd} failed on {node.name}") from e

        for child in children:
            child.send_cmd(cmd=cmd, path=None, *args, **kwargs)

        return 0


    # def _propagate_command(self, cmd:str,
    #                       cfg_method:str=None, overwrite_data:dict={},
    #                       timeout:int=None) -> tuple:

    #     ok, failed = {}, {}

    #     for child in self.children:
    #         o, f = child._propagate_command(cmd=cmd,
    #                                         cfg_method = cfg_method, overwrite_data = overwrite_data,
    #                                         timeout = timeout)
    #         ok.update(o)
    #         failed.update(f)

    #     return (ok, failed)


# Now on to useful stuff
class ApplicationNode(GroupNode):
    def __init__(self, name, sup, console, parent=None):
        # Absolutely no children for ApplicationNode
        super().__init__(name=name, console=console, parent=parent, children=None)
        self.sup = sup

    # def _propagate_command(self, *args, **kwargs):
    #     raise RuntimeError("ERROR: You can't send a command directly to an application! Send it to the parent subsystem!")

    # def send_command(self, *args, **kwargs):
    #     raise RuntimeError("ERROR: You can't send a command directly to an application! Send it to the parent subsystem!")


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
                failed.append(n)
                child.to_error(event, name)
            children.append(child)
        self.children = children
        
        if not failed:
            self.end_boot()
        else:
            self.to_error(event, failed)


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

