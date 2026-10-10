"""Pure canonical JSON v1; hashes identify bytes, never authenticity.

UTF-8, sorted string keys, compact separators, literal Unicode, one trailing LF.
Aware datetimes use versioned typed UTC tags with six fractional digits and Z.
Dates use typed ISO tags. Reserved-key mappings are escaped. Int and float types remain distinct (1 versus 1.0);
negative floating zero normalizes to 0.0. Lists and tuples intentionally share
an ordered-array representation; Decimal trailing zeros are insignificant. Decimal uses
an explicit tagged object, not a float. Raw nonfinite missingness must be tagged
by the caller; bare NaN/Infinity are rejected everywhere. No file IO or loading.
Resource limits are validation bounds, not strict peak-memory bounds. Encoding
and JSON parsing may allocate temporary objects before rejecting a payload;
this library does not protect against arbitrary resource exhaustion.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math

from pydantic import BaseModel


# Encoding v1 reserves this key; ordinary mappings containing it are escaped.
TAG = '$evidence/v1'
MAX_DEPTH = 64
MAX_NODES = 100_000
MAX_BYTES = 4_000_000
MAX_DECIMAL_DIGITS = 4096


def _normalize(value, active, depth=0, budget=None):
    if budget is None:
        budget = [MAX_NODES]
    budget[0] -= 1
    if depth > MAX_DEPTH or budget[0] < 0:
        raise ValueError('canonical resource limit exceeded')
    if isinstance(value, BaseModel):
        # Revalidate even an already-created model; never trust model_construct.
        value = type(value).model_validate(value).model_dump(mode='python')
    if value is None or type(value) in (bool, int, str):
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError('canonical JSON requires finite numbers')
        return 0.0 if value == 0 else value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('canonical Decimal must be finite')
        # Fixed notation, trimmed fractional zeros; no decimal-context rounding.
        if len(value.as_tuple().digits) + abs(value.as_tuple().exponent) > MAX_DECIMAL_DIGITS:
            raise ValueError('Decimal expansion limit exceeded')
        text = format(value, 'f')
        if '.' in text:
            text = text.rstrip('0').rstrip('.')
        if value == 0:
            text = '0'
        return {TAG: ['decimal', text]}
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValueError('timestamp must be timezone-aware')
        return {TAG: ['datetime', value.astimezone(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')]}
    if type(value) is date:
        return {TAG: ['date', value.isoformat()]}
    if isinstance(value, Mapping) or type(value) in (list, tuple):
        identity = id(value)
        if identity in active:
            raise ValueError('cyclic canonical input')
        active.add(identity)
        try:
            if isinstance(value, Mapping):
                if any(type(key) is not str for key in value):
                    raise ValueError('canonical mapping keys must be strings')
                result = {key: _normalize(item, active, depth + 1, budget) for key, item in value.items()}
                return {TAG: ['mapping', result]} if TAG in result else result
            return [_normalize(item, active, depth + 1, budget) for item in value]
        finally:
            active.remove(identity)
    raise ValueError('unsupported canonical value type')


def canonical_bytes(value) -> bytes:
    """Return canonical bytes without mutating inputs; no implicit string coercion."""
    normalized = _normalize(value, set())
    _check_wire(normalized)
    result = (json.dumps(normalized, ensure_ascii=False, sort_keys=True,
                       separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')
    if len(result) > MAX_BYTES:
        raise ValueError('canonical byte limit exceeded')
    return result


def content_digest(value) -> str:
    """SHA-256 over canonical_bytes(value), excluding any imaginary self-hash."""
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def parse_json(data: str | bytes):
    """Strict JSON parser: rejects duplicate keys and nonfinite literals/overflow.

    Versioned typed tags decode losslessly; ordinary reserved-key mappings escape.
    Limits: 4 MB UTF-8, depth 64, 100,000 nodes, Decimal expansion 4096 digits. This does not verify artifacts or trust claims.
    """
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result

    def invalid(_):
        raise ValueError('nonfinite JSON literal')

    if not isinstance(data, (str, bytes)) or len(data.encode('utf-8') if isinstance(data, str) else data) > MAX_BYTES:
        raise ValueError('JSON byte limit exceeded')
    try:
        value = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)
    except RecursionError:
        raise ValueError('JSON nesting limit exceeded') from None
    _check_wire(value)  # Check before decoding; reject overflow such as 1e999.
    return _decode(value)


def _decode(value):
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if not isinstance(value, dict):
        return value
    if TAG not in value:
        return {key: _decode(item) for key, item in value.items()}
    tag = value[TAG]
    if set(value) != {TAG} or not isinstance(tag, list) or len(tag) != 2:
        raise ValueError('malformed typed evidence tag')
    kind, payload = tag
    if kind == 'mapping' and isinstance(payload, dict) and TAG in payload:
        return {key: _decode(item) for key, item in payload.items()}
    if type(payload) is str:
        try:
            if kind == 'decimal':
                result = Decimal(payload)
            elif kind == 'datetime':
                result = datetime.fromisoformat(payload.replace('Z', '+00:00'))
            elif kind == 'date':
                result = date.fromisoformat(payload)
            else:
                raise ValueError('unsupported typed evidence tag')
            # Only canonical encodings are accepted, including finite decimals.
            if _normalize(result, set()) != value:
                raise ValueError('noncanonical typed evidence tag')
            return result
        except (ValueError, ArithmeticError):
            raise ValueError('invalid typed evidence tag') from None
    raise ValueError('malformed typed evidence tag')


def _check_wire(value):
    """Bound both encoded JSON and Python payloads; never truncate evidence."""
    stack = [(value, 0)]
    count = 0
    while stack:
        item, depth = stack.pop()
        count += 1
        if count > MAX_NODES or depth > MAX_DEPTH:
            raise ValueError('canonical resource limit exceeded')
        if type(item) is float and not math.isfinite(item):
            raise ValueError('canonical JSON requires finite numbers')
        if isinstance(item, dict):
            stack.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            stack.extend((child, depth + 1) for child in item)
