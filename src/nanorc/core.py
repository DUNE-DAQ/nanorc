import logging
import time
from .cfgmgr import ConfigManager
from .appctrl import AppSupervisor, ResponseListener
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
from rich.progress import *
from rich.table import Table
from .runinfo import start_run, print_run_info

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

    def __init__(self, console: Console, top_cfg: str, partition_label:str, run_num_mgr, run_registry, logbook_type:str, timeout: int,
                 use_kerb=True, logbook_prefix="", fsm_cfg="partition", port_offset=0,
                 pm=None):
        super(NanoRC, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.console = console
        self.pm = pm

        self.ssh_conf = []
        if not use_kerb:
            self.ssh_conf = ["-o GSSAPIAuthentication=no"]
        self.port_offset = port_offset
        self.cfg = TreeBuilder(
            log=self.log,
            top_cfg=top_cfg,
            console=self.console,
            fsm_conf=fsm_cfg,
            resolve_hostname = pm.use_sshpm(),
            port_offset=self.port_offset)
        self.partition = partition_label

        self.custom_cmd = self.cfg.get_custom_commands()
        self.console.print(f'Extra commands are {list(self.custom_cmd.keys())}')

        self.apparatus_id = self.cfg.apparatus_id

        self.runs = []
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

    def get_command_sequence(self, command:str):
        seq_cmd = self.topnode.fsm.command_sequences.get(command)
        return seq_cmd if seq_cmd else [command]

    def can_execute(self, command:str, quiet=False):
        return self.topnode.can_execute(command, quiet=quiet)

    def execute_custom_command(self, command, data, timeout, node_path=None, check_dead=True):
        if not timeout:
            timeout = self.timeout

        node_to_send = None
        extra_arg={}

        if not node_path:
            self.log.info(f'Sending {command} to all the nodes')
            node_to_send = self.topnode
        elif isinstance(node_path, ApplicationNode):
            self.log.info(f'Telling {node_path.parent.name} to send {command} to {node_path.name}')
            node_to_send = node_path.parent
            extra_arg['app'] = node_path.name
        else:
            self.log.info(f'Sending {command} to {node_path.name}')
            node_to_send = node_path

        if not node_to_send.can_execute_custom_or_expert(command, check_dead):
            self.return_code = node_to_send.return_code
            return

        ret = node_to_send.send_custom_command(command, data, timeout=timeout, **extra_arg)
        self.log.debug(ret)

    def send_expert_command(self, node_path, json_file, timeout):
        if not timeout:
            timeout = self.timeout

        if not node_path.can_execute_custom_or_expert("expert", check_dead=True):
            self.return_code = node_path.return_code
            return

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

        if not isinstance(node_path, ApplicationNode):
            self.log.error(f'You can only send expert commands to individual application! I\'m not sending anything for now.')
            return

        ret = node_path.parent.send_expert_command(node_path, data, timeout=timeout)
        self.log.info(f'Reply: {ret}')

    def execute_command(self, command, node_path=None, **kwargs):
        force = kwargs.get('force')
        if not node_path:
            node_path=self.topnode

        if not force and not node_path.can_execute(command):
            self.return_code = node_path.return_code.value
            return

        kwargs['timeout'] = kwargs['timeout'] if kwargs.get('timeout') else self.timeout
        print(command, node_path.name)
        self.log.debug(f'Executing the cmd {command} on the node {node_path.name}, using timeout = {kwargs["timeout"]}')
        transition = getattr(node_path, command)
        kwargs['pm'] = self.pm
        transition(**kwargs)
        self.return_code = node_path.return_code.value


    def status(self) -> NoReturn:
        """
        Displays the status of the applications
        :returns:   Nothing
        :rtype:     None
        """
        if not self.topnode:
            return

        if self.runs:
            print_run_info(self.runs[-1], self.console)
        print_status(apparatus_id=self.apparatus_id, topnode=self.topnode, console=self.console, partition=self.partition)

    def ls(self, leg:bool) -> NoReturn:
        """
        Print the nodes
        """
        self.return_code = print_node(node=self.topnode, console=self.console, leg=leg)


    def boot(self, timeout:int) -> NoReturn:
        """
        Boot applications
        """
        self.execute_command(
            "boot",
            partition=self.partition,
            timeout=timeout,
            ssh_conf=self.ssh_conf,
            log_path=self.log_path,
        )


    def terminate(self, timeout:int, force:bool, **kwargs) -> NoReturn:
        """
        Terminates applications (but keep all the subsystems structure)
        """
        self.execute_command("terminate", timeout=timeout, force=force)

    def ls_thread(self) -> NoReturn:
        import threading
        self.console.print("Threading threads")
        self.console.print(threading.enumerate())
        from multiprocessing import Manager
        with Manager() as manager:
            self.console.print("Multiprocess threads")
            self.console.print(manager.list())

    def abort(self, timeout:int, **kwargs) -> NoReturn:
        """
        Abort applications
        """
        self.execute_command("abort", timeout=timeout)

    def init(self, node_path, timeout:int, **kwargs) -> NoReturn:
        """
        Initializes the applications.
        """
        self.execute_command("init", node_path=node_path, raise_on_fail=True, timeout=timeout)


    def conf(self, node_path, timeout:int, **kwargs) -> NoReturn:
        """
        Sends configure command to the applications.
        """
        self.execute_command("conf", node_path=node_path, raise_on_fail=True, timeout=timeout)


    def scrap(self, node_path, force:bool, timeout:int, **kwargs) -> NoReturn:
        """
        Send scrap command
        """
        self.execute_command("scrap", node_path=node_path, raise_on_fail=True, timeout=timeout, force=force)

    def start(self, run_type:str, trigger_interval_ticks:int, disable_data_storage:bool, timeout:int, message:str, **kwargs) -> NoReturn:
        """
        Sends start command to the applications

        Args:
            disable_data_storage (bool): whether to store or not the data
            run_type (str): PROD or TEST
            message (str): some free text to describe the run
        """

        if not self.topnode.can_execute("start"):
            self.return_code = self.topnode.return_code
            return

        run = 0
        if self.run_num_mgr:
            run = self.run_num_mgr.get_run_number()
        else:
            run = 1

        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")

        if self.logbook:
            try:
                self.logbook.message_on_start(message, run, run_type)
            except Exception as e:
                self.log.error(f"Couldn't make an entry to elisa, do it yourself manually at {self.logbook.website}\nError text:\n{str(e)}")


        runtime_start_data = {
            "disable_data_storage": disable_data_storage,
            "run": run,
        }

        if self.cfgsvr:
            try:
                cfg_save_dir = self.cfgsvr.save_on_start(self.topnode, run=run, run_type=run_type,
                                                         overwrite_data=runtime_start_data,
                                                         cfg_method="runtime_start")
            except Exception as e:
                self.log.error(f'Couldn\'t save the configuration so not starting a run!\n{str(e)}')
                self.return_code = 1
                return

        self.execute_command(
            "start",
            node_path = None,
            raise_on_fail = True,
            cfg_method = "runtime_start",
            overwrite_data = runtime_start_data,
            timeout = timeout
        )

        self.return_code = self.topnode.return_code.value
        if self.return_code == 0:
            self.runs.append(
                start_run(
                    run_number=run,
                    run_type=run_type,
                    enable_data_storage=not disable_data_storage,
                )
            )
            text = ""
            if self.run_num_mgr:
                text += f"Started run #{run}"
            else:
                text += "Started running"

            if self.cfgsvr:
                text+=f", saving run data in {cfg_save_dir}"

            self.console.rule(f"[bold magenta]{text}[/bold magenta]")
        else:
            self.log.error(f"There was an error when starting the run #{run}:")
            self.log.error(f'Response: {self.topnode.response}')

    def message(self, message:str) -> NoReturn:
        """
        Append the logbook
        """
        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")
            try:
                self.logbook.add_message(message)
                # if self.runs:
                #     if self.runs[-1].is_running():
                #         self.runs[-1].messages.append(message)
            except Exception as e:
                self.log.error(f"Couldn't make an entry to elisa, do it yourself manually at {self.logbook.website}\nError text:\n{str(e)}")

    def stop(self, force:bool, timeout:int, **kwargs) -> NoReturn:
        """
        Sends stop command
        """
        self.execute_command("stop", node_path=None, raise_on_fail=True, timeout=timeout, force=force)

    def prestop2(self, force:bool, timeout:int, **kwargs) -> NoReturn:
        """
        Sends stop command
        """
        self.execute_command("prestop2", node_path=None, raise_on_fail=True, timeout=timeout, force=force)


    def execute_script(self, timeout, data=None) -> NoReturn:
        self.execute_custom_command('scripts', data=data, timeout=timeout)


    def enable_triggers(self, trigger_interval_ticks: Union[int, None], timeout, **kwargs) -> NoReturn:
        """
        Start the triggers
        """
        self.execute_command(
            "enable_triggers",
            node_path = None,
            raise_on_fail = True,
            force = False,
            trigger_interval_ticks = trigger_interval_ticks,
            timeout = timeout
        )

    def disable_triggers(self, timeout:int, force:bool, **kwargs) -> NoReturn:
        """
        Start the triggers
        """
        self.execute_command(
            "disable_triggers",
            node_path = None,
            raise_on_fail = True,
            force = force,
            timeout = timeout,
        )

    def prestop1(self, timeout:int, force:bool, message:str, **kwargs) -> NoReturn:
        """
        Stop the triggers
        """

        if not force and not self.topnode.can_execute("prestop1"):
            self.return_code = self.topnode.return_code
            return

        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")
            try:
                self.logbook.message_on_stop(message)
                # if self.runs: self.runs[-1].messages.append(message)
            except Exception as e:
                self.log.error(f"Couldn't make an entry to elisa, do it yourself manually at {self.logbook.website}\nError text:\n{str(e)}")

        if self.cfgsvr:
            self.cfgsvr.save_on_stop(self.runs[-1].run_number)

        self.execute_command("prestop1", node_path=None, raise_on_fail=True, timeout=timeout, force=force)
        self.return_code = self.topnode.return_code.value

        if self.return_code == 0:
            run = None
            if self.runs:
                self.runs[-1].finish_run()
                run = self.runs[-1].run_number
            if self.run_num_mgr:
                self.console.rule(f"[bold magenta]Stopped run #{run}[/bold magenta]")
            else:
                self.console.rule(f"[bold magenta]Stopped running[/bold magenta]")


    def change_rate(self, trigger_interval_ticks, timeout) -> NoReturn:
        """
        Change the trigger interval ticks
        """
        self.execute_custom_command(
            "change_rate",
            data={'trigger_interval_ticks':trigger_interval_ticks},
            timeout=timeout
        )


    def exclude(self, node_path, timeout, resource_name) -> NoReturn:

        if not node_path.can_execute_custom_or_expert("exclude", False):
            self.return_code = node_path.return_code
            return

        ret = node_path.exclude()
        if ret != 0:
            return

        self.execute_custom_command(
            "exclude",
            data={'resource_name': resource_name if resource_name else node_path.name},
            timeout=timeout,
            node_path=node_path,
            check_dead=False
        )


    def include(self, node_path, timeout, resource_name) -> NoReturn:

        if not node_path.can_execute_custom_or_expert("include", True):
            self.return_code = node_path.return_code
            return

        ret = node_path.include()
        if ret != 0:
            return

        self.execute_custom_command(
            "include",
            data={'resource_name': resource_name if resource_name else node_paht.name},
            timeout=timeout,
            node_path=node_path
        )
