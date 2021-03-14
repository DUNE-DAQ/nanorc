import os.path
import json

class ConfigManager:
    """docstring for ConfigManager"""
    def __init__(self, cfg_dir):
        super(ConfigManager, self).__init__()
        self.cfg_dir = cfg_dir

        self._load()

    def _load(self):

        cfgs = {}
        for f in ('boot', 'init', 'conf'):
            fpath = os.path.join(self.cfg_dir, f+'.json')
            if not os.path.exists(fpath):
                raise RuntimeError(f"ERROR: {f}.json not found in {self.cfg_dir}")

            with open(fpath, 'r') as jf:
                try:
                    j = json.load(jf)
                    cfgs[f] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {f}.json") from e

        # Basic checks
        assert cfgs['boot']['apps'].keys() == cfgs['init'].keys()
        assert cfgs['boot']['apps'].keys() == cfgs['conf'].keys()

        self.boot = cfgs['boot']
        # Load init profiles
        init_data = {}
        for f in set(cfgs['init'].values()):
            fpath = os.path.join(self.cfg_dir, f+'.json')
            if not os.path.exists(fpath):
                raise RuntimeError(f"ERROR: {f}.json not found in {self.cfg_dir}")

            with open(fpath, 'r') as jf:
                try:
                    j = json.load(jf)
                    init_data[f] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {f}.json") from e 

        self.init = { a:init_data[d] for a,d in cfgs['init'].items()}
            
        # Load init profiles
        conf_data = {}
        for f in set(cfgs['conf'].values()):
            fpath = os.path.join(self.cfg_dir, f+'.json')
            if not os.path.exists(fpath):
                raise RuntimeError(f"ERROR: {f}.json not found in {self.cfg_dir}")

            with open(fpath, 'r') as jf:
                try:
                    j = json.load(jf)
                    conf_data[f] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {f}.json") from e 

        self.conf = { a:conf_data[d] for a,d in cfgs['conf'].items()}



if __name__ == '__main__':
    from os.path import dirname, join
    from rich.console import Console
    from rich.pretty import Pretty

    console = Console()
    cfg = ConfigManager(join(dirname(__file__), 'examples', 'listrev_2x'))
    console.print("Boot data :boot:")
    console.print(Pretty(cfg.boot))

    console.print("Init data :boot:")
    console.print(Pretty(cfg.init))

    console.print("Conf data :boot:")
    console.print(Pretty(cfg.conf))
