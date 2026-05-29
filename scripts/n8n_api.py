#!/usr/bin/env python3
"""
Helper pra API REST do n8n self-hosted.

Usa key salva em ~/.config/n8n-quirk/api_key.txt (perms 600).
Base URL: https://n8n.quirkgrowth.online

Uso CLI:
    python3 n8n_api.py list                  # lista workflows
    python3 n8n_api.py get <id>              # detalhes JSON do workflow
    python3 n8n_api.py creds                 # lista credenciais (sem secrets)
    python3 n8n_api.py activate <id>         # ativa workflow
    python3 n8n_api.py deactivate <id>       # desativa workflow
    python3 n8n_api.py delete <id>           # deleta workflow
    python3 n8n_api.py executions <id>       # últimas execuções
    python3 n8n_api.py snapshot <id> <path>  # salva blueprint do workflow em arquivo

Uso como módulo:
    import n8n_api
    wf = n8n_api.get_workflow("Xy7AbCd123")
    n8n_api.update_workflow(wf["id"], name=wf["name"], nodes=wf["nodes"], connections=wf["connections"])
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

N8N_URL = "https://n8n.quirkgrowth.online"
KEY_PATH = os.path.expanduser("~/.config/n8n-quirk/api_key.txt")


def _key() -> str:
    return open(KEY_PATH).read().strip()


def _request(method: str, path: str, payload: dict = None) -> dict:
    """Faz request à API do n8n e retorna JSON parseado."""
    url = f"{N8N_URL}/api/v1{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "X-N8N-API-KEY": _key(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:400]}")


def list_workflows(limit: int = 50) -> dict:
    return _request("GET", f"/workflows?limit={limit}")


def get_workflow(wf_id: str) -> dict:
    return _request("GET", f"/workflows/{wf_id}")


def create_workflow(name: str, nodes: list, connections: dict, settings: dict = None) -> dict:
    payload = {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": settings or {"executionOrder": "v1"},
    }
    return _request("POST", "/workflows", payload)


def update_workflow(wf_id: str, **fields) -> dict:
    """Atualiza workflow. Campos comuns: name, nodes, connections, settings."""
    # n8n API espera todos os campos básicos no PUT — não é PATCH parcial
    current = get_workflow(wf_id)
    payload = {
        "name": fields.get("name", current["name"]),
        "nodes": fields.get("nodes", current["nodes"]),
        "connections": fields.get("connections", current["connections"]),
        "settings": fields.get("settings", current.get("settings", {"executionOrder": "v1"})),
    }
    return _request("PUT", f"/workflows/{wf_id}", payload)


def activate_workflow(wf_id: str) -> dict:
    return _request("POST", f"/workflows/{wf_id}/activate")


def deactivate_workflow(wf_id: str) -> dict:
    return _request("POST", f"/workflows/{wf_id}/deactivate")


def delete_workflow(wf_id: str) -> dict:
    return _request("DELETE", f"/workflows/{wf_id}")


def list_credentials() -> dict:
    """
    NOTA: a public-api do n8n NÃO suporta GET /credentials por padrão (HTTP 405).
    Pra listar credenciais, abra https://n8n.quirkgrowth.online/credentials na UI.
    Mantido aqui pra futuras versões da API.
    """
    return _request("GET", "/credentials")


def list_executions(wf_id: str = None, limit: int = 10) -> dict:
    qs = f"?limit={limit}"
    if wf_id:
        qs += f"&workflowId={wf_id}"
    return _request("GET", f"/executions{qs}")


def webhook_url(wf_id: str) -> str:
    """Extrai a URL pública do webhook do primeiro node Webhook do workflow."""
    wf = get_workflow(wf_id)
    for n in wf.get("nodes", []):
        if n.get("type") == "n8n-nodes-base.webhook":
            path = n.get("parameters", {}).get("path", "")
            return f"{N8N_URL}/webhook/{path}"
    return None


def _print_workflows(data):
    for w in data.get("data", []):
        active = "ON " if w.get("active") else "off"
        print(f"  {w['id']:25s} | {active} | {w['name']}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    cmd = sys.argv[1]

    try:
        if cmd == "list":
            _print_workflows(list_workflows(50))
        elif cmd == "get":
            wf_id = sys.argv[2]
            print(json.dumps(get_workflow(wf_id), indent=2, ensure_ascii=False))
        elif cmd == "creds":
            for c in list_credentials().get("data", []):
                print(f"  {c['id']:25s} | {c['type']:30s} | {c['name']}")
        elif cmd == "activate":
            print(json.dumps(activate_workflow(sys.argv[2]), indent=2))
        elif cmd == "deactivate":
            print(json.dumps(deactivate_workflow(sys.argv[2]), indent=2))
        elif cmd == "delete":
            print(json.dumps(delete_workflow(sys.argv[2]), indent=2))
        elif cmd == "executions":
            wf_id = sys.argv[2]
            for e in list_executions(wf_id, 10).get("data", []):
                print(f"  {e['id']:20s} | {e.get('status', '?'):10s} | {e.get('startedAt', '?')}")
        elif cmd == "webhook":
            wf_id = sys.argv[2]
            url = webhook_url(wf_id)
            print(url or "(nenhum node Webhook neste workflow)")
        elif cmd == "snapshot":
            wf_id = sys.argv[2]
            path = sys.argv[3]
            wf = get_workflow(wf_id)
            with open(path, "w") as f:
                json.dump(wf, f, indent=2, ensure_ascii=False)
            print(f"Snapshot salvo em {path}")
        else:
            print(f"Comando desconhecido: {cmd}")
            print(__doc__)
            return 1
    except RuntimeError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
