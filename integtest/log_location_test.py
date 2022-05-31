import pytest
import integrationtest.log_file_checks as log_file_checks

# The next three variable declarations *must* be present as globals in the test
# file. They're read by the "fixtures" in conftest.py to determine how
# to run the config generation and nanorc

# The name of the python module for the config generation
confgen_name="daqconf_multiru_gen"
# The arguments to pass to the config generator, excluding the json
# output directory (the test framework handles that)
confgen_arguments={"Working Dir": "-o . -s 10 -n 2".split(),
                   "New Folder": "-o ./logs -s 10 -n 2".split()}
# The commands to run in nanorc, as a list
nanorc_command_list="boot init conf start 1 resume wait 10 stop scrap terminate".split()

# The tests themselves

def test_nanorc_success(run_nanorc):
    # Check that nanorc completed correctly
    assert run_nanorc.completed_process.returncode==0

def test_log_files(run_nanorc):
    # Check that there are no warnings or errors in the log files (placeholder)
    print(run_nanorc.log_files  )
    assert log_file_checks.log_has_no_errors(run_nanorc.log_files)
