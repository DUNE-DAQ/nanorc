import requests
import json

API_HOST="http://10.73.136.62"
API_PORT="5000"
API_USER="SOMEUSER"
API_PSWD="SOMEPASS"

class RunNumberManager:
    """A class that interacts with the run number db"""
    
    def __init__(self):
        super(RunNumberManager, self).__init__()
        self.run = None

    def get_run_number(self):
        req = requests.get(API_HOST+":"+API_PORT+'/runnumber/get', auth=(API_USER, API_PSWD))
        self.run = req.json()[0][0][0]
        return self.run

    def increment_run_number(self):
        req = requests.get(API_HOST+":"+API_PORT+'/runnumber/increment', auth=(API_USER, API_PSWD))
        self.run = req.json()[0][0][0]
        return self.run

    def update_stop(self, run_number):
        req = requests.get(API_HOST+":"+API_PORT+'/runnumber/updatestop/'+str(run_number), auth=(API_USER, API_PSWD))
        return req.json()[0][0][0]

    def save_next_run_data(self, data):
        pass
    
    def save_end_of_run_data(self, data):
        pass
    

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
