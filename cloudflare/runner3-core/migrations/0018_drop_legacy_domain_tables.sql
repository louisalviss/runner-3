-- Domain isolation cleanup: dedicated D1s are canonical for RSS, Content Intelligence,
-- Opportunity Radar and Personal Library/Ebook. runner3-core remains control-plane only.
-- Backups verified before applying this migration.

DROP TABLE IF EXISTS rss_articles_fts;
DROP TABLE IF EXISTS rss_translations;
DROP TABLE IF EXISTS rss_processing_events;
DROP TABLE IF EXISTS rss_preference_events;
DROP TABLE IF EXISTS rss_reader_state;
DROP TABLE IF EXISTS rss_article_versions;
DROP TABLE IF EXISTS rss_articles;
DROP TABLE IF EXISTS rss_reader_categories;

DROP TABLE IF EXISTS content_features;
DROP TABLE IF EXISTS content_scores;
DROP TABLE IF EXISTS user_content_events;
DROP TABLE IF EXISTS personal_score_stage;
DROP TABLE IF EXISTS recommendation_runs;
DROP TABLE IF EXISTS interest_family_profile;
DROP TABLE IF EXISTS interest_profile;
DROP TABLE IF EXISTS content_items;

DROP TABLE IF EXISTS opportunity_candidate_regime_state;
DROP TABLE IF EXISTS opportunity_regime_history;
DROP TABLE IF EXISTS opportunity_regime_current;

DROP TABLE IF EXISTS ebook_reader_progress_v65;
DROP TABLE IF EXISTS ebook_reader_state_v72;
DROP TABLE IF EXISTS ebook_reader_trace_v113;
DROP TABLE IF EXISTS library_file_index_v1;
DROP TABLE IF EXISTS library_index_meta_v1;
