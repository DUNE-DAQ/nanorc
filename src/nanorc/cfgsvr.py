import os.path
import json
import copy
from distutils.dir_util import copy_tree

class ConfigSaver:
    """docstring for ConfigManager"""

    def __init__(self, cfg_dir, cfg_outdir):
        super(ConfigSaver, self).__init__()
        self.cfg_dir = cfg_dir
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
        postfix = ""
        counter = 1
        while os.path.exists(outdir+postfix):
            counter+=1
            postfix = "_"+str(counter)

        return outdir+postfix+"/"

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

    def save_on_start(self, data: dict, run:int) -> str:
        """
        Save the configuration runtime start parameter set
        :param      data:  The data
        :type       data:  dict
        :param      run :  run number
        :type       run :  int

        :returns:   Path of the saved config
        :rtype:     str
        """
        self.thisrun_outdir = self._get_new_out_dir_name(run)
        print(self.thisrun_outdir)
        os.makedirs(self.thisrun_outdir)
        copy_tree(self.cfg_dir, self.thisrun_outdir)

        f = open(self.thisrun_outdir+"start_parsed.json", "w")
        f.write(json.dumps(data, indent=2))
        f.close()

        return self.thisrun_outdir


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
        instance = ConfigSaver(cfg_dir, cfg_outdir)
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
