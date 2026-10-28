// File selection only; all financial parsing, validation and calculation is server-side.
'use strict';
const picker = document.getElementById('backup-file');
const payload = document.getElementById('backup-data');
const status = document.getElementById('file-status');
const preview = document.getElementById('restore-preview');
const paste = document.getElementById('paste-backup');
let selection = 0;
document.getElementById('file-choice').hidden = false;
paste.open = false;
payload.addEventListener('invalid', () => { paste.open = true; });
picker.addEventListener('change', async () => {
  const current = ++selection;
  const file = picker.files[0];
  payload.value = '';
  status.textContent = '';
  preview.disabled = true;
  if (!file) { preview.disabled = false; return; }
  const maxBytes = Number(picker.dataset.maxBytes || 4 * 1024 * 1024);
  if (file.size > maxBytes) {
    status.textContent = `This file is too large. Choose a backup of ${maxBytes / (1024 * 1024)} MiB or less.`;
    preview.disabled = false;
    return;
  }
  try {
    const contents = await file.text();
    if (current !== selection) return;
    payload.value = contents;
    status.textContent = 'File ready. Choose Preview to check it before saving.';
  } catch {
    if (current !== selection) return;
    status.textContent = 'Could not read this file. Choose it again or paste its contents.';
  } finally {
    if (current === selection) preview.disabled = false;
  }
});
