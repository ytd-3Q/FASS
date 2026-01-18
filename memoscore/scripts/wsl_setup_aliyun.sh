#!/usr/bin/env bash
set -euo pipefail

export RUSTUP_UPDATE_ROOT=https://mirrors.aliyun.com/rustup/rustup
export RUSTUP_DIST_SERVER=https://mirrors.aliyun.com/rustup

curl --proto '=https' --tlsv1.2 -sSf https://mirrors.aliyun.com/repo/rust/rustup-init.sh | sh -s -- -y --profile minimal

source "$HOME/.cargo/env"

rustup set profile minimal
rustup toolchain install stable --no-self-update
rustup default stable

