/**
 * Run setup() once from the editor after the first `clasp push`.
 * It formats the sheet and (re)installs the time-driven trigger.
 */
function setup() {
  var config = getConfig();
  if (!config.sharedSecret) throw new Error('Set the SHARED_SECRET script property first');
  getSheet_(config);

  ScriptApp.getProjectTriggers()
    .filter(function (t) { return t.getHandlerFunction() === 'dailyDigest'; })
    .forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('dailyDigest').timeBased().everyDays(1).atHour(8).create();

  console.log('Setup complete. Sheet "%s", digest at 08:00 to %s', config.sheetName, config.adminEmails.join(', '));
}

/** Time-driven: remind admins of tickets nobody picked up. */
function dailyDigest() {
  var config = getConfig();
  sendDailyDigest_(config, getStaleTickets_(config, 24));
}

/**
 * Simple trigger: keep "Resolved at" in sync with the Status dropdown.
 * Runs as the editing user, so it only touches the edited row.
 */
function onEdit(e) {
  var sheet = e.range.getSheet();
  if (sheet.getName() !== getConfig().sheetName || e.range.getColumn() !== COL['Status'] || e.range.getRow() < 2) {
    return;
  }
  var resolvedCell = sheet.getRange(e.range.getRow(), COL['Resolved at']);
  if (e.value === STATUS.RESOLVED) {
    resolvedCell.setValue(new Date());
  } else if (e.oldValue === STATUS.RESOLVED) {
    resolvedCell.clearContent();
  }
}

/** Manual end-to-end check from the editor: builds a signed request exactly like the backend. */
function testSignedRequest() {
  var config = getConfig();
  var payload = JSON.stringify({
    feedbackId: 'test-' + Date.now(),
    fullName: 'Test User',
    email: config.adminEmails[0] || 'test@example.com',
    phone: '0900000000',
    subject: 'Test từ Apps Script editor',
    message: 'Nếu bạn thấy dòng này trong Sheet và nhận được 2 email thì relay hoạt động.',
    source: 'editor-test'
  });
  var timestamp = Math.floor(Date.now() / 1000);
  var envelope = { payload: payload, timestamp: timestamp, signature: hmacSha256Hex_(timestamp + '.' + payload, config.sharedSecret) };
  var response = doPost({ postData: { type: 'application/json', contents: JSON.stringify(envelope) }, parameter: {} });
  console.log(response.getContent());
}
