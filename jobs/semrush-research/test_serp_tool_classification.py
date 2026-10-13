import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from serp_dd_live import url_kind,classify_serp,gate

def make(keyword,urls):
    return classify_serp(keyword,[{'position':i+1,'url':url,'domain':url.split('/')[2],'kind':None,'features':[]} for i,url in enumerate(urls)])

class SerpToolV3Tests(unittest.TestCase):
    def test_article_keywords_not_tools(self):
        urls=[
            'https://gowindmill.com/resources/lists/areas-of-improvement-performance-review-examples/',
            'https://breezy.hr/blog/areas-of-improvement',
            'https://hibob.com/blog/performance-review-examples',
            'https://indeed.com/career-advice/career-development/areas-of-improvement',
            'https://reddit.com/r/jobs/comments/foo/bar',
            'https://lattice.com/articles/areas-of-improvement',
            'https://leapsome.com/blog/performance-review-phrases',
            'https://predictivesuccess.com/blog/review-examples/',
            'https://linkedin.com/pulse/areas-improvement-performance-reviews',
            'https://mit.edu/hr/performance/reviews']
        x=make('areas of improvement performance review examples',urls)
        self.assertEqual(x['exact_tool_top10'],0)
        self.assertEqual(gate([x]),'WATCH_INFORMATIONAL_SERP')
    def test_document_not_tool_even_matching_keyword(self):
        self.assertEqual(url_kind('https://dalefoundation.org/upload/courses/charting-symbols.pdf'),'information')
        self.assertEqual(url_kind('https://gechic.com/en/best-free-annotation-software-tools/'),'unknown')
        self.assertEqual(url_kind('https://dcbyte.com/market/about-generator-capacity'),'unknown')
    def test_actual_tools_saturated(self):
        urls=[f'https://tools{i}.com/tools/pdf-converter' for i in range(9)]+['https://reddit.com/r/pdf/comments/x']
        x=make('pdf converter',urls)
        self.assertEqual(x['exact_tool_top10'],9)
        self.assertEqual(gate([x]),'DROP_SERP_SATURATED')
    def test_unknown_is_not_product_pass(self):
        urls=[f'https://site{i}.com/product' for i in range(10)]
        x=make('investment analysis platform',urls)
        self.assertEqual(gate([x]),'WATCH_AMBIGUOUS_SERP')
    def test_low_results_fail_closed(self):
        x=make('rare utility',['https://site.com/tools/converter'])
        self.assertEqual(gate([x]),'BLOCKED_INCOMPLETE_SERP')
    def test_tool_and_info_split(self):
        urls=['https://a.com/tools/ai-review-generator','https://b.com/blog/review-generator',
              'https://c.com/guides/free-generator','https://d.com/resources/tools',
              'https://e.com/calculator','https://f.com/doc.pdf',
              'https://g.com/tools/meeting-helper','https://h.com/app/editor',
              'https://i.com/blog/top-ai-tools','https://j.com/generator']
        x=make('ai review generator',urls)
        self.assertEqual(x['exact_tool_top10'],5)
        self.assertEqual(x['article_top10'],4)
        self.assertEqual(gate([x]),'WATCH_COMPETITION')
if __name__=='__main__':unittest.main()
