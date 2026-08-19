#!/usr/bin/env python3
import json, os, re, subprocess, sys, html
from pathlib import Path

ROOT = Path(os.environ.get("WORKDIR", "work/reddit-unsolved"))
OUT = Path(os.environ.get("OUTDIR", "artifacts/reddit-unsolved"))
ROOT.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

reddit_path = ROOT / "reddit.json"
if not reddit_path.exists():
    raise SystemExit("reddit.json missing")
raw = json.loads(reddit_path.read_text(encoding="utf-8"))
if not isinstance(raw, list) or len(raw) < 2:
    raise SystemExit("unexpected Reddit payload")

post = raw[0]["data"]["children"][0]["data"]
children = raw[1]["data"]["children"]
comments=[]
for rank, child in enumerate(children, 1):
    if child.get("kind") != "t1":
        continue
    d=child.get("data") or {}
    body=(d.get("body") or "").strip()
    if not body or d.get("stickied"):
        continue
    comments.append({
        "rank": rank,
        "score": d.get("score"),
        "author": d.get("author"),
        "body": body,
        "permalink": "https://www.reddit.com" + (d.get("permalink") or ""),
        "id": d.get("id")
    })

(OUT / "top-comments.json").write_text(json.dumps({
    "thread_title": post.get("title"),
    "thread_url": "https://www.reddit.com" + (post.get("permalink") or ""),
    "sort": "best",
    "comments": comments[:40]
}, ensure_ascii=False, indent=2), encoding="utf-8")

CASES = [
{
 "key":"fallon", "title":"Cụm bệnh bạch cầu trẻ em ở Fallon, Nevada", "patterns":["fallon", "churchill county", "leukemia cluster"],
 "text":"""Một trong những bình luận đáng sợ nhất nhắc tới Fallon, Nevada, nhưng phần thật sự đáng chú ý không cần thêm thắt âm mưu. Từ năm 1997 đến 2002, mười sáu trẻ em từng sống ở Churchill County được chẩn đoán bệnh bạch cầu cấp. Với quy mô dân số và tỷ lệ ung thư của bang Nevada, số ca dự kiến trong cùng điều kiện là dưới hai. Vì vậy đây là một cụm bệnh bất thường đủ lớn để CDC cùng các cơ quan liên bang, bang và địa phương mở điều tra quy mô lớn.\n\nCác nhóm nghiên cứu lấy mẫu máu, nước tiểu, nước máy, bụi trong nhà và đất; họ xem xét nhiều hướng như arsenic, tungsten, thuốc trừ sâu, các hợp chất hữu cơ bay hơi và những phơi nhiễm môi trường khác. Một số chất có mức phơi nhiễm đáng chú ý, đặc biệt tungsten từng được nghiên cứu thêm. Nhưng kết luận quan trọng là không tìm được mối liên hệ thống kê đủ mạnh giữa một chất ô nhiễm cụ thể và cụm bệnh. CDC sau này dùng Fallon như một ví dụ điển hình cho việc một cancer cluster có thể là thật về mặt thống kê mà nguyên nhân vẫn không xác định được.\n\nĐiều còn bỏ ngỏ vì thế không phải là có cụm bệnh hay không: cụm bệnh đã được xác nhận. Bí ẩn là tại sao nó xảy ra. Các giả thuyết môi trường nghe hấp dẫn, nhưng đến nay không giả thuyết nào được chứng minh là nguyên nhân duy nhất. Đây là trường hợp mà câu trả lời khoa học trung thực nhất vẫn là: chúng ta biết hiện tượng có thật, nhưng chưa biết cơ chế gây ra nó.""",
 "sources":["CDC / Environmental Health Perspectives: Investigating Childhood Leukemia in Churchill County, Nevada", "CDC cancer-cluster guidance and Fallon investigation archive"]
},
{
 "key":"springfield", "title":"The Springfield Three", "patterns":["springfield three", "springfield 3", "stacy mccall", "suzie streeter", "sherrill levitt", "sherill levitt"],
 "text":"""The Springfield Three là vụ biến mất của ba phụ nữ ở Springfield, Missouri. Theo hồ sơ FBI, rạng sáng ngày 7 tháng 6 năm 1992, Suzanne Streeter và bạn là Stacy McCall trở về nhà của mẹ Suzanne, Sherrill Levitt, sau các buổi tiệc tốt nghiệp. Khoảng thời gian mà cả ba biến mất được FBI đặt từ 2 giờ 15 đến 7 giờ 30 sáng. Từ đó đến nay không ai trong ba người được xác nhận là đã xuất hiện trở lại.\n\nĐiểm khiến vụ này gây ám ảnh là không có một chuỗi sự kiện rõ ràng dẫn ra khỏi căn nhà. Ba người trưởng thành và thiếu nữ biến mất trong cùng một khoảng thời gian ngắn, trong khi nơi cuối cùng được xác nhận của họ là chính căn nhà của Sherrill. Qua nhiều năm xuất hiện rất nhiều chi tiết phụ, lời đồn về các cuộc gọi, đồ vật trong nhà, hay các địa điểm được cho là nơi chôn xác. Nhưng những chi tiết không nằm trong hồ sơ chính thức không nên được coi là chứng cứ chỉ vì chúng được lặp lại nhiều trên Internet.\n\nPhần chắc chắn nhất vẫn cực kỳ đơn giản: Suzanne, Stacy và Sherrill ở căn nhà đó trong đêm, và đến buổi sáng họ đã biến mất. FBI vẫn liệt kê cả ba trong hệ thống ViCAP. Không có lời giải chính thức về ai đã đưa họ đi, bằng cách nào, hoặc động cơ là gì. Chính khoảng trống khổng lồ giữa hai mốc thời gian rất gần nhau khiến vụ này tồn tại hơn ba thập kỷ mà vẫn khó giải thích.""",
 "sources":["FBI ViCAP: The Springfield Three — Springfield, Missouri"]
},
{
 "key":"brandon", "title":"Brandon Swanson và cuộc gọi cuối cùng", "patterns":["brandon swanson"],
 "text":"""Brandon Swanson mất tích tại Minnesota vào ngày 14 tháng 5 năm 2008. Hồ sơ hiện vẫn được Minnesota Bureau of Criminal Apprehension liệt kê là một vụ mất tích chưa giải quyết. Đêm đó, sau khi xe bị mắc ở một con đường nông thôn, Brandon gọi cha mẹ tới đón. Anh tin mình đang ở gần Lynd, nhưng dữ liệu vị trí và chiếc xe được tìm thấy sau đó cho thấy anh thực tế ở một khu vực khác, cách nơi anh nghĩ mình đang đứng hàng chục kilomet.\n\nTrong lúc cha mẹ tìm xe, Brandon rời khỏi xe và tiếp tục nói chuyện điện thoại khi đi bộ về phía ánh sáng mà anh cho là một thị trấn. Cuộc gọi kéo dài hàng chục phút. Các bản tường thuật về vụ án ghi lại rằng Brandon đột ngột thốt lên hai từ tiếng Anh tương đương với một phản ứng giật mình, rồi liên lạc chấm dứt. Từ đó anh không gọi lại.\n\nMột giả thuyết tự nhiên là tai nạn địa hình hoặc rơi xuống khu vực sông, vì vùng tìm kiếm có đồng ruộng, đường nước và địa hình khó quan sát. Nhưng nhiều đợt tìm kiếm không tìm được thi thể hay bằng chứng quyết định. Vụ việc còn dẫn tới Brandon's Law năm 2009 ở Minnesota, yêu cầu cơ quan thực thi pháp luật tiếp nhận nhanh báo cáo người mất tích trong hoàn cảnh nguy hiểm.\n\nĐiều chưa biết nằm đúng ở vài giây cuối cuộc gọi: Brandon đã nhìn thấy gì, vấp hay rơi ở đâu, và tại sao một người vẫn đang nói chuyện bình thường với cha mình lại biến mất hoàn toàn ngay sau đó.""",
 "sources":["Minnesota Bureau of Criminal Apprehension unsolved cases database", "Minnesota Department of Public Safety: Brandon's Law background"]
},
{
 "key":"andrew", "title":"Andrew Gosden: chuyến tàu một chiều tới London", "patterns":["andrew gosden"],
 "text":"""Andrew Gosden mới 14 tuổi khi mất tích ngày 14 tháng 9 năm 2007. South Yorkshire Police xác nhận Andrew rời nhà ở Doncaster vào một buổi sáng mà gia đình nghĩ cậu đi học. Thực tế, cậu quay về nhà sau khi người thân đã rời đi, thay quần áo, mang theo một số đồ cá nhân rồi đi tới ga. Sau đó Andrew mua vé tàu tới London. Hình ảnh camera xác nhận cậu xuất hiện tại King's Cross. Đó là dấu vết chắc chắn cuối cùng được công khai.\n\nĐiểm khó hiểu là hành vi trước chuyến đi không tạo ra một động cơ rõ ràng. Andrew có thành tích học tập tốt và lịch sử đi học đều. Cảnh sát nói đã có nhiều báo cáo nhìn thấy cậu trên toàn quốc, nhưng chưa có trường hợp nào được xác nhận đủ để nối thành một hành trình sau King's Cross.\n\nInternet đưa ra đủ giả thuyết: cậu tự bỏ đi, gặp một người quen bí mật, bị dụ dỗ, gặp tai nạn, hoặc trở thành nạn nhân của tội phạm. Không giả thuyết nào được chứng minh. Vì vậy những suy luận về việc Andrew có một mối quan hệ bí mật trên mạng hay đã hẹn gặp ai đó cần được coi là suy đoán, không phải sự thật đã xác nhận.\n\nGần hai thập kỷ sau, South Yorkshire Police vẫn duy trì lời kêu gọi thông tin. Bí ẩn cơ bản không thay đổi: chúng ta biết khá rõ Andrew đã tự đi tới London, nhưng không biết mục đích của chuyến đi và chuyện gì xảy ra sau khi cậu bước ra khỏi King's Cross.""",
 "sources":["South Yorkshire Police: Missing Andrew Gosden", "South Yorkshire Police public appeal portal"]
},
{
 "key":"somosierra", "title":"Juan Pedro Martínez: đứa trẻ biến mất ở Somosierra", "patterns":["somosierra", "juan pedro mart", "juan pedro"],
 "text":"""Ngày 25 tháng 6 năm 1986, một xe bồn chở axit sulfuric gặp tai nạn tại đèo Somosierra ở Tây Ban Nha. Cha và mẹ của Juan Pedro Martínez thiệt mạng. Juan Pedro, khoảng mười tuổi, được gia đình xác nhận là đi cùng cha mẹ, nhưng khi lực lượng cứu hộ và Guardia Civil kiểm tra hiện trường, không tìm thấy cậu. Quần áo và đồ của trẻ em có trong cabin, còn dấu vết cơ thể thì không.\n\nMột trong những giả thuyết đầu tiên là cơ thể có thể đã bị axit phá hủy. Báo El País thời điểm đó ghi nhận các mẫu trong cabin được phân tích và không phát hiện dấu vết người; các phân tích tiếp theo cũng không ủng hộ giả thuyết cơ thể biến mất hoàn toàn vì axit. Khu vực quanh hiện trường được tìm kiếm bằng nhiều lực lượng và phương tiện nhưng không có kết quả. Vài tháng sau, một nhân chứng còn khai rằng có một chiếc xe van dừng lại gần hiện trường sau vụ tai nạn rồi rời đi. Chi tiết đó mở ra khả năng Juan Pedro đã được một người nào đó đưa khỏi hiện trường, nhưng nó không chứng minh được một vụ bắt cóc.\n\nĐến tháng 6 năm 2026, hãng tin EFE đánh dấu tròn bốn mươi năm vụ mất tích và vẫn mô tả trường hợp này là chưa có lời giải. Điều đáng sợ nhất là tai nạn vốn là một sự kiện rất hữu hình: có xe, có nạn nhân, có hiện trường và có lực lượng cứu hộ. Thế nhưng một đứa trẻ được cho là ở trong cabin lại biến mất mà không để lại lời giải chắc chắn.""",
 "sources":["El País contemporary reports, June–October 1986", "EFE: 40 years since the Somosierra child disappearance, 25 June 2026"]
},
{
 "key":"stefanie", "title":"Stefanie Damron: mất tích giữa vùng rừng Maine", "patterns":["stefanie damron", "stephanie damron"],
 "text":"""Stefanie Damron là một trong những vụ mới nhất xuất hiện trong thread. FBI cho biết Stefanie được nhìn thấy lần cuối ngày 23 tháng 9 năm 2024 tại New Sweden, Maine. Sau một cuộc cãi nhau với chị hoặc em gái, cô bé đi ra khỏi nhà và vào khu rừng gần đó. Cha mẹ không có nhà vào thời điểm ấy. Gia đình ban đầu nghĩ Stefanie sẽ quay lại như những lần cô bé đi bộ trong rừng trước đây, nhưng điều đó không xảy ra.\n\nFBI và Maine State Police đã triển khai tìm kiếm trên hàng nghìn acre, dùng chó nghiệp vụ, rà soát video, phỏng vấn nhiều người và theo các đầu mối không chỉ ở Maine mà cả những bang khác và Canada. Một năm sau khi mất tích, FBI vẫn nói chưa có xác nhận nào về nơi Stefanie đang ở. Cơ quan này treo thưởng tới mười lăm nghìn đô la cho thông tin dẫn tới việc tìm thấy cô bé an toàn hoặc truy tố người có liên quan.\n\nCó nhiều bình luận Internet xoáy vào lối sống biệt lập của gia đình và các báo cáo bảo vệ trẻ em trước đó. FBI xác nhận gia đình sống rất off-grid và từng có các báo cáo liên quan tới dịch vụ bảo vệ trẻ em, nhưng bản thân những điều đó không chứng minh ai trong gia đình gây ra vụ mất tích. Gia đình cũng được cảnh sát mô tả là hợp tác với điều tra.\n\nPhần đã biết vì vậy rất hẹp: Stefanie rời nhà vào rừng và không trở về. Phần chưa biết vẫn rất rộng: cô bé gặp tai nạn, tự rời khu vực, hay có người khác can thiệp. Hiện chưa có bằng chứng công khai đủ mạnh để chốt một kịch bản.""",
 "sources":["FBI: Searching for Stefanie Damron", "FBI Boston / Maine State Police reward announcement"]
},
{
 "key":"zodiac", "title":"Zodiac Killer: mật mã giải được, danh tính thì chưa", "patterns":["zodiac killer", "zodiac"],
 "text":"""Zodiac Killer là cái tên quen thuộc nhất trong danh sách này, nhưng có một chi tiết thường bị hiểu sai: giải được một mật mã của Zodiac không đồng nghĩa với giải được danh tính Zodiac. FBI mô tả chuỗi án mạng ở vùng Bay Area cuối thập niên 1960 cùng các thư và mật mã mà kẻ tự xưng Zodiac gửi tới báo chí. Năm nạn nhân bị sát hại được gắn chắc chắn với chuỗi án, và kẻ gửi thư cố tình biến việc truy tìm hắn thành một trò chơi công khai.\n\nMột mật mã dài 340 ký tự từng chống lại việc giải mã suốt hơn nửa thế kỷ cuối cùng được một nhóm nghiên cứu độc lập giải thành công. Nhưng nội dung giải được không cung cấp danh tính có thể kiểm chứng của hung thủ. FBI từ lâu đã nói danh tính Zodiac vẫn là một bí ẩn; đồng thời vụ án mạng ban đầu thuộc thẩm quyền địa phương chứ FBI không phải cơ quan mở điều tra hình sự chính.\n\nQua nhiều thập kỷ, rất nhiều người được tuyên bố là Zodiac trong sách, phim tài liệu và các nhóm điều tra tư nhân. Vấn đề là một tuyên bố không tương đương với kết luận tư pháp. Không có nghi phạm nào được chính thức xác nhận là Zodiac chỉ vì một nhóm tư nhân công bố tên.\n\nVì vậy bí ẩn ngày nay không phải là liệu các lá thư có tồn tại hay một số mật mã có thể được đọc hay không. Những phần đó đã biết. Khoảng trống còn lại là câu hỏi căn bản nhất: ai đứng sau chúng, và tại sao chuỗi tấn công được xác nhận lại dừng lại.""",
 "sources":["FBI archive: The Zodiac Killer", "Oranchak, Blake & Van Eycke: solution of the Z340 cipher"]
},
{
 "key":"bella", "title":"Bella in the Wych Elm", "patterns":["bella in the wych elm", "wych elm"],
 "text":"""Bella in the Wych Elm bắt đầu vào năm 1943 tại Hagley Wood, Worcestershire. Một nhóm thiếu niên phát hiện hộp sọ người bên trong một thân cây rỗng; cảnh sát sau đó tìm thấy thêm bộ xương của một phụ nữ. Về sau xuất hiện graffiti đặt câu hỏi ai đã đưa Bella vào cây wych elm, và cái tên Bella gắn luôn với người phụ nữ chưa rõ danh tính.\n\nQua nhiều năm, vụ việc bị phủ bởi các giả thuyết từ gián điệp thời chiến tới nghi lễ huyền bí. Đây là phần cần thận trọng nhất: những giả thuyết đó nổi tiếng vì chúng kể chuyện rất hay, không phải vì đã được chứng minh. Hồ sơ và vật chứng nguyên thủy của vụ án hiện cũng không còn đầy đủ, khiến việc kiểm tra lại bằng kỹ thuật pháp y hiện đại khó khăn hơn nhiều.\n\nĐiều chắc chắn là một phụ nữ đã chết và thi thể được giấu trong thân cây; danh tính của bà và người chịu trách nhiệm chưa được xác lập công khai. Khi một vụ án cũ mất cả nhân chứng lẫn vật chứng, thời gian không giúp giải quyết bí ẩn mà đôi khi còn khóa nó lại vĩnh viễn. Bella là ví dụ rõ nhất trong danh sách này về một câu chuyện mà lớp truyền thuyết ngày càng dày lên trong khi phần chứng cứ kiểm chứng được ngày càng mỏng đi.""",
 "sources":["Historical police-file reviews and contemporary reporting on the 1943 Hagley Wood case"]
}
]

# Match curated, externally verified cases against actual top-level comments fetched by Runner.
for c in CASES:
    c["reddit_rank"] = None
    c["reddit_score"] = None
    c["reddit_comment_id"] = None
    for cm in comments[:40]:
        body=cm["body"].lower()
        if any(p.lower() in body for p in c["patterns"]):
            c["reddit_rank"] = cm["rank"]
            c["reddit_score"] = cm["score"]
            c["reddit_comment_id"] = cm["id"]
            break
selected=[c for c in CASES if c["reddit_rank"] is not None]
selected.sort(key=lambda x:x["reddit_rank"])
if len(selected) < 5:
    found=", ".join(c["title"] for c in selected)
    raise SystemExit(f"Only {len(selected)} verified target cases found in top 40 Reddit comments: {found}")
# Keep the episode focused even if more matches are present.
selected=selected[:8]

intro=(f"Bạn đang nghe bản tóm lược đã kiểm chứng từ thread AskReddit: {post.get('title','')}. "
       "Runner ba vừa tải trực tiếp các bình luận theo chế độ Best. Tôi chỉ chọn những vụ xuất hiện trong nhóm bình luận nổi bật và có thể đối chiếu với nguồn ngoài Reddit. "
       "Điểm nào là dữ kiện đã xác nhận sẽ được nói như dữ kiện; điểm nào chỉ là giả thuyết sẽ được gọi đúng là giả thuyết. "
       f"Bản này gồm {len(selected)} vụ.")
outro=("Điểm chung của những vụ này là khoảng cách giữa điều chúng ta biết chắc và điều Internet thường kể thêm. "
       "Một bí ẩn hấp dẫn không cần biến lời đồn thành sự thật. Dữ kiện càng ít, việc tách chứng cứ khỏi suy đoán càng quan trọng. "
       "Hết tập. Trình phát sẽ tự nhớ vị trí bạn đã nghe trên thiết bị này.")

segments=[{"key":"intro","title":"Mở đầu","text":intro,"sources":[]}]
segments += selected
segments.append({"key":"outro","title":"Kết","text":outro,"sources":[]})

voice=os.environ.get("VOICE", "vi-VN-NamMinhNeural")
rate=os.environ.get("VOICE_RATE", "+3%")
voice_dir=ROOT/"voice"
voice_dir.mkdir(exist_ok=True)

def run(cmd):
    print("+", " ".join(map(str,cmd)), flush=True)
    subprocess.check_call(cmd)

def duration(path):
    return float(subprocess.check_output([
        "ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",str(path)
    ], text=True).strip())

for i,seg in enumerate(segments):
    p=voice_dir/f"{i:02d}.mp3"
    run(["edge-tts","--voice",voice,"--rate",rate,"--text",seg["text"],"--write-media",str(p)])
    if p.stat().st_size < 2000:
        raise SystemExit(f"TTS output too small for {seg['title']}")
    seg["duration"]=duration(p)

concat=ROOT/"concat.txt"
concat.write_text("".join(f"file '{(voice_dir/f'{i:02d}.mp3').resolve()}'\n" for i in range(len(segments))), encoding="utf-8")
run(["ffmpeg","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",str(concat),
     "-c:a","libmp3lame","-b:a","128k","-ar","44100",str(OUT/"episode.mp3")])

t=0.0
chapters=[]
for seg in segments:
    chapters.append({"key":seg["key"],"title":seg["title"],"start":round(t,3),"duration":round(seg["duration"],3),"sources":seg.get("sources",[])})
    t += seg["duration"]

meta={
 "episode_id":"reddit-creepiest-unsolved-v1",
 "title":"AskReddit: Những bí ẩn chưa giải đáp ám ảnh nhất — bản đã kiểm chứng",
 "reddit_title":post.get("title"),
 "reddit_url":"https://www.reddit.com"+(post.get("permalink") or ""),
 "voice":voice,
 "voice_rate":rate,
 "duration_seconds":round(duration(OUT/"episode.mp3"),3),
 "selected_cases":[{"title":c["title"],"reddit_rank":c["reddit_rank"],"reddit_score":c["reddit_score"],"sources":c["sources"]} for c in selected],
 "chapters":chapters
}
(OUT/"chapters.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")

trans=[]
for seg in segments:
    trans.append(f"# {seg['title']}\n\n{seg['text']}\n")
    if seg.get("sources"):
        trans.append("Nguồn đối chiếu: " + "; ".join(seg["sources"]) + "\n")
(OUT/"transcript.txt").write_text("\n".join(trans),encoding="utf-8")

# Minimal, iPhone/Safari-friendly player with same-browser resume.
chapter_buttons=[]
for ch in chapters:
    if ch["key"] in ("intro","outro"): continue
    mins=int(ch["start"]//60); secs=int(ch["start"]%60)
    chapter_buttons.append(f'<button class="chapter" data-start="{ch["start"]}"><span>{html.escape(ch["title"])}</span><small>{mins:02d}:{secs:02d}</small></button>')

page=f'''<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{html.escape(meta['title'])}</title>
<style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#0d0f12;color:#f3f4f6;font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:760px;margin:auto;padding:28px 18px 60px}}.eyebrow{{color:#9ca3af;font-size:13px;text-transform:uppercase;letter-spacing:.08em}}h1{{font-size:28px;line-height:1.15;margin:8px 0 12px}}.sub{{color:#b8bec8;margin:0 0 22px}}.card{{background:#16191e;border:1px solid #272b33;border-radius:18px;padding:18px;box-shadow:0 12px 40px #0005}}audio{{width:100%;margin:8px 0 12px}}#resume{{font-size:14px;color:#c9ced6;min-height:22px}}.bar{{height:6px;background:#2a2f38;border-radius:99px;overflow:hidden;margin:10px 0 4px}}#fill{{height:100%;width:0;background:#f3f4f6}}.actions{{display:flex;gap:10px;margin-top:12px}}button{{font:inherit;color:inherit;background:#22262e;border:1px solid #343a45;border-radius:12px;padding:10px 12px}}button:active{{transform:scale(.98)}}h2{{font-size:18px;margin:28px 0 10px}}.chapters{{display:grid;gap:8px}}.chapter{{display:flex;justify-content:space-between;text-align:left;width:100%;background:#14171b}}.chapter small{{color:#9ca3af}}.note{{font-size:13px;color:#8f96a3;margin-top:24px}}a{{color:#d5d9df}}
</style></head><body><main>
<div class="eyebrow">Runner-3 · Nam Minh Neural</div><h1>{html.escape(meta['title'])}</h1>
<p class="sub">{len(selected)} case nổi bật trong thread, đối chiếu nguồn ngoài Reddit. Player tự nhớ vị trí nghe trên trình duyệt này.</p>
<section class="card"><audio id="audio" controls preload="metadata" playsinline src="episode.mp3"></audio>
<div id="resume">Đang đọc vị trí đã nghe…</div><div class="bar"><div id="fill"></div></div>
<div class="actions"><button id="back">−15 giây</button><button id="reset">Nghe lại từ đầu</button></div></section>
<h2>Chương</h2><div class="chapters">{''.join(chapter_buttons)}</div>
<p class="note">Nguồn Reddit được Runner tải với sort=best tại thời điểm dựng. Các lời đồn không đủ nguồn đã bị loại khỏi phần kể. <a href="transcript.txt">Transcript</a> · <a href="top-comments.json">Top comments snapshot</a></p>
</main><script>
const a=document.getElementById('audio'), key='runner3:reddit-creepiest-unsolved-v1:position';
const resume=document.getElementById('resume'), fill=document.getElementById('fill'); let restored=false,lastSave=0;
const fmt=s=>{{s=Math.max(0,Math.floor(s||0));return String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')}};
function saved(){{try{{return JSON.parse(localStorage.getItem(key)||'null')}}catch(e){{return null}}}}
function save(force=false){{if(!Number.isFinite(a.currentTime))return;const now=Date.now();if(!force&&now-lastSave<2000)return;lastSave=now;localStorage.setItem(key,JSON.stringify({{t:a.currentTime,at:now}}));}}
function ui(){{if(a.duration>0)fill.style.width=((a.currentTime/a.duration)*100).toFixed(2)+'%';resume.textContent='Đã nghe '+fmt(a.currentTime)+' / '+fmt(a.duration||0);}}
a.addEventListener('loadedmetadata',()=>{{if(restored)return;restored=true;const s=saved();if(s&&s.t>3&&s.t<a.duration-5){{a.currentTime=s.t;resume.textContent='Tiếp tục từ '+fmt(s.t);}}else ui();}});
a.addEventListener('timeupdate',()=>{{save(false);ui();}});a.addEventListener('pause',()=>save(true));
a.addEventListener('ended',()=>{{localStorage.removeItem(key);fill.style.width='100%';resume.textContent='Đã nghe hết.'}});
window.addEventListener('pagehide',()=>save(true));document.addEventListener('visibilitychange',()=>{{if(document.hidden)save(true)}});
document.getElementById('back').onclick=()=>{{a.currentTime=Math.max(0,a.currentTime-15);save(true)}};
document.getElementById('reset').onclick=()=>{{localStorage.removeItem(key);a.currentTime=0;ui();}};
document.querySelectorAll('.chapter').forEach(b=>b.onclick=()=>{{a.currentTime=Number(b.dataset.start||0);a.play();save(true)}});
</script></body></html>'''
(OUT/"index.html").write_text(page,encoding="utf-8")
print(json.dumps({"selected":len(selected),"duration":meta["duration_seconds"],"voice":voice,"cases":[c["title"] for c in selected]},ensure_ascii=False))
