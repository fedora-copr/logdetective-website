# Log Detective website

Production instance: http://logdetective.com

## DEMO

![Video](./frontend/public/img/log_detective_demo.gif)

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
