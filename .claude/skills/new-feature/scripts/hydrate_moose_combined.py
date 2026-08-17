#!/usr/bin/env python3
"""Stamp, verify, and hydrate a MOOSE combined opt build into a new worktree."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


SCHEMA = 1
MANIFEST_REL = Path("framework/build/hydration/combined-opt-v1.json")
STATE_REL = Path("framework/build/hydration/state-v1.json")
PROFILE = {
    "METHOD": "opt",
    "MOOSE_UNITY": "true",
    "MOOSE_HEADER_SYMLINKS": "true",
}
GENERATED_HEADERS = (
    Path("framework/include/base/MooseConfig.h"),
    Path("framework/include/base/MooseRevision.h"),
    Path("modules/combined/include/base/CombinedRevision.h"),
)
# Absolute __FILE__ strings are common in MOOSE objects. These sources are the
# known cases that turn their source location into a runtime data/resource root.
FORCED_LOCAL_SOURCES = (
    Path("framework/src/base/Moose.C"),
    Path("framework/src/utils/ADFParser.C"),
    Path("modules/solid_mechanics/src/base/SolidMechanicsApp.C"),
)
ENV_PREFIX_RE = re.compile(rb"(/[^\x00\s\\]+?/envs/[^/\x00\s\\:]+)")
UNITY_SOURCE_RE = re.compile(rb"(/[^\x00\s\\]+/build/unity_src/[^\x00\s\\]+\.C)")
BUILD_ACTION_RE = re.compile(
    r"Compiling|Linking|Building and linking|Creating Unity|Rebuilding symlinks"
)
PACKAGE_PREFIXES = (
    "moose-",
    "mpich",
    "clang",
    "compiler-rt",
    "libcxx",
    "llvm-openmp",
    "cctools",
    "ld64",
    "tapi",
    "sdkroot_env",
)
BUILD_ENV_KEYS = (
    "CC",
    "CXX",
    "CFLAGS",
    "CPPFLAGS",
    "CXXFLAGS",
    "LDFLAGS",
    "LIBMESH_DIR",
    "PETSC_DIR",
    "WASP_DIR",
    "SDKROOT",
    "CONDA_BUILD_SYSROOT",
)
_ENV_CACHE: dict[Path, dict[str, str]] = {}


class Incompatible(RuntimeError):
    """The donor or target is unsafe to hydrate."""


class HydrationError(RuntimeError):
    """Hydration began but did not complete."""


def log(message: str) -> None:
    print(f"[moose-hydrate] {message}", flush=True)


def require_supported_host() -> None:
    if platform.system() != "Darwin":
        raise Incompatible("combined hydration is currently supported only on macOS")


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode:
        detail = ""
        if capture:
            detail = "\n" + (result.stderr or result.stdout or "").strip()
        raise HydrationError(f"command failed ({result.returncode}): {' '.join(command)}{detail}")
    return result


def output(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    return run(command, cwd=cwd, env=env, capture=True).stdout.strip()


def canonical_repo(path: str | Path, label: str) -> Path:
    root = Path(path).expanduser().resolve(strict=True)
    top = Path(output(["git", "-C", str(root), "rev-parse", "--show-toplevel"])).resolve()
    if top != root:
        raise Incompatible(f"{label} must be a MOOSE worktree root: {root}")
    return root


def git_sha(root: Path) -> str:
    return output(["git", "-C", str(root), "rev-parse", "HEAD"])


def require_tracked_clean(root: Path, label: str) -> None:
    status = output(["git", "-C", str(root), "status", "--porcelain=v1", "--untracked-files=all"])
    if status:
        raise Incompatible(f"{label} source worktree is not clean; hydrate before feature edits")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def env_for(prefix: Path) -> dict[str, str]:
    prefix = prefix.resolve()
    if prefix not in _ENV_CACHE:
        script = "import json, os; print(json.dumps(dict(os.environ), sort_keys=True))"
        result = subprocess.run(
            [conda_executable(), "run", "-p", str(prefix), "python", "-c", script],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            raise HydrationError(
                f"could not activate conda environment {prefix}: {result.stderr.strip()}"
            )
        try:
            activated = json.loads(result.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as error:
            raise HydrationError(f"could not parse activated environment for {prefix}") from error
        activated["PATH"] = f"{prefix / 'bin'}{os.pathsep}{activated.get('PATH', '')}"
        _ENV_CACHE[prefix] = activated
    return _ENV_CACHE[prefix].copy()


def conda_executable() -> str:
    candidate = os.environ.get("CONDA_EXE") or shutil.which("conda")
    if not candidate:
        raise HydrationError("conda is not available")
    return candidate


def package_snapshot(prefix: Path) -> list[list[object]]:
    records: list[list[object]] = []
    for metadata in sorted((prefix / "conda-meta").glob("*.json")):
        data = json.loads(metadata.read_text())
        name = data.get("name", "")
        if name.startswith(PACKAGE_PREFIXES):
            records.append(
                [
                    name,
                    data.get("version"),
                    data.get("build") or data.get("build_string"),
                    data.get("build_number"),
                    data.get("subdir") or data.get("platform"),
                ]
            )
    return sorted(records)


def normalize(text: str, root: Path, prefix: Path) -> str:
    replacements = sorted(
        ((str(prefix), "@CONDA@"), (str(root), "@MOOSE@")),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text.strip()


def compiler_snapshot(prefix: Path, root: Path) -> dict[str, str]:
    env = env_for(prefix)
    mpicxx = prefix / "bin/mpicxx"
    if not mpicxx.is_file():
        raise Incompatible(f"missing compiler wrapper: {mpicxx}")
    version = output([str(mpicxx), "--version"], env=env)
    show = output([str(mpicxx), "-show"], env=env)
    libmesh = prefix / "bin/libmesh-config"
    host = output([str(libmesh), "--host"], env=env) if libmesh.is_file() else ""
    return {
        "mpicxx_version": normalize(version, root, prefix),
        "mpicxx_show": normalize(show, root, prefix),
        "libmesh_host": normalize(host, root, prefix),
        "build_env": {
            key: normalize(env[key], root, prefix) for key in BUILD_ENV_KEYS if env.get(key)
        },
        "machine": platform.machine(),
        "system": platform.system(),
    }


def make_command(*, jobs: int, dry_run: bool = False) -> list[str]:
    command = ["make"]
    if dry_run:
        command.append("-n")
    command.extend(["-j", str(jobs)])
    command.extend(f"{key}={value}" for key, value in PROFILE.items())
    return command


def require_settled_build(root: Path, prefix: Path, jobs: int) -> None:
    dry = output(
        make_command(jobs=jobs, dry_run=True),
        cwd=root / "modules/combined",
        env=env_for(prefix),
    )
    unexpected: list[str] = []
    for line in dry.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("if [ x"):
            continue
        if "scripts/premake.py" in stripped and stripped.startswith(("python", str(prefix))):
            continue
        if stripped.startswith("ln -sf ") and (
            "Revision.h" in stripped or "/build/header_symlinks/" in stripped
        ):
            continue
        unexpected.append(stripped)
    if unexpected:
        actions = [line for line in unexpected if BUILD_ACTION_RE.search(line)]
        preview = "\n  ".join((actions or unexpected)[:8])
        raise Incompatible(
            f"donor combined build is not settled; {len(actions)} compile/link actions remain:\n"
            f"  {preview}"
        )


def eligible_lo(relative: str) -> bool:
    if relative.startswith("modules/module_loader/"):
        return False
    if re.match(r"modules/[^/]+/src/main\..*\.lo$", relative):
        return relative.startswith("modules/combined/src/main.")
    if relative.endswith(".opt.lo"):
        return True
    return relative.startswith("framework/contrib/gtest/") and relative.endswith(".lo")


def env_prefixes(paths: list[Path]) -> set[str]:
    found: set[str] = set()
    for path in paths:
        data = path.read_bytes()
        found.update(match.decode(errors="replace") for match in ENV_PREFIX_RE.findall(data))
    return found


def discover_donor_env(dependencies: list[Path]) -> Path:
    matches = sorted(env_prefixes(dependencies))
    if len(matches) != 1:
        shown = ", ".join(matches) or "none"
        raise Incompatible(f"expected one donor conda prefix in dependency files; found: {shown}")
    prefix = Path(matches[0]).resolve()
    if not (prefix / "conda-meta").is_dir():
        raise Incompatible(f"dependency metadata references a missing conda environment: {prefix}")
    return prefix


def parse_pic_object(lo: Path) -> Path:
    match = re.search(r"^pic_object='([^']+)'", lo.read_text(errors="replace"), re.MULTILINE)
    if not match:
        raise Incompatible(f"missing pic_object in {lo}")
    obj = (lo.parent / match.group(1)).resolve()
    expected_parent = (lo.parent / ".libs").resolve()
    if obj.parent != expected_parent:
        raise Incompatible(f"unexpected PIC object path in {lo}: {obj}")
    return obj


def find_header_symlinks(root: Path) -> list[Path]:
    links: list[Path] = []
    for search_root in (root / "framework", root / "modules"):
        for header_root in search_root.rglob("header_symlinks"):
            if not header_root.is_dir() or header_root.parent.name != "build":
                continue
            if "modules/module_loader" in header_root.relative_to(root).as_posix():
                continue
            for directory, subdirs, files in os.walk(header_root, followlinks=False):
                names = list(files)
                for name in list(subdirs):
                    candidate = Path(directory) / name
                    if candidate.is_symlink():
                        names.append(name)
                        subdirs.remove(name)
                for name in names:
                    candidate = Path(directory) / name
                    if candidate.is_symlink():
                        links.append(candidate)
    return sorted(set(links))


def build_inventory(root: Path) -> dict[str, object]:
    candidates: list[tuple[Path, Path, Path, bytes]] = []
    for search_root in (root / "framework", root / "modules"):
        for lo in search_root.rglob("*.lo"):
            relative = lo.relative_to(root).as_posix()
            if not eligible_lo(relative):
                continue
            dep = Path(f"{lo}.d")
            obj = parse_pic_object(lo)
            if not dep.is_file() or not obj.is_file():
                raise Incompatible(f"incomplete object triplet for {relative}")
            candidates.append((lo, dep, obj, dep.read_bytes()))
    if not candidates:
        raise Incompatible("no reusable combined opt object triplets found")

    forced_absolute = {source: str(root / source).encode() for source in FORCED_LOCAL_SOURCES}
    forced_seen: set[Path] = set()
    reusable: list[dict[str, str]] = []
    excluded: list[dict[str, object]] = []
    unity_sources: set[Path] = set()
    dependencies = [dep for _, dep, _, _ in candidates]
    donor_env = discover_donor_env(dependencies)
    all_binary_prefixes: set[str] = set()

    for lo, dep, obj, dep_data in sorted(candidates):
        sources = [source for source, absolute in forced_absolute.items() if absolute in dep_data]
        forced_seen.update(sources)
        object_prefixes = env_prefixes([obj])
        all_binary_prefixes.update(object_prefixes)
        foreign_prefixes = sorted(
            value for value in object_prefixes if Path(value).resolve() != donor_env
        )
        unity_sources.update(
            Path(value.decode(errors="strict")) for value in UNITY_SOURCE_RE.findall(dep_data)
        )
        triplet = {
            "lo": lo.relative_to(root).as_posix(),
            "dep": dep.relative_to(root).as_posix(),
            "object": obj.relative_to(root).as_posix(),
        }
        reasons = [source.as_posix() for source in sources]
        reasons.extend(f"foreign-conda:{value}" for value in foreign_prefixes)
        if reasons:
            excluded.append({**triplet, "reason": reasons})
        else:
            reusable.append(triplet)

    missing_forced = set(FORCED_LOCAL_SOURCES) - forced_seen
    if missing_forced:
        missing = ", ".join(path.as_posix() for path in sorted(missing_forced))
        raise Incompatible(f"could not locate path-sensitive unity objects for: {missing}")

    for path in unity_sources:
        try:
            path.relative_to(root)
        except ValueError as error:
            raise Incompatible(f"unity source escapes donor root: {path}") from error
        if not path.is_file():
            raise Incompatible(f"missing generated unity source: {path}")

    for header in GENERATED_HEADERS:
        if not (root / header).is_file():
            raise Incompatible(f"missing generated header: {header}")

    binary_prefixes = sorted(all_binary_prefixes)

    copied_paths: set[Path] = set(GENERATED_HEADERS)
    copied_paths.update(path.relative_to(root) for path in unity_sources)
    for triplet in reusable:
        copied_paths.update(Path(triplet[key]) for key in ("lo", "dep", "object"))

    file_records = []
    for relative in sorted(copied_paths):
        path = root / relative
        file_records.append(
            {"path": relative.as_posix(), "size": path.stat().st_size, "sha256": sha256_file(path)}
        )

    symlink_records = [
        {"path": link.relative_to(root).as_posix(), "target": os.readlink(link)}
        for link in find_header_symlinks(root)
    ]

    library_dirs = sorted(
        {
            library.parent.relative_to(root).as_posix()
            for search_root in (root / "framework", root / "modules")
            for library in search_root.rglob("*.la")
            if not library.relative_to(root).as_posix().startswith("modules/module_loader/")
        }
    )

    return {
        "donor_env": str(donor_env),
        "reusable": reusable,
        "forced_local": excluded,
        "files": file_records,
        "header_symlinks": symlink_records,
        "library_dirs": library_dirs,
        "candidate_count": len(candidates),
        "binary_prefixes": binary_prefixes,
    }


def explicit_lock(prefix: Path) -> list[str]:
    text = output([conda_executable(), "list", "-p", str(prefix), "--explicit"])
    return [
        line
        for line in text.splitlines()
        if line and not line.startswith("#") and line != "@EXPLICIT"
    ]


def manifest_path(root: Path) -> Path:
    return root / MANIFEST_REL


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def stamp(args: argparse.Namespace) -> None:
    donor = canonical_repo(args.donor, "donor")
    require_supported_host()
    require_tracked_clean(donor, "donor")
    inventory = build_inventory(donor)
    prefix = Path(str(inventory.pop("donor_env"))).resolve()
    require_settled_build(donor, prefix, args.jobs)
    versioner = donor / "scripts/versioner.yaml"
    manifest = {
        "schema": SCHEMA,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "donor_root": str(donor),
        "git_sha": git_sha(donor),
        "versioner_sha256": sha256_file(versioner),
        "profile": PROFILE,
        "environment": {
            "prefix": str(prefix),
            "packages": package_snapshot(prefix),
            "compiler": compiler_snapshot(prefix, donor),
            "explicit_lock": explicit_lock(prefix),
        },
        "inventory": inventory,
    }
    manifest["artifact_digest"] = canonical_json_digest(manifest["inventory"])
    write_json_atomic(manifest_path(donor), manifest)
    log(
        f"stamped {len(inventory['reusable'])} reusable objects; "
        f"{len(inventory['forced_local'])} forced local"
    )
    log(f"manifest: {manifest_path(donor)}")


def load_manifest(donor: Path) -> dict[str, object]:
    path = manifest_path(donor)
    if not path.is_file():
        raise Incompatible(
            f"missing stamped donor manifest: {path}; build a clean combined opt seed, then run stamp"
        )
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise Incompatible("donor hydration manifest must be a JSON object")
    if type(data.get("schema")) is not int or data.get("schema") != SCHEMA:
        raise Incompatible("unsupported donor hydration manifest schema/profile")
    if type(data.get("profile")) is not dict or data.get("profile") != PROFILE:
        raise Incompatible("unsupported donor hydration manifest schema/profile")

    required_strings = (
        "created_at",
        "donor_root",
        "git_sha",
        "versioner_sha256",
        "artifact_digest",
    )
    missing = [key for key in required_strings if type(data.get(key)) is not str]
    if missing:
        raise Incompatible(f"donor hydration manifest has invalid fields: {', '.join(missing)}")

    environment = data.get("environment")
    inventory = data.get("inventory")
    if not isinstance(environment, dict) or not isinstance(inventory, dict):
        raise Incompatible("donor hydration manifest is missing environment/inventory data")
    environment_types = {
        "prefix": str,
        "packages": list,
        "compiler": dict,
        "explicit_lock": list,
    }
    invalid_environment = [
        key for key, expected in environment_types.items() if type(environment.get(key)) is not expected
    ]
    if invalid_environment or not all(
        type(record) is str for record in environment.get("explicit_lock", [])
    ):
        shown = ", ".join(invalid_environment) or "explicit_lock"
        raise Incompatible(f"donor hydration manifest has invalid environment fields: {shown}")
    compiler = environment["compiler"]
    compiler_strings = ("mpicxx_version", "mpicxx_show", "libmesh_host", "machine", "system")
    if any(type(compiler.get(key)) is not str for key in compiler_strings) or type(
        compiler.get("build_env")
    ) is not dict:
        raise Incompatible("donor hydration manifest has invalid compiler fields")
    if not all(type(key) is str and type(value) is str for key, value in compiler["build_env"].items()):
        raise Incompatible("donor hydration manifest has invalid compiler build_env fields")
    if not all(type(record) is list and len(record) == 5 for record in environment["packages"]):
        raise Incompatible("donor hydration manifest has invalid package records")

    inventory_types = {
        "reusable": list,
        "forced_local": list,
        "files": list,
        "header_symlinks": list,
        "library_dirs": list,
        "candidate_count": int,
        "binary_prefixes": list,
    }
    invalid_inventory = [
        key for key, expected in inventory_types.items() if type(inventory.get(key)) is not expected
    ]
    if invalid_inventory:
        raise Incompatible(
            f"donor hydration manifest has invalid inventory fields: {', '.join(invalid_inventory)}"
        )
    if inventory["candidate_count"] < 1:
        raise Incompatible("donor hydration manifest has an invalid candidate count")

    def string_fields(record: object, keys: tuple[str, ...]) -> bool:
        return type(record) is dict and all(type(record.get(key)) is str for key in keys)

    if not all(string_fields(record, ("lo", "dep", "object")) for record in inventory["reusable"]):
        raise Incompatible("donor hydration manifest has invalid reusable-object records")
    if not all(
        string_fields(record, ("lo", "dep", "object"))
        and type(record.get("reason")) is list
        and all(type(reason) is str for reason in record["reason"])
        for record in inventory["forced_local"]
    ):
        raise Incompatible("donor hydration manifest has invalid forced-local records")
    if not all(
        string_fields(record, ("path", "sha256"))
        and type(record.get("size")) is int
        and record["size"] >= 0
        and re.fullmatch(r"[0-9a-f]{64}", record["sha256"])
        for record in inventory["files"]
    ):
        raise Incompatible("donor hydration manifest has invalid file records")
    if not all(
        string_fields(record, ("path", "target")) for record in inventory["header_symlinks"]
    ):
        raise Incompatible("donor hydration manifest has invalid header-symlink records")
    if not all(type(value) is str for value in inventory["library_dirs"]):
        raise Incompatible("donor hydration manifest has invalid library-directory records")
    if not all(type(value) is str for value in inventory["binary_prefixes"]):
        raise Incompatible("donor hydration manifest has invalid binary-prefix records")
    return data


def require_environment_match(
    prefix: Path, root: Path, manifest: dict[str, object], label: str
) -> None:
    environment = manifest["environment"]
    if not (prefix / "conda-meta").is_dir():
        raise Incompatible(f"{label} conda environment is missing: {prefix}")
    if package_snapshot(prefix) != environment["packages"]:
        raise Incompatible(f"{label} build-package fingerprint differs from donor stamp")
    if explicit_lock(prefix) != environment["explicit_lock"]:
        raise Incompatible(f"{label} exact conda package lock differs from donor stamp")
    if compiler_snapshot(prefix, root) != environment["compiler"]:
        raise Incompatible(f"{label} compiler fingerprint differs from donor stamp")


def verify_manifest(donor: Path, manifest: dict[str, object], jobs: int) -> None:
    require_tracked_clean(donor, "donor")
    if manifest.get("donor_root") != str(donor):
        raise Incompatible("donor moved since it was stamped")
    if manifest.get("git_sha") != git_sha(donor):
        raise Incompatible("donor HEAD changed since it was stamped")
    if manifest.get("versioner_sha256") != sha256_file(donor / "scripts/versioner.yaml"):
        raise Incompatible("donor versioner.yaml changed since it was stamped")

    environment = manifest["environment"]
    prefix = Path(environment["prefix"]).resolve()
    require_environment_match(prefix, donor, manifest, "donor")

    if manifest.get("artifact_digest") != canonical_json_digest(manifest["inventory"]):
        raise Incompatible("donor manifest inventory does not match its recorded digest")
    current_inventory = build_inventory(donor)
    current_inventory.pop("donor_env", None)
    if manifest.get("artifact_digest") != canonical_json_digest(current_inventory):
        raise Incompatible("donor artifact inventory changed since stamp")
    require_settled_build(donor, prefix, jobs)


def preflight(args: argparse.Namespace) -> dict[str, object]:
    require_supported_host()
    donor = canonical_repo(args.donor, "donor")
    manifest = load_manifest(donor)
    verify_manifest(donor, manifest, args.jobs)
    lease = canonical_json_digest(manifest)
    expected_lease = getattr(args, "lease", None)
    if expected_lease is not None and expected_lease != lease:
        raise Incompatible(
            f"donor lease changed after initial preflight: expected {expected_lease}, found {lease}"
        )
    inventory = manifest["inventory"]
    log(
        f"preflight passed: sha={manifest['git_sha']} lease={lease} "
        f"reusable={len(inventory['reusable'])} forced_local={len(inventory['forced_local'])}"
    )
    return manifest


def resolve_named_env(name: str) -> Path:
    result = output(
        [conda_executable(), "run", "-n", name, "python", "-c", "import sys; print(sys.prefix)"]
    )
    return Path(result.splitlines()[-1]).resolve()


def create_env(args: argparse.Namespace) -> None:
    manifest = preflight(args)
    target = canonical_repo(args.target, "target")
    if git_sha(target) != manifest["git_sha"]:
        raise Incompatible("target MOOSE SHA does not match the stamped donor")
    require_tracked_clean(target, "target")
    lock = manifest["environment"]["explicit_lock"]
    descriptor, lock_path = tempfile.mkstemp(prefix="moose-hydration-", suffix=".txt")
    try:
        with os.fdopen(descriptor, "w") as handle:
            handle.write("@EXPLICIT\n")
            handle.write("\n".join(lock))
            handle.write("\n")
        run([conda_executable(), "create", "-n", args.name, "--file", lock_path, "-y"])
    finally:
        if os.path.exists(lock_path):
            os.unlink(lock_path)
    prefix = resolve_named_env(args.name)
    require_environment_match(prefix, target, manifest, "fresh target")
    log(f"created fresh locked environment {args.name}: {prefix}")


def target_is_pristine(target: Path) -> bool:
    if (target / STATE_REL).exists() or (target / "modules/combined/combined-opt").exists():
        return False
    if (target / "framework/include/base/MooseConfig.h").exists():
        return False
    for search_root in (target / "framework", target / "modules"):
        for pattern in ("*.lo", "*.lo.d", "*.la", "*.dylib"):
            if next(search_root.rglob(pattern), None) is not None:
                return False
        if any(path.is_file() for path in search_root.rglob(".libs/*.o")):
            return False
        if any(path.is_file() or path.is_symlink() for path in search_root.rglob("build/header_symlinks/*")):
            return False
    return True


def clone_groups(pairs: list[tuple[Path, Path]]) -> None:
    groups: dict[tuple[Path, Path], list[Path]] = collections.defaultdict(list)
    for source, destination in pairs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        groups[(source.parent, destination.parent)].append(source)
    fallback = False
    for (_, destination_parent), sources in sorted(groups.items(), key=lambda item: str(item[0])):
        command = ["/bin/cp", "-c", *(str(path) for path in sorted(sources)), str(destination_parent)]
        result = subprocess.run(command, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode:
            fallback = True
            run(["/bin/cp", *(str(path) for path in sorted(sources)), str(destination_parent)])
    if fallback:
        log("APFS clone unavailable for some files; used physical copies")


def rebase(raw: str, donor: Path, target: Path, donor_env: Path, target_env: Path) -> str:
    replacements = sorted(
        ((str(donor), str(target)), (str(donor_env), str(target_env))),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for old, new in replacements:
        if raw == old or raw.startswith(f"{old}/"):
            return f"{new}{raw[len(old):]}"
    return raw


def has_forbidden_reference(
    data: bytes | str, *, forbidden: tuple[Path, ...], allowed: tuple[Path, ...]
) -> bool:
    payload = data.encode() if isinstance(data, str) else data
    for path in sorted(allowed, key=lambda value: len(str(value)), reverse=True):
        payload = payload.replace(str(path).encode(), b"@HYDRATED_PATH@")
    return any(str(path).encode() in payload for path in forbidden)


def stage_artifacts(
    donor: Path, target: Path, target_env: Path, manifest: dict[str, object], stage: Path
) -> tuple[list[Path], list[Path]]:
    inventory = manifest["inventory"]
    donor_env = Path(manifest["environment"]["prefix"]).resolve()
    file_relatives = [Path(record["path"]) for record in inventory["files"]]
    pairs = [(donor / relative, stage / relative) for relative in file_relatives]
    clone_groups(pairs)

    for record in inventory["files"]:
        staged = stage / record["path"]
        if staged.stat().st_size != record["size"] or sha256_file(staged) != record["sha256"]:
            raise HydrationError(f"staged artifact differs from donor manifest: {record['path']}")

    text_paths: list[Path] = []
    replacements = sorted(
        (
            (str(donor).encode(), str(target).encode()),
            (str(donor_env).encode(), str(target_env).encode()),
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for relative in file_relatives:
        staged = stage / relative
        if staged.suffix == ".o":
            continue
        data = staged.read_bytes()
        for old, new in replacements:
            data = data.replace(old, new)
        staged.write_bytes(data)
        text_paths.append(staged)

    symlink_paths: list[Path] = []
    for record in inventory["header_symlinks"]:
        relative = Path(record["path"])
        staged = stage / relative
        staged.parent.mkdir(parents=True, exist_ok=True)
        mapped = rebase(record["target"], donor, target, donor_env, target_env)
        staged.symlink_to(mapped)
        symlink_paths.append(staged)

    forbidden = (donor,) if donor_env == target_env else (donor, donor_env)
    allowed = (target, target_env)
    for path in text_paths:
        data = path.read_bytes()
        if has_forbidden_reference(data, forbidden=forbidden, allowed=allowed):
            raise HydrationError(f"donor path remains after staging: {path.relative_to(stage)}")
    for path in symlink_paths:
        raw = os.readlink(path)
        if has_forbidden_reference(raw, forbidden=forbidden, allowed=allowed):
            raise HydrationError(f"donor symlink remains after staging: {path.relative_to(stage)}")

    generated = [
        stage / Path(record["path"])
        for record in inventory["files"]
        if "/unity_src/" in record["path"] and record["path"].endswith(".C")
    ]
    generated.extend(stage / path for path in GENERATED_HEADERS)
    generated_time = time.time_ns()
    for path in generated:
        os.utime(path, ns=(generated_time, generated_time))
    output_time = max(time.time_ns(), generated_time + 1_000_000_000)
    reusable_outputs: list[Path] = []
    for triplet in inventory["reusable"]:
        for key in ("lo", "object"):
            path = stage / triplet[key]
            os.utime(path, ns=(output_time, output_time))
            reusable_outputs.append(path)
    return text_paths, symlink_paths


def install_stage(stage: Path, target: Path, manifest: dict[str, object]) -> tuple[list[Path], list[Path]]:
    created_files: list[Path] = []
    created_dirs: list[Path] = []

    def ensure_parent(path: Path) -> None:
        missing: list[Path] = []
        current = path
        while not current.exists() and current != target:
            missing.append(current)
            current = current.parent
        for directory in reversed(missing):
            directory.mkdir()
            created_dirs.append(directory)

    try:
        staged_paths = sorted(
            (path for path in stage.rglob("*") if path.is_file() or path.is_symlink()),
            key=lambda path: path.as_posix(),
        )
        for source in staged_paths:
            relative = source.relative_to(stage)
            destination = target / relative
            if os.path.lexists(destination):
                raise HydrationError(f"target path already exists: {relative}")
            ensure_parent(destination.parent)
            os.replace(source, destination)
            created_files.append(destination)
        for relative in manifest["inventory"]["library_dirs"]:
            for directory in (target / relative, target / relative / ".libs"):
                if not directory.exists():
                    ensure_parent(directory.parent)
                    directory.mkdir()
                    created_dirs.append(directory)
    except Exception:
        for path in reversed(created_files):
            if os.path.lexists(path):
                path.unlink()
        for path in reversed(created_dirs):
            try:
                path.rmdir()
            except OSError:
                pass
        raise
    return created_files, created_dirs


def write_state(target: Path, value: dict[str, object]) -> None:
    write_json_atomic(target / STATE_REL, value)


def load_state(target: Path) -> dict[str, object]:
    path = target / STATE_REL
    if not path.is_file():
        raise Incompatible(f"target has no hydration receipt: {path}")
    state = json.loads(path.read_text())
    required = {
        "schema": int,
        "status": str,
        "donor_root": str,
        "donor_sha": str,
        "donor_manifest_digest": str,
        "target_env": str,
        "created_files": list,
        "created_dirs": list,
    }
    if not isinstance(state, dict):
        raise Incompatible("target hydration receipt must be a JSON object")
    invalid = [key for key, expected in required.items() if type(state.get(key)) is not expected]
    if invalid or state.get("schema") != SCHEMA:
        shown = ", ".join(invalid) or "schema"
        raise Incompatible(f"target hydration receipt has invalid fields: {shown}")
    if not all(type(value) is str for value in state["created_files"] + state["created_dirs"]):
        raise Incompatible("target hydration receipt has invalid created-path records")
    return state


def scan_text_paths(target: Path, donor: Path, donor_env: Path, target_env: Path) -> int:
    candidates: set[Path] = set()
    for search_root in (target / "framework", target / "modules"):
        for pattern in ("*.lo", "*.lo.d", "*.la", "*.lai"):
            candidates.update(search_root.rglob(pattern))
        candidates.update(
            path for path in search_root.rglob("*.C") if "/build/unity_src/" in path.as_posix()
        )
    candidates.update(target / path for path in GENERATED_HEADERS)
    forbidden = (donor,) if donor_env == target_env else (donor, donor_env)
    allowed = (target, target_env)
    checked = 0
    for path in sorted(candidates):
        if not path.is_file():
            continue
        checked += 1
        data = path.read_bytes()
        if has_forbidden_reference(data, forbidden=forbidden, allowed=allowed):
            raise HydrationError(f"target text metadata still references donor: {path}")
    for link in find_header_symlinks(target):
        raw = os.readlink(link)
        if has_forbidden_reference(raw, forbidden=forbidden, allowed=allowed):
            raise HydrationError(f"target header symlink still references donor: {link}")
    return checked


def scan_macho_paths(target: Path, donor: Path, donor_env: Path, target_env: Path) -> int:
    candidates = set(target.rglob("*.dylib")) | set(target.rglob("*.so"))
    candidates.update(
        path for path in target.rglob("*") if path.is_file() and os.access(path, os.X_OK)
    )
    combined = target / "modules/combined/combined-opt"
    candidates.add(combined)
    count = 0
    for path in sorted(candidates):
        if not path.is_file():
            continue
        description = output(["file", "-b", str(path)])
        if "Mach-O" not in description:
            continue
        count += 1
        loads = output(["otool", "-L", str(path)]) + "\n" + output(["otool", "-l", str(path)])
        forbidden = (donor,) if donor_env == target_env else (donor, donor_env)
        if has_forbidden_reference(
            loads, forbidden=forbidden, allowed=(target, target_env)
        ):
            raise HydrationError(f"Mach-O load path still references donor: {path}")
    return count


def require_canary_summary(test_output: str) -> None:
    summaries = re.findall(
        r"(?m)^(\d+) passed, (\d+) skipped, (\d+) failed\s*$", test_output
    )
    if summaries != [("2", "0", "0")]:
        tail = "\n".join(test_output.strip().splitlines()[-12:])
        raise HydrationError(f"combined canaries did not report exactly 2 passes:\n{tail}")


def post_validate(
    donor: Path,
    target: Path,
    target_env: Path,
    manifest: dict[str, object],
    jobs: int,
) -> dict[str, object]:
    donor_env = Path(manifest["environment"]["prefix"]).resolve()
    combined = target / "modules/combined/combined-opt"
    if not os.access(combined, os.X_OK):
        raise HydrationError("target combined-opt was not produced")

    second = output(
        make_command(jobs=jobs), cwd=target / "modules/combined", env=env_for(target_env)
    )
    if BUILD_ACTION_RE.search(second):
        raise HydrationError("second target make was not compile/link clean")

    text_count = scan_text_paths(target, donor, donor_env, target_env)
    macho_count = scan_macho_paths(target, donor, donor_env, target_env)
    capabilities = output([str(combined), "--show-capabilities"], env=env_for(target_env))
    required_paths = (
        str(target / "framework/data"),
        str(target / "modules/solid_mechanics/data"),
    )
    if any(path not in capabilities for path in required_paths):
        raise HydrationError("combined capabilities do not contain target-local data paths")
    if has_forbidden_reference(
        capabilities, forbidden=(donor, donor_env), allowed=(target, target_env)
    ):
        raise HydrationError("combined capabilities still reference the donor build")

    test_command = [
        "./run_tests",
        "--opt",
        "--no-color",
        "-j",
        "1",
        "-p",
        "1",
        "--re=(crack_loop\\.screen_output_test$|basic_optimize.*fd$)",
    ]
    test_env = env_for(target_env)
    test_env["MOOSE_TERM_FORMAT"] = "ns"
    test_result = run(test_command, cwd=target / "modules", env=test_env, capture=True)
    test_output = f"{test_result.stdout or ''}\n{test_result.stderr or ''}"
    require_canary_summary(test_output)
    require_tracked_clean(target, "target")
    return {
        "text_metadata_files": text_count,
        "macho_files": macho_count,
        "canaries": 2,
        "second_make_actions": 0,
    }


def hydrate(args: argparse.Namespace) -> None:
    started = time.monotonic()
    donor = canonical_repo(args.donor, "donor")
    manifest = preflight(args)
    target = canonical_repo(args.target, "target")
    target_env = Path(sys.prefix).resolve()
    if not (target_env / "conda-meta").is_dir():
        raise Incompatible("run hydrate with the target conda environment's Python")
    if git_sha(target) != manifest["git_sha"]:
        raise Incompatible("target MOOSE SHA does not match the stamped donor")
    require_tracked_clean(target, "target")
    if not target_is_pristine(target):
        raise Incompatible("target already contains MOOSE build artifacts; hydrate immediately after creation")
    require_environment_match(target_env, target, manifest, "target")
    if donor.stat().st_dev != target.stat().st_dev:
        log("donor and target are on different filesystems; physical copy fallback may be slower")

    stage = Path(tempfile.mkdtemp(prefix=".moose-hydration-", dir=target.parent))
    try:
        log("staging and rebasing reusable combined objects")
        stage_artifacts(donor, target, target_env, manifest, stage)
        verify_manifest(donor, manifest, args.jobs)
        created_files, created_dirs = install_stage(stage, target, manifest)
    finally:
        shutil.rmtree(stage, ignore_errors=True)

    state = {
        "schema": SCHEMA,
        "status": "building",
        "donor_root": str(donor),
        "donor_sha": manifest["git_sha"],
        "donor_manifest_digest": canonical_json_digest(manifest),
        "target_env": str(target_env),
        "created_files": [path.relative_to(target).as_posix() for path in created_files],
        "created_dirs": [path.relative_to(target).as_posix() for path in created_dirs],
    }
    write_state(target, state)

    log("recompiling path-sensitive objects and relinking combined-opt locally")
    run(make_command(jobs=args.jobs), cwd=target / "modules/combined", env=env_for(target_env))
    validation = post_validate(donor, target, target_env, manifest, args.jobs)
    state.update(
        {
            "status": "validated",
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "reused_objects": len(manifest["inventory"]["reusable"]),
            "forced_local_objects": len(manifest["inventory"]["forced_local"]),
            "validation": validation,
        }
    )
    write_state(target, state)
    log(
        f"validated in {state['elapsed_seconds']}s: reused={state['reused_objects']} "
        f"forced_local={state['forced_local_objects']} Mach-O={validation['macho_files']}"
    )


def validate(args: argparse.Namespace) -> None:
    donor = canonical_repo(args.donor, "donor")
    manifest = preflight(args)
    target = canonical_repo(args.target, "target")
    target_env = Path(sys.prefix).resolve()
    if git_sha(target) != manifest["git_sha"]:
        raise Incompatible("target MOOSE SHA does not match the stamped donor")
    state = load_state(target)
    expected_state = {
        "donor_root": str(donor),
        "donor_sha": manifest["git_sha"],
        "donor_manifest_digest": canonical_json_digest(manifest),
        "target_env": str(target_env),
    }
    mismatched = [key for key, expected in expected_state.items() if state.get(key) != expected]
    if mismatched or state["status"] not in ("building", "validated"):
        shown = ", ".join(mismatched) or "status"
        raise Incompatible(f"target hydration receipt does not match this build: {shown}")
    require_environment_match(target_env, target, manifest, "target")
    validation = post_validate(donor, target, target_env, manifest, args.jobs)
    state.update({"status": "validated", "validation": validation})
    write_state(target, state)
    log(f"validation passed: {json.dumps(validation, sort_keys=True)}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)

    for name in ("stamp", "preflight"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--donor", required=True)
        subparser.add_argument("--jobs", type=int, default=8)

    create = subparsers.add_parser("create-env")
    create.add_argument("--donor", required=True)
    create.add_argument("--target", required=True)
    create.add_argument("--name", required=True)
    create.add_argument("--lease", required=True)
    create.add_argument("--jobs", type=int, default=8)

    for name in ("hydrate", "validate"):
        subparser = subparsers.add_parser(name)
        subparser.add_argument("--donor", required=True)
        subparser.add_argument("--target", required=True)
        if name == "hydrate":
            subparser.add_argument("--lease", required=True)
        subparser.add_argument("--jobs", type=int, default=8)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "stamp":
            stamp(args)
        elif args.command == "preflight":
            preflight(args)
        elif args.command == "create-env":
            create_env(args)
        elif args.command == "hydrate":
            hydrate(args)
        elif args.command == "validate":
            validate(args)
        else:
            raise AssertionError(args.command)
    except Incompatible as error:
        print(f"[moose-hydrate] INCOMPATIBLE: {error}", file=sys.stderr)
        return 2
    except (HydrationError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"[moose-hydrate] ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
