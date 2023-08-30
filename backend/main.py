import flask
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


@app.route("/frontend/fetch-logs/")
def frontend_fetch_logs():
    return flask.jsonify({
        "build_id": 12345,
        "build_id_title": "Copr build ID",
        "log": LOG_OUTPUT,
    })
