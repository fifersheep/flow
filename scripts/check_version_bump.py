#!/usr/bin/env python3
"""Every change ships a version bump. This checks two things:

1. Consistency — plugin.json's version and both versions in marketplace.json
   agree. (They drifted once; that is what this half prevents.)
2. Bump — the working tree's version is strictly greater than the base ref's.
   Skipped when no base ref is given, so the same script serves as a local
   consistency check: python3 scripts/check_version_bump.py

CI passes the base ref: python3 scripts/check_version_bump.py origin/main
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ".claude-plugin/plugin.json"
MARKET = ".claude-plugin/marketplace.json"
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse(version, where):
    m = SEMVER_RE.match(version or "")
    if not m:
        raise SystemExit(f"{where}: version {version!r} is not X.Y.Z")
    return tuple(int(g) for g in m.groups())


def versions(plugin_text, market_text):
    """All declared versions as {location: version string}."""
    market = json.loads(market_text)
    found = {PLUGIN: json.loads(plugin_text).get("version"),
             f"{MARKET} metadata": market.get("metadata", {}).get("version")}
    for entry in market.get("plugins", []):
        found[f"{MARKET} plugins[{entry.get('name')}]"] = entry.get("version")
    return found


def read_tree():
    return ((ROOT / PLUGIN).read_text(), (ROOT / MARKET).read_text())


def read_ref(ref):
    def show(path):
        r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"cannot read {path} at {ref}: {r.stderr.strip()}")
        return r.stdout
    return (show(PLUGIN), show(MARKET))


def check_consistent(found, label):
    distinct = set(found.values())
    if len(distinct) != 1:
        detail = "\n".join(f"  {k}: {v}" for k, v in found.items())
        raise SystemExit(
            f"version mismatch in {label} — all manifests must declare the "
            f"same version:\n{detail}")
    return parse(next(iter(distinct)), label)


def main(argv):
    head = check_consistent(versions(*read_tree()), "working tree")
    if len(argv) < 2:
        print(f"ok: version {'.'.join(map(str, head))} consistent across manifests")
        return 0
    base_ref = argv[1]
    base = check_consistent(versions(*read_ref(base_ref)), base_ref)
    if head <= base:
        raise SystemExit(
            f"version not bumped: {base_ref} is {'.'.join(map(str, base))}, "
            f"this branch is {'.'.join(map(str, head))}. Every PR bumps the "
            f"version in {PLUGIN} and {MARKET} — patch for fixes, minor for "
            f"new or changed behaviour, major for breaking changes.")
    print(f"ok: {'.'.join(map(str, base))} → {'.'.join(map(str, head))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
