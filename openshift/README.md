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

or

```bash
make build-prod
```

Push the image to quay.io
[quay.io/log-detective][quay-organization]:

```
docker-compose -f docker-compose.prod.yaml push
```

or

```bash
make push-prod
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

[quay-organization]: https://quay.io/repository/log-detective/website
[group1]: https://accounts.fedoraproject.org/group/communishift/
[group2]: https://accounts.fedoraproject.org/group/communishift-log-detective/


## TLS certificates

This is a copy-pasta of Packit's process: https://github.com/packit/deployment/blob/main/docs/deployment/tls-certs.md
Praise @jpopelka

We will use DNS TXT entries to verify we own the domain. Ping @TomasTomecek to get access to the domain.

Locally:
```
$ dnf install certbot
```

Run certbot in the root of this git repo.
```
$ certbot certonly --config-dir cert/ --work-dir cert/ --logs-dir cert/ --manual --preferred-challenges dns --email ttomecek@redhat.com -d log-detective.com -d logdetective.com
```

```
Please deploy a DNS TXT record under the name:
```

Set those 2 TXT DNS entries for log-detective.com and logdetective.com

Wait for those 2 entries to be up:
```
$ watch -d nslookup -q=TXT _acme-challenge.logdetective.com
```

Alternatively check the record using porkbun's DNS server:
```
$ dig -t txt _acme-challenge.logdetective.com. @curitiba.ns.porkbun.com.
```

You need to run the certbot command twice for both certificates.

Once verified, you should delete those TXT DNS records.

All certificate stuff is in gitignored cert/ folder.

Copy the content to the running log-detective:
```
$ oc cp cert/ log-detective-temp-pod:/persistent
```

Connect to the pod and rename cert/ to letsencrypt/:
```
$ oc rsh deployment/log-detective-website
$ mv /persistent/{cert,letsencrypt}
```

🎉🎉🎉
