#!/usr/bin/python3
"""
Iterate over failed koji builds and using logjuicer, prepare a data set out of them.

You need to have logjuicer available on your $PATH, compile and install it out of HEAD

https://github.com/logjuicer/logjuicer
"""
import argparse
import json
import os
import tempfile
import koji
import requests
from pathlib import Path
from subprocess import check_call, CalledProcessError
from typing import Iterator, Any, Optional

from backend.fetcher import KojiProvider, FetchError


interested_log_names = ("build.log", "root.log")
koji_requests_session = requests.sessions.Session()
koji_url = "https://koji.fedoraproject.org"
koji_top_url = "https://kojipkgs.fedoraproject.org/"
koji_api_url = "{}/kojihub".format(koji_url)


class LogjuicerDatasetBuilder:
    def __init__(self):
        self.koji_client = koji.ClientSession(koji_api_url)

    def get_latest_successful_build(self, package_id: int) -> dict[str, Any]:
        builds = self.koji_client.listBuilds(
            type="rpm", state=koji.BUILD_STATES['COMPLETE'],
            # TODO: match target/chroot
            queryOpts={'order': '-completion_time', 'limit': 1},
            packageID=package_id,
        )
        try:
            return builds[0]
        except IndexError:
            print(f"WARNING: can't find latest successful build: {builds}")
            return {}

    def get_latest_successful_logs(self, package_id: int) -> dict[str, str]:
        # no logs here, just relative link chunks
        latest_build = self.get_latest_successful_build(package_id)
        if not latest_build:
            return {}
        logs = self.koji_client.getBuildLogs(latest_build["build_id"])
        response = {}
        for log_data in logs:
            if log_data["dir"] not in ("noarch", "x86_64"):
                continue
            if log_data["name"] not in ("build.log", "root.log"):
                continue
            response[log_data["name"]] = koji_requests_session.get(
                f"{koji_top_url}{log_data['path']}").text
        return response

    def iter_koji_builds(self, start_from_nvr: Optional[str] = None) -> Iterator[dict]:
        """ provide iterator of failed koji builds for further processing, descending order """
        iterations = 100
        limit = 10
        if start_from_nvr:
            latest_failed_build = self.koji_client.getBuild(start_from_nvr)
        else:
            latest_failed_build = self.koji_client.listBuilds(
                type="rpm", state=koji.BUILD_STATES["FAILED"],
                queryOpts={'order': '-completion_time', 'limit': 1}
            )[0]
        last_time = latest_failed_build["completion_time"]
        while iterations:
            builds = self.koji_client.listBuilds(
                type="rpm", state=koji.BUILD_STATES["FAILED"], completeBefore=last_time,
                queryOpts={'order': '-completion_time', 'limit': limit}
            )
            last_time = builds[-1]["completion_time"]
            iterations -= 1
            yield from builds

    def evaluate_log_files(self, build: dict, root_dir_path: Path):
        """ fetch build.log and root.log files and eval them with logjuicer """
        build_id = build["build_id"]
        package_id = build["package_id"]
        completion_time = build["completion_time"]
        k = KojiProvider(build_or_task_id=build_id)

        try:
            failed_logs = {item["name"]: item["content"] for item in k.fetch_logs()}
        except FetchError as ex:
            print(f"WARNING: unable to obtain log files for build {build_id}: {ex}")
            return

        suc_logs = self.get_latest_successful_logs(package_id)
        if not suc_logs:
            return

        for log_name in interested_log_names:
            try:
                log_content = suc_logs[log_name]
            except KeyError:
                # couldn't fetch last successful log, let's continue
                continue
            with tempfile.NamedTemporaryFile(prefix=log_name) as suc:
                succ_log_path = Path(suc.name)
                succ_log_path.write_text(log_content)
                with tempfile.NamedTemporaryFile(prefix=log_name) as fail:
                    fail_log_path = Path(fail.name)
                    fail_log_content = failed_logs[log_name]
                    fail_log_path.write_bytes(fail_log_content)
                    anomaly_snippet = self.logjuicer_get_all_anomalies(
                        str(succ_log_path), str(fail_log_path))
                    print(f"[{completion_time}] {build['nvr']}, {log_name} "
                          f"({len(fail_log_content)}), LJ: {len(anomaly_snippet)}")
                    self.record(build["nvr"], log_name, root_dir_path,
                                anomaly_snippet, fail_log_content)

    def logjuicer_get_all_anomalies(self, succ_log_path: str, fail_log_path: str) -> str:
        with tempfile.NamedTemporaryFile(prefix='logjuicer', suffix='.json') as juicer:
            e = os.environ.copy()
            # https://github.com/logjuicer/logjuicer/issues/91
            e["LOGJUICER_KEEP_DUPLICATE"] = "1"
            try:
                check_call(["logjuicer", "--report", juicer.name,
                            "diff", succ_log_path, fail_log_path], env=e)
            except CalledProcessError as ex:
                print(f"logjuicer failed for {succ_log_path}: {ex}")
                return {}
            juicer_output = json.load(juicer)
            anomaly_lines = []
            for report in juicer_output["log_reports"]:
                anomalies = report["anomalies"]
                for anomaly in anomalies:
                    # include only anomalies with this relevance
                    if anomaly["anomaly"]["distance"] >= 0.5:
                        anomaly_lines += anomaly["before"]
                        anomaly_lines.append(anomaly["anomaly"]["line"])
                        anomaly_lines += anomaly["after"]
            # Openai has returned an error: This model's maximum context length is 8192 tokens.
            return "\n".join(anomaly_lines)[-8000:]

    def record(self, build: str, logname: str, root_dir_path: Path,
               logjuicer_snippet: str, full_log: str):
        build_results_dir = root_dir_path / f"{build}"
        build_results_dir.mkdir(exist_ok=True)
        if logjuicer_snippet:
            logjuicer_path = build_results_dir / f"logjuicer-{logname}"
            if not logjuicer_path.exists():
                logjuicer_path.write_text(logjuicer_snippet)
        if full_log:
            full_log_path = build_results_dir / logname
            if not full_log_path.exists():
                full_log_path.write_bytes(full_log)


def main():
    parser = argparse.ArgumentParser("logjuicer-dataset-create")
    parser.add_argument("--nvr", type=str, default=None,
                        help="start from this NVR and continue to older builds")
    parser.add_argument("--path", type=str, default="./logjuicer-data/",
                        help="place results in this directory")
    args = parser.parse_args()

    root_dir_path = Path(args.path)
    root_dir_path.mkdir(exist_ok=True)
    builder = LogjuicerDatasetBuilder()
    for build in builder.iter_koji_builds(start_from_nvr=args.nvr):
        builder.evaluate_log_files(build, root_dir_path)


main()
