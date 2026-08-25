# Long-form ebook editorial pipeline

`story_pipeline` bắt đầu từ **Vương Bài Tiến Hóa (VBTH)** nhưng orchestration/checkpoint/storage contract dùng chung cho các ebook dài tương tự.

## Kiến trúc chuẩn

- **Cloudflare R2 = canonical machine artifact store**: master/source, config snapshots, chapter work, sidecars, QA artifacts, builds và final machine copy.
- **Runner3 Core Worker + Cloudflare D1 = durable control plane**: progress, semantic identity, artifact hash/R2 key, QA state, resume/recovery.
- **Google Sheet `AI Flow Control Center` = human control view**: status/progress/next action; không phải runtime SOT trừ flow nào khai báo decision layer explicit.
- **Dropbox = human library**: context dài, tài liệu, sample và final deliverable. Không chứa raw/intermediate/retry/sidecar hàng loạt và không nằm trên execution path.
- **Runner/VPS = execution**: extract/clean/edit/QA/build EPUB.
- **GitHub = code/config/manifests/migrations/proof metadata nhỏ**, không phải artifact store.

D1 dùng schema/API generic hiện có; không tạo Worker/Queue/bảng riêng cho từng ebook.

## Book manifests

Mỗi ebook có manifest trong `story_pipeline/books/`.

- VBTH: `books/vbth.json`
- Ebook mới: copy `books/_template.json`, đặt `book_id` ổn định, title/author/chapter count, source adapter, editorial versions và R2 prefix riêng.

Checkpoint namespace:

```text
ebook-editorial / book:<book_id>:main
ebook-editorial / book:<book_id>:chapter:<NNNN>
```

VBTH vẫn mirror checkpoint cũ `vbth-editorial/main` trong giai đoạn tương thích.

## Canonical R2 layout

Bucket mặc định dùng shared bucket `runner3-artifacts`; mỗi ebook bị cô lập bằng prefix.

```text
runner3-artifacts/
  ebooks/<book_id>/
    source/
      master.epub
      chapters/...
    config/
      story-bible.json
      glossary.json
      editorial-rules.md
      gold/...
    work/
      chapters/
        0001.*
        0001.meta.json
    qa/
      reports/...
      failures/...
    builds/
      ...
    final/
      <book_id>-final.epub
```

Không mirror R2 sang Dropbox.

## Human projection

Google Sheet chỉ cần một dòng/flow để nhìn nhanh toàn hệ thống. Dropbox chỉ publish thứ người cần đọc/lấy:

```text
<Dropbox human root>/<book_id>/
  README / long context
  sample
  final deliverable
```

Nếu Sheet/Dropbox lỗi hoặc sync trễ, ebook runtime vẫn tiếp tục dựa trên D1 + R2.

## Durable chapter contract

Một chapter chỉ được `DONE` theo thứ tự:

```text
source hiện tại
  -> semantic identity (source + meaningful editorial config/model versions)
  -> AI edit
  -> QA PASS
  -> artifact + sidecar local
  -> upload artifact + sidecar lên R2
  -> readback/hash verify từ R2
  -> commit D1 chapter checkpoint
  -> advance book/main progress
  -> project status sang Google Sheet
  -> publish human-facing output sang Dropbox khi cần
```

**Không commit D1 success trước R2 verify.**

Sidecar `ebook-chapter-artifact-v1` lưu tối thiểu:

```text
book_id, chapter
source_sha256
config_sha256
semantic_input_sha256
artifact_sha256
artifact_bytes
qa=pass
```

Resume semantics:

- D1 + sidecar + artifact cùng hash/current semantic identity -> `SKIP`.
- D1 mất/stale nhưng sidecar + artifact cùng khớp current semantic identity -> `RECOVER` D1, không edit lại.
- Artifact tồn tại nhưng thiếu/sai sidecar, source/config đổi, hash lệch -> `EDIT`.

**Mere artifact existence never authorizes recovery.**

## Generic checkpoint commands

```bash
python story_pipeline/ebook_checkpoint.py sync-main \
  --book story_pipeline/books/vbth.json \
  --state story_pipeline/state.json

python story_pipeline/ebook_checkpoint.py prepare-sidecar \
  --book story_pipeline/books/vbth.json \
  --chapter 4 \
  --source-file /work/source/0004.txt \
  --artifact-file /work/output/0004.txt \
  --meta-out /work/output/0004.meta.json \
  --config-file story_pipeline/config/story_bible.json

python story_pipeline/ebook_checkpoint.py decision \
  --book story_pipeline/books/vbth.json \
  --chapter 4 \
  --source-file /work/source/0004.txt \
  --artifact-file /work/output/0004.txt \
  --artifact-meta-file /work/output/0004.meta.json \
  --config-file story_pipeline/config/story_bible.json

# Chỉ gọi sau khi caller đã upload + readback/hash verify cả 2 object trên R2.
python story_pipeline/ebook_checkpoint.py complete \
  --book story_pipeline/books/vbth.json \
  --chapter 4 \
  --source-file /work/source/0004.txt \
  --artifact-file /work/output/0004.txt \
  --artifact-meta-file /work/output/0004.meta.json \
  --artifact-r2-key 'ebooks/vbth/work/chapters/0004.txt' \
  --artifact-meta-r2-key 'ebooks/vbth/work/chapters/0004.meta.json' \
  --config-file story_pipeline/config/story_bible.json
```

Storage transport R2 và human-projection adapters phải tách khỏi generic D1 helper; không nhét Cloudflare/Dropbox/Google credentials vào checkpoint logic.

Xem chuẩn chung toàn repo tại `docs/FLOW_STORAGE_STANDARD.md` và registry tại `ops/flow-control/registry.json`.

---

# VBTH source-specific post-crawl pipeline

VBTH giữ **TiênVuc là nguồn prose duy nhất**. Nguồn Trung chỉ dùng làm mục lục/boundary reference để khôi phục cấu trúc chương gốc; không lấy prose Trung để dịch lại.

## Data layers

1. `raw/` — artifact Runner3 (`page.txt` + metadata), bất biến.
2. `clean/` — tách body TiênVuc, bỏ navigation/boilerplate, chuẩn hóa alias đã biết.
3. `editor_packets/` — mỗi packet gồm 1 phần nguồn + đúng phần Story Bible liên quan.
4. `edited/` — bản Việt đã biên tập, kiểm hash đầu vào + glossary.
5. `merged/` — ghép/split TiênVuc theo `chapter_map` explicit ở mức **segment**, vì ranh giới chương gốc có thể nằm giữa một part TiênVuc.
6. `qa.json` — kiểm consistency và rác nguồn.
7. `book.epub` — EPUB3.

Các thư mục local trên là workspace tạm của runner; canonical machine copy tương ứng phải nằm dưới `ebooks/vbth/` trên R2.

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

## VBTH source commands

```bash
python story_pipeline/pipeline.py clean  --input raw --output clean --bible story_pipeline/config/story_bible.json
python story_pipeline/pipeline.py packet --clean clean --output editor_packets --bible story_pipeline/config/story_bible.json
python story_pipeline/pipeline.py apply  --clean clean --edits edits --output edited --bible story_pipeline/config/story_bible.json
python story_pipeline/merge_segments.py  --edited edited --output merged --map story_pipeline/config/chapter_map.001-003.json
python story_pipeline/pipeline.py qa     --chapters merged --bible story_pipeline/config/story_bible.json --output qa.json
python story_pipeline/pipeline.py epub   --chapters merged --output Vuong-Bai-Tien-Hoa.epub
```

## Batch policy

- Khởi đầu 8–20 phần nguồn/batch; batch là scheduling, checkpoint vẫn theo chapter/artifact identity.
- Cập nhật Story Bible sau mỗi batch trước khi biên tập batch kế tiếp.
- Không biên tập hàng nghìn phần độc lập mà thiếu glossary/context chung.
- Chỉ release batch khi edit/apply, merge và QA đều pass.
- Luôn giữ source -> clean -> edited để sửa glossary hàng loạt mà không phải crawl/lấy source lại.
