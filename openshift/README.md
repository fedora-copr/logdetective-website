# OpenShift deployment

At this time, the `log-detective` website is deployed in Fedora
CommuniShift.

- Dashboard: https://console-openshift-console.apps.fedora.cj14.p1.openshiftapps.com/
- Documentation: https://docs.fedoraproject.org/en-US/infra/ocp4/sop_communishift/

## Tools

For some reason, in the Fedora repositories, there is an outdated
(version 3.x) `oc` command (the `origin-clients` package). You might
need to install it like this

https://docs.okd.io/latest/cli_reference/openshift_cli/getting-started-cli.html

## Permissions

To be able to access the OpenShift project please ping fedora-infra to
add you to [communishift][group1] group and @FrostyX, to add you to
[communishift-log-detective][group2] group.

## Login

First, log in using the OpenShift dashboard URL, then click your name
in the top-right and "Copy login command". Display token and run the
`oc` command.

```bash
oc login --token=... --server=https://api.fedora.cj14.p1.openshiftapps.com:6443
```

## Deploy

The production container uses code from
https://github.com/fedora-copr/log-detective-website
so commit and push your changes.

Build the container image:

```
docker-compose -f docker-compose.prod.yaml build --no-cache
```

Push the image to quay.io
[quay.io/jkadlcik/log-detective][quay-repo]:

```
docker-compose -f docker-compose.prod.yaml push
```

Make sure you are using the correct OpenShift project

```
oc project communishift-log-detective
```

If a Kubernetes/OpenShift configuration change needs to be applied,
run the following command. Otherwise you can skip it.

```
oc apply -f openshift/log-detective.yaml
```

To kill the current deployment and start a fresh, up-to-date
container, run

```
oc rollout restart deploy/log-detective-website
```

You can debug the instance using

```
oc logs -f deploy/log-detective-website
# or
oc rsh deploy/log-detective-website
```

[quay-repo]: https://quay.io/repository/jkadlcik/log-detective
[group1]: https://accounts.fedoraproject.org/group/communishift/
[group2]: https://accounts.fedoraproject.org/group/communishift-log-detective/
