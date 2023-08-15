import json
import os
import pytest
import subprocess
import tempfile

conf_list = ["jhancock-kube-config"]
commands = "boot conf start_run 111 wait 60 stop_run scrap terminate".split()

@pytest.fixture(params = conf_list)
def perform_all_runs(request):
    '''For each config in conf_list, run some commands with nanorc'''
    if request.param[1]:
        cluster_url = "k8s://np04-srv-015:31000"
        conf_url = f"db://{request.param}"
        partition_name = f"test-partition-for-{request.param}"
        arglist = ["nanorc", "--pm", cluster_url, conf_url, partition_name] + commands

    output = subprocess.run(arglist)
    return output.returncode

def test_no_errors(perform_all_runs):
    assert perform_all_runs == 0

