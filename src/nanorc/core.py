import logging
import time
import json
import os
from rich.console import Console
from rich.style import Style
from rich.pretty import Pretty
from .node import GroupNode
from .treebuilder import TreeBuilder
from .cfgsvr import FileConfigSaver, DBConfigSaver
from .credmgr import credentials
from .node_render import *
from rich.traceback import Traceback

from datetime import datetime

from typing import Union, NoReturn

class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, top_cfg: str, run_num_mgr: str, run_registry: str, timeout: int):
        super(NanoRC, self).__init__()     
        self.log = logging.getLogger(self.__class__.__name__)
        self.console = console

        self.cfg = TreeBuilder(top_cfg, self.console)
        self.apparatus_id = self.cfg.apparatus_id

        self.run_num_mgr = run_num_mgr
        self.cfgsvr = run_registry
        self.cfgsvr.cfgmgr = self.cfg
        self.cfgsvr.apparatus_id = self.apparatus_id
        self.timeout = timeout
        self.return_code = None

        self.topnode = self.cfg.get_tree_structure()
        self.console.print(f"Running on the apparatus [bold red]{self.cfg.apparatus_id}[/bold red]:")

        self.listener = None


    def status(self) -> NoReturn:
        """
        Displays the status of the applications

        :returns:   Nothing
        :rtype:     None
        """

        if not self.topnode:
            return

        print_status(apparatus_id=self.apparatus_id, topnode=self.topnode, console=self.console)


    def boot(self) -> NoReturn:
        """
        Boots applications
        """

        self.return_code = self.topnode.boot(timeout=self.timeout)


    def terminate(self) -> NoReturn:
        """
        Terminates applications (but keep all the subsystems structure)
        """
        self.return_code = self.topnode.terminate()


    def ls(self, leg:bool=True) -> NoReturn:
        """
        Print the nodes
        """

        self.return_code = print_node(node=self.topnode, console=self.console, leg=leg)


    def init(self, path) -> NoReturn:
        """
        Initializes the applications.
        """

        self.return_code = self.topnode.init(path=path, raise_on_fail=True, timeout=self.timeout)


    def conf(self, path) -> NoReturn:
        """
        Sends configure command to the applications.
        """

        self.return_code = self.topnode.conf(path, raise_on_fail=True, timeout=self.timeout)


    def start(self, disable_data_storage: bool, run_type:str) -> NoReturn:
        """
        Sends start command to the applications

        Args:
            disable_data_storage (bool): Description
            run_type (str): Description
        """
        # self.return_code = self.topnode.allowed("start", None)
        if not self.topnode.can_start():
            self.console.log(f"I cannot start now! {self.topnode.name} is {self.topnode.state}!")
            return 1
        self.run = self.run_num_mgr.get_run_number()

        runtime_start_data = {
            "disable_data_storage": disable_data_storage,
            "run": self.run,
        }

        cfg_save_dir = self.cfgsvr.save_on_start(self.topnode, run=self.run, run_type=run_type,
                                                 overwrite_data=runtime_start_data,
                                                 cfg_method="runtime_start")

        self.return_code = self.topnode.start(None,
                                              raise_on_fail=True,
                                              cfg_method="runtime_start",
                                              overwrite_data=runtime_start_data,
                                              timeout=self.timeout)

        self.console.log(f"[bold magenta]Started run #{self.run}, saving run data in {cfg_save_dir}[/bold magenta]")


    def stop(self) -> NoReturn:
        """
        Sends stop command
        """

        self.return_code = self.topnode.stop(None, raise_on_fail=True, timeout=self.timeout)
        if self.return_code != 0:
            self.cfgsvr.save_on_stop(self.run)
            self.console.log(f"[bold magenta]Stopped run #{self.run}[/bold magenta]")


    def pause(self) -> NoReturn:
        """
        Sends pause command
        """

        self.return_code = self.topnode.pause(None, raise_on_fail=True, timeout=self.timeout)


    def resume(self, trigger_interval_ticks: Union[int, None]) -> NoReturn:
        """
        Sends resume command
        
        :param      trigger_interval_ticks:  The trigger interval ticks
        :type       trigger_interval_ticks:  int
        """

        runtime_resume_data = {}

        if not trigger_interval_ticks is None:
            runtime_resume_data["trigger_interval_ticks"] = trigger_interval_ticks

        self.cfgsvr.save_on_resume(self.topnode,
                                   overwrite_data=runtime_resume_data,
                                   cfg_method="runtime_resume")

        self.return_code = self.topnode.resume(None,
                                               raise_on_fail=True,
                                               cfg_method="runtime_resume",
                                               overwrite_data=runtime_resume_data,
                                               timeout=self.timeout)


    def scrap(self, path) -> NoReturn:
        """
        Send scrap command
        """

        self.return_code = self.topnode.scrap(None, raise_on_fail=True, timeout=self.timeout)
