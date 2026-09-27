/**
 * Chung kết: mỗi câu nộp MỘT đáp án qua DRES và được chấm ngay — không còn danh
 * sách xếp hạng 100 dòng (R@k) của sơ tuyển.
 *
 * Bật cờ này thì mọi đường vào giỏ đáp án bị ẩn: nút "+" trên thẻ kết quả,
 * "Chọn ▸" / "+ Chốt" trên thẻ TRAKE, nút Giỏ trên thanh nav, Add Answer và giỏ
 * bên phải popup video. Chỗ đó popup đặt khối "Nộp DRES", mở sẵn. Để hai luồng
 * cùng hiện thì một cú "Add Answer" quen tay giữa giờ thi là mất thời gian vô
 * ích, còn nhầm sang nút DRES thì là một lần nộp sai bị trừ điểm.
 *
 * Code giỏ vẫn nguyên: đặt `false` là quay về đúng giao diện sơ tuyển.
 */
export const DRES_ONLY = true;
