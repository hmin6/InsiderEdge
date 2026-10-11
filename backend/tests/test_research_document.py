"""Issue #118 research speech: mocked providers and fail-closed document verification."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from sqlalchemy.orm import Session

from test_core_api import setup, seed, research
from test_ai_services import isolated_providers, providers
from app.api.snowflake import get_provider
from app.services import research_document as rd
from app.services.ai_providers import ProviderFailure
from app.services.snowflake_research import Context

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/ai/research_document.json').read_text())


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    monkeypatch.setattr(rd, 'validated_research', rd.ValidatedResearch())


@pytest.fixture
def generated(setup):
    client, engine, app = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        session.add(research())
    gemini, audio = providers(app)
    gemini.generate.return_value = {k: v for k, v in FIXTURE['gemini_explanation'].items() if k != 'ticker'}
    snowflake = Mock()
    snowflake.generate.return_value = ('mock-model', Context.model_validate(FIXTURE['snowflake_context']))
    app.dependency_overrides[get_provider] = lambda: snowflake
    explanation = client.post('/api/companies/AAPL/explain').json()
    response = client.post('/api/companies/AAPL/snowflake-research')
    assert response.status_code == 200 and response.json()['status'] == 'available'
    request = dict(research_event_id='AAPL:2026-10-02', snowflake_context=response.json()['context'],
                   gemini_explanation=explanation)
    request['document'] = rd.combine(Context.model_validate(request['snowflake_context']),
                                    rd.VerifiedExplanation.model_validate(explanation)).model_dump()
    return client, engine, gemini, snowflake, audio, request


def test_frontend_backend_golden_document_and_script_match():
    document = rd.combine(Context.model_validate(FIXTURE['snowflake_context']),
                          rd.VerifiedExplanation.model_validate(FIXTURE['gemini_explanation']))
    assert document.model_dump() == FIXTURE['document']
    assert rd.script('AAPL', document) == FIXTURE['script']


@pytest.mark.parametrize('source', ['both', 'snowflake', 'gemini'])
def test_verified_document_only_is_synthesized_without_model_calls(generated, source):
    client, _, gemini, snowflake, audio, request = generated
    if source == 'gemini': request.pop('snowflake_context')
    if source == 'snowflake': request.pop('gemini_explanation')
    request['document'] = rd.combine(
        Context.model_validate(request['snowflake_context']) if 'snowflake_context' in request else None,
        rd.VerifiedExplanation.model_validate(request['gemini_explanation']) if 'gemini_explanation' in request else None,
    ).model_dump()
    response = client.post('/api/companies/AAPL/research-audio', json=request)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {'ticker', 'transcript', 'status', 'audio_base64', 'audio_mime_type'}
    assert body['status'] == 'ok' and body['audio_mime_type'] == 'audio/mpeg' and body['audio_base64']
    expected = rd.script('AAPL', rd.ResearchDocument.model_validate(request['document']))
    assert body['transcript'] == audio.synthesize.call_args.args[0] == expected
    assert gemini.generate.call_count == snowflake.generate.call_count == 1
    if source == 'snowflake': assert 'Quantitative AI interpretation was unavailable.' in expected
    if source == 'gemini': assert 'Qualitative research context was unavailable.' in expected


@pytest.mark.parametrize('change', ['document', 'whitespace', 'source', 'ticker', 'attribution', 'omission', 'no_sources'])
def test_altered_or_arbitrary_research_never_reaches_speech(generated, change):
    client, _, _, _, audio, request = generated
    if change == 'document': request['document']['sections'][0]['items'][0] = 'Buy now for a guaranteed 999% return.'
    elif change == 'whitespace': request['document']['sections'][0]['items'][0] += ' '
    elif change == 'source': request['snowflake_context']['event_context'] = ['An invented price of 999 dollars.']
    elif change == 'ticker': request['gemini_explanation']['ticker'] = 'BRK.B'
    elif change == 'attribution': request['document']['sources'] = ['Unknown provider']
    elif change == 'omission': request['document']['sections'].pop()
    else:
        request.pop('snowflake_context'); request.pop('gemini_explanation')
    assert client.post('/api/companies/AAPL/research-audio', json=request).status_code == 403
    audio.synthesize.assert_not_called()


@pytest.mark.parametrize('change', ['extra', 'raw_text', 'malformed_source', 'oversized_string', 'too_many_sections'])
def test_strict_request_shape_rejects_bad_input(generated, change):
    client, _, _, _, audio, request = generated
    if change == 'extra': request['raw_text'] = 'arbitrary speech'
    elif change == 'raw_text': request = {'text': 'arbitrary speech'}
    elif change == 'malformed_source': request['gemini_explanation']['extra'] = 'untrusted'
    elif change == 'oversized_string': request['document']['sections'][0]['items'][0] = 'x' * 701
    else: request['document']['sections'] *= 2
    assert client.post('/api/companies/AAPL/research-audio', json=request).status_code == 422
    audio.synthesize.assert_not_called()


def test_total_script_size_is_bounded(generated):
    client, _, _, _, audio, request = generated
    request['document']['sections'][0]['items'] = ['x' * 700] * 40
    assert client.post('/api/companies/AAPL/research-audio', json=request).status_code == 413
    audio.synthesize.assert_not_called()


@pytest.mark.parametrize('change', ['event', 'company', 'new_event', 'evidence', 'expired'])
def test_stale_or_expired_verification_never_reaches_audio(generated, monkeypatch, change):
    from app.db.models import ResearchEvent
    client, engine, _, _, audio, request = generated
    path = '/api/companies/AAPL/research-audio'
    expected = 403
    if change == 'event': request['research_event_id'] = 'AAPL:2026-10-03'; expected = 409
    elif change == 'company': path = '/api/companies/MSFT/research-audio'; expected = 409
    elif change == 'new_event':
        with Session(engine) as session, session.begin(): session.add(research(day=date(2026, 10, 5)))
        expected = 409
    elif change == 'evidence':
        with Session(engine) as session, session.begin(): session.get(ResearchEvent, request['research_event_id']).aggregate_purchase_value = 99
    else: monkeypatch.setattr(rd, 'monotonic', lambda: 10 ** 12)
    assert client.post(path, json=request).status_code == expected
    audio.synthesize.assert_not_called()


def test_audio_failure_keeps_exact_document_transcript(generated):
    client, _, gemini, snowflake, audio, request = generated
    audio.synthesize.side_effect = ProviderFailure('private error')
    result = client.post('/api/companies/AAPL/research-audio', json=request).json()
    assert result['status'] == 'audio_unavailable'
    assert result['audio_base64'] is None and result['audio_mime_type'] is None
    assert result['transcript'] == rd.script('AAPL', rd.ResearchDocument.model_validate(request['document']))
    assert 'private error' not in str(result)
    assert gemini.generate.call_count == snowflake.generate.call_count == 1


@pytest.mark.parametrize('category,expected', [
    ('provider_timeout', 'provider_timeout'), ('provider_http_error', 'provider_http_error'),
    ('provider_invalid_response', 'provider_invalid_response'), ('empty_audio', 'empty_audio'),
    ('configuration_unavailable', 'configuration_unavailable'), ('PRIVATE_CATEGORY', 'other'),
])
def test_safe_audio_failure_diagnostic(generated, caplog, category, expected):
    client, _, _, _, audio, request = generated
    audio.synthesize.side_effect = ProviderFailure('PRIVATE_EXCEPTION', reason_category=category)
    response = client.post('/api/companies/AAPL/research-audio', json=request)
    assert response.status_code == 200
    result = response.json()
    assert result == dict(ticker='AAPL', status='audio_unavailable', audio_base64=None,
                         audio_mime_type=None, transcript=rd.script(
                             'AAPL', rd.ResearchDocument.model_validate(request['document'])))
    records = [r for r in caplog.records if r.name == rd.__name__]
    assert len(records) == 1 and records[0].exc_info is None
    assert records[0].getMessage() == (
        'Research audio unavailable ticker=AAPL research_event_id=AAPL:2026-10-02 '
        f'audio_reason={expected}')
    for private in ('PRIVATE_EXCEPTION', 'PRIVATE_CATEGORY', result['transcript'],
                    'Authorization', 'xi-api-key', 'audio_base64', 'https://'):
        assert private not in records[0].getMessage()


@pytest.mark.parametrize('audio_value,expected', [(b'', 'empty_audio'),
    (None, 'provider_invalid_response'), (b'x' * (5 * 1024 * 1024 + 1), 'provider_invalid_response')],
    ids=['empty', 'wrong_type', 'oversized'])
def test_audio_result_validation_diagnostic(generated, caplog, audio_value, expected):
    client, _, _, _, audio, request = generated
    audio.synthesize.return_value = audio_value
    response = client.post('/api/companies/AAPL/research-audio', json=request)
    assert response.status_code == 200 and response.json()['status'] == 'audio_unavailable'
    assert f'audio_reason={expected}' in caplog.text


def test_success_and_verification_failure_do_not_log_audio_fallback(generated, caplog):
    client, _, _, _, audio, request = generated
    assert client.post('/api/companies/AAPL/research-audio', json=request).json()['status'] == 'ok'
    audio.synthesize.reset_mock()
    rd.validated_research.entries.clear()
    assert client.post('/api/companies/AAPL/research-audio', json=request).status_code == 403
    audio.synthesize.assert_not_called()
    assert 'audio_reason=' not in caplog.text


@pytest.mark.parametrize('case,expected', [
    ('timeout', 'provider_timeout'), ('http', 'provider_http_error'),
    ('redirect', 'provider_http_error'), ('mime', 'provider_invalid_response'),
    ('signature', 'provider_invalid_response'), ('oversize', 'provider_invalid_response'),
    ('empty', 'empty_audio'), ('configuration', 'configuration_unavailable'),
    ('voice', 'configuration_unavailable'), ('unknown', 'other'),
])
def test_real_audio_adapter_safe_diagnostics(generated, monkeypatch, caplog, case, expected):
    from urllib.error import HTTPError
    from unittest.mock import MagicMock
    from app.api.ai import get_elevenlabs
    from app.services import ai_providers
    from test_ai_services import REAL_POST
    client, _, _, _, _, request = generated
    client.app.dependency_overrides[get_elevenlabs] = ai_providers.ElevenLabsProvider
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'PRIVATE_API_KEY')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'PRIVATE_VOICE')
    response = MagicMock()
    response.headers.get_content_type.return_value = 'audio/mpeg'
    response.read.return_value = b'ID3PRIVATE_AUDIO'
    opener = Mock()
    opener.open.return_value.__enter__ = Mock(return_value=response)
    opener.open.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(ai_providers, 'build_opener', Mock(return_value=opener))
    monkeypatch.setattr(ai_providers, 'post', REAL_POST)
    if case == 'timeout': opener.open.side_effect = TimeoutError('PRIVATE_EXCEPTION')
    elif case in ('http', 'redirect'):
        opener.open.side_effect = HTTPError('https://private.invalid', 302 if case == 'redirect' else 503,
                                            'PRIVATE_EXCEPTION', {}, None)
    elif case == 'mime': response.headers.get_content_type.return_value = 'application/json'
    elif case == 'signature': response.read.return_value = b'PRIVATE_AUDIO'
    elif case == 'oversize': response.read.return_value = b'x' * (5 * 1024 * 1024 + 1)
    elif case == 'empty': response.read.return_value = b''
    elif case == 'configuration': monkeypatch.delenv('ELEVENLABS_API_KEY')
    elif case == 'voice': monkeypatch.setenv('ELEVENLABS_VOICE_ID', '')
    elif case == 'unknown': opener.open.side_effect = OSError('PRIVATE_EXCEPTION')
    result = client.post('/api/companies/AAPL/research-audio', json=request)
    assert result.status_code == 200 and result.json()['status'] == 'audio_unavailable'
    assert f'audio_reason={expected}' in caplog.text
    for private in ('PRIVATE_API_KEY', 'PRIVATE_VOICE', 'PRIVATE_AUDIO', 'PRIVATE_EXCEPTION',
                    'https://private.invalid', result.json()['transcript'], 'xi-api-key', 'Authorization'):
        assert private not in caplog.text


def test_legacy_brief_is_unchanged(generated):
    client, _, gemini, snowflake, audio, _ = generated
    result = client.post('/api/companies/AAPL/brief').json()
    assert result['status'] == 'ok' and 'Research Summary' not in result['transcript']
    assert 'not investment advice' in result['transcript']
    assert gemini.generate.call_count == snowflake.generate.call_count == 1


def test_unknown_ticker_does_not_call_audio(generated):
    client, _, _, _, audio, request = generated
    assert client.post('/api/companies/UNKNOWN/research-audio', json=request).status_code == 404
    audio.synthesize.assert_not_called()


def test_hash_cache_is_bounded_evidence_bound_and_expires(monkeypatch):
    clock = [100.]
    monkeypatch.setattr(rd, 'monotonic', lambda: clock[0])
    cache = rd.ValidatedResearch(capacity=1, ttl=10)
    cache.remember('gemini', {'event': 'one'}, {'text': 'verified'})
    assert cache.contains('gemini', {'event': 'one'}, {'text': 'verified'})
    assert not cache.contains('gemini', {'event': 'two'}, {'text': 'verified'})
    assert not cache.contains('gemini', {'event': 'one'}, {'text': 'altered'})
    assert 'verified' not in str(cache.entries)
    clock[0] += 11
    assert not cache.contains('gemini', {'event': 'one'}, {'text': 'verified'})
    cache.remember('snowflake', {}, {})
    assert len(cache.entries) == 1
