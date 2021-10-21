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
from .node import GroupNode, SubsystemNode, ApplicationNode
from .sshpm import SSHProcessManager
from .topcfgmgr import TopLevelConfigManager
from .cfgsvr import ConfigSaver
from .appctrl import AppSupervisor, ResponseListener, ResponseTimeout, NoResponse
from .runmgr import RunNumberDBManager, SimpleRunNumberManager
from .credmgr import credentials

from rich.traceback import Traceback

from datetime import datetime

from typing import Union, NoReturn

def search_tree(path:str, from_node:GroupNode)->[GroupNode]:
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
        self.cfg = TopLevelConfigManager(top_cfg, self.console)
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

        self.apps = self.cfg.get_tree_structure()
        self.console.print(f"Running on the apparatus [bold red]{self.cfg.apparatus_id}[/bold red]:")
        self.ls(leg=False)

        self.listener = None


    def status(self) -> NoReturn:
        """
        Displays the status of the applications

        :returns:   Nothing
        :rtype:     None
        """

        if not self.apps:
            return

        table = Table(title=f"{self.cfg.apparatus_id} apps")
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
        
        if len(nodes)>1:
            self.log.error(f"Something weird is going one, {path} correspond to several nodes")
            self.return_code = 10
            return ok, failed

        for rootnode in nodes:
            ok, failed = rootnode.send_command(cmd=cmd,
                                               state_entry=state_entry, state_exit=state_exit,
                                               cfg_method=cfg_method,
                                               overwrite_data=overwrite_data if overwrite_data else {},
                                               timeout=self.timeout)

        if raise_on_fail and len(failed)>0:
            self.log.error(f"ERROR: Failed to execute '{cmd}' on {', '.join(failed.keys())} applications")
            self.return_code = 13
            for a,r in failed.items():
                self.log.error(f"{a}: {r}")
            raise RuntimeError(f"ERROR: Failed to execute '{cmd}' on {', '.join(failed.keys())} applications")

        self.return_code = 0
        return ok, failed


    def boot(self) -> NoReturn:
        """
        Boots applications
        """
        self.apps.boot()


    def terminate(self) -> NoReturn:
        """
        Terminates applications (but keep all the subsystems structure)
        """
        self.apps.terminate()


    def ls(self, leg:boot=True) -> NoReturn:

        for pre, _, node in RenderTree(self.apps):
            if node == self.apps:
                self.console.print(f"{pre}[red]{node.name}[/red]")
            elif isinstance(node, SubsystemNode):
                self.console.print(f"{pre}[yellow]{node.name}[/yellow]")
            elif isinstance(node, ApplicationNode):
                self.console.print(f"{pre}[blue]{node.name}[/blue]")
            else:
                self.console.print(f"{pre}{node.name}")

        if leg:
            self.console.print("\nLegend:")
            self.console.print(" - [red]root node[/red]")
            self.console.print(" - [yellow]subsystems[/yellow]")
            self.console.print(" - [blue]applications[/blue]\n")


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
