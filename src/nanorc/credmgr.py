

def new_kerberos_ticket(user:str, realm:str, password:str=None, where:str="~/"):
    env = {'KRB5CCNAME': f'DIR:{where}'}
    success = False
    password_provided = password is not None

    while not success:
        if password is None:
            print(f'Password for {user}@{realm}:')
            try:
                from getpass import getpass
                password = getpass()

            except KeyboardInterrupt:
                return False
        import subprocess

        p = subprocess.Popen(
            ['kinit', f'{user}@{realm}'],
            stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE,
            env=env
        )
        stdout_data = p.communicate(password.encode())
        print(stdout_data[-1].decode())
        success = p.returncode==0

        if not success and password_provided:
            raise RuntimeError(f'Authentication error for {user}@{realm}. The password provided (likely in configuration file) is incorrect')

    return True



def get_kerberos_user(silent=False, where:str="~/"):
    import logging
    log = logging.getLogger('get_kerberos_user')

    env = {'KRB5CCNAME': f'DIR:{where}'}
    args=['klist'] # on my mac, I can specify --json and that gives everything nicely in json format... but...
    import subprocess

    proc = subprocess.run(args, capture_output=True, text=True, env=env)
    raw_kerb_info = proc.stdout.split('\n')


    if not silent:
        log.info(proc.stdout)

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



def check_kerberos_credentials(against_user:str, silent=False, where:str="~/"):
    import logging
    log = logging.getLogger('check_kerberos_credentials')

    env = {'KRB5CCNAME': f'DIR:{where}'}

    kerb_user = get_kerberos_user(
        silent=silent,
        where=where
    )

    if not silent:
        if kerb_user:
            log.info(f'Detected kerberos ticket for user: \'{kerb_user}\'')
        else:
            log.info(f'No kerberos ticket found')

    if not kerb_user:
        if not silent: log.info('No kerberos ticket')
        return False
    elif kerb_user != against_user: # we enforce the user is the same
        if not silent: log.info('Another user is logged in')
        return False
    else:
        import subprocess
        ticket_is_valid = subprocess.call(['klist', '-s'], env=env) == 0
        if not silent and not ticket_is_valid:
            log.info('Kerberos ticket is expired')
        return ticket_is_valid



class ServiceAuthentication():
    def __init__(self, service:str, user:str):
        super().__init__()
        self.service = service
        self.user = user


class SimpleAuthentication(ServiceAuthentication):
    def __init__(self, service:str, user:str, password:str):
        super().__init__(service, user)
        self.password = password


class ServiceAccountWithKerberos(ServiceAuthentication):
    def __init__(self, service:str, user:str, password:str, realm:str):
        super().__init__(service, user)
        self.password = password
        self.realm = realm

    def generate_cern_sso_cookie(self, website, kerberos_directory, output_directory):
        args = []
        env = {'KRB5CCNAME': f'DIR:{kerberos_directory}'}

        from nanorc.utils import which
        import sh

        if which('cern-get-sso-cookie'):
            executable = sh.Command("cern-get-sso-cookie")
            args = ["--krb", "-r", "-u", website, "-o", output_directory]
        elif which('auth-get-sso-cookie'):
            executable = sh.Command('auth-get-sso-cookie')
            args = ['-u', website, '-o', output_directory]
        else:
            raise RuntimeError("Couldn't get SSO cookie, there is no 'cern-get-sso-cookie' or 'auth-get-user-token' on your system!")

        env.update(self.krbenv)
        proc = executable(*args, _env=env, _new_session=True)
        if proc.exit_code != 0:
            self.log.error("Couldn't get SSO cookie!")
            self.log.error("You need to 'kinit' or 'change_user' and try again!")
            self.log.error(f'{executable} stdout: {proc.stdout}')
            self.log.error(f'{executable} stderr: {proc.stderr}')
            raise RuntimeError("Couldn't get SSO cookie!")
        return output_directory


class UserAccountWithKerberos(ServiceAuthentication):
    def __init__(self, service:str, user:str, password, realm:str):
        super().__init__(service, user)
        self.password = password
        self.realm = realm



class AuthenticationFactory():
    @staticmethod
    def get_from_dict(service:str, auth_data:dict[str,str]):
        match auth_data['type']:
            case "simple":
                return SimpleAuthentication(
                    service,
                    auth_data['user'],
                    auth_data.get('password'),
                )
            case "service-account":
                return ServiceAccountWithKerberos(
                    service,
                    auth_data['user'],
                    auth_data.get('password'),
                    auth_data['realm'],
                )
            case _:
                raise RuntimeError(f"Authentication method {auth_data['type']} is not supported")



class CredentialManager:
    def __init__(self):
        import logging
        self.log = logging.getLogger(self.__class__.__name__)
        self.authentications = []


    def add_login(self, service:str, data:dict[str,str]):
        self.authentications.append(
            AuthenticationFactory.get_from_dict(service, data)
        )


    def get_login(self, service:str, user:str):
        for auth in self.authentications:
            if service == auth.service and user == auth.user:
                return auth
        self.log.error(f"Couldn't find login for service: {service}, user: {user}")


    def rm_login(self, service:str, user:str):
        for auth in self.authentications:
            if service == auth.service and user == auth.user:
                self.authentications.remove(auth)
                return
        self.log.error(f"Couldn't find login for service: {service}, user: {user}")



class SessionHandler:
    def __init__(self):
        import logging
        self.log = logging.getLogger(self.__class__.__name__)
        self.nanorc_user = None
        self.session_name = None
        self.session_number = None
        self.session_ticket_path = None


    def __get_kerberos_cache_path(self, session_name:str, session_number:int):
        import os
        from pathlib import Path

        return Path(
            os.path.expanduser(f'~/.nanorc_kerbcache_{session_name}_session_{session_number}')
        )


    def session_is_in_use(self, session_name:str, session_number:int):
        cache_path = self.__get_kerberos_cache_path(
            session_name,
            session_number,
        )
        import os
        return os.path.isfile(cache_path/'active_session')


    def start_session(self, session_number, apparatus_id):
        self.session_number = session_number
        self.session_name = apparatus_id # here is the mother of all the session definition questions...
        self.create_session_kerberos_cache()


    def stop_session(self):
        import os
        if os.path.isfile(self.session_ticket_path/'active_session'):
            os.remove(self.session_ticket_path/'active_session')


    def quit(self):

        if self.session_ticket_path is not None:
            self.stop_session()


    def create_session_kerberos_cache(self):
        if self.session_number is None or self.session_name is None:
            raise RuntimeError('Session number (or name) hasn\'t been specified, I cannot create a nanorc kerberos cache')

        self.__get_kerberos_cache_path(self.session_name, self.session_number)
        import os

        if not os.path.isdir(self.session_ticket_path):
            os.mkdir(self.session_ticket_path)


    def start_session(self):

        self.create_session_kerberos_cache()

        if self.session_ticket_path is None:
            raise RuntimeError('Nanorc\'s kerberos cache wasn\'t initialised!')

        f = open(self.session_ticket_path/'active_session', "w")
        f.close()


    def change_user(self, user):
        if self.session_ticket_path is None:
            raise RuntimeError('Nanorc\'s kerberos cache wasn\'t initialised!')

        if user == self.nanorc_user.user:
            return True

        previous = self.nanorc_user
        self.nanorc_user = user

        if check_kerberos_credentials(silent=True):
            return True

        new_ticket = new_kerberos_ticket()

        if not new_ticket:
            self.nanorc_user = previous
            return False
        return True




credentials = CredentialManager()
