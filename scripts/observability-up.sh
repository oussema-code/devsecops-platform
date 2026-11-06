#!/usr/bin/env bash
set -Eeuo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/common.sh"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
helm repo add grafana https://grafana.github.io/helm-charts --force-update
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts --force-update
install_chart() {
  h upgrade --install "$1" "$2" --version "$3" -n monitoring --create-namespace \
    -f "$PLATFORM_ROOT/platform/values/$1.yaml" --wait --timeout 10m
}
install_chart monitoring prometheus-community/kube-prometheus-stack 92.20.0
install_chart probe prometheus-community/prometheus-blackbox-exporter 11.20.2
install_chart loki grafana/loki 7.5.0
install_chart tempo grafana/tempo 1.24.4
install_chart otel open-telemetry/opentelemetry-collector 0.178.2
install_chart alloy grafana/alloy 1.15.0
k -n monitoring create configmap storefront-dashboard --from-file="$PLATFORM_ROOT/platform/observability/storefront.json" --dry-run=client -o yaml | k apply -f -
k -n monitoring label configmap storefront-dashboard grafana_dashboard=1 --overwrite
