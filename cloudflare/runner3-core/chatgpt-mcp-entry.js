import app from "./artifact-library-reader-v7-github-audio-entry.js";
import { handleChatGptMcp } from "./src/chatgpt-mcp-oauth.js";

export default {
  ...app,
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const mcpResponse = await handleChatGptMcp(request, env, url);
    if (mcpResponse) return mcpResponse;
    return app.fetch(request, env, ctx);
  }
};