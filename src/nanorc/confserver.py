import logging
from rich.console import Console
from flask_restful import Resource
from flask import request, abort, make_response, jsonify


'''
Resources for Flask app
'''

class RetrieveConf(Resource):
    def get(self):
        log = logging.getLogger('RetrieveConf')
        log.debug(f'GET "RetrieveConf" request with args: {request.args}')
        name = request.args.get('name')

        if not name:
            abort(404, description=f'You need to provide a configuration name!')

        log.debug(f"Looking for config {name}")

        if name not in self.conf_data:
            abort(404, description=f'Couldn\'t find the configuration \"{name}\", available configurations are {list(self.conf_data.keys())}')

        return make_response(jsonify(self.conf_data[name]))

    @classmethod
    def set_conf_data(cls, conf_data):
        cls.conf_data = conf_data
        return cls

class ListConf(Resource):
    def get(self):
        log = logging.getLogger('ListConf')
        log.info(f'GET "RetrieveConf" request')
        return make_response(jsonify(list(self.conf_data.keys())))

    @classmethod
    def set_conf_data(cls, conf_data):
        cls.conf_data = conf_data
        return cls

class ConfServer:
    def __init__(self, name_to_paths_map={}):
        self.log = logging.getLogger('nano-conf-service')

        self.conf_data = {}
        from nanorc.argval import validate_conf_name
        from pathlib import Path
        for name, path in name_to_paths_map.items():
            validate_conf_name({}, {}, name)
            self.conf_data[name] = self.get_json_recursive(Path(path))


    def get_json_recursive(self, path):
        import json, os

        data = {}
        boot = path/"boot.json"
        if os.path.isfile(boot):
            with open(boot,'r') as f:
                data['boot'] = json.load(f)

        for filename in os.listdir(path):
            if os.path.isfile(path/filename) and filename[-5:] == ".info":
                with open(path/filename,'r') as f:
                    data['config_info'] = json.load(f)

        for filename in os.listdir(path/"data"):
            with open(path/'data'/filename,'r') as f:
                app_cmd = filename.replace('.json', '').split('_')
                app = app_cmd[0]
                cmd = "_".join(app_cmd[1:])

                if not app in data:
                    data[app] = {
                        cmd: json.load(f)
                    }
                else:
                    data[app][cmd]=json.load(f)

        return data

    def start_conf_service(self, port):
        from flask import Flask
        from flask_restful import Api

        self.app = Flask('nano-conf-svc')
        self.api = Api(self.app)

        RetrieveConf_withdata = RetrieveConf.set_conf_data(self.conf_data)
        ListConf_withdata     = ListConf.set_conf_data(self.conf_data)

        self.api.add_resource(RetrieveConf_withdata, "/retrieveLast", methods=['GET'])
        self.api.add_resource(ListConf_withdata    , "/"    , methods=['GET'])
        #self.api.add_resource(ListConf_withdata    , "/"            , methods=['GET'])

        from .utils import FlaskManager
        self.manager = FlaskManager(
            port = port,
            app = self.app,
            name = "nano-conf-svc"
        )

        self.manager.start()

    def terminate(self):
        self.manager.stop()
