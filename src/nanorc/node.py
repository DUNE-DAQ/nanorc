from anytree import NodeMixin

# This one is just to give a nicer name
class DAQNode(NodeMixin):
    def __init__(self, name:str, parent=None, children=None):
        self.name = name
        self.parent = parent
        if children:
            self.children = children
        #super().__init__(args, kwargs)
        
# Now on to useful stuff
class SubsystemNode(NodeMixin):
    def __init__(self, name, cfgmgr, parent=None, children=None):
        self.name = name
        self.cfgmgr = cfgmgr
        self.pm = None
        self.listener = None
        self.parent = parent
        if children:
            self.children = children

class ApplicationNode(NodeMixin):
    def __init__(self, name, sup, parent=None, children=None):
        self.name = name
        self.sup = sup
        self.parent = parent
        if children:
            self.children = children
    
