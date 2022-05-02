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
        self.last_command = None
        self.last_path = None
        self.worker_thread = None

## PL:
## I don't know how else to do this, if this is None, the variable isn't global
rc_context = NanoWebContext(Console())

def convert_nanorc_return_code(return_code:int):
    return 200 if return_code == 0 else 500

def get_argument(form, arg_name, default_val=None, required=True):
    if required:
        return form[arg_name]

    if not form.get(arg_name):
        return default_val

    return form.get(arg_name)

def validatePath(rc, prompted_path):
    hierarchy = []
    if "/" in prompted_path:
        hierarchy = prompted_path.split("/")

    topnode = rc.topnode

    r = Resolver('name')
    try:
        node = r.get(topnode, prompted_path)
    except Exception as ex:
        raise RuntimeError(f"Couldn't find {prompted_path} in the tree") from ex

    return hierarchy


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
            path = validatePath(rc_context.rc, path)
        except Exception as ex:
            resp = make_response(f"Couldn't find {path} in the tree")
            return resp

        r = Resolver('name')
        path = "/".join(path)
        node = r.get(rc_context.rc.topnode, path)
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
            fsm_data = {'states': topnode.fsm.states_cfg,
                        'transitions': topnode.fsm.transitions_cfg
                        }
            resp = make_response(jsonify(fsm_data))
            return resp
        return "No FSM initiated!"

def parse_argument(form, commands):
    cmd=form['command'].lower()
    ret = {}
    for param in commands[cmd].params:
        ret[param.name] = form[param.name] if param.name in form else param.default

        if ret[param.name] == None: continue

        if str(param.type) == 'INT':
            ret[param.name] = int(ret[param.name])
        elif str(param.type) == 'BOOL':
            ret[param.name] = bool(ret[param.name])

    return ret


class command(Resource):
    @auth.login_required
    def get(self):
        resp_data = {}
        state = rc_context.rc.topnode.state
        state_allowed_transitions = []

        for transition in rc_context.rc.topnode.fsm.transitions_cfg:
            if transition['source'] == state or transition['source'] == '*':
                state_allowed_transitions += [transition['trigger']]

        if not state in ['none', "booted"]:
            state_allowed_transitions += list(rc_context.rc.custom_cmd.keys()) + ["enable"+"disable"]
        if state in ['paused', "running"]:
            state_allowed_transitions += ["start_trigger"+ "stop_trigger", "change_rate"]
        if state in ['configured', 'running']:
            print('adding pin_threads')
            state_allowed_transitions += ["pin-threads"]

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
                        'default':param.default,
                        'required':param.required
                    }
                } for param in cmd_data.params ]



        return make_response(jsonify(resp_data))

    @auth.login_required
    def post(self):
        if rc_context.worker_thread and rc_context.worker_thread.is_alive():
            return "busy!"
        try:
            form = request.form
            cmd  = form['command'].lower()
            path = get_argument(form, 'path', default_val=None, required=False)
            print(form)
            target=rc_context.commands[cmd].callback.__wrapped__.__wrapped__ # anyway to makethis clean??
            # target(rc_context.ctx, rc_context, **parse_argument(form, rc_context.commands))

            if not target:
                raise RuntimeError(f'I don\'t know of command {cmd}')

            logger = logging.getLogger()
            if os.path.isfile('rest_command.log'):
                os.remove('rest_command.log')
            log_handle = logging.FileHandler("rest_command.log")
            logger.addHandler(log_handle)

            # if cmd == 'boot' or cmd == 'terminate':
            rc_context.worker_thread = threading.Thread(target=target,
                                                        name="command-worker",
                                                        args=[rc_context.ctx,rc_context],
                                                        kwargs=parse_argument(form, rc_context.commands))
            # elif cmd == 'scrap':
            #     force     = get_argument(form, 'force',     default_val=True, required=False)
            #     args=[force]

            #     rc_context.worker_thread = threading.Thread(target=target,
            #                                                 name="command-worker",
            #                                                 args=args)

            # elif cmd == 'stop':
            #     stop_wait = get_argument(form, 'stop_wait', default_val=0   , required=False)
            #     force     = get_argument(form, 'force',     default_val=True, required=False)
            #     message   = get_argument(form, 'message',   default_val=""  , required=False)

            #     def pause_sleep_stop(force, stop_wait, message):
            #         rc_context.rc.pause(force)
            #         time.sleep(stop_wait)
            #         if rc_context.rc.return_code == 0:
            #             rc_context.rc.stop(force, message=message)

            #     args=[stop_wait, force, message]

            #     rc_context.worker_thread = threading.Thread(target=pause_sleep_stop,
            #                                                 name="command-worker",
            #                                                 args=args)


            # elif cmd == 'start':
            #     run_type               =     get_argument(form, 'run_type'              , default_val='TEST', required=False)
            #     run_num                = int(get_argument(form, 'run_num'               , default_val=None  , required=True ))
            #     disable_data_storage   =     get_argument(form, 'disable_data_storage'  , default_val=False , required=False)
            #     trigger_interval_ticks =     get_argument(form, 'trigger_interval_ticks', default_val=None  , required=False)
            #     message                =     get_argument(form, 'message'               , default_val=''    , required=False)
            #     resume_wait            =     get_argument(form, 'resume_wait'           , default_val=0     , required=False)

            #     if not (run_type=="TEST" or run_type=="PROD"):
            #         raise RuntimeError(f"Wrong run_type (can be either TEST or PROD), yours was: \"{run_type}\"")

            #     def start_sleep_resume(disable_data_storage, run_type, trigger_interval_ticks, resume_wait, message):
            #         rc = rc_context.rc
            #         rc.start(disable_data_storage, run_type, message)
            #         time.sleep(resume_wait)
            #         if rc.return_code==0:
            #             rc.resume(trigger_interval_ticks)

            #     rc_context.rc.run_num_mgr.set_run_number(run_num)

            #     args = [disable_data_storage, run_type, trigger_interval_ticks, resume_wait, message]

            #     rc_context.worker_thread = threading.Thread(target=start_sleep_resume,
            #                                                 name="command-worker",
            #                                                 args=args)


            # elif cmd == 'resume':
            #     trigger_interval_ticks = get_argument(form, 'trigger_interval_ticks', default_val=None  , required=False)

            #     args=[trigger_interval_ticks]

            #     rc_context.worker_thread = threading.Thread(target=target,
            #                                                 name="command-worker",
            #                                                 args=args)

            # else:
            #     if not path:
            #         path = rc_context.rc.topnode.name
            #     path = validatePath(rc_context.rc, path)

            #     rc_context.worker_thread = threading.Thread(target=target, name="command-worker", args=[path])
            rc_context.worker_thread.start()

            rc_context.worker_thread.join()
            rc_context.last_command = cmd
            rc_context.last_path = path

            logger.removeHandler(log_handle)
            logs = open('rest_command.log').read()

            resp_data = {
                "command"    : cmd,
                "path"       : path,
                "return_code": rc_context.rc.return_code,
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

        self.app.run(host="0.0.0.0", port=self.port,
                     debug=True, use_reloader=False,
                     threaded=True)
