# FAQ for Kubernetes

## What was that command again to use K8s with the NP04 cluster?
```bash
daqconf_multiru_gen --force-pm k8s .... conf-dir # generate the configuration in the usual way, with the --force-pm
upload_conf conf-dir conf-name # upload the configuration to the service
nanorc --pm k8s://np04-srv-015:31000 db://conf-name # tell nanorc to run k8s process manager
```

## NanoRC exited ungracefully and all my apps are still running, what do I do?
```bash
kubectl delete namespace <your-session-name>
```
should sort you out.

## NanoRC can't start the response listener, what do I do?
See the same entry in the FAQ.

## NanoRC won't boot my apps?
There are many reasons why this could happen, here are the 2 most common:
 - Somebody else is running on the same server, in which case you need to pass `--partition-number 1` (or any number between 1 and 10) to the `nanorc` command.
 - Somebody else is running with the same k8s namespace, in which case you should change the session name
 - The machine you are trying to run on don't have enough resources (or at least k8s thinks so). You can check the exact reason by heading to the np04-srv-015:31001 page, then selecting your session name, and going to the list of pod and selecting the one that hasn't started.

## Where are my app logs?
To see logs, do:
 ```bash
 kubectl logs -n <your-session-name> <app-name>
 ```

## I want more logs
See the same entry in the FAQ.
