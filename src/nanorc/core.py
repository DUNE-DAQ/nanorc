import logging
import time
import json
import os
import importlib

from datetime import datetime
from typing import Union, NoReturn

from rich.console import Console
from rich.style import Style
from rich.pretty import Pretty
from rich.traceback import Traceback

from .node import GroupNode
from .treebuilder import TreeBuilder
from .cfgsvr import FileConfigSaver, DBConfigSaver
from .credmgr import credentials
from .logbook import ElisaLogbook, FileLogbook


class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, top_cfg: str, run_num_mgr, run_registry, logbook_type:str, timeout: int,
                 use_kerb=True, logbook_prefix="", log_path='.'):
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
        self.log_path = os.path.expandvars(log_path)

        if not os.path.isdir(self.log_path):
            try:
                os.makedirs(self.log_path)
            except Exception as e:
                raise RuntimeError(f'Logging path: {self.log_path} doesn\'t exist, and I cannot create it!') from e

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

        self.topnode.print_status(self.apparatus_id, self.console)


    def boot(self) -> NoReturn:
        """
        Boots applications
        """
        now = datetime.now() # current date and time
        date_time = now.strftime("%Y%m%d_%H%M%S")
        time_stamp_log_path = self.log_path + f'/logs_{date_time}'
        try:
            os.mkdir(time_stamp_log_path)
        except:
            raise RuntimeError(f'Can\'t create directory {time_stamp_log_path} not booting.')
        self.return_code = self.topnode.boot(log_path=time_stamp_log_path)


    def terminate(self) -> NoReturn:
        """
        Terminates applications (but keep all the subsystems structure)
        """

        self.return_code = self.topnode.terminate()


    def ls(self, leg:bool=True) -> NoReturn:
        """
        Print the nodes
        """

        self.return_code = self.topnode.print(leg, self.console)


    def init(self, path) -> NoReturn:
        """
        Initializes the applications.
        """

        self.return_code = self.topnode.send_command(path, 'init',
                                                     'NONE', 'INITIAL',
                                                     raise_on_fail=True,
                                                     timeout=self.timeout)


    def conf(self, path) -> NoReturn:
        """
        Sends configure command to the applications.
        """

        self.return_code = self.topnode.send_command(path, 'conf',
                                                     'INITIAL', 'CONFIGURED',
                                                     raise_on_fail=True,
                                                     timeout=self.timeout)


    def start(self, disable_data_storage: bool, run_type:str, message:str="") -> NoReturn:
        """
        Sends start command to the applications

        Args:
            disable_data_storage (bool): Description
            run_type (str): Description
        """

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

        cfg_save_dir = self.cfgsvr.save_on_start(self.topnode, run=self.run, run_type=run_type,
                                                 overwrite_data=runtime_start_data,
                                                 cfg_method="runtime_start")

        self.return_code = self.topnode.send_command(None, 'start',
                                                     'CONFIGURED', 'RUNNING',
                                                     raise_on_fail=True,
                                                     cfg_method="runtime_start",
                                                     overwrite_data=runtime_start_data,
                                                     timeout=self.timeout)

        self.console.log(f"[bold magenta]Started run #{self.run}, saving run data in {cfg_save_dir}[/bold magenta]")

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
        self.return_code = self.topnode.send_command(None, 'stop', 'RUNNING', 'CONFIGURED', raise_on_fail=True, timeout=self.timeout, force=force)
        self.console.log(f"[bold magenta]Stopped run #{self.run}[/bold magenta]")


    def pause(self, force:bool=False) -> NoReturn:
        """
        Sends pause command
        """

        self.return_code = self.topnode.send_command(None, 'pause',
                                                     'RUNNING', 'RUNNING',
                                                     raise_on_fail=True,
                                                     timeout=self.timeout,
                                                     force=force)


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

        self.return_code = self.topnode.send_command(None, 'resume', 'RUNNING', 'RUNNING', raise_on_fail=True, cfg_method="runtime_resume", overwrite_data=runtime_resume_data, timeout=self.timeout)


    def scrap(self, path, force:bool=False) -> NoReturn:
        """
        Send scrap command
        """

        self.return_code = self.topnode.send_command(path, 'scrap',
                                                     'CONFIGURED', 'INITIAL',
                                                     raise_on_fail=True,
                                                     timeout=self.timeout,
                                                     force=force)
