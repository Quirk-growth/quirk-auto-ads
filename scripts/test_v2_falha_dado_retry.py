#!/usr/bin/env python3
"""Smoke test: falha de dado + RETRY manual.

Cenário: estado pronta_pra_subir + criativo inválido (placehold) → CONFIRMAR → falhou_dado
       → corrige criativo → RETRY → tentativa nova.

Como a conta Meta atual barra por pagamento (estado real), o RETRY também termina em
falhou_dado, mas com tentativas_count incrementado — comprovando que o comando RETRY
foi reconhecido e o fluxo reiniciado.
"""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def reset():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    conn.commit(); conn.close()


def send_text(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_estado():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    row = cur.fetchone(); conn.close()
    return row[0] if row else None


def setup_pronta_pra_subir():
    """Insere conversa direto no DB com brief completo + criativo inválido."""
    brief = {
        'objetivo': 'investimento', 'faixa_valor': 'ate_700k', 'trilho_escolhido': 'precisao',
        'publico_escolhido': 'Pub Quirk Invest',
        'campanha': {'nome': 'Test RETRY', 'objetivo_meta': 'OUTCOME_LEADS', 'verba_diaria': 30, 'periodo': '7 dias'},
        'conjunto': {'idade_min': 30, 'idade_max': 55, 'geo': 'Goiânia', 'geo_cidade': 'Goiânia', 'geo_raio_km': 17, 'limitar': True},
        'anuncio': {'tipo_imovel': 'apartamento', 'valor_imovel': 450000, 'copy': 'teste retry'},
        'targeting_meta': {'geo_locations': {'cities': [{'key': '254063', 'radius': 17, 'distance_unit': 'kilometer'}]},
                           'age_min': 30, 'age_max': 55,
                           'flexible_spec': [{'interests': [{'id': '6003392721577', 'name': 'Investment'}]}]}
    }
    estado = {
        'etapa_atual': 'pronta_pra_subir',
        'criativo': {'recebido': True, 'url': 'https://placehold.co/1080x1080/fff/000/png?text=invalid', 'mimetype': 'image/png', 'recebido_em': 'now'},
        'brief': brief,
        'ultima_tentativa': None
    }
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute("""INSERT INTO auto_ads.conversas (telefone, historico, estado_json, criativo_url)
                   VALUES (%s, 'mock_historico', %s, %s)
                   ON CONFLICT (telefone) DO UPDATE SET estado_json = EXCLUDED.estado_json, criativo_url = EXCLUDED.criativo_url, historico = EXCLUDED.historico""",
                (PHONE, json.dumps(estado), estado['criativo']['url']))
    conn.commit(); conn.close()


def set_criativo(url):
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"""UPDATE auto_ads.conversas
                    SET estado_json = jsonb_set(estado_json, '{{criativo}}',
                        jsonb_build_object('recebido', true, 'url', '{url}', 'mimetype', 'image/jpeg', 'recebido_em', 'now')),
                        criativo_url = '{url}'
                    WHERE telefone = '{PHONE}'""")
    conn.commit(); conn.close()


def main():
    reset()
    setup_pronta_pra_subir()
    print('✓ setup: pronta_pra_subir + criativo inválido')

    print('\n[CONFIRMAR (vai falhar)]')
    send_text('CONFIRMAR')
    time.sleep(70)
    estado = get_estado()
    ult = estado.get('ultima_tentativa') or {}
    print(f"  etapa={estado['etapa_atual']} tentativas_count={ult.get('tentativas_count')} motivo={(ult.get('motivo') or '')[:120]}")
    assert estado['etapa_atual'] in ['falhou_dado', 'falhou_infra'], f"esperava falha; ficou {estado['etapa_atual']}"
    tent1 = ult.get('tentativas_count', 0)

    print('\n[corrige criativo pra URL válida]')
    set_criativo('https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1080')

    print('\n[RETRY]')
    send_text('RETRY')
    time.sleep(70)
    estado = get_estado()
    ult = estado.get('ultima_tentativa') or {}
    print(f"  etapa final={estado['etapa_atual']} tentativas_count={ult.get('tentativas_count')} motivo={(ult.get('motivo') or '')[:120]}")
    assert estado['etapa_atual'] in ['ativa', 'falhou_dado', 'falhou_infra']
    tent2 = ult.get('tentativas_count', 0)
    assert tent2 > tent1, f"tentativas_count não incrementou ({tent1} → {tent2}) — RETRY pode não ter rodado"

    print(f'\n✓ RETRY ciclo completo. Tentativas: {tent1} → {tent2}')


if __name__ == '__main__':
    main()
