/**
 * SFACG Editor Helper
 * 
 * Load once per page via chrome-devtools_evaluate_script:
 *   chrome-devtools_evaluate_script(function="<contents of this file>")
 * 
 * Then call:
 *   chrome-devtools_evaluate_script(function="() => sfacg.insert(CONTENT)")
 *   chrome-devtools_evaluate_script(function="() => sfacg.fillTitle(TITLE)")
 *   chrome-devtools_evaluate_script(function="() => sfacg.confirm()")
 *   chrome-devtools_evaluate_script(function="() => sfacg.publish()")
 *   chrome-devtools_evaluate_script(function="() => sfacg.submit(CONTENT, TITLE)")
 */
(() => {
  if (window.sfacg) return window.sfacg;

  function getEditor() {
    const e = window.wangEditor;
    if (!e) throw new Error('wangEditor not found');
    return e;
  }

  function findInput() {
    return document.querySelector('input[placeholder*="章节号"]') ||
           document.querySelector('input[placeholder*="章节名"]');
  }

  function findButton(text) {
    const els = document.querySelectorAll('span, button, div');
    for (const el of els) {
      if (el.textContent.trim() === text && el.offsetParent !== null) return el;
    }
    return null;
  }

  const api = {
    insert(content) {
      const e = getEditor();
      e.focus();
      e.selectAll();
      document.execCommand('delete');
      const ps = content.split('\n').filter(p => p.trim());
      const html = ps.map(p => '<p>' + p + '</p>').join('');
      e.dangerouslyInsertHtml(html);
      return { ok: true, chars: e.getText().length };
    },

    fillTitle(title) {
      const input = findInput();
      if (!input) return { error: 'title input not found' };
      input.focus();
      input.value = '';
      const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype, 'value'
      ).set;
      nativeInputValueSetter.call(input, title);
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
      return { ok: true, value: input.value };
    },

    confirm() {
      const btn = findButton('确认编辑');
      if (!btn) return { error: 'confirm button not found' };
      btn.click();
      return { ok: true };
    },

    publish() {
      const btn = findButton('确定发布');
      if (!btn) return { error: 'publish button not found' };
      btn.click();
      return { ok: true };
    },

    getStatus() {
      const e = getEditor();
      const input = findInput();
      return {
        chars: e.getText().length,
        title: input ? input.value : null,
        empty: e.isEmpty()
      };
    },

    submit(content, title) {
      const r1 = this.insert(content);
      if (r1.error) return r1;
      const r2 = this.fillTitle(title);
      if (r2.error) return r2;
      const r3 = this.confirm();
      if (r3.error) return r3;
      return { ok: true, status: 'confirmed, waiting for publish dialog' };
    }
  };

  window.sfacg = api;
  return { loaded: true };
})()
