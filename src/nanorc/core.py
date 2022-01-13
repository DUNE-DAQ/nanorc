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
from .logbook import ElisaLogbook, FileLogbook
import importlib
from rich.traceback import Traceback

from datetime import datetime

from typing import Union, NoReturn

class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, top_cfg: str, run_num_mgr, run_registry, logbook_type:str, timeout: int,
                 use_kerb=True, logbook_prefix=""):
        super(NanoRC, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.console = console

        ssh_conf = []
        if not use_kerb:
            ssh_conf = ["-o GSSAPIAuthentication=no"]

        self.cfg = TreeBuilder(top_cfg=top_cfg,
                               console=self.console,
                               ssh_conf=ssh_conf)
        self.apparatus_id = self.cfg.apparatus_id

        self.run_num_mgr = run_num_mgr
        self.cfgsvr = run_registry
        self.cfgsvr.cfgmgr = self.cfg
        self.cfgsvr.apparatus_id = self.apparatus_id
        self.timeout = timeout
        self.return_code = None
        self.logbook = None
        self.log_path = None
        if logbook_type == "elisa":
            try:
                from . import confdata
                elisa_conf = json.loads(importlib.resources.read_text(confdata, "elisa_conf.json"))
                if elisa_conf.get(self.apparatus_id):
                    self.logbook = ElisaLogbook(configuration = elisa_conf[self.apparatus_id],
                                                console = console)
                else:
                    self.log.error(f"Can't find config {self.apparatus_id} confdata/elisa_conf.json, reverting to file logbook!")
            except Exception as e:
                self.log.error(f"Can't find confdata/elisa_conf.json, reverting to file logbook! {str(e)}")

        if not self.logbook:
            self.log.info("Using filelogbook")
            self.logbook = FileLogbook(logbook_prefix, self.console)

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
        self.topnode.boot(timeout=self.timeout)
        self.return_code = self.topnode.return_code.value


    def terminate(self) -> NoReturn:
        """
        Terminates applications (but keep all the subsystems structure)
        """
        self.topnode.terminate()
        self.return_code = self.topnode.return_code.value


    def ls(self, leg:bool=True) -> NoReturn:
        """
        Print the nodes
        """
        self.return_code = print_node(node=self.topnode, console=self.console, leg=leg)


    def init(self, path) -> NoReturn:
        """
        Initializes the applications.
        """
        self.topnode.init(path=path, raise_on_fail=True, timeout=self.timeout)
        self.return_code = self.topnode.return_code.value


    def conf(self, path) -> NoReturn:
        """
        Sends configure command to the applications.
        """
        self.topnode.conf(path=path, raise_on_fail=True, timeout=self.timeout)
        self.return_code = self.topnode.return_code.value


    def start(self, disable_data_storage: bool, run_type:str, message:str="") -> NoReturn:
        """
        Sends start command to the applications

        Args:
            disable_data_storage (bool): Description
            run_type (str): Description
        """
        # self.return_code = self.topnode.allowed("start", None)
        if not self.topnode.can_start():
            self.console.log(f"I cannot start now! {self.topnode.name} is {self.topnode.state}!")
            self.return_code = 1
            return
        self.run = self.run_num_mgr.get_run_number()

        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")

        try:
            self.logbook.message_on_start(message, self.run, run_type)
        except Exception as e:
            self.log.error(f"Couldn't make an entry to elisa, do it yourself manually at {self.logbook.website}\nError text:\n{str(e)}")


        runtime_start_data = {
            "disable_data_storage": disable_data_storage,
            "run": self.run,
        }

        try:
            cfg_save_dir = self.cfgsvr.save_on_start(self.topnode, run=self.run, run_type=run_type,
                                                     overwrite_data=runtime_start_data,
                                                     cfg_method="runtime_start")
        except Exception as e:
            self.log.error(f'Couldn\'t save the configuration so not starting a run!\n{str(e)}')
            self.return_code = 1
            return

        self.topnode.start(path=None, raise_on_fail=True,
                           cfg_method="runtime_start",
                           overwrite_data=runtime_start_data,
                           timeout=self.timeout)
        self.return_code = self.topnode.return_code.value
        if self.return_code == 0:
            self.log.info(f"[bold magenta]Started run #{self.run}, saving run data in {cfg_save_dir}[/bold magenta]")
        else:
            self.log.error(f"[bold red]There was an error when starting the run #{self.run}[/bold red]:")
            self.log.error(f'Response: {self.topnode.response}')

    def message(self, message:str="") -> NoReturn:
        """
        Append the logbook
        """

        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")
            try:
                self.logbook.add_message(message)
            except Exception as e:
                self.log.error(f"Couldn't make an entry to elisa, do it yourself manually at {self.logbook.website}\nError text:\n{str(e)}")


    def stop(self, force:bool=False, message:str="") -> NoReturn:
        """
        Sends stop command
        """

        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")
            try:
                self.logbook.message_on_stop(message)
            except Exception as e:
                self.log.error(f"Couldn't make an entry to elisa, do it yourself manually at {self.logbook.website}\nError text:\n{str(e)}")


        self.cfgsvr.save_on_stop(self.run)
        self.topnode.stop(path=None, raise_on_fail=True, timeout=self.timeout, force=force)
        self.return_code = self.topnode.return_code.value
        self.console.log(f"[bold magenta]Stopped run #{self.run}[/bold magenta]")


    def pause(self, force:bool=False) -> NoReturn:
        """
        Sends pause command
        """
        self.topnode.pause(path=None, raise_on_fail=True, timeout=self.timeout, force=force)
        self.return_code = self.topnode.return_code.value


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

        self.topnode.resume(path=None, raise_on_fail=True,
                            cfg_method="runtime_resume",
                            overwrite_data=runtime_resume_data,
                            timeout=self.timeout)
        self.return_code = self.topnode.return_code.value


    def scrap(self, path, force:bool=False) -> NoReturn:
        """
        Send scrap command
        """
        self.topnode.scrap(path=None, raise_on_fail=True, timeout=self.timeout, force=force)
        self.return_code = self.topnode.return_code.value
