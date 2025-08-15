# OpenShift deployment

At this time, the `logdetective` website is deployed in Fedora
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
[communishift-logdetective][group2] group.

## Login

First, log in using the OpenShift dashboard URL, then click your name
in the top-right and "Copy login command". Display token and run the
`oc` command.

```bash
oc login --token=... --server=https://api.fedora.cj14.p1.openshiftapps.com:6443
```

## Build

The production container uses code from
https://github.com/fedora-copr/logdetective-website
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
[quay.io/logdetective][quay-organization]:

```
docker-compose -f docker-compose.prod.yaml push
```

or

```bash
make push-prod
```

Alternatively, when working with github repo, the image can be published
by simply creating a tag with name respecting [semver](https://semver.org/) convention
and starting with 'v' prefix, i.e. `v0.0.4`.
This will trigger github action in `docker-publish.yml`.

New image will be created with the same tag and pushed to quay.io.
Tag `latest` will also be updated to point to the new image.

The best way to publish an image is to make a new release of the project,
using the github [dialog](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository#creating-a-release).
This will also generate release notes.

## Update production

Once you created the new release, you should wait for our GitHub action to
build a matching container image and push it to [our quay
repository](https://quay.io/repository/logdetective/website?tab=history).

When you see the image in the listing, continue with the regular Deploy process
described below.

You can then verify based on the Image digest what we are running production:
```
oc describe pod logdetective-website-xxxxxxxx-xxxxx | grep 'Image ID'
   Image ID:       quay.io/logdetective/website@sha256:71a5cf95568e593df8a0723081b4bd17506d2236bdb431d9149f00337add3376
```

The Tag History shows these digests.

## Pull Image

Alternativelly you can use existing image.
Pre-build images are available at quay.io/logdetective, semantically versioned,
with versions correponding to tags of this repo.

```bash
docker pull quay.io/logdetective/website:latest
```

Images are build and pushed with every new tag by a github action.


## Deploy

Make sure you are using the correct OpenShift project

```
oc project communishift-log-detective
```

If a Kubernetes/OpenShift configuration change needs to be applied,
run the following command. Otherwise you can skip it.

```
oc apply -f openshift/logdetective.yaml
```

To kill the current deployment and start a fresh, up-to-date
container, run

```
oc rollout restart deploy/logdetective-website
```

You can debug the instance using

```
oc logs -f deploy/logdetective-website
# or
oc rsh deploy/logdetective-website
```

[quay-organization]: https://quay.io/repository/logdetective/website
[group1]: https://accounts.fedoraproject.org/group/communishift/
[group2]: https://accounts.fedoraproject.org/group/communishift-logdetective/


### Secrets

Hugging Face token:
```
$ oc create secret generic hf-secret --from-literal=token=$TOKEN
```

Sentry token must be taken from sentry configuration, if it is setup.
Otherwise the reporting won't work.

```
oc create secret generic sentry-secret --from-literal=token=$TOKEN
```


## TLS certificates
We use the `certbot` tool to get our Let's Encrypt certificates.

We generate a single certificate that works for both of our domains in 4 combinations:
1. `*.log-detective.com`
1. `.log-detective.com`
1. `*.logdetective.com`
1. `.logdetective.com`

We need all these 4 entries to get https://log... and https://www... working.

Both our domains are hosted on `porkbun.com`. We use DNS TXT entries to verify
we own the domain during the cert generation process.

Ping @TomasTomecek to get access to the domain if you want to refresh the certs
or set up a DNS entry.

Start by installing certbot:
```
$ dnf install certbot
```

### Automated

There is a plugin
[certbot_dns_porkbun](https://github.com/infinityofspace/certbot_dns_porkbun)
for certbot that makes domain refresh trivial.

Makes sure the plugin is installed in the same python sitelib as the main
certbot tool. Otherwise certbot tool won't find it.

You can verify it works correctly like this:
```
$ certbot plugins

* dns-porkbun
Description: Obtain certificates using a DNS TXT record for Porkbun domains
Interfaces: Authenticator, Plugin
Entry point: EntryPoint(name='dns-porkbun',
value='certbot_dns_porkbun.cert.client:Authenticator', group='certbot.plugins')
```

The plugin uses porkbun's API secret and a key to authenticate. Once you have
it, just fire this command and it should yield the certificates in a few
minutes (DNS propagation can take some time, hence the 120 seconds below).

```
$ certbot certonly --config-dir cert/ --work-dir cert/ --logs-dir cert/ \
  --authenticator dns-porkbun --preferred-challenges dns --email $USER@redhat.com \
  -d '*.log-detective.com' -d '*.logdetective.com' \
  -d 'log-detective.com' -d 'logdetective.com' \
  --dns-porkbun-key $KEY \
  --dns-porkbun-secret $SECRET \
  --dns-porkbun-propagation-seconds 120
```

**Note: certbot may generate files under either log-detective.com or logdetective.com paths.**

Head over now to the section [Apply certificates](#apply-certificates).

### Manual

This is a copy-pasta of Packit's process: https://github.com/packit/deployment/blob/main/docs/deployment/tls-certs.md
Praise @jpopelka

Run certbot in the root of this git repo.
```
$ certbot certonly --config-dir cert/ --work-dir cert/ --logs-dir cert/ \
  --manual --preferred-challenges dns \
  --email $USER@redhat.com \
  -d '*.log-detective.com' -d '*.logdetective.com' \
  -d 'log-detective.com' -d 'logdetective.com'
```

You will soon be prompted:
```
Please deploy a DNS TXT record under the name:
```

Set those 2 TXT DNS entries for log-detective.com and logdetective.com
and wait for DNS to resolve them:
```
$ watch -d nslookup -q=TXT _acme-challenge.logdetective.com
```

Alternatively check the record using porkbun's DNS server:
```
$ dig -t txt _acme-challenge.logdetective.com. @curitiba.ns.porkbun.com.
```
Delete those TXT DNS records.

All certificate stuff is in gitignored cert/ folder.


### Apply certificates

You can verify the newly created cert with `openssl` CLI. Here we check that both domains are set as SAN:
```
$ openssl x509 -inform pem -noout -text -in 'cert/live/logdetective.com/fullchain.pem'
...
  X509v3 Subject Alternative Name:
      DNS:*.log-detective.com, DNS:*.logdetective.com, DNS:log-detective.com, DNS:logdetective.com
```

Make sure that paths specified in the spec for Log Detective deployment in `log-detective.yaml` are in sync with actual files in volume:

- "/persistent/letsencrypt/live/log-detective.com/cert.pem"
- "/persistent/letsencrypt/live/log-detective.com/privkey.pem"
- "/persistent/letsencrypt/live/log-detective.com/fullchain.pem"

The webserver expects them (see the production Dockerfile).

Copy the content of directory `cert/` to the running logdetective website pod:
```
$ oc cp cert/ logdetective-website-$pod:/persistent
```

Connect to the pod, back up old certs and rename cert/ to letsencrypt/:
```
$ oc rsh deployment/logdetective-website

$ mv /persistent/letsencrypt{,-old}
$ mv /persistent/{cert,letsencrypt}
```

Kill the running pod so the certs are actually loaded.

🎉🎉🎉
