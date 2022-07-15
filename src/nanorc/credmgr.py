import sys, os
import logging
from getpass import getpass
import subprocess
import logging
import tempfile

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

    def get_login(self, service:str, user:str):
        for auth in self.authentications:
            if service == auth.service and user == auth.user:
                return auth
        self.log.error(f"Couldn't find login for service: {service}, user: {user}")

    def get_login(self, service:str):
        for auth in self.authentications:
            if service == auth.service:
                return auth
        self.log.error(f"Couldn't find login for service: {service}")

    def rm_login(self, service:str, user:str):
        for auth in self.authentications:
            if service == auth.service and user == auth.user:
                self.authentications.remove(auth)
                return

    def change_user(self, user):
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

    def check_kerberos_credentials(self, silent=False):
        while True:
            args=["klist"] # on my mac, we can specify --json and that gives everything nicely in json format... but...
            proc = subprocess.run(args, capture_output=True, text=True)
            raw_kerb_info = proc.stdout.split('\n')
            kerb_user = None
            valid_until = None
            for line in raw_kerb_info:
                split_line = line.split(' ')
                split_line =  [x for x in split_line if x!='']
                find_princ = line.find('Default principal')
                if find_princ!=-1:
                    kerb_user = split_line[2]
                    kerb_user = kerb_user.split('@')[0]

                if kerb_user:
                    break

            if not kerb_user:
                if not silent: self.log.error('CredentialManager: No kerberos ticket!')
                return False
            elif kerb_user != self.user: # we enforce the user is thec
                return False
            else:
                return True if subprocess.call(['klist', '-s']) == 0 else False



    def new_kerberos_ticket(self):
        success = False

        while not success:
            print(f'Password for {self.user}@CERN.CH:')
            try:
                password = getpass()
            except KeyboardInterrupt:
                return False

            p = subprocess.Popen(['kinit', self.user+'@CERN.CH'],
                                 stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout_data = p.communicate(password.encode())
            print(stdout_data[-1].decode())
            success = p.returncode==0

        return True

    def generate_new_sso_cookie(self, website):
        SSO_COOKIE_PATH=tempfile.NamedTemporaryFile(mode='w', prefix="ssocookie", delete=False).name
        max_tries = 3
        it_try = 0
        args=["cern-get-sso-cookie", "--krb", "-r", "-u", website, "-o", f"{SSO_COOKIE_PATH}"]
        proc = subprocess.run(args, env={ 'LD_LIBRARY_PATH':'/lib64' })
        if proc.returncode != 0:
            self.log.error("CredentialManager: Couldn't get SSO cookie!")
            raise RuntimeError("CredentialManager: Couldn't get SSO cookie!")
        return SSO_COOKIE_PATH

credentials = CredentialManager()
