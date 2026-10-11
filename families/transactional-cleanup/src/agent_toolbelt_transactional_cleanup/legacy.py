"""Bounded authentication of the canonical v1 snapshot format for abandonment."""
from __future__ import annotations

import hashlib
import hmac
import json
import re


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
