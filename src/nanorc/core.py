import logging
import time
import json
import os
from rich.console import Console
from rich.style import Style
from rich.pretty import Pretty
from .statefulnode import StatefulNode
from .treebuilder import TreeBuilder
from .cfgsvr import FileConfigSaver, DBConfigSaver
from .credmgr import credentials
from .node_render import *
from .logbook import ElisaLogbook, FileLogbook
import importlib
from . import confdata
from rich.traceback import Traceback

from datetime import datetime

from typing import Union, NoReturn

class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, top_cfg: str, run_num_mgr, run_registry, logbook_type:str, timeout: int,
                 use_kerb=True, logbook_prefix="", fsm_cfg="partition"):
        super(NanoRC, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.console = console
        ssh_conf = []
        if not use_kerb:
            ssh_conf = ["-o GSSAPIAuthentication=no"]

        self.cfg = TreeBuilder(log=self.log,
                               top_cfg=top_cfg,
                               console=self.console,
                               ssh_conf=ssh_conf,
                               fsm_conf=fsm_cfg)

        self.apparatus_id = self.cfg.apparatus_id

        self.run_num_mgr = run_num_mgr
        self.cfgsvr = run_registry
        if self.cfgsvr:
            self.cfgsvr.cfgmgr = self.cfg
            self.cfgsvr.apparatus_id = self.apparatus_id
        self.timeout = timeout
        self.return_code = None
        self.logbook = None
        self.log_path = None

        if logbook_type != 'file' and logbook_type != '':
            try:
                elisa_conf = json.load(open(logbook_type,'r'))
                if elisa_conf.get(self.apparatus_id):
                    self.logbook = ElisaLogbook(configuration = elisa_conf[self.apparatus_id],
                                                console = console)
                else:
                    self.log.error(f"Can't find config {self.apparatus_id} in {logbook_type}, reverting to file logbook!")
            except Exception as e:
                self.log.error(f"Can't find {logbook_type}, reverting to file logbook! {str(e)}")

        elif logbook_type == 'file':
            self.log.info("Using filelogbook")
            self.logbook = FileLogbook(logbook_prefix, self.console)

        self.topnode = self.cfg.get_tree_structure()
        self.console.print(f"Running on the apparatus [bold red]{self.cfg.apparatus_id}[/bold red]:")



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
        if not self.topnode.can_boot():
            self.log.error(f'Cannot boot, as you are in {self.topnode.state} state.')
            self.topnode.return_code = ErrorCode.InvalidTransition
            self.return_code = self.topnode.return_code.value
            return
        self.topnode.boot(timeout=self.timeout, log=self.log_path)
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
        if not self.topnode.can_init():
            self.log.error(f'Cannot init, as you are in {self.topnode.state} state.')
            self.topnode.return_code = ErrorCode.InvalidTransition
            self.return_code = self.topnode.return_code.value
            return
        self.topnode.init(path=path, raise_on_fail=True, timeout=self.timeout)
        self.return_code = self.topnode.return_code.value


    def conf(self, path) -> NoReturn:
        """
        Sends configure command to the applications.
        """
        if not self.topnode.can_conf():
            self.log.error(f'Cannot conf, as you are in {self.topnode.state} state.')
            self.topnode.return_code = ErrorCode.InvalidTransition
            self.return_code = self.topnode.return_code.value
            return
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
            self.topnode.return_code = ErrorCode.InvalidTransition
            self.return_code = self.topnode.return_code.value
            self.return_code = 1
            return

        if self.run_num_mgr:
            self.run = self.run_num_mgr.get_run_number()
        else:
            self.run = 1

        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")

        if self.logbook:
            try:
                self.logbook.message_on_start(message, self.run, run_type)
            except Exception as e:
                self.log.error(f"Couldn't make an entry to elisa, do it yourself manually at {self.logbook.website}\nError text:\n{str(e)}")


        runtime_start_data = {
            "disable_data_storage": disable_data_storage,
            "run": self.run,
        }

        if self.cfgsvr:
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
            text = ""
            if self.run_num_mgr:
                text += f"Started run #{self.run}"
            else:
                text += "Started running"

            if self.cfgsvr:
                text+=f", saving run data in {cfg_save_dir}"

            self.console.rule(f"[bold magenta]{text}[/bold magenta]")
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

        if not self.topnode.can_stop():
            self.log.error(f'Cannot stop, as you are in {self.topnode.state} state.')
            self.topnode.return_code = ErrorCode.InvalidTransition
            self.return_code = self.topnode.return_code.value
            return

        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")
            try:
                self.logbook.message_on_stop(message)
            except Exception as e:
                self.log.error(f"Couldn't make an entry to elisa, do it yourself manually at {self.logbook.website}\nError text:\n{str(e)}")

        if self.cfgsvr:
            self.cfgsvr.save_on_stop(self.run)

        self.topnode.stop(path=None, raise_on_fail=True, timeout=self.timeout, force=force)
        self.return_code = self.topnode.return_code.value

        if self.return_code == 0:
            if self.run_num_mgr:
                self.console.rule(f"[bold magenta]Stopped run #{self.run}[/bold magenta]")
            else:
                self.console.rule(f"[bold magenta]Stopped running[/bold magenta]")


    def pause(self, force:bool=False) -> NoReturn:
        """
        Sends pause command
        """
        if not self.topnode.can_pause():
            self.log.error(f'Cannot pause, as you are in {self.topnode.state} state.')
            self.topnode.return_code = ErrorCode.InvalidTransition
            self.return_code = self.topnode.return_code.value
            return

        self.topnode.pause(path=None, raise_on_fail=True, timeout=self.timeout, force=force)
        self.return_code = self.topnode.return_code.value


    def resume(self, trigger_interval_ticks: Union[int, None]) -> NoReturn:
        """
        Sends resume command

        :param      trigger_interval_ticks:  The trigger interval ticks
        :type       trigger_interval_ticks:  int
        """
        runtime_resume_data = {}
        if not self.topnode.can_resume():
            self.log.error(f'Cannot resume, as you are in {self.topnode.state} state.')
            self.topnode.return_code = ErrorCode.InvalidTransition
            self.return_code = self.topnode.return_code.value
            return

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
        if not self.topnode.can_scrap():
            self.log.error(f'Cannot scrap, as you are in {self.topnode.state} state.')
            self.topnode.return_code = ErrorCode.InvalidTransition
            self.return_code = self.topnode.return_code.value
            return

        self.topnode.scrap(path=None, raise_on_fail=True, timeout=self.timeout, force=force)
        self.return_code = self.topnode.return_code.value
