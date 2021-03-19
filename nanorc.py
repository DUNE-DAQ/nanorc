#!/usr/bin/env python3

import os
import sh
import sys
import time
import json
import cmd
import click
import click_shell
import os.path
from rich.table import Table
from rich.console import Console
from rich.pretty import Pretty
from rich.traceback import Traceback
from rich.layout import Layout
from rich.progress import *
from rich.style import Style

from sshpm import SSHProcessManager
from cfgmgr import ConfigManager
from appctrl import AppSupervisor

class NanoContext:
    """docstring for NanoContext"""
    def __init__(self, console):
        super(NanoContext, self).__init__()
        self.console = console
        self.print_traceback = False
        self.rc = None
        
        
class NanoRC:
    """A Shonky RC for DUNE DAQ"""

    def __init__(self, console: Console, cfg_dir: str):
        super(NanoRC, self).__init__()     
        self.console = console
        self.cfg = ConfigManager(cfg_dir)

        self.pm = SSHProcessManager(console)
        self.apps = None


    def status(self) -> None:

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
            alive = sup.handle.proc.is_alive()
            ping = sup.commander.ping()
            last_cmd_failed = (sup.last_sent_command != sup.last_ok_command)
            table.add_row(
                app, 
                sup.handle.host,
                str(alive),
                str(ping),
                Text(str(sup.last_sent_command), style=('bold red' if last_cmd_failed else '')),
                sup.last_ok_command
            )
        self.console.print(table)


    def send_many(self, cmd: str, data: dict, state_entry: str, state_exit: str, sequence: list = None, raise_on_fail: bool =False):
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

        # Loop over data keys if no sequence is specified or all apps, if data is emoty
        if not sequence:
            sequence = data.keys() if data else self.apps.keys()

        ok, failed = {}, {}
        for n in sequence:
            r = self.apps[n].send_command(cmd, data[n] if data else {}, state_entry, state_exit)
            (ok if r['success'] else failed)[n] = r
        if raise_on_fail and failed:
            raise RuntimeError(f"ERROR: Failed to execute '{cmd}' on {', '.join(failed.keys())} applications")
        return ok, failed


    def boot(self) -> None:
        
        self.console.log(Pretty(self.cfg.boot))

        try:
            self.pm.boot(self.cfg.boot)
        except Exception as e:
            self.console.log(Traceback())
            return

        self.apps = { n:AppSupervisor(self.console, h) for n,h in self.pm.apps.items() }


    def terminate(self):
        if self.apps:
            for s in self.apps.values():
                s.terminate()
            self.apps = None
        self.pm.terminate()


    def init(self):
        """
        Initializes the applications.
        """
        ok, failed = self.send_many('init', self.cfg.init, 'NONE', 'INITIAL', raise_on_fail=True)

    def conf(self):
        """
        Sends configure command to the applications.
        """
        ok, failed = self.send_many('conf', self.cfg.conf, 'INITIAL', 'CONFIGURED', raise_on_fail=True)

    def start(self, run: int, disable_data_storage: bool, trigger_interval_ticks: int):
        """
        Sends start command to the applications
        
        :param      run:                     The run
        :type       run:                     int
        :param      disable_data_storage:    The disable data storage
        :type       disable_data_storage:    bool
        :param      trigger_interval_ticks:  The trigger interval ticks
        :type       trigger_interval_ticks:  int
        """
        runtime_start_data = {
                "disable_data_storage": disable_data_storage,
                "run": run,
                "trigger_interval_ticks": trigger_interval_ticks
            }

        start_data = self.cfg.runtime_start(runtime_start_data)
        app_seq = getattr(self.cfg, 'start_order', None)
        ok, failed = self.send_many('start', start_data, 'CONFIGURED', 'RUNNING', sequence=app_seq, raise_on_fail=True)


    def stop(self):
        """
        Sends stop command
        """

        app_seq = getattr(self.cfg, 'stop_order', None)
        ok, failed = self.send_many('stop', self.cfg.stop, 'RUNNING', 'CONFIGURED', sequence=app_seq, raise_on_fail=True)


    def pause(self):
        """
        Sends pause command
        """
        app_seq = getattr(self.cfg, 'pause_order', None)
        ok, failed = self.send_many('pause', None, 'RUNNING', 'RUNNING', app_seq, raise_on_fail=True)


    def resume(self, trigger_interval_ticks: int):
        """
        Sends resume command
        
        :param      trigger_interval_ticks:  The trigger interval ticks
        :type       trigger_interval_ticks:  int
        """
        runtime_resume_data = {
            "trigger_interval_ticks": trigger_interval_ticks
        }

        resume_data = self.cfg.runtime_resume(runtime_resume_data)

        app_seq = getattr(self.cfg, 'resume_order', None)
        ok, failed = self.send_many('resume', resume_data, 'RUNNING', 'RUNNING', sequence=app_seq, raise_on_fail=True)


    def scrap(self):
        """
        Send scrap command
        """
        ok, failed = self.send_many('scrap', None, 'CONFIGURED', 'INITIAL', raise_on_fail=True)



# ------------------------------------------------------------------------------
# Add -h as default help option
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
@click_shell.shell(prompt='shonky rc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.pass_obj
@click.pass_context
@click.argument('cfg_dir', type=click.Path(exists=True))
def cli(ctx, obj, traceback, cfg_dir):

    obj.print_traceback = traceback

    grid = Table(title='Shonky RC', show_header=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky RC to run DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row("Handle wiht care!")

    console.print(grid)

    try:
        rc = NanoRC(console, cfg_dir)
    except Exception as e:
        obj.console.log(Traceback())
        raise click.Abort()
        
    def cleanup_rc():
        console.log("Terminating RC before exiting")
        rc.terminate()

    ctx.call_on_close(cleanup_rc)    
    obj.rc = rc


@cli.command('status')
@click.pass_obj
def status(obj):
    obj.rc.status()

@cli.command('boot')
@click.pass_obj
def boot(obj):
    obj.rc.boot()
    obj.rc.status()

@cli.command('init')
@click.pass_obj
def init(obj):
    obj.rc.init()
    obj.rc.status()

@cli.command('conf')
@click.pass_obj
def conf(obj):
    obj.rc.conf()
    obj.rc.status()

@cli.command('start')
@click.argument('run', type=int)
@click.option('--disable-data-storage/--enable-data-storage', type=bool, default=False, help='Toggle data storage')
# @click.option('--trigger-interval-ticks', type=int, default=50000000, help='Trigger separation in ticks')
@click.pass_obj
def start(obj, run, disable_data_storage):
    """
    Starts the run
    """
    obj.rc.start(run, disable_data_storage, 50000000) # FIXME: how?
    obj.rc.status()

@cli.command('stop')
@click.pass_obj
def stop(obj):
    obj.rc.stop()
    obj.rc.status()

@cli.command('pause')
@click.pass_obj
def pause(obj):
    obj.rc.pause()
    obj.rc.status()

@cli.command('resume')
@click.option('--trigger-interval-ticks', type=int, default=50000000, help='Trigger separation in ticks')
@click.pass_obj
def resume(obj, trigger_interval_ticks):
    obj.rc.resume(trigger_interval_ticks)
    obj.rc.status()

@cli.command('scrap')
@click.pass_obj
def scrap(obj):
    obj.rc.scrap()
    obj.rc.status()

@cli.command('terminate')
@click.pass_obj
def terminate(obj):
    obj.rc.terminate()
    obj.rc.status()


@cli.command('wait')
@click.pass_obj
@click.argument('seconds', type=int)
def wait(obj, seconds):

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=obj.console,
    ) as progress:
        waiting = progress.add_task("[yellow]waiting", total=seconds)

        for _ in range(seconds):
            progress.update(waiting, advance=1)

            time.sleep(1)


if __name__ == '__main__':

    console = Console()
    obj = NanoContext(console)

    try:
        cli(obj=obj, show_default=True)
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        if not obj.print_traceback:
            console.log(e)
        else:
            console.print_exception()






