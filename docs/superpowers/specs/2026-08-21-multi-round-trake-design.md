# Nhiều vòng thi, nhật ký thao tác, và cách nộp TRAKE

2026-08-21

## Vấn đề

Ba việc, đến từ một buổi review:

1. **Import task thỉnh thoảng làm mất toàn bộ task.** Không rõ nguyên nhân, không
   ai truy được ai đã bấm gì.
2. **Cần lưu nhiều vòng** để admin quản lý nhiều bộ task, và chọn vòng nào được
   dùng.
3. **UI TRAKE chưa nộp được.** Không click vào frame để xem video tại khúc đó
   như KIS.

## Chẩn đoán: task không hề bị xoá

Không có đường nào trong hệ thống xoá task. Không `DELETE FROM tasks`, không
`DELETE FROM packs`. Task không bị xoá — nó bị **ẩn**.

`routers/packs.py`, trong `commit_pack`:

```sql
UPDATE packs SET active = 0 WHERE active = 1
```

`/api/board` chỉ đọc pack đang `active`, và frontend không bao giờ truyền
`pack_id`. Nên bất kỳ lần commit import thứ hai nào — thử lại, sửa regex, upload
nhầm — đều cho vòng đang thi nghỉ, kéo theo toàn bộ task và mọi đáp án dưới nó
biến khỏi mọi màn hình cùng lúc. Dữ liệu vẫn nằm nguyên trong SQLite; không giao
diện nào với tới được nữa.

Không có gì ghi lại việc đó, nên câu "ai đã bấm gì" không trả lời được.

## Quyết định

| | Chốt |
|---|---|
| Import và kích hoạt | Tách đôi. Import chỉ tạo vòng; kích hoạt là hành động riêng |
| Xoá vòng | Xoá mềm, khôi phục được. Từ chối xoá vòng đang dùng |
| Quyền xoá | **Giữ nguyên** — không siết gì cả (xem "Đã cắt") |
| Nhật ký | Ghi mọi thay đổi trạng thái và mọi lần xoá, kèm nội dung để khôi phục |
| TRAKE | Một hàng N ô trong kết quả TRAKE search, mỗi ô là một thẻ KIS |

### Đã cắt khỏi kế hoạch

**Siết quyền xoá.** Bản thảo đầu có mục 1.4 giới hạn `DELETE /api/answers/{id}`
theo người giữ task, và "Xoá sạch" chỉ cho admin. Bị loại bỏ theo yêu cầu.

Hệ quả cần biết: nút **"Xoá sạch"** trên màn Export vẫn hiện với mọi member và
`DELETE FROM answers` là xoá cứng. Nó không còn là nguyên nhân của lỗi mất task
— cái đó do phần import xử lý — nhưng vẫn là một đường mất dữ liệu riêng. Bù lại
bằng nhật ký: mọi lần xoá đều lưu nội dung và admin khôi phục lại được.

**Ghim mốc rồi chạy lại DP cho TRAKE.** `top_candidates()` hiện là top-10 toàn
video theo điểm riêng từng event, không biết các mốc khác nằm đâu, nên có thể đề
xuất frame đứng *trước* E1. Cách sửa là thêm tham số `pins` vào `/trake-search`
và một endpoint `/trake-event-search` để gõ lại mô tả một event trong một video.
Chưa nằm trong phạm vi lần này.

## Phần 1 — Backend

### 1.1 Cơ chế migration

`schema.sql` toàn `IF NOT EXISTS`, nên không thêm cột được: CREATE bị bỏ qua thì
cột mới không bao giờ xuất hiện. `db/migrations.py` chạy các bước đánh số theo
`PRAGMA user_version`, mỗi bước một transaction, chạy đúng một lần.

Bước 1: `ALTER TABLE packs ADD COLUMN deleted_at TEXT`.

### 1.2 Import không đụng vào vòng đang thi

Bỏ `UPDATE packs SET active = 0`, insert với `active = 0`. Đây là toàn bộ cách
lỗi xảy ra và nó biến mất ở dòng này.

### 1.3 API quản lý vòng

| Endpoint | Việc |
|---|---|
| `GET /api/admin/packs` | Danh sách vòng + số task, số đáp án, ai import |
| `POST /api/admin/packs/{id}/activate` | Một transaction: hạ mọi pack, nâng pack này |
| `PATCH /api/admin/packs/{id}` | Đổi tên, đặt deadline (`""` để xoá deadline) |
| `DELETE /api/admin/packs/{id}` | Xoá mềm. 409 nếu là vòng đang dùng |
| `POST /api/admin/packs/{id}/restore` | Hoàn tác xoá mềm |
| `GET /api/admin/audit` | Nhật ký |
| `POST /api/admin/audit/{id}/restore` | Khôi phục các dòng một lần xoá đã lấy đi |

Xoá mềm vì hai lý do. Xoá cứng không chạy được: `tasks.pack_id` và
`presence.task_id` không có `ON DELETE CASCADE`, nên xoá một vòng ai đó đã mở sẽ
ném lỗi khoá ngoại. Và với một công cụ mà khiếu nại chính là mất dữ liệu, xoá
không hoàn tác được là hướng sai.

Từ chối xoá vòng đang dùng thay vì tự động hạ nó xuống: xoá vòng đang thi sẽ làm
rỗng mọi bảng cùng lúc — đúng cái thất bại mà thay đổi này sinh ra để chặn.

### 1.5 / 1.7 Nhật ký và khôi phục

```sql
CREATE TABLE audit_log (
  id, at, user_id, action, target, summary, detail, restored_at
);
```

`detail` mang theo chính các dòng bị xoá. Một giỏ 100 dòng là vài KB JSON, đổi
lại một cú bấm nhầm trở thành khôi phục được chứ không chỉ giải thích được.

Khôi phục giữ nguyên `sort_key` cũ nên dòng về đúng chỗ trong giỏ — hạng 1 quay
lại là hạng 1, không rơi xuống đáy một danh sách mà thứ tự chiếm 1/5 điểm.
`restored_at` chặn khôi phục hai lần. Task đã mất thì bỏ qua dòng đó thay vì từ
chối cả lô.

### 1.6 Vá kèm

`/api/packs/active` là `SELECT * FROM packs WHERE active = 1` trần, không
`ORDER BY`, không lọc `deleted_at` — lệch với `/api/board`. Gộp thành một hàm
`_shared.active_pack()`.

## Phần 2 — Frontend

- **`pages/Rounds.tsx`** (admin): bảng các vòng + tab Nhật ký. Kích hoạt hỏi xác
  nhận nêu rõ đang đánh đổi gì — *"Vòng 1 (2 task, 3 đáp án) sẽ ngừng hiển thị"*.
- **Import** kết thúc tại chỗ với *"chưa kích hoạt"* + nút sang màn Vòng. Nhảy về
  Board sẽ vẫn hiện vòng cũ, trông y như import không có tác dụng.
- **Export** thêm bộ chọn vòng (admin), để xuất lại file của vòng cũ.
- **Root** so `board.round.id` với `task.pack_id` mỗi 10 giây. Lệch thì đóng task
  đang giữ và báo. Không có bước này, đa vòng tự nó tạo ra một kiểu mất-công-việc
  mới: member nộp đáp án vào vòng đã nghỉ, không export nào lấy tới.

## Phần 3 — UI nộp TRAKE

Một đáp án TRAKE là **một dòng, N frame, một video**: `L26_V194,4707,5100,5425,5850`.

Trước đó không có cách nào nộp một dòng hợp lệ. `App.tsx` và `SubmitForm` đều
dựng `Array.from({length: n_events}, () => frame)` — N bản sao của cùng một
frame; còn `TrakeCard`, thứ duy nhất hiển thị đúng N khoảnh khắc, không có đường
nào ghi vào giỏ.

Hàng N ô vốn đã đúng bố cục. Thiếu là mỗi ô chưa **hành xử** như thẻ KIS:

| Thẻ KIS | Ô sự kiện |
|---|---|
| viền tô theo điểm | giữ — dùng `TrakeEvent.score`, chuẩn hoá trong tập ứng viên của chính event đó |
| ảnh `aspect-[3/2]` | giữ |
| 🔍 mở VideoPopUp | giữ — nút nộp thành "Chốt cho E2" |
| tên + timestamp + % | giữ |
| `+` thêm vào giỏ | bỏ khỏi ô; thành một nút **Chọn** cho cả hàng |
| `⏱` mốc temporal | bỏ — vô nghĩa bên trong TRAKE |
| — | thêm dải ứng viên dưới mỗi ô |

Không có nháp, không có thanh đáy, không có dòng dở dang ở đâu cả. **Chọn** tắt
khi thiếu mốc, nên không đường nào ghi được dòng TRAKE thiếu frame vào giỏ.

`+` trên kết quả search thường ẩn đi khi task là TRAKE.

## Lỗi phát hiện dọc đường

- **`types/api.ts` dùng `||` thay vì `??`** cho `VITE_API_BASE_URL`. Chuỗi rỗng
  nghĩa là "same origin" — giá trị mà Vite proxy cần — bị `||` nuốt và thay bằng
  `localhost:8000`. Hậu quả: API cộng tác proxy đúng còn mọi lệnh search thì
  không. `api/base.ts` vốn đã dùng `??`.
- **`AnswerBasket`** hướng dẫn *"Bấm A trên một kết quả tìm kiếm"*. Nút trên màn
  hình tên là `+`.

## Kiểm chứng

Backend: 83 test, ruff sạch. Frontend: 35 test, tsc và eslint sạch, build xong.

Một kịch bản end-to-end qua HTTP (`e2e_rounds.py`) diễn lại đúng lỗi gốc: import
vòng 1, kích hoạt, nộp 3 đáp án, rồi import vòng 2 giữa lúc đang thi — vòng 1
vẫn là vòng đang dùng, task và đáp án còn nguyên.
