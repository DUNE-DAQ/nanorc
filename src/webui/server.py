from flask import Flask, render_template
import requests
from flask_cors import CORS, cross_origin

app = Flask(__name__)
CORS(app, support_credentials=True)

@app.route('/')
@cross_origin(supports_credentials=True)
def index():
    return render_template('index.html')

@app.after_request
def after_request(response):
    header = response.headers
    header['Access-Control-Allow-Origin'] = 'http://localhost:5001'
    header['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    header['Access-Control-Allow-Methods'] = 'OPTIONS, HEAD, GET, POST, DELETE, PUT'
    return response

@app.route('/tree')
def tree():
    resp = requests.get('http://host.docker.internal:5001/nanorcrest/tree', auth=('fooUsr', 'barPass'))
    return str(resp.text.replace('name', 'text'))

if __name__ == "__main__":
    app.run("0.0.0.0")