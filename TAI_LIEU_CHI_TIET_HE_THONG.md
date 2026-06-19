# Tài Liệu Chi Tiết Hệ Thống GitOps - Progressive Delivery với Security

## Mục Lục
1. [Tổng Quan Hệ Thống](#1-tổng-quan-hệ-thống)
2. [Luồng Hoạt Động Tổng Thể](#2-luồng-hoạt-động-tổng-thể)
3. [Chi Tiết Từng File YAML](#3-chi-tiết-từng-file-yaml)
4. [Sơ Đồ Kiến Trúc](#4-sơ-đồ-kiến-trúc)
5. [Kịch Bản Hoạt Động](#5-kịch-bản-hoạt-động)

---

## 1. Tổng Quan Hệ Thống

### 1.1 Mô Tả Hệ Thống
Đây là một hệ thống GitOps hoàn chỉnh triển khai trên Kubernetes với các tính năng:

- **Progressive Delivery**: Triển khai ứng dụng theo chiến lược Canary với phân tích tự động
- **Security**: Bảo mật container images với image signing và admission control
- **Monitoring**: Giám sát real-time với Prometheus và cảnh báo qua email
- **GitOps**: Quản lý hạ tầng hoàn toàn qua Git với ArgoCD

### 1.2 Các Thành Phần Chính

#### Infrastructure Components
- **ArgoCD**: GitOps controller quản lý deployment tự động từ Git
- **Argo Rollouts**: Controller cho progressive delivery (canary deployments)
- **Prometheus Stack**: Giám sát metrics và alerting
- **Gatekeeper (OPA)**: Policy enforcement cho admission control
- **Sigstore Policy Controller**: Xác thực chữ ký số của container images
- **External Secrets Operator (ESO)**: Quản lý secrets động

#### Application Components
- **API Service**: Flask application với metrics endpoint
- **Analysis Templates**: Tự động phân tích success rate trong canary deployment
- **Alert Rules**: Cảnh báo SLO violations

### 1.3 Namespaces

```
├── argocd                    # ArgoCD controller
├── monitoring                # Prometheus + Alertmanager + Grafana
├── argo-rollouts             # Argo Rollouts controller
├── gatekeeper-system         # OPA Gatekeeper
├── cosign-system             # Sigstore Policy Controller
├── external-secrets          # External Secrets Operator
└── demo                      # Application workload
```

---

## 2. Luồng Hoạt Động Tổng Thể

### 2.1 Luồng CI/CD (GitHub Actions → GHCR → ArgoCD)

```
┌──────────────┐
│  Developer   │
│  Git Push    │
└──────┬───────┘
       │
       ▼
┌─────────────────────────────────────────────────┐
│         GitHub Actions CI Pipeline              │
│                                                 │
│  1. Checkout code                               │
│  2. Build Docker image locally                  │
│  3. ┌─────────────────────────┐                │
│     │   Trivy Security Scan   │                │
│     │  (HIGH/CRITICAL CVEs)   │                │
│     └──────────┬──────────────┘                │
│                │                                │
│       ┌────────┴────────┐                      │
│       │                 │                      │
│    [FAIL]            [PASS]                    │
│   Pipeline           │                         │
│   Stops              ▼                         │
│              4. Build & Push to GHCR           │
│              5. Cosign Sign Image              │
│              6. Update rollout.yaml version    │
│              7. Git commit & push              │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
           ┌──────────────────────┐
           │  GitHub Repository   │
           │  (Source of Truth)   │
           └──────────┬───────────┘
                      │
                      │ ArgoCD monitors
                      ▼
           ┌──────────────────────┐
           │   ArgoCD Controller  │
           │   (Pull-based sync)  │
           └──────────┬───────────┘
                      │
                      ▼
           ┌──────────────────────────────────┐
           │    Kubernetes Cluster            │
           │                                  │
           │  ┌────────────────────────┐     │
           │  │  Sigstore Policy       │     │
           │  │  Controller            │     │
           │  │  (Image Verification)  │     │
           │  └───────────┬────────────┘     │
           │              │                   │
           │              ▼                   │
           │     [Signature Valid?]           │
           │         │         │              │
           │      [YES]      [NO]             │
           │         │         │              │
           │         ▼         ▼              │
           │   Deploy Pod   Block Pod         │
           └──────────────────────────────────┘
```

### 2.2 Luồng Progressive Delivery (Canary Rollout)

```
┌──────────────────────────────────────────────────┐
│         Argo Rollout Canary Strategy            │
│                                                  │
│  1. Deploy 10% traffic to new version           │
│     ├─ Old: 90% traffic                         │
│     └─ New: 10% traffic                         │
│                                                  │
│  2. Analysis Template chạy (30s interval)       │
│     └─ Query Prometheus: success_rate >= 90%?   │
│                                                  │
│     ┌──────────┴──────────┐                    │
│     │                     │                    │
│  [PASS]               [FAIL]                   │
│     │                     │                    │
│     ▼                     ▼                    │
│  Continue             Auto Rollback            │
│                                                │
│  3. Deploy 50% traffic                         │
│     ├─ Old: 50%                                │
│     └─ New: 50%                                │
│                                                │
│  4. Analysis Template chạy lại                 │
│     ┌──────────┴──────────┐                   │
│     │                     │                   │
│  [PASS]               [FAIL]                  │
│     │                     │                   │
│     ▼                     ▼                   │
│  Continue             Auto Rollback           │
│                                               │
│  5. Deploy 100% traffic (Complete)            │
│     └─ New: 100%                              │
└───────────────────────────────────────────────┘
```

### 2.3 Luồng Monitoring & Alerting

```
┌─────────────────────────────────────────────────┐
│           Prometheus Monitoring Flow            │
│                                                 │
│  ┌──────────────┐                              │
│  │  API Pods    │                              │
│  │  /metrics    │                              │
│  └──────┬───────┘                              │
│         │                                      │
│         │ ServiceMonitor scrapes every 15s     │
│         ▼                                      │
│  ┌──────────────────┐                         │
│  │   Prometheus     │                         │
│  │   Storage        │                         │
│  └──────┬───────────┘                         │
│         │                                     │
│         │ Recording Rule: api:success_rate:5m │
│         ▼                                     │
│  ┌──────────────────────────────┐            │
│  │  Alert Rule Evaluation       │            │
│  │  success_rate < 95% for 2m?  │            │
│  └──────────┬───────────────────┘            │
│             │                                │
│      ┌──────┴──────┐                        │
│      │             │                        │
│   [NO]          [YES]                       │
│   Normal        Alert FIRING                │
│                    │                        │
│                    ▼                        │
│          ┌─────────────────┐               │
│          │  Alertmanager   │               │
│          │  Route to Email │               │
│          └─────────┬───────┘               │
│                    │                       │
│                    ▼                       │
│          ┌─────────────────┐              │
│          │  Send Email via │              │
│          │  Gmail SMTP     │              │
│          └─────────────────┘              │
└──────────────────────────────────────────┘
```

---

## 3. Chi Tiết Từng File YAML

### 3.1 Infrastructure Setup

#### `argocd/root.yaml`
**Mục đích**: App-of-Apps pattern - điểm khởi đầu quản lý tất cả ứng dụng

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
```

**Chức năng**:
- Đây là "root application" quản lý tất cả child applications
- Trỏ đến thư mục `argocd/apps/` chứa tất cả Application manifests khác
- Khi apply file này, ArgoCD sẽ tự động phát hiện và deploy tất cả apps trong thư mục
- Bật `automated sync` với `prune` và `selfHeal` để tự động đồng bộ và sửa drift

**Sync Wave**: Không có (root level)

---

#### `argocd/apps/app-common.yaml`
**Mục đích**: Deploy namespace và tài nguyên chung

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "-1"
```

**Chức năng**:
- Deploy namespace `demo` trước tất cả các thành phần khác
- Namespace có label `policy.sigstore.dev/include: "true"` (đang bị comment) để kích hoạt image signature verification
- Phải chờ image đầu tiên được sign thành công mới uncomment label này

**Sync Wave**: `-1` (deploy đầu tiên)


**File được deploy**: `app-common/demo-namespace.yaml`

---

#### `argocd/apps/policy-controller.yaml`
**Mục đích**: Cài đặt Sigstore Policy Controller để xác thực chữ ký số của container images

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "-1"
source:
  chart: policy-controller
  targetRevision: 0.9.0
```

**Chức năng**:
- Cài đặt admission webhook để chặn mọi yêu cầu tạo Pod
- Xác thực chữ ký số của container images trước khi cho phép deploy
- Sử dụng Helm chart từ Sigstore official repository
- Tự động cài đặt CRDs (Custom Resource Definitions)

**Sync Wave**: `-1` (cài đặt sớm cùng namespace)

**Namespace**: `cosign-system`

---

#### `argocd/apps/gatekeeper.yaml`
**Mục đích**: Cài đặt OPA Gatekeeper để enforce policies

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "-2"
source:
  chart: gatekeeper
  targetRevision: 3.18.2
```

**Chức năng**:
- Cài đặt Open Policy Agent (OPA) admission controller
- Enforce các policy về security và best practices
- Kiểm tra trước khi cho phép tạo/update resources trong cluster
- Tắt audit interval và label namespace để tối ưu performance

**Sync Wave**: `-2` (deploy trước cả policy-controller)

**Namespace**: `gatekeeper-system`

---

#### `argocd/apps/gatekeeper-constraints.yaml`
**Mục đích**: Deploy các ConstraintTemplate và Constraint cho Gatekeeper

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "0"
path: gatekeeper/constraints
```

**Chức năng**:
- Deploy các policy templates và constraints
- Áp dụng các quy tắc bảo mật cho Rollout resources trong namespace `demo`

**Sync Wave**: `0` (sau khi Gatekeeper controller đã sẵn sàng)

**Files được deploy**:
- `gatekeeper/constraints/00-constrainttemplates.yaml`
- `gatekeeper/constraints/10-constraints.yaml`

---

#### `argocd/apps/k8s-rollout.yaml`
**Mục đích**: Cài đặt Argo Rollouts controller

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "0"
source:
  chart: argo-rollouts
  targetRevision: 2.37.7
```

**Chức năng**:
- Cài đặt controller quản lý progressive delivery
- Hỗ trợ canary, blue-green deployments
- Tự động scale replicas và quản lý traffic splitting
- Tích hợp với analysis templates để tự động validate deployments

**Sync Wave**: `0` (infrastructure layer)

**Namespace**: `argo-rollouts`

---

#### `argocd/apps/external-secrets-operator.yaml` (eso.yaml)
**Mục đích**: Cài đặt External Secrets Operator

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "-1"
source:
  chart: external-secrets
  targetRevision: 0.10.0
```

**Chức năng**:
- Quản lý secrets từ external providers (AWS Secrets Manager, HashiCorp Vault, etc.)
- Trong lab này dùng fake provider để demo
- Tự động sync secrets vào Kubernetes

**Sync Wave**: `-1` (infrastructure sớm)

**Namespace**: `external-secrets`

---

#### `argocd/apps/eso-config.yaml`
**Mục đích**: Deploy cấu hình cho External Secrets Operator

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "0"
path: eso
```

**Chức năng**:
- Deploy SecretStore và ExternalSecret resources
- Tạo secret `db-secret` trong namespace `demo` từ fake provider

**Files được deploy**:
- `eso/secret-store.yaml`: Fake provider với password hardcoded
- `eso/external-secret.yaml`: ExternalSecret tham chiếu SecretStore

**Sync Wave**: `0` (sau khi ESO controller ready)

---

#### `argocd/apps/k8s-prometheus.yaml`
**Mục đích**: Cài đặt Prometheus monitoring stack

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "2"
source:
  chart: kube-prometheus-stack
  targetRevision: 65.1.1
```

**Chức năng**:
- Cài đặt Prometheus để thu thập metrics
- Cài đặt Alertmanager để gửi alerts qua email
- Cài đặt Grafana để visualization (optional)
- Cấu hình email notifications qua Gmail SMTP

**Helm Values quan trọng**:
```yaml
prometheus:
  prometheusSpec:
    serviceMonitorSelectorNilUsesHelmValues: false  # Cho phép discover tất cả ServiceMonitors

alertmanager:
  config:
    receivers:
      - name: 'email-notifications'
        email_configs:
          - to: 'phuockhoamai@gmail.com'
            smarthost: 'smtp.gmail.com:587'
            auth_password_file: /etc/alertmanager/secrets/alertmanager-email/password
  alertmanagerSpec:
    secrets:
      - alertmanager-email  # Mount secret chứa Gmail App Password
```

**Sync Wave**: `2` (sau khi apps đã deploy)

**Namespace**: `monitoring`

---

#### `argocd/apps/policies.yaml`
**Mục đích**: Deploy ClusterImagePolicy cho Sigstore

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "1"
path: policies
```

**Chức năng**:
- Deploy policy xác định images nào cần verify signature
- Chứa public key để verify signatures

**File được deploy**: `policies/cluster-image-policy.yaml`

**Sync Wave**: `1` (sau infrastructure, trước apps)

---

#### `argocd/apps/rbac.yaml`
**Mục đích**: Deploy RBAC roles và bindings

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "1"
path: rbac
```

**Chức năng**:
- Tạo Role và ClusterRole cho các personas: developer, SRE, viewer
- Bind users (alice, bob, carol) vào các roles tương ứng

**Files được deploy**:
- `rbac/roles.yaml`
- `rbac/rolebindings.yaml`

**Sync Wave**: `1`

---

### 3.2 Application Components

#### `argocd/apps/app-analysis.yaml`
**Mục đích**: Deploy AnalysisTemplate cho automated canary validation

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "1"
path: app-analysis
```

**Chức năng**:
- Deploy template định nghĩa cách phân tích metrics từ Prometheus
- Sử dụng trong Rollout strategy để tự động validate canary

**File được deploy**: `app-analysis/analysis-template.yaml`

**Sync Wave**: `1` (trước khi deploy API)

---

#### `argocd/apps/app-alert.yaml`
**Mục đích**: Deploy PrometheusRule cho SLO monitoring

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "1"
path: app-alert
```

**Chức năng**:
- Deploy recording rules và alerting rules
- Tạo alerts khi success rate < 95%

**File được deploy**: `app-alert/prometheus-rules.yaml`

**Sync Wave**: `1`

**Namespace**: `monitoring`

---

#### `argocd/apps/app-api.yaml`
**Mục đích**: Deploy API application với Rollout

```yaml
annotations:
  argocd.argoproj.io/sync-wave: "2"
path: app-api
```

**Chức năng**:
- Deploy Rollout, Service, ServiceMonitor cho API
- Đây là workload chính của hệ thống

**Files được deploy**:
- `app-api/rollout.yaml` (sync-wave: 0)
- `app-api/service.yaml` (sync-wave: 1)
- `app-api/servicemonitor.yaml` (sync-wave: 2)

**Sync Wave**: `2` (deploy sau khi infrastructure ready)

---

### 3.3 Security & Policy Files

#### `gatekeeper/constraints/00-constrainttemplates.yaml`
**Mục đích**: Định nghĩa các ConstraintTemplate (policy templates) bằng Rego

**4 Templates được định nghĩa**:

##### 1. K8sDisallowedImageTags
```rego
violation[{"msg": msg}] {
  container := containers[_]
  tag := input.parameters.tags[_]
  endswith(container.image, sprintf(":%s", [tag]))
}
```

**Chức năng**:
- Cấm sử dụng các image tags cụ thể (ví dụ: `latest`)
- Bắt buộc phải dùng explicit tag hoặc digest
- Kiểm tra cả containers và initContainers

##### 2. K8sRequiredContainerLimits
```rego
violation[{"msg": msg}] {
  container := containers[_]
  required := input.parameters.limits[_]
  not container.resources.limits[required]
}
```

**Chức năng**:
- Bắt buộc phải set resource limits (cpu, memory)
- Đảm bảo containers không tiêu tốn tài nguyên vô tội vạ

##### 3. K8sDisallowRunAsUserZero
```rego
violation[{"msg": msg}] {
  container := containers[_]
  container.securityContext.runAsUser == 0
}
```

**Chức năng**:
- Cấm chạy container với root user (UID 0)
- Best practice security: run as non-root

##### 4. K8sDisallowHostNetwork
```rego
violation[{"msg": msg}] {
  pod_spec.hostNetwork == true
}
```

**Chức năng**:
- Cấm sử dụng host network
- Tránh pods can thiệp vào network của node

**Sync Wave**: `0` (trong file)

---

#### `gatekeeper/constraints/10-constraints.yaml`
**Mục đích**: Áp dụng các ConstraintTemplate vào namespace `demo` cho Rollout resources

**4 Constraints được tạo**:

##### 1. rollout-disallow-latest-image-tag
```yaml
spec:
  enforcementAction: deny
  match:
    kinds:
      - apiGroups: [argoproj.io]
        kinds: [Rollout]
    namespaces: [demo]
  parameters:
    tags: [latest]
```

**Chức năng**: Từ chối Rollout nếu dùng image tag `latest`

##### 2. rollout-require-container-limits
```yaml
parameters:
  limits:
    - cpu
    - memory
```

**Chức năng**: Bắt buộc Rollout phải set cpu và memory limits

##### 3. rollout-disallow-runasuser-zero
**Chức năng**: Từ chối Rollout nếu chạy với UID 0 (root)

##### 4. rollout-disallow-hostnetwork
**Chức năng**: Từ chối Rollout nếu bật hostNetwork

**Sync Wave**: `1` (trong file)

**Enforcement**: `deny` - Hard block, không cho phép tạo resource vi phạm

---

#### `policies/cluster-image-policy.yaml`
**Mục đích**: Định nghĩa policy xác thực chữ ký số cho container images

```yaml
apiVersion: policy.sigstore.dev/v1beta1
kind: ClusterImagePolicy
metadata:
  name: image-signature-policy
spec:
  images:
    - glob: "ghcr.io/pkhoa011004/w10-api**"
  authorities:
    - key:
        data: |
          -----BEGIN PUBLIC KEY-----
          MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEGZIjYF8vVOWZ...
          -----END PUBLIC KEY-----
```

**Chức năng**:
- Sigstore Policy Controller sử dụng policy này
- Chỉ áp dụng cho images match glob pattern `ghcr.io/pkhoa011004/w10-api**`
- Sử dụng public key nhúng trực tiếp để verify signature
- Nếu signature không hợp lệ hoặc không tồn tại → Block Pod creation

**Public Key**: Cặp với private key được dùng trong CI pipeline để sign images

---

### 3.4 RBAC Configuration

#### `rbac/roles.yaml`
**Mục đích**: Định nghĩa 3 roles với quyền hạn khác nhau

##### Role: developer (namespace-scoped)
```yaml
rules:
- apiGroups: [apps]
  resources: [deployments]
  verbs: [create, get, list, watch, update, patch, delete]
- apiGroups: [""]
  resources: [pods, services]
  verbs: [create, get, list, watch, update, patch, delete]
```

**Quyền hạn**: Toàn quyền quản lý deployments, pods, services trong namespace `demo`

##### ClusterRole: sre (cluster-scoped)
```yaml
rules:
- apiGroups: [""]
  resources: [pods, pods/log]
  verbs: [create, get, list, watch, update, patch, delete]
- apiGroups: [""]
  resources: [pods/exec]
  verbs: [create, get]
```

**Quyền hạn**: 
- Quản lý pods toàn cluster
- Đọc logs
- Exec vào pods để troubleshoot

##### ClusterRole: viewer (cluster-scoped)
```yaml
rules:
- apiGroups: ["*"]
  resources: ["*"]
  verbs: [get, list, watch]
```

**Quyền hạn**: Read-only trên toàn bộ cluster

---

#### `rbac/rolebindings.yaml`
**Mục đích**: Gán users vào roles

##### alice-developer (RoleBinding)
```yaml
subjects:
- kind: User
  name: alice
roleRef:
  kind: Role
  name: developer
```

**User alice**: Có quyền developer trong namespace `demo`

##### bob-sre (ClusterRoleBinding)
```yaml
subjects:
- kind: User
  name: bob
roleRef:
  kind: ClusterRole
  name: sre
```

**User bob**: Có quyền SRE toàn cluster

##### carol-viewer (ClusterRoleBinding)
```yaml
subjects:
- kind: User
  name: carol
roleRef:
  kind: ClusterRole
  name: viewer
```

**User carol**: Read-only toàn cluster

---

### 3.5 External Secrets Configuration

#### `eso/secret-store.yaml`
**Mục đích**: Định nghĩa SecretStore với fake provider (demo only)

```yaml
apiVersion: external-secrets.io/v1beta1
kind: SecretStore
metadata:
  name: fake-store
  namespace: demo
spec:
  provider:
    fake:
      data:
        - key: db-password
          value: "my-super-secret-password-v2"
```

**Chức năng**:
- Fake provider lưu secrets hardcoded trong manifest (KHÔNG dùng production!)
- Trong thực tế sẽ dùng AWS Secrets Manager, Vault, GCP Secret Manager, etc.
- Secrets được refresh theo interval định nghĩa trong ExternalSecret

---

#### `eso/external-secret.yaml`
**Mục đích**: Tạo Kubernetes Secret từ external provider

```yaml
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: db-secret-external
  namespace: demo
spec:
  refreshInterval: "10s"
  secretStoreRef:
    name: fake-store
  target:
    name: db-secret
    creationPolicy: Owner
  data:
    - secretKey: db-password
      remoteRef:
        key: db-password
```

**Chức năng**:
- Tạo Secret `db-secret` trong namespace `demo`
- Refresh mỗi 10 giây
- Secret chứa key `db-password` với value từ SecretStore
- `creationPolicy: Owner` → ESO quản lý lifecycle của Secret

**Kết quả**: Secret `db-secret` được mount vào API pods tại `/etc/secrets/`

---

### 3.6 Application Workload

#### `app-api/rollout.yaml`
**Mục đích**: Định nghĩa Rollout cho API application với canary strategy

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata:
  name: api
  namespace: demo
  annotations:
    argocd.argoproj.io/sync-wave: "0"
spec:
  replicas: 4
```

**Cấu hình Pod Template**:

##### Security Context
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  runAsGroup: 1000
  fsGroup: 1000
containers:
  - securityContext:
      allowPrivilegeEscalation: false
      capabilities:
        drop: [ALL]
```

**Chức năng**: Chạy với non-root user, drop tất cả capabilities

##### Container Spec
```yaml
image: ghcr.io/pkhoa011004/w10-api:0.0.3
env:
  - name: VERSION
    value: "v0.0.3"
  - name: ERROR_RATE
    value: "0"
```

**Environment Variables**:
- `VERSION`: Hiển thị version trong response
- `ERROR_RATE`: Tỷ lệ lỗi giả lập (0-1) để test canary analysis

##### Probes
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 5
readinessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 3
```

##### Resources
```yaml
resources:
  requests:
    cpu: 50m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 128Mi
```

**Tuân thủ**: Gatekeeper constraint yêu cầu phải có limits

##### Volume Mount
```yaml
volumeMounts:
  - name: db-secret-vol
    mountPath: /etc/secrets
    readOnly: true
volumes:
  - name: db-secret-vol
    secret:
      secretName: db-secret
```

**Chức năng**: Mount secret `db-secret` vào `/etc/secrets/db-password`

##### Canary Strategy
```yaml
strategy:
  canary:
    analysis:
      templates:
        - templateName: success-rate
      startingStep: 1
    steps:
      - setWeight: 10
      - pause: {duration: 2m}
      - setWeight: 50
      - pause: {duration: 2m}
      - setWeight: 100
```

**Luồng Canary**:
1. **Step 0**: Deploy canary pods (10% weight)
2. **Step 1**: Chạy Analysis Template - query Prometheus mỗi 30s
   - Nếu success_rate >= 90% → Continue
   - Nếu fail 10 lần liên tiếp → Rollback
3. **Pause 2 phút**
4. **Step 2**: Scale canary lên 50%
5. **Chạy Analysis tiếp**
6. **Pause 2 phút**
7. **Step 3**: Promote canary lên 100% (hoàn tất)

**Sync Wave**: `0` (deploy pods trước)

---

#### `app-api/service.yaml`
**Mục đích**: Expose API pods

```yaml
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: demo
  annotations:
    argocd.argoproj.io/sync-wave: "1"
spec:
  selector:
    app: api
  ports:
    - name: http
      port: 80
      targetPort: 8080
```

**Chức năng**:
- ClusterIP service expose API pods
- Port 80 → targetPort 8080
- Selector `app: api` match tất cả pods (cả stable và canary)

**Sync Wave**: `1` (sau khi Rollout đã tạo pods)

---

#### `app-api/servicemonitor.yaml`
**Mục đích**: Cấu hình Prometheus scrape metrics từ API

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: api
  namespace: demo
  annotations:
    argocd.argoproj.io/sync-wave: "2"
spec:
  selector:
    matchLabels:
      app: api
  endpoints:
    - port: http
      path: /metrics
      interval: 15s
```

**Chức năng**:
- Prometheus tự động discover ServiceMonitor này
- Scrape `/metrics` endpoint mỗi 15 giây
- Metrics được lưu vào Prometheus TSDB

**Sync Wave**: `2` (sau Service)

---

### 3.7 Analysis & Alerting

#### `app-analysis/analysis-template.yaml`
**Mục đích**: Template phân tích success rate cho canary validation

```yaml
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata:
  name: success-rate
  namespace: demo
spec:
  metrics:
    - name: success-rate
      interval: 30s
      successCondition: result >= 0.90
      failureLimit: 10
      provider:
        prometheus:
          address: http://kube-prometheus-stack-prometheus.monitoring.svc:9090
          query: |
            scalar(
              sum(rate(flask_http_request_duration_seconds_count{namespace="demo",job="api",status!~"5.."}[2m]))
              /
              sum(rate(flask_http_request_duration_seconds_count{namespace="demo",job="api"}[2m]))
            )
```

**Hoạt động**:
- **Interval**: Chạy query mỗi 30 giây
- **Query**: Tính success rate từ metrics `flask_http_request_duration_seconds_count`
  - Numerator: Requests không phải 5xx (status!~"5..")
  - Denominator: Tất cả requests
  - Rate window: 2 phút
- **Success Condition**: result >= 0.90 (90%)
- **Failure Limit**: Cho phép fail tối đa 10 lần liên tiếp trước khi rollback

**Khi Analysis Fail**:
- Rollout tự động rollback về stable version
- Canary pods bị xóa
- Traffic 100% về stable

---

#### `app-alert/prometheus-rules.yaml`
**Mục đích**: Định nghĩa recording rules và alerting rules

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: slo-alerts
  namespace: monitoring
spec:
  groups:
    - name: slo
      interval: 30s
      rules:
        # Recording Rule
        - record: api:success_rate:5m
          expr: |
            sum(rate(flask_http_request_duration_seconds_count{status!~"5.."}[5m]))
            /
            sum(rate(flask_http_request_duration_seconds_count[5m]))

        # Alerting Rule
        - alert: SLOViolation
          expr: api:success_rate:5m < 0.95
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "API SLO Violation"
            description: "Success rate {{ $value | humanizePercentage }} (SLO: 95%)"
```

**Recording Rule**: `api:success_rate:5m`
- Pre-compute success rate với 5 phút window
- Lưu thành time series mới để query nhanh hơn

**Alerting Rule**: `SLOViolation`
- Fire khi success rate < 95% trong 2 phút
- Severity: critical
- Gửi email qua Alertmanager

**Khác biệt với Analysis**:
- **Analysis**: Ngưỡng 90%, dùng để validate canary deployment
- **Alert**: Ngưỡng 95%, dùng để monitor SLO của production

---

#### `app-alert/email-secret.yaml.example`
**Mục đích**: Template cho Gmail App Password secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: alertmanager-email
  namespace: monitoring
type: Opaque
stringData:
  password: your-gmail-app-password-16-chars
```

**Lưu ý**:
- File này được `.argocdignore` → KHÔNG được ArgoCD quản lý
- Phải manually apply: `kubectl apply -f email-secret.yaml`
- Cần tạo Gmail App Password tại: https://myaccount.google.com/apppasswords
- Secret này được mount vào Alertmanager pod

---

### 3.8 Application Source Code

#### `src/api/app.py`
**Mục đích**: Flask API application với metrics và error injection

```python
from flask import Flask, jsonify
from prometheus_flask_exporter import PrometheusMetrics

app = Flask(__name__)
PrometheusMetrics(app)  # Tự động thêm /metrics endpoint

ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))
VERSION = os.getenv("VERSION", "v1")
```

**Endpoints**:

##### `GET /`
```python
@app.get("/")
def index():
    # Đọc secret từ file
    db_password = read_from_file("/etc/secrets/db-password")
    
    # Random error injection
    if random.random() < ERROR_RATE:
        return jsonify(error="injected", version=VERSION), 500
    
    return jsonify(ok=True, version=VERSION, db_password=db_password)
```

**Chức năng**:
- Đọc `db-password` từ mounted secret
- Inject lỗi 500 theo tỷ lệ `ERROR_RATE`
- Trả về version để verify deployment

##### `GET /healthz`
```python
@app.get("/healthz")
def healthz():
    return "ok", 200
```

**Chức năng**: Health check cho liveness/readiness probes

##### `GET /metrics`
- Tự động được tạo bởi `prometheus_flask_exporter`
- Expose metrics:
  - `flask_http_request_duration_seconds_count`: Request count với labels (status, method, path)
  - `flask_http_request_duration_seconds_sum`: Total duration
  - `flask_http_request_duration_seconds_bucket`: Histogram buckets

---

#### `src/api/Dockerfile`
**Mục đích**: Container image cho API

```dockerfile
FROM python:3.13-alpine
RUN pip install flask prometheus-flask-exporter
COPY app.py /app/app.py
WORKDIR /app
ENV FLASK_APP=app.py
EXPOSE 8080
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
```

**Đặc điểm**:
- Base image: `python:3.13-alpine` (nhỏ gọn)
- Dependencies: `flask`, `prometheus-flask-exporter`
- Port: 8080
- **Lưu ý**: Image này chạy với root user mặc định, nhưng Rollout override bằng `runAsUser: 1000`

---


## 4. Sơ Đồ Kiến Trúc Chi Tiết

### 4.1 Sơ Đồ Deployment với Sync Waves

```
Thời gian ──────────────────────────────────────────────────▶

Sync Wave -2:
┌─────────────────┐
│   Gatekeeper    │ (OPA admission controller)
└─────────────────┘

Sync Wave -1:
┌────────────────┐  ┌─────────────────────┐  ┌──────────────────┐
│   Namespace    │  │ Policy Controller   │  │  ESO Operator    │
│     demo       │  │    (Sigstore)       │  │                  │
└────────────────┘  └─────────────────────┘  └──────────────────┘

Sync Wave 0:
┌────────────────┐  ┌─────────────────┐  ┌──────────────────────┐
│ Argo Rollouts  │  │  Gatekeeper     │  │  ESO Config          │
│   Controller   │  │  Constraints    │  │  (SecretStore)       │
└────────────────┘  └─────────────────┘  └──────────────────────┘

Sync Wave 1:
┌─────────────────┐  ┌──────────────────┐  ┌─────────────────┐
│ ClusterImage    │  │ Analysis         │  │  RBAC           │
│ Policy          │  │ Template         │  │  Roles          │
└─────────────────┘  └──────────────────┘  └─────────────────┘

┌─────────────────────────────────────┐
│  Prometheus Rules (Alert Rules)     │
└─────────────────────────────────────┘

Sync Wave 2:
┌─────────────────────────────────────────────┐
│        Prometheus Stack                     │
│  (Prometheus + Alertmanager + Grafana)      │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│           API Application                   │
│  ┌───────────────────────────────────┐      │
│  │ Wave 0: Rollout (Pods)            │      │
│  ├───────────────────────────────────┤      │
│  │ Wave 1: Service                   │      │
│  ├───────────────────────────────────┤      │
│  │ Wave 2: ServiceMonitor            │      │
│  └───────────────────────────────────┘      │
└─────────────────────────────────────────────┘
```

### 4.2 Sơ Đồ Traffic Flow trong Canary Deployment

```
┌─────────────────────────────────────────────────────────┐
│                 Service: api (port 80)                  │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┴────────────┐
        │                        │
        ▼                        ▼
┌────────────────┐      ┌────────────────┐
│  Stable Pods   │      │  Canary Pods   │
│  (v0.0.2)      │      │  (v0.0.3)      │
│                │      │                │
│  90% traffic   │      │  10% traffic   │
│  (step 1)      │      │  (step 1)      │
└────────────────┘      └────────────────┘
        │                        │
        │                        │
        └───────────┬────────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │   ServiceMonitor      │
        │   scrape /metrics     │
        └───────────┬───────────┘
                    │
                    ▼
        ┌───────────────────────┐
        │     Prometheus        │
        │  Store metrics TSDB   │
        └───────────┬───────────┘
                    │
                    ▼
        ┌──────────────────────────────┐
        │    AnalysisRun Instance      │
        │  Query Prometheus every 30s  │
        │                              │
        │  success_rate >= 90%?        │
        └───────────┬──────────────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
       [YES]                 [NO]
         │                     │
         ▼                     ▼
    Continue            ┌────────────┐
    to 50%              │  Rollback  │
    traffic             │  to Stable │
                        └────────────┘
```

### 4.3 Sơ Đồ Security Pipeline

```
┌───────────────────────────────────────────────────────┐
│            GitHub Actions CI Pipeline                 │
│                                                       │
│  1. Git Push → Trigger Workflow                      │
│                                                       │
│  2. ┌─────────────────────────────────┐             │
│     │  Trivy Vulnerability Scan       │             │
│     │  Scan: HIGH,CRITICAL CVEs       │             │
│     └──────────┬──────────────────────┘             │
│                │                                     │
│       ┌────────┴────────┐                           │
│       │                 │                           │
│    [FAIL]            [PASS]                         │
│   ⛔ Stop          ✅ Continue                        │
│                       │                             │
│  3. ┌─────────────────▼──────────────┐             │
│     │  Build & Push to GHCR          │             │
│     │  ghcr.io/user/w10-api:0.0.3    │             │
│     └─────────────────┬───────────────┘             │
│                       │                             │
│  4. ┌─────────────────▼──────────────┐             │
│     │  Cosign Sign Image             │             │
│     │  cosign sign --key private.key │             │
│     │  → Tạo .sig artifact           │             │
│     └─────────────────┬───────────────┘             │
│                       │                             │
│  5. Update rollout.yaml → Git Push                  │
└───────────────────────┼───────────────────────────────┘
                        │
                        ▼
           ┌────────────────────────┐
           │   GitHub Repository    │
           │   (Updated manifest)   │
           └────────────┬───────────┘
                        │
                        ▼
           ┌────────────────────────┐
           │   ArgoCD Sync          │
           └────────────┬───────────┘
                        │
                        ▼
           ┌─────────────────────────────────────┐
           │    Kubernetes API Server            │
           │                                     │
           │  Pod Creation Request               │
           └────────────┬────────────────────────┘
                        │
                        ▼
           ┌─────────────────────────────────────┐
           │  Sigstore Policy Controller         │
           │  (Admission Webhook)                │
           │                                     │
           │  1. Read ClusterImagePolicy         │
           │  2. Extract public key              │
           │  3. Download .sig from GHCR         │
           │  4. Verify signature                │
           └────────────┬────────────────────────┘
                        │
              ┌─────────┴─────────┐
              │                   │
          [Valid]            [Invalid]
              │                   │
              ▼                   ▼
      ✅ Allow Pod         ⛔ Reject Pod
         Creation            Creation
```

### 4.4 Sơ Đồ Monitoring & Alerting Flow

```
┌──────────────────────────────────────────────────┐
│              API Pods                            │
│                                                  │
│  ┌────────────┐  ┌────────────┐                │
│  │ Stable Pod │  │ Canary Pod │                │
│  │  :8080     │  │  :8080     │                │
│  └─────┬──────┘  └─────┬──────┘                │
│        │                │                       │
│        └───────┬────────┘                       │
│            GET /metrics                         │
│     (prometheus_flask_exporter)                 │
└────────────────┼───────────────────────────────┘
                 │
                 │ ServiceMonitor scrapes every 15s
                 ▼
┌─────────────────────────────────────────────────┐
│          Prometheus Server                      │
│                                                 │
│  1. Scrape metrics                             │
│  2. Store in TSDB                              │
│  3. ┌────────────────────────────────┐        │
│     │ Recording Rule (every 30s)     │        │
│     │ api:success_rate:5m            │        │
│     │   = success_count / total      │        │
│     └────────────┬───────────────────┘        │
│                  │                            │
│  4. ┌────────────▼───────────────────┐       │
│     │  Alerting Rule Evaluation      │       │
│     │  api:success_rate:5m < 0.95?   │       │
│     └────────────┬───────────────────┘       │
│                  │                           │
│         ┌────────┴────────┐                 │
│         │                 │                 │
│      [NO]              [YES]                │
│     Normal           for 2m                 │
│                         │                   │
│                         ▼                   │
│              Alert: SLOViolation            │
│              severity: critical             │
└─────────────────────────┼──────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────┐
│         Alertmanager                         │
│                                              │
│  1. Receive alert from Prometheus           │
│  2. Group by: alertname, severity           │
│  3. Route to: email-notifications           │
│  4. ┌────────────────────────────┐         │
│     │  Email Config              │         │
│     │  to: phuockhoamai@gmail    │         │
│     │  from: phuockhoamai@gmail  │         │
│     │  smarthost: smtp.gmail:587 │         │
│     │  auth_password: (secret)   │         │
│     └────────────┬─────────────────┘         │
│                  │                           │
└──────────────────┼───────────────────────────┘
                   │
                   ▼
          ┌────────────────┐
          │  Gmail SMTP    │
          │  Send Email    │
          └────────────────┘
                   │
                   ▼
          📧 Email received:
          🚨 [W10 Demo Alert] 
             SLOViolation - critical
```

---

## 5. Kịch Bản Hoạt Động

### 5.1 Kịch Bản 1: Deploy Version Mới Thành Công

**Điều kiện**: ERROR_RATE = 0 (success rate = 100%)

```
Thời gian  │  Trạng thái                                      │  Traffic Split
═══════════╪══════════════════════════════════════════════════╪════════════════
T+0        │ Developer push code v0.0.3 với ERROR_RATE=0     │
           │                                                  │
T+1        │ GitHub Actions:                                 │
           │ - Trivy scan: PASS ✅                            │
           │ - Build image                                   │
           │ - Cosign sign                                   │
           │ - Update rollout.yaml → Git push                │
           │                                                  │
T+2        │ ArgoCD detect changes → Sync                    │
           │                                                  │
T+3        │ Kubernetes API:                                 │
           │ - Policy Controller verify signature ✅          │
           │ - Create canary pods (v0.0.3)                   │
           │                                                  │
T+4        │ Rollout: Step 1 - 10% canary                   │  Stable 90%
           │                                                  │  Canary 10%
           │                                                  │
T+4:30     │ AnalysisRun starts                              │
           │ - Query Prometheus: success_rate = 100%         │
           │ - Result >= 90% ✅ PASS                          │
           │                                                  │
T+5:00     │ Analysis query #2: 100% ✅                       │
T+5:30     │ Analysis query #3: 100% ✅                       │
           │ ... (tiếp tục mỗi 30s)                          │
           │                                                  │
T+6        │ Pause 2m completed → Continue                   │
           │                                                  │
T+6:05     │ Rollout: Step 2 - 50% canary                   │  Stable 50%
           │ - Scale up canary pods                          │  Canary 50%
           │ - Analysis continues                            │
           │                                                  │
T+8        │ Pause 2m completed → Continue                   │
           │                                                  │
T+8:05     │ Rollout: Step 3 - 100% canary (PROMOTE)        │  Canary 100%
           │ - Scale down stable pods                        │
           │ - Canary becomes new stable                     │
           │                                                  │
T+9        │ Deployment completed ✅                          │  Stable 100%
           │ - Old pods terminated                           │  (v0.0.3)
           │ - Version v0.0.3 fully deployed                 │
```

**Kết quả**: Deployment thành công, không có alert email

---

### 5.2 Kịch Bản 2: Deploy Fail và Auto Rollback

**Điều kiện**: ERROR_RATE = 0.15 (success rate = 85% < 90%)

```
Thời gian  │  Trạng thái                                      │  Traffic Split
═══════════╪══════════════════════════════════════════════════╪════════════════
T+0        │ Developer push code v0.0.4 với ERROR_RATE=0.15  │
           │                                                  │
T+1        │ GitHub Actions: Build & Sign ✅                  │
           │                                                  │
T+2        │ ArgoCD sync → Create canary pods                │
           │                                                  │
T+3        │ Rollout: Step 1 - 10% canary                   │  Stable 90%
           │                                                  │  Canary 10%
           │                                                  │
T+3:30     │ AnalysisRun #1:                                 │
           │ - Query: success_rate = 85%                     │
           │ - 85% < 90% ❌ FAIL (failure 1/10)               │
           │                                                  │
T+4:00     │ AnalysisRun #2:                                 │
           │ - Query: success_rate = 85%                     │
           │ - ❌ FAIL (failure 2/10)                         │
           │                                                  │
T+4:30     │ AnalysisRun #3: ❌ FAIL (failure 3/10)           │
T+5:00     │ AnalysisRun #4: ❌ FAIL (failure 4/10)           │
...        │ ...                                             │
T+8:00     │ AnalysisRun #10: ❌ FAIL (failure 10/10)         │
           │                                                  │
           │ 🚨 FAILURE LIMIT REACHED → ROLLBACK             │
           │                                                  │
T+8:10     │ Rollout Controller:                             │  Stable 100%
           │ - Abort rollout                                 │  (v0.0.3)
           │ - Scale down canary pods                        │
           │ - Restore 100% traffic to stable                │
           │                                                  │
T+8:30     │ Rollback completed ✅                            │  Stable 100%
           │ - Canary pods terminated                        │  (v0.0.3)
           │ - System back to stable v0.0.3                  │
           │ - Version v0.0.4 never fully deployed           │
```

**Kết quả**: 
- Deployment tự động rollback
- Alert email CÓ THỂ gửi nếu lỗi kéo dài đủ 2 phút (success_rate < 95%)
- Không ảnh hưởng đến 90% traffic stable

---

### 5.3 Kịch Bản 3: Deploy Thành Công Nhưng Vi Phạm SLO (Trigger Alert)

**Điều kiện**: ERROR_RATE = 0.07 (success rate = 93%)

```
Thời gian  │  Trạng thái                                      │  Alert Status
═══════════╪══════════════════════════════════════════════════╪════════════════
T+0        │ Deploy v0.0.5 với ERROR_RATE=0.07               │
           │                                                  │
T+3        │ Canary 10% deployed                             │
           │                                                  │
T+3:30     │ AnalysisRun:                                    │
           │ - success_rate = 93%                            │
           │ - 93% >= 90% ✅ Analysis PASS                    │  Normal
           │ - BUT: 93% < 95% ⚠️ SLO Violation               │
           │                                                  │
T+4:00     │ Prometheus Alert Rule:                          │
           │ - api:success_rate:5m = 93%                     │
           │ - 93% < 95% (threshold)                         │  Pending
           │ - Alert state: PENDING                          │  (for < 2m)
           │                                                  │
T+5:00     │ Alert continues: 93% < 95%                      │  Pending
           │                                                  │  (for 1m)
T+6:00     │ Alert duration reached 2m threshold             │  🚨 FIRING
           │ → State: PENDING → FIRING                       │
           │                                                  │
T+6:10     │ Alertmanager:                                   │
           │ - Receive alert "SLOViolation"                  │
           │ - Group by: alertname, severity                 │
           │ - Route to: email-notifications                 │
           │                                                  │
T+6:15     │ Email sent via Gmail SMTP ✉️                     │
           │ To: phuockhoamai@gmail.com                      │
           │ Subject: 🚨 [W10 Demo Alert]                    │
           │          SLOViolation - critical                │
           │ Body: Success rate 93% (SLO: 95%)              │
           │                                                  │
T+8        │ Rollout continues (Analysis passed)             │  🚨 FIRING
           │ - 50% canary deployed                           │
           │                                                  │
T+10       │ Rollout completes - 100% v0.0.5                 │  🚨 FIRING
           │ Alert still firing (success rate still 93%)     │
           │                                                  │
T+15       │ Alert resolved when:                            │  ✅ Resolved
           │ - Team fixes ERROR_RATE → 0                     │
           │ - success_rate recovers > 95%                   │
           │ - Resolution email sent                         │
```

**Kết quả**:
- ✅ Deployment hoàn tất (pass canary analysis với ngưỡng 90%)
- 🚨 Alert email gửi đi (vi phạm SLO với ngưỡng 95%)
- Cần can thiệp để khôi phục success rate

---

### 5.4 Kịch Bản 4: Deploy Bị Chặn - Image Chưa Được Ký Số

**Điều kiện**: Deploy image không có chữ ký hợp lệ

```
Thời gian  │  Trạng thái                                      │  Result
═══════════╪══════════════════════════════════════════════════╪════════════
T+0        │ Developer push code v0.0.6                      │
           │                                                  │
T+1        │ GitHub Actions:                                 │
           │ - Trivy scan: PASS ✅                            │
           │ - Build & Push image ✅                          │
           │ - ⚠️ SKIP cosign sign (bị lỗi hoặc cố ý skip)    │
           │ - Update rollout.yaml → Git push                │
           │                                                  │
T+2        │ ArgoCD detect changes → Sync                    │
           │                                                  │
T+3        │ Kubernetes API Server:                          │
           │ - Receive Pod creation request                  │
           │ - Forward to admission webhooks                 │
           │                                                  │
           │ Sigstore Policy Controller:                     │
           │ 1. Check ClusterImagePolicy                     │
           │    - Match: ghcr.io/.../w10-api:0.0.6 ✅        │
           │ 2. Download .sig artifact from GHCR             │
           │    - .sig not found ❌                           │
           │ 3. Signature verification: FAILED               │
           │                                                  │
T+3:05     │ Admission Response: DENY ⛔                      │
           │                                                  │
           │ Error Message:                                  │
           │ "failed policy: image-signature-policy          │
           │  ghcr.io/pkhoa011004/w10-api:0.0.6             │
           │  signature verification failed"                 │
           │                                                  │
T+3:10     │ ArgoCD Application Status:                      │
           │ - Sync Status: OutOfSync                        │
           │ - Health: Degraded ⚠️                            │
           │ - Sync Error: admission webhook denied          │
           │                                                  │
T+3:15     │ Rollout Status:                                 │
           │ - Pods: 0/4 Ready                               │
           │ - Canary pods FAILED to create                  │
           │ - Stable pods continue running (no change)      │
           │                                                  │
Result     │ 🛑 DEPLOYMENT BLOCKED                            │ BLOCKED
           │ - No pods created                               │
           │ - System remains at old version                 │
           │ - Need to fix: re-run CI with cosign sign       │
```

**Kết quả**:
- ⛔ Deployment hoàn toàn bị chặn
- Không có pod mới nào được tạo
- Hệ thống vẫn chạy stable version an toàn
- Cần fix CI pipeline và re-deploy

---

### 5.5 Kịch Bản 5: Deploy Bị Chặn - Vi Phạm Gatekeeper Policy

**Điều kiện**: Rollout sử dụng image tag `latest` (vi phạm constraint)

```
Thời gian  │  Trạng thái                                      │  Result
═══════════╪══════════════════════════════════════════════════╪════════════
T+0        │ Developer sửa rollout.yaml:                     │
           │ image: ghcr.io/.../w10-api:latest ⚠️             │
           │ Git push                                        │
           │                                                  │
T+1        │ ArgoCD detect changes → Attempt sync            │
           │                                                  │
T+2        │ Kubernetes API Server:                          │
           │ - Receive Rollout update request                │
           │ - Forward to admission webhooks                 │
           │                                                  │
           │ Gatekeeper Admission Webhook:                   │
           │ 1. Check all ConstraintTemplates                │
           │ 2. Evaluate K8sDisallowedImageTags              │
           │    - Match: kind=Rollout, namespace=demo ✅     │
           │    - Check constraint parameters:               │
           │      tags: [latest]                             │
           │    - Image ends with ":latest"? YES ❌          │
           │                                                  │
T+2:05     │ Violation detected:                             │
           │ "container <api> uses disallowed image          │
           │  tag <latest>"                                  │
           │                                                  │
           │ Admission Response: DENY ⛔                      │
           │ enforcementAction: deny                         │
           │                                                  │
T+2:10     │ ArgoCD Application Status:                      │
           │ - Sync Status: Failed                           │
           │ - Error: admission webhook                      │
           │   "validation.gatekeeper.sh" denied             │
           │                                                  │
Result     │ 🛑 DEPLOYMENT BLOCKED BY POLICY                  │ BLOCKED
           │ - Must use explicit tag (e.g., :0.0.3)          │
           │ - Cannot use :latest in production              │
           │ - Fix manifest and re-deploy                    │
```

**Các Policy Khác Cũng Được Enforce**:

```
Policy                      │  Violation Example                   │  Enforcement
════════════════════════════╪══════════════════════════════════════╪══════════════
DisallowedImageTags         │  image: app:latest                   │  ⛔ DENY
                            │  image: app (no tag)                 │  ⛔ DENY
────────────────────────────┼──────────────────────────────────────┼──────────────
RequiredContainerLimits     │  resources:                          │  ⛔ DENY
                            │    # missing limits                  │
────────────────────────────┼──────────────────────────────────────┼──────────────
DisallowRunAsUserZero       │  securityContext:                    │  ⛔ DENY
                            │    runAsUser: 0                      │
────────────────────────────┼──────────────────────────────────────┼──────────────
DisallowHostNetwork         │  spec:                               │  ⛔ DENY
                            │    hostNetwork: true                 │
```

---

## 6. Tổng Kết

### 6.1 Bảng Tóm Tắt Sync Waves

| Wave | Components | Mục Đích | Namespace |
|------|-----------|----------|-----------|
| -2 | Gatekeeper | OPA admission controller | gatekeeper-system |
| -1 | app-common, policy-controller, ESO | Infrastructure sớm | demo, cosign-system, external-secrets |
| 0 | k8s-rollout, gatekeeper-constraints, eso-config | Controllers & configs | argo-rollouts, gatekeeper-system, demo |
| 1 | policies, app-analysis, app-alert, rbac | Application configs | cosign-system, demo, monitoring |
| 2 | k8s-prometheus, app-api | Monitoring & workload | monitoring, demo |

### 6.2 Tóm Tắt Các File YAML Theo Chức Năng

#### GitOps Management
- `argocd/root.yaml`: App-of-Apps root
- `argocd/apps/*.yaml`: Child applications (13 files)

#### Security & Policy
- `policies/cluster-image-policy.yaml`: Image signature verification
- `gatekeeper/constraints/*.yaml`: OPA policies
- `rbac/*.yaml`: RBAC roles & bindings

#### Application Workload
- `app-api/*.yaml`: API Rollout + Service + ServiceMonitor
- `app-analysis/*.yaml`: AnalysisTemplate for canary
- `app-alert/*.yaml`: PrometheusRule for alerts
- `app-common/*.yaml`: Namespace

#### Infrastructure
- `eso/*.yaml`: External Secrets config
- Source code: `src/api/*`

### 6.3 Key Takeaways

1. **GitOps**: Mọi thay đổi đều qua Git → ArgoCD tự động sync
2. **Security**: 
   - Trivy scan vulnerabilities
   - Cosign sign images
   - Policy Controller verify signatures
   - Gatekeeper enforce best practices
3. **Progressive Delivery**: Canary với automated analysis
4. **Observability**: Prometheus metrics → Analysis & Alerts
5. **Self-Healing**: ArgoCD tự động sửa configuration drift

### 6.4 Troubleshooting Common Issues

| Issue | Root Cause | Solution |
|-------|------------|----------|
| Pod không tạo được | Image signature invalid | Re-run CI với cosign sign |
| Rollout bị reject | Vi phạm Gatekeeper policy | Sửa manifest tuân thủ policy |
| Canary rollback | Success rate < 90% | Giảm ERROR_RATE environment |
| Không nhận alert email | Secret chưa được tạo | Apply email-secret.yaml manually |
| ArgoCD OutOfSync | Drift hoặc manual changes | Enable auto-sync hoặc manual sync |

---

**Tài liệu được tạo dựa trên phân tích hệ thống GitOps với ArgoCD, Argo Rollouts, Prometheus, Gatekeeper và Sigstore.**
