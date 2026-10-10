"""Synthetic, mocked Snowflake integration: no live requests or credentials."""
import json
from unittest.mock import Mock, MagicMock
import pytest
from app.api.snowflake import get_context, get_provider
from app.services import ai_providers
from app.services.snowflake_research import Context, SnowflakeProvider, assemble, research
from test_core_api import setup

EVIDENCE = {'ticker': 'AAPL', 'company_name': 'Apple', 'sector': 'Technology',
            'event': {'research_event_id': 'AAPL:2026-03-16', 'unique_buyer_count': None}}
CONTENT = dict(event_context=['A persisted purchase event is available.'],
               research_considerations=['What does the filing disclose about ownership?'],
               filing_context=['Review the original filing for transaction details.'])

@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    for name in ('SNOWFLAKE_PAT', 'SNOWFLAKE_ACCOUNT_URL', 'SNOWFLAKE_MODEL', 'SNOWFLAKE_TIMEOUT_SECONDS'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ai_providers, 'post', Mock(side_effect=AssertionError('Live calls forbidden')))


def configure(monkeypatch):
    monkeypatch.setenv('SNOWFLAKE_PAT', 'synthetic-test-token')
    monkeypatch.setenv('SNOWFLAKE_ACCOUNT_URL', 'https://test-account.snowflakecomputing.com')


def body(content=CONTENT, finish_reason='stop'):
    return json.dumps({'choices': [{'finish_reason': finish_reason, 'message': {'content': json.dumps(content)}}]}).encode()


def test_unconfigured_and_no_event():
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'
    provider = Mock()
    assert research({**EVIDENCE, 'event': None}, provider).status == 'unavailable'
    provider.generate.assert_not_called()


def test_success_and_exact_request(monkeypatch):
    configure(monkeypatch)
    ai_providers.post.return_value = body(), 'application/json'
    ai_providers.post.side_effect = None
    result = research(EVIDENCE, SnowflakeProvider())
    assert result.status == 'available' and result.context.model_dump() == CONTENT
    url, headers, payload, timeout, limit = ai_providers.post.call_args.args
    assert url.endswith('/api/v2/cortex/v1/chat/completions')
    assert headers['Authorization'] == 'Bearer synthetic-test-token'
    assert payload['model'] == 'llama3.1-8b' and payload['stream'] is False
    assert payload['max_completion_tokens'] == 1800
    assert 'max_tokens' not in payload
    assert json.loads(payload['messages'][1]['content']) == EVIDENCE
    assert timeout == 30 and limit == 128 * 1024
    assert 'synthetic-test-token' not in result.model_dump_json()


@pytest.mark.parametrize('content', [{}, {**CONTENT, 'extra': []}, {**CONTENT, 'event_context': [1]},
                                    {**CONTENT, 'event_context': ['Buy this stock.']},
                                    {**CONTENT, 'event_context': ['Guaranteed 99 percent.']}])
def test_invalid_content(monkeypatch, content):
    configure(monkeypatch)
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body(content), 'application/json'
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'


@pytest.mark.parametrize('failure', [TimeoutError('private'), OSError('private'),
                                    ai_providers.ProviderFailure('private')])
def test_transport_failure(monkeypatch, failure):
    configure(monkeypatch)
    # Exercise the real transport sanitization with an opener that cannot reach the network.
    monkeypatch.setattr(ai_providers, 'post', REAL_POST)
    monkeypatch.setattr(ai_providers, 'build_opener', Mock(side_effect=failure))
    result = research(EVIDENCE, SnowflakeProvider())
    assert result.status == 'unavailable' and 'private' not in result.model_dump_json()

REAL_POST = ai_providers.post


def test_malformed_response(monkeypatch):
    configure(monkeypatch)
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = b'not-json', 'application/json'
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'


@pytest.mark.parametrize('origin', ['http://test.snowflakecomputing.com', 'https://evil.test',
                                   'https://test.snowflakecomputing.com@evil.test',
                                   'https://test.snowflakecomputing.com/path'])
def test_origin_validation(monkeypatch, origin):
    configure(monkeypatch)
    monkeypatch.setenv('SNOWFLAKE_ACCOUNT_URL', origin)
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'
    ai_providers.post.assert_not_called()


def test_route_and_core_independence(setup):
    client, _, app = setup
    app.dependency_overrides[get_context] = lambda: EVIDENCE
    before = client.get('/api/companies/AAPL').json()
    response = client.post('/api/companies/AAPL/snowflake-research')
    assert response.status_code == 200 and response.json()['status'] == 'unavailable'
    assert client.get('/api/companies/AAPL').json() == before
    assert '/api/companies/{ticker}/snowflake-research' in client.get('/openapi.json').json()['paths']
    del app.dependency_overrides[get_context]
    assert client.post('/api/companies/UNKNOWN/snowflake-research').status_code == 404


def test_latest_event_and_bounded_filing_provenance(setup):
    from datetime import date
    from sqlalchemy.orm import Session
    from app.api.dependencies import get_universe
    from test_core_api import seed, research as event, transaction
    client, engine, app = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        session.add(event(day=date(2026, 9, 1)))
        session.add(event(feature_metadata={'source_transaction_ids': ['synthetic-one'],
                                          'private_unrelated': 'must not be transmitted'},
                          aggregate_purchase_value=0))
        session.add(transaction(insider_name='Synthetic owner'))
    with Session(engine) as session:
        evidence = assemble(session, get_universe().ticker_to_company('AAPL'))
    assert evidence['event']['research_event_id'] == 'AAPL:2026-10-02'
    assert evidence['event']['aggregate_purchase_value'] == '0E-10' or float(evidence['event']['aggregate_purchase_value']) == 0
    assert evidence['event']['unique_buyer_count'] is None
    assert evidence['filings'][0]['transaction_date'] != evidence['filings'][0]['filing_date']
    assert evidence['filings'][0]['source_owner_name'] == 'Synthetic owner'
    assert 'private_unrelated' not in json.dumps(evidence)
    provider = Mock()
    provider.generate.return_value = ('llama3.1-8b', Context.model_validate(CONTENT))
    app.dependency_overrides[get_provider] = lambda: provider
    response = client.post('/api/companies/aapl/snowflake-research')
    assert response.status_code == 200 and response.json()['status'] == 'available'
    assert response.json()['research_event_id'] == 'AAPL:2026-10-02'


@pytest.mark.parametrize('status', [401, 403, 429, 500, 503])
def test_http_errors_are_sanitized(monkeypatch, status):
    from urllib.error import HTTPError
    configure(monkeypatch)
    monkeypatch.setattr(ai_providers, 'post', REAL_POST)
    opener = Mock()
    opener.open.side_effect = HTTPError('https://synthetic.test', status, 'private', {}, None)
    monkeypatch.setattr(ai_providers, 'build_opener', Mock(return_value=opener))
    result = research(EVIDENCE, SnowflakeProvider())
    assert result.status == 'unavailable'
    assert 'private' not in result.model_dump_json()
    assert opener.open.call_count == 1


def test_signal_persistence_is_unchanged(setup):
    from sqlalchemy.orm import Session
    from app.db.models import Signal
    from test_core_api import seed, research as event
    client, engine, app = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        row = event()
        session.add(row)
        session.flush()
        session.add(Signal(signal_id='synthetic', research_event_id=row.research_event_id,
                           ticker='AAPL', public_event_day=row.public_event_day,
                           score_status='insufficient_data', unavailable_components=['A'],
                           anomaly_score=0, model_probability=0))
    with Session(engine) as session:
        before = {column.name: getattr(session.get(Signal, 'synthetic'), column.name)
                  for column in Signal.__table__.columns}
    provider = Mock()
    provider.generate.return_value = ('llama3.1-8b', Context.model_validate(CONTENT))
    app.dependency_overrides[get_provider] = lambda: provider
    assert client.post('/api/companies/AAPL/snowflake-research').json()['status'] == 'available'
    with Session(engine) as session:
        after = {column.name: getattr(session.get(Signal, 'synthetic'), column.name)
                 for column in Signal.__table__.columns}
    assert before == after
    transmitted = json.dumps(provider.generate.call_args.args[0])
    for forbidden in ('anomaly_score', 'model_probability', 'car30', 'insider_edge_score'):
        assert forbidden not in transmitted


@pytest.mark.parametrize('finish_reason', ['', 'stop'])
def test_complete_cortex_assistant_response(monkeypatch, finish_reason):
    configure(monkeypatch)
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body(finish_reason=finish_reason), 'application/json'
    result = research(EVIDENCE, SnowflakeProvider())
    assert result.status == 'available'
    assert result.context.model_dump() == CONTENT


@pytest.mark.parametrize('finish_reason', ['length', 'content_filter', 'error', 'tool_calls', None])
def test_incomplete_or_error_finish_reason_rejected(monkeypatch, finish_reason):
    configure(monkeypatch)
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body(finish_reason=finish_reason), 'application/json'
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'


@pytest.mark.parametrize('content', ['{"event_context":', '{}',
                                  json.dumps({**CONTENT, 'filing_context': []}),
                                  json.dumps({**CONTENT, 'event_context': ['Buy now.']}),
                                  json.dumps({**CONTENT, 'event_context': ['Return is 99 percent.']})])
def test_empty_finish_reason_still_requires_safe_complete_content(monkeypatch, content):
    configure(monkeypatch)
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = json.dumps({'choices': [
        {'finish_reason': '', 'message': {'role': 'assistant', 'content': content}}
    ]}).encode(), 'application/json'
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'


def test_real_transport_sets_json_content_type(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(ai_providers, 'post', REAL_POST)
    response = Mock()
    response.read.return_value = body(finish_reason='')
    response.headers.get_content_type.return_value = 'application/json'
    opener = Mock()
    opener.open.return_value = MagicMock()
    opener.open.return_value.__enter__.return_value = response
    monkeypatch.setattr(ai_providers, 'build_opener', Mock(return_value=opener))
    assert research(EVIDENCE, SnowflakeProvider()).status == 'available'
    request = opener.open.call_args.args[0]
    assert request.get_header('Content-type') == 'application/json'
    assert request.get_header('Accept') == 'application/json'
    assert json.loads(request.data)['model'] == 'llama3.1-8b'
    assert opener.open.call_count == 1


@pytest.mark.parametrize('finish_reason', ['', 'stop'])
@pytest.mark.parametrize('statement', [
    'The filing date is 2026-03-13.',
    'The source accession is 0000000001-26-000004.',
    'Document type 4 is recorded.',
])
def test_grounded_numeric_output(monkeypatch, finish_reason, statement):
    configure(monkeypatch)
    evidence = {**EVIDENCE, 'filings': [{'filing_date': '2026-03-13',
                'accession_number': '0000000001-26-000004', 'document_type': '4'}]}
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body({**CONTENT, 'filing_context': [statement]}, finish_reason), 'application/json'
    assert research(evidence, SnowflakeProvider()).status == 'available'


@pytest.mark.parametrize('statement', [
    'The percentage is 99%.', 'The percentage is 4%.', 'The percentage is 4 percent.',
    'The filing date is 2026-03-14.', 'The purchase amount is $9999.',
    'The purchase amount is $4.', 'The purchase quantity is 9999 shares.',
    'The purchase quantity is 4 shares.', 'The score is 4.',
    'The probability is 4.', 'The return is 4.', 'The price is 4.',
    'The accession is 0000000001-26-000005.',
])
def test_invented_or_reinterpreted_numbers_rejected(monkeypatch, statement):
    configure(monkeypatch)
    evidence = {**EVIDENCE, 'filings': [{'filing_date': '2026-03-13',
                'accession_number': '0000000001-26-000004', 'document_type': '4'}]}
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body({**CONTENT, 'filing_context': [statement]}, ''), 'application/json'
    assert research(evidence, SnowflakeProvider()).status == 'unavailable'


@pytest.mark.parametrize('statement', [
    'Whether American Express insider buying on 2026-03-16 is associated with stock price movement',
    'For the filing dated 2026-03-13, what questions about stock price movement warrant review?',
    'For accession 0000000001-26-000004, examine whether returns are associated with the disclosed context.',
    'For the event on 2026-03-16, what limitations apply to probability, score, IES and CAR interpretation?',
])
def test_identifiers_with_qualitative_quantitative_subjects(monkeypatch, statement):
    configure(monkeypatch)
    evidence = {**EVIDENCE, 'filings': [{'filing_date': '2026-03-13',
                'accession_number': '0000000001-26-000004', 'document_type': '4'}]}
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body({**CONTENT, 'research_considerations': [statement]}, ''), 'application/json'
    assert research(evidence, SnowflakeProvider()).status == 'available'


@pytest.mark.parametrize('statement', [
    'The stock price was 4', 'The return was 4', 'The probability was 4',
    'The score was 4', 'CAR30 was 4', 'IES: 4', 'The price equals 4',
])
def test_numeric_quantitative_assignments_are_rejected(monkeypatch, statement):
    configure(monkeypatch)
    evidence = {**EVIDENCE, 'document_type': '4'}
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body({**CONTENT, 'event_context': [statement]}, ''), 'application/json'
    assert research(evidence, SnowflakeProvider()).status == 'unavailable'


@pytest.mark.parametrize('case,expected', [
    ('configuration', 'configuration_missing'), ('no_event', 'research_event_missing'),
    ('malformed', 'provider_response_invalid'), ('finish', 'finish_reason_rejected'),
    ('schema', 'schema_validation_failed'), ('safety', 'safety_language_rejected'),
    ('numeric', 'numeric_grounding_rejected'), ('unexpected', 'unexpected_error'),
])
def test_safe_unavailable_diagnostics(monkeypatch, caplog, case, expected):
    import logging
    from copy import deepcopy
    caplog.set_level(logging.WARNING, logger='app.services.snowflake_research')
    evidence = deepcopy(EVIDENCE)
    evidence['company_name'] = 'PRIVATE_EVIDENCE_MARKER'
    if case != 'configuration':
        configure(monkeypatch)
    if case == 'no_event':
        evidence['event'] = None
    ai_providers.post.side_effect = None
    content = {**CONTENT}
    if case == 'schema':
        content = {'event_context': ['RAW_PROVIDER_MARKER']}
    elif case == 'safety':
        content = {**CONTENT, 'event_context': ['Buy RAW_PROVIDER_MARKER.']}
    elif case == 'numeric':
        content = {**CONTENT, 'event_context': ['RAW_PROVIDER_MARKER 99999']}
    response = body(content, finish_reason='length' if case == 'finish' else '')
    if case == 'malformed':
        response = b'RAW_PROVIDER_MARKER not JSON synthetic-test-token'
    ai_providers.post.return_value = response, 'application/json'
    provider = SnowflakeProvider()
    if case == 'unexpected':
        provider = Mock()
        provider.generate.side_effect = ValueError('RAW_PROVIDER_MARKER synthetic-test-token')
    result = research(evidence, provider)
    assert result.status == 'unavailable' and result.context is None and result.model is None
    assert set(result.model_dump()) == {'ticker', 'research_event_id', 'provider', 'model',
                                       'status', 'context', 'provenance', 'limitations'}
    records = [r for r in caplog.records if r.name == 'app.services.snowflake_research']
    assert len(records) == 1
    message = records[0].getMessage()
    assert 'ticker=AAPL' in message and f'reason={expected}' in message
    assert ('research_event_id=None' if case == 'no_event' else
            'research_event_id=AAPL:2026-03-16') in message
    assert records[0].exc_info is None
    for forbidden in ('synthetic-test-token', 'Authorization', 'RAW_PROVIDER_MARKER',
                      'PRIVATE_EVIDENCE_MARKER', 'event_context', 'Use only supplied evidence'):
        assert forbidden not in caplog.text
    assert expected not in result.model_dump_json()


@pytest.mark.parametrize('failure,expected', [
    (TimeoutError('RAW_PROVIDER_MARKER'), 'provider_timeout'),
    (ValueError('RAW_PROVIDER_MARKER'), 'provider_response_invalid'),
])
def test_transport_diagnostic_categories(monkeypatch, caplog, failure, expected):
    import logging
    configure(monkeypatch)
    caplog.set_level(logging.WARNING, logger='app.services.snowflake_research')
    monkeypatch.setattr(ai_providers, 'post', REAL_POST)
    monkeypatch.setattr(ai_providers, 'build_opener', Mock(side_effect=failure))
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'
    assert f'reason={expected}' in caplog.text
    assert 'RAW_PROVIDER_MARKER' not in caplog.text


def test_http_error_diagnostic_is_safe(monkeypatch, caplog):
    import logging
    from urllib.error import HTTPError
    configure(monkeypatch)
    caplog.set_level(logging.WARNING, logger='app.services.snowflake_research')
    monkeypatch.setattr(ai_providers, 'post', REAL_POST)
    error = HTTPError('https://private.test', 403, 'RAW_PROVIDER_MARKER',
                      {'Authorization': 'synthetic-test-token'}, None)
    monkeypatch.setattr(ai_providers, 'build_opener', Mock(side_effect=error))
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'
    assert 'reason=provider_http_error' in caplog.text
    for forbidden in ('private.test', 'RAW_PROVIDER_MARKER', 'Authorization', 'synthetic-test-token'):
        assert forbidden not in caplog.text


@pytest.mark.parametrize('value', ['250072.030', '250072.03', '250,072.03', '250,072.0300'])
def test_equivalent_grounded_decimal_formatting(monkeypatch, value):
    configure(monkeypatch)
    evidence = {**EVIDENCE, 'event': {**EVIDENCE['event'], 'aggregate_purchase_value': '250072.030'}}
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body({**CONTENT, 'event_context': [
        f'The recorded aggregate purchase value is {value}.']}, ''), 'application/json'
    assert research(evidence, SnowflakeProvider()).status == 'available'


@pytest.mark.parametrize('statement', [
    'The value is 250072.04.', 'The value is 250073.', 'The value is 25,0072.03.',
    'The value is 0250072.03.', 'The value is 250072.03%.',
    'The price was 250072.03.', 'The return was 250072.03.',
    'The probability was 250072.03.', 'The score was 250072.03.',
    'CAR30 was 250072.03.', 'IES was 250072.03.',
    'The quantity was 250072.03 shares.', 'The date is 2026-03-17.',
    'The accession is 0000000001-26-000005.',
])
def test_decimal_normalization_remains_fail_closed(monkeypatch, statement):
    configure(monkeypatch)
    evidence = {**EVIDENCE, 'event': {**EVIDENCE['event'], 'aggregate_purchase_value': '250072.030'},
                'filings': [{'filing_date': '2026-03-16',
                             'accession_number': '0000000001-26-000004', 'document_type': '4'}]}
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body({**CONTENT, 'event_context': [statement]}, ''), 'application/json'
    assert research(evidence, SnowflakeProvider()).status == 'unavailable'


def test_decimal_normalization_does_not_normalize_identifiers():
    from app.services.snowflake_research import numbers_grounded
    assert not numbers_grounded({'4.0'}, {'4'})
    assert not numbers_grounded({'2026-3-16'}, {'2026-03-16'})
    assert not numbers_grounded({'1-26-4'}, {'0000000001-26-000004'})
    assert numbers_grounded({'250072'}, {'250072.000'})


@pytest.mark.parametrize('numeric,kind', [
    ('98765', 'integer'), ('98765.43', 'decimal'), ('98,765.43', 'grouped_decimal'),
    ('$98765', 'currency'), ('98765%', 'percentage'), ('2027-01-02', 'date_like'),
    ('0000000001-26-999999', 'identifier_like'), ('98765 shares', 'other_numeric'), ('1e99', 'other_numeric'),
])
def test_rejected_numeric_token_logged_without_surrounding_text(monkeypatch, caplog, numeric, kind):
    import logging
    configure(monkeypatch)
    caplog.set_level(logging.WARNING, logger='app.services.snowflake_research')
    evidence = {**EVIDENCE, 'company_name': 'PRIVATE_EVIDENCE_MARKER'}
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body({**CONTENT, 'event_context': [
        f'RAW_PROVIDER_BEFORE {numeric} RAW_PROVIDER_AFTER 99998.']}, ''), 'application/json'
    result = research(evidence, SnowflakeProvider())
    assert result.status == 'unavailable' and result.context is None
    assert f'rejected_token={numeric} token_kind={kind}' in caplog.text
    assert 'reason=numeric_grounding_rejected' in caplog.text
    assert 'ticker=AAPL research_event_id=AAPL:2026-03-16' in caplog.text
    assert '99998' not in caplog.text
    for forbidden in ('RAW_PROVIDER_BEFORE', 'RAW_PROVIDER_AFTER', 'synthetic-test-token',
                      'Authorization', 'PRIVATE_EVIDENCE_MARKER', 'event_context', 'Use only supplied evidence'):
        assert forbidden not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert 'rejected_token' not in result.model_dump_json()
    assert 'token_kind' not in result.model_dump_json()


def test_rejected_token_length_is_bounded(monkeypatch, caplog):
    import logging
    from app.services.snowflake_research import TOKEN_LOG_LIMIT
    configure(monkeypatch)
    caplog.set_level(logging.WARNING, logger='app.services.snowflake_research')
    ai_providers.post.side_effect = None
    numeric = '9' * 200
    ai_providers.post.return_value = body({**CONTENT, 'event_context': [numeric]}, ''), 'application/json'
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'
    record = next(r for r in caplog.records if r.name == 'app.services.snowflake_research')
    assert len(record.args[3]) == TOKEN_LOG_LIMIT
    assert numeric not in caplog.text


def test_unrecognized_numeric_format_logs_only_digits(monkeypatch, caplog):
    import logging
    configure(monkeypatch)
    caplog.set_level(logging.WARNING, logger='app.services.snowflake_research')
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body({**CONTENT, 'event_context': ['PRIVATE99suffix']}, ''), 'application/json'
    assert research(EVIDENCE, SnowflakeProvider()).status == 'unavailable'
    assert 'rejected_token=99 token_kind=other_numeric' in caplog.text
    assert 'PRIVATE' not in caplog.text and 'suffix' not in caplog.text


def test_available_result_has_no_rejection_log(monkeypatch, caplog):
    configure(monkeypatch)
    ai_providers.post.side_effect = None
    ai_providers.post.return_value = body(), 'application/json'
    result = research(EVIDENCE, SnowflakeProvider())
    assert result.status == 'available' and result.context.model_dump() == CONTENT
    assert 'rejected_token' not in caplog.text
