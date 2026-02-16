FROM registry.fedoraproject.org/fedora:42
LABEL maintainer="copr-devel@lists.fedorahosted.org"

RUN dnf -y update && \
    # Base packages
    dnf -y install htop \
                   make \
                   wget \
                   net-tools \
                   iputils \
                   vim \
                   plocate \
                   git-core git-lfs \
                   sudo \
                   findutils \
                   rsync \
    # The dependencies for this project
    && dnf -y install \
                   python3-fastapi \
                   python3-uvicorn+standard \
                   python3-jinja2 \
                   python3-requests \
                   python3-koji \
                   python3-copr \
                   python3-sentry-sdk+fastapi \
                   python3-regex \
    && dnf clean all
