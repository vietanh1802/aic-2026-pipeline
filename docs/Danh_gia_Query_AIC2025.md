# Đánh giá các câu Query - AI Challenge HCMC 2025

Tài liệu này tổng hợp nhận xét cho toàn bộ 89 câu query trong 3 vòng thi (Round 1, 2, 3) của cuộc thi AI Challenge HCMC 2025 vòng sơ tuyển.

## Thống kê loại query

| **Loại query** | **Số lượng** | **Tỉ lệ** |
|----------------|--------------|-----------|
| KIS            | 73           | 82.0%     |
| TRAKE          | 7            | 7.9%      |
| QA             | 9            | 10.1%     |

## Bảng phân loại chi tiết từng câu query (xanh lá nghĩa là có đáp án theo ý kiến của t, nhưng chưa chắc đúng frame, lấy làm tập kiểm thử; đỏ là chưa có đáp án, được lấy làm tập test trên toàn bộ dataset)

Lưu ý:

1.  Đối với các câu KIS, đáp án có hai phần: một là mã video (L21_V015), hai là số frame trong video đó (tùy mỗi video, có video 25 fps, có video 30 fps)

2.  Đối với các câu QA, đáp án có ba phần: hai phần đầu giống KIS, phần còn lại là đáp án của câu hỏi trong query

3.  Đối với các câu TRAKE, đáp án có các phần như sau: phần đầu là mã video giống với hai câu hỏi KIS và QA. Phần còn lại là số frame chính xác, có bao nhiêu hành động thì có bấy nhiêu frame cần điền vào đáp án.

Link đánh giá cơ bản tất cả các câu query: [<u>All Queries</u>](https://docs.google.com/document/d/1cmxXOx7ObI9DMZ1ydbWlkoAi0KpTLZ0xBw81yQtOtDY/edit?usp=sharing)

<table>
<colgroup>
<col style="width: 5%"/>
<col style="width: 4%"/>
<col style="width: 43%"/>
<col style="width: 7%"/>
<col style="width: 29%"/>
<col style="width: 9%"/>
</colgroup>
<thead>
<tr class>
<th><strong>Mã câu</strong></th>
<th><strong>Loại</strong></th>
<th><strong>Nội dung câu query</strong></th>
<th><strong>Độ khó</strong></th>
<th><strong>Frame trả lời năm ngoái</strong></th>
<th><strong>Đánh giá cơ bản</strong></th>
</tr>
</thead>
<tbody>
<tr class>
<td><strong>R1-1</strong></td>
<td>KIS</td>
<td>Đây là phần giới thiệu việc phóng tàu vũ trụ tư nhân. Đoạn clip bắt đầu với hình ảnh 4 phi hành gia mặc áo đen. Một trong những nhiệm vụ dự kiến của tàu vũ trụ là nghiên cứu ánh sáng cực quang ở vùng cực</td>
<td>Trung bình</td>
<td>L21_V015,25605</td>
<td><a href="https://docs.google.com/document/d/1x2LcG50wZDjPOF3EJbtf2adye64CHTli5LVncPk0hyQ/edit?usp=sharing"><u>R1-1-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-2</strong></td>
<td>KIS</td>
<td>Mẩu tin giới thiệu về đàn hổ tại một địa phương ở miền Nam vừa có thêm khoảng 3-6 con hổ con. Đây là một giống hổ quý hiếm</td>
<td>Dễ</td>
<td>L21_V029,11555</td>
<td><a href="https://docs.google.com/document/d/1B2FvVzWule6WRDe_O4JU6tdbI4zP5WbY6rl7yvfM090/edit?usp=sharing"><u>R1-2-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-4</strong></td>
<td>TRAKE</td>
<td><p>E1: Khoảnh khắc đầu tiên bột được bỏ vào tô măng tây.</p>
<p>E2: Khoảnh khắc đầu tiên thấy miến măng tây đầu tiên tiếp xúc với dầu trong chảo.</p>
<p>E3: Khoảnh khắc miếng măng tây đầu tiên rời khỏi chảo dầu.</p>
<p>E4: Khoảng khắc miếng măng tây cuối cùng rời chảo dầu và nằm hoàn toàn trên dĩa.</p></td>
<td>Trung bình</td>
<td>L26_V194,4707,5100,5425,5850</td>
<td><a href="https://docs.google.com/document/d/1f7cGN8wsFkmi_etLnOIIs5gFqK-NJ9Tj87vD8YxVEjs/edit?usp=sharing"><u>R1-4-TRAKE</u></a></td>
</tr>
<tr class>
<td><strong>R1-5</strong></td>
<td>KIS</td>
<td>Đoạn clip cần tìm là cảnh hai người phụ nữ đang cho dê ăn: một người mặc áo thun trắng quàng áo đỏ trên vai, người kia mặc áo dài tay kẻ sọc tím truyền thống. Cả hai đều mỉm cười, tỏ vẻ thích thú. Không gian trại rộng rãi, có mái che bằng tôn và hàng rào gỗ chia thành nhiều dãy chuồng, trong đó có hàng dài dê được nuôi nhốt.</td>
<td>Trung bình</td>
<td>L27_V014,7297</td>
<td><a href="https://docs.google.com/document/d/1u8ytDzyomN_v9FUoaWhVvGEYyBbcnOvEpfibbn02IYI/edit?usp=sharing"><u>R1-5-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-6</strong></td>
<td>KIS</td>
<td>Đoạn clip cần tìm bắt đầu bằng cảnh 1 người đầu bếp đặt đang đặt món gỏi cuốn chay bày trên đĩa, nhân gồm rau xanh cuộn tròn và đậu hũ, gói trong bánh tráng màu vàng và tím. Đĩa được trang trí thêm lá xanh và hoa pansy tím-vàng, tạo cảm giác thanh mát và tinh tế.</td>
<td>Khó</td>
<td><p>L26_V385,6734</p>
<p>L26_V056 là video đúng</p>
<p><strong>Đã kiểm tra lại 2026: L26_V056,6375</strong></p></td>
<td><a href="https://docs.google.com/document/d/1NRXYgInYPkSxSb5hd7GZ2sZZkp9r721ZE9V6vYqlynk/edit?usp=sharing"><u>R1-6-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-7</strong></td>
<td>KIS</td>
<td>Đoạn clip cần tìm là cảnh quay trong một khu rừng, dưới gốc cây to với nhiều lá khô phủ đầy mặt đất. Nổi bật ở cận cảnh là một chú chim có bộ lông đen ánh xanh ở đầu và thân trên, còn cánh và lưng màu nâu đỏ. Đôi mắt chim đỏ rực, tạo điểm nhấn rõ ràng. Đây là loài chim thường thấy ở vùng Nam Bộ Việt Nam.</td>
<td>Trung bình</td>
<td>L29_V023,10915</td>
<td><a href="https://docs.google.com/document/d/1Ca6QPn8MlCE3CYphWAw3M0MDXRofSFzvm6Vc_DTAYos/edit?usp=sharing"><u>R1-7-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-8</strong></td>
<td>KIS</td>
<td>Đoạn video về một lễ hội ẩm thực Nhật Bản lớn nhất thế giới. Hãy tìm chính xác phân cảnh một cô bé đeo một con bạch tuộc / con mực màu đỏ phía trước ngực. Trên tay cô bé có cầm một chiếc túi giấy.</td>
<td>Khó</td>
<td>L22_V030,18327</td>
<td><a href="https://docs.google.com/document/d/1oTgdUCyTMu65qPTvga_-qcLlQt1RMTsRWx65ZklsYg8/edit?usp=sharing"><u>R1-8-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-9</strong></td>
<td>KIS</td>
<td>Đoạn clip là cảnh thu hoạch dứa ở miền Tây: một bà cụ ngồi bên giỏ dứa trò chuyện với cô gái mặc áo hồng quàng khăn rằn; xung quanh chất đầy dứa, phía sau có người phụ nữ đội nón lá cầm trái dứa và một chiếc ghe xanh đậu cạnh bờ, tạo không khí nông thôn mộc mạc, yên bình.</td>
<td>Trung bình</td>
<td>L27_V013,540</td>
<td><a href="https://docs.google.com/document/d/1ETU_oxjyHXJFAv2fLLRhw0z3sHjmtcmboFmGOtM-Tmg/edit?usp=sharing"><u>R1-9-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-10</strong></td>
<td>KIS</td>
<td>Tìm chính xác đoạn clip ngắn có ba người (hai phụ nữ và một nam giới) đang ngồi cạnh nhau, tập trung chơi nhạc cụ kim loại có dạng tròn, rỗng, với các vết lõm để tạo ra âm thanh khi gõ tay. Có 1 người mặc áo trắng ngồi giữa 2 người mặc áo đen. Bối cảnh phía sau là một kệ sách nhiều ngăn, xếp đầy sách với nhiều màu sắc</td>
<td>Trung bình</td>
<td>L30_V017,1947</td>
<td><a href="https://docs.google.com/document/d/1lsqZw4ZJdo9572TaXSUoP9JkvzaO1SUyo5dwkharnvs/edit?usp=sharing"><u>R1-10-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-11</strong></td>
<td>KIS</td>
<td><p>Trong đoạn clip có là một chàng trai đội mũ lưỡi trai đen, mặc áo thun trắng có dòng chữ tiếng Anh, đang ngồi cạnh một chiếc hộp. Trên hộp, anh sắp xếp nhiều mảnh bìa cắt rời với hình thù ngẫu nhiên.</p>
<p>Nhờ ánh sáng chiếu từ một phía, các mảnh bìa đó đổ bóng lên tường, tạo thành hình chân dung một người đàn ông với khuôn mặt rõ nét, tóc vuốt gọn và mặc vest.</p></td>
<td>Khó</td>
<td>L30_V057,3075</td>
<td><a href="https://docs.google.com/document/d/1Qd2LWKpz1hoEFlOR7B3eoUnJSwFflewjngU1nw06HJU/edit?usp=sharing"><u>R1-11-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-12</strong></td>
<td>KIS</td>
<td>Đoạn video mô tả cảnh trang trí bánh rán. Phân cảnh bắt đầu là một chiếc đĩa sứ màu trắng nằm trên một khay gỗ hình chữ nhật. Bên cạnh chiếc đĩa sứ là một chén đựng một vài trái dâu, nhưng có 2 trái bị rơi ra ngoài. Ngoài ra, bên cạnh đĩa sứ còn có một chén sứ nhỏ màu trắng đựng chuối đã được cắt sẵn và một cái thìa nhỏ màu nâu. Phân cảnh tiếp theo cho thấy đầu bếp đặt 2 chiếc bánh rán lên đĩa sứ và bắt đầu trang trí. Bước đầu tiên là việc rưới chocolate lên trên mặt bánh. Sau đó, đầu bếp đặt các lát chuối lên trên một chiếc bánh rán, chiếc còn lại được đặt các lát dâu tây lên.</td>
<td>Dễ</td>
<td>L26_V200,4480</td>
<td><a href="https://docs.google.com/document/d/1T8WefEhjujJuK9Ws__KFeaGxd502OWiOpHecfjnEP5s/edit?usp=sharing"><u>R1-12-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-13</strong></td>
<td>KIS</td>
<td>Đoạn video mô tả một người ngồi vệ sinh máy ảnh. Công đoạn này bắt đầu bằng việc tháo rời máy ảnh. Tiếp theo, chiếc ống kính đã được tháo rời và được đặt ngay ngắn trên một chiếc khăn màu tím hồng. Phân cảnh cuối cùng là vệ sinh ống kính (lens) bằng một chiếc tăm bông.</td>
<td>Trung bình</td>
<td>L30_V095,2672</td>
<td><a href="https://docs.google.com/document/d/1xW0WQeY8aYkvYMosNq_YvESQQXFmIHzkZgTRei9rgKc/edit?usp=sharing"><u>R1-13-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-14</strong></td>
<td>KIS</td>
<td><p>Đoạn clip bắt đầu với cảnh một tác phẩm điêu khắc cát hoành tráng tại Lễ hội điêu khắc trên cát. Tác phẩm mô tả cảnh những thanh niên chơi thể thao đường phố: một người trượt patin, hai người trượt ván</p>
<p>Nền phía sau là họa tiết vòm cong lớn và có khắc chữ.</p>
<p>Tiếp theo có cảnh nhiều tác phẩm khác bằng cát, và có 2 cột khói màu hồng</p></td>
<td>Trung bình</td>
<td>L21_V027,26880</td>
<td><a href="https://docs.google.com/document/d/1EHTbnXe4wKO31IprGON3Z_j34Ff7UkzClfVH90WaEX0/edit?usp=sharing"><u>R1-14-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-15</strong></td>
<td>QA</td>
<td>Đoạn video về một chương trình từ thiện của một câu lạc bộ tên là FANA. Trong đoạn video có thể thấy câu lạc bộ này đang đi trao quà tại một xã thuộc tỉnh Khánh Hòa. Hỏi xã này có tên là gì? (tại thời điểm đó)</td>
<td>Dễ</td>
<td>L30_V072,1745,Xã Giang Ly</td>
<td><a href="https://docs.google.com/document/d/1O5Veef0DbqcRtNre_iYPj7T25lYpy0GNWini9MDMTdo/edit?usp=sharing"><u>R1-15-QA</u></a></td>
</tr>
<tr class>
<td><strong>R1-16</strong></td>
<td>TRAKE</td>
<td><p>Đoạn video múa lân một con lân màu vàng đen trắng, tìm các sự kiện sau:</p>
<p>E1: Lân quay vòng trên cột số 4 bằng 2 chân trước rồi tiếp đất. Khoảnh khắc đầu tiên mà lân bắt đầu xoay vòng.</p>
<p>E2: Khoảnh khắc 4 chân hoàn toàn chạm đất đầu tiên.</p>
<p>E3: Khoảnh khắc đầu tiên 2 người biểu diễn lân cuối chào ban giám khảo.</p>
<p>E4: Sau đó lân tiến lại chào một con rồng. Khoảnh khắc đầu tiên con rồng cử động đầu.</p></td>
<td>Khó</td>
<td>L24_V033,15930,15990,16350,16890</td>
<td><a href="https://docs.google.com/document/d/1k6QTj-xd38lZ5mdIiejjR78FsoBbBae_ym0tBiW0Ioc/edit?usp=sharing"><u>R1-16-TRAKE</u></a></td>
</tr>
<tr class>
<td><strong>R1-17</strong></td>
<td>KIS</td>
<td>Đoạn video trong buổi trao quà từ thiện diễn ra tại 1 bệnh viện trong dịp Xuân 2024. Trong cảnh có hai người đàn ông (mặc áo sơ mi hồng và sơ mi trắng) đứng hai bên, đại diện ban tổ chức. Ở giữa là bốn em nhỏ và thiếu niên, trong đó có em mặc áo đỏ, em mặc áo trắng, em mặc váy hồng và em mặc áo xanh. Các em được trao bảng tượng trưng với nội dung "Chương trình: Trao kinh phí hỗ trợ cho trẻ em mồ côi do dịch COVID-19". Trước mặt mỗi em là túi quà lớn mang logo y tế. Phía sau là phông nền màu đỏ với khẩu hiệu đón xuân và thông tin sự kiện.</td>
<td>Trung bình</td>
<td>L30_V092,2485</td>
<td><a href="https://docs.google.com/document/d/1bQfNOVroV8dZZ_XfIdOGF7h0zDJEAjVujkqOqgPyT9Y/edit?usp=sharing"><u>R1-17-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-18</strong></td>
<td>TRAKE</td>
<td><p>E1: Khoảnh khắc đầu tiên thấy cắt nấm.</p>
<p>E2: Khoảnh khắc đầu tiên cắt củ năng.</p>
<p>E3: Khoảnh khắc đầu tiên cắt đậu hủ.</p>
<p>E4: Khoảnh khắc chảo đặt lên bếp, đầu bếp mở lửa và thấy lửa bắt đầu xuất hiện</p></td>
<td>Trung bình</td>
<td>L26_V072,2450,3125,3400,3800</td>
<td><a href="https://docs.google.com/document/d/1eRQlx0oPvInEKf6uLWF1HN1JjRugynbYXQtGmlThg7w/edit?usp=sharing"><u>R1-18-TRAKE</u></a></td>
</tr>
<tr class>
<td><strong>R1-19</strong></td>
<td>QA</td>
<td>Trong đoạn video có 2 câu thơ của một nhà thơ ca ngợi anh hùng Nguyễn Trung Trực trong đình thần Nguyễn Trung Trực tại Kiên Giang. Hai câu thơ đó là gì?</td>
<td>Dễ</td>
<td>L27_V010,5550,"Hoả hồng Nhật Tảo oanh thiên địa, Kiếm bạch Kiên Giang khấp quỷ thần."</td>
<td><a href="https://docs.google.com/document/d/1ilkA_QGAaafyK8IIRKGTv4NLLNgODXvJ9d1wZXf3Dns/edit?usp=sharing"><u>R1-19-QA</u></a></td>
</tr>
<tr class>
<td><strong>R1-20</strong></td>
<td>KIS</td>
<td><p>Trên đĩa tròn màu trắng có 1 ly panna cotta. Có một bàn tay lần lượt đặt thêm 2 ly panna cotta nữa vào đĩa.</p>
<p>Mỗi ly panna cotta có lớp kem mịn màu trắng ngà, bên trên trang trí vài lát nho đỏ, thêm lá bạc hà xanh tạo điểm nhấn tươi mát.</p>
<p>Bên cạnh trên đĩa còn có hai bông hoa ăn được (màu đỏ và vàng) để tăng phần đẹp mắt.</p></td>
<td>Dễ</td>
<td>L26_V004,5400</td>
<td><a href="https://docs.google.com/document/d/1MfExSaGFJd2-a96v6qChqHY8-2nPw06BpjnPvl0AC0M/edit?usp=sharing"><u>R1-20-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-21</strong></td>
<td>KIS</td>
<td>Đoạn video vể nghiên cứu tại 1 Đại học ở thành phố Lausanne về việc nghiên cứu cơ chế bay của bọ để chế tạo robot</td>
<td>Bỏ qua</td>
<td>None</td>
<td><a href="https://docs.google.com/document/d/1pGwotV0BBlyxvM1gdFf2-B711Fmu706sCFBhBndtkgk/edit?usp=sharing"><u>R1-21-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-22</strong></td>
<td>QA</td>
<td>Đoạn video về một người phụ nữ dạy nấu ăn cho những người khác. Trong đoạn video có thể thấy một người đang cầm công thức món ăn với nguyên liệu chính là 200g thịt nạc xay. Hỏi tiêu đề của công thức nấu ăn (tên món ăn) này là gì?</td>
<td>Dễ</td>
<td>L26_V178,4086,Bánh ít trần</td>
<td><a href="https://docs.google.com/document/d/1RXhX-NEhqYE5whLnOol8Mt8uh2VAPocweamlv5ny2TQ/edit?usp=sharing"><u>R1-22-QA</u></a></td>
</tr>
<tr class>
<td><strong>R1-23</strong></td>
<td>KIS</td>
<td>Đoạn clip về 1 thị trấn ven biển thu hút du khách hiếu kỳ nhờ 1 loài động vật biển nguy hiểm. Loài động vật này nổi tiếng trong 1 bộ phim của đạo diễn Steven Spielberg được sản xuất vào năm 1975</td>
<td>Khó</td>
<td>L22_V022,16770</td>
<td><a href="https://docs.google.com/document/d/1lmEh0KwaquZL4TlEjX95K_PzvGtjnydiIbFAYnNNkHs/edit?usp=sharing"><u>R1-23-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-24</strong></td>
<td>KIS</td>
<td>Đoạn video về tường thuật một cuộc đua xe đạp. Tìm phân cảnh với góc quay trực diện từ trên cao xuống dõi theo các tay đua. Trong khung hình gồm có 3 tay đua đang đạp thành một đường thẳng. Cả 3 tay đua đều đến từ cùng một đội, với đồng phục áo trắng quần vàng xanh. Tay đua đầu tiên đội nón trắng, tay đua thứ hai đội nón đỏ và tay đua cuối cùng đội nón đen.</td>
<td>Rất khó</td>
<td>L23_V007,3246</td>
<td><a href="https://docs.google.com/document/d/1bRv1FK-yWnvUY8XS5eFKeSzizQ0xChUEBOvx5IAzM5k/edit?usp=sharing"><u>R1-24-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R1-25</strong></td>
<td>KIS</td>
<td>Tìm một đoạn video đua xe đạp, góc quay từ flycam trên cao, một vận động viên mặc áo xanh dương, trắng đang vượt ba vận động viên khác và lên vị trí dẫn đầu. Biết sau đó vận động viên này dẫn đầu suốt đoạn đường còn lại đến đích.</td>
<td>Rất khó</td>
<td>L23_V017,1108</td>
<td><a href="https://docs.google.com/document/d/1PoFCHetqngwHGls6tAzpnaPeGrxYPJS8wHMxRF_Lbvc/edit?usp=sharing"><u>R1-25-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-1</strong></td>
<td>KIS</td>
<td>Nhiều người mặt áo cờ đỏ sao vàng đứng trước biểu tượng một con cua khổng lồ. Những người này đều đội nón, một số người quấn khăn rằn trên cổ.</td>
<td>Dễ</td>
<td>K03_V019,11708</td>
<td><a href="https://docs.google.com/document/d/1ePRLkM4t8qOvwA6hDNyrR1rkX_Nrv_flFQB7EvOGpeI/edit?usp=sharing"><u>R2-1-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-2</strong></td>
<td>KIS</td>
<td>Đoạn clip ghi lại một lễ hội đèn lồng. Trên phố, nhiều người mặc hanbok diễu hành, mang theo đủ loại đèn lồng rực rỡ. Nổi bật ở giữa là một phụ nữ cầm hai đèn lồng tròn lớn màu cam, xung quanh có đèn lồng hình cá, tôm và nhiều kiểu dáng khác. Tiếp đó, xuất hiện một chiếc đèn lồng khổng lồ hình người trong trang phục truyền thống Hàn Quốc: áo tím viền vàng, váy xanh, hai tay nâng một đèn lồng nhỏ màu cam - xanh phát sáng rực rỡ.</td>
<td>Trung bình</td>
<td>K14_V027,13571</td>
<td><a href="https://docs.google.com/document/d/1NpI7lmYqDhthSN3yk-gfymK3ag75DpOrYmVVLe-RrPc/edit?usp=sharing"><u>R2-2-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-3</strong></td>
<td>QA</td>
<td><p>Đoạn clip về một gian trưng bày văn hóa - du lịch. Ở giữa là bản đồ Việt Nam được kết bằng trái cây màu vàng và nâu. Phía trước có hai người giới thiệu: một cô gái mặc trang phục dân tộc truyền thống màu nâu, thắt dải yếm xanh - hồng - tím; một người đàn ông mặc áo thun xanh đậm và quần sáng.</p>
<p>Phía trên là quốc kỳ Việt Nam treo chính giữa.</p>
<p>Hảy cho biết đây là khu du lịch quốc gia tại địa điểm nào của Việt Nam (thông tin có ngay dưới bản đồ, được ghi bằng chữ màu xanh lá cây)</p></td>
<td>Trung bình</td>
<td>K17_V003,11226,Mộc Châu</td>
<td><a href="https://docs.google.com/document/d/1fRMpywYE8iMgh9FOWxWVCL0yy3Okuj29t3g79xNP8nU/edit?usp=sharing"><u>R2-3-QA</u></a></td>
</tr>
<tr class>
<td><strong>R2-4</strong></td>
<td>KIS</td>
<td><p>Đoạn clip trích trong cảnh cứu hộ người dân trong lũ lụt. Có cảnh ở giữa là một cụ bà đội nón lá, ngồi trên một chiếc xuồng cứu hộ màu cam, trên xuồng có áo mưa màu xanh da trời.</p>
<p>Bên phải là một thanh niên mặc áo mưa tím, đang ra sức đẩy xuồng, gương mặt lộ rõ sự căng thẳng, quyết tâm.</p>
<p>Phía sau có người mặc áo phao màu cam hỗ trợ.</p>
<p>Xung quanh là dòng nước ngập, cho thấy khu vực đang chịu ảnh hưởng nặng nề bởi mưa lũ.</p></td>
<td>Trung bình</td>
<td>K01_V009,11642</td>
<td><a href="https://docs.google.com/document/d/1pooYfc1J_71tFvpQAcrDGG2A6zbMxlHYPX5LzHdJHBk/edit?usp=sharing"><u>R2-4-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-5</strong></td>
<td>KIS</td>
<td>Đoạn clip có cảnh quay không gian triển lãm nghệ thuật hiện đại. Ở giữa là một hệ thống robot vẽ tranh: hai cánh tay robot được lắp đặt đối xứng, gắn trên khung kim loại, cùng thực hiện thao tác vẽ trên một khung vẽ hình vuông ở giữa. Bức tranh xuất hiện nhiều mảng màu đen - xám - trắng, tạo nên bố cục trừu tượng. Xung quanh là phòng trưng bày với nhiều tác phẩm nghệ thuật khác treo trên tường, gồm tranh, ảnh và màn hình kỹ thuật số trình chiếu hình ảnh. Cuối đoạn clip có 1 quyển sách bìa màu xanh đậm có chữ MILK</td>
<td>Trung bình</td>
<td>K02_V005,23018</td>
<td><a href="https://docs.google.com/document/d/13SZ47-Ja8oER1jnMRvfcQ5W9Neigf_7WMFMzrPypLL8/edit?usp=sharing"><u>R2-5-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-6</strong></td>
<td>KIS</td>
<td>Đoạn clip mở đầu với cảnh đài phun nước được bao quanh bởi hàng trăm ngọn nến xếp ngay ngắn, tạo nên khung cảnh lung linh giữa đám đông và tòa nhà cổ sáng đèn phía sau. Tiếp đó, một người phụ nữ ngồi bên thành một công trình tròn, hai tay nâng ngọn nến trong ly thủy tinh, xung quanh đặt nhiều ly nến khác tỏa sáng huyền ảo.</td>
<td>Khó</td>
<td>K09_V018,20313</td>
<td><a href="https://docs.google.com/document/d/1gN2GMIGZxo81HDFeMsUA2BJYHimBoo3X50uG32hCF1E/edit?usp=sharing"><u>R2-6-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-7</strong></td>
<td>KIS</td>
<td>Đoạn clip mở đầu với hình ảnh tác phẩm điêu khắc người tuyết khổng lồ màu trắng, đội mũ, quàng khăn đỏ và gương mặt tươi cười sinh động. Kết thúc clip là cảnh tái hiện chiếc bình gốm sứ khổng lồ với hoa văn xanh trắng cùng chi tiết cây tùng, thể hiện sự kết hợp hài hòa giữa nghệ thuật băng tuyết và văn hóa truyền thống</td>
<td>Dễ</td>
<td>K05_V025,26181</td>
<td><a href="https://docs.google.com/document/d/1esUDdmLCZ4bedI0pV_UdLKqamx7vTSGv_NmGvackXU0/edit?usp=sharing"><u>R2-7-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-8</strong></td>
<td>KIS</td>
<td>Đoạn clip mở đầu với hình ảnh cây cầu có hệ thống vòm thép đỏ uốn cong đối xứng như những đợt sóng lượn. Khoảng 30 giây sau, clip kết thúc bằng cảnh một chiếc ca nô tạo vệt sóng tròn lớn trên mặt nước, để lại những vòng xoáy đồng tâm rõ nét.</td>
<td>Trung bình</td>
<td>K03_V023,7552</td>
<td><a href="https://docs.google.com/document/d/1FiGi6IVYhSysbnbXa2En7KauGyyN9gU3SjDZ93YCalo/edit?usp=sharing"><u>R2-8-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-9</strong></td>
<td>KIS</td>
<td>Đoạn video đưa tin về việc ngư dân vừa câu được một con cá nhám với kích thước hiếm gặp, nặng đến 211kg. Đoạn tin đưa hình ảnh của con cá rất lớn treo trên một chiếc xe cẩu.</td>
<td>Trung bình</td>
<td>K12_V001,8681</td>
<td><a href="https://docs.google.com/document/d/1pE0zuJb6qYJCiPjystx35tIP_grua55lYlUh_LDjeGo/edit?usp=sharing"><u>R2-9-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-10</strong></td>
<td>TRAKE</td>
<td><p>Cảnh láp ráp trong một xưởng.</p>
<p>E1: Một cánh tay rô bot đang lắp một cái khung cho một chiếc xe. Lấy khoảnh khắc cái khung chạm vào chiếc xe.</p>
<p>E2: Một công nhân đang lắp gì đó rồi quay một cái tay xoay. Lấy khoảnh khắc tay xoay bắt đầu quay thiết bị.</p>
<p>E3: Các công nhân đang lắp ráp cho cửa ô tô. Ở đây có một công nhân mặc áo đen. Lấy khoảnh khắc đầu tiên người công nhân này gấp cái khăn khi quay mặt lại hướng camera.</p></td>
<td>Khó</td>
<td>K07_V025,22200,22260,22350</td>
<td><a href="https://docs.google.com/document/d/1raBFkdlm1t8jfIk3ZfnXNpf32LDfVTCGUSNDj1f3BCM/edit?usp=sharing"><u>R2-10-TRAKE</u></a></td>
</tr>
<tr class>
<td><strong>R2-11</strong></td>
<td>KIS</td>
<td>Cảnh quay một người phụ nữ lớn tuổi đang đọc sách, tay đeo một xâu hạt. Sau đó là cảnh quay người phụ này đang mở một quyển sách có bìa là ảnh chân dung của một cụ lão in trắng đen có dòng chữ màu trắng ở trên. Bìa quyển sách có màu vàng đất làm chủ đạo</td>
<td>Trung bình</td>
<td>L30_V014,1280</td>
<td><a href="https://docs.google.com/document/d/1C1xN0mAsA7VGYmbxCysZ8OnOot3AzmGibnSHbcXPEoo/edit?usp=sharing"><u>R2-11-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-12</strong></td>
<td>KIS</td>
<td>Trong một lễ hội trình diễn, các người mẫu lần lượt bước trên sàn. Mở màn là những bộ cổ phục "Nhật Bình" với đủ màu sắc. Trong đó, có cảnh người phụ nữ cầm những bông sen đứng đối diện nam người mẫu và cả 2 mặc áo màu xanh lá. Sau đó là các trang phục hiện đại hơn. Kết thúc bằng cảnh các người mẫu đồng loạt ra đứng sân khấu chào khán giả.</td>
<td>Khó</td>
<td><p>K07_V019,9405</p>
<p>Chưa tìm được video đúng</p></td>
<td><a href="https://docs.google.com/document/d/1npZsynNY_8_uFjxRbn-nrrj2atPmffU8GoPZ9nG3Dm8/edit?usp=sharing"><u>R2-12-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-13</strong></td>
<td>KIS</td>
<td>Hình ảnh những chiếc bánh có 2 mức giá được viết mẫu giấy đen nhỏ lần lượt là 9.00€ và 4€.80. Sau đó là cảnh các chiến bánh này trong giai đoạn sản xuất, được xếp thành từng tầng, mỗi tầng gồm 12 cái bánh.</td>
<td>Trung bình</td>
<td>Vid đúng là K09_V015</td>
<td><a href="https://docs.google.com/document/d/1ZkenaPTAoegYW8PtOcTeZVO-ZQm8kjCSxsQDLRTASzI/edit?usp=sharing"><u>R2-13-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-14</strong></td>
<td>KIS</td>
<td>Đoạn video minh họa thống kê cho tác dụng phụ khi dùng thuốc điều trị bệnh. Để trực quan hóa số liệu cho việc số ca có triệu chứng, các icon hình não được xếp vào hình chữ nhật 5 x 10 và trừ dòng dưới cùng sẽ có thêm 2 icon dư ra. Sấp xỉ 5,8% số người có triệu chứng này đã tử vong.</td>
<td>Khó</td>
<td>K16_V010,15047</td>
<td><a href="https://docs.google.com/document/d/1BtS9FvOGbs128azkmhGQEbTHsDlztWZ5dbRWNrVIYjE/edit?usp=sharing"><u>R2-14-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-15</strong></td>
<td>KIS</td>
<td>Một người đang chụp hình những chiếc ván trượt. Sau đó cảnh quay một cô gái đang phỏng vấn và sau lưng cô là một người mặc trang phục Deadpool và kết thúc bằng cảnh cô gái này múa vài đường kiếm/đao.</td>
<td>Trung bình</td>
<td>K01_V018,12953</td>
<td><a href="https://docs.google.com/document/d/1NsCVqkjcBFQ_kQ8O8gkuTZUCN0Cx05NWe0t0k9KdJ9A/edit?usp=sharing"><u>R2-15-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-16</strong></td>
<td>KIS</td>
<td>Cảnh quay nhiều người đứng quanh một cột đá có các số 10, 12, 14, 16, 18, 20. Ở xung quanh khu vực này đang có các chú công an. Sau một lúc, ta thấy người quay phim đang đứng trên một chiếc cầu bắng ngang con sông nước chảy siết.</td>
<td>Khó</td>
<td>None</td>
<td><a href="https://docs.google.com/document/d/1OqdfOKckM8FMxdIHtrva7oOckHjW1jJcJE-fGqpUzjA/edit?usp=sharing"><u>R2-16-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-17</strong></td>
<td>KIS</td>
<td>Một người phụ nữ đang trả lời phỏng vấn, người phụ nữ này đội nón len, đeo kính. Trên kính có chữ Happy New Year.</td>
<td>Trung bình</td>
<td>K07_V030,22278</td>
<td><a href="https://docs.google.com/document/d/1Aiinly1j3oubvkIOrstjvJipi_mdfxfXhyZUGFDWNyU/edit?usp=sharing"><u>R2-17-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-18</strong></td>
<td>KIS</td>
<td>Cảnh quay các con mèo trong một căn phòng. Có một tô bằng kim loại úp ngược lại trên thùng màu đỏ. Kết thúc bằng cảnh một chú mèo có đeo bảng tên có chữ "Nà Ní"</td>
<td>Dễ</td>
<td>L30_V040,475</td>
<td><a href="https://docs.google.com/document/d/1egMqlDueORYL0fA50YAFXjIvMAJKbLupwcYYaEpAJSE/edit?usp=sharing"><u>R2-18-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-19</strong></td>
<td>KIS</td>
<td>Cảnh quay bắt đầu bằng rất nhiều người vui chơi ở một con suối. Có một nhóm người ngồi dưới một tấm bạt. Trên suối có các bạn nhỏ nô đùa, và kết thúc cảnh quay có một bạn nhỏ mặc áo đen và vàng đang ngồi giữa dòng suối.</td>
<td>Khó</td>
<td>None</td>
<td><a href="https://docs.google.com/document/d/1Enz_VnjcALeXcXNf9sPsH0x0HxU0q_0WuxWHaOIV4SA/edit?usp=sharing"><u>R2-19-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-20</strong></td>
<td>KIS</td>
<td>Đoạn video bắt đầu bằng cảnh một số người đang cào muối trên đồng. Cảnh tiếp theo là một đoàn người đang vẫy tay phía sau một bảng chữ. Cuối cùng là hình ảnh một đoàn người đang đứng trước một căn nhà có câu "Gừng cay muối mặn xin đừng quên nhau".</td>
<td>Trung bình</td>
<td>K06_V010,7935</td>
<td><a href="https://docs.google.com/document/d/1EsEKf5MLCxMm-p2sWSciBF6j9k9JRHJ0Fwot9iL1AVQ/edit?usp=sharing"><u>R2-20-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-21</strong></td>
<td>QA</td>
<td>Đây là câu 3 trong bài tập vận dụng. Các dữ kiện của đề bài bao gồm khoảng cách giữa AB là một số có 2 chữ số có chữ số hàng chục bằng chữ số hàng đơn vị. Chữ số này còn dùng để làm một điều kiện khác trong bài và được nêu ra ngay trong cùng câu mở đầu. Đáp án của bài là C. Hỏi chữ số này là số mấy?</td>
<td>Khó</td>
<td>L25_V058,26958,66</td>
<td><a href="https://docs.google.com/document/d/1haJNO9raq7PZ0CToD1pzZxa5KKyDC3r-v8YfipK1urE/edit?usp=sharing"><u>R2-21-QA</u></a></td>
</tr>
<tr class>
<td><strong>R2-22</strong></td>
<td>TRAKE</td>
<td><p>Một cảnh quay từ camera an ninh về một lần khám xét.</p>
<p>E1: Người cảnh sát vẫy tay đưa nghi phạm vào phòng.</p>
<p>E2: Sau khi vào phòng, cảnh sát ra hiệu chỉ tay vào vị trí cần đứng. Hãy lấy cảnh đầu tiên chỉ tay được thực hiện</p>
<p>E2: Khoảnh khắc đầu tiên cảnh sát hoàn toàn khom người xuống để quét kiểm tra</p></td>
<td>Rất khó</td>
<td>Vid đúng là K02_V005</td>
<td><a href="https://docs.google.com/document/d/101HcZu7f4kmgLyQqfrGV-nNOrNFBwoHH_6lfQEotewI/edit?usp=sharing"><u>R2-22-TRAKE</u></a></td>
</tr>
<tr class>
<td><strong>R2-23</strong></td>
<td>KIS</td>
<td>Cảnh quay chú gấu bông màu xanh đựng trong chiếc hộp hình trụ trong suốt. Trên chú gấu bông này có những cảm biến giúp chuyển động và phát ra âm thanh.</td>
<td>Khó</td>
<td><p>K04_V013,21300</p>
<p>Chưa tìm được video đúng</p></td>
<td><a href="https://docs.google.com/document/d/1UhU2fCz-tIWdT5fnuXWG_ohe60ILbBOmrvVJhlFwwuw/edit?usp=sharing"><u>R2-23-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-24</strong></td>
<td>KIS</td>
<td>Một nhóm ngư dân campuchia đang ngồi cầm tấm bạt để nâng một con cá rất to. Đây là loài cá trong tình trạng nguy cấp. Có 3 con khác nhau được đánh bắt. Kết thúc đoạn trước cảnh một nhà nghiên cứu sinh học được phỏng vấn.</td>
<td>Trung bình</td>
<td>K05_V013,23220</td>
<td><a href="https://docs.google.com/document/d/1oxJ6WaIr3pgX9jWvabD_Q5soMMXbFtw4yxGf0Y9enP8/edit?usp=sharing"><u>R2-24-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-25</strong></td>
<td>KIS</td>
<td>Một con robot có 4 chân gắn với 4 bánh xe chạy trên đồng cỏ. Cảnh sau có những con bò đứng kế bên con robot. Đoán clip kết thúc bằng cảnh phỏng vấn người trong nhóm làm ra con robot để mô tả các phương thức hoạt động và sự hữu ích của nó.</td>
<td>Trung bình</td>
<td>K05_V018,18690</td>
<td><a href="https://docs.google.com/document/d/1NbLGwdQMFBDhLJVmdSH907ncPnkOOXUwHxaXwJneZks/edit?usp=sharing"><u>R2-25-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-26</strong></td>
<td>KIS</td>
<td>Cảnh phỏng vấn tổng thống Donald Trump, đằng sau ông là các bức hình và những lá cờ. Sau đó là cảnh một đoàn người đang di chuyển trên đường dọc theo một bờ biển. Cuối cùng là cảnh một số người trong đoàn người này đang vác những bao tải màu trắng.</td>
<td>Khó</td>
<td>Vid đúng là K09_V012</td>
<td><a href="https://docs.google.com/document/d/1rEzH4mMcRu2ScUd2CEkw1cbwwIbejnB32R4uypsAPFg/edit?usp=sharing"><u>R2-26-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-27</strong></td>
<td>KIS</td>
<td>Đoạn video về một cuộc họp bàn về giá điện. Phân cảnh đầu tiên là hình ảnh một người đàn ông mặc áo trắng, đeo kính, đang đứng phát biểu. Trên tay người đàn ông có cầm một văn bản. Xung quanh là những người khác đang ngồi nghe. Một trong những phân cảnh sau đó là hình ảnh phòng họp rộng, khá đông người ngồi. Phía trên có một màn hình led đưa thông tin về cuộc họp với chữ trắng và nền màu xanh dương.</td>
<td>Khó</td>
<td>Vid đúng là K15_V010</td>
<td><a href="https://docs.google.com/document/d/1f_gOazPA-rUQraMbZ6djknx6ibdDUojOUG-wFnS_G_s/edit?usp=sharing"><u>R2-27-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-28</strong></td>
<td>KIS</td>
<td>Đoạn video chứa hình ảnh của nhiều loại cá cảnh khác nhau, trong đó có cá đĩa, cá rồng, và nhiều loại cá khác. Một vài phân cảnh có hình ảnh của cá la hán với đầu rất to.</td>
<td>Trung bình</td>
<td>K18_V002,4680</td>
<td><a href="https://docs.google.com/document/d/1GPsRtb052hvZcOvYPTuhLb7WUhokrXyEdrVSZrHydkA/edit?usp=sharing"><u>R2-28-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-29</strong></td>
<td>KIS</td>
<td>Đoạn video đưa tin về một cảng biển. Phân cảnh đầu tiên là hình ảnh biển mênh mông với một cây cầu rất dài nối ra giữa biển. Trong đoạn tin có một số phân cảnh phỏng vấn một người đàn ông đội nón tai bèo.</td>
<td>Khó</td>
<td>Vid đúng là K03_V022</td>
<td><a href="https://docs.google.com/document/d/1t8l2ZHVGIq8l5iK3sI3f2SMbe4pnW9TuCqICyOn4tr0/edit?usp=sharing"><u>R2-29-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R2-30</strong></td>
<td>KIS</td>
<td>Đoạn video đưa tin về một cuộc đua giữa các kị sĩ. Một trong các phân cảnh là hình ảnh đồng cỏ xanh rộng, các kị sĩ cưỡi ngựa chạy trên cánh đồng này. Rất đông người đứng xem xung quanh khu vực đua. Trên đường đua có cắm những lá cờ màu đỏ.</td>
<td>Trung bình</td>
<td>K09_V007,5790</td>
<td><a href="https://docs.google.com/document/d/1aGuznZtauLqGzB4Q-s33-xpilSCsYZktHXXqxYPRNuQ/edit?usp=sharing"><u>R2-30-KIS</u></a></td>
</tr>
<tr class>
<td><strong>R3-1</strong></td>
<td>TRAKE</td>
<td><p>Đây là một cảnh nấu món cá.</p>
<p>E1: Người đầu bếp khuấy một hỗn hợp nước sốt. Lấy khoảnh khắc người đầu bếp lấy muỗng chạm vào nước sốt lần đầu tiên.</p>
<p>E2: Người đầu bếp rưới nước sốt vào nồi. Trong nồi có một khoanh cá và phía trên là 1 quả ớt. Miếng cá này được đặt lên trên các miếng thịt. Lấy khoảnh khắc nước sốt được cho hoàn toàn hết vào nồi.</p></td>
<td>Trung bình</td>
<td>L26_V176, 4603, 4672</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-2</strong></td>
<td>KIS</td>
<td>Cảnh quay cận cảnh một miếng thiếc có nhiều lỗ thủng. Được biết lỗ thủng này do người đàn ông dùng đinh đóng vào. Mặt lõm của miếng thiếc này màu trắng. Kết thúc cảnh quay ta thấy được công dụng của miếng thiếc này.</td>
<td>Trung bình</td>
<td>L29_V020, 16988</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-3</strong></td>
<td>KIS</td>
<td>Đoạn video nói về ngành hàng không ở Việt Nam. Để mô tả về ngành này, ta thấy được một bản đồ Việt Nam, với các biểu tượng máy bay biểu thị cho sân bay quốc tế hoặc quốc nội cũng như đường bay từ các địa điểm này. Các thông tin này được tóm tắt trong 4 ý chính.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-4</strong></td>
<td>KIS</td>
<td>Cảnh quay các con động vật nối đuôi nhau. Con đi đầu lớn nhất, các con phía sau có kích thước lần lượt là nhỏ lớn nhỏ lớn. Tuy nhiên, ở vị trí thứ 2 có 2 con đi song song. Sau đó là cảnh con chim ở trên cây.</td>
<td>Trung bình</td>
<td>K10_V002,19170</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-5</strong></td>
<td>KIS</td>
<td>Cảnh những chiếc xe máy được chụp từ phía sau. Có 2 người đang đội mũ bảo hiểm 3/4 hoặc fullface ở bên trái khung hình. Sau đó là cảnh quay một cánh cổng mà các cột đèn phía trước (hướng về phía camera) ở bên phải đang bật và bên trái thì đang tắt.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-6</strong></td>
<td>KIS</td>
<td>Cảnh quay các dãy xe nối đuôi nhau với xe đầu tiên màu trắng. Sau đó là cảnh quay gần hơn đến chiếc xe đầu tiên. Ta thấy đèn xe mỗi bên là hình chữ U ngược đang nhấp nháy. Xe này không có biển số và ta thấy họa tiếc khắc chìm nổi ở giữa đầu xe.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-7</strong></td>
<td>KIS</td>
<td>Cảnh quay từ phía sau một cậu bé và một cô gái đứng cạnh nhau. cậu bé này đang mặc một chiếc quần màu xanh. Đây là một đám cháy đang được các lính cứu hỏa ra sức dập lửa. Sau đó ta thấy những người xung quanh đưa camera ra quay phim lại và hình như đang livestream. Đây là một cửa hàng ở TP Đồng Xoài.</td>
<td>Trung bình</td>
<td>K08_V019,22183</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-8</strong></td>
<td>KIS</td>
<td>Đoạn video 3D mô phỏng nhiệm vụ của một tàu vũ trụ. Có đoạn mô phỏng tàu dùng một loại sóng để quét một bề mặt một địa hình. Có đoạn mô phỏng quỹ đạo của con tàu này.</td>
<td>Khó</td>
<td>K16_V004,15602</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-9</strong></td>
<td>KIS</td>
<td>Trong đoạn video nhìn thấy rất nhiều khinh khí cầu. Có cái có hình cờ hải tặc Luffy trong anime One Piece. Có cái thể hiện hình ảnh người Na'vi trong phim Avatar.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-10</strong></td>
<td>KIS</td>
<td>Một người phụ nữ đang bế một chú chó trả lời phỏng vấn. Chú chó này đạt giải trong một cuộc thi bơi được tổ chức trong một công viên nước.</td>
<td>Trung bình</td>
<td>K20_V009,23950</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-11</strong></td>
<td>KIS</td>
<td>Hai cảnh sát giao thông đang dùng bình chữa cháy để dập một chiếc xe ô tô đang cháy. Chiếc xe bị cháy bên cạnh biển báo hiệu cho biết tốc độ tối đa cho phép là 120km/h.</td>
<td>Trung bình</td>
<td>K19_V022,12761</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-12</strong></td>
<td>KIS</td>
<td>Đoạn video múa rồng, những người biểu diễn múa rồng mặc trang phục của các vận động viên bóng đá.</td>
<td>Trung bình</td>
<td>K08_V021,27090</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-13</strong></td>
<td>QA</td>
<td>Đoạn video mở đầu là hình ảnh một mâm bánh xèo. Kế tiếp là hình ảnh một gian hàng bánh có bảng hiệu "Bánh Dân Gian Miền Tây", mỗi chữ trên một vật hình tròn. Hỏi địa điểm tổ chức sự kiện này được nhắc đến trong video là gì?</td>
<td>Khó</td>
<td>L29_V020,2560,Cà Mau hình như là đáp án sai</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-14</strong></td>
<td>KIS</td>
<td>Trong đoạn tin có nhiều tác phẩm trang trí bằng trái cây. Có đa dạng các loại tác phẩm, có nhiều tác phẩm có hình ảnh chân dung Bác Hồ, Dinh Độc Lập, xe tăng số hiệu 390.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-15</strong></td>
<td>KIS</td>
<td>Trong một đoạn video nấu ăn một món ăn về tôm. Cảnh quay đang lột vỏ con tôm cuối cùng và sau đó để con tôm này lên dĩa đang có sẵn 5 con tôm đã lột vỏ.</td>
<td>Trung bình</td>
<td>L26_V222,3000</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-16</strong></td>
<td>KIS</td>
<td>Nhiều con rùa có kích thước nhỏ đang ăn rau cải trong một trang trại rùa.</td>
<td>Dễ</td>
<td>K04_V021,19746</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-17</strong></td>
<td>KIS</td>
<td>Cảnh đầu tiên có thể thấy 2 bạn nữ mặc áo dài tạo dáng chụp hình với hoa, hai bạn nắm tay nhau, mỗi bạn đang cầm bó hoa giơ lên cao .Sau đó là cảnh 4 bạn nữ mặc áo dài nắm tay nhau đi phía trước chợ Bến Thành.</td>
<td>Khó</td>
<td>K02_V007,11681 là đáp án sai</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-18</strong></td>
<td>KIS</td>
<td>Đoạn tin về trái sầu riêng. Cuối đoạn video là cảnh quay từ trên cao, có một người đẩy xe có chất sầu riêng đi về hướng phải, có một người đẩy xe trống đi về hướng trái.</td>
<td>Trung bình</td>
<td>K04_V013,8618</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-19</strong></td>
<td>KIS</td>
<td>Một nhóm người đang đứng xung quanh một cái bàn, trên bàn có thiết bị và một chiếc điện thoại. Sau đó là cảnh quay cận vào điện thoại, 1 người đang thao tác trên màn hình điện thoại bấm chọn 50ml.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-20</strong></td>
<td>QA</td>
<td>Một cái bàn có để nhiều hộp đĩa CD. Một trong những bìa đĩa có tiêu đề là "Khung trời mơ ước", "Nhớ ai". Đây là cảnh trong một tin tức về một nghệ sĩ, hãy cho biết tên của nghệ sĩ này?</td>
<td>Trung bình</td>
<td>K06_V022,11100,Phạm Đăng Khương</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-21</strong></td>
<td>KIS</td>
<td>Đoạn video chạy nước rút của một chặng đua xe đạp. Người về nhất mặc áo xám, nón trắng. Người về nhì mặc áo trắng, nó trắng. Người về ba mặc áo đen, nón đỏ.</td>
<td>Rất khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-22</strong></td>
<td>KIS</td>
<td>Đầu tiên là cảnh quay một người đang làm hành động mở một gói bánh snack, góc quay từ phía bên trong gói bánh. Sau đó là cảnh quay một dĩa snack khoai tây lát.</td>
<td>Rất khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-23</strong></td>
<td>KIS</td>
<td>Cảnh quay một phụ nữ cosplay nữ siêu nhân đang đi trong hành lang bệnh viện, tiến lại gần một em bé trên tay một người phụ nữ. Người cosplay nữ siêu nhân cùng tạo hình trái tim với đứa bé bằng bàn tay.</td>
<td>Khó</td>
<td>K06_V014,13496</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-24</strong></td>
<td>TRAKE</td>
<td><p>Đoạn video giới thiệu du lịch, trong đoạn video có một người trả lời phỏng vấn, phía sau có thể thấy là Hoàng Thành Thăng Long, hãy tìm thời điểm đầu tiên các địa điểm sau xuất hiện trong bản tin:</p>
<p>E1: Xuất hiện Tháp Rùa tại Hồ Hoàn Kiếm.</p>
<p>E2: Xuất hiện Nhà thờ Lớn Hà Nội.</p>
<p>E3: Xuất hiện Cột cờ Hà Nội</p>
<p>E4: Xuất hiện Văn miếu Quốc Tử Giám</p></td>
<td>Khó</td>
<td>K01_V012,7669,7975,8075,8201</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-25</strong></td>
<td>KIS</td>
<td>Trong đoạn video thấy 3 người đang chất giỏ tôm lên một xe tải có nhiều cây nước đá. Người ở giữa nhúng giỏ tôm vào nước trước khi chất lên xe.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-26</strong></td>
<td>KIS</td>
<td>Đoạn video một tuyến đường ngập nước, người dân đi lại khó khăn. Đoạn video có hình ảnh cột mốc cho biết đây là QL60 tại KM00, thành phố Tân An.</td>
<td>Trung bình</td>
<td>K13_V003,10666</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-27</strong></td>
<td>KIS</td>
<td>Đoạn video Tổng thống Mỹ Donald Trump đi bên cạnh một người phụ nữ. Trang phục người phụ nữ mặc cho thấy có vẻ người này là một sĩ quan. Khung cảnh và âm thanh có vẻ là ở sân bay.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-28</strong></td>
<td>KIS</td>
<td>Đoạn video tin tức về một cánh tay robot. Trong đoạn video có một mô phỏng 3D của cánh tay robot này. Cánh tay robot này có 3 ngón tay.</td>
<td>Khó</td>
<td>K12_V007,18454</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-29</strong></td>
<td>KIS</td>
<td>Cảnh một bạn nam đang đứng trước sản phẩm của mình trong một cuộc thi. Sau đó bạn nam này trả lời phỏng vấn bằng ngôn ngữ ký hiệu.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-30</strong></td>
<td>KIS</td>
<td>Cảnh quay các nguyên liệu được bài trí trên bàn. Ở giữa là một chiếc dĩa trống. Ta đánh số dĩa trên cùng là số 1, và các chén/dĩa khác xung quanh chiếc dĩa trống theo chiều kim đồng hồ được đánh số tăng dần. Các nguyên liệu này sau đó được làm thành 1 chiếc bánh với các lớp từ dưới lên dùng nguyên liệu của các chén/dĩa theo thứ tự: 1 -&gt; 2 -&gt; 4 -&gt; 5 -&gt; 6 -&gt; 3 -&gt; 6 -&gt; ? -&gt; 2 -&gt; 1 -&gt; ?. "?" đại diện cho các nguyên liệu không có trong cảnh quay nguyên liệu ban đầu. Kết thúc đoạn cần tìm bằng việc đầu bếp hoàn thành chiếc bánh đầu tiên.</td>
<td>Rất khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-31</strong></td>
<td>KIS</td>
<td>Cảnh quay mà khung hình được chia làm 3 phần quay một người đang nói về chủ đề y khoa. Cảnh bên phải cùng mặc áo khác màu và vị trí dòng chữ khác với 2 cảnh còn lại. Sau đó là một cảnh khác cũng có bố cục chia 3 tương tự, tuy nhiên lần này cảnh ở giữa tóc ngắn hơn 2 bên còn lại.</td>
<td>Rất khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-32</strong></td>
<td>QA</td>
<td>Cảnh quay một món ăn được bày trên 1 vỉ nướng đặt trên bếp ga. Tuy nhiên món ăn này được nướng trong lò thay vì bếp ga. Sau đó là cảnh làm xốt chấm. Kết thúc bằng cảnh món ăn được bày ra trên dĩa. Trên dĩa trang trí có 2 quả cà chua. Đếm số lượng các "miếng" trên vỉ nướng.</td>
<td>Khó</td>
<td>L26_V444,4845,16</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-33</strong></td>
<td>KIS</td>
<td>Đoạn video gồm các hình ảnh từ tài liệu văn bản/inforgraphic của tổng cục thống kê về tình hình kinh tế xã hội 9 tháng đầu năm 2024. Trong đoạn video có hình ảnh thể hiện tốc độ tăng trưởng GDP và cơ cấu GDP trong 9 tháng này.</td>
<td>Trung bình</td>
<td>K02_V007,4140</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-34</strong></td>
<td>KIS</td>
<td>Trong đoạn video, có thể thấy khung gầm của một xe ô tô điện (chỉ có khung gầm, không có bộ phận bên trên) trong một hệ thống tự động đổi pin. Hệ thống đang tiến hành các thao tác để đổi pin.</td>
<td>Khó</td>
<td>None</td>
<td></td>
</tr>
<tr class>
<td><strong>R3-35</strong></td>
<td>QA</td>
<td>Đoạn video về việc chế tạo vaccine phòng một loại virus. Thông tin trong đoạn video cho biết virus này gây tỷ lệ tử vong (fatality rate) lên đến 88%. Tên của loại virus này là gì?</td>
<td>Trung bình</td>
<td>K02_V012,19388,Marburg</td>
<td></td>
</tr>
</tbody>
</table>
