import os
import socket
import sh
import sys
import time
import atexit
import signal
import threading
import queue
import signal
import logging
from rich.console import Console
from rich.progress import *
from rich.table import Table


# # ------------------------------------------------
# # pexpect.spawn(...,preexec_fn=on_parent_exit('SIGTERM'))
from ctypes import cdll

# Constant taken from http://linux.die.net/include/linux/prctl.h
PR_SET_PDEATHSIG = 1

class PrCtlError(Exception):
    pass


def on_parent_exit(signum):
    """
    Return a function to be run in a child process which will trigger
    SIGNAME to be sent when the parent process dies
    """
    def set_parent_exit_signal():
        # http://linux.die.net/man/2/prctl
        result = cdll['libc.so.6'].prctl(PR_SET_PDEATHSIG, signum)
        if result != 0:
            raise PrCtlError('prctl failed with error code %s' % result)
    return set_parent_exit_signal
# # ------------------------------------------------

# ---
def is_port_open(ip, port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect((ip, int(port)))
        s.shutdown(2)
        return True
    except:
        return False


# ---
def file_logger(logfile, echo=False):
    log = open(logfile, "w")

    def interact(line, stdin):
        log.write(line)
        log.flush()
        if echo:
            sys.stdout.write(line)
            sys.stdout.flush()

    return interact


class AppProcessDescriptor(object):
    """docstring for AppProcessDescriptor"""

    def __init__(self, name):
        super(AppProcessDescriptor, self).__init__()
        self.proc = None
        self.name = name
        self.logfile = None
        self.ssh_args = None
        self.host = None
        self.cmd = None
        self.conf = None

    def __str__(self):
        return str(vars(self))


class AppProcessWatcherThread(threading.Thread):
    def __init__(self, pm, app, proc):
        threading.Thread.__init__(self)
        self.pm = pm
        self.app = app
        self.proc = proc

    def run(self):

        exc = None
        try:
            self.proc.wait()
        except sh.ErrorReturnCode as e:
            exc = e

        self.pm.notify_join(self.app, self, exc)


# ---
class SSHProcessManager(object):
    """An poor's man process manager based on ssh"""

    __instances = set()

    @classmethod
    def kill_all_instances(cls):
        instances = set(cls.__instances)
        for i in instances:
            i.kill()

    def __init__(self, console: Console):
        super(SSHProcessManager, self).__init__()
        self.console = console
        self.log = logging.getLogger(__name__)
        self.apps = {}
        self.watchers = []
        self.event_queue = queue.Queue()

        # Add self to the list of instances
        self.__instances.add(self)

    def __del__(self):
        if self in self.__instances:
            self.__instances.remove(self)
        self.kill()

    def watch(self, name, proc):
        t = AppProcessWatcherThread(self, name, proc)
        t.start()

        self.watchers.append(t)

    def notify_join(self, name, watcher, exc):
        self.log.info(f"{name} process exited"+(f" with exit code {exc.exit_code}" if exc else ""))
        self.log.debug(name+str(exc))
        self.event_queue.put((name, exc))

    def boot(self, boot_info):

        if self.apps:
            raise RuntimeError(
                f"ERROR: apps have already been booted {' '.join(self.apps.keys())}. Terminate them all before booting a new set."
            )

        # Add a check for env and apps in boot_info keys

        apps = boot_info["apps"]
        hosts = boot_info["hosts"]
        env_vars = boot_info["env"]

        for app_name, app_conf in apps.items():

            host = hosts[app_conf["host"]]

            exec_vars = boot_info['exec'][app_conf['exec']]['env']

            app_vars = {}
            app_vars.update(env_vars)
            app_vars.update(exec_vars)
            app_vars.update({
                "APP_NAME": app_name,
                "APP_PORT": app_conf["port"],
                "APP_WD": os.getcwd()
                })
            cmd=';'.join([ f"export {n}=\"{v}\"" for n,v in app_vars.items()] + boot_info['exec'][app_conf['exec']]['cmd'])

            log_file = f'log_{app_name}_{app_conf["port"]}.txt'

            ssh_args = [host, "-tt", "-o StrictHostKeyChecking=no", cmd]

            desc = AppProcessDescriptor(app_name)
            desc.logfile = log_file
            desc.cmd = cmd
            desc.ssh_args = ssh_args
            desc.host = host
            desc.port = app_conf["port"]
            desc.conf = app_conf.copy()
            self.apps[app_name] = desc

        apps_running = []
        for name, desc in self.apps.items():
            if is_port_open(desc.host, desc.port):
                apps_running += [name]
        if apps_running:
            raise RuntimeError(f"ERROR: apps already running? {apps_running}")

        for name, desc in self.apps.items():
            proc = sh.ssh(
                *desc.ssh_args,
                _out=file_logger(desc.logfile),
                _bg=True,
                _bg_exc=False,
                _new_session=True,
                _preexec_fn=on_parent_exit(signal.SIGTERM),
            )
            self.watch(name, proc)
            desc.proc = proc

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
            total = progress.add_task("[yellow]# apps started", total=len(apps))
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

    def check_apps(self):
        responding = []
        alive = []
        for name, desc in self.apps.items():

            if desc.proc is not None and desc.proc.is_alive():
                alive += [name]
            if desc.proc is not None and is_port_open(
                desc.host, desc.conf["port"]
            ):
                responding += [name]
        return alive, responding

    def status_apps(self):
        table = Table(title="Apps (process")
        table.add_column("name", style="magenta")
        table.add_column("is alive", style="magenta")
        table.add_column("open port", style="magenta")
        table.add_column("host", style="magenta")

        alive, resp = self.check_apps()

        for app, desc in self.apps.items():
            table.add_row(app, str(app in alive), str(app in resp), desc.host)
        self.console.print(table)


    def terminate(self):
        for name, desc in self.apps.items():
            if desc.proc is not None and desc.proc.is_alive():
                try:
                    desc.proc.terminate()
                except OSError:
                    pass
        self.apps = {}

    def kill(self):
        for name, desc in self.apps.items():
            if desc.proc is not None and desc.proc.is_alive():
                try:
                    desc.proc.kill()
                except OSError:
                    pass
        self.apps = {}

# Cleanup before exiting
def __goodbye(*args, **kwargs):
    print("Killing all processes before exiting")
    SSHProcessManager.kill_all_instances()


# atexit.register(__goodbye)
