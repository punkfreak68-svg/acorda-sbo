async function fetchJSON(path) {
  const res = await fetch(path + "?v=" + Date.now());
  return await res.json();
}

function formatMoney(v) {
  if (v == null || v === "") return "—";
  try { return Number(v).toLocaleString("pt-BR", { style: "currency", currency: "BRL" }); }
  catch { return v; }
}

function badgeSituacao(s) {
  const map = { em_apuracao: "Em apuração", confirmado: "Confirmado", arquivado: "Arquivado" };
  return `<span class="badge">${map[s] || "—"}</span>`;
}

async function renderCasosDestaque() {
  const data = await fetchJSON("data/casos.json");
  const top = data.casos.slice(0, 3);
  const el = document.getElementById("casos-destaque");
  el.innerHTML = top.map(c => `
    <article class="card">
      <h3>${c.titulo}</h3>
      <p>${c.resumo}</p>
      <p><strong>Órgão:</strong> ${c.orgao} · <strong>Valor:</strong> ${formatMoney(c.valor_total)}</p>
      <p>${badgeSituacao(c.situacao)} · Atualizado: ${c.ultima_atualizacao || "—"}</p>
      <p><a class="btn" href="${c.link || '#'}" target="_blank" rel="noopener">Abrir dossiê</a></p>
    </article>
  `).join("");
}

async function renderNovidades() {
  const data = await fetchJSON("data/novidades.json");
  const el = document.getElementById("lista-novidades");
  if (!el) return;
  const itens = (data.itens || []).slice(0, 10);
  const last = data.ultima_atualizacao || "";
  const lbl = document.getElementById("ultima-atualizacao");
  if (lbl) lbl.textContent = last;
  el.innerHTML = itens.map(n => `
    <li>
      <a href="${n.link}" target="_blank" rel="noopener">${n.titulo}</a>
      <div class="muted">${n.fonte} · ${n.data || ""}</div>
      ${n.resumo ? `<div>${n.resumo}</div>` : ""}
    </li>
  `).join("") || "<li>Nada novo por enquanto.</li>";
}

async function renderCasosLista() {
  const data = await fetchJSON("data/casos.json");
  const el = document.getElementById("lista-casos");
  const busca = document.getElementById("busca");
  const filtroSit = document.getElementById("filtro-situacao");
  const filtroAno = document.getElementById("filtro-ano");

  function apply() {
    const q = (busca.value || "").toLowerCase();
    const s = (filtroSit.value || "");
    const a = (filtroAno.value || "");
    const list = data.casos.filter(c => {
      const hit = (c.titulo + " " + c.resumo + " " + c.orgao + " " + (c.fornecedores || []).join(" ")).toLowerCase().includes(q);
      const okS = !s || c.situacao === s;
      const okA = !a || (c.ano + "") === a;
      return hit && okS && okA;
    });
    el.innerHTML = list.map(c => `
      <article class="card">
        <h3>${c.titulo}</h3>
        <p>${c.resumo}</p>
        <p><strong>Órgão:</strong> ${c.orgao} · <strong>Tipo:</strong> ${c.tipo} · <strong>Ano:</strong> ${c.ano}</p>
        <p><strong>Valor total:</strong> ${formatMoney(c.valor_total)} · ${badgeSituacao(c.situacao)}</p>
        <details><summary>Fontes e documentos</summary>
          <ul>${(c.fontes || []).map(f => `<li><a href="${f.link}" target="_blank" rel="noopener">${f.titulo || f.link}</a> (${f.data_acesso || ""})</li>`).join("")}</ul>
        </details>
      </article>
    `).join("") || "<p>Nenhum caso encontrado.</p>";
  }

  [busca, filtroSit, filtroAno].forEach(i => i && i.addEventListener("input", apply));
  apply();
}