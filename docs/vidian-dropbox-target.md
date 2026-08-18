# Vidian Dropbox target

Preferred durable storage root: `/Vidian-Corpus`.

Suggested placement for canonical v2 assets:

- `/Vidian-Corpus/90_Raw/vidian-semantic-corpus-v2-full.zip`
- `/Vidian-Corpus/99_Processed/vidian_fts.sqlite`
- `/Vidian-Corpus/00_Index/vidian_canonical_v2.json`

The binary ZIP and SQLite index should be uploaded with a byte-preserving upload path. The ChatGPT Dropbox connector's text `create_file` action is not suitable for these binary artifacts.
