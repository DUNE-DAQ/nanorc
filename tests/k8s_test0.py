#!/usr/bin/env python

from kubernetes import client, config
from kubernetes import utils

import yaml
from os import path
from copy import deepcopy
import rich
import distutils.util

# ---
def query_yes_no(question, default='no'):
    if default is None:
        prompt = " [y/n] "
    elif default == 'yes':
        prompt = " [Y/n] "
    elif default == 'no':
        prompt = " [y/N] "
    else:
        raise ValueError(f"Unknown setting '{default}' for default.")

    while True:
        try:
            resp = input(question + prompt).strip().lower()
            if default is not None and resp == '':
                return default == 'yes'
            else:
                return distutils.util.strtobool(resp)
        except ValueError:
            print("Please respond with 'yes' or 'no' (or 'y' or 'n').\n")

# ---
def load_manifest(mpath):
    with open(mpath) as f:
        dep = yaml.safe_load_all(f)
        return [d for d in dep]

# ---
def list_pods(core_v1):
    print("Listing pods with their IPs:")
    ret = core_v1.list_pod_for_all_namespaces(watch=False)
    for i in ret.items:
        print("%s\t%s\t%s" % (i.status.pod_ip, i.metadata.namespace, i.metadata.name))


def create_deployment(api, deployment, name, namespace):

    body = deepcopy(deployment)
    body['metadata']['name'] = name

    # Create deployement
    resp = api.create_namespaced_deployment(
        body=body, namespace=namespace
    )

    print("\n[INFO] deployment `nginx-deployment` created.\n")
    print("%s\t%s\t\t\t%s\t%s" % ("NAMESPACE", "NAME", "REVISION", "IMAGE"))
    print(
        "%s\t\t%s\t%s\t\t%s\n"
        % (
            resp.metadata.namespace,
            resp.metadata.name,
            resp.metadata.generation,
            resp.spec.template.spec.containers[0].image,
        )
    )


def update_deployment(api, deployment, name, namespace):
    # Update container image
    deployment.spec.template.spec.containers[0].image = "nginx:1.16.0"

    # patch the deployment
    resp = api.patch_namespaced_deployment(
        name=name, namespace=namespace, body=deployment
    )

    print("\n[INFO] deployment's container image updated.\n")
    print("%s\t%s\t\t\t%s\t%s" % ("NAMESPACE", "NAME", "REVISION", "IMAGE"))
    print(
        "%s\t\t%s\t%s\t\t%s\n"
        % (
            resp.metadata.namespace,
            resp.metadata.name,
            resp.metadata.generation,
            resp.spec.template.spec.containers[0].image,
        )
    )


def restart_deployment(api, deployment, name, namespace):
    # update `spec.template.metadata` section
    # to add `kubectl.kubernetes.io/restartedAt` annotation
    deployment.spec.template.metadata.annotations = {
        "kubectl.kubernetes.io/restartedAt": datetime.datetime.utcnow()
        .replace(tzinfo=pytz.UTC)
        .isoformat()
    }

    # patch the deployment
    resp = api.patch_namespaced_deployment(
        name=name, namespace=namespace, body=deployment
    )

    print(f"\n[INFO] deployment `{name}` restarted.\n")
    print("%s\t\t\t%s\t%s" % ("NAME", "REVISION", "RESTARTED-AT"))
    print(
        "%s\t%s\t\t%s\n"
        % (
            resp.metadata.name,
            resp.metadata.generation,
            resp.spec.template.metadata.annotations,
        )
    )


def delete_deployment(api, name, namespace):
    # Delete deployment
    resp = api.delete_namespaced_deployment(
        name=name,
        namespace=namespace,
        body=client.V1DeleteOptions(
            propagation_policy="Foreground", grace_period_seconds=5
        ),
    )
    print(f"\n[INFO] deployment `{name}` deleted.")

#------------------------------------------------------
def create_daqapp_deployment(api, name, namespace):
    # load template from file
    # dep = load_manifest(path.join(path.dirname(__file__), '..', '..', 'pocket', 'manifests', 'minidaqapp', 'daq_application.yaml'))
    manifests = load_manifest(path.join('/home/ale/devel/pocket/', 'pocket', 'manifests', 'minidaqapp', 'daq_application.yaml'))

    if len(manifests) != 1:
        raise RuntimeError(f"Expecting 1 manifest in yaml document, found {len(manifests)}")

    daqapp_manifest = manifests[0]
    # Replace name and namespace
    daqapp_manifest['metadata']['name'] = name
    daqapp_manifest['metadata']['namespace'] = namespace
    daqapp_manifest['spec']['selector']['matchLabels']['app'] = name
    daqapp_manifest['spec']['template']['metadata']['labels']['app'] = name

    args = [
        '--name', name,
        '--commandFacility', 'rest://localhost:3333'
    ]
    daqapp_manifest['spec']['template']['spec']['containers'][0]['args'] = args

    create_deployment(api, daqapp_manifest, name, namespace)
    

def create_nanorc_responder(api, name, namespace):
    # Load template from file
    manifests = load_manifest(path.join('/home/ale/devel/pocket/', 'pocket', 'manifests', 'minidaqapp', 'nanorc_responder.yaml'))
    dep['metadata']['namespace'] = namespace
    create_deployment(api, dep, name, namespace) 

if __name__ == '__main__':
    
    import time
    
    # Configs can be set in Configuration class directly or using helper utility
    config.load_kube_config()

    api = client.ApiClient()

    core_v1 = client.CoreV1Api()
    apps_v1 = client.AppsV1Api()
    
    list_pods(core_v1)

    create_daqapp_deployment(apps_v1, 'rubu', 'dunedaq')
    # create_nanorc_responder(apps_v1, 'nanorc', 'dunedaq ')

    # # time.sleep(10)
    # while(True):
    #     list_pods(core_v1)

    #     yn = query_yes_no("Continue?")
    #     if yn:
    #         break

    # delete_deployment(apps_v1, 'rubu' ,'dunedaq ')
    # delete_deployment(apps_v1, 'nanorc' ,'dunedaq ')
    # list_pods(core_v1)

