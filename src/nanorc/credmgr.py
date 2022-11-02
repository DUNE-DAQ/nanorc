import sys, os
import logging
from getpass import getpass
import subprocess
import logging
import tempfile
from pathlib import Path

class Authentication():
    def __init__(self, service:str, user:str, password:str):
        self.service = service
        self.user = user
        self.password = password
        self.log = logging.getLogger(self.__class__.__name__)

class CredentialManager:
    def __init__(self):
        self.log = logging.getLogger(self.__class__.__name__)
        self.authentications = []
        self.user = None
        self.console = None
        self.partition_name = None
        self.partition_number = None
        self.cache_initialised = False
        self.krbenv = {}

    def quit(self):
         if self.cache_initialised and os.path.isdir(self.krb_cache_path):
             self.stop_partition()
        #     self.log.info(f'Flushing kerberos ticket in {self.krb_cache_path}')
        #     import shutil
        #     shutil.rmtree(self.krb_cache_path)

    def create_kerb_cache(self):
        if self.partition_number is None or self.partition_name is None:
            raise RuntimeError('Partition number (or name) hasn\'t been specified, I cannot create a nanorc kerberos cache')

        self.krb_cache_path = Path(os.path.expanduser(f'~/.nanorc_kerbcache_{self.partition_name}_part{self.partition_number}'))
        if not os.path.isdir(self.krb_cache_path):
            os.mkdir(self.krb_cache_path)
        self.krbenv = {'KRB5CCNAME': f'DIR:{self.krb_cache_path}'}
        self.cache_initialised = True

    def set_partition(self, partition_number, apparatus_id):
        self.partition_number = partition_number
        self.partition_name = apparatus_id # here is the mother of all the partition definition questions...
        self.create_kerb_cache()

    def stop_partition(self):
        if os.path.isfile(self.krb_cache_path/'active_partition'):
            os.remove(self.krb_cache_path/'active_partition')

    def start_partition(self):
        if not self.cache_initialised: raise RuntimeError('Nanorc\'s kerberos cache wasn\'t initialised!')
        f = open(self.krb_cache_path/'active_partition', "w")
        f.write(self.partition_name)
        f.close()

    def add_login(self, service:str, user:str, password:str):
        self.authentications.append(Authentication(service, user, password))

    def add_login_from_file(self, service:str, file:str):
        if not os.path.isfile(os.getcwd()+"/"+file+".py"):
            self.log.error(f"Couldn't find file {file} in PWD")
            raise

        sys.path.append(os.getcwd())
        i = __import__(file, fromlist=[''])
        self.add_login(service, i.user, i.password)
        self.log.info(f"Added login data from file: {file}")

    def get_login(self, service:str, user:str=""):
        for auth in self.authentications:
            if service == auth.service and (user == auth.user if user else True):
                return auth
        self.log.error(f"Couldn't find login for service: {service}, user: {user}")

    def rm_login(self, service:str, user:str):
        for auth in self.authentications:
            if service == auth.service and user == auth.user:
                self.authentications.remove(auth)
                return

    def change_user(self, user):
        if not self.cache_initialised: raise RuntimeError('Nanorc\'s kerberos cache wasn\'t initialised!')
        if user == self.user:
            return True

        previous = self.user
        self.user = user

        if self.check_kerberos_credentials(silent=True):
            return True

        new_ticket = self.new_kerberos_ticket()
        if not new_ticket:
            self.user = previous
            return False
        return True

    def partition_in_use(self):
        if not self.cache_initialised: raise RuntimeError('Nanorc\'s kerberos cache wasn\'t initialised!')
        if os.path.isfile(self.krb_cache_path/'active_partition'):
            f = open(self.krb_cache_path/'active_partition', "r")
            pname = f.read()
            return pname
        return None

    def check_kerberos_credentials(self, silent=False):
        if not self.cache_initialised: raise RuntimeError('Nanorc\'s kerberos cache wasn\'t initialised!')
        while True:
            kerb_user = self.get_kerberos_user(silent=silent)
            if kerb_user:
                self.log.info(f'Detected kerb ticket for user: \'{kerb_user}\'')
            else:
                self.log.info(f'No kerb ticket')

            if not kerb_user:
                if not silent: self.log.error('CredentialManager: No kerberos ticket!')
                return False
            elif kerb_user != self.user: # we enforce the user is thec
                return False
            else:
                return True if subprocess.call(['klist', '-s'], env=self.krbenv) == 0 else False

    def get_kerberos_user(self, silent=False):
        if not self.cache_initialised: raise RuntimeError('Nanorc\'s kerberos cache wasn\'t initialised!')
        args=['klist'] # on my mac, we can specify --json and that gives everything nicely in json format... but...
        proc = subprocess.run(args, capture_output=True, text=True, env=self.krbenv)
        raw_kerb_info = proc.stdout.split('\n')
        if not silent: self.log.info(proc.stdout)
        kerb_user = None
        for line in raw_kerb_info:
            split_line = line.split(' ')
            split_line =  [x for x in split_line if x!='']
            find_princ = line.find('Default principal')
            if find_princ!=-1:
                kerb_user = split_line[2]
                kerb_user = kerb_user.split('@')[0]

            if kerb_user:
                return kerb_user
        return None

    def new_kerberos_ticket(self):
        if not self.cache_initialised: raise RuntimeError('Nanorc\'s kerberos cache wasn\'t initialised!')
        success = False

        while not success:
            print(f'Password for {self.user}@CERN.CH:')
            try:
                password = getpass()
            except KeyboardInterrupt:
                return False

            p = subprocess.Popen(['kinit', self.user+'@CERN.CH'],
                                 stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
                                 env=self.krbenv)
            stdout_data = p.communicate(password.encode())
            print(stdout_data[-1].decode())
            success = p.returncode==0

        return True

    def generate_new_sso_cookie(self, website):
        if not self.cache_initialised: raise RuntimeError('Nanorc\'s kerberos cache wasn\'t initialised!')
        SSO_COOKIE_PATH=tempfile.NamedTemporaryFile(mode='w', prefix="ssocookie", delete=False).name
        max_tries = 3
        it_try = 0
        args=["cern-get-sso-cookie", "--krb", "-r", "-u", website, "-o", f"{SSO_COOKIE_PATH}"]
        env = { 'LD_LIBRARY_PATH':'/lib64'}
        env.update(self.krbenv)
        proc = subprocess.run(args, env=env)
        if proc.returncode != 0:
            self.log.error("CredentialManager: Couldn't get SSO cookie!")
            self.log.error("You need to 'kinit' or 'change_user' and try again!")
            raise RuntimeError("CredentialManager: Couldn't get SSO cookie!")
        return SSO_COOKIE_PATH

credentials = CredentialManager()
