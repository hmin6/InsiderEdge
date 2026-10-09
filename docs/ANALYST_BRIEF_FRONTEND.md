# Issue #29: optional analyst brief

Owner: Mingquan Lin. Branch: `frontend/29-elevenlabs`. Priority: P1.

AnalystBrief is mounted independently in CompanyPage, replacing only its audio
placeholder. Company fetching, quantitative panels, and Gemini are unchanged.
The component accepts ticker and optional evidenceKey; changing either remounts
the panel, aborts generation, removes playback, and revokes its object URL.

The browser calls only POST `/api/companies/{ticker}/brief` on VITE_API_BASE_URL
(default localhost:8000). No ElevenLabs credentials or provider calls are used.
Responses use the exact BriefResponse contract: transcript, audio_base64,
audio_mime_type, and ok/audio_unavailable status. No fake audio is provided.

Generation is user initiated, blocks duplicate clicks with a synchronous ref,
times out after 30 seconds, and supports retry after failures. Successful briefs
are retained without regeneration. Transcript text is escaped, always available
after success, and survives decoding or playback failure. Native audio controls
provide play/pause; Replay from start resets playback without generating again.
There is no autoplay. Audio uses a Blob URL revoked when content unmounts/changes.
Static skeletons and shared reduced-motion-aware reveal styles are used.

The backend brief endpoint is not currently implemented. Until it is ready,
generation shows a controlled error and leaves all other content usable.

Validation: npm run build, npm test, git diff --check.
Manual review with backend: verify play/pause/replay, audio_unavailable transcript,
invalid audio/playback errors, slow requests/repeated clicks, navigation during
generation/playback, and unchanged Gemini/quantitative content. Browser playback
and object-URL lifecycle are not automatically exercised by rendering/API tests.

PR target: main.

Closes #29
