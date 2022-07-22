from string import Template
import os.path
import os
import tempfile
import json
from pathlib import Path
import copy
import socket
import requests
import importlib.resources as resources
from . import confdata
from urllib.parse import urlparse

def parse_string(string_to_format:str, dico:dict={}) -> str:
    from string import Formatter
    fieldnames = [fname for _, fname, _, _ in Formatter().parse(string_to_format) if fname]

    if len(fieldnames)>1:
        raise RuntimeError(f"Too many fields in string {string_to_format}")
    elif len(fieldnames)==0:
        return string_to_format

    fieldname = fieldnames[0]
    try:
        string_to_format = string_to_format.format(**dico)
    except Exception as e:
        raise RuntimeError(f"Couldn't find the IP of {fieldname}. Aborting") from e

    return string_to_format

class ConfigManager:

    def __init__(self, log, config, resolve_hostname=True, port_offset=0):
        super().__init__()
        self.conf_dirs = []
        self.resolve_hostname = resolve_hostname
        self.log = log
        self.conf_str = ''
        self.boot = {}
        self.port_offset = port_offset
        self.tmp = None # hack
        self.scheme = None
        self.expected_std_cmds = ['init', 'conf']

        self.scheme = config.scheme+'://'
        if config.scheme == 'db':
            self.log.info(f'Using the configuration service to grab \'{config.netloc}\'')

            conf_service={}
            with resources.path(confdata, "config_service.json") as p:
                conf_service = json.load(open(p,'r'))
            url = conf_service['socket']

            version = config.query
            conf_name = config.netloc
            r = None
            request_uri = ""
            if version:
                self.log.info(f'Using version {version} of \'{conf_name}\'.')
                self.conf_str = url+'/retrieveVersion?name='+conf_name+'&version='+version
            else:
                self.log.info(f'Using latest version of \'{conf_name}\'.')
                self.conf_str = url+'/retrieveLast?name='+conf_name

            try:
                self.log.debug(f'Configuration request: http://{self.conf_str}')
                r = requests.get("http://"+self.conf_str)
                if r.status_code == 200:
                    config = r.json()
                    self.boot = self.load_boot(config['boot'], self.port_offset, False)
                    self.boot['response_listener']['port'] += self.port_offset
                    # hack
                    self.data = config
                else:
                    raise RuntimeError(f'Couldn\'t get the configuration {conf_name}')
            except:
                if r:
                    self.log.error(f'Couldn\'t get the configuration from the conf service (http://{self.conf_str})\nService response: {json.loads(r.text).get("message",r.text)}')
                else:
                    self.log.error(f'Something went horribly wrong while getting http://{self.conf_str}')
                exit(1)
            self.custom_commands = self._get_custom_commands_from_dict(self.data)
        else:
            self.scheme = 'file://'
            conf_path = os.path.expandvars(config.path)

            if not (os.path.exists(conf_path) and os.path.isdir(conf_path)):
                raise RuntimeError(f"'{conf_path}' does not exist or is not a directory")

            boot = self._import_data(Path(conf_path)/'boot.json')
            self.boot = self.load_boot(boot, self.port_offset, True)
            self.boot['response_listener']['port'] += self.port_offset
            self.conf_str = self._resolve_dir_and_save_to_tmpdir(
                conf_path = Path(conf_path)/'data',
                hosts = self.boot["hosts"],
                port_offset = self.port_offset
            )
            self.custom_commands = self._get_custom_commands_from_dirs(conf_path)

    def _import_data(self, cfg_path: dict) -> None:
        data = {}
        if not os.path.exists(cfg_path):
            raise RuntimeError(f"ERROR: {cfg_path} not found")

        with open(cfg_path, "r") as jf:
            try:
                return json.load(jf)
            except json.decoder.JSONDecodeError as e:
                raise RuntimeError(f"ERROR: failed to load {fpath}") from e

    def _get_custom_commands_from_dict(self, data:dict):
        from collections import defaultdict
        custom_cmds = defaultdict(list)
        for app in data.keys():
            if data.get('conf'):
                for key, value in data[app].items():
                    if key in self.expected_std_cmds: continue # normal command
                    custom_cmds[key].append(value)

        return custom_cmds


    def _get_custom_commands_from_dirs(self, path:str):
        from collections import defaultdict
        custom_cmds = defaultdict(list)
        for cmd_file in os.listdir(path+'/data'):
            std_cmd_flag = False
            for std_cmd in self.expected_std_cmds:
                if std_cmd+".json" in cmd_file:
                    std_cmd_flag = True
                    break # just a normal command

            if std_cmd_flag:
                continue

            cmd_name = '_'.join(cmd_file.split('_')[1:]).replace('.json', '')
            custom_cmds[cmd_name].append(json.load(open(path+'/data/'+cmd_file, 'r')))

        return custom_cmds

    def get_custom_commands(self):
        return self.custom_commands


    def _resolve_dir_and_save_to_tmpdir(self, conf_path, hosts:dict, port_offset:int=0) -> None:
        if not os.path.exists(conf_path):
            raise RuntimeError(f"ERROR: {conf_path} does not exist!")

        external_connections = self.boot['external_connections']

        self.tmp = tempfile.TemporaryDirectory(
            dir=os.getcwd(),
            prefix='nanorc-flatconf-',
        )

        for original_file in os.listdir(conf_path):
            data = self._import_data(conf_path/original_file)
            self.log.debug(f"Original conections in '{conf_path/original_file}':")
            data = self._resolve_hostnames(data, hosts)
            if port_offset:
                self.log.debug(f"Offsetting the ports by {port_offset}, new connections:")
                data = self._offset_ports(data, external_connections)

            with open(os.path.join(self.tmp.name, original_file), 'w') as parsed_file:
                json.dump(data, parsed_file, indent=4, sort_keys=True)

        return os.path.join(os.getcwd(), self.tmp.name)

    def _resolve_hostnames(self, data, hosts):

        if not "connections" in data:
            return data

        for connection in data['connections']:
            if "queue://" in connection['uri']:
                continue

            origuri = connection['uri']
            connection['uri'] = parse_string(connection['uri'], hosts)
            self.log.debug(f" - '{connection['uid']}': {connection['uri']} ({origuri})")
        return data


    def _offset_ports(self, data, external_connections):

        if not "connections" in data:
            return data

        for connection in data['connections']:
            if "queue://" in connection['uri']:
                continue

            if not connection['uid'] in external_connections:
                port = urlparse(connection['uri']).port
                newport = port + self.port_offset
                connection['uri'] = connection['uri'].replace(str(port), str(newport))
                self.log.debug(f" - '{connection['uid']}': {connection['uri']}")

        return data



    def load_boot(self, boot, port_offset, resolve_hostname):
        if self.resolve_hostname:
            boot["hosts"] = {
                n: (h if (not h in ("localhost", "127.0.0.1")) else socket.gethostname())
                for n, h in boot["hosts"].items()
            }

        #port offseting
        for app in boot["apps"]:
            port = boot['apps'][app]['port']
            newport = port + port_offset
            boot['apps'][app]['port'] = newport

        boot['response_listener']['port'] += port_offset

        ll = { **boot["env"] }  # copy to avoid RuntimeError: dictionary changed size during iteration
        for k, v in ll.items():
            if v == "getenv_ifset":
                if k in os.environ.keys():
                    boot["env"][k] = os.environ[k]
                else:
                    boot["env"].pop(k)
            elif str(v).find("getenv") == 0:
                if k in os.environ.keys():
                    boot["env"][k] = os.environ[k]
                elif str(v).find(":") > 0:
                    boot["env"][k] = v[v.find(":") + 1:]
                else:
                    raise ValueError("Key " + k + " is not in environment and no default specified!")

        if boot.get('scripts'):
            for script_spec in boot["scripts"].values():
                ll = { **script_spec["env"] }  # copy to avoid RuntimeError: dictionary changed size during iteration
                for k, v in ll.items():
                    if v == "getenv_ifset":
                        if k in os.environ.keys():
                            script_spec["env"][k] = os.environ[k]
                        else:
                            script_spec["env"].pop(k)
                    elif str(v).find("getenv") == 0:
                        if k in os.environ.keys():
                            script_spec["env"][k] = os.environ[k]
                        elif str(v).find(":") > 0:
                            script_spec["env"][k] = v[v.find(":") + 1:]
                        else:
                            raise ValueError("Key " + k + " is not in environment and no default specified!")

        for exec_spec in boot["exec"].values():
            ll = { **exec_spec["env"] }  # copy to avoid RuntimeError: dictionary changed size during iteration
            for k, v in ll.items():
                if v == "getenv_ifset":
                    if k in os.environ.keys():
                        exec_spec["env"][k] = os.environ[k]
                    else:
                        exec_spec["env"].pop(k)
                elif str(v).find("getenv") == 0:
                    if k in os.environ.keys():
                        exec_spec["env"][k] = os.environ[k]
                    elif str(v).find(":") > 0:
                        exec_spec["env"][k] = v[v.find(":") + 1:]
                    else:
                        raise ValueError("Key " + k + " is not in environment and no default specified!")

        return boot


    def __del__(self):
        if self.tmp:
            self.tmp.cleanup()

    def get_conf_location(self, for_apps) -> str:
        if self.scheme == 'db://':
            if for_apps: return self.scheme+self.conf_str
            else:        return "http://"+self.conf_str
        elif self.scheme == 'file://':
            if for_apps: return self.scheme+self.conf_str
            else:        return self.conf_str

    def generate_data_for_module(self, data: dict=None, module:str="") -> dict:
        """
        Generates runtime start parameter set
        :param      data:  The data
        :type       data:  dict
        :param      module:  which module (default all)
        :type       module:  str

        :returns:   Complete parameter set.
        :rtype:     dict
        """
        if module != "":
            raise RuntimeError("cannot send data to one specific module that isn't conf of init!")

        if not data:
            return {}

        return {
            "modules": [
                {
                    "data": data,
                    "match": ""
                }
            ]
        }


if __name__ == "__main__":
    from os.path import dirname, join
    from rich.console import Console
    from rich.pretty import Pretty
    from rich.traceback import Traceback

    console = Console()
    try:
        cfg = ConfigManager(join(dirname(__file__), "examples", "minidaqapp"))
    except Exception as e:
        console.print(Traceback())

    console.print("Boot data :boot:")
    console.print(Pretty(cfg.boot))

    console.print("Init data :boot:")
    console.print(Pretty(cfg.init))

    console.print("Conf data :boot:")
    console.print(Pretty(cfg.conf))

    console.print("Start data :runner:")
    console.print(Pretty(cfg.start))
    console.print("Start order :runner:")
    console.print(Pretty(cfg.start_order))

    console.print("Stop data :busstop:")
    console.print(Pretty(cfg.stop))
    console.print("Stop order :busstop:")
    console.print(Pretty(cfg.stop_order))
