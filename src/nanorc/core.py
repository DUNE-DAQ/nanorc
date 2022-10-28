import logging
import time
from .cfgmgr import ConfigManager
from .appctrl import AppSupervisor, ResponseListener
import json
import os
import copy as cp
import requests
import importlib.resources as resources
from rich.console import Console
from rich.style import Style
from rich.pretty import Pretty
from .statefulnode import StatefulNode, CanExecuteReturnVal
from .treebuilder import TreeBuilder
from .cfgsvr import FileConfigSaver, DBConfigSaver
from .credmgr import credentials
from .node_render import *
from .logbook import FileLogbook, ElisaLogbook
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
        self.logbook_type = logbook_type
        self.log_path = None
        self.current_run_type = None
        self.message_thread_id = None
        '''
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
        '''

        if logbook_type == 'file':
            self.log.info("Using file logbook")
            self.logbook = FileLogbook(logbook_prefix, self.console)
        else:
            self.log.info("Using ELisA logbook")
            self.logbook = ElisaLogbook(self.apparatus_id)
        self.topnode = self.cfg.get_tree_structure()
        self.console.print(f"Running on the apparatus [bold red]{self.cfg.apparatus_id}[/bold red]:")

    def get_command_sequence(self, command:str):
        seq_cmd = self.topnode.fsm.command_sequences.get(command)
        return seq_cmd if seq_cmd else [command]

    def can_execute(self, command:str, quiet=False):
        return self.topnode.can_execute(command, quiet=quiet)

    def execute_custom_command(self, command, data, timeout, node_path=None, check_dead=True, check_inerror=True, only_included=True):
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

        canexec = node_to_send.can_execute_custom_or_expert(
            command,
            quiet=False,
            check_dead=check_dead,
            check_inerror=check_inerror,
            only_included=only_included,
        )
        if canexec != CanExecuteReturnVal.CanExecute:
            self.log.error(f'Cannot execute {command}, reason: {str(canexec)}')
            self.return_code = node_to_send.return_code
            return

        ret = node_to_send.send_custom_command(command, data, timeout=timeout, **extra_arg)
        self.log.debug(ret)

    def send_expert_command(self, node_path, json_file, timeout):
        if not timeout:
            timeout = self.timeout

        canexec = node_path.can_execute_custom_or_expert("expert", check_dead=True)

        if canexec != CanExecuteReturnVal.CanExecute:
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

        canexec = node_path.can_execute(
            command,
            quiet=True,
            check_dead=not force,
            check_inerror=not force,
            only_included=True,
        )
        if canexec == CanExecuteReturnVal.InvalidTransition:
            self.return_code = node_path.return_code.value
            self.log.info(f"Cannot execute {command}, reason: {str(canexec)}")
            return
        elif canexec != CanExecuteReturnVal.CanExecute:
            if not force:
                self.log.info(f"Cannot execute {command}, reason: {str(canexec)}, you may be able to --force")
                return

        kwargs['timeout'] = kwargs['timeout'] if kwargs.get('timeout') else self.timeout

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
        self.execute_command("abort", timeout=timeout, force=True)


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

    def start(self, run_type:str, trigger_rate:float, disable_data_storage:bool, timeout:int, message:str, **kwargs) -> NoReturn:
        """
        Sends start command to the applications

        Args:
            disable_data_storage (bool): whether to store or not the data
            run_type (str): PROD or TEST
            message (str): some free text to describe the run
        """

        canexec = self.topnode.can_execute("start")
        if canexec != CanExecuteReturnVal.CanExecute:
            self.log.error(f'Cannot execute start, reason: {str(canexec)}')
            self.return_code = self.topnode.return_code
            return

        run = 0
        if self.run_num_mgr:
            run = self.run_num_mgr.get_run_number()
        else:
            run = 1

        stparam = {
            "run":run,
            "disable_data_storage":disable_data_storage
        }

        if not trigger_rate is None:
            stparam['trigger_rate'] = trigger_rate

        runtime_start_data = rccmd.StartParams(**stparam).pod() # EnFoRcE tHiS sChEmA aNd DiTcH iT

        self.current_run_type = run_type

        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")

        try:
            self.logbook.message_on_start(message, run, self.current_run_type)
        except Exception as e:
                self.log.error(f"Writing to the {self.logbook_type} logbook unsuccessful\nError text:\n{str(e)}")


        if self.cfgsvr:
            try:
                cfg_save_dir = self.cfgsvr.save_on_start(
                    self.topnode,
                    run=run,
                    run_type=run_type,
                    data=runtime_start_data,
                )
            except Exception as e:
                self.log.error(f'Couldn\'t save the configuration so not starting a run!\n{str(e)}')
                self.return_code = 1
                return

        self.execute_command(
            "start",
            node_path = None,
            raise_on_fail = True,
            overwrite_data = runtime_start_data,
            timeout = timeout
        )

        self.return_code = self.topnode.return_code.value
        if self.return_code == 0:
            self.runs.append(
                start_run(
                    run_number = run,
                    run_type = run_type,
                    enable_data_storage = not disable_data_storage,
                    trigger_rate = trigger_rate
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
                except Exception as e:
                    self.log.error(f"Writing to the {self.logbook_type} logbook unsuccessful\nError text:\n{str(e)}")

    def stop(self, force:bool, timeout:int, message="", **kwargs) -> NoReturn:
        """
        Sends stop command
        """
        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")

        try:
            self.logbook.message_on_stop()
        except Exception as e:
            self.log.error(f"Writing to the {self.logbook_type} logbook unsuccessful\nError text:\n{str(e)}")


        self.execute_command("stop", node_path=None, raise_on_fail=True, timeout=timeout, force=force)

    def stop_trigger_sources(self, force:bool, timeout:int, **kwargs) -> NoReturn:
        """
        Sends stop command
        """
        self.execute_command("stop_trigger_sources", node_path=None, raise_on_fail=True, timeout=timeout, force=force)


    def execute_script(self, timeout, data=None) -> NoReturn:
        self.execute_custom_command('scripts', data=data, timeout=timeout)


    def enable_triggers(self, timeout, **kwargs) -> NoReturn:
        """
        Start the triggers
        """

        self.execute_command(
            "enable_triggers",
            node_path = None,
            raise_on_fail = True,
            force = False,
            timeout = timeout
        )

    def disable_triggers(self, timeout:int, force:bool, **kwargs) -> NoReturn:
        """
        Stop the triggers
        """
        self.execute_command(
            "disable_triggers",
            node_path = None,
            raise_on_fail = True,
            force = force,
            timeout = timeout,
        )

    def drain_dataflow(self, timeout:int, force:bool, message:str, **kwargs) -> NoReturn:
        """
        Stop the triggers
        """

        if not force:
            canexec = self.topnode.can_execute("drain_dataflow")
            if canexec != CanExecuteReturnVal.CanExecute:
                self.log.error(f'Cannot execute drain_dataflow, reason: {str(canexec)}')
                self.return_code = self.topnode.return_code
                return

        if message != "":
            self.log.info(f"Adding the message:\n--------\n{message}\n--------\nto the logbook")
            
        try:
            self.logbook.message_on_stop()
        except Exception as e:
            self.log.error(f"Writing to the {self.logbook_type} logbook unsuccessful\nError text:\n{str(e)}")

        if self.cfgsvr:
            self.cfgsvr.save_on_stop(self.runs[-1].run_number)

        self.execute_command("drain_dataflow", node_path=None, raise_on_fail=True, timeout=timeout, force=force)
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


    def change_rate(self, trigger_rate:float, timeout) -> NoReturn:
        """
        Change the trigger interval ticks
        """
        trigger_data = rccmd.ChangeRateParams(
            trigger_rate = trigger_rate,
        ).pod() # quick schema check


        self.execute_custom_command(
            "change_rate",
            data = trigger_data,
            timeout = timeout
        )
        if self.runs:
            self.runs[-1].trigger_rate = trigger_rate


    def exclude(self, node_path, timeout, resource_name) -> NoReturn:

        canexec = node_path.can_execute_custom_or_expert(
            command = "exclude",
            quiet = False,
            only_included = False,
            check_dead = False,
            check_inerror = False,
        )
        if canexec != CanExecuteReturnVal.CanExecute:
            self.log.error(f'Cannot execute exclude, reason: {str(canexec)}')
            self.return_code = node_path.return_code
            return

        ret = node_path.exclude()
        if ret != 0:
            return

        self.execute_custom_command(
            "exclude",
            data = {'resource_name': resource_name if resource_name else node_path.name},
            timeout = timeout,
            node_path = None,
            only_included = False,
            check_dead = False,
            check_inerror = False,
        )

        self.topnode.resolve_error()



    def include(self, node_path, timeout, resource_name) -> NoReturn:

        canexec = node_path.can_execute_custom_or_expert(
            command = "include",
            quiet = False,
            only_included = False,
            check_dead = False,
            check_inerror = False,
        )
        if canexec != CanExecuteReturnVal.CanExecute:
            self.log.error(f'Cannot execute include, reason: {str(canexec)}')
            self.return_code = node_path.return_code
            return

        ret = node_path.include()
        if ret != 0:
            return

        self.execute_custom_command(
            "include",
            data = {'resource_name': resource_name if resource_name else node_paht.name},
            timeout = timeout,
            node_path = None,
            only_included = False,
            check_dead = False,
            check_inerror = False,
        )

        self.topnode.resolve_error()
