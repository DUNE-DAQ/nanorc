import os.path
import logging
import tarfile
import json
import copy
import requests
from .cfgmgr import ConfigManager
from .credmgr import credentials,Authentication
from distutils.dir_util import copy_tree

# Straight from stack overflow
# https://stackoverflow.com/a/17081026/8475064
def make_tarfile(output_filename, source_dir):
    with tarfile.open(output_filename, "w:gz") as tar:
        tar.add(source_dir, arcname=os.path.basename(source_dir))
        
class SimpleConfigSaver:
    """docstring for ConfigManager"""

    def __init__(self, cfg_outdir:str):
        super(SimpleConfigSaver, self).__init__()
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

    def _get_new_resume_file_name(self) -> str:
        """
        Create a new name for saving the runtime configuration each time resume is issued

        :returns:   Path for the new resume file
        :rtype:     str
        """
        postfix = ""
        counter = 1
        filename = self.thisrun_outdir+"/resume_parsed"
        ext=".json"
        while os.path.exists(filename+postfix+ext):
            counter+=1
            postfix = "_"+str(counter)

        return filename+postfix+ext

    def save_on_start(self, data: dict, run:int, run_type:str) -> tuple:
        """
        Save the configuration runtime start parameter set
        :param      data:  The data
        :type       data:  dict
        :param      run :  run number
        :type       run :  int
        :param      run_type :  run type
        :type       run_type :  str

        :returns:   Path of the saved config
        :rtype:     str
        """
        if not self.cfgmgr:
            raise RuntimeError(f"{__name__}: ERROR : You need to set the cfgmgr of this ConfigSaver")
        self.thisrun_outdir = self._get_new_out_dir_name(run)
        os.makedirs(self.thisrun_outdir)
        copy_tree(self.cfgmgr.cfg_dir, self.thisrun_outdir)

        f = open(self.thisrun_outdir+"start_parsed.json", "w")
        f.write(json.dumps(data, indent=2))
        f.close()
        
        tgz_path = os.path.normpath(self.thisrun_outdir)+".tgz"
        make_tarfile(output_filename=tgz_path, source_dir=self.thisrun_outdir)

        return self.thisrun_outdir, tgz_path


    def save_on_resume(self, data: dict) -> dict:
        """
        Generates runtime resume parameter set
        :param      data:  The data
        :type       data:  dict

        :returns: None
        """
        f = open(self._get_new_resume_file_name(), "w")
        f.write(json.dumps(data, indent=2))
        f.close()

    
    def save_on_stop(self, run:int):
        pass
        

        

class DBConfigSaver(SimpleConfigSaver):
    def __init__(self, cfg_outdir:str, socket:str):
        super().__init__(cfg_outdir)
        
        self.API_SOCKET = socket
        auth = credentials.get_login("runregistrydb")
        self.API_USER = auth.user
        self.API_PSWD = auth.password
        self.timeout = 2
        self.log = logging.getLogger(self.__class__.__name__)

    def save_on_start(self, data: dict, run:int, run_type:str) -> tuple:
        cfg_dir, cfg_file = super().save_on_start(data, run, run_type)
        det_id = '_'.join(self.cfgmgr.boot['apps'].keys())

        files = {'file': open(cfg_file,'rb')}
        post_data = {"run_num": str(run),
                     "det_id": det_id,
                     "run_type": run_type
                     }
        
        try:
            r = requests.post(self.API_SOCKET+"/runregistry/insertRun/",
                              files=files,
                              data=post_data,
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

        return cfg_dir, cfg_file, "run_registry_db"

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
