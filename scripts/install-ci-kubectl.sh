#!/usr/bin/env bash
set -Eeuo pipefail
tool_dir="$(mktemp -d)"
trap 'rm -rf "$tool_dir"' EXIT
curl --fail --silent --show-error --location -o "$tool_dir/kubectl" https://dl.k8s.io/release/v1.36.5/bin/linux/amd64/kubectl
curl --fail --silent --show-error --location -o "$tool_dir/kubectl.sha256" https://dl.k8s.io/release/v1.36.5/bin/linux/amd64/kubectl.sha256
(cd "$tool_dir" && printf '%s  kubectl\n' "$(cat kubectl.sha256)" | sha256sum --check)
mkdir -p "$HOME/.local/bin"
install -m 755 "$tool_dir/kubectl" "$HOME/.local/bin/kubectl"
if [[ -n "${GITHUB_PATH:-}" ]]; then echo "$HOME/.local/bin" >> "$GITHUB_PATH"; fi
