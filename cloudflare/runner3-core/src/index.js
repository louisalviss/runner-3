export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return Response.json({
        ok: true,
        service: "runner3-core",
        time: new Date().toISOString()
      });
    }

    if (url.pathname === "/radar/latest") {
      return Response.json({
        status: "placeholder",
        message: "D1 migration layer ready"
      });
    }

    return new Response("Not Found", { status: 404 });
  }
};
