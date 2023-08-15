import json
import os
import pytest
import subprocess
import tempfile

conf_list = ["default-config", "top-level.json", r"db://jhancock-basic"]
commands = "boot conf start_run 111 wait 60 stop_run scrap terminate".split()

@pytest.fixture(params = conf_list)
def perform_all_runs(request):
    '''For each config in conf_list, run some commands with nanorc'''
    start_dir = os.getcwd()
    temp_dir_object = tempfile.TemporaryDirectory()
    temp_dir_name = temp_dir_object.name                #Make a temp directory and then enter it.
    os.chdir(temp_dir_name)
    if request.param[:5] == "db://":
        conf_name = request.param
        partition_name = f"test-partition-for-{conf_name[5:]}"
    else:
        conf_name = f"{start_dir}/{request.param}"      #We are somewhere in /tmp so the absolute path is needed.
        partition_name = f"test-partition-for-{request.param.split('.')[0]}"
    arglist = ["nanorc", "--loglevel", "CRITICAL", conf_name, partition_name] + commands
    output = subprocess.run(arglist)
    os.chdir(start_dir)
    return output.returncode

def test_no_errors(perform_all_runs):
    assert perform_all_runs == 0
