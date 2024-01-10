FROM registry.fedoraproject.org/fedora:38
MAINTAINER copr-devel@lists.fedorahosted.org

RUN dnf -y update && \
    # Base packages
    dnf -y install htop \
                   make \
                   wget \
                   net-tools \
                   iputils \
                   vim \
                   mlocate \
                   git \
                   sudo \
                   python3-ipdb \
                   findutils \
    # The dependencies for this project
    && dnf -y install \
                   python3-fastapi \
                   python3-uvicorn \
                   python3-jinja2 \
                   python3-requests \
                   python3-koji \
                   python3-copr \
    && dnf clean all
