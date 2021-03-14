#!/usr/bin/env python

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

from sshpm import SSHProcessManager
from cfgmgr import ConfigManager
from appctrl import AppSupervisor

        
class NanoRC:
    """docstring for NanoRC"""
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
        table.add_column("last cmd ok", style="magenta")

        for app, sup in self.apps.items():
            alive = sup.handle.proc.is_alive()
            ping = sup.commander.ping()
            table.add_row(app, str(alive), str(ping), sup.handle.host, sup.last_sent_command, sup.last_ok_command)
        self.console.print(table)

    def create(self) -> None:
        
        self.console.print(Pretty(self.cfg.boot))

        try:
            self.pm.boot(self.cfg.boot)
        except Exception as e:
            self.console.print(Traceback())
            return

        self.apps = { n:AppSupervisor(self.console, h) for n,h in self.pm.apps.items() }

    def destroy(self):
        if self.apps:
            for s in self.apps.values():
                s.terminate()
            self.apps = None
        self.pm.terminate()

    def init(self):
        for n,s in self.apps.items():
            s.send_command('init', self.cfg.init[n], 'NONE', 'INITIAL')

    def conf(self):
        for n,s in self.apps.items():
            s.send_command('conf', self.cfg.conf[n], 'INITIAL', 'CONFIGURED')

    def start(self, runnum):
        for n,s in self.apps.items():
            s.send_command('start', {"run": runnum}, 'CONFIGURED', 'RUNNING')

    def stop(self):
        for n,s in self.apps.items():
            s.send_command('stop', {}, 'RUNNING', 'CONFIGURED')

    def scrap(self):
        for n,s in self.apps.items():
            s.send_command('scrap', {}, 'CONFIGURED', 'INITIAL')



def cleanup(ctx):
    ctx.obj.destroy()

# ------------------------------------------------------------------------------
# Add -h as default help option
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
# @shell(
#     prompt=click.style('ipbb', fg='blue') + '> ',
#     intro='Starting IPBus Builder...',
#     context_settings=CONTEXT_SETTINGS
# )
# @click.group(context_settings=CONTEXT_SETTINGS)
@click_shell.shell(prompt='shonky rc> ', on_finished=cleanup, context_settings=CONTEXT_SETTINGS)

# @click.command()
@click.pass_context
@click.argument('cfg_dir', type=click.Path(exists=True))
def cli(ctx, cfg_dir):

    console = Console()
    grid = Table(title='Shonky RC', show_header=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky RC to run DUNE-DAQ applications.")
    grid.add_row("Use it wisely!")
    console.print(grid)
    try:
        rc = NanoRC(console, cfg_dir)
    except Exception as e:
        console.print(Traceback())
        raise click.Abort()
    ctx.obj = rc
    # NanoRCShell(console, rc).cmdloop()

@cli.command('status')
@click.pass_obj
def status(rc):
    rc.status()

@cli.command('create')
@click.pass_obj
def create(rc):
    rc.create()
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
@click.argument('runnum', type=int)
@click.pass_obj
def start(rc, runnum):
    rc.start(runnum)
    rc.status()

@cli.command('stop')
@click.pass_obj
def stop(rc):
    rc.stop()
    rc.status()

@cli.command('scrap')
@click.pass_obj
def scrap(rc):
    rc.scrap()
    rc.status()

@cli.command('destroy')
@click.pass_obj
def destroy(rc):
    rc.destroy()
    rc.status()

if __name__ == '__main__':
    cli()






