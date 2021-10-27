#!/usr/bin/env python3

"""
NanoRC's REST API
"""

import click
import time
import re
from flask import Flask, render_template, request, make_response, stream_with_context, render_template_string, url_for, redirect
from flask_restful import Api, Resource

from nanorc.auth import auth
from threading import Thread
from nanorc.tail import Tail
# from flask_sso import SSO

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from nanorc.core import *
from nanorc.cli import loglevels, updateLogLevel, NanoContext
from nanorc.runmgr import SimpleRunNumberManager
from nanorc.cfgsvr import SimpleConfigSaver

rc_context = None

app = Flask("nanorc_rest_api")
api = Api(app)

def return_code(return_code):
    return 200 if return_code == 0 else 500

@api.resource('/nanorcrest/sendcmd', methods=['POST'])
class sendcmd(Resource):
    @auth.login_required
    def post(self):
        try:
            # Flush the console
            _=rc_context.rc.console.export_html()
            
            if request.form['cmd'] == 'BOOT':
                target = rc_context.rc.boot()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            elif request.form['cmd'] == 'TERMINATE':
                target = rc_context.rc.terminate()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            elif request.form['cmd'] == 'STATUS':
                target = rc_context.rc.status()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            elif request.form['cmd'] == 'INIT':
                target = rc_context.rc.init()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            elif request.form['cmd'] == 'CONF':
                target = rc_context.rc.conf()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            elif request.form['cmd'] == 'START':
                target = rc_context.rc.start()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            elif request.form['cmd'] == 'STOP':
                target = rc_context.rc.stop()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            elif request.form['cmd'] == 'PAUSE':
                target = rc_context.rc.pause()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            elif request.form['cmd'] == 'RESUME':
                target = rc_context.rc.resume()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            elif request.form['cmd'] == 'SCRAP':
                target = rc_context.rc.scrap()
                resp = make_response(rc_context.rc.console.export_html(), return_code(target))
            else:
                raise RuntimeError(f"I don't know of command {request.form['cmd']}")
        except Exception as e:
            print(e)
            resp = make_response(e.text)

        return resp
    
@app.route('/')
@auth.login_required
def index():
    return "Best thing since light saber"

@click.command()
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--timeout', type=int, default=60, help='Application commands timeout')
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.option('--host', type=str, default="0.0.0.0", help='Which host the rest API should run')
@click.option('--port', type=int, default=5001, help='which port to use')
@click.argument('top_cfg', type=click.Path(exists=True))
@click.pass_obj
@click.pass_context
def cli(ctx, obj, traceback, loglevel, timeout, cfg_dumpdir, host, port, top_cfg):

    obj.print_traceback = traceback

    grid = Table(title='Shonky API NanoRC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nanp RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row("Use it with care!")

    obj.console.print(Panel.fit(grid))

    if loglevel:
        updateLogLevel(loglevel)

    try:
        rc = NanoRC(obj.console, top_cfg,
                    SimpleRunNumberManager(),
                    SimpleConfigSaver(cfg_dumpdir),
                    timeout)
        rc_context = obj
        rc_context.top_json = top_cfg
        rc_context.rc = rc
        print(f"Starting up on {host}:{port}")
        app.run(host=host, port=port, debug=True, use_reloader=False)

    except Exception as e:
        logging.getLogger("cli").exception("Failed to build NanoRC, or start the API")
        raise click.Abort()

    def cleanup_rc():
        logging.getLogger("cli").warning("NanoRC context cleanup: Terminating RC before exiting")
        rc.terminate()
        ctx.exit(rc.return_code)

    ctx.call_on_close(cleanup_rc)
    
def main():
    global rc_context
    
    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

    console = Console(record=True)
    rc_context = NanoContext(console)

    try:
        cli(obj=rc_context, show_default=True)
        
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        if not obj.print_traceback:
            console.log(e)
        else:
            console.print_exception()


if __name__ == '__main__':
    main()
