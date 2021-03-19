import logging
import requests
import queue
import json
import socket

from flask import Flask, request, cli
from multiprocessing import Process, Queue
from rich.console import Console
from rich.pretty import Pretty
from sshpm import AppProcessHandle


log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)
cli.show_server_banner = lambda *_: None


class AppCommander(object):
    """docstring for DAQAppController"""

    def __init__(
        self, console: Console, app: str, host: str, port: int, reply_port: int
    ):
        super(AppCommander, self).__init__()
        self.console = console
        self.app = app
        self.app_host = host
        self.app_port = port
        self.app_url = f"http://{self.app_host}:{str(self.app_port)}/command"
        self.listener_port = reply_port
        self.reply_queue = Queue()
        self.listener = self._create_listener(reply_port)

    def __del__(self):
        self._kill_listener()

    def _kill_listener(self):
        if self.listener:
            self.listener.terminate()
            self.listener.join()
        self.listener = None

    def _create_listener(self, port: int) -> Process:
        app = Flask(__name__)

        # @app.route('/response', methods = ['POST'])
        def index():
            json = request.get_json(force=True)
            # enqueue command reply
            self.reply_queue.put(json)
            return "Response received"

        app.add_url_rule("/response", "index", index, methods=["POST"])

        flask_srv = Process(target=app.run, kwargs={"host": "0.0.0.0", "port": port})
        flask_srv.start()
        return flask_srv

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
        cmd = {
            "id": cmd_id,
            "data": cmd_data,
            "entry_state": entry_state,
            "exit_state": exit_state,
        }
        self.console.log(f"Sending {cmd_id} to {self.app}", Pretty(cmd))

        headers = {
            "content-type": "application/json",
            "X-Answer-Port": str(self.listener_port),
        }
        response = requests.post(self.app_url, data=json.dumps(cmd), headers=headers)
        try:
            r = self.reply_queue.get(timeout=timeout)
            self.console.log(f"Received reply from {self.app} to {cmd_id}", Pretty(r))

        except queue.Empty as e:
            # Proper error handling, please
            self.console.log("Bugger")
            raise RuntimeError(
                f"Timeout while waiting for a reply from {self.app} for command {cmd_id} "
            )
        return r


class AppSupervisor:
    """docstring for AppSupervisor"""

    def __init__(self, console: Console, handle: AppProcessHandle):
        super(AppSupervisor, self).__init__()
        self.console = console
        self.handle = handle
        self.commander = AppCommander(
            console, handle.name, handle.host, handle.port, handle.port + 10000
        )
        self.last_sent_command = None
        self.last_ok_command = None

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
        self.commander._kill_listener()
        del self.commander


# if __name__ == '__main__':

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
