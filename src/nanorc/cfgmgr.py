import os.path
import json
from pathlib import Path
import copy
import socket
import requests
import importlib.resources as resources
import tempfile
from . import confdata
from urllib.parse import urlparse

"""Extract nested values from a JSON tree."""


def json_extract(obj, key):
    """Recursively fetch values from nested JSON."""
    arr = []

    def extract(obj, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == key:
                    arr.append(v)
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr

    values = extract(obj, arr, key)
    return values

def dump_json_recursively(json_data, path):
    for f in json_data['files']:
        with open(path/(f['name']+'.json'), 'w') as outfile:
            json.dump(f['configuration'], outfile, indent=4)

    for d in json_data['dirs']:
        dirname = path/d['name']
        dirname.mkdir(exist_ok=True)
        dump_json_recursively(d['dir_content'], dirname)


class ConfigManager:
    """docstring for ConfigManager"""

    def __init__(self, log, config, resolve_hostname=True, port_offset=0):
        super().__init__()
        self.resolve_hostname = resolve_hostname
        self.log = log

        cfg_dir = ''

        if config.scheme == 'confservice':
            self.log.info(f'Using the configuration service to grab \'{config.netloc}\'')

            conf_service={}
            with resources.path(confdata, "config_service.json") as p:
                conf_service = json.load(open(p,'r'))
            url = conf_service['socket']

            version = config.query
            conf_name = config.netloc
            r = None
            if version:
                self.log.info(f'Using version {version} of \'{conf_name}\'.')
                r = requests.get('http://'+url+'/retrieveVersion?name='+conf_name+'&version='+version)
            else:
                self.log.info(f'Using latest version of \'{conf_name}\'.')
                r = requests.get('http://'+url+'/retrieveLast?name='+conf_name)

            try:
                if r.status_code == 200:
                    config = json.loads(r.json())
                    path = Path(tempfile.mkdtemp())
                    dump_json_recursively(config, path)
                    cfg_dir = path
            except:
                self.log.error(f'Couldn\'t get/parse the configuration from the conf service.\nHTTP response: {r.status_code}, body: {r.json()}\nAre you sure the configuration \'{conf_name}\' exist?')
                exit(1)
        else:
            cfg_dir = config.path

        cfg_dir = os.path.expandvars(cfg_dir)

        if not (os.path.exists(cfg_dir) and os.path.isdir(cfg_dir)):
            raise RuntimeError(f"'{cfg_dir}' does not exist or is not a directory")

        self.cfg_dir = cfg_dir
        self.port_offset = port_offset
        self._load()

    def _import_cmd_data(self, cmd: str, cfg: dict) -> None:
        data = {}
        for f in set(cfg["apps"].values()):
            fpath = os.path.join(self.cfg_dir, f + ".json")
            if not os.path.exists(fpath):
                raise RuntimeError(f"ERROR: {f}.json not found in {self.cfg_dir}")

            with open(fpath, "r") as jf:
                try:
                    j = json.load(jf)
                    data[f] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {f}.json") from e

        x = {a: data[d] for a, d in cfg["apps"].items()}
        setattr(self, cmd, x)

        if "order" in cfg:
            setattr(self, f"{cmd}_order", cfg["order"])

    def get_custom_commands(self):
        ret = {}
        for cmd in self.extra_cmds.keys():
            ret[cmd] = getattr(self, cmd)
        return ret

    def _load(self) -> None:

        pm_cfg = ["boot"]
        rc_cmds = ["init", "conf", "start", "stop", "pause", "resume", "scrap"]
        cfgs = {}
        for f in pm_cfg + rc_cmds:
            fpath = os.path.join(self.cfg_dir, f + ".json")
            if not os.path.exists(fpath):
                raise RuntimeError(f"ERROR: {f}.json not found in {self.cfg_dir}")

            with open(fpath, "r") as jf:
                try:
                    j = json.load(jf)
                    cfgs[f] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {f}.json") from e

        self.boot = cfgs["boot"]

        json_files = [f for f in os.listdir(self.cfg_dir) if os.path.isfile(os.path.join(self.cfg_dir, f)) and '.json' in f]
        self.extra_cmds = {}

        for json_file in json_files:
            cmd = json_file.split(".")[0]

            if cmd in rc_cmds+pm_cfg:
                continue

            with open(os.path.join(self.cfg_dir,json_file), 'r') as jf:
                try:
                    j = json.load(jf)
                    cfgs[cmd] = j
                    self.extra_cmds[cmd] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {cmd}.json") from e

        for c in rc_cmds+list(self.extra_cmds.keys()):
            self._import_cmd_data(c, cfgs[c])

        # Post-process conf
        # Boot:
        self.boot["hosts"] = {
            n: (h if (not h in ("localhost", "127.0.0.1")) else socket.gethostname())
            for n, h in self.boot["hosts"].items()
        }

        #port offseting
        for app in self.boot["apps"]:
            port = self.boot['apps'][app]['port']
            newport = port + self.port_offset
            self.boot['apps'][app]['port'] = newport

        self.boot['response_listener']['port'] += self.port_offset

        ll = { **self.boot["env"] }  # copy to avoid RuntimeError: dictionary changed size during iteration
        for k, v in ll.items():
            if v == "getenv_ifset":
                if k in os.environ.keys():
                    self.boot["env"][k] = os.environ[k]
                else:
                    self.boot["env"].pop(k)
            elif str(v).find("getenv") == 0:
                if k in os.environ.keys():
                    self.boot["env"][k] = os.environ[k]
                elif str(v).find(":") > 0:
                    self.boot["env"][k] = v[v.find(":") + 1:]
                else:
                    raise ValueError("Key " + k + " is not in environment and no default specified!")
        if self.boot.get('scripts'):
            for script_spec in self.boot["scripts"].values():
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

        for exec_spec in self.boot["exec"].values():
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

        # Conf:
        external_connections = self.boot['external_connections']
        hosts = self.boot["hosts"]

        for connections in json_extract(self.init, "connections"):
            for c in connections:
                if "queue://" in c['uri']:
                    continue
                from string import Formatter
                origuri = c['uri']
                fieldnames = [fname for _, fname, _, _ in Formatter().parse(c['uri']) if fname]

                if len(fieldnames)>1:
                    raise RuntimeError(f"Too many fields in connection {c['uri']}")

                for fieldname in fieldnames:
                    try:
                        if self.resolve_hostname: # replace host_ruemu0 by np04-srv-XXX (ssh)
                            dico = {"HOST_IP": hosts[fieldname]}
                        else: # relace by host_ruemu0 by ruemu0 (K8s)
                            dico = {"HOST_IP": fieldname.replace('host_', '')}

                        c['uri'] = c['uri'].replace(fieldname, "HOST_IP").format(**dico)
                    except Exception as e:
                        raise RuntimeError(f"Couldn't find the IP of {fieldname}. Aborting") from e

                if not c['uid'] in external_connections: # TODO: ignore this altogether with k8s
                    # Port offsetting
                    port = urlparse(c['uri']).port
                    newport = port + self.port_offset
                    c['uri'] = c['uri'].replace(str(port), str(newport))
                self.log.debug(f"{c['uid']}: {c['uri']}")


    def runtime_start(self, data: dict) -> dict:
        """
        Generates runtime start parameter set
        :param      data:  The data
        :type       data:  dict

        :returns:   Complete parameter set.
        :rtype:     dict
        """

        start = copy.deepcopy(self.start)

        for c in json_extract(start, "modules"):
            for m in c:
                m["data"].update(data)
        return start

    def runtime_resume(self, data: dict) -> dict:
        """
        Generates runtime resume parameter set
        :param      data:  The data
        :type       data:  dict

        :returns:   Complete parameter set.
        :rtype:     dict
        """
        resume = copy.deepcopy(self.resume)

        for c in json_extract(resume, "modules"):
            for m in c:
                m["data"].update(data)
        return resume



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

    console.print("Start data V:runner:")
    console.print(Pretty(cfg.runtime_start({"aa": "bb"})))
