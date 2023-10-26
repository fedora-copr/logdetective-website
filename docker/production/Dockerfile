FROM registry.fedoraproject.org/fedora:38
MAINTAINER copr-devel@lists.fedorahosted.org

ENV FEEDBACK_DIR=/persistent/results
ENV ENV=production

RUN dnf -y update && \
    # Base packages
    dnf -y install htop \
                   make \
                   wget \
                   net-tools \
                   iputils \
                   vim \
                   mlocate \
                   jq \
                   fpaste \
                   git \
                   sudo \
                   python3-ipdb \
                   findutils \
    # Frontend
    && dnf -y install \
                   npm \
                   java \
    # Backend
    && dnf -y install \
                   python3-fastapi \
                   python3-uvicorn \
                   python3-gunicorn \
                   python3-jinja2 \
                   python3-requests \
                   python3-koji \
                   python3-copr \
                   koji \
    && dnf clean all


RUN git clone https://github.com/fedora-copr/lightspeed-build-website.git /src


WORKDIR /src/frontend
RUN npm install
RUN npm install -g shadow-cljs
RUN npx shadow-cljs release app


# According to the documentation, gunicorn is a valid production server
# https://www.uvicorn.org/deployment/
WORKDIR /src/backend
ENV PYTHONPATH="${PYTHONPATH}:/src"
CMD gunicorn -k uvicorn.workers.UvicornWorker api:app -b 0.0.0.0:8080
