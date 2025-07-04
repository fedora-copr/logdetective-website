FROM registry.fedoraproject.org/fedora:42
LABEL maintainer="copr-devel@lists.fedorahosted.org"

ENV ENV=production

RUN dnf -y update && \
    # Base packages; git-lfs for the gif we have on the frontpage
    dnf -y install git-core git-lfs \
    # Frontend
    && dnf -y install \
                   npm \
                   java


RUN git clone https://github.com/fedora-copr/logdetective-website.git /src


WORKDIR /src/frontend
RUN npm install
RUN npm install -g shadow-cljs@">=2.26.0 <3.0.0"
RUN npx shadow-cljs release app

FROM registry.fedoraproject.org/fedora:42
LABEL maintainer="copr-devel@lists.fedorahosted.org"

ENV ENV=production

# TODO: how to get envs from env file in openshift?
ENV STORAGE_DIR=/persistent
ENV FEEDBACK_DIR=/persistent/results

RUN dnf -y install python3-fastapi \
                   python3-uvicorn+standard \
                   python3-gunicorn \
                   python3-jinja2 \
                   python3-requests \
                   python3-koji \
                   python3-copr \
                   python3-pip \
                   koji \
                   htop \
                   make \
                   wget \
                   net-tools \
                   iputils \
                   vim \
                   plocate \
                   jq \
                   fpaste \
                   git \
                   findutils \
    && dnf clean all \
    && pip3 --no-cache-dir install datasets \
    && mkdir -p /src/{frontend,backend}

COPY --from=0 /src/frontend/public /src/frontend/public
COPY --from=0 /src/backend /src/backend
COPY --from=0 /src/files/compile_extraction_dataset.py /usr/bin/compile_extraction_dataset.py

# According to the documentation, gunicorn is a valid production server
# https://www.uvicorn.org/deployment/
WORKDIR /src/backend/src
ENV PYTHONPATH="${PYTHONPATH}:/src/backend"

# We should put this into a config file
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "--certfile", "/persistent/letsencrypt/live/logdetective.com/cert.pem", "--keyfile", "/persistent/letsencrypt/live/log-detective.com/privkey.pem", "--ca-certs", "/persistent/letsencrypt/live/log-detective.com/fullchain.pem", "api:app", "-b", "0.0.0.0:8080", "--max-requests", "50", "--max-requests-jitter", "5"]
