import logging
import time
from rich.console import Console
from rich.style import Style
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text
from .sshpm import SSHProcessManager
from .k8spm import K8SProcessManager
from .cfgmgr import ConfigManager
from .appctrl import AppSupervisor, ResponseListener
from rich.traceback import Traceback
from rich.progress import *
from rich.table import Table

from typing import Union, NoReturn

class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, cfg_dir: str, timeout:int):
        super(NanoRC, self).__init__()     
        self.log = logging.getLogger(self.__class__.__name__)
        self.console = console
        self.cfg = ConfigManager(cfg_dir)
        self.timeout = timeout

        # self.pm = SSHProcessManager(console)
        self.k8spm = K8SProcessManager(console)
        self.apps = None
        self.listener = None

    def status(self) -> NoReturn:
        """
        Displays the status of the applications
    

        Returns:
            NoReturn: nothing
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

        for app, sup in self.apps.items():
            alive = sup.desc.proc.is_alive()
            ping = sup.commander.ping()
            last_cmd_failed = (sup.last_sent_command != sup.last_ok_command)
            table.add_row(
                app, 
                sup.desc.host,
                str(alive),
                str(ping),
                Text(str(sup.last_sent_command), style=('bold red' if last_cmd_failed else '')),
                str(sup.last_ok_command)
            )
        self.console.print(table)


    def send_many(self, cmd: str, data: dict, state_entry: str, state_exit: str, sequence: list = None, raise_on_fail: bool=False):
        """
        Sends many commands to all applications
        
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
        
        Args:
            cmd (str): Command name
            data (dict): Command data
            state_entry (str): Initial state before the command
            state_exit (str): Sinal state after the command
            sequence (list, optional): Order with which commands are sent
            raise_on_fail (bool, optional): Raise an exception if sending fails
        
        Returns:
            TYPE: Description
        
        Raises:
            RuntimeError: Description
        """

        ok, failed = {}, {}
        if not self.apps:
            self.log.warning(f"No applications defined to send '{cmd}' to. Has 'boot' been executed?")
            return ok, failed

        # Loop over data keys if no sequence is specified or all apps, if data is empty
        if not sequence:
            sequence = data.keys() if data else self.apps.keys()
        for n in sequence:
            r = self.apps[n].send_command(cmd, data[n] if data else {}, state_entry, state_exit, self.timeout)
            (ok if r['success'] else failed)[n] = r
        if raise_on_fail and failed:
            self.log.error(f"ERROR: Failed to execute '{cmd}' on {', '.join(failed.keys())} applications")
            for a,r in failed.items():
                self.log.error(f"{a}: {r}")
            raise RuntimeError(f"ERROR: Failed to execute '{cmd}' on {', '.join(failed.keys())} applications")
        return ok, failed


    def boot(self, partition: str) -> NoReturn:
        """
        Boots applications
        """
        
        self.log.debug(str(self.cfg.boot))

        try:
            self.k8spm.boot(self.cfg.boot, partition)
        except Exception as e:
            self.console.print_exception()
            return

        self.listener = ResponseListener(self.cfg.boot["response_listener"]["port"])

        response_host = f'nanorc.{self.k8spm.partition}'
        proxy = ('127.0.0.1', 31000)

        self.apps = { n:AppSupervisor(self.console, d, self.listener, response_host, proxy) for n,d in self.k8spm.apps.items() }

        # TODO: move (some of) this loop into k8spm?
        timeout = 30
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            total = progress.add_task("[yellow]# apps started", total=len(self.apps))
            apps_tasks = {
                a: progress.add_task(f"[blue]{a}", total=1) for a in self.apps
            }
            waiting = progress.add_task("[yellow]timeout", total=timeout)

            for _ in range(timeout):
                progress.update(waiting, advance=1)

                alive, resp = self.check_apps()
                # progress.log(alive, resp)
                for a, t in apps_tasks.items():
                    if a in resp:
                        progress.update(t, completed=1)
                progress.update(total, completed=len(resp))
                if resp == list(self.apps.keys()):
                    progress.update(waiting, visible=False)
                    break
                time.sleep(1)

    # ---
    def check_apps(self):
        responding = []
        alive = []
        for name, sup in self.apps.items():

            desc = sup.desc

            if desc.proc is not None and desc.proc.is_alive():
                alive += [name]
            if desc.proc is not None and sup.commander.ping():
                responding += [name]
        return alive, responding


    def terminate(self) -> NoReturn:
        if self.apps:
            for n,s in self.apps.items():
                s.terminate()
                if self.listener:
                    self.listener.unregister(n)
            self.apps = None
        if self.listener:
            self.listener.terminate()

        self.log.warning("Terminating")
        self.k8spm.terminate()
    


    def init(self) -> NoReturn:
        """
        Initializes the applications.
        """
        ok, failed = self.send_many('init', self.cfg.init, 'NONE', 'INITIAL', raise_on_fail=True)

    def conf(self) -> NoReturn:
        """
        Sends configure command to the applications.
        """
        app_seq = getattr(self.cfg, 'conf_order', None)
        ok, failed = self.send_many('conf', self.cfg.conf, 'INITIAL', 'CONFIGURED', sequence=app_seq, raise_on_fail=True)

    def start(self, run: int, disable_data_storage: bool) -> NoReturn:
        """
        Sends start command to the applications
        
        Args:
            run (int): Run number
            disable_data_storage (bool): disable storage of data
        """
        runtime_start_data = {
                "disable_data_storage": disable_data_storage,
                "run": run,
            }

        # TODO: delete 
        # if not trigger_interval_ticks is None:
        #     runtime_start_data["trigger_interval_ticks"] = trigger_interval_ticks

        start_data = self.cfg.runtime_start(runtime_start_data)
        app_seq = getattr(self.cfg, 'start_order', None)
        ok, failed = self.send_many('start', start_data, 'CONFIGURED', 'RUNNING', sequence=app_seq, raise_on_fail=True)


    def stop(self) -> NoReturn:
        """
        Sends stop command
        """

        app_seq = getattr(self.cfg, 'stop_order', None)
        ok, failed = self.send_many('stop', self.cfg.stop, 'RUNNING', 'CONFIGURED', sequence=app_seq, raise_on_fail=True)


    def pause(self) -> NoReturn:
        """
        Sends pause command
        """
        app_seq = getattr(self.cfg, 'pause_order', None)
        ok, failed = self.send_many('pause', self.cfg.pause, 'RUNNING', 'RUNNING', app_seq, raise_on_fail=True)


    def resume(self, trigger_interval_ticks: Union[int, None]) -> NoReturn:
        """
        Sends resume command
        
        :param      trigger_interval_ticks:  The trigger interval ticks
        :type       trigger_interval_ticks:  int
        """
        runtime_resume_data = {}

        if not trigger_interval_ticks is None:
            runtime_resume_data["trigger_interval_ticks"] = trigger_interval_ticks

        resume_data = self.cfg.runtime_resume(runtime_resume_data)

        app_seq = getattr(self.cfg, 'resume_order', None)
        ok, failed = self.send_many('resume', resume_data, 'RUNNING', 'RUNNING', sequence=app_seq, raise_on_fail=True)


    def scrap(self) -> NoReturn:
        """
        Send scrap command
        """
        app_seq = getattr(self.cfg, 'scrap_order', None)
        ok, failed = self.send_many('scrap', self.cfg.scrap, 'CONFIGURED', 'INITIAL', sequence=app_seq, raise_on_fail=True)
