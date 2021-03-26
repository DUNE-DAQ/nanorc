import logging
import requests
import queue
import json
import socket
import threading

from flask import Flask, request, cli
from multiprocessing import Process, Queue
from rich.console import Console
from rich.pretty import Pretty
from .sshpm import AppProcessDescriptor


log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)
cli.show_server_banner = lambda *_: None

class ResponseDispatcher(threading.Thread):

    STOP="RESPONSE_QUEUE_STOP"

    def __init__(self, listener):
        threading.Thread.__init__(self)
        self.listener = listener

    def run(self):

        while True:
            r = self.listener.reponse_queue.get()
            if r == self.STOP:
                break

            self.listener.notify(r)

    def stop(self):
        self.listener.reponse_queue.put_nowait(self.STOP)
        self.join()

class ResponseListener:
    """
    This class describes a notification listener.
    """
    def __init__(self, port : int ):
        self.log = logging.getLogger("ResponseListener")
        self.port = port
        self.reponse_queue = Queue()
        self.handlers = {}
        self.flask = self._create()
        self.dispatcher = ResponseDispatcher(self)
        self.dispatcher.start()

    def __del__(self):
        self.terminate()

    def _create(self) -> Process:
        app = Flask(__name__)

        # @app.route('/response', methods = ['POST'])
        def index():
            json = request.get_json(force=True)
            # enqueue command reply
            self.reponse_queue.put(json)
            return "Response received"

        app.add_url_rule("/response", "index", index, methods=["POST"])

        flask_srv = Process(target=app.run, kwargs={"host": "0.0.0.0", "port": self.port})
        flask_srv.start()
        return flask_srv

    def terminate(self):
        """
        Terminate the listener
        """
        if self.flask:
            self.flask.terminate()
            self.flask.join()
        self.flask = None
        self.dispatcher.stop()

    def register(self, app: str, handler):
        """
        Register a new notification handler
        
        :param      app:           The application
        :type       app:           str
        :param      handler:       The handler
        :type       handler:       { type_description }
        
        :rtype:     None
        
        :raises     RuntimeError:  { exception_description }
        """
        if app in self.handlers:
            raise RuntimeError(f"Handler already registered with notification listerner for app {app}")
        
        self.handlers[app] = handler

    def unregister(self, app: str):
        """
        De-register a notification handler
        
        :param      app:  The application
        :type       app:  str
        
        :returns:   { description_of_the_return_value }
        :rtype:     { return_type_description }
        """
        if not app in self.handlers:
            return RuntimeError(f"No handler registered for app {app}")
        del self.handlers[app]


    def notify(self, reply: dict):
        if 'appname' not in reply:
            raise RuntimeError("No 'appname' field in reply {reply}")

        app = reply["appname"]

        if not app in self.handlers:
            self.log.warning(f"Received notification for unregistered app '{app}'")
            return

        self.handlers[app].notify(reply)


class AppCommander:
    """docstring for DAQAppController"""

    def __init__(
        self, console: Console, app: str, host: str, port: int, response_port: int
    ):
        self.log = logging.getLogger(app)
        self.console = console
        self.app = app
        self.app_host = host
        self.app_port = port
        self.app_url = f"http://{self.app_host}:{str(self.app_port)}/command"
        self.listener_port = response_port
        self.reponse_queue = Queue()
        # self.listener = self._create_listener(response_port)

    def __del__(self):
        pass

    def notify(self, response):
        self.reponse_queue.put(response)

    def ping(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect((self.app_host, self.app_port))
            s.shutdown(2)
            return True
        except:
            return False

    def send_command(
        self,
        cmd_id: str,
        cmd_data: dict,
        entry_state: str = "ANY",
        exit_state: str = "ANY",
        timeout: int = 60,
    ):
        # Use moo schema here?
        cmd = {
            "id": cmd_id,
            "data": cmd_data,
            "entry_state": entry_state,
            "exit_state": exit_state,
        }
        self.log.info(f"Sending {cmd_id} to {self.app} ({self.app_url})")
        self.log.info(json.dumps(cmd, sort_keys=True, indent=2))

        headers = {
            "content-type": "application/json",
            "X-Answer-Port": str(self.listener_port),
        }
        response = requests.post(self.app_url, data=json.dumps(cmd), headers=headers)
        self.log.info(f"Response: {response}")
        try:
            r = self.reponse_queue.get(timeout=timeout)
            self.log.info(f"Received reply from {self.app} to {cmd_id}")
            self.log.info(json.dumps(r, sort_keys=True, indent=2))

        except queue.Empty as e:
            # Proper error handling, please
            self.log.error(f"Timeout while waiting for a reply from {self.app} for command {cmd_id}")
            raise RuntimeError(
                f"Timeout while waiting for a reply from {self.app} for command {cmd_id} "
            )
        return r


class AppSupervisor:
    """Lightweight application supervisor"""

    def __init__(self, console: Console, desc: AppProcessDescriptor, listener: ResponseListener):
        self.console = console
        self.desc = desc
        self.commander = AppCommander(
            console, desc.name, desc.host, desc.port, listener.port
        )
        self.last_sent_command = None
        self.last_ok_command = None
        listener.register(desc.name, self.commander)

    def send_command(
        self,
        cmd_id: str,
        cmd_data: dict,
        entry_state: str = "ANY",
        exit_state: str = "ANY",
        timeout: int = 10,
    ):
        self.last_sent_command = cmd_id
        r = self.commander.send_command(
            cmd_id, cmd_data, entry_state, exit_state, timeout
        )
        if r["result"] == "OK":
            self.last_ok_command = cmd_id
        return r

    def terminate(self):
        del self.commander





def test_listener():
    # import ipdb
    # ipdb.set_trace()
    # a1 = AppCommander(Console(), 'stoka', 'localhost', 12345, 22345)
    # a2 = AppCommander(Console(), 'suka', 'localhost', 12346, 22346)
    # input('>>> Press Enter to init')
    # a1.send_command('init', init, 'NONE', 'INITIAL')
    # a2.send_command('init', init, 'NONE', 'INITIAL')
    # input('>>> Press Enter to Kill')
    # a1._kill_listener()
    # a2._kill_listener()
    import time
    class DummyApp(object):
        """docstring for Dummy"""
        
        def notify(self, reply):
            print(f"Received response: {reply}")

    dummy = DummyApp()

    nl = ResponseListener(56789)
    nl.stoca = 'sjuca'
    nl.register('dummy', dummy)

    time.sleep(0.1)
    url = f"http://localhost:56789/response"

    headers = {
        "content-type": "application/json",
    }
    response = requests.post(url, data=json.dumps({"appname": "dummy"}), headers=headers)
    nl.terminate()

if __name__ == '__main__':
    test_listener()
    
