import logging
import time
import json
import os
from anytree import AnyNode, RenderTree, PreOrderIter
from rich.console import Console
from rich.style import Style
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text
from .sshpm import SSHProcessManager
from .topcfgmgr import TopLevelConfigManager
from .cfgsvr import ConfigSaver
from .appctrl import AppSupervisor, ResponseListener, ResponseTimeout, NoResponse
from .runmgr import RunNumberDBManager, SimpleRunNumberManager
from .credmgr import credentials

from rich.traceback import Traceback

from datetime import datetime

from typing import Union, NoReturn

def search_tree(path:str, from_node:AnyNode):
    if path == "/" or path == "/root":
        return [from_node]
    
    results = []
    for node in PreOrderIter(from_node):
        this_path = ""
        for parent in node.path:
            this_path += "/"+parent.id
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
            if hasattr(node, "is_app") and node.is_app:
                sup = node.app_supervisor
                alive = sup.desc.proc.is_alive()
                ping  = sup.commander.ping()
                last_cmd_failed = (sup.last_sent_command != sup.last_ok_command)
                table.add_row(
                    pre+node.id, 
                    sup.desc.host,
                    str(alive),
                    str(ping),
                    Text(str(sup.last_sent_command), style=('bold red' if last_cmd_failed else '')),
                    str(sup.last_ok_command)
                )
                
            else:
                table.add_row(pre+node.id)
                
                
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
        :param      sequence:       The sequence
        :type       sequence:       list
        :param      raise_on_fail:  Raise an exception if any application fails
        :type       raise_on_fail:  bool
        """
        
        nodes = search_tree(path, self.apps)
        
        ok, failed = {}, {}
        if not nodes:
            self.log.warning(f"No applications defined to send '{cmd}' to.")
            self.return_code = 10
            return ok, failed

        for rootnode in nodes:
            for node in PreOrderIter(rootnode):
                if hasattr(node, "is_subsystem") and node.is_subsystem:
                    print(f"Sending {cmd} to {node.id}")
                    
                    sequence = getattr(node.config, cmd+'_order', None)
                    if cfg_method:
                        f=getattr(node.config,cfg_method)
                        data = f(overwrite_data)
                    else:
                        data = getattr(node.config, cmd)
                    
                    
                    appset = list(node.children)
                    print(f"sequence? {sequence}")
                    if not sequence:
                        # Loop over data keys if no sequence is specified or all apps, if data is empty
                        
                        for n in appset:
                            print(f"Sending {cmd} to {n.id}:"+str(hasattr(n,"app_supervisor")))
                            n.app_supervisor.send_command(cmd, data[n.id] if data else {}, state_entry, state_exit)

                        start = datetime.now()

                        while(appset):
                            done = []
                            for n in appset:
                                try:
                                    r = n.app_supervisor.check_response()
                                except NoResponse:
                                    continue
                                # except AppCommander.ResponseTimeout 
                                # failed[n] = {}
                                done += [n]
                    
                                (ok if r['success'] else failed)[n.id] = r

                            for d in done:
                                appset.remove(d)

                            now = datetime.now()
                            elapsed = (now - start).total_seconds()

                            if elapsed > self.timeout:
                                raise RuntimeError("Send multicommand failed")

                            time.sleep(0.1)
                            self.log.info("tic toc")

                    else:
                        # There probably is a way to do that in a much nicer, pythonesque, way
                        for n in sequence:
                            for child_node in appset:
                                if n == child_node.id:
                                    r = child_node.app_supervisor.send_command_and_wait(cmd, data[n] if data else {},
                                                                                        state_entry, state_exit, self.timeout)
                            (ok if r['success'] else failed)[n] = r

        if raise_on_fail and failed:
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
        for node in PreOrderIter(self.apps):
            if node.is_subsystem:
                self.log.debug(str(node.config.boot))

                try:
                    node.pm = SSHProcessManager(self.console)
                    node.pm.boot(node.config.boot)
                except Exception as e:
                    self.console.print_exception()
                    self.return_code = 11
                    return
                
                node.listener = ResponseListener(node.config.boot["response_listener"]["port"])
                children = [ AnyNode(id=n, is_app = True, is_subsystem = False,
                                     app_supervisor=AppSupervisor(self.console, d, node.listener))
                             for n,d in node.pm.apps.items() ]
                node.children = children


    def terminate(self) -> NoReturn:
        for node in PreOrderIter(self.apps):
            if hasattr(node, "is_app") and node.is_app:
                node.app_supervisor.terminate()
                if node.parent.listener:
                    node.parent.listener.unregister(node.id)
                node.parent = None

        for node in PreOrderIter(self.apps):
            if hasattr(node, "is_subsystem") and node.is_subsystem:
                if hasattr(node, "listener") and node.listener:
                    node.listener.terminate()
                if hasattr(node, "pm") and node.pm:
                    node.pm.terminate()
                del node


    def ls(self) -> NoReturn:
        self.console.print("Legend:")
        self.console.print(" - [yellow]subsystems[/yellow]")
        self.console.print(" - [red]applications[/red]\n")

        for pre, _, node in RenderTree(self.apps):
            if hasattr(node, "is_subsystem") and node.is_subsystem:
                self.console.print(f"{pre}[yellow]{node.id}[/yellow]")
            elif hasattr(node, "is_app") and node.is_app:
                self.console.print(f"{pre}[red]{node.id}[/red]")
            else:
                self.console.print(f"{pre}{node.id}")


    def init(self, path:str) -> NoReturn:
        """
        Initializes the applications.
        """
        # def send_to_tree(self, path: str, cmd: str, data: dict,
        #              state_entry: str, state_exit: str, raise_on_fail: bool=False):

        ok, failed = self.send_to_tree(path, 'init', None, 'NONE', 'INITIAL', raise_on_fail=True)


    def conf(self, path:str) -> NoReturn:
        """
        Sends configure command to the applications.
        """
        ok, failed = self.send_to_tree(path, 'conf', None, 'INITIAL', 'CONFIGURED', raise_on_fail=True)


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

        # start_data = self.cfg.runtime_start(runtime_start_data)
        # cfg_save_dir = self.cfgsvr.save_on_start(start_data, self.run)

        # app_seq = getattr(self.cfg, 'start_order', None)
        # ok, failed = self.send_many('start', start_data, 'CONFIGURED', 'RUNNING', sequence=app_seq, raise_on_fail=True)
        ok, failed = self.send_to_tree("/", 'start', runtime_start_data, 'CONFIGURED', 'RUNNING', raise_on_fail=True, cfg_method="runtime_start")
        self.console.log(f"[bold magenta]Started run #{self.run}, saving run data in [/bold magenta]")
        # self.console.log(f"[bold magenta]Started run #{self.run}, saving run data in {cfg_save_dir}[/bold magenta]")


    def stop(self) -> NoReturn:
        """
        Sends stop command
        """

        # app_seq = getattr(self.cfg, 'stop_order', None)
        ok, failed = self.send_to_tree("/", 'stop', None, 'RUNNING', 'CONFIGURED', raise_on_fail=True)
        # ok, failed = self.send_many('stop', self.cfg.stop, 'RUNNING', 'CONFIGURED', sequence=app_seq, raise_on_fail=True)
        self.console.log(f"[bold magenta]Stopped run #{self.run}[/bold magenta]")


    def pause(self, path:str) -> NoReturn:
        """
        Sends pause command
        """
        # app_seq = getattr(self.cfg, 'pause_order', None)
        # ok, failed = self.send_many('pause', self.cfg.pause, 'RUNNING', 'RUNNING', app_seq, raise_on_fail=True)
        ok, failed = self.send_to_tree(path, 'pause', None, 'RUNNING', 'RUNNING', raise_on_fail=True)


    def resume(self, path:str, trigger_interval_ticks: Union[int, None]) -> NoReturn:
        """
        Sends resume command
        
        :param      trigger_interval_ticks:  The trigger interval ticks
        :type       trigger_interval_ticks:  int
        """
        runtime_resume_data = {}

        if not trigger_interval_ticks is None:
            runtime_resume_data["trigger_interval_ticks"] = trigger_interval_ticks

        # resume_data = self.cfg.runtime_resume(runtime_resume_data)
        # self.cfgsvr.save_on_resume(resume_data)

        # app_seq = getattr(self.cfg, 'resume_order', None)
        ok, failed = self.send_to_tree(path, 'resume', runtime_resume_data, 'RUNNING', 'RUNNING', raise_on_fail=True, cfg_method="runtime_resume")
        ##ok, failed = self.send_to_tree("/", 'start', runtime_start_data, 'CONFIGURED', 'RUNNING', raise_on_fail=True, cfg_method="runtime_start")
        # ok, failed = self.send_many('resume', resume_data, 'RUNNING', 'RUNNING', sequence=app_seq, raise_on_fail=True)


    def scrap(self, path:str) -> NoReturn:
        """
        Send scrap command
        """
        # app_seq = getattr(self.cfg, 'scrap_order', None)
        # ok, failed = self.send_many('scrap', self.cfg.scrap, 'CONFIGURED', 'INITIAL', sequence=app_seq, raise_on_fail=True)
        ok, failed = self.send_to_tree(path, 'scrap', None, 'CONFIGURED', 'INITIAL', raise_on_fail=True)
