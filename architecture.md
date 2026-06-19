# Sơ đồ Kiến trúc Luồng Quét Lỗi, Ký Số và Xác Thực Image (Trivy + Cosign + Sigstore)

Tài liệu này mô tả chi tiết sơ đồ kiến trúc hệ thống, bao gồm các luồng chạy chính và cách thức liên kết giữa các thành phần từ khi lập trình viên đẩy mã nguồn lên Git cho tới khi ứng dụng được xác thực và khởi chạy trên Kubernetes.

---

## 1. Sơ đồ kiến trúc (Mermaid Diagram)

Dưới đây là sơ đồ luồng dữ liệu và tương tác giữa các hệ thống:

```mermaid
graph TD
    %% Định nghĩa các lớp CSS và màu sắc
    classDef git fill:#F05032,stroke:#333,stroke-width:2px,color:#fff;
    classDef ci fill:#2088FF,stroke:#333,stroke-width:2px,color:#fff;
    classDef registry fill:#24292E,stroke:#333,stroke-width:2px,color:#fff;
    classDef argocd fill:#F3C63F,stroke:#333,stroke-width:2px,color:#111;
    classDef k8s fill:#326CE5,stroke:#333,stroke-width:2px,color:#fff;
    classDef security fill:#00C853,stroke:#333,stroke-width:2px,color:#fff;

    %% Thành phần & Tương tác
    Developer[Lập trình viên] -->|1. Git Push Code| GitHubRepo((GitHub Repository)):::git
    
    subgraph CI_Pipeline ["GitHub Actions CI Pipeline"]
        Checkout[Checkout Code] --> BuildLocal[Build Local Docker Image]
        BuildLocal --> TrivyScan{Trivy Scan CVEs?}:::security
        
        %% Nhánh quyết định của Trivy
        TrivyScan -->|Có lỗi HIGH/CRITICAL| FailPipeline[Pipeline Bị Lỗi / Dừng lại]:::security
        TrivyScan -->|Sạch lỗi hoặc Ngoại lệ .trivyignore| BuildPush[Build & Push Image lên GHCR]
        
        BuildPush --> InstallCosign[Cài đặt Cosign]
        InstallCosign --> CosignSign[Ký số Image bằng Private Key]
    end
    
    GitHubRepo -->|2. Kích hoạt CI Workflow| Checkout
    
    %% Tương tác với Container Registry
    BuildPush -->|3a. Đẩy Container Image| GHCR[GitHub Container Registry - GHCR]:::registry
    CosignSign -->|3b. Đẩy Chữ ký số .sig| GHCR
    CosignSign -->|4. Commit & Đẩy cập nhật Rollout Version| GitHubRepo
    
    %% Đồng bộ GitOps qua ArgoCD
    subgraph GitOps ["ArgoCD GitOps Sync"]
        ArgoCD[ArgoCD Controller]:::argocd -->|5. Theo dõi thay đổi Git| GitHubRepo
        ArgoCD -->|6. Đồng bộ tài nguyên lên K8s| K8sCluster[Kubernetes Cluster]:::k8s
    end
    
    %% Luồng xác thực Admission Controller trên K8s
    subgraph Kubernetes_Cluster ["Kubernetes Cluster Namespace: demo"]
        APIServer[K8s API Server]:::k8s
        PolicyController[Sigstore Policy Controller]:::security
        CIP[ClusterImagePolicy]:::security
        Workload[Khởi tạo Pods API thành công]:::k8s
        
        APIServer -->|7. Chặn yêu cầu tạo Pod| PolicyController
        PolicyController -->|8. Lấy khóa công khai xác thực| CIP
        PolicyController -->|9. Tải Image và Chữ ký số để đối chiếu| GHCR
        
        PolicyController -->|10a. Chữ ký hợp lệ| Workload
        PolicyController -->|10b. Chữ ký không hợp lệ/Không có| Reject[Từ chối tạo Pod / Block]:::security
    end
    
    K8sCluster -.-> APIServer
```

---

## 2. Giải thích chi tiết các Luồng Chạy (Flow Details)

Kiến trúc bao gồm **3 luồng chính** liên kết chặt chẽ với nhau:

### Luồng 1: Quy trình CI & Bảo mật hình ảnh (CI & Vulnerability Scan)
1. **Developer** commit code và push lên **GitHub Repository**.
2. GitHub Actions khởi chạy và bắt đầu quy trình build:
   - **Build Local Image**: Image được build cục bộ trên Runner trước.
   - **Trivy Scan**: Quét các lỗi bảo mật có mức độ `HIGH,CRITICAL`. Nếu phát hiện lỗi và lỗi đó không nằm trong danh sách bỏ qua của tệp `.trivyignore` (chứa ngoại lệ có thời hạn), pipeline sẽ lập tức bị báo đỏ và dừng lại.
   - **Push Registry**: Nếu vượt qua Trivy, image chính thức được build lại và đẩy lên **GHCR**.
   - **Cosign Sign**: Cosign sử dụng `COSIGN_PRIVATE_KEY` và `COSIGN_PASSWORD` được lưu trữ an toàn trong GitHub Secrets để thực hiện ký số lên image vừa đẩy lên, sau đó đẩy tệp chữ ký (dưới định dạng OCI artifact `.sig`) lên GHCR.
   - **Version Bump**: CI tự động cập nhật tag image mới vào cấu hình ứng dụng (`rollout.yaml`) và đẩy ngược lại mã nguồn lên Git.

### Luồng 2: Quy trình GitOps & Khai báo chính sách (ArgoCD & Policy Sync)
1. **ArgoCD** liên tục lắng nghe thay đổi của GitHub Repository.
2. Khi phát hiện thay đổi (bao gồm cả cập nhật chính sách hoặc cập nhật phiên bản image mới), ArgoCD thực hiện đồng bộ:
   - Đồng bộ **Sigstore Policy Controller** (Helm Chart) cài đặt webhook và tài nguyên giám sát.
   - Đồng bộ cấu hình **ClusterImagePolicy** chứa khóa công khai (`cosign.pub`) tương ứng của bạn.
   - Đồng bộ ứng dụng Rollout phiên bản mới lên Namespace `demo`.

### Luồng 3: Quy trình Xác thực deploy (Kubernetes Admission Verification)
1. Khi ArgoCD yêu cầu triển khai hoặc cập nhật Pod trong namespace `demo` (đã được gắn nhãn kích hoạt `policy.sigstore.dev/include: "true"`):
   - Yêu cầu tạo Pod được gửi tới **K8s API Server**.
   - API Server chuyển tiếp yêu cầu đến **Sigstore Policy Controller** thông qua cơ chế *Mutating/Validating Admission Webhook*.
2. Policy Controller đọc cấu hình quy định tại **ClusterImagePolicy**:
   - Xác định xem image của Pod đang dùng có khớp với mẫu quy định trong chính sách (`ghcr.io/pkhoa011004/w10-api*`) hay không.
   - Truy vấn lên **GHCR** để tải về tệp chữ ký số `.sig` đi kèm với image đó.
   - Sử dụng khóa công khai (`cosign.pub`) nhúng trực tiếp trong chính sách để xác thực chữ ký.
3. Ra quyết định:
   - **Thành công (Valid)**: Chấp thuận yêu cầu, API Server cho phép tạo và chạy Pod trong cụm.
   - **Thất bại (Invalid/Missing)**: Reject và trả về thông báo lỗi cấm chạy pod chưa được ký số an toàn.
