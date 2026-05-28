#!/usr/bin/env python3
"""
resolve_interests.py — Resolve nomes de interests/behaviors/work_positions
da Meta Marketing API para IDs numéricos do catálogo Detailed Targeting.

Pra que serve:
  Substituir, no prompt extrator do Quirk Auto Ads, os {"name": "Luxury goods"}
  por {"id": "6003107902433", "name": "Luxury goods"}. Mais robusto: nome pode
  mudar de tradução no catálogo Meta, ID é permanente.

Uso:
  1. Pega um access_token de System User com escopo ads_read (mesmo usado no
     Make pelo D.1-D.4) — pode ser o token guardado no Data Store.
  2. Define como variável de ambiente:
       export META_ACCESS_TOKEN="EAA..."
  3. Roda:
       python3 resolve_interests.py
  4. Saída em 2 arquivos no mesmo diretório:
       - interests_ids.json   (machine-readable, top 3 matches por item)
       - resolve_report.md    (human-readable, pra você revisar e escolher)

Dependências: só biblioteca padrão do Python 3.7+. Sem pip install nada.

Opções:
  --dry-run     Não chama a API; só lista o que seria pesquisado.
  --locale XX   Locale dos resultados (default: pt_BR).
  --quiet       Suprime logs intermediários.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

API_VERSION = "v25.0"
GRAPH_URL = f"https://graph.facebook.com/{API_VERSION}"
DEFAULT_LOCALE = "pt_BR"
RATE_LIMIT_SLEEP = 0.4  # 400ms entre chamadas, conservador

# ============================================================
# LISTA MESTRE — extraída de APLICAR_NO_MAKE_PROMPT_E_D2.md
# Mantém em sincronia com a tabela do prompt extrator.
# ============================================================
ITEMS_TO_RESOLVE = {
    "adinterest": [
        # Pub Quirk 1 (viajantes)
        "Travel",
        "Frequent travelers",
        "Hotels",
        # Pub Quirk 1.1-1.5 (condomínio, portais, construção)
        "Gated community",
        "Single-family detached home",
        "Real estate investing",
        "Real estate",
        "OLX Brasil",
        "Zap Imóveis",
        "VivaReal",
        "Real estate development",
        "Construction",
        # Pub Quirk 2 (médio/alto)
        "Investment",
        # Pub Quirk 3-7 (luxo/internacional)
        "International travel",
        "Luxury hotels",
        "Luxury goods",
        "Luxury vehicles",
        "Fine dining",
        # Pub Quirk 7 (nichos)
        "Boating",
        "Golf",
        "Swimming pools",
        "Helicopters",
        # Pub Quirk Invest
        "Stock market",
        "Passive income",
        "Personal finance",
        # Pub Corretores
        "Real estate broker",
        "Real estate agency",
        # Profissões (alguns são interests em vez de work_positions)
        "Medicine",
        "Law",
        "Healthcare",
    ],
    "adTargetingCategory": [
        # Behaviors — type=adTargetingCategory + class=behaviors
        "Frequent international travelers",
        "Frequent travelers",
        "Engaged shoppers",
    ],
    "adworkposition": [
        # Cargos profissionais — demographics > job titles
        "Physician",
        "Lawyer",
        "Dentist",
        "Judge",
        "Civil servant",
        "Manager",
        "Business owner",
        "Engineer",
        "Architect",
        "Real estate agent",
        "Real estate broker",
    ],
}


def log(msg, quiet=False):
    if not quiet:
        print(msg, flush=True)


def graph_search(item_type, query, access_token, locale, extra_params=None):
    """Faz GET no /search da Graph API e devolve a lista de resultados."""
    params = {
        "type": item_type,
        "q": query,
        "locale": locale,
        "limit": 5,
        "access_token": access_token,
    }
    if extra_params:
        params.update(extra_params)

    url = f"{GRAPH_URL}/search?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return {"ok": True, "data": payload.get("data", [])}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return {"ok": False, "error": f"HTTP {e.code}: {body[:300]}"}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"Network error: {e.reason}"}
    except Exception as e:
        return {"ok": False, "error": f"Unexpected: {type(e).__name__}: {e}"}


def resolve_all(access_token, locale, quiet=False):
    """Itera por todos os itens e devolve mapa resolvido."""
    resolved = {}
    failures = []

    total = sum(len(items) for items in ITEMS_TO_RESOLVE.values())
    count = 0

    for item_type, names in ITEMS_TO_RESOLVE.items():
        log(f"\n=== Tipo: {item_type} ({len(names)} itens) ===", quiet)
        resolved[item_type] = {}

        for name in names:
            count += 1
            log(f"  [{count}/{total}] Buscando: {name!r}...", quiet)

            extra = {"class": "behaviors"} if item_type == "adTargetingCategory" else None
            result = graph_search(item_type, name, access_token, locale, extra)

            if not result["ok"]:
                log(f"    ✗ Falhou: {result['error']}", quiet)
                failures.append({"type": item_type, "query": name, "error": result["error"]})
                resolved[item_type][name] = None
            elif not result["data"]:
                log(f"    ⚠ Nenhum resultado", quiet)
                resolved[item_type][name] = []
            else:
                top3 = result["data"][:3]
                resolved[item_type][name] = top3
                best = top3[0]
                size_str = ""
                lower = best.get("audience_size_lower_bound")
                upper = best.get("audience_size_upper_bound")
                if lower and upper:
                    size_str = f"  [tamanho: {lower:,}-{upper:,}]"
                log(f"    ✓ {best.get('id')} — {best.get('name')}{size_str}", quiet)

            time.sleep(RATE_LIMIT_SLEEP)

    return resolved, failures


def write_json_output(resolved, out_path):
    """Salva o JSON machine-readable."""
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "api_version": API_VERSION,
                "data": resolved,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def write_markdown_report(resolved, failures, out_path):
    """Salva o relatório human-readable."""
    lines = []
    lines.append("# Resolução de IDs — Resultado")
    lines.append(f"\n**Gerado em:** {datetime.utcnow().isoformat()}Z")
    lines.append(f"**API:** {API_VERSION}\n")

    if failures:
        lines.append("## ⚠️ Falhas\n")
        for f in failures:
            lines.append(f"- `{f['type']}` / `{f['query']}` → {f['error']}")
        lines.append("")

    for item_type, items in resolved.items():
        lines.append(f"\n## Tipo: `{item_type}`\n")

        for query, matches in items.items():
            if matches is None:
                lines.append(f"### {query}\n\n**Erro ao buscar.** Ver seção de falhas.\n")
                continue

            if not matches:
                lines.append(f"### {query}\n\n**Nenhum resultado.** Tentar variações (PT vs EN, sinônimos).\n")
                continue

            lines.append(f"### {query}\n")
            lines.append("| Rank | ID | Nome retornado | Audience size | Path/Topic |")
            lines.append("|---|---|---|---|---|")
            for i, m in enumerate(matches, 1):
                lower = m.get("audience_size_lower_bound", "—")
                upper = m.get("audience_size_upper_bound", "—")
                size = f"{lower:,}-{upper:,}" if isinstance(lower, int) else "—"
                path = " > ".join(m.get("path", [])) if m.get("path") else (m.get("topic") or "—")
                lines.append(
                    f"| {i} | `{m.get('id')}` | {m.get('name')} | {size} | {path} |"
                )
            lines.append("")

    lines.append("\n---\n")
    lines.append("## Próximo passo")
    lines.append("\nRevisar cada item acima:")
    lines.append("- ✓ Se o rank 1 está claramente certo → usar o ID dele.")
    lines.append("- ⚠ Se ambíguo (múltiplos parecidos) → escolher manualmente o que tem audience size compatível com o público-alvo da Quirk (BR).")
    lines.append("- ✗ Se nenhum resultado → tentar variação do nome (PT, sinônimo) ou remover do template.")
    lines.append("\nDepois, atualizar `APLICAR_NO_MAKE_PROMPT_E_D2.md` substituindo `{\"name\": \"X\"}` por `{\"id\": \"Y\", \"name\": \"X\"}`.")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Não chama a API; lista o que seria pesquisado.")
    parser.add_argument("--locale", default=DEFAULT_LOCALE, help=f"Locale dos resultados (default: {DEFAULT_LOCALE})")
    parser.add_argument("--quiet", action="store_true", help="Suprime logs intermediários")
    parser.add_argument("--out-dir", default=".", help="Diretório de saída (default: diretório atual)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    json_out = out_dir / "interests_ids.json"
    md_out = out_dir / "resolve_report.md"

    if args.dry_run:
        log("=== DRY RUN ===")
        total = sum(len(items) for items in ITEMS_TO_RESOLVE.values())
        log(f"Total de itens a resolver: {total}")
        for item_type, names in ITEMS_TO_RESOLVE.items():
            log(f"\n[{item_type}] ({len(names)} itens):")
            for n in names:
                log(f"  - {n}")
        log(f"\nLocale: {args.locale}")
        log(f"Saída: {json_out}, {md_out}")
        log("\nPara rodar de verdade, remova --dry-run e defina META_ACCESS_TOKEN.")
        return 0

    token = os.environ.get("META_ACCESS_TOKEN")
    if not token:
        print("ERRO: variável META_ACCESS_TOKEN não definida.", file=sys.stderr)
        print("Faça: export META_ACCESS_TOKEN=\"EAA...\" antes de rodar.", file=sys.stderr)
        return 1

    log(f"Iniciando resolução — locale={args.locale}, API={API_VERSION}")
    log(f"Rate limit: {RATE_LIMIT_SLEEP}s entre chamadas")

    start = time.time()
    resolved, failures = resolve_all(token, args.locale, args.quiet)
    elapsed = time.time() - start

    log(f"\n=== Concluído em {elapsed:.1f}s ===")
    log(f"Falhas: {len(failures)}")

    write_json_output(resolved, json_out)
    write_markdown_report(resolved, failures, md_out)

    log(f"\n✓ JSON: {json_out}")
    log(f"✓ Relatório: {md_out}")
    log("\nAbra resolve_report.md pra revisar cada item e decidir os IDs.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
