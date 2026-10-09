"""Conservative offline owner evidence from immutable Issue #2 source caches."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import csv
import io
import xml.etree.ElementTree as ET
import zipfile

from app.services.sec.normalize import accession, cik
from app.services.sec.edgar import parse_edgar


@dataclass(frozen=True)
class BuyerEvidence:
    # Caller-supplied evidence must associate these identities with the transaction.
    identities: tuple[str, ...]
    source: str


def cached_buyers(cache: Path, transactions: list[dict]):
    """Only a complete, single-reporting-owner filing supports automatic association.

    Multiple filing owners, missing identifiers and unavailable sources remain unknown.
    No name-based identity or transaction-to-owner assignment is invented.
    """
    wanted = {row['accession_number'] for row in transactions}
    evidence, issues = {}, []
    filing_rows = {}
    for row in transactions:
        filing_rows.setdefault(row['accession_number'], []).append(row)
    verified_xml_keys = {}
    owners_by_accession = {}
    for key in sorted(wanted):
        path = cache / f'{key}.xml'
        if not path.exists():
            continue
        try:
            data = path.read_bytes()
            if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
                raise ValueError('Unsupported XML')
            root = ET.fromstring(data)
            for node in root.iter():
                node.tag = node.tag.rsplit('}', 1)[-1]
            if root.tag != 'ownershipDocument':
                raise ValueError('Not ownership XML')
            example = filing_rows[key][0]
            if cik(root.findtext('issuer/issuerCik')) != cik(example['cik']):
                raise ValueError('Cached issuer mismatch')
            parsed = parse_edgar(data, {'accession_number': key, 'filing_date': example['filing_date'].isoformat(),
                                       'document_type': example['document_type']})
            verified_xml_keys[key] = {row['canonical_transaction_key'] for row in parsed.records}
            owners = root.findall('reportingOwner')
            # Two reportingOwner elements remain ambiguous even if their CIKs repeat.
            if len(owners) == 1:
                identity = cik(owners[0].findtext('reportingOwnerId/rptOwnerCik'))
                owners_by_accession[key] = BuyerEvidence((identity,), path.name)
            else:
                owners_by_accession[key] = None
        except (ValueError, ET.ParseError, OSError):
            owners_by_accession[key] = None
            issues.append({'accession_number': key, 'reason': 'invalid cached owner evidence'})
    remaining = wanted - owners_by_accession.keys()
    # Read archives only if XML did not establish the filing's evidence status.
    for path in sorted(cache.glob('*_form345.zip')) if remaining else []:
        try:
            with zipfile.ZipFile(path) as archive:
                files = {PurePosixPath(name).name.upper(): name for name in archive.namelist()}
                name = files.get('REPORTINGOWNER.TSV')
                if name is None:
                    continue
                by_key = {}
                invalid = set()
                with archive.open(name) as source:
                    for row in csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig'), delimiter='\t'):
                        key = accession(row.get('ACCESSION_NUMBER'))
                        if key not in remaining:
                            continue
                        try:
                            identity = cik(row.get('RPTOWNERCIK'))
                            by_key.setdefault(key, set()).add(identity)
                        except ValueError:
                            invalid.add(key)
                for key, identities in by_key.items():
                    value = (BuyerEvidence(tuple(identities), path.name)
                             if len(identities) == 1 and key not in invalid else None)
                    if key in owners_by_accession and owners_by_accession[key] != value:
                        owners_by_accession[key] = None
                    else:
                        owners_by_accession[key] = value
        except (ValueError, OSError, zipfile.BadZipFile, UnicodeError):
            issues.append({'source': path.name, 'reason': 'invalid cached owner archive'})
    for row in transactions:
        value = owners_by_accession.get(row['accession_number'])
        if row['accession_number'] in verified_xml_keys and row['canonical_transaction_key'] not in verified_xml_keys[row['accession_number']]:
            value = None
        if value is not None:
            evidence[row['transaction_id']] = value
    return evidence, issues
