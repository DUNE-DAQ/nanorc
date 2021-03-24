import os
import time
import json
import keyboard
import threading

from rich.console import Console
from rich.table import Table
from rich.layout import Layout
from rich.live import Live
from multiprocessing import Queue



# ---
def flatten_json(y) -> dict:
    out = {}

    def flatten(x, name=''):
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '/')
        elif type(x) is list:
            i = 0
            for a in x:
                flatten(a, name + str(i) + '/')
                i += 1
        else:
            out[name[:-1]] = x

    flatten(y)
    return out


# ---
def json_extract(obj, key) -> list:
    """Recursively fetch values from nested JSON."""
    arr = []
    path = []

    def extract(obj, path, arr, key):
        """Recursively search for values of key in JSON tree."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                path.append(k)
                if k == key:
                    arr.append((path[:], v))
                if isinstance(v, (dict, list)):
                    extract(v, path, arr, key)
                path.pop()
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                path.append(i)
                extract(item, path, arr, key)
                path.pop(i)
        return arr

    values = extract(obj, path, arr, key)
    return values

# ---
def json_get_path(j, path) -> dict:
    x = j
    for p in path:
        x = x[p]
    return x


# def json_to_table(j, name):

#     if not name in j:
#         return None
#     t = Table(title=name, show_header=False)
#     t.add_column('name')
#     t.add_column('value')
#     for k,v in flatten_json(j[name]).items():
#         t.add_row(k, str(v))
#     return t


# ---
def info_to_table(info, name) -> Table:
    # print(info)

    t = Table(title=name, show_header=False, show_edge=False, padding=(0,0))
    t.add_column('block')

    ext = json_extract(info, 'time')
    for p, btime in ext:
        bclass = p[-2]
        bdata = json_get_path(info, p[:-1]+['data'])
        t.add_row(info_block_to_table('/'.join(p[1:-2]), bclass, btime, bdata))

    return t

# ---
def info_block_to_table(bpath, bclass, btime, bdata) -> Table:
    print(bdata)
    title = f"{bpath}[{bclass}] {btime}"
    t = Table(title=title, show_header=False)
    for k,v in flatten_json(bdata).items():
        if k == 'class_name':
            continue
        t.add_row(k, str(v))
    return t

# ---
def make_layout(apps) -> Layout:
    """Define the layout."""
    layout = Layout(name="root")

    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1),
        Layout(name="footer", size=7),
    )
    layout["main"].split(
        Layout(name="side"),
        Layout(name="body", ratio=2, minimum_size=60),
        direction="horizontal",
    )

    app_layouts = [Layout(name=app) for app in apps]
    layout["body"].split(*app_layouts, direction="horizontal")
    layout["side"].split(Layout(name="box1"), Layout(name="box2"))
    return layout

class InfoThread(threading.Thread):
    def __init__(self, info_file, interval):
        # super().__init__(self)
        threading.Thread.__init__(self)
        self.info_file = info_file
        self.polling_interval = interval
        self.queue = Queue()
        self.running = False

    def run(self):
        self.running = True
        with open(self.info_file, 'rb') as f:
            f.seek(-2, os.SEEK_END)
            while f.read(1) != b'\n':
                f.seek(-2, os.SEEK_CUR)
            last_line = f.readline().decode()
            j = json.loads(last_line[:-1]) 
            self.queue.put(j)
            
            while self.running:
                time.sleep(1)
                l = f.readline().decode()
                # print('tick')
                # logging.info('tick')
                if l:
                    # print('tock')
                    # logging.info('tock')
                    j = json.loads(l[:-1])
                    self.queue.put(j)
        print("Farewell!")

