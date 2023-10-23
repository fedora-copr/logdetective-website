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
PYTHONPATH=/opt/lightspeed-build-website uvicorn api:app --host 0.0.0.0 --port 5020 --reload
```

Open http://127.0.0.1:5020 in your web browser.
