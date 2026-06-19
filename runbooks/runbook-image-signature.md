# Hướng Dẫn: Xác Thực Chữ Ký Container Image & Khắc Phục Sự Cố

## 1. Tổng quan
Tài liệu hướng dẫn này giải thích quy trình ký số container image, cách **Sigstore Policy Controller** thực thi chính sách xác thực chữ ký trên cụm Kubernetes và cách điều tra, khắc phục các sự cố triển khai bị chặn bởi admission controller này.

---

## 2. Quy Trình Xác Thực Chữ Ký Ảnh (Image Verification Workflow)
1. **CI Pipeline Build & Ký số**: GitHub Actions tiến hành build image, chạy quét lỗi Trivy, đẩy lên registry GHCR, và sử dụng khóa riêng tư (Private Key) để ký số lên image thông qua công cụ Cosign.
2. **Kiểm soát Truy cập Cụm (Cluster Admission Control)**: 
   - Sigstore Policy Controller lắng nghe tất cả các yêu cầu tạo Pod trên cụm.
   - Đối chiếu image với cấu hình `ClusterImagePolicy` (nơi chứa khóa công khai - Public Key).
   - Nếu namespace của Pod có chứa nhãn kích hoạt `policy.sigstore.dev/include: "true"`, controller sẽ kiểm tra xem image đó có chữ ký số hợp lệ khớp với khóa công khai hay không.
   - Mọi container image không có chữ ký số hoặc chữ ký không hợp lệ đều bị chặn (reject).

---

## 3. Cách Bật Thực Thi Trên Namespace
Để tránh việc chặn các lần deploy khởi đầu khi chưa cấu hình xong khoá, nhãn thực thi sẽ tạm thời bị comment trong quá trình bootstrap cụm. Khi image đầu tiên được ký số thành công và đẩy lên GHCR:

Bật tính năng xác thực bằng cách bỏ comment nhãn `policy.sigstore.dev/include: "true"` trong file [app-common/demo-namespace.yaml](file:///d:/GitHub/rbac_admission/app-common/demo-namespace.yaml) hoặc gán trực tiếp qua CLI:
```bash
kubectl label ns demo policy.sigstore.dev/include=true --overwrite
```

---

## 4. Các Kịch Bản Thử Nghiệm (Test Scenarios)

### Kịch bản A: Triển khai Image đã Ký số (Happy Path)
1. Thực hiện đẩy thay đổi bất kỳ vào mã nguồn API.
2. Workflow trên GitHub Actions tự động chạy build, quét lỗi, push và ký số image.
3. ArgoCD cập nhật file cấu hình [app-api/rollout.yaml](file:///d:/GitHub/rbac_admission/app-api/rollout.yaml) trỏ về tag image mới.
4. Triển khai hoàn tất thành công trên cụm.

### Kịch bản B: Triển khai Image chưa được Ký số (Bị Từ Chối)
Nếu bạn thử triển khai một image không có chữ ký (ví dụ: ảnh nginx mặc định) vào namespace `demo`:
```bash
kubectl run test-unsigned --image=nginx:latest -n demo
```
*Thông báo lỗi kỳ vọng:*
```
Error from server (InternalError): admission webhook "policy.sigstore.dev" denied the request: 
validation failed: image nginx:latest does not have a valid signature
```

---

## 5. Các Bước Điều Tra & Khắc Phục Sự Cố (Troubleshooting)

Khi một Rollout hoặc Deployment bị kẹt (không tạo được Pod mới) do lỗi xác thực chữ ký, hãy làm theo các bước sau:

### Bước 1: Kiểm tra Sự kiện Tạo Pod
Kiểm tra xem ReplicaSet có bị kẹt hay có thông báo lỗi từ webhook nào không:
```bash
kubectl get replicasets -n demo -l app=api
kubectl describe replicaset -n demo <tên-replicaset-của-bạn>
```
Tìm các sự kiện có thông báo bị chặn bởi admission webhook `policy.sigstore.dev`.

### Bước 2: Xác thực Chữ ký Image Cục bộ bằng Cosign
Tải file khóa công khai [signing/cosign.pub](file:///d:/GitHub/rbac_admission/signing/cosign.pub) và chạy lệnh Cosign để xác thực chữ ký của image trực tiếp:
```bash
cosign verify --key signing/cosign.pub ghcr.io/pkhoa011004/w10-api:<tag-phiên-bản>
```
- Nếu thấy thông báo `wildcard-like authority matched`, chữ ký của image hoàn toàn hợp lệ.
- Nếu thấy thông báo `no matching signatures`, có nghĩa image này chưa được ký hoặc đã được ký bởi một cặp khóa khác.

### Bước 3: Cách Xử Lý Lỗi Image Chưa Ký
Nếu image đã được build nhưng khâu ký số tự động trên CI/CD bị lỗi:
1. Thực hiện kích hoạt chạy lại (Re-run) job build-push trên GitHub Actions.
2. Hoặc thực hiện ký thủ công trực tiếp nếu bạn nắm giữ khóa riêng tư (Private Key):
   ```bash
   cosign sign --key <đường-dẫn-tới-private-key> ghcr.io/pkhoa011004/w10-api:<tag-phiên-bản>
   ```
