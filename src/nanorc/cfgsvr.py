from anytree import PreOrderIter
import os
import json
import os.path
import logging
import tarfile
import json
import copy
import requests
import tempfile
from .statefulnode import StatefulNode
from .node import SubsystemNode
from .cfgmgr import ConfigManager
from .credmgr import credentials,Authentication
from distutils.dir_util import copy_tree

# Straight from stack overflow
# https://stackoverflow.com/a/17081026/8475064
def make_tarfile(output_filename, source_dir):
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))

def save_conf_to_dir(topnode, outdir, runtime_data):

    for node in PreOrderIter(topnode):

        if isinstance(node, SubsystemNode):

            this_path = ""
            for parent in node.path:
                this_path += "/"+parent.name

            full_path = outdir+this_path
            os.makedirs(full_path)

            location = node.cfgmgr.get_conf_location(for_apps=False)

            if os.path.isdir(location):
                copy_tree(location, full_path)

            else:
                import requests
                r = requests.get(location)
                if r.status_code == 200:
                    config = r.json()
                    with open(os.path.join(full_path, 'full_configuration.json'), 'w') as f:
                        json.dump(config, f, indent=4, sort_keys=True)
                else:
                    raise RuntimeError(f'Couldn\'t get the configuration {location}')


            rd = node.cfgmgr.generate_data_for_module(runtime_data)

            with open(os.path.join(full_path, "runtime_data.json"), "w") as f:
                json.dump(rd, f, indent=4, sort_keys=True)


class FileConfigSaver:
    """docstring for ConfigManager"""

    def __init__(self, cfg_outdir:str):
        super(FileConfigSaver, self).__init__()
        self.cfgmgr = None
        self.outdir = cfg_outdir

    def _get_new_out_dir_name(self, run:int) -> str:
        """
        Create a unique directory name for saving the configs in this run
        :param      run :  run number
        :type       run :  int

        :returns:   Path for saving the config
        :rtype:     str
        """
        prefix = "/RunConf_"
        outdir = self.outdir+prefix+str(run)
        if os.path.exists(outdir):
            raise RuntimeError(f"Folder containing the run {run} already exists!")

        return outdir+"/"

    def _get_new_resume_file_name(self, path:str) -> str:
        """
        Create a new name for saving the runtime configuration each time resume is issued

        :returns:   Path for the new resume file
        :rtype:     str
        """
        postfix = ""
        counter = 1
        filename = path+"/resume_parsed"
        ext=".json"
        while os.path.exists(filename+postfix+ext):
            counter+=1
            postfix = "_"+str(counter)

        return filename+postfix+ext

    def save_on_start(self,
                      topnode:StatefulNode,
                      run:int,
                      run_type:str,
                      data:dict) -> str:
        """
        Save the configuration runtime start parameter set
        :param      apps:  the application tree
        :type       apps:  StatefulNode
        :param      run :  run number
        :type       run :  int
        :param      data :  the runtime start data
        :type       data :  dict
        :param      run_type :  run type
        :type       run_type :  str

        :returns:   Path of the saved config
        :rtype:     str
        """
        if not self.cfgmgr:
            raise RuntimeError(f"{__name__}: ERROR : You need to set the cfgmgr of this ConfigSaver")
        try:
            self.thisrun_outdir = self._get_new_out_dir_name(run)
        except Exception as e:
            raise RuntimeError(str(e))

        save_conf_to_dir(
            outdir = self.thisrun_outdir,
            topnode = topnode,
            runtime_data = data,
        )
        return self.thisrun_outdir


    def save_on_stop(self, run:int):
        pass




class DBConfigSaver:
    def __init__(self, socket:str):
        self.API_SOCKET = socket
        auth = credentials.get_login("runregistrydb")
        self.API_USER = auth.user
        self.API_PSWD = auth.password
        self.timeout = 2
        self.apparatus_id = None
        self.log = logging.getLogger(self.__class__.__name__)

    def save_on_resume(self, topnode, overwrite_data:dict, cfg_method:str) -> str:
        return "not_saving_to_db_on_resume"

    def save_on_start(self,
                      topnode,
                      run:int,
                      run_type:str,
                      data:dict) -> str:

        fname=None
        dname=None

        with tempfile.TemporaryDirectory() as dir_name:
            from urllib.parse import ParseResult
            dname = dir_name
            json_object = self.cfgmgr.top_cfg
            nice_top = {}
            for key, value in json_object.items():
                if isinstance(value, ParseResult):
                    nice_top[key] = value.geturl()
                else:
                    nice_top[key] = value
            with open(dname+"/top_config.json", "w") as outfile:
                json.dump(nice_top, outfile, indent=4)

            save_conf_to_dir(
                outdir = dir_name,
                topnode = topnode,
                runtime_data = data,
            )

            with tempfile.NamedTemporaryFile(suffix='.tar.gz', delete=False) as f:
                with tarfile.open(fileobj=f, mode='w:gz') as tar:
                    tar.add(dname, arcname=os.path.basename(dname))
                f.flush()
                f.seek(0)
                fname = f.name

            with open(fname, "rb") as f:
                files = {'file': f}
                version = os.getenv("DUNE_DAQ_BASE_RELEASE")
                if not version:
                    raise RuntimeError('RunRegistryDB: dunedaq version not in the variable env DUNE_DAQ_BASE_RELEASE! Exit nanorc and\nexport DUNE_DAQ_BASE_RELEASE=dunedaq-vX.XX.XX\n')

                post_data = {"run_num": run,
                             "det_id": self.apparatus_id,
                             "run_type": run_type,
                             "software_version": version}


                try:
                    r = requests.post(self.API_SOCKET+"/runregistry/insertRun/",
                                      files=files,
                                      data=post_data,
                                      auth=(self.API_USER, self.API_PSWD),
                                      timeout=self.timeout)
                    r.raise_for_status()

                except requests.HTTPError as exc:
                    error = f"{__name__}: RunRegistryDB: HTTP Error: {exc}, {r.text}"
                    self.log.error(error)
                    raise RuntimeError(error) from exc
                except requests.ConnectionError as exc:
                    error = f"{__name__}: Connection to {self.API_SOCKET} wasn't successful: {exc}"
                    self.log.error(error)
                    raise RuntimeError(error) from exc
                except requests.Timeout as exc:
                    error = f"{__name__}: Connection to {self.API_SOCKET} timed out: {exc}"
                    self.log.error(error)
                    raise RuntimeError(error) from exc

            os.remove(fname)

        return "run_registry_db"

    def save_on_stop(self, run:str) -> None:
        try:
            r = requests.get(self.API_SOCKET+"/runregistry/updateStopTime/"+str(run),
                              auth=(self.API_USER, self.API_PSWD),
                              timeout=self.timeout)
        except requests.HTTPError as exc:
            error = f"{__name__}: RunRegistryDB: HTTP Error (maybe failed auth, maybe ill-formed post message, ...)"
            self.log.error(error)
            raise RuntimeError(error) from exc
        except requests.ConnectionError as exc:
            error = f"{__name__}: Connection to {self.API_SOCKET} wasn't successful"
            self.log.error(error)
            raise RuntimeError(error) from exc
        except requests.Timeout as exc:
            error = f"{__name__}: Connection to {self.API_SOCKET} timed out"
            self.log.error(error)
            raise RuntimeError(error) from exc



if __name__ == "__main__":
    import sys
    from os.path import dirname, join
    from rich.console import Console
    from rich.pretty import Pretty
    from rich.traceback import Traceback
    import click

    @click.command()
    @click.argument('cfg_dir', type=click.Path(exists=True))
    @click.argument('cfg_outdir', type=click.Path())
    @click.argument('run', type=int)
    def config_saver_test(cfg_dir, cfg_outdir, run):
        cfgmgr = ConfigManager(join(dirname(__file__), "examples", "minidaqapp"))
        instance = ConfigSaver(cfgmgr, cfg_outdir)
        print(f"Save start data for run {run}")
        runtime_start_data = {
            "disable_data_storage": True,
            "run": run,
        }
        instance.save_on_start(runtime_start_data, run)
        print("Save resume data")
        runtime_resume_data = {
            "disable_data_storage": False
        }
        instance.save_on_resume(runtime_resume_data)
        print(f"Data is in {cfg_outdir}")

    config_saver_test()
