from anytree import AnyNode
from .cfgmgr import ConfigManager
import json


class TopLevelConfigManager:
    def extract_json_to_nodes(self, js, mother) -> AnyNode:
        children = []
    
        for n,d in js.items():
            if n != "conf-dir":
                child = AnyNode(id=n, is_subsystem=False)
                self.extract_json_to_nodes(d, child)
                children.append(child)
                self.nodes.append(child)
            else:
                mother.is_subsystem = True
                mother.conf_dir = d
        
        mother.children = children

    def __init__(self, top_cfg):
        self.nodes = []
        f = open(top_cfg, 'r')
        self.top_cfg = json.load(f)
        self.root = AnyNode(id="root", is_subsystem=False)
        self.extract_json_to_nodes(self.top_cfg, self.root)
        
        self._load()
        from anytree import RenderTree
        for pre, _, node in RenderTree(self.root):
            print("%s%s" % (pre, node.id))
        
        
    def _load(self):
        from anytree import PreOrderIter
        for node in PreOrderIter(self.root):
            if node.is_subsystem:
                node.config = ConfigManager(node.conf_dir)

    # This should get changed so that it copies the node, and strips the config
    def get_tree_structure(self):
        return self.root
        
