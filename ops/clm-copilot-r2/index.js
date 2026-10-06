var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// src/index.mjs
var json = /* @__PURE__ */ __name((data, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    "access-control-allow-origin": "*",
    "access-control-allow-headers": "content-type",
    "access-control-allow-methods": "POST, OPTIONS"
  }
}), "json");
function bestChoice(answer, fallback) {
  if (!answer || typeof answer !== "object") return { value: fallback, confidence: 0 };
  const direct = answer.choice;
  const probs = answer.probabilities || answer.probs || answer.scores || {};
  if (typeof direct === "string") {
    const p2 = Number(probs[direct] ?? answer.confidence ?? 0);
    return { value: direct, confidence: Number.isFinite(p2) ? p2 : 0 };
  }
  let best = fallback, p = -1;
  for (const [k, v] of Object.entries(probs)) {
    const n = Number(v);
    if (Number.isFinite(n) && n > p) {
      best = k;
      p = n;
    }
  }
  return { value: best, confidence: p < 0 ? 0 : p };
}
__name(bestChoice, "bestChoice");
function adviceFor(mechanism, problemLayer, conversationLayer, escalation) {
  if (mechanism === "trust_injury") return {
    severity: escalation === "high" ? "red" : "yellow",
    title: "Trust issue \u0111ang chi ph\u1ED1i",
    advice: "\u0110\u1EEBng tranh lan sang \u0111\xFAng/sai ho\u1EB7c quy\u1EC1n ri\xEAng t\u01B0. X\u1EED l\xFD vi\u1EC7c kh\xF4i ph\u1EE5c trust tr\u01B0\u1EDBc."
  };
  if (mechanism === "cooperation") return {
    severity: "red",
    title: "Hi\u1EC3u nh\u01B0ng kh\xF4ng h\u1EE3p t\xE1c",
    advice: "\u0110\u1EEBng gi\u1EA3i th\xEDch th\xEAm. Chuy\u1EC3n sang boundary, tr\xE1ch nhi\u1EC7m c\u1EE5 th\u1EC3 v\xE0 h\u1EC7 qu\u1EA3 c\u1EE7a vi\u1EC7c kh\xF4ng th\u1EF1c hi\u1EC7n."
  };
  if (mechanism === "emotional_regression" || conversationLayer === "T1") return {
    severity: "red",
    title: "\u0110ang tr\u01B0\u1EE3t xu\u1ED1ng T1",
    advice: "Kh\xF4ng ti\u1EBFp t\u1EE5c ch\u1EE9ng minh ai \u0111\xFAng. H\u1EA1 c\u0103ng th\u1EB3ng tr\u01B0\u1EDBc r\u1ED3i h\u1ECFi m\u1ED9t nhu c\u1EA7u ho\u1EB7c s\u1EF1 ki\u1EC7n c\u1EE5 th\u1EC3."
  };
  if (mechanism === "frame_mismatch" && problemLayer === "T4") return {
    severity: "yellow",
    title: "Task \u2260 v\u1EA5n \u0111\u1EC1 th\u1EADt",
    advice: "\u0110\u1EEBng ti\u1EBFp t\u1EE5c \u0111\u1EBFm task. X\xE1c \u0111\u1ECBnh ownership, nhu c\u1EA7u ho\u1EB7c \u0111\u1ECBnh ngh\u0129a kh\xE1c nhau \u0111ang n\u1EB1m b\xEAn d\u01B0\u1EDBi."
  };
  if (mechanism === "interest_conflict") return {
    severity: "yellow",
    title: "C\xF3 xung \u0111\u1ED9t l\u1EE3i \xEDch th\u1EADt",
    advice: "Kh\xF4ng c\u1ED1 gi\u1EA3i th\xEDch \u0111\u1EC3 ng\u01B0\u1EDDi kia 'hi\u1EC3u h\u01A1n'. X\xE1c \u0111\u1ECBnh constraint v\xE0 chuy\u1EC3n sang th\u01B0\u01A1ng l\u01B0\u1EE3ng trade-off."
  };
  if (mechanism === "layer_mismatch") return {
    severity: "yellow",
    title: "\u0110ang x\u1EED l\xFD d\u01B0\u1EDBi t\u1EA7ng c\u1EA7n thi\u1EBFt",
    advice: "Ng\u1EEBng tranh \u1EDF chi ti\u1EBFt b\u1EC1 m\u1EB7t. X\xE1c \u0111\u1ECBnh pattern, c\u01A1 ch\u1EBF ho\u1EB7c ownership m\xE0 v\u1EA5n \u0111\u1EC1 th\u1EF1c s\u1EF1 y\xEAu c\u1EA7u."
  };
  return {
    severity: "green",
    title: "Ch\u01B0a th\u1EA5y conflict r\xF5",
    advice: "Gi\u1EEF cu\u1ED9c n\xF3i chuy\u1EC7n c\u1EE5 th\u1EC3: s\u1EF1 ki\u1EC7n, nhu c\u1EA7u v\xE0 cam k\u1EBFt. Ch\u1EC9 n\xE2ng t\u1EA7ng khi pattern l\u1EB7p l\u1EA1i."
  };
}
__name(adviceFor, "adviceFor");
function maskText(text) {
  return text.replace(/https?:\/\/\S+/gi, "<url>").replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi, "<email>").replace(/(?:\+?\d[\d .()-]{7,}\d)/g, "<phone>").slice(-12e3);
}
__name(maskText, "maskText");
async function saveSample(env, row) {
  try {
    const sample = {
      id: row.id,
      created_at: (/* @__PURE__ */ new Date()).toISOString(),
      source_package: row.sourcePackage,
      masked_text: row.maskedText,
      mechanism: row.mechanism,
      problem_layer: row.problemLayer,
      conversation_layer: row.conversationLayer,
      confidence: row.confidence,
      tier: row.tier,
      helpful: null,
      outcome: null
    };
    await env.DATASET.put("samples/" + row.id + ".json", JSON.stringify(sample), {
      httpMetadata: { contentType: "application/json" }
    });
  } catch {
  }
}
__name(saveSample, "saveSample");
var index_default = {
  async fetch(request, env) {
    if (request.method === "OPTIONS") return json({ ok: true });
    const url = new URL(request.url);
    if (request.method === "GET") {
      return json({
        ok: true,
        service: "clm-conversation-copilot-api",
        model: "@cf/cloudflare/clef-flash",
        dataset: "clm-copilot-v1"
      });
    }
    if (request.method !== "POST") return json({ error: "method_not_allowed" }, 405);
    const rate = await env.RATE_LIMITER.limit({ key: "clm-personal" });
    if (!rate.success) return json({ error: "rate_limited" }, 429);
    let body;
    try {
      body = await request.json();
    } catch {
      return json({ error: "invalid_json" }, 400);
    }
    if (url.pathname === "/feedback") {
      const id = String(body?.analysisId || "");
      if (!id) return json({ error: "analysis_id_required" }, 400);
      const helpful = body?.helpful === true ? 1 : body?.helpful === false ? 0 : null;
      const outcome = typeof body?.outcome === "string" ? body.outcome.slice(0, 80) : null;
      const key = "samples/" + id + ".json";
      const object = await env.DATASET.get(key);
      if (object) {
        const sample = await object.json();
        if (helpful !== null) sample.helpful = helpful;
        if (outcome !== null) sample.outcome = outcome;
        sample.feedback_updated_at = (/* @__PURE__ */ new Date()).toISOString();
        await env.DATASET.put(key, JSON.stringify(sample), {
          httpMetadata: { contentType: "application/json" }
        });
      }
      return json({ ok: true });
    }
    const text = typeof body?.text === "string" ? body.text.trim() : "";
    if (text.length < 2) return json({ error: "text_required" }, 400);
    const sourcePackage = String(body?.sourcePackage || "").slice(0, 200);
    const state = {
      sourcePackage,
      conversation: text.slice(-12e3)
    };
    const questions = {
      mechanism: {
        type: "choice",
        instructions: "What is the dominant mechanism in this interaction? Judge the current conversation only, not the person's fixed personality.",
        criteria: {
          frame_mismatch: "People are using different definitions, assumptions, frames, or meanings.",
          layer_mismatch: "The problem requires a higher abstraction level than the conversation is using.",
          interest_conflict: "The parties have genuinely competing goals, scarce resources, or incompatible constraints.",
          trust_injury: "A breach of trust or unresolved betrayal is central.",
          cooperation: "A person appears to understand the request but is unwilling to cooperate or accept responsibility.",
          emotional_regression: "Attack, defensiveness, shutdown, contempt, or escalating emotion dominates.",
          external_frame: "An outside narrative or framework is being imported and applied to interpret the relationship.",
          unclear: "There is not enough evidence for a stronger classification."
        }
      },
      problem_layer: {
        type: "choice",
        instructions: "What is the lowest cognitive layer sufficient to solve the actual problem?",
        criteria: {
          T1: "Immediate safety, emotion regulation, or reactive state.",
          T2: "A concrete rule, task, role, routine, or commitment is sufficient.",
          T3: "The problem requires reasoning about evidence, assumptions, causes, or alternatives.",
          T4: "The problem requires system ownership, feedback loops, incentives, patterns, or interacting variables.",
          T5: "The problem requires changing the governing frame, objective, or system itself."
        }
      },
      conversation_layer: {
        type: "choice",
        instructions: "At what cognitive layer is the current conversation actually operating?",
        criteria: {
          T1: "Reactive attack, defense, threat, shutdown, or raw emotion.",
          T2: "Rules, roles, norms, concrete tasks, should/must statements.",
          T3: "Reasoning, evidence, challenge of assumptions, cause-and-effect.",
          T4: "System interactions, feedback loops, ownership, incentives, patterns.",
          T5: "Explicitly comparing or replacing frames/objectives/systems."
        }
      },
      escalation: {
        type: "choice",
        instructions: "How likely is this interaction to escalate if the same conversational pattern continues?",
        criteria: {
          low: "Little sign of escalation.",
          medium: "Some defensiveness or repeated mismatch.",
          high: "Attack/defense, contempt, shutdown, threat, or rapid escalation is evident."
        }
      },
      cooperation: {
        type: "choice",
        instructions: "What best describes cooperation in the visible interaction?",
        criteria: {
          willing: "Both appear willing to solve the issue.",
          uncertain: "Not enough evidence.",
          unwilling: "Someone appears to understand but refuses responsibility, compromise, or cooperation."
        }
      },
      ownership_gap: {
        type: "noul",
        instructions: "Is the conflict centrally about one person only executing after reminders while the other still has to notice, remember, plan, assign, or own the whole domain?"
      },
      trust_breach: {
        type: "noul",
        instructions: "Is an actual or strongly alleged breach of trust central to this interaction?"
      },
      unwilling_despite_understanding: {
        type: "noul",
        instructions: "Does someone appear to understand the request or responsibility but explicitly refuse to cooperate or take responsibility?"
      },
      active_regression: {
        type: "noul",
        instructions: "Is the interaction currently dominated by attack, contempt, defensiveness, shutdown, or escalating reactive emotion?"
      }
    };
    try {
      let out = await env.AI.run("@cf/cloudflare/clef-flash", {
        model: "clef-flash",
        state,
        questions
      });
      const flashA = out?.answers || {};
      const flashMechanism = bestChoice(flashA.mechanism, "unclear");
      const flashProblem = bestChoice(flashA.problem_layer, "T3");
      const flashConversation = bestChoice(flashA.conversation_layer, "T2");
      const needsDeep = flashMechanism.confidence < 0.55 || flashProblem.confidence < 0.5 || flashConversation.confidence < 0.5 || flashMechanism.value === "unclear";
      let tier = "clef-flash";
      if (needsDeep) {
        out = await env.AI.run("@cf/cloudflare/clef", {
          model: "clef",
          state,
          questions
        });
        tier = "clef";
      }
      const a = out?.answers || {};
      const mechanism = bestChoice(a.mechanism, "unclear");
      const problem = bestChoice(a.problem_layer, "T3");
      const conversation = bestChoice(a.conversation_layer, "T2");
      const escalation = bestChoice(a.escalation, "medium");
      const coop = bestChoice(a.cooperation, "uncertain");
      const noun = /* @__PURE__ */ __name((x) => Number(x?.noul ?? 0), "noun");
      const ownershipGap = noun(a.ownership_gap);
      const trustBreach = noun(a.trust_breach);
      const unwilling = noun(a.unwilling_despite_understanding);
      const regression = noun(a.active_regression);
      let m = mechanism.value;
      let pLayer = problem.value;
      if (trustBreach >= 0.7) {
        m = "trust_injury";
      } else if (unwilling >= 0.72 || coop.value === "unwilling" && coop.confidence > 0.68) {
        m = "cooperation";
      } else if (ownershipGap >= 0.62) {
        m = "frame_mismatch";
        pLayer = "T4";
      } else if (regression >= 0.74) {
        m = "emotional_regression";
      }
      const ui = adviceFor(m, pLayer, conversation.value, escalation.value);
      const confidence = Math.max(
        mechanism.confidence || 0,
        trustBreach,
        unwilling,
        ownershipGap,
        regression
      );
      const analysisId = crypto.randomUUID();
      await saveSample(env, {
        id: analysisId,
        sourcePackage,
        maskedText: maskText(text),
        mechanism: m,
        problemLayer: pLayer,
        conversationLayer: conversation.value,
        confidence,
        tier
      });
      return json({
        analysisId,
        mechanism: m,
        problemLayer: pLayer,
        conversationLayer: conversation.value,
        severity: ui.severity,
        title: ui.title,
        advice: ui.advice,
        confidence,
        model: out?.model || tier,
        tier
      });
    } catch (e) {
      return json({ error: "clef_failed", message: String(e?.message || e).slice(0, 300) }, 502);
    }
  }
};
export {
  index_default as default
};
//# sourceMappingURL=index.js.map
