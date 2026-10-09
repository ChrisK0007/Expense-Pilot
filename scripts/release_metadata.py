"""Validate release channels before CI can publish a Docker image."""
import os
from pathlib import Path
import re


def release_metadata(version, event, ref, base_ref=""):
    number = r"(?:0|[1-9][0-9]*)"
    if not re.fullmatch(rf"{number}\.{number}\.{number}(?:-beta\.[1-9][0-9]*)?", version):
        raise ValueError("Version must be X.Y.Z or X.Y.Z-beta.N (N starts at 1)")
    beta = "-beta." in version
    branch = base_ref if event == "pull_request" else ref.removeprefix("refs/heads/")
    if branch == "main" and beta:
        raise ValueError("main requires a stable version; remove the beta suffix before release")
    if branch == "beta" and not beta:
        raise ValueError("beta requires a version such as 1.0.1-beta.1")
    tagged = ref.startswith("refs/tags/v")
    if tagged and ref != "refs/tags/v" + version:
        raise ValueError("The Git tag must match server/VERSION")
    publish = event in ("push", "workflow_dispatch") and (
        ref in ("refs/heads/main", "refs/heads/beta") or tagged
    )
    moving_tag = ""
    if publish and ref == "refs/heads/main":
        moving_tag = "latest"
    elif publish and ref == "refs/heads/beta":
        moving_tag = "beta"
    return {"version": version, "publish": str(publish).lower(), "moving_tag": moving_tag}


if __name__ == "__main__":
    version = (Path(__file__).resolve().parents[1] / "server/VERSION").read_text().strip()
    try:
        result = release_metadata(version, os.environ.get("GITHUB_EVENT_NAME", ""),
                                  os.environ.get("GITHUB_REF", ""), os.environ.get("GITHUB_BASE_REF", ""))
    except ValueError as error:
        raise SystemExit(str(error))
    output = "".join(f"{key}={value}\n" for key, value in result.items())
    print(output, end="")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as target:
            target.write(output)
