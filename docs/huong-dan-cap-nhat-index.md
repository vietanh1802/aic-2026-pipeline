# Hướng dẫn cập nhật bộ index

Runbook cho cả team. Phần lý do kỹ thuật và các bẫy nằm ở
[`updating-indexes.md`](updating-indexes.md); file này chỉ trả lời hai câu:
**cập nhật thế nào** và **làm sao biết máy đang chạy bộ mới hay bộ cũ**.

## Ba điều phải nắm trước khi bấm bất cứ nút gì

1. **S3 là bản gốc duy nhất.** `s3://aic2026-artifacts/indexes/` là nguồn chuẩn.
   Máy API chỉ giữ một bản sao trong `/opt/aic/indexes`. Không ai sửa trực tiếp
   trên máy API.

2. **API nạp index vào RAM một lần rồi thôi.** Đổi file dưới đĩa mà không khởi
   động lại container thì API vẫn trả kết quả từ bộ cũ — và `/status` vẫn báo
   đúng số đếm như thường. Đây là lỗi im lặng nguy hiểm nhất trong quy trình
   này, nên có hẳn một trường `stale_files` để bắt nó.

3. **Năm file phải cùng một mẻ sinh.** `beit3.index`, `clip.index`,
   `beit3_mapping.json`, `clip_mapping.json`, `keyframe_metadata.json`. Lệch mẻ
   thì `faiss_id` trỏ sang frame khác: không hàm nào báo lỗi, tìm kiếm vẫn ra
   kết quả, kết quả chỉ đơn giản là sai.

## Ai làm bước nào

| Bước | Ai | Ở đâu |
|---|---|---|
| 1–2. Sinh index và đẩy lên S3 | người giữ file 15 GB | máy cá nhân, thủ công |
| 3–5. Kéo về máy API, restart, kiểm tra | cả team | nút bấm GitHub Actions |
| Kiểm tra "đang chạy bộ nào" | cả team | nút bấm, hoặc `curl` |

Bước 1–2 không tự động hoá được: 15 GB nằm trên máy cá nhân, runner của GitHub
không với tới.

---

## Việc phải làm một lần trước khi team dùng nút

Role OIDC `aic2026-github-actions-deploy-role` ban đầu chỉ có quyền EC2 và SSM,
không có quyền S3 nào. Workflow sẽ chết ngay ở dòng đầu bước sync. Cấp quyền
đọc — chỉ đọc, chỉ đúng prefix `indexes/`:

```powershell
aws iam put-role-policy --role-name aic2026-github-actions-deploy-role `
  --policy-name aic2026-github-actions-indexes-read `
  --policy-document file://deploy/p6/github-oidc-indexes-read-policy.json --profile aic
```

Truyền policy bằng `file://`. Nhét JSON thẳng vào dòng lệnh trên Windows sẽ lỗi
`MalformedPolicyDocument` vì dấu nháy bị nuốt trước khi CLI nhìn thấy.

Làm một lần là xong, không phải lặp lại.

## Bước 1 — Sinh lại index

Chạy notebook như thường. Kết quả rơi vào `backend/app/indexes/`.

Trước khi đẩy lên, đếm lại cho chắc năm file đều mới:

```powershell
Get-ChildItem backend/app/indexes/ | Select-Object Name, Length, LastWriteTime
```

Nếu chỉ một vài file có ngày giờ mới còn lại là cũ thì **dừng ở đây**. Đẩy lên
lệch mẻ là rơi vào đúng cái bẫy số 3.

## Bước 2 — Đẩy lên S3

```powershell
aws s3 sync backend/app/indexes/ s3://aic2026-artifacts/indexes/ --profile aic
```

Thêm `--delete` khi có file đã bị xoá hẳn khỏi bộ mới. Không có nó thì file cũ
vẫn nằm lại và máy API sẽ giữ cả hai.

Xác nhận đã lên đủ:

```powershell
aws s3api list-objects-v2 --bucket aic2026-artifacts --prefix indexes/ --profile aic `
  --query 'Contents[].{Key:Key,Size:Size,LastModified:LastModified}' --output table
```

Bộ đầy đủ hiện tại là **9 object, 15.0 GiB** — năm file index cộng bốn file
trọng số model. Nếu thấy ít hơn thì chưa xong, đừng sang bước 3.

## Bước 3 — Bấm nút để máy API kéo về

Vào **Actions → Indexes → Run workflow** trên
<https://github.com/vietanh1802/aic-2026-pipeline/actions>, rồi điền:

| Ô | Điền gì |
|---|---|
| Use workflow from | `staging` |
| action | `sync-and-verify` |
| delete_removed | bật **chỉ khi** bước 2 đã dùng `--delete` |
| expect_keyframes | số keyframe mong đợi, để trống nếu không chắc |

`expect_keyframes` là chốt chặn cuối: điền vào thì workflow sẽ đỏ nếu bộ index
nạp lên không đúng số keyframe bạn nghĩ. Bộ đang chạy có **868 524** keyframe.

Workflow tự lo phần còn lại: máy đang tắt thì bật lên, chờ SSM, `aws s3 sync`
xuống `/opt/aic/indexes`, restart container API, rồi chạy kiểm tra.

Mất khoảng 5–20 phút tuỳ lượng dữ liệu thay đổi; riêng warm-up đã ~90–140s.

## Bước 4 — Đọc kết quả

Xanh là xong. Trong log bước *Verify the reloaded index set* sẽ thấy:

```
== index files the process is serving ==
== comparing the loaded set against s3://aic2026-artifacts/indexes/ ==
  beit3.index: serving the S3 copy (3557474349 bytes, 2026-08-17T16:37:30+00:00)
  beit3_mapping.json: serving the S3 copy (62821333 bytes, ...)
  clip.index: serving the S3 copy (541783085 bytes, ...)
  clip_mapping.json: serving the S3 copy (7535930 bytes, ...)
  keyframe_metadata.json: serving the S3 copy (437223535 bytes, ...)
Index verification passed
```

Dòng `serving the S3 copy` mới là bằng chứng. Nó nói: **thứ đang nằm trong RAM
của API đúng bằng thứ S3 đang phát**, so từng byte và từng mốc thời gian.

Cuối cùng, nhớ nâng `VERSION` để còn nhận diện bản đang chạy.

---

## Kiểm tra bất cứ lúc nào: đang chạy bộ mới hay bộ cũ?

### Cách 1 — bấm nút, không đụng gì

**Actions → Indexes → Run workflow**, chọn `action: verify-only`.

Nó bỏ qua toàn bộ phần sync và restart, chỉ hỏi API rồi đối chiếu với S3. Không
sửa gì, không restart gì. Máy đang tắt thì workflow báo đỏ ngay với lời nhắn rõ
ràng chứ không tự bật lên (bật máy tốn tiền, mà máy tắt thì cũng chẳng có gì để
kiểm tra).

### Cách 2 — hỏi thẳng API

```bash
curl -s https://aic-api.umaga.fun/status | jq '{stale_files, index_files, keyframes}'
```

Đọc ba thứ:

- `index_files.<tên file>.loaded` — vân tay của file **tại lúc API nạp vào RAM**.
  Đây là bộ đang thực sự phục vụ.
- `index_files.<tên file>.on_disk` — vân tay của file **đang nằm dưới đĩa ngay lúc
  này**.
- `stale_files` — danh sách file mà hai cái trên lệch nhau.

Vân tay gồm `bytes` và `mtime`. `mtime` khớp thẳng với `LastModified` bên S3, vì
`aws s3 sync` đóng dấu mốc thời gian của object lên file nó tải về.

### Bảng đọc kết quả

| Thấy gì | Nghĩa là | Làm gì |
|---|---|---|
| `stale_files: []` và `loaded` khớp S3 | Đang chạy đúng bộ mới nhất | Không phải làm gì |
| `stale_files` có tên file | File dưới đĩa đã đổi nhưng **API chưa nạp lại** — vẫn đang trả kết quả từ bộ cũ | Chạy `sync-and-verify` để restart |
| `stale_files: []` nhưng `loaded` lệch S3 | API nhất quán nhưng đang chạy một mẻ khác với mẻ S3 đang phát | Chạy `sync-and-verify` |
| `loaded` là `null` | File đó chưa từng được nạp | Kiểm tra `files` xem có thiếu file không |

Đối chiếu tay với S3 khi cần:

```powershell
aws s3api head-object --bucket aic2026-artifacts --key indexes/beit3.index --profile aic `
  --query '{bytes:ContentLength,mtime:LastModified}'
```

So với `index_files."beit3.index".loaded`. Trùng cả hai giá trị là đang chạy đúng
bản S3.

### Vì sao không nhìn số keyframe cho nhanh?

Vì số đếm không phân biệt được. Sinh lại index trên cùng tập keyframe thì
`keyframes` và `vectors.beit3` giữ nguyên y hệt — và các số đó đọc ra từ biến
trong RAM, nên một container **chưa hề restart** báo con số giống hệt một
container đã cập nhật xong. Số đếm chỉ chứng minh năm file khớp nhau, không
chứng minh chúng là bộ mới.

---

## Trục trặc thường gặp

**Workflow đỏ ở bước Sync, log ghi `Refusing to sync: source holds N objects`**
Bước 2 chưa xong hoặc gõ nhầm prefix. Script từ chối sync khi S3 có dưới 5
object, vì nếu kèm `--delete` thì nó sẽ xoá sạch bộ index máy API đang dùng.

**Workflow đỏ với `The files on disk moved but the process did not reload them`**
Sync xong nhưng container không restart được. Chạy lại `sync-and-verify`.

**Workflow đỏ với `MISMATCH loaded=... s3=...`**
Máy API đang phục vụ một mẻ khác với mẻ trên S3. Hay gặp nhất là ai đó vừa đẩy
bộ mới lên S3 trong lúc workflow đang chạy.

**Workflow đỏ với `cannot read s3://...` kèm `AccessDenied`**
Chưa cấp policy ở phần "Việc phải làm một lần" bên trên.

**Workflow đỏ với `Index set is inconsistent`**
Đúng cái bẫy số 3: năm file không cùng một mẻ. Quay lại bước 1.

**`verify-only` đỏ với `The API instance is stopped`**
Máy đang tắt để tiết kiệm credit. Bật bằng **Actions → Power API EC2 →
`action: start`** rồi chạy lại.

## Nhớ tắt máy khi xong

Máy API `r6i.xlarge` tốn khoảng **$0.30/giờ**. Để chạy 24/7 là ~$215/tháng,
vượt xa $150 credit. Xong việc thì **Actions → Power API EC2 → `action: stop`**.
