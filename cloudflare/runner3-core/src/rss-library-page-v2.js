const LIBRARY_UX_CSS = `<style id="rss-library-ux-v2">
.sheetback{background:#000b;backdrop-filter:blur(7px);-webkit-backdrop-filter:blur(7px)}
.sheet{max-height:min(82dvh,720px);background:#121212;border-color:#2d2d2d;border-radius:24px 24px 0 0;padding:12px 14px calc(22px + env(safe-area-inset-bottom));overscroll-behavior:contain}
.sheethead{position:sticky;top:-12px;z-index:2;margin:0 -2px;padding:6px 2px 10px;background:#121212ee;backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border-bottom:1px solid #202020}
.sheethead h2{font-size:21px;letter-spacing:-.02em}
.sheet .setting{margin-top:14px}
.sheet .setting:first-of-type{display:grid;grid-template-columns:minmax(0,1fr) 112px;align-items:center;gap:12px;margin-top:8px;padding:10px 0 14px;border-bottom:1px solid #242424}
.sheet .setting:first-of-type h3{margin:0;font-size:15px;font-weight:600}
.sheet .setting:first-of-type select{width:112px;height:38px}
.sheet .setting:nth-of-type(2)>h3{font-size:15px;margin:0 0 4px;font-weight:600}
.sheet .hint{margin:0 0 10px;font-size:12px;line-height:1.45;color:#8e8e96}
.category-editor-toggle{width:100%;height:42px;border:1px solid #303030;border-radius:12px;background:#181818;color:#eee;display:flex;align-items:center;justify-content:center;font-weight:600;margin-bottom:9px}
.catcreate{display:none!important;grid-template-columns:minmax(0,1fr) 42px;gap:7px;margin:0 0 10px;padding:10px;border:1px solid #292929;border-radius:14px;background:#0d0d0d}
.catcreate.open{display:grid!important}
.catcreate .keywords{grid-column:1/-1}
.catcreate textarea.keywords{width:100%;height:76px;min-height:76px;border:1px solid #303030;border-radius:10px;background:#101010;color:#eee;padding:9px 10px;resize:none;line-height:1.35;font:inherit;outline:none}
.catlist{gap:6px;margin-top:0}
.catitem{grid-template-columns:minmax(0,1fr) 38px;gap:7px;min-height:54px;padding:8px 9px;border-radius:13px;transition:border-color .16s,background .16s}
.catitem>div{min-width:0}
.catitem>div>div{font-size:16px;line-height:1.2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.catitem small{display:none}
.catitem .iconbtn{width:36px;height:36px;border-radius:10px}
.catitem .catdelete{display:none;width:36px;height:36px;align-items:center;justify-content:center}
.catitem.editing{grid-template-columns:minmax(0,1fr) 38px 38px;border-color:#4a4a4a;background:#171717}
.catitem.editing .catdelete{display:inline-flex}
.catitem.editing>span:last-child{display:none}
@media(max-width:430px){.sheet{padding-left:12px;padding-right:12px}.sheet .setting:first-of-type{grid-template-columns:minmax(0,1fr) 104px}.sheet .setting:first-of-type select{width:104px}.catitem{min-height:52px}}
</style>`;

const LIBRARY_UX_SCRIPT = `<script id="rss-library-ux-v2-script">
(function(){
  var sheet=document.querySelector('.sheet');
  var create=document.querySelector('.catcreate');
  var list=document.querySelector('#catList');
  var settings=document.querySelector('#settings');
  if(!sheet||!create||!list||!settings)return;

  var heading=sheet.querySelector('.sheethead h2');
  if(heading)heading.textContent='Cài đặt';
  var sectionTitle=sheet.querySelector('.setting:nth-of-type(2)>h3');
  if(sectionTitle)sectionTitle.textContent='Phân loại';
  var hint=sheet.querySelector('.hint');
  if(hint)hint.textContent='Tự phân loại theo từ khoá. Chạm nút sửa ở một mục để xem hoặc chỉnh chi tiết.';

  var oldKeywords=document.querySelector('#newKeywords');
  if(oldKeywords&&oldKeywords.tagName!=='TEXTAREA'){
    var textarea=document.createElement('textarea');
    textarea.id='newKeywords';
    textarea.className='keywords';
    textarea.placeholder='Từ khoá tự phân loại, cách nhau bằng dấu phẩy';
    textarea.value=oldKeywords.value||'';
    oldKeywords.replaceWith(textarea);
  }

  var toggle=document.createElement('button');
  toggle.type='button';
  toggle.className='category-editor-toggle';
  toggle.textContent='Thêm phân loại';
  create.parentNode.insertBefore(toggle,create);

  function clearEditingRows(){
    var rows=list.querySelectorAll('.catitem.editing');
    for(var i=0;i<rows.length;i++)rows[i].classList.remove('editing');
  }
  function closeEditor(clearFields){
    create.classList.remove('open');
    clearEditingRows();
    toggle.textContent='Thêm phân loại';
    if(clearFields){
      var name=document.querySelector('#newCat');
      var keywords=document.querySelector('#newKeywords');
      if(name)name.value='';
      if(keywords)keywords.value='';
    }
  }
  function openEditor(row){
    clearEditingRows();
    if(row)row.classList.add('editing');
    create.classList.add('open');
    toggle.textContent=row?'Đóng chỉnh sửa':'Đóng';
  }

  toggle.addEventListener('click',function(){
    if(create.classList.contains('open'))closeEditor(true);
    else openEditor(null);
  });

  list.addEventListener('click',function(event){
    var edit=event.target.closest('.catitem .iconbtn');
    if(!edit)return;
    var row=edit.closest('.catitem');
    openEditor(row);
  });

  settings.addEventListener('click',function(){
    closeEditor(true);
  });
  var close=document.querySelector('#closeSheet');
  if(close)close.addEventListener('click',function(){closeEditor(true)});
  var back=document.querySelector('#sheetback');
  if(back)back.addEventListener('click',function(event){if(event.target===back)closeEditor(true)});

  var save=document.querySelector('#saveCat');
  if(save)save.addEventListener('click',function(){
    setTimeout(function(){
      var name=document.querySelector('#newCat');
      if(name&&!name.value.trim())closeEditor(false);
    },250);
  });
})();
</script>`;

function injectBefore(html, marker, value) {
  const index = html.lastIndexOf(marker);
  if (index < 0) return html;
  return html.slice(0, index) + value + html.slice(index);
}

export async function polishRssLibraryResponse(response, request, url) {
  if (!response || request.method !== "GET" || url.pathname !== "/rss/library") return response;
  const contentType = response.headers.get("content-type") || "";
  if (!contentType.includes("text/html")) return response;
  let html = await response.text();
  if (!html.includes('id="rss-library-ux-v2"')) {
    html = injectBefore(html, "</head>", LIBRARY_UX_CSS);
    html = injectBefore(html, "</body>", LIBRARY_UX_SCRIPT);
  }
  const headers = new Headers(response.headers);
  headers.delete("content-length");
  headers.set("cache-control", "no-store");
  headers.set("content-type", "text/html; charset=utf-8");
  return new Response(html, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}
