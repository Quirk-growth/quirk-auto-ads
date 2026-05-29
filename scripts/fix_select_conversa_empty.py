#!/usr/bin/env python3
"""
BUG: select_conversa retorna 0 rows pra cliente novo (sem conversa registrada).
Quando isso acontece, n8n não dispara o próximo node — o fluxo morre em silêncio.

FIX: trocar a query pra sempre retornar 1 row, com COALESCE pra campos vazios.
Assim a 1ª msg de qualquer cliente novo passa adiante com histórico = ''.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api
import config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)

    new_query = (
        "SELECT $1::text AS telefone, "
        "COALESCE((SELECT historico FROM auto_ads.conversas WHERE telefone = $1), '') AS historico, "
        "COALESCE((SELECT criativo_url FROM auto_ads.conversas WHERE telefone = $1), '') AS criativo_url"
    )

    updated = 0
    for node in wf["nodes"]:
        if node["name"] == "select_conversa":
            node["parameters"]["query"] = new_query
            # garante que queryReplacement está com o phone
            node["parameters"].setdefault("options", {})
            node["parameters"]["options"]["queryReplacement"] = "={{ $('normalize_phone').item.json.telefone_normalizado }}"
            updated += 1
            print(f"  ↻ select_conversa: query agora sempre retorna 1 row (COALESCE)")
        if node["name"] == "media_select_cliente":
            # Sem mudança aqui — não impede o fluxo, mas vou auditar
            pass

    if updated == 0:
        print("ERRO: select_conversa não encontrado")
        sys.exit(1)

    n8n_api.update_workflow(
        WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"],
        settings=wf.get("settings", {"executionOrder": "v1"}),
    )
    print(f"\n✓ Workflow atualizado — primeira msg de cliente novo agora flui corretamente")


if __name__ == "__main__":
    main()
