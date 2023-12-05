# Backend

## Dependencies

This is not packaged, and probably never will be. Install API and ASGI server
manually:

```
dnf install python3-fastapi python3-uvicorn
```

## Development

Run the development ASGI server with

```
PYTHONPATH=/opt/log-detective-website uvicorn api:app --host 0.0.0.0 --port 5020 --reload
```

or use compose:

```bash
docker-compose up -d
```

Open http://127.0.0.1:5020 in your web browser.

## Testing

Run the tests in container with

```bash
make test-backend-in-container
```

or locally on your machine. You need to have installed all the dependencies inside all dockerfiles
located in the docker/backend directory.

```bash
make test-backend-local
```
