#!/usr/bin/env python3

"""
NanoRC's REST API
"""

import click
import time
import re
from flask import Flask, render_template, request, make_response, stream_with_context, render_template_string, url_for, redirect, jsonify, Markup
from flask_restful import Api, Resource
from anytree.exporter import DictExporter
from anytree.resolver import Resolver

from nanorc.auth import auth
from threading import Thread
import threading

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from nanorc.core import *
from nanorc.cli import loglevels, updateLogLevel
from nanorc.runmgr import SimpleRunNumberManager
from nanorc.cfgsvr import FileConfigSaver

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
        self.last_command = None
        self.last_path = None
        self.worker_thread = None

rc_context = None

app = Flask("nanorc_rest_api")
api = Api(app)

def convert_nanorc_return_code(return_code:int):
    return 200 if return_code == 0 else 500

def validatePath(rc, prompted_path):
    hierarchy = []
    if "/" in prompted_path:
        hierarchy = prompted_path.split("/")

    topnode = rc.topnode

    r = Resolver('name')
    try:
        node = r.get(topnode, prompted_path)
    except Exception as ex:
        raise RuntimeError(f"Couldn't find {prompted_path} in the tree") from ex

    return hierarchy

@api.resource('/nanorcrest/status', methods=['GET'])
class status(Resource):
    @auth.login_required
    def get(self):
        if rc_context.worker_thread and rc_context.worker_thread.is_alive():
            return "I'm busy!"
        else:
            data = rc_context.rc.status_data()
            resp = make_response(jsonify(data))
            return resp

@api.resource('/nanorcrest/node/<path>', methods=['GET'])
class node(Resource):
    @auth.login_required
    def get(self, path):
        path = "/"+path.replace(".", "/")
        try:
            path = validatePath(rc_context.rc, path)
        except Exception as ex:
            resp = make_response(f"Couldn't find {path} in the tree")
            return resp

        r = Resolver('name')
        path = "/".join(path)
        node = r.get(rc_context.rc.topnode, path)
        data = node.node_status_data()
        resp = make_response(data, 200)
        return resp

@api.resource('/nanorcrest/tree', methods=['GET'])
class tree(Resource):
    @auth.login_required
    def get(self):
        if rc_context.rc.topnode:
            exporter = DictExporter(attriter=lambda attrs: [(k, v) for k, v in attrs if k == "name"])
            json_tree = exporter.export(rc_context.rc.topnode)
            resp = make_response(jsonify(json_tree))
            return resp
        return "No tree initialised!"
    
@api.resource('/nanorcrest/fsm', methods=['GET'])
class fsm(Resource):
    @auth.login_required
    def get(self):
        topnode = rc_context.rc.topnode
        if topnode:
            fsm_data = {'states': topnode.fsm.states_cfg,
                        'transitions': topnode.fsm.transitions_cfg
                        }
            resp = make_response(jsonify(fsm_data))
            return resp
        return "No FSM initiated!"

@api.resource('/nanorcrest/command', methods=['POST', 'GET'])
class command(Resource):
    @auth.login_required
    def get(self):
        resp_data = {
            "command": rc_context.last_command,
            "path"   : rc_context.last_path,
        }
        print(f"nanorcrest.command.get {jsonify(resp_data)}")
        return make_response(jsonify(resp_data))

    @auth.login_required
    def post(self):
        if rc_context.worker_thread and rc_context.worker_thread.is_alive():
            return "busy!"
        try:
            cmd  = request.form['command'].lower()
            path = request.form.get('path')
            data = request.form.get('data')
            
            target=getattr(rc_context.rc, cmd) # anyway to makethis clean??
            if not target:
                raise RuntimeError(f'I don\'t know of command {cmd}')
            
            logger = logging.getLogger()
            if os.path.isfile('rest_command.log'):
                os.remove('rest_command.log')
            log_handle = logging.FileHandler("rest_command.log")
            logger.addHandler(log_handle)
            
            if cmd == 'boot' or cmd == 'terminate' or cmd == 'stop':
                rc_context.worker_thread = threading.Thread(target=target,
                                                            name="command-worker")

            elif cmd == 'START':
                run_type = request.form['run_type']
                rc_context.rc.run_num_mgr.set_run_number(int(request.form['run_num']))

                disable_data_storage = False
                if request.form.get('disable_data_storage'):
                    disable_data_storage = request.form.get('disable_data_storage')
                args = [disable_data_storage, run_type]

                if request.form.get('trigger_interval_ticks'):
                    args.append(request.form['trigger_interval_ticks'])

                rc_context.worker_thread = threading.Thread(target=target,
                                                            name="command-worker",
                                                            args=args)

            elif cmd == 'RESUME':
                args = []

                if request.form.get('trigger_interval_ticks'):
                    args.append(request.form['trigger_interval_ticks'])

                rc_context.worker_thread = threading.Thread(target=target,
                                                            name="command-worker",
                                                            args=args)
                
            else:
                if not path:
                    path = rc_context.rc.topnode.name
                path = validatePath(rc_context.rc, path)
                
                rc_context.worker_thread = threading.Thread(target=target, name="command-worker", args=[path])
            rc_context.worker_thread.start()
            
            rc_context.worker_thread.join()
            rc_context.last_command = cmd
            rc_context.last_path = path

            logger.removeHandler(log_handle)
            logs = open('rest_command.log').read()
            
            resp_data = {
                "command"    : cmd,
                "path"       : path,
                "return_code": rc_context.rc.return_code,
                "logs"       : logs
            }
            resp = make_response(resp_data)
            return resp
        
        except Exception as e:
            print(e)
            resp = make_response(jsonify({"Exception": str(e)}))
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
@click.option('--log-path', type=click.Path(exists=True), default=None, help='Where the logs should go (on localhost of applications)')
@click.option('--kerberos/--no-kerberos', default=True, help='Whether you want to use kerberos for communicating between processes')
@click.option('--logbook-prefix', type=str, default="logbook", help='Prefix for the logbook file')
@click.option('--host', type=str, default="0.0.0.0", help='Which host the rest API should run')
@click.option('--port', type=int, default=5001, help='which port to use')
@click.argument('top_cfg', type=click.Path(exists=True))
@click.pass_obj
@click.pass_context
def cli(ctx, obj, traceback, loglevel, timeout, cfg_dumpdir, log_path, logbook_prefix, kerberos, host, port, top_cfg):

    obj.print_traceback = traceback

    grid = Table(title='Shonky API NanoRC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nano RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row("Use it with care!")

    obj.console.print(Panel.fit(grid))

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
        obj.console.log(f"Starting up on {host}:{port}")
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
