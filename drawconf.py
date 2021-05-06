#!/usr/bin/env python3


import json
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
                # print(f"{modname} is a NetworkToQueue instance!")
                netedge = modcfg["data"]["receiver_config"]["address"]
                if not netedge in netedges:
                    netedges[netedge] = { "src": "", "sink": "", "label": "" }

                # print(f"Setting sink of network edge {netedge} to {procname}_{modname}")
                netedges[netedge]["sink"] = f"{procname}_{modname}"
                netedges[netedge]["label"] = modcfg["data"]["msg_module_name"]
            if modname in netsenders:
                # print(f"{modname} is a QueueToNetwork instance!")
                netedge = modcfg["data"]["sender_config"]["address"]
                if not netedge in netedges:
                    netedges[netedge] = { "src": "", "sink": "" }
                # print(f"Setting src of network edge {netedge} to {procname}_{modname}")
                netedges[netedge]["src"] = f"{procname}_{modname}"
    
    for netedge in netedges:
        src = netedges[netedge]["src"]
        sink = netedges[netedge]["sink"]
        label = netedges[netedge]["label"]
        # print(f"Setting up {netedge} to connect {src} to {sink}")
        
        conf.edge(src, sink, label=f"{label}\n{netedge}")

    print("Writing output dot")
    with open(output_file, 'w') as dotfile:
        dotfile.write(conf.source)


if __name__ == '__main__':
    print("Starting cli")
    cli()






