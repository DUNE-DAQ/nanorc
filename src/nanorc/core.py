import logging
import time
import json
import os
from anytree import RenderTree, PreOrderIter
from rich.console import Console
from rich.style import Style
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text
from .node import DAQNode, SubsystemNode, ApplicationNode
from .sshpm import SSHProcessManager
from .topcfgmgr import TopLevelConfigManager
from .cfgsvr import ConfigSaver
from .appctrl import AppSupervisor, ResponseListener, ResponseTimeout, NoResponse
from .runmgr import RunNumberDBManager, SimpleRunNumberManager
from .credmgr import credentials

from rich.traceback import Traceback

from datetime import datetime

from typing import Union, NoReturn

def search_tree(path:str, from_node:DAQNode)->[DAQNode]:
    if path == "/" or path == "/root":
        return [from_node]
    
    results = []
    for node in PreOrderIter(from_node):
        this_path = ""
        for parent in node.path:
            this_path += "/"+parent.name
        if this_path == path:
            results.append(node)
            
    return results
        

class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, top_cfg: str, cfg_outdir: str, dotnanorc_file: str, timeout: int):
        super(NanoRC, self).__init__()     
        self.log = logging.getLogger(self.__class__.__name__)
        self.console = console
        self.cfg = TopLevelConfigManager(top_cfg)
        # self.cfg = ConfigManager(cfg_dir)

        if dotnanorc_file != "":
            dotnanorc_file = os.path.expanduser(dotnanorc_file)
            self.console.print(f"[blue]Loading {dotnanorc_file}[/blue]")
            f = open(dotnanorc_file)
            self.dotnanorc = json.load(f)
            credentials.add_login("rundb",
                                  self.dotnanorc["rundb"]["user"],
                                  self.dotnanorc["rundb"]["password"])
            self.log.info("RunDB socket "+self.dotnanorc["rundb"]["socket"])
            self.rnm = RunNumberDBManager(self.dotnanorc["rundb"]["socket"])
        else:
            self.rnm = SimpleRunNumberManager()

        self.cfgsvr = ConfigSaver(self.cfg, cfg_outdir)
        self.timeout = timeout
        self.return_code = 0

        # self.pm = SSHProcessManager(console)
        
        self.apps = self.cfg.get_tree_structure()
        self.listener = None


    def status(self) -> NoReturn:
        """
        Displays the status of the applications

        :returns:   Nothing
        :rtype:     None
        """

        if not self.apps:
            return

        table = Table(title="Apps")
        table.add_column("name", style="blue")
        table.add_column("host", style="magenta")
        table.add_column("alive", style="magenta")
        table.add_column("pings", style="magenta")
        table.add_column("last cmd")
        table.add_column("last succ. cmd", style="green")

        for pre, _, node in RenderTree(self.apps):
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
                
                
        self.console.print(table)


        
    def send_to_tree(self, path: str, cmd: str, overwrite_data: dict,
                     state_entry: str, state_exit: str, raise_on_fail: bool=False, cfg_method: str=None):
        """
        Sends many commands to all applications

        :param      path:           The path to which we want to send the command to
        :type       path:           str
        :param      cmd:            The command
        :type       cmd:            str
        :param      data:           The data
        :type       data:           dict
        :param      state_entry:    The state entry
        :type       state_entry:    str
        :param      state_exit:     The state exit
        :type       state_exit:     str
        :param      raise_on_fail:  Raise an exception if any application fails
        :type       raise_on_fail:  bool
        """
        
        nodes = search_tree(path, self.apps)
        
        ok, failed, excpt = {}, {}, {}
        
        if not nodes:
            self.log.warning(f"No applications defined to send '{cmd}' to.")
            self.return_code = 10
            return ok, failed
        
        for rootnode in nodes:
            for node in PreOrderIter(rootnode):
                if isinstance(node, SubsystemNode):
                    print(f"Sending {cmd} to {node.name}")
                    ok, failed = node.send_command(cmd, overwrite_data[node.name] if overwrite_data else {}, state_entry, state_exit)
                    # try:
                    #     ok, failed = node.send_command(cmd, data[node.name] if data else {}, state_entry, state_exit)
                    # except Exception as e:
                    #     excpt[node.name] = e
                        

        if raise_on_fail and len(failed)>0:
            self.log.error(f"ERROR: Failed to execute '{cmd}' on {', '.join(failed.keys())} applications")
            self.return_code = 13
            for a,r in failed.items():
                self.log.error(f"{a}: {r}\nEXCEPTION:\n{excpt['node.name']}")
                print(f"{a}: {r}\nEXCEPTION:\n{excpt['node.name']}")
            raise RuntimeError(f"ERROR: Failed to execute '{cmd}' on {', '.join(failed.keys())} applications")

        self.return_code = 0
        return ok, failed


    def boot(self) -> NoReturn:
        """
        Boots applications
        """
        for node in PreOrderIter(self.apps):
            if isinstance(node, SubsystemNode):
                self.log.debug(str(node.cfgmgr.boot))

                try:
                    node.pm = SSHProcessManager(self.console)
                    node.pm.boot(node.cfgmgr.boot)
                except Exception as e:
                    self.console.print_exception()
                    self.return_code = 11
                    return
                
                node.listener = ResponseListener(node.cfgmgr.boot["response_listener"]["port"])
                children = [ ApplicationNode(name=n,
                                             sup=AppSupervisor(self.console, d, node.listener),
                                             parent=node)
                             for n,d in node.pm.apps.items() ]
                node.children = children


    def terminate(self) -> NoReturn:
        for node in PreOrderIter(self.apps):
            if isinstance(node, ApplicationNode):
                node.sup.terminate()
                if node.parent.listener:
                    node.parent.listener.unregister(node.name)
                node.parent = None

        for node in PreOrderIter(self.apps):
            if isinstance(node, SubsystemNode):
                if node.listener:
                    node.listener.terminate()
                if node.pm:
                    node.pm.terminate()
                del node


    def ls(self) -> NoReturn:
        self.console.print("Legend:")
        self.console.print(" - [yellow]subsystems[/yellow]")
        self.console.print(" - [red]applications[/red]\n")

        for pre, _, node in RenderTree(self.apps):
            if isinstance(node, SubsystemNode):
                self.console.print(f"{pre}[yellow]{node.name}[/yellow]")
            elif isinstance(node, ApplicationNode):
                self.console.print(f"{pre}[red]{node.name}[/red]")
            else:
                self.console.print(f"{pre}{node.name}")


    def init(self, path:str) -> NoReturn:
        """
        Initializes the applications.
        """
        ok, failed = self.send_to_tree(path, 'init', None,
                                       'NONE', 'INITIAL', raise_on_fail=True)


    def conf(self, path:str) -> NoReturn:
        """
        Sends configure command to the applications.
        """
        ok, failed = self.send_to_tree(path, 'conf', None,
                                       'INITIAL', 'CONFIGURED', raise_on_fail=True)


    def start(self, disable_data_storage: bool) -> NoReturn:
        """
        Sends start command to the applications
        
        Args:
            disable_data_storage (bool): Description
        """

        self.run = self.rnm.get_run_number()

        runtime_start_data = {
                "disable_data_storage": disable_data_storage,
                "run": self.run,
            }

        cfg_save_dir = self.cfgsvr.save_on_start(self.apps, run=self.run,
                                                 overwrite_data=runtime_start_data,
                                                 cfg_method="runtime_start")

        ok, failed = self.send_to_tree("/", 'start', runtime_start_data,
                                       'CONFIGURED', 'RUNNING', raise_on_fail=True,
                                       cfg_method="runtime_start")
        self.console.log(f"[bold magenta]Started run #{self.run}, saving run data in {cfg_save_dir}[/bold magenta]")


    def stop(self) -> NoReturn:
        """
        Sends stop command
        """

        ok, failed = self.send_to_tree("/", 'stop', None,
                                       'RUNNING', 'CONFIGURED', raise_on_fail=True)
        self.console.log(f"[bold magenta]Stopped run #{self.run}[/bold magenta]")


    def pause(self, path:str) -> NoReturn:
        """
        Sends pause command
        """

        ok, failed = self.send_to_tree(path, 'pause', None,
                                       'RUNNING', 'RUNNING', raise_on_fail=True)


    def resume(self, path:str, trigger_interval_ticks: Union[int, None]) -> NoReturn:
        """
        Sends resume command
        
        :param      trigger_interval_ticks:  The trigger interval ticks
        :type       trigger_interval_ticks:  int
        """
        runtime_resume_data = {}

        if not trigger_interval_ticks is None:
            runtime_resume_data["trigger_interval_ticks"] = trigger_interval_ticks

        self.cfgsvr.save_on_resume(self.apps,
                                   overwrite_data=runtime_resume_data,
                                   cfg_method="runtime_resume")

        ok, failed = self.send_to_tree(path, 'resume', runtime_resume_data,
                                       'RUNNING', 'RUNNING', raise_on_fail=True,
                                       cfg_method="runtime_resume")


    def scrap(self, path:str) -> NoReturn:
        """
        Send scrap command
        """
        ok, failed = self.send_to_tree(path, 'scrap', None,
                                       'CONFIGURED', 'INITIAL', raise_on_fail=True)
