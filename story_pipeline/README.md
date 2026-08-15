# Vương Bài Tiến Hóa — post-crawl pipeline

Pipeline này giữ **TiênVuc là nguồn prose duy nhất**. Nguồn Trung chỉ được dùng làm mục lục/boundary reference để khôi phục cấu trúc chương gốc; không lấy prose Trung để dịch lại.

## Data layers

1. `raw/` — artifact Runner3 (`page.txt` + metadata), bất biến.
2. `clean/` — tách body TiênVuc, bỏ navigation/boilerplate, chuẩn hóa alias đã biết.
3. `editor_packets/` — mỗi packet gồm 1 phần nguồn + đúng phần Story Bible liên quan.
4. `edited/` — bản Việt đã biên tập, kiểm hash đầu vào + glossary.
5. `merged/` — ghép/split TiênVuc theo `chapter_map` explicit ở mức **segment**, vì ranh giới chương gốc có thể nằm giữa một part TiênVuc.
6. `qa.json` — kiểm consistency và rác nguồn.
7. `book.epub` — EPUB3.

Repo public chỉ giữ **code/config**. Nội dung truyện crawl và EPUB nên để trong workflow artifacts hoặc storage riêng, không commit vào repo.

## Vì sao cần chapter map explicit

Không được ghép chỉ theo tiêu đề TiênVuc hoặc cứ N phần thành một chương. Một section của TiênVuc có thể bị chia thành nhiều phần web trong khi nguyên tác chứa nhiều chương khác nhau; thậm chí điểm cắt chương gốc nằm giữa một part TiênVuc. `chapter_map` vì vậy dùng `segments` với `start_at` / `end_before` marker và là boundary source-of-truth có thể audit.

Ví dụ đã xác minh cho chương gốc 1–3 nằm tại `config/chapter_map.001-003.json`.

## Editor contract

`packet` tạo input cố định cho editor. Editor trả `part-XXXX.edit.json`:

```json
{
  "source_part": 1,
  "input_sha256": "...",
  "edited_title": "...",
  "edited_body": "...",
  "new_entities": [],
  "editor_notes": []
}
```

`apply` từ chối edit cũ/sai hash, drift độ dài bất thường và alias đã bị cấm. Nhân vật/skill/item mới phải được review và thêm vào `config/story_bible.json` trước batch tiếp theo.

## Commands

```bash
python story_pipeline/pipeline.py clean  --input raw --output clean --bible story_pipeline/config/story_bible.json
python story_pipeline/pipeline.py packet --clean clean --output editor_packets --bible story_pipeline/config/story_bible.json
python story_pipeline/pipeline.py apply  --clean clean --edits edits --output edited --bible story_pipeline/config/story_bible.json
python story_pipeline/merge_segments.py  --edited edited --output merged --map story_pipeline/config/chapter_map.001-003.json
python story_pipeline/pipeline.py qa     --chapters merged --bible story_pipeline/config/story_bible.json --output qa.json
python story_pipeline/pipeline.py epub   --chapters merged --output Vuong-Bai-Tien-Hoa.epub
```

## Batch policy

- Khởi đầu 8–20 phần TiênVuc/batch.
- Cập nhật Story Bible sau mỗi batch trước khi biên tập batch kế tiếp.
- Không biên tập hàng nghìn phần độc lập mà thiếu glossary/context chung.
- Chỉ release batch khi `apply`, segment merge và `qa` đều pass.
- Luôn giữ raw → clean → edited để sửa glossary hàng loạt mà không phải crawl lại.
