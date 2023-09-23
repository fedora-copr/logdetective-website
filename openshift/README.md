# OpenShift deployment

At this time, the `lightspeed-build` website is deployed in Fedora
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
[communishift-lightspeed-build][group2] group.


## Login

First, log in using the OpenShift dashboard URL, then click your name
in the top-right and "Copy login command". Display token and run the
`oc` command.

```bash
oc login --token=... --server=https://api.fedora.cj14.p1.openshiftapps.com:6443
```


## Deploy

The production container uses code from
https://github.com/fedora-copr/lightspeed-build-website
so commit and push your changes.

Build the container image:

```
docker-compose -f docker-compose.prod.yaml build
```

Push the image to quay.io
[quay.io/jkadlcik/lightspeed-build][quay-repo]:

```
docker-compose -f docker-compose.prod.yaml push
```

Make sure you are using the correct OpenShift project

```
oc project communishift-lightspeed-build
```

If a Kubernetes/OpenShift configuration change needs to be applied,
run the following command. Otherwise you can skip it.

```
oc apply -f openshift/lightspeed-build.yaml
```

To kill the current deployment and start a fresh, up-to-date
container, run

```
oc rollout restart deploy/lightspeed-build-website
```

You can debug the instance using

```
oc logs -f deploy/lightspeed-build-website
# or
oc rsh deploy/lightspeed-build-website
```



[quay-repo]: https://quay.io/repository/jkadlcik/lightspeed-build
[group1]: https://accounts.fedoraproject.org/group/communishift/
[group2]: https://accounts.fedoraproject.org/group/communishift-lightspeed-build/
