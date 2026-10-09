"""Read official UTF-8 tab-separated quarterly archives without extracting files."""
from collections import defaultdict
import csv
import io
from pathlib import PurePosixPath
import zipfile

from .normalize import InvalidRow, Report, accession, assign_identities, normalize, text


def parse_bulk(data: bytes) -> Report:
    report = Report()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        files = {PurePosixPath(name).name.upper(): name for name in archive.namelist()}
        def rows(table):
            filename = files.get(f'{table}.TSV')
            if filename is None:
                raise InvalidRow(f'missing required SEC table {table}')
            with archive.open(filename) as source:
                yield from csv.DictReader(io.TextIOWrapper(source, encoding='utf-8-sig'), delimiter='\t')

        submissions = {}
        for row in rows('SUBMISSION'):
            key = accession(row['ACCESSION_NUMBER'])
            if key in submissions:
                raise InvalidRow('duplicate SUBMISSION accession')
            submissions[key] = row
        owners = defaultdict(dict)
        for row in rows('REPORTINGOWNER'):
            key = accession(row['ACCESSION_NUMBER'])
            owner_key = text(row.get('RPTOWNERCIK'))
            if not owner_key:
                report.issue(key, 'reporting_owner', 'missing reporting-owner CIK')
                continue
            if owner_key in owners[key] and owners[key][owner_key] != row:
                raise InvalidRow('conflicting REPORTINGOWNER key')
            owners[key][owner_key] = row

        for table in ('NONDERIV_TRANS', 'DERIV_TRANS'):
            seen = set()
            for row in rows(table):
                try:
                    key = accession(row.get('ACCESSION_NUMBER'))
                    source_key = text(row.get(f'{table}_SK'))
                    if not source_key:
                        raise InvalidRow('missing transaction surrogate key')
                    if (key, source_key) in seen:
                        report.issue(key, table, 'duplicate source transaction key; skipped')
                        continue
                    seen.add((key, source_key))
                    submission = submissions.get(key)
                    if submission is None:
                        raise InvalidRow('transaction has no matching SUBMISSION')
                    filing_owners = sorted(owners[key].values(), key=lambda owner: owner['RPTOWNERCIK'])
                    if not filing_owners:
                        report.issue(key, 'reporting_owner', 'no reporting owner for filing')
                    names = sorted({owner['RPTOWNERNAME'].strip() for owner in filing_owners if text(owner.get('RPTOWNERNAME'))})
                    roles = sorted({part.strip() for owner in filing_owners
                                    for part in (owner.get('RPTOWNER_RELATIONSHIP', ''), owner.get('RPTOWNER_TITLE', ''), owner.get('RPTOWNER_TXT', ''))
                                    if text(part)})
                    raw = {
                        'accession_number': key, 'source_type': 'bulk',
                        'document_type': submission.get('DOCUMENT_TYPE'),
                        'ticker': submission.get('ISSUERTRADINGSYMBOL'), 'cik': submission.get('ISSUERCIK'),
                        'company_name': submission.get('ISSUERNAME'),
                        'insider_name': ' | '.join(names), 'insider_role': ' | '.join(roles),
                        'filing_date': submission.get('FILING_DATE'), 'transaction_date': row.get('TRANS_DATE'),
                        'transaction_code': row.get('TRANS_CODE'), 'acquired_or_disposed': row.get('TRANS_ACQUIRED_DISP_CD'),
                        'derivative_flag': table == 'DERIV_TRANS', 'security_title': row.get('SECURITY_TITLE'),
                        'shares': row.get('TRANS_SHARES'), 'price': row.get('TRANS_PRICEPERSHARE'),
                        'shares_owned_after': row.get('SHRS_OWND_FOLWNG_TRANS'),
                        'direct_or_indirect': row.get('DIRECT_INDIRECT_OWNERSHIP'),
                        'aff10b5one': submission.get('AFF10B5ONE'),
                    }
                    normalized = normalize(raw, report)
                    if normalized is not None:
                        report.records.append(normalized)
                except InvalidRow as error:
                    report.issue(None, table, str(error))
    assign_identities(report.records)
    return report
