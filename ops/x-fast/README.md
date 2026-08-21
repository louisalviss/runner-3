# X Fast direct flow

Primary path: ChatGPT -> `runner3-x-fast-direct` Cloudflare Worker -> FxTwitter API.

Fallback inside Worker: public X HTML snapshot.

Final fallback: existing Runner-3 GitHub Actions `x-fast` flow.

Goal: remove GitHub Actions cold-start from normal X status reads.
