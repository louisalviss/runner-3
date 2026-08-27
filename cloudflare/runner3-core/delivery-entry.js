import app from "./mailbox-entry.js";
import { handleDelivery } from "./src/delivery.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const deliveryResponse = await handleDelivery(request, env, url);
    if (deliveryResponse) return deliveryResponse;
    return app.fetch(request, env, ctx);
  },
  async scheduled(event, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(event, env, ctx);
  },
};
