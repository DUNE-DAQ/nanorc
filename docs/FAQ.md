# FAQ

## NanoRC exited ungracefully and all my apps are still running, what do I do?
You'll need to go on each of the servers where the applications where running, run `htop --user ${USER}`, click (yes, click on your terminal) on the `daq_application`, then `F9` and enter twice. You can also do the equivalent by doing `ps a|grep daq_application`, note the first number of the line and run `kill <the-number>`.

## NanoRC it can't start the response listener, what do I do?
You probably are running on the NP04 cluster with the web proxy. You can quit nanorc, and run `source ~np04daq/bin/web_proxy.sh -u` and start again.

## NanoRC won't boot my apps?
There are many reasons why this could happen, here are the 2 most common:
 - You don't have password-less ssh keys (see how to create password-less ssh keys)
 - Somebody else is running on the same server, in which case you need to pass `--partition-number 1` (or any number between 1 and 10) to the `nanorc` command.

## How do I create password-less ssh keys?
Here is the broad idea (but you are welcome to look on Google too):
```bash
ssh-keygen
```
then tap `<Enter>` twice when prompted for a password (*do not* enter a password here).
Then do:
```bash
ssh-copy-id <the-host-where-you-app-will-run>
```
This command should prompt you a password, for the last time. This is the same password you used to log on the server. After that you can do:
```bash
ssh <the-host-where-you-app-will-run>
```
and you _shouldn't_ be prompted for a password ever again!

## I don't want to create ssh keys, how do I do?
This isn't particularly recommended, but if you are running on the `dunegpvm` you won't have the choice. You can run nanorc with kerberos, by doing `nanorc --kerberos ...`.
