# Vương Bài Tiến Hóa — STYLE v1 strict test

## Mục tiêu
- Viết lại prose convert thành tiếng Việt tự nhiên, lạnh, gọn, dễ đọc.
- Không tóm tắt; giữ dữ kiện/cốt truyện 1:1.
- Có thể tách/gộp/đảo câu trong cùng một ý để tiếng Việt tự nhiên.
- Nhịp chiến đấu nhanh; câu mô tả rõ hình ảnh, tránh Hán-Việt gượng.

## Bất biến tuyệt đối
- Giữ nguyên mọi con số, %, đơn vị, cấp độ, điều kiện skill, item, tên riêng và quan hệ nhân quả.
- Không dịch, Việt hóa, đổi tên, đổi viết hoa hoặc tự chuẩn hóa tên riêng/item/skill/class nếu nguồn đã có tên nhận diện được.
- Đặc biệt PHẢI giữ nguyên chuỗi `Knights of the Round Table`; không đổi thành `Hiệp Sĩ Bàn Tròn`.
- Giữ cách gọi `mặt nạ người hầu`, `trọng kiếm sĩ`, `trọng thuẫn cự chùy sĩ`; không sáng tạo tên class mới như `Kẻ Hầu Hạ Mặt Nạ`.
- Giữ `Dấu Ấn Mộng Yểm`, `Chân Thực Thiết Cát Thuật`, `Dị biến chi lôi đình cự côn` khi các tên này xuất hiện.
- Item có tên riêng phải giữ đúng tên lõi; không biến item thành mô tả chung.
- Không tự thêm POV, cảm xúc, giải thích, tình tiết hoặc hình ảnh không có trong nguồn.
- Không tự quy đổi đơn vị.

## Đại từ và giọng
- Với Phương Lâm: ưu tiên `hắn`, không dùng `anh ta`.
- Với Marseille và nam nhân vật khác trong narration: ưu tiên `hắn` hoặc tên riêng khi cần tránh nhập nhằng; không dùng `anh ta`.
- Không dùng `họ` nếu chủ ngữ là nhóm đối địch mà `bọn họ` tự nhiên hơn trong văn phong hiện tại.
- Phương Lâm: quan sát lạnh, thực dụng, đầu óc nhanh; không tô bi lụy quá mức.
- Ưu tiên động từ trực tiếp, câu vừa/ngắn, tránh từ đệm.

## Dấu hiệu convert phải loại
- mười phần; nhưng mà; đồng dạng; phảng phất; đang tại; phát giác; bạo lộ; sử dụng về sau; kỹ năng phóng thích; đối hắn vô hiệu; tại X giây bên trong; chói tai ... thanh âm.
- Classifier/demonstrative đặt sai kiểu `cái này trang bị`, `bản vật phẩm`.
- Không tạo câu vô nghĩa do sửa máy, ví dụ kiểu `cắn răng đoản kiếm`; phải hiểu đúng hành động gốc rồi viết tiếng Việt tự nhiên như `ngậm đoản kiếm` nếu nguồn là miệng cắn kiếm.

## Hệ thống/item/skill
- Có thể đổi số viết bằng chữ sang chữ số hoặc ngược lại CHỈ KHI giá trị hoàn toàn không đổi; tuy nhiên ưu tiên giữ hình thức nguồn để QA dễ hơn.
- Các dòng hệ thống có thể tách dòng cho dễ đọc nhưng không được mất bất kỳ thuộc tính/điều kiện nào.
- Không thay `điểm tâm lúa mì đen` bằng `bánh mì đen` nếu nó đang được dùng như tên vật phẩm.

## Quy tắc QA
- Sau khi viết xong, tự rà lại trong im lặng: số/%/đơn vị; proper nouns; item/skill/class; câu cuối; không truncation; không duplicate; không tự dịch tên.
- Chỉ xuất bản chương hoàn chỉnh, không xuất ghi chú QA.
