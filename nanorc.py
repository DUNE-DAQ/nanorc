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
from rich.progress import *

from sshpm import SSHProcessManager
from cfgmgr import ConfigManager
from appctrl import AppSupervisor

        
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
        table.add_column("last cmd", style="magenta")
        table.add_column("last succ. cmd", style="magenta")

        for app, sup in self.apps.items():
            alive = sup.handle.proc.is_alive()
            ping = sup.commander.ping()
            table.add_row(app, sup.handle.host, str(alive), str(ping),  sup.last_sent_command, sup.last_ok_command)
        self.console.print(table)

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
        # Init sent to all
        for n,s in self.apps.items():
            s.send_command('init', self.cfg.init[n], 'NONE', 'INITIAL')

    def conf(self):
        # Conf sent to all
        for n,s in self.apps.items():
            s.send_command('conf', self.cfg.conf[n], 'INITIAL', 'CONFIGURED')

    def start(self, run, disable_data_storage, trigger_interval_ticks):
        runtime_start_data = {
                "disable_data_storage": disable_data_storage,
                "run": run,
                "trigger_interval_ticks": trigger_interval_ticks
            }

        start_data = self.cfg.runtime_start(runtime_start_data)
        # Start sent to apps in pre-defined order
        for n in getattr(self.cfg, 'start_order', self.apps.keys()):
            self.apps[n].send_command('start', start_data[n], 'CONFIGURED', 'RUNNING')

    def stop(self):

        # Take order from config if defined
        for n in getattr(self.cfg, 'stop_order', self.apps.keys()):
            self.apps[n].send_command('stop', self.cfg.stop[n], 'RUNNING', 'CONFIGURED')

    def pause(self):
        # Pause sent only to some apps, what about order?
        for n in self.cfg.pause.keys():
            self.apps[n].send_command('pause', {}, 'RUNNING', 'RUNNING')

    def resume(self, trigger_interval_ticks):
        runtime_resume_data = {
            "trigger_interval_ticks": trigger_interval_ticks
        }

        resume_data = self.cfg.runtime_resume(runtime_resume_data)

        # Resume sent only to some apps, what about order?
        for n in resume_data.keys():
            self.apps[n].send_command('resume', resume_data[n], 'RUNNING', 'RUNNING')

    def scrap(self):
        # Scrap sent to all
        for n,s in self.apps.items():
            s.send_command('scrap', {}, 'CONFIGURED', 'INITIAL')



# ------------------------------------------------------------------------------
# Add -h as default help option
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
@click_shell.shell(prompt='shonky rc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.pass_context
@click.argument('cfg_dir', type=click.Path(exists=True))
def cli(ctx, cfg_dir):

    console = Console()
    grid = Table(title='Shonky RC', show_header=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky RC to run DUNE-DAQ applications.")
    grid.add_row("Give a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row("Use it wisely!")

    console.print(grid)
    try:
        rc = NanoRC(console, cfg_dir)
    except Exception as e:
        console.log(Traceback())
        raise click.Abort()
    ctx.obj = rc
    
    def cleanup_rc():
        console.log("Terminating RC before exiting")
        rc.terminate()

    ctx.call_on_close(cleanup_rc)    

@cli.command('status')
@click.pass_obj
def status(rc):
    rc.status()

@cli.command('boot')
@click.pass_obj
def boot(rc):
    rc.boot()
    rc.status()

@cli.command('init')
@click.pass_obj
def init(rc):
    rc.init()
    rc.status()

@cli.command('conf')
@click.pass_obj
def conf(rc):
    rc.conf()
    rc.status()

@cli.command('start')
@click.argument('run', type=int)
@click.option('--disable-data-storage/--enable-data-storage', type=bool, default=False, help='Toggle data storage')
# @click.option('--trigger-interval-ticks', type=int, default=50000000, help='Trigger separation in ticks')
@click.pass_obj
def start(rc, run, disable_data_storage):
    """
    Starts the run
    """
    rc.start(run, disable_data_storage, 50000000) # FIXME: how?
    rc.status()

@cli.command('stop')
@click.pass_obj
def stop(rc):
    rc.stop()
    rc.status()

@cli.command('pause')
@click.pass_obj
def pause(rc):
    rc.pause()
    rc.status()

@cli.command('resume')
@click.option('--trigger-interval-ticks', type=int, default=50000000, help='Trigger separation in ticks')
@click.pass_obj
def resume(rc, trigger_interval_ticks):
    rc.resume(trigger_interval_ticks)
    rc.status()

@cli.command('scrap')
@click.pass_obj
def scrap(rc):
    rc.scrap()
    rc.status()

@cli.command('terminate')
@click.pass_obj
def terminate(rc):
    rc.terminate()
    rc.status()


@cli.command('wait')
@click.pass_obj
@click.argument('seconds', type=int)
def wait(rc, seconds):

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        TimeElapsedColumn(),
        console=rc.console,
    ) as progress:
        waiting = progress.add_task("[yellow]waiting", total=seconds)

        for _ in range(seconds):
            progress.update(waiting, advance=1)

            time.sleep(1)


if __name__ == '__main__':

    cli(show_default=True)





