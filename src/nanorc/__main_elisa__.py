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
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.traceback import Traceback
from rich.progress import *

from nanorc.core import NanoRC
from nanorc.runmgr import DBRunNumberManager
from nanorc.cfgsvr import DBConfigSaver
from nanorc.credmgr import credentials
from .cli import *
# ------------------------------------------------------------------------------
@click_shell.shell(prompt='user@np04rc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--timeout', type=int, default=60, help='Application commands timeout')
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.option('--kerberos/--no-kerberos', default=False, help='Whether you want to use kerberos for communicating between processes')
@click.argument('cfg_dir', type=click.Path(exists=True))
@click.argument('user', type=str)
@click.pass_obj
@click.pass_context
def elisaCli(ctx, obj, traceback, loglevel, timeout, cfg_dumpdir, kerberos, cfg_dir, user):
    obj.print_traceback = traceback
    credentials.change_user(user)
    ctx.command.shell.prompt = f"{credentials.user}@nano_elisarc> "
    grid = Table(title='Shonky NanoRC (ELisA logbook)', show_header=False, show_edge=False)
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
                    top_cfg = cfg_dir,
                    run_num_mgr = SimpleRunNumberManager(),
                    run_registry = FileConfigSaver(cfg_dumpdir),
                    logbook_type = "elisa",
                    timeout = timeout,
                    use_kerb = kerberos)
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


elisaCli.add_command(status, 'status')
elisaCli.add_command(boot, 'boot')
elisaCli.add_command(init, 'init')
elisaCli.add_command(conf, 'conf')
elisaCli.add_command(pause, 'pause')
elisaCli.add_command(resume, 'resume')
elisaCli.add_command(scrap, 'scrap')
elisaCli.add_command(wait, 'wait')
elisaCli.add_command(terminate, 'terminate')

@elisaCli.command('change_user')
@click.argument('user', type=str, default=None)
@click.pass_obj
@click.pass_context
def change_user(ctx, obj, user):
    if credentials.change_user(user):
        ctx.parent.command.shell.prompt = f"{credentials.user}@elisarc > "


@elisaCli.command('kinit')
@click.pass_obj
@click.pass_context
def kinit(ctx, obj):
    credentials.new_kerberos_ticket()

@elisaCli.command('stop')
@click.option('--stop-wait', type=int, default=0, help='Seconds to wait between Pause and Stop commands')
@click.option('--force', default=False, is_flag=True)
@click.option('--message', type=str, default="")
@click.pass_obj
def stop(obj, stop_wait:int, force:bool, message:str):
    if not credentials.check_kerberos_credentials():
        logging.error(f'User {credentials.user} doesn\'t have valid kerberos ticket, use kinit to create a ticket (in a shell or in nanorc)')
        return
    obj.rc.pause(force)
    obj.rc.status()
    time.sleep(stop_wait)
    obj.rc.stop(force, message=message)
    obj.rc.status()


@elisaCli.command('message')
@click.argument('message', type=str, default=None)
@click.pass_obj
def message(obj, message):
    if not credentials.check_kerberos_credentials():
        logging.error(f'User {credentials.user} doesn\'t have valid kerberos ticket, use kinit to create a ticket (in a shell or in nanorc)')
        return
    obj.rc.message(message)

@elisaCli.command('start')
@click.argument('run', type=int)
@click.option('--disable-data-storage/--enable-data-storage', type=bool, default=False, help='Toggle data storage')
@click.option('--trigger-interval-ticks', type=int, default=None, help='Trigger separation in ticks')
@click.option('--resume-wait', type=int, default=0, help='Seconds to wait between Start and Resume commands')
@click.option('--message', type=str, default="")
@click.pass_obj
def start(obj:NanoContext, run:int, disable_data_storage:bool, trigger_interval_ticks:int, resume_wait:int, message:str):
    """
    Start Command

    Args:
        obj (NanoContext): Context object
        disable_data_storage (bool): Flag to disable data writing to storage
    """
    if not credentials.check_kerberos_credentials():
        logging.error(f'User {credentials.user} doesn\'t have valid kerberos ticket, use kinit to create a ticket (in a shell or in nanorc)')
        return

    obj.rc.run_num_mgr.set_run_number(run)
    obj.rc.start(disable_data_storage, "TEST", message=message)
    obj.rc.status()
    time.sleep(resume_wait)
    obj.rc.resume(trigger_interval_ticks)
    obj.rc.status()

def main():
    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

    console = Console()
    credentials.console = console # some uglyness right here
    obj = NanoContext(console)

    try:
        elisaCli(obj=obj, show_default=True)
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        if not obj.print_traceback:
            console.log(e)
        else:
            console.print_exception()

if __name__ == '__main__':
    main()
