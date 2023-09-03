import flask
import requests
from pprint import pprint
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
    logs = [{"name": "fake-builder-live.log", "content": LOG_OUTPUT}]

    if source == "copr":
        url = "https://download.copr.fedorainfracloud.org/results/"
        url += "@copr/copr/fedora-38-x86_64/06302362-copr-dist-git/"

        logs = []
        names = ["builder-live.log.gz", "backend.log.gz", "build.log.gz"]
        for name in names:
            response = requests.get("{0}/{1}".format(url, name))
            logs.append({"name": name, "content": response.text})

    return flask.jsonify({
        "build_id": 12345,
        "build_id_title": "Copr build ID",
        "logs": logs,
    })


@app.route("/frontend/contribute/<source>/<int:build_id>", methods=["POST"])
def frontend_contribute_post(source, build_id):
    # TODO Validate and store
    print("Submitted data for {0} build #{1}".format(source, build_id))
    pprint(flask.request.json)

    # TODO A reasonable JSON response
    return flask.jsonify({})
