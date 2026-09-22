// exodus-view embed elements for hand-written reports.
//
//   <script src="http://127.0.0.1:8765/embed.js"></script>
//   <meta name="exo-root" content="/abs/path">            optional: relative file= paths resolve here
//
//   <exo-view file="out.e" var="disp_y" warp wscale="10" step="last" view="iso"
//             controls="time" height="360" png="fig1.png">caption html</exo-view>
//   <exo-input file="input.i" [open]></exo-input>            collapsible listing of a text file
//   <exo-globals file="out.e" [step="last|all|N"]></exo-globals>  postprocessor table
//
// Every <exo-view> attribute except height/png/controls is a viewer URL parameter
// (see viewer.html). The figure shows the live viewer when the server answers and
// the png fallback otherwise, so a report keeps working after the server is gone.
(() => {
  const script = document.currentScript;
  const SERVER = (script && script.dataset.server) || (script && script.src ? new URL(script.src).origin : 'http://127.0.0.1:8765');
  const rootMeta = document.querySelector('meta[name="exo-root"]');
  const ROOT = rootMeta ? rootMeta.content.replace(/\/$/, '')
    : (location.protocol === 'file:' ? decodeURIComponent(location.pathname).replace(/\/[^/]*$/, '') : '');
  const resolve = p => (!p || p.startsWith('/') || p.startsWith('~') || !ROOT) ? p : ROOT + '/' + p;
  const ATTRS = ['file', 'var', 'step', 'warp', 'wscale', 'wprefix', 'blocks', 'ss', 'ns', 'cut', 'cmap', 'range',
                 'edges', 'opacity', 'up', 'bg', 'view', 'cam', 'controls', 'probe', 'lock2d'];
  let alive = null;
  const serverUp = () => alive || (alive = fetch(SERVER + '/api/files', { signal: AbortSignal.timeout(1500) })
    .then(r => r.ok).catch(() => false));
  const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  const fmt = x => (x === null || x === undefined || Number.isNaN(x)) ? 'nan'
    : x === 0 ? '0' : (Math.abs(x) >= 1e5 || Math.abs(x) < 1e-3) ? x.toExponential(3) : String(+x.toPrecision(5));

  document.head.appendChild(Object.assign(document.createElement('style'), { textContent: `
    exo-view { display: block; margin: 1.2em 0; }
    exo-view figure { margin: 0; }
    exo-view .exo-box { position: relative; width: 100%; border: 1px solid #d0d4da; border-radius: 4px; overflow: hidden; background: #fff; }
    exo-view .exo-box iframe { width: 100%; height: 100%; border: 0; display: block; }
    exo-view .exo-box img { width: 100%; height: 100%; object-fit: contain; display: block; }
    exo-view .exo-box.static::after { content: "static"; position: absolute; right: 6px; top: 4px; font: 10px sans-serif; color: #888; }
    exo-view .exo-off { display: flex; align-items: center; justify-content: center; height: 100%; text-align: center; color: #666; font: 13px sans-serif; }
    exo-view .exo-off code { display: block; margin-top: 6px; font-size: 11px; color: #333; }
    exo-view figcaption { font-size: 0.9em; color: #444; margin-top: 0.4em; }
    exo-view .exo-full { float: right; font-size: 0.85em; color: #557; text-decoration: none; margin-left: 1em; }
    exo-view .exo-full:hover { text-decoration: underline; }
    exo-input details { margin: 1em 0; }
    exo-input summary { cursor: pointer; font-family: ui-monospace, Menlo, monospace; font-size: 0.9em; color: #335; }
    exo-input pre { font-size: 11.5px; line-height: 1.35; background: #f6f7f9; border: 1px solid #e0e3e8; border-radius: 4px; padding: 8px 10px; overflow: auto; max-height: 480px; }
    exo-globals table { border-collapse: collapse; font-size: 0.9em; margin: 0.8em 0; }
    exo-globals td, exo-globals th { border-bottom: 1px solid #e0e3e8; padding: 2px 10px 2px 0; text-align: right; font-family: ui-monospace, Menlo, monospace; }
    exo-globals td:first-child, exo-globals th:first-child { text-align: left; font-family: inherit; }
    exo-globals th { color: #555; font-weight: 600; }
    .exo-err { color: #a33; font: 12px sans-serif; }
  ` }));

  class ExoView extends HTMLElement {
    async connectedCallback() {
      if (this.dataset.done) return;
      this.dataset.done = '1';
      const caption = this.innerHTML.trim();
      this.innerHTML = '';
      const q = new URLSearchParams();
      for (const a of ATTRS) {
        if (!this.hasAttribute(a)) continue;
        let v = this.getAttribute(a);
        if (a === 'file') v = resolve(v);
        if ((a === 'warp' || a === 'probe') && v === '') v = '1';   // bare boolean attribute
        if (v !== '') q.set(a, v);
      }
      const full = new URLSearchParams(q); full.delete('controls');
      const fullUrl = SERVER + '/?' + full.toString();
      q.set('embed', '1');
      const src = SERVER + '/?' + q.toString();
      const fig = document.createElement('figure');
      const box = document.createElement('div');
      box.className = 'exo-box';
      box.style.height = (this.getAttribute('height') || '360') + 'px';
      const cap = document.createElement('figcaption');
      cap.innerHTML = `<a class="exo-full" href="${fullUrl}" target="_blank">full viewer</a>` + caption;
      fig.append(box, cap);
      this.appendChild(fig);
      const png = this.getAttribute('png');
      if (await serverUp()) {
        const f = document.createElement('iframe');
        f.src = src; f.title = this.getAttribute('file') || 'exodus view';
        box.appendChild(f);
      } else if (png) {
        const img = document.createElement('img');
        img.src = png; img.alt = caption.replace(/<[^>]*>/g, '');
        box.appendChild(img);
        box.classList.add('static');
        box.title = 'viewer server not running; showing the rendered image';
      } else {
        box.innerHTML = `<div class="exo-off">viewer server not running<code>scripts/conda-run.sh -C moose -- python scripts/exodus-view.py</code></div>`;
      }
    }
  }

  class ExoInput extends HTMLElement {
    async connectedCallback() {
      if (this.dataset.done) return;
      this.dataset.done = '1';
      const file = resolve(this.getAttribute('file'));
      const name = (file || '').split('/').pop();
      const det = document.createElement('details');
      if (this.hasAttribute('open')) det.open = true;
      det.innerHTML = `<summary>${esc(this.getAttribute('title') || name)}</summary><pre>loading…</pre>`;
      this.appendChild(det);
      try {
        if (!(await serverUp())) throw new Error('viewer server not running');
        const r = await fetch(SERVER + '/api/text?path=' + encodeURIComponent(file));
        if (!r.ok) throw new Error((await r.json()).error);
        det.querySelector('pre').textContent = await r.text();
      } catch (e) {
        det.querySelector('pre').innerHTML = `<span class="exo-err">${esc(e.message)}</span>`;
      }
    }
  }

  class ExoGlobals extends HTMLElement {
    async connectedCallback() {
      if (this.dataset.done) return;
      this.dataset.done = '1';
      const file = resolve(this.getAttribute('file'));
      const which = this.getAttribute('step') || 'last';
      try {
        if (!(await serverUp())) throw new Error('viewer server not running');
        const r = await fetch(SERVER + '/api/globals?file=' + encodeURIComponent(file));
        if (!r.ok) throw new Error((await r.json()).error);
        const g = await r.json();
        if (!g.names.length) { this.innerHTML = '<p class="exo-err">no global variables in this file</p>'; return; }
        const n = g.values.length;
        const steps = which === 'all' ? [...Array(n).keys()] : [which === 'last' ? n - 1 : Math.min(n - 1, +which)];
        let h = '<table><tr><th>postprocessor</th>' + steps.map(s => `<th>t = ${fmt(g.times[s])}</th>`).join('') + '</tr>';
        g.names.forEach((nm, i) => { h += `<tr><td>${esc(nm)}</td>` + steps.map(s => `<td>${fmt(g.values[s][i])}</td>`).join('') + '</tr>'; });
        this.innerHTML = h + '</table>';
      } catch (e) {
        this.innerHTML = `<p class="exo-err">${esc(e.message)}</p>`;
      }
    }
  }

  customElements.define('exo-view', ExoView);
  customElements.define('exo-input', ExoInput);
  customElements.define('exo-globals', ExoGlobals);
})();
