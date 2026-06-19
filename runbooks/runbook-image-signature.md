# Runbook: Container Image Signature Verification & Troubleshooting

## 1. Overview
This runbook explains how to sign container images, how the **Sigstore Policy Controller** enforces signature verification in the Kubernetes cluster, and how to troubleshoot deployments blocked by the admission controller.

---

## 2. Image Verification Workflow
1. **CI Pipeline Build & Sign**: GitHub Actions builds the image, runs Trivy, pushes it to GHCR, and signs it using Cosign with a private key.
2. **Cluster Admission Control**: 
   - Sigstore Policy Controller listens for pod creation requests.
   - It matches pods against the `ClusterImagePolicy` (which contains the public key).
   - If the pod namespace has the label `policy.sigstore.dev/include: "true"`, the controller checks if the container image has a valid signature matching the public key.
   - Unsigned or invalidly signed images are blocked.

---

## 3. How to Enable Enforcement on Namespace
To avoid blocking initial deployments, the admission label is commented out during bootstrap. Once the first signed image is successfully pushed to GHCR:

Enable verification by uncommenting `policy.sigstore.dev/include: "true"` in [app-common/demo-namespace.yaml](file:///d:/GitHub/rbac_admission/app-common/demo-namespace.yaml) or apply the label directly:
```bash
kubectl label ns demo policy.sigstore.dev/include=true --overwrite
```

---

## 4. Test Scenarios

### Scenario A: Deploying a Signed Image (Happy Path)
1. Push a change to the api source folder.
2. The GitHub Actions workflow automatically builds, scans, pushes, and signs the image.
3. ArgoCD updates `app-api/rollout.yaml` to point to the new signed tag.
4. The deployment succeeds.

### Scenario B: Deploying an Unsigned Image (Verification Rejection)
If you attempt to run an unsigned image (e.g., standard nginx) in the `demo` namespace:
```bash
kubectl run test-unsigned --image=nginx:latest -n demo
```
*Expected Error Output:*
```
Error from server (InternalError): admission webhook "policy.sigstore.dev" denied the request: 
validation failed: image nginx:latest does not have a valid signature
```

---

## 5. Troubleshooting & Remediation

When a Rollout or Deployment fails to spawn pods because of signature verification, follow these troubleshooting steps:

### Step 1: Check Pod Creation Events
If a deployment is stuck, inspect the ReplicaSet events:
```bash
kubectl get replicasets -n demo -l app=api
kubectl describe replicaset -n demo <replicaset-name>
```
Look for events indicating that the admission controller blocked the pod creation.

### Step 2: Verify Image Locally with Cosign
Download the public key `signing/cosign.pub` and verify the signature of the image using Cosign:
```bash
cosign verify --key signing/cosign.pub ghcr.io/pkhoa011004/w10-api:<tag>
```
- If you see `wildcard-like authority matched`, the image is validly signed.
- If you see `no matching signatures`, the image is unsigned or signed with a different key.

### Step 3: Remediation for Unsigned Images
If the image was built but failed to be signed due to CI/CD issues:
1. Re-run the GitHub Actions build-push workflow.
2. Alternatively, manually sign the image if you have access to the private key:
   ```bash
   cosign sign --key <path-to-private-key> ghcr.io/pkhoa011004/w10-api:<tag>
   ```
