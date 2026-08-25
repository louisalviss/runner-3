-- Exact six-item RSS Library pilot selected from the 2026-08-24 render manifest.
-- Seed is idempotent and never resets runtime fetch/translation state.

INSERT INTO rss_articles (
  article_id, stable_key, canonical_url, source_key, source_name,
  source_language, item_type, title, published_at, fetch_status,
  translation_status
) VALUES
  (
    'projectsyndicate-url-26a9686e21ebe4fa865d',
    'projectsyndicate:url:26a9686e21ebe4fa865d',
    'https://www.project-syndicate.org/commentary/robust-aggregate-indicators-conceal-widening-economic-divide-by-kaushik-basu-2026-08',
    'projectsyndicate', 'Project Syndicate', 'en', 'article',
    'The Age of Gated Recessions', '2026-08-24T14:44:01Z', 'pending', 'pending'
  ),
  (
    'projectsyndicate-url-db223b141f372578df3c',
    'projectsyndicate:url:db223b141f372578df3c',
    'https://www.project-syndicate.org/commentary/society-based-on-ai-could-make-citizens-and-democracy-redundant-by-stephen-holmes-2026-08',
    'projectsyndicate', 'Project Syndicate', 'en', 'article',
    'The AI Curse', '2026-08-24T13:56:15Z', 'pending', 'pending'
  ),
  (
    'genk-165260824141950644',
    'genk:id:165260824141950644',
    'https://genk.vn/vi-sao-teamviewer-chon-dung-thoi-diem-de-dat-cuoc-vao-thi-truong-viet-nam-165260824141950644.chn',
    'genk', 'GenK', 'vi', 'article',
    'Vì sao TeamViewer chọn đúng thời điểm để đặt cược vào thị trường Việt Nam?',
    '2026-08-24T10:10:00Z', 'pending', 'native_vi'
  ),
  (
    'fulcrum-url-a87e54dbda2e37fe40a7',
    'fulcrum:url:a87e54dbda2e37fe40a7',
    'https://fulcrum.sg/the-45-minute-standard-making-southeast-asias-industrial-parks-efficient-and-liveable/',
    'fulcrum', 'Fulcrum', 'en', 'article',
    'The 45-Minute Standard: Making Southeast Asia’s Industrial Parks Efficient and Liveable',
    '2026-08-24T06:00:00Z', 'pending', 'pending'
  ),
  (
    'tinhte-4171630',
    'tinhte:id:4171630',
    'https://tinhte.vn/thread/hoverair-versa-camera-bo-tui-biet-bay-duong-nhu-da-bi-cam-ban-tai-my.4171630/',
    'tinhte', 'Tinhte', 'vi', 'article',
    'HoverAir Versa – “camera bỏ túi biết bay” – dường như đã bị cấm bán tại Mỹ',
    '2026-08-24T05:58:03Z', 'pending', 'native_vi'
  ),
  (
    'nghiencuuquocte-url-6cd04807aefc80d9be93',
    'nghiencuuquocte:url:6cd04807aefc80d9be93',
    'https://nghiencuuquocte.org/2026/08/24/cai-cach-thi-truong-von-va-co-che-thoai-von-ma-viet-nam-con-thieu/',
    'nghiencuuquocte', 'Nghiên cứu Quốc tế', 'vi', 'article',
    'Cải cách thị trường vốn và cơ chế thoái vốn mà Việt Nam còn thiếu',
    '2026-08-23T22:45:42Z', 'pending', 'native_vi'
  )
ON CONFLICT(canonical_url) DO UPDATE SET
  stable_key = excluded.stable_key,
  source_key = excluded.source_key,
  source_name = excluded.source_name,
  source_language = excluded.source_language,
  item_type = excluded.item_type,
  title = excluded.title,
  published_at = excluded.published_at,
  updated_at = CURRENT_TIMESTAMP;
