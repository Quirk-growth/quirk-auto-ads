#!/usr/bin/env python3
"""
e_02 — Transforma o workflow "WhatsApp Cloud Inbound" no adaptador de entrada.

Recebe o webhook da Meta (Cloud API), faz:
  - GET  -> verificação (hub.challenge)  [já existia]
  - POST -> parseia a mensagem e REPASSA pro webhook do fluxo principal,
            no formato que ele já espera (body.message.type / body.chat.phone / ...).

Assim o fluxo PRINCIPAL não precisa de nenhuma mudança na entrada.

Nós: webhook -> route -> [ respond , if_forward -> forward_to_main ]
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import n8n_api

WF_ID = "7vhoapaFk2zY8ptL"
MAIN_WEBHOOK = "https://n8n.quirkgrowth.online/webhook/quirk-auto-ads"

ROUTE_CODE = r"""
const VERIFY_TOKEN = "quirk_wa_28efc561d81a16b3";
const item = $input.first().json;
const q = item.query || {};

// 1) Verificação do webhook (Meta manda GET com hub.challenge)
if (q["hub.challenge"] !== undefined) {
  const ok = q["hub.verify_token"] === VERIFY_TOKEN && q["hub.mode"] === "subscribe";
  return [{ json: { responseBody: ok ? String(q["hub.challenge"]) : "forbidden", doForward: false } }];
}

// 2) Evento POST — parseia o payload da WhatsApp Cloud API
const body = item.body || {};
let msg = null;
try {
  const entry  = (body.entry   || [])[0] || {};
  const change = (entry.changes || [])[0] || {};
  const value  = change.value || {};
  msg = (value.messages || [])[0] || null;
} catch (e) {}

// Sem mensagem de cliente (status de entrega/leitura, etc.) -> só confirma 200
if (!msg) {
  return [{ json: { responseBody: "EVENT_RECEIVED", doForward: false } }];
}

const from = msg.from; // ex: 5511952136200 (com DDI, sem +)
let type = "text", text = "", mediaId = "";

if (msg.type === "text") {
  text = (msg.text && msg.text.body) || "";
} else if (["image", "video", "audio", "document", "sticker"].includes(msg.type)) {
  type = "media";
  const mo = msg[msg.type] || {};
  mediaId = mo.id || "";
  text = mo.caption || "";
} else if (msg.type === "button") {
  text = (msg.button && msg.button.text) || "";
} else if (msg.type === "interactive") {
  const it = msg.interactive || {};
  text = (it.button_reply && it.button_reply.title) ||
         (it.list_reply && it.list_reply.title) || "";
}

// Monta no formato que o fluxo principal já consome:
//  - switch_type          lê  body.message.type   ('text'|'media')
//  - normalize_phone      lê  body.chat.phone / body.message.text
//  - media_normalize_phone lê body.message.id (= media_id p/ download na Cloud API)
const forward = {
  message: {
    type,
    text,
    id: (type === "media") ? mediaId : (msg.id || ""),
    from,
    sender_pn: from,
  },
  chat: { phone: from },
};

return [{ json: { responseBody: "EVENT_RECEIVED", doForward: true, forward } }];
""".strip()


def main():
    wf = n8n_api.get_workflow(WF_ID)
    nodes = wf["nodes"]
    by_name = {n["name"]: n for n in nodes}
    pos_route = by_name["route"].get("position", [0, 0])

    # atualiza o route
    by_name["route"]["parameters"]["jsCode"] = ROUTE_CODE

    # if_forward
    if_forward = {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                "conditions": [{
                    "leftValue": "={{ $json.doForward }}",
                    "rightValue": "",
                    "operator": {"type": "boolean", "operation": "true", "singleValue": True},
                }],
                "combinator": "and",
            },
            "options": {},
        },
        "id": "e02ifforward000001",
        "name": "if_forward",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2.2,
        "position": [pos_route[0] + 220, pos_route[1] + 160],
    }
    # forward_to_main
    forward_to_main = {
        "parameters": {
            "method": "POST",
            "url": MAIN_WEBHOOK,
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json.forward) }}",
            "options": {},
        },
        "id": "e02forwardmain0001",
        "name": "forward_to_main",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [pos_route[0] + 440, pos_route[1] + 160],
        "continueOnFail": True,
    }
    nodes += [if_forward, forward_to_main]

    conns = wf["connections"]
    # route -> respond (mantém) + route -> if_forward
    conns["route"] = {"main": [[
        {"node": "respond", "type": "main", "index": 0},
        {"node": "if_forward", "type": "main", "index": 0},
    ]]}
    # if_forward: saída TRUE(0) -> forward_to_main ; FALSE(1) -> nada
    conns["if_forward"] = {"main": [
        [{"node": "forward_to_main", "type": "main", "index": 0}],
        [],
    ]}

    ALLOWED = {"executionOrder", "saveExecutionProgress", "saveManualExecutions",
               "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone"}
    clean = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    clean.setdefault("executionOrder", "v1")

    n8n_api.update_workflow(WF_ID, name=wf["name"], nodes=nodes, connections=conns, settings=clean)
    print("✓ Cloud Inbound agora parseia + repassa pro fluxo principal.")
    print("  webhook -> route -> [respond, if_forward -> forward_to_main]")


if __name__ == "__main__":
    main()
