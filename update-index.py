#!/usr/bin/env python3
"""Build rsinput.ko for recent Armada images and write the index the devices read.

Usage: update-index.py ARMADA_DIR OLD_INDEX OUT_DIR

ARMADA_DIR is a clone of armada-os/armada with the image branches as origin/<branch>
and cerroverb/armada's PR branches as fork/<branch>. OLD_INDEX is the index.json of the
current release (may be missing). Modules already built for the same kernel tree and
patches are reused. New ones are written to OUT_DIR as rsinput-<key>.ko next to
OUT_DIR/index.json. A device looks up the commit in its IMAGE_VERSION under "images".
"""
import hashlib, json, os, subprocess, sys

IMAGE_BRANCHES = ("main", "beta")
COMMITS_PER_BRANCH = 300
PR_BRANCHES = ("rsinput-report-rate", "direct-controller-mode")
SERIES = "packages/kernel/patches/series"
MAX_BUILDS_PER_RUN = 4

armada, old_index_path, out_dir = sys.argv[1:4]
here = os.path.dirname(os.path.abspath(__file__))


def git(*args):
    return subprocess.run(["git", "-C", armada, *args], check=True, capture_output=True, text=True).stdout


def series_names(ref):
    return [line.split("#")[0].split()[0] for line in git("show", f"{ref}:{SERIES}").splitlines()
            if line.split("#")[0].strip()]


def pr_patches():
    """Patch name -> content for the patches each PR branch adds to Armada's series."""
    patches = {}
    for branch in PR_BRANCHES:
        ref = f"fork/{branch}"
        base = git("merge-base", "origin/main", ref).strip()
        for name in set(series_names(ref)) - set(series_names(base)):
            patches[name] = git("show", f"{ref}:packages/kernel/patches/{name}")
    return patches


patches = pr_patches()
patch_dir = os.path.join(out_dir, "patches")
os.makedirs(patch_dir, exist_ok=True)
for name, text in patches.items():
    with open(os.path.join(patch_dir, name), "w") as f:
        f.write(text)
patch_hash = hashlib.sha256("".join(n + patches[n] for n in sorted(patches)).encode()).hexdigest()

images = {}
for branch in IMAGE_BRANCHES:
    for commit in git("rev-list", f"--max-count={COMMITS_PER_BRANCH}", f"origin/{branch}").split():
        tree = git("rev-parse", f"{commit}:packages/kernel").strip()
        images[commit] = (hashlib.sha256((tree + patch_hash).encode()).hexdigest()[:16], tree)

try:
    with open(old_index_path) as f:
        old_modules = json.load(f)["modules"]
except FileNotFoundError:
    old_modules = {}

modules, builds = {}, 0
# Newest commits first, so the kernels devices are most likely to run get built first.
for commit, (key, tree) in images.items():
    if key in modules:
        continue
    if key in old_modules:
        modules[key] = old_modules[key]
        continue
    if builds == MAX_BUILDS_PER_RUN:
        continue
    builds += 1
    ko = os.path.join(out_dir, f"rsinput-{key}.ko")
    subprocess.run([os.path.join(here, "build-module.sh"), armada, commit, patch_dir, ko], check=True)
    with open(ko, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()
    vermagic = subprocess.run(["modinfo", "-F", "vermagic", ko], check=True, capture_output=True, text=True).stdout.strip()
    modules[key] = {"sha256": digest, "vermagic": vermagic, "kernel_tree": tree, "patches": sorted(patches)}

index = {
    "images": {commit: key for commit, (key, _) in images.items() if key in modules},
    "modules": modules,
}
with open(os.path.join(out_dir, "index.json"), "w") as f:
    json.dump(index, f, indent=1, sort_keys=True)
print(f"{builds} built, {len(modules)} modules, {len(index['images'])} images")
