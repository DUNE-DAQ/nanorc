#!/usr/bin/env python

import logging
import rich
import socket
import time
from kubernetes import client, config
from rich.console import Console
from rich.progress import track

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
        s = self.pm._apps_v1_api.read_namespaced_deployment_status(self.name, self.namespace)
        return s.status.updated_replicas == s.spec.replicas


class K8SProcessManager(object):
    """docstring for K8SProcessManager"""
    def __init__(self, console: Console):
        """A Kubernetes Process Manager
        
        Args:
            console (Console): Description
        """
        super(K8SProcessManager, self).__init__()

        self.log = logging.getLogger(__name__)
        self.console = console
        self.apps = {}
        self.partition = None

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
        self.log.info(f"Creating {namespace} namespace")

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
            raise RuntimeError(f"Failed to create namespace {namespace}") from e

    # ----
    def delete_namespace(self, namespace: str):
        self.log.info(f"Deleting {namespace} namespace")
        try:
            # 
            resp = self._core_v1_api.delete_namespace(
                name=namespace
            )
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to delete namespace {namespace}") from e

    # ----
    def create_daqapp_deployment(self, name: str, app_label: str, namespace: str, cmd_port: int = 3333, mount_cvmfs: bool = False, env_vars: dict = None):
        self.log.info(f"Creating {namespace}:{name} daq application (port: {cmd_port})")

        # Deployment
        deployment = client.V1Deployment(
            # api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=name),
            spec=client.V1DeploymentSpec(
                selector=client.V1LabelSelector(match_labels={"app": app_label}),
                replicas=1,
                template=client.V1PodTemplateSpec(
                    metadata=client.V1ObjectMeta(labels={"app": app_label}),
                    spec=client.V1PodSpec(
                        containers=[
                            client.V1Container(
                                name="deployment",
                                image="pocket-daq-cvmfs:v0.1.0",
                                env = [
                                    client.V1EnvVar(
                                        name=k,
                                        value=v
                                        )
                                    for k,v in env_vars.items()
                                ] if env_vars else None,
                                args=[
                                    "--name", name, 
                                    "-c", "rest://localhost:3333",
                                    "-i", "influx://influxdb.monitoring:8086/write?db=influxdb"
                                    ],
                                ports=[
                                    client.V1ContainerPort(
                                        container_port=3333,
                                        name="restcmd",
                                        protocol="TCP"
                                        )
                                ],
                                # image_pull_policy="Never",
                                volume_mounts=[
                                    client.V1VolumeMount(
                                        mount_path="/cvmfs/dunedaq.opensciencegrid.org",
                                        name="dunedaq"
                                    )
                                ] if mount_cvmfs else None
                            )
                        ],
                        volumes=[
                            client.V1Volume(
                                name="dunedaq",
                                persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                                    claim_name="dunedaq.opensciencegrid.org",
                                    read_only=True
                                    )
                            )
                        ] if mount_cvmfs else None
                    ))
            )

        )


        self.log.debug(deployment)
        # return
        # Creation of the Deployment in specified namespace
        # (Can replace "default" with a namespace you may have created)
        try:
            # 
            resp = self._apps_v1_api.create_namespaced_deployment(
                namespace=namespace, body=deployment
            )
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create daqapp deployment {namespace}:{name}") from e

        service = client.V1Service(
            metadata=client.V1ObjectMeta(name=name),
            spec=client.V1ServiceSpec(
                ports=[
                    client.V1ServicePort(
                        name = "restcmd",
                        protocol = "TCP",
                        target_port = "restcmd",
                        port = 3333,
                    )
                ],
                selector = {"app": app_label}
            )
        )  # V1Service
        self.log.debug(service)

        try:
            resp = self._core_v1_api.create_namespaced_service(namespace, service)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create daqapp service {namespace}:{name}") from e

    # ----
    def create_nanorc_responder(self, name: str, app_label: str, namespace: str, ip: str, port: int):

        self.log.info(f"Creating nanorc responder service {namespace}:{name} for {ip}:{port}")

        # Creating Service object
        service = client.V1Service(
            metadata=client.V1ObjectMeta(name=name),
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
            raise RuntimeError(f"Failed to create nanorc responder service {namespace}:{name}") from e

        self.log.info("Creating nanorc responder endpoint")

        # Create Endpoints Objects
        endpoints = client.V1Endpoints(
            metadata=client.V1ObjectMeta(
                name=name
            ),
            subsets=[
                client.V1EndpointSubset(
                    addresses=[
                        client.V1EndpointAddress(ip=ip)
                    ],
                    ports=[
                        client.V1EndpointPort(port=port)
                    ]
                )
            ]
        )
        self.log.debug(endpoints)

        try:
            self._core_v1_api.create_namespaced_endpoints(namespace, endpoints)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create nanorc responder endpoint {namespace}:{name}") from e

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
                        requests={'storage': '1Gi'}
                    ),
                storage_class_name=name
                )
            )

        try:
            self._core_v1_api.create_namespaced_persistent_volume_claim(namespace, claim)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create persistent volume claim {namespace}:{name}") from e


    def boot(self, boot_info, partition):

        if self.apps:
            raise RuntimeError(
                f"ERROR: apps have already been booted {' '.join(self.apps.keys())}. Terminate them all before booting a new set."
            )

        logging.info('Resolving the kind gateway')
        import docker, ipaddress
        docker_client = docker.from_env()
        # for n in docker_client.networks.list():
            # print(n.name)

        try:
            kind_network = next(iter(n for n in docker_client.networks.list() if n.name == 'kind'))
        except Exception as exc:
            raise RuntimeError("Failed to identfy docker network 'kind'") from exc

        try:
            kind_gateway = next(iter(s['Gateway'] for s in kind_network.attrs['IPAM']['Config'] if isinstance(ipaddress.ip_address(s['Gateway']), ipaddress.IPv4Address)), None)
        except Exception as exc:
            raise RuntimeError("Identify the kind gateway address'") from exc
        logging.info(f"kind network gateway: {kind_gateway}")

        apps = boot_info["apps"].copy()
        env_vars = boot_info["env"].copy()
        # TODO: move into the rc boot method. The PM should not know about DUNEDAQ_PARTITION
        env_vars['DUNEDAQ_PARTITION'] = partition

        self.partition = partition
        cmd_port = 3333
        
        # Create partition
        self.create_namespace(self.partition)
        # Create the persistent volume claim
        self.create_cvmfs_pvc('dunedaq.opensciencegrid.org', self.partition)

        for app_name, app_conf in apps.items():

            app_desc = AppProcessDescriptor(app_name)
            app_desc.conf = app_conf.copy()
            app_desc.partition = self.partition
            app_desc.host = f'{app_name}.{self.partition}'
            app_desc.port = cmd_port
            app_desc.proc = K8sProcess(self, app_name, self.partition)

            self.create_daqapp_deployment(app_name, app_name, self.partition, cmd_port, mount_cvmfs=True, env_vars=env_vars)
            self.apps[app_name] = app_desc

        self.create_nanorc_responder('nanorc', 'nanorc', self.partition, kind_gateway, boot_info["response_listener"]["port"])   

    # ---
    def terminate(self):

        timeout = 60
        if self.partition:
            self.delete_namespace(self.partition)

            # TODO: add progressbar here
            # for _ in range(timeout):
            for _ in track(range(timeout), description="Terminating namespace..."):

                try:
                    s = self._core_v1_api.read_namespace_status(self.partition)
                except client.exceptions.ApiException as exc:
                    if exc.reason == 'Not Found':
                        return
                    else:
                        break
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

    # config.load_kube_config()

    # core_v1 = client.CoreV1Api()
    # apps_v1 = client.AppsV1Api()

    # list_pods(core_v1)
    # create_daqapp_deployment(apps_v1, 'trigger', 'trg', 'dunedaq')
    # create_daqapp_service(core_v1, 'trigger', 'trg', 'dunedaq')
    # create_nanorc_responder(core_v1, 'nanorc', 'nanorc', 'dunedaq', '192.168.200.12', 56789)
    
    partition = 'dunedaq-0'
    pm = K8SProcessManager()
    # pm.list_pods()
    # pm.list_endpoints()
    pm.create_namespace(partition)
    pm.create_cvmfs_pvc('dunedaq.opensciencegrid.org', partition)
    pm.create_daqapp_deployment('trigger', 'trg', partition, True)
    pm.create_nanorc_responder('nanorc', 'nanorc', partition, '128.141.174.0', 56789)
    # pm.list_pods()

if __name__ == '__main__':
    main()