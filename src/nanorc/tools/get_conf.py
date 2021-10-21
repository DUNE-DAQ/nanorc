import os
import io
import tempfile
import tarfile
import sh
import sys
import time
import json
import cmd
import click
import os.path
import logging
import requests
from rich.table import Table
from rich.panel import Panel
from rich.console import Console
from rich.traceback import Traceback
from rich.progress import *

from nanorc.credmgr import credentials

def query(socket:str, query:str, user:str, password:str, log) -> dict:
    try:
        print(socket+query)
        r = requests.get(socket+query,
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
@click.pass_obj
def print_run_config(obj, run_number, get_config, dotnanorc):
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
    
    data = json.loads(r.text)[0][0]
    
    run_number      = data[0]
    start_timestamp = data[1]
    end_timestamp   = data[2]
    apparatus_id    = data[3]
    run_type        = data[4]
    text=f"Considering run number {run_number}"
    grid = Table(title=f'Run #{run_number}', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_column()
    grid.add_row("Run type"  , run_type       )
    grid.add_row("Start time", start_timestamp)
    grid.add_row("End time"  , end_timestamp  )
    grid.add_row("Apparatus" , apparatus_id   )
    obj.console.print(grid)

    if not get_config: return
    
    metadata_query = "runregistry/getRunBlob/"+str(run_number)
    data = query(dotnanorc["runregistrydb"]["socket"], metadata_query,
                 dotnanorc["runregistrydb"]["user"],
                 dotnanorc["runregistrydb"]["password"], log)

    f = tempfile.NamedTemporaryFile(mode="w",suffix='.tar.gz', delete=False)
    print(data.headers)
    print(type(data.text.encode('utf-8')))
    f.write(data.text)
    fname = f.name
    f.close()
    f = open(fname)
    print(f.read(2))
    print(b'0x1f0x8b')
    dir_name = tempfile.TemporaryDirectory()
    tar = tarfile.open(fname, "r:gz")
    tar.extractall(dir_name)
    tar.close()
    
    obj.console.print_json(dir_name+"/top_level.json")
    
    os.remove(fname)
    os.remove(dir_name)
    
    
class minimal_context:
    def __init__(self, console):
        self.console = console
        
def main():
    obj = minimal_context(Console())
    try:
        print_run_config(obj=obj)
    except Exception as e:
        obj.console.log("[bold red]Exception caught[/bold red]")
        obj.console.log(e)
        obj.console.print_exception()
        
if __name__ == '__main__':
    main()
