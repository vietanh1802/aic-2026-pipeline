# Cải tiến frontend v2 — tám hạng mục từ spec.md

2026-08-26

## Bối cảnh

`spec.md` (round 1) gom góp ý của bốn thành viên sau vòng sơ tuyển. Lọc ra
những mục thuộc frontend, đối chiếu với code hiện tại, còn lại tám hạng mục —
tất cả làm được **thuần frontend, không đụng backend**:

| # | Hạng mục | Nguồn (spec.md) |
|---|---|---|
| 1 | Nút đóng/xoá to hơn | Bằng, dòng 28 |
| 2 | Hover preview frame trong giỏ | Văn An, dòng 5 |
| 3 | Focus vào clip cụ thể | Văn An, dòng 4 |
| 4 | Xem kết quả của đồng đội | Bằng, dòng 27 |
| 5 | Trải K dòng trên đoạn đã đánh dấu (KIS/Q&A) | Bằng, dòng 29–31 + trao đổi |
| 6 | TRAKE: trải đều N mốc + trả về DP | Bằng, dòng 32 |
| 7 | Nhập đáp án thủ công | Vanh, dòng 36 |
| 8 | Goto frame | Phát, dòng 25 + trao đổi |

Mục 5 được làm rõ qua trao đổi: cách chấm là R@k mà đề KIS mô tả **một
khoảng** trong video chứ không phải một khoảnh khắc, nên thao tác thật của
người thi là thêm điểm đầu + cuối → giữa → rồi chia tiếp — từng dòng một,
bằng tay, rất chậm. Cần một nút làm cả chuỗi đó trong một cú bấm.

Mục 8 được chốt là "goto frame": dán một frame ID đồng đội nhắc đến → mở ngay
video tại đúng frame đó. Không phải image-similarity search.

### Đã cắt khỏi phạm vi

- **Lưu bộ query cũ + ground truth** (Phát 1e) — bỏ theo yêu cầu khi review
  thiết kế. (Phần lưu trữ pack thì màn Rounds đã có sẵn từ thiết kế
  2026-08-21.)
- **Pipeline test tự động** (Phát 1a–d) — nhánh riêng, đúng như 1c đề xuất.
- **Sửa lỗi chạy TRAKE, VLM verifier, cắt frame, encoding zip** — thuộc
  backend/pipeline, không nằm trong spec frontend này.
- **Ghim mốc rồi chạy lại DP cho TRAKE** (`pins` / `/trake-event-search`) —
  giữ nguyên quyết định cắt của thiết kế 2026-08-21. Trải đều + chỉnh tay
  (mục 6) đáp ứng nhu cầu thực tế mà không cần backend.

## Quyết định

| | Chốt |
|---|---|
| Hướng chung | Thuần frontend — không endpoint mới, không migration |
| Trải K dòng | Gọi `addAnswer` tuần tự theo thứ tự ưu tiên bisection; không atomic, lỗi giữa chừng thì báo "đã thêm i/K" và dừng |
| Xem đồng đội | Tích hợp vào Board + giỏ, không tab mới; giỏ của người khác là chỉ-đọc ở tầng UI |
| Mở popup từ ngoài App | Store zustand nhỏ (`popupStore`) thay vì nâng state lên Root |
| Ảnh cho dòng giỏ | Suy ra keyframe gần nhất phía client bằng `findMatchingKeyframes` + `keyframes.json`, không hỏi backend |

## Thiết kế

### Hạ tầng chung (phục vụ mục 1, 4, 8)

**`store/popupStore.ts` — mới.** Yêu cầu mở video popup từ bất kỳ đâu:

```ts
type PopupRequest = { videoId: string; frameIdx: number } | null;
// open(videoId, frameIdx) / clear()
```

`App.tsx` subscribe: khi có request thì mở `VideoPopup` đúng như luồng nội bộ
hiện tại (suy `frameId`, `startTime` qua `startMsAt`) rồi `clear()`. Các chỗ
mở popup sẵn có trong App giữ nguyên, không đi qua store. Người ghi:
`GotoFrame`, dòng giỏ trong `AnswerBasket` và `AnswerPanel`.

**`helpers/videoSource.ts` — thêm `keyframeUrl(name)`.** Ghép URL ảnh keyframe
`<API base>/static/images/<name>.jpg` — cùng gốc với `url` mà backend trả
trong kết quả search. Một chỗ duy nhất biết quy tắc này.

**`components/FramePreview` — mới.** Props: `videoId`, `frameIdx`, `size`.
Tự tìm keyframe gần nhất (`findMatchingKeyframes` trên `keyframes.json`,
chọn bên gần hơn trong `smaller`/`larger`), render qua `KeyframeImg` nên ảnh
thiếu tự xuống cấp thành ô "Chưa tải ảnh". Không tự định vị — chỗ dùng quyết
định thumbnail hay floating.

### 1. Nút đóng/xoá to hơn

Mọi nút dismiss nhỏ được nâng vùng bấm lên tối thiểu 40×40px bằng padding,
giữ nguyên glyph và màu hover:

- `VideoPopUp/index.tsx` — nút `×` góc trên phải (hiện `text-xl` không padding)
- `AnswerBasket/index.tsx` — `×` và `↑1` trên từng dòng, `×` header
- `CandidateResults/index.tsx` — `✕` của Lightbox

### 2. Hover preview trong giỏ

Trong `AnswerBasket` và `AnswerPanel`, mỗi dòng đáp án:

- thumbnail ~48px luôn hiện bên trái dòng (`FramePreview` cỡ nhỏ), lấy frame
  đầu tiên của dòng;
- hover vào dòng → preview phóng to ~360px nổi cạnh dòng (`FramePreview` cỡ
  lớn), đè lên trên danh sách, biến mất khi rời chuột. Chỉ CSS/hover state,
  không fetch gì thêm ngoài chính ảnh đó.

### 3. Focus vào clip

`useSearchStore` thêm `focusVideos: string[]` + `toggleFocusVideo`,
`clearFocus`. Nút 🎯 trên từng thẻ kết quả (`FrameDisplay`) và trên header
nhóm video (App, chế độ sort theo video_id) toggle video vào danh sách.

Khi danh sách khác rỗng:

- lưới kết quả chỉ hiện các video trong danh sách (lọc trong `App.tsx`
  trước khi render, áp cho cả hai chế độ sort);
- một thanh pill trên vùng kết quả liệt kê từng video đang focus (mỗi pill
  có `×` riêng) + nút "Xoá lọc";
- nhãn đếm đổi thành "X/Y kết quả (đang lọc)" — filter bị quên không thể
  giả dạng search hỏng.

Filter **sống qua các lần search** (chủ đích: gõ lại query nhiều lần để soi
cùng vài clip nghi ngờ), chỉ mất khi tự xoá.

### 4. Xem kết quả của đồng đội

Không tab mới — tích hợp:

- **Dòng giỏ bấm được**: click vào dòng (ngoài các nút) trong `AnswerBasket`
  / `AnswerPanel` → `popupStore.open(video_id, frames[0])` → popup mở đúng
  video tại frame đó. Đây chính là "click frame ID → hiện ngay video".
- **Lối tắt từ Board**: ô đếm đáp án (`12/100`) thành nút với task đã có
  người giữ → mở task đó (đường "Xem" sẵn có) **và** mở luôn giỏ. Root nhận
  thêm cờ `openBasket` trong handler `onOpenTask`.
- **Chỉ-đọc khi không phải giỏ mình**: task đang mở không thuộc mình
  (`task.owner?.id !== me?.id`) → ẩn `×`, `↑1`, panel autofill, nhập tay;
  thay hàng hành động bằng ghi chú "đang xem giỏ của <tên>". Backend vẫn cho
  sửa (quyết định "Đã cắt" 2026-08-21 giữ nguyên) — chặn ở UI là đủ cho
  round này.
- Dòng có thêm `title` tên người tạo (màu stripe mine/mate đã có sẵn).

### 5. Trải K dòng trên đoạn đã đánh dấu (KIS/Q&A)

**`helpers/frameRange.ts` — thêm `spreadFrames(start, end, k): number[]`.**
Trả về tối đa `k` frame **duy nhất**, theo thứ tự ưu tiên bisection:

```
[đầu, cuối, giữa, giữa-nửa-trái, giữa-nửa-phải, …]
```

Cài bằng BFS trên các nửa khoảng: phát `start`, `end`, rồi lần lượt điểm
giữa của từng khoảng con, bỏ trùng. Đoạn ngắn tự co: `[100,102]` với k=5 →
`[100, 102, 101]` — 3 dòng, không đệm.

**UI — `SubmitForm` trong `VideoPopUp`.** Cạnh "Add Answer" (vẫn nộp điểm
giữa như cũ): nút **"Trải K dòng"** + chọn K (3/5/7/9, mặc định 5). Bật khi
đã có cả hai mốc I/O và task là KIS/Q&A (TRAKE bị disable như strip hiện
tại). Bấm → gọi `addAnswer` tuần tự đúng thứ tự trả về, nên rank trong giỏ =
thứ tự ưu tiên. Nút hiện tiến độ "3/5…"; lỗi giữa chừng → "đã thêm i/K dòng"
rồi dừng, các dòng đã vào giữ nguyên (xoá lẻ được), không tự retry. Task
Q&A: các dòng mang answer text đang gõ trong popup, như một lần add đơn.

### 6. TRAKE: trải đều + trả về DP

- **"Trải đều"** — nút mới trên header thẻ TRAKE (cạnh "Chọn"): lấy span =
  min→max frame trên toàn bộ ứng viên của thẻ, chia đều N vị trí
  (`round(min + i·(max−min)/(N−1))`), mỗi vị trí **snap về keyframe thật gần
  nhất** qua `findMatchingKeyframes` (có ảnh, có tên); không có keyframe thì
  rơi về frame thô kiểu `byHand`. Kết quả ghi vào `trakeSwaps` cho cả N slot
  — từ đó luồng như cũ: chỉnh từng slot qua strip/lightbox/popup, "Chọn" để
  commit.
- **"↩ DP"** — slot đang bị swap có nút trả về lựa chọn của DP (xoá key khỏi
  `trakeSwaps`); hiện tại swap là một chiều, thử nghiệm xong không quay lại
  được.

### 7. Nhập đáp án thủ công

`AnswerBasket`, dưới panel autofill: control **"+ Nhập tay"** gấp gọn. Mở ra:

- `video_id` — input có datalist autocomplete từ key của `fps_map.json`;
  video lạ chặn submit kèm thông báo;
- `frames` — một số cho KIS/Q&A; danh sách phẩy đúng `n_events` giá trị cho
  TRAKE (thiếu/thừa chặn submit); số nguyên không âm;
- `answer_text` — chỉ hiện với Q&A.

Submit qua `addAnswer` sẵn có. Đây là lối thoát cho "hệ thống không tìm ra
kết quả" — không cần kết quả search nào.

### 8. Goto frame

`components/GotoFrame` — mới, đặt ở hàng header màn search. Một input nhận:

1. `L01_V001 1234` (video + cách + frame)
2. `L01_V001-1234` (video-frame)
3. tên file keyframe đầy đủ (parse bằng `frameIdFromName` /
   `videoIdFromFrame` sẵn có)

Parse xong validate video trên `fps_map.json` (sai → báo inline ngay dưới ô)
rồi `popupStore.open()`. Enter để đi; không nút riêng.

## Xử lý lỗi

- Trải K dòng: báo tiến độ, dừng tại lỗi, không retry ngầm (xem mục 5).
- Nhập tay + goto frame: validate `video_id` trên `fps_map.json` **trước**
  khi gọi API; sai thì báo inline, không request.
- Giỏ người khác: chỉ-đọc ở UI (xem mục 4).
- Mọi mặt ảnh mới đi qua `KeyframeImg` → thiếu ảnh thành ô "Chưa tải ảnh".

## Kiểm thử

Vitest, theo pattern `helpers/*.test.ts` sẵn có; cài đặt theo TDD:

- `spreadFrames` — thứ tự bisection, bỏ trùng đoạn ngắn, k > span, start=end;
- parser của `GotoFrame` — cả 3 dạng nhập + các chuỗi phải bị từ chối;
- `keyframeUrl` — ghép đúng gốc API;
- selector lọc focus — lọc đúng, đếm "X/Y" đúng, rỗng = không lọc;
- trải đều TRAKE — chia N vị trí đúng công thức, snap về keyframe gần nhất,
  fallback khi không có keyframe.

## Tệp đụng tới

Mới: `store/popupStore.ts`, `components/FramePreview/`,
`components/GotoFrame/`.

Sửa: `App.tsx`, `Root.tsx`, `pages/Board.tsx`, `components/AnswerBasket/`,
`components/VideoPopUp/` (`index`, `AnswerPanel`, `SubmitForm`),
`components/CandidateResults/`, `components/FrameDisplay/`,
`components/ResultInfoAndSort/` (nhãn "X/Y (đang lọc)"),
`store/useSearchStore.ts`, `helpers/frameRange.ts`,
`helpers/videoSource.ts`.
