"""DocTrad snapshot retention, called only under the OneForAll operation lock."""
import json
import re
import shutil
from pathlib import Path

REQUIRED = {"data.tar", "record.json", "env.json", "database.dump"}

def prune_doctrad(backups, pending):
    root = Path(backups) / "doctrad"
    if not root.is_dir() or root.is_symlink(): return []
    protected = set()
    for path in Path(pending).glob("*.json"):
        try:
            value = json.loads(path.read_text())
            snapshot = value.get("snapshot")
            if snapshot: protected.add(Path(snapshot).resolve())
        except (OSError, ValueError, AttributeError):
            # Unknown pending state: perform no automatic deletion.
            return []
    snapshots = []
    for path in root.iterdir():
        if path.is_symlink() or not path.is_dir() or not re.fullmatch(r"\d{8}T\d{6}-[0-9a-f]{6}", path.name): continue
        try:
            if any(not (path / name).is_file() or (path / name).is_symlink()
                   for name in REQUIRED | {"SHA256.json"}): continue
            hashes = json.loads((path / "SHA256.json").read_text())
            record = json.loads((path / "record.json").read_text())
            if not REQUIRED.issubset(hashes) or not re.fullmatch(r"[0-9a-f]{40}", record.get("sha", "")): continue
            if any(not isinstance(hashes[name], str) or not re.fullmatch(r"[0-9a-f]{64}", hashes[name]) for name in REQUIRED): continue
        except (OSError, ValueError, TypeError, AttributeError): continue
        snapshots.append(path)
    snapshots.sort(key=lambda p: p.name, reverse=True)
    if len(snapshots) < 3: return []
    keep = set(snapshots[:2])
    # Snapshot names use UTC. Keep the last available earlier calendar day;
    # this preserves a day boundary even when no backup was made yesterday.
    newest_day = snapshots[0].name[:8]
    older_day = next((p for p in snapshots if p.name[:8] < newest_day), None)
    if older_day: keep.add(older_day)
    removed = []
    for path in snapshots:
        if path in keep or path.resolve() in protected: continue
        # Do not descend into an unexpected mounted filesystem.
        device = path.stat().st_dev
        if any(p.is_mount() or (not p.is_symlink() and p.stat().st_dev != device)
               for p in path.rglob("*")): continue
        shutil.rmtree(path)
        removed.append(path.name)
        print("DocTrad : ancienne sauvegarde supprimée :", path.name)
    return removed
