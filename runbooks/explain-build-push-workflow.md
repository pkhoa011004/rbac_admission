# Giải Thích Luồng CI/CD - Pipeline Build & Push Image

Tài liệu này giải thích chi tiết hoạt động của file cấu hình GitHub Actions Workflow tại [build-push.yml](file:///d:/GitHub/rbac_admission/.github/workflows/build-push.yml). Đây là trái tim của luồng DevSecOps / GitOps trong hệ thống, đảm bảo mọi container image trước khi được triển khai lên cụm Kubernetes đều phải qua khâu quét lỗ hổng bảo mật, ký số và tự động đồng bộ cấu hình.

---

## 1. Điều Kiện Kích Hoạt (Triggers)
Workflow được thiết lập chạy tự động dựa trên các sự kiện sau:
* **Push**: Khi có code mới được đẩy lên nhánh `main` và có sự thay đổi nằm trong:
  * Thư mục chứa mã nguồn ứng dụng: `src/api/**`
  * Bản thân file workflow này: `.github/workflows/build-push.yml`
* **Workflow Dispatch**: Cho phép chạy thủ công từ giao diện của GitHub Actions.

---

## 2. Các Biến Môi Trường Toàn Cục (Environment Variables)
* `REGISTRY`: `ghcr.io` - Sử dụng GitHub Container Registry làm nơi lưu trữ các container images.
* `IMAGE_NAME`: Tự động lấy tên theo định dạng `<tên_chủ_sở_hữu_repo>/w10-api` (Ví dụ: `pkhoa011004/w10-api`).

---

## 3. Các Bước Thực Thi Chi Tiết (Steps)

Luồng chạy (Job `build-and-push`) chạy trên hệ điều hành ảo `ubuntu-latest` và thực hiện các bước tuần tự như sau:

### Bước 1: Checkout mã nguồn (`Checkout repository`)
* **Hành động**: Sử dụng action `actions/checkout@v4` với `fetch-depth: 0` để kéo toàn bộ lịch sử commit của dự án về runner. Việc lấy đầy đủ lịch sử commit là bắt buộc để có thể tính toán chính xác phiên bản ở bước sau.

### Bước 2: Tính toán phiên bản ứng dụng (`Calculate semantic version`)
* **Hành động**: Sử dụng action `paulhatch/semantic-version@v5.4.0` để tự động phân tích lịch sử commit và tạo ra một số phiên bản chuẩn Semantic Versioning (ví dụ: `0.0.3`).
* **Quy luật**: 
  * Nếu trong commit có chuỗi `BREAKING CHANGE:` hoặc `!:` -> tăng phiên bản Major (X.0.0).
  * Nếu commit bắt đầu bằng `feat` -> tăng phiên bản Minor (0.X.0).
  * Các trường hợp còn lại -> tăng phiên bản Patch (0.0.X).

### Bước 3: Đăng nhập vào Registry (`Log in to Container Registry`)
* **Hành động**: Sử dụng `docker/login-action@v3` để đăng nhập vào GitHub Container Registry (`ghcr.io`).
* **Thông tin**: Sử dụng tài khoản GitHub hiện tại của Actions (`github.actor`) và token bảo mật tạm thời `secrets.GITHUB_TOKEN`.

### Bước 4: Trích xuất Metadata của Image (`Extract metadata`)
* **Hành động**: Sử dụng `docker/metadata-action@v5` để tự động sinh ra các nhãn (labels) và các tags cho Docker Image.
* **Các tag được tạo ra**:
  * `latest` (ảnh mới nhất).
  * Phiên bản dạng số (ví dụ: `0.0.3`).
  * Phiên bản kết hợp mã SHA commit (để phục vụ việc theo dõi vết chính xác).

### Bước 5: Build Image cục bộ để quét lỗi (`Build Docker image locally`)
* **Hành động**: Thực hiện build Docker image từ thư mục `./src/api` nhưng **chưa push lên registry**. Image được nạp trực tiếp vào Docker daemon cục bộ của runner dưới tag tạm thời là `local-scan`.

### Bước 6: Quét lỗ hổng bảo mật bằng Trivy (`Run Trivy vulnerability scanner`)
* **Hành động**: Chạy công cụ **Trivy** (`aquasecurity/trivy-action@v0.36.0`) để quét các thư viện OS và ứng dụng bên trong image `local-scan`.
* **Cơ chế kiểm soát (Security Gate)**:
  * `severity: 'CRITICAL,HIGH'`: Chỉ quét các lỗ hổng mức độ Nghiêm Trọng (Critical) và Cao (High).
  * `exit-code: '1'`: **CỰC KỲ QUAN TRỌNG**. Nếu phát hiện bất kỳ lỗi nào thỏa mãn điều kiện quét và không nằm trong danh sách bỏ qua ngoại lệ `.trivyignore`, pipeline sẽ lập tức báo đỏ và dừng lại toàn bộ.

### Bước 7: Build và Push Image chính thức (`Build and push Docker image`)
* **Hành động**: Sau khi đảm bảo image sạch lỗi ở bước 6, tiến hành build chính thức và đẩy (push) image lên GitHub Container Registry (`ghcr.io`) với đầy đủ các tag đã trích xuất ở Bước 4.

### Bước 8: Cài đặt và Ký số Image bằng Cosign (`Sign image with Cosign`)
* **Hành động**:
  1. Cài đặt công cụ Cosign (`sigstore/cosign-installer@v3.5.0`).
  2. Ký số bảo mật lên container image vừa đẩy lên bằng khoá riêng tư (Private Key) được cấu hình trong GitHub Secrets:
     * Ký lên tag phiên bản cụ thể (ví dụ: `0.0.3`).
     * Ký lên tag `latest`.
* **Mục đích**: Chữ ký số này sẽ được hệ thống **Sigstore Policy Controller** trên cụm Kubernetes xác thực trước khi cho phép chạy Pod.

### Bước 9: Cập nhật cấu hình GitOps (`Update rollout.yaml with new version`)
* **Hành động**: Chạy các câu lệnh shell (`sed`) để tự động tìm và thay thế tên image cũ bằng địa chỉ image mới cùng phiên bản mới vừa build thành công trong file cấu hình [app-api/rollout.yaml](file:///d:/GitHub/rbac_admission/app-api/rollout.yaml).

### Bước 10: Tự động Commit & Push cấu hình mới (`Commit and push version update`)
* **Hành động**: Thay mặt bot `github-actions[bot]` để commit sự thay đổi của file `app-api/rollout.yaml` và đẩy ngược trực tiếp trở lại nhánh `main` trên GitHub.
* **Mục đích**: Đây là luồng **GitOps**. Khi tệp cấu hình trên Git được cập nhật phiên bản mới, ArgoCD đang chạy ở cụm Kubernetes sẽ lập tức phát hiện ra sự thay đổi và tự động đồng bộ (sync) kéo image mới về triển khai (Canary Deployment).

### Bước 11: Tạo thẻ Tag Git (`Create git tag`)
* **Hành động**: Tự động tạo và push một Git tag tương ứng với phiên bản ứng dụng vừa build (ví dụ: `v0.0.3`) lên GitHub để phục vụ việc lưu trữ lịch sử phát hành (Release).

---

## 4. Các Điểm Sáng Về Bảo Mật Trong Workflow
1. **Quét lỗi trước khi phát hành**: Không cho phép đẩy các image có lỗi bảo mật nghiêm trọng lên registry công cộng.
2. **Ký số chống giả mạo (Cosign)**: Ngăn chặn triệt để các cuộc tấn công chuỗi cung ứng (supply chain attack) hoặc kẻ gian chèn image độc hại vào cụm. Cụm Kubernetes chỉ chấp nhận các image được xác thực bằng chữ ký tương ứng với cặp khóa trong dự án của bạn.
3. **Tự động hóa hoàn toàn (GitOps)**: Con người không cần can thiệp trực tiếp vào cụm Kubernetes hay chỉnh sửa cấu hình thủ công, giảm thiểu sai sót vận hành.
