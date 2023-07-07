import click
from .k8spm import K8SProcessManager
from .sshpm import SSHProcessManager
from urllib import parse

class pm_desc:
    def __init__(self, pm_arg):
        self.arg = pm_arg
        try:
            pm_uri = parse.urlparse(pm_arg)
        except:
            raise click.BadParameter(f'Badly formatted --pm')

        self.is_ssh = (pm_uri.scheme == 'ssh')
        self.is_kind = (pm_uri.scheme == 'kind')
        self.is_k8s_cluster = (pm_uri.scheme == 'k8s')
        if not self.is_ssh and not self.is_kind and not self.is_k8s_cluster:
            raise click.BadParameter(f'--pm should be either ssh://, kind://, or k8s://')

        if self.is_kind or self.is_k8s_cluster:
            self.address = pm_uri.netloc
            if not self.address:
                self.address = 'localhost'
                self.port = 31000
            else:
                try:
                    self.address = pm_uri.hostname
                    self.port = int(pm_uri.port)
                except:
                    raise click.BadParameter(f'Badly formatted --k8s address k8s://hostname:port')

        if self.is_kind and self.address != "localhost":
            raise click.BadParameter(f'Kind address can only be localhost for now!')

    def use_k8spm(self):
        return self.is_kind or self.is_k8s_cluster

    def use_sshpm(self):
        return self.is_ssh


class PMFactory:
    def __init__(self, cfgmgr, console):
        self.console = console
        self.cfgmgr = cfgmgr

    def get_pm(self, event):
        pm = event.kwargs['pm']

        if pm.use_k8spm():
            # Yes, we need the list of connections here
            connections = {}
            for app, data in self.cfgmgr.data.items():
                if not isinstance(data, dict): continue
                if not 'init' in data: continue
                connections[app] = []
                # please hide all this configuration details from me!
                for connection in data['init']['connections']:
                    if connection["connection_type"] == "kQueue": # this is burnin my eyes
                        continue
                    connections[app].append(connection)

            return K8SProcessManager(
                console = self.console,
                connections = connections,
                cluster_config = event.kwargs['pm']
            )
        else:
            return SSHProcessManager(
                console = self.console,
                log_path = event.kwargs.get('log_path'),
                ssh_conf = event.kwargs['ssh_conf'],
            )
