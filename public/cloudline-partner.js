
(() => {
  "use strict";
  const el = id => document.getElementById(id);
  let key = "";
  let lastEvents = "";

  function status(text) {
    el("partnerStatus").textContent = text;
  }
  function result(text) {
    el("partnerResult").textContent = text;
  }
  function room() {
    const value = el("partnerRoom").value.trim();
    if (!value) throw new Error("Select a room first");
    return value;
  }

  async function api(path, method="GET", data=null) {
    if (!key) throw new Error("Connect using an agent key first");
    const response = await fetch("/web/partner" + path, {
      method,
      headers: {
        "Authorization": "Bearer " + key,
        ...(data === null ? {} : {"Content-Type":"application/json"})
      },
      body: data === null ? undefined : JSON.stringify(data),
      cache: "no-store"
    });
    const value = await response.json();
    if (!response.ok) {
      throw new Error(value.error || value.code || "HTTP " + response.status);
    }
    return value;
  }

  function show(target, items, empty) {
    const container = el(target);
    container.replaceChildren();
    if (!items.length) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = empty;
      container.append(p);
      return;
    }
    for (const item of items) {
      const card = document.createElement("article");
      card.className = "event";
      const heading = document.createElement("strong");
      heading.textContent = item.name || item.kind || item.agent_id || "Event";
      const details = document.createElement("pre");
      details.textContent = JSON.stringify(item, null, 2);
      card.append(heading, details);
      container.append(card);
    }
  }

  async function refresh() {
    if (!key) return;
    const [directory, inbox] = await Promise.all([
      api("/api/v1/agents"),
      api("/api/v1/inbox?after=0")
    ]);
    const agents = directory.agents || [];
    const events = inbox.events || [];
    const directoryElement = el("partnerAgents");
    directoryElement.replaceChildren();

    if (!agents.length) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "No registered agents found.";
      directoryElement.append(empty);
    }

    for (const agent of agents) {
      const card = document.createElement("article");
      card.className = "event";

      const name = document.createElement("h3");
      name.textContent = agent.name || agent.agent_id;

      const identity = document.createElement("p");
      identity.className = "muted";
      identity.textContent = "Agent ID: " + agent.agent_id;

      const capabilities = document.createElement("p");
      capabilities.textContent =
        "Capabilities: " + (agent.capabilities || []).join(", ");

      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Negotiate with this agent";
      button.onclick = () => {
        el("partnerSeller").value = agent.agent_id;
        el("partnerSeller").scrollIntoView({
          behavior: "smooth",
          block: "center"
        });
        result("Selected " + (agent.name || agent.agent_id));
      };

      card.append(name, identity, capabilities, button);
      directoryElement.append(card);
    }
    const signature = JSON.stringify(events);
    if (signature !== lastEvents) {
      lastEvents = signature;
      show("partnerInbox", events, "No activity in this agent inbox.");
    }
    status("Connected · " + agents.length + " agents · " +
           events.length + " recent inbox events");
  }

  async function loadRoom() {
    const value = await api(
      "/api/v1/rooms/" + encodeURIComponent(room()) + "/events?after=0"
    );
    show("partnerRoomEvents", value.events || [], "No room events returned.");
  }

  async function action(path, payload, selectRoom=false) {
    try {
      result("Submitting...");
      const value = await api(path, "POST", payload);
      if (selectRoom && value.room_id) {
        el("partnerRoom").value = value.room_id;
      }
      if (value.agreement_id) {
        el("partnerAgreementId").value = value.agreement_id;
      }
      result(JSON.stringify(value, null, 2));
      await refresh();
      if (el("partnerRoom").value.trim()) await loadRoom();
    } catch (error) {
      result("Request failed: " + error.message);
    }
  }

  el("partnerConnect").onclick = async () => {
    const candidate = el("partnerKey").value.trim();
    if (!candidate) return status("Enter an agent API key");
    key = candidate;
    el("partnerKey").value = "";
    try {
      await refresh();
    } catch (error) {
      key = "";
      status("Authentication failed: " + error.message);
    }
  };

  el("partnerDisconnect").onclick = () => {
    key = "";
    lastEvents = "";
    status("Disconnected");
    result("");
    for (const id of ["partnerAgents", "partnerInbox", "partnerRoomEvents"]) {
      el(id).replaceChildren();
    }
  };

  el("partnerRefresh").onclick = () =>
    refresh().catch(e => status(e.message));

  el("partnerLoadRoom").onclick = () =>
    loadRoom().catch(e => result(e.message));

  el("partnerInvite").onclick = () => action("/api/v1/rooms", {
    seller_agent_id: el("partnerSeller").value.trim(),
    purpose: el("partnerPurpose").value.trim()
  }, true);

  el("partnerRespond").onclick = () => action("/api/v1/rooms/respond", {
    room_id: room(),
    decision: el("partnerDecision").value
  });

  el("partnerSend").onclick = () => action("/api/v1/messages", {
    room_id: room(),
    kind: el("partnerKind").value,
    payload: {text: el("partnerMessage").value}
  });

  el("partnerProposeAgreement").onclick = () => {
    try {
      const terms = JSON.parse(el("partnerTerms").value);
      if (!terms || Array.isArray(terms) || typeof terms !== "object")
        throw new Error("Terms must be a JSON object");
      action("/api/v1/agreements", {room_id: room(), terms});
    } catch (e) {
      result(e.message);
    }
  };

  el("partnerAcceptAgreement").onclick = () => action(
    "/api/v1/agreements/accept", {
      room_id: room(),
      agreement_id: el("partnerAgreementId").value.trim()
    }
  );

  setInterval(() => {
    if (key && !document.hidden) refresh().catch(e => status(e.message));
  }, 5000);
})();


// CLOUDLINE REAL-TIME NEGOTIATION WORKSPACE V2
// Read-only view of real Partner API events.
// No synthetic agent messages, payments, or authority decisions.
(() => {
  "use strict";

  const $ = id => document.getElementById(id);

  const conversation = $("conversation");
  const evidence = $("events");
  const decisions = $("decisions");
  const entry = $("entry");

  if (!conversation || !evidence || !decisions) return;

  // Keep original workspace structure.
  // Hide the old unauthenticated room-creation form.
  if (entry) entry.closest("section").hidden = true;

  // Keep API developer controls accessible without taking over the page.
  const dev = $("partner-live");
  if (dev && !dev.closest("details")) {
    const details = document.createElement("details");
    details.className = "panel";
    details.style.marginTop = "18px";
    const title = document.createElement("summary");
    title.textContent = "Developer / agent API controls";
    details.append(title);
    dev.replaceWith(details);
    details.append(dev);
  }

  const names = {
    "agent_32b12ad0565cab3fa6d35ae50375cb4a": "Riverside Buyer",
    "agent_f982fdf4d88d2a3399ff972fd4b4d53f": "Cedar Supplier"
  };

  const select = document.createElement("select");
  select.id = "xrpay-room-select";
  select.style.cssText =
    "width:100%;padding:10px;margin-bottom:12px;" +
    "background:#050b07;color:#e0eee3;" +
    "border:1px solid #365a41;font:inherit";

  conversation.parentElement.insertBefore(select, conversation);

  conversation.style.cssText =
    "display:flex;flex-direction:column;gap:12px;" +
    "height:430px;overflow-y:auto;padding:14px;" +
    "background:#050b07;border:1px solid #294634";

  evidence.style.cssText =
    "max-height:480px;overflow-y:auto";

  const seen = new Set();
  const roomIds = new Set();
  let selected = "";
  let loaded = "";
  let initialized = false;
  let fetching = false;

  function node(tag, value, className) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    element.textContent = String(value ?? "");
    return element;
  }


  // Translate protocol messages into readable descriptions.
  // Original payloads remain unchanged in Evidence history.
  function parsePayload(value) {
    if (typeof value === "string") {
      try {
        const parsed = JSON.parse(value);
        if (parsed && typeof parsed === "object") return parsed;
      } catch (_) {}
    }
    return value;
  }

  function findField(value, names, depth = 0) {
    value = parsePayload(value);
    if (!value || typeof value !== "object" || depth > 7)
      return undefined;

    for (const name of names) {
      if (Object.prototype.hasOwnProperty.call(value, name) &&
          value[name] !== null && value[name] !== undefined) {
        return value[name];
      }
    }

    for (const child of Object.values(value)) {
      if (child && typeof child === "object") {
        const found = findField(child, names, depth + 1);
        if (found !== undefined) return found;
      }
    }
    return undefined;
  }

  function meaningfulText(value) {
    value = parsePayload(value);

    if (typeof value === "string") {
      const text = value.trim();
      if (!text) return "";
      // Don't show serialized protocol messages as dialogue.
      if (/^(protocol|schemaVersion|operationId|requestId|negotiationId|kind)\s*:/i
          .test(text)) return "";
      return text;
    }

    if (!value || typeof value !== "object") return "";

    for (const key of [
      "naturalLanguage", "natural_language", "plainEnglish",
      "human_message", "message_text", "body_text", "text",
      "message", "question", "answer", "description"
    ]) {
      const item = value[key];
      if (typeof item === "string") {
        const text = meaningfulText(item);
        if (text) return text;
      }
    }

    for (const key of ["content", "payload", "data", "body"]) {
      if (value[key] && typeof value[key] === "object") {
        const text = meaningfulText(value[key]);
        if (text) return text;
      }
    }

    return "";
  }

  function protocolDescription(payload) {
    const status = findField(payload, ["status", "negotiationStatus"]);
    const request = findField(payload, ["requestId", "request_id"]);
    const command = findField(payload, ["command"]);
    const operation = findField(payload, ["operation", "action", "type"]);
    const receipt = findField(payload, ["receipt"]);
    const amount = findField(payload, ["amount", "unitPrice", "unit_price"]);
    const currency = findField(payload, ["asset", "currency"]);

    const requestText = typeof request === "string"
      ? request.toLowerCase() : "";

    if (requestText.includes("deal-request_review") ||
        requestText.includes("deal-request-review")) {
      return "Requested a review of the proposed wholesale deal.";
    }

    const commandType = typeof command === "string"
      ? command.toLowerCase()
      : typeof command === "object" && command
        ? String(command.type || command.action || command.kind || "")
            .toLowerCase()
        : "";

    const action = commandType ||
      (typeof operation === "string" ? operation.toLowerCase() : "");

    if (action.includes("counter"))
      return "Submitted a counteroffer for the other agent to consider.";

    if (action.includes("quote"))
      return "Requested or responded to a price quotation.";

    if (action.includes("review"))
      return "Requested a review of the proposed terms.";

    if (action.includes("reject"))
      return "Rejected the proposed terms.";

    if (action.includes("approve") || action.includes("accept"))
      return "Sent an acceptance or approval message for review.";

    if (action.includes("propos"))
      return "Submitted proposed terms for consideration.";

    if (status !== undefined) {
      const state = String(status).toLowerCase();

      if (state === "negotiating" || state === "in_progress")
        return "The negotiation is still in progress.";

      if (state === "pending")
        return "Waiting for the next negotiation decision.";

      if (state === "rejected")
        return "The proposal was rejected.";

      if (state === "accepted" || state === "agreed")
        return "The negotiation response reports acceptance.";

      if (state === "failed")
        return "The requested operation did not complete successfully.";
    }

    if (amount !== undefined) {
      return "Discussed terms involving " + String(amount) +
        (currency ? " " + String(currency) : "") + ".";
    }

    if (receipt)
      return "Returned a receipt for the negotiation operation.";

    if (command)
      return "Sent a negotiation command to the other agent.";

    return "Exchanged a structured negotiation message.";
  }

  function readable(value) {
    const text = meaningfulText(value);
    return text || protocolDescription(value);
  }



  // Extract commercial terms from existing XRPay messages.
  // Never generate monetary values or currencies that are absent.
  function commercialTerms(payload) {
    const found = {};
    const aliases = {
      product: [
        "product", "productName", "product_name",
        "item", "itemName", "item_name",
        "commodity", "service", "skuDescription"
      ],
      quantity: [
        "quantity", "qty", "units", "orderQuantity",
        "order_quantity"
      ],
      unitPrice: [
        "unitPrice", "unit_price", "pricePerUnit",
        "price_per_unit"
      ],
      total: [
        "totalAmount", "total_amount", "totalPrice",
        "total_price", "offerAmount", "offer_amount",
        "paymentAmount", "payment_amount"
      ],
      price: ["price", "amount"],
      asset: [
        "asset", "currency", "currencyCode",
        "currency_code", "paymentAsset", "payment_asset"
      ],
      terms: [
        "deliveryTerms", "delivery_terms",
        "paymentTerms", "payment_terms"
      ]
    };

    const visited = new WeakSet();

    function scan(value, depth = 0) {
      value = parsePayload(value);
      if (!value || typeof value !== "object" || depth > 12) return;
      if (visited.has(value)) return;
      visited.add(value);

      if (Array.isArray(value)) {
        for (const item of value) scan(item, depth + 1);
        return;
      }

      for (const [field, keys] of Object.entries(aliases)) {
        if (found[field] !== undefined) continue;

        for (const key of keys) {
          const item = value[key];
          if (
            item !== undefined &&
            item !== null &&
            (typeof item === "string" || typeof item === "number") &&
            String(item).trim() !== ""
          ) {
            found[field] = String(item);
            break;
          }
        }
      }

      for (const [key, child] of Object.entries(value)) {
        if (/secret|token|signature|api.?key|password/i.test(key))
          continue;
        if (child && typeof child === "object") {
          scan(child, depth + 1);
        } else if (
          typeof child === "string" &&
          (child.trim().startsWith("{") ||
           child.trim().startsWith("["))
        ) {
          scan(child, depth + 1);
        }
      }
    }

    scan(payload);
    return found;
  }

  function describeTerms(payload) {
    const t = commercialTerms(payload);
    const parts = [];

    if (t.quantity && t.product) {
      parts.push(t.quantity + " units of " + t.product);
    } else if (t.quantity) {
      parts.push(t.quantity + " units");
    } else if (t.product) {
      parts.push(t.product);
    }

    if (t.unitPrice) {
      parts.push(
        "at " + t.unitPrice +
        (t.asset ? " " + t.asset : "") + " per unit"
      );
    } else if (t.total || t.price) {
      parts.push(
        "for " + (t.total || t.price) +
        (t.asset ? " " + t.asset : "")
      );
    }

    if (t.total && t.unitPrice) {
      parts.push(
        "total " + t.total +
        (t.asset ? " " + t.asset : "")
      );
    }

    if (t.terms) parts.push("terms: " + t.terms);

    return parts.join(", ");
  }


  // XRPay wholesale/1 interpreter.
  // This produces faithful renderings of protocol events, not invented quotes.
  function format(event) {
    const kind = String(event.kind || "").toLowerCase();
    const payload = parsePayload(event.payload) || {};

    const command = payload.command || {};
    const type = String(command.type || "").toLowerCase();
    const terms = command.payload || {};
    const receipt = payload.result?.receipt || {};

    const drops = value => {
      if (value === undefined || value === null || value === "") return null;
      if (!/^\d+$/.test(String(value))) return null;
      const n = BigInt(String(value));
      const whole = n / 1000000n;
      const frac = String(n % 1000000n).padStart(6, "0")
        .replace(/0+$/, "");
      return whole.toString() + (frac ? "." + frac : "");
    };

    const money = value => {
      const amount = drops(value);
      return amount === null ? null : amount + " XRP";
    };

    const date = value => {
      if (!value) return null;
      const d = new Date(value);
      return Number.isNaN(d.getTime())
        ? String(value)
        : d.toLocaleString("en-US", {
            timeZone: "UTC",
            month: "short",
            day: "numeric",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false
          }) + " UTC";
    };

    // Preserve genuine written dialogue when supplied by XRPay.
    const spoken = meaningfulText(payload);
    if (spoken) {
      return {
        label: kind.toUpperCase(),
        content: spoken
      };
    }

    if (type === "quote.propose") {
      const quantity = terms.quantity;
      const asset = terms.asset || "asset unspecified";
      const product = String(terms.productName || terms.productDescription ||
        terms.productId || "unspecified product");

      let description = product;
      if (/cloudline-coffee/i.test(product)) {
        description = "the coffee test product";
      }

      const parts = [
        "I'm offering " +
        (quantity ?? "an unspecified quantity") +
        " " + (terms.unit || "units") +
        " of " + description + "."
      ];

      if (asset === "XRP") {
        if (money(terms.unitPriceDrops)) {
          parts.push("The unit price is " +
            money(terms.unitPriceDrops) + ".");
        }
        if (money(terms.totalDrops)) {
          parts.push("The quoted total is " +
            money(terms.totalDrops) + ".");
        }
        if (money(terms.shippingDrops) !== null) {
          parts.push("Shipping: " + money(terms.shippingDrops) + ".");
        }
        if (money(terms.taxDrops) !== null) {
          parts.push("Tax: " + money(terms.taxDrops) + ".");
        }
        if (money(terms.feeCapDrops)) {
          parts.push("The transaction fee cap is " +
            money(terms.feeCapDrops) + ".");
        }
      } else {
        parts.push("The quoted asset is " + asset + ".");
        parts.push("See the evidence for the asset-specific amount.");
      }

      if (terms.deliveryDeadline) {
        parts.push("Delivery deadline: " +
          date(terms.deliveryDeadline) + ".");
      }
      if (terms.inspectionHours !== undefined) {
        parts.push("Inspection period: " +
          terms.inspectionHours + " hours.");
      }
      if (terms.cancellationTerms) {
        parts.push("Conditions: " + terms.cancellationTerms);
      }
      if (terms.expiresAt) {
        parts.push("This offer expires " + date(terms.expiresAt) + ".");
      }

      return {
        label: "Commercial quotation",
        content: parts.join("\n\n")
      };
    }

    if (type === "deal.request_review") {
      return {
        label: "Review requested",
        content: "I've submitted the current deal terms for review. " +
          "The agreement still requires the applicable approvals."
      };
    }

    if (payload.kind === "result" && receipt.status) {
      const state = String(receipt.status).toLowerCase();

      const states = {
        negotiating: "The negotiation remains in progress.",
        awaiting_approvals:
          "The proposed terms are awaiting the required approvals.",
        rejected: "The submitted operation was rejected.",
        failed: "The submitted operation failed."
      };

      return {
        label: "XRPay response",
        content: states[state] ||
          "XRPay reported status: " +
          state.replaceAll("_", " ") + "."
      };
    }

    if (kind === "agreement_proposed") {
      return {
        label: "Agreement proposed",
        content: "The commercial terms have been submitted as an " +
          "agreement for both participants to consider."
      };
    }

    if (kind === "agreement_accepted") {
      return {
        label: "Agreement accepted",
        content: "Acceptance has been recorded for these terms. " +
          "Payment execution still requires separate authorization."
      };
    }

    if (kind === "room_invited") {
      return {
        label: "Negotiation invitation",
        content: "A negotiation room has been requested."
      };
    }

    if (kind === "room_status_changed") {
      return {
        label: "Room admission",
        content: "The negotiation room admission status has changed."
      };
    }

    if (/denied|blocked|unauthorized/i.test(kind)) {
      return {
        label: "Action denied",
        content: "Cloudline recorded an authorization denial. " +
          "See the evidence panel for the specific reason."
      };
    }

    return {
      label: kind.replaceAll("_", " ") || "Event",
      content: "XRPay exchanged a structured message. " +
        "Its full content is preserved in the evidence panel."
    };
  }

  // CLOUDLINE ECONOMIC CONTEXT V1
  // Interpret actual commercial fields without changing stored evidence.
  const economicNames = {
    product: ["product", "productName", "product_name", "item",
              "itemName", "item_name", "commodity", "service",
              "productDescription", "product_description"],
    quantity: ["quantity", "qty", "orderQuantity", "order_quantity",
               "requestedQuantity", "requested_quantity", "units"],
    unitPrice: ["unitPrice", "unit_price", "pricePerUnit",
                "price_per_unit", "quotedUnitPrice"],
    total: ["totalAmount", "total_amount", "totalPrice", "total_price",
            "offerAmount", "offer_amount", "quotedTotal"],
    amount: ["amount", "price"],
    currency: ["currency", "currencyCode", "currency_code",
               "asset", "paymentAsset", "payment_asset"],
    condition: ["deliveryTerms", "delivery_terms", "paymentTerms",
                "payment_terms", "condition", "conditions"]
  };

  function economicValue(payload, aliases) {
    const queue = [payload];
    let scanned = 0;

    while (queue.length && scanned++ < 300) {
      let value = queue.shift();

      if (typeof value === "string") {
        const trimmed = value.trim();
        if ((trimmed.startsWith("{") && trimmed.endsWith("}")) ||
            (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
          try { value = JSON.parse(trimmed); }
          catch (_) { continue; }
        } else {
          continue;
        }
      }

      if (!value || typeof value !== "object") continue;

      if (!Array.isArray(value)) {
        for (const alias of aliases) {
          const item = value[alias];
          if ((typeof item === "string" || typeof item === "number") &&
              String(item).trim()) {
            return String(item).trim();
          }
        }
      }

      for (const [key, item] of Object.entries(value)) {
        if (/secret|token|signature|password|api.?key/i.test(key))
          continue;
        if (item && (typeof item === "object" ||
                     (typeof item === "string" &&
                      /^[\s]*[\[{]/.test(item)))) {
          queue.push(item);
        }
      }
    }
    return null;
  }

  function economicDetail(payload) {
    const values = {};
    for (const [field, aliases] of Object.entries(economicNames)) {
      values[field] = economicValue(payload, aliases);
    }

    const parts = [];
    if (values.product) parts.push("Item or service: " + values.product);
    if (values.quantity) parts.push("Quantity: " + values.quantity);
    if (values.unitPrice) parts.push(
      "Price per unit: " + values.unitPrice +
      (values.currency ? " " + values.currency : "")
    );
    if (values.total) parts.push(
      "Proposed total: " + values.total +
      (values.currency ? " " + values.currency : "")
    );
    else if (values.amount && !values.unitPrice) parts.push(
      "Recorded amount: " + values.amount +
      (values.currency ? " " + values.currency : "")
    );
    if (values.currency && !values.unitPrice &&
        !values.total && !values.amount) {
      parts.push("Asset: " + values.currency);
    }
    if (values.condition) parts.push("Condition: " + values.condition);

    return parts;
  }

  // Keep the existing message interpretation, but add its real economics.
  const originalEconomicFormat = format;
  format = function(event) {
    const result = originalEconomicFormat(event);
    const details = []; // Embedded in the XRPay-specific formatter

    if (details.length) {
      return {
        ...result,
        content: details.join("\n") +
          (result.content ? "\n\n" + result.content : "")
      };
    }
    return result;
  };

  // Room purpose is contextual information, not a new agent statement.
  function showCommercialContext(room) {
    let context = document.getElementById("xrpay-economic-context");

    if (!context) {
      context = document.createElement("div");
      context.id = "xrpay-economic-context";
      context.className = "notice";
      context.style.marginBottom = "12px";
      conversation.insertAdjacentElement("beforebegin", context);
    }

    const current = String(room.purpose || "").trim();
    const identity = room.id + "|" + current;
    if (context.dataset.identity === identity) return;

    context.dataset.identity = identity;
    context.replaceChildren();

    const heading = document.createElement("strong");
    heading.textContent = "What this negotiation concerns";

    const text = document.createElement("p");
    text.textContent = current || "No commercial purpose supplied.";

    const note = document.createElement("small");
    note.textContent =
      "Recorded room purpose. Individual offers and prices " +
      "must be supported by their own message evidence.";

    context.append(heading, text, note);
  }

  function conversationEvent(event) {
    const who = names[event.sender] || "cloudline";
    const isBuyer = who === "Riverside Buyer";
    const isSystem = !names[event.sender];
    const msg = format(event);

    const row = document.createElement("div");
    row.style.cssText =
      "display:flex;flex-direction:column;align-items:" +
      (isSystem ? "center" :
       isBuyer ? "flex-start" : "flex-end");

    const bubble = document.createElement("div");
    bubble.style.cssText =
      "width:fit-content;max-width:85%;padding:12px 15px;" +
      "border:1px solid " +
      (isSystem ? "#786941" :
       isBuyer ? "#39764c" : "#4384a3") +
      ";background:" +
      (isSystem ? "#19180e" :
       isBuyer ? "#102519" : "#0d2330") +
      ";overflow-wrap:anywhere;white-space:pre-wrap";

    if (/block|denied|unauthoriz/i.test(event.kind)) {
      bubble.style.background = "#301616";
      bubble.style.borderColor = "#fa8585";
    }

    bubble.append(
      node("strong", msg.label),
      node("p", msg.content),
      node("small", event.created_at || "Time unavailable", "muted")
    );

    row.append(
      node("small", who, "muted"),
      bubble
    );
    conversation.append(row);
  }

  function evidenceEvent(event) {
    const card = document.createElement("article");
    card.className = "event";

    if (/block|denied|unauthoriz/i.test(event.kind))
      card.className += " denied";

    card.append(
      node("strong", event.kind),
      node("p", (names[event.sender] || event.sender || "cloudline") +
        " · " + event.created_at, "muted")
    );

    const details = document.createElement("details");
    details.append(node("summary", "View original JSON"));

    const raw = document.createElement("pre");
    raw.textContent = JSON.stringify(event, null, 2);
    details.append(raw);

    card.append(details);
    evidence.append(card);
  }

  function displayOutcome(record) {
    const agreements = record.agreements || [];
    const agreement = agreements.at(-1);
    const accepted = agreement &&
      Boolean(agreement.buyer_accepted) &&
      Boolean(agreement.seller_accepted);

    $("room-state").textContent = record.room.status;
    $("buyer-name").textContent =
      names[record.room.buyer] || record.room.buyer;
    $("seller-name").textContent =
      names[record.room.seller] || record.room.seller;
    $("room-purpose").textContent = record.room.purpose;
    $("room-link").textContent = "Room ID: " + record.room.id;

    $("agreement-state").textContent = accepted
      ? "Both accepted"
      : agreement ? "Awaiting acceptance" : "Not established";

    const denialEvents = record.events.filter(e =>
      /block|denied|unauthoriz/i.test(e.kind)
    );

    // Authorization here means room admission, not spending authority.
    const roomStatus = String(record.room.status || "").toUpperCase();

    $("authority-state").textContent =
      roomStatus === "OPEN"
        ? "AUTHORIZED"
        : roomStatus === "REJECTED"
          ? "DENIED"
          : "PENDING";

    $("authority-state").title =
      roomStatus === "OPEN"
        ? "Authenticated room invitation accepted. Room access authorized; payment authority not granted."
        : "Room admission has not been authorized.";
    $("settlement-state").textContent = "Not verified";

    decisions.replaceChildren();

    const summary = document.createElement("article");
    summary.className = "event";

    summary.append(
      node("strong", accepted
        ? "Both agents accepted the agreement"
        : agreement
          ? "Agreement awaiting acceptance"
          : "No completed agreement"),
      node("p", "Negotiation acceptance does not grant payment authority."),
      node("p", "XRPL settlement has not been verified.")
    );

    if (agreement) {
      const details = document.createElement("details");
      details.append(node("summary", "Agreement JSON"));
      const raw = document.createElement("pre");
      raw.textContent = JSON.stringify(agreement, null, 2);
      details.append(raw);
      summary.append(details);
    }

    decisions.append(summary);

    for (const event of denialEvents) {
      const denied = document.createElement("article");
      denied.className = "event denied";
      denied.append(
        node("strong", "Recorded authorization denial"),
        node("p", readable(event.payload)),
        node("small", event.created_at, "muted")
      );
      decisions.append(denied);
    }
  }

  function reset() {
    seen.clear();
    conversation.replaceChildren();
    evidence.replaceChildren();
    loaded = selected;
  }

  select.addEventListener("change", () => {
    selected = select.value;
    reset();
    poll();
  });

  async function poll() {
    if (fetching || document.hidden) return;
    fetching = true;

    try {
      const response = await fetch("/api/workspace/rooms", {
        cache: "no-store"
      });

      if (!response.ok)
        throw new Error("Partner API HTTP " + response.status);

      const data = await response.json();
      const rooms = data.rooms || [];
      const ids = rooms.map(r => r.room.id);

      // Follow a newly created room from Godfred's integration.
      const newRoom = initialized
        ? rooms.find(r => !roomIds.has(r.room.id))
        : null;

      if (newRoom) selected = newRoom.room.id;
      if (!ids.includes(selected)) selected = ids[0] || "";

      if (JSON.stringify(ids) !==
          JSON.stringify([...select.options].map(o => o.value))) {
        select.replaceChildren();

        for (const record of rooms) {
          const option = document.createElement("option");
          option.value = record.room.id;
          option.textContent =
            record.room.id.slice(0, 22) + " · " +
            record.room.status + " · " +
            record.events.length + " events";
          select.append(option);
        }
      }

      if (selected) select.value = selected;
      roomIds.clear();
      ids.forEach(id => roomIds.add(id));

      const record = rooms.find(r => r.room.id === selected);

      if (!record) {
        $("connection").textContent = "Watching XRPay";
        $("conversation-state").textContent =
          "Waiting for Godfred's agents.";
        initialized = true;
        return;
      }

      if (loaded !== selected) reset();

      const events = [...record.events].sort((a,b) =>
        String(a.created_at).localeCompare(String(b.created_at))
      );

      let additions = 0;

      for (const event of events) {
        const id = record.room.id + ":" + event.id;
        if (seen.has(id)) continue;

        seen.add(id);
        conversationEvent(event);
        evidenceEvent(event);
        additions++;
      }

      if (additions) {
        conversation.scrollTop = conversation.scrollHeight;
        evidence.scrollTop = evidence.scrollHeight;
      }

      showCommercialContext(record.room);
      displayOutcome(record);

      $("connection").textContent = "XRPay connected";
      $("conversation-state").textContent =
        "Live communication · Riverside Buyer ↔ Cedar Supplier";
      $("status").textContent =
        events.length + " recorded events · " +
        (additions ? additions + " new on screen" :
         "Waiting for API activity");

      initialized = true;

    } catch (error) {
      $("connection").textContent = "Connection error";
      $("status").textContent = error.message;
    } finally {
      fetching = false;
    }
  }

  poll();
  setInterval(poll, 1000);
})();


// CLOUDLINE UNIFIED SESSION CONTROLLER V5
// The Partner API creates rooms. This controller only selects and displays them.
(() => {
  const STORAGE = "cloudline.awaiting.xrpay.room.v5";

  function setup() {
    const select = document.getElementById("xrpay-room-select");
    if (!select) {
      console.error("cloudline: room selector unavailable");
      return;
    }

    if (document.getElementById("cpx-fresh-session")) return;

    const style = document.createElement("style");
    style.textContent = `
      /* Hide stale data everywhere while waiting */
      body.cpx-awaiting #room-purpose,
      body.cpx-awaiting #room-link,
      body.cpx-awaiting #buyer-name,
      body.cpx-awaiting #seller-name,
      body.cpx-awaiting #xrpay-economic-context,
      body.cpx-awaiting #xrpay-room-select,
      body.cpx-awaiting #conversation-state,
      body.cpx-awaiting #connection,
      body.cpx-awaiting #status,
      body.cpx-awaiting #room-state,
      body.cpx-awaiting #agreement-state,
      body.cpx-awaiting #authority-state,
      body.cpx-awaiting #settlement-state {
        visibility: hidden !important;
      }

      body.cpx-awaiting #conversation,
      body.cpx-awaiting #events,
      body.cpx-awaiting #evidence,
      body.cpx-awaiting #decisions {
        position: relative !important;
        min-height: 190px !important;
        overflow: hidden !important;
      }

      body.cpx-awaiting #conversation > *,
      body.cpx-awaiting #events > *,
      body.cpx-awaiting #evidence > *,
      body.cpx-awaiting #decisions > * {
        visibility: hidden !important;
      }

      body.cpx-awaiting #conversation::after,
      body.cpx-awaiting #events::after,
      body.cpx-awaiting #evidence::after,
      body.cpx-awaiting #decisions::after {
        content: "AWAITING NEW SESSION";
        position: absolute;
        inset: 0;
        display: grid;
        place-items: center;
        text-align: center;
        color: #45f875;
        background: #061009;
        border: 1px solid #235936;
        font: 700 12px ui-monospace, Menlo, monospace;
        letter-spacing: .13em;
        z-index: 10;
      }

      #cpx-session-state {
        margin: 12px 0;
        padding: 15px;
        border: 1px solid #347b46;
        background: linear-gradient(100deg,#08180c,#0d2815);
        color: #a4edb6;
        font: 11px/1.7 ui-monospace,Menlo,monospace;
        letter-spacing: .04em;
      }

      #cpx-fresh-session {
        display: block;
        width: 100%;
        min-height: 54px;
        margin: 10px 0;
        padding: 12px;
        background: linear-gradient(100deg,#12371e,#1b5a30);
        border: 1px solid #45f875;
        color: #dfffe7;
        font: 700 12px ui-monospace,Menlo,monospace;
        letter-spacing: .14em;
        cursor: pointer;
        box-shadow: 0 0 17px #1cc64a24;
      }

      #cpx-fresh-session.is-waiting {
        background: #0a2011;
        border-color: #327b43;
        color: #7aefa0;
        cursor: default;
        opacity: 1;
      }

      #cpx-fresh-session:focus-visible {
        outline: 2px solid #ceffda;
        outline-offset: 3px;
      }
    `;
    document.head.appendChild(style);

    const button = document.createElement("button");
    button.id = "cpx-fresh-session";
    button.type = "button";
    button.textContent = "▶ ARM NEW SESSION";

    const state = document.createElement("div");
    state.id = "cpx-session-state";
    state.textContent = "XRPay negotiation monitor online.";

    select.insertAdjacentElement("afterend", button);
    button.insertAdjacentElement("afterend", state);

    let waiting = false;
    let baseline = new Set();
    let pendingRoom = null;
    let busy = false;

    const idOf = item => item?.room?.id || null;

    async function fetchRooms() {
      const response = await fetch("/api/workspace/rooms", {
        cache: "no-store"
      });
      if (!response.ok) throw Error("HTTP " + response.status);
      const data = await response.json();
      return Array.isArray(data.rooms) ? data.rooms : [];
    }

    function saveWaiting() {
      try {
        sessionStorage.setItem(
          STORAGE,
          JSON.stringify({baseline: [...baseline]})
        );
      } catch (_) {}
    }

    function clearWaiting() {
      try {
        sessionStorage.removeItem(STORAGE);
      } catch (_) {}
    }

    function enterWaiting() {
      waiting = true;
      pendingRoom = null;

      document.body.classList.add("cpx-awaiting");

      select.value = "";
      select.disabled = true;

      button.disabled = true;
      button.classList.add("is-waiting");
      button.textContent = "● WAITING FOR XRPAY";

      state.textContent =
        "SESSION ARMED // No room selected. Listening for Godfred's next API-created negotiation.";
    }

    function finishWaiting(roomId) {
      waiting = false;
      pendingRoom = null;
      clearWaiting();

      select.disabled = false;
      select.value = roomId;
      select.dispatchEvent(
        new Event("change", {bubbles: true})
      );

      // Let the existing workspace renderer process the selected room
      // before making its information visible.
      setTimeout(() => {
        document.body.classList.remove("cpx-awaiting");
        button.disabled = false;
        button.classList.remove("is-waiting");
        button.textContent = "▶ ARM NEW SESSION";
        state.textContent =
          "NEW ROOM CONNECTED // " + roomId;
      }, 1200);
    }

    button.addEventListener("click", async () => {
      if (waiting) return;

      button.disabled = true;
      button.textContent = "SYNCING ROOM HISTORY...";

      try {
        const existing = await fetchRooms();
        baseline = new Set(
          existing.map(idOf).filter(Boolean)
        );

        saveWaiting();
        enterWaiting();
      } catch (error) {
        button.disabled = false;
        button.textContent = "▶ ARM NEW SESSION";
        state.textContent =
          "Cannot arm session: " + error.message;
      }
    });

    // Restore waiting mode after a browser refresh.
    try {
      const saved = JSON.parse(
        sessionStorage.getItem(STORAGE) || "null"
      );
      if (saved && Array.isArray(saved.baseline)) {
        baseline = new Set(saved.baseline);
        enterWaiting();
        state.textContent =
          "SESSION RESTORED // Listening for a new XRPay negotiation.";
      }
    } catch (_) {
      clearWaiting();
    }

    async function poll() {
      if (!waiting || busy) return;
      busy = true;

      try {
        const rooms = await fetchRooms();

        if (!pendingRoom) {
          const fresh = rooms.find(
            item => idOf(item) && !baseline.has(idOf(item))
          );
          if (fresh) {
            pendingRoom = idOf(fresh);
            state.textContent =
              "NEW ROOM DETECTED // Synchronizing " + pendingRoom;
          }
        }

        if (pendingRoom) {
          // Wait until the original live workspace has indexed the room.
          const option = [...select.options].find(
            o => o.value === pendingRoom
          );

          if (option) {
            finishWaiting(pendingRoom);
          }
        }
      } catch (error) {
        state.textContent =
          "XRPay connection interrupted // Retrying: " +
          error.message;
      } finally {
        busy = false;
      }
    }

    setInterval(poll, 1000);
    poll();

    console.info("cloudline: unified session V5 ready");
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setup, {
      once: true
    });
  } else {
    setup();
  }
})();
