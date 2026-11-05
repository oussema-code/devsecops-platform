.PHONY: cluster-up deploy verify test storefront production hubble status
cluster-up:
	bash scripts/cluster-up.sh
deploy:
	bash scripts/deploy-apps.sh
verify:
	python3 scripts/verify-platform.py
test:
	python3 -m unittest discover -s tests -v
	bash -n scripts/common.sh scripts/cluster-up.sh scripts/deploy-apps.sh
storefront:
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n boutique-staging port-forward --address 127.0.0.1 service/frontend 18081:80
production:
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n boutique-production port-forward --address 127.0.0.1 service/frontend 18082:80
hubble:
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n kube-system port-forward --address 127.0.0.1 service/hubble-ui 12000:80
status:
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform get nodes
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform get pods -A
