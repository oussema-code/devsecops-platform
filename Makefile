.PHONY: cluster-up deploy gitops-up verify test storefront production hubble argocd status
cluster-up:
	bash scripts/cluster-up.sh
deploy:
	bash scripts/deploy-apps.sh
gitops-up:
	bash scripts/gitops-up.sh
verify:
	python3 scripts/verify-platform.py
test:
	python3 -m unittest discover -s tests -v
	bash -n scripts/*.sh
storefront:
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n boutique-staging port-forward --address 127.0.0.1 service/frontend 18081:80
production:
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n boutique-production port-forward --address 127.0.0.1 service/frontend 18082:80
hubble:
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n kube-system port-forward --address 127.0.0.1 service/hubble-ui 12000:80
argocd:
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n argocd port-forward --address 127.0.0.1 service/argocd-server 18443:443
status:
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform get nodes
	kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform get pods -A
