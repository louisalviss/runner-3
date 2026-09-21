function execute(){
 return Response.success([
  {title:'Mới cập nhật',input:'https://truyenhub.net/danh-sach/moi-cap-nhat',script:'gen.js'},
  {title:'Truyện mới',input:'https://truyenhub.net/danh-sach/truyen-moi',script:'gen.js'},
  {title:'Truyện hot',input:'https://truyenhub.net/danh-sach/truyen-hot',script:'gen.js'},
  {title:'Hoàn thành',input:'https://truyenhub.net/danh-sach/truyen-full',script:'gen.js'}
 ]);
}
