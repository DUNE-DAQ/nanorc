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
import importlib.resources as resources

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
from . import confdata

from .cli import *
# ------------------------------------------------------------------------------
@click_shell.shell(prompt='anonymous@np04rc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--log-path', type=click.Path(exists=True), default='/log', help='Where the logs should go (on localhost of applications)')
@click.option('--timeout', type=int, default=60, help='Application commands timeout')
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.option('--dotnanorc', type=click.Path(), default="~/.nanorc.json", help='A JSON file which has auth/socket for the DB services')
@click.option('--kerberos/--no-kerberos', default=False, help='Whether you want to use kerberos for communicating between processes')
@click.argument('cfg_dir', type=click.Path(exists=True))
@click.argument('user', type=str)
@click.pass_obj
@click.pass_context
def np04cli(ctx, obj, traceback, loglevel, log_path, timeout, cfg_dumpdir, dotnanorc, kerberos, cfg_dir, user):
    obj.print_traceback = traceback
    credentials.change_user(user)
    ctx.command.shell.prompt = f"{credentials.user}@np04rc> "
    grid = Table(title='Shonky Nano04RC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nano RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row(f"Use it with care, {credentials.user}!")

    obj.console.print(Panel.fit(grid))


    if loglevel:
        updateLogLevel(loglevel)

    try:
        dotnanorc = os.path.expanduser(dotnanorc)
        obj.console.print(f"[blue]Loading {dotnanorc}[/blue]")
        f = open(dotnanorc)
        dotnanorc = json.load(f)

        rundb_socket = json.loads(resources.read_text(confdata, "run_number.json"))['socket']
        runreg_socket = json.loads(resources.read_text(confdata, "run_registry.json"))['socket']

        credentials.add_login("rundb",
                              dotnanorc["rundb"]["user"],
                              dotnanorc["rundb"]["password"])
        credentials.add_login("runregistrydb",
                              dotnanorc["runregistrydb"]["user"],
                              dotnanorc["runregistrydb"]["password"])
        logging.getLogger("cli").info("RunDB socket "+rundb_socket)
        logging.getLogger("cli").info("RunRegistryDB socket "+runreg_socket)

        rc = NanoRC(console = obj.console,
                    top_cfg = cfg_dir,
                    run_num_mgr = DBRunNumberManager(rundb_socket),
                    run_registry = DBConfigSaver(runreg_socket),
                    logbook_type = "elisa",
                    timeout = timeout,
                    use_kerb = kerberos)

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


np04cli.add_command(status, 'status')
np04cli.add_command(boot, 'boot')
np04cli.add_command(init, 'init')
np04cli.add_command(conf, 'conf')
np04cli.add_command(pause, 'pause')
np04cli.add_command(resume, 'resume')
np04cli.add_command(scrap, 'scrap')
np04cli.add_command(wait, 'wait')
np04cli.add_command(terminate, 'terminate')

@np04cli.command('change_user')
@click.argument('user', type=str, default=None)
@click.pass_obj
@click.pass_context
def change_user(ctx, obj, user):
    if credentials.change_user(user):
        ctx.parent.command.shell.prompt = f"{credentials.user}@np04rc > "

@np04cli.command('kinit')
@click.pass_obj
@click.pass_context
def kinit(ctx, obj):
    credentials.new_kerberos_ticket()

@np04cli.command('stop')
@click.option('--stop-wait', type=int, default=0, help='Seconds to wait between Pause and Stop commands')
@click.option('--force', default=False, is_flag=True)
@click.option('--message', type=str, default="")
@click.pass_obj
def stop(obj, stop_wait:int, force:bool, message:str):
    if not credentials.check_kerberos_credentials():
        logging.getLogger("cli").error(f'User {credentials.user} doesn\'t have valid kerberos ticket, use kinit to create a ticket (in a shell or in nanorc)')
        return
    obj.rc.pause(force)
    obj.rc.status()
    time.sleep(stop_wait)
    obj.rc.stop(force, message=message)
    obj.rc.status()


@np04cli.command('message')
@click.argument('message', type=str, default=None)
@click.pass_obj
def message(obj, message):
    if not credentials.check_kerberos_credentials():
        logging.getLogger("cli").error(f'User {credentials.user} doesn\'t have valid kerberos ticket, use kinit to create a ticket (in a shell or in nanorc)')
        return
    obj.rc.message(message)

@np04cli.command('start')
@click.argument('run-type', required=True,
                type=click.Choice(['TEST', 'PROD']))
@click.option('--disable-data-storage/--enable-data-storage', type=bool, default=False, help='Toggle data storage')
@click.option('--trigger-interval-ticks', type=int, default=None, help='Trigger separation in ticks')
@click.option('--resume-wait', type=int, default=0, help='Seconds to wait between Start and Resume commands')
@click.option('--message', type=str, default="")
@click.pass_obj
def start(obj:NanoContext, run_type:str, disable_data_storage:bool, trigger_interval_ticks:int, resume_wait:int, message:str):
    """
    Start Command

    Args:
        obj (NanoContext): Context object
        disable_data_storage (bool): Flag to disable data writing to storage
    """
    if not credentials.check_kerberos_credentials():
        logging.getLogger("cli").error(f'User {credentials.user} doesn\'t have valid kerberos ticket, use kinit to create a ticket (in a shell or in nanorc)')
        return

    obj.rc.start(disable_data_storage, run_type, message=message)
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
        np04cli(obj=obj, show_default=True)
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        if not obj.print_traceback:
            console.log(e)
        else:
            console.print_exception()

if __name__ == '__main__':
    main()
