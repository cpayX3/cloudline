"use strict";

(() => {
  const el = id => document.getElementById(id);
  const result = el("clResult");

  if (!result) return;

  let busy = false;

  function scope() {
    return {
      service: el("clService").value.trim(),
      resource: el("clResource").value.trim(),
      network: "xrpl:0",
      asset: el("clAsset").value,
      recipient: el("clRecipient").value.trim()
    };
  }

  async function request(path, body) {
    const token = el("clToken").value.trim();

    if (!token) {
      throw new Error("ROOM_SESSION_TOKEN_REQUIRED");
    }

    const response = await fetch(path, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + token
      },
      body: JSON.stringify(body),
      cache: "no-store"
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || "REQUEST_REJECTED");
    }

    return data;
  }

  async function execute(path, extra) {
    if (busy) return;

    const room_id = el("clRoom").value.trim();

    if (!room_id) {
      result.textContent = "ROOM_ID_REQUIRED";
      return;
    }

    busy = true;
    result.textContent = "Submitting authenticated request...";

    try {
      const data = await request(path, {
        room_id,
        ...extra
      });

      result.textContent = JSON.stringify(data, null, 2);
    } catch (error) {
      result.textContent = "BLOCKED: " + error.message;
    } finally {
      busy = false;
    }
  }

  el("clConsent").addEventListener("click", () =>
    execute("/api/autonomous/consent", { enabled: true })
  );

  el("clRevoke").addEventListener("click", () =>
    execute("/api/autonomous/consent", { enabled: false })
  );

  el("clScope").addEventListener("click", () =>
    execute("/api/autonomous/scope", { scope: scope() })
  );

  el("clRun").addEventListener("click", () =>
    execute("/api/autonomous/run", scope())
  );
})();
