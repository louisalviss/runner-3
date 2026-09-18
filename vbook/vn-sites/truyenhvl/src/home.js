function execute(){return Response.success([
{title:"Tất cả",input:"https://truyenhvl.com/truyen",script:"gen.js"},
{title:"Hot",input:"https://truyenhvl.com/truyen?sort=views",script:"gen.js"},
{title:"Hoàn thành",input:"https://truyenhvl.com/truyen?status=completed",script:"gen.js"}
]);}
