#!/usr/bin/env python3
"""
classify_intent v8: cobre variações naturais de ALTERAR_GEO que v7 perdia.

Bug observado na sessão de testes:
  "Quero alterar localização de uma campanha" → OUTRO (❌ devia ser ALTERAR_GEO)

Causa: as 2 regexes de geo em v7 eram:
  1. /\b(alterar|mudar|trocar)\s+.{0,15}\bgeo\b/i  ← exige a palavra "geo"
  2. /mudar\s+(de\s+)?(regi[aã]o|cidade|bairro)/i  ← só "mudar", não "alterar"/"trocar"

Gaps corrigidos:
  - "localização" / "localidade" + (alterar|mudar|trocar)
  - "alterar/trocar de região/cidade/bairro" (padrão 2 só tinha "mudar")
  - "alterar a região/cidade/bairro" (sem "de")

Resultado: qualquer forma natural de pedir mudança de geo → ALTERAR_GEO.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


# Apenas as linhas de ALTERAR_GEO atualizadas — o resto de classify_intent não muda
OLD_GEO_PATTERNS = """else if (/\\b(alterar|mudar|trocar)\\s+.{0,15}\\bgeo\\b/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/mudar\\s+(de\\s+)?(regi[aã]o|cidade|bairro)/i.test(msg)) intent = 'ALTERAR_GEO';"""

NEW_GEO_PATTERNS = """else if (/\\b(alterar|mudar|trocar)\\s+.{0,15}\\bgeo\\b/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/(alterar|mudar|trocar)\\s+.{0,20}(localiza[çc][aã]o|localidade)/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/\\b(alterar|mudar|trocar)\\s+(de\\s+|a\\s+|o\\s+)?(regi[aã]o|cidade|bairro)/i.test(msg)) intent = 'ALTERAR_GEO';"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    old_code = nb['classify_intent']['parameters']['jsCode']
    if OLD_GEO_PATTERNS not in old_code:
        print('⚠️  Padrão antigo não encontrado — verifique manualmente.')
        return

    new_code = old_code.replace(OLD_GEO_PATTERNS, NEW_GEO_PATTERNS)
    nb['classify_intent']['parameters']['jsCode'] = new_code
    print('  ↻ classify_intent v8:')
    print('    + localização/localidade → ALTERAR_GEO')
    print('    + alterar/trocar de região/cidade/bairro → ALTERAR_GEO (antes só "mudar")')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ classify_intent v8 aplicado')


if __name__ == '__main__':
    main()
