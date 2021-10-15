from .node import DAQNode, SubsystemNode
from .cfgmgr import ConfigManager
import json


class TopLevelConfigManager:
    def extract_json_to_nodes(self, js, mother) -> DAQNode:
    
        for n,d in js.items():
            if "conf-dir" in d:
                mother = SubsystemNode(name=n,
                                       cfgmgr=ConfigManager(d["conf-dir"]),
                                       parent=mother)
            else:
                child = DAQNode(name=n, parent=mother)
                self.extract_json_to_nodes(d, child)

    def __init__(self, top_cfg):
        f = open(top_cfg, 'r')
        self.top_cfg = json.load(f)
        self.root = DAQNode("root")
        self.extract_json_to_nodes(self.top_cfg, self.root)
        
        # self._load()
        from anytree import RenderTree
        for pre, _, node in RenderTree(self.root):
            print(f"{pre}{node.name} - {type(node)}")
        
    # This should get changed so that it copies the node, and strips the config
    def get_tree_structure(self):
        return self.root
        
