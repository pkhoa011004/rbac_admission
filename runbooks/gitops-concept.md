# Cẩm Nang Tìm Hiểu Về GitOps (Lý Thuyết Cơ Bản)

Tài liệu này cung cấp một cái nhìn tổng quan, phi hệ thống (mang tính khái niệm chung) về **GitOps** — một phương pháp luận hiện đại để triển khai và quản lý cơ sở hạ tầng cũng như ứng dụng.

---

## 1. GitOps là gì?

**GitOps** là sự kết hợp giữa **Git** (hệ thống quản lý phiên bản) và **Operations** (vận hành hệ thống). 

Hiểu một cách đơn giản nhất:
> *GitOps là phương pháp quản lý vận hành hệ thống mà ở đó **Git** đóng vai trò là nguồn chân lý duy nhất (Single Source of Truth) chứa toàn bộ cấu hình mong muốn của hệ thống.*

Thay vì chạy các lệnh thủ công như `kubectl apply` hay ssh vào server để thay đổi cấu hình, mọi thao tác thay đổi trạng thái của hệ thống đều được thực hiện thông qua các pull request trên Git.

---

## 2. Bốn Nguyên Tắc Cốt Lõi của GitOps

Theo định nghĩa của cộng đồng Cloud Native, một hệ thống chuẩn GitOps cần tuân thủ 4 nguyên tắc sau:

### 1. Khai báo hệ thống bằng mã nguồn (Declarative)
Toàn bộ trạng thái mong muốn của hệ thống (hạ tầng, mạng, ứng dụng, chính sách bảo mật) phải được mô tả dưới dạng khai báo (ví dụ: file YAML, JSON, Terraform). Hệ thống tự hiểu cần làm gì để đạt trạng thái đó thay vì chỉ ra từng bước thực hiện (Imperative).

### 2. Quản lý phiên bản và bất biến (Versioned & Immutable)
Mọi cấu hình được lưu trữ trong Git. Điều này giúp:
- Lưu lại toàn bộ lịch sử thay đổi (ai sửa cái gì, khi nào).
- Cho phép khôi phục lại trạng thái cũ (rollback) cực kỳ nhanh chóng chỉ bằng lệnh `git revert` hoặc `git checkout`.

### 3. Tự động đồng bộ (Pulled Automatically)
Sau khi cấu hình trên Git được phê duyệt và merge, các công cụ GitOps tự động phát hiện và áp dụng thay đổi đó lên hệ thống thực tế mà không cần sự can thiệp thủ công từ con người.

### 4. Tự động sửa sai (Continuous Reconciliation & Self-Healing)
Một tác nhân phần mềm (software agent) liên tục so sánh:
- **Trạng thái mong muốn** (trên Git)
- **Trạng thái thực tế** (trên Cluster)

Nếu có sự sai lệch (ví dụ: ai đó lỡ tay xóa một pod hoặc sửa cấu hình trực tiếp trên cụm bằng CLI), tác nhân này sẽ tự động ghi đè trạng thái thực tế để đưa hệ thống quay về đúng cấu hình đã khai báo trên Git.

---

## 3. Cách Hoạt Động: Mô hình Push-based vs Pull-based

Trong triển khai GitOps, có hai mô hình chính để cập nhật cấu hình:

### Mô hình Push-based (Đẩy từ CI)
- **Hoạt động:** Khi có sự thay đổi trên Git, hệ thống CI (như GitHub Actions, Jenkins) sẽ trực tiếp chạy các lệnh deploy (như `kubectl apply`, `helm upgrade`) để cập nhật lên cụm K8s.
- **Nhược điểm:** Hệ thống CI cần giữ thông tin quản trị (credentials/kubeconfig) của cụm Kubernetes, dẫn đến nguy cơ mất an toàn bảo mật.

### Mô hình Pull-based (Kéo từ cụm - Khuyên dùng)
- **Hoạt động:** Một phần mềm (như ArgoCD hoặc FluxCD) nằm **bên trong** cụm Kubernetes sẽ liên tục kéo (pull) thông tin từ Git về và tự đồng bộ cục bộ.
- **Ưu điểm:** Cụm Kubernetes không cần mở cổng ra ngoài, hệ thống CI bên ngoài không cần biết mật khẩu của cụm. Tính bảo mật cực kỳ cao và hỗ trợ tự động sửa sai (Self-Healing).

```
[ Git Repository ] <------- 1. Pull / Đối chiếu ------- [ GitOps Agent ]
       ^                                                      |
       |                                                      v
[ Developer ] -- Push --> [ Khai báo cấu hình ]         [ Cụm Kubernetes ]
```

---

## 4. Lợi ích khi áp dụng GitOps

- **Tăng tốc độ bàn giao:** Lập trình viên chỉ cần biết sử dụng Git để deploy ứng dụng thay vì phải học các câu lệnh vận hành phức tạp.
- **Khôi phục thảm họa (Disaster Recovery) thần tốc:** Nếu toàn bộ cụm Kubernetes bị sập hoàn toàn, bạn chỉ cần tạo một cụm mới và trỏ công cụ GitOps về Git Repository, toàn bộ hệ thống sẽ được tái thiết lập trong vài phút.
- **Kiểm soát bảo mật (Audit & Compliance) chặt chẽ:** Mọi thay đổi hệ thống đều phải đi qua bước Pull Request, được đồng nghiệp xem xét (Code Review) và phê duyệt trước khi áp dụng.
- **Nhất quán:** Tránh hiện tượng lệch cấu hình (Configuration Drift) giữa môi trường Dev, Staging và Production.

---

## 5. Các công cụ GitOps phổ biến hiện nay

1. **ArgoCD:** Công cụ GitOps dạng Pull-based phổ biến nhất cho Kubernetes, cung cấp giao diện trực quan sinh động để quản lý trạng thái các ứng dụng.
2. **FluxCD:** Công cụ GitOps tối giản, nhẹ và bảo mật tốt, thường cấu hình hoàn toàn qua code (GitOps thuần túy).
