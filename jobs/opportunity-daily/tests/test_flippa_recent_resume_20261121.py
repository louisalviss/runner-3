import ast, json, pathlib, unittest, types, datetime

TARGET = pathlib.Path(__file__).resolve().parents[1] / "flippa-daily-stage-20261013.py"

def bootstrap():
    tree=ast.parse(TARGET.read_text())
    fn=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="do_bootstrap")
    namespace={"RawCDPSkill":None,"PROFILE":"test","STATE":"existing",
               "datetime":datetime.datetime,"timezone":datetime.timezone,
               "random":types.SimpleNamespace(uniform=lambda a,b:0),
               "time":types.SimpleNamespace(sleep=lambda v:None),"json":json}
    exec(compile(ast.Module(body=[fn],type_ignores=[]),str(TARGET),"exec"),namespace)
    return namespace

class FakePage:
    pass

class FakeSkill:
    def __init__(self,*a,**kw): self.page=FakePage()
    def __enter__(self):return self
    def __exit__(self,*e):return False

class RecentResumeTests(unittest.TestCase):
    def state(self):
        return {"first_done":True,"first_ids":["1"],"recent_done":False,
                "recent_ids":[],"recent_rows":{},"pages":[],"errors":[],"status":"PAUSED","next_main_page":1}

    @staticmethod
    def cards(page,count=100):
        return [{"id":str(page*100000+i),"href":"https://flippa.com/"+str(page*100000+i),
                 "heading":"Product","text":"listing"} for i in range(count)]

    def runtime(self,source):
        ns=bootstrap()
        ns["RawCDPSkill"]=FakeSkill
        called=[];writes=[]
        def fetch(p,s,url,*a):
            import re
            i=int(re.search(r"page=(\d+)",url).group(1))
            called.append(i)
            return source(i)
        ns["fetch_cards"]=fetch
        ns["check_stop"]=lambda *a: None
        ns["norm"]=lambda x,first: dict(x)
        ns["atomic"]=lambda path,state: writes.append(json.loads(json.dumps(state)))
        return ns,called,writes

    def test_one_page_budget(self):
        ns,called,writes=self.runtime(lambda i:(200,"NONE",self.cards(i)))
        state=self.state()
        ns["do_bootstrap"](state,1)
        self.assertEqual(called,[1])
        self.assertFalse(state["recent_done"])
        self.assertEqual(len(state["recent_ids"]),100)
        self.assertEqual(len([x for x in state["pages"] if x["lane"]=="recent"]),1)

    def test_resume_without_refetching_prior_pages(self):
        ns,called,writes=self.runtime(lambda i:(200,"NONE",self.cards(i)))
        state=self.state()
        ns["do_bootstrap"](state,2)
        ns["do_bootstrap"](state,3)
        self.assertEqual(called,[1,2,3,4,5])
        self.assertTrue(state["recent_done"])
        self.assertEqual(len(state["recent_ids"]),500)

    def test_200_with_missing_cards_does_not_promote(self):
        ns,called,writes=self.runtime(lambda i:(200,"NONE",self.cards(i,47)))
        state=self.state()
        with self.assertRaisesRegex(RuntimeError,"STOP_RECENT_INCOMPLETE"):
            ns["do_bootstrap"](state,1)
        self.assertEqual(called,[1])
        self.assertFalse(state["recent_done"])
        self.assertEqual(len(state["recent_ids"]),0)
        self.assertEqual(state["errors"][-1]["reason"],"RECENT_100_CARDS_NOT_VERIFIED")

    def test_duplicate_page_across_pages_not_500(self):
        ns,called,writes=self.runtime(lambda i:(200,"NONE",self.cards(1)))
        state=self.state()
        ns["do_bootstrap"](state,5)
        self.assertEqual(called,[1,2,3,4,5])
        self.assertFalse(state["recent_done"])
        self.assertEqual(len(state["recent_ids"]),100)

if __name__=="__main__":unittest.main()
