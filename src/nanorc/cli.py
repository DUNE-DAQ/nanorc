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
from click_shell import make_click_shell
import os.path
import socket
from pathlib import Path
import logging
import threading

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
from nanorc.rest import RestApi, NanoWebContext, rc_context
from nanorc.webui import WebServer

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

def validate_timeout(ctx, param, timeout):
    if timeout is None:
        return timeout
    if timeout<=0:
        raise click.BadParameter('Timeout should be >0')
    return timeout

def accept_timeout(default_timeout):
    def add_decorator(function):
        return click.option('--timeout', type=int, default=default_timeout, help="Timeout, in seconds", callback=validate_timeout)(function)
    return add_decorator

def validatePath(ctx, param, prompted_path):

    if prompted_path is None:
        return None

    if prompted_path[0] != '/':
        prompted_path = '/'+prompted_path

    hierarchy = prompted_path.split("/")
    topnode = ctx.obj.rc.topnode

    r = Resolver('name')
    try:
        node = r.get(topnode, prompted_path)
        return node
    except Exception as ex:
        raise click.BadParameter(f"Couldn't find {prompted_path} in the tree") from ex

    return node

def validateCfgDir(ctx, param, path):
    return str(Path(path))

def check_rc(ctx, obj):
    if ctx.parent.invoked_subcommand == '*' and obj.rc.return_code:
        ctx.exit(obj.rc.return_code)

def validate_partition_number(ctx, param, number):
    if number<0 or number>10:
        raise click.BadParameter(f"Partition number should be between 0 and 10 (you fed {number})")
    return number

def add_custom_cmds(cli, rc_cmd_exec, cmds):
    for c,d in cmds.items():
        arg_list = {}
        arg_default = {}
        for app, app_data in d.items():
            for modules_data in app_data.values():
                for module_data in modules_data:
                    module = module_data['match']
                    cmd_data = module_data['data']
                    for arg in cmd_data:
                        arg_list[arg] = type(cmd_data[arg])
                        arg_default[arg] = cmd_data[arg]

        def execute_custom(ctx, obj, timeout, **kwargs):
            rc_cmd_exec(command=obj.info_name, data=kwargs, timeout=timeout)

        execute_custom = click.pass_obj(execute_custom)
        execute_custom = click.pass_context(execute_custom)
        execute_custom = click.command(c)(execute_custom)
        execute_custom = accept_timeout(None)(execute_custom)
        for arg, argtype in arg_list.items():
            arg_pretty = arg.replace("_", "-")
            execute_custom = click.option(f'--{arg_pretty}', type=argtype, default=arg_default[arg])(execute_custom)
        cli.add_command(execute_custom, c)

# ------------------------------------------------------------------------------
@click_shell.shell(prompt='shonky rc> ', chain=True, context_settings=CONTEXT_SETTINGS)
@click.version_option(__version__)
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.option('--log-path', type=click.Path(exists=True), default=None, help='Where the logs should go (on localhost of applications)')
@click.option('--kerberos/--no-kerberos', default=True, help='Whether you want to use kerberos for communicating between processes')
@click.option('--logbook-prefix', type=str, default="logbook", help='Prefix for the logbook file')
@accept_timeout(60)
@click.option('--partition-number', type=int, default=0, help='Which partition number to run', callback=validate_partition_number)
@click.option('--web/--no-web', is_flag=True, default=False, help='whether to spawn webui')
@click.argument('top_cfg', type=click.Path(exists=True), callback=validateCfgDir)
@click.pass_obj
@click.pass_context
def cli(ctx, obj, traceback, loglevel, cfg_dumpdir, log_path, logbook_prefix, timeout, kerberos, partition_number, web, top_cfg):
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

    port_offset = 0 + partition_number * 1_000
    rest_port = 5005 + partition_number
    webui_port = 5015 + partition_number
    
    if loglevel:
        updateLogLevel(loglevel)

    rest_thread  = threading.Thread()
    webui_thread = threading.Thread()
        
    try:
        rc = NanoRC(console = obj.console,
                    top_cfg = top_cfg,
                    run_num_mgr = SimpleRunNumberManager(),
                    run_registry = FileConfigSaver(cfg_dumpdir),
                    logbook_type = "file",
                    timeout = timeout,
                    use_kerb = kerberos,
                    logbook_prefix = logbook_prefix,
                    port_offset = port_offset)

        if log_path:
            rc.log_path = os.path.abspath(log_path)

        add_custom_cmds(ctx.command, rc.execute_custom_command, rc.custom_cmd)

        if web:
            host = socket.gethostname()

            # rc_context = obj
            rc_context.console = obj.console
            rc_context.top_json = top_cfg
            rc_context.rc = rc
            
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
        if rc.topnode.state != 'none': logging.getLogger("cli").warning("NanoRC context cleanup: Terminating RC before exiting")
        rc.terminate()
        if rc.return_code:
            ctx.exit(rc.return_code)

    ctx.call_on_close(cleanup_rc)
    obj.rc = rc
    obj.shell = ctx.command
    rc.ls(False)
    if web:
        rest_thread.join()
        webui_thread.join()

@cli.command('status')
@click.pass_obj
def status(obj: NanoContext):
    obj.rc.status()

@cli.command('pin-threads')
@click.option('--pin-thread-file', type=click.Path(exists=True), default=None)
@accept_timeout(None)
@click.pass_obj
def pin_threads(obj:NanoContext, pin_thread_file, timeout:int):
    data = { "script_name": 'thread_pinning' }
    if pin_thread_file:
        data["env"]: { "DUNEDAQ_THREAD_PIN_FILE": pin_thread_file }
    obj.rc.execute_script(data=data, timeout=timeout)

@cli.command('boot')
@accept_timeout(None)
@click.argument('partition', type=str)
@click.pass_obj
@click.pass_context
def boot(ctx, obj, partition:str, timeout:int):
    obj.rc.boot(partition=partition, timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('init')
@click.option('--path', type=str, default=None, callback=validatePath)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def init(ctx, obj, path, timeout:int):
    obj.rc.init(path, timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('ls')
@click.pass_obj
def ls(obj):
    obj.rc.ls()


@cli.command('conf')
@click.option('--path', type=str, default=None, callback=validatePath)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def conf(ctx, obj, path, timeout:int):
    obj.rc.conf(path, timeout=timeout)
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
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def start(ctx, obj:NanoContext, run:int, disable_data_storage:bool, trigger_interval_ticks:int, resume_wait:int, message:str, timeout:int):
    """
    Start Command

    Args:
        obj (NanoContext): Context object
        run (int): Run number
        disable_data_storage (bool): Flag to disable data writing to storage

    """

    obj.rc.run_num_mgr.set_run_number(run)
    obj.rc.start(disable_data_storage, "TEST", message=message, timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()
    time.sleep(resume_wait)
    if obj.rc.return_code == 0:
        time.sleep(resume_wait)
        obj.rc.resume(trigger_interval_ticks, timeout=timeout)
        obj.rc.status()

@cli.command('stop')
@click.option('--stop-wait', type=int, default=0, help='Seconds to wait between Pause and Stop commands')
@click.option('--force', default=False, is_flag=True)
@click.option('--message', type=str, default="")
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def stop(ctx, obj, stop_wait:int, force:bool, message:str, timeout:int):
    obj.rc.pause(force, timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()
    time.sleep(stop_wait)
    if obj.rc.return_code == 0:
        obj.rc.stop(force, message=message, timeout=timeout)
        obj.rc.status()

@cli.command('pause')
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def pause(ctx, obj, timeout:int):
    obj.rc.pause(timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('resume')
@click.option('--trigger-interval-ticks', type=int, default=None, help='Trigger separation in ticks')
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def resume(ctx, obj:NanoContext, trigger_interval_ticks:int, timeout:int):
    """Resume Command

    Args:
        obj (NanoContext): Context object
        trigger_interval_ticks (int): Trigger separation in ticks
    """
    obj.rc.resume(trigger_interval_ticks, timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()


@cli.command('scrap')
@click.option('--path', type=str, default=None, callback=validatePath)
@click.option('--force', default=False, is_flag=True)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def scrap(ctx, obj, path, force, timeout):
    obj.rc.scrap(path, force, timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('start_trigger')
@click.option('--trigger-interval-ticks', type=int, default=None)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def start_trigger(ctx, obj, trigger_interval_ticks, timeout):
    obj.rc.start_trigger(trigger_interval_ticks, timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('stop_trigger')
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def stop_trigger(ctx, obj, timeout):
    obj.rc.stop_trigger(timeout=timeout)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('change_rate')
@click.argument('trigger-interval-ticks', type=int)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def change_rate(ctx, obj, trigger_interval_ticks, timeout):
    obj.rc.change_rate(trigger_interval_ticks, timeout)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('enable')
@click.argument('path', type=str, default=None, callback=validatePath)
@click.option('--resource-name', type=str, required=True)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def enable(ctx, obj, path, resource_name, timeout):
    obj.rc.enable(path, timeout=timeout, resource_name=resource_name)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('disable')
@click.argument('path', type=str, default=None, callback=validatePath)
@click.option('--resource-name', type=str, required=True)
@accept_timeout(None)
@click.pass_obj
@click.pass_context
def disable(ctx, obj, path, resource_name, timeout):
    obj.rc.disable(path, timeout=timeout, resource_name=resource_name)
    check_rc(ctx,obj)
    obj.rc.status()

@cli.command('terminate')
@accept_timeout(None)
@click.pass_obj
def terminate(obj, timeout):
    obj.rc.terminate(timeout=timeout)
    time.sleep(1)
    obj.rc.status()

@cli.command('expert_command')
@click.argument('app', type=str, default=None, callback=validatePath)
@click.argument('json_file', type=click.Path(exists=True))
@accept_timeout(None)
@click.pass_obj
def expert_command(obj, app, json_file, timeout):
    obj.rc.send_expert_command(app, json_file, timeout=timeout)

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

@cli.command('shell')
@click.pass_obj
@click.pass_context
def start_shell(ctx, obj):
    ctx.command = obj.shell
    shell = make_click_shell(ctx,prompt=ctx.command.shell.prompt)
    shell.cmdloop()
