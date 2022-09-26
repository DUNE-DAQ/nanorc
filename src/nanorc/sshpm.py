import os
import socket
import copy as cp
import sh
import sys
import time
import atexit
import signal
import threading
import queue
from datetime import datetime
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
        if type(line) != str:
            return

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

    def __init__(self, console: Console, log_path, ssh_conf):
        super(SSHProcessManager, self).__init__()
        self.console = console
        self.log = logging.getLogger(__name__)
        self.apps = {}
        self.watchers = []
        self.event_queue = queue.Queue()
        self.ssh_conf = ssh_conf
        self.log_path = log_path
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

    def execute_script(self, script_data):
        env_vars = script_data["env"]
        cmd =';'.join([ f"export {n}=\"{v}\"" for n,v in env_vars.items()])
        cmd += ";"+"; ".join(script_data['cmd'])
        hosts = set(self.boot_info["hosts"].values())
        for host in hosts:
            self.log.info(f'Executing {script_data["cmd"]} on {host}.')
            ssh_args = [host, "-tt", "-o StrictHostKeyChecking=no"] + [cmd]
            proc = sh.ssh(ssh_args)
            self.log.info(proc)

    def boot(self, boot_info, conf_loc, timeout):

        if self.apps:
            raise RuntimeError(
                f"ERROR: apps have already been booted {' '.join(self.apps.keys())}. Terminate them all before booting a new set."
            )

        # Add a check for env and apps in boot_info keys
        self.boot_info = boot_info
        apps = boot_info["apps"]
        hosts = boot_info["hosts"]
        rte_script = boot_info.get('rte_script')
        env_vars = boot_info["env"]

        if rte_script:
            self.log.info(f'Using the Runtime environment script "{rte_script}"')

        for app_name, app_conf in apps.items():

            host = hosts[app_conf["host"]]
            env_formatter = {
                "APP_HOST": host,
                "DUNEDAQ_PARTITION": env_vars['DUNEDAQ_PARTITION'],
                "APP_NAME": app_name,
                "APP_PORT": app_conf["port"],
                "APP_WD": os.getcwd(),
                "CONF_LOC": conf_loc,
            }

            exec_vars_cp = cp.deepcopy(boot_info['exec'][app_conf['exec']]['env'])
            exec_vars = {}

            for k,v in exec_vars_cp.items():
                exec_vars[k]=v.format(**env_formatter)

            app_vars = {}
            app_vars.update(env_vars)
            app_vars.update(exec_vars)
            env_formatter.update(app_vars)
            args = " ".join([a.format(**env_formatter) for a in boot_info['exec'][app_conf['exec']]['args']])

            log_file = f'log_{app_name}_{app_conf["port"]}.txt'
            env_var = [f'export {n}=\"{v}\"' for n, v in app_vars.items()]
            cmd=';'.join(
                [f"cd {env_formatter['APP_WD']}"] +
                [boot_info['exec'][app_conf['exec']]['cmd']+" "+args]
            )

            if rte_script:
                cmd = ';'.join(env_var)+f';source {rte_script};{cmd}'
                
            else:
                cmd = ';'.join(env_var)+';'+cmd

            if self.log_path:
                now = datetime.now() # current date and time
                date_time = now.strftime("%Y-%m-%d_%H:%M:%S")
                log_file_localhost = f'log_{date_time}_{app_name}_{app_conf["port"]}.txt'
                cmd = "{ "+cmd+"; } &> "+ self.log_path+"/"+log_file_localhost

            ssh_args = [host, "-tt", "-o StrictHostKeyChecking=no"]
            # if not self.can_use_kerb:
            ssh_args += self.ssh_conf

            ssh_test_args = ssh_args+['echo "Knock knock, tricks or treats!"']

            try:
                test_proc = sh.ssh(ssh_test_args)
            except Exception as e:
                self.log.error(f'I cannot ssh to {host}:')
                self.log.error(f'ssh {" ".join(ssh_test_args)}')
                raise e

            ssh_args += [cmd]

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
                # _preexec_fn=on_parent_exit(signal.SIGTERM),
            )
            self.watch(name, proc)
            desc.proc = proc

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

                alive, failed, resp = self.check_apps()

                for a, t in apps_tasks.items():
                    if a in resp:
                        progress.update(t, completed=1)

                progress.update(total, completed=len(resp))

                if set.union(set(resp), set(failed.keys())) == set(self.apps.keys()):
                    progress.update(waiting, visible=False)
                    break
                time.sleep(1)

    def check_apps(self):
        responding = []
        alive = []
        failed = {}

        for name, desc in self.apps.items():

            if desc.proc is None:
                # Should I throw an error here?
                continue

            # Process status
            if not desc.proc.is_alive():
                try:
                    exit_code = desc.proc.exit_code
                except sh.ErrorReturnCode as e:
                    exit_code = e.exit_code
                failed[name] = exit_code
            else:
                alive += [name]

                # Command port status
                if is_port_open(
                        desc.host, desc.conf["port"]
                    ):
                    responding += [name]

        return alive, failed, responding

    def status_apps(self):
        table = Table(title="Apps (process)")
        table.add_column("name", style="magenta")
        table.add_column("is alive", style="magenta")
        table.add_column("open port", style="magenta")
        table.add_column("host", style="magenta")

        alive, failed, resp = self.check_apps()

        for app, desc in self.apps.items():
            table.add_row(app, "alive" if (app in alive) else f"dead[{failed[app]}]", str(app in resp), desc.host)
        self.console.print(table)


    def terminate(self):
        for name, desc in self.apps.items():
            if desc.proc is not None and desc.proc.is_alive():
                try:
                    desc.proc.terminate()
                    while desc.proc.is_alive():
                        time.sleep(0.1)
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
