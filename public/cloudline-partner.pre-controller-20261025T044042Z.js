
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


// CLOUDLINE XRPay LIVE FEED
// Watches Godfred's real Partner API records.
// Read-only. Does not start, control, or impersonate agents.
(() => {
  "use strict";

  const existing = document.getElementById("xrpay-evidence");
  if (existing) existing.remove();

  const oldControls = document.getElementById("cloudline-live-controls");
  if (oldControls) oldControls.remove();

  const panel = document.createElement("section");
  panel.className = "panel";
  panel.id = "xrpay-live-feed";
  panel.style.marginTop = "18px";

  panel.innerHTML = `
    <div class="top" style="margin-bottom:12px">
      <div>
        <div class="eyebrow">EXTERNAL AGENT INTEGRATION</div>
        <h2 style="margin:4px 0">XRPay / Godfred — Live Negotiations</h2>
        <p class="muted">
          Riverside Buyer ↔ Cedar Supplier.
          Events arrive from Godfred's API through cloudline.
        </p>
      </div>
      <span class="pill" id="xrpay-connection">CONNECTING</span>
    </div>

    <div class="metrics">
      <div class="metric">
        <div class="eyebrow">Negotiation rooms</div>
        <strong id="xrpay-rooms">0</strong>
      </div>
      <div class="metric">
        <div class="eyebrow">Recorded events</div>
        <strong id="xrpay-count">0</strong>
      </div>
      <div class="metric">
        <div class="eyebrow">Latest activity</div>
        <strong id="xrpay-latest">Waiting</strong>
      </div>
      <div class="metric">
        <div class="eyebrow">Payment authority</div>
        <strong>NOT GRANTED</strong>
      </div>
    </div>

    <div class="notice">
      <strong>LIVE INTEGRATION MONITOR</strong>
      <p id="xrpay-status">
        Connecting to cloudline negotiation records...
      </p>
      <small>
        Negotiation agreement does not constitute payment authorization
        or blockchain settlement.
      </small>
    </div>

    <h3 style="margin-top:22px">Active negotiation rooms</h3>
    <div id="xrpay-room-list" class="timeline"
         style="margin-top:12px"></div>

    <div class="top" style="margin:24px 0 12px">
      <h3>Live negotiation timeline</h3>
      <span class="pill" id="xrpay-new-count">WAITING FOR EVENTS</span>
    </div>
    <div id="xrpay-stream" class="timeline"></div>
  `;

  const anchor = document.getElementById("partner-live");

  if (anchor) {
    anchor.insertAdjacentElement("afterend", panel);
  } else {
    document.querySelector("main").append(panel);
  }

  const $ = id => document.getElementById(id);

  const seen = new Set();
  const agreementStates = new Map();
  const knownRooms = new Set();

  let initialized = false;
  let polling = false;
  let freshCount = 0;
  let lastSignature = "";

  const names = {
    "agent_32b12ad0565cab3fa6d35ae50375cb4a":
      "Riverside Buyer",
    "agent_f982fdf4d88d2a3399ff972fd4b4d53f":
      "Cedar Supplier"
  };

  function agentName(id) {
    return names[id] || id || "cloudline";
  }

  function label(kind) {
    return String(kind || "EVENT")
      .replaceAll("_", " ")
      .toUpperCase();
  }

  function textElement(tag, value, className) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    item.textContent = String(value ?? "");
    return item;
  }

  function addCard(kind, sender, timestamp, payload, fresh, roomId) {
    const card = document.createElement("article");
    card.className = "event";

    if (fresh) {
      card.style.borderLeft = "4px solid #45ef83";
      card.style.boxShadow = "0 0 13px rgba(69,239,131,.22)";
      card.style.background = "#10301b";
    }

    if (/BLOCK|DENIED|REJECT/i.test(kind)) {
      card.className = "event denied";
    }

    const head = document.createElement("div");
    head.className = "event-head";

    head.append(
      textElement("strong", label(kind)),
      textElement("small", fresh ? "● NEW EVENT" : "RECORDED")
    );

    card.append(head);
    card.append(
      textElement("p", agentName(sender), "muted"),
      textElement("small", timestamp || "Timestamp unavailable"),
      textElement("p", "Room: " + roomId, "muted")
    );

    if (payload !== undefined && payload !== null) {
      const details = document.createElement("details");
      const toggle = document.createElement("summary");
      toggle.textContent = "View original event evidence";

      const raw = document.createElement("pre");
      raw.textContent = JSON.stringify(payload, null, 2);

      details.append(toggle, raw);
      card.append(details);
    }

    $("xrpay-stream").prepend(card);

    while ($("xrpay-stream").children.length > 160) {
      $("xrpay-stream").lastElementChild.remove();
    }

    if (fresh) {
      freshCount++;
      $("xrpay-new-count").textContent =
        freshCount + " NEW EVENT(S)";
    }
  }

  function drawRooms(records) {
    const signature = JSON.stringify(records.map(item => ({
      id: item.room.id,
      status: item.room.status,
      events: item.events.length,
      agreements: item.agreements
    })));

    if (signature === lastSignature) return;

    lastSignature = signature;
    const target = $("xrpay-room-list");
    target.replaceChildren();

    for (const record of records) {
      const room = record.room;

      const card = document.createElement("article");
      card.className = "event";

      card.append(
        textElement(
          "strong",
          agentName(room.buyer) + " ↔ " + agentName(room.seller)
        ),
        textElement("p", "Status: " + room.status),
        textElement("p", "Purpose: " + room.purpose),
        textElement("small", "Room ID: " + room.id),
        textElement("p", record.events.length + " recorded events")
      );

      for (const agreement of record.agreements) {
        const accepted =
          Boolean(agreement.buyer_accepted) &&
          Boolean(agreement.seller_accepted);

        card.append(
          textElement(
            "p",
            accepted
              ? "BILATERAL AGREEMENT RECORDED · PAYMENT NOT AUTHORIZED"
              : "AGREEMENT AWAITING ACCEPTANCE"
          )
        );
      }

      target.append(card);
    }
  }

  async function poll() {
    if (polling || document.hidden) return;
    polling = true;

    try {
      const response = await fetch("/api/demo/xrpay", {
        cache: "no-store"
      });

      if (!response.ok) {
        throw new Error("Evidence API HTTP " + response.status);
      }

      const data = await response.json();
      const records = data.rooms || [];

      $("xrpay-connection").textContent = "● LIVE";
      $("xrpay-connection").style.color = "#45ef83";

      $("xrpay-rooms").textContent = records.length;

      const total = records.reduce(
        (count, item) => count + (item.events || []).length,
        0
      );

      $("xrpay-count").textContent = total;

      const additions = [];

      for (const record of records) {
        const room = record.room;

        if (initialized && !knownRooms.has(room.id)) {
          additions.push({
            id: "room-created:" + room.id,
            kind: "NEW NEGOTIATION ROOM",
            sender: room.buyer,
            timestamp: room.created_at,
            payload: {
              purpose: room.purpose,
              status: room.status,
              seller: room.seller
            },
            roomId: room.id
          });
        }

        knownRooms.add(room.id);

        for (const event of record.events || []) {
          const id = room.id + ":" + event.id;
          if (seen.has(id)) continue;

          seen.add(id);

          additions.push({
            id,
            kind: event.kind,
            sender: event.sender,
            timestamp: event.created_at,
            payload: event.payload,
            roomId: room.id
          });
        }

        for (const agreement of record.agreements || []) {
          const id = room.id + ":" + agreement.id;
          const state =
            String(agreement.buyer_accepted) + ":" +
            String(agreement.seller_accepted);

          if (agreementStates.get(id) === state) continue;

          if (initialized && agreementStates.has(id)) {
            additions.push({
              id: id + ":" + state,
              kind: "AGREEMENT STATUS UPDATED",
              sender: "cloudline",
              timestamp: new Date().toISOString(),
              payload: {
                agreement_id: agreement.id,
                buyer_accepted: Boolean(agreement.buyer_accepted),
                seller_accepted: Boolean(agreement.seller_accepted),
                payment_authority: "NOT_GRANTED"
              },
              roomId: room.id
            });
          }

          agreementStates.set(id, state);
        }
      }

      // Sort original events by their timestamps, not by HTTP arrival order.
      additions.sort((a, b) =>
        String(a.timestamp).localeCompare(String(b.timestamp))
      );

      for (const event of additions) {
        addCard(
          event.kind,
          event.sender,
          event.timestamp,
          event.payload,
          initialized,
          event.roomId
        );
      }

      drawRooms(records);

      const last = records.flatMap(r => r.events || [])
        .map(e => e.created_at)
        .filter(Boolean)
        .sort()
        .at(-1);

      $("xrpay-latest").textContent =
        last ? last.replace("T", " ").slice(0, 19) + " UTC"
             : "Waiting";

      $("xrpay-status").textContent = initialized
        ? "Watching Godfred's XRPay API activity. " +
          "New room invitations, messages, offers and agreements " +
          "appear automatically as cloudline records them."
        : "Historical negotiation evidence loaded. " +
          "Now watching for new autonomous agent activity.";

      initialized = true;

    } catch (error) {
      $("xrpay-connection").textContent = "DISCONNECTED";
      $("xrpay-connection").style.color = "#fa8585";
      $("xrpay-status").textContent =
        "Connection error: " + error.message;
    } finally {
      polling = false;
    }
  }

  poll();
  setInterval(poll, 1000);
})();
