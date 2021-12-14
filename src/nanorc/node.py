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

class GroupNode(NodeMixin):
    def __init__(self, name:str, parent=None, children=None):
        self.name = name
        self.parent = parent
        self.log = logging.getLogger(self.__class__.__name__+"_"+self.name)
        if children:
            self.children = children


    def print_status(self, apparatus_id:str=None, console:Console=None) -> int:
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
                    pre+node.name,
                    sup.desc.host,
                    str(alive),
                    str(ping),
                    Text(str(sup.last_sent_command), style=('bold red' if last_cmd_failed else '')),
                    str(sup.last_ok_command)
                )

            else:
                table.add_row(pre+node.name)

        console.print(table)

    def print(self, leg:bool=False, console:Console=None) -> int:
        if console:
            print_func = console.print
        else:
            print_func = print

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

    def send_command(self, path:[str], cmd:str, state_entry:str, state_exit:str, cfg_method:str=None, overwrite_data:dict={}, raise_on_fail:bool=True, timeout:int=None, force:bool=False) -> int:

        if path:
            r = Resolver('name')
            prompted_path = "/".join(path)
            self.log.info(f"node.send_command prompted path {prompted_path}")
            node = r.get(self, prompted_path)
        else:
            node = self

        self.log.debug(f"Sending {cmd} to {node.name}")

        if not node: return

        ok, failed = node._propagate_command(cmd=cmd, state_entry=state_entry, state_exit=state_exit, cfg_method=cfg_method, overwrite_data=overwrite_data, timeout=timeout, force=force)

        if raise_on_fail and len(failed)>0:
            self.log.error(f"ERROR: Failed to execute '{cmd}' on {', '.join(failed.keys())} applications")
            self.return_code = 13
            for a,r in failed.items():
                self.log.error(f"{a}: {r}")
            raise RuntimeError(f"ERROR: Failed to execute '{cmd}' on {', '.join(failed.keys())} applications")

        return 0


    def _propagate_command(self, cmd:str, state_entry:str, state_exit:str, cfg_method:str=None, overwrite_data:dict={}, timeout:int=None, force:bool=False) -> tuple:

        ok, failed = {}, {}

        for child in self.children:
            o, f = child._propagate_command(cmd=cmd,
                                            state_entry = state_entry, state_exit = state_exit,
                                            cfg_method = cfg_method, overwrite_data = overwrite_data,
                                            timeout = timeout, force=force)
            ok.update(o)
            failed.update(f)

        return (ok, failed)

    def terminate(self) -> int:
        self.log.debug(f"Sending terminate to {self.name}")
        if not self.children:
            return

        for child in self.children:
            child.terminate()
        return 0

    def boot(self) -> int:
        self.log.debug(f"Sending boot to {self.name}")

        if not self.children:
            return

        for child in self.children:
            child.boot()
        return 0


# Now on to useful stuff
class ApplicationNode(NodeMixin):
    def __init__(self, name, sup, parent=None):
        self.name = name
        self.sup = sup
        self.parent = parent
        # Absolutely no children for applicationnode

    def _propagate_command(self, *args, **kwargs):
        raise RuntimeError("ERROR: You can't send a command directly to an application! Send it to the parent subsystem!")

    def send_command(self, *args, **kwargs):
        raise RuntimeError("ERROR: You can't send a command directly to an application! Send it to the parent subsystem!")


class SubsystemNode(NodeMixin):
    def __init__(self, name:str, cfgmgr, console, parent=None, children=None):
        self.name = name
        self.cfgmgr = cfgmgr
        self.pm = None
        self.listener = None
        self.parent = parent
        self.console = console
        self.log = logging.getLogger(self.__class__.__name__+"_"+self.name)
        if children:
            self.children = children

    def boot(self) -> NoReturn:
        self.log.debug(f"Sending boot to {self.name}")
        try:
            self.pm = SSHProcessManager(self.console)
            self.pm.boot(self.cfgmgr.boot)
        except Exception as e:
            self.console.print_exception()
            self.return_code = 11
            return

        self.listener = ResponseListener(self.cfgmgr.boot["response_listener"]["port"])
        children = [ ApplicationNode(name=n,
                                     sup=AppSupervisor(self.console, d, self.listener),
                                     parent=self)
                     for n,d in self.pm.apps.items() ]
        self.children = children

    def terminate(self) -> NoReturn:
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


    def _propagate_command(self, cmd:str, state_entry:str, state_exit:str, cfg_method:str=None, overwrite_data:dict={}, timeout:int=None, force:bool=False) -> tuple:
        self.log.debug(f"Sending {cmd} to {self.name}")

        sequence = getattr(self.cfgmgr, cmd+'_order', None)

        appset = list(self.children)
        ok, failed = {}, {}

        for n in appset:
            if not n.sup.desc.proc.is_alive() or not n.sup.commander.ping():
                text = f"'{n.name}' seems to be dead. So I cannot initiate transition '{state_entry}' -> '{state_exit}'."
                if force:
                    self.log.error(text+f"\nBut! '--force' was specified, so I'll ignore '{n.name}'!")
                    appset.remove(n)
                else:
                    raise RuntimeError(text+"\nYou may be able to use '--force' if you want to 'stop' or 'scrap' the run.")

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

                n.sup.send_command(cmd, data[n.name] if data else {}, state_entry, state_exit)


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

                        r = child_node.sup.send_command_and_wait(cmd, data[n] if data else {},
                                                                 state_entry, state_exit, timeout)
                        (ok if r['success'] else failed)[n] = r


        return (ok, failed)
