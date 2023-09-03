import flask
import requests
from .data import LOG_OUTPUT


app = flask.Flask(
    __name__,

    static_url_path="",
    static_folder="../frontend/public/",
    template_folder="../frontend/public/")


@app.route("/")
def home():
    return flask.render_template("index.html")


@app.route("/contribute/<source>/<int:build_id>")
def contribute(source, build_id):
    return flask.render_template("contribute.html")


@app.route("/frontend/contribute/<source>/<int:build_id>")
def frontend_contribute_get(source, build_id):
    """
    This route is called from JavaScript, right after the page is loaded.
    It fetches logs from the outside world and returns them as JSON, so that
    JavaScript can display them to the user
    """
    log = LOG_OUTPUT
    if source == "copr":
        url = "https://download.copr.fedorainfracloud.org/results/"
        url += "@copr/copr/fedora-38-x86_64/06302362-copr-dist-git/"
        url += "builder-live.log.gz"
        response = requests.get(url)
        log = response.text

    return flask.jsonify({
        "build_id": 12345,
        "build_id_title": "Copr build ID",
        "log": log,
    })
