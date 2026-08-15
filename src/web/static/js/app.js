/**
 * Hermes Control Hub — Frontend Logic
 */

// State
let allContacts = [];
let allDictionaryTerms = [];

// DOM Elements
const contactsContainer = document.getElementById('contacts-container');
const dictionaryContainer = document.getElementById('dictionary-container');
const countContactsEl = document.getElementById('count-contacts');
const countDictEl = document.getElementById('count-dict');
const statGraphNodesEl = document.getElementById('stat-graph-nodes');

const contactSearchInput = document.getElementById('contact-search');
const contactFilterRole = document.getElementById('contact-filter-role');
const dictSearchInput = document.getElementById('dict-search');
const dictFilterCategory = document.getElementById('dict-filter-category');

// Modals
const modalContact = document.getElementById('modal-contact');
const formContact = document.getElementById('form-contact');
const modalTerm = document.getElementById('modal-term');
const formTerm = document.getElementById('form-term');

// Toast
function showToast(message, isError = false) {
  const toast = document.getElementById('toast');
  const toastMsg = document.getElementById('toast-message');
  toastMsg.textContent = message;
  toast.style.borderLeftColor = isError ? 'var(--color-danger)' : 'var(--color-primary)';
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 3500);
}

// Tabs
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    
    btn.classList.add('active');
    const targetId = btn.dataset.tab;
    const targetContent = document.getElementById(targetId);
    if (targetContent) targetContent.classList.add('active');
  });
});

// Init
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadContacts();
  loadDictionary();

  // Search & Filter Listeners
  contactSearchInput.addEventListener('input', renderContacts);
  contactFilterRole.addEventListener('change', renderContacts);
  dictSearchInput.addEventListener('input', renderDictionary);
  dictFilterCategory.addEventListener('change', renderDictionary);

  // Global Refresh
  document.getElementById('btn-refresh-all').addEventListener('click', () => {
    loadStats();
    loadContacts();
    loadDictionary();
    showToast('Dados recarregados da VPS!');
  });

  // Contact Modal Triggers
  document.getElementById('btn-open-new-contact').addEventListener('click', () => {
    document.getElementById('modal-contact-title').textContent = 'Novo Contato';
    formContact.reset();
    document.getElementById('contact-id').value = '';
    modalContact.classList.add('active');
  });
  document.getElementById('btn-close-contact-modal').addEventListener('click', () => modalContact.classList.remove('active'));
  document.getElementById('btn-cancel-contact').addEventListener('click', () => modalContact.classList.remove('active'));

  // Term Modal Triggers
  document.getElementById('btn-open-new-term').addEventListener('click', () => {
    formTerm.reset();
    modalTerm.classList.add('active');
  });
  document.getElementById('btn-close-term-modal').addEventListener('click', () => modalTerm.classList.remove('active'));
  document.getElementById('btn-cancel-term').addEventListener('click', () => modalTerm.classList.remove('active'));

  // Form Submissions
  formContact.addEventListener('submit', handleSaveContact);
  formTerm.addEventListener('submit', handleSaveTerm);

  // Query Testing
  document.getElementById('btn-run-query').addEventListener('click', runHermesQuery);
  document.getElementById('query-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') runHermesQuery();
  });
});

// --- API Calls & Loading ---

async function loadStats() {
  try {
    const res = await fetch('/api/v1/memory/stats');
    if (res.ok) {
      const data = await res.json();
      statGraphNodesEl.textContent = `${data.graph_nodes || 32} nós no Grafo`;
    }
  } catch (err) {
    console.error('Erro ao carregar métricas:', err);
  }
}

async function loadContacts() {
  try {
    const res = await fetch('/api/v1/contacts');
    if (res.ok) {
      allContacts = await res.json();
    }
    
    // Se a tabela SQL ainda não tiver os nós do grafo, busca do grafo
    if (allContacts.length === 0) {
      const graphRes = await fetch('/api/v1/memory/graph/nodes?category=PERSON');
      if (graphRes.ok) {
        const graphNodes = await graphRes.json();
        allContacts = graphNodes.map(n => ({
          id: n.name,
          name: n.name,
          phone_number: n.phone || '',
          role: n.role || 'UNKNOWN',
          company: n.company || '',
          projects: n.projects || (n.details ? [n.details] : []),
          custom_weight: n.weight || 0.5,
          notes: n.details || ''
        }));
      }
    }

    countContactsEl.textContent = allContacts.length;
    renderContacts();
  } catch (err) {
    console.error('Erro ao carregar contatos:', err);
  }
}

async function loadDictionary() {
  try {
    const res = await fetch('/api/v1/dictionary');
    if (res.ok) {
      allDictionaryTerms = await res.json();
      countDictEl.textContent = allDictionaryTerms.length;
      renderDictionary();
    }
  } catch (err) {
    console.error('Erro ao carregar dicionário:', err);
  }
}

// --- Renderers ---

function getRoleBadgeClass(role) {
  const r = (role || '').toUpperCase();
  if (r === 'FAMILY_CORE') return 'badge-family';
  if (r === 'EXECUTIVE') return 'badge-executive';
  if (r === 'COLLEAGUE') return 'badge-colleague';
  if (r === 'STAKEHOLDER') return 'badge-stakeholder';
  if (r === 'SERVICE_VENDOR') return 'badge-vendor';
  return 'badge-vendor';
}

function getRoleLabel(role) {
  const r = (role || '').toUpperCase();
  const map = {
    'FAMILY_CORE': 'Família',
    'EXECUTIVE': 'Diretoria / Gestão',
    'COLLEAGUE': 'Colega / Parceiro',
    'STAKEHOLDER': 'Consultoria / Stakeholder',
    'SERVICE_VENDOR': 'Fornecedor',
    'UNKNOWN': 'Não Classificado'
  };
  return map[r] || r;
}

function getInitials(name) {
  if (!name) return '??';
  const parts = name.trim().split(' ');
  if (parts.length >= 2) return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
  return name.substring(0, 2).toUpperCase();
}

function renderContacts() {
  const searchTerm = contactSearchInput.value.toLowerCase().trim();
  const filterRole = contactFilterRole.value.toUpperCase();

  const filtered = allContacts.filter(c => {
    const matchSearch = (
      c.name.toLowerCase().includes(searchTerm) ||
      (c.company && c.company.toLowerCase().includes(searchTerm)) ||
      (c.phone_number && c.phone_number.toLowerCase().includes(searchTerm)) ||
      (c.role && c.role.toLowerCase().includes(searchTerm))
    );
    const matchRole = !filterRole || (c.role && c.role.toUpperCase() === filterRole);
    return matchSearch && matchRole;
  });

  if (filtered.length === 0) {
    contactsContainer.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: var(--text-muted);">
        <p style="font-size: 1.2rem; margin-bottom: 0.5rem;">Nenhum contato encontrado</p>
        <small>Adicione novos contatos para expandir o Grafo Social do Hermes.</small>
      </div>
    `;
    return;
  }

  contactsContainer.innerHTML = filtered.map(c => {
    const rawDigits = (c.phone_number || '').replace(/\D/g, '');
    const cleanPhone = rawDigits.length in [10, 11] && !rawDigits.startsWith('55') ? `55${rawDigits}` : rawDigits;
    const whatsappLink = cleanPhone ? `https://wa.me/${cleanPhone}` : '#';
    const initials = getInitials(c.name);
    const badgeClass = getRoleBadgeClass(c.role);
    const roleLabel = getRoleLabel(c.role);
    const projectsHtml = (c.projects || []).map(p => `<span class="project-chip">${p}</span>`).join('');

    return `
      <div class="contact-card" id="contact-card-${c.id || rawDigits}">
        <div class="contact-header">
          <div class="contact-avatar" id="avatar-${rawDigits}">
            ${c.avatar_url ? `<img src="${c.avatar_url}" alt="${c.name}">` : initials}
          </div>
          <div class="contact-title-group">
            <div class="contact-name">${c.name}</div>
            <div class="contact-company">${c.company || 'Pessoal / Geral'}</div>
            <span class="badge ${badgeClass}">${roleLabel}</span>
          </div>
        </div>

        <div class="contact-details">
          ${c.phone_number ? `
            <div>
              <a href="${whatsappLink}" target="_blank" class="contact-phone-link">
                📱 ${c.phone_number}
              </a>
            </div>
          ` : '<span class="text-muted">Sem telefone cadastrado</span>'}

          ${c.notes ? `<div style="font-size: 0.8rem; color: var(--text-muted);">${c.notes}</div>` : ''}

          ${projectsHtml ? `<div class="contact-projects">${projectsHtml}</div>` : ''}
        </div>

        <div class="contact-actions">
          ${cleanPhone ? `
            <button class="btn btn-secondary btn-sm" onclick="fetchWhatsAppAvatar('${cleanPhone}')" title="Buscar foto oficial do perfil no WhatsApp">
              📸 Puxar Foto
            </button>
          ` : '<span></span>'}

          <div style="display: flex; gap: 0.4rem;">
            <button class="btn btn-secondary btn-sm" onclick="editContact('${c.id || c.name}')">✏️ Editar</button>
            <button class="btn btn-danger btn-sm" onclick="deleteContact('${c.id || c.name}')">🗑️</button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function renderDictionary() {
  const searchTerm = dictSearchInput.value.toLowerCase().trim();
  const filterCat = dictFilterCategory.value.toUpperCase();

  const filtered = allDictionaryTerms.filter(t => {
    const matchSearch = (
      t.term.toLowerCase().includes(searchTerm) ||
      (t.expansion && t.expansion.toLowerCase().includes(searchTerm)) ||
      (t.phonetic_variations && t.phonetic_variations.some(v => v.toLowerCase().includes(searchTerm)))
    );
    const matchCat = !filterCat || (t.category && t.category.toUpperCase() === filterCat);
    return matchSearch && matchCat;
  });

  if (filtered.length === 0) {
    dictionaryContainer.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: var(--text-muted);">
        <p style="font-size: 1.2rem; margin-bottom: 0.5rem;">Nenhum termo encontrado</p>
      </div>
    `;
    return;
  }

  dictionaryContainer.innerHTML = filtered.map(t => {
    const variationsHtml = (t.phonetic_variations || []).map(v => `<span class="variation-chip">${v}</span>`).join('');

    return `
      <div class="dict-card">
        <div class="dict-header">
          <span class="dict-term">${t.term}</span>
          <span class="badge badge-executive">${t.category}</span>
        </div>

        ${t.expansion ? `<div class="dict-expansion">${t.expansion}</div>` : ''}

        <div class="dict-variations">
          ${variationsHtml}
        </div>

        ${t.description ? `<div class="dict-desc">${t.description}</div>` : ''}

        <div style="display: flex; justify-content: flex-end; margin-top: auto; padding-top: 0.5rem; border-top: 1px solid var(--border-subtle);">
          <button class="btn btn-danger btn-sm" onclick="deleteTerm('${t.id || t.term}')">Remover</button>
        </div>
      </div>
    `;
  }).join('');
}

// --- WhatsApp Avatar Fetcher ---

async function fetchWhatsAppAvatar(phone) {
  const avatarEl = document.getElementById(`avatar-${phone}`);
  if (avatarEl) {
    avatarEl.innerHTML = '<span style="font-size: 0.8rem;">⏳</span>';
  }

  try {
    const res = await fetch(`/api/v1/contacts/avatar/${phone}`);
    if (res.ok) {
      const data = await res.json();
      if (data.profile_picture_url) {
        if (avatarEl) {
          avatarEl.innerHTML = `<img src="${data.profile_picture_url}" alt="Foto WhatsApp">`;
        }
        showToast('Foto do perfil carregada via WhatsApp!');
        return;
      }
    }
    showToast('Foto não encontrada no WhatsApp deste número.', true);
    if (avatarEl) avatarEl.textContent = '👤';
  } catch (err) {
    console.error('Erro ao buscar foto:', err);
    showToast('Erro ao comunicar com a Evolution API', true);
  }
}

// --- Contact Form Actions ---

async function handleSaveContact(e) {
  e.preventDefault();
  const contactId = document.getElementById('contact-id').value;
  const name = document.getElementById('contact-name').value.trim();
  const nickname = document.getElementById('contact-nickname').value.trim();
  const phone_number = document.getElementById('contact-phone').value.trim();
  const role = document.getElementById('contact-role').value;
  const company = document.getElementById('contact-company').value.trim();
  const projectsRaw = document.getElementById('contact-projects').value.trim();
  const notes = document.getElementById('contact-notes').value.trim();

  const projects = projectsRaw ? projectsRaw.split(',').map(p => p.trim()).filter(Boolean) : [];

  const payload = {
    name,
    nickname: nickname || null,
    phone_number,
    role,
    company: company || null,
    projects,
    notes: notes || null
  };

  try {
    const res = await fetch('/api/v1/contacts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      showToast(`Contato ${name} salvo e sincronizado na VPS!`);
      modalContact.classList.remove('active');
      loadContacts();
      loadStats();
    } else {
      showToast('Erro ao salvar contato na VPS', true);
    }
  } catch (err) {
    console.error('Erro:', err);
    showToast('Erro de conexão ao salvar', true);
  }
}

function editContact(idOrName) {
  const contact = allContacts.find(c => c.id === idOrName || c.name === idOrName);
  if (!contact) return;

  document.getElementById('modal-contact-title').textContent = 'Editar Contato';
  document.getElementById('contact-id').value = contact.id || '';
  document.getElementById('contact-name').value = contact.name || '';
  document.getElementById('contact-nickname').value = contact.nickname || '';
  document.getElementById('contact-phone').value = contact.phone_number || '';
  document.getElementById('contact-role').value = contact.role || 'UNKNOWN';
  document.getElementById('contact-company').value = contact.company || '';
  document.getElementById('contact-projects').value = (contact.projects || []).join(', ');
  document.getElementById('contact-notes').value = contact.notes || '';

  modalContact.classList.add('active');
}

async function deleteContact(idOrName) {
  if (!confirm(`Deseja realmente excluir o contato ${idOrName}?`)) return;

  try {
    const contact = allContacts.find(c => c.id === idOrName || c.name === idOrName);
    const targetId = contact && contact.id ? contact.id : idOrName;

    const res = await fetch(`/api/v1/contacts/${targetId}`, { method: 'DELETE' });
    if (res.ok || res.status === 204) {
      showToast(`Contato removido da VPS!`);
      loadContacts();
      loadStats();
    } else {
      showToast('Erro ao excluir contato', true);
    }
  } catch (err) {
    console.error('Erro:', err);
    showToast('Erro ao excluir contato', true);
  }
}

// --- Term Form Actions ---

async function handleSaveTerm(e) {
  e.preventDefault();
  const term = document.getElementById('term-name').value.trim();
  const category = document.getElementById('term-category').value;
  const expansion = document.getElementById('term-expansion').value.trim();
  const variationsRaw = document.getElementById('term-variations').value.trim();
  const description = document.getElementById('term-description').value.trim();

  const phonetic_variations = variationsRaw.split(',').map(v => v.trim()).filter(Boolean);

  const payload = {
    term,
    category,
    expansion: expansion || null,
    phonetic_variations,
    description: description || null
  };

  try {
    const res = await fetch('/api/v1/dictionary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      showToast(`Termo ${term} salvo na VPS!`);
      modalTerm.classList.remove('active');
      loadDictionary();
    } else {
      showToast('Erro ao salvar termo', true);
    }
  } catch (err) {
    console.error('Erro:', err);
    showToast('Erro ao salvar termo', true);
  }
}

async function deleteTerm(idOrTerm) {
  if (!confirm(`Deseja remover o termo ${idOrTerm}?`)) return;

  try {
    const tObj = allDictionaryTerms.find(t => t.id === idOrTerm || t.term === idOrTerm);
    const targetId = tObj && tObj.id ? tObj.id : idOrTerm;

    const res = await fetch(`/api/v1/dictionary/${targetId}`, { method: 'DELETE' });
    if (res.ok || res.status === 204) {
      showToast(`Termo removido da VPS!`);
      loadDictionary();
    } else {
      showToast('Erro ao remover termo', true);
    }
  } catch (err) {
    console.error('Erro:', err);
  }
}

// --- Live Hermes Query Testing ---

function setQuery(text) {
  document.getElementById('query-input').value = text;
  runHermesQuery();
}

async function runHermesQuery() {
  const queryInput = document.getElementById('query-input');
  const query = queryInput.value.trim();
  if (!query) return;

  const resultBox = document.getElementById('query-result-box');
  const answerEl = document.getElementById('query-answer');
  const metaEl = document.getElementById('query-meta');
  const timeEl = document.getElementById('query-time');

  resultBox.style.display = 'block';
  answerEl.textContent = 'Processando com Gemini 3.1 Flash Lite + RAG Híbrido...';
  timeEl.textContent = 'Consultando...';
  metaEl.innerHTML = '';

  const startTime = performance.now();

  try {
    const res = await fetch('/api/v1/memory/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: 5, include_graph: true })
    });

    const elapsed = Math.round(performance.now() - startTime);
    timeEl.textContent = `${elapsed}ms`;

    if (res.ok) {
      const data = await res.json();
      answerEl.textContent = data.answer || 'Sem resposta gerada.';

      const mentions = (data.entities_mentioned || []).join(', ');
      metaEl.innerHTML = `
        <div><strong>Entidades do Grafo Mencionadas:</strong> ${mentions || 'Nenhuma'}</div>
        <div><strong>Fontes Citadas:</strong> ${data.sources ? data.sources.length : 0} memórias de áudio</div>
      `;
    } else {
      answerEl.textContent = 'Erro ao consultar a API do Hermes.';
    }
  } catch (err) {
    answerEl.textContent = `Erro de conexão: ${err.message}`;
  }
}
