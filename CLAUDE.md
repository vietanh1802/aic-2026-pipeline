# CLAUDE.md

Ghi chú cho Claude Code làm việc trên repo này. Đọc hết trước khi sửa gì.

## Quy tắc bắt buộc của chủ repo

1. **Trả lời bằng tiếng Việt.** Mọi câu trả lời, mọi giải thích.
2. **Code pipeline/thí nghiệm phải viết trong notebook, không tạo file `.py` rời.**
   Ngoại lệ duy nhất: backend và frontend — hai phần đó là ứng dụng thật, sống
   trong file thật.
3. **Notebook mới phải có số thứ tự trong tên** để phân biệt (vd `78_ocr_scene_merge.ipynb`).
4. **Không xoá cách cũ — comment nó lại**, kèm lý do vì sao đổi. Hàm và biến
   viết mới thì **đặt tên bằng tiếng Anh**, kể cả biến. Chú thích thì tiếng Việt
   hoặc tiếng Anh đều được, miễn nói được *vì sao*, không phải *làm gì*.
5. **Đừng phức tạp hoá.** Chủ repo đã nhắc chuyện này. Làm đúng thứ được yêu
   cầu, không dựng thêm tầng trừu tượng cho tương lai giả định.
6. **KHÔNG BAO GIỜ commit hai đường dẫn này** — chúng là file test cấp quyền cho
   một tài khoản AWS khác vào S3 của chủ repo, đã nằm trong `.gitignore`:
   - `bucket-policy-backup/`
   - `deploy/p6/iam-operator-policy.json`

## Dự án là gì

**Bquerium** — công cụ tra cứu khoảnh khắc video cho **AI Challenge HCMC 2026**.
Nhóm 5 người + 1 tài khoản admin ngồi thi cùng lúc: gõ mô tả cảnh bằng tiếng
Việt/Anh, hệ thống trả về keyframe khớp, người dùng chốt khung rồi nộp danh sách
xếp hạng.

Ba loại câu, mỗi loại chấm khác nhau — quyết định gần như mọi lựa chọn giao diện:

| Loại | Nộp gì | Chấm |
| --- | --- | --- |
| **KIS** | `video, frame` | Đúng/sai cả dòng |
| **Q&A** | `video, frame, đáp án chữ` | Đáp án chữ mới là thứ được chấm |
| **TRAKE** | `video, frame_1..frame_N` | **Theo từng mốc**: sai một mốc mất 1/N, sai video mất trắng |

Điểm là **R@k** — tính trên k dòng đầu. Nên **thứ tự dòng là dữ liệu**, không
phải trang trí: mọi chỗ sinh dòng tự động đều phải gửi tuần tự để giữ đúng thứ
hạng, không `Promise.all`.

## Bố cục repo

```
backend/          FastAPI + SQLite. Tìm kiếm + cộng tác (giỏ đáp án, board, export).
  app/main.py       các endpoint tìm kiếm (ensemble/single/temporal/trake/ocr)
  app/preprocess.py LÕI TRUY XUẤT — FAISS/BEiT3/CLIP. Không sửa (INV-1 của spec).
  app/routers/      auth, packs, board, answers, export, rounds, search_state
  app/db/           schema.sql (baseline) + migrations.py (bước đánh số)
  tests/            pytest, 152 test
frontend/         React 19 + TS + Vite + Tailwind v4 + Zustand
  src/App.tsx       màn tìm kiếm (file lớn nhất)
  src/Root.tsx      toàn bộ định tuyến — 6 màn, không dùng router library
  src/components/   AppNav, Basket/BasketBody, VideoPopUp, CandidateResults...
  src/pages/        Board, Evaluation, Export, ImportPack, Login, ChangePassword
  src/store/        useSearchStore, queryStore, authStore, popupStore, healthStore,
                    pickedFrameStore
drive-video-proxy/ Node/Express, phát video từ Google Drive (HTTP Range)
notebooks/        pipeline offline: cắt keyframe, OCR, dựng index
deploy/p6/        script SSM deploy lên EC2
docs/             spec và thiết kế; `docs/superpowers/specs/` là nguồn đáng tin
VERSION           một dòng semver — CI CHẶN nếu không tăng
```

`README.md` mô tả các endpoint **đã bị xoá** (`/text-search`, `/faiss-search`,
`/combined-search`, `/filter-search`). Đừng tin nó; đọc `backend/app/main.py`.

## Lệnh

```bash
# backend
cd backend && uvicorn app.main:app --reload          # cổng 8000
cd backend && python -m pytest -q --basetemp=<thư mục ghi được>
cd backend && python -m ruff check app

# frontend
cd frontend && npm run dev                            # cổng 5173
cd frontend && npx tsc -b && npm run lint && npm test && npm run build
```

**pytest trên Windows:** chạy trần sẽ ra ~83 lỗi `PermissionError` ở
`C:\...\Temp\pytest-of-Windows`. Đó là quyền thư mục tạm, **không phải test
hỏng** — thêm `--basetemp` trỏ vào chỗ ghi được là hết.

Tài khoản seed: `admin`, `vanh`, `bang`, `nam`, `an`, `phat` — mật khẩu mặc định
`password` (xem `backend/scripts/seed_team.py`).

## Deploy

Đẩy lên nhánh `staging` là chạy `.github/workflows/deploy.yml`:

```
version-guard  →  check-frontend (lint, tsc, test, build)  →  deploy-frontend (Cloudflare Pages)
               →  check-backend  (ruff, import, pytest)    →  deploy-backend  (GHCR + SSM lên EC2)
                                                              → smoke test → tự rollback nếu hỏng
```

**Trước khi push phải sửa `VERSION`.** Cổng `version-guard` so với VERSION mà
`staging` đang có; giữ nguyên hoặc lùi số là CI đỏ ngay bước đầu. Bump xong thì
`git add -A` (nhớ file bị xoá), commit, `git push origin staging`.

Sau khi web lên, nhìn góc phải thanh nav phải thấy đúng số phiên bản. Còn số cũ
là trình duyệt cache — Ctrl+Shift+R.

## Những chỗ đã cắn người khác

**Migration.** Cột/bảng thêm trong `migrations.py` **không được** khai lại trong
`schema.sql`. `schema.sql` toàn `IF NOT EXISTS` nên `ALTER` ở đó chạy lại lần hai
là `duplicate column name` và **toàn bộ test đỏ**. `CREATE TABLE IF NOT EXISTS`
thì an toàn cả hai nơi. Không bao giờ sửa hay đánh số lại một bước đã ship —
thêm bước mới.

**Export.** File nộp là CSV **không bọc nháy** (`L05_V005, 888, màu xanh`). Tuyệt
đối không dùng `csv.writer`: nó tuân RFC 4180 nên gặp dấu nháy trong đáp án Q&A
sẽ bọc cả trường, ban tổ chức đọc ra chuỗi khác. Ghép trường bằng tay.
`Content-Disposition` phải theo RFC 6266 (`filename=` ASCII + `filename*=UTF-8''…`)
— nhãn vòng thi có dấu tiếng Việt sẽ làm latin-1 nổ 500.

**Xác minh code đã chạy trên dev server.** Vite **xoá comment** khi phục vụ
module. Grep comment để kiểm tra sẽ báo "chưa có" cho code đang chạy. Luôn grep
**code**, không grep chú thích:
```bash
curl -s "http://localhost:5173/src/App.tsx" | grep -c "tenBienThat"
```

**Heredoc trên Windows.** `python - <<'PY'` đọc stdin bằng cp1252, chuỗi tiếng
Việt bị nát và script âm thầm không làm gì. Script có tiếng Việt thì viết ra file
bằng công cụ Write rồi chạy, hoặc dùng `io.open(..., encoding="utf-8")` cho mọi
đọc/ghi.

**`npm ci` xoá sạch `node_modules`** và làm chết dev server đang chạy. Trên máy
chủ repo dùng `npm install`.

**Vòng lặp vô hạn.** Các generator rải frame trong `backend/app/answers/autofill.py`
lặp `while produced < limit`. Nếu không có gì để sinh thì `produced` đứng yên và
nó quay mãi — pytest treo. Luôn lọc trước danh sách nguồn và `return` sớm khi rỗng.

## Mô hình dữ liệu cần nhớ

- `answers.author_id` = **chủ danh sách**; `answers.created_by` = ai tạo dòng đó.
  Hai cái khác nhau, và mọi đường ghi phải khoá theo `author_id` — thiếu chỗ nào
  là người này sửa được bài người kia.
- `tasks.chosen_author_id` = danh sách của ai sẽ được nộp. `NULL` = chưa chọn.
- Câu chưa ai làm thì xuất ra **file rỗng**, không phải lỗi. Chỉ "có bài nhưng
  chưa chọn người" mới từ chối.
- Ảnh keyframe luôn nằm trên nền `--proto-dark`. Nền có màu làm lệch cảm nhận
  màu trong ảnh, mà so màu giữa hai khung mới là việc chính.

## Thói quen làm việc mà chủ repo đã xác nhận

- **Kiểm bằng kịch bản gọi API thật** với backend đang chạy, không chỉ unit test.
  Nhiều lỗi trong repo này chỉ lộ ra khi đi đúng luồng người dùng.
- Sửa xong chạy đủ: `npx tsc -b`, `npm run lint`, `npm test`, `pytest`, `ruff`.
- Sửa UI xong thì kiểm module Vite đang phục vụ như trên.
- Xoá một tính năng thì **để lại chú thích nói vì sao bỏ và dùng gì thay** —
  đừng để chỗ đó trống trơn.

---

Sửa file này khi có quy tắc mới hoặc khi phát hiện một cái bẫy tốn thời gian.
