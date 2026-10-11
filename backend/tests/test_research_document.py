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
