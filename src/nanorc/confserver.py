import logging
from rich.console import Console
from flask_restful import Resource
from flask import request, abort, make_response, jsonify

class ConfigurationEndpoint(Resource):
    def __init__(self, config_data, *args, **kwargs):
        self.conf_data = config_data
        super().__init__(*args, **kwargs)
        self.log = logging.getLogger('ConfigurationEndpoint')

    def post(self):
        self.log.debug(f'POST "ConfigurationEndpoint" request with args: {request.args}')
        res = {}
        try:
            name = request.args['name']
            conf_json = request.json
            self.conf_data[name] = conf_json
            res['success'] = True
        except Exception as e:
            res['error'] = str(e)
            res['success'] = False
        return make_response(jsonify(res))

    def get(self):
        self.log.debug(f'GET "ConfigurationEndpoint" request with args: {request.args}')
        name = request.args.get('name')

        if not name:
            return make_response(jsonify(list(self.conf_data.keys())))

        self.log.debug(f"Looking for config {name}")
        if name not in self.conf_data:
            abort(404, description=f'{name} not in configurations store, available configs are: {list(self.conf_data.keys())}')

        data = self.conf_data.get(name)
        return make_response(jsonify(data))

class ConfigUploadFailed(Exception):
    """Couldn't upload the configuration """
    pass
    def __init__(self, name, path):
        self.name = name
        self.path = path
        super().__init__(f"Couldn't upload the configuration {self.name} in {self.path} to nanorc's internal configuration server")

class ConfServer:
    def __init__(self, port):
        self.log = logging.getLogger('nano-conf-service')
        self._start_conf_service(port)
        self.port = port

    def _start_conf_service(self, port):
        from flask import Flask
        from flask_restful import Api

        self.app = Flask('nano-conf-svc')
        self.api = Api(self.app)
        config_data = {}
        self.api.add_resource(
            ConfigurationEndpoint, "/configuration",
            methods = ['GET', 'POST'],
            resource_class_kwargs = {"config_data":config_data}
        )

        from .utils import FlaskManager
        self.manager = FlaskManager(
            port = port,
            app = self.app,
            name = "nano-conf-svc"
        )

        self.manager.start()
        while not self.manager.is_ready():
            from time import sleep
            sleep(0.1)

    def add_configuration(self, name, path):
        from nanorc.argval import validate_conf_name
        from pathlib import Path
        validate_conf_name({}, {}, name)
        from requests import post
        header = {
            'Accept' : 'application/json',
            'Content-Type':'application/json'
        }
        import json
        from nanorc.utils import get_json_recursive

        try:
            r = post(
                f'http://0.0.0.0:{self.port}/configuration?name={name}',
                headers=header,
                data=json.dumps(get_json_recursive(Path(path)))
            )
        except Exception as e:
            raise ConfigUploadFailed(name, path) from e

        if not r.json()['success']:
            raise ConfigUploadFailed(name, path)

    def terminate(self):
        self.manager.stop()
