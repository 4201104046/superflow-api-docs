// Module có "protected": true trong modules.json: openapi đã mã hóa (AES-256-GCM, nén gzip), mở bằng tài khoản docs.
// File mã hóa sinh bởi tools/docs/encrypt.mjs ở repo của module (vd ca_quan_govap). Chỉ index.html nạp file này,
// và chỉ khi module đang mở là protected → các module khác không bị ảnh hưởng.
(function (root) {
  var subtle = root.crypto && root.crypto.subtle;
  var enc = new TextEncoder();

  function fromB64(s) {
    var bin = atob(s), out = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }
  function toB64(buf) {
    var bytes = new Uint8Array(buf), s = '';
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return btoa(s);
  }
  function hex(buf) {
    return Array.prototype.map.call(new Uint8Array(buf), function (b) { return ('0' + b.toString(16)).slice(-2); }).join('');
  }
  function sessionKey(mod) { return 'docs_unlock_' + mod.id; }

  function fetchLocked(mod) {
    return fetch(mod.url + '?v=' + encodeURIComponent(mod.rev || Date.now()), { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('fetch'); return r.json(); });
  }

  // khóa nội dung (32 byte) → giải mã + giải nén → object OpenAPI
  function openWithKey(locked, rawKey) {
    return subtle.importKey('raw', rawKey, 'AES-GCM', false, ['decrypt'])
      .then(function (key) { return subtle.decrypt({ name: 'AES-GCM', iv: fromB64(locked.iv) }, key, fromB64(locked.data)); })
      .then(function (gz) {
        var stream = new Blob([gz]).stream().pipeThrough(new DecompressionStream('gzip'));
        return new Response(stream).text();
      })
      .then(function (text) { return JSON.parse(text); });
  }

  function remember(mod, rawKey) {
    try { sessionStorage.setItem(sessionKey(mod), JSON.stringify({ rev: mod.rev, key: toB64(rawKey) })); } catch (e) {}
  }

  root.DocsLock = {
    supported: !!(subtle && root.DecompressionStream),

    // Đã đăng nhập trong tab này với đúng bản (rev) hiện tại → mở luôn, không hỏi lại
    restore: function (mod) {
      var saved = null;
      try { saved = JSON.parse(sessionStorage.getItem(sessionKey(mod)) || 'null'); } catch (e) {}
      if (!saved || saved.rev !== mod.rev || !saved.key) return Promise.resolve(null);
      return fetchLocked(mod)
        .then(function (locked) { return openWithKey(locked, fromB64(saved.key)); })
        .catch(function () { root.DocsLock.forget(mod); return null; });
    },

    // Sai tài khoản / mật khẩu → reject Error('credentials')
    unlock: function (mod, user, password) {
      var locked, raw;
      return fetchLocked(mod)
        .then(function (l) { locked = l; return subtle.digest('SHA-256', enc.encode(String(user).trim().toLowerCase())); })
        .then(function (digest) {
          var id = hex(digest);
          var account = (locked.accounts || []).filter(function (a) { return a.id === id; })[0];
          if (!account) throw new Error('credentials');
          return subtle.importKey('raw', enc.encode(password), 'PBKDF2', false, ['deriveKey'])
            .then(function (base) {
              return subtle.deriveKey({ name: 'PBKDF2', hash: locked.kdf.hash, salt: fromB64(account.salt), iterations: locked.kdf.iterations },
                base, { name: 'AES-GCM', length: 256 }, false, ['decrypt']);
            })
            .then(function (kek) { return subtle.decrypt({ name: 'AES-GCM', iv: fromB64(account.iv) }, kek, fromB64(account.key)); })
            .catch(function () { throw new Error('credentials'); });
        })
        .then(function (rawKey) { raw = rawKey; return openWithKey(locked, rawKey); })
        .then(function (spec) { remember(mod, raw); return spec; });
    },

    forget: function (mod) {
      try { sessionStorage.removeItem(sessionKey(mod)); } catch (e) {}
    }
  };
})(typeof window !== 'undefined' ? window : globalThis);
