from flask import Flask, redirect, url_for, render_template, request, session, g, jsonify, Response
from datetime import timedelta
import sys, os, time
import json
import threading
import logging
import jsonref
from functools import wraps, update_wrapper
from logging.handlers import RotatingFileHandler
from os import environ as env
from anytree import RenderTree
from anytree.search import find_by_attr
from anytree.importer import DictImporter
from flask_socketio import SocketIO, send, emit
from keycloak import Client
from datetime import datetime
from werkzeug.utils import secure_filename
from copy import deepcopy
from pathlib import Path

sys.path.append(os.path.join(os.path.dirname(__file__), '..','..', 'Control'))
from nodetree import NodeTree
from daqcontrol import daqcontrol as daqctrl

configPath = os.path.join(env['DAQ_CONFIG_DIR'])

with open(os.path.join(os.path.dirname(__file__), 'serverconfiguration.json')) as f:
  serverConfigJson = json.load(f)
f.close()

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
thread_lock = threading.Lock()
thread = None
sysConf = {}
root = threading.local()
mainRoot = None
ALLOWED_EXTENSIONS = set(serverConfigJson['ALLOWED_EXTENSIONS'])
whoInterlocked = {}
whoInterlocked[''] = [None, 0]
TIMEOUT = serverConfigJson['timeout_for_requests_secs']
LOGOUT_URL = serverConfigJson['LOGOUT_URL']

def systemConfiguration(configName, configPath):
    global sysConf
    with open(os.path.join(configPath, 'config-dict.json')) as f:
        configJson = json.load(f)
    f.close()
    if configName not in sysConf:
        try:
            sysConf[configName] = reinitTree(configJson)
        except Exception as e:
            logAndEmit('general', 'ERROR', str(e))

def getConfigsInDir(configPath):
    listOfFiles = []
    for d in os.listdir(configPath):
        conf_path = os.path.join(configPath, d)
        if not os.path.isfile(conf_path) and "config-dict.json" in os.listdir(conf_path):
            listOfFiles.append(d)
    return listOfFiles

def reinitTree(configJson, oldRoot=None):
    if oldRoot != None:
        for pre, _, node in RenderTree(oldRoot):
            node.stopStateCheckers()
    #try:
    with open(os.path.join(session['configPath'], configJson['tree'])) as f:
        tree = json.load(f)
    f.close()
    #except:
    #    raise Exception("Invalid tree configuration")

    try:
        with open(os.path.join(session['configPath'], configJson['fsm_rules'])) as f:
            fsm_rules = json.load(f)
        f.close()
    except:
        raise Exception("Invalid FSM configuration")

    state_action = fsm_rules["fsm"]
    order_rules = fsm_rules["order"]
    # try:
    with open(os.path.join(session['configPath'], configJson['config'])) as f:
        base_dir_uri = Path(session['configPath']).as_uri() + '/'
        jsonref_obj = jsonref.load(f, base_uri=base_dir_uri, loader=jsonref.JsonLoader())
    f.close()

    if "configuration" in jsonref_obj:
        # schema with references (version >= 10)
        configuration = deepcopy(jsonref_obj)["configuration"]
    else:
        # old-style schema (version < 10)
        configuration = jsonref_obj
    # except:
    #     raise Exception("Invalid devices configuration")
    # try:
    #     with open(os.path.join(env['DAQ_CONFIG_DIR'], configJson['grafana'])) as f:
    #         grafanaConfig = json.load(f)
    #     f.close()
    # except:
    #     raise Exception("Invalid grafana/kibana nodes configuration:" + e)

    group = configuration['group']
    if 'path' in configuration.keys():
        dir = configuration['path']
    else:
        dir = env['DAQ_BUILD_DIR']
    exe = "/bin/daqling"
    lib_path = 'LD_LIBRARY_PATH=' + env['LD_LIBRARY_PATH'] + ':' + dir + '/lib/,TDAQ_ERS_STREAM_LIBS=DaqlingStreams'
    components = configuration["components"]

    dc = daqctrl(group)

    importer = DictImporter(nodecls=NodeTree)

    newRoot = importer.import_(tree)

    for pre, _, node in RenderTree(newRoot):
        for c in components:
            if node.name == c['name']:
                node.configure(order_rules, state_action, pconf=c, exe=exe, dc=dc, dir=dir, lib_path=lib_path)
            else:
                node.configure(order_rules, state_action)

        node.startStateCheckers()
    return newRoot

def executeComm(ctrl, action):
    r = ''
    configName = session['configName']
    logAndEmit(configName, 'INFO', 'User ' + session['user']['cern_upn'] + ' has sent command '+action+' on node '+ctrl)
    global sysConf
    try:
      if action == "exclude":
        r = find_by_attr(sysConf[session['configName']], ctrl).exclude()
      elif action == "include":
        r = find_by_attr(sysConf[session['configName']], ctrl).include()
      else:
        r = find_by_attr(sysConf[session['configName']], ctrl).executeAction(action)
    except Exception as e:
      logAndEmit(configName,'ERROR', ctrl+': '+str(e))
    if r != '':
        logAndEmit(configName, 'INFO', ctrl + ': ' + str(r))
    return r
def allowedFile(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def getState(ctrl, action):
  try:
      find_by_attr(root, ctrl).executeAction(action)
  except Exception as e:
      logAndEmit('general','ERROR', e)

def uploadFile(path):
    file = request.files['file']
    if file and allowedFile(file.filename):
        filename = secure_filename(file.filename)
        if filename in getConfigsInDir(path):
            return 'File already present'
        try:
            file.save(os.path.join(path, filename))
        except Exception as e:
            logAndEmit('general','ERROR', e)
            return e
        return 'Successfuly uploaded'
    else:
        return 'Forbidden file'

def getStatesList(locRoot):
    list = {}
    global whoInterlocked
    for pre, _, node in RenderTree(locRoot):
        list[node.name] = [find_by_attr(locRoot, node.name).getState(), find_by_attr(locRoot, node.name).inconsistent,find_by_attr(locRoot, node.name).included]
    return list

def stateChecker():
    global whoInterlocked
    l1 = {}
    l2 = {}
    whoValue = {}
    files = getConfigsInDir(configPath)
    for file in files:
        whoValue[file] = whoInterlocked[file]
    while True:
        files = getConfigsInDir(configPath)
        for file in sysConf:
            if file not in whoInterlocked:
                whoInterlocked[file] = [None, 0]
                whoValue[file] = [None, 0]
                systemConfiguration(configPath)
            if whoInterlocked[file][0] not in [None, "local_user"]:
                if (whoInterlocked[file][1] + timedelta(minutes = serverConfigJson['timeout_control_expiration_mins']) < datetime.now()):
                    logAndEmit(file ,'INFO', 'Control of ' + file + ' for user ' + whoInterlocked[file][0] + ' has EXPIRED')
                    whoInterlocked[file] = [None, 0]
            if whoValue[file][0] != whoInterlocked[file][0]:
                socketio.emit('interlockChng', whoInterlocked[file][0], broadcast=True)
            whoValue[file] = whoInterlocked[file]
            l2[file] = getStatesList(sysConf[file])
            try:
                if l1[file] != l2[file]:
                    socketio.emit('stsChng'+file, l2[file], broadcast=True)
            except Exception as e:
                print("Exception", e)
            l1[file] = l2[file]
        time.sleep(0.5)


def logAndEmit(configtype ,type, message):
    now = datetime.now()
    timestamp = now.strftime("%d/%m/%Y, %H:%M:%S")
    if type == 'INFO':
        app.logger.info("["+configtype+"] "+timestamp+" "+type+": "+message)
    elif type == 'WARNING':
        app.logger.warning("["+configtype+"] "+timestamp+" "+type+": "+message)
    elif type == 'ERROR':
        app.logger.error("["+configtype+"] "+timestamp+" "+type+": "+message)
    socketio.emit('logChng', "["+configtype+"] "+timestamp+" "+type+": "+message, broadcast=True)

keycloak_client = Client(callback_uri=serverConfigJson['callbackUri'])
app.secret_key = os.urandom(24)
app.config['PERMANENT_SESSION_LIFETIME'] =  timedelta(minutes=serverConfigJson['timeout_session_expiration_mins'])


# systemConfiguration(configPath+"demo-tree")


def nocache(view):
    @wraps(view)
    def no_cache(*args, **kwargs):
        response = make_response(view(*args, **kwargs))
        response.headers['Last-Modified'] = datetime.now()
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '-1'
        return response

    return update_wrapper(no_cache, view)

@app.before_request
def func():
  session.modified = True

@app.route('/login', methods=['GET', 'POST'])
def login():
    if serverConfigJson['SSO_enabled'] == 1:
        auth_url, state = keycloak_client.login()
        session['state'] = state
        return redirect(auth_url)
    else:
        session['user'] = {}
        session['user']['cern_upn']  = "local_user"
        session['configName'] = ''
        session['configPath'] = ''
        session['configDict'] = ""
        return redirect(url_for('index'))

@app.route('/login/callback', methods=['GET'])
def login_callback():
    state = request.args.get('state', 'unknown')
    _state = session.pop('state', None)
    if state != _state:
        return Response('Invalid state', status=403)
    code = request.args.get('code')

    response = keycloak_client.callback(code)

    access_token = response["access_token"]

    userinfo = keycloak_client.fetch_userinfo(access_token)
    session['user'] = userinfo
    session['configName'] = ''
    session['configPath'] = ''
    session['configDist'] = ""
    logAndEmit('general', 'INFO', 'User connected: '+session['user']['cern_upn'])
    return redirect(url_for('index'))

@app.route('/test', methods=['GET', 'POST'])
def test():
    find_by_attr(root, "Root").exclude()
    return str(session['user'])

@app.route('/log')
def log():
    with open(serverConfigJson['serverlog_location_name']) as f:
        ret = f.read()
    f.close()
    return jsonify(ret)

@app.route('/serverconfig')
def serverconfig():
    return jsonify(serverConfigJson)

@app.route('/')
def index():
    print(whoInterlocked)
    if 'user' in session:
        print(whoInterlocked)
        return render_template('index.html', usr=session['user']['cern_upn'], wholocked=whoInterlocked[session['configName']][0], currConfigFile = session['configName'], statesGraphics=serverConfigJson['states'], displayName=serverConfigJson['displayedName'] )
    return redirect(url_for('login'))

@app.route('/interlock', methods=['POST'])
def interlock():
    global whoInterlocked
    if whoInterlocked[session['configName']][0] == None:
        whoInterlocked[session['configName']] = [session['user']['cern_upn'], datetime.now()]
        logAndEmit(session['configName'], 'INFO', 'User ' + session['user']['cern_upn'] + ' has TAKEN control of configuration '+session['configName'])
        return "Control has been taken"
    else:
        if whoInterlocked[session['configName']][0] == session["user"]['cern_upn']:
            logAndEmit(session['configName'], 'INFO', 'User ' + session['user']['cern_upn'] + ' has RELEASED control of configuration ' + session['configName'])
            whoInterlocked[session['configName']] = [None, 0]
            return "Control has been released"
        else:
            logAndEmit(session['configName'], 'WARNING', 'User ' + session['user']['cern_upn'] + ' ATTEMPTED to take control of configuration ' + session['configName']+' but failed, because it is controlled by '+ str(whoInterlocked[session['configName']][0]))
            return "Controlled by user " + str(whoInterlocked[session['configName']][0])


@app.route('/ajaxParse', methods=['POST'])
def ajaxParse():
    node =  request.form['node']
    command = request.form['command']
    configName = session['configName']
    whoInterlocked[session['configName']][1] = datetime.now()
    try:
        r = executeComm(node, command)
    except Exception as e:
        logAndEmit(configName,'ERROR', str(e))
    time.sleep(TIMEOUT)
    return jsonify(r)
    
@app.route("/logout")
def logout():
    if serverConfigJson['SSO_enabled'] == 1:
        logAndEmit('general', 'INFO', 'User disconnected: ' + session['user']['cern_upn'])
        session.pop('user', None)
        session.pop('configName', None)
        session.pop('configPath', None)
        session.pop('configDict', None)
        return redirect("{}?redirect_uri={}".format(
            LOGOUT_URL,
            url_for('index', _external=True))
        )
    else:
        return redirect(url_for('index'))

@app.route('/urlTreeJson')
def urlTreeJson():
    try:
        with open(os.path.join(session['configPath'], session['configDict']['tree']), 'r') as file:
            return file.read().replace('name', 'text')
    except:
        return "error"

@app.route('/configsJson', methods=['GET', 'POST'])
def configsJson():
    if request.form.get('configFile'):
        session['configName'] = request.form['configFile']
        logAndEmit(session['configName'], 'INFO', 'User ' + session['user']['cern_upn'] + ' has switched to configuration ' + session['configName'])
        session['configPath'] = os.path.join(env['DAQ_CONFIG_DIR'], request.form['configFile'])
        with open(os.path.join(session['configPath'], 'config-dict.json')) as f:
            session['configDict'] = json.load(f)
        f.close()
        systemConfiguration(session['configName'], session['configPath'])
        return "Success"
    else:
        return jsonify(getConfigsInDir(configPath))

@app.route('/fsmrulesJson', methods=['GET', 'POST'])
def fsmrulesJson():
    try:
        with open(os.path.join(session['configPath'], session['configDict']['fsm_rules'])) as f:
                fsmRules = json.load(f)
        f.close()
    except:
        return "error"
    return fsmRules['fsm']

@app.route('/grafanaJson', methods=['GET', 'POST'])
def grafanaJson():
    try:
        with open(os.path.join(session['configPath'], session['configDict']['grafana'])) as f:
                grafanaConfig = json.load(f)
        f.close()
    except:
        return "error"
    return jsonify(grafanaConfig)


@app.route('/uploadCfgFile', methods=['POST'])
def uploadCfgFile():
    return uploadFile(env['DAQ_CONFIG_DIR'])

@app.route('/uploadMainConfigurationFile', methods=['POST'])
def uploadMainConfigurationFile():
    return uploadFile(os.path.join(env['DAQ_CONFIG_DIR'],'ControlGUI'))

@app.route('/statesList', methods=['GET', 'POST'])
def statesList():
    global sysConf
    list = {}
    list = getStatesList(sysConf[session['configName']])
    list['whoLocked'] = whoInterlocked[session['configName']][0]
    return list

@socketio.on('connect', namespace='/')
def connect():
    print('Client connected')

    #socketio.emit('stsChng',statesList(), broadcast=True)
@app.before_first_request
def startup():
    global thread
    for file in getConfigsInDir(configPath):
        print(file)
        whoInterlocked[file]=[None, 0]
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(stateChecker)
    handler = RotatingFileHandler(serverConfigJson['serverlog_location_name'], maxBytes=1000000, backupCount=0)
    logging.root.setLevel(logging.NOTSET)
    handler.setLevel(logging.NOTSET)
    app.logger.addHandler(handler)

if __name__ == "__main__":
    app.run("0.0.0.0")
    socketio.run(app)
