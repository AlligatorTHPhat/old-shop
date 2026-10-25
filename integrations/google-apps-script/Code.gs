/**
 * OldShop contact relay, deployed as a Web App.
 *
 *   POST  signed JSON from the backend  -> new ticket row + emails
 *   POST  legacy form fields            -> same, only if ALLOW_UNSIGNED_FORM=true
 *   GET                                 -> health check
 *
 * Apps Script always answers HTTP 200, so the outcome is in the body: {ok, ticketId?, error?}.
 */

function doGet() {
  return json_({ ok: true, service: 'oldshop-contact-relay', time: new Date().toISOString() });
}

function doPost(e) {
  try {
    var config = getConfig();
    var message = parseRequest_(e, config);
    var ticket = createTicket_(message, config);
    return json_({ ok: true, ticketId: ticket.ticketId, duplicate: ticket.duplicate });
  } catch (err) {
    // Expected rejections (bad signature, validation) are not worth a stack trace.
    if (!(err instanceof RelayError)) console.error(err);
    return json_({ ok: false, error: err.message });
  }
}

/** Normalise both request shapes into one message object. */
function parseRequest_(e, config) {
  var body = e && e.postData && e.postData.contents;
  var envelope = null;
  if (body && e.postData.type === 'application/json') {
    try {
      envelope = JSON.parse(body);
    } catch (ignored) {
      throw new RelayError('Malformed JSON');
    }
  }

  if (envelope && envelope.signature) {
    verifyEnvelope_(envelope, config.sharedSecret);
    return validateMessage_(JSON.parse(envelope.payload));
  }

  if (!config.allowUnsignedForm) throw new RelayError('Unsigned requests are disabled');
  var p = (e && e.parameter) || {};
  var message = validateMessage_({
    fullName: p.fullName,
    email: p.email,
    phone: p.phone,
    subject: p.subject,
    message: p.message,
    source: 'legacy-form'
  });
  throttleUnsigned_(message.email);
  return message;
}

function validateMessage_(m) {
  var clean = {
    feedbackId: m.feedbackId ? String(m.feedbackId) : '',
    fullName: trim_(m.fullName, 100),
    email: trim_(m.email, 255).toLowerCase(),
    phone: trim_(m.phone, 20),
    subject: trim_(m.subject, 200) || 'Liên hệ từ website',
    message: trim_(m.message, LIMITS.MESSAGE_MAX_LENGTH),
    source: trim_(m.source, 30) || 'web'
  };
  if (!clean.fullName) throw new RelayError('fullName is required');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(clean.email)) throw new RelayError('email is invalid');
  if (!clean.message) throw new RelayError('message is required');
  return clean;
}

function createTicket_(message, config) {
  // The backend retries on network errors; the same feedback must not create two tickets.
  if (message.feedbackId) {
    var existing = findTicketByBackendId_(config, message.feedbackId);
    if (existing) return { ticketId: existing, duplicate: true };
  }

  var ticketId = newTicketId_();
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    appendTicket_(config, ticketId, message);
  } finally {
    lock.releaseLock();
  }

  notifyAdmins_(config, ticketId, message);
  sendAutoReply_(config, ticketId, message);
  return { ticketId: ticketId, duplicate: false };
}

/** OS-YYMMDD-XXXX, short enough to read over the phone. */
function newTicketId_() {
  var date = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyMMdd');
  var suffix = Utilities.getUuid().replace(/-/g, '').slice(0, 4).toUpperCase();
  return 'OS-' + date + '-' + suffix;
}

function RelayError(message) {
  this.name = 'RelayError';
  this.message = message;
}
RelayError.prototype = Object.create(Error.prototype);

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}

function trim_(value, maxLength) {
  return String(value == null ? '' : value).trim().slice(0, maxLength);
}
