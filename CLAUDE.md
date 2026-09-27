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
   - `bucket-policy-backup/` (từ 2026-09-27 nằm ở `_local/bucket-policy-backup/`;
     dòng `bucket-policy-backup/` trong `.gitignore` không neo `/` nên vẫn chặn ở mọi nơi)
   - `deploy/p6/iam-operator-policy.json`
7. **Đừng tự thêm đường dẫn dữ liệu mà chủ repo không nêu.** Một lần đoán thêm
   thư mục zip đã suýt trộn nhầm hai bộ keyframe vào cùng một index. Thiếu đường
   dẫn thì hỏi, đừng điền bừa cho đủ.

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
  app/evaluation/   benchmark: seeds/round{1,2,3}-*.json, tổng 90 câu
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
  thanhbangcao/     notebook của cả nhóm, có INDEX.md
scripts/          script phụ: mapping frontend, index ASR, sync_and_unzip.py (+ drive_zips.json)
deploy/p6/        script SSM deploy lên EC2
docs/             spec và thiết kế; `docs/superpowers/specs/` là nguồn đáng tin
VERSION           một dòng semver — CI CHẶN nếu không tăng
_local/           (gitignored) MỌI dữ liệu tải về máy: index, zip, shard, contest-backup,
                  bucket-policy-backup… Tải thứ gì mới về thì bỏ vào đây, đừng để ở gốc.
```

Hai chỗ **đừng tin**:

- `README.md` mô tả các endpoint **đã bị xoá** (`/text-search`, `/faiss-search`,
  `/combined-search`, `/filter-search`). Đọc `backend/app/main.py`.
- `backend/app/preprocess.py` có **1232 dòng đầu là bản cũ đã comment**. Code
  thật bắt đầu từ dòng 1233. Grep file này luôn kèm `grep -v '^\s*#'`.

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

Máy chủ: EC2 `r6i.2xlarge` — 8 vCPU, 64 GiB RAM, **không có GPU**. Mọi thứ chạy
lúc truy vấn (encode text BEiT3/CLIP, FAISS) đều là CPU. Thư mục app trên máy
chủ là `/opt/aic/app`.

---

## Dữ liệu offline: keyframe và index

Phần này tốn nhiều thời gian nhất để dò lại. Đọc trước khi động vào bất cứ thứ
gì liên quan tới ảnh, index hay zip.

### Tên khung là hợp đồng

```
L26_V041-0047-3798.jpg
└──┬───┘ └┬─┘ └─┬─┘
 video   cảnh  frame_idx
        4 chữ số
```

Sinh ra bởi `f"{video}-{sid:04d}-{fi}.jpg"` trong notebook cắt. **Mã cảnh luôn 4
chữ số** — đã đối chiếu 360.531/360.531 dòng trong `beit3_mapping.json`. Con số
này là cách duy nhất phân biệt bản cắt hiện tại với bộ keyframe cũ (2 chữ số).

### Bộ dữ liệu đang chạy

| | |
| --- | --- |
| Keyframe | **360.531** |
| Video | **873**, chỉ `L21`–`L30` (**không có K nào**) |
| Zip | **98** file `AIC2026_frames_p{1..5}_{NNN}.zip` |
| Bảng tra | `data_raw/zip_manifest.json` — `video_to_zip`, `by_batch`, `by_part` |

Zip nằm ở `Drive/MyDrive/aic26/Frame_Transnet_2026_v001/zips`. Ảnh còn được phát
qua HTTP tại `https://aic-frames.umaga.fun/images/<tên>.jpg` — **nhanh và rẻ hơn
đọc zip trên Drive rất nhiều**, nhưng `urllib` mặc định bị Cloudflare trả 403,
phải giả User-Agent trình duyệt.

`AIC2026_frames_p4_008.zip` là zip **duy nhất** trộn hai batch (`K20` + `L21`).
Lọc theo tên zip sẽ sai; phải lọc tới từng tên khung.

### Định dạng artifact (`backend/app/indexes/`)

```
beit3.index / clip.index          FAISS IndexFlatIP
beit3_mapping.json                {"0": "http://localhost:8000/static/images/L25_V001-0000-3.jpg", ...}
keyframe_metadata.json            MỘT DANH SÁCH [ {...}, {...} ]  ← KHÔNG phải dict
```

Hai chỗ dễ sai:

- `*_mapping.json` chỉ có **một tiền tố duy nhất** cho cả 360.531 dòng. Mapping
  mới phải theo đúng dạng đó; `preprocess.py` cắt chuỗi tại `/static/` nên dạng
  khác sẽ dựng ra URL thiếu đoạn `images/` → ảnh 404.
- `keyframe_metadata.json` là **list**, không phải dict. `"tên.jpg" in metadata`
  **luôn False** và không báo lỗi gì cả. Nó nặng 136 MB nên cũng đừng ghi lại
  trong vòng lặp.

### Quy tắc cắt frame — và chỗ nó hụt

`notebooks/thanhbangcao/07..11_cut_frames_*.ipynb`, SECTION 06b:

```python
FLOOR_SECONDS     = 50 / 30    # ≈ 1,67 giây — hết sàn 2 ảnh
SECONDS_PER_EXTRA = 2.0        # sau sàn, cứ 2 giây thêm 1 ảnh
N_MIN, N_MAX      = 2, 40      # v001;  v002 hạ trần xuống 3
```

`sample_scene(s, e, fps)` **không nhìn một pixel nào** — nó ngầm cho rằng mỗi
giây phim mang lượng thông tin như nhau. Hai hệ quả đã đo được:

- Trần `N_MAX = 40` bắt đầu cắn từ cảnh dài hơn ~80 giây. **380 cảnh vượt ngưỡng
  đó (0,4%) nhưng chiếm 21,9% tổng thời lượng** — và **377/380 là L25**.
- Cảnh 672 giây được đúng 40 khung, tức hai khung cách nhau **17,2 giây**.

Năm notebook **không cùng phiên bản**: 07 đã là v002 (`N_MAX = 3`), 08–11 vẫn là
v001 (`N_MAX = 40`). Index L21–L30 đang chạy là **v001**. Đẩy v002 sang phần 2–5
sẽ làm cảnh 60 giây từ 32 khung còn 3 khung — tệ hơn 10 lần.

Notebook cắt cũng **không lọc độ nét**: `alg1_dedup_filter` chỉ được định nghĩa,
không nơi nào gọi. Bản demo cũ `[10_07]` thì có (Laplacian), nhưng khâu đó đã
mất khi chuyển sang quy tắc theo độ dài.

### `fps_map.json` là nguồn đúng, không phải `ffprobe`

BTC dùng chính bảng đó để đánh số frame trong đáp án. `ffprobe` có thể trả `30.0`
ở video BTC ghi `29.97` — lệch 20%, tới phút 20 là sai gần 4 phút, đủ trượt hẳn
cảnh chứa đáp án. Và **đừng "sửa" `29.97` thành `30000/1001`**: dùng `29.97` mới
tái lập đúng `frame_idx` của BTC.

### Thư mục KHÔNG được dùng

`Drive/MyDrive/aic26/Zipped/` — 30 file `K01.zip`…`L30.zip`, mỗi file 3–4 GB.
Đó là **bộ keyframe khác**, tên khung dạng `L21_V001-01-1003240.jpg` (mã cảnh
**2** chữ số). Batch vẫn là `L21` nên lọc theo batch **không chặn được**. Trộn
nó vào index là hỏng cả index mà không có dấu hiệu gì.

---

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

**Heredoc trên Windows.** `python - <<'PY'` đọc stdin bằng cp1252 — chuỗi tiếng
Việt nát, và **backslash bị đếm sai** nên `"\\,"` ra số lượng khác hẳn ý định.
Script có tiếng Việt hoặc có backslash thì **viết ra file bằng công cụ Write rồi
chạy**, đừng dùng heredoc. Bẫy này đã cắn nhiều lần.

**`ffmpeg-python` tự escape backslash của chính nó.** `.filter("select",
"not(mod(n\\,3))")` ra tới ffmpeg thành `not(mod(n\\\\\\\\\\,3))`; ffmpeg thoát
với EINVAL, stdout rỗng. Gọi ffmpeg bằng `subprocess` với mảng tham số tường
minh khi filter có dấu phẩy.

**Đừng nuốt stderr.** `pipe_stderr=True` rồi không đọc = thất bại **hoàn toàn im
lặng**; lỗi chỉ lộ ra ở chỗ khác dưới dạng `IndexError` trên mảng rỗng. Ghi
stderr ra file tạm (pipe đầy 64 KB thì tiến trình con block), và raise kèm nguyên
lệnh khi kết quả rỗng.

**HuggingFace trả 401 cho repo KHÔNG TỒN TẠI** — để không lộ repo private. Tên
gõ sai hiện ra y như lỗi thiếu token. Kiểm bằng `curl -s -o /dev/null -w "%{http_code}"
https://huggingface.co/api/models/<repo>` trước khi nghi ngờ đăng nhập.

**`timm==0.4.12` bị ghim cứng** trong `backend/requirements.txt` vì
`modeling_finetune.py` của BEiT3 dùng `timm.models.registry`, API đã bị xoá từ
timm ≥ 0.9. Model mới (PE-Core…) cần timm mới. **Hai thứ này không sống chung
được** — phải giải trước khi deploy bất kỳ encoder mới nào.

**`npm ci` xoá sạch `node_modules`** và làm chết dev server đang chạy. Trên máy
chủ repo dùng `npm install`.

**Vòng lặp vô hạn.** Các generator rải frame trong `backend/app/answers/autofill.py`
lặp `while produced < limit`. Nếu không có gì để sinh thì `produced` đứng yên và
nó quay mãi — pytest treo. Luôn lọc trước danh sách nguồn và `return` sớm khi rỗng.

**Cache hỏng vẫn là cache.** Một lần chạy lỗi kịp ghi `np.save` mảng rỗng xuống
đĩa; lần chạy sau nạp lên như thể kết quả thật, im ru. Ghi cache **sau cùng**,
và lúc nạp thì từ chối cache rỗng/dị dạng thay vì tin nó.

**Đĩa Colab.** Model tải về **không** được giải phóng bởi `del model`. PE-Core-bigG
9,01 GB · CLIP ViT-bigG 9,46 GB · PE-Core-L 2,50 GB. Nạp ba model trong một phiên
là ~21 GB. Đọc zip nhiều GB trên Drive còn làm FUSE cache phình thêm — lấy ảnh
qua HTTP rẻ hơn nhiều.

## Mô hình dữ liệu cần nhớ

- `answers.author_id` = **chủ danh sách**; `answers.created_by` = ai tạo dòng đó.
  Hai cái khác nhau, và mọi đường ghi phải khoá theo `author_id` — thiếu chỗ nào
  là người này sửa được bài người kia.
- `tasks.chosen_author_id` = danh sách của ai sẽ được nộp. `NULL` = chưa chọn.
- Câu chưa ai làm thì xuất ra **file rỗng**, không phải lỗi. Chỉ "có bài nhưng
  chưa chọn người" mới từ chối.
- Ảnh keyframe luôn nằm trên nền `--proto-dark`. Nền có màu làm lệch cảm nhận
  màu trong ảnh, mà so màu giữa hai khung mới là việc chính.

## Benchmark — cổng quyết định duy nhất

`backend/app/evaluation/seeds/` giữ **90 câu** (25 + 30 + 35) kèm video và khoảng
frame đúng. Đây là thứ duy nhất nói được một thay đổi có ăn hay không.

Hai bài học đã trả giá:

- Hướng fusion (OCR + ASR + RAM++) **lên ở vòng 1 nhưng xuống ở vòng 2**. Đo một
  vòng rồi kết luận là sai.
- Chạy lại cùng một policy có thể lệch tới **0,05 MRR**. So hai lần chạy đơn lẻ
  là đang so nhiễu; phải lấy trung bình nhiều lần lặp.

Một detector hoạt động hoàn hảo mà không nhấc được R@k thì vẫn là công cốc.

## Thói quen làm việc mà chủ repo đã xác nhận

- **Kiểm bằng kịch bản gọi API thật** với backend đang chạy, không chỉ unit test.
  Nhiều lỗi trong repo này chỉ lộ ra khi đi đúng luồng người dùng.
- **Notebook cũng phải kiểm được.** Viết xong thì compile từng ô, và chạy thử
  phần logic thuần trên dữ liệu thật hoặc dữ liệu giả có đặt bẫy — đừng đưa cho
  chủ repo một notebook mới chỉ "đọc thấy đúng".
- **Kiểm chỗ rẻ trước chỗ đắt.** Một phép thử đường dẫn 1 giây đặt trước bước
  chạy 20 phút đã cứu được vài lần.
- Sửa xong chạy đủ: `npx tsc -b`, `npm run lint`, `npm test`, `pytest`, `ruff`.
- Sửa UI xong thì kiểm module Vite đang phục vụ như trên.
- Xoá một tính năng thì **để lại chú thích nói vì sao bỏ và dùng gì thay** —
  đừng để chỗ đó trống trơn.

---

Sửa file này khi có quy tắc mới hoặc khi phát hiện một cái bẫy tốn thời gian.
