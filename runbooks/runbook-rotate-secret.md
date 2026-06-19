# Runbook: Secret Rotation without Restarting Pods

## 1. Overview
This runbook explains the procedure for rotating (updating) application secrets in the Kubernetes cluster using **External Secrets Operator (ESO)** and verifying that the application picks up the new secret without restarting the pods.

By mounting the secret as a **Volume** instead of injecting it as environment variables, Kubernetes dynamically updates the secret file inside the container, achieving zero-downtime rotation.

---

## 2. Prerequisites
- Access to the `w10` minikube cluster with `kubectl` configured.
- The `external-secrets-operator` and `external-secrets-config` applications are deployed and healthy in ArgoCD.

---

## 3. Step-by-Step Rotation Procedure

For this lab, we use a `fake` provider (mock SecretStore) to demonstrate the pattern. In a production environment, the provider would be AWS Secrets Manager or HashiCorp Vault.

### Step 1: Update the Secret Source
Open [eso/secret-store.yaml](file:///d:/GitHub/rbac_admission/eso/secret-store.yaml) and update the secret value:

```yaml
spec:
  provider:
    fake:
      data:
        - key: db-password
          value: "my-super-secret-password-v3" # Update this value
```

### Step 2: Push changes to Git (GitOps Sync)
Commit and push the changes to apply them through ArgoCD:
```bash
git add eso/secret-store.yaml
git commit -m "chore: rotate database password to v3"
git push origin main
```

*(Note: If testing locally without git push, you can apply it directly via: `kubectl apply -f eso/secret-store.yaml`)*

### Step 3: Verify ESO Synchronization
ESO automatically polls the provider every **10 seconds** (defined as `refreshInterval: 10s` in `eso/external-secret.yaml`).

Check if the Kubernetes Secret has been updated:
```bash
kubectl get secret db-secret -n demo -o jsonpath='{.data.db-password}' | base64 -d; echo
```
*Expected Output:* `my-super-secret-password-v3`

---

## 4. Verify Zero-Downtime Application Update

### Step 1: Check Pod Age and Restarts
Verify that Kubernetes did **not** restart the API pods to apply the new secret. The restart count should remain unchanged and the pod age should not reset:
```bash
kubectl get pods -n demo -l app=api
```
*Expected Output:*
```
NAME                   READY   STATUS    RESTARTS   AGE
api-664bd47576-cjk76   1/1     Running   0          2h
api-664bd47576-jw5fq   1/1     Running   0          2h
```

### Step 2: Verify Secret Value inside Container
Exec into one of the active API pods and read the secret file mounted at `/etc/secrets/db-password`:
```bash
# Get one of the pod names
POD_NAME=$(kubectl get pods -n demo -l app=api -o jsonpath='{.items[0].metadata.name}')

# Print the secret content inside the container
kubectl exec -it $POD_NAME -n demo -c api -- cat /etc/secrets/db-password; echo
```
*Expected Output:* `my-super-secret-password-v3`

---

## 5. Why the Pod Does Not Need to Restart
- **Volume Mount vs Env Var**: We mount the secret as a file volume under `/etc/secrets/db-password`.
- **Kubelet Dynamic Sync**: When the underlying secret object is updated in the API server, the `kubelet` on the node automatically updates the projected volume content inside the running container (usually within a minute).
- **Application Live Reload**: The application reads the secret directly from the file system. Because it is read on-demand or watched dynamically, we avoid restarting the container and maintain 100% availability.
