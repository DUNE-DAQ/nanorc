#!/usr/bin/env python3


"""
Command Line Interface for NanoRC
"""
import os
import sh
import sys
import time
import json
import cmd
import click
import click_shell
import os.path
import logging

from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.traceback import Traceback
from rich.progress import *

from nanorc.core import NanoRC



class NanoContext:
    """docstring for NanoContext"""
    def __init__(self, console):
        super(NanoContext, self).__init__()
        self.console = console
        self.print_traceback = False
        self.rc = None


# ------------------------------------------------------------------------------
# Add -h as default help option
CONTEXT_SETTINGS = dict(help_option_names=['-h', '--help'])
# ------------------------------------------------------------------------------


loglevels = {
    'CRITICAL': logging.CRITICAL,
    'ERROR': logging.ERROR,
    'WARNING': logging.WARNING,
    'INFO': logging.INFO,
    'DEBUG': logging.DEBUG,
    'NOTSET': logging.NOTSET,
}

# ------------------------------------------------------------------------------
@click_shell.shell(prompt='shonky rc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default=None, help='Set the log level')
@click.argument('cfg_dir', type=click.Path(exists=True))
@click.pass_obj
@click.pass_context
def cli(ctx, obj, traceback, loglevel, cfg_dir):

    obj.print_traceback = traceback

    grid = Table(title='Shonky NanoRC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nanp RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row("Use it with care!")

    console.print(Panel.fit(grid))


    if loglevel:
        level = loglevels[loglevel]
        logger = logging.getLogger()
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)

    try:
        rc = NanoRC(console, cfg_dir)
    except Exception as e:
        logging.getLogger("rich").exception("Failed to build NanoRC")
        raise click.Abort()
        
    def cleanup_rc():
        print("NanoRC context cleanup: Terminating RC before exiting")
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

    RUN: run number

    """
    obj.rc.start(run, disable_data_storage, None) # FIXME: how?
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
@click.option('--trigger-interval-ticks', type=int, default=None, help='Trigger separation in ticks')
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

    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

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






