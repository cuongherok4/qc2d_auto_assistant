# M13 — Hướng dẫn công việc để cả người không chuyên kỹ thuật cũng hiểu

Tài liệu này giải thích **cần làm gì, ai làm, phải giao cái gì và nhìn vào đâu để biết đã xong**. Người điều phối không cần đọc mã nguồn vẫn có thể dùng các mục “Đạt khi” để kiểm tra tiến độ.

Đây là phân công đề xuất dựa trên hiện trạng đã đối chiếu ngày 13/10/2026. “Đã viết” nghĩa là đã thấy mã nguồn trên nhánh của thành viên; chưa mặc nhiên có nghĩa cả hệ thống đã ghép và chạy với dữ liệu thật. Các số liệu trong ví dụ là minh họa.

## 1. Sản phẩm cuối cùng cần làm được điều gì?

Giả sử nhóm có 1.000 ảnh đường phố đã được người khác khoanh xe, người và đặt tên. Người kiểm tra không biết nên xem ảnh nào trước.

Hệ thống của nhóm cần:

1. Nhận ảnh, các khung đã khoanh và tài liệu hướng dẫn gán nhãn.
2. Đọc tài liệu để biết thế nào là đúng, sai hoặc được phép bỏ qua.
3. Tìm những chỗ đáng nghi trong từng ảnh.
4. Đưa ảnh đáng nghi lên đầu danh sách, ghi rõ nên nhìn vật nào và vì sao.
5. Cho người kiểm tra xem ảnh, đưa ra kết luận và lưu lại thời gian kiểm tra.
6. Đo xem cách xem ảnh theo thứ tự này có giúp tìm lỗi sớm hơn không.

**Ví dụ kết quả người dùng cần thấy:** “Ảnh street_017 có điểm rủi ro 78,65. Nên xem xe B vì chưa có khung; người D vì đang mang nhãn xe; xe C vì quá nhỏ so với quy định.” Điểm cao là lời nhắc xem trước, chưa phải kết luận ảnh chắc chắn sai.

[Xem hai hình minh họa đầu vào và từng bước xử lý](vi-du-xuyen-suot.md).

## 2. Những từ cần hiểu trước khi nhận việc

| Từ thường gặp | Hiểu đơn giản |
|---|---|
| Nhãn, box | Khung chữ nhật quanh vật thể và tên của vật đó, ví dụ “xe” hoặc “người” |
| Guideline | Tài liệu quy định phải khoanh gì, đặt tên gì, vật nào được bỏ qua |
| LLM | AI đọc tài liệu và chuyển các quy định thành danh sách có cấu trúc |
| Spec | Bản quy định viết theo cách chương trình đọc được; vẫn cần người kiểm tra và duyệt |
| Detector | AI nhìn ảnh và tự đề xuất vật thể nằm ở đâu, thuộc loại nào |
| Tín hiệu | Một dấu hiệu đáng nghi, chẳng hạn hai khung trùng nhau hoặc máy thấy xe mà nhãn chưa có |
| Bằng chứng | Chỉ đúng vị trí đáng nghi và giải thích, chẳng hạn “xe B cao 60 px chưa có khung” |
| Hàng đợi | Danh sách ảnh đã được xếp theo thứ tự nên kiểm tra |
| CVAT, extension | Màn hình xem/gán nhãn và bảng phụ bên cạnh để hiện gợi ý của hệ thống |
| API | Phần chuyển dữ liệu giữa bộ xử lý và màn hình; người sử dụng không cần thao tác trực tiếp |
| Pilot | Một lượt dùng thử có người thật, ghi lại kết quả và thời gian |
| Ghép code | Đưa các phần chương trình của từng người vào một bản chung rồi kiểm tra chúng làm việc cùng nhau |

## 3. Ghi nhận phần đã làm để không giao lại từ đầu

| Người | Phần đã thấy trong mã nguồn | Việc chuyển sang làm tiếp |
|---|---|---|
| **Tú Anh** | Màn hình phụ trong CVAT; nhận danh sách ảnh; lưu kết luận và thời gian; công cụ đọc/chỉnh/duyệt guideline; công cụ dựng demo và ghi nhận pilot | Bàn giao, nối dữ liệu thật, kiểm tra toàn luồng, tổ chức pilot. Không viết lại các công cụ trên |
| **Long** | Bốn dấu hiệu cơ bản; đọc bản quy định; kiểm tra khung thấp hơn ngưỡng cho phép | Bàn giao phần đã có, bổ sung luật còn thiếu, duyệt nội dung guideline, kiểm tay và báo cáo |
| **Cường** | Nền tảng đọc dữ liệu, tính điểm, tính chỉ số đánh giá và điều phối chương trình | Ghép các phần, bổ sung phần còn thiếu, tạo danh sách kèm bằng chứng, đo kết quả |
| **Sơn** | Chưa xác minh được sản phẩm detector chạy đủ dữ liệu trong lần đối chiếu | Trước hết bàn giao phần đã làm ở máy riêng nếu có; tiếp tục chuẩn bị dữ liệu và chạy detector |

Không giao lại toàn bộ phần của Sơn chỉ vì chưa thấy trên bản chung; cần xem sản phẩm đã có trước. Tương tự, giao diện đã hiện lên chưa đủ để kết luận hệ thống đã chấm điểm đúng.

## 4. Làm theo 10 việc dưới đây

### Việc 1 — Gom phần đã viết thành một bản dùng chung

**Cường phụ trách; Tú Anh, Long và Sơn bàn giao.** Làm trước khi yêu cầu ai viết lại một chức năng.

1. Tú Anh chỉ rõ bản chương trình đang chạy và hướng dẫn mở màn hình review, đọc guideline, lưu kết luận.
2. Long bàn giao bốn dấu hiệu đã viết và phần kiểm ngưỡng kích thước đã có.
3. Sơn báo ảnh/nhãn đã có ở đâu, đã chạy detector được bao nhiêu ảnh, phần nào còn ở máy riêng.
4. Cường ghép các phần vào bản chung. Khi hai người sửa cùng một chỗ, Cường phối hợp để giữ các chức năng đã có.
5. Nhóm chạy thử một ví dụ nhỏ, ghi lỗi bằng thao tác tái hiện cụ thể.

**Phải giao:** bản chung có thể mở được; hướng dẫn chạy; bảng “đã chạy được / còn thiếu / ai xử lý”.

**Đạt khi:** một thành viên khác làm theo hướng dẫn có thể mở bản chung và xem ví dụ. Nếu dùng dữ liệu giả lập, phải ghi rõ là giả lập.

### Việc 2 — Chuẩn bị ảnh và nhãn để cả nhóm kiểm cùng một thứ

**Sơn phụ trách; Cường và Tú Anh nhận.** Không cần chờ toàn bộ AI hoàn thành.

1. Chuẩn bị ảnh BDD100K và nhãn đi kèm. Mỗi ảnh phải có tên để tìm lại đúng nhãn của nó.
2. Kiểm tra ảnh mở được, tên ảnh khớp với nhãn; phân biệt ảnh không có nhãn với ảnh bị thiếu tệp nhãn.
3. Chọn trước **100 ảnh để thử đường đi của dữ liệu**. Khi chạy ổn mới mở rộng đến tập dự kiến 10.000 ảnh.
4. Báo số ảnh thực có, số ảnh lỗi/thiếu và nơi lưu. Không báo “đủ 10k” nếu chưa kiểm đủ.
5. Tú Anh đưa các ảnh thử vào CVAT và kiểm tra tên ảnh trong danh sách mở đúng ảnh trên màn hình.

**Phải giao:** bộ ảnh + nhãn dùng chung, danh sách ảnh thử, ghi chú dữ liệu thiếu nếu có.

**Đạt khi:** Cường đọc được nhãn, Tú Anh mở đúng ảnh trong CVAT, Long tìm lại được cùng ảnh để đối chiếu. Ví dụ chọn `street_017` thì cả ba người đều thấy cùng một ảnh.

### Việc 3 — Viết rõ quy định trước khi yêu cầu máy kiểm

**Long phụ trách nội dung; Tú Anh hướng dẫn dùng công cụ đã viết.** Cường hỗ trợ khi cần giải quyết cách diễn giải.

1. Chuẩn bị bản guideline cơ sở và các biến thể đã dự kiến. Tên tài liệu phải nói rõ bản nào áp dụng cho bộ ảnh nào.
2. Ghi rõ tên vật được phép gán, khi nào được bỏ qua, kích thước đo trên ảnh gốc và các thuộc tính bắt buộc.
3. Dùng công cụ của Tú Anh đưa tài liệu vào AI đọc. AI phải trả lại quy định và câu/trang làm căn cứ.
4. Long mở tài liệu gốc, đối chiếu từng quy định AI trích: có nhầm 30 thành 300 không, có tự thêm điều tài liệu không nói không?
5. Sửa phần sai; phần chưa rõ thì ghi “chưa rõ”, không tự coi là một luật đã thống nhất.
6. Duyệt bản đúng, ghi người duyệt và phiên bản; bàn giao cho Cường và Sơn.

**Ví dụ:** tài liệu nói “bỏ qua xe cao dưới 30 px”. AI cần trích được “xe → 30 px”, kèm câu nguồn. Không được tự biến thành “chiều rộng 30 px” hoặc áp dụng cho mọi loại vật.

**Phải giao:** tài liệu gốc + bản quy định đã duyệt + danh sách chỗ chưa rõ. Đây là ba thứ người không biết lập trình vẫn có thể đọc và kiểm.

**Đạt khi:** đọc tài liệu và bản trích sẽ thấy cùng ý nghĩa; bản chưa duyệt không được dùng như quy định chính thức. Một bản đã duyệt phải được chạy thử qua chương trình kiểm của Long, không chỉ mở xem được.

### Việc 4 — Cho AI nhìn ảnh và đối chiếu với khung người đã vẽ

**Sơn phụ trách; Long cung cấp quy định; Cường nhận kết quả.** Có thể bắt đầu chạy AI trên 100 ảnh trong lúc Long kiểm guideline.

1. Chọn và ghi rõ model dùng để tìm vật trong ảnh; báo loại vật model nhận được và loại nào chưa hỗ trợ.
2. Chạy trên 100 ảnh thử, lưu vị trí và tên từng vật model tìm thấy. Nhãn người đã vẽ vẫn giữ riêng.
3. Loại khỏi phần bắt buộc đối chiếu những vật guideline cho phép bỏ qua. Ví dụ xe 18 px khi ngưỡng là 30 px.
4. So vị trí vật model tìm thấy với vị trí khung hiện có, rồi mới so tên nhãn.
5. Tạo bốn dạng nghi ngờ: vật có vẻ bị bỏ sót; tên nhãn khác nhau; khung có vẻ lệch; khung hiện có nhưng model không tìm thấy vật tương ứng.
6. Lưu ảnh/vị trí minh họa cho từng dạng. Khi kết quả thử đúng cách xử lý, chạy tiếp toàn bộ tập đã thống nhất.

**Ví dụ:** model thấy xe B cao 60 px nhưng không có nhãn nào ở đó → ghi “nghi thiếu xe B”. Với người D đã có khung nhưng tên là xe → ghi “nghi sai tên”, tránh đếm cùng một sự khác biệt thành cả thiếu vật lẫn thừa vật.

**Phải giao:** danh sách dự đoán, các điểm khác nhau với nhãn, ảnh minh họa và số ảnh thực sự chạy thành công.

**Đạt khi:** người kiểm tra nhìn được model đề xuất box nào, khác nhãn ở đâu và thuộc quy định nào. “Model không thấy” chỉ là nghi ngờ: model cũng có thể bỏ sót vật đúng.

### Việc 5 — Kiểm các khung theo quy định và dấu hiệu bất thường

**Long phụ trách luật và bốn dấu hiệu đã có. Tú Anh làm ba dấu hiệu hình học còn lại sau khi luồng review được ghép ổn.** Cường không chờ đủ mọi dấu hiệu mới tạo bản thử đầu tiên.

Bốn dấu hiệu Long đã viết là: ảnh quá đông vật thể; nhiều vật rất nhỏ; có loại vật ít gặp; khung chạm mép ảnh nhưng chưa ghi vật bị cắt bởi mép ảnh. Ba dấu hiệu đầu chủ yếu nhắc ảnh khó kiểm, không tự chứng minh nhãn sai. Long bàn giao ví dụ cho từng dấu hiệu để Cường đưa vào bản chung.

Long cần bàn giao phần đã viết, sau đó hoàn thiện:

1. **Khung dưới ngưỡng:** dùng lại phần đã có. Ví dụ xe C cao 18 px nhưng yêu cầu từ 30 px → nghi gán thừa.
2. **Tên không được phép:** guideline chỉ cho phép xe và người, nhãn lại mang tên khác → chỉ ra tên đó.
3. **Thiếu thông tin bắt buộc:** guideline yêu cầu ghi vật có bị che khuất hay không, nhưng nhãn chưa có trường này → nhắc bổ sung.
4. **Vật bắt buộc gán nhưng bị thiếu:** dùng kết quả đối chiếu của Sơn. Không tự tạo thêm một phiên bản tìm vật khác.
5. Với trường hợp sát ngưỡng, chẳng hạn cao 29 px so với ngưỡng 30 px và có vùng dung sai đã thống nhất, ghi là cần xem thêm thay vì kết luận chắc chắn sai.

Ba việc hình học bổ sung của Tú Anh là: phát hiện kích thước quá khác thường; hai khung cùng tên gần như trùng nhau; hai khung khác tên chồng lấp bất thường. Phải xét các trường hợp hợp lý như người đang đi xe, không coi mọi chồng lấp là lỗi.

**Phải giao:** mỗi phép kiểm có một ví dụ bị nhắc, một ví dụ không bị nhắc và lý do dễ hiểu. Ghi rõ phép kiểm nào đã chạy được, phép nào chưa chạy.

**Đạt khi:** cùng một khung xe 18 px bị nhắc theo guideline 30 px nhưng không bị nhắc bởi luật kích thước nếu guideline chỉ yêu cầu 15 px. Điều này cho thấy hệ thống thật sự dùng quy định của bộ ảnh.

### Việc 6 — Gom các nghi ngờ thành danh sách nên xem trước

**Cường phụ trách; nhận kết quả từ Sơn, Long và Tú Anh.** Bắt đầu với các dấu hiệu đã chạy được.

1. Gom các dấu hiệu theo từng ảnh, kể cả ảnh không có cảnh báo.
2. Quy định dấu hiệu nào quan trọng hơn. Ví dụ nghi bỏ sót vật có thể được ưu tiên hơn ảnh chỉ đông vật thể.
3. Tính điểm, sắp từ cao xuống thấp; ghi rõ bản này dùng những dấu hiệu nào.
4. Chọn tối đa ba lý do nổi bật. Mỗi lý do phải chỉ được vật, vị trí hoặc con số có thể kiểm lại.
5. Giao cho Tú Anh cả danh sách thứ tự lẫn vị trí đáng nghi. Đặt cùng phiên bản để tránh dùng điểm mới với lời giải thích cũ.

**Ví dụ lý do đạt:** “Xe B cao 60 px chưa có nhãn; guideline yêu cầu gán xe từ 30 px.” **Lý do chưa đạt:** “Ảnh có vấn đề, cần kiểm tra.”

**Phải giao:** danh sách ảnh có hạng/điểm/lý do và dữ liệu chỉ vị trí các box nghi vấn.

**Đạt khi:** người nhận mở một ảnh trong danh sách và chỉ ra được vì sao nó được ưu tiên. Nếu chưa nối detector, phải nói rõ bản này chưa sử dụng detector.

### Việc 7 — Nối danh sách vào màn hình và lưu được một lượt review thật

**Tú Anh phụ trách, Cường hỗ trợ kết nối kết quả.** Phần màn hình, lưu dữ liệu và công cụ đã viết được dùng lại.

1. Nhận danh sách và bằng chứng cùng phiên bản từ Cường, cho hiện trong bảng phụ cạnh CVAT.
2. Chọn một dòng và kiểm tra mở đúng ảnh, đúng khung hình. Mỗi máy phải có bảng liên kết ảnh của chính máy đó.
3. Kiểm tra điểm, ba lý do và vị trí box trên màn hình có khớp sản phẩm Cường giao không.
4. Thực hiện lần lượt “Lỗi thật”, “Bot nhầm”, “Bỏ qua”; kiểm tra lưu được tên người và thời gian của phiên làm việc.
5. Thử tải lại trang và gửi lại thao tác sau lỗi kết nối: không mất kết luận đã lưu, không biến cùng một lần gửi thành hai lượt review.
6. Mở bảng kết quả đã lưu, chỉ ra một dòng tương ứng với thao tác vừa thực hiện.

**Phải giao:** một lượt chạy có ảnh thật, ảnh chụp màn hình hoặc video ngắn, và dòng kết quả đã lưu để đối chiếu.

**Đạt khi:** có thể đi từ “chọn ảnh” đến “xem lại kết luận đã lưu” mà không phải sửa dữ liệu thủ công giữa các bước.

**Chấm lại sau sửa nhãn là việc tiếp theo:** Tú Anh đã có phần gửi yêu cầu, Cường còn phải nối bộ chấm điểm. Khi nối xong, thử sửa nhãn → Save trong CVAT → chấm lại → xem lý do/điểm mới. Điểm có thể không đổi nếu dấu hiệu khác vẫn còn; không đặt điều kiện cứ bấm là điểm phải giảm. Nếu chưa nối thì ghi rõ chưa hỗ trợ.

### Việc 8 — Kiểm bằng mắt để biết cảnh báo nào đúng

**Long tổ chức; Long và Sơn kiểm độc lập.** Việc này kiểm chất lượng phát hiện, khác với lượt đo tốc độ ở việc 9.

1. Lập danh sách đề xuất 150 ảnh: 75 ảnh chọn ngẫu nhiên, 75 ảnh lấy ở đầu hàng đợi nhưng không trùng 75 ảnh trước.
2. Giữ nguyên ảnh, nhãn và guideline ban đầu để cả hai người xem cùng một phiên bản.
3. Mỗi người tự xem đủ danh sách, chưa trao đổi kết luận. Nếu có thể, che điểm/lý do máy khi kiểm lần đầu để ít bị gợi ý dẫn dắt.
4. Với mỗi ảnh, ghi có lỗi/không thấy lỗi/chưa chắc, vị trí vật, loại lỗi và quy định dùng để kết luận.
5. Sau đó mới đối chiếu, ghi các chỗ bất đồng và kết luận cuối. Giữ cả hai bản nhận xét ban đầu.
6. Cường hoặc Long dùng kết quả để tính mức đồng thuận giữa hai người; Long giải thích các bất đồng trong báo cáo.

**Phải giao:** danh sách 150 ảnh, hai bảng nhận xét độc lập, bảng thống nhất sau đối chiếu. Nếu chỉ làm được 80 ảnh thì ghi 80, không đổi tên thành 150 ảnh đã kiểm.

**Đạt khi:** mọi con số trong bảng đều tìm lại được ảnh và người đánh giá. Mẫu có nhiều ảnh ở đầu hàng đợi không tự đại diện cho tỉ lệ lỗi của toàn bộ 10.000 ảnh.

**Kiểm thêm ảnh ít được ưu tiên:** Long và Cường chốt chính xác cách chọn, Tú Anh chỉnh cách đưa ảnh này vào review. Ví dụ nếu lấy 5% phần còn lại sau top 20% của 1.000 ảnh thì lấy 5% × 800 = 40 ảnh. Đây không phải “cứ 10 ảnh chèn một ảnh”; hai cách không được ghi như nhau.

### Việc 9 — Chứng minh xem theo hàng đợi có lợi hơn

**Cường phụ trách phép so sánh; Tú Anh tổ chức dùng thử; Long ghi báo cáo.** Có hai phép đo riêng.

**A. Đo khả năng đưa ảnh lỗi lên đầu danh sách.**

1. Cường tạo bản sao nhãn để cố ý thêm lỗi đã biết đáp án: xóa một nhãn, đổi tên, dịch/co giãn khung hoặc thêm khung giả theo kế hoạch thí nghiệm.
2. Bản đáp án giữ riêng, không đưa cho bộ tìm dấu hiệu để nó “nhìn trước đáp án”. Nhãn dùng review thật không bị sửa để tạo thí nghiệm.
3. Tách bộ dùng điều chỉnh và bộ dùng kiểm tra cuối. Chốt cách chấm trước khi mở kết quả kiểm tra cuối.
4. So cùng một bộ ảnh bằng thứ tự ngẫu nhiên, thứ tự file và thứ tự hệ thống đề xuất.
5. Đếm khi chỉ xem 20% ảnh đầu thì bao nhiêu ảnh có lỗi đã được đưa vào phần đã xem. Báo thêm số lỗi theo từng loại nếu có đáp án chi tiết.

**Ví dụ cách đọc số:** có 100 ảnh, trong đó 20 ảnh bị lỗi. Nếu 20 ảnh đầu của hệ thống chứa 12 ảnh lỗi thì đã đưa được 12/20 = 60% ảnh lỗi vào phần ưu tiên. Đây là ví dụ tính toán, không phải kết quả dự án; cũng chưa có nghĩa reviewer thực tế nhìn ra mọi lỗi trong 12 ảnh đó.

**B. Đo thời gian người thật.**

1. Dùng công cụ pilot Tú Anh đã viết để đăng ký một bộ 30 ảnh mới đối với hai người tham gia.
2. Tạo hai bản công việc CVAT riêng từ cùng nhãn ban đầu: một người xem theo hàng đợi, một người xem theo thứ tự file. Không để việc sửa nhãn của người này làm thay đổi ảnh của người kia.
3. Giữ điều kiện hiển thị và nhiệm vụ review giống nhau; thay đổi chính là thứ tự ảnh. Ghi rõ nếu có khác biệt khác.
4. Ghi thời gian và kết luận thật. Nếu một người đã xem bộ này trong việc 8, chọn người khác hoặc bộ ảnh khác.
5. So số lỗi được xác nhận trong cùng khoảng thời gian. Nếu đủ thời gian, dùng bộ mới và đổi vai hai người để giảm ảnh hưởng người nhanh/người chậm.

**Phải giao:** bảng so sánh có nguồn từ lần chạy và bản xuất kết quả dùng thử. Tách rõ số liệu lỗi giả lập với lỗi thật.

**Đạt khi:** người đọc biết số nào là tính trên đáp án thí nghiệm, số nào đo bằng đồng hồ của người thật. Không kết luận “tiết kiệm 80% thời gian” chỉ vì hệ thống ưu tiên 20% ảnh. Lượt thử nhỏ chỉ cho kết quả ban đầu.

### Việc 10 — Làm bản nộp mà người khác có thể xem và chạy lại

**Long viết báo cáo; Cường chốt nội dung và số liệu; Tú Anh dựng máy demo; Sơn chuẩn bị ảnh minh họa và hỗ trợ dữ liệu.**

1. Chọn một ví dụ dễ hiểu theo chuỗi: tài liệu → quy định đã duyệt → ảnh có chỗ nghi → lý do → người kiểm tra → kết quả đã lưu.
2. Tú Anh dựng lại bản đã ghép theo hướng dẫn. Ghi rõ phần nào dùng dữ liệu thật và phần nào dùng minh họa.
3. Cường và Long đưa bảng so sánh vào báo cáo, mỗi con số có nguồn; ghi cả hạn chế và tính năng chưa hoàn tất.
4. Quay video 3–5 phút theo đúng luồng vừa chạy. Không cần đi vào cách viết code.
5. Một thành viên khác xem tài liệu/video và giải thích lại được: hệ thống nhận gì, làm gì, giúp ai, kết quả tốt ở điểm nào.

**Phải giao:** hướng dẫn chạy, báo cáo, hình hệ thống, video và bảng kết quả kèm nguồn.

**Đạt khi:** bản demo, báo cáo và video mô tả cùng một phiên bản; không trình bày tính năng dự định làm như tính năng đã hoàn thành.

## 5. Mỗi người bắt đầu từ đâu ngay bây giờ?

| Người | Làm trước | Làm tiếp | Người đang chờ sản phẩm |
|---|---|---|---|
| **Cường** | Ghép phần đã có của Tú Anh và Long; kiểm bộ 100 ảnh | Ra hàng đợi đầu tiên có bằng chứng; ghép detector; đo chất lượng | Tú Anh cần hàng đợi; Long cần số liệu |
| **Sơn** | Bàn giao tình trạng dữ liệu và phần đã làm; chạy detector 100 ảnh | Lọc theo guideline, đối chiếu nhãn, chạy đủ tập, kiểm tay | Cường cần tín hiệu; Long cần kết quả tìm vật bỏ sót |
| **Tú Anh** | Bàn giao và hướng dẫn dùng công cụ đã viết; mở được batch thử | Nối hàng đợi thật, kiểm lưu kết luận, chạy pilot; sau đó bổ sung hình học/vẽ box | Long cần công cụ guideline; cả nhóm cần màn hình dùng thử |
| **Long** | Bàn giao các luật/tín hiệu đã viết; chuẩn bị và duyệt guideline | Hoàn thiện luật, lập phiếu kiểm tay, kiểm độc lập với Sơn, viết báo cáo | Sơn và Cường cần quy định đã duyệt |

Sơn chạy AI trong lúc Long kiểm guideline; Tú Anh dùng danh sách mẫu để kiểm màn hình trong lúc Cường ghép dữ liệu. Chưa có toàn bộ 10.000 ảnh vẫn có thể kiểm đường đi bằng 100 ảnh. Bản thử phải ghi rõ dùng mẫu nào và bao nhiêu ảnh.

## 6. Những mốc người điều phối có thể kiểm mà không đọc code

| Mốc | Yêu cầu nhóm mở cho xem | Chưa đạt nếu |
|---|---|---|
| **1. Có đầu vào chung** | Cùng một ảnh, nhãn và tài liệu; AI trích luật, người duyệt xem được | Mỗi máy dùng một bộ khác nhau hoặc không biết quy định nào đang áp dụng |
| **2. Có kết quả QC đầu tiên** | Một ảnh hiện điểm, lý do và vật bị nghi | Chỉ có điểm mà không giải thích được điểm đến từ đâu |
| **3. Dùng được xuyên suốt** | Chọn ảnh → mở đúng CVAT → kết luận → xem lại dữ liệu đã lưu | Phải sửa file thủ công giữa chừng, mất kết luận hoặc mở nhầm ảnh |
| **4. Có bằng chứng chất lượng** | Bảng kiểm tay và bảng so sánh; mở được ảnh/vết ghi làm nguồn | Chỉ có video đẹp, không có số liệu kiểm chứng |
| **5. Có bản nộp** | Người khác dựng lại được; video và báo cáo cùng phiên bản | Bản chạy chỉ hoạt động trên một máy nhờ thao tác chưa được hướng dẫn |

Lịch trước đó đặt mốc demo ngày 16/10 và dừng bổ sung tính năng lúc 20:00 ngày 15/10. Khi cập nhật lịch, giữ thứ tự các mốc trên và báo rõ sản phẩm thực tế đã đạt, thay vì chỉ đổi ngày.

## 7. Những việc chưa cần đưa vào phần bắt buộc

Sau khi luồng cốt lõi chạy ổn mới cân nhắc: AI xem ảnh để trả lời câu hỏi phức tạp; model học cách chấm điểm từ dữ liệu; tự học lại sau các lượt review. Cường phụ trách các phần mở rộng này, Tú Anh hỗ trợ kết nối khi cần.

Nếu thiếu thời gian, ưu tiên **danh sách có lý do → review có lưu kết quả → đánh giá có bằng chứng**. Chưa có AI nâng cao vẫn có thể làm rõ giá trị của đề tài bằng bản dùng luật và detector. Không đưa các phần mở rộng chưa chạy vào con số tiến độ hoàn thành.

## 8. Mẫu bàn giao dùng chung

Mỗi việc chỉ nên ghi “xong” khi người nhận kiểm được sản phẩm. Có thể sao chép mẫu dưới đây vào báo cáo nhóm:

```text
Việc số / tên việc:
Người làm:
Trạng thái: chưa bắt đầu / đang làm / chờ đầu vào / chờ kiểm tra / đã nhận bàn giao
Đã làm được gì, nói bằng kết quả nhìn thấy:
Sản phẩm nằm ở đâu:
Dùng dữ liệu thật hay giả lập, bao nhiêu ảnh:
Người nhận cần làm gì để kiểm tra:
Kết quả mong đợi khi kiểm tra:
Còn thiếu gì hoặc đang lỗi ở đâu:
Đang chờ ai giao cái gì:
Người nhận xác nhận / ngày:
```

Ví dụ: “Đã đưa 100 ảnh thử vào màn hình; chọn street_017 mở đúng ảnh; bấm Lỗi thật rồi tải lại vẫn thấy kết quả đã lưu. Chưa nối chấm lại sau sửa nhãn; đang chờ Cường giao bộ chấm điểm.” Báo như vậy giúp cả người không chuyên biết phần nào dùng được và phần nào còn thiếu.

Chi tiết hiện trạng mã nguồn và giao diện bàn giao nằm trong [bản phân tích kỹ thuật](phan-tich-va-phan-cong-13-10.md). Dùng tài liệu này để giao việc và kiểm đầu ra; dùng bản kỹ thuật khi lập trình và ghép các phần.
