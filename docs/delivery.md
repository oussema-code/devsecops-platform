# Delivery and promotion

## GitOps

Argo CD reads `git@github.com:oussema-code/devsecops-platform.git` through a
repository-specific, read-only SSH deploy key. The private key lives only in
ignored local state and the `argocd/platform-repository` Secret. It cannot push.
The AppProject restricts destinations to the two Boutique namespaces and resource
kinds to the application's deployments, Services, policies, budgets and quotas.

Staging automatically reconciles and repairs drift from `main`. Production
requires an explicit sync; it intentionally does not automatically repair drift.
Deleting an Application does not automatically delete its workloads because no
cascading-delete finalizer is set.

`make gitops-up` installs Argo CD and repository access. Once it is installed,
`make deploy` refuses to modify the app directly. Use Git for configuration.
`make argocd` opens a loopback tunnel to https://127.0.0.1:18443 with Argo CD's
self-signed TLS certificate. Username: `admin`. Retrieve the generated password
locally; never commit it:

```bash
kubectl --kubeconfig .platform/kubeconfig --context kind-devsecops-platform -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 --decode
```

## Image release

The manually dispatched `Build and stage signed release` workflow builds eleven
images from `upstream.lock.json`, using three concurrent GitHub-hosted runners.
Each image must pass Trivy's HIGH/CRITICAL vulnerability gate, including findings
with no fix. No blanket vulnerability exclusions are configured. A failed image
blocks the complete release; scan reports and SBOMs are workflow artifacts.
Application source remains upstream and is not edited for feature development.

Successful builds publish to `ghcr.io/oussema-code/boutique-SERVICE`, sign the
immutable digest using GitHub OIDC and Cosign, and attach a CycloneDX SBOM
attestation. Cosign is pinned to 2.6.1 for the classic signature layout supported
by Kyverno/GHCR; upgrade only after testing the newer bundle-format integration
([upstream compatibility issue](https://github.com/kyverno/kyverno/issues/16664)).

The user approved public application images while keeping platform Git private.
GHCR creates new packages private by default. Their first publication requires
changing each package's visibility to public in GitHub's package settings. The
staging job verifies anonymous pulls for every digest before changing Git, so
unreadable images are never promoted. A partial build, mismatched source revision,
unexpected registry, or mixed build configuration is also rejected.

When all checks pass, CI commits the digest set to staging. Argo CD then deploys
it. CI uses a write-scoped token only in the staging-update job; build jobs have
package publishing and OIDC permissions. Pull-request validation is read-only.

## Production promotion and rollback

After staging acceptance, copy its `images` entries and `release.json` to the
production overlay in a reviewed Git change. Never rebuild images for production.
Sync `boutique-production` explicitly in Argo CD to that approved Git revision.
For recovery, revert the production image change in Git and explicitly sync the
revert. Keeping Git as the desired state avoids a temporary cluster-only rollback.

GitHub returned HTTP 403 for private branch protection on the current account
plan. Required checks cannot be enforced on `main` without a suitable GitHub plan
or a different repository visibility decision. The repository remains private as
requested. CI and the explicit production sync gate are active controls, but
direct pushes remain possible. No paid plan or visibility change was made.
