from flask import Flask, request, make_response, jsonify
from flask_restful import Api, Resource
from flask_cors import CORS, cross_origin
import os
import logging
import time
from nanorc.auth import auth
import threading
from nanorc.node_render import status_data
from rich.console import Console
from anytree.resolver import Resolver
from anytree.exporter import DictExporter
from os import path
import nanorc.argval as argval

class NanoWebContext:
    def __init__(self, console: Console):
        """
        Nanorc Context for rest api use.
        Args: console (Console): rich console for messages and logging
        """
        super(NanoWebContext, self).__init__()
        self.console = console
        self.print_traceback = False
        self.rc = None
        self.obj = None
        self.last_command = None
        self.last_path = None
        self.worker_thread = None
        self.commands = []

## PL:
## I don't know how else to do this, if this is None, the variable isn't global
rc_context = NanoWebContext(Console())

def convert_nanorc_return_code(return_code:int):
    return 200 if return_code == 0 else 500


class status(Resource):
    @auth.login_required
    def get(self):
        if rc_context.worker_thread and rc_context.worker_thread.is_alive():
            return "I'm busy!"
        data = status_data(rc_context.rc.topnode)
        resp = make_response(jsonify(data))
        return resp

class node(Resource):
    @auth.login_required
    def get(self, path):
        if rc_context.worker_thread and rc_context.worker_thread.is_alive():
            return "I'm busy!"
        path = path.replace(".", "/")
        try:
            node = argval.validate_node_path(rc_context, None, path)
        except Exception as ex:
            resp = make_response(f"Couldn't find {path} in the tree")
            return resp

        r = Resolver('name')
        data = status_data(node, False)
        resp = make_response(data, 200)
        return resp

class tree(Resource):
    @auth.login_required
    def get(self):
        if rc_context.worker_thread and rc_context.worker_thread.is_alive():
            return "I'm busy!"
        if rc_context.rc.topnode:
            exporter = DictExporter(attriter=lambda attrs: [(k, v) for k, v in attrs if k == "name"])
            json_tree = exporter.export(rc_context.rc.topnode)
            resp = make_response(jsonify(json_tree))
            return resp
        return "No tree initialised!"

# @api.resource('/nanorcrest/fsm', methods=['GET'])
class fsm(Resource):
    @auth.login_required
    def get(self):
        if rc_context.worker_thread and rc_context.worker_thread.is_alive():
            return "I'm busy!"
        topnode = rc_context.rc.topnode
        if topnode:
            fsm_data = {
                'states': topnode.fsm.states_cfg,
                'transitions': topnode.fsm.transitions_cfg
            }
            resp = make_response(jsonify(fsm_data))
            return resp
        return "No FSM initiated!"

def parse_argument(form, ctx):
    commands = ctx.commands
    rc = ctx.rc

    cmd=form['command'].lower()
    ret = {}

    for param in commands[cmd].params:
        value = None
        if param.name in form or param.required:
            value = form[param.name]
        else:
            value = param.default

        if value != None:
            if str(param.type) == 'INT':
                value = int(value)
            elif str(param.type) == 'BOOL':
                value = True if value == 'true' else False

        ### <hack>
        if param.name == 'timeout':
            value = argval.validate_timeout(None, None, value)
        elif param.name == 'node_path':
            value = argval.validate_node_path(rc_context, None, value)
        elif param.name == 'stop_wait':
            value = argval.validate_stop_wait(None, None, value)
        elif param.name == 'pin_thread_file':
            value = argval.validate_path_exists(value)
        elif param.name == 'partition':
            value = argval.validate_partition(None, None, value)

        ### </hack>
        ret[param.name] = value

    print(f"Command args: {ret}")
    return ret


class command(Resource):
    @auth.login_required
    def get(self):
        resp_data = {}
        state = rc_context.rc.topnode.state
        state_allowed_transitions = []
        rc_context.rc.topnode.fsm.transitions_cfg
        for transition in rc_context.rc.topnode.fsm.transitions_cfg:
            if transition['source'] == state or transition['source'] == '*':
                state_allowed_transitions += [transition['trigger']]

        for key, command_list in rc_context.rc.topnode.fsm.command_sequences.items():
            add_it = True
            for cmd in command_list:
                if not cmd['cmd'] in state_allowed_transitions and not cmd['optional']:
                    add_it = False
                    break
                elif cmd['cmd'] in state_allowed_transitions:
                    break

            if add_it:
                state_allowed_transitions += [key]

        if state != 'none':
            state_allowed_transitions += list(rc_context.rc.custom_cmd.keys()) + ["include", "exclude"]
        if state == 'running':
            state_allowed_transitions += ["change_rate"]
        if state in ['configured', 'running', 'ready']:
            state_allowed_transitions += ["pin_threads"]

        if 'shell'          in state_allowed_transitions: state_allowed_transitions.remove('shell'         )
        if 'wait'           in state_allowed_transitions: state_allowed_transitions.remove('wait'          )
        if 'expert_command' in state_allowed_transitions: state_allowed_transitions.remove('expert_command')
        if 'ls'             in state_allowed_transitions: state_allowed_transitions.remove('ls'            )
        if 'status'         in state_allowed_transitions: state_allowed_transitions.remove('status'        )

        for cmd_name, cmd_data in rc_context.commands.items():
            if not cmd_name in state_allowed_transitions: continue
            resp_data[cmd_name] = [
                {
                    param.name:
                    {
                        'type': 'PATH' if 'Path' in str(param.type) else str(param.type),
                        'default': param.default,
                        'required': param.required
                    }
                } for param in cmd_data.params ]



        return make_response(jsonify(resp_data))

    @auth.login_required
    def post(self):
        if rc_context.worker_thread and rc_context.worker_thread.is_alive():
            return "busy!"
        try:
            form = request.form
            cmd = form['command'].lower()

            # <hack>
            def get_underlying_func(func):
                if hasattr(func, '__wrapped__'):
                    # pass_obj, and pass_context create new object that aren't the function
                    # anyway to make this clean??
                    return get_underlying_func(func.__wrapped__)
                else:
                    return func
            # </hack>

            target = get_underlying_func(rc_context.commands[cmd].callback)

            if not target:
                raise RuntimeError(f'I don\'t know of command {cmd}')

            logger = logging.getLogger()
            if os.path.isfile('rest_command.log'):
                os.remove('rest_command.log')
            log_handle = logging.FileHandler("rest_command.log")
            logger.addHandler(log_handle)

            rc_context.worker_thread = threading.Thread(
                target=target,
                name="command-worker",
                args=[rc_context.ctx,rc_context],
                kwargs=parse_argument(form, rc_context)
            )
            rc_context.worker_thread.start()
            rc_context.worker_thread.join()
            rc_context.last_command = cmd
            rc_context.last_path = path

            logger.removeHandler(log_handle)
            logs = open('rest_command.log').read()

            resp_data = {
                "command"    : form,
                "return_code": int(rc_context.rc.return_code),
                "logs"       : logs
            }
            resp = make_response(resp_data)
            return resp

        except Exception as e:
            print(e)
            resp = make_response(jsonify({"Exception": str(e)}))
            return resp


@auth.login_required
def index():
    return "Best thing since light saber"


class RestApi:
    def __init__(self, rc_context, host, port):
        self.nanorc = rc_context.rc
        self.host = host
        self.port = port
        self.app = Flask("nanorc_rest_api")
        self.api = Api(self.app)
        CORS(self.app)

        self.api.add_resource(status,  '/nanorcrest/status')
        self.api.add_resource(node,    '/nanorcrest/node/<path>')
        self.api.add_resource(tree,    '/nanorcrest/tree')
        self.api.add_resource(fsm,     '/nanorcrest/fsm')
        self.api.add_resource(command, '/nanorcrest/command')
        self.app.add_url_rule('/', view_func=index)

    def run(self):
        if not self.host or not self.port:
            raise RuntimeError('RestAPI: no host or port specified!')

        self.app.run(host=self.host, port=self.port,
                     debug=True, use_reloader=False,
                     threaded=True)
