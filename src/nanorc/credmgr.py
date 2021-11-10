import sys, os
import logging

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

class Authentication():
    def __init__(self, service:str, user:str, password:str):
        self.service = service
        self.user = user
        self.password = password
    
class CredentialManager():
    def __init__(self):
        self.authentications = []
        
    def add_login(self, service:str, user:str, password:str):
        self.authentications.append(Authentication(service, user, password))

    def add_login_from_file(self, service:str, file:str):
        if not os.path.isfile(os.getcwd()+"/"+file+".py"):
            log.error(f"Couldn't find file {file} in PWD")
            raise
            
        sys.path.append(os.getcwd())
        i = __import__(file, fromlist=[''])
        self.add_login(service, i.user, i.password)
        log.info(f"Added login data from file: {file}")
        # for auth in self.authentications:
        #     print(auth.service, auth.user)
        
    def get_login(self, service:str, user:str):
        for auth in self.authentications:
            if service == auth.service and user == auth.user:
                return auth
        log.error(f"Couldn't find login for service: {service}, user: {user}")
        
    def get_login(self, service:str):
        for auth in self.authentications:
            if service == auth.service:
                return auth
        log.error(f"Couldn't find login for service: {service}")

    def rm_login(self, service:str, user:str):
        for auth in self.authentications:
            if service == auth.service and user == auth.user:
                self.authentications.remove(auth)
                return

credentials = CredentialManager()
        
