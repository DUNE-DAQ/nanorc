from .node import GroupNode, SubsystemNode
from .cfgmgr import ConfigManager
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

class TopLevelConfigManager:
    def extract_json_to_nodes(self, js, mother) -> GroupNode:
        for n,d in js.items():
            if isinstance(d, dict):
                child = GroupNode(name=n, parent=mother)
                self.extract_json_to_nodes(d, child)
            elif isinstance(d, str):
                node = SubsystemNode(name=n,
                                     cfgmgr=ConfigManager(d),
                                     console=self.console,
                                     parent=mother)
            else:
                raise RuntimeError(f"ERROR processing the tree {n}: {d} I don't know what that's supposed to mean?")

    def __init__(self, top_cfg, console):
        f = open(top_cfg, 'r')
        self.console = console
        try:
            # decoder = JSONDecoder(object_pairs_hook=dict_raise_on_duplicates)
            # self.top_cfg = decoder.decode(f)
            self.top_cfg = json.load(f, object_pairs_hook=dict_raise_on_duplicates)
            
        except Exception as e:
            raise RuntimeError("Failed to parse your top level json, please check it again") from e
        self.apparatus_id = self.top_cfg["apparatus_id"]
        del self.top_cfg["apparatus_id"]
        self.root = GroupNode(self.apparatus_id)
        self.extract_json_to_nodes(self.top_cfg, self.root)

    # This should get changed so that it copies the node, and strips the config
    def get_tree_structure(self):
        return self.root
        
