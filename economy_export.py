"""Portable, dependency-free downloads of Studio's aggregate economy observations."""
import csv
from copy import deepcopy
from datetime import datetime, timezone
import io
import json
import zipfile


# key, readable label, unit, required source, scope, interpretation
METRICS = (
    ('wallet', 'Character-wallet Yang', 'Yang', 'players', 'selected population and stage', 'Current wallets; excludes banks and Won.'),
    ('accounts', 'Accounts', 'accounts', 'players', 'selected population and stage', 'Distinct accounts owning characters in this view.'),
    ('activeAccounts', 'Active accounts', 'accounts', 'active', 'selected population and stage', 'Distinct accounts with retained CHARACTER/ITEM log activity during the selected period.'),
    ('medianWallet', 'Median account wallet', 'Yang', 'players', 'selected population and stage', 'Median of character wallets aggregated by account; includes dormant accounts.'),
    ('top10Share', 'Top 10% wallet share', 'percent', 'players', 'selected population and stage', 'Percentage of wallet Yang held by the wealthiest 10% of accounts, rounded up.'),
    ('won', 'Wallet Won', 'Won', 'players', 'selected population and stage', 'Separate currency; never converted into Yang.'),
    ('turnover', 'Recorded shop turnover', 'Yang', 'sales', 'selected population and stage', 'Completed positive Yang-only shop sales; GM involvement follows the population rules.'),
    ('trades', 'Completed shop trades', 'transactions', 'sales', 'selected population and stage', 'Count of included Yang-only settlement records.'),
    ('buyers', 'Distinct shop buyers', 'characters', 'sales', 'selected population and stage', 'Distinct buyer characters, not accounts.'),
    ('stock', 'Held item units', 'units', 'stock', 'selected population and stage', 'Includes equipped and listed units. Account storage has no stage and appears with All levels only.'),
    ('attempts', 'Upgrade attempts', 'attempts', 'refines', 'selected population and stage', 'Success flags 0/1 only; excludes downgrade detail rows.'),
    ('successes', 'Successful upgrades', 'attempts', 'refines', 'selected population and stage', 'Successful upgrade attempts; conversion is not destruction.'),
    ('successRate', 'Upgrade success rate', 'percent', 'refines', 'selected population and stage', 'Observed successes / attempts; unavailable with no attempts.'),
    ('scrollAttempts', 'Named scroll upgrade attempts', 'attempts', 'refines', 'selected population and stage', 'Scroll method is not proof of protection or exact consumption.'),
    ('burns', 'Refine destruction records', 'log records', 'actions', 'selected population and stage', 'REMOVE (REFINE FAIL) records, not a reconstructed unit count.'),
    ('recordedIn', 'Mixed global recorded Yang in', 'Yang', 'money', 'mixed global; includes possible GM activity', 'Partial signed money_log; has no actor identity and ignores population/stage filters.'),
    ('recordedOut', 'Mixed global recorded Yang out', 'Yang', 'money', 'mixed global; includes possible GM activity', 'Partial signed money_log; not a complete currency reconciliation.'),
    ('recordedNet', 'Mixed global recorded Yang balance', 'Yang', 'money', 'mixed global; includes possible GM activity', 'Recorded in minus out; does not establish inflation.'),
)
FILTER_KEYS = ('population', 'stage', 'days', 'early', 'mid', 'classification')
CONTEXT = ('observed_at_utc',) + FILTER_KEYS
SNAPSHOT_CONTEXT = ('snapshot_id', 'captured_at_utc') + FILTER_KEYS + ('source_availability',)
ITEM_SOURCES = dict.fromkeys(('stock', 'equipped', 'listed', 'stockChange'), 'stock')
ITEM_SOURCES.update(dict.fromkeys(('sales', 'unitsSold', 'turnover', 'unitPrice', 'priceChange'), 'sales'))
ITEM_SOURCES.update(dict.fromkeys(('acquisitions', 'uses', 'npcSales', 'burns'), 'actions'))


def utc(at):
    return datetime.fromtimestamp(at, timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def filename(data, extension):
    config = data['filters']
    stamp = datetime.fromtimestamp(data['export']['at'], timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f"metin2-economy-{stamp}-{config['population']}-{config['stage']}-{config['days']}d.{extension}"


def csv_bytes(headers, rows):
    def cell(value):
        # Keep numeric negatives numeric. Escape formula-like catalog / journal text.
        if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n'))):
            return "'" + value
        return value
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\r\n')
    writer.writerow(headers)
    writer.writerows([cell(value) for value in row] for row in rows)
    return output.getvalue().encode('utf-8-sig')


def metric_value(metrics, key, source, available):
    return metrics.get(key) if available is None or source in available else None


def normalise(data):
    # UI cells already check source availability; exports must preserve that meaning
    # in the underlying values as well, including older collector zero defaults.
    data = deepcopy(data)
    available = set(data['available'])
    for key, _, _, source, _, _ in METRICS:
        data['metrics'][key] = metric_value(data['metrics'], key, source, available)
    for row in data['items']:
        for key, source in ITEM_SOURCES.items():
            if source not in available:
                row[key] = None
    for row in data['bands']:
        for key, source in (('accounts', 'players'), ('characters', 'players'), ('active', 'active'), ('wallet', 'players'), ('turnover', 'sales'), ('attempts', 'refines')):
            if source not in available:
                row[key] = None
    if 'sales' not in available:
        data['prices'].update(percent=None, matched=None)
    for key in ('accounts', 'wallet', 'involvedTrades'):
        if not data['gm']['identified'] or ('sales' if key == 'involvedTrades' else 'players') not in available:
            data['gm'][key] = None
    for row in data['snapshots'] + data['legacySnapshots']:
        for key, _, _, source, _, _ in METRICS:
            row['metrics'][key] = metric_value(row['metrics'], key, source, row.get('available'))
    return data


def spreadsheet_tables(data):
    """Flat tables with explicit filter context and blank unavailable measurements."""
    filters, available = data['filters'], set(data['available'])
    context = [utc(data['at'])] + [filters.get(key) for key in FILTER_KEYS]
    def table(headers, rows):
        return csv_bytes(CONTEXT + tuple(headers), (context + list(row) for row in rows))
    summary = []
    for key, label, unit, source, scope, definition in METRICS:
        value = metric_value(data['metrics'], key, source, available)
        status = 'unavailable' if source not in available else 'insufficient data' if value is None else 'observed'
        summary.append([key, label, value, unit, status, scope, definition])
    summary.extend([
        ['priceMovement', 'Comparable goods price movement', data['prices']['percent'], 'percent', 'unavailable' if 'sales' not in available else 'observed' if data['prices']['percent'] is not None else 'insufficient data', 'selected population and stage', 'Adjacent equal-length periods; exact commodity IDs, >=5 trades in each period and >=3 matched IDs. Equal-weight geometric change, not a fixed-basket inflation index.'],
        ['matchedPriceItems', 'Matched commodity item IDs', data['prices']['matched'] if 'sales' in available else None, 'item IDs', 'observed' if 'sales' in available else 'unavailable', 'selected population and stage', 'Number of exact commodity IDs meeting the minimum-trade requirement in both periods.'],
    ])
    for key, label, unit in (('accounts', 'Identified GM accounts', 'accounts'), ('wallet', 'Identified GM wallet Yang', 'Yang'), ('involvedTrades', 'GM-involved shop trade records', 'transactions')):
        source = 'sales' if key == 'involvedTrades' else 'players'
        known = data['gm']['identified'] and source in available
        summary.append(['gm_' + key, label, data['gm'][key] if known else None, unit, 'observed' if known else 'unavailable', 'all GM accounts; all levels', 'Context outside the selected population/stage; GM trade records can include Won or non-positive Yang.'])
    tables = {'summary.csv': table(('metric', 'label', 'value', 'unit', 'availability', 'scope', 'definition'), summary)}

    fields = ('id', 'name', 'category', 'grade', 'stock', 'equipped', 'listed', 'stockChange', 'sales', 'unitsSold', 'turnover', 'unitPrice', 'priceChange', 'acquisitions', 'uses', 'npcSales', 'burns')
    item_headers = ('item_id', 'item_name', 'category', 'catalog_upgrade_grade', 'held_units', 'equipped_units', 'listed_units', 'stock_change_units', 'shop_sales', 'units_sold', 'turnover_yang', 'median_unit_price_yang', 'commodity_price_change_percent', 'acquisition_records', 'use_records', 'npc_sale_records', 'destruction_records')
    tables['items.csv'] = table(item_headers + ('stock_available', 'sales_available', 'action_logs_available'),
        ([row.get(key) if key not in ITEM_SOURCES or ITEM_SOURCES[key] in available else None for key in fields] + [source in available for source in ('stock', 'sales', 'actions')] for row in data['items']))
    band_fields = (('accounts', 'players'), ('characters', 'players'), ('active', 'active'), ('wallet', 'players'), ('turnover', 'sales'), ('attempts', 'refines'))
    tables['progression.csv'] = table(('band', 'level_min', 'level_max', 'accounts', 'characters', 'active_accounts', 'wallet_yang', 'turnover_yang', 'upgrade_attempts', 'scope'),
        ([row['key'], 1 if row['key'] == 'early' else filters['early'] + 1 if row['key'] == 'mid' else filters['mid'] + 1,
          filters['early'] if row['key'] == 'early' else filters['mid'] if row['key'] == 'mid' else None] +
         [row[key] if source in available else None for key, source in band_fields] +
         ['selected population; every stage regardless of stage filter; accounts may appear in multiple bands'] for row in data['bands']))
    tables['bank_balances.csv'] = table(('bank', 'yang', 'won', 'scope'),
        (list(row) + ['selected population; all levels regardless of stage filter'] for row in data['banks']))
    for name, key in (('yang_flows.csv', 'type'), ('yang_daily.csv', 'date')):
        tables[name] = table((key, 'recorded_in_yang', 'recorded_out_yang', 'scope'),
            ([row[key], row['created'], row['removed'], 'mixed global; includes possible GM activity; partial coverage'] for row in data['money' if key == 'type' else 'daily']))
    tables['activity.csv'] = table(('record_type', 'target_id_or_action', 'log_records', 'unit'),
        ([kind, key, count, 'log records; not item units'] for kind, rows in (('metin_or_boss_kills', data['activity']), ('item_or_character_action', data['actionTotals'])) for key, count in sorted(rows.items())))
    tables['upgrade_methods.csv'] = table(('method', 'upgrade_attempts'), sorted(data['methods'].items()))
    tables['configured_sources.csv'] = table(('target_id', 'target_name', 'level', 'kind', 'distinct_item_ids', 'shared_pools', 'definition_groups', 'scope'),
        ([row['id'], row['name'], row['level'], row['kind'], row['items'], row['pools'], json.dumps(row['groups'], ensure_ascii=False), 'saved definitions; all populations and levels; not measured drop production'] for row in data['sources']))

    for prefix, snapshots in (('', data['snapshots']), ('legacy_', data['legacySnapshots'])):
        def snapshot_context(row):
            return [row['id'], utc(row['at'])] + [row['filters'].get(key) for key in FILTER_KEYS] + [','.join(row['available']) if 'available' in row else 'not recorded; stored metrics only']
        tables[prefix + 'snapshots.csv'] = csv_bytes(SNAPSHOT_CONTEXT + tuple(row[0] for row in METRICS),
            (snapshot_context(row) + [metric_value(row['metrics'], key, source, row.get('available')) for key, _, _, source, _, _ in METRICS] for row in snapshots))
        tables[prefix + 'snapshot_items.csv'] = csv_bytes(SNAPSHOT_CONTEXT + ('item_id', 'held_units'),
            (snapshot_context(row) + [item['id'], item['stock']] for row in snapshots for item in row['items']))
    tables['journal.csv'] = csv_bytes(('note_id', 'saved_at_utc', 'title', 'body', 'scope'),
        ([row['id'], utc(row['at']), row['title'], row['body'], 'all saved Studio notes; not tied to filters'] for row in data['notes']))
    coverage = list(data['coverage']) + [['Collection', 'Live database' if data['connected'] else 'Offline', data.get('error', data['export']['observation'])]]
    coverage += [['Report alert', 'Review', message] for message in data['alerts']]
    tables['coverage.csv'] = table(('measurement', 'status', 'explanation'), coverage)
    tables['item_ownership_flows.csv'] = table(('item_id','account_owners','largest_owner_share_percent','studio_quest_in_units','studio_quest_out_units','scope'),
        ([row['id'],row.get('owners'),row.get('topOwnerShare'),row.get('scriptIn'),row.get('scriptOut'),'Inventory deltas from instrumented Studio quests only; excludes ordinary loot/crafting/refining'] for row in data['items']))
    tables['watchlist_history.csv'] = table(('item_id','observation_utc','held_units','listed_units','trades_in_window','median_unit_price_yang'),
        ([watch['id'],utc(point['at']),point.get('stock'),point.get('listed'),point.get('sales'),point.get('unitPrice')] for watch in data.get('watchlist',[]) for point in watch['history']))
    tables['equipment_access.csv'] = table(('catalog_grade','held_units','account_owners','active_owners','active_accounts','active_access_percent'),
        ([row.get(key) for key in ('grade','units','owners','activeOwners','activeAccounts','activeAccessPercent')] for row in data.get('rarity',[])))
    tables['refinement_steps.csv'] = table(('logged_item_name','raw_step','success_flag','method','attempts','step_semantics'),
        ([row['itemName'],row['rawStep'],row['success'],row['method'],row['attempts'],'raw engine label; numerical upgrade grade is unverified'] for row in data.get('refineSteps',[])))
    tables['review_queue.csv'] = table(('item_id','item_name','reasons','held_units','trades','status'),
        ([row['item'],row['name'],' | '.join(row['reasons']),row['stock'],row['sales'],row['confidence']] for row in data.get('reviewQueue',[])))
    tables['experiments.csv'] = csv_bytes(('id','baseline_at_utc','title','hypothesis','filters','items','changeset','finished_at_utc','baseline_metrics','after_metrics'),
        ([row['id'],utc(row['at']),row['title'],row['hypothesis'],json.dumps(row['filters']),','.join(row['items']),row['changeset'],utc(row['finished']) if row['finished'] else '',json.dumps(row['baseline']['metrics']),json.dumps(row['outcome']['metrics']) if row['outcome'] else ''] for row in data.get('experiments',[])))

    return tables


def download(data, format):
    if format not in ('zip', 'json'):
        raise ValueError('Choose a CSV pack (zip) or JSON export.')
    data = normalise(data)
    raw = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    if format == 'json':
        return raw, 'application/json; charset=utf-8', filename(data, 'json')
    readme = f"""METIN2 SERVER STUDIO - ECONOMY EXPORT
Exported (UTC): {utc(data['export']['at'])}
Observed (UTC): {utc(data['at'])}
Database connected: {data['connected']}
Selected filters: {json.dumps(data['filters'], sort_keys=True)}

Unzip this folder and open the CSV tables in Excel, LibreOffice or another
analysis tool. Files use UTF-8 with a BOM, comma separators and UTC timestamps.
Percent values use 12.5 for 12.5%, rather than 0.125. Numeric values are not
rounded for display. Blank measurements mean unavailable / insufficient data,
not zero. Availability columns and coverage.csv explain missing sources.
Potential spreadsheet formulas in text are prefixed with an apostrophe.
report.json contains the original, unescaped aggregate data.

summary.csv: metrics, units, scope, availability and definitions.
items.csv: ALL item rows in the selected population/stage/period, independent
of table search, category, grade, sort or pagination. Event records are not
consumption quantities. stock_change_units compares with the report baseline;
it is blank until a comparable snapshot is at least one minute old.
progression.csv: every stage for the selected population; cross-stage accounts
can appear in several bands. Bank balances also cover all levels.
yang_flows.csv / yang_daily.csv: MIXED GLOBAL, including possible GM activity.
These do not follow population/stage filters; coverage is partial.
activity.csv / upgrade_methods.csv: observed log records and upgrade attempts.
configured_sources.csv: all saved definitions; not production measurements.
snapshots.csv / snapshot_items.csv: ALL matching saved snapshots and stocks,
including history beyond the dashboard's 90-point chart. Snapshots store
aggregate metrics, bands and per-ID stock, prices and demand when available. Older snapshots retain their original fields.
Older snapshots may lack source availability; their stored zeros are not
evidence that a source was available.
legacy_snapshots.csv / legacy_snapshot_items.csv: earlier mixed definitions,
kept SEPARATE and excluded from current baselines. Compare matching filters
and classification versions only. Do not join snapshot tables by time alone;
use snapshot_id. A lower stock can reflect transfers or stage movement.
journal.csv: ALL saved notes, across filters, beyond the dashboard's 50 notes.
coverage.csv: source limitations, offline status and sample alerts.
report.json: complete selected report, matching saved history and journal.

GM status applies to the whole account, including alts and storage. Regular
economy contains known humans and bots, excludes GM assets and trades involving
either GM party. Historical GM gifts held by ordinary accounts cannot be traced.
Everyone includes GMs; GM-only includes trades involving either GM party.
Yang and Won remain separate. Won trades are excluded from Yang turnover/prices.
Exports do not modify game data or save a snapshot. Collection may use the
latest cached observation (up to 60 seconds). No raw player/account IDs,
login names, passwords or transaction records are collected for these exports.
Journal text is included as entered by the user.
"""
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('README.txt', readme.encode('utf-8'))
        archive.writestr('report.json', raw)
        for name, contents in spreadsheet_tables(data).items():
            archive.writestr(name, contents)
    return output.getvalue(), 'application/zip', filename(data, 'zip')
