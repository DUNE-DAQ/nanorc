from http import server
from flask import Flask, render_template
import requests
from flask_cors import CORS, cross_origin
import argparse
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("-s","--serverhost", help="address of the server")
args = parser.parse_args()

app = Flask(__name__)
CORS(app, support_credentials=True)
@app.route('/')
@cross_origin(supports_credentials=True)
def index():
    global args
    if args.serverhost:
        return render_template('index.html',serverhost=args.serverhost)
    else:
        return render_template('index.html',serverhost="localhost:5001")

if __name__ == "__main__":
    app.run("0.0.0.0")