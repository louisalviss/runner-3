import sqlite3
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
NEW_JOIN = "FROM content_features f\n    JOIN item_signal sig ON sig.item_id=f.item_id AND sig.signal<>0"
OLD_JOIN = "FROM content_features f"


class ProfileSignalPruneTest(unittest.TestCase):
    def test_profile_weights_match_unpruned_projection(self):
        result = subprocess.run(
            ['node', '--input-type=module', '-e',
             "import {profileProjectionCte} from './cloudflare/runner3-core/src/content-personalization.js'; process.stdout.write(profileProjectionCte());"],
            cwd=ROOT, capture_output=True, text=True, check=True, timeout=10)
        optimized = result.stdout
        self.assertEqual(optimized.count(NEW_JOIN), 1)
        legacy = optimized.replace(NEW_JOIN, OLD_JOIN)
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.executescript('''
          CREATE TABLE user_content_events(item_id TEXT,event_type TEXT,event_at TEXT);
          CREATE TABLE content_features(item_id TEXT,feature_type TEXT,feature_key TEXT,weight REAL,confidence REAL);
        ''')
        events = [
            ('engaged1','liked','2026-11-11 09:00:00'),
            ('engaged1','follow_up','2026-11-11 09:01:00'),
            ('engaged2','interest_saved','2026-11-10 12:00:00'),
            ('engaged3','disliked','2026-11-09 12:00:00'),
            ('engaged4','selected','2026-11-08 11:00:00'),
        ]
        for i in range(150):
            events.append(('shown'+str(i),'shown','2026-11-11 09:00:00'))
        conn.executemany('INSERT INTO user_content_events VALUES (?,?,?)',events)
        features = [
            (item,typ,key,0.7+(idx%3)*0.1,0.85)
            for idx,item in enumerate(['engaged1','engaged2','engaged3','engaged4']+
                                      ['shown'+str(i) for i in range(150)])
            for typ,key in [('topic','momentum'),('concept','breakout'),
                            ('mechanism','trend-following')]
        ]
        conn.executemany('INSERT INTO content_features VALUES (?,?,?,?,?)',features)
        conn.commit()
        for selection in ('SELECT * FROM leaf_projected ORDER BY feature_type,feature_key',
                          'SELECT * FROM family_scored ORDER BY feature_type,feature_key'):
            before = conn.execute(legacy+'\n'+selection).fetchall()
            after = conn.execute(optimized+'\n'+selection).fetchall()
            self.assertEqual(before, after)
            if "leaf_projected" in selection:
                self.assertGreater(len(after),0)


if __name__ == '__main__':
    unittest.main()
