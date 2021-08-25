#!/usr/bin/env python

import logging
import rich
import socket
from kubernetes import client, config


class K8SProcessManager(object):
    """docstring for K8SProcessManager"""
    def __init__(self):
        super(K8SProcessManager, self).__init__()

        self.log = logging.getLogger(__name__)

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
                body=ns
            )
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to delete namespace {namespace}") from e

    # ----
    def create_daqapp_deployment(self, name: str, app_label: str, namespace: str, mount_cvmfs: bool):
        self.log.info(f"Creating {namespace}:{name} daq application")

        volume_mount = client.V1VolumeMount(
                mount_path="/cvmfs/dunedaq.opensciencegrid.org",
                name="dunedaq"
            )

        container = client.V1Container(
            name="deployment",
            image="pocket-daq-cvmfs:v0.1.0",
            args=["--name", "theapp", "-c", "rest://localhost:3333"],
            ports=[
                client.V1ContainerPort(container_port=3333)
            ],
            # image_pull_policy="Never",
            volume_mounts=[volume_mount] if mount_cvmfs else None
        )

        volume = client.V1Volume(
            name="dunedaq",
            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(
                claim_name="dunedaq.opensciencegrid.org",
                read_only=True
                )
            )

        # Template
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": app_label}),
            spec=client.V1PodSpec(
                containers=[container],
                volumes=[volume] if mount_cvmfs else None
            ))

        selector = client.V1LabelSelector(match_labels={"app": app_label})
        # Spec
        spec = client.V1DeploymentSpec(
            selector=selector,
            replicas=1,
            template=template)
        # Deployment
        deployment = client.V1Deployment(
            api_version="apps/v1",
            kind="Deployment",
            metadata=client.V1ObjectMeta(name=name),
            spec=spec)

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



        # Creating Meta Data
        metadata = client.V1ObjectMeta(name=name)

        # Creating Port object
        port = client.V1ServicePort(
            protocol = 'TCP',
            target_port = 3333,
            port = 3333,
        )

        # Creating spec 
        spec = client.V1ServiceSpec(
                ports=[port],
                selector = {"app": app_label}
            )

        service = client.V1Service(metadata=metadata, spec=spec)  # V1Service
        self.log.debug(service)

        try:
            resp = self._core_v1_api.create_namespaced_service(namespace, service)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create daqapp service {namespace}:{name}") from e

    # ----
    def create_nanorc_responder(self, name: str, app_label: str, namespace: str, ip: str, port: int):

        self.log.info("Creating nanorc responder service {namespace}:{name}")

        # Creating Meta Data
        metadata = client.V1ObjectMeta(name=name)

        # Creating Port object
        svc_port = client.V1ServicePort(
            protocol = 'TCP',
            target_port = port,
            port = port,
        )

        # Creating spec 
        spec = client.V1ServiceSpec(
                ports=[svc_port],
            )

        # Creating Service object
        service = client.V1Service(metadata=metadata, spec=spec)  # V1Service
        self.log.debug(service)
        try:
            resp = self._core_v1_api.create_namespaced_service(namespace, service)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create nanorc responder service {namespace}:{name}") from e

        self.log.info("Creating nanorc responder endpoint")

        # Creating Meta Data
        metadata = client.V1ObjectMeta(name=name)

        responder_address = client.V1EndpointAddress(
                ip=ip
            )

        ep_port = client.V1EndpointPort(
                port=port,
            )

        # Creating endpoints subsets
        subset = client.V1EndpointSubset(addresses=[responder_address], ports=[ep_port])
        # Create Endpoints Objects
        endpoints = client.V1Endpoints(metadata=metadata, subsets=[subset])
        self.log.info(endpoints)

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

        # Creating Meta Data
        metadata = client.V1ObjectMeta(name=name, namespace=namespace)

        # Creating spec
        spec=client.V1PersistentVolumeClaimSpec(
            access_modes=['ReadOnlyMany'],
            resources=client.V1ResourceRequirements(
                    requests={'storage': '1Gi'}
                ),
            storage_class_name=name
            )

        # Create claim 
        claim = client.V1PersistentVolumeClaim(
            metadata=metadata,
            spec=spec
            )

        try:
            self._core_v1_api.create_namespaced_persistent_volume_claim(namespace, claim)
        except Exception as e:
            self.log.error(e)
            raise RuntimeError(f"Failed to create persistent volume claim {namespace}:{name}") from e
    # def boot(self, boot_info):

    #     if self.apps:
    #         raise RuntimeError(
    #             f"ERROR: apps have already been booted {' '.join(self.apps.keys())}. Terminate them all before booting a new set."
    #         )

    #     apps = boot_info["apps"]
    #     hosts = boot_info["hosts"]
    #     env_vars = boot_info["env"]
    #     partition = 'dunedaq-0'

    #     for app_name, app_conf in apps.items():
    #         self.create_daqapp_deployment(app_name, app_name, partition)
    #     self.create_nanorc_responder('nanorc', 'nanorc', partition, socket.gethostname(), 56789)


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