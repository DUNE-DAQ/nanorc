from .statefulnode import StatefulNode
from .node import SubsystemNode
from .cfgmgr import ConfigManager
import os
import json
from collections import OrderedDict
from json import JSONDecoder
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

class TreeBuilder:
    def extract_json_to_nodes(self, js, mother, fsm_conf) -> StatefulNode:
        for n,d in js.items():
            if isinstance(d, dict):
                child = StatefulNode(name=n,
                                  parent=mother,
                                  console=self.console,
                                  fsm_conf = fsm_conf)
                self.extract_json_to_nodes(d, child, fsm_conf = fsm_conf)
            elif isinstance(d, str):
                node = SubsystemNode(name=n,
                                     ssh_conf=self.ssh_conf,
                                     cfgmgr=ConfigManager(d),
                                     console=self.console,
                                     fsm_conf = fsm_conf,
                                     parent = mother)
            else:
                self.log.error(f"ERROR processing the tree {n}: {d} I don't know what that's supposed to mean?")
                exit(1)

    def get_custom_commands(self):
        ret = {}
        for node in PreOrderIter(self.topnode):
            ret.update(node.get_custom_commands())
        return ret

    def __init__(self, log, top_cfg, fsm_conf, console, ssh_conf):
        self.log = log
        self.ssh_conf = ssh_conf
        self.fsm_conf = fsm_conf
        if os.path.isdir(top_cfg):
            apparatus_id = top_cfg.split('/')[-1]
            data = {
                "apparatus_id": apparatus_id,
                apparatus_id: top_cfg
            }
            data = json.dumps(data)
        elif os.path.isfile(top_cfg):
            f = open(top_cfg, 'r')
            data = f.read()
        else:
            self.log.error(f"{top_cfg} invalid! You must provide either a top level json file or a directory name")
            exit(1)

        self.console = console

        try:
            self.top_cfg = json.loads(data, object_pairs_hook=dict_raise_on_duplicates)
        except json.JSONDecodeError as e:
            self.log.error("Failed to parse your top level json:\n"+str(e))
            exit(1)
        except RuntimeError as e:
            self.log.error(str(e)+" in your top level json.")
            exit(1)

        self.apparatus_id = self.top_cfg.get("apparatus_id")
        if self.apparatus_id:
            del self.top_cfg['apparatus_id']
        else:
            self.apparatus_id = top_cfg.replace('.json', '')

        cmd_order = self.top_cfg.get('command_order')
        if cmd_order:
            del self.top_cfg['command_order']

        self.topnode = StatefulNode(self.apparatus_id, console=self.console,
                                    fsm_conf=self.fsm_conf, order=cmd_order, verbose=True)
        self.extract_json_to_nodes(self.top_cfg, self.topnode, fsm_conf=self.fsm_conf)

    # This should get changed so that it copies the node, and strips the config
    def get_tree_structure(self):
        return self.topnode
