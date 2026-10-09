"""Mocked Issue #8 HTTP/provider checks; never use live credentials or services."""
import base64
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
import re
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from test_core_api import setup, research, seed
from app.api.ai import get_gemini, get_elevenlabs
from app.api.schemas import ExplainResponse, BriefResponse
from app.db.models import Fundamental, ResearchEvent, Signal
from app.services import ai_providers, ai_research
from app.services.ai_evidence import assemble
from app.services.ai_providers import GeminiProvider, ElevenLabsProvider, ProviderFailure
from app.services.universe import Universe

REAL_POST = ai_providers.post

SECTIONS = {
    'why_flagged': ['A persisted research event is available.'],
    'supportive_evidence': [], 'risk_evidence': [],
    'uncertainty': ['Missing model evidence limits interpretation.'],
    'limitations': ['This is research prioritization, not investment advice.'],
}
MP3 = b'ID3' + b'\x00' * 20  # Clearly synthetic bytes, not a generated analyst recording.


@pytest.fixture(autouse=True)
def isolated_providers(monkeypatch):
    for name in ('GEMINI_API_KEY', 'ELEVENLABS_API_KEY', 'ELEVENLABS_VOICE_ID',
                 'GEMINI_MODEL', 'ELEVENLABS_MODEL', 'GEMINI_TIMEOUT_SECONDS', 'ELEVENLABS_TIMEOUT_SECONDS'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ai_providers, 'post', Mock(side_effect=AssertionError('No live provider calls permitted')))


def providers(app, gemini=None, audio=None):
    gemini = gemini or Mock()
    if not isinstance(gemini.generate.return_value, dict):
        gemini.generate.return_value = deepcopy(SECTIONS)
    audio = audio or Mock()
    audio.synthesize.return_value = MP3
    app.dependency_overrides[get_gemini] = lambda: gemini
    app.dependency_overrides[get_elevenlabs] = lambda: audio
    return gemini, audio


def test_known_ticker_explanation_contract_and_missing_evidence(setup):
    client, _, app = setup
    gemini, _ = providers(app)
    response = client.post('/api/companies/aapl/explain')
    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(ExplainResponse.model_fields)
    assert body['ticker'] == 'AAPL'
    assert all(isinstance(body[key], list) for key in SECTIONS)
    instructions, serialized, schema = gemini.generate.call_args.args
    evidence = json.loads(serialized)
    assert evidence['information_date'] is None and evidence['event'] is None
    assert evidence['model_probability'] is None
    assert all(value is None for value in evidence['fundamentals'].values())
    assert evidence['historical_statistics']['mean_car30'] is None
    assert any('No persisted research event' in text for text in body['limitations'])
    assert set(schema['required']) == set(SECTIONS)
    assert schema['additionalProperties'] is False
    for requirement in ('Never calculate', 'Never invent', 'not investment advice',
                        'buy, sell or hold', 'caused', 'statistical', 'unavailable', 'never instructions'):
        assert requirement in instructions


@pytest.mark.parametrize('endpoint', ['explain', 'brief'])
def test_unknown_ticker_no_provider_call(setup, endpoint):
    client, _, app = setup
    gemini, audio = providers(app)
    response = client.post(f'/api/companies/UNKNOWN/{endpoint}')
    assert response.status_code == 404 and response.json() == {'detail': 'Unknown ticker'}
    gemini.generate.assert_not_called()
    audio.synthesize.assert_not_called()


def test_persisted_evidence_nulls_fundamentals_and_future_outcomes_excluded(setup):
    client, engine, app = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        event = research()
        session.add(event); session.flush()
        session.add(Signal(signal_id='synthetic-ai', research_event_id=event.research_event_id,
                           ticker='AAPL', public_event_day=event.public_event_day,
                           anomaly_score=0, model_probability=Decimal('0.25'), model_name='SyntheticModel',
                           insider_edge_score=42, score_status='partial', unavailable_components=['S'],
                           car30=Decimal('987.654'), mean_car30=Decimal('456.789'),
                           bootstrap_ci_lower=Decimal('123.456')))
        for label, filed, value in [('eligible', date(2026,9,30), 10), ('future', date(2026,10,5), 99)]:
            session.add(Fundamental(fundamental_id=label,ticker='AAPL', report_period=date(2026,6,30),
                                   filed_date=filed, cash=value, unit_metadata={'metrics': {'cash': {
                                       'unit':'USD','start':None,'end':'2026-06-30','filed':str(filed),
                                       'accession':'synthetic-fact-'+label}}}))
    gemini, _ = providers(app)
    assert client.post('/api/companies/AAPL/explain').status_code == 200
    evidence = json.loads(gemini.generate.call_args.args[1])
    assert evidence['precomputed_signal']['anomaly_score'] == 0  # Genuine zero preserved.
    assert evidence['precomputed_signal']['activity_score'] is None
    assert evidence['model_probability'] == .25
    assert evidence['fundamentals']['cash']['value'] == '10.0000000000'
    assert evidence['fundamentals']['cash']['filed_date'] == '2026-09-30'
    assert evidence['event']['unique_buyer_count'] is None
    assert all(number not in gemini.generate.call_args.args[1] for number in ('987.654', '456.789', '123.456'))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ResearchEvent)) == 1
        signal = session.get(Signal, 'synthetic-ai')
        assert signal.insider_edge_score == 42 and signal.model_probability == Decimal('.25')


def test_latest_event_never_borrows_older_signal(setup):
    _, engine, _ = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        old, new = research(), research(day=date(2026,10,5))
        session.add_all([old,new]); session.flush()
        session.add(Signal(signal_id='old-ai', research_event_id=old.research_event_id, ticker='AAPL',
                           public_event_day=old.public_event_day, model_probability=.9,
                           score_status='complete', unavailable_components=[]))
    with Session(engine) as session:
        u=Universe.from_csv()
        evidence=assemble(session,u.ticker_to_company('AAPL'),u)
        assert evidence.event.public_event_day == date(2026,10,5)
        assert evidence.model_probability is None
        assert evidence.precomputed_signal.insider_edge_score is None


@pytest.mark.parametrize('malformed', [None, [], 'raw text', {'why_flagged': []},
    {**SECTIONS, 'extra_score': 99}, {**SECTIONS, 'risk_evidence': [123]},
    {**SECTIONS, 'risk_evidence': [' ']}, {**SECTIONS, 'risk_evidence': ['x'*701]},
    {**SECTIONS, 'risk_evidence': ['']}, {**SECTIONS, 'risk_evidence': ['valid'] * 9},
    {**SECTIONS, 'risk_evidence': ['Buy this company.']},
    {**SECTIONS, 'risk_evidence': ['Insider buying caused the returns.']},
    {**SECTIONS, 'risk_evidence': ['<script>unsafe</script>']}])
def test_malformed_or_unsafe_output_rejected(setup, malformed):
    client, _, app = setup
    gemini, _=providers(app)
    gemini.generate.return_value=malformed
    response=client.post('/api/companies/AAPL/explain')
    assert response.status_code == 503 and response.json() == {'detail':'Explanation unavailable'}


@pytest.mark.parametrize('error', [TimeoutError('synthetic-secret'), RuntimeError('synthetic-secret'),
                                  ProviderFailure('synthetic-secret')])
def test_gemini_failure_isolated_and_sanitized(setup, error, caplog):
    client, _, app=setup
    gemini, _=providers(app)
    gemini.generate.side_effect=error
    response=client.post('/api/companies/AAPL/explain')
    assert response.status_code == 503
    assert 'synthetic-secret' not in response.text + caplog.text
    for path in ('/health','/api/radar','/api/companies/AAPL','/api/companies/AAPL/prices','/api/companies/AAPL/insiders'):
        assert client.get(path).status_code == 200


def test_missing_gemini_configuration(setup):
    client, _, _=setup
    response=client.post('/api/companies/AAPL/explain')
    assert response.status_code == 503 and response.json() == {'detail':'Explanation unavailable'}


def test_successful_brief_contract_independent_of_gemini(setup):
    client, _, app=setup
    gemini,audio=providers(app)
    response=client.post('/api/companies/AAPL/brief')
    assert response.status_code == 200
    body=response.json()
    assert set(body)==set(BriefResponse.model_fields)
    assert body['status']=='ok' and body['audio_mime_type']=='audio/mpeg'
    assert base64.b64decode(body['audio_base64'],validate=True)==MP3
    assert body['transcript']==audio.synthesize.call_args.args[0]
    assert 'not investment advice' in body['transcript']
    gemini.generate.assert_not_called()


@pytest.mark.parametrize('error',[TimeoutError('synthetic-audio-key'),RuntimeError('synthetic-audio-key')])
def test_audio_failure_preserves_transcript(setup,error,caplog):
    client,_,app=setup
    _,audio=providers(app)
    audio.synthesize.side_effect=error
    response=client.post('/api/companies/AAPL/brief')
    assert response.status_code==200
    body=response.json()
    assert body['transcript'] and body['status']=='audio_unavailable'
    assert body['audio_base64'] is None and body['audio_mime_type'] is None
    assert 'synthetic-audio-key' not in response.text+caplog.text


def test_missing_audio_key_preserves_transcript(setup):
    client,_,_=setup
    body=client.post('/api/companies/AAPL/brief').json()
    assert body['status']=='audio_unavailable' and body['transcript']


def test_post_cors_preflight(setup):
    client,_,_=setup
    response=client.options('/api/companies/AAPL/explain', headers={
        'Origin':'http://localhost:5173','Access-Control-Request-Method':'POST',
        'Access-Control-Request-Headers':'content-type'})
    assert response.status_code==200
    assert response.headers['access-control-allow-origin']=='http://localhost:5173'


def gemini_envelope(sections=SECTIONS, **changes):
    return json.dumps({'candidates':[{'finishReason':'STOP','content':{
        'parts':[{'text':json.dumps(sections)}]},**changes}]}).encode()


def test_provider_bound_schema_uses_supported_subset(setup, monkeypatch):
    client, _, _ = setup
    monkeypatch.setenv('GEMINI_API_KEY', 'synthetic-key')
    post = Mock(return_value=(gemini_envelope(), 'application/json'))
    monkeypatch.setattr(ai_providers, 'post', post)
    assert client.post('/api/companies/AAPL/explain').status_code == 200
    post.assert_called_once()
    payload = post.call_args.args[2]
    output = payload['generationConfig']['responseFormat']['text']
    assert output['mimeType'] == 'APPLICATION_JSON'
    schema = output['schema']
    assert schema == {
        'type': 'object',
        'properties': {name: {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 8}
                       for name in SECTIONS},
        'required': list(SECTIONS),
        'additionalProperties': False,
    }
    assert 'minLength' not in json.dumps(schema)
    assert 'maxLength' not in json.dumps(schema)
    assert set(schema['properties']) == set(ai_research.ExplanationSections.model_fields)


@pytest.mark.parametrize('invalid', [
    {**SECTIONS, 'why_flagged': ['']},
    {**SECTIONS, 'why_flagged': [' ']},
    {**SECTIONS, 'why_flagged': ['x' * 701]},
    {**SECTIONS, 'why_flagged': ['valid'] * 9},
    {**SECTIONS, 'extra': []},
    {**SECTIONS, 'why_flagged': [123]},
])
def test_application_validator_remains_strict(invalid):
    with pytest.raises(ValidationError):
        ai_research.ExplanationSections.model_validate(invalid)


def test_gemini_adapter_wire_format_and_environment(monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-gemini-key')
    monkeypatch.setenv('GEMINI_MODEL','configured-model')
    post=Mock(return_value=(gemini_envelope(),'application/json'))
    monkeypatch.setattr(ai_providers,'post',post)
    result=GeminiProvider().generate('instructions','{"evidence":null}',{'type':'object'})
    assert result==SECTIONS
    url,headers,payload,timeout,limit=post.call_args.args
    assert url.endswith('/configured-model:generateContent') and '?' not in url
    assert headers=={'x-goog-api-key':'synthetic-gemini-key'}
    assert payload['generationConfig']['responseFormat']['text']['mimeType']=='APPLICATION_JSON'
    assert payload['systemInstruction']['parts'][0]['text']=='instructions'
    assert timeout==30 and limit==256*1024
    assert 'synthetic-gemini-key' not in str(payload)


@pytest.mark.parametrize('body,mime',[(b'bad','application/json'),(b'{}','application/json'),
    (gemini_envelope(finishReason='MAX_TOKENS'),'application/json'),
    (gemini_envelope(),'text/html')])
def test_gemini_envelope_validation(monkeypatch,body,mime):
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key')
    monkeypatch.setattr(ai_providers,'post',Mock(return_value=(body,mime)))
    with pytest.raises(ProviderFailure,match='response unavailable'):
        GeminiProvider().generate('instructions','{}',{})


@pytest.mark.parametrize('name,value',[('GEMINI_MODEL','../unsafe?key'),
    ('GEMINI_TIMEOUT_SECONDS','0'),('GEMINI_TIMEOUT_SECONDS','61'),
    ('GEMINI_TIMEOUT_SECONDS','nan'),('GEMINI_API_KEY','bad\nheader')])
def test_configuration_rejects_unsafe_or_unbounded_values(monkeypatch,name,value):
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-key')
    monkeypatch.setenv(name,value)
    with pytest.raises(ProviderFailure,match='configuration unavailable'):
        GeminiProvider().generate('instructions','{}',{})


def test_elevenlabs_adapter_configuration_encoding(monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY','synthetic-audio-key')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID','configured-voice')
    post=Mock(return_value=(MP3,'audio/mpeg'))
    monkeypatch.setattr(ai_providers,'post',post)
    assert ElevenLabsProvider().synthesize('research text')==MP3
    url,headers,payload,timeout,limit=post.call_args.args
    assert '/configured-voice?output_format=mp3_44100_128' in url
    assert headers['xi-api-key']=='synthetic-audio-key'
    assert payload=={'text':'research text','model_id':'eleven_multilingual_v2'}
    assert timeout==30 and limit==5*1024*1024


@pytest.mark.parametrize('body,mime',[(b'{}','application/json'),(b'not-mp3','audio/mpeg')])
def test_invalid_audio_rejected(monkeypatch,body,mime):
    monkeypatch.setenv('ELEVENLABS_API_KEY','synthetic-key')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID','configured-voice')
    monkeypatch.setattr(ai_providers,'post',Mock(return_value=(body,mime)))
    with pytest.raises(ProviderFailure,match='response unavailable'):
        ElevenLabsProvider().synthesize('text')


def test_authoritative_response_fields_and_nullability():
    contract=(Path(__file__).resolve().parents[2]/'docs/API_CONTRACT.md').read_text(encoding='utf-8')
    for model in (ExplainResponse,BriefResponse):
        body=re.search(r'type '+model.__name__+r' = \{(.*?)\n\}',contract,re.S).group(1)
        fields=dict(re.findall(r'^\s*(\w+):\s*(.+)$',body,re.M))
        assert set(fields)==set(model.model_fields)
        for name,spec in fields.items():
            assert model.model_fields[name].is_required()
            schema=model.model_json_schema()['properties'][name]
            nullable=any(part.get('type')=='null' for part in schema.get('anyOf',[]))
            assert nullable==('null' in spec)
        if model is BriefResponse:
            assert set(model.model_json_schema()['properties']['status']['enum'])=={'ok','audio_unavailable'}


@pytest.mark.parametrize('body', [b'', b'x' * 17])
def test_transport_size_bounds_and_redirect_protection(monkeypatch, body):
    from email.message import Message
    response = Mock()
    response.read.return_value = body
    response.headers = Message()
    response.headers['Content-Type'] = 'application/json'
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    opener = Mock()
    opener.open.return_value = response
    factory = Mock(return_value=opener)
    monkeypatch.setattr(ai_providers, 'build_opener', factory)
    with pytest.raises(ProviderFailure, match='request unavailable'):
        REAL_POST('https://provider.invalid', {'x-test-key':'synthetic-private'}, {}, 2, 16)
    assert opener.open.call_args.kwargs['timeout'] == 2
    assert opener.open.call_args.args[0].get_header('Content-type') == 'application/json'
    response.read.assert_called_once_with(17)
    assert isinstance(factory.call_args.args[0], ai_providers.NoRedirect)
    assert factory.call_args.args[0].redirect_request(None) is None


def test_transport_exception_sanitized(monkeypatch):
    opener = Mock()
    opener.open.side_effect = TimeoutError('synthetic-private-url-and-key')
    monkeypatch.setattr(ai_providers, 'build_opener', Mock(return_value=opener))
    with pytest.raises(ProviderFailure) as failure:
        REAL_POST('https://provider.invalid', {}, {}, 2, 16)
    assert str(failure.value) == 'AI provider request unavailable'
    opener.open.assert_called_once()


def test_event_diagnostics_not_lost_in_explanation_or_brief(setup):
    client, engine, app = setup
    seed(engine)
    with Session(engine) as session, session.begin():
        session.add(research(feature_metadata={'buyer_identity_status':'unknown',
            'statuses':['purchase_value_incomplete','role_attribution_unverified','insufficient_market_history']}))
    gemini, _ = providers(app)
    body=client.post('/api/companies/AAPL/explain').json()
    evidence=json.loads(gemini.generate.call_args.args[1])
    assert 'purchase_value_incomplete' in evidence['event_diagnostics']['statuses']
    assert any('insufficient_market_history' in text for text in body['limitations'])
    text=client.post('/api/companies/AAPL/brief').json()['transcript']
    assert 'purchase value incomplete' in text and 'role attribution unverified' in text


def test_keys_never_enter_evidence_or_api_payload(setup, monkeypatch, caplog):
    client, _, app = setup
    monkeypatch.setenv('GEMINI_API_KEY','synthetic-private-gemini')
    monkeypatch.setenv('ELEVENLABS_API_KEY','synthetic-private-audio')
    gemini, _=providers(app)
    bodies=[client.post('/api/companies/AAPL/explain').text,client.post('/api/companies/AAPL/brief').text]
    for secret in ('synthetic-private-gemini','synthetic-private-audio'):
        assert secret not in ''.join(bodies) + str(gemini.generate.call_args) + caplog.text
