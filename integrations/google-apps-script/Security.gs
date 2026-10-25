/**
 * Request authentication.
 *
 * Web Apps cannot read HTTP headers, so the backend signs the body instead
 * (backend/app/services/contact_relay.py):
 *
 *   signature = hex(HMAC_SHA256(SHARED_SECRET, timestamp + "." + payload))
 */

function verifyEnvelope_(envelope, secret) {
  if (!secret) throw new Error('SHARED_SECRET is not configured');
  if (typeof envelope.payload !== 'string' || !envelope.timestamp) {
    throw new RelayError('Invalid envelope');
  }

  var age = Math.abs(Date.now() / 1000 - Number(envelope.timestamp));
  if (!(age <= LIMITS.SIGNATURE_MAX_AGE_SECONDS)) throw new RelayError('Expired signature');

  var expected = hmacSha256Hex_(envelope.timestamp + '.' + envelope.payload, secret);
  if (!constantTimeEquals_(expected, String(envelope.signature))) throw new RelayError('Bad signature');
}

function hmacSha256Hex_(value, secret) {
  var bytes = Utilities.computeHmacSha256Signature(value, secret, Utilities.Charset.UTF_8);
  return bytes
    .map(function (b) {
      var v = (b + 256) % 256; // Apps Script returns signed bytes
      return (v < 16 ? '0' : '') + v.toString(16);
    })
    .join('');
}

function constantTimeEquals_(a, b) {
  if (a.length !== b.length) return false;
  var diff = 0;
  for (var i = 0; i < a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

/** Legacy unsigned form posts: at most one per email per minute. */
function throttleUnsigned_(email) {
  var cache = CacheService.getScriptCache();
  var key = 'rl:' + Utilities.base64EncodeWebSafe(email);
  if (cache.get(key)) throw new RelayError('Too many requests, please wait a minute');
  cache.put(key, '1', LIMITS.UNSIGNED_PER_EMAIL_SECONDS);
}
