import unittest
from product_keyword_gate import detect_profile, product_keyword_candidates

def raw(*rows):
    return {'rows':[{'phrase':a,'url':b,'volume':v,'traffic':t,'keywordDifficulty':22} for a,b,v,t in rows]}

class ProductKeywordGateTests(unittest.TestCase):
    def test_no_profile(self):
        self.assertEqual(product_keyword_candidates('flycid.com',raw(('eastern iowa airport','https://flycid.com',18000,50)),{'title':'Eastern Iowa Airport','description':'flights'}),[])

    def test_kpi_is_not_cmms(self):
        context={'title':'Field Service Management & CMMS Software','description':'Field maintenance and work order software'}
        q=product_keyword_candidates('fieldex.com',raw(
            ('define kpi key performance indicators','https://fieldex.com/blog/kpi',4400,7),
            ('work order generator','https://fieldex.com/en/work-order-generator',110,3),
            ('work order template','https://fieldex.com/en/blog/template',2400,1)),context)
        self.assertEqual({x['keyword'] for x in q},{'work order generator','work order template'})

    def test_civic_news_is_not_data(self):
        context={'title':'Legis1 | Congressional Intelligence, Lobbying Data & Witness Database'}
        q=product_keyword_candidates('legis1.com',raw(
            ('k-12 education news','https://legis1.com/news/k12',8100,7),
            ('lobby groups list','https://legis1.com/rankings',390,13),
            ('list of lobbyist groups','https://legis1.com/rankings',390,10),
            ('congressional witness database','https://legis1.com/witnesses',90,2)),context)
        self.assertEqual({x['keyword'] for x in q},{'lobby groups list','congressional witness database'})

    def test_api_not_inside_capitalization(self):
        context={'title':'Invent AI Customer Service','description':'WhatsApp automation chatbot'}
        q=product_keyword_candidates('useinvent.com',raw(
            ('whatsapp official capitalization brand name','https://useinvent.com/blog/brand',480,1),
            ('whatsapp business automation tools','https://useinvent.com/blog/automation',480,11),
            ('best ai customer journey automation platform','https://useinvent.com/blog/customer-journey',80,2)),context)
        self.assertEqual([x['keyword'] for x in q],['whatsapp business automation tools'])

    def test_meeting_software_but_not_best_ai_tools(self):
        context={'title':'AI Meeting Assistant: Transcription & Tasks'}
        q=product_keyword_candidates('sally.io',raw(
            ('best ai tools','https://sally.io/blog/ai',16000,20),
            ('meeting minutes software','https://sally.io/blog/meeting-minutes',1000,1)),context)
        self.assertEqual([x['keyword'] for x in q],['meeting minutes software'])

    def test_generator_is_not_automatically_software(self):
        context={'title':'Field Service Management & CMMS Software','description':'maintenance and work order software'}
        q=product_keyword_candidates('fieldex.com',raw(
            ('commercial generator maintenance checklist','https://fieldex.com/checklist/genset',210,1),
            ('work order generator','https://fieldex.com/en/work-order-generator',110,3)),context)
        self.assertEqual(q[0]['keyword'],'work order generator')

    def test_meeting_software_without_assistant_intent(self):
        context={'title':'AI Meeting Assistant: Transcription & Tasks'}
        q=product_keyword_candidates('sally.io',raw(
            ('1:1 meeting software performance conversations employee engagement','https://sally.io/blog/performance',40,0),
            ('meeting minutes software','https://sally.io/blog/meeting-minutes',1000,1)),context)
        self.assertEqual([x['keyword'] for x in q],['meeting minutes software'])

    def test_generic_product_fallback(self):
        context={'title':'PDF Compressor - Free Online File Tools','description':'Compress PDF documents into smaller files'}
        q=product_keyword_candidates('tinyfile.app',raw(
            ('pdf compressor','https://tinyfile.app/compress-pdf',1900,3),
            ('celebrity lifestyle news','https://tinyfile.app/blog/news',10000,40)),context)
        self.assertEqual([x['keyword'] for x in q],['pdf compressor'])
        self.assertEqual(q[0]['profile'],'generic_product')

    def test_hardware_and_airport_do_not_inherit_utility_fallback(self):
        self.assertIsNone(detect_profile({'title':'FPGA Embedded Boards','description':'Hardware vendor offering embedded automation boards'}))
        self.assertIsNone(detect_profile({'title':'Eastern Iowa Airport','description':'Flights and airlines from Cedar Rapids'}))

    def test_generic_utility_requires_subject_anchor(self):
        context={'title':'Invoice Generator','description':'Create invoices for freelancers using online tools'}
        q=product_keyword_candidates('billpilot.app',raw(
            ('best marketing automation software','https://billpilot.app/marketing',8000,22),
            ('invoice generator','https://billpilot.app/invoice',1900,5)),context)
        self.assertEqual([x['keyword'] for x in q],['invoice generator'])

if __name__=='__main__':unittest.main()
