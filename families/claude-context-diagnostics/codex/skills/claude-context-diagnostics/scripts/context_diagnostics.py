"""Bounded metadata-only diagnostics for an exact Claude Code JSONL session."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import uuid

VERSION = '0.1.1'
MAX_RECORD = 16 * 1024 * 1024


class DiagnosticError(Exception):
    pass


def number(value):
    return value if type(value) is int and value >= 0 else None


def identifier(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', value) else None


def session_uuid(value):
    try:
        parsed = str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise DiagnosticError('An exact session UUID is required.') from None
    if value.lower() != parsed:
        raise DiagnosticError('An exact session UUID is required.')
    return parsed


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z') if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def seconds(before, after):
    a, b = timestamp(before), timestamp(after)
    if a is None or b is None:
        return None
    value = (datetime.fromisoformat(b.replace('Z', '+00:00')) - datetime.fromisoformat(a.replace('Z', '+00:00'))).total_seconds()
    return round(value, 3) if value >= 0 else None


def text_chars(content):
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(b.get('text', '')) for b in content if isinstance(b, dict) and isinstance(b.get('text'), str))
    return 0


def basename(value):
    if not isinstance(value, str):
        return None
    leaf = value.replace('\\', '/').rsplit('/', 1)[-1]
    # Treat paths as untrusted metadata; strip controls and formatting delimiters.
    return re.sub(r'[^A-Za-z0-9_. -]', '_', leaf)[:80] or None


def usage_metadata(message):
    usage = message.get('usage')
    if not isinstance(usage, dict) or number(usage.get('input_tokens')) is None:
        return None
    keys = ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens', 'output_tokens')
    clean = {k:number(usage.get(k)) for k in keys}
    # Anthropic omits cache counters when unused. Explicit invalid values stay unknown.
    for key in keys[1:3]:
        if key not in usage:
            clean[key] = 0
    clean['total_input_tokens'] = sum(clean[k] for k in keys[:3]) if all(clean[k] is not None for k in keys[:3]) else None
    return clean


def resolve_transcript(home, sid, explicit=None):
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise DiagnosticError('The explicit transcript is unavailable.')
        return path
    projects = home / 'projects'
    if not projects.is_dir():
        raise DiagnosticError('Claude projects directory is unavailable; supply --claude-home or --transcript.')
    matches = [p for p in projects.glob(f'*/{sid}.jsonl') if p.is_file()]
    if len(matches) != 1:
        raise DiagnosticError('Exact transcript is missing or ambiguous; supply --transcript with the same session ID.')
    return matches[0]


def read_nodes(path, sid):
    nodes = {}
    leaf = None
    matched = False
    counts = {'duplicate_uuids':0, 'malformed_records':0, 'oversized_records':0, 'foreign_session_records':0, 'sidechain_records':0, 'trailing_partial_bytes':0, 'unsupported_conversation_records':0, 'invalid_parent_references':0, 'invalid_timestamps':0}
    with path.open('rb') as source:
        initial = os.fstat(source.fileno())
        limit = initial.st_size
        while source.tell() < limit:
            raw = source.readline(min(MAX_RECORD + 1, limit - source.tell()))
            if len(raw) > MAX_RECORD:
                counts['oversized_records'] += 1
                while raw and not raw.endswith(b'\n') and source.tell() < limit:
                    raw = source.readline(min(MAX_RECORD + 1, limit - source.tell()))
                continue
            if not raw.endswith(b'\n'):
                counts['trailing_partial_bytes'] = len(raw)
                break
            try:
                item = json.loads(raw)
            except (ValueError, UnicodeError):
                counts['malformed_records'] += 1
                continue
            if not isinstance(item, dict):
                counts['malformed_records'] += 1
                continue
            if item.get('sessionId') == sid:
                matched = True
            if item.get('sessionId') and item['sessionId'] != sid:
                counts['foreign_session_records'] += 1
                continue
            if item.get('isSidechain'):
                counts['sidechain_records'] += 1
                continue
            kind = item.get('type')
            conversation = kind in ('user','assistant','system')
            uid = identifier(item.get('uuid'))
            if uid is None:
                if kind in ('user','assistant','system'):
                    counts['unsupported_conversation_records'] += 1
                continue
            msg = item.get('message') or {}
            if not isinstance(msg, dict):
                counts['unsupported_conversation_records'] += 1
                continue
            if not conversation and kind not in ('attachment','progress'):
                counts['unsupported_conversation_records'] += 1
            boundary = kind == 'system' and item.get('subtype') == 'compact_boundary'
            meta = item.get('compactMetadata') or {}
            if not isinstance(meta, dict):
                meta = {}
            parent_value=item.get('parentUuid')
            logical_value=item.get('logicalParentUuid') if boundary else None
            parent=identifier(parent_value);logical_parent=identifier(logical_value)
            invalid_references=sum(value is not None and cleaned is None for value,cleaned in ((parent_value,parent),(logical_value,logical_parent)))
            counts['invalid_parent_references'] += invalid_references
            recorded_at=timestamp(item.get('timestamp'))
            if item.get('timestamp') is not None and recorded_at is None:
                counts['invalid_timestamps'] += 1
            node = {'uuid':uid, 'parent':parent, 'logical_parent':logical_parent,
                    'invalid_ancestry':bool(invalid_references),
                    'timestamp':recorded_at, 'kind':kind, 'tools':[], 'results':[],
                    'usage':usage_metadata(msg) if kind == 'assistant' and not item.get('isApiErrorMessage') else None,
                    'request':identifier(item.get('requestId')) or identifier(msg.get('id')) or uid,
                    'model':identifier(msg.get('model'))}
            if boundary:
                node['compact'] = {k:number(meta.get(k)) for k in ('preTokens','postTokens','durationMs')}
                node['compact']['trigger'] = meta.get('trigger') if meta.get('trigger') in ('auto','manual') else 'unknown'
            content = msg.get('content')
            if conversation and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get('type') == 'tool_use':
                        inp = block.get('input') or {}
                        node['tools'].append({'tool_id':identifier(block.get('id')), 'tool':identifier(block.get('name')) or 'other',
                                              'file':basename(inp.get('file_path')) if isinstance(inp, dict) else None})
                    elif block.get('type') == 'tool_result':
                        node['results'].append({'tool_id':identifier(block.get('tool_use_id')), 'characters':text_chars(block.get('content'))})
            if uid in nodes:
                counts['duplicate_uuids'] += 1
            nodes[uid] = node
            if conversation:
                leaf = uid
        final = os.fstat(source.fileno())
    if not matched:
        raise DiagnosticError('Transcript does not establish the requested session identity.')
    if leaf is None:
        raise DiagnosticError('No supported mainline conversation records were found.')
    current = path.stat()
    changed = (initial.st_dev, initial.st_ino) != (current.st_dev, current.st_ino) or final.st_size < limit
    if changed:
        raise DiagnosticError('Transcript was replaced or truncated while being read; no report emitted.')
    return nodes, leaf, counts, {'bytes':limit, 'grew_during_read':final.st_size > limit, 'modified_at_start':datetime.fromtimestamp(initial.st_mtime, timezone.utc).isoformat().replace('+00:00','Z')}


def build_report(nodes, leaf, counts, snapshot, sid, cycles=5, top=5):
    chain, seen, warnings = [], set(), []
    ancestry_complete=True
    invalid_ancestry=False
    current = leaf
    while current:
        if current in seen:
            ancestry_complete=False
            warnings.append('Parent ancestry contains a cycle; history is incomplete.')
            break
        seen.add(current)
        node = nodes.get(current)
        if node is None:
            ancestry_complete=False
            warnings.append('A parent record is unavailable; history is incomplete.')
            break
        chain.append(node)
        if node.get('invalid_ancestry'):
            ancestry_complete=False;invalid_ancestry=True
        current = node['parent'] or node['logical_parent']
    chain.reverse()
    if invalid_ancestry:
        warnings.append('Selected ancestry contains an invalid parent reference; history is incomplete.')
    if counts['malformed_records'] or counts['oversized_records'] or counts['unsupported_conversation_records']:
        warnings.append('Unsupported, malformed or oversized conversation records were skipped; telemetry may be incomplete.')
    if counts['trailing_partial_bytes']:
        warnings.append('A trailing incomplete append was excluded from the snapshot.')
    if counts['invalid_timestamps']:
        warnings.append('Invalid timestamps were omitted; time-based telemetry may be incomplete.')
    tools = {t['tool_id']:t for n in chain for t in n['tools'] if t['tool_id']}
    # A single assistant response may be serialized as several content-block rows.
    last_requests = {n['request']:n['uuid'] for n in chain if n['usage'] is not None}
    compactions, results, growth = [], [], []
    previous = latest = None
    intervening = []
    result_ids = set()
    segment = 0
    boundary_count = sum('compact' in n for n in chain)
    first_scope = max(1,boundary_count-cycles+1) if boundary_count else 0
    for node in chain:
        if 'compact' in node:
            boundary = {'timestamp':node['timestamp'], **node['compact'], 'first_observed_input_after':None,
                        'seconds_since_previous':seconds(compactions[-1]['timestamp'],node['timestamp']) if compactions else None}
            compactions.append(boundary)
            segment += 1
            previous = None
            intervening = []
        for result in node['results']:
            rid = result['tool_id']
            key = rid or node['uuid']
            if key in result_ids:
                continue
            result_ids.add(key)
            row = {'timestamp':node['timestamp'], **result, 'tool':tools.get(rid,{}).get('tool','unknown'), 'file':tools.get(rid,{}).get('file')}
            if segment >= first_scope:
                results.append(row)
            intervening.append(row)
        if node['usage'] is None or last_requests[node['request']] != node['uuid']:
            continue
        latest = {'timestamp':node['timestamp'], 'model':node['model'], **node['usage']}
        total = latest['total_input_tokens']
        if compactions and compactions[-1]['first_observed_input_after'] is None and total is not None:
            compactions[-1]['first_observed_input_after'] = total
        if previous is not None and total is not None and previous['total_input_tokens'] is not None and intervening:
            delta = total - previous['total_input_tokens']
            if delta > 0 and segment >= first_scope:
                growth.append({'timestamp':node['timestamp'], 'observed_input_delta':delta,
                               'intervening_result_characters':sum(r['characters'] for r in intervening),
                               'intervening_results':len(intervening), 'tools':intervening[-3:]})
        previous = latest
        intervening = []
    if latest is None:
        warnings.append('No recorded input usage is available; current usage is unknown.')
    selected = compactions[-cycles:]
    durations = [c['durationMs'] for c in selected if c['durationMs'] is not None]
    report = {'ok':True, 'schema_version':1, 'version':VERSION, 'session_id':sid, 'leaf_uuid':leaf,
              'source':'recorded_mainline_transcript_snapshot', 'snapshot':snapshot, 'coverage':counts,
              'ancestry_complete':ancestry_complete,
              'latest_usage':latest, 'compactions':selected,
              'tool_metrics_scope':{'since_compaction':selected[0]['timestamp'] if selected else None,
                                    'meaning':'Since the earliest shown boundary, or all available ancestry when no boundary exists.'},
              'compaction_summary':{'completed_in_selected_ancestry':len(compactions), 'shown':len(selected),
                                    'shown_duration_seconds':round(sum(durations)/1000,3) if durations else None,
                                    'duration_records_available':len(durations)},
              'largest_tool_results':sorted(results,key=lambda r:r['characters'],reverse=True)[:top],
              'largest_input_growth':sorted(growth,key=lambda r:r['observed_input_delta'],reverse=True)[:top],
              'warnings':warnings,
              'limits':['Latest usage is historical input for a recorded request, not a live context meter or remaining budget.',
                        'Character counts are not token counts; input growth includes other request changes and is not exact per-tool attribution.',
                        'The latest recorded mainline leaf may differ from a branch selected in a still-open UI.',
                        'Completed compaction metadata does not expose an in-progress compaction or effective model capacity.']}
    return report


def report_session(path, sid, cycles=5, top=5, leaf=None):
    sid = session_uuid(sid)
    nodes, default_leaf, counts, snapshot = read_nodes(path, sid)
    chosen = identifier(leaf) if leaf else default_leaf
    if chosen not in nodes:
        raise DiagnosticError('The explicit branch leaf is unavailable in this session.')
    return build_report(nodes,chosen,counts,snapshot,sid,cycles,top)


def bounded(value):
    n = int(value)
    if not 1 <= n <= 10:
        raise argparse.ArgumentTypeError('Use a value from 1 through 10.')
    return n


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['report'])
    parser.add_argument('--session-id',required=True)
    parser.add_argument('--claude-home',default=os.environ.get('CLAUDE_CONFIG_DIR') or str(Path.home()/'.claude'))
    parser.add_argument('--transcript')
    parser.add_argument('--leaf-uuid')
    parser.add_argument('--cycles',type=bounded,default=5)
    parser.add_argument('--top',type=bounded,default=5)
    args = parser.parse_args(argv)
    try:
        sid = session_uuid(args.session_id)
        path = resolve_transcript(Path(args.claude_home).expanduser(),sid,args.transcript)
        report = report_session(path,sid,args.cycles,args.top,args.leaf_uuid)
    except (DiagnosticError,OSError) as exc:
        # Do not serialize OS exception text, which can contain private paths.
        message = str(exc) if isinstance(exc,DiagnosticError) else 'Transcript could not be read.'
        print(json.dumps({'ok':False,'error':message}))
        return 2
    print(json.dumps(report,separators=(',',':'),ensure_ascii=True))
    return 0


if __name__ == '__main__':
    sys.exit(main())
