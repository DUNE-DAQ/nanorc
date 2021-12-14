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
@click_shell.shell(prompt='shonky np04rc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--timeout', type=int, default=60, help='Application commands timeout')
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.option('--dotnanorc', type=click.Path(), default="~/.nanorc.json", help='A JSON file which has auth/socket for the DB services')

@click.argument('cfg_dir', type=click.Path(exists=True))
@click.pass_obj
@click.pass_context
def np04cli(ctx, obj, traceback, loglevel, timeout, cfg_dumpdir, dotnanorc, cfg_dir):
    obj.print_traceback = traceback

    grid = Table(title='Shonky Nano04RC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nanp RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row("Use it with care!")

    obj.console.print(Panel.fit(grid))


    if loglevel:
        updateLogLevel(loglevel)

    try:
        dotnanorc = os.path.expanduser(dotnanorc)
        obj.console.print(f"[blue]Loading {dotnanorc}[/blue]")
        f = open(dotnanorc)
        dotnanorc = json.load(f)
        credentials.add_login("rundb",
                              dotnanorc["rundb"]["user"],
                              dotnanorc["rundb"]["password"])
        credentials.add_login("runregistrydb",
                              dotnanorc["runregistrydb"]["user"],
                              dotnanorc["runregistrydb"]["password"])
        logging.getLogger("cli").info("RunDB socket "+dotnanorc["rundb"]["socket"])
        logging.getLogger("cli").info("RunRegistryDB socket "+dotnanorc["runregistrydb"]["socket"])
        rc = NanoRC(obj.console, cfg_dir,
                    DBRunNumberManager(dotnanorc["rundb"]["socket"]),
                    DBConfigSaver(dotnanorc["runregistrydb"]["socket"]),
                    timeout)
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
np04cli.add_command(start, 'start')
np04cli.add_command(stop, 'stop')
np04cli.add_command(pause, 'pause')
np04cli.add_command(resume, 'resume')
np04cli.add_command(scrap, 'scrap')
np04cli.add_command(wait, 'wait')
np04cli.add_command(terminate, 'terminate')

@np04cli.command('start')
@click.argument('run-type', required=True,
                type=click.Choice(['TEST', 'PROD']))
@click.option('--disable-data-storage/--enable-data-storage', type=bool, default=False, help='Toggle data storage')
@click.option('--trigger-interval-ticks', type=int, default=None, help='Trigger separation in ticks')
@click.option('--resume-wait', type=int, default=0, help='Seconds to wait between Start and Resume commands')
@click.pass_obj
def start(obj:NanoContext, run_type:str, disable_data_storage:bool, trigger_interval_ticks:int, resume_wait:int):
    """
    Start Command

    Args:
        obj (NanoContext): Context object
        disable_data_storage (bool): Flag to disable data writing to storage
    """

    obj.rc.start(disable_data_storage, run_type)
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
