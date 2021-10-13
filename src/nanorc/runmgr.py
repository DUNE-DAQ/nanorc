import requests
import json
from .credmgr import credentials,Authentication
import logging

class SimpleRunNumberManager:
    def __init__(self):
        self.run_number = None

    def get_run_number(self):
        return self.run_number

    def set_run_number(self, run:int):
        self.run_number = run

class RunNumberDBManager:
    """A class that interacts with the run number db"""

    def __init__(self, socket):
        super(RunNumberDBManager, self).__init__()
        self.log = logging.getLogger(self.__class__.__name__)
        self.run = None
        self.API_SOCKET=socket
        auth = credentials.get_login("rundb")
        self.API_USER=auth.user
        self.API_PSWD=auth.password
        self.timeout = 2
        
    def get_run_number(self):
        self._increment_run_number()
        return self._get_run_number()
    
    def _get_run_number(self):
        try:
            req = requests.get(self.API_SOCKET+'/runnumber/get',
                               auth=(self.API_USER, self.API_PSWD),
                               timeout=self.timeout)
            req.raise_for_status()
        except requests.HTTPError as exc:
            error = f"{__name__}: RunDB: Failed authentication"
            self.log.error(error)
            raise RuntimeError(error) from exc
        except requests.ConnectionError as exc:
            error = f"{__name__}: Connection to {self.API_SOCKET} wasn't successful"
            self.log.error(error)
            raise RuntimeError(error) from exc
        except requests.Timeout as exc:
            error = f"{__name__}: Connection to {self.API_SOCKET} timed out"
            self.log.error(error)
            raise RuntimeError(error) from exc
        
        self.run = req.json()[0][0][0]
        return self.run

    def _increment_run_number(self):
        try:
            req = requests.get(self.API_SOCKET+'/runnumber/increment',
                               auth=(self.API_USER, self.API_PSWD),
                               timeout=self.timeout)
            req.raise_for_status()
        except requests.HTTPError as exc:
            error = f"{__name__}: RunDB: Failed authentication"
            self.log.error(error)
            raise RuntimeError(error) from exc
        except requests.ConnectionError as exc:
            error = f"{__name__}: Connection to {self.API_SOCKET} wasn't successful"
            self.log.error(error)
            raise RuntimeError(error) from exc
        except requests.Timeout as exc:
            error = f"{__name__}: Connection to {self.API_SOCKET} timed out"
            self.log.error(error)
            raise RuntimeError(error) from exc
        
            
        self.run = req.json()[0][0][0]
        return self.run

    def _update_stop(self, run_number):
        try:
            req = requests.get(self.API_SOCKET+'/runnumber/updatestop/'+str(run_number),
                               auth=(self.API_USER, self.API_PSWD),
                               timeout=self.timeout)
            req.raise_for_status()
        except requests.HTTPError as exc:
            error = f"{__name__}: RunDB: Failed authentication"
            self.log.error(error)
            raise RuntimeError(error) from exc
        except requests.ConnectionError as exc:
            error = f"{__name__}: Connection to {self.API_SOCKET} wasn't successful"
            self.log.error(error)
            raise RuntimeError(error) from exc
        except requests.Timeout as exc:
            error = f"{__name__}: Connection to {self.API_SOCKET} timed out"
            self.log.error(error)
            raise RuntimeError(error) from exc
        
        return req.json()[0][0][0]


def test_runmgr():
    rnm = RunNumberDBManager()
    rnm.get_run_number()
    print(f"Run: {rnm.run}")
    rnm.increment_run_number() 
    print(f"Run: {rnm.run} after incrementing")
    date = rnm.update_stop(rnm.run)
    print(f"Run {rnm.run} finished at: {date}")

if __name__ == '__main__':
    test_runmgr()
