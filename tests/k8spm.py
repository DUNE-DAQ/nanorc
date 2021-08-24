#!/usr/bin/env python

from kubernetes import client, config
import rich


class K8SProcessManager(object):
    """docstring for K8SProcessManager"""
    def __init__(self):
        super(K8SProcessManager, self).__init__()

        config.load_kube_config()

        self._core_v1_api = client.CoreV1Api()
        self._apps_v1_api = client.AppsV1Api()



    def list_pods(self):
        print("Listing pods with their IPs:")
        ret = self._core_v1_api.list_pod_for_all_namespaces(watch=False)
        for i in ret.items:
            print("%s\t%s\t%s" % (i.status.pod_ip, i.metadata.namespace, i.metadata.name))

    # ----
    def create_namespace(self, namespace : str):
        ns = client.V1Namespace(
            metadata=client.V1ObjectMeta(name=namespace)
        )
        try:
            # 
            resp = self._core_v1_api.create_namespace(
                body=ns
            )
        except Exception as e:
            rich.print("[red]Error[/red]")
            rich.print(e)
            return

    # ----
    def delete_namespace(self, namespace: str):
        try:
            # 
            resp = self._core_v1_api.delete_namespace(
                body=ns
            )
        except Exception as e:
            rich.print("[red]Error[/red]")
            rich.print(e)
            return

    # ----
    def create_daqapp_deployment(self, name: str, app_label: str, namespace: str):
        container = client.V1Container(
            name="deployment",
            image="pocket-daq:0.1.2",
            args=["--name", "theapp", "-c", "rest://localhost:3333"],
            ports=[
                client.V1ContainerPort(container_port=3333)
            ]
            # image_pull_policy="Never",
        )
        # Template
        template = client.V1PodTemplateSpec(
            metadata=client.V1ObjectMeta(labels={"app": app_label}),
            spec=client.V1PodSpec(containers=[container]))

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

        rich.print(deployment)
        # return
        # Creation of the Deployment in specified namespace
        # (Can replace "default" with a namespace you may have created)
        try:
            # 
            resp = self._apps_v1_api.create_namespaced_deployment(
                namespace=namespace, body=deployment
            )
        except Exception as e:
            rich.print("[red]Error[/red]")
            rich.print(e)
            return
        rich.print(resp)


    # # ----
    # def create_daqapp_service(self, name, app_label, namespace):

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
        rich.print(service)

        try:
            resp = self._core_v1_api.create_namespaced_service(namespace, service)
        except Exception as e:
            rich.print("[red]Error[/red]")
            rich.print(e)
            return

        rich.print(resp)


    # ----
    def create_nanorc_responder(self, name: str, app_label: str, namespace: str, ip: str, port: int):
        # # Creating Meta Data
        # metadata = client.V1ObjectMeta(name=name)

        # rich.print("[blue]Creating nanorc responder service[/blue]")
        # # Creating Port object
        # port = client.V1ServicePort(
        #     protocol = 'TCP',
        #     target_port = port,
        #     port = port,
        #     node_port = 0
        # )

        # # Creating spec 
        # spec = client.V1ServiceSpec(
        #         ports=[port],
        #         selector = {"app": app_label}
        #     )

        # # Creating Service object
        # service = client.V1Service(metadata=metadata, spec=spec)  # V1Service
        # rich.print(service)
        # try:
        #     resp = self._core_v1_api.create_namespaced_service(namespace, service)
        # except Exception as e:
        #     rich.print("[red]Error[/red]")
        #     rich.print(e)
        #     return

        rich.print("[blue]Creating nanorc responder endpoint[/blue]")

        # Creating Meta Data
        metadata = client.V1ObjectMeta(name=name)

        responder_address = client.V1EndpointAddress(
                ip=ip
            )

        ep_port = client.V1EndpointPort(
                port=port,
                name=name
            )

        # Creating endpoints subsets
        subset = client.V1EndpointSubset(addresses=[responder_address], ports=[ep_port])
        # Create Endpoints Objects
        endpoints = client.V1Endpoints(metadata=metadata, subsets=[subset])

        try:
            self._core_v1_api.create_namespaced_endpoints(namespace, endpoints)
        except Exception as e:
            rich.print("[red]Error[/red]")
            rich.print(e)
            return
# ---
def main():
    # config.load_kube_config()

    # core_v1 = client.CoreV1Api()
    # apps_v1 = client.AppsV1Api()

    # list_pods(core_v1)
    # create_daqapp_deployment(apps_v1, 'trigger', 'trg', 'dunedaq')
    # create_daqapp_service(core_v1, 'trigger', 'trg', 'dunedaq')
    # create_nanorc_responder(core_v1, 'nanorc', 'nanorc', 'dunedaq', '192.168.200.12', 56789)
    # 
    partition = 'daq-p0'
    pm = K8SProcessManager()
    pm.list_pods()
    pm.create_namespace(partition)
    pm.create_daqapp_deployment('trigger', 'trg', partition)
    pm.create_nanorc_responder('nanorc', 'nanorc', partition, '192.168.200.12', 56789)
    pm.list_pods()

if __name__ == '__main__':
    main()