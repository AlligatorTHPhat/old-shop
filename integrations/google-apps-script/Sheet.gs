/** The bound spreadsheet is the ticket store; one row per contact message. */

function getSheet_(config) {
  var spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = spreadsheet.getSheetByName(config.sheetName);
  if (!sheet) sheet = initSheet_(spreadsheet.insertSheet(config.sheetName));
  return sheet;
}

function initSheet_(sheet) {
  sheet.getRange(1, 1, 1, COLUMNS.length).setValues([COLUMNS]).setFontWeight('bold').setBackground('#f1f3f4');
  sheet.setFrozenRows(1);
  sheet.setColumnWidth(COL['Message'], 420);
  sheet.getRange(2, COL['Message'], sheet.getMaxRows() - 1, 1).setWrap(true);

  var statusRange = sheet.getRange(2, COL['Status'], sheet.getMaxRows() - 1, 1);
  statusRange.setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(Object.keys(STATUS).map(function (k) { return STATUS[k]; }), true)
      .setAllowInvalid(false)
      .build()
  );

  var colors = {};
  colors[STATUS.NEW] = '#fce8e6';
  colors[STATUS.IN_PROGRESS] = '#fef7e0';
  colors[STATUS.RESOLVED] = '#e6f4ea';
  colors[STATUS.SPAM] = '#e8eaed';
  sheet.setConditionalFormatRules(
    Object.keys(colors).map(function (status) {
      return SpreadsheetApp.newConditionalFormatRule()
        .whenTextEqualTo(status)
        .setBackground(colors[status])
        .setRanges([statusRange])
        .build();
    })
  );
  return sheet;
}

function appendTicket_(config, ticketId, m) {
  var row = new Array(COLUMNS.length).fill('');
  row[COL['Ticket ID'] - 1] = ticketId;
  row[COL['Received at'] - 1] = new Date();
  row[COL['Name'] - 1] = m.fullName;
  row[COL['Email'] - 1] = m.email;
  // Leading apostrophe keeps phone numbers like 0909... from losing their zero.
  row[COL['Phone'] - 1] = m.phone ? "'" + m.phone : '';
  row[COL['Subject'] - 1] = m.subject;
  row[COL['Message'] - 1] = m.message;
  row[COL['Source'] - 1] = m.source;
  row[COL['Backend ID'] - 1] = m.feedbackId;
  row[COL['Status'] - 1] = STATUS.NEW;
  getSheet_(config).appendRow(sanitizeRow_(row));
}

function findTicketByBackendId_(config, feedbackId) {
  var sheet = getSheet_(config);
  var last = sheet.getLastRow();
  if (last < 2) return null;
  var match = sheet
    .getRange(2, COL['Backend ID'], last - 1, 1)
    .createTextFinder(String(feedbackId))
    .matchEntireCell(true)
    .findNext();
  return match ? sheet.getRange(match.getRow(), COL['Ticket ID']).getValue() : null;
}

/** Tickets still NEW after `hours`, oldest first. */
function getStaleTickets_(config, hours) {
  var sheet = getSheet_(config);
  var last = sheet.getLastRow();
  if (last < 2) return [];
  var cutoff = Date.now() - hours * 3600 * 1000;
  return sheet
    .getRange(2, 1, last - 1, COLUMNS.length)
    .getValues()
    .filter(function (r) {
      return r[COL['Status'] - 1] === STATUS.NEW && new Date(r[COL['Received at'] - 1]).getTime() < cutoff;
    })
    .map(function (r) {
      return {
        ticketId: r[COL['Ticket ID'] - 1],
        receivedAt: r[COL['Received at'] - 1],
        name: r[COL['Name'] - 1],
        email: r[COL['Email'] - 1],
        subject: r[COL['Subject'] - 1]
      };
    });
}

/**
 * A cell starting with = + - @ is evaluated as a formula by Sheets; prefix it so user input
 * can never inject one (CSV/formula injection).
 */
function sanitizeRow_(row) {
  return row.map(function (v) {
    return typeof v === 'string' && /^[=+\-@]/.test(v) ? "'" + v : v;
  });
}
