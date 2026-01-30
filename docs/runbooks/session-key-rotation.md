# Session signing key rotation runbook

This runbook describes how to rotate the session signing key used by
applications that mount a `sessionSecret` from the example Helm chart.

## Preconditions

- Access to the Kubernetes cluster (kubectl configured).
- The application HelmRelease has `sessionSecret.enabled` set to `true`.
- The Secret name and key match the Helm values (defaults:
  `example-app-session-key` and `session_key`).

## Rotate the key

1. Generate a new signing key (64 bytes or longer):

   ```bash
   openssl rand -base64 64
   ```

2. Update the Secret with the new key:

   ```bash
   kubectl -n <namespace> create secret generic example-app-session-key \
     --from-literal=session_key="<new-key>" \
     --dry-run=client -o yaml | kubectl apply -f -
   ```

3. Restart the application deployment so pods pick up the new key:

   ```bash
   kubectl -n <namespace> rollout restart deployment/example-app
   ```

4. Confirm the rollout completes successfully:

   ```bash
   kubectl -n <namespace> rollout status deployment/example-app
   ```

## Rollback

If the rotation causes unexpected behaviour, re-apply the previous key using
step 2, then restart the deployment again.
