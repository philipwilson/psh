#!/bin/sh
# tools/ci/build_bash_oracle.sh — build the pinned differential oracle,
# GNU bash 5.3 + official patches 001..015 (= 5.3.15), from source.
#
# Improvement Program 2026-09, standing rule D1: the oracle contract is bash
# major.minor 5.3 (patch level 5.3.15 recorded), resolved by
# tests/harness/shell_oracle.py#resolve_bash (BASH_PATH -> Homebrew -> PATH).
# The Linux nightly (.github/workflows/nightly.yml) builds and runs the SAME
# 5.3.15 so that version drift between hosts is impossible; Ubuntu's system
# bash (5.2.21) is deliberately no longer exercised.
#
# Usage:
#   sh tools/ci/build_bash_oracle.sh [PREFIX] [WORKDIR]
#     PREFIX   install prefix (default: $HOME/bash-oracle-5.3.15)
#     WORKDIR  scratch build dir (default: a fresh dir under $TMPDIR or /tmp)
#
# Environment:
#   BASH_ORACLE_MIRROR  base URL of the GNU bash directory
#                       (default https://ftp.gnu.org/gnu/bash)
#   BASH_ORACLE_FORCE   set to 1 to rebuild even if PREFIX already holds 5.3.15
#   BASH_ORACLE_KEEP    set to 1 to keep WORKDIR after a successful build
#   MAKEFLAGS/JOBS      JOBS overrides the parallelism (default: CPU count)
#
# Every download is verified against a PUBLISHED sha256 before use.  GNU
# publishes only detached GPG signatures on ftp.gnu.org, so the checksums
# below are the ones recorded in Homebrew's bash formula for 5.3.15
# (`brew cat bash`, 2026-09-06) — an independently maintained, publicly
# reviewed source.  A mismatch aborts the build; nothing is ever installed
# from an unverified file.
#
# Exit status: 0 and the built binary's version line on success; non-zero
# with a diagnostic on any download, checksum, patch, build or version-check
# failure.  The final check refuses to succeed unless the INSTALLED binary
# reports BASH_VERSION 5.3.15* — a wrong build must fail loudly here rather
# than let the suite silently test some other bash.

set -eu

EXPECTED_VERSION="5.3.15"
BASE_VERSION="5.3"
PATCH_COUNT=15

PREFIX="${1:-$HOME/bash-oracle-$EXPECTED_VERSION}"
WORKDIR="${2:-${TMPDIR:-/tmp}/bash-oracle-build.$$}"
MIRROR="${BASH_ORACLE_MIRROR:-https://ftp.gnu.org/gnu/bash}"

TARBALL="bash-$BASE_VERSION.tar.gz"
TARBALL_URL="$MIRROR/$TARBALL"
TARBALL_SHA256="0d5cd86965f869a26cf64f4b71be7b96f90a3ba8b3d74e27e8e9d9d5550f31ba"
PATCH_URL_DIR="$MIRROR/bash-$BASE_VERSION-patches"

# "NNN sha256" pairs, one per line (POSIX sh has no arrays).
PATCH_SHA256S="
001 1f608434364af86b9b45c8b0ea3fb3b165fb830d27697e6cdfc7ac17dee3287f
002 e385548a00130765ec7938a56fbdca52447ab41fabc95a25f19ade527e282001
003 f245d9c7dc3f5a20d84b53d249334747940936f09dc97e1dcb89fc3ab37d60ed
004 9591d245045529f32f0812f94180b9d9ce9023f5a765c039b852e5dfc99747d0
005 cca1ef52dbbf433bc98e33269b64b2c814028efe2538be1e2c9a377da90bc99d
006 29119addefed8eff91ae37fd51822c31780ee30d4a28376e96002706c995ff10
007 c0976bbfffa1453c7cfdd62058f206a318568ff2d690f5d4fa048793fa3eb299
008 097cd723cbfb8907674ac32214063a3fd85282657ec5b4e544d2c0f719653fb4
009 eee30fe78a4b0cb2fe20e010e00308899cfc613e0774ebb3c8557a1552f24f8c
010 cf76f1cce2ea300c18bff9f002d21f280cc931acd17c28518110b93fe6e72569
011 0298df8f5ea2a31d3be43ed7d269c5b3c7c342dd5b570bea7f64d66dcbbe7531
012 d71379b39bebaedaf123414414e77fb458a0a43b9ad3116594c6df7ca6754573
013 042f9cda967e24bf4211944697441e93d06ff42b4b998629a98a1b249279f200
014 bd4360b401d38507e358783dcad8536a99c6789f0d3a5bd0cfb8c4a34144696c
015 55b79ceee2fc27f6767eed697e939a7eb2fe2a28c01556bd75f18d581014f46e
"

log() { printf '%s\n' "build_bash_oracle: $*"; }
die() { printf '%s\n' "build_bash_oracle: ERROR: $*" >&2; exit 1; }

# --- helpers -----------------------------------------------------------------

sha256_of() {
    # Print the hex sha256 of $1 using whichever tool the host has.
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | cut -d' ' -f1
    elif command -v openssl >/dev/null 2>&1; then
        openssl dgst -sha256 "$1" | sed 's/^.*= *//'
    else
        die "no sha256sum, shasum or openssl on this host; cannot verify downloads"
    fi
}

fetch_verified() {
    # fetch_verified URL DEST SHA256 — download, then refuse on a mismatch.
    url=$1; dest=$2; want=$3
    log "fetching $url"
    curl -fsSL --retry 3 --retry-delay 2 -o "$dest" "$url" \
        || die "download failed: $url"
    got=$(sha256_of "$dest")
    if [ "$got" != "$want" ]; then
        rm -f "$dest"
        die "sha256 mismatch for $(basename "$dest"): got $got, expected $want"
    fi
    log "verified $(basename "$dest") ($got)"
}

installed_version() {
    # Print BASH_VERSION of the binary at $1, or nothing if it cannot run.
    [ -x "$1" ] || return 0
    "$1" -c 'printf "%s\n" "$BASH_VERSION"' 2>/dev/null || true
}

cpu_count() {
    if [ -n "${JOBS:-}" ]; then printf '%s\n' "$JOBS"
    elif command -v nproc >/dev/null 2>&1; then nproc
    elif command -v sysctl >/dev/null 2>&1; then sysctl -n hw.ncpu 2>/dev/null || echo 2
    else echo 2
    fi
}

# --- fast path: an existing, correct install ---------------------------------

ORACLE="$PREFIX/bin/bash"
have=$(installed_version "$ORACLE")
case "$have" in
    "$EXPECTED_VERSION"*)
        if [ "${BASH_ORACLE_FORCE:-0}" != "1" ]; then
            log "already built: $ORACLE reports $have (set BASH_ORACLE_FORCE=1 to rebuild)"
            exit 0
        fi
        log "BASH_ORACLE_FORCE=1: rebuilding over $ORACLE ($have)"
        ;;
    "") ;;
    *)  log "existing $ORACLE reports $have, not $EXPECTED_VERSION; rebuilding" ;;
esac

# --- download + verify -------------------------------------------------------

for tool in curl tar patch make; do
    command -v "$tool" >/dev/null 2>&1 || die "required tool not found: $tool"
done
command -v cc >/dev/null 2>&1 || command -v gcc >/dev/null 2>&1 \
    || die "no C compiler (cc/gcc) found"

# PREFIX is created only once every download has verified (just before
# configure), so a failed run never leaves an empty prefix directory behind.
mkdir -p "$WORKDIR"
cd "$WORKDIR"
log "workdir $WORKDIR, prefix $PREFIX, mirror $MIRROR"

fetch_verified "$TARBALL_URL" "$WORKDIR/$TARBALL" "$TARBALL_SHA256"

patch_sha256() {
    # patch_sha256 NNN — the published checksum for bash53-NNN, or nothing.
    printf '%s\n' "$PATCH_SHA256S" | awk -v n="$1" '$1 == n { print $2 }'
}

# A plain counted loop (not `printf | while read`): a pipeline body runs in
# a subshell in POSIX sh, where `die`'s exit would not stop the script.
i=1
while [ "$i" -le "$PATCH_COUNT" ]; do
    num=$(printf '%03d' "$i")
    sum=$(patch_sha256 "$num")
    [ -n "$sum" ] || die "no published sha256 recorded for bash53-$num"
    fetch_verified "$PATCH_URL_DIR/bash53-$num" "$WORKDIR/bash53-$num" "$sum"
    i=$((i + 1))
done

# --- extract + patch ---------------------------------------------------------

rm -rf "$WORKDIR/bash-$BASE_VERSION"
tar -xzf "$WORKDIR/$TARBALL" -C "$WORKDIR"
cd "$WORKDIR/bash-$BASE_VERSION"

i=1
while [ "$i" -le "$PATCH_COUNT" ]; do
    num=$(printf '%03d' "$i")
    log "applying bash53-$num"
    # GNU's bash patches are -p0 relative to the source root; -s keeps the
    # log to failures only, and a failed hunk is fatal (no fuzz tolerated).
    patch -p0 -s -F0 < "$WORKDIR/bash53-$num" \
        || die "patch bash53-$num did not apply cleanly"
    i=$((i + 1))
done

# --- configure + build + install ---------------------------------------------

# Plain GNU defaults: the oracle must behave like a stock GNU bash, not like a
# distribution's customised build.  The prefix is under the caller's control
# (a $HOME path in CI, so no privileges are needed).
mkdir -p "$PREFIX"
log "configure --prefix=$PREFIX"
./configure --prefix="$PREFIX" >"$WORKDIR/configure.log" 2>&1 \
    || { tail -40 "$WORKDIR/configure.log" >&2; die "configure failed (log: $WORKDIR/configure.log)"; }

jobs=$(cpu_count)
log "make -j$jobs"
make -j"$jobs" >"$WORKDIR/make.log" 2>&1 \
    || { tail -40 "$WORKDIR/make.log" >&2; die "make failed (log: $WORKDIR/make.log)"; }

log "make install"
make install >"$WORKDIR/install.log" 2>&1 \
    || { tail -40 "$WORKDIR/install.log" >&2; die "make install failed (log: $WORKDIR/install.log)"; }

# --- verify the INSTALLED binary --------------------------------------------

got=$(installed_version "$ORACLE")
case "$got" in
    "$EXPECTED_VERSION"*) ;;
    *) die "installed $ORACLE reports BASH_VERSION '$got', expected $EXPECTED_VERSION*" ;;
esac

if [ "${BASH_ORACLE_KEEP:-0}" != "1" ]; then
    cd /
    rm -rf "$WORKDIR"
fi

log "built $ORACLE"
"$ORACLE" --version | head -1
"$ORACLE" -c 'printf "BASH_VERSION=%s MACHTYPE=%s printf-%%a-of-1=%a\n" "$BASH_VERSION" "$MACHTYPE" 1'
