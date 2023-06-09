import logging
import click
from rich.console import Console
from flask_restful import Resource
from flask import request, abort, make_response, jsonify

conf_data = {}
log = logging.getLogger('nano-conf-service')
console = Console()


def validate_conf_name(ctx, param, conf_name):
  import re

  pat = re.compile(r'[a-z0-9]([-a-z0-9]*[a-z0-9])?')
  ## Nanorc-12334 allowed (with hyphen) This is straight from k8s error message when the partition name isn't right
  if not re.fullmatch(pat, conf_name):
    raise click.BadParameter(f'Name {conf_name} should be alpha-numeric-hyphen! Make sure you name has the form [a-z0-9]([-a-z0-9]*[a-z0-9])?')
  return conf_name


def get_json_recursive(path):
  import json, os

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

'''
Resources for Flask app
'''
class RetrieveConf(Resource):
  def get(self):
    log.debug(f'GET "RetrieveConf" request with args: {request.args}')
    name = request.args.get('name')

    if not name:
      abort(404, description=f'You need to provide a configuration name!')

    log.debug(f"Looking for config {name}")

    if name not in conf_data:
      abort(404, description=f'Couldn\'t find the configuration \"{name}\", available configurations are {list(conf_data.keys())}')

    import flask
    return make_response(jsonify(conf_data[name]))

class ListConf(Resource):
  def get(self):
    log.debug(f'GET "RetrieveConf" request')
    return make_response(jsonify(list(conf_data.keys())))



def start_service(port):
  from flask import Flask
  from flask_restful import Api
  app = Flask('nano-conf-svc')
  api = Api(app)
  api.add_resource(RetrieveConf, "/retrieveLast", methods=['GET'])
  api.add_resource(ListConf    , "/listConf"    , methods=['GET'])
  app.run (
    host = '0.0.0.0',
    port = port,
    debug = True
  )

@click.command()
@click.argument('json_dir', type=click.Path(exists=True), required=True)
@click.argument('name', type=str, required=True, callback=validate_conf_name)
@click.option('--port', type=int, default=None, help='Where the port for the service will be')
@click.option('--verbose', is_flag=True, type=bool, default=False)
def svc(json_dir, name, port, verbose):
  if name in conf_data:
    raise RuntimeError(f'Configuration name \"{name}\" is already in the conf service.')

  from pathlib import Path

  conf_data[name] = get_json_recursive(Path(json_dir))
    header = {
    'Accept' : 'application/json',
    'Content-Type':'application/json'
   }

  start_service(port)

def main():
  try:
    svc()
  except Exception as e:
    console.log("[bold red]Exception caught[/bold red]")
    console.log(e)
    console.print_exception()

if __name__ == '__main__':
  main()
