from .node import DAQNode, SubsystemNode
from .cfgmgr import ConfigManager
import json


class TopLevelConfigManager:
    def extract_json_to_nodes(self, js, mother) -> DAQNode:
    
        for n,d in js.items():
            if "conf-dir" in d:
                mother = SubsystemNode(name=n,
                                       cfgmgr=ConfigManager(d["conf-dir"]),
                                       console=self.console,
                                       parent=mother)
            else:
                child = DAQNode(name=n, parent=mother)
                self.extract_json_to_nodes(d, child)

    def __init__(self, top_cfg, console):
        f = open(top_cfg, 'r')
        self.console = console
        self.top_cfg = json.load(f)
        self.root = DAQNode("root")
        self.extract_json_to_nodes(self.top_cfg, self.root)
        
        from anytree import RenderTree
        for pre, _, node in RenderTree(self.root):
            print(f"{pre}{node.name}")
        
    # This should get changed so that it copies the node, and strips the config
    def get_tree_structure(self):
        return self.root
        
