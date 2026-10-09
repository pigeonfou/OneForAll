"""Immutable CPU dependency pools for DocTrad; application code stays per release."""
import hashlib
import json
import re
import shutil
from pathlib import Path
from common import OPT, as_user, atomic, run, user

def cpu_requirements(text):
    selected = []
    torch = None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"): continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        if not match: raise ValueError("Le verrou DocTrad doit contenir uniquement des versions exactes")
        name = match[1].lower().replace("_", "-")
        if name == "torch": torch = line
        if name.startswith(("nvidia-", "cuda-")) or name == "triton": continue
        selected.append(line)
    if not torch: raise ValueError("Version PyTorch absente du verrou")
    return "\n".join(selected) + "\n", torch

def prepare_doctrad_environment(release, temp):
    requirements, torch = cpu_requirements((release / "requirements.lock").read_text())
    identity = as_user("doctrad", "python3", "-c",
        "import sys,sysconfig,platform; print(sys.version); print(sysconfig.get_config_var('SOABI')); print(platform.machine())", capture=True)
    digest = hashlib.sha256(("doctrad-cpu-v1\n" + identity + "\n" + requirements).encode()).hexdigest()
    pools = OPT / "apps/doctrad/dependencies"
    pools.mkdir(parents=True, exist_ok=True)
    pool = pools / digest
    if not (pool / ".ready").is_file():
        if pool.exists(): shutil.rmtree(pool)
        pool.mkdir()
        run("chown", user("doctrad") + ":" + user("doctrad"), pool)
        as_user("doctrad", "python3", "-m", "venv", pool)
        atomic(pool / "requirements.cpu.lock", requirements, 0o644)
        env = {"TMPDIR": str(temp), "PIP_DISABLE_PIP_VERSION_CHECK": "1"}
        pip = pool / "bin/pip"
        # No CUDA fallback: unavailable CPU wheel fails before switching the active release.
        as_user("doctrad", pip, "install", "--no-deps", "--index-url",
            "https://download.pytorch.org/whl/cpu", torch, env=env)
        as_user("doctrad", pip, "install", "--no-deps", "-r", pool / "requirements.cpu.lock", env=env)
        as_user("doctrad", pip, "install", "wheel", env=env)
        as_user("doctrad", pool / "bin/python", "-m", "pip", "check")
        as_user("doctrad", pool / "bin/python", "-c",
            "import torch; assert torch.version.cuda is None; assert torch.ones(1).item() == 1")
        atomic(pool / ".ready", digest + "\n")
        run("chown", "-R", "root:root", pool)
        run("chmod", "-R", "a-w", pool)
        print("DocTrad : dépendances CPU préparées.")
    else:
        print("DocTrad : dépendances inchangées, environnement réutilisé.")
    as_user("doctrad", "python3", "-m", "venv", release / ".venv")
    query = "import sysconfig; print(sysconfig.get_path('purelib'))"
    shared_site = as_user("doctrad", pool / "bin/python", "-c", query, capture=True).strip()
    release_site = as_user("doctrad", release / ".venv/bin/python", "-c", query, capture=True).strip()
    # A private venv per release keeps code/entrypoints isolated, sharing only immutable libraries.
    atomic(Path(release_site) / "oneforall-dependencies.pth", shared_site + "\n", 0o644)
    as_user("doctrad", release / ".venv/bin/pip", "install", "--no-deps", "--no-build-isolation",
        release, env={"TMPDIR": str(temp), "PIP_DISABLE_PIP_VERSION_CHECK": "1"})
    as_user("doctrad", release / ".venv/bin/python", "-m", "pip", "check")
    atomic(release / ".dependencies", digest + "\n", 0o644)
    return pool
