import logging
import time
import json
import os
import copy as cp
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

# Good ol' moo import
from dunedaq.env import get_moo_model_path
import moo.io
moo.io.default_load_path = get_moo_model_path()
import moo.otypes
import moo.oschema as moosc
moo.otypes.load_types('rcif/cmd.jsonnet')
moo.otypes.load_types('cmdlib/cmd.jsonnet')
import dunedaq.rcif.cmd as rccmd  # AddressedCmd,
import dunedaq.cmdlib.cmd as cmd  # AddressedCmd,


class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, top_cfg: str, run_num_mgr, run_registry, logbook_type:str, timeout: int,
                 use_kerb=True, logbook_prefix="", port_offset=0, partition_label=None, partition_number=None, fsm_cfg="partition"):
        super(NanoRC, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.console = console
        ssh_conf = []
        if not use_kerb:
            ssh_conf = ["-o GSSAPIAuthentication=no"]
        self.partition_label = partition_label
        self.partition_number = partition_number
        self.port_offset = port_offset
        self.cfg = TreeBuilder(log=self.log,
                               top_cfg=top_cfg,
                               console=self.console,
                               ssh_conf=ssh_conf,
                               fsm_conf=fsm_cfg,
                               port_offset=self.port_offset,
                               partition_label=self.partition_label,
                               partition_number=self.partition_number)

        self.custom_cmd = self.cfg.get_custom_commands()
        self.console.print(f'Extra commands are {list(self.custom_cmd.keys())}')

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


    def execute_custom_command(self, command, data, timeout, node=None):
        if not timeout:
            timeout = self.timeout

        if not node:
            self.log.debug(f'Sending {command} to all the nodes')
            ret = self.topnode.send_custom_command(command, data, timeout=timeout)
        elif isinstance(node, ApplicationNode):
            self.log.debug(f'Telling {node.parent.name} to send {command} to {node.name}')
            ret = node.parent.send_custom_command(command, data, timeout=timeout, app=node.name)
        else:
            self.log.debug(f'Sending {command} to {node.name}')
            ret = node.send_custom_command(command, data, timeout=timeout)

        self.log.debug(ret)

    def send_expert_command(self, app, json_file, timeout):
        if not timeout:
            timeout = self.timeout

        data = json.load(open(json_file,'r'))
        try:
            # masterminding moo here, and constructing a schema of no schema
            cmd_data = moo.otypes.make_type(
                name='command_data',
                text="command_data",
                doc="",
                schema="string",
                dtype='string')
            # check this out, this is dumping raw json into a string
            obj = cmd_data(json.dumps(data['data']))
            d = cmd.Data(obj)
            data_cp = cp.deepcopy(data)
            data_cp['data'] = d
            the_cmd = rccmd.RCCommand(**data_cp)
            if the_cmd.exit_state != 'ANY' and the_cmd.entry_state != the_cmd.exit_state:
                self.log.error(f'The entry and exit states need to be the same for expert commands!')

            # fortunately we dont keep this frankenschemoo
        except Exception as e:
            self.log.error(f'The file {json_file} content doesn\'t correspond to a rcif.command.RCCommand, bailing\n{e}')
            return

        if not isinstance(app, ApplicationNode):
            self.log.error(f'You can only send expert commands to individual application! I\'m not sending anything for now.')
            return

        ret = app.parent.send_expert_command(app, data, timeout=timeout)
        self.log.info(f'Reply: {ret}')

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

        kwargs['timeout'] = kwargs['timeout'] if kwargs.get('timeout') else self.timeout
        self.log.debug(f'Using timeout = {kwargs["timeout"]}')
        transition = getattr(self.topnode, command)
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


    def boot(self, timeout:int=None) -> NoReturn:
        """
        Boots applications
        """
        self.execute_command("boot", timeout=timeout, log=self.log_path)


    def terminate(self, timeout:int=None) -> NoReturn:
        """
        Terminates applications (but keep all the subsystems structure)
        """
        self.execute_command("terminate", timeout=timeout)


    def init(self, path, timeout:int=None) -> NoReturn:
        """
        Initializes the applications.
        """
        self.execute_command("init", path=path, raise_on_fail=True, timeout=timeout)


    def conf(self, path, timeout:int=None) -> NoReturn:
        """
        Sends configure command to the applications.
        """
        self.execute_command("conf", path=path, raise_on_fail=True, timeout=timeout)


    def pause(self, force:bool=False, timeout:int=None) -> NoReturn:
        """
        Sends pause command
        """
        self.execute_command("pause", path=None, raise_on_fail=True, timeout=timeout, force=force)


    def scrap(self, path, force:bool=False, timeout:int=None) -> NoReturn:
        """
        Send scrap command
        """
        self.execute_command("scrap", path=None, raise_on_fail=True, timeout=timeout, force=force)


    def start(self, disable_data_storage: bool, run_type:str, message:str="", timeout:int=None) -> NoReturn:
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

        self.execute_command("start", path=None, raise_on_fail=True,
                             cfg_method="runtime_start",
                             overwrite_data=runtime_start_data,
                             timeout=timeout)

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


    def stop(self, force:bool=False, message:str="", timeout:int=None) -> NoReturn:
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

        self.execute_command("stop", path=None, raise_on_fail=True, timeout=timeout, force=force)
        self.return_code = self.topnode.return_code.value

        if self.return_code == 0:
            if self.run_num_mgr:
                self.console.rule(f"[bold magenta]Stopped run #{self.run}[/bold magenta]")
            else:
                self.console.rule(f"[bold magenta]Stopped running[/bold magenta]")




    def resume(self, trigger_interval_ticks: Union[int, None], timeout:int=None) -> NoReturn:
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

        self.execute_command("resume",
                             path=None, raise_on_fail=True,
                             cfg_method="runtime_resume",
                             overwrite_data=runtime_resume_data,
                             timeout=timeout)
        self.return_code = self.topnode.return_code.value


    def execute_script(self, timeout, data=None) -> NoReturn:
        self.execute_custom_command('scripts', data=data, timeout=timeout)

    def start_trigger(self, trigger_interval_ticks: Union[int, None], timeout) -> NoReturn:
        """
        Start the triggers
        """
        self.execute_custom_command("start_trigger",
                                    data={'trigger_interval_ticks':trigger_interval_ticks},
                                    timeout=timeout)


    def stop_trigger(self, timeout) -> NoReturn:
        """
        Stop the triggers
        """
        self.execute_custom_command("stop_trigger",
                                    data={},
                                    timeout=timeout)


    def change_rate(self, trigger_interval_ticks, timeout) -> NoReturn:
        """
        Start the triggers
        """
        self.execute_custom_command("change_rate",
                                    data={'trigger_interval_ticks':trigger_interval_ticks},
                                    timeout=timeout)


    def disable(self, node, timeout, resource_name) -> NoReturn:
        """
        Start the triggers
        """
        ret = node.disable()
        if ret != 0:
            return
        self.execute_custom_command("disable",
                                    data={'resource_name': resource_name if resource_name else node.name},
                                    timeout=timeout,
                                    node=node)


    def enable(self, node, timeout, resource_name) -> NoReturn:
        """
        Start the triggers
        """
        ret = node.enable()
        if ret != 0:
            return
        self.execute_custom_command("enable",
                                    data={'resource_name': resource_name if resource_name else node.name},
                                    timeout=timeout,
                                    node=node)
