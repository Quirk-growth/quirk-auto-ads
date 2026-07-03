#!/usr/bin/env python3
"""
e_01 — Migra o workflow PRINCIPAL (Quirk Auto Ads) de uazapi → WhatsApp Cloud API.

- 12 nós de envio de texto: POST uazapi/send/text  ->  POST graph/{phone_id}/messages
- media_download (uazapi /message/download) -> 2 passos Cloud API:
      media_get_url (GET /{media_id})  ->  media_download (code: emite fileURL+mimetype)

Não coloca token em código: usa a credencial "Quirk WhatsApp Cloud" (Header Auth)
já criada no n8n (id em n8n_workflow/.wa_cloud_cred_id).

Uso:
    python3 scripts/e_01_migrate_main_to_cloud.py           # aplica
    python3 scripts/e_01_migrate_main_to_cloud.py --dry     # só mostra, não aplica
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))
import n8n_api

WF_ID = "fBUin1UPt5xJEp6g"
GRAPH = "https://graph.facebook.com/v25.0"
PHONE_ID = open(os.path.expanduser("~/.config/n8n-quirk/wa_phone_number_id.txt")).read().strip()
CRED_ID = open("/Users/renanreal/quirk_auto_ads/n8n_workflow/.wa_cloud_cred_id").read().strip()
CRED_NAME = "Quirk WhatsApp Cloud"

TEXT_SENDS = [
    "send_nao_cadastrado", "send_resposta", "send_confirmacao_cliente",
    "media_send_confirma", "send_gestao_msg", "send_not_found",
    "send_processando", "send_validando", "send_inativo",
    "send_onboarding_msg", "send_ativacao_msg", "send_falha_msg",
]

DRY = "--dry" in sys.argv


# ── extração de number/text a partir do nó atual (2 estilos) ──────────────
def expr_inner(val):
    """'={{ X }}' -> 'X'  ; retorna None se não for expressão pura."""
    if not isinstance(val, str):
        return None
    v = val[1:].strip() if val.startswith("=") else val.strip()
    if v.startswith("{{") and v.endswith("}}"):
        return v[2:-2].strip()
    return None


def parse_jsonbody(raw):
    """Template n8n '={...}' -> (obj, slots). slots[i] = ('q'|'b', expr):
    'q' = expressão que estava ENTRE ASPAS ("{{x}}") -> produz string crua
    'b' = expressão CRUA ({{x}}) -> já produz um valor JSON pronto
    """
    body = raw[1:] if raw.startswith("=") else raw
    slots = []

    def qrepl(m):
        slots.append(("q", m.group(1).strip()))
        return json.dumps(f"@@E{len(slots)-1}@@")

    b = re.sub(r'"\{\{(.+?)\}\}"', qrepl, body, flags=re.S)

    def brepl(m):
        slots.append(("b", m.group(1).strip()))
        return json.dumps(f"@@E{len(slots)-1}@@")

    b = re.sub(r"\{\{(.+?)\}\}", brepl, b, flags=re.S)
    return json.loads(b), slots


def _slot_of(val, slots):
    m = re.fullmatch(r"@@E(\d+)@@", val) if isinstance(val, str) else None
    return slots[int(m.group(1))] if m else None


def get_number_token_and_text(node):
    """Retorna (number_token, text_spec).
    number_token: string pronta pra ir dentro de  "to": "<...>"
    text_spec: ('literal', s) | ('rawstr', expr) | ('jsonval', expr)
    """
    p = node["parameters"]
    if p.get("bodyParameters"):
        d = {x["name"]: x["value"] for x in p["bodyParameters"]["parameters"]}
        num, txt = d.get("number"), d.get("text")
        ni = expr_inner(num)
        number_token = "{{ " + ni + " }}" if ni is not None else str(num)
        ti = expr_inner(txt)
        text_spec = ("rawstr", ti) if ti is not None else ("literal", txt)
        return number_token, text_spec

    obj, slots = parse_jsonbody(p.get("jsonBody", ""))
    ns = _slot_of(obj.get("number", ""), slots)
    number_token = "{{ " + ns[1] + " }}" if ns else str(obj.get("number", ""))
    ts = _slot_of(obj.get("text", ""), slots)
    if ts is None:
        text_spec = ("literal", obj.get("text", ""))
    elif ts[0] == "q":
        text_spec = ("rawstr", ts[1])   # string crua -> precisa stringify
    else:
        text_spec = ("jsonval", ts[1])  # já é JSON pronto -> embute cru
    return number_token, text_spec


def body_value(text_spec):
    kind, v = text_spec
    if kind == "literal":
        return json.dumps(v, ensure_ascii=False)
    if kind == "rawstr":
        return "{{ JSON.stringify(" + v + ") }}"
    return "{{ " + v + " }}"  # jsonval


def build_cloud_jsonbody(number_token, text_spec):
    return (
        "={\n"
        '  "messaging_product": "whatsapp",\n'
        f'  "to": "{number_token}",\n'
        '  "type": "text",\n'
        '  "text": { "body": ' + body_value(text_spec) + ', "preview_url": true }\n'
        "}"
    )


# ── main ──────────────────────────────────────────────────────────────────
def main():
    wf = n8n_api.get_workflow(WF_ID)
    nodes = wf["nodes"]
    by_name = {n["name"]: n for n in nodes}

    # 1) migra os 12 envios de texto
    for name in TEXT_SENDS:
        n = by_name[name]
        number_token, text_spec = get_number_token_and_text(n)
        new_body = build_cloud_jsonbody(number_token, text_spec)
        p = n["parameters"]
        p.pop("bodyParameters", None)
        p["method"] = "POST"
        p["url"] = f"{GRAPH}/{PHONE_ID}/messages"
        p["authentication"] = "predefinedCredentialType"
        p["nodeCredentialType"] = "httpHeaderAuth"
        p["sendHeaders"] = True
        p["headerParameters"] = {"parameters": [{"name": "Content-Type", "value": "application/json"}]}
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = new_body
        n["credentials"] = {"httpHeaderAuth": {"id": CRED_ID, "name": CRED_NAME}}
        n["continueOnFail"] = True
        print(f"\n### {name}")
        print(new_body)

    # 2) media_download -> media_get_url (GET media obj) + media_download (code)
    md = by_name["media_download"]
    pos = md.get("position", [0, 0])

    media_get_url = {
        "parameters": {
            "method": "GET",
            "url": f"{GRAPH}/{{{{ $('media_normalize_phone').item.json.message_id }}}}",
            "authentication": "predefinedCredentialType",
            "nodeCredentialType": "httpHeaderAuth",
            "options": {},
        },
        "id": "e01mediageturl0001",
        "name": "media_get_url",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [pos[0] - 200, pos[1]],
        "credentials": {"httpHeaderAuth": {"id": CRED_ID, "name": CRED_NAME}},
        "continueOnFail": True,
    }
    # media_download vira CODE node que emite fileURL+mimetype (compat downstream)
    md["type"] = "n8n-nodes-base.code"
    md["typeVersion"] = 2
    md["parameters"] = {
        "jsCode": (
            "// Cloud API: media_get_url devolve {url, mime_type}. "
            "Emite no formato antigo (fileURL/mimetype) p/ compat.\n"
            "const g = $input.first().json || {};\n"
            "return [{ json: { fileURL: g.url || '', mimetype: g.mime_type || '' } }];\n"
        )
    }
    md.pop("credentials", None)
    nodes.append(media_get_url)

    # rewire: media_select_conversa -> media_get_url -> media_download
    conns = wf["connections"]
    conns["media_select_conversa"]["main"][0] = [{"node": "media_get_url", "type": "main", "index": 0}]
    conns["media_get_url"] = {"main": [[{"node": "media_download", "type": "main", "index": 0}]]}
    print("\n### media_download migrado (2 passos Cloud API) + rewire OK")

    if DRY:
        print("\n[DRY] nada aplicado.")
        return

    # A API pública só aceita um subconjunto de settings
    ALLOWED = {"executionOrder", "saveExecutionProgress", "saveManualExecutions",
               "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone"}
    clean_settings = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    if "executionOrder" not in clean_settings:
        clean_settings["executionOrder"] = "v1"

    n8n_api.update_workflow(WF_ID, name=wf["name"], nodes=nodes, connections=conns,
                            settings=clean_settings)
    print("\n✓ APLICADO no workflow principal.")


if __name__ == "__main__":
    main()
