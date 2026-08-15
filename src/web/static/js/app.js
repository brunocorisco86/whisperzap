/**
 * Hermes Control Hub — Frontend Logic
 */

// State
let allContacts = [];
let allDictionaryTerms = [];
let allTasks = [];
let allMessages = [];
let visNetworkInstance = null;
let graphRawData = null;

// DOM Elements
const contactsContainer = document.getElementById('contacts-container');
const dictionaryContainer = document.getElementById('dictionary-container');
const tasksContainer = document.getElementById('tasks-container');
const messagesContainer = document.getElementById('messages-container');

const countContactsEl = document.getElementById('count-contacts');
const countDictEl = document.getElementById('count-dict');
const countTasksEl = document.getElementById('count-tasks');
const statGraphNodesEl = document.getElementById('stat-graph-nodes');

const contactSearchInput = document.getElementById('contact-search');
const contactFilterRole = document.getElementById('contact-filter-role');
const dictSearchInput = document.getElementById('dict-search');
const dictFilterCategory = document.getElementById('dict-filter-category');
const tasksSearchInput = document.getElementById('tasks-search');
const tasksFilterStatus = document.getElementById('tasks-filter-status');
const tasksFilterPriority = document.getElementById('tasks-filter-priority');

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

    if (targetId === 'tab-graph') {
      setTimeout(renderInteractiveGraph, 100);
    } else if (targetId === 'tab-tasks') {
      loadTasks();
    } else if (targetId === 'tab-messages') {
      loadMessages();
    } else if (targetId === 'tab-sentiment') {
      loadDailySentiments();
      populateSentimentSpeakers();
    }
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
  
  if (tasksSearchInput) tasksSearchInput.addEventListener('input', renderTasks);
  if (tasksFilterStatus) tasksFilterStatus.addEventListener('change', renderTasks);
  if (tasksFilterPriority) tasksFilterPriority.addEventListener('change', renderTasks);

  // Global Refresh
  document.getElementById('btn-refresh-all').addEventListener('click', () => {
    loadStats();
    loadContacts();
    loadDictionary();
    loadTasks();
    loadMessages();
    loadGraphData();
    showToast('Dados recarregados da VPS!');
  });

  const btnRefreshMessages = document.getElementById('btn-refresh-messages');
  if (btnRefreshMessages) {
    btnRefreshMessages.addEventListener('click', () => {
      loadMessages();
      showToast('Feed de mensagens e áudios atualizado!');
    });
  }

  // Graph Controls
  const btnResetGraph = document.getElementById('btn-reset-graph');
  if (btnResetGraph) {
    btnResetGraph.addEventListener('click', () => {
      if (visNetworkInstance) visNetworkInstance.fit({ animation: { duration: 600 } });
    });
  }

  const btnReloadGraph = document.getElementById('btn-reload-graph');
  if (btnReloadGraph) {
    btnReloadGraph.addEventListener('click', () => {
      loadGraphData();
      showToast('Grafo NetworkX recarregado!');
    });
  }

  const btnCloseNodeDetail = document.getElementById('btn-close-node-detail');
  if (btnCloseNodeDetail) {
    btnCloseNodeDetail.addEventListener('click', () => {
      document.getElementById('node-detail-panel').style.display = 'none';
    });
  }

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

  // Sentiment Tab Listeners
  const sentimentDatePicker = document.getElementById('sentiment-date-picker');
  if (sentimentDatePicker) {
    const todayStr = new Date().toISOString().split('T')[0];
    sentimentDatePicker.value = todayStr;
    sentimentDatePicker.addEventListener('change', (e) => {
      loadDailySentiments(e.target.value);
    });
  }

  const btnCollectSentiment = document.getElementById('btn-collect-today-sentiment');
  if (btnCollectSentiment) {
    btnCollectSentiment.addEventListener('click', async () => {
      const selectedDate = sentimentDatePicker ? sentimentDatePicker.value : '';
      await collectSentiments(selectedDate);
    });
  }

  const speakerSelect = document.getElementById('sentiment-speaker-select');
  if (speakerSelect) {
    speakerSelect.addEventListener('change', (e) => {
      const speaker = e.target.value;
      if (speaker) {
        loadSentimentTimeline(speaker);
      } else {
        const panel = document.getElementById('sentiment-timeline-panel');
        if (panel) panel.style.display = 'none';
      }
    });
  }

  // Carrega dados do grafo
  loadGraphData();
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
    
    // Fallback se SQL vazio
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

async function loadTasks() {
  try {
    const res = await fetch('/api/v1/memory/tasks');
    if (res.ok) {
      allTasks = await res.json();
      if (countTasksEl) countTasksEl.textContent = allTasks.filter(t => t.status === 'PENDING').length;
      renderTasks();
    }
  } catch (err) {
    console.error('Erro ao carregar tarefas:', err);
  }
}

async function loadMessages() {
  try {
    const res = await fetch('/api/v1/memory/messages');
    if (res.ok) {
      allMessages = await res.json();
      renderMessages();
    }
  } catch (err) {
    console.error('Erro ao carregar mensagens:', err);
  }
}

async function loadGraphData() {
  try {
    const res = await fetch('/api/v1/memory/graph/full');
    if (res.ok) {
      graphRawData = await res.json();
      if (document.getElementById('tab-graph').classList.contains('active')) {
        renderInteractiveGraph();
      }
    }
  } catch (err) {
    console.error('Erro ao carregar grafo completo:', err);
  }
}

// --- Interactive Graph NetworkX Engine ---

function renderInteractiveGraph() {
  const container = document.getElementById('graph-canvas');
  if (!container || !graphRawData || typeof vis === 'undefined') return;

  const data = {
    nodes: new vis.DataSet(graphRawData.nodes),
    edges: new vis.DataSet(graphRawData.edges)
  };

  const options = {
    nodes: {
      shape: 'dot',
      font: {
        face: 'Inter',
        color: '#f8fafc',
        size: 13,
        strokeWidth: 3,
        strokeColor: '#090d16'
      },
      borderWidth: 2,
      shadow: { enabled: true, color: 'rgba(0,0,0,0.5)', size: 8 }
    },
    edges: {
      smooth: { type: 'continuous', roundness: 0.2 },
      arrows: { to: { enabled: true, scaleFactor: 0.6 } }
    },
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: -35,
        centralGravity: 0.008,
        springLength: 95,
        springConstant: 0.18,
        damping: 0.75
      },
      stabilization: { iterations: 120 }
    },
    interaction: {
      hover: true,
      tooltipDelay: 100,
      zoomView: true,
      dragView: true
    }
  };

  if (visNetworkInstance) {
    visNetworkInstance.destroy();
  }

  visNetworkInstance = new vis.Network(container, data, options);

  visNetworkInstance.on('click', (params) => {
    if (params.nodes.length > 0) {
      const nodeId = params.nodes[0];
      showNodeDetails(nodeId);
    } else {
      document.getElementById('node-detail-panel').style.display = 'none';
    }
  });
}

function showNodeDetails(nodeId) {
  const node = graphRawData.nodes.find(n => n.id === nodeId);
  if (!node) return;

  const panel = document.getElementById('node-detail-panel');
  const title = document.getElementById('node-detail-title');
  const body = document.getElementById('node-detail-body');

  title.textContent = node.label;
  
  const attrs = node.attributes || {};
  const connectedEdges = graphRawData.edges.filter(e => e.from === nodeId || e.to === nodeId);

  let connectionsHtml = connectedEdges.map(e => {
    const isOut = e.from === nodeId;
    const target = isOut ? e.to : e.from;
    const arrow = isOut ? '➔' : '⬅';
    return `<div style="font-size: 0.78rem; padding: 0.2rem 0;">${arrow} <b>${e.label}</b> ${target}</div>`;
  }).join('');

  body.innerHTML = `
    <div><strong>Categoria:</strong> <span class="badge badge-executive">${node.category}</span></div>
    ${attrs.role ? `<div><strong>Papel / Role:</strong> ${attrs.role}</div>` : ''}
    ${attrs.phone ? `<div><strong>Telefone:</strong> <a href="https://wa.me/${attrs.phone.replace(/\D/g, '')}" target="_blank" class="contact-phone-link">📱 ${attrs.phone}</a></div>` : ''}
    ${attrs.company ? `<div><strong>Empresa:</strong> ${attrs.company}</div>` : ''}
    ${attrs.details ? `<div><strong>Detalhes:</strong> ${attrs.details}</div>` : ''}
    <div style="margin-top: 0.5rem; border-top: 1px solid var(--border-subtle); padding-top: 0.5rem;">
      <strong>Conexões no Grafo (${connectedEdges.length}):</strong>
      <div style="max-height: 140px; overflow-y: auto; margin-top: 0.3rem;">
        ${connectionsHtml || '<span class="text-muted">Sem conexões diretas</span>'}
      </div>
    </div>
  `;

  panel.style.display = 'block';
}

// --- Renderers ---

function getRoleBadgeClass(role) {
  const r = (role || '').toUpperCase();
  if (r === 'FAMILY_CORE') return 'badge-family';
  if (r === 'EXECUTIVE') return 'badge-executive';
  if (r === 'PRODUCER_COOPERATED') return 'badge-producer';
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
    'PRODUCER_COOPERATED': 'Produtor Rural / Associado',
    'COLLEAGUE': 'Colega / Parceiro',
    'STAKEHOLDER': 'Consultoria / Stakeholder',
    'SERVICE_VENDOR': 'Fornecedor',
    'UNKNOWN': 'Não Classificado'
  };
  return map[r] || r;
}

function getSentimentInfo(sentiment) {
  const s = (sentiment || 'NEUTRAL').toUpperCase();
  const map = {
    'POSITIVE': { emoji: '😊', label: 'Positivo', class: 'sentiment-positive' },
    'CONFIDENT': { emoji: '🎯', label: 'Confiante', class: 'sentiment-confident' },
    'NEUTRAL': { emoji: '😐', label: 'Neutro', class: 'sentiment-neutral' },
    'URGENT': { emoji: '🚨', label: 'Urgente', class: 'sentiment-urgent' },
    'ANXIOUS': { emoji: '😟', label: 'Preocupado', class: 'sentiment-anxious' },
    'FRUSTRATED': { emoji: '😤', label: 'Frustrado', class: 'sentiment-frustrated' }
  };
  return map[s] || { emoji: '😐', label: 'Neutro', class: 'sentiment-neutral' };
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
    const cleanPhone = (rawDigits.length === 10 || rawDigits.length === 11) && !rawDigits.startsWith('55') ? `55${rawDigits}` : rawDigits;
    const whatsappLink = cleanPhone ? `https://wa.me/${cleanPhone}` : '#';
    const initials = getInitials(c.name);
    const badgeClass = getRoleBadgeClass(c.role);
    const roleLabel = getRoleLabel(c.role);
    const latestSentInfo = getSentimentInfo(c.latest_sentiment);
    const projectsHtml = (c.projects || []).map(p => `<span class="project-chip">${p}</span>`).join('');

    const recentSentimentsHtml = (c.recent_sentiments && c.recent_sentiments.length > 0)
      ? `
        <div class="sentiments-history">
          <span>Últimos Áudios:</span>
          ${c.recent_sentiments.map(s => {
            const sInfo = getSentimentInfo(s.sentiment);
            return `<span class="sentiment-pill ${sInfo.class}" title="${s.created_at || ''}: ${s.summary || s.sentiment}">${sInfo.emoji} ${s.created_at || ''}</span>`;
          }).join('')}
        </div>
      `
      : '';

    return `
      <div class="contact-card" id="contact-card-${c.id || rawDigits}">
        <div class="contact-header">
          <div class="contact-avatar" id="avatar-${rawDigits}">
            ${c.avatar_url ? `<img src="${c.avatar_url}" alt="${c.name}">` : initials}
          </div>
          <div class="contact-title-group">
            <div class="contact-name">${c.name}</div>
            <div class="contact-company">${c.company || 'Pessoal / Geral'}</div>
            <div style="display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; margin-top: 0.2rem;">
              <span class="badge ${badgeClass}">${roleLabel}</span>
              <span class="sentiment-badge ${latestSentInfo.class}" title="Sentimento mais recente">${latestSentInfo.emoji} ${latestSentInfo.label}</span>
            </div>
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

          ${recentSentimentsHtml}
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

function renderTasks() {
  if (!tasksContainer) return;

  const searchTerm = (tasksSearchInput ? tasksSearchInput.value : '').toLowerCase().trim();
  const filterStatus = tasksFilterStatus ? tasksFilterStatus.value.toUpperCase() : '';
  const filterPriority = tasksFilterPriority ? tasksFilterPriority.value.toUpperCase() : '';

  const filtered = allTasks.filter(t => {
    const matchSearch = (
      t.title.toLowerCase().includes(searchTerm) ||
      (t.assignee && t.assignee.toLowerCase().includes(searchTerm))
    );
    const matchStatus = !filterStatus || t.status === filterStatus;
    const matchPriority = !filterPriority || t.priority === filterPriority;
    return matchSearch && matchStatus && matchPriority;
  });

  if (filtered.length === 0) {
    tasksContainer.innerHTML = `
      <div class="empty-state" style="text-align: center; padding: 3rem; color: var(--text-muted);">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">Nenhuma tarefa encontrada</p>
      </div>
    `;
    return;
  }

  tasksContainer.innerHTML = filtered.map(t => {
    const isDone = t.status === 'DONE';
    const priorityColor = t.priority === 'URGENT' ? '#ef4444' : t.priority === 'HIGH' ? '#f59e0b' : '#10b981';

    return `
      <div class="task-card ${isDone ? 'task-done' : ''}">
        <div class="task-info">
          <div class="task-title">${t.title}</div>
          <div class="task-meta">
            <span class="badge" style="background: rgba(255,255,255,0.08); color: ${priorityColor};">${t.priority}</span>
            ${t.assignee ? `<span>👤 ${t.assignee}</span>` : ''}
            ${t.due_date ? `<span>📅 ${t.due_date}</span>` : ''}
          </div>
        </div>
        <div>
          <button class="btn btn-secondary btn-sm" onclick="toggleTaskStatus('${t.id}', '${isDone ? 'PENDING' : 'DONE'}')">
            ${isDone ? '🔄 Reabrir' : '✅ Concluir'}
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function renderMessages() {
  if (!messagesContainer) return;

  if (allMessages.length === 0) {
    messagesContainer.innerHTML = `
      <div class="empty-state" style="text-align: center; padding: 3rem; color: var(--text-muted);">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">Nenhuma mensagem de áudio ou texto processada ainda</p>
        <small>As notas de voz enviadas no WhatsApp aparecerão aqui em tempo real.</small>
      </div>
    `;
    return;
  }

  messagesContainer.innerHTML = allMessages.map(m => {
    const urgencyColor = m.urgency === 'URGENT' ? '#ef4444' : m.urgency === 'HIGH' ? '#f59e0b' : '#10b981';
    return `
      <div class="message-item">
        <div class="message-header">
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span class="message-speaker">${m.speaker || 'Desconhecido'}</span>
            ${m.urgency ? `<span class="badge" style="font-size: 0.75rem; background: rgba(255,255,255,0.08); color: ${urgencyColor};">${m.urgency}</span>` : ''}
            ${m.intent ? `<span class="badge badge-executive" style="font-size: 0.7rem;">${m.intent}</span>` : ''}
          </div>
          <span style="font-size: 0.8rem; color: var(--text-muted);">${m.created_at || ''}</span>
        </div>
        <div class="message-text">"${m.revised_text || m.raw_text}"</div>
        ${m.summary ? `<div class="message-summary">💡 <b>Resumo:</b> ${m.summary}</div>` : ''}
        <div style="display: flex; gap: 0.75rem; margin-top: 0.4rem; font-size: 0.75rem; color: var(--text-muted);">
          ${m.tasks_count ? `<span>📋 <b>${m.tasks_count}</b> tarefa(s) extraída(s)</span>` : ''}
          ${m.entities_count ? `<span>🏷️ <b>${m.entities_count}</b> entidade(s)</span>` : ''}
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

// --- WhatsApp Avatar & Profile Fetcher ---

async function fetchWhatsAppAvatar(phone) {
  const avatarEl = document.getElementById(`avatar-${phone}`);
  if (avatarEl) {
    avatarEl.innerHTML = '<span style="font-size: 0.8rem;">⏳</span>';
  }

  try {
    const res = await fetch(`/api/v1/contacts/profile/${phone}`);
    if (res.ok) {
      const data = await res.json();
      let msg = '';
      if (data.profile_picture_url && avatarEl) {
        avatarEl.innerHTML = `<img src="${data.profile_picture_url}" alt="Foto WhatsApp">`;
        msg += '📸 Foto';
      }
      if (data.name) {
        msg += (msg ? ' e ' : '') + `👤 Nome: "${data.name}"`;
      }

      if (msg) {
        showToast(`Perfil sincronizado do WhatsApp: ${msg}!`);
        loadContacts();
        return;
      }
    }
    showToast('Foto ou nome público não disponíveis para este número no WhatsApp.', true);
    if (avatarEl) avatarEl.textContent = '👤';
  } catch (err) {
    console.error('Erro ao buscar perfil do WhatsApp:', err);
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
      loadGraphData();
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
      loadGraphData();
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

// --- Task Actions ---

async function toggleTaskStatus(taskId, newStatus) {
  try {
    const res = await fetch(`/api/v1/memory/tasks/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    if (res.ok) {
      showToast(`Status da tarefa atualizado para ${newStatus}!`);
      loadTasks();
    }
  } catch (err) {
    console.error('Erro ao atualizar tarefa:', err);
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

// --- Subsistema de Sentimentos & Série Temporal ---

async function loadDailySentiments(targetDate = '') {
  const container = document.getElementById('sentiment-daily-container');
  const badge = document.getElementById('sentiment-day-badge');
  if (!container) return;

  const dateParam = targetDate ? `?date=${targetDate}` : '';
  if (badge) badge.textContent = targetDate || 'Hoje';

  try {
    const res = await fetch(`/api/v1/memory/sentiment/daily${dateParam}`);
    if (res.ok) {
      const snapshots = await res.json();
      renderDailySentiments(snapshots, targetDate);
    }
  } catch (err) {
    console.error('Erro ao carregar sentimentos diários:', err);
  }
}

async function collectSentiments(targetDate = '') {
  try {
    const dateParam = targetDate ? `?date=${targetDate}` : '';
    const res = await fetch(`/api/v1/memory/sentiment/collect${dateParam}`, { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      showToast(`Consolidação concluída! ${data.total_people} pessoa(s) e ${data.total_interactions} interação(ões).`);
      loadDailySentiments(targetDate);
      populateSentimentSpeakers();
    }
  } catch (err) {
    console.error('Erro ao consolidar sentimentos:', err);
    showToast('Erro ao consolidar sentimentos na VPS.', true);
  }
}

function renderDailySentiments(snapshots, targetDate) {
  const container = document.getElementById('sentiment-daily-container');
  if (!container) return;

  if (!snapshots || snapshots.length === 0) {
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 2.5rem; color: var(--text-muted);">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">Nenhuma interação registrada para ${targetDate || 'esta data'}</p>
        <small>Clique em "Consolidar Sentimentos" ou envie mensagens de voz no WhatsApp para alimentar o termômetro.</small>
      </div>
    `;
    return;
  }

  container.innerHTML = snapshots.map(s => {
    const sInfo = getSentimentInfo(s.dominant_sentiment);
    const badgeClass = getRoleBadgeClass(s.role);
    const roleLabel = getRoleLabel(s.role);
    const scoreFormatted = (s.avg_sentiment_score > 0 ? '+' : '') + s.avg_sentiment_score.toFixed(2);
    const initials = getInitials(s.speaker);

    const highlightsHtml = (s.highlights || []).map(h => `
      <div style="font-size: 0.75rem; color: var(--text-muted); background: rgba(255,255,255,0.03); padding: 0.25rem 0.4rem; border-radius: 4px; margin-top: 0.2rem;">
        ${h}
      </div>
    `).join('');

    return `
      <div class="contact-card" style="cursor: pointer;" onclick="selectSpeakerForTimeline('${s.speaker}')">
        <div class="contact-header">
          <div class="contact-avatar">${initials}</div>
          <div class="contact-title-group">
            <div class="contact-name">${s.speaker}</div>
            <div style="display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; margin-top: 0.2rem;">
              <span class="badge ${badgeClass}">${roleLabel}</span>
              <span class="sentiment-badge ${sInfo.class}">
                ${sInfo.emoji} ${sInfo.label} (${scoreFormatted})
              </span>
            </div>
          </div>
        </div>

        <div class="contact-details" style="margin-top: 0.6rem;">
          <div style="font-size: 0.8rem; color: var(--text-main); font-weight: 500;">
            📊 <b>${s.interactions_count}</b> interações hoje:
            <span style="color: #4ade80;">+${s.positive_count}</span> / 
            <span style="color: #94a3b8;">~${s.neutral_count}</span> / 
            <span style="color: #f87171;">-${s.negative_count}</span>
          </div>

          ${s.executive_summary ? `<div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem;">📝 ${s.executive_summary}</div>` : ''}

          ${highlightsHtml ? `<div style="margin-top: 0.4rem;">${highlightsHtml}</div>` : ''}
        </div>

        <div class="contact-actions" style="margin-top: 0.6rem;">
          <button class="btn btn-secondary btn-sm" style="width: 100%;" onclick="event.stopPropagation(); selectSpeakerForTimeline('${s.speaker}')">
            📈 Ver Série Temporal
          </button>
        </div>
      </div>
    `;
  }).join('');
}

async function populateSentimentSpeakers() {
  const select = document.getElementById('sentiment-speaker-select');
  if (!select) return;

  try {
    const res = await fetch('/api/v1/contacts');
    if (res.ok) {
      const contacts = await res.json();
      select.innerHTML = '<option value="">Selecione uma pessoa para ver a Série Temporal...</option>' +
        contacts.map(c => `<option value="${c.name}">${c.name} (${c.role})</option>`).join('');
    }
  } catch (err) {
    console.error('Erro ao popular lista de pessoas para sentimentos:', err);
  }
}

function selectSpeakerForTimeline(speakerName) {
  const select = document.getElementById('sentiment-speaker-select');
  if (select) {
    select.value = speakerName;
  }
  loadSentimentTimeline(speakerName);
}

async function loadSentimentTimeline(speakerName) {
  const panel = document.getElementById('sentiment-timeline-panel');
  const nameEl = document.getElementById('timeline-speaker-name');
  const metaEl = document.getElementById('timeline-speaker-meta');
  const badgeEl = document.getElementById('timeline-overall-badge');
  const container = document.getElementById('timeline-points-container');

  if (!panel || !speakerName) return;

  panel.style.display = 'block';
  nameEl.textContent = speakerName;
  metaEl.textContent = 'Carregando série temporal...';
  container.innerHTML = '<p class="text-muted">Buscando dados históricos na VPS...</p>';

  try {
    const res = await fetch(`/api/v1/memory/sentiment/timeline?speaker=${encodeURIComponent(speakerName)}`);
    if (res.ok) {
      const data = await res.json();
      renderSentimentTimeline(data);
    }
  } catch (err) {
    console.error('Erro ao carregar série temporal:', err);
    container.innerHTML = '<p class="text-muted">Erro ao carregar série temporal.</p>';
  }
}

function renderSentimentTimeline(data) {
  const metaEl = document.getElementById('timeline-speaker-meta');
  const badgeEl = document.getElementById('timeline-overall-badge');
  const container = document.getElementById('timeline-points-container');

  const sInfo = getSentimentInfo(data.overall_sentiment);
  metaEl.textContent = `Papel: ${data.role} • ${data.total_days_tracked} dia(s) rastreado(s) • Score Médio Geral: ${data.avg_score > 0 ? '+' : ''}${data.avg_score.toFixed(2)}`;
  badgeEl.innerHTML = `<span class="sentiment-badge ${sInfo.class}" style="font-size: 0.9rem;">${sInfo.emoji} Humor Geral: ${sInfo.label}</span>`;

  if (!data.timeline || data.timeline.length === 0) {
    container.innerHTML = '<p class="text-muted">Nenhum ponto temporal registrado para este contato ainda.</p>';
    return;
  }

  container.innerHTML = data.timeline.map(p => {
    const ptInfo = getSentimentInfo(p.dominant_sentiment);
    const scoreWidth = Math.min(Math.max((p.avg_sentiment_score + 1.0) / 2.0 * 100, 5), 100);
    const barColor = p.dominant_sentiment === 'POSITIVE' ? '#10b981' : p.dominant_sentiment === 'NEGATIVE' ? '#ef4444' : '#64748b';

    const highlightsHtml = (p.highlights || []).map(h => `
      <div style="font-size: 0.75rem; color: var(--text-muted); padding: 0.2rem 0;">• ${h}</div>
    `).join('');

    return `
      <div style="background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 8px; padding: 0.8rem 1rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
          <div style="display: flex; align-items: center; gap: 0.6rem;">
            <span style="font-weight: 600; color: var(--text-main);">📅 ${p.date}</span>
            <span class="sentiment-badge ${ptInfo.class}">${ptInfo.emoji} ${ptInfo.label}</span>
          </div>
          <div style="font-size: 0.8rem; color: var(--text-muted);">
            <b>${p.interactions_count}</b> msg(s) | Score: <b>${p.avg_sentiment_score > 0 ? '+' : ''}${p.avg_sentiment_score.toFixed(2)}</b>
          </div>
        </div>

        <!-- Barra de Progresso Emocional -->
        <div style="width: 100%; height: 6px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden; margin: 0.4rem 0;">
          <div style="width: ${scoreWidth}%; height: 100%; background: ${barColor}; border-radius: 3px;"></div>
        </div>

        ${highlightsHtml ? `<div style="margin-top: 0.4rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 0.4rem;">${highlightsHtml}</div>` : ''}
      </div>
    `;
  }).join('');
}
