from .statefulnode import StatefulNode
from .node import SubsystemNode
from .cfgmgr import ConfigManager
import os
import copy as cp
import json
from pathlib import Path
from urllib.parse import ParseResult
from collections import OrderedDict
from json import JSONDecoder
from pathlib import Path
from anytree import PreOrderIter

def dict_raise_on_duplicates(ordered_pairs):
    count=0
    d=OrderedDict()
    for k,v in ordered_pairs:
        if k in d:
            raise RuntimeError(f"Duplicated entries \"{k}\"")
        else:
            d[k]=v
    return d

class ConfigManagerCreationFailed(Exception):
    """The creation of a configuration node failed """
    pass
    def __init__(self, node):
        self.node = node
        super().__init__(f"Failed to build configuration manager for node '{node}'")


class TreeBuilder:
    def extract_json_to_nodes(self, js, mother, fsm_conf) -> StatefulNode:
        for n,d in js.items():
            if isinstance(d, dict):
                child = StatefulNode(
                    name=n,
                    parent=mother,
                    console=self.console,
                    fsm_conf = fsm_conf
                )

                self.extract_json_to_nodes(d, child, fsm_conf = fsm_conf)

            elif isinstance(d, ParseResult):
                try:
                    cfgmgr = ConfigManager(
                        log = self.log,
                        process_manager_description = self.process_manager_description,
                        config_url = d,
                        session = self.session,
                        port_offset = self.port_offset+self.subsystem_port_offset,
                        upload_to = self.conf_server
                    )
                except Exception as e:
                    raise ConfigManagerCreationFailed(n) from e

                node = SubsystemNode(
                    name = n,
                    log = self.log,
                    cfgmgr = cfgmgr,
                    console = self.console,
                    fsm_conf = fsm_conf,
                    parent = mother
                )
                self.subsystem_port_offset += self.subsystem_port_increment
            else:
                self.log.error(f"ERROR processing the tree {n}: {d} I don't know what that's supposed to mean?")
                exit(1)

    def get_custom_commands(self):
        ret = {}
        for node in PreOrderIter(self.topnode):
            if node == self.topnode:
                continue

            for cmd, data in node.get_custom_commands().items():
                if cmd not in ret:
                    ret[cmd] = {}

                for app_name, cmd_data in data.items():
                    ret[cmd][f'{self.apparatus_id}/{node.name}/{app_name}'] = cmd_data
        return ret

    def terminate(self):
        self.conf_server.terminate()

    def __init__(self, log, top_cfg, process_manager_description, fsm_conf, console, port_offset, session):
        self.session = session
        self.log = log
        self.process_manager_description = process_manager_description
        self.fsm_conf = fsm_conf
        self.port_offset = port_offset
        self.subsystem_port_offset = 0
        self.subsystem_port_increment = 50
        from .confserver import ConfServer
        self.conf_server = ConfServer(8547+port_offset)
        self.apparatus_id, self.top_cfg = TreeBuilder.get_apparatus_and_config(top_cfg)

        self.console = console

        self.apparatus_id = self.top_cfg.get("apparatus_id")

        if self.apparatus_id:
            del self.top_cfg['apparatus_id']
        else:
            self.apparatus_id = top_cfg.replace('.json', '')

        cmd_order = self.top_cfg.get('command_order')
        if cmd_order:
            del self.top_cfg['command_order']

        self.topnode = StatefulNode(
            self.apparatus_id,
            console=self.console,
            log=self.log,
            fsm_conf=self.fsm_conf,
            order=cmd_order,
            verbose=True,
        )

        self.extract_json_to_nodes(
            self.top_cfg,
            self.topnode,
            fsm_conf=self.fsm_conf
        )


    @staticmethod
    def get_apparatus_and_config(input):
        import logging
        log = logging.getLogger('get_apparatus_and_config')

        match input.scheme:
            case 'file':
                apparatus_id = Path(input.path).name
                data = {
                    "apparatus_id": apparatus_id,
                    apparatus_id: input
                }
                return apparatus_id, data

            case 'topjson':
                from .argval import validate_conf
                f = open(input.path)
                data = {}
                try:
                    data = json.load(f)
                except Exception as e:
                    log.error(f'Couldn\'t parse top json: {str(e)}')
                    exit(1)
                if not 'apparatus_id' in data:
                    log.error(f'\'{input}\' does not have an \'apparatus_id\' entry')
                    exit(1)

                data_cp = cp.deepcopy(data)

                for key, val in data.items():
                    if key=='apparatus_id':
                        continue
                    try:
                        data_cp[key] = validate_conf(None, None, val)
                    except Exception as e:
                        log.error(f'Error parsing the line {key}:{val} of the configuration: {e}')

                return apparatus_id, data_cp

            case 'db':
                pretty_name = input.netloc
                data = {
                    "apparatus_id": pretty_name,
                    pretty_name: input
                }
                return pretty_name, data

            case _:
                log.error(f"'{input}' invalid! You must provide either a top level json file, a directory name, or confservice:configuration")
                exit(1)



    # This should get changed so that it copies the node, and strips the config
    def get_tree_structure(self):
        return self.topnode
