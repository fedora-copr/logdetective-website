import flask
from pprint import pprint
from .providers import (
    FetchError,
    decode_base64_url,
    fetch_debug_logs,
    fetch_copr_logs,
    fetch_koji_logs,
    fetch_packit_logs,
    fetch_url_logs,
)


COPR_BUILD_URL = "https://copr.fedorainfracloud.org/coprs/build/{0}"
KOJI_BUILD_URL = "https://koji.fedoraproject.org/koji/buildinfo?buildID={0}"


# TODO All routes should work with trailing slashes and without trailing slashes


app = flask.Flask(
    __name__,
    static_url_path="",
    static_folder="../frontend/public/",
    template_folder="../frontend/public/")


@app.errorhandler(Exception)
def handle_exceptions(ex):
    return error("Server Error", str(ex))


def error(title, description):
    # TODO We need to handle exceptions when there is a syntax error in the
    # code, etc.
    print(title)
    print(description)

    if flask.request.path.startswith("/frontend"):
        data = {"error": title, "description": description}
        return flask.jsonify(data), 200
    return "SERVER ERROR", 500


# WebUI routes
# The routes accessed by users

@app.route("/")
def home():
    return flask.render_template("index.html")


@app.route("/contribute/<path:args>")  # path allows optional number of params
def contribute(args):
    return flask.render_template("contribute.html")


# Frontend API routes
# These are called from JavaScript to asynchronously fetch or post data

@app.route("/frontend/contribute/copr/<int:build_id>/<chroot>",
           defaults={"source": "copr"})
@app.route("/frontend/contribute/koji/<int:build_id>/<arch>",
           defaults={"source": "koji"})
@app.route("/frontend/contribute/packit/<int:packit_id>/",
           defaults={"source": "packit"})
@app.route("/frontend/contribute/url/<base64>/",
           defaults={"source": "url"})
@app.route("/frontend/contribute/debug", defaults={"source": "debug"})
def frontend_contribute_copr(source=None, *args, **kwargs):
    """
    This route is called from JavaScript, right after the page is loaded.
    It fetches logs from the outside world and returns them as JSON, so that
    JavaScript can display them to the user
    """
    try:
        if source == "copr":
            build_title = "Copr build"
            build_id = kwargs["build_id"]
            build_url = COPR_BUILD_URL.format(build_id)
            logs = fetch_copr_logs(kwargs["build_id"], kwargs["chroot"])

        elif source == "koji":
            build_title = "Koji build"
            build_id = kwargs["build_id"]
            build_url = KOJI_BUILD_URL.format(build_id)
            logs = fetch_koji_logs(kwargs["build_id"], kwargs["arch"])

        elif source == "packit":
            build_title = "Packit build"
            build_id = kwargs["packit_id"]
            # TODO Packit probably doesn't have a Web UI for showing a single
            # packit build. We could instead point directly to Copr or Koji but
            # that would require refactoring the code (and making it more
            # complex) and I don't want to do that right now.
            build_url = "https://dashboard.packit.dev/jobs/copr-builds"
            logs = fetch_packit_logs(kwargs["packit_id"])

        elif source == "url":
            build_title = "URL"
            build_id = None
            build_url = decode_base64_url(kwargs["base64"])
            logs = fetch_url_logs(build_url)

        else:
            build_title = "Debug output"
            build_id = "123456"
            build_url = "#"
            logs = fetch_debug_logs()

        return flask.jsonify({
            "build_id": build_id,
            "build_id_title": build_title,
            "build_url": build_url,
            "logs": logs,
        })
    except FetchError as ex:
        title = "Unable to fetch logs from {0}".format(source.capitalize())
        return error(title, str(ex))


# path allows optional number of params
@app.route("/frontend/contribute/<source>/<path:args>", methods=["POST"])
def frontend_contribute_post(source, args):
    """
    This route is called from JavaScript, after clicking the submit button
    It saves the user provided data to our storage
    """

    # TODO Validate and store
    print("Submitted data for {0}: #{1}".format(source, args))
    pprint(flask.request.json)

    # TODO A reasonable JSON response
    return flask.jsonify({})
