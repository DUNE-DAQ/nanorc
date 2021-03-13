import os
import socket
import sh
import sys
import time
import atexit
import signal
import threading
import queue
from rich.console import Console
from rich.progress import *
"""
Boot info example

{
    "env" : {
        "DBT_ROOT": "env",
        "DBT_AREA_ROOT": "env"
    },
    "apps" : {
        "stoca" : {
            "exec": "daq_application",
            "host": "localhost",
            "port": 12345
        },
        "suka": {
            "exec": "daq_application",
            "host": "localhost",
            "port": 12346
        }
    }
}
"""



# ---
def is_port_open(ip,port):
   s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   try:
      s.connect((ip, int(port)))
      s.shutdown(2)
      return True
   except:
      return False

# ---
def file_logger(logfile, echo=False):

    log = open(logfile, 'w')

    def interact(line, stdin):
        log.write(line)
        log.flush()
        if echo:
            sys.stdout.write(line)
            sys.stdout.flush()

    return interact


class AppInfo(object):
    """docstring for AppInfo"""
    def __init__(self, name):
        super(AppInfo, self).__init__()
        self.proc = None
        self.name = name
        self.logfile = None
        self.ssh_args = None
        self.host = None
        self.cmd = None
        self.conf = None

    def __str__(self):
        return str(vars(self))


class ProcWatcherThread(threading.Thread):

    def __init__(self, pm, app, proc):
        threading.Thread.__init__(self)
        self.pm = pm
        self.app = app
        self.proc = proc

    def run(self):
        try:
            self.proc.wait()
        except sh.ErrorReturnCode as e:
            self.pm.notify_error(self.app, e)


# ---
class SSHProcessManager(object):
    """An poor's man process manager based on ssh"""

    __instances = set()

    @classmethod
    def kill_all_instances(cls):
        instances = set(cls.__instances)
        for i in instances:
            i.terminate()


    def __init__(self, console: Console):
        super(SSHProcessManager, self).__init__()
        self.console = console
        self.apps = {}
        self.watchers = []
        self.event_queue = queue.Queue()
        # Add self to the list of instances
        self.__instances.add(self)

    def watch(self, name, proc):
        t = ProcWatcherThread(self, name, proc)
        t.start()

        self.watchers.append(t)

    def notify_error(self, name, exc):
        print(name, exc.exit_code)


    def spawn(self, boot_info):

        # Add a check for env and apps in boot_info keys

        apps = boot_info['apps']
        hosts = boot_info['hosts']

        env_vars = { k:(os.environ[k] if v == 'env' else v) for k,v in boot_info['env'].items() }

        for app_name, app_conf in apps.items():

            cmd_fac = f'rest://localhost:{app_conf["port"]}'
            host = hosts[app_conf["host"]]

            cmd=f'cd {env_vars["DBT_AREA_ROOT"]}; source {env_vars["DBT_ROOT"]}/dbt-setup-env.sh; dbt-setup-runtime-environment; {app_conf["exec"]} --name {app_name} -c {cmd_fac}'

            ssh_args = [
                host,
                '-tt',
                cmd
            ]

            log_file = f'log_{app_name}_{app_conf["port"]}.txt'

            info = AppInfo(app_name)
            info.logfile = log_file
            info.cmd = cmd
            info.ssh_args = ssh_args
            info.host = host
            info.conf = app_conf.copy()
            self.apps[app_name] = info


        apps_running = []
        for name, info in self.apps.items():
            if is_port_open(info.conf['host'], info.conf['port']):
                apps_running += [name]
        if apps_running:
            raise RuntimeError(f"ERROR: apps already running? {apps_running}")

        for name, info in self.apps.items():
            proc = sh.ssh(*info.ssh_args, _out=file_logger(f'log_{app_name}_{app_conf["port"]}.txt'), _bg=True, _bg_exc=False)
            self.watch(name, proc)
            info.proc = proc

       
        timeout=60
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            total = progress.add_task("[yellow]Started apps", total=len(apps))
            apps_tasks = { a:progress.add_task(f"[blue]{a}", total=1) for a in self.apps}
            waiting = progress.add_task("[yellow]Timeout", total=timeout)

            for _ in range(timeout):
                progress.update(waiting, advance=1)

                alive, resp = self.check_apps()
                # progress.log(alive, resp)
                if resp == list(self.apps.keys()):
                    progress.update(waiting, visible=False)
                    break
                for a,t in apps_tasks.items():
                    if a in resp:
                        progress.update(t, completed=1)
                progress.update(total, completed=len(resp))
                time.sleep(1)



    def check_apps(self):
        responding = []
        alive = []
        for name, info in self.apps.items():

            if info.proc.is_alive():
                alive += [name]
            if is_port_open(info.host, info.conf['port']):
                responding += [name]
        return alive, responding


    def terminate(self):

        for name, info in self.apps.items():
            if info.proc is not None and info.proc.is_alive():
                info.proc.terminate()

        self.apps = {}



# Cleanup before exiting
def __goodbye(*args, **kwargs):
    print("Killing all processes before exiting")
    SSHProcessManager.kill_all_instances()

atexit.register(__goodbye)

# 
# signal.signal(signal.SIGTERM, __goodbye)
# signal.signal(signal.SIGINT, __goodbye)
# ---