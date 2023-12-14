FROM registry.fedoraproject.org/fedora:38
MAINTAINER copr-devel@lists.fedorahosted.org

ENV ENV=production

RUN dnf -y update && \
    # Base packages
    dnf -y install git \
    # Frontend
    && dnf -y install \
                   npm \
                   java


RUN git clone https://github.com/fedora-copr/log-detective-website.git /src


WORKDIR /src/frontend
RUN npm install
RUN npm install -g shadow-cljs
RUN npx shadow-cljs release app

FROM registry.fedoraproject.org/fedora:38
MAINTAINER copr-devel@lists.fedorahosted.org

ENV ENV=production

# TODO: how to get envs from env file in openshift?
ENV STORAGE_DIR=/persistent
ENV FEEDBACK_DIR=/persistent/results

RUN dnf -y install python3-fastapi \
                   python3-uvicorn \
                   python3-gunicorn \
                   python3-jinja2 \
                   python3-requests \
                   python3-koji \
                   python3-copr \
                   koji \
                   htop \
                   btop \
                   make \
                   wget \
                   net-tools \
                   iputils \
                   vim \
                   mlocate \
                   jq \
                   fpaste \
                   git \
                   python3-ipdb \
                   findutils \
    && dnf clean all \
    && mkdir -p /src/{frontend,backend}

COPY --from=0 /src/frontend/public /src/frontend/public
COPY --from=0 /src/backend /src/backend

# According to the documentation, gunicorn is a valid production server
# https://www.uvicorn.org/deployment/
WORKDIR /src/backend
ENV PYTHONPATH="${PYTHONPATH}:/src"

# We should put this into a config file
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--certfile", "/persistent/letsencrypt/live/log-detective.com/cert.pem", "--keyfile", "/persistent/letsencrypt/live/log-detective.com/privkey.pem", "--ca-certs", "/persistent/letsencrypt/live/log-detective.com/fullchain.pem", "api:app", "-b", "0.0.0.0:8080"]
