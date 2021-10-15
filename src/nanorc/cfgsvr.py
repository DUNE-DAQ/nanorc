from anytree import PreOrderIter
import os.path
import json
import copy
from .node import DAQNode, SubsystemNode
from .cfgmgr import ConfigManager
from distutils.dir_util import copy_tree

class ConfigSaver:
    """docstring for ConfigManager"""

    def __init__(self, cfgmgr:ConfigManager, cfg_outdir:str):
        super(ConfigSaver, self).__init__()
        self.cfgmgr = cfgmgr
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

    def save_on_start(self, apps:DAQNode, run:int,
                      overwrite_data:dict, cfg_method:str) -> str:
        """
        Save the configuration runtime start parameter set
        :param      apps:  the application tree
        :type       apps:  DAQNode
        :param      run :  run number
        :type       run :  int
        :param      overwrite_data :  the runtime start data
        :type       overwrite_data :  dict
        :param      cfg_method :  which config method to call on start
        :type       cfg_method :  str

        :returns:   Path of the saved config
        :rtype:     str
        """
        self.thisrun_outdir = self._get_new_out_dir_name(run)
        for node in PreOrderIter(apps):
            if isinstance(node, SubsystemNode):
                this_path = ""
                for parent in node.path:
                    this_path += "/"+parent.name
                    
                full_path = self.thisrun_outdir+this_path
                os.makedirs(full_path)
                copy_tree(node.cfgmgr.cfg_dir, full_path)
                
                if cfg_method:
                    f=getattr(node.cfgmgr,cfg_method)
                    data = f(overwrite_data)

                f = open(full_path+"/start_parsed.json", "w")
                f.write(json.dumps(data, indent=2))
                f.close()

        return self.thisrun_outdir


    def save_on_resume(self, apps:DAQNode, overwrite_data: dict, cfg_method:str) -> dict:
        """
        :param      apps:  the application tree
        :type       apps:  DAQNode
        :param      overwrite_data :  the runtime start data
        :type       overwrite_data :  dict
        :param      cfg_method :  which config method to call on start
        :type       cfg_method :  str

        :returns: None
        """
        for node in PreOrderIter(apps):
            if isinstance(node, SubsystemNode):
                this_path = ""
                for parent in node.path:
                    this_path += "/"+parent.name
                    
                full_path = self.thisrun_outdir+this_path
                
                if cfg_method:
                    f=getattr(node.cfgmgr,cfg_method)
                    data = f(overwrite_data)

                f = open(self._get_new_resume_file_name(full_path), "w")
                f.write(json.dumps(data, indent=2))
                f.close()



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
