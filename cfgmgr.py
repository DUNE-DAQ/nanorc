import os.path
import json
import copy
import socket

"""Extract nested values from a JSON tree."""


def json_extract(obj, key):
    """Recursively fetch values from nested JSON."""
    arr = []

    def extract(obj, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == key:
                    arr.append(v)
                if isinstance(v, (dict, list)):
                    extract(v, arr, key)
        elif isinstance(obj, list):
            for item in obj:
                extract(item, arr, key)
        return arr

    values = extract(obj, arr, key)
    return values

class ConfigManager:
    """docstring for ConfigManager"""
    def __init__(self, cfg_dir):
        super(ConfigManager, self).__init__()
        self.cfg_dir = cfg_dir

        self._load()


    def _import_cmd_data(self, cmd: str, cfg: dict) -> None:
        data = {}
        for f in set(cfg['apps'].values()):
            fpath = os.path.join(self.cfg_dir, f+'.json')
            if not os.path.exists(fpath):
                raise RuntimeError(f"ERROR: {f}.json not found in {self.cfg_dir}")

            with open(fpath, 'r') as jf:
                try:
                    j = json.load(jf)
                    data[f] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {f}.json") from e 

        x = { a:data[d] for a,d in cfg['apps'].items()}
        setattr(self, cmd, x)

        if 'order' in cfg:
            setattr(self, f'{cmd}_order', cfg['order'])


    def _load(self) -> None:

        cfgs = {}
        cmds = ['init', 'conf', 'start', 'stop', 'pause', 'resume', 'scrap']
        for f in ['boot']+cmds:
            fpath = os.path.join(self.cfg_dir, f+'.json')
            if not os.path.exists(fpath):
                raise RuntimeError(f"ERROR: {f}.json not found in {self.cfg_dir}")

            with open(fpath, 'r') as jf:
                try:
                    j = json.load(jf)
                    cfgs[f] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {f}.json") from e

        # Consistency check.
        # Note to self: some commands (pause/resume) are meant to be for some applications only
        # This check needs to be softened then
        # assert cfgs['boot']['apps'].keys() == cfgs['init']['apps'].keys()
        # assert cfgs['boot']['apps'].keys() == cfgs['conf']['apps'].keys()
        # assert cfgs['boot']['apps'].keys() == cfgs['start']['apps'].keys()
        # assert cfgs['boot']['apps'].keys() == cfgs['stop']['apps'].keys()

        self.boot = cfgs['boot']

        for c in cmds:
            self._import_cmd_data(c, cfgs[c])
    

        # Post-process conf
        # Boot:
        self.boot['hosts'] =  { n:(h if (not h in ('localhost', '127.0.0.1')) else socket.gethostname()) for n,h in self.boot['hosts'].items() }

        # Conf:
        ips = { n:socket.gethostbyname(h) for n,h in self.boot['hosts'].items()}
        # Set sender and receiver address to ips
        for c in json_extract(self.conf, 'sender_config')+json_extract(self.conf, 'receiver_config'):
            c['address'] = c['address'].format(**ips)


    def runtime_start(self, data: dict) -> dict:
        """
        Generates runtime start parameter set        
        :param      data:  The data
        :type       data:  dict
        
        :returns:   Complete parameter set.
        :rtype:     dict
        """
        start = copy.deepcopy(self.start)

        for c in json_extract(start, 'modules'):
            for m in c:
                m['data'] = data
        return start

    def runtime_resume(self, data: dict) -> dict:
        """
        Generates runtime resume parameter set        
        :param      data:  The data
        :type       data:  dict
        
        :returns:   Complete parameter set.
        :rtype:     dict
        """
        resume = copy.deepcopy(self.resume)

        for c in json_extract(resume, 'modules'):
            for m in c:
                m['data'] = data
        return resume


if __name__ == '__main__':
    from os.path import dirname, join
    from rich.console import Console
    from rich.pretty import Pretty
    from rich.traceback import Traceback


    console = Console()
    try:
        cfg = ConfigManager(join(dirname(__file__), 'examples', 'minidaqapp'))
    except Exception as e:
        console.print(Traceback())

    console.print("Boot data :boot:")
    console.print(Pretty(cfg.boot))

    console.print("Init data :boot:")
    console.print(Pretty(cfg.init))

    console.print("Conf data :boot:")
    console.print(Pretty(cfg.conf))

    console.print("Start data :runner:")
    console.print(Pretty(cfg.start))
    console.print("Start order :runner:")
    console.print(Pretty(cfg.start_order))

    console.print("Stop data :busstop:")
    console.print(Pretty(cfg.stop))
    console.print("Stop order :busstop:")
    console.print(Pretty(cfg.stop_order))


    console.print("Start data V:runner:")
    console.print(Pretty(cfg.runtime_start({'aa': 'bb'})))
