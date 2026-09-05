import app from "./audio-entry.js";
import { handleMailboxFast } from "./mailbox-fast-entry.js";

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const mailboxResponse = await handleMailboxFast(request, env, url);
    if (mailboxResponse) return mailboxResponse;
    return app.fetch(request, env, ctx);
  },
  async scheduled(controller, env, ctx) {
    if (typeof app.scheduled === "function") return app.scheduled(controller, env, ctx);
  },
};
