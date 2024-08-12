FROM registry.fedoraproject.org/fedora:40
LABEL maintainer="copr-devel@lists.fedorahosted.org"

RUN dnf -y update && \
    # Base packages
    dnf -y install htop \
                   make \
                   wget \
                   net-tools \
                   iputils \
                   vim \
                   mlocate \
                   git-core git-lfs \
                   sudo \
                   python3-ipdb \
                   findutils \
    # The dependencies for this project
    && dnf -y install \
                   npm \
                   java \
    && dnf clean all

RUN npm install -g shadow-cljs@">=2.26.0 <3.0.0"

# TODO In the next steps we want to copy the source code to the container,
# install all Javascript dependencies and pre-install all ClojureScript
# dependencies. However we want to make them available to the bind-mounted
# directory in /opt/log-detective-website that will be used when running the
# container. Unfortunatelly, I don't know how to do that, which makes running
# the container for the first time take a couple of minutes before it is ready.
# To whomever trying to fix this, here are some useful commands:
#
# We cannot use volumes to bindmount code from the host during the build phase.
# We need to copy them.
# COPY ./ /src/code/
#
# WORKDIR /src/code/frontend
# RUN npm install
#
# Unintuitive command but it downloads all ClojureScript dependencies
# https://github.com/thheller/shadow-cljs/issues/362
# RUN npx shadow-cljs classpath
