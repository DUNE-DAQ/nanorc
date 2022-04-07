import logging
import time
from .sshpm import SSHProcessManager
from .k8spm import K8SProcessManager
from .cfgmgr import ConfigManager
from .appctrl import AppSupervisor, ResponseListener
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
from rich.progress import *
from rich.table import Table

from datetime import datetime

from typing import Union, NoReturn

from dunedaq.env import get_moo_model_path
import moo.io
moo.io.default_load_path = get_moo_model_path()

# Load configuration types
import moo.otypes
moo.otypes.load_types('rcif/cmd.jsonnet')
moo.otypes.load_types('appfwk/cmd.jsonnet')
moo.otypes.load_types('appfwk/app.jsonnet')

moo.otypes.load_types('dfmodules/triggerrecordbuilder.jsonnet')
moo.otypes.load_types('dfmodules/datawriter.jsonnet')
moo.otypes.load_types('dfmodules/hdf5datastore.jsonnet')
moo.otypes.load_types('dfmodules/fragmentreceiver.jsonnet')
moo.otypes.load_types('dfmodules/triggerdecisionreceiver.jsonnet')
moo.otypes.load_types('nwqueueadapters/queuetonetwork.jsonnet')
moo.otypes.load_types('nwqueueadapters/networktoqueue.jsonnet')
moo.otypes.load_types('nwqueueadapters/networkobjectreceiver.jsonnet')
moo.otypes.load_types('nwqueueadapters/networkobjectsender.jsonnet')
moo.otypes.load_types('networkmanager/nwmgr.jsonnet')


# Import new types
import dunedaq.cmdlib.cmd as basecmd # AddressedCmd,
import dunedaq.rcif.cmd as rccmd # AddressedCmd,
import dunedaq.appfwk.cmd as cmd # AddressedCmd,
import dunedaq.appfwk.app as app # AddressedCmd,
import dunedaq.dfmodules.triggerrecordbuilder as trb
import dunedaq.dfmodules.datawriter as dw
import dunedaq.hdf5libs.hdf5filelayout as h5fl
import dunedaq.dfmodules.hdf5datastore as hdf5ds
import dunedaq.dfmodules.fragmentreceiver as frcv
import dunedaq.dfmodules.triggerdecisionreceiver as tdrcv
import dunedaq.nwqueueadapters.networktoqueue as ntoq
import dunedaq.nwqueueadapters.queuetonetwork as qton
import dunedaq.nwqueueadapters.networkobjectreceiver as nor
import dunedaq.nwqueueadapters.networkobjectsender as nos
import dunedaq.networkmanager.nwmgr as nwmgr

class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, top_cfg: str, run_num_mgr, run_registry, logbook_type:str, timeout: int,
                 use_kerb=True, logbook_prefix="", fsm_cfg="partition",
                 use_k8s=False):
        
        super(NanoRC, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.console = console
        self.use_k8s = use_k8s
        h5fl.PathParams(detector_group_type="TPC",
                        detector_group_name="TPC",
                        region_name_prefix='SOMETHING',
                        element_name_prefix="Link"),
                                        
        ssh_conf = []
        if not use_kerb:
            ssh_conf = ["-o GSSAPIAuthentication=no"]

        self.cfg = TreeBuilder(log=self.log,
                               top_cfg=top_cfg,
                               console=self.console,
                               ssh_conf=ssh_conf,
                               fsm_conf=fsm_cfg,
                               resolve_hostname = not use_k8s)

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

        if logbook_type != 'file' and logbook_type != None and logbook_type != '':
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


    def can_transition(self, command):
        can_execute = getattr(self.topnode, "can_"+command)
        if not can_execute():
            self.log.error(f'Cannot {command}, as you are in {self.topnode.state} state.')
            self.topnode.return_code = ErrorCode.InvalidTransition
            self.return_code = self.topnode.return_code.value
            return False
        return True


    def execute_command(self, command, *args, **kwargs):
        if not self.can_transition(command):
            return

        transition = getattr(self.topnode, command)
        kwargs['k8s'] = self.use_k8s
        transition(*args, **kwargs)
        self.return_code = self.topnode.return_code.value

    def status(self) -> NoReturn:
        """
        Displays the status of the applications
        :returns:   Nothing
        :rtype:     None
        """
        if not self.topnode:
            return

        print_status(apparatus_id=self.apparatus_id, topnode=self.topnode, console=self.console)

    def ls(self, leg:bool=True) -> NoReturn:
        """
        Print the nodes
        """
        self.return_code = print_node(node=self.topnode, console=self.console, leg=leg)


    def boot(self, partition: str) -> NoReturn:
        """
        Boots applications
        """
        self.execute_command("boot", timeout=self.timeout, log=self.log_path, partition=partition)


    def terminate(self) -> NoReturn:
        """
        Terminates applications (but keep all the subsystems structure)
        """
        self.execute_command("terminate")


    def init(self, path) -> NoReturn:
        """
        Initializes the applications.
        """
        self.execute_command("init", path=path, raise_on_fail=True, timeout=self.timeout)


    def conf(self, path) -> NoReturn:
        """
        Sends configure command to the applications.
        """
        self.execute_command("conf", path=path, raise_on_fail=True, timeout=self.timeout)


    def pause(self, force:bool=False) -> NoReturn:
        """
        Sends pause command
        """
        self.execute_command("pause", path=None, raise_on_fail=True, timeout=self.timeout, force=force)


    def scrap(self, path, force:bool=False) -> NoReturn:
        """
        Send scrap command
        """
        self.execute_command("scrap", path=None, raise_on_fail=True, timeout=self.timeout, force=force)


    def start(self, disable_data_storage: bool, run_type:str, message:str="") -> NoReturn:
        """
        Sends start command to the applications

        Args:
            disable_data_storage (bool): Description
            run_type (str): Description
        """
        # self.return_code = self.topnode.allowed("start", None)
        if not self.can_transition("start"):
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

        if not self.can_transition("stop"):
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




    def resume(self, trigger_interval_ticks: Union[int, None]) -> NoReturn:
        """
        Sends resume command

        :param      trigger_interval_ticks:  The trigger interval ticks
        :type       trigger_interval_ticks:  int
        """
        if not self.can_transition("resume"):
            return

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
