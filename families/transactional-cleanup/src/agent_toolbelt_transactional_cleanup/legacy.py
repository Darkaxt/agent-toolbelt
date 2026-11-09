"""Bounded authentication of the canonical v1 snapshot format for abandonment."""
from __future__ import annotations

import hashlib
import hmac
import json
import re

BULK_FIELDS = {'baseline', 'entries', 'manifest', 'items', 'registrations', 'results'}


def open_record(path, key, expected_host):
    """Authenticate any canonical v1 record while streaming past bulk fields.

    Retention needs bounded metadata for open snapshots AND issued/partial tickets.
    This does not grant abandonment or deletion authority; open_snapshot keeps its
    separate strict unissued-snapshot contract.
    """
    metadata = {}
    field = bytearray()
    name = None
    phase = 'object'
    depth = 0
    quoted = escaped = False
    with path.open('rb') as stream:
        header = stream.read(len(b'{"mac":"","payload":') + 64)
        match = re.fullmatch(rb'\{"mac":"([a-f0-9]{64})","payload":', header)
        if not match:
            raise ValueError('Unsupported legacy state envelope')
        remaining = path.stat().st_size - len(header) - 1
        signature = hmac.new(key, digestmod='sha256')
        while remaining:
            chunk = stream.read(min(1024*1024, remaining))
            if not chunk:
                raise ValueError('Truncated legacy state')
            signature.update(chunk)
            remaining -= len(chunk)
            for byte in chunk:
                if phase == 'object':
                    if byte != 123:
                        raise ValueError('Legacy payload must be an object')
                    phase = 'key'
                    continue
                if phase == 'done':
                    raise ValueError('Unexpected legacy trailing payload')
                if phase == 'key':
                    if byte == 58 and not quoted:
                        name = json.loads(field)
                        if not isinstance(name, str) or name in metadata:
                            raise ValueError('Invalid legacy metadata key')
                        field.clear(); phase = 'value'
                        continue
                    field.append(byte)
                else:
                    if not quoted and depth == 0 and byte in (44, 125):
                        if name not in BULK_FIELDS:
                            metadata[name] = json.loads(field)
                        field.clear(); name = None
                        phase = 'key' if byte == 44 else 'done'
                        continue
                    if name not in BULK_FIELDS:
                        field.append(byte)
                if len(field) > 1024*1024:
                    raise ValueError('Legacy metadata exceeds bounded reader limit')
                if quoted:
                    if escaped:
                        escaped = False
                    elif byte == 92:
                        escaped = True
                    elif byte == 34:
                        quoted = False
                elif byte == 34:
                    quoted = True
                elif phase == 'value' and byte in (123, 91):
                    depth += 1
                elif phase == 'value' and byte in (125, 93):
                    depth -= 1
        ending = stream.read(2)
    if phase != 'done' or ending != b'}' or not hmac.compare_digest(signature.hexdigest(), match[1].decode()):
        raise ValueError('Legacy state signature or envelope mismatch')
    if metadata.get('host') != expected_host or metadata.get('policy') != '1':
        raise ValueError('Legacy state belongs to another host or policy')
    return metadata


def open_snapshot(path, key, expected_host):
    # v1 wrote sorted, compact JSON: mac first, then the canonical payload.
    # Authenticate that exact byte stream without loading the baseline dictionary.
    with path.open('rb') as stream:
        header = stream.read(len(b'{"mac":"","payload":') + 64)
        match = re.fullmatch(rb'\{"mac":"([a-f0-9]{64})","payload":', header)
        if not match:
            raise ValueError('Unsupported legacy state envelope')
        remaining = path.stat().st_size - len(header) - 1
        signature = hmac.new(key, digestmod='sha256')
        checksum = hashlib.sha256(header)
        first, tail = b'', b''
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError('Truncated legacy snapshot')
            if not first:
                first = chunk[:16]
            signature.update(chunk); checksum.update(chunk)
            tail = (tail + chunk)[-1024 * 1024:]
            remaining -= len(chunk)
        ending = stream.read()
        checksum.update(ending)
    if ending != b'}' or not hmac.compare_digest(signature.hexdigest(), match[1].decode()):
        raise ValueError('Legacy snapshot signature mismatch')
    if not first.startswith(b'{"baseline":{'):
        raise ValueError('Only unissued legacy open baseline snapshots can be discarded')
    boundary = tail.rfind(b'},"created_at":')
    if boundary < 0:
        raise ValueError('Legacy metadata exceeds bounded reader limit')
    payload = json.loads(b'{' + tail[boundary + 2:])
    if (payload.get('host') != expected_host or payload.get('policy') != '1'
            or payload.get('state') != 'open' or payload.get('ticket_id')):
        raise ValueError('Legacy snapshot is not an unissued open transaction on this host')
    roots = payload.get('roots')
    if not isinstance(roots, list) or not roots or any(not isinstance(root, str) or not root for root in roots):
        raise ValueError('Legacy snapshot has no valid target roots')
    return payload, checksum.hexdigest()
