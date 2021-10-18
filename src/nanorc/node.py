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
    
    def send_command(self, cmd:str, overwrite_data:dict, state_entry:str, state_exit:str):
        self.log.debug(f"Sending {cmd} to {n.name}")
        print(f"Sending {cmd} to {n.name}")
                    
        sequence = getattr(self.cfgmgr, cmd+'_order', None)
        if cfg_method:
            f=getattr(self.cfgmgr,cfg_method)
            data = f(overwrite_data)
        else:
            data = getattr(self.cfgmgr, cmd)
                        
        appset = list(self.children)
        
        if not sequence:
            # Loop over data keys if no sequence is specified or all apps, if data is empty
            
            for n in appset:
                n.sup.send_command(cmd, data[n.name] if data else {}, state_entry, state_exit)

                start = datetime.now()
                
                while(appset):
                    done = []
                    for n in appset:
                        try:
                            r = n.sup.check_response()
                        except NoResponse:
                            continue
                        # except AppCommander.ResponseTimeout 
                        # failed[n] = {}
                        done += [n]
                    
                        (ok if r['success'] else failed)[n.name] = r

                        for d in done:
                            appset.remove(d)

                            now = datetime.now()
                            elapsed = (now - start).total_seconds()

                            if elapsed > self.timeout:
                                raise RuntimeError("Send multicommand failed")

                            time.sleep(0.1)
                            self.log.info("tic toc")

        else:
            # There probably is a way to do that in a much nicer, pythonesque, way
            for n in sequence:
                for child_node in appset:
                    if n == child_node.name:
                        r = child_node.sup.send_command_and_wait(cmd, data[n] if data else {},
                                                                 state_entry, state_exit, self.timeout)
                        (ok if r['success'] else failed)[n] = r


        return (ok, failed)

class ApplicationNode(NodeMixin):
    def __init__(self, name, sup, parent=None, children=None):
        self.name = name
        self.sup = sup
        self.parent = parent
        if children:
            self.children = children
    
