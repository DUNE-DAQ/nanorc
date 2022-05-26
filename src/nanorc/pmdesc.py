import click

class pm_desc:
    def __init__(self, pm_arg):
        self.arg = pm_arg
        # TODO use urllib
        self.is_ssh = (self.arg=='ssh')
        self.is_kind = (self.arg.find('kind')==0)
        self.is_k8s_cluster = (self.arg.find('k8s')==0)
        if not self.is_ssh and not self.is_kind and not self.is_k8s_cluster:
            raise click.BadParameter(f'--pm should be either ssh, kind, or k8s')

        if self.is_kind or self.is_k8s_cluster:
            self.address = self.arg
            self.address = self.address.replace('kind', '')
            self.address = self.address.replace('k8s', '')
            self.address = self.address.replace('://', '')
            if not self.address:
                self.address = 'localhost'
                self.port = '31000'
            else:
                address_and_port = self.address.split(':')
                if len(address_and_port) == 2:
                    self.address = address_and_port[0]
                    self.port = int(address_and_port[1])
                else:
                    raise click.BadParameter(f'Badly formed k8s address: {self.address}, should be of the form: server_name:port_number')

        if self.is_kind and self.address != "localhost":
            raise click.BadParameter(f'Kind address can only be localhost for now!')

    def use_k8spm(self):
        return self.is_kind or self.is_k8s_cluster

    def use_sshpm(self):
        return self.is_ssh
