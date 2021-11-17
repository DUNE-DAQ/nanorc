import os
import io
import tempfile
import tarfile
import socket
import sh
from flask import Flask
import sys
import time
import json
import cmd
import click
import os.path
import logging
import requests
from rich.table import Table
from rich.text import Text
from rich.json import JSON
from rich.panel import Panel
from rich.console import Console
from rich.traceback import Traceback
from rich.progress import *

from nanorc.credmgr import credentials

def query(socket:str, query:str, user:str, password:str, log) -> dict:
    try:
        print(socket+"/"+query)
        r = requests.get(socket+"/"+query,
                         auth=(user,password),
                         timeout=2)
        
    except requests.HTTPError as exc:
        error = f"{__name__}: RunRegistryDB: HTTP Error (maybe failed auth, maybe ill-formed post message, ...)"
        log.error(error)
        raise RuntimeError(error) from exc
    except requests.ConnectionError as exc:
        error = f"{__name__}: Connection to {socket} wasn't successful"
        log.error(error)
        raise RuntimeError(error) from exc
    except requests.Timeout as exc:
        error = f"{__name__}: Connection to {socket} timed out"
        log.error(error)
        raise RuntimeError(error) from exc
    return r

@click.command()
@click.argument('run_number', default=None, required=False)
@click.option('--get-config', type=bool, default=True, help="whether to download the configuration and render it")
@click.option('--dotnanorc', type=click.Path(), default="~/.nanorc.json", help='A JSON file which has auth/socket for the DB services')
@click.option('--html/--no-html', default=True, help='whether we should start a little HTML server, short-lived to see the result')
@click.option('--host', type=str, default="localhost", help='Where the temp server should serve HTML')
@click.option('--port', type=int, default=5001, help='Which port the temp server should serve HTML')
@click.pass_obj
def print_run_config(obj, run_number, get_config, dotnanorc, html, host, port):
    dotnanorc = os.path.expanduser(dotnanorc)
    log = logging.getLogger("getconf")

    obj.console.print(f"[blue]Loading {dotnanorc}[/blue]")
    f = open(dotnanorc)
    dotnanorc = json.load(f)
    credentials.add_login("rundb",
                          dotnanorc["rundb"]["user"],
                          dotnanorc["rundb"]["password"])
    credentials.add_login("runregistrydb",
                          dotnanorc["runregistrydb"]["user"],
                          dotnanorc["runregistrydb"]["password"])
    log.info("RunDB socket "+dotnanorc["rundb"]["socket"])
    log.info("RunRegistryDB socket "+dotnanorc["runregistrydb"]["socket"])
    
    metadata_query = "runregistry/getRunMetaLast/1"
    if run_number:
        metadata_query = "runregistry/getRunMeta/"+str(run_number)
        
    r = query(dotnanorc["runregistrydb"]["socket"], metadata_query,
                 dotnanorc["runregistrydb"]["user"],
                 dotnanorc["runregistrydb"]["password"], log)
    
    data = json.loads(r.text)[1][0]
    keys = json.loads(r.text)[0]
    obj.console.export_html()
    zip_iterator = zip(keys, data)
    data_dict = dict(zip_iterator)
    run_number = data_dict['RUN_NUMBER']
    text=f"Considering run number {run_number}"
    grid = Table(title=f"Run #{run_number}", show_header=False, show_edge=True)
    grid.add_column()
    grid.add_column()
    for key, val in data_dict.items():
        grid.add_row(str(key), str(val))
    obj.console.print(grid)

    if not get_config: return
    obj.console.print()
    obj.console.print()
    obj.console.print()
    obj.console.print(Text("Configuration following..."))
    obj.console.print()
    obj.console.print()
    obj.console.print()
    metadata_query = "runregistry/getRunBlob/"+str(run_number)
    data = query(dotnanorc["runregistrydb"]["socket"], metadata_query,
                 dotnanorc["runregistrydb"]["user"],
                 dotnanorc["runregistrydb"]["password"], log)

    f = tempfile.NamedTemporaryFile(mode="w+b",suffix='.tar.gz', delete=False)
    f.write(data.content)
    fname = f.name
    f.close()
    # f = open(fname)
    
    with tempfile.TemporaryDirectory() as temp_name:
        tar = tarfile.open(fname, "r:gz")
        tar.extractall(temp_name)
        tar.close()
        for rootn, dirn, filen in os.walk(temp_name):
            for f in filen:
                name = os.path.join(rootn,f)
                print(name)
                try: # such a sloppy way of doing things. Get a grip man!
                    file_name = name.split(temp_name)[1]
                    file_name = "/".join(file_name.split("/")[2:])
                except:
                    file_name = name
                fi = open(name, "r")

                grid = Table(title=f"File: {file_name}", show_header=False)
                grid.add_row(JSON(fi.read()))
                obj.console.print(grid)

    if not html:
        return

    html_text = obj.console.export_html()
    class Server:
        def __init__(self, html_text, host, port):
            self.host = host
            if host == "0.0.0.0" or host == "localhost":
                self.host = socket.gethostname()
            self.port = port
            self.html_text = html_text

        def run(self):
            app = Flask(__name__)

            def index():
                return self.html_text
            

            app.add_url_rule("/", "index", index, methods=["GET"])
            app.run(host=self.host, port=self.port, debug=False, use_reloader=False)

    serv = Server(html_text, host, port)
    
    obj.console.print(f"\n\n\n\n\nYou can now navigate to:\nhttp:{serv.host}:{serv.port}\nCtrl-C when you are done!\n\n\n\n\n")
    serv.run()



class minimal_context:
    def __init__(self, console):
        self.console = console
        
def main():
    obj = minimal_context(Console(record=True))
    try:
        print_run_config(obj=obj)
    except Exception as e:
        obj.console.log("[bold red]Exception caught[/bold red]")
        obj.console.log(e)
        obj.console.print_exception()
        
if __name__ == '__main__':
    main()
