# Lightspeed build website

## Development

Easily run on your machine:

```
docker-compose up -d
```

See README files for frontend and backend:

- [frontend](frontend/README.md)
- [backend](backend/README.md)


## Features:

- [ ] Fetch build logs from Copr and other build systems
- [ ] Allow uploading build log from user computer
- [ ] Use GET parameter for Copr build id (so that we can link this
      page from a build detail in Copr)
- [ ] Select a text within the log and click a button to anotate it


## Frontend scope:

For this purpose, frontend = Javascript, HTML, CSS

- [ ] Form controls on each page


## Backend scope:

For this purpose backend = Python, storage, etc

- [ ] Store the submitted results
- [ ] Routing for the home page, about, contact, etc pages
- [ ] All the logic for fetching logs based on build IDs
- [ ] Fancy (optional): API to be used from the frontend
    - For example, if we render the page with empty forms, then
      Javascript asks the backend API to fetch the build details and
      logs, and then Javascripts fills the forms, the page will be
      much snappier
