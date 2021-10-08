import os.path
import json
import copy
import socket
from distutils.dir_util import copy_tree

"""Extract nested values from a JSON tree."""

CFG_OUTDIR=os.path.expanduser("~/")

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
        for f in set(cfg["apps"].values()):
            fpath = os.path.join(self.cfg_dir, f + ".json")
            if not os.path.exists(fpath):
                raise RuntimeError(f"ERROR: {f}.json not found in {self.cfg_dir}")

            with open(fpath, "r") as jf:
                try:
                    j = json.load(jf)
                    data[f] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {f}.json") from e

        x = {a: data[d] for a, d in cfg["apps"].items()}
        setattr(self, cmd, x)

        if "order" in cfg:
            setattr(self, f"{cmd}_order", cfg["order"])

    def _load(self) -> None:

        pm_cfg = ["boot"]
        rc_cmds = ["init", "conf", "start", "stop", "pause", "resume", "scrap"]
        cfgs = {}
        for f in pm_cfg + rc_cmds:
            fpath = os.path.join(self.cfg_dir, f + ".json")
            if not os.path.exists(fpath):
                raise RuntimeError(f"ERROR: {f}.json not found in {self.cfg_dir}")

            with open(fpath, "r") as jf:
                try:
                    j = json.load(jf)
                    cfgs[f] = j
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {f}.json") from e

        self.boot = cfgs["boot"]

        for c in rc_cmds:
            self._import_cmd_data(c, cfgs[c])

        # Post-process conf
        # Boot:
        self.boot["hosts"] = {
            n: (h if (not h in ("localhost", "127.0.0.1")) else socket.gethostname())
            for n, h in self.boot["hosts"].items()
        }

        for k, v in self.boot["env"].items():
            if str(v).find("getenv") == 0:
                if k in os.environ.keys():
                    self.boot["env"][k] = os.environ[k]
                elif str(v).find(":") > 0:
                    self.boot["env"][k] = v[v.find(":") + 1:]
                else:
                    raise ValueError("Key " + k + " is not in environment and no default specified!")
               
        for exec_spec in self.boot["exec"].values():
            for k, v in exec_spec["env"].items():
                if str(v).find("getenv") == 0:
                    if k in os.environ.keys():
                        exec_spec["env"][k] = os.environ[k]
                    elif str(v).find(":") > 0:
                        exec_spec["env"][k] = v[v.find(":") + 1:]
                    else:
                        raise ValueError("Key " + k + " is not in environment and no default specified!")
            
        # Conf:
        ips = {n: socket.gethostbyname(h) for n, h in self.boot["hosts"].items()}
        # Set sender and receiver address to ips
        for c in json_extract(self.conf, "sender_config") + json_extract(self.conf, "receiver_config"):
            c["address"] = c["address"].format(**ips)

    def runtime_start(self, data: dict) -> dict:
        """
        Generates runtime start parameter set
        :param      data:  The data
        :type       data:  dict

        :returns:   Complete parameter set and path of the saved config
        :rtype:     tuple(dict, str)
        """
        start = copy.deepcopy(self.start)

        outdir = CFG_OUTDIR+"/RunConf_"+str(data["run"])
        postfix = ""
        counter = 1
        while os.path.exists(outdir+postfix):
            counter+=1
            postfix = "_"+str(counter)

        self.outdir = outdir+postfix+"/"
        os.mkdir(self.outdir)
        copy_tree(self.cfg_dir, self.outdir)

        config = json_extract(start, "modules")
        for c in config:
            for m in c:
                m["data"].update(data)

        f = open(self.outdir+"start_parsed.json", "w")
        f.write(json.dumps(config, indent=2))
        f.close()
        return start,self.outdir

    def runtime_resume(self, data: dict) -> dict:
        """
        Generates runtime resume parameter set
        :param      data:  The data
        :type       data:  dict

        :returns:   Complete parameter set.
        :rtype:     dict
        """
        resume = copy.deepcopy(self.resume)

        postfix = ""
        counter = 1
        while os.path.exists(self.outdir+"resume_parsed"+postfix+".json"):
            counter+=1
            postfix = "_"+str(counter)

        config = json_extract(resume, "modules")
        for c in config:
            for m in c:
                m["data"].update(data)

        file_name = self.outdir+"resume_parsed"+postfix+".json"
        f = open(file_name, "w")
        f.write(json.dumps(config, indent=2))
        f.close()
        return resume


if __name__ == "__main__":
    import sys
    from os.path import dirname, join
    from rich.console import Console
    from rich.pretty import Pretty
    from rich.traceback import Traceback

    console = Console()
    try:
        cfg = ConfigManager(sys.argv[1])
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
    console.print(Pretty(cfg.runtime_start({"trigger_interval_ticks": "bb"}, 1001)))

    console.print("Resume :runner:")
    console.print(Pretty(cfg.runtime_resume({"trigger_interval_ticks": "bb"})))

    console.print("Resume :runner:")
    console.print(Pretty(cfg.runtime_resume({"trigger_interval_ticks": "cc"})))
