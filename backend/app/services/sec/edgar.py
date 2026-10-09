"""Normalize original ownership XML with authoritative filing metadata."""
import xml.etree.ElementTree as ET

from .normalize import InvalidRow, Report, assign_identities, flag, normalize, text


def parse_edgar(data: bytes, metadata: dict) -> Report:
    # Ownership filings need neither DTDs nor entities.
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise InvalidRow('XML DTD/entities are unsupported')
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise InvalidRow('invalid ownership XML') from None
    for element in root.iter():
        element.tag = element.tag.rsplit('}', 1)[-1]
    if root.tag != 'ownershipDocument':
        raise InvalidRow('expected original ownership XML, not rendered HTML')
    report = Report()
    def get(node, path):
        return text(node.findtext(path))
    document = get(root, 'documentType')
    expected = (metadata.get('document_type') or document or '').replace('/', '-')
    if expected != (document or '').replace('/', '-'):
        raise InvalidRow('filing metadata and XML form disagree')
    names, roles = set(), set()
    for owner in root.findall('reportingOwner'):
        name = get(owner, 'reportingOwnerId/rptOwnerName')
        if name:
            names.add(name)
        relationship = owner.find('reportingOwnerRelationship')
        if relationship is not None:
            for xml_name, role in [('isOfficer', 'OFFICER'), ('isDirector', 'DIRECTOR'),
                                   ('isTenPercentOwner', 'TENPERCENTOWNER'), ('isOther', 'OTHER')]:
                try:
                    if flag(get(relationship, xml_name)):
                        roles.add(role)
                except InvalidRow:
                    report.issue(metadata.get('accession_number'), xml_name, 'invalid owner relationship flag')
            for name in ('officerTitle', 'otherText'):
                if get(relationship, name):
                    roles.add(get(relationship, name))
    if not names:
        report.issue(metadata.get('accession_number'), 'reporting_owner', 'no reporting owner name')
    for table, tag, derivative in [('nonDerivativeTable', 'nonDerivativeTransaction', False),
                                   ('derivativeTable', 'derivativeTransaction', True)]:
        for row in root.findall(f'{table}/{tag}'):
            raw = {
                'accession_number': metadata.get('accession_number'), 'source_type': 'edgar',
                'document_type': document, 'filing_date': metadata.get('filing_date'),
                'accepted_at': metadata.get('accepted_at'),
                'ticker': get(root, 'issuer/issuerTradingSymbol'), 'cik': get(root, 'issuer/issuerCik'),
                'company_name': get(root, 'issuer/issuerName'),
                'insider_name': ' | '.join(sorted(names)), 'insider_role': ' | '.join(sorted(roles)),
                'transaction_date': get(row, 'transactionDate/value'),
                'transaction_code': get(row, 'transactionCoding/transactionCode'),
                'acquired_or_disposed': get(row, 'transactionAmounts/transactionAcquiredDisposedCode/value'),
                'derivative_flag': derivative, 'security_title': get(row, 'securityTitle/value'),
                'shares': get(row, 'transactionAmounts/transactionShares/value'),
                'price': get(row, 'transactionAmounts/transactionPricePerShare/value'),
                'shares_owned_after': get(row, 'postTransactionAmounts/sharesOwnedFollowingTransaction/value'),
                'direct_or_indirect': get(row, 'ownershipNature/directOrIndirectOwnership/value'),
                'aff10b5one': get(root, 'aff10b5One'),
            }
            normalized = normalize(raw, report)
            if normalized is not None:
                report.records.append(normalized)
    assign_identities(report.records)
    return report
