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
import threading
import socket

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
import nanorc.argval as argval
from nanorc.rest import RestApi, NanoWebContext, rc_context
from nanorc.webui import WebServer

from nanorc.common_commands import add_common_cmds, add_custom_cmds, accept_timeout, accept_wait, check_rc, execute_cmd_sequence, accept_message, add_run_end_parameters
from nanorc.cli import CONTEXT_SETTINGS, loglevels, updateLogLevel
from nanorc.nano_context import NanoContext

# ------------------------------------------------------------------------------
@click_shell.shell(prompt='anonymous@np04rc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--log-path', type=click.Path(exists=True), default='/log', help='Where the logs should go (on localhost of applications)')
@accept_timeout(60)
@click.option('--elisa-conf', type=click.Path(exists=True), default=None, help='ELisA configuration (by default, use the one in src/nanorc/confdata)')
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.option('--dotnanorc', type=click.Path(), default="~/.nanorc.json", help='A JSON file which has auth/socket for the DB services')
@click.option('--kerberos/--no-kerberos', default=False, help='Whether you want to use kerberos for communicating between processes')
@click.option('--pm', type=str, default="ssh://", help='Process manager, can be: ssh://, kind://, or k8s://np04-srv-015:31000, for example', callback=argval.validate_pm)
@click.option('--web/--no-web', is_flag=True, default=False, help='whether to spawn webui')
@click.option('--partition-number', type=int, default=0, help='Which partition number to run', callback=argval.validate_partition_number)
@click.argument('cfg_dir', type=str, callback=argval.validate_conf)
@click.argument('user', type=str)
@click.argument('partition-label', type=str, callback=argval.validate_partition)
@click.pass_obj
@click.pass_context
def np04cli(ctx, obj, traceback, loglevel, elisa_conf, log_path, cfg_dumpdir, dotnanorc, kerberos, timeout, partition_number, partition_label, web, pm, cfg_dir, user):

    if not elisa_conf:
        with resources.path(confdata, "elisa_conf.json") as p:
            elisa_conf = p

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

    port_offset = 0 + partition_number * 500
    rest_port = 5005 + partition_number
    webui_port = 5015 + partition_number

    if loglevel:
        updateLogLevel(loglevel)

    rest_thread  = threading.Thread()
    webui_thread = threading.Thread()
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

        rc = NanoRC(
            console = obj.console,
            top_cfg = cfg_dir,
            partition_label = partition_label,
            run_num_mgr = DBRunNumberManager(rundb_socket),
            run_registry = DBConfigSaver(runreg_socket),
            logbook_type = elisa_conf,
            timeout = timeout,
            use_kerb = kerberos,
            port_offset = port_offset,
            pm = pm
        )

        rc.log_path = os.path.abspath(log_path)
        add_common_cmds(ctx.command, end_of_run_cmds=False)
        add_custom_cmds(ctx.command, rc.execute_custom_command, rc.custom_cmd)

        if web:
            host = socket.gethostname()

            rc_context.obj = obj
            rc_context.console = obj.console
            rc_context.top_json = cfg_dir
            rc_context.rc = rc
            rc_context.commands = ctx.command.commands
            rc_context.ctx = ctx

            obj.console.log(f"Starting up RESTAPI on {host}:{rest_port}")
            rest = RestApi(rc_context, host, rest_port)
            rest_thread = threading.Thread(target=rest.run, name="NanoRC_REST_API")
            rest_thread.start()
            obj.console.log(f"Started RESTAPI")

            webui_thread = None
            obj.console.log(f'Starting up Web UI on {host}:{webui_port}')
            webui = WebServer(host, webui_port, host, rest_port)
            webui_thread = threading.Thread(target=webui.run, name='NanoRC_WebUI')
            webui_thread.start()
            obj.console.log(f"")
            obj.console.log(f"")
            obj.console.log(f"")
            obj.console.log(f"")
            grid = Table(title='Web NanoRC', show_header=False, show_edge=False)
            grid.add_column()
            grid.add_row(f"Started Web UI, you can now connect to: [blue]{host}:{webui_port}[/blue],")
            if 'np04' in host:
                grid.add_row(f"You probably need to set up a SOCKS proxy to lxplus:")
                grid.add_row("[blue]ssh -N -D 8080 your_cern_uname@lxtunnel.cern.ch[/blue] # on a different terminal window on your machine")
                grid.add_row(f'Make sure you set up browser SOCKS proxy with port 8080 too,')
                grid.add_row('on Chrome, \'Hotplate localhost SOCKS proxy setup\' works well).')
            grid.add_row()
            grid.add_row(f'[red]To stop this, ctrl-c [/red][bold red]twice[/bold red] (that will kill the REST and WebUI threads).')
            obj.console.print(Panel.fit(grid))
            obj.console.log(f"")
            obj.console.log(f"")
            obj.console.log(f"")
            obj.console.log(f"")

    except Exception as e:
        logging.getLogger("cli").exception("Failed to build NanoRC")
        raise click.Abort()

    def cleanup_rc():
        if rc.topnode.state != 'none':
            logging.getLogger("cli").warning("NanoRC context cleanup: Aborting applications before exiting")
            rc.abort(timeout=120)
        if rc.return_code:
            ctx.exit(rc.return_code)

    ctx.call_on_close(cleanup_rc)
    obj.rc = rc
    obj.shell = ctx.command
    rc.ls(False)
    if web:
        rest_thread.join()
        webui_thread.join()

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

@np04cli.command('klist')
@click.pass_obj
@click.pass_context
def klist(ctx, obj):
    credentials.check_kerberos_credentials(silent=False)
    import subprocess
    # print(subprocess.call(['klist', '-s']))
    proc = subprocess.run(['klist', '-s'], capture_output=True, text=True, env=credentials.krbenv)
    obj.rc.log.info(f'klist -s\nstdout: {proc.stdout}')
    obj.rc.log.info(f'stderr: {proc.stderr}')
    obj.rc.log.info(f'ret code: {proc.returncode}')


def add_run_start_parameters():
    # sigh start...
    def add_decorator(function):
        f1 = click.argument('run-type', required=True, type=click.Choice(['TEST', 'PROD']))(function)
        f2 = click.option('--trigger-rate', type=float, default=None, help='Trigger rate in Hz')(f1)
        f3 = click.option('--disable-data-storage/--enable-data-storage', type=bool, default=False, help='Toggle data storage')(f2)
        f4 = accept_timeout(None)(f3)
        return click.option('--message', type=str, default="")(f4)
     # sigh end
    return add_decorator

def start_defaults_overwrite(kwargs):
    kwargs['path'] = None
    return kwargs

def is_authenticated():
    if not credentials.check_kerberos_credentials():
        logging.getLogger("cli").error(f'\'{credentials.user}\' doesn\'t have valid kerberos ticket, use \'kinit\', or \'change_user\' to create a ticket (in a shell or in nanorc)')
        return False
    return True


@np04cli.command('start_run')
@add_run_start_parameters()
@accept_wait()
@click.pass_obj
@click.pass_context
def start_run(ctx, obj, wait:int, **kwargs):
    if not is_authenticated(): return

    kwargs['node_path'] = None
    execute_cmd_sequence(
        ctx = ctx,
        rc = obj.rc,
        command = 'start_run',
        wait = wait,
        force = False,
        cmd_args = start_defaults_overwrite(kwargs)
    )


@np04cli.command('start')
@add_run_start_parameters()
@click.pass_obj
@click.pass_context
def start(ctx, obj:NanoContext, **kwargs):
    if not is_authenticated(): return

    obj.rc.start(**start_defaults_overwrite(kwargs))
    check_rc(ctx,obj.rc)
    obj.rc.status()

@np04cli.command('message')
@accept_message(argument=True)
@click.pass_obj
def message(obj, message):
    if not is_authenticated(): return
    obj.rc.message(message)


@np04cli.command('stop_run')
@accept_wait()
@add_run_end_parameters()
@click.pass_obj
@click.pass_context
def stop_run(ctx, obj, wait:int, **kwargs):
    if not is_authenticated(): return

    execute_cmd_sequence(
        ctx = ctx,
        rc = obj.rc,
        command = 'stop_run',
        force = kwargs['force'],
        wait = wait,
        cmd_args = kwargs
    )

@np04cli.command('shutdown')
@accept_wait()
@add_run_end_parameters()
@click.pass_obj
@click.pass_context
def shutdown(ctx, obj, wait:int, **kwargs):
    if not is_authenticated(): return

    kwargs['node_path'] = None
    execute_cmd_sequence(
        ctx = ctx,
        rc = obj.rc,
        wait = wait,
        command = 'shutdown',
        force = kwargs['force'],
        cmd_args = kwargs
    )


@np04cli.command('drain_dataflow')
@add_run_end_parameters()
@click.pass_obj
@click.pass_context
def drain_dataflow(ctx, obj, **kwargs):
    if not is_authenticated(): return

    obj.rc.drain_dataflow(**kwargs)
    check_rc(ctx,obj.rc)
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
