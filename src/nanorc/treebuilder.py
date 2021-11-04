from .node import GroupNode, SubsystemNode
from .cfgmgr import ConfigManager
from .fsm import FSMMachine
import os
import json
from collections import OrderedDict
from json import JSONDecoder

def dict_raise_on_duplicates(ordered_pairs):
    count=0
    d=OrderedDict()
    for k,v in ordered_pairs:
        if k in d:
            raise RuntimeError(f"Duplicated entries {k}")
        else:
            d[k]=v
    return d

class TreeBuilder:
    def extract_json_to_nodes(self, js, mother, FSM) -> GroupNode:
        for n,d in js.items():
            if isinstance(d, dict):
                child = GroupNode(name=n,
                                  parent=mother,
                                  console=self.console)
                FSM.add_node(child)
                self.extract_json_to_nodes(d, child, FSM)
            elif isinstance(d, str):
                child = SubsystemNode(name=n,
                                      cfgmgr=ConfigManager(d),
                                      console=self.console,
                                      parent=mother,
                                      fsm=FSM) # UGLY
                FSM.add_node(child)
            else:
                raise RuntimeError(f"ERROR processing the tree {n}: {d} I don't know what that's supposed to mean?")

    def __init__(self, top_cfg, console):
        if os.path.isdir(top_cfg):
            data = {
                "apparatus_id": top_cfg,
                top_cfg:top_cfg
            }
            data = json.dumps(data)
        elif os.path.isfile(top_cfg):
            f = open(top_cfg, 'r')
            data = f.read()
        else:
            raise RuntimeError(f"{top_cfg} You must provide either a top level json file or a directory name")
            
        self.console = console
        
        try:
            self.top_cfg = json.loads(data, object_pairs_hook=dict_raise_on_duplicates)
            
        except Exception as e:
            raise RuntimeError("Failed to parse your top level json, please check it again") from e
        self.apparatus_id = self.top_cfg["apparatus_id"]
        del self.top_cfg['apparatus_id']

        FSM = FSMMachine(json.load(open(top_cfg))['fsm'])
        del self.top_cfg['fsm']

        self.topnode = GroupNode(self.apparatus_id, console=self.console)
        FSM.add_node(self.topnode)

        self.extract_json_to_nodes(self.top_cfg, self.topnode, FSM)

    # This should get changed so that it copies the node, and strips the config
    def get_tree_structure(self):
        return self.topnode
        
