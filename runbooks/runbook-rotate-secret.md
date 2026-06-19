# Hướng Dẫn: Xoay Vòng Secret Không Cần Restart Pods

## 1. Tổng quan
Tài liệu hướng dẫn này trình bày quy trình xoay vòng (cập nhật) mật khẩu ứng dụng trong cụm Kubernetes bằng cách sử dụng **External Secrets Operator (ESO)** và xác minh ứng dụng tự động nhận giá trị secret mới mà không cần phải khởi động lại (restart) các pods.

Bằng cách mount secret dưới dạng **Volume** (tệp tin) thay vì truyền trực tiếp làm biến môi trường (Environment Variable), Kubernetes sẽ tự động cập nhật tệp tin secret bên trong container khi giá trị nguồn thay đổi, đảm bảo quá trình xoay vòng diễn ra mà hoàn toàn không có thời gian gián đoạn (zero-downtime).

---

## 2. Điều kiện kiên quyết (Prerequisites)
- Quyền truy cập vào cụm minikube `w10` đã được cấu hình lệnh `kubectl`.
- Các ứng dụng `external-secrets-operator` và `external-secrets-config` đã được triển khai thành công và ở trạng thái Healthy trên ArgoCD.

---

## 3. Quy Trình Các Bước Xoay Vòng Secret

Trong bài thực hành này, chúng ta sử dụng nhà cung cấp giả lập (`fake` provider) để chứng minh tính đúng đắn của giải pháp. Trong môi trường production thực tế, bạn sẽ sử dụng dịch vụ lưu trữ chính thống như AWS Secrets Manager hoặc HashiCorp Vault.

### Bước 1: Cập nhật giá trị Secret gốc
Mở file [eso/secret-store.yaml](file:///d:/GitHub/rbac_admission/eso/secret-store.yaml) và tiến hành thay đổi giá trị mật khẩu giả lập:

```yaml
spec:
  provider:
    fake:
      data:
        - key: db-password
          value: "my-super-secret-password-v3" # Cập nhật giá trị mới tại đây
```

### Bước 2: Đẩy thay đổi lên Git (GitOps Sync)
Thực hiện commit và push thay đổi để hệ thống ArgoCD tự động nhận diện và đồng bộ:
```bash
git add eso/secret-store.yaml
git commit -m "chore: rotate database password to v3"
git push origin main
```

*(Lưu ý: Nếu kiểm thử trực tiếp ở local không qua Git, bạn có thể chạy lệnh: `kubectl apply -f eso/secret-store.yaml`)*

### Bước 3: Xác minh quá trình đồng bộ của ESO
ESO tự động quét nguồn cung cấp định kỳ mỗi **10 giây** (theo tham số `refreshInterval: 10s` trong [eso/external-secret.yaml](file:///d:/GitHub/rbac_admission/eso/external-secret.yaml)).

Chạy lệnh sau để kiểm tra xem Kubernetes Secret đã nhận giá trị mới chưa:
```bash
kubectl get secret db-secret -n demo -o jsonpath='{.data.db-password}' | base64 -d; echo
```
*Kết quả đầu ra kỳ vọng:* `my-super-secret-password-v3`

---

## 4. Xác Minh Ứng Dụng Cập Nhật Không Cần Khởi Động Lại

### Bước 1: Kiểm tra Thời gian chạy (Age) và Số lần khởi động lại (Restarts) của Pod
Xác minh rằng Kubernetes không hề chạy lại các pods của API ứng dụng để áp dụng secret mới. Số lần restart phải giữ nguyên và thời gian chạy (AGE) không bị reset về 0s:
```bash
kubectl get pods -n demo -l app=api
```
*Kết quả đầu ra kỳ vọng:*
```
NAME                   READY   STATUS    RESTARTS   AGE
api-664bd47576-cjk76   1/1     Running   0          2h
api-664bd47576-jw5fq   1/1     Running   0          2h
```

### Bước 2: Kiểm tra nội dung Secret bên trong Container đang chạy
Truy cập (exec) vào một trong các pods API đang hoạt động để đọc tệp tin secret được mount tại đường dẫn `/etc/secrets/db-password`:
```bash
# Lấy tên của một pod API bất kỳ
POD_NAME=$(kubectl get pods -n demo -l app=api -o jsonpath='{.items[0].metadata.name}')

# Xem nội dung tệp secret bên trong container của pod đó
kubectl exec -it $POD_NAME -n demo -c api -- cat /etc/secrets/db-password; echo
```
*Kết quả đầu ra kỳ vọng:* `my-super-secret-password-v3`

---

## 5. Tại sao Pod không cần khởi động lại?
- **Volume Mount vs Env Var**: Chúng tôi mount secret dưới dạng một tệp nằm trong volume tại thư mục `/etc/secrets/db-password`.
- **Đồng bộ động của Kubelet**: Khi đối tượng secret được cập nhật trên API Server, tiến trình `kubelet` chạy trên node sẽ tự động phát hiện và cập nhật lại nội dung tệp tin gắn trong container (quá trình này thường diễn ra trong vòng 1 phút).
- **Ứng dụng đọc dữ liệu động (Live Reload)**: Ứng dụng đọc giá trị mật khẩu trực tiếp từ tệp tin filesystem. Do tệp tin được đọc theo nhu cầu (on-demand) hoặc có cơ chế giám sát thay đổi, chúng ta tránh được việc phải khởi động lại container mà vẫn giữ được tính khả dụng 100%.
