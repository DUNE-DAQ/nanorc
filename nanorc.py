#!/usr/bin/env python

import os
import sh
import sys
import socket
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

    def status(self) -> None:
        if self.pm.apps:
            self.pm.status_apps()

    def create(self):
        
        self.console.print(Pretty(self.cfg.boot))

        try:
            self.pm.boot(self.cfg.boot)
        except Exception as e:
            self.console.print(Traceback())
            return

        self.apps = { n:AppSupervisor(self.console, h) for n,h in self.pm.apps.items() }

    def destroy(self):
        for s in self.apps.values():
            s._kill_listener()
        self.pm.terminate()


    def init(self):
        for n,s in self.apps.items():
            s.send_command('init', self.cfg.init[n], 'NONE', 'INITIAL')

    def conf(self):
        for n,s in self.apps.items():
            s.send_command('conf', self.cfg.conf[n], 'INITIAL', 'CONFIGURED')

    def start(self):
        for n,s in self.apps.items():
            s.send_command('start', {}, 'CONFIGURED', 'RUNNING')

class NanoRCShell(cmd.Cmd):
    """A Poor's man RC"""
    prompt = 'shonky rc> '
    def __init__(self, console: Console, rc: NanoRC):
        super(NanoRCShell, self).__init__()
        self.rc = rc
        self.console = console

    def postcmd(self, stop, line):
        self.console.print()
        self.rc.status()
        return stop

    def do_create(self, arg: str):
        self.rc.create()

    def do_init(self, arg: str):
        self.rc.init()

    def do_conf(self, arg: str):
        self.rc.conf()

    def do_start(self, arg: str):
        self.rc.start()

    def do_destroy(self, arg: str):
        self.rc.destroy()

    def do_exit(self, arg: str):
        self.rc.destroy()
        return True

    do_EOF = do_exit


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
# @click_shell.shell(context_settings=CONTEXT_SETTINGS)

@click.command()
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
    NanoRCShell(console, rc).cmdloop()

if __name__ == '__main__':
    cli()






