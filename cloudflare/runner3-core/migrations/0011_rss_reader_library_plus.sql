CREATE TABLE IF NOT EXISTS rss_reader_categories (
  name TEXT PRIMARY KEY,
  keywords TEXT,
  sort_order INTEGER NOT NULL DEFAULT 100,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO rss_reader_categories (name, keywords, sort_order) VALUES
  ('AI', 'ai,artificial intelligence,llm,chatgpt,openai,anthropic,gemini,model,neural,robotics,robot', 10),
  ('Tech', 'technology,tech,software,hardware,apple,iphone,android,cloudflare,chip,semiconductor,security,browser,startup,app,device', 20),
  ('Kinh tế', 'kinh tế,economy,economic,finance,financial,market,bond,debt,inflation,interest rate,rates,gdp,trade,business,investment,stock,capital', 30),
  ('Chính trị', 'chính trị,politics,political,government,election,president,parliament,party,geopolitics,diplomacy,war,policy,state,regulation', 40),
  ('Khoa học', 'khoa học,science,research,study,biology,physics,space,evolution,medicine,climate,astronomy,cognition', 50),
  ('Khác', '', 999);

DELETE FROM rss_reader_categories WHERE name IN ('Trading', 'WordPress');

UPDATE rss_reader_state
SET category = NULL,
    updated_at = CURRENT_TIMESTAMP
WHERE category IN ('Trading', 'WordPress');
