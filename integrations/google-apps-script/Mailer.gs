/** Outgoing emails, rendered from the HTML templates (auto-escaped with <?= ?>). */

function notifyAdmins_(config, ticketId, m) {
  if (!config.adminEmails.length) return;
  var html = render_('AdminNotification', {
    ticketId: ticketId,
    m: m,
    sheetUrl: SpreadsheetApp.getActiveSpreadsheet().getUrl(),
    shopName: config.shopName
  });
  MailApp.sendEmail({
    to: config.adminEmails.join(','),
    replyTo: m.email,
    subject: '[' + config.shopName + '] ' + ticketId + ' - ' + m.subject,
    htmlBody: html,
    name: config.shopName + ' Helpdesk'
  });
}

function sendAutoReply_(config, ticketId, m) {
  // Keep some quota for admin notifications when the daily limit is close.
  if (MailApp.getRemainingDailyQuota() < LIMITS.MIN_MAIL_QUOTA_FOR_AUTOREPLY) {
    console.warn('Mail quota low, auto-reply skipped for ' + ticketId);
    return;
  }
  var html = render_('AutoReply', { ticketId: ticketId, m: m, shopName: config.shopName, shopUrl: config.shopUrl });
  MailApp.sendEmail({
    to: m.email,
    subject: config.shopName + ' đã nhận được yêu cầu ' + ticketId,
    htmlBody: html,
    name: config.shopName,
    replyTo: config.adminEmails[0] || ''
  });
}

function sendDailyDigest_(config, tickets) {
  if (!tickets.length || !config.adminEmails.length) return;
  MailApp.sendEmail({
    to: config.adminEmails.join(','),
    subject: '[' + config.shopName + '] ' + tickets.length + ' yêu cầu chưa xử lý quá 24h',
    htmlBody: render_('DailyDigest', {
      tickets: tickets,
      sheetUrl: SpreadsheetApp.getActiveSpreadsheet().getUrl(),
      shopName: config.shopName
    }),
    name: config.shopName + ' Helpdesk'
  });
}

function render_(file, data) {
  var template = HtmlService.createTemplateFromFile(file);
  Object.keys(data).forEach(function (key) {
    template[key] = data[key];
  });
  return template.evaluate().getContent();
}
