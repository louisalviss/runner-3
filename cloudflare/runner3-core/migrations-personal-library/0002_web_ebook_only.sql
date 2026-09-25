-- Web Personal Library is ebook-only. Comic authority remains Telegram/local.
DELETE FROM library_file_index_v1
WHERE category IS NULL OR LOWER(category) <> 'ebook';
