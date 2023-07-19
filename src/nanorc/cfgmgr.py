import os.path
import os
import tempfile
import json
import copy as cp
import socket
import requests
import importlib.resources as resources
from . import confdata
from urllib.parse import urlparse

class SessionNamespaceIncompatible(Exception):
    def __init__(self, namespace, session, conf):
        super().__init__(f'Session "{session}" and namespace "{namespace}" (in your configuration "{conf}") incompatible')


class WrongConfigurationType(Exception):
    def __init__(self, conf, pm):
        super().__init__(f'The configuration "{conf.geturl()}" is incompatible with the "{pm}" process manager')


class ConfigManager:

    def __init__(self, log, config_url, process_manager_description, port_offset=0, session=None, upload_to=None):
        super().__init__()
        self.process_manager_description = process_manager_description
        self.log = log
        self.conf_str = ''
        self.boot = {}
        self.port_offset = port_offset
        self.scheme = None
        self.expected_std_cmds = ['init', 'conf']
        self.conf_server = upload_to
        self.conf_data, self.config_query_string = self.fetch_configuration(config_url)
        self.log.debug(f'"{config_url.path}" content: {list(self.conf_data.keys())}')

        self._ensure_conf_pm_consistency(
            self.conf_data,
            self.process_manager_description,
            config_url
        )
        self._ensure_conf_session_consistency(
            self.conf_data,
            session,
            config_url
        )

        self.boot = self._load_boot(
            self.conf_data,
            port_offset,
            resolve_hostname = not process_manager_description.use_k8spm()
        )
        self._log_diff('NanoRC\'s boot parsing', self.boot, self.conf_data['boot'])

        if process_manager_description.use_sshpm():
            new_data = self._offset_ports(self.conf_data)
            self._log_diff('NanoRC\'s port offsetting', self.conf_data, new_data)
            self.conf_data = new_data

            new_data = self._resolve_hostnames(self.conf_data)
            self._log_diff('NanoRC\'s host resolution', self.conf_data, new_data)
            self.conf_data = new_data

        self.custom_commands = self._get_custom_commands_from_dict(self.conf_data)
        from nanorc.utils import get_random_string
        config_url._replace(scheme = '')
        config_url = config_url.path.split('/')[-1].replace('_', '-').replace(':', '').replace('.', '').lower()+'-'+get_random_string(5) # ensure no 2 config will be the same
        self.conf_server.add_configuration_data(config_url, self.conf_data)
        self.conf_url = f'{self.conf_server.get_conf_address_prefix()}?name={config_url}'

    def _log_diff(self, title, dict_new, dict_old):
        from deepdiff import DeepDiff
        dd = DeepDiff(dict_new, dict_old)
        dd = dd.to_json()
        self.log.debug(f'{title}:\n{json.dumps(json.loads(dd), indent=4)}')


    def _ensure_conf_pm_consistency(self, data, pm, conf_name):
        attributes_for_k8s = [
            'boot.exec.daq_application_k8s',
        ]
        attributes_for_ssh = [
            'boot.hosts-ctrl',
            'boot.hosts-data'
        ]

        def key_present(key, jsond):
            keys = key.split('.')
            primary = keys[0]

            if len(keys) == 1:
                ret = primary in jsond
                return ret

            rest = '.'.join(keys[1:])
            if primary in jsond:
                return key_present(rest, jsond[primary])
            return False

        if pm.use_k8spm():
            for k8s_attr in attributes_for_k8s:
                if not key_present(k8s_attr, data):
                    raise WrongConfigurationType(conf_name, 'k8s')

        if pm.use_sshpm():
            for ssh_attr in attributes_for_ssh:
                if not key_present(ssh_attr, data):
                    raise WrongConfigurationType(conf_name, 'ssh')


    def _ensure_conf_session_consistency(self, data, session, conf_name):
        if session and data.get('boot', {}).get('k8s_namespace', None):
            if session != self.boot['k8s_namespace']:
                raise SessionNamespaceIncompatible(self.boot['k8s_namespace'], session, conf_name)


    def fetch_configuration(self, config_url):
        if config_url.scheme == 'db':
            return self.fetch_from_configuration_db_service(config_url)
        else:
            return self.fetch_from_file_system(config_url)


    def fetch_from_configuration_db_service(self,config_url):
        self.log.info(f'Using the configuration service to grab \'{config_url.netloc}\'')

        conf_service={}
        with resources.path(confdata, "config_service.json") as p:
            conf_service = json.load(open(p,'r'))
        svc_url = conf_service['socket']

        version = config_url.query
        conf_name = config_url.netloc
        r = None

        if version:
            self.log.info(f'Using version {version} of \'{conf_name}\'.')
            conf_query_str = svc_url+'/retrieveVersion?name='+conf_name+'&version='+version
        else:
            self.log.info(f'Using latest version of \'{conf_name}\'.')
            conf_query_str = svc_url+'/retrieveLast?name='+conf_name

        try:
            self.log.debug(f'Configuration request: http://{conf_query_str}')
            r = requests.get("http://"+conf_query_str)
            if r.status_code == 200:
                return (r.json(), conf_query_str)
            else:
                raise RuntimeError(f'Couldn\'t get the configuration {conf_name} from {svc_url}')

        except Exception as e:
            if r:
                self.log.error(f'Couldn\'t get the configuration from the conf service (http://{self.conf_str})\nService response: {json.loads(r.text).get("message",r.text)}\nException: {str(e)}')
            else:
                self.log.error(f'Something went horribly wrong while getting http://{self.conf_str}\nException: {str(e)}')
            exit(1)


    def fetch_from_file_system(self,config_url):
        from .utils import get_json_recursive
        return (get_json_recursive(config_url.path), f'file://{config_url.path}')


    def _import_data(self, cfg_path: dict) -> dict:
        if not os.path.exists(cfg_path):
            raise RuntimeError(f"ERROR: {cfg_path} not found")

        with open(cfg_path, "r") as jf:
            try:
                return json.load(jf)
            except json.decoder.JSONDecodeError as e:
                raise RuntimeError(f"ERROR: failed to load {cfg_path}") from e

    def _get_custom_commands_from_dict(self, data:dict):
        from collections import defaultdict
        custom_cmds = defaultdict(list)

        for app_name, app_data in data.items():
            if app_data is not dict: continue
            for command_name, command_data in app_data.items():
                if command_name in self.expected_std_cmds:
                    continue
                custom_cmds[app_name].append(command_data)

        return custom_cmds


    # def _get_custom_commands_from_dirs(self, path:str):
    #     from collections import defaultdict
    #     custom_cmds = defaultdict(list)
    #     for cmd_file in os.listdir(path+'/data'):
    #         std_cmd_flag = False
    #         for std_cmd in self.expected_std_cmds:
    #             if std_cmd+".json" in cmd_file:
    #                 std_cmd_flag = True
    #                 break # just a normal command

    #         if std_cmd_flag:
    #             continue

    #         cmd_name = '_'.join(cmd_file.split('_')[1:]).replace('.json', '')
    #         custom_cmds[cmd_name].append(json.load(open(path+'/data/'+cmd_file, 'r')))

        return custom_cmds

    def get_custom_commands(self):
        return self.custom_commands


    def _resolve_hostnames(self, conf_data):
        conf_port_host_resolved = cp.deepcopy(conf_data)

        hosts = self.boot.get('hosts-data',{})
        from nanorc.utils import parse_string

        for app_name, app_data in conf_port_host_resolved.items():
            if not type(app_data) == dict:
                continue

            if not 'init' in app_data:
                continue

            init_data = app_data['init']

            if not "connections" in init_data:
                return conf_data

            for connection in init_data['connections']:
                if "queue://" in connection['uri']:
                    continue

                origuri = connection['uri']
                connection['uri'] = parse_string(connection['uri'], hosts)
                self.log.debug(f" - '{connection['id']['uid']}': {connection['uri']} ({origuri})")

            conf_port_host_resolved[app_name]['init'] = init_data

        return conf_port_host_resolved


    def _offset_ports(self, conf_data):
        conf_port_offset = cp.deepcopy(conf_data)
        external_connections = self.boot.get('external_connections', [])

        for app_name, app_data in conf_port_offset.items():
            if not type(app_data) == dict:
                continue

            if not 'init' in app_data:
                continue

            init_data = app_data['init']
            if not "connections" in init_data:
                continue

            for connection in init_data['connections']:
                if "queue://" in connection['uri']:
                    continue

                if not connection['id']['uid'] in external_connections:
                    try:
                        port = urlparse(connection['uri']).port
                        newport = port + self.port_offset
                        connection['uri'] = connection['uri'].replace(str(port), str(newport))
                        self.log.debug(f" - '{connection['id']['uid']}': {connection['uri']}")
                    except Exception as e:
                        self.log.debug(f" - '{connection['id']['uid']}' ('{connection['uri']}') port wasn\'t offset, reason: {str(e)}")

            conf_port_offset[app_name]['init'] = init_data

        return conf_port_offset



    def _load_boot(self, config, port_offset, resolve_hostname):
        boot = cp.deepcopy(config['boot'])

        if resolve_hostname:
            boot["hosts-ctrl"] = {
                n: (h if (not h in ("localhost", "127.0.0.1")) else socket.gethostname())
                for n, h in boot["hosts-ctrl"].items()
            }

        #port offseting
        if "services" in boot:
            for app in boot["services"]:
                port = boot['services'][app]['port']
                newport = port + port_offset
                boot['services'][app]['port'] = newport
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


    def get_conf_location(self, for_apps) -> str:
        if for_apps: return "db://"+self.conf_url
        else:        return "http://"+self.conf_url


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
