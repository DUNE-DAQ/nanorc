import requests
import json
from .credmgr import credentials,Authentication

class RunNumberManager:
    """A class that interacts with the run number db"""
    
    def __init__(self, socket):
        super(RunNumberManager, self).__init__()
        self.run = None
        self.API_SOCKET=socket
        auth = credentials.get_login("rundb")
        self.API_USER=auth.user
        self.API_PSWD=auth.password

    def get_run_number(self):
        req = requests.get(self.API_SOCKET+'/runnumber/get', auth=(self.API_USER, self.API_PSWD))
        self.run = req.json()[0][0][0]
        return self.run

    def increment_run_number(self):
        req = requests.get(self.API_SOCKET+'/runnumber/increment', auth=(self.API_USER, self.API_PSWD))
        self.run = req.json()[0][0][0]
        return self.run

    def update_stop(self, run_number):
        req = requests.get(self.API_SOCKET+'/runnumber/updatestop/'+str(run_number), auth=(self.API_USER, self.API_PSWD))
        return req.json()[0][0][0]
    

def test_runmgr():
    rnm = RunNumberManager()
    rnm.get_run_number()
    print(f"Run: {rnm.run}")
    rnm.increment_run_number() 
    print(f"Run: {rnm.run} after incrementing")
    date = rnm.update_stop(rnm.run)
    print(f"Run {rnm.run} finished at: {date}")
    
if __name__ == '__main__':
    test_runmgr()
