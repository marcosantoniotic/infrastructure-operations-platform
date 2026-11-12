#!/usr/bin/env python3
"""Private recovery context. Never emits environment values or secret contents."""
import argparse
import configparser
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import subprocess
import tarfile


def docker(*args):
    result = subprocess.run(["docker", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Docker recovery operation failed")
    return result.stdout


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def database(path):
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise RuntimeError("Grafana SQLite integrity check failed")
        return {table: db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
                for table in ("dashboard", "data_source")}


def inspect_source(container, project):
    item = json.loads(docker("container", "inspect", container))[0]
    project = Path(project).resolve(strict=True)
    if project == Path("/") or not project.is_dir():
        raise RuntimeError("Unsafe project directory")
    mounts = []
    for mount in item["Mounts"]:
        if mount["Type"] == "volume" and mount["Destination"] == "/var/lib/grafana":
            continue
        if mount["Type"] != "bind" or mount["RW"]:
            raise RuntimeError("Unrepresented writable or non-bind Grafana mount")
        source = Path(mount["Source"])
        if source.is_symlink() or not source.resolve(strict=True).is_relative_to(project):
            raise RuntimeError("Grafana bind is outside the reviewed project")
        for entry in [source, *source.rglob("*")] if source.is_dir() else [source]:
            if entry.is_symlink() or not (entry.is_file() or entry.is_dir()):
                raise RuntimeError("Special files and links are not recovery context")
        mounts.append(mount)
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", item["Image"]):
        raise RuntimeError("An immutable source image is required")
    if any("\n" in value or "\r" in value or "\0" in value for value in item["Config"]["Env"]):
        raise RuntimeError("Multiline environment requires an explicit recovery design")
    image = json.loads(docker("image", "inspect", item["Image"]))[0]["Config"]
    for field in ("Entrypoint", "Cmd", "User", "WorkingDir"):
        if item["Config"].get(field) != image.get(field):
            raise RuntimeError("Custom Grafana execution settings require a reviewed recovery design")
    env = dict(value.split("=", 1) for value in item["Config"]["Env"])
    ini = configparser.ConfigParser(interpolation=None)
    config = PurePosixPath(env.get("GF_PATHS_CONFIG", "/etc/grafana/grafana.ini"))
    # Review a custom mounted grafana.ini as well as environment overrides.
    for mount in sorted(mounts, key=lambda m: len(m["Destination"]), reverse=True):
        destination = PurePosixPath(mount["Destination"])
        try:
            relative = config.relative_to(destination)
        except ValueError:
            continue
        path = Path(mount["Source"]) / relative
        if path.is_file():
            ini.read(path)
        break
    if env.get("GF_DATABASE_TYPE", ini.get("database", "type", fallback="sqlite3")) != "sqlite3":
        raise RuntimeError("External Grafana databases require a separate backup design")
    if env.get("GF_DATABASE_URL", ini.get("database", "url", fallback="")):
        raise RuntimeError("Database URLs require a separate backup design")
    if env.get("GF_PATHS_DATA", "/var/lib/grafana") != "/var/lib/grafana":
        raise RuntimeError("Custom Grafana data paths require a separate backup design")
    if env.get("GF_DATABASE_PATH", ini.get("database", "path", fallback="grafana.db")) not in (
            "grafana.db", "/var/lib/grafana/grafana.db"):
        raise RuntimeError("Custom SQLite paths require a separate backup design")
    return item, mounts


def capture(container, project, output):
    item, mounts = inspect_source(container, project)
    target = Path(output)
    if target.exists():
        raise RuntimeError("Never overwrite a recovery context")
    volume = next(m for m in item["Mounts"]
                  if m["Type"] == "volume" and m["Destination"] == "/var/lib/grafana")
    # Called after the clean stop, while the data tar is captured.
    if item["State"]["Running"]:
        raise RuntimeError("Capture requires the original Grafana to be stopped")
    runtime = {"format": 1, "image": item["Image"], "env": item["Config"]["Env"],
               "mounts": [], "database_counts": database(Path(volume["Source"]) / "grafana.db")}
    records = {}
    with tarfile.open(target, "x:gz") as archive:
        for index, mount in enumerate(mounts):
            source = Path(mount["Source"])
            name = "mounts/m" + str(index)
            runtime["mounts"].append({"path": name, "destination": mount["Destination"]})
            archive.add(source, arcname=name, recursive=True)
            entries = [source, *source.rglob("*")] if source.is_dir() else [source]
            for entry in entries:
                if entry.is_file():
                    key = name if entry == source else name + "/" + entry.relative_to(source).as_posix()
                    records[key] = {"bytes": entry.stat().st_size, "sha256": digest(entry)}
        data = json.dumps(runtime).encode()
        records["runtime.private.json"] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        for name, data in [("runtime.private.json", data), ("manifest.json", json.dumps(records).encode())]:
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o600
            archive.addfile(member, io.BytesIO(data))
    os.chmod(target, 0o600)


def unpack(archive_path, workspace):
    workspace = Path(workspace)
    if workspace.is_symlink() or not workspace.is_dir() or workspace.stat().st_mode & 0o077:
        raise RuntimeError("A private existing workspace is required")
    destination = workspace / "context"
    if destination.exists():
        raise RuntimeError("Never reuse extracted context")
    with tarfile.open(archive_path, "r:gz") as archive:
        members = archive.getmembers()
        names = [m.name for m in members]
        if len(names) != len(set(names)) or sum(m.size for m in members) > 1024 ** 3:
            raise RuntimeError("Duplicate or oversized context")
        for member in members:
            p = PurePosixPath(member.name)
            if p.is_absolute() or ".." in p.parts or not (member.isfile() or member.isdir()):
                raise RuntimeError("Unsafe context member")
        records = json.load(archive.extractfile("manifest.json"))
        if set(records) != {m.name for m in members if m.isfile()} - {"manifest.json"}:
            raise RuntimeError("Incomplete context manifest")
        # Verify before extracting anything.
        for member in members:
            if member.isfile() and member.name != "manifest.json":
                with archive.extractfile(member) as stream:
                    h = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        h.update(chunk)
                if records[member.name] != {"bytes": member.size, "sha256": h.hexdigest()}:
                    raise RuntimeError("Context hash mismatch")
        destination.mkdir(mode=0o700)
        for member in sorted(members, key=lambda m: (not m.isdir(), len(PurePosixPath(m.name).parts))):
            p = destination / member.name
            p.parent.mkdir(parents=True, exist_ok=True)
            if member.isdir():
                p.mkdir(exist_ok=True)
            else:
                with archive.extractfile(member) as source, p.open("xb") as target:
                    shutil.copyfileobj(source, target)
            os.chmod(p, member.mode & 0o777)
            os.chown(p, member.uid, member.gid)
    return json.loads((destination / "runtime.private.json").read_text())


def start(args):
    runtime = unpack(args.archive, args.workspace)
    if not re.fullmatch(r"grafana-restore-check-[0-9]+-[0-9]+", args.name):
        raise RuntimeError("Refuse a non-disposable container name")
    if args.volume != args.name:
        raise RuntimeError("Refuse a non-disposable Grafana volume")
    if subprocess.run(["docker", "container", "inspect", args.name], capture_output=True).returncode == 0:
        raise RuntimeError("Disposable container already exists")
    docker("image", "inspect", runtime["image"])  # No implicit pull or image substitution.
    workspace = Path(args.workspace)
    env = [v for v in runtime["env"] if not v.startswith(
        ("GF_ANALYTICS_REPORTING_ENABLED=", "GF_ANALYTICS_CHECK_FOR_UPDATES=",
         "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES="))]
    env += ["GF_ANALYTICS_REPORTING_ENABLED=false", "GF_ANALYTICS_CHECK_FOR_UPDATES=false",
            "GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES=false"]
    envfile = workspace / "runtime.env.private"
    envfile.write_text("\n".join(env) + "\n")
    os.chmod(envfile, 0o600)
    command = ["run", "--detach", "--network", "none", "--pull=never", "--name", args.name,
               "--volume", args.volume + ":/var/lib/grafana", "--env-file", str(envfile)]
    for mount in runtime["mounts"]:
        source = workspace / "context" / mount["path"]
        if not source.resolve().is_relative_to((workspace / "context/mounts").resolve()):
            raise RuntimeError("Unsafe recovered bind")
        target = mount["destination"]
        if not target.startswith("/") or ".." in PurePosixPath(target).parts or target == "/":
            raise RuntimeError("Unsafe recovered destination")
        command += ["--volume", str(source) + ":" + target + ":ro,Z"]
    command.append(runtime["image"])
    docker(*command)


def validate(args):
    runtime = json.loads((Path(args.workspace) / "context/runtime.private.json").read_text())
    item = json.loads(docker("container", "inspect", args.name))[0]
    if item["HostConfig"]["NetworkMode"] != "none" or item["HostConfig"].get("PortBindings"):
        raise RuntimeError("Recovery container is not isolated")
    if item["Image"] != runtime["image"]:
        raise RuntimeError("Recovery image differs")
    mount = next(m for m in item["Mounts"] if m["Destination"] == "/var/lib/grafana")
    if mount.get("Name") != args.volume:
        raise RuntimeError("Unexpected recovery data volume")
    if database(Path(mount["Source"]) / "grafana.db") != runtime["database_counts"]:
        raise RuntimeError("Recovered Grafana catalog differs")
    print("Grafana context, SQLite and catalog counts verified")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["preflight", "capture", "start", "validate"])
    for name in ("container", "project", "output", "archive", "workspace", "volume", "name"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    if args.action == "preflight":
        inspect_source(args.container, args.project)
    elif args.action == "capture":
        capture(args.container, args.project, args.output)
    elif args.action == "start":
        start(args)
    else:
        validate(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Avoid leaking environment values, SQL or secret file contents.
        raise SystemExit("Grafana recovery context refused: " + type(error).__name__)
