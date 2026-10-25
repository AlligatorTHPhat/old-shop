/**
 * Configuration lives in Script Properties (Project Settings > Script properties),
 * never in code, so the repository holds no secret.
 *
 *   SHARED_SECRET        same value as GAS_SHARED_SECRET in the backend .env (required)
 *   ADMIN_EMAILS         comma-separated list notified for every new ticket (required)
 *   SHOP_NAME            shown in emails (default "OldShop")
 *   SHOP_URL             link in the auto-reply (default "")
 *   SHEET_NAME           tab used as the ticket table (default "Contacts")
 *   ALLOW_UNSIGNED_FORM  "true" to also accept the legacy browser form post (default "false")
 */

var STATUS = {
  NEW: 'NEW',
  IN_PROGRESS: 'IN_PROGRESS',
  RESOLVED: 'RESOLVED',
  SPAM: 'SPAM'
};

var COLUMNS = [
  'Ticket ID',
  'Received at',
  'Name',
  'Email',
  'Phone',
  'Subject',
  'Message',
  'Source',
  'Backend ID',
  'Status',
  'Assignee',
  'Resolved at',
  'Notes'
];

// 1-based column indexes, derived from COLUMNS so the two never drift apart.
var COL = COLUMNS.reduce(function (acc, name, i) {
  acc[name] = i + 1;
  return acc;
}, {});

var LIMITS = {
  SIGNATURE_MAX_AGE_SECONDS: 300, // reject replayed requests older than 5 minutes
  MESSAGE_MAX_LENGTH: 5000,
  UNSIGNED_PER_EMAIL_SECONDS: 60, // one legacy form post per email per minute
  MIN_MAIL_QUOTA_FOR_AUTOREPLY: 20
};

function getConfig() {
  var props = PropertiesService.getScriptProperties().getProperties();
  return {
    sharedSecret: props.SHARED_SECRET || '',
    adminEmails: (props.ADMIN_EMAILS || '')
      .split(',')
      .map(function (s) { return s.trim(); })
      .filter(String),
    shopName: props.SHOP_NAME || 'OldShop',
    shopUrl: props.SHOP_URL || '',
    sheetName: props.SHEET_NAME || 'Contacts',
    allowUnsignedForm: props.ALLOW_UNSIGNED_FORM === 'true'
  };
}
