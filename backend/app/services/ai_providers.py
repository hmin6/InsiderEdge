"""Small REST adapters. No SDK dependency, provider logging, or automatic retries."""
import json
import os
import re
from urllib.request import Request, build_opener, HTTPRedirectHandler


class ProviderFailure(RuntimeError):
    """Only sanitized public messages cross the provider boundary."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        # Never forward credential headers to a redirect target.
        return None


def post(url, headers, payload, timeout, limit):
    try:
        request = Request(url, data=json.dumps(payload, allow_nan=False).encode('utf-8'),
                          headers={'Content-Type': 'application/json', **headers}, method='POST')
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            body = response.read(limit + 1)
            mime = response.headers.get_content_type()
        if not body or len(body) > limit:
            raise ValueError
        return body, mime
    except Exception:
        raise ProviderFailure('AI provider request unavailable') from None


def configuration(key_name, model_name, default_model, timeout_name):
    try:
        key = os.environ[key_name].strip()
        model = os.environ.get(model_name, default_model).strip()
        timeout = float(os.environ.get(timeout_name, '30'))
        if not key or '\r' in key or '\n' in key or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', model):
            raise ValueError
        if not 1 <= timeout <= 60:
            raise ValueError
        return key, model, timeout
    except Exception:
        raise ProviderFailure('AI provider configuration unavailable') from None


class GeminiProvider:
    def generate(self, instructions, evidence, schema):
        key, model, timeout = configuration('GEMINI_API_KEY', 'GEMINI_MODEL',
                                            'gemini-3.8-flash', 'GEMINI_TIMEOUT_SECONDS')
        payload = {
            'systemInstruction': {'parts': [{'text': instructions}]},
            'contents': [{'role': 'user', 'parts': [{'text': evidence}]}],
            'generationConfig': {'candidateCount': 1, 'maxOutputTokens': 4096,
                                 'responseFormat': {'text': {'mimeType': 'APPLICATION_JSON', 'schema': schema}}},
        }
        body, mime = post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                          {'x-goog-api-key': key}, payload, timeout, 256 * 1024)
        try:
            if mime != 'application/json':
                raise ValueError
            response = json.loads(body)
            candidates = response['candidates']
            if len(candidates) != 1 or candidates[0].get('finishReason') != 'STOP':
                raise ValueError
            parts = candidates[0]['content']['parts']
            text = ''.join(part['text'] for part in parts if not part.get('thought', False))
            return json.loads(text)
        except Exception:
            raise ProviderFailure('AI provider response unavailable') from None


class ElevenLabsProvider:
    def synthesize(self, transcript):
        key, model, timeout = configuration('ELEVENLABS_API_KEY', 'ELEVENLABS_MODEL',
                                            'eleven_multilingual_v2', 'ELEVENLABS_TIMEOUT_SECONDS')
        voice = os.environ.get('ELEVENLABS_VOICE_ID', '').strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', voice):
            raise ProviderFailure('Audio provider configuration unavailable')
        body, mime = post(f'https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128',
                          {'xi-api-key': key, 'Accept': 'audio/mpeg'},
                          {'text': transcript, 'model_id': model}, timeout, 5 * 1024 * 1024)
        if mime != 'audio/mpeg' or not (body.startswith(b'ID3') or
                len(body) > 1 and body[0] == 0xff and body[1] & 0xe0 == 0xe0):
            raise ProviderFailure('Audio provider response unavailable')
        return body
