#!/bin/bash
# build-module.sh ARMADA_DIR COMMIT PATCH_DIR OUT_KO
# Builds rsinput.ko for the Armada image made from COMMIT, with the extra rsinput patches
# in PATCH_DIR (applied in name order, skipping any the commit already carries).
# Follows Armada's packages/kernel/scripts/build-kernel.sh up to modules_prepare:
# kernel.org stable source, patches/series, defconfig plus the config fragment.
set -euo pipefail
armada=$1 commit=$2 patch_dir=$3 out_ko=$4
cache=${CACHE_DIR:-$PWD/work/cache}
work=$(mktemp -d "${TMPDIR:-/tmp}/rsinput-build.XXXXXX")
trap 'rm -rf "$work"' EXIT
mkdir -p "$cache"

git -C "$armada" archive "$commit" packages/kernel | tar -x -C "$work" --strip-components=1
kernel=$work/kernel
version=$(. "$kernel/BASE.env"; echo "$VERSION")
tarball=$cache/linux-$version.tar.gz
[ -f "$tarball" ] || curl -fsSL -o "$tarball" "https://github.com/gregkh/linux/archive/refs/tags/v$version.tar.gz"
tar -xf "$tarball" -C "$work"
src=$work/linux-$version
cd "$src"

series=$(sed 's/#.*//' "$kernel/patches/series" | awk 'NF {print $1}')
for p in $series; do
    patch -p1 -s --forward --no-backup-if-mismatch < "$kernel/patches/$p"
done
for p in "$patch_dir"/*.patch; do
    if grep -qx "$(basename "$p")" <<<"$series"; then
        echo "already in Armada: $(basename "$p")"
        continue
    fi
    patch -p1 -s --forward --no-backup-if-mismatch < "$p"
    echo "applied: $(basename "$p")"
done

export KBUILD_BUILD_USER=armada KBUILD_BUILD_HOST=builder
make -s defconfig
frag=$work/config.fragment
# Same filter as Armada's build: kconfig cannot parse trailing comments on assignments.
sed -E '/^[[:space:]]*CONFIG_[A-Z0-9_]+=/ s/[[:space:]]*#.*$//' "$kernel/config/armada-kernel.config.overrides" > "$frag"
bash scripts/kconfig/merge_config.sh .config "$frag" > "$work/merge.log"
grep -qx 'CONFIG_JOYSTICK_RSINPUT=m' .config || { echo "CONFIG_JOYSTICK_RSINPUT is not a module"; exit 1; }
if grep -qx 'CONFIG_MODVERSIONS=y' .config; then echo "MODVERSIONS is on, the build would need the kernel's Module.symvers"; exit 1; fi
make -s -j"$(nproc)" modules_prepare

mod=$work/mod
mkdir "$mod"
cp drivers/input/joystick/rsinput.c "$mod/"
echo 'obj-m := rsinput.o' > "$mod/Kbuild"
# Without a full kernel build there is no Module.symvers, so modpost cannot see the
# kernel's exports. Armada builds with MODVERSIONS off, so the kernel resolves them when
# the module loads, and a missing one still fails insmod.
make -s -j"$(nproc)" M="$mod" KBUILD_MODPOST_WARN=1 modules
# Armada installs its modules with INSTALL_MOD_STRIP=1, which strips debug info.
strip --strip-debug "$mod/rsinput.ko"
install -D -m 644 "$mod/rsinput.ko" "$out_ko"
echo "built $(modinfo -F vermagic "$out_ko") for $commit"
