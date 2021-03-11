import os
import socket
import sh
import sys
import time

"""
Boot info example

{
    "env" : {
        "DBT_ROOT": "env",
        "DBT_AREA_ROOT": "env"
    },
    "apps" : {
        "stoca" : {
            "exec": "daq_application",
            "host": "localhost",
            "port": 12345
        },
        "suka": {
            "exec": "daq_application",
            "host": "localhost",
            "port": 12346
        }
    }
}
"""



# ---
def is_port_open(ip,port):
   s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   try:
      s.connect((ip, int(port)))
      s.shutdown(2)
      return True
   except:
      return False

# ---
def logger(logfile, echo=False):

    log = open(logfile, 'w')

    def interact(line, stdin):
        log.write(line)
        log.flush()
        if echo:
            sys.stdout.write(line)
            sys.stdout.flush()

    return interact


class AppInfo(object):
    """docstring for AppInfo"""
    def __init__(self, name):
        super(AppInfo, self).__init__()
        self.proc = None
        self.name = name
        self.logfile = None
        self.ssh_args = None
        self.cmd = None
        self.conf = None

    def __str__(self):
        return str(vars(self))

        
# ---
class SSHProcessManager(object):
    """An poor's man process manager based on ssh"""
    def __init__(self):
        super(SSHProcessManager, self).__init__()

        self.apps = {}
    
    
    def spawn(self, boot_info):

        # Add a check for env and apps in boot_info keys

        apps = boot_info['apps']

        env_vars = { k:(os.environ[k] if v == 'env' else v) for k,v in boot_info['env'].items() }


        for app_name, app_conf in apps.items():

            cmd_fac = f'rest://localhost:{app_conf["port"]}'

            # CMD=f"cd {DBT_AREA_ROOT}; source {DBT_ROOT}/dbt-setup-env.sh; source {DBT_ROOT}/scripts/dbt-setup-runtime-environment.sh;daq_application --name {APP_NAME} -c {cmd_fac}"
            cmd=f'cd {env_vars["DBT_AREA_ROOT"]}; source {env_vars["DBT_ROOT"]}/dbt-setup-env.sh; dbt-setup-runtime-environment; {app_conf["exec"]} --name {app_name} -c {cmd_fac}'

            ssh_args = [
                app_conf['host'],
                '-tt',
                cmd
            ]

            log_file = f'log_{app_name}_{app_conf["port"]}.txt'

            info = AppInfo(app_name)
            info.logfile = log_file
            info.cmd = cmd
            info.ssh_args = ssh_args
            info.conf = app_conf.copy()
            self.apps[app_name] = info


        apps_running = []
        for name, info in self.apps.items():
            if is_port_open(info.conf['host'], info.conf['port']):
                apps_running += [name]
        if apps_running:
            raise RuntimeError(f"ERROR: apps already running? {apps_running}")

        for name, info in self.apps.items():
            info.proc = sh.ssh(*info.ssh_args, _out=logger(f'log_{app_name}_{app_conf["port"]}.txt'), _bg=True)

        for _ in range(20):
            apps_starting = []
            for name, info in self.apps.items():
                if not is_port_open(info.conf['host'], info.conf['port']):
                    apps_starting += [name]
            if apps_starting:
                print(f"Waiting for apps {','.join(apps_starting)}")
            else:
                print(f"Apps {','.join(self.apps)} started")
                break
            time.sleep(1)



    def terminate(self):

        for name, info in self.apps.items():
            if info.proc is not None:
                info.proc.terminate()



