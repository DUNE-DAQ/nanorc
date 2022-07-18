import requests
from pathlib import Path
import os
import json
import click
from rich.console import Console
import importlib.resources as resources
from nanorc import confdata

console = Console()
def validate_conf_name(ctx, param, conf_name):
  import re

  pat = re.compile(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?')
  ## Nanorc-12334 allowed (with hyphen) This is straight from k8s error message when the partition name isn't right
  if not re.fullmatch(pat, conf_name):
    raise click.BadParameter(f'Name {conf_name} should be alpha-numeric-hyphen! Make sure you name has the form [a-z0-9]([-a-z0-9]*[a-z0-9])?')
  return conf_name

def get_json_recursive(path):
  data = {}
  boot = path/"boot.json"
  if os.path.isfile(boot):
    with open(boot,'r') as f:
      data['boot'] = json.load(f)

  for filename in os.listdir(path):
    if os.path.isfile(path/filename) and filename[-5:] == ".info":
      with open(path/filename,'r') as f:
        data['config_info'] = json.load(f)

  for filename in os.listdir(path/"data"):
    with open(path/'data'/filename,'r') as f:
      app_cmd = filename.replace('.json', '').split('_')
      app = app_cmd[0]
      cmd = "_".join(app_cmd[1:])

      if not app in data:
        data[app] = {
          cmd: json.load(f)
        }
      else:
        data[app][cmd]=json.load(f)


  return data


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


def main():
    try:
        upload_conf()
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        console.log(e)
        console.print_exception()

if __name__ == '__main__':
    main()
