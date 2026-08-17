# Runner3 WordPress — Canonical Free Domain Flow

Status: **WORKING / VERIFIED 2026-08-17**

## Mục tiêu

Tạo một hostname miễn phí cho WordPress đang chạy trên Wasmer, gắn custom domain hoàn toàn bằng automation, không cần mua domain và không yêu cầu user thao tác DNS thủ công nếu provider cho phép.

Flow này là canonical cho yêu cầu kiểu:

- "đăng ký domain free gắn vào site"
- "tạo domain free cho WordPress Runner3"
- "gắn domain miễn phí vào Wasmer"

## Kết quả hiện tại

- Site: Runner3 WordPress trên Wasmer
- Free hostname: `runner3wp.pntr.dev`
- URL live: `https://runner3wp.pntr.dev/`
- Wasmer DNS target: `lnh8iwtjmk3x.id.wasmer.app`
- Public HTTPS check: HTTP `200`
- Frontend check: có nội dung `Runner3`
- Final URL vẫn giữ custom hostname, không redirect về `.wasmer.app`

## Provider ưu tiên

### 1. PNTR — route mặc định

Dùng `*.pntr.dev`.

Lý do:

- miễn phí
- không cần signup để tạo guest subdomain
- hỗ trợ DNS record trực tiếp trong dashboard
- không có CAPTCHA ở flow đã chạy
- anonymous free quota hiện cho phép 1 active subdomain
- có thể tự động hóa bằng Playwright trên GitHub Actions

Lưu ý: guest subdomain gắn với browser session. Vì Runner3 là ephemeral, session phải được persist mã hóa trong repo; tuyệt đối không commit cookie/session plaintext.

### 2. is-a-good.dev — fallback đẹp hơn nhưng chậm

Hỗ trợ A/CNAME nhưng flow chuẩn qua GitHub fork + PR / maintainer review, do đó không phải route mặc định khi mục tiêu là zero-touch + live nhanh.

### 3. ClouDNS — không dùng cho zero-touch

Signup đã probe và gặp hCaptcha + reCAPTCHA. Không bypass CAPTCHA.

## Flow thực thi chuẩn

### Bước A — lấy DNS target từ Wasmer

1. Mở app Wasmer → Settings → Domains.
2. Add custom hostname dự kiến.
3. Wasmer trả về CNAME target.
4. Với site hiện tại target là:

```text
lnh8iwtjmk3x.id.wasmer.app
```

Workflow/script liên quan:

- `.github/workflows/wasmer-add-free-domain.yml`
- `scripts/wasmer-add-free-domain.mjs`

### Bước B — tạo subdomain PNTR

1. Mở `pntr.dev` bằng Playwright trên GitHub Actions.
2. Vào dashboard guest session.
3. `Add subdomain`.
4. Điền tên, ví dụ `runner3wp`.
5. Submit `Create Subdomain`.
6. Xác nhận card `runner3wp.pntr.dev` xuất hiện và Active subdomains = `1/1`.

Files:

- `.github/workflows/pntr-register-runner3.yml`
- `scripts/pntr-register-runner3.mjs`
- `ops/pntr/domain-status.json`

### Bước C — persist guest session an toàn

Sau khi domain được tạo:

1. Export Playwright storageState.
2. Encrypt storageState bằng secret automation hiện có.
3. Chỉ commit encrypted blob.
4. Không log cookie/token/session plaintext.

Persisted state:

- `ops/pntr/browser-state.aes`

Encryption key hiện được lấy từ GitHub Actions secret, không lưu trong repo.

### Bước D — cấu hình DNS trên PNTR

PNTR UI có 2 tầng:

1. Expand domain card.
2. Bấm `Add Record`.
3. Form record hiện ra với các button type: `A`, `AAAA`, `CNAME`, `MX`, `TXT`.
4. Chọn `CNAME`.
5. Điền Value:

```text
lnh8iwtjmk3x.id.wasmer.app
```

6. Bấm `Add Record` lần thứ hai để lưu.
7. Xác nhận status internal = `ready`, `cnameConfigured=true`.

Files:

- `.github/workflows/pntr-configure-cname.yml`
- `scripts/pntr-configure-cname.mjs`
- `ops/pntr/domain-status.json`

### Bước E — gắn hostname vào Wasmer

1. Restore encrypted Wasmer browser session.
2. Settings → Domains.
3. Add `runner3wp.pntr.dev`.
4. Chờ Wasmer nhận hostname.
5. Không tin detector chung nếu dashboard còn domain cũ có dòng `Valid configuration`; phải kiểm tra đúng card/domain target.

Files:

- `.github/workflows/wasmer-add-free-domain.yml`
- `scripts/wasmer-add-free-domain.mjs`
- `ops/wasmer/free-domain.json`

### Bước F — verification cuối bắt buộc

Không kết luận "xong" chỉ vì UI provider/Wasmer báo success.

Phải verify ngoài Internet:

1. DNS resolve được.
2. `https://<domain>/` trả HTTP 2xx.
3. `curl -L` final URL vẫn là custom domain.
4. Body chứa fingerprint của site, hiện dùng `Runner3`.

Canonical success condition:

```text
httpCode = 200
frontContainsRunner3 = true
finalUrl = https://runner3wp.pntr.dev/
live = true
```

Files:

- `.github/workflows/verify-pntr-wasmer-domain.yml`
- `ops/pntr/live-verify.json`

## Điểm quan trọng rút ra

- Không dùng trạng thái UI làm source of truth duy nhất.
- Wasmer page có thể chứa nhiều domain; regex `Valid configuration` chung từng tạo false-positive.
- Source of truth cuối cùng là request public HTTPS thực tế.
- PNTR có thể resolve public ra Cloudflare A/AAAA thay vì trả CNAME trực tiếp khi query; điều này không làm flow fail nếu custom hostname thực sự trả đúng site qua HTTPS.
- Với PNTR, automation phải giữ cùng guest browser session; tạo session mới có thể mất quyền quản lý subdomain.
- GitHub runner là ephemeral, nên mọi browser session cần dùng lại phải được persist mã hóa.
- Không bypass CAPTCHA, không multi-account farming để né quota.
- Không commit credential, cookie hay token plaintext vào repo public.

## Khi tái sử dụng cho site mới

Parameterize 4 giá trị:

```text
SUBDOMAIN_NAME
FQDN
WASMER_APP
WASMER_CNAME_TARGET
```

Sau đó chạy lại chuỗi:

```text
Wasmer target discovery
→ PNTR create
→ encrypted session persist
→ PNTR CNAME configure
→ Wasmer domain attach
→ public DNS/HTTPS/content verify
→ only then mark LIVE
```

Nếu domain free chỉ dùng để test/MVP, giữ PNTR. Nếu site bắt đầu có traffic/doanh thu hoặc cần brand/SEO lâu dài, migrate sang domain sở hữu riêng và giữ cùng Wasmer origin/deploy flow.
