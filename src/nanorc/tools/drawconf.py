#!/usr/bin/env python3


import json
import re
import click
import os

from graphviz import Digraph

@click.command()
@click.option('-o', '--output-file', type=click.Path(), default='config.dot')
@click.argument('json_dir', type=click.Path())
def cli(output_file, json_dir):

    print(f"Loading JSON files from {json_dir}")
    cfg_dir = os.path.join(json_dir, "data")
    files = [ (fi) for fi in os.listdir(cfg_dir) if "_init" in fi ]
    
    print("Creating main Digraph")
    conf = Digraph(name=json_dir)
    conf.graph_attr['rankdir']='LR'

    netsenders = []
    netrecvrs = []
    nwconnections = {}
    nwconnectionnames = []
    nwtopicnames = []
    procname_to_host = {}
    j = {}
    filename = os.path.join(json_dir, "boot.json")
    with open(filename, "r") as jf:
        try:
            j = json.load(jf)
        except json.decoder.JSONDecodeError as e:
            raise RuntimeError(f"ERROR: failed to load {filename}") from e

        for app in j["apps"].keys():
            procname_to_host[app] = j["apps"][app]["host"]


    for file in files:
        procname = file[:-10]
        filename = os.path.join(cfg_dir, file)
        print(f"Parsing init file for process {procname}")
        j = {}
        with conf.subgraph(name=f"cluster_{procname}", node_attr={'shape': 'box'}) as procconf:
            procconf.attr(label=f"{procname}")
            with open(filename, "r") as jf:
                try:
                    j = json.load(jf)
                except json.decoder.JSONDecodeError as e:
                    raise RuntimeError(f"ERROR: failed to load {filename}") from e

            # NetworkManager connections should be the same for all processes
            if len(nwconnections) == 0:
                for nwconn in j["nwconnections"]:
                    name = nwconn["name"]
                    target = re.search(r"host_[^}]*", nwconn["address"]).group()
                    is_subscriber = len(nwconn["topics"]) != 0
                    print(f"Adding NetworkManager connection with name {name}, target host {target}, and is_subscriber {is_subscriber}")
                    nwconnections[name] = {"target": target, "is_subscriber": is_subscriber, "topics": nwconn["topics"]}
                    nwconnectionnames.append(name)
                    if len(nwconn["topics"]) != 0:
                        nwtopicnames.extend(nwconn["topics"])
                    
                    conf.node(name)

            # print("Parsing module configuration")
            qmap = {}
            for modcfg in j["modules"]:
                modinst = modcfg["inst"]
                modplug = modcfg["plugin"]

                if modplug == "NetworkToQueue":
                    netrecvrs.append(modinst)
                if modplug == "QueueToNetwork":
                    netsenders.append(modinst)

                for qcfg in modcfg["data"]["qinfos"]:
                    qinst = qcfg["inst"]
                    qdir = qcfg["dir"]
    
                    if qinst not in qmap:
                        qmap[qinst] = { "sinks": [], "sources": []}

                    if qdir == "input":
                        qmap[qinst]["sinks"].append(f"{procname}_{modinst}")
                    elif qdir == "output":
                        qmap[qinst]["sources"].append(f"{procname}_{modinst}")

                procconf.node(f"{procname}_{modinst}", label=f"{modinst}\n{modplug}")

            # print("Creating queue links")
            for qinst in qmap:
                # print(f"Queue {qinst}")
                qcfg = qmap[qinst]
                procconf.node(f"{procname}_{qinst}", shape="point", width='0.01', height='0.01', xlabel=f"{qinst}")
                
                first = True
                for qsrc in qcfg["sources"]:
                    procconf.edge(qsrc, f"{procname}_{qinst}", dir="none")
                for qsin in qcfg["sinks"]:
                    procconf.edge(f"{procname}_{qinst}", qsin)

    netedges = {}

    files = [ (fi) for fi in os.listdir(cfg_dir) if "_conf" in fi ]
    for file in files:
        procname = file[:-10]
        filename = os.path.join(cfg_dir, file)
        print(f"Parsing conf file for process {procname}")
        j = {} 
        with open(filename, "r") as jf:
            try:
                j = json.load(jf)
            except json.decoder.JSONDecodeError as e:
                raise RuntimeError(f"ERROR: failed to load {filename}") from e
        
        for modcfg in j["modules"]:    
            modname = modcfg["match"]
            if modname in netrecvrs:
                print(f"{modname} is a NetworkToQueue instance!")
                conn_name = modcfg["data"]["receiver_config"]["name"]
                netedge = f"{procname}_{modname}_{conn_name}"

                print(f"Setting sink of network edge {netedge} to {procname}_{modname}")
                netedges[netedge] = {"src": conn_name, "sink":  f"{procname}_{modname}", "label": f"{modname}\n{modcfg['data']['msg_module_name']}", "color":"green"}
            elif modname in netsenders:
                print(f"{modname} is a QueueToNetwork instance!")
                conn_name = modcfg["data"]["sender_config"]["name"]
                netedge = f"{procname}_{modname}_{conn_name}"

                print(f"Setting src of network edge {netedge} to {procname}_{modname}")
                netedges[netedge] = {"sink": conn_name, "src":  f"{procname}_{modname}", "label": f"{modname}\n{modcfg['data']['msg_module_name']}", "color":"green"}
            else:
                def add_nwedge(conn_name):
                    netedge = f"{procname}_{modname}_{conn_name}"
                    is_receiver = (nwconnections[conn_name]["target"] == procname_to_host[procname] and not nwconnections[conn_name]["is_subscriber"]) or \
                                  (nwconnections[conn_name]["is_subscriber"] and nwconnections[conn_name]["target"] != procname_to_host[procname])

                    print(f"Found NetworkManager connection {conn_name} in {procname}_{modname}, is_receiver: {is_receiver}")
                    if is_receiver:
                        netedges[netedge] = {"src": conn_name, "sink": f"{procname}_{modname}", "color": "blue", "label":f"{modname}"}
                    else:
                        netedges[netedge] = {"src": f"{procname}_{modname}", "sink": conn_name, "color": "blue", "label":f"{modname}"}

                # We need to search for NetworkManager connections now
                def search_nwconnection(obj_to_search):
                    if type(obj_to_search) == type(dict()):
                        for key in obj_to_search.keys():
                            if type(obj_to_search[key]) == type(""):
                                if obj_to_search[key] in nwconnectionnames and not "reply_connection_name" in key:
                                    add_nwedge(obj_to_search[key])
                                elif obj_to_search[key] in nwtopicnames and not "timesync_connection_name" in obj_to_search.keys():
                                    topic_name = obj_to_search[key]
                                    for nwconn in nwconnections:
                                        if topic_name in nwconnections[nwconn]["topics"]:
                                            add_nwedge(nwconn)
                                    
                            else:
                                search_nwconnection(obj_to_search[key])
                    elif type(obj_to_search) == type([]):
                        for key in obj_to_search:
                            if type(key) == type(""):
                                if key in nwconnectionnames:
                                    add_nwedge(key)
                                elif key in nwtopicnames:
                                    topic_name = key
                                    for nwconn in nwconnections:
                                        if topic_name in nwconnections[nwconn]["topics"]:
                                            add_nwedge(nwconn)
                            else:
                                search_nwconnection(key)
                if "data" in modcfg:
                    search_nwconnection(modcfg["data"])            
    
    for netedge in netedges:
        src = netedges[netedge]["src"]
        sink = netedges[netedge]["sink"]
        label = netedges[netedge]["label"]
        color = netedges[netedge]["color"]
        print(f"Setting up {netedge} to connect {src} to {sink}")
        
        conf.attr('edge', color=color)
        conf.edge(src, sink, label=f"{label}")

    print("Writing output dot")
    with open(output_file, 'w') as dotfile:
        dotfile.write(conf.source)



def main():
    print("Starting cli")
    cli()

if __name__ == '__main__':
    main()




