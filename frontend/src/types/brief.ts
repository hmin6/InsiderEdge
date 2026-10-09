export type BriefResponse = {
  ticker: string;
  transcript: string;
  audio_base64: string | null;
  audio_mime_type: string | null;
  status: 'ok' | 'audio_unavailable';
};
