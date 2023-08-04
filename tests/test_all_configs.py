import json
import os
import pytest
import subprocess
import tempfile

conf_list = ["default-config", "top-level.json"]
commands = "boot conf start_run 111 wait 60 stop_run scrap terminate".split()

@pytest.fixture(params = conf_list)
def perform_all_runs(request):
    '''For each config in conf_list, run some commands with nanorc'''
    dir_object = tempfile.TemporaryDirectory()
    temp_dir_name = dir_object.name                 #Put the logs in a temporary directory, since we don't want them filling up the CWD
    conf_name = request.param[0]
    partition_name = f"test-partition-for-{request.param[0].split('.')[0]}"
    arglist = ["nanorc", "--loglevel", "CRITICAL", "--cfg-dumpdir", temp_dir_name, "--log-path", temp_dir_name, conf_name, partition_name] + commands

    output = subprocess.run(arglist)
    return output.returncode

def test_no_errors(perform_all_runs):
    assert perform_all_runs == 0
