from http import server

from flask import Flask, render_template
import requests
from flask_cors import CORS, cross_origin

import importlib.resources as resources
from nanorc.webuidata import templates

class WebServer:
    def __init__(self, host, port, rest_host, rest_port):
        self.host = host
        self.port = port
        self.rest_host = rest_host
        self.rest_port = rest_port

        root_folder=''
        with resources.path(templates, "index.html") as p:
            ## PL:
            ## this intergalactical piece of dog crap
            ## basically, this is getting where index.html is and cd ../../ to feed the correct root directory
            ## but Hey! this is using importlib.resources!
            p=(str(p)).split('/')[:-2]
            root_folder='/'.join(p)

        self.app = Flask("webserver_nanorc", root_path=root_folder)
        CORS(self.app)

        @cross_origin(supports_credentials=True)
        def index():
            if not self.rest_host or not self.rest_port:
                raise RuntimeError('Rest API endpoint not specified!')
            return render_template('index.html', serverhost=self.rest_host+":"+str(self.rest_port))
        
        self.app.add_url_rule("/",'index',index)

    def run(self):
        if not self.host or not self.port:
            raise RuntimeError('WebUI: no host or port specified!')
        self.app.run(host=self.host, port=self.port,
                     debug=True, use_reloader=False,
                     threaded=True)
