import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_RECORDING_RETRIES,
  canRetryRecording,
  recordingDuration,
  recordingFailure,
  recordingRefreshDelay,
  validateRecordingTicket,
} from '../src/services/labelingRecordingModel.ts';

const ticket = {
  url: 'https://storage.example/evidence.webm?sig=redacted',
  expiresAt: '2026-10-27T14:15:00Z',
  contentType: 'video/webm',
  durationSeconds: 249.6,
  etag: '0xETAG',
  blobVersionId: null,
};

test('recording ticket requires HTTPS, video content type, ETag and valid expiry', () => {
  assert.equal(validateRecordingTicket(ticket), null);
  assert.match(validateRecordingTicket({ ...ticket, url: 'http://storage/evidence.webm' }), /HTTPS/);
  assert.match(validateRecordingTicket({ ...ticket, contentType: 'text/plain' }), /video/);
  assert.match(validateRecordingTicket({ ...ticket, etag: '' }), /ETag/);
  assert.match(validateRecordingTicket({ ...ticket, expiresAt: 'invalid' }), /expiración/);
});
test('persisted evidence duration is used when the ticket has no duration', () => {
  assert.equal(recordingDuration(ticket, 200), 249.6);
  assert.equal(recordingDuration({ ...ticket, durationSeconds: null }, 200), 200);
  assert.equal(recordingDuration({ ...ticket, durationSeconds: null }, null), 0);
});
test('refresh is scheduled before expiry and retries have a hard cap', () => {
  const now = Date.parse('2026-10-27T14:10:00Z');
  assert.equal(recordingRefreshDelay(ticket.expiresAt, now), 270_000);
  assert.equal(recordingRefreshDelay(ticket.expiresAt, Date.parse('2026-10-27T14:14:45Z')), 0);
  assert.equal(canRetryRecording(0), true);
  assert.equal(canRetryRecording(MAX_RECORDING_RETRIES), false);
});

test('deleted and unavailable storage responses produce distinct user states', () => {
  const deleted = recordingFailure({ problem: { title: 'Gone', status: 410, code: 'RECORDING_RETAINED_OR_DELETED' } });
  const unavailable = recordingFailure({ problem: { title: 'Down', status: 503, code: 'STORAGE_UNAVAILABLE' } });
  assert.equal(deleted.kind, 'deleted');
  assert.match(deleted.message, /eliminada|retención/);
  assert.equal(unavailable.kind, 'storage');
  assert.match(unavailable.message, /almacenamiento/);
});
