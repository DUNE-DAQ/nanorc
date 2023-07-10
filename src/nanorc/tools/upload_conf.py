import requests
from pathlib import Path
import os
import json
import click
from rich.console import Console
import importlib.resources as resources
from nanorc import confdata
from nanorc.argval import validate_conf_name

console = Console()


@click.command()
@click.argument('json_dir', type=click.Path(exists=True), required=True)
@click.argument('name', type=str, required=True, callback=validate_conf_name)
@click.option('--url', type=str, default=None, help='Where the config service is')
@click.option('--verbose', is_flag=True, type=bool, default=False)
def upload_conf(url, json_dir, name, verbose):
    if not url:
        conf_service={}
        with resources.path(confdata, "config_service.json") as p:
            conf_service = json.load(open(p,'r'))
        url = conf_service['socket']

    docid=0
    version=0
    coll_name=0
    from nanorc.utils import get_json_recursive
    conf_data = get_json_recursive(Path(json_dir))

    header = {
        'Accept' : 'application/json',
        'Content-Type':'application/json'
    }

    response = requests.post(
        'http://'+url+'/create?collection='+name,
        headers=header,
        data=json.dumps(conf_data)
    )

    if response.status_code == 200:
      resp_data = response.json()

      if verbose:
          console.log(f"conf service responded with {resp_data}")
      if not resp_data['success']:
          raise RuntimeError(f'Couldn\'t upload your configuration: {resp_data["error"]}')

      docid=resp_data['docid']
      version=resp_data['version']
      coll_name=resp_data['coll_name']

      console.log(f'Uploaded [blue]{json_dir}[/blue] to the configuration service (url: \'{url}\') with name: [blue]{name}[/blue], version: [blue]{version}[/blue]')

      return docid, coll_name, version
    else:
      console.log(f'[red bold]Couldn\'t upload {json_dir} to the configuration service (url: \'{url}\') with name: {name}[/red bold]')


def main():
  try:
    upload_conf()
  except Exception as e:
    console.log("[bold red]Exception caught[/bold red]")
    console.log(e)
    console.print_exception()

if __name__ == '__main__':
  main()
