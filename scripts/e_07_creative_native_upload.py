#!/usr/bin/env python3
"""
e_07 — Reestrutura o criativo pra upload de mídia via nó NATIVO (multipart binário).

Descoberta: o code node do n8n NÃO consegue enviar multipart/form-data binário
(formData/Buffer dão 400; require('form-data') é bloqueado). Só o HTTP Request
NATIVO faz multipart. Então:

  meta_d2_adset -> meta_d3_prep (code: baixa bytes + prepareBinaryData)
               -> meta_d3_upload (nativo: multipart -> video_id/image_hash)
               -> meta_d3_creative (code: poll + thumbnail + adcreative)
               -> meta_d4_ad

Validado com vídeo real (4.5MB -> video_id retornado).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import n8n_api

WF_ID = "fBUin1UPt5xJEp6g"
NODES = os.path.join(os.path.dirname(__file__), "nodes")


def main():
    wf = n8n_api.get_workflow(WF_ID)
    nodes = wf["nodes"]
    conns = wf["connections"]
    by = {n["name"]: n for n in nodes}

    creative = by["meta_d3_creative"]
    px, py = creative.get("position", [1600, 0])

    # 1) meta_d3_creative vira o FINISH (novo código)
    creative["parameters"]["jsCode"] = open(os.path.join(NODES, "meta_d3_creative.js")).read()
    creative["type"] = "n8n-nodes-base.code"
    creative["typeVersion"] = 2
    creative.pop("credentials", None)
    creative["continueOnFail"] = True

    # 2) cria meta_d3_prep (code) + meta_d3_upload (nativo) — se ainda não existem
    if "meta_d3_prep" not in by:
        nodes.append({
            "parameters": {"jsCode": open(os.path.join(NODES, "meta_d3_prep.js")).read()},
            "id": "metad3prep0001", "name": "meta_d3_prep",
            "type": "n8n-nodes-base.code", "typeVersion": 2,
            "position": [px - 400, py], "continueOnFail": True,
        })
    else:
        by["meta_d3_prep"]["parameters"]["jsCode"] = open(os.path.join(NODES, "meta_d3_prep.js")).read()

    if "meta_d3_upload" not in by:
        nodes.append({
            "parameters": {
                "method": "POST",
                "url": "=https://graph.facebook.com/v25.0/act_{{ $json.adAccountId }}/{{ $json.isVideo ? 'advideos' : 'adimages' }}?access_token={{ $json.token }}",
                "sendBody": True,
                "contentType": "multipart-form-data",
                "bodyParameters": {"parameters": [
                    {"parameterType": "formBinaryData", "name": "source", "inputDataFieldName": "data"}
                ]},
                "options": {},
            },
            "id": "metad3upload001", "name": "meta_d3_upload",
            "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
            "position": [px - 200, py], "continueOnFail": True,
        })

    # 3) religa: meta_d2_adset -> meta_d3_prep -> meta_d3_upload -> meta_d3_creative
    conns["meta_d2_adset"] = {"main": [[{"node": "meta_d3_prep", "type": "main", "index": 0}]]}
    conns["meta_d3_prep"] = {"main": [[{"node": "meta_d3_upload", "type": "main", "index": 0}]]}
    conns["meta_d3_upload"] = {"main": [[{"node": "meta_d3_creative", "type": "main", "index": 0}]]}
    # meta_d3_creative -> meta_d4_ad já existe (mantém)

    ALLOWED = {"executionOrder", "saveExecutionProgress", "saveManualExecutions",
               "saveDataErrorExecution", "saveDataSuccessExecution",
               "executionTimeout", "errorWorkflow", "timezone"}
    clean = {k: v for k, v in (wf.get("settings") or {}).items() if k in ALLOWED}
    clean.setdefault("executionOrder", "v1")

    n8n_api.update_workflow(WF_ID, name=wf["name"], nodes=nodes, connections=conns, settings=clean)
    print("✓ Reestruturado: meta_d2_adset -> meta_d3_prep -> meta_d3_upload -> meta_d3_creative -> meta_d4_ad")


if __name__ == "__main__":
    main()
