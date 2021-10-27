#!/usr/bin/env python3

"""
Command Line Interface for NanoRC
"""

import click
import time
import re
import requests
from flask import Flask, render_template, request, make_response, stream_with_context, render_template_string, url_for, redirect
from nanorc.auth import auth, APP_PASS
from threading import Thread
from nanorc.tail import Tail
# from flask_sso import SSO

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from nanorc.core import *
from nanorc.cli import loglevels, updateLogLevel, NanoContext
from nanorc.runmgr import SimpleRunNumberManager
from nanorc.cfgsvr import SimpleConfigSaver

last_action = "None"
console_context = None
API_SOCKET = None

app = Flask("nanorc")

html_buttons = {
    "status":"<form method=\"GET\" action=\"/sendcmd\"><input type=\"submit\" value=\"STATUS\" name=\"button\"/></form>",
    "boot":"<form method=\"POST\" action=\"/sendcmd\"><input type=\"submit\" value=\"BOOT\" name=\"button\"/></form>",
    "init":"<form method=\"POST\" action=\"/sendcmd\"><input type=\"submit\" value=\"INIT\" name=\"button\"/></form>",
    "conf":"<form method=\"POST\" action=\"/sendcmd\"><input type=\"submit\" value=\"CONF\" name=\"button\"/></form>",
    "start":"<form method=\"POST\" action=\"/sendcmd\"><input type=\"submit\" value=\"START\" name=\"button\"/></form>",
    "stop":"<form method=\"POST\" action=\"/sendcmd\"><input type=\"submit\" value=\"STOP\" name=\"button\"/></form>",
    "scrap":"<form method=\"POST\" action=\"/sendcmd\"><input type=\"submit\" value=\"SCRAP\" name=\"button\"/></form>",
    "terminate":"<form method=\"POST\" action=\"/sendcmd\"><input type=\"submit\" value=\"TERMINATE\" name=\"button\"/></form>",
    "pause":"<form method=\"POST\" action=\"/sendcmd\"><input type=\"submit\" value=\"PAUSE\" name=\"button\"/></form>",
    "resume":"<form method=\"POST\" action=\"/sendcmd\"><input type=\"submit\" value=\"RESUME\" name=\"button\"/></form>"
}

@app.after_request
def add_header(response):
    response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
    if ('Cache-Control' not in response.headers):
        response.headers['Cache-Control'] = 'public, max-age=0'
    return response

# @app.route("/statusstream")
# def statusstream():
#     @stream_with_context
#     def generate():
#         counter = 0 
#         while True:
#                 text=rc_context.rc.console.export_html()
#                 rc_context.rc.status()
#                 status_text=rc_context.rc.console.export_html()
#                 start=status_text.find("<body>")
#                 end=status_text.find("</body>")
#                 status_text=status_text[start+6:end]
#                 counter+=1
#                 yield f"Frame: {counter} {status_text}<!-- separator -->"
#                 time.sleep(2)
#             else:
#                 return

#     return app.response_class(generate())

# def callback(line):
#     print(line)
#     return logs.append(line)

# @app.route("/taillog")
# def taillog():
#     @stream_with_context
#     def generate():
#         while True:
#             if len(tail_threads)>0:
#                 break

#             for f in os.listdir("."):
#                 if re.match("log_.*txt", f):
#                     t = Tail(f)
#                     t.register_callback(callback)
#                     tail_threads.append(Thread(target=t.follow).start())

#             if len(tail_threads)>0:
#                 break

#             time.sleep(1)

#         while True:
#             print(logs)
#             yield "<!-- separator-->".join(logs)
#             time.sleep(1)

#     return app.response_class(generate())
            
@app.route('/sendcmd', methods=['POST'])
def sendcmd():
    global API_SOCKET
    if request.method == "POST":
        post_data = {"cmd": request.form.get('button')}
        try:
            user = list(APP_PASS.keys())[0]
            pswd = list(APP_PASS.values())[0]
            r = requests.post(API_SOCKET+"/nanorcrest/sendCmd/",
                              data=post_data,
                              auth=(user, pswd),
                              timeout=120)
        except requests.HTTPError as exc:
            error = f"{__name__}: NanoRC Web: HTTP Error (maybe failed auth, maybe ill-formed post message, ...)"
            raise RuntimeError(error) from exc
        except requests.ConnectionError as exc:
            error = f"{__name__}: NanoRC Web: Connection to {API_SOCKET} wasn't successful"
            raise RuntimeError(error) from exc
        except requests.Timeout as exc:
            error = f"{__name__}: NanoRC Web: Connection to {API_SOCKET} timed out"
            raise RuntimeError(error) from exc
    resp = make_response(redirect(url_for("index")))
    resp.set_cookie(r.text)
    return resp
    
@app.route('/')
@app.route('/index', methods=['GET'])
@auth.login_required
def index():
    global API_SOCKET
    last_cmd = "None"
    buttons = [html_buttons["boot"]]
    if len(request.cookies): ## we came from sencmd
        last_cmd = request.cookies.get["sent_cmd"]
        
        ## absolutely fab FSM
        if   last_cmd == "BOOT": buttons = [html_buttons["init"], html_buttons["terminate"]]
        elif last_cmd == "INIT": buttons = [html_buttons["conf"], html_buttons["terminate"]]
        elif last_cmd == "CONF": buttons = [html_buttons["start"],html_buttons["scrap"]]
        elif last_cmd == "START" or last_cmd == "RESUME":
            buttons = [html_buttons["stop"], html_buttons["pause"]]
        elif last_cmd == "PAUSE": buttons = [html_buttons["resume"]]
        elif last_cmd == "STOP": buttons = [html_buttons["scrap"]]
        elif last_cmd == "SCRAP": buttons = [html_buttons["terminate"]]
        return render_template("index.html",
                               last_action=last_cmd,
                               title=request.cookies.get["apparatus_id"],
                               top_level=request.cookies.get["top_cfg"],
                               buttons=buttons,
                               run=request.cookies.get["run_number"]
                               )

    else:
        post_data = {"cmd": "STATUS"}
        try:
            user = list(APP_PASS.keys())[0]
            pswd = list(APP_PASS.values())[0]
            r = requests.post(API_SOCKET+"/nanorcrest/sendCmd",
                              data=post_data,
                              auth=(user, pswd),
                              timeout=2)
        except requests.HTTPError as exc:
            error = f"{__name__}: NanoRC Web: HTTP Error (maybe failed auth, maybe ill-formed post message, ...)"
            raise RuntimeError(error) from exc
        except requests.ConnectionError as exc:
            error = f"{__name__}: NanoRC Web: Connection to {API_SOCKET} wasn't successful"
            raise RuntimeError(error) from exc
        except requests.Timeout as exc:
            error = f"{__name__}: NanoRC Web: Connection to {API_SOCKET} timed out"
            raise RuntimeError(error) from exc

        data = r.json()
        html_render = data["console_html"]
        css_data_start=html_render.find("<style>")
        css_data_end=html_render.find("</style>")+8
        css_data=html_render[css_data_start:css_data_end]
        status_data_start=html_render.find("<code>")
        status_data_end=html_render.find("</code>")+7
        status_data=html_render[status_data_start:status_data_end]
        render_data = {
            "css": css_data,
            "nanorc_status": status_data,
            "last_action":"None",
            "title": data["apparatus_id"],
            "top_level": data["top_cfg"],
            "buttons": buttons,
            "run": data["run_number"]
        }
        
        return render_template("index.html", **render_data)

class ConsoleContext:
    """docstring for NanoContext"""
    def __init__(self, console: Console):
        """Nanorc Context for click use.
        
        Args:
            console (Console): rich console for messages and logging
        """
        super(ConsoleContext, self).__init__()
        self.console = console

    
@click.command()
@click.option('--host', type=str, default="0.0.0.0", help='Which host should this HTML server be run on')
@click.option('--port', type=int, default=5005, help='which port to use')
@click.argument('api-socket', type=str, default="0.0.0.0:5001")
@click.pass_obj
@click.pass_context
def cli(ctx, obj, host, port, api_socket):
    global API_SOCKET
    API_SOCKET="http://"+api_socket
    console_context.console.log(f"Starting up on http://{host}:{port}, and using the REST API socket: {API_SOCKET}")
    app.run(host=host, port=port, debug=True, use_reloader=False)
    
def main():
    global console_context
    console = Console()
    console_context = ConsoleContext(console)
    try:
        cli()
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        console.log(e)

if __name__ == '__main__':
    main()
