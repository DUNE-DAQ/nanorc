import logging
import time
import json
import os
from rich.console import Console
from rich.style import Style
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text
from .sshpm import SSHProcessManager
from .cfgmgr import ConfigManager
from .cfgsvr import ConfigSaver
from .appctrl import AppSupervisor, ResponseListener, ResponseTimeout, NoResponse
from .runmgr import RunNumberDBManager, SimpleRunNumberManager
from .credmgr import credentials

from rich.traceback import Traceback

from datetime import datetime


from typing import Union, NoReturn

class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, cfg_dir: str, cfg_outdir: str, dotnanorc_file: str, timeout: int):
        super(NanoRC, self).__init__()     
        self.log = logging.getLogger(self.__class__.__name__)
        self.console = console
        self.cfg = ConfigManager(cfg_dir)

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

        self.pm = SSHProcessManager(console)
        self.apps = None
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
        """

        ok, failed = {}, {}
        if not self.apps:
            self.log.warning(f"No applications defined to send '{cmd}' to. Has 'boot' been executed?")
            self.return_code = 10
            return ok, failed

        if not sequence:
            # Loop over data keys if no sequence is specified or all apps, if data is empty
            appset = list(data.keys() if data else self.apps.keys())
            self.log.info(f"Sending {cmd} to {appset}")

            for n in appset:
                self.apps[n].send_command(cmd, data[n] if data else {}, state_entry, state_exit)

            start = datetime.now()

            while(appset):

                done = []
                for n in appset:
                    try:
                        r = self.apps[n].check_response()
                    except NoResponse:
                        continue
                    # except AppCommander.ResponseTimeout 
                        # failed[n] = {}
                    done += [n]
                    
                    (ok if r['success'] else failed)[n] = r

                for d in done:
                    appset.remove(d)

                now = datetime.now()
                elapsed = (now - start).total_seconds()

                if elapsed > self.timeout:
                    raise RuntimeError("Send multicommand failed")

                time.sleep(0.1)
                self.log.info("tic toc")

        else:
            for n in sequence:
                r = self.apps[n].send_command_and_wait(cmd, data[n] if data else {}, state_entry, state_exit, self.timeout)
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
        
        self.log.debug(str(self.cfg.boot))

        try:
            self.pm.boot(self.cfg.boot)
        except Exception as e:
            self.console.print_exception()
            self.return_code = 11
            return

        self.listener = ResponseListener(self.cfg.boot["response_listener"]["port"])
        self.apps = { n:AppSupervisor(self.console, d, self.listener) for n,d in self.pm.apps.items() }


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
        self.pm.terminate()


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


    def start(self, disable_data_storage: bool) -> NoReturn:
        """
        Sends start command to the applications
        
        Args:
            run (int): Description
            disable_data_storage (bool): Description
        """

        self.run = self.rnm.get_run_number()

        runtime_start_data = {
                "disable_data_storage": disable_data_storage,
                "run": self.run,
            }

        start_data = self.cfg.runtime_start(runtime_start_data)
        cfg_save_dir = self.cfgsvr.save_on_start(start_data, self.run)

        app_seq = getattr(self.cfg, 'start_order', None)
        ok, failed = self.send_many('start', start_data, 'CONFIGURED', 'RUNNING', sequence=app_seq, raise_on_fail=True)
        self.console.log(f"[bold magenta]Started run #{self.run}, saving run data in {cfg_save_dir}[/bold magenta]")


    def stop(self) -> NoReturn:
        """
        Sends stop command
        """

        app_seq = getattr(self.cfg, 'stop_order', None)
        ok, failed = self.send_many('stop', self.cfg.stop, 'RUNNING', 'CONFIGURED', sequence=app_seq, raise_on_fail=True)
        self.console.log(f"[bold magenta]Stopped run #{self.run}[/bold magenta]")


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
        self.cfgsvr.save_on_resume(resume_data)

        app_seq = getattr(self.cfg, 'resume_order', None)
        ok, failed = self.send_many('resume', resume_data, 'RUNNING', 'RUNNING', sequence=app_seq, raise_on_fail=True)


    def scrap(self) -> NoReturn:
        """
        Send scrap command
        """
        app_seq = getattr(self.cfg, 'scrap_order', None)
        ok, failed = self.send_many('scrap', self.cfg.scrap, 'CONFIGURED', 'INITIAL', sequence=app_seq, raise_on_fail=True)
