# Log Detective website

Production instance: http://logdetective.com

## DEMO

![Video](./frontend/public/img/log_detective_demo.gif)

## Submit annotations via API

### Copr

This is how you can submit annotations to Log Detective via our API. We'll use
python code to demonstrate this for annotating a Copr build log..
```
import requests

build_id = "8896521"
chroot = "rhel-9-x86_64"
url = f"https://logdetective.com/frontend/contribute/copr/{build_id}/{chroot}"

data = {
    "username": "FAS:me",
    "fail_reason": "Failed because...",
    "how_to_fix": "Like this...",
    "spec_file": {
        "name": "llvm.spec",
        "content": "Yes, the actual content of the spec file"
    },
    # if you are annotating a container build
    # "container_file": None,
    "logs": [
        {
            # could be any log file, but usually it is "build.log"
            "name": "build.log",
            # please put the whole content of the log file here
            "content": "content of the build log",
            "snippets": [
                {
                    # index of the snippet within the file
                    # you can check they are correct by doing `log_content[start_index:end_index]`
                    "start_index": 1,
                    "end_index": 2,
                    "user_comment": "this snippet is relevant because...",
                    # we store this to be sure the indices are correct
                    "text": "content of the snippet"
                }
            ]
        }
    ]
}
requests.post(url, json=data)
```

Full API docs are available at https://logdetective.com/docs

## Development

Easily run on your machine:

```
docker-compose up -d
```

See README files for frontend and backend:

- [frontend](frontend/README.md)
- [backend](backend/README.md)

### With [logdetective server](https://github.com/fedora-copr/logdetective)

To be able to use parts of the website communicating with logdetective server you need to specify server url. To specify server url you need to add `SERVER_URL` variable into the `docker-compose.yaml`.

Similar to this:
```yaml
...
services:
  backend:
    ...
    environment:
      - SERVER_URL=http://192.168.0.1:8080
```

If you want to also run the logdetective server locally use docker compose on the [logdetective repository](https://github.com/fedora-copr/logdetective). And specify your local IP ("localhost" or 127.0.0.1 can't be used because of container networking).

## Deployment

See [openshift/README](openshift/README.md)
