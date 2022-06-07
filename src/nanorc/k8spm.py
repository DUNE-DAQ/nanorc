#!/usr/bin/env python

import logging
import rich
import socket
import time
import json
import copy as cp
import os
from urllib.parse import urlparse
from kubernetes import client, config
from rich.console import Console
from rich.progress import *

class AppProcessDescriptor(object):
    """docstring for AppProcessDescriptor"""

    def __init__(self, name):
        super(AppProcessDescriptor, self).__init__()
        self.name = name
        self.host = None
        self.conf = None
        self.port = None
        self.proc = None


    def __str__(self):
        return str(vars(self))

class K8sProcess(object):

    def __init__(self, pm, name, namespace):
        self.pm = pm
        self.name = name
        self.namespace = namespace

    def is_alive(self):
        try:
            s = self.pm._core_v1_api.read_namespaced_pod_status(self.name, self.namespace)
            for cond in s.status.conditions:
                if cond.type == "Ready" and cond.status == "True":
                    return True
            return False
        except:
            return False

    def status(self):
        try:
            s = self.pm._core_v1_api.read_namespaced_pod_status(self.name, self.namespace)
            container_status = s.status.container_statuses[0].state
            if   container_status.running:
                return "Running"
            elif container_status.terminated:
                return f"Terminated {container_status.terminated.exit_code} {container_status.terminated.reason}"
            elif container_status.waiting:
                return f"Waiting {container_status.waiting.reason}"
            else:
                return 'Unknown'
        except:
            return 'Unknown'



class K8SProcessManager(object):
    def __init__(self, console: Console, cluster_config, connections):
        """A Kubernetes Process Manager

        Args:
            console (Console): Description
        """
        super(K8SProcessManager, self).__init__()
        self.log = logging.getLogger(__name__)
        self.connections = connections
        self.mount_cvmfs = True
        self.console = console
        self.apps = {}
        self.partition = None
        self.cluster_config = cluster_config

        config.load_kube_config()

        self._core_v1_api = client.CoreV1Api()
        self._apps_v1_api = client.AppsV1Api()



    def list_pods(self):
        self.log.info("Listing pods with their IPs:")
        ret = self._core_v1_api.list_pod_for_all_namespaces(watch=False)
        for i in ret.items:
            self.log.info("%s\t%s\t%s" % (i.status.pod_ip, i.metadata.namespace, i.metadata.name))

    def list_endpoints(self):
        self.log.info("Listing endpoints:")
        ret = self._core_v1_api.list_endpoints_for_all_namespaces(watch=False)
        for i in ret.items:
            self.log.info("%s\t%s" % (i.metadata.namespace, i.metadata.name))

    # ----
    def create_namespace(self, namespace : str):
        self.log.info(f"Creating \"{namespace}\" namespace")

        ns = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace)
        )
        try:
            #
            resp = self._core_v1_api.create_namespace(
                body=ns
            )
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create namespace \"{namespace}\"") from e

    # ----
    def delete_namespace(self, namespace: str):
        self.log.info(f"Deleting \"{namespace}\" namespace")
        try:
            #
            resp = self._core_v1_api.delete_namespace(
                name=namespace
            )
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to delete namespace \"{namespace}\"") from e

    def get_container_port_list_from_connections(self, app_name:str, connections:list=None, cmd_port:int=3333):
        ret = [
            client.V1ContainerPort(
                name = 'restcmd',
                protocol = "TCP",
                container_port = cmd_port,
            )]
        for c in connections:
            uri = urlparse(c['uri'])
            if uri.hostname != "0.0.0.0": continue

            ret += [
                client.V1ContainerPort(
                    # My sympathy for the nwmgr took yet another hit here
                    name = c['uid'].lower().replace(".", "").replace("_", "").replace("$","").replace("{", "").replace("}", "")[-15:],
                    protocol = uri.scheme.upper(),
                    container_port = uri.port,
                )]
        return ret


    def get_service_port_list_from_connections(self, app_name:str, connections:list=None, cmd_port:int=3333):
        ret = [
            client.V1ServicePort(
                name = 'restcmd',
                protocol = "TCP",
                target_port = cmd_port,
                port = cmd_port,
            )]

        for c in connections:
            uri = urlparse(c['uri'])
            if uri.hostname != "0.0.0.0": continue

            ret += [
                client.V1ServicePort(
                    # My sympathy for the nwmgr took yet another hit here
                    name = c['uid'].lower().replace(".", "").replace("_", "").replace("$","").replace("{", "").replace("}", "")[-15:],
                    protocol = uri.scheme.upper(),
                    target_port = uri.port,
                    port = uri.port,
                )]
        return ret

    # ----
    def create_daqapp_pod(
            self,
            name: str,
            app_label: str,
            app_boot_info:dict,
            namespace: str,
            run_as: dict = None):

        self.log.info(f"Creating \"{namespace}:{name}\" daq application (image: \"{app_boot_info['image']}\", use_flx={app_boot_info['use_flx']})")

        pod = client.V1Pod(
            # Run the pod with same user id and group id as the current user
            # Required in kind environment to create non-root files in shared folders
            metadata = client.V1ObjectMeta(
                name=name,
                labels={"app": app_label}
            ),
            spec = client.V1PodSpec(
                restart_policy="Never",
                security_context=client.V1PodSecurityContext(
                    run_as_user=run_as['uid'],
                    run_as_group=run_as['gid'],
                ) if run_as else None,
                host_pid=True,
                affinity=client.V1Affinity(
                    node_affinity = client.V1NodeAffinity(
                        required_during_scheduling_ignored_during_execution=client.V1NodeSelector(
                            node_selector_terms = [
                                client.V1NodeSelectorTerm(
                                    match_expressions=[
                                        # client.V1NodeSelectorRequirement(
                                        {
                                            'key':'kubernetes.io/hostname',
                                            'operator':'In',
                                            'values':[app_boot_info['node']]
                                        }
                                    ]
                                )
                            ]
                        )
                   ) if app_boot_info.get("node") else None,
                    pod_anti_affinity = client.V1PodAntiAffinity(
                        required_during_scheduling_ignored_during_execution=[
                            client.V1PodAffinityTerm(
                                topology_key="kubernetes.io/hostname",#??? not sure what this does
                                label_selector=client.V1LabelSelector(
                                    match_expressions=[
                                        client.V1LabelSelectorRequirement(
                                            key='app',
                                            operator="In",
                                            values=app_boot_info['anti_affinity_pods'],
                                        )
                                    ]
                                )
                            )
                            # for pod in
                        ]
                    ) if app_boot_info.get('anti_affinity_pods') else None,
                ),
                # List of processes
                containers=[
                    # DAQ application container
                    client.V1Container(
                        name="daq-application",
                        image=app_boot_info["image"],
                        image_pull_policy= "IfNotPresent",
                        # Environment variables
                        security_context = client.V1SecurityContext(privileged=app_boot_info['use_flx']),
                        resources = (
                            client.V1ResourceRequirements({
                                "felix.cern/flx": "2", # requesting 2 FLXs
                                "memory": "32Gi" # yes bro
                            })
                        ) if app_boot_info['use_flx'] else None,
                        env = [
                            client.V1EnvVar(
                                name=k,
                                value=str(v)
                            ) for k,v in app_boot_info['env'].items()
                        ],
                        command=['/dunedaq/run/app-entrypoint.sh'],
                        args=app_boot_info['args'],
                        ports=self.get_container_port_list_from_connections(app_name=name, connections=app_boot_info['connections'], cmd_port=app_boot_info['cmd_port']),
                        volume_mounts=(
                            ([
                                client.V1VolumeMount(
                                    mount_path="/"+app_boot_info['pvc'],
                                    name=app_boot_info['pvc'],
                                    read_only=True
                            )] if app_boot_info['pvc'] else []) +
                            ([
                                client.V1VolumeMount(
                                    mount_path="/cvmfs/dunedaq.opensciencegrid.org",
                                    name="dunedaq-cvmfs",
                                    read_only=True
                            )] if self.mount_cvmfs else []) +
                            ([
                                client.V1VolumeMount(
                                    mount_path="/cvmfs/dunedaq-development.opensciencegrid.org",
                                    name="dunedaq-dev-cvmfs",
                                    read_only=True
                            )] if self.mount_cvmfs and app_boot_info['mount_cvmfs_dev'] else []) +
                            ([
                                client.V1VolumeMount(
                                    mount_path="/dunedaq/pocket",
                                    name="pocket",
                                    read_only=False
                            )] if self.cluster_config.is_kind else []) +
                            ([
                                client.V1VolumeMount(
                                    mount_path="/dev",
                                    name="devfs",
                                    read_only=False
                            )] if app_boot_info['use_flx'] else [])
                        )
                    )
                ],
                volumes=(
                    ([
                        client.V1Volume(
                            name=app_boot_info['pvc'],
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                claim_name=app_boot_info['pvc'],
                                read_only=True
                            )
                        )
                    ] if app_boot_info['pvc'] else []) +
                    ([
                        client.V1Volume(
                            name="dunedaq-cvmfs",
                            host_path=client.V1HostPathVolumeSource(path='/cvmfs/dunedaq.opensciencegrid.org')
                        )
                    ] if self.mount_cvmfs else []) +
                    ([
                        client.V1Volume(
                            name="dunedaq-dev-cvmfs",
                            host_path=client.V1HostPathVolumeSource(path='/cvmfs/dunedaq-development.opensciencegrid.org')
                        )
                    ] if self.mount_cvmfs and app_boot_info['mount_cvmfs_dev'] else []) +
                    ([
                        client.V1Volume(
                            name="pocket",
                            host_path=client.V1HostPathVolumeSource(path='/pocket')
                        )
                    ] if self.cluster_config.is_kind else [])+
                    ([
                        client.V1Volume(
                            name="devfs",
                            host_path=client.V1HostPathVolumeSource(path='/dev')
                        )
                    ] if app_boot_info['use_flx'] else [])
                )
            )
        )

        self.log.debug(pod)

        # Creation of the pod in specified namespace
        try:
            #
            resp = self._core_v1_api.create_namespaced_pod (
                namespace = namespace,
                body = pod
            )
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create daqapp pod \"{namespace}:{name}\"") from e

        service = client.V1Service(
            metadata = client.V1ObjectMeta(name=name),
            spec = client.V1ServiceSpec(
                ports = self.get_service_port_list_from_connections(app_name=name, connections=app_boot_info['connections'], cmd_port=app_boot_info['cmd_port']),
                selector = {"app": app_label}
            )
        )  # V1Service
        self.log.debug(service)

        try:
            resp = self._core_v1_api.create_namespaced_service(namespace, service)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create daqapp service \"{namespace}:{name}\"") from e

    # ----
    def create_nanorc_responder(self, name: str, namespace: str, ip: str, port: int):

        self.log.info(f"Creating nanorc responder service \"{namespace}:{name}\" for \"{ip}:{port}\"")

        # Creating Service object
        service = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=name,
            ),
            spec=client.V1ServiceSpec(
                ports=[
                    client.V1ServicePort(
                        protocol = 'TCP',
                        target_port = port,
                        port = port,
                    )
                ],
            )
        )  # V1Service

        self.log.debug(service)
        try:
            resp = self._core_v1_api.create_namespaced_service(namespace, service)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create nanorc responder service \"{namespace}:{name}\"") from e

        self.log.info(f"Creating nanorc responder endpoint {ip}:{port}")

        # Create Endpoints Objects
        endpoints = client.V1Endpoints(
            metadata = client.V1ObjectMeta(name=name),
            subsets=[
                client.V1EndpointSubset(
                    addresses = [
                        client.V1EndpointAddress(ip=ip)
                    ],
                    ports=[
                        client.CoreV1EndpointPort(port=port)
                    ]
                )
            ]
        )
        self.log.debug(endpoints)

        try:
            self._core_v1_api.create_namespaced_endpoints(namespace, endpoints)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create nanorc responder endpoint \"{namespace}:{name}\"") from e

    """
    ---
    # Source: cvmfs-csi/templates/persistentvolumeclaim.yaml
    apiVersion: v1
    kind: PersistentVolumeClaim
    metadata:
      name: dunedaq.opensciencegrid.org
    spec:
      accessModes:
      - ReadOnlyMany
      resources:
        requests:
          storage: 1Gi
      storageClassName: dunedaq.opensciencegrid.org
    """
    def create_cvmfs_pvc(self, name: str, namespace: str):

        # Create claim
        claim = client.V1PersistentVolumeClaim(
            # Meta-data
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=namespace
            ),
            # Claim
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=['ReadOnlyMany'],
                resources=client.V1ResourceRequirements(
                        requests={'storage': '2Gi'}
                    ),
                storage_class_name=name
                )
            )

        try:
            self._core_v1_api.create_namespaced_persistent_volume_claim(namespace, claim)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create persistent volume claim \"{namespace}:{name}\"") from e


    def create_data_pvc(self, name:str, namespace:str):
        # # Create persistent volume
        # This shouldn't be in nanorc (as it should only be executed once)
        # claim = client.V1PersistentVolume(
        #     # Meta-data
        #     metadata=client.V1ObjectMeta(
        #         name=name,
        #     ),
        #     # Claim
        #     spec=client.V1PersistentVolumeSpec(
        #         access_modes=['ReadOnlyMany'],
        #         # persistent_volume_reclaim_policy="Retain",
        #         storage_class_name=name,
        #         capacity={
        #             "storage": "5Gi"
        #         },
        #         node_affinity = client.V1VolumeNodeAffinity(
        #             client.V1NodeSelector(
        #                 node_selector_terms = [
        #                     client.V1NodeSelectorTerm(
        #                         match_expressions=[
        #                             {
        #                                 'key':'kubernetes.io/hostname',
        #                                 'operator':'In',
        #                                 'values':['np04-srv-004']
        #                             }
        #                         ]
        #                     )
        #                 ]
        #             )
        #         ),
        #         local=client.V1LocalVolumeSource(
        #             path="/"+name,
        #             # type='Directory'
        #         )
        #     )
        # )

        # try:
        #     self._core_v1_api.create_persistent_volume(claim)
        # except Exception as e:
        #     self.log.error(e)
        #     raise RuntimeError(f"Failed to create persistent volume claim \"{namespace}:{name}\"") from e

        # Create claim
        claim = client.V1PersistentVolumeClaim(
            # Meta-data
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=namespace
            ),
            # Claim
            spec=client.V1PersistentVolumeClaimSpec(
                access_modes=['ReadOnlyMany'],
                storage_class_name=name,
                resources=client.V1ResourceRequirements(
                    requests={'storage': '2Gi'}
                ),
            )
        )

        try:
            self._core_v1_api.create_namespaced_persistent_volume_claim(namespace, claim)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create persistent volume claim \"{namespace}:{name}\"") from e



    #---
    def boot(self, boot_info, timeout):

        if self.apps:
            raise RuntimeError(
                f"ERROR: apps have already been booted {' '.join(self.apps.keys())}. Terminate them all before booting a new set."
            )

        if self.cluster_config.is_kind:
            logging.info('Resolving the kind gateway')
            import docker, ipaddress
            # Detect docker environment
            docker_client = docker.from_env()

            # Find the docker network called Kind
            try:
                kind_network = next(iter(n for n in docker_client.networks.list() if n.name == 'kind'))
            except Exception as exc:
                raise RuntimeError("Failed to identfy docker network 'kind'") from exc

            # And extract the gateway ip, which corresponds to the host
            try:
                self.gateway = next(iter(s['Gateway'] for s in kind_network.attrs['IPAM']['Config'] if isinstance(ipaddress.ip_address(s['Gateway']), ipaddress.IPv4Address)), None)
            except Exception as exc:
                raise RuntimeError("Identify the kind gateway address'") from exc
            logging.info(f"Kind network gateway: {self.gateway}")
        else:
            self.gateway = socket.gethostbyname(socket.gethostname())
            logging.info(f"K8s gateway: {self.gateway} ({socket.gethostname()})")

        apps = boot_info["apps"].copy()
        env_vars = boot_info["env"]
        hosts = boot_info["hosts"]

        self.partition = boot_info['env']['DUNEDAQ_PARTITION']

        # Create partition
        self.create_namespace(self.partition)
        # Create the persistent volume claim
        # self.create_cvmfs_pvc('dunedaq.opensciencegrid.org', self.partition)
        # self.create_data_pvc('data1', self.partition)

        run_as = {
            'uid': os.getuid(),
            'gid': os.getgid(),
        }

        readout_apps = [aname for aname in apps.keys() if "ruflx" in aname or "ruemu" in aname]
        dataflow_apps = [aname for aname in apps.keys() if "dataflow" in aname]
        rest_apps = [aname for aname in apps.keys() if aname not in readout_apps+dataflow_apps]

        app_boot_order = readout_apps + dataflow_apps + rest_apps

        for app_name in app_boot_order:
            app_conf = apps[app_name]

            host = hosts[app_conf["host"]]
            cmd_port = app_conf['port']
            env_formatter = {
                "APP_HOST": host,
                "DUNEDAQ_PARTITION": env_vars['DUNEDAQ_PARTITION'],
                "APP_NAME": app_name,
                "APP_PORT": cmd_port,
                "APP_WD": os.getcwd(),
            }

            exec_data = boot_info['exec'][app_conf['exec']]
            exec_vars_cp = cp.deepcopy(exec_data['env'])
            exec_vars = {}

            for k,v in exec_vars_cp.items():
                exec_vars[k]=v.format(**env_formatter)

            app_env = {}
            app_env.update(env_vars)
            app_env.update(exec_vars)

            env_formatter.update(app_env)
            app_args = [a.format(**env_formatter) for a in boot_info['exec'][app_conf['exec']]['args']]
            app_img = exec_data['image']
            app_cmd = exec_data['cmd']
            if not app_img:
                raise RuntimeError("You need to specify an image in the configuration!")

            ## ? Maybe?
            unwanted_env = ['PATH', 'LD_LIBRARY_PATH', 'CET_PLUGIN_PATH','DUNEDAQ_SHARE_PATH']
            for var in unwanted_env:
                if var in app_env:
                    del app_env[var]


            ## This is meant to mean:
            # if the image is of form pocket_dune_bla (without version postfix)
            # or if the first letter of the version starts with N
            # then, we want to mount /cvmfs/dunedaq-development....
            # Else we are probably in "full release mode" in which case the name of the version will be v3.0.4, and we don't need to mount it
            image_and_ver = app_img.split(":")
            mount_cvmfs_dev = False
            if len(image_and_ver)==1:
                mount_cvmfs_dev = True
            elif len(image_and_ver)==2:
                if image_and_ver[1] or image_and_ver[1] == "latest":
                    mount_cvmfs_dev = (image_and_ver[1][0] == 'N')
                else:
                    raise RuntimeError("Malformed image name in boot.json")
            else:
                raise RuntimeError("Malformed image name in boot.json")

            app_boot_info ={
                "env": app_env,
                "args": app_args,
                "image": app_img,
                "cmd_port": cmd_port,
                "mount_cvmfs_dev": mount_cvmfs_dev,
                "pvc": None,#('data1' if "dataflow" in app_name else None), ## TODO: find a nice way to do that thru config
                "use_flx": ("ruflx" in app_name), ## TODO: find a nice way to do that thru config
                "connections": self.connections[app_name],
            }

            if self.cluster_config.is_k8s_cluster:
                if app_name in readout_apps:
                    app_boot_info["node"] = host
                else:
                    app_boot_info["anti_affinity_pods"] = readout_apps

            self.log.debug(json.dumps(app_boot_info, indent=2))
            app_desc = AppProcessDescriptor(app_name)
            app_desc.conf = app_conf.copy()
            app_desc.partition = self.partition
            app_desc.host = f'{app_name}.{self.partition}'
            app_desc.pod = ''
            app_desc.port = cmd_port
            app_desc.proc = K8sProcess(self, app_name, self.partition)

            k8s_name = app_name.replace("_", "-").replace(".", "")

            self.create_daqapp_pod(
                name = k8s_name, # better kwargs all this...
                app_label = k8s_name,
                app_boot_info = app_boot_info,
                namespace = self.partition,
                run_as = run_as
            )

            self.apps[app_name] = app_desc

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            console=self.console,
        ) as progress:
            total = progress.add_task("[yellow]# apps started", total=len(self.apps))
            apps_tasks = {
                a: progress.add_task(f"[blue]{a}", total=1) for a in self.apps
            }
            waiting = progress.add_task("[yellow]timeout", total=timeout)

            for _ in range(timeout):
                progress.update(waiting, advance=1)

                ready = self.check_apps()
                for a, t in apps_tasks.items():
                    if a in ready:
                        progress.update(t, completed=1)
                        self.apps[a].pod = ready[a]
                progress.update(total, completed=len(ready))
                r = list(ready.keys())
                a = list(self.apps.keys())
                r.sort()
                a.sort()
                if r==a:
                    progress.update(waiting, visible=False)
                    break

                time.sleep(1)

        self.create_nanorc_responder(
            name = 'nanorc',
            namespace = self.partition,
            ip = self.gateway,
            port = boot_info["response_listener"]["port"])

    # ---
    def check_apps(self):
        ready = {}
        for p in self._core_v1_api.list_namespaced_pod(self.partition).items:
            for name in self.apps.keys():
                if name in p.metadata.name and p.status.phase == "Running":
                    ready[name]=p.metadata.name
        return ready

    # ---
    def terminate(self):

        timeout = 60
        if self.partition:
            self.delete_namespace(self.partition)

            for _ in track(range(timeout), description="Terminating namespace..."):

                s = self._core_v1_api.list_namespace()
                found = False
                for namespace in s.items:
                    if namespace.metadata.name == self.partition:
                        found = True
                        break
                if not found:
                    return
                time.sleep(1)

            logging.warning('Timeout expired!')


# ---
def main():

    from rich.logging import RichHandler

    logging.basicConfig(
        level="INFO",
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )

    partition = 'dunedaq-0'
    pm = K8SProcessManager()
    # pm.list_pods()
    # pm.list_endpoints()
    pm.create_namespace(partition)
    pm.create_cvmfs_pvc('dunedaq.opensciencegrid.org', partition)
    pm.create_daqapp_pod('trigger', 'trg', partition, True)
    pm.create_nanorc_responder('nanorc', 'nanorc', partition, '128.141.174.0', 56789)
    # pm.list_pods()

if __name__ == '__main__':
    main()
