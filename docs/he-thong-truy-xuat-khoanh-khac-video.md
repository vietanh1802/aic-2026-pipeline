# Hướng tới Hệ thống Truy xuất Khoảnh khắc Hiệu quả và Bền vững: Một Khung Thống nhất cho Mô hình Đa Mức độ Chi tiết và Xếp hạng lại theo Thời gian

> *Towards Efficient and Robust Moment Retrieval System: A Unified Framework for Multi-Granularity Models and Temporal Reranking*
> arXiv:2504.08384v1 [cs.CV] — 11/04/2025

## Nhóm tác giả

Huu-Loc Tran¹, Tinh-Anh Nguyen-Nhu², Huu-Phong Phan-Nguyen¹, Tien-Huy Nguyen¹, Nhat-Minh Nguyen-Dich³, Anh Dao⁴, Huy-Duc Do⁵, Quan Nguyen⁶, Hoang M. Le⁷, Quang-Vinh Dinh⁸

| # | Đơn vị |
|---|--------|
| 1 | Trường Đại học Công nghệ Thông tin, ĐHQG-HCM, Việt Nam |
| 2 | Trường Đại học Bách khoa, ĐHQG-HCM, Việt Nam |
| 3 | Trường Đại học Bách khoa Hà Nội, Việt Nam |
| 4 | Michigan State University, Hoa Kỳ |
| 5 | Trường Đại học Kinh tế Quốc dân, Hà Nội, Việt Nam |
| 6 | Học viện Công nghệ Bưu chính Viễn thông, Hà Nội, Việt Nam |
| 7 | York University, Canada |
| 8 | AI VIETNAM Lab |

*Tất cả các tác giả đóng góp ngang nhau. Nghiên cứu được tài trợ hoàn toàn bởi AI VIETNAM.*

---

## Tóm tắt

Việc hiểu video dạng dài (long-form video) đặt ra thách thức lớn cho các hệ thống truy xuất tương tác, vì các phương pháp thông thường khó xử lý hiệu quả khối lượng nội dung video khổng lồ. Các cách tiếp cận hiện có thường chỉ dựa vào một mô hình đơn lẻ, lưu trữ kém hiệu quả, tìm kiếm theo thời gian thiếu ổn định, và xếp hạng lại không quan tâm tới ngữ cảnh — tất cả đều hạn chế hiệu quả tổng thể.

Bài báo đề xuất một khung (framework) mới nhằm cải thiện truy xuất video tương tác thông qua **bốn đóng góp chính**:

1. **Chiến lược tìm kiếm tổ hợp (ensemble search)** kết hợp mô hình thô (CLIP) và mô hình chi tiết (BEiT-3) để nâng cao độ chính xác truy xuất.
2. **Kỹ thuật tối ưu lưu trữ** giảm dư thừa bằng cách chọn các keyframe đại diện thông qua TransNetV2 và loại bỏ trùng lặp.
3. **Cơ chế tìm kiếm theo thời gian** định vị đoạn video bằng cặp truy vấn kép cho điểm bắt đầu và điểm kết thúc.
4. **Phương pháp xếp hạng lại theo thời gian** tận dụng ngữ cảnh của các khung hình lân cận để ổn định thứ hạng.

Được đánh giá trên các tác vụ tìm kiếm mục tiêu đã biết (known-item search) và hỏi–đáp (question answering), khung đề xuất cho thấy cải thiện đáng kể về độ chính xác, hiệu suất và khả năng diễn giải cho người dùng.

---

## 1. Giới thiệu

Những tiến bộ gần đây của học sâu đã cải thiện đáng kể các tác vụ thị giác cốt lõi như nhận dạng, thích ứng miền và trả lời câu hỏi trực quan, mở đường cho các hệ thống hiểu video mạnh mẽ hơn. Tuy nhiên, phần lớn các phương pháp hiện có được thiết kế cho các đoạn video ngắn — thường chỉ vài giây đến vài phút — nên không phù hợp với các kịch bản thực tế liên quan đến video dạng dài. Khoảng trống này là thách thức lớn cho các ứng dụng như truy xuất video dựa trên nội dung và giám sát, nơi việc xử lý nội dung dài hàng giờ là bắt buộc.

**Truy xuất video tương tác** đã nổi lên như một giải pháp hứa hẹn nhờ kết hợp phân tích tự động với đầu vào của con người. Các tiến bộ gần đây, được kiểm chứng qua các cuộc thi như TRECVID và VBS (Video Browser Showdown), cho thấy sự cộng tác người–máy không chỉ tinh chỉnh kết quả tự động theo thời gian thực mà còn nâng cao đáng kể hiệu quả tìm kiếm.

### Các hướng tiếp cận hiện tại

| Hướng tiếp cận | Cơ chế | Hạn chế |
|---|---|---|
| Truy xuất dựa trên văn bản | So khớp truy vấn với metadata, phụ đề, hoặc embedding học sâu (CLIP, W2VV++) | Khả năng diễn giải kém |
| Dựa trên khái niệm (concept-based) | Dùng phát hiện đối tượng và phân loại cảnh để gán nhãn ngữ nghĩa cấp cao | Giới hạn bởi tập nhãn định sẵn, chú thích thiếu nhất quán |
| Tìm kiếm trực quan theo nội dung | Truy xuất khung hình tương tự bằng đặc trưng CNN | Có thể trả về kết quả không liên quan về ngữ nghĩa |
| Truy vấn phác thảo / không gian | Biểu đạt ý định tìm kiếm bằng hình ảnh | Độ biến thiên diễn giải cao |

### Bốn hạn chế then chốt được giải quyết

1. **Phụ thuộc một mô hình duy nhất** → hạn chế khả năng nắm bắt đồng thời ngữ nghĩa tổng quát và chi tiết tinh vi.
2. **Lập chỉ mục mọi khung hình** → dư thừa, gây tốn kém lưu trữ và làm chậm tìm kiếm.
3. **Tìm kiếm theo thời gian không ổn định** → khó định vị chính xác chuỗi sự kiện.
4. **Xếp hạng lại truyền thống bỏ qua ngữ cảnh thời gian** → thứ hạng thiếu nhất quán.

### Bốn đóng góp tương ứng

1. **Ensemble Search** — kết hợp mô hình mức thô (ngữ nghĩa rộng) với mô hình mức tinh (chi tiết) để cho kết quả bền vững hơn.
2. **Storage Optimization** — chọn keyframe đại diện qua khử trùng lặp thông minh, cắt giảm đáng kể nhu cầu lưu trữ mà không hy sinh chất lượng tìm kiếm.
3. **Temporal Search** — cơ chế truy vấn kép (điểm bắt đầu + điểm kết thúc) định vị chính xác đoạn video theo trình tự thời gian.
4. **Temporal Reranking** — tận dụng thông tin ngữ cảnh từ các khung hình lân cận để tinh chỉnh thứ tự ứng viên, giữ tính mạch lạc cấu trúc.

---

## 2. Các nghiên cứu liên quan

Nghiên cứu về truy xuất video phát triển theo hai hướng bổ trợ nhau: **truy xuất khoảnh khắc trong một video đơn lẻ (SVMR)** và **truy xuất ở cấp kho ngữ liệu (VCMR)** — vừa xác định video liên quan, vừa định vị khoảnh khắc tương ứng.

### 2.1. Truy xuất khoảnh khắc video (Video Moment Retrieval)

**Mục tiêu:** định vị một đoạn mục tiêu trong video chưa cắt xén dựa trên truy vấn ngôn ngữ tự nhiên.

- **Hướng dựa trên đề xuất (proposal-based):** sinh ra các đoạn ứng viên rồi xếp hạng theo mức độ liên quan với truy vấn.
- **Hướng không dùng đề xuất (proposal-free):** hồi quy trực tiếp biên thời gian bằng cơ chế chú ý lặp giữa khung hình và từ trong truy vấn, thường tận dụng kiến trúc transformer.

**Mở rộng sang VCMR** — trước tiên chọn video ứng viên từ một kho lớn, sau đó định vị khoảnh khắc trong video đã chọn. Các phương pháp chia thành:

- **Một giai đoạn (one-stage):** thực hiện truy xuất và định vị đồng thời theo kiểu đầu-cuối. Ví dụ **HERO** dùng bộ mã hóa transformer phân cấp tích hợp tín hiệu thị giác và văn bản xuyên phương thức.
- **Hai giai đoạn (two-stage):** truy xuất video ứng viên dựa trên độ tương đồng văn bản–video toàn cục, rồi định vị chi tiết trên từng ứng viên. **CONQUER** là ví dụ tiêu biểu với cơ chế xếp hạng nhận biết truy vấn, mở rộng tốt cho quy mô lớn.

**Ảnh hưởng của mô hình ngôn ngữ lớn:** một số nghiên cứu gần đây tích hợp việc hiểu video và truy xuất khoảnh khắc vào khung dự đoán token kế tiếp. Ngoài ra, kỹ thuật sinh cũng được khai thác — ví dụ **MomentDiff** mô hình hóa truy xuất khoảnh khắc như một quá trình khuếch tán, tinh chỉnh dần các đề xuất thời gian ngẫu nhiên thành đoạn đúng.

### 2.2. Hệ thống truy xuất tương tác

Các pipeline tự động hoàn toàn vẫn gặp khó với truy vấn phức tạp và video dài. Hệ thống truy xuất tương tác đưa con người vào vòng lặp (human-in-the-loop). Các benchmark như **VBS** thúc đẩy nghiên cứu về phương pháp tương tác đa phương thức kết hợp văn bản, phác thảo, bộ lọc và khung hình mẫu. Một số công trình đề xuất khung học tăng cường học từ phản hồi người dùng; số khác giới thiệu hệ thống tương tác dạng hỏi–đáp mô phỏng tương tác người dùng bằng mô hình VideoQA.

---

## 3. Phương pháp

### 3.1. Định nghĩa bài toán

Cho một kho video chưa cắt xén $\mathcal{V}$ và một truy vấn văn bản $q$, mục tiêu của VCMR là xác định khoảnh khắc $m^* = (t^s, t^e)$ khớp nhất với $q$, trong đó $t^s$ và $t^e$ lần lượt là mốc thời gian bắt đầu và kết thúc:

$$m^* = \arg\max_{m} P(m \mid q, \mathcal{V}) \tag{1}$$

Quy trình VCMR gồm hai giai đoạn:

1. Truy xuất các khoảnh khắc ứng viên $m$ từ các video trong kho.
2. Định vị chính xác khoảnh khắc tối ưu $m^*$ trong video được chọn $v^*$.

Hệ thống còn tích hợp thành phần **Hỏi–Đáp (QA)**, cho phép người dùng tương tác với các khoảnh khắc đã định vị để thu được câu trả lời tinh chỉnh dựa trên ngữ cảnh bổ sung.

**Chuyển sang truy xuất cấp ảnh.** Vì phương pháp truy xuất cấp video khó nắm bắt chi tiết thời gian tinh vi, nhóm tác giả chuyển sang cách tiếp cận cấp ảnh — coi từng khung hình là đơn vị truy xuất cơ bản. Nhược điểm thiếu ngữ cảnh thời gian được bù đắp bằng ba thành phần: **reranking** (3.3), **ensemble search** (3.4) và **mô hình hóa thời gian** (3.5).

### 3.2. Lưu trữ dữ liệu

Chiến lược lưu trữ tối ưu là yếu tố then chốt. Bằng cách chọn một tập khung hình tối thiểu nhưng đại diện, hệ thống giảm dư thừa và tăng hiệu quả truy xuất mà không ảnh hưởng độ chính xác. Gồm ba giai đoạn:

#### 3.2.1. Chọn keyframe

Sử dụng **TransNetV2** — mô hình học sâu nhanh và chính xác cho phát hiện chuyển cảnh. Đây là kiến trúc lai CNN + RNN, xuất sắc trong việc phát hiện cả cắt cứng (hard cut) lẫn chuyển cảnh dần dần. Mô hình xử lý tuần tự các khung hình đầu vào và xác định xác suất chuyển cảnh, cho phép phân đoạn cảnh chính xác.

Sau khi phát hiện chuyển cảnh, hệ thống **lấy mẫu 4 khung hình cách đều nhau trong mỗi cảnh** dựa trên chỉ số khung hình, thay vì lưu toàn bộ. Chiến lược này bảo đảm biểu diễn vừa đa dạng vừa gọn nhẹ cho mỗi cảnh.

#### 3.2.2. Trích xuất đặc trưng

Sử dụng hai bộ trích xuất mạnh: **BEiT-3** và **CLIP**. Cả hai đều đạt hiệu năng vượt trội trên nhiều bộ dữ liệu chuẩn, có khả năng sinh embedding chiều cao, nắm bắt các quan hệ trực quan phức tạp mà mô hình CNN truyền thống có thể bỏ sót.

#### 3.2.3. Tối ưu lưu trữ

Dù chỉ giữ 4 keyframe mỗi cảnh, vẫn có thể còn khung hình dư thừa. Nhóm tác giả áp dụng thuật toán loại trùng dựa trên độ tương đồng đặc trưng:

- Tính **cosine similarity** giữa các keyframe trong cùng một cảnh, dùng embedding từ BEiT-3 và CLIP.
- Nếu một khung hình có điểm tương đồng **> 0.9** với bất kỳ khung hình nào khác trong cùng cảnh → coi là gần trùng lặp và bị loại bỏ.

**Thuật toán 1 — Lọc khung hình (Frame Filtering)**

```
1:  for mỗi group, values trong grouped_videos do
2:      Tải ranh giới cảnh từ file
3:      Khởi tạo id = 0 và frame_in_scene = []
4:      Đặt ngưỡng S ← 0.9
5:      for mỗi key, path trong values do
6:          if khung hình hiện tại nằm trong ranh giới cảnh then
7:              Thêm khung hình vào frame_in_scene
8:          else
9:              Tính embedding: f ← embedding của khung hình
10:             Tính độ tương đồng: E = sim(f1, f2)
11:             Xác định khung hình dư thừa (nếu E > S)
12:             Loại bỏ khung hình dư thừa
13:             Chuyển sang cảnh kế tiếp (id += 1)
14:             Đặt lại frame_in_scene
15:         end if
16:     end for
17: end for
```

Toàn bộ embedding sau tối ưu được lưu vào **chỉ mục FAISS** (CLIP/BEiT-3).

### 3.3. Xếp hạng lại (Reranking)

Phương pháp **tổng hợp điểm lân cận (neighbor score aggregation)** được xem là một cách chọn keyframe mạnh vì tăng cường đồng thời **tính ổn định** và **tính liên quan theo thời gian**.

Lập luận nền tảng: vì mô hình phát hiện chuyển cảnh đã được dùng để lấy keyframe, các vùng xung quanh một keyframe rất có khả năng chia sẻ đặc trưng thị giác/ngữ nghĩa chung, hoặc phản ánh dịch chuyển thời gian trong cùng một shot. Nhờ đó:

- Bảo đảm chọn keyframe đáng tin cậy khi các lân cận cục bộ có độ tương đồng thị giác ổn định.
- Bảo đảm tính mạch lạc thời gian khi nội dung truy vấn mô tả chuyển động trải rộng qua các khung hình kề nhau.

Điểm số tổng hợp củng cố keyframe ứng viên dựa trên các lân cận ổn định — cả về mặt ngữ nghĩa lẫn điểm số — tạo nên biểu diễn mạnh cho cảnh. Với truy vấn mô tả tính thời gian, việc tổng hợp theo lân cận thể hiện rõ ngữ cảnh động mà truy vấn muốn diễn tả. Các tình huống cực đoan như thay đổi cảnh đột ngột được xử lý bằng bước kiểm tra điểm có điều kiện, lọc bỏ phần đóng góp không liên quan hoặc bị thiếu, nhờ đó đạt độ bền vững hợp lý.

**Thuật toán 2 — Tổng hợp điểm lân cận (Neighbor Score Aggregation)**

```
Yêu cầu: Tập chỉ số I, Truy vấn Q
1:  function AGGREGATENEIGHBORSCORES(I, Q)
2:      Khởi tạo từ điển aggregated_score A
3:      for mỗi idx trong I do
4:          key ← chuyển idx sang số nguyên
5:          neighbors ← GETNEIGHBORS(key)
6:          total_score ← 0
7:          for mỗi lân cận N trong neighbors do
8:              score ← COMPUTESCORE(N, Q)
9:              if score ≠ None then
10:                 Thêm lân cận vào danh sách chỉ số
11:                 total_score ← total_score + score
12:             end if
13:         end for
14:         UPDATESCORES(A, key, total_score)
15:     end for
16:     sorted_scores ← SORT(A, giảm dần)
17:     return sorted_scores
18: end function
```

### 3.4. Tìm kiếm tổ hợp (Ensemble Search)

Truy xuất ảnh–văn bản đòi hỏi đồng thời **hiểu thị giác chi tiết** và **căn chỉnh khái niệm ở mức thô**:

| Mô hình | Điểm mạnh | Điểm yếu | Nguyên nhân từ huấn luyện |
|---|---|---|---|
| **BEiT-3** | Căn chỉnh ảnh–văn bản chi tiết | Có thể bỏ sót ngữ cảnh rộng | Tập trung vào hiểu ngữ nghĩa toàn diện |
| **CLIP** | Truy xuất zero-shot tốt | Khó phân biệt chi tiết tinh vi | Học biểu diễn cô đọng từ văn bản hạn chế |

Để cân bằng **precision** và **recall**, nhóm tác giả đề xuất phương pháp ensemble kết hợp thế mạnh của cả hai.

**Thuật toán 3 — Ensemble Search**

```
Yêu cầu: query (chuỗi), model_configs (danh sách (model_name, weight, use_flag))
Kết quả: ranked_results (danh sách (index, score))
1:  Khởi tạo score_dict rỗng
2:  Chuẩn hóa trọng số: Σ wᵢ = 1 cho các mô hình được chọn
3:  for mọi (model_name, w, use_flag) ∈ model_configs do
4:      if use_flag then
5:          Nạp mô hình và processor cho model_name
6:          e ← EncodeText(model_name, query)
7:          I, S ← Search(model_name_idx, e, M = 50)
8:          S_max ← max(S)
9:          for mọi (i, s) ∈ (I, S) do
10:             score_dict[i] += (s / S_max) × w
11:         end for
12:     end if
13: end for
14: ranked_results ← Sort(score_dict, giảm dần)
15: return ranked_results
```

**Quy trình:**

1. Mã hóa truy vấn văn bản bằng cả hai mô hình với phương pháp tokenization riêng, chuẩn hóa về độ dài đơn vị.
2. Dùng embedding riêng của từng mô hình để truy xuất **top M** kết quả từ chỉ mục tương ứng.
3. Chuẩn hóa điểm tương đồng của mỗi mô hình theo giá trị lớn nhất của chính nó, tránh chênh lệch thang đo.
4. Áp trọng số phản ánh mức đóng góp tương đối của từng mô hình.
5. Cộng gộp điểm có trọng số theo từng định danh ảnh (ảnh xuất hiện ở cả hai tập kết quả sẽ được cộng dồn).
6. Sắp xếp giảm dần để tạo danh sách vừa chi tiết chính xác vừa liên quan rộng, khắc phục hạn chế của từng mô hình riêng lẻ.

### 3.5. Tìm kiếm theo thời gian (Temporal Search)

Tìm kiếm video theo thời gian khó vì bản chất động của nội dung thị giác và sự phụ thuộc giữa các khung hình. Khác với truy xuất ảnh tĩnh, nó phải xác định không chỉ khung hình liên quan mà cả **khoảng thời gian** để định vị sự kiện chính xác. Một khung hình đơn lẻ chỉ cho ước lượng thô, không có biên thời gian rõ ràng.

**Chiến lược tìm kiếm hai chiều (bidirectional):**

- Giả định khung hình đầu vào (đã truy xuất và rerank) là khung tham chiếu đúng.
- Mở rộng **sang trái** từ chỉ số khung đầu vào cho đến khi tìm được **20 khung liên quan** hoặc điểm tương đồng rơi xuống dưới ngưỡng chấp nhận.
- Áp dụng đối xứng **sang phải**.
- Chọn cặp khung hình tối ưu: hai khung có điểm tương đồng cao nhất với truy vấn tương ứng, đồng thời khoảng cách thời gian (bao gồm khung đầu vào) không vượt quá ràng buộc định trước $\text{gap}_C$.

**Thuật toán 4 — Chọn cặp khung hình theo thời gian (Temporal Frame Pair Selection)**

```
1:  function FINDBESTFRAMEPAIR(query_1, query_2, input_frame, index, img_path, gap_C)
2:      Xác định video và frame ID từ input_frame
3:      Khởi tạo danh sách khung hình liên quan bên trái và bên phải
4:      Đặt ngưỡng tương đồng để lọc khung hình
5:      while Khung hình còn liên quan và chưa vượt giới hạn do
6:          Tính độ tương đồng với query_1
7:          Dừng nếu độ tương đồng quá thấp
8:          Thêm khung hình vào danh sách trái và dịch sang trái
9:      end while
10:     while Khung hình còn liên quan và chưa vượt giới hạn do
11:         Tính độ tương đồng với query_2
12:         Dừng nếu độ tương đồng quá thấp
13:         Thêm khung hình vào danh sách phải và dịch sang phải
14:     end while
15:     Gom tất cả khung hình ứng viên từ trái, hiện tại và phải
16:     Tìm cặp khung hình tối đa hóa độ tương đồng kết hợp
17:     Bảo đảm cặp khung hình thỏa ràng buộc thời gian (gap_C)
18:     return cặp khung hình khớp nhất
19: end function
```

### 3.6. Hệ thống truy xuất video tương tác

Hệ thống phục vụ hai tác vụ cốt lõi: **Truy xuất Khoảnh khắc (Moment Retrieval)** và **Hỏi–Đáp Video (Video QA)**. Giao diện thân thiện cho phép nhập truy vấn, chọn chiến lược tìm kiếm và tinh chỉnh kết quả theo vòng lặp.

#### 3.6.1. Truy xuất khoảnh khắc

Người dùng nhập truy vấn văn bản tự do. Hai chiến lược truy xuất được cung cấp để điều chỉnh cách hệ thống ưu tiên khung hình ứng viên:

- **Neighbors-based reranking** — tinh chỉnh kết quả ban đầu bằng độ tương đồng cục bộ giữa các khung hình.
- **Ensemble search** — kết hợp nhiều chiến lược tìm kiếm để tăng độ bền vững.

**Hiển thị Top-100 keyframe.** Sau khi gửi truy vấn, hệ thống trả về tối đa 100 keyframe khớp nhất với mô tả văn bản. Mỗi keyframe hiển thị kèm dấu thời gian, giúp người dùng nhanh chóng đánh giá và so sánh các ứng viên.

**Tìm kiếm thời gian với truy vấn kép.** Người dùng cung cấp **hai mô tả văn bản riêng biệt**: một mô tả điểm **bắt đầu**, một mô tả điểm **kết thúc**. Dựa trên hai mini-query này, hệ thống gợi ý khung bắt đầu và khung kết thúc trong video liên quan. Giao diện đánh dấu:

- 🟩 **Khung bắt đầu đề xuất — viền xanh lá**
- 🟥 **Khung kết thúc đề xuất — viền đỏ**

Người dùng có thể xem lại và điều chỉnh nếu cần để tinh chỉnh biên khoảnh khắc.

**Hoàn tất khoảnh khắc.** Khi hài lòng, người dùng xác nhận lựa chọn. Hệ thống trích xuất và ghi log đoạn video đã xác định, phục vụ cho việc kiểm tra chi tiết hơn hoặc cho tác vụ QA.

#### 3.6.2. Hỏi–Đáp video (Video QA)

Sau khi tìm kiếm theo thời gian xác định đoạn liên quan, người dùng thực hiện QA bằng cách **quan sát trực tiếp** các khung hình đã trích xuất. Khác với hệ thống QA tự động, cách tiếp cận này dựa vào người dùng để xem xét đoạn hiển thị và tự rút ra câu trả lời phù hợp nhất.

**Lợi ích của QA dựa trên quan sát:**

- Độ chính xác cao hơn nhờ quan sát trực tiếp thay vì suy đoán.
- Độ tin cậy cao hơn nhờ thu thập dữ liệu theo thời gian thực.
- Linh hoạt hơn khi thích ứng với môi trường thay đổi.
- Phát hiện được các bất thường tinh vi mà mô hình VideoQA có thể bỏ sót → ra quyết định hiệu quả hơn và bảo đảm chất lượng tổng thể tốt hơn.

---

## 4. Kết quả thực nghiệm

### 4.1. Tìm kiếm mục tiêu đã biết (Known-Item Search)

#### 4.1.1. Reranking và Ensemble Search

Hệ thống được đánh giá trên tác vụ Known-Item Search — truy xuất khung hình cụ thể từ video dựa trên truy vấn do người dùng định nghĩa. Bốn chiến lược được khảo sát:

1. **Single-Model (BEiT-3):** chỉ dùng bộ trích xuất đặc trưng BEiT-3 để so khớp khung hình với truy vấn.
2. **Neighbors-Based Reranking:** tinh chỉnh danh sách ứng viên ban đầu bằng cách khai thác các lân cận cục bộ ổn định, đẩy lên các khung hình nhất quán về ngữ cảnh.
3. **Ensemble (BEiT-3 + OpenCLIP):** kết hợp hai bộ trích xuất để tích hợp nhiều "góc nhìn" của truy vấn, tăng độ bền vững.
4. **Kết hợp Ensemble + Reranking:** tích hợp cả hai để tối đa hóa độ bền vững, xử lý được sự biến thiên giữa các góc nhìn khác nhau.

> **Truy vấn ví dụ:** *"Hai cảnh trong một khu rừng. Ở cảnh đầu tiên, vài người đang đi bộ khi ánh nắng chiếu xuống mặt đất, và chỉ nhìn thấy phần thân dưới của họ. Bên phải khung hình có một cái cây phủ đầy rêu xanh. Ở cảnh thứ hai, ta biết rằng đó là những đứa trẻ đang đi trong rừng."*

**Kết quả theo từng chiến lược:**

| Chiến lược | Quan sát |
|---|---|
| **Single-Model (BEiT-3)** | Hệ thống tìm được một khung hình đúng nhưng **xếp hạng khá thấp**, cho thấy mô hình đơn lẻ gặp khó với chi tiết cảnh tinh vi (thân người chỉ hiện một phần, cây phủ rêu). |
| **Neighbors-Based Reranking** | Bằng cách xét lân cận cục bộ trong không gian đặc trưng, hệ thống đẩy lên các khung hình chia sẻ tín hiệu thị giác ổn định. Số khung hình đúng ở top tăng rõ rệt → **tính nhất quán không gian/thời gian đóng vai trò then chốt** trong việc phân biệt khung hình thực sự liên quan với các "distractor" trông tương tự. |
| **Ensemble (BEiT-3 + OpenCLIP)** | BEiT-3 mạnh ở so khớp chi tiết, OpenCLIP mạnh ở căn chỉnh ngữ nghĩa. Hợp nhất hai biểu diễn thường đẩy khung hình đúng lên **top-1 hoặc top-5**. Đặc biệt hữu ích với truy vấn mô tả cả đối tượng cụ thể (cây phủ rêu) lẫn ngữ cảnh bao trùm (trẻ em đang đi bộ). |
| **Ensemble + Reranking** | Cho kết quả **bền vững nhất**. Xử lý tốt che khuất một phần, thay đổi ánh sáng và chuyển động phức tạp. Qua tất cả các thử nghiệm, khung hình mục tiêu (viền đỏ) liên tục xuất hiện ở thứ hạng cao nhất — vượt trội so với baseline đơn mô hình về cả độ chính xác lẫn độ ổn định. |

#### 4.1.2. Tìm kiếm theo thời gian

Dựa trên danh sách khung hình ứng viên đã được cải thiện từ giai đoạn truy xuất cấp ảnh, cơ chế **temporal search** nhằm định vị một **đoạn video liên tục** tiến triển từ mô tả "bắt đầu" đến mô tả "kết thúc", qua đó nắm bắt tiến trình tự nhiên của sự kiện.

Hai truy vấn văn bản riêng biệt được sử dụng:

- **Start Query:** *"Ở cảnh đầu tiên, vài người đang đi bộ, và bên phải khung hình có một cái cây phủ rêu xanh; máy quay chỉ ghi lại phần thân dưới của họ."*
- **End Query:** *"Ở cảnh thứ hai, ta biết rằng đó là những đứa trẻ đang đi trong rừng."*

Bằng cách đưa vào ràng buộc thời gian — trình tự thời gian và liên kết ngữ nghĩa giữa hai sự kiện — hệ thống tái dựng chính xác hơn toàn bộ mạch tường thuật của truy vấn. Cách tiếp cận này dựa trên nhận định rằng nhiều khái niệm video (nhân vật bước vào/rời khỏi khung hình, môi trường thay đổi) vốn mang tính tuần tự và **không thể biểu diễn đầy đủ bằng một ảnh tĩnh**.

Thực nghiệm cho thấy phương pháp truy vấn kép liên tục cho ra đoạn video tập trung chứa các khung hình liên quan giữa mô tả bắt đầu và kết thúc — kể cả với video có chuyển cảnh dần dần hoặc chuyển động máy quay tinh tế.

> Người dùng phản hồi rằng việc chỉ định hai truy vấn không chỉ giúp kết quả chính xác hơn mà còn khiến quá trình tìm kiếm **tự nhiên hơn**, vì nó phản ánh đúng cách con người mô tả sự kiện trong đời sống hằng ngày: *"Nó bắt đầu khi X xảy ra và kết thúc khi Y xảy ra."*

### 4.2. Hỏi–Đáp (Question Answering)

Trong tác vụ QA, người dùng trước tiên dùng phương pháp Known-Item Search để xác định khoảnh khắc quan tâm trong video dài. Sau khi định vị được đoạn đó, hệ thống hiển thị một chuỗi khung hình tuần tự trải từ điểm bắt đầu đến điểm kết thúc do người dùng xác định. Việc trực quan hóa từng khung hình này cho phép người dùng quan sát các tín hiệu ngữ cảnh và thị giác vốn sẽ bị mất trong truy xuất khung hình đơn lẻ.

> **Truy vấn ví dụ:** *"Chú rể, bên cạnh là gia đình, đang chờ đợi cô dâu với sự hào hứng và mong đợi. Cô dâu rạng rỡ bước xuống lối đi, được cha mẹ tự hào dẫn dắt, tay cầm bó hoa tươi. Cô dâu tiến về phía chú rể trong khi khách mời chứng kiến khoảnh khắc đặc biệt này tại một sảnh lễ được trang hoàng lộng lẫy. **Mẹ cô dâu mặc váy màu gì?**"*

Sau khi xem xét các khung hình liên quan, người dùng nhập câu trả lời cuối cùng (ví dụ: *"Đỏ"*) vào ô trả lời. Hệ thống ghi lại phản hồi cùng với các khung hình đã chọn. Cơ chế này vừa tăng tính minh bạch, vừa hỗ trợ phân tích về sau — cho phép người dùng hoặc người đánh giá kiểm chứng cách một câu trả lời được rút ra.

---

## 5. Kết luận

Bài báo đề xuất một khung thống nhất cho truy xuất video tương tác, giải quyết các thách thức của nội dung dạng dài. Bằng cách tích hợp **ensemble search**, **tối ưu lưu trữ**, **tìm kiếm theo thời gian** và **xếp hạng lại theo thời gian**, phương pháp khắc phục hạn chế của các hệ thống hiện có, nâng cao đồng thời độ chính xác và hiệu suất.

Thông qua sự kết hợp giữa mô hình truy xuất mức thô và mức tinh, phương pháp bảo đảm nhận diện nội dung chính xác trong khi giảm thiểu dư thừa. Khung đề xuất cho thấy tiềm năng của **cộng tác người–máy**, mang lại giải pháp có khả năng mở rộng cho tìm kiếm video dựa trên nội dung và phân tích đa phương tiện, với hiệu năng mạnh trên cả tác vụ known-item search và question answering.

---

## Bảng thuật ngữ

| Thuật ngữ tiếng Anh | Nghĩa tiếng Việt |
|---|---|
| Moment Retrieval | Truy xuất khoảnh khắc |
| SVMR (Single Video Moment Retrieval) | Truy xuất khoảnh khắc trong một video đơn |
| VCMR (Video Corpus Moment Retrieval) | Truy xuất khoảnh khắc trong kho video |
| Keyframe | Khung hình đại diện / khung hình khóa |
| Shot transition detection | Phát hiện chuyển cảnh |
| Coarse-grained / Fine-grained | Mức thô / mức chi tiết |
| Reranking | Xếp hạng lại |
| Ensemble search | Tìm kiếm tổ hợp |
| Known-Item Search | Tìm kiếm mục tiêu đã biết |
| Human-in-the-loop | Có con người trong vòng lặp |
| Proposal-based / Proposal-free | Dựa trên đề xuất / không dùng đề xuất |
| Embedding | Vector biểu diễn đặc trưng |
| Cosine similarity | Độ tương đồng cosine |

---

## Tài liệu tham khảo chính được nhắc đến

- **TransNetV2** — Souček & Lokoč, *TransNet V2: An Effective Deep Network Architecture for Fast Shot Transition Detection*, ACM MM 2024.
- **CLIP** — Radford et al., *Learning Transferable Visual Models From Natural Language Supervision*, ICML 2021.
- **BEiT-3** — Wang et al., *Image as a Foreign Language: BEiT Pretraining for Vision and Vision-Language Tasks*, CVPR 2023.
- **HERO** — Li et al., *Hierarchical Encoder for Video+Language Omni-representation Pre-training*, arXiv 2020.
- **CONQUER** — Hou, Ngo & Chan, *Contextual Query-aware Ranking for Video Corpus Moment Retrieval*, ACM MM 2021.
- **MomentDiff** — Li et al., *Generative Video Moment Retrieval from Random to Real*, NeurIPS 2023.
- **W2VV++** — Li et al., *W2VV++: Fully Deep Learning for Ad-hoc Video Search*, ACM MM 2019.

*(Bài báo gốc có 62 tài liệu tham khảo — danh sách đầy đủ xem trong file PDF gốc.)*
