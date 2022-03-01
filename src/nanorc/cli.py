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

from . import __version__

from anytree.resolver import Resolver

from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.traceback import Traceback
from rich.progress import *

from nanorc.runmgr import SimpleRunNumberManager
from nanorc.cfgsvr import FileConfigSaver
from nanorc.core import NanoRC
from nanorc.logbook import FileLogbook
from nanorc.credmgr import credentials

class NanoContext:
    """docstring for NanoContext"""
    def __init__(self, console: Console):
        """Nanorc Context for click use.

        Args:
            console (Console): rich console for messages and logging
        """
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

def updateLogLevel(loglevel):
        level = loglevels[loglevel]

        # Update log level for root logger
        logger = logging.getLogger()
        logger.setLevel(level)
        for handler in logger.handlers:
            handler.setLevel(level)
        # And then manually tweak 'sh.command' logger. Sigh.
        sh_command_level = level if level > logging.INFO else (level+10)
        sh_command_logger = logging.getLogger(sh.__name__)
        # sh_command_logger.propagate = False
        sh_command_logger.setLevel(sh_command_level)
        for handler in sh_command_logger.handlers:
            handler.setLevel(sh_command_level)

def validatePath(ctx, param, prompted_path):

    if prompted_path is None:
        return None

    hierarchy = prompted_path.split("/")

    topnode = ctx.obj.rc.topnode

    r = Resolver('name')
    try:
        node = r.get(topnode, prompted_path)
    except Exception as ex:
        raise click.BadParameter(f"Couldn't find {prompted_path} in the tree") from ex

    return hierarchy

def check_rc(ctx, obj):
    if ctx.parent.invoked_subcommand == '*' and obj.rc.return_code:
        ctx.exit(obj.rc.return_code)
    #elif obj.rc.return_code:
    #    logging.getLogger("cli").warning("NanoRC could not execute command. Interactive mode: please try again")

# ------------------------------------------------------------------------------
@click_shell.shell(prompt='shonky rc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--timeout', type=int, default=60, help='Application commands timeout')
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.option('--log-path', type=click.Path(exists=True), default=None, help='Where the logs should go (on localhost of applications)')
@click.option('--kerberos/--no-kerberos', default=True, help='Whether you want to use kerberos for communicating between processes')
@click.option('--logbook-prefix', type=str, default="logbook", help='Prefix for the logbook file')
@click.argument('top_cfg', type=click.Path(exists=True))
@click.pass_obj
@click.pass_context
def cli(ctx, obj, traceback, loglevel, timeout, cfg_dumpdir, log_path, logbook_prefix, kerberos, top_cfg):
    obj.print_traceback = traceback
    credentials.user = 'user'
    ctx.command.shell.prompt = f'{credentials.user}@rc> '

    grid = Table(title='Shonky NanoRC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nano RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row(f"Use it with care, {credentials.user}!")

    obj.console.print(Panel.fit(grid))


    if loglevel:
        updateLogLevel(loglevel)

    try:
        rc = NanoRC(console = obj.console,
                    top_cfg = top_cfg,
                    run_num_mgr = SimpleRunNumberManager(),
                    run_registry = FileConfigSaver(cfg_dumpdir),
                    logbook_type = "file",
                    timeout = timeout,
                    use_kerb = kerberos,
                    logbook_prefix = logbook_prefix)

        if log_path:
            rc.log_path = os.path.abspath(log_path)

    except Exception as e:
        logging.getLogger("cli").exception("Failed to build NanoRC")
        raise click.Abort()

    def cleanup_rc():
        logging.getLogger("cli").warning("NanoRC context cleanup: Terminating RC before exiting")
        rc.terminate()
        if rc.return_code:
            ctx.exit(rc.return_code)

    ctx.call_on_close(cleanup_rc)
    obj.rc = rc
    rc.ls(False)

@cli.command('status')
@click.pass_obj
def status(obj: NanoContext):
    obj.rc.status()

@cli.command('boot')
@click.pass_obj
@click.pass_context
def boot(ctx, obj):
    obj.rc.boot()
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('init')
@click.option('--path', type=str, default=None, callback=validatePath)
@click.pass_obj
@click.pass_context
def init(ctx, obj, path):
    obj.rc.init(path)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('ls')
@click.pass_obj
def ls(obj):
    obj.rc.ls()


@cli.command('conf')
@click.option('--path', type=str, default=None, callback=validatePath)
@click.pass_obj
@click.pass_context
def conf(ctx, obj, path):
    obj.rc.conf(path)
    check_rc(ctx,obj)
    obj.rc.status()


@cli.command('message')
@click.argument('message', type=str, default=None)
@click.pass_obj
def message(obj, message):
    obj.rc.message(message)

@cli.command('start')
@click.argument('run', type=int)
@click.option('--disable-data-storage/--enable-data-storage', type=bool, default=False, help='Toggle data storage')
@click.option('--trigger-interval-ticks', type=int, default=None, help='Trigger separation in ticks')
@click.option('--resume-wait', type=int, default=0, help='Seconds to wait between Start and Resume commands')
@click.option('--message', type=str, default="")
@click.pass_obj
@click.pass_context
def start(ctx, obj:NanoContext, run:int, disable_data_storage:bool, trigger_interval_ticks:int, resume_wait:int, message:str):
    """
    Start Command

    Args:
        obj (NanoContext): Context object
        run (int): Run number
        disable_data_storage (bool): Flag to disable data writing to storage

    """

    obj.rc.run_num_mgr.set_run_number(run)
    obj.rc.start(disable_data_storage, "TEST", message=message)
    check_rc(ctx,obj)
    obj.rc.status()
    time.sleep(resume_wait)
    if obj.rc.return_code == 0:
        time.sleep(resume_wait)
        obj.rc.resume(trigger_interval_ticks)
        obj.rc.status()

@cli.command('stop')
@click.option('--stop-wait', type=int, default=0, help='Seconds to wait between Pause and Stop commands')
@click.option('--force', default=False, is_flag=True)
@click.option('--message', type=str, default="")
@click.pass_obj
@click.pass_context
def stop(ctx, obj, stop_wait:int, force:bool, message:str):
    obj.rc.pause(force)
    check_rc(ctx,obj)
    obj.rc.status()
    time.sleep(stop_wait)
    if obj.rc.return_code == 0:
        obj.rc.stop(force, message=message)
        obj.rc.status()

@cli.command('pause')
@click.pass_obj
@click.pass_context
def pause(ctx, obj):
    obj.rc.pause()
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('resume')
@click.option('--trigger-interval-ticks', type=int, default=None, help='Trigger separation in ticks')
@click.pass_obj
@click.pass_context
def resume(ctx, obj:NanoContext, trigger_interval_ticks:int):
    """Resume Command

    Args:
        obj (NanoContext): Context object
        trigger_interval_ticks (int): Trigger separation in ticks
    """
    obj.rc.resume(trigger_interval_ticks)
    check_rc(ctx,obj)
    obj.rc.status()


@cli.command('scrap')
@click.option('--path', type=str, default=None, callback=validatePath)
@click.option('--force', default=False, is_flag=True)
@click.pass_obj
@click.pass_context
def scrap(ctx, obj, path, force):
    obj.rc.scrap(path, force)
    check_rc(ctx,obj)
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
