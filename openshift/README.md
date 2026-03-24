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

Token for authentication with Log Detective must be set if the service demands it.

```
oc create secret generic log-detective-secret --from-literal=token=$TOKEN
```


## TLS certificates
We use the OpenShift `cert-manager` operator to automate the provisioning and renewal of our Let's Encrypt certificates.

We generate a single certificate that covers all 4 of our domain combinations.

*(Note: The HTTP-01 challenge does not support wildcard certificates, so each domain is explicitly listed in the `Ingress` resource).*

### How it Works

Our architecture relies on **Edge Termination** via OpenShift's routing layer.
The application pod (Gunicorn) serves plain HTTP traffic on port `8080`, and the OpenShift router handles all HTTPS decryption and redirection.

The pipeline consists of three main components:

1. **The Issuer (`production_issuer.yaml`):** We maintain a `ClusterIssuer` or `Issuer` configured for the Let's Encrypt production ACME server.
It uses the `HTTP-01` challenge type. To comply with CommuniShift firewall rules, the solver is configured to use a `ClusterIP` service.

2. **The Ingress (`openshift/log-detective.yaml`):**
   Instead of manually defining OpenShift `Route` objects, we define a standard Kubernetes `Ingress`.
   The Ingress contains the `cert-manager.io/issuer: "letsencrypt-production"` annotation. OpenShift automatically translates this `Ingress` into four Edge-terminated `Route` objects.

3. **Certificate Generation & Storage:**
   When the `Ingress` is applied, `cert-manager` detects the annotation and automatically requests a certificate.
   It briefly spins up temporary solver pods to answer Let's Encrypt's HTTP-01 verification ping.
   Once verified, the resulting TLS certificate is saved directly into a Kubernetes `Secret` named `logdetective-production-tls`.
   OpenShift's router natively injects this secret into the live Routes.

### Maintenance and Renewals

Approximately 30 days before the certificates expire, `cert-manager` will spin up background solver pods,
re-verify the domains, and update the Kubernetes `Secret`.
OpenShift will reload the new certificates at the edge without dropping any traffic and without requiring an application restart.

**Important Quota Note:** Because `cert-manager` attempts to validate all 4 domains simultaneously during renewal, it will briefly spin up multiple temporary solver pods.
The `communishift-log-detective` project must maintain a minimum quota of **5 pods** to ensure renewals do not fail due to resource exhaustion.

In new deployment, use `staging_issuer.yaml` and `staging_certificate.yaml` resource definitions,
to verify that the cluster supports `cert-manager`.

This test should be conducted before full deployment of the website.
