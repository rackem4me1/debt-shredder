"""Stateless backup review; a signed payload binds saving to reviewed inputs."""
import hashlib
import hmac
from dashboard.forms import shell
from dashboard.report import render, text
from dashboard.strategies import payment_order


def review_signature(payload, secret):
    return hmac.new(secret.encode(), payload.encode('utf-8'), hashlib.sha256).hexdigest()


def restore_form(token, error=''):
    notice = '<p class="error" role="alert">'+text(error)+'</p>' if error else ''
    return shell('Restore a backup', '''<h1>Restore a scenario backup</h1><p>Choose a Debt Shredder scenario backup. You will review its results before saving a new copy. Existing scenarios stay unchanged.</p><p>This restores a what-if scenario, not bank transactions or a record of payments made.</p>'''+notice+
        '<form method="post" action="/restore-preview"><input type="hidden" name="token" value="'+text(token)+'">'+
        '<section><div id="file-choice" hidden><label for="backup-file">Scenario backup file (.json)</label><input id="backup-file" type="file" accept=".json,application/json"><p id="file-status" role="status" aria-live="polite"></p></div>'+
        '<details id="paste-backup" open><summary>Paste backup contents instead</summary><label for="backup-data">Backup contents</label><textarea id="backup-data" name="payload" rows="8" style="width:100%" required spellcheck="false"></textarea></details><p>Maximum file size: 4 MiB. File contents are sent only to this local app when you choose Preview.</p><button type="submit" id="restore-preview">Preview restored scenario</button></section></form><p><a href="/">Back to saved scenarios</a></p><script src="/restore.js" defer></script>')


def restore_preview(scenario, token):
    payload = scenario.model_dump_json()
    signature = review_signature(payload, token)
    fields = {'token':token,'payload':payload,'signature':signature}
    hidden=''.join('<input type="hidden" name="'+text(k)+'" value="'+text(v)+'">' for k,v in fields.items())
    intro='<section><h1>Review restored scenario</h1><p>Nothing has been saved yet. These estimates were recalculated from the backup using this app. Check the dates, amounts and payment request order below.</p><p>Saving creates a separate local scenario, even if you already have this one. No existing file is replaced and no money moves.</p><form method="post" action="/restore-save">'+hidden+'<button type="submit">Save restored copy</button></form><p><a href="/restore">Choose another backup</a> · <a href="/">Cancel and return home</a></p></section>'
    return render(scenario).replace('<h1>','<h2>',1).replace('</h1>','</h2>',1).replace('<main>','<main>'+intro,1).replace('</main>',payment_order(scenario)+'</main>',1)
