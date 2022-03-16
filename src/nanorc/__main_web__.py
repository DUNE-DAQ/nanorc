#!/usr/bin/env python3

"""
NanoRC WEB
"""

import click
import logging
import threading
import socket
from nanorc.core import NanoRC
from nanorc.runmgr import SimpleRunNumberManager
from nanorc.cfgsvr import FileConfigSaver

from nanorc.rest import RestApi, NanoWebContext, rc_context

from nanorc.webui import WebServer
from nanorc.cli import loglevels, updateLogLevel
from nanorc.credmgr import credentials

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

@click.command()
@click.option('--rest-host', type=str, default="localhost", help='Host of the server for the REST API')
@click.option('--webui-host', type=str, default="localhost", help='Host of the server for the WebUI')
@click.option('--rest-port', type=int, default=5001, help='Port of the server for the REST API')
@click.option('--webui-port', type=int, default=5002, help='Port of the server for the WebUI')
@click.option('--rest/--no-rest', default=True, help='Whether you want to run the REST API')
@click.option('--webui/--no-webui', default=True, help='Whether you want to run the WebUI')
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
def cli(ctx, obj,
        rest_host, webui_host, rest_port, webui_port, rest, webui,
        traceback, loglevel,
        timeout, cfg_dumpdir, log_path, logbook_prefix, kerberos, top_cfg):

    obj.print_traceback = traceback
    credentials.user = 'user'

    grid = Table(title='Shonky NanoRC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nano RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row(f"Use it with care, {credentials.user}!")

    obj.console.print(Panel.fit(grid))
    rest_thread=None
    if rest:
        obj.console.log('Spawning REST API')

        if loglevel:
            updateLogLevel(loglevel)

        try:
            rc = NanoRC(console = obj.console,
                        top_cfg = top_cfg,
                        run_num_mgr = SimpleRunNumberManager(),
                        run_registry = FileConfigSaver(cfg_dumpdir),
                        logbook_type = 'file',
                        timeout = timeout,
                        use_kerb = kerberos,
                        logbook_prefix = logbook_prefix)
            rc_context = obj
            rc_context.top_json = top_cfg
            rc_context.rc = rc
            rest_host = socket.gethostname() if rest_host == 'localhost'  else rest_host
        
            obj.console.log(f"Starting up RESTAPI on {rest_host}:{rest_port}")
            rest = RestApi(rc_context, rest_host, rest_port)
            rest_thread = threading.Thread(target=rest.run,
                                           name="REST_API")
            rest_thread.start()
            obj.console.log(f"Started RESTAPI")

        except Exception as e:
            logging.getLogger("cli").exception("Failed to build NanoRC, or start the API")
            raise click.Abort()

        def cleanup_rc():
            logging.getLogger("cli").warning("NanoRC context cleanup: Terminating RC before exiting")
            rc.terminate()
            ctx.exit(rc.return_code)

        ctx.call_on_close(cleanup_rc)

    webui_thread = None
    if webui:
        webui_host = socket.gethostname() if webui_host == 'localhost'  else webui_host
        obj.console.log(f'Starting up Web UI on {webui_host}:{webui_port}')
        webui = WebServer(webui_host, webui_port, rest_host, rest_port)
        webui_thread = threading.Thread(target = webui.run,
                                        name='WebUI')
        webui_thread.start()
        obj.console.log(f"Started Web UI")
    
    if rest:
        rest_thread.join()


def main():
    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

    console = Console(record=True)
    # rc_context = NanoWebContext(console)
    rc_context.console=console
    try:
        cli(obj=rc_context, show_default=True)

    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        if not rc_context.print_traceback:
            console.log(e)
        else:
            console.print_exception()

if __name__ == '__main__':
    main()
