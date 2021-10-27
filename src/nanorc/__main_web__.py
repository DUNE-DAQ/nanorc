#!/usr/bin/env python3

"""
Command Line Interface for NanoRC
"""

import click
import time
from flask import Flask, render_template, request, make_response, stream_with_context, render_template_string, url_for, redirect
from nanorc.auth import auth
from threading import Thread
# from flask_sso import SSO

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from nanorc.core import *
from nanorc.cli import loglevels, updateLogLevel, NanoContext
from nanorc.runmgr import SimpleRunNumberManager
from nanorc.cfgsvr import SimpleConfigSaver

rc_context = None
last_action = "None"

app = Flask("nanorc")
# ext = SSO(app=app)

# # CERN Single-Sign-On
# SSO_ATTRIBUTE_MAP = {
#     "ADFS_LOGIN": (True, nickname),
#     "ADFS_EMAIL": (True, email),
# }
# SSO_LOGIN_URL = 
# app.config['SSO_ATTRIBUTE_MAP'] = SSO_ATTRIBUTE_MAP


# @sso.login_handler
# def login_callback(user_info):
#     """Store information in session."""
#     session['user'] = user_info

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
    print("add header")
    response.headers['X-UA-Compatible'] = 'IE=Edge,chrome=1'
    if ('Cache-Control' not in response.headers):
        response.headers['Cache-Control'] = 'public, max-age=0'
    return response

@app.route("/statusstream")
def statusstream():
    @stream_with_context
    def generate():
        counter = 0 
        while True:
            if rc_context:
                text=rc_context.rc.console.export_html()
                rc_context.rc.status()
                status_text=rc_context.rc.console.export_html()
                start=status_text.find("<body>")
                end=status_text.find("</body>")
                status_text=status_text[start+6:end]
                title_text=rc_context.rc.apparatus_id+str(counter)
                counter+=1
                ### How nice would it be, if <!-- separator --> could actually be the separator
                ### Unfortunately, it gets stripped somewhere, and in index.html, we have to use <code>
                ### to separate, which is extremely distaceful
                yield f"{counter} {status_text}<!-- separator -->"
                time.sleep(2)
            else:
                return

    return app.response_class(generate())

@app.route('/sendcmd', methods=['POST'])
def sendcmd():
    if rc_context:
        if request.method == "POST":
            if request.form.get('button') == 'BOOT':
                last_action = "BOOT"
                print("BOOTING")
                Thread(target=rc_context.rc.boot).start()
                print("BOOTING2")
                
            elif request.form.get('button') == 'TERMINATE':
                last_action = "TERMINATE"
                print("TERMINATING")
                Thread(target=rc_context.rc.terminate).start()
                print("TERMINATING2")
            else:
                pass
        else:
            pass
    return redirect(url_for("index"))
    
@app.route('/')
@app.route('/index')
@auth.login_required
def index():
    if rc_context:
        return render_template("index.html",
                               title=rc_context.rc.apparatus_id,
                               top_level=rc_context.rc.cfg.top_cfg,
                               buttons=[html_buttons["boot"], html_buttons["terminate"]])
    else:
        return "Best thing since light saber"

@click.command()
@click.option('-t', '--traceback', is_flag=True, default=False, help='Print full exception traceback')
@click.option('-l', '--loglevel', type=click.Choice(loglevels.keys(), case_sensitive=False), default='INFO', help='Set the log level')
@click.option('--timeout', type=int, default=60, help='Application commands timeout')
@click.option('--cfg-dumpdir', type=click.Path(), default="./", help='Path where the config gets copied on start')
@click.argument('top_cfg', type=click.Path(exists=True))
@click.pass_obj
@click.pass_context
def cli(ctx, obj, traceback, loglevel, timeout, cfg_dumpdir, top_cfg):

    obj.print_traceback = traceback

    grid = Table(title='Shonky Web NanoRC', show_header=False, show_edge=False)
    grid.add_column()
    grid.add_row("This is an admittedly shonky nanp RC to control DUNE-DAQ applications.")
    grid.add_row("  Give it a command and it will do your biddings,")
    grid.add_row("  but trust it and it will betray you!")
    grid.add_row("Use it with care!")

    obj.console.print(Panel.fit(grid))

    if loglevel:
        updateLogLevel(loglevel)

    try:
        print("buidling nanorc")
        rc = NanoRC(obj.console, top_cfg,
                        SimpleRunNumberManager(),
                        SimpleConfigSaver(cfg_dumpdir),
                        timeout)
        rc_context = obj
        rc_context.top_json = top_cfg
        rc_context.rc = rc
        app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False )

    except Exception as e:
        logging.getLogger("cli").exception("Failed to build NanoRC")
        raise click.Abort()

    def cleanup_rc():
        logging.getLogger("cli").warning("NanoRC context cleanup: Terminating RC before exiting")
        rc.terminate()
        ctx.exit(rc.return_code)

    ctx.call_on_close(cleanup_rc)
    
def main():
    print("main")
    global rc_context
    # global last_action
    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

    console = Console(record=True)
    rc_context = NanoContext(console)

    try:
        print("calling cli")
        cli(obj=rc_context, show_default=True)
        
    except Exception as e:
        console.log("[bold red]Exception caught[/bold red]")
        if not obj.print_traceback:
            console.log(e)
        else:
            console.print_exception()


if __name__ == '__main__':
    main()
