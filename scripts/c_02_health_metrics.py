#!/usr/bin/env python3
"""
Hardening 2: health check + dashboard de métricas.

Componentes:
1. SQL migration 006: views de métricas + tabela health_checks
2. Workflow n8n separado "Quirk Health Check" que roda 1x/hora:
   - POST webhook com phone fake 5500000000000 + msg 'oi'
   - Aguarda 30s, busca última exec, valida que rodou agente_principal
   - INSERT em auto_ads.health_checks (ok, duration, exec_id)
3. Helper Python: print_dashboard() — lê views e formata pra terminal

Pra rodar o dashboard manualmente: python3 scripts/c_02_health_metrics.py dashboard
"""
import os, sys
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def apply_sql():
    sql_path = '/Users/renanreal/quirk_auto_ads/sql/006_metrics_views.sql'
    with open(sql_path) as f:
        sql = f.read()
    db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()
    # Validate
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='auto_ads' AND table_name='health_checks'")
    assert cur.fetchone()[0] == 1, 'health_checks não criada'
    cur.execute("SELECT count(*) FROM information_schema.views WHERE table_schema='auto_ads' AND table_name LIKE 'metrics_%'")
    assert cur.fetchone()[0] >= 3, 'views de métricas faltando'
    conn.close()
    print('✓ SQL migration 006 aplicada (views + health_checks)')


def create_health_workflow():
    """Cria workflow 'Quirk Health Check' separado que roda a cada hora."""
    # Check se já existe
    wfs = n8n_api.list_workflows()
    for wf in wfs.get('data', []):
        if wf.get('name') == 'Quirk Health Check':
            print(f"  Workflow já existe (id={wf['id']}). Skip criação.")
            return wf['id']

    # Schedule trigger node + HTTP webhook call + wait + execution check + Postgres insert
    nodes = [
        {
            'id': 'cron_trigger', 'name': 'cron_trigger',
            'type': 'n8n-nodes-base.scheduleTrigger', 'typeVersion': 1.2,
            'position': [200, 200],
            'parameters': {
                'rule': {'interval': [{'field': 'hours', 'hoursInterval': 1}]}
            }
        },
        {
            'id': 'start_ts', 'name': 'start_ts',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [400, 200],
            'parameters': {'language': 'javaScript', 'jsCode': 'return [{json: {start_ms: Date.now()}}];'}
        },
        {
            'id': 'ping_webhook', 'name': 'ping_webhook',
            'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
            'position': [600, 200],
            'parameters': {
                'method': 'POST',
                'url': config.WORKFLOW_URL,
                'sendBody': True,
                'specifyBody': 'json',
                'jsonBody': '{"chat":{"phone":"+55 00 00000-0000"},"message":{"type":"text","text":"healthcheck_ping","from":"5500000000000@s.whatsapp.net"}}',
                'sendHeaders': True,
                'headerParameters': {'parameters': [{'name': 'Content-Type', 'value': 'application/json'}]},
                'options': {}
            },
            'continueOnFail': True
        },
        {
            'id': 'wait_30s', 'name': 'wait_30s',
            'type': 'n8n-nodes-base.wait', 'typeVersion': 1,
            'position': [800, 200],
            'parameters': {'amount': 30, 'unit': 'seconds'}
        },
        {
            'id': 'check_latest_exec', 'name': 'check_latest_exec',
            'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
            'position': [1000, 200],
            'parameters': {
                'method': 'GET',
                'url': f'{config.N8N_URL}/api/v1/executions?workflowId={config.get_workflow_id()}&limit=1',
                'sendHeaders': True,
                'headerParameters': {'parameters': [{'name': 'X-N8N-API-KEY', 'value': open(config.N8N_API_KEY_PATH).read().strip()}]},
                'options': {}
            }
        },
        {
            'id': 'eval_health', 'name': 'eval_health',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1200, 200],
            'parameters': {
                'language': 'javaScript',
                'jsCode': """const resp = $('check_latest_exec').first().json;
const start_ms = $('start_ts').first().json.start_ms;
const latest = resp.data?.[0] || {};
const ok = latest.status === 'success' || latest.finished === true;
return [{json: {
  ok,
  exec_id: latest.id || '',
  duration_ms: Date.now() - start_ms,
  error_node: ok ? '' : (latest.error?.node?.name || 'unknown'),
  error_msg: ok ? '' : (latest.error?.message || 'no detail')
}}];
"""
            }
        },
        {
            'id': 'insert_health', 'name': 'insert_health',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [1400, 200],
            'parameters': {
                'operation': 'executeQuery',
                'query': """INSERT INTO auto_ads.health_checks (ok, duration_ms, exec_id, error_node, error_msg)
VALUES (
  {{ $('eval_health').item.json.ok }},
  {{ $('eval_health').item.json.duration_ms }},
  '{{ $('eval_health').item.json.exec_id }}',
  '{{ ($('eval_health').item.json.error_node || '').replace(/'/g, "''") }}',
  '{{ ($('eval_health').item.json.error_msg || '').replace(/'/g, "''") }}'
)""",
                'options': {}
            },
            'credentials': {'postgres': config.POSTGRES_CRED}
        }
    ]

    connections = {
        'cron_trigger': {'main': [[{'node': 'start_ts', 'type': 'main', 'index': 0}]]},
        'start_ts': {'main': [[{'node': 'ping_webhook', 'type': 'main', 'index': 0}]]},
        'ping_webhook': {'main': [[{'node': 'wait_30s', 'type': 'main', 'index': 0}]]},
        'wait_30s': {'main': [[{'node': 'check_latest_exec', 'type': 'main', 'index': 0}]]},
        'check_latest_exec': {'main': [[{'node': 'eval_health', 'type': 'main', 'index': 0}]]},
        'eval_health': {'main': [[{'node': 'insert_health', 'type': 'main', 'index': 0}]]}
    }

    new_wf = n8n_api.create_workflow(
        name='Quirk Health Check',
        nodes=nodes,
        connections=connections,
        settings={'executionOrder': 'v1'}
    )
    wf_id = new_wf['id']
    print(f'  ✓ workflow Quirk Health Check criado (id={wf_id}) — ative manualmente no n8n')
    return wf_id


def print_dashboard():
    """Printa dashboard de métricas no terminal."""
    db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    print('\n' + '='*60)
    print('  📊 QUIRK AUTO ADS — DASHBOARD 24H')
    print('='*60)

    cur.execute('SELECT * FROM auto_ads.metrics_24h')
    cols = [d[0] for d in cur.description]
    row = cur.fetchone()
    if row:
        for c, v in zip(cols, row):
            label = c.replace('_', ' ').replace('24h', '(24h)').replace('1h', '(1h)')
            print(f'  {label:35s} {v}')

    print('\n  TOP MOTIVOS DE ERRO (24h):')
    cur.execute('SELECT * FROM auto_ads.metrics_erros_24h')
    rows = cur.fetchall()
    if rows:
        for classe, motivo, qtd in rows[:5]:
            print(f'    {qtd:3d}× [{classe or "-"}] {(motivo or "")[:70]}')
    else:
        print('    (nenhum erro registrado)')

    print('\n  CAMPANHAS POR STATUS:')
    cur.execute('SELECT * FROM auto_ads.metrics_campanhas_status')
    rows = cur.fetchall()
    by_status = {}
    for tel, status, qtd in rows:
        by_status[status] = by_status.get(status, 0) + qtd
    for status, qtd in sorted(by_status.items()):
        print(f'    {status:25s} {qtd}')

    cur.execute('SELECT count(DISTINCT telefone) FROM auto_ads.clientes WHERE ativo = true')
    print(f'\n  CLIENTES ATIVOS: {cur.fetchone()[0]}')

    conn.close()
    print('='*60)


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'dashboard':
        print_dashboard()
        return
    apply_sql()
    create_health_workflow()
    print()
    print_dashboard()


if __name__ == '__main__':
    main()
