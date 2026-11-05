(function () {
  var mods = window.API_DOC_MODULES || [];
  var root = document.documentElement.getAttribute('data-root') || '';
  var current = document.documentElement.getAttribute('data-module') || '';

  var sel = document.getElementById('module-select');
  if (sel) {
    var home = document.createElement('option');
    home.value = ''; home.textContent = 'Tất cả module';
    sel.appendChild(home);
    mods.forEach(function (m) {
      var o = document.createElement('option');
      o.value = m.id; o.textContent = m.name;
      if (m.id === current) o.selected = true;
      sel.appendChild(o);
    });
    sel.addEventListener('change', function () {
      window.location.href = root + (sel.value ? sel.value + '/' : '');
    });
  }

  var list = document.getElementById('module-list');
  if (list) {
    mods.forEach(function (m) {
      var a = document.createElement('a');
      a.className = 'mod'; a.href = m.id + '/';
      a.innerHTML = '<h3><span></span><span class="upd"></span></h3><p></p><div class="meta"><code></code><code></code></div>';
      a.querySelector('h3 span').textContent = m.name;
      a.querySelector('.upd').textContent = m.updated ? 'Cập nhật ' + m.updated : '';
      a.querySelector('p').textContent = m.description || '';
      var codes = a.querySelectorAll('code');
      codes[0].textContent = m.base || '';
      codes[1].textContent = (m.endpoints || 0) + ' endpoint';
      list.appendChild(a);
    });
  }

  document.querySelectorAll('.code pre').forEach(function (pre) {
    if (pre.hasAttribute('data-raw')) return;
    pre.innerHTML = pre.innerHTML
      .replace(/("[^"\n]*")(\s*:)/g, '<span class="k">$1</span>$2')
      .replace(/(:\s*)("[^"\n]*")/g, '$1<span class="s">$2</span>')
      .replace(/(\[|,\s*)("[^"\n]*")(?=\s*[\],])/g, '$1<span class="s">$2</span>');
  });

  document.querySelectorAll('.code').forEach(function (box) {
    var pre = box.querySelector('pre');
    var btn = document.createElement('button');
    btn.className = 'copy'; btn.type = 'button'; btn.textContent = 'Copy';
    btn.addEventListener('click', function () {
      var done = function () { btn.textContent = 'Đã copy'; setTimeout(function () { btn.textContent = 'Copy'; }, 1500); };
      var fallback = function () {
        var r = document.createRange(); r.selectNodeContents(pre);
        var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
        btn.textContent = 'Đã chọn, nhấn Ctrl+C';
      };
      try { navigator.clipboard.writeText(pre.textContent).then(done, fallback); } catch (e) { fallback(); }
    });
    box.appendChild(btn);
  });
})();
