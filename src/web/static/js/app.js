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

// Performance & Pagination State
let contactsLimit = 20;
let tasksLimit = 10;
let messagesCurrentPage = 1;
const messagesPageSize = 10;
let dictCurrentPage = 1;
const dictPageSize = 50;

// WordMap Strategic State
let currentWordMapItems = [];
let currentWordMapFilter = 'ALL';
let selectedWordMapTopic = null;

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
const contactFilterPeriod = document.getElementById('contact-filter-period');
const dictSearchInput = document.getElementById('dict-search');
const dictFilterCategory = document.getElementById('dict-filter-category');
const tasksSearchInput = document.getElementById('tasks-search');
const tasksFilterStatus = document.getElementById('tasks-filter-status');
const tasksFilterPriority = document.getElementById('tasks-filter-priority');
const msgSearchInput = document.getElementById('msg-search');
const msgFilterIntent = document.getElementById('msg-filter-intent');
const msgFilterSentiment = document.getElementById('msg-filter-sentiment');
const btnRefreshMessages = document.getElementById('btn-refresh-messages');

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
    } else if (targetId === 'tab-analytics') {
      loadAnalyticsDashboard();
    } else if (targetId === 'tab-sentiment') {
      loadDailySentiments();
      populateSentimentSpeakers();
    }
  });
});

function activateTab(tabId) {
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (btn) btn.click();
}
window.activateTab = activateTab;

// Init
document.addEventListener('DOMContentLoaded', () => {
  loadStats();
  loadContacts();
  loadDictionary();

  // Search & Filter Listeners
  contactSearchInput.addEventListener('input', renderContacts);
  contactFilterRole.addEventListener('change', renderContacts);
  if (contactFilterPeriod) contactFilterPeriod.addEventListener('change', renderContacts);
  
  const contactsLimitSelect = document.getElementById('contacts-limit-select');
  if (contactsLimitSelect) {
    contactsLimitSelect.addEventListener('change', (e) => {
      contactsLimit = e.target.value === 'all' ? 'all' : parseInt(e.target.value, 10);
      renderContacts();
    });
  }

  dictSearchInput.addEventListener('input', () => { dictCurrentPage = 1; renderDictionary(); });
  dictFilterCategory.addEventListener('change', () => { dictCurrentPage = 1; renderDictionary(); });
  
  const btnDictPrev = document.getElementById('btn-dict-prev');
  const btnDictNext = document.getElementById('btn-dict-next');
  if (btnDictPrev) {
    btnDictPrev.addEventListener('click', () => {
      if (dictCurrentPage > 1) {
        dictCurrentPage--;
        renderDictionary();
        if (dictionaryContainer) dictionaryContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }
  if (btnDictNext) {
    btnDictNext.addEventListener('click', () => {
      dictCurrentPage++;
      renderDictionary();
      if (dictionaryContainer) dictionaryContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  if (tasksSearchInput) tasksSearchInput.addEventListener('input', renderTasks);
  if (tasksFilterStatus) tasksFilterStatus.addEventListener('change', renderTasks);
  if (tasksFilterPriority) tasksFilterPriority.addEventListener('change', renderTasks);

  const tasksLimitSelect = document.getElementById('tasks-limit-select');
  if (tasksLimitSelect) {
    tasksLimitSelect.addEventListener('change', (e) => {
      tasksLimit = e.target.value === 'all' ? 'all' : parseInt(e.target.value, 10);
      renderTasks();
    });
  }

  if (msgSearchInput) msgSearchInput.addEventListener('input', () => { messagesCurrentPage = 1; renderMessages(); });
  if (msgFilterIntent) msgFilterIntent.addEventListener('change', () => { messagesCurrentPage = 1; renderMessages(); });
  if (msgFilterSentiment) msgFilterSentiment.addEventListener('change', () => { messagesCurrentPage = 1; renderMessages(); });

  const btnMsgPrev = document.getElementById('btn-msg-prev');
  const btnMsgNext = document.getElementById('btn-msg-next');
  if (btnMsgPrev) {
    btnMsgPrev.addEventListener('click', () => {
      if (messagesCurrentPage > 1) {
        messagesCurrentPage--;
        renderMessages();
        if (messagesContainer) messagesContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }
  if (btnMsgNext) {
    btnMsgNext.addEventListener('click', () => {
      messagesCurrentPage++;
      renderMessages();
      if (messagesContainer) messagesContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }

  // Analytics Listeners
  const analyticsPeriodSelect = document.getElementById('analytics-period');
  const analyticsGroupBySelect = document.getElementById('analytics-groupby');
  const btnRefreshAnalytics = document.getElementById('btn-refresh-analytics');
  if (analyticsPeriodSelect) analyticsPeriodSelect.addEventListener('change', loadAnalyticsDashboard);
  if (analyticsGroupBySelect) analyticsGroupBySelect.addEventListener('change', loadAnalyticsDashboard);
  if (btnRefreshAnalytics) btnRefreshAnalytics.addEventListener('click', loadAnalyticsDashboard);

  // WordMap Strategic Filter Buttons
  document.querySelectorAll('.wordmap-filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.wordmap-filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentWordMapFilter = btn.dataset.pillar;
      renderWordMapCloud();
    });
  });

  // WordMap Modal Actions
  const btnCloseWordMapModal = document.getElementById('btn-close-wordmap-modal');
  const modalWordMapAction = document.getElementById('modal-wordmap-action');
  if (btnCloseWordMapModal && modalWordMapAction) {
    btnCloseWordMapModal.addEventListener('click', () => modalWordMapAction.classList.remove('active'));
  }

  const btnWordMapMelpomene = document.getElementById('btn-wordmap-ask-melpomene');
  if (btnWordMapMelpomene && modalWordMapAction) {
    btnWordMapMelpomene.addEventListener('click', () => {
      if (!selectedWordMapTopic) return;
      modalWordMapAction.classList.remove('active');
      activateTab('tab-query');
      setQuery(`O que as conversas relatam sobre '${selectedWordMapTopic.word}'?`);
      runHermesQuery();
    });
  }

  const btnWordMapCaliope = document.getElementById('btn-wordmap-filter-caliope');
  if (btnWordMapCaliope && modalWordMapAction) {
    btnWordMapCaliope.addEventListener('click', () => {
      if (!selectedWordMapTopic) return;
      modalWordMapAction.classList.remove('active');
      activateTab('tab-messages');
      if (msgSearchInput) {
        msgSearchInput.value = selectedWordMapTopic.word;
        messagesCurrentPage = 1;
        renderMessages();
      }
    });
  }

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

  const btnTogglePhysics = document.getElementById('btn-toggle-physics');
  if (btnTogglePhysics) {
    btnTogglePhysics.addEventListener('click', toggleGraphPhysics);
  }

  const graphFilterMode = document.getElementById('graph-filter-mode');
  if (graphFilterMode) {
    graphFilterMode.addEventListener('change', () => {
      loadGraphData();
      showToast('Filtro do grafo atualizado!');
    });
  }

  const graphSearchNode = document.getElementById('graph-search-node');
  if (graphSearchNode) {
    graphSearchNode.addEventListener('input', (e) => {
      const term = (e.target.value || '').toLowerCase().trim();
      if (!term || !graphRawData || !visNetworkInstance) return;
      const matchedNode = graphRawData.nodes.find(n => (n.label && n.label.toLowerCase().includes(term)) || (n.id && n.id.toLowerCase().includes(term)));
      if (matchedNode) {
        visNetworkInstance.focus(matchedNode.id, {
          scale: 1.2,
          animation: { duration: 500, easingFunction: 'easeInOutQuad' }
        });
        showNodeDetails(matchedNode.id);
      }
    });
  }

  const btnTriggerJanitor = document.getElementById('btn-trigger-janitor');
  if (btnTriggerJanitor) {
    btnTriggerJanitor.addEventListener('click', triggerGraphJanitor);
  }

  const btnCloseNodeDetail = document.getElementById('btn-close-node-detail');
  if (btnCloseNodeDetail) {
    btnCloseNodeDetail.addEventListener('click', () => {
      document.getElementById('node-detail-panel').style.display = 'none';
    });
  }

  // RAG Query Testing Listeners
  const btnRunQuery = document.getElementById('btn-run-query');
  if (btnRunQuery) {
    btnRunQuery.addEventListener('click', runHermesQuery);
  }

  const queryInput = document.getElementById('query-input');
  if (queryInput) {
    queryInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        runHermesQuery();
      }
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
  const btnEratoViewAll = document.getElementById('btn-erato-view-all');
  if (btnEratoViewAll) {
    btnEratoViewAll.addEventListener('click', () => {
      if (sentimentDatePicker) sentimentDatePicker.value = '';
      btnEratoViewAll.className = 'btn btn-primary btn-sm';
      loadDailySentiments('all');
    });
  }

  if (sentimentDatePicker) {
    sentimentDatePicker.addEventListener('change', (e) => {
      if (btnEratoViewAll) btnEratoViewAll.className = 'btn btn-secondary btn-sm';
      loadDailySentiments(e.target.value);
    });
  }

  const btnCollectSentiment = document.getElementById('btn-collect-today-sentiment');
  if (btnCollectSentiment) {
    btnCollectSentiment.addEventListener('click', async () => {
      const selectedDate = sentimentDatePicker && sentimentDatePicker.value ? sentimentDatePicker.value : '';
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

  // Harvest Trigger Listener
  const btnTriggerHarvest = document.getElementById('btn-trigger-harvest');
  if (btnTriggerHarvest) {
    btnTriggerHarvest.addEventListener('click', triggerHarvest);
  }

  // Messages Tab Filter Listeners
  if (msgSearchInput) {
    msgSearchInput.addEventListener('input', renderMessages);
  }
  if (msgFilterIntent) {
    msgFilterIntent.addEventListener('change', renderMessages);
  }
  if (msgFilterSentiment) {
    msgFilterSentiment.addEventListener('change', renderMessages);
  }
  if (btnRefreshMessages) {
    btnRefreshMessages.addEventListener('click', () => {
      loadMessages();
      showToast('Feed de mensagens atualizado!');
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
      statGraphNodesEl.textContent = `${data.graph_nodes || 32} nós na Memória`;
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
    await loadCandidates();
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

let isGraphPhysicsActive = false;

async function loadGraphData() {
  try {
    const filterSelect = document.getElementById('graph-filter-mode');
    const filterVal = filterSelect ? filterSelect.value : '7';
    const daysCutoff = parseInt(filterVal, 10);
    const mainOnly = isNaN(daysCutoff) || daysCutoff > 0;
    const effectiveCutoff = isNaN(daysCutoff) ? 7 : daysCutoff;

    const res = await fetch(`/api/v1/memory/graph/full?main_only=${mainOnly}&days_cutoff=${effectiveCutoff}`);
    if (res.ok) {
      graphRawData = await res.json();
      if (document.getElementById('tab-graph').classList.contains('active')) {
        renderInteractiveGraph();
      }
    }
  } catch (err) {
    console.error('Erro ao carregar grafo:', err);
  }
}

function updatePhysicsButtonState(active) {
  const btn = document.getElementById('btn-toggle-physics');
  if (!btn) return;
  if (active) {
    btn.innerHTML = '⚡ Física: Ativa';
    btn.classList.remove('btn-secondary');
    btn.classList.add('btn-primary');
  } else {
    btn.innerHTML = '🧊 Física: Congelada';
    btn.classList.remove('btn-primary');
    btn.classList.add('btn-secondary');
  }
}

function toggleGraphPhysics() {
  if (!visNetworkInstance) return;
  isGraphPhysicsActive = !isGraphPhysicsActive;
  visNetworkInstance.setOptions({ physics: { enabled: isGraphPhysicsActive } });
  updatePhysicsButtonState(isGraphPhysicsActive);
  showToast(isGraphPhysicsActive ? '⚡ Simulação de física ativada!' : '🧊 Grafo congelado (modo de alta performance mobile).');
}
window.toggleGraphPhysics = toggleGraphPhysics;

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
      stabilization: { iterations: 60, updateInterval: 20 }
    },
    interaction: {
      hover: true,
      tooltipDelay: 100,
      zoomView: true,
      dragView: true,
      hideEdgesOnDrag: true,
      hideEdgesOnZoom: true
    }
  };

  if (visNetworkInstance) {
    visNetworkInstance.destroy();
  }

  visNetworkInstance = new vis.Network(container, data, options);

  // Congelamento automático de física após estabilizar para economia total de bateria/CPU em smartphones
  visNetworkInstance.on('stabilizationIterationsDone', () => {
    visNetworkInstance.setOptions({ physics: { enabled: false } });
    isGraphPhysicsActive = false;
    updatePhysicsButtonState(false);
  });

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

async function triggerGraphJanitor() {
  const btn = document.getElementById('btn-trigger-janitor');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '🧹 Fazendo Faxina...';
  }

  try {
    const res = await fetch('/api/v1/memory/graph/clean', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) throw new Error('Falha ao acionar a Zeladora');

    const data = await res.json();
    showToast(data.summary || 'Faxina concluída com sucesso!');

    // Recarrega os nós no grafo e estatísticas
    await loadGraphData();
    await loadStats();
  } catch (err) {
    console.error('Erro na faxina da Zeladora:', err);
    showToast('Erro ao executar a faxina no Grafo.', true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🧹 Faxina da Zeladora';
    }
  }
}
window.triggerGraphJanitor = triggerGraphJanitor;

// --- Renderers ---

function getRoleBadgeClass(role) {
  const r = (role || '').toUpperCase();
  if (r === 'OWNER') return 'badge-owner';
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
    'OWNER': '👑 PROPRIETÁRIO',
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

function formatPhoneNumber(phone) {
  if (!phone) return '';
  const digits = phone.replace(/\D/g, '');
  if (digits.length === 13 && digits.startsWith('55')) {
    return `+55 (${digits.substring(2, 4)}) ${digits.substring(4, 9)}-${digits.substring(9)}`;
  } else if (digits.length === 12 && digits.startsWith('55')) {
    return `+55 (${digits.substring(2, 4)}) ${digits.substring(4, 8)}-${digits.substring(8)}`;
  } else if (digits.length === 11) {
    return `(${digits.substring(0, 2)}) ${digits.substring(2, 7)}-${digits.substring(7)}`;
  } else if (digits.length === 10) {
    return `(${digits.substring(0, 2)}) ${digits.substring(2, 6)}-${digits.substring(6)}`;
  }
  return phone;
}

function formatLastInteractionBadge(dtStr) {
  if (!dtStr) return '<span style="color: var(--text-muted); font-size: 0.75rem;">💬 Sem mensagens recentes</span>';
  const dt = new Date(dtStr);
  const now = new Date();
  const diffMs = now - dt;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  const timeStr = dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });

  if (diffDays === 0 && dt.getDate() === now.getDate()) {
    return `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 0.72rem;" title="${dt.toLocaleString('pt-BR')}">🟢 Hoje às ${timeStr}</span>`;
  } else if (diffDays <= 1) {
    return `<span class="badge" style="background: rgba(59, 130, 246, 0.15); color: #60a5fa; font-size: 0.72rem;" title="${dt.toLocaleString('pt-BR')}">Ontem às ${timeStr}</span>`;
  } else if (diffDays <= 7) {
    return `<span class="badge" style="background: rgba(139, 92, 246, 0.15); color: #c084fc; font-size: 0.72rem;" title="${dt.toLocaleString('pt-BR')}">Há ${diffDays} dias</span>`;
  } else if (diffDays <= 30) {
    return `<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #fbbf24; font-size: 0.72rem;" title="${dt.toLocaleString('pt-BR')}">Há ${Math.round(diffDays / 7)} sem</span>`;
  } else {
    return `<span class="badge" style="background: rgba(100, 116, 139, 0.15); color: #94a3b8; font-size: 0.72rem;" title="${dt.toLocaleString('pt-BR')}">${dt.toLocaleDateString('pt-BR')}</span>`;
  }
}

function renderContacts() {
  const searchTerm = contactSearchInput.value.toLowerCase().trim();
  const filterRole = contactFilterRole.value.toUpperCase();
  const filterPeriod = (contactFilterPeriod ? contactFilterPeriod.value : 'today').toLowerCase();

  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const start7d = now.getTime() - (7 * 24 * 60 * 60 * 1000);
  const start30d = now.getTime() - (30 * 24 * 60 * 60 * 1000);

  let filtered = allContacts.filter(c => {
    const matchSearch = (
      c.name.toLowerCase().includes(searchTerm) ||
      (c.company && c.company.toLowerCase().includes(searchTerm)) ||
      (c.phone_number && c.phone_number.toLowerCase().includes(searchTerm)) ||
      (c.role && c.role.toLowerCase().includes(searchTerm))
    );
    const matchRole = !filterRole || (c.role && c.role.toUpperCase() === filterRole);

    let matchPeriod = true;
    if (filterPeriod !== 'all') {
      if (!c.last_interaction_at) {
        matchPeriod = false;
      } else {
        const itemTime = new Date(c.last_interaction_at).getTime();
        if (filterPeriod === 'today') {
          matchPeriod = itemTime >= startToday;
        } else if (filterPeriod === '7d') {
          matchPeriod = itemTime >= start7d;
        } else if (filterPeriod === '30d') {
          matchPeriod = itemTime >= start30d;
        }
      }
    }

    return matchSearch && matchRole && matchPeriod;
  });

  // Se filtrado por período ou busca, ordena por data de interação mais recente
  if (filterPeriod !== 'all') {
    filtered.sort((a, b) => {
      const timeA = a.last_interaction_at ? new Date(a.last_interaction_at).getTime() : 0;
      const timeB = b.last_interaction_at ? new Date(b.last_interaction_at).getTime() : 0;
      return timeB - timeA;
    });
  }

  const totalFiltered = filtered.length;
  const paginationBar = document.getElementById('contacts-pagination-bar');
  const paginationInfo = document.getElementById('contacts-pagination-info');

  if (totalFiltered === 0) {
    if (paginationBar) paginationBar.style.display = 'none';
    contactsContainer.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: var(--text-muted);">
        <p style="font-size: 1.2rem; margin-bottom: 0.5rem;">Nenhum contato encontrado no período selecionado (${filterPeriod === 'today' ? 'Hoje' : filterPeriod === '7d' ? 'Últimos 7 dias' : 'Último Mês'})</p>
        <small>Mude o filtro para <strong>"Todos os Contatos"</strong> ou aguarde novas interações no WhatsApp.</small>
      </div>
    `;
    return;
  }

  const displayedList = contactsLimit === 'all' ? filtered : filtered.slice(0, contactsLimit);

  if (paginationBar) paginationBar.style.display = 'flex';
  if (paginationInfo) {
    paginationInfo.innerHTML = `Exibindo <strong>${displayedList.length}</strong> de <strong>${totalFiltered}</strong> contatos`;
  }

  contactsContainer.innerHTML = displayedList.map(c => {
    const rawDigits = (c.phone_number || '').replace(/\D/g, '');
    const hasValidPhone = rawDigits.length >= 8;
    const cleanPhone = hasValidPhone ? ((rawDigits.length === 10 || rawDigits.length === 11) && !rawDigits.startsWith('55') ? `55${rawDigits}` : rawDigits) : '';
    const whatsappLink = cleanPhone ? `https://wa.me/${cleanPhone}` : '#';
    const displayPhone = hasValidPhone ? formatPhoneNumber(cleanPhone) : '';
    const initials = getInitials(c.name);
    const badgeClass = getRoleBadgeClass(c.role);
    const roleLabel = getRoleLabel(c.role);
    const latestSentInfo = getSentimentInfo(c.latest_sentiment);
    const interactionBadgeHtml = formatLastInteractionBadge(c.last_interaction_at);
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

    const isFav = Boolean(c.is_favorite);
    const canGenTasks = Boolean(c.can_generate_tasks);
    const weightPercent = Math.round((c.effective_weight || 0.4) * 100);

    return `
      <div class="contact-card ${isFav ? 'is-favorite' : ''}" id="contact-card-${c.id || cleanPhone || c.name}">
        <div class="contact-header">
          <div class="contact-avatar" id="avatar-${cleanPhone || c.name}">
            ${c.avatar_url ? `<img src="${c.avatar_url}" alt="${c.name}">` : initials}
          </div>
          <div class="contact-title-group" style="flex: 1;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
              <div class="contact-name">${c.name}</div>
              <button class="btn-favorite-icon ${isFav ? 'active' : ''}" onclick="toggleContactFavorite('${c.id || cleanPhone || c.name}')" title="${isFav ? 'Remover dos Favoritos' : 'Salvar como Favorito (+10% de peso)'}">
                ${isFav ? '⭐' : '☆'}
              </button>
            </div>
            <div class="contact-company">${c.company || 'Pessoal / Geral'}</div>
            <div style="display: flex; gap: 0.35rem; align-items: center; flex-wrap: wrap; margin-top: 0.25rem;">
              <span class="badge ${badgeClass}">${roleLabel}</span>
              ${isFav ? `<span class="badge badge-owner" style="font-size: 0.68rem;">⭐ +10% Fav</span>` : ''}
              <span class="badge badge-vendor" style="font-size: 0.68rem;" title="Peso efetivo de prioridade">${weightPercent}% Peso</span>
              <span class="sentiment-badge ${latestSentInfo.class}" title="Sentimento mais recente">${latestSentInfo.emoji} ${latestSentInfo.label}</span>
              
              <!-- Toggle de Permissão para Gerar Tarefas -->
              <label class="toggle-tasks-wrapper ${canGenTasks ? 'active' : ''}" title="Permitir que mensagens deste contato gerem tarefas acionáveis para você">
                <span class="toggle-switch-ui">
                  <input type="checkbox" ${canGenTasks ? 'checked' : ''} onchange="toggleContactTasks('${c.id || cleanPhone || c.name}')">
                  <span class="toggle-switch-slider"></span>
                </span>
                <span class="toggle-tasks-label">${canGenTasks ? '⚡ Cria Tarefas' : '⚡ Tarefas OFF'}</span>
              </label>
            </div>
          </div>
        </div>

        <div class="contact-details">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
            ${hasValidPhone ? `
              <a href="${whatsappLink}" target="_blank" class="contact-phone-link" title="Abrir conversa no WhatsApp">
                📱 ${displayPhone}
              </a>
            ` : '<span class="text-muted" style="font-size: 0.8rem;">📱 Sem telefone</span>'}
            ${interactionBadgeHtml}
          </div>

          ${c.notes ? `<div style="font-size: 0.8rem; color: var(--text-muted);">${c.notes}</div>` : ''}

          ${projectsHtml ? `<div class="contact-projects">${projectsHtml}</div>` : ''}

          ${recentSentimentsHtml}
        </div>

        <div class="contact-actions">
          ${cleanPhone ? `
            <button class="btn btn-secondary btn-sm" onclick="fetchWhatsAppAvatar('${cleanPhone}')" title="Buscar foto oficial do perfil no WhatsApp">
              📸 Foto
            </button>
          ` : '<span></span>'}

          <div style="display: flex; gap: 0.4rem; align-items: center;">
            <button class="btn btn-secondary btn-sm" onclick="toggleContactFavorite('${c.id || cleanPhone || c.name}')" title="Alternar favorito">
              ${isFav ? '⭐ Favorito' : '☆ Favoritar'}
            </button>
            <button class="btn btn-secondary btn-sm" onclick="editContact('${c.id || c.name}')">✏️</button>
            <button class="btn btn-danger btn-sm" onclick="deleteContact('${c.id || c.name}')">🗑️</button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function toggleContactFavorite(contactId) {
  try {
    const res = await fetch(`/api/v1/contacts/${encodeURIComponent(contactId)}/favorite`, { method: 'PATCH' });
    if (!res.ok) throw new Error('Falha ao alternar status de favorito');
    const updated = await res.json();
    const idx = allContacts.findIndex(c => c.id === updated.id || c.name === updated.name || c.phone_number === updated.phone_number);
    if (idx !== -1) {
      allContacts[idx] = updated;
    }
    renderContacts();
    showToast(updated.is_favorite ? `⭐ ${updated.name} salvo nos Favoritos (+10% de peso)!` : `☆ ${updated.name} removido dos Favoritos.`);
  } catch (err) {
    showToast('Erro ao atualizar favorito: ' + err.message, 'error');
  }
}
window.toggleContactFavorite = toggleContactFavorite;

async function toggleContactTasks(contactId) {
  try {
    const res = await fetch(`/api/v1/contacts/${encodeURIComponent(contactId)}/toggle-tasks`, { method: 'PATCH' });
    if (!res.ok) throw new Error('Falha ao alternar permissão de tarefas');
    const updated = await res.json();
    const idx = allContacts.findIndex(c => c.id === updated.id || c.name === updated.name || c.phone_number === updated.phone_number);
    if (idx !== -1) {
      allContacts[idx] = updated;
    }
    renderContacts();
    showToast(updated.can_generate_tasks ? `⚡ ${updated.name} agora PODE gerar tarefas!` : `🔒 ${updated.name} NÃO gerará mais tarefas.`);
  } catch (err) {
    showToast('Erro ao atualizar permissão de tarefas: ' + err.message, 'error');
  }
}
window.toggleContactTasks = toggleContactTasks;

function renderTasks() {
  if (!tasksContainer) return;

  const searchTerm = (tasksSearchInput ? tasksSearchInput.value : '').toLowerCase().trim();
  const filterStatus = tasksFilterStatus ? tasksFilterStatus.value.toUpperCase() : '';
  const filterPriority = tasksFilterPriority ? tasksFilterPriority.value.toUpperCase() : '';

  const filtered = allTasks.filter(t => {
    const matchSearch = (
      t.title.toLowerCase().includes(searchTerm) ||
      (t.assignee && t.assignee.toLowerCase().includes(searchTerm)) ||
      (t.speaker && t.speaker.toLowerCase().includes(searchTerm)) ||
      (t.message_summary && t.message_summary.toLowerCase().includes(searchTerm))
    );
    const matchStatus = !filterStatus || t.status === filterStatus;
    const matchPriority = !filterPriority || t.priority === filterPriority;
    return matchSearch && matchStatus && matchPriority;
  });

  const totalFiltered = filtered.length;
  const paginationBar = document.getElementById('tasks-pagination-bar');
  const paginationInfo = document.getElementById('tasks-pagination-info');

  if (totalFiltered === 0) {
    if (paginationBar) paginationBar.style.display = 'none';
    tasksContainer.innerHTML = `
      <div class="empty-state" style="text-align: center; padding: 3rem; color: var(--text-muted);">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">Nenhuma tarefa encontrada</p>
        <small>Tarefas acionáveis extraídas de notas de voz aparecerão aqui com a ancoragem de quem solicitou.</small>
      </div>
    `;
    return;
  }

  const displayedList = tasksLimit === 'all' ? filtered : filtered.slice(0, tasksLimit);

  if (paginationBar) paginationBar.style.display = 'flex';
  if (paginationInfo) {
    paginationInfo.innerHTML = `Exibindo <strong>${displayedList.length}</strong> de <strong>${totalFiltered}</strong> tarefas`;
  }

  tasksContainer.innerHTML = displayedList.map(t => {
    const isDone = t.status === 'DONE';
    const isCancelled = t.status === 'CANCELLED';
    const priorityColor = t.priority === 'URGENT' ? '#ef4444' : t.priority === 'HIGH' ? '#f59e0b' : '#10b981';
    const speakerName = t.speaker || 'Desconhecido';
    const initials = speakerName.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase() || 'U';

    // Telefone / WhatsApp do solicitante
    const phoneClean = (t.sender_phone || '').replace(/[^0-9]/g, '');
    const waLink = phoneClean.length >= 10 ? `https://wa.me/${phoneClean}` : null;

    // Rótulo amigável do papel
    const roleLabels = {
      'PRODUCER_COOPERATED': '🌾 Produtor Rural',
      'FAMILY_CORE': '🏠 Família',
      'EXECUTIVE': '👔 Diretoria / Gestão',
      'COLLEAGUE': '🤝 Colega / Parceiro',
      'STAKEHOLDER': '💼 Consultor',
      'SERVICE_VENDOR': '🚚 Fornecedor',
      'UNKNOWN': '👤 Contato',
    };
    const roleBadge = t.sender_role ? (roleLabels[t.sender_role] || t.sender_role) : null;

    let cardClass = 'task-card';
    if (isDone) cardClass += ' task-done';
    if (isCancelled) cardClass += ' task-cancelled';

    return `
      <div class="${cardClass}" id="task-card-${t.id}">
        <!-- Topo: Título da Tarefa e Solicitante (Gatilho) -->
        <div class="task-top-row">
          <div style="flex: 1;">
            <div class="task-title">
              ${isCancelled ? '<span style="color: #ef4444; font-size: 0.85rem; margin-right: 0.4rem;">[IGNORADA]</span>' : ''}
              ${t.title}
            </div>
          </div>

          <!-- Box de Ancoragem do Solicitante (Gatilho) -->
          <div class="task-requester-box" title="Pessoa que enviou o áudio / gerou o gatilho desta tarefa">
            <div class="task-requester-avatar">${initials}</div>
            <div>
              <div style="font-size: 0.72rem; color: var(--text-muted); line-height: 1;">Gatilho de:</div>
              <div class="task-requester-name">${speakerName}</div>
            </div>
            ${roleBadge ? `<span class="badge" style="font-size: 0.68rem; background: rgba(255,255,255,0.06);">${roleBadge}</span>` : ''}
          </div>
        </div>

        <!-- Menu Sanfona (Accordion) de Contexto Original "De quem foi ➔ Pra quem foi" -->
        <div class="task-accordion" id="task-accordion-${t.id}">
          <button class="task-accordion-header" type="button" onclick="toggleTaskAccordion('${t.id}')">
            <div class="task-accordion-header-left">
              <span class="accordion-chevron" id="chevron-${t.id}">▶</span>
              <span class="accordion-title-text">
                <b>Origem do Disparo & Contexto</b>
              </span>
            </div>
            <div class="task-flow-pills">
              <span class="flow-pill flow-from" title="Remetente da mensagem que disparou a tarefa">
                🗣️ De: <b>${speakerName}</b>
              </span>
              <span class="flow-arrow">➔</span>
              <span class="flow-pill flow-to" title="Destinatário / Atribuído a">
                🎯 Para: <b>${t.assignee || 'Bruno Conter'}</b>
              </span>
            </div>
          </button>

          <div class="task-accordion-content" id="task-accordion-body-${t.id}" style="display: none;">
            <div class="task-participants-bar">
              <div>
                <span style="color: var(--text-muted); font-size: 0.72rem; display: block;">🗣️ Remetente:</span>
                <div><b>${speakerName}</b> ${roleBadge ? `<span class="badge" style="font-size: 0.65rem; margin-left: 0.2rem;">${roleBadge}</span>` : ''}</div>
              </div>
              <div>
                <span style="color: var(--text-muted); font-size: 0.72rem; display: block;">🎯 Destinatário / Responsável:</span>
                <div><b>${t.assignee || 'Bruno Conter'}</b> ${t.due_date ? `(Prazo: ${t.due_date})` : ''}</div>
              </div>
              ${t.message_time ? `
                <div>
                  <span style="color: var(--text-muted); font-size: 0.72rem; display: block;">⏱️ Horário do Disparo:</span>
                  <div>${t.message_time}</div>
                </div>
              ` : ''}
              ${t.audio_duration_s ? `
                <div>
                  <span style="color: var(--text-muted); font-size: 0.72rem; display: block;">🎙️ Duração do Áudio:</span>
                  <div>${Math.round(t.audio_duration_s)}s</div>
                </div>
              ` : ''}
            </div>

            <!-- Caixa de Transcrição / Mensagem Original -->
            <div class="task-original-box">
              <div class="task-original-header">
                <span>📜 <b>Transcrição / Mensagem Original do Gatilho:</b></span>
                <button class="btn btn-secondary btn-xs" type="button" onclick="copyTaskOriginalText('${t.id}')" title="Copiar transcrição completa">
                  📋 Copiar
                </button>
              </div>
              <p class="task-original-text" id="task-text-${t.id}">"${t.revised_text || t.raw_text || t.source_text_snippet || 'Texto não disponível'}"</p>
            </div>

            ${t.message_summary ? `
              <div class="task-summary-callout">
                💡 <b>Resumo Cognitivo da Conversa:</b> ${t.message_summary}
              </div>
            ` : ''}
          </div>
        </div>

        <!-- Caixa de Anotações & Observações Futuras -->
        <div class="task-notes-section">
          <div class="task-notes-header">
            <span>📝 <b>Anotações & Observações:</b></span>
            ${t.notes ? '<span style="color: #10b981; font-size: 0.72rem;">● Anotação salva</span>' : '<span style="font-size: 0.72rem;">Sem anotações</span>'}
          </div>
          <textarea class="task-notes-textarea" id="task-notes-${t.id}" placeholder="Escreva observações, acompanhamentos ou decisões para conferir no futuro...">${t.notes || ''}</textarea>
          <div class="task-notes-actions">
            <button class="btn btn-secondary btn-sm" onclick="saveTaskNotes('${t.id}')" title="Salvar anotação para conferência futura">
              💾 Salvar Anotação
            </button>
          </div>
        </div>

        <!-- Rodapé: Metadados e Ações -->
        <div class="task-footer-row">
          <div class="task-meta-items">
            <span class="badge" style="background: rgba(255,255,255,0.08); color: ${priorityColor}; font-weight: 700;">
              ● ${t.priority}
            </span>
            <span class="badge" style="background: rgba(255,255,255,0.06);">
              Status: ${t.status}
            </span>
            ${t.assignee ? `<span>🎯 <b>Responsável:</b> ${t.assignee}</span>` : ''}
            ${t.due_date ? `<span>📅 <b>Prazo:</b> ${t.due_date}</span>` : ''}
            ${t.created_at ? `<span>⏱️ ${typeof t.created_at === 'string' ? t.created_at.substring(0, 10) : ''}</span>` : ''}
          </div>

          <div style="display: flex; gap: 0.5rem; align-items: center;">
            ${waLink ? `
              <a href="${waLink}" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration: none; color: #25d366;" title="Falar com ${speakerName} no WhatsApp">
                💬 WhatsApp
              </a>
            ` : ''}

            ${isCancelled ? `
              <button class="btn btn-secondary btn-sm" style="color: var(--color-primary);" onclick="toggleTaskStatus('${t.id}', 'PENDING')" title="Restaurar tarefa para pendente">
                🔄 Restaurar Tarefa
              </button>
            ` : `
              <button class="btn btn-secondary btn-sm" onclick="toggleTaskStatus('${t.id}', '${isDone ? 'PENDING' : 'DONE'}')">
                ${isDone ? '🔄 Reabrir Tarefa' : '✅ Concluir Tarefa'}
              </button>
              <button class="btn btn-secondary btn-sm" style="color: var(--color-danger);" onclick="toggleTaskStatus('${t.id}', 'CANCELLED')" title="Ignorar esta tarefa">
                🚫 Ignorar
              </button>
            `}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function toggleTaskAccordion(taskId) {
  const body = document.getElementById(`task-accordion-body-${taskId}`);
  const chevron = document.getElementById(`chevron-${taskId}`);
  if (!body) return;

  const isHidden = body.style.display === 'none' || !body.style.display;
  body.style.display = isHidden ? 'flex' : 'none';
  if (chevron) {
    if (isHidden) {
      chevron.classList.add('expanded');
    } else {
      chevron.classList.remove('expanded');
    }
  }
}
window.toggleTaskAccordion = toggleTaskAccordion;

function copyTaskOriginalText(taskId) {
  const textEl = document.getElementById(`task-text-${taskId}`);
  if (!textEl) return;
  const raw = textEl.textContent.replace(/^"|"$/g, '').trim();
  navigator.clipboard.writeText(raw).then(() => {
    showToast('📋 Transcrição copiada para a área de transferência!');
  }).catch(err => {
    showToast('Erro ao copiar texto: ' + err, 'error');
  });
}
window.copyTaskOriginalText = copyTaskOriginalText;

function renderMessages() {
  if (!messagesContainer) return;

  const searchTerm = msgSearchInput ? msgSearchInput.value.toLowerCase().trim() : '';
  const filterIntent = msgFilterIntent ? msgFilterIntent.value.toUpperCase() : '';
  const filterSentiment = msgFilterSentiment ? msgFilterSentiment.value.toUpperCase() : '';

  const filtered = allMessages.filter(m => {
    const revised = (m.revised_text || '').toLowerCase();
    const raw = (m.raw_text || '').toLowerCase();
    const textValid = (m.revised_text || m.raw_text || '').trim();
    if (!textValid) return false;

    const speaker = (m.speaker || '').toLowerCase();
    const summary = (m.summary || '').toLowerCase();

    const matchSearch = !searchTerm || speaker.includes(searchTerm) || revised.includes(searchTerm) || raw.includes(searchTerm) || summary.includes(searchTerm);
    const matchIntent = !filterIntent || (m.intent && m.intent.toUpperCase() === filterIntent);
    const matchSentiment = !filterSentiment || (m.sentiment && m.sentiment.toUpperCase() === filterSentiment);

    return matchSearch && matchIntent && matchSentiment;
  });

  const totalFiltered = filtered.length;
  const paginationBar = document.getElementById('messages-pagination-bar');
  const paginationInfo = document.getElementById('messages-pagination-info');
  const btnPrev = document.getElementById('btn-msg-prev');
  const btnNext = document.getElementById('btn-msg-next');

  if (totalFiltered === 0) {
    if (paginationBar) paginationBar.style.display = 'none';
    messagesContainer.innerHTML = `
      <div class="empty-state" style="text-align: center; padding: 3rem; color: var(--text-muted);">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">Nenhuma mensagem encontrada</p>
        <small>As notas de voz enviadas no WhatsApp aparecerão aqui em tempo real com análise semântica e métricas.</small>
      </div>
    `;
    return;
  }

  const totalPages = Math.ceil(totalFiltered / messagesPageSize) || 1;
  if (messagesCurrentPage > totalPages) messagesCurrentPage = totalPages;
  if (messagesCurrentPage < 1) messagesCurrentPage = 1;

  const startIndex = (messagesCurrentPage - 1) * messagesPageSize;
  const pageItems = filtered.slice(startIndex, startIndex + messagesPageSize);

  if (paginationBar) paginationBar.style.display = 'flex';
  if (paginationInfo) {
    paginationInfo.innerHTML = `Página <strong>${messagesCurrentPage}</strong> de <strong>${totalPages}</strong> (Total: ${totalFiltered} conversas)`;
  }
  if (btnPrev) btnPrev.disabled = (messagesCurrentPage <= 1);
  if (btnNext) btnNext.disabled = (messagesCurrentPage >= totalPages);

  messagesContainer.innerHTML = pageItems.map(m => {
    const initials = (m.speaker || 'U').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
    const urgencyColor = m.urgency === 'URGENT' ? '#ef4444' : m.urgency === 'HIGH' ? '#f59e0b' : '#10b981';

    // Mapeamento de Sentimento
    const sentimentConfig = {
      'POSITIVE': { emoji: '😊', label: 'Positivo', color: '#10b981' },
      'CONFIDENT': { emoji: '💪', label: 'Confiante', color: '#06b6d4' },
      'NEUTRAL': { emoji: '😐', label: 'Neutro', color: '#94a3b8' },
      'URGENT': { emoji: '🚨', label: 'Urgente', color: '#ef4444' },
      'ANXIOUS': { emoji: '😰', label: 'Ansioso', color: '#f59e0b' },
      'FRUSTRATED': { emoji: '😤', label: 'Frustrado', color: '#e11d48' },
    };
    const sent = sentimentConfig[m.sentiment] || sentimentConfig['NEUTRAL'];

    // Prosódia Acústica
    const prosody = m.meta_info && m.meta_info.prosody;
    const prosodyHtml = prosody ? `
      <span class="badge ${prosody.tone_badge_class || 'badge-info'}" style="font-size: 0.72rem;" title="Prosódia Acústica: ${prosody.speech_rate_wps} pal/s • Pausas: ${Math.round(prosody.pause_ratio * 100)}% • Fala ativa: ${prosody.speech_duration_s}s">
        ${prosody.tone_label} (${prosody.speech_rate_wps} pal/s)
      </span>
    ` : '';

    // Telefone / WhatsApp
    let phoneClean = '';
    if (m.meta_info && m.meta_info.remoteJid) {
      phoneClean = m.meta_info.remoteJid.replace(/[^0-9]/g, '');
    } else if (m.speaker && /^\d+$/.test(m.speaker.replace(/[^0-9]/g, ''))) {
      phoneClean = m.speaker.replace(/[^0-9]/g, '');
    }
    const waLink = phoneClean.length >= 10 ? `https://wa.me/${phoneClean}` : null;

    // Tarefas
    const tasksHtml = (m.tasks && m.tasks.length > 0) ? `
      <div class="message-tasks-list">
        <div style="font-size: 0.8rem; font-weight: 600; color: var(--text-muted); margin-bottom: 0.2rem;">📋 Tarefas Acionáveis Extraídas:</div>
        ${m.tasks.map(t => `
          <div class="message-task-mini">
            <span style="display: flex; align-items: center; gap: 0.4rem;">
              <span style="color: ${t.priority === 'URGENT' ? '#ef4444' : t.priority === 'HIGH' ? '#f59e0b' : '#10b981'}; font-weight: 700;">●</span>
              <span>${t.title}</span>
              ${t.assignee ? `<small style="color: var(--text-muted);">(${t.assignee})</small>` : ''}
            </span>
            <span class="badge" style="font-size: 0.7rem; background: rgba(255,255,255,0.06);">${t.status}</span>
          </div>
        `).join('')}
      </div>
    ` : '';

    // Entidades
    const entitiesHtml = (m.entities && m.entities.length > 0) ? `
      <div class="message-entities-chips">
        ${m.entities.map(e => `
          <span class="message-chip" title="Categoria: ${e.category}">
            🏷️ ${e.name}
          </span>
        `).join('')}
      </div>
    ` : '';

    return `
      <div class="message-item" id="msg-card-${m.id}">
        <!-- Header -->
        <div class="message-header">
          <div class="message-speaker-info">
            <div class="message-avatar">${initials}</div>
            <div>
              <div class="message-speaker-name">
                <span>${m.speaker || 'Desconhecido'}</span>
                ${waLink ? `<a href="${waLink}" target="_blank" title="Abrir conversa no WhatsApp">💬 WhatsApp</a>` : ''}
              </div>
              <small style="color: var(--text-muted); font-size: 0.78rem;">${m.created_at || 'Data desconhecida'}</small>
            </div>
          </div>

          <div class="message-badges">
            <span class="badge badge-executive" style="font-size: 0.72rem;">${m.intent}</span>
            <span class="badge" style="font-size: 0.72rem; background: rgba(255,255,255,0.06); color: ${urgencyColor};">${m.urgency}</span>
            <span class="badge" style="font-size: 0.72rem; background: rgba(255,255,255,0.06); color: ${sent.color};" title="Score emocional: ${m.sentiment_score || 0.0}">
              ${sent.emoji} ${sent.label} (${m.sentiment_score > 0 ? '+' : ''}${m.sentiment_score || 0.0})
            </span>
            ${prosodyHtml}
          </div>
        </div>

        <!-- Resumo -->
        ${m.summary ? `<div class="message-summary">💡 <b>Resumo Executivo:</b> ${m.summary}</div>` : ''}

        <!-- Transcription Box (Abas Revisado vs Bruto) -->
        <div class="message-transcription-box">
          <div class="message-transcription-tabs">
            <button class="transcription-tab-btn active" id="btn-tab-revised-${m.id}" onclick="toggleTranscriptionTab('${m.id}', 'revised')">
              ✨ Texto Revisado (Gemini 3.1 Flash-Lite)
            </button>
            <button class="transcription-tab-btn" id="btn-tab-raw-${m.id}" onclick="toggleTranscriptionTab('${m.id}', 'raw')">
              🎙️ Transcrição Bruta (Whisper)
            </button>
          </div>

          <div class="message-text" id="text-revised-${m.id}">"${m.revised_text || m.raw_text || ''}"</div>
          <div class="message-raw-text" id="text-raw-${m.id}" style="display: none;">"${m.raw_text || m.revised_text || ''}"</div>
        </div>

        <!-- Tarefas Extraídas -->
        ${tasksHtml}

        <!-- Entidades Identificadas -->
        ${entitiesHtml}

        <!-- Rodapé e Ações -->
        <div class="message-meta-bar">
          <div style="display: flex; gap: 0.75rem; align-items: center;">
            ${m.audio_duration_s ? `<span>⏱️ <b>${m.audio_duration_s}s</b> de áudio</span>` : ''}
            <span>🤖 <b>Gemini 3.1 Flash-Lite</b></span>
          </div>

          <div style="display: flex; gap: 0.5rem; align-items: center;">
            <button class="btn btn-secondary btn-sm" onclick="copyMessageText('${encodeURIComponent(m.revised_text || m.raw_text || '')}')" title="Copiar texto revisado">
              📋 Copiar
            </button>
            ${waLink ? `
              <a href="${waLink}" target="_blank" class="btn btn-secondary btn-sm" style="text-decoration: none;" title="Responder no WhatsApp">
                💬 Responder
              </a>
            ` : ''}
            <button class="btn btn-secondary btn-sm" style="color: var(--color-danger);" onclick="deleteMessage('${m.id}')" title="Excluir mensagem da memória">
              🗑️ Excluir
            </button>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Alterna entre abas de texto revisado e texto bruto no feed
window.toggleTranscriptionTab = function(msgId, tabType) {
  const btnRevised = document.getElementById(`btn-tab-revised-${msgId}`);
  const btnRaw = document.getElementById(`btn-tab-raw-${msgId}`);
  const textRevised = document.getElementById(`text-revised-${msgId}`);
  const textRaw = document.getElementById(`text-raw-${msgId}`);

  if (!btnRevised || !btnRaw || !textRevised || !textRaw) return;

  if (tabType === 'revised') {
    btnRevised.classList.add('active');
    btnRaw.classList.remove('active');
    textRevised.style.display = 'block';
    textRaw.style.display = 'none';
  } else {
    btnRaw.classList.add('active');
    btnRevised.classList.remove('active');
    textRaw.style.display = 'block';
    textRevised.style.display = 'none';
  }
};

// Copia o texto revisado para a área de transferência
window.copyMessageText = function(encodedText) {
  const text = decodeURIComponent(encodedText);
  navigator.clipboard.writeText(text).then(() => {
    showToast('Texto copiado para a área de transferência!');
  }).catch(err => {
    console.error('Erro ao copiar:', err);
    showToast('Erro ao copiar texto', true);
  });
};

// Exclui uma mensagem da memória
window.deleteMessage = async function(messageId) {
  if (!confirm('Deseja realmente excluir esta mensagem da memória? Esta ação não pode ser desfeita.')) {
    return;
  }

  try {
    const res = await fetch(`/api/v1/memory/messages/${messageId}`, {
      method: 'DELETE'
    });
    if (res.ok || res.status === 204) {
      showToast('Mensagem excluída com sucesso!');
      await loadMessages();
      await loadStats();
    } else {
      showToast('Erro ao excluir mensagem', true);
    }
  } catch (err) {
    console.error('Erro ao excluir mensagem:', err);
    showToast('Falha na comunicação com o servidor', true);
  }
};

function editTerm(idOrTerm) {
  const termObj = allDictionaryTerms.find(t => t.id === idOrTerm || t.term === idOrTerm);
  if (!termObj) return;

  const modalTitle = document.getElementById('modal-term-title');
  if (modalTitle) modalTitle.textContent = `Editar Termo: ${termObj.term}`;

  const inputName = document.getElementById('term-name');
  const inputCategory = document.getElementById('term-category');
  const inputExpansion = document.getElementById('term-expansion');
  const inputVariations = document.getElementById('term-variations');
  const inputDesc = document.getElementById('term-description');

  if (inputName) inputName.value = termObj.term || '';
  if (inputCategory) inputCategory.value = termObj.category || 'AGRONEGOCIO';
  if (inputExpansion) inputExpansion.value = termObj.expansion || '';
  if (inputVariations) inputVariations.value = (termObj.phonetic_variations || []).join(', ');
  if (inputDesc) inputDesc.value = termObj.description || '';

  if (modalTerm) modalTerm.classList.add('active');
}
window.editTerm = editTerm;

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

  const totalFiltered = filtered.length;
  const paginationBar = document.getElementById('dict-pagination-bar');
  const paginationInfo = document.getElementById('dict-pagination-info');
  const btnPrev = document.getElementById('btn-dict-prev');
  const btnNext = document.getElementById('btn-dict-next');

  if (totalFiltered === 0) {
    if (paginationBar) paginationBar.style.display = 'none';
    dictionaryContainer.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: var(--text-muted);">
        <p style="font-size: 1.2rem; margin-bottom: 0.5rem;">Nenhum termo encontrado</p>
      </div>
    `;
    return;
  }

  const totalPages = Math.ceil(totalFiltered / dictPageSize) || 1;
  if (dictCurrentPage > totalPages) dictCurrentPage = totalPages;
  if (dictCurrentPage < 1) dictCurrentPage = 1;

  const startIndex = (dictCurrentPage - 1) * dictPageSize;
  const displayedTerms = filtered.slice(startIndex, startIndex + dictPageSize);

  if (paginationBar) paginationBar.style.display = 'flex';
  if (paginationInfo) {
    paginationInfo.innerHTML = `Página <strong>${dictCurrentPage}</strong> de <strong>${totalPages}</strong> (Total: ${totalFiltered} termos)`;
  }
  if (btnPrev) btnPrev.disabled = (dictCurrentPage <= 1);
  if (btnNext) btnNext.disabled = (dictCurrentPage >= totalPages);

  dictionaryContainer.innerHTML = displayedTerms.map(t => {
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

        <div style="display: flex; justify-content: flex-end; gap: 0.5rem; margin-top: auto; padding-top: 0.5rem; border-top: 1px solid var(--border-subtle);">
          <button class="btn btn-secondary btn-sm" onclick="editTerm('${t.id || t.term}')" title="Editar este termo">✏️ Editar</button>
          <button class="btn btn-danger btn-sm" onclick="deleteTerm('${t.id || t.term}')">Remover</button>
        </div>
      </div>
    `;
  }).join('');
}

let allLexicalCandidates = [];

async function loadCandidates() {
  try {
    const res = await fetch('/api/v1/dictionary/candidates?status=PENDING');
    if (res.ok) {
      allLexicalCandidates = await res.json();
      renderCandidates();
    }
  } catch (err) {
    console.error('Erro ao carregar candidatos léxicos:', err);
  }
}

function renderCandidates() {
  const container = document.getElementById('candidates-container');
  const badge = document.getElementById('candidates-count-badge');
  if (!container) return;

  if (badge) {
    badge.textContent = `${allLexicalCandidates.length} pendente(s)`;
    badge.className = allLexicalCandidates.length > 0 ? 'badge badge-warning' : 'badge badge-success';
  }

  if (allLexicalCandidates.length === 0) {
    container.innerHTML = `
      <div style="width: 100%; color: var(--text-muted); font-size: 0.85rem; padding: 0.5rem 0;">
        ✨ Nenhum termo ambíguo pendente no buffer! A IA compreendeu todos os áudios recentes com clareza.
      </div>
    `;
    return;
  }

  container.innerHTML = allLexicalCandidates.map(c => `
    <div style="background: rgba(255,255,255,0.03); border: 1px dashed var(--border-color); border-radius: 8px; padding: 0.75rem 1rem; flex: 1 1 calc(33.333% - 0.75rem); min-width: 250px; display: flex; flex-direction: column; justify-content: space-between; gap: 0.5rem;">
      <div>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <strong style="color: var(--accent-color); font-size: 0.95rem;">"${c.raw_term}"</strong>
          <span class="badge" style="font-size: 0.7rem; background: rgba(245, 158, 11, 0.15); color: #f59e0b;">
            ${c.occurrence_count || 1}x ouvido
          </span>
        </div>
        ${c.suggested_term ? `<div style="font-size: 0.8rem; color: var(--text-main); margin-top: 0.2rem;">💡 Sugestão: <b>${c.suggested_term}</b></div>` : ''}
        ${c.context ? `<div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.3rem; font-style: italic;">"${c.context.substring(0, 80)}..."</div>` : ''}
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 0.4rem; margin-top: 0.4rem; padding-top: 0.4rem; border-top: 1px solid rgba(255,255,255,0.05);">
        <button class="btn btn-primary btn-sm" onclick="promoteCandidate('${c.id}', '${c.suggested_term || c.raw_term}', '${c.category || 'GERAL'}')" title="Promover imediatamente para o Dicionário Oficial">
          ✅ Promover
        </button>
        <button class="btn btn-secondary btn-sm" onclick="rejectCandidate('${c.id}')" title="Descartar este ruído">
          🗑️
        </button>
      </div>
    </div>
  `).join('');
}

async function triggerHarvest() {
  const btn = document.getElementById('btn-trigger-harvest');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Pescando...';
  }

  try {
    const res = await fetch('/api/v1/dictionary/harvest', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      if (data.promoted_terms_count > 0) {
        showToast(`🎣 Harvester finalizado! ${data.promoted_terms_count} novo(s) termo(s) incorporados ao Dicionário: ${data.promoted_terms.join(', ')}`);
      } else {
        showToast(`🎣 Harvester analisou ${data.total_candidates_analyzed} termos. Nenhum novo jargão pendente para promoção.`);
      }
      loadDictionary();
      loadCandidates();
    } else {
      showToast('Erro ao rodar Harvester', true);
    }
  } catch (err) {
    console.error('Erro no Harvester:', err);
    showToast('Erro ao comunicar com o Harvester', true);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🎣 Rodar Pesca (19h)';
    }
  }
}

async function promoteCandidate(candidateId, defaultTerm, category) {
  const termName = prompt('Confirme ou edite o termo canônico oficial:', defaultTerm || '');
  if (!termName) return;

  try {
    const res = await fetch(`/api/v1/dictionary/candidates/${candidateId}/promote?term_override=${encodeURIComponent(termName)}&category=${encodeURIComponent(category || 'GERAL')}`, {
      method: 'PATCH'
    });
    if (res.ok) {
      showToast(`Termo "${termName}" promovido com sucesso para o Dicionário Oficial!`);
      loadDictionary();
      loadCandidates();
    } else {
      showToast('Erro ao promover termo', true);
    }
  } catch (err) {
    console.error('Erro:', err);
  }
}

async function rejectCandidate(candidateId) {
  try {
    const res = await fetch(`/api/v1/dictionary/candidates/${candidateId}`, { method: 'DELETE' });
    if (res.ok || res.status === 204) {
      showToast('Candidato descartado.');
      loadCandidates();
    }
  } catch (err) {
    console.error('Erro:', err);
  }
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
  const contactId = document.getElementById('contact-id').value.trim();
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
    const isEditing = Boolean(contactId);
    const url = isEditing ? `/api/v1/contacts/${encodeURIComponent(contactId)}` : '/api/v1/contacts';
    const method = isEditing ? 'PATCH' : 'POST';

    const res = await fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    if (res.ok) {
      showToast(`Contato ${name} ${isEditing ? 'atualizado' : 'cadastrado'} e sincronizado na VPS!`);
      modalContact.classList.remove('active');
      document.getElementById('contact-id').value = '';
      loadContacts();
      loadStats();
      loadGraphData();
    } else {
      const errData = await res.json().catch(() => ({}));
      showToast(`Erro ao salvar contato: ${errData.detail || res.statusText}`, true);
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
      const label = newStatus === 'DONE' ? 'Concluída' : (newStatus === 'CANCELLED' ? 'Ignorada' : 'Pendente');
      showToast(`Tarefa marcada como ${label}!`);
      loadTasks();
    }
  } catch (err) {
    console.error('Erro ao atualizar tarefa:', err);
    showToast('Falha ao atualizar tarefa', true);
  }
}
window.toggleTaskStatus = toggleTaskStatus;

async function saveTaskNotes(taskId) {
  const textarea = document.getElementById(`task-notes-${taskId}`);
  if (!textarea) return;

  const notesText = textarea.value.trim();
  try {
    const res = await fetch(`/api/v1/memory/tasks/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ notes: notesText })
    });
    if (res.ok) {
      showToast('Anotação da tarefa salva com sucesso!');
      await loadTasks();
    } else {
      showToast('Erro ao salvar anotação da tarefa', true);
    }
  } catch (err) {
    console.error('Erro ao salvar anotação:', err);
    showToast('Falha na comunicação com o servidor', true);
  }
}
window.saveTaskNotes = saveTaskNotes;

// --- Live Hermes Query Testing ---

function setQuery(text) {
  const input = document.getElementById('query-input');
  if (input) {
    input.value = text;
    runHermesQuery();
  }
}
window.setQuery = setQuery;

function formatQueryAnswerMarkdown(text) {
  if (!text) return '';
  let formatted = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

  // Negrito **texto**
  formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  // Itálico *texto*
  formatted = formatted.replace(/\*(.*?)\*/g, '<em>$1</em>');
  // Itens de lista
  formatted = formatted.replace(/^\s*-\s+(.*)$/gm, '• $1');
  // Quebras de linha
  formatted = formatted.replace(/\n/g, '<br>');

  return formatted;
}

async function runHermesQuery() {
  const queryInput = document.getElementById('query-input');
  const btnRunQuery = document.getElementById('btn-run-query');
  const query = queryInput ? queryInput.value.trim() : '';
  if (!query) return;

  const resultBox = document.getElementById('query-result-box');
  const answerEl = document.getElementById('query-answer');
  const metaEl = document.getElementById('query-meta');
  const timeEl = document.getElementById('query-time');

  if (btnRunQuery) {
    btnRunQuery.disabled = true;
    btnRunQuery.textContent = '⚡ Consultando...';
  }

  if (resultBox) resultBox.style.display = 'block';
  if (answerEl) answerEl.innerHTML = '<div style="color: #38bdf8;">🧠 Processando com Gemini 3.1 Flash Lite + RAG Híbrido...</div>';
  if (timeEl) timeEl.textContent = 'Consultando...';
  if (metaEl) metaEl.innerHTML = '';

  const startTime = performance.now();

  try {
    const res = await fetch('/api/v1/memory/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, top_k: 5, include_graph: true })
    });

    const elapsed = Math.round(performance.now() - startTime);
    if (timeEl) timeEl.textContent = `${elapsed}ms`;

    if (res.ok) {
      const data = await res.json();
      if (answerEl) {
        answerEl.innerHTML = formatQueryAnswerMarkdown(data.answer) || 'Sem resposta gerada.';
      }

      const mentions = (data.entities_mentioned || []).map(e => `<span class="message-chip" style="margin-right: 4px;">🏷️ ${e}</span>`).join('');
      if (metaEl) {
        metaEl.innerHTML = `
          <div style="margin-bottom: 0.4rem;"><strong>Entidades do Grafo Mencionadas:</strong> ${mentions || '<span style="color:var(--text-muted)">Nenhuma</span>'}</div>
          <div><strong>Fontes Citadas:</strong> ${data.sources ? data.sources.length : 0} memórias registradas</div>
        `;
      }
    } else {
      if (answerEl) answerEl.innerHTML = '<span style="color: #ef4444;">❌ Erro ao consultar a API do Hermes.</span>';
    }
  } catch (err) {
    if (answerEl) answerEl.innerHTML = `<span style="color: #ef4444;">❌ Erro de conexão: ${err.message}</span>`;
  } finally {
    if (btnRunQuery) {
      btnRunQuery.disabled = false;
      btnRunQuery.textContent = '⚡ Perguntar';
    }
  }
}
window.runHermesQuery = runHermesQuery;

// --- Subsistema de Sentimentos & Série Temporal (Erato) ---

async function loadDailySentiments(targetDate = 'all') {
  const container = document.getElementById('sentiment-daily-container');
  const badge = document.getElementById('sentiment-day-badge');
  if (!container) return;

  const isAll = !targetDate || targetDate === 'all' || targetDate === 'todos';
  const url = isAll ? '/api/v1/memory/sentiment/daily?date=all&days=30' : `/api/v1/memory/sentiment/daily?date=${targetDate}`;
  
  if (badge) {
    badge.textContent = isAll ? 'Últimos 30 Dias' : targetDate;
  }

  container.innerHTML = `
    <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--text-muted);">
      <p>⏳ Carregando termômetro e análise de sentimentos...</p>
    </div>
  `;

  try {
    const res = await fetch(url);
    if (res.ok) {
      const snapshots = await res.json();
      renderDailySentiments(snapshots, isAll ? 'all' : targetDate);
    } else {
      container.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 2.5rem; color: var(--text-muted);">
          <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">Falha ao carregar dados de sentimentos.</p>
        </div>
      `;
    }
  } catch (err) {
    console.error('Erro ao carregar sentimentos diários:', err);
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 2.5rem; color: var(--text-muted);">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">Erro de conexão ao carregar Erato.</p>
      </div>
    `;
  }
}

async function collectSentiments(targetDate = '') {
  try {
    const dateParam = (targetDate && targetDate !== 'all') ? `?date=${targetDate}` : '';
    const res = await fetch(`/api/v1/memory/sentiment/collect${dateParam}`, { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      showToast(`Consolidação concluída! ${data.total_people} pessoa(s) e ${data.total_interactions} interação(ões).`);
      loadDailySentiments(targetDate || 'all');
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
    const periodLabel = (targetDate === 'all' || !targetDate) ? 'os últimos 30 dias' : targetDate;
    container.innerHTML = `
      <div class="empty-state" style="grid-column: 1 / -1; text-align: center; padding: 2.5rem; color: var(--text-muted);">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">Nenhuma interação registrada para ${periodLabel}</p>
        <small>Clique em "Consolidar Hoje" ou envie mensagens de voz no WhatsApp para alimentar o termômetro.</small>
      </div>
    `;
    return;
  }

  // Ordenação OBRIGATÓRIA: Mais interações primeiro
  const sorted = [...snapshots].sort((a, b) => (b.interactions_count || 0) - (a.interactions_count || 0));

  container.innerHTML = sorted.map((s, idx) => {
    const sInfo = getSentimentInfo(s.dominant_sentiment);
    const badgeClass = getRoleBadgeClass(s.role);
    const roleLabel = getRoleLabel(s.role);
    const scoreFormatted = (s.avg_sentiment_score > 0 ? '+' : '') + s.avg_sentiment_score.toFixed(2);
    const initials = getInitials(s.speaker);
    const medal = idx === 0 ? '🥇 ' : idx === 1 ? '🥈 ' : idx === 2 ? '🥉 ' : '';

    const highlightsHtml = (s.highlights || []).map(h => `
      <div style="font-size: 0.75rem; color: var(--text-muted); background: rgba(255,255,255,0.03); padding: 0.25rem 0.4rem; border-radius: 4px; margin-top: 0.2rem;">
        ${h}
      </div>
    `).join('');

    const periodText = (targetDate === 'all' || !targetDate) ? 'nos últimos 30 dias' : 'nesta data';

    return `
      <div class="contact-card" style="cursor: pointer;" onclick="selectSpeakerForTimeline('${s.speaker}')">
        <div class="contact-header">
          <div class="contact-avatar">${initials}</div>
          <div class="contact-title-group">
            <div class="contact-name">${medal}${s.speaker}</div>
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
            📊 <b>${s.interactions_count}</b> interações ${periodText}:
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
    const res = await fetch('/api/v1/memory/sentiment/daily?date=all&days=30');
    if (res.ok) {
      const speakers = await res.json();
      if (!speakers || speakers.length === 0) {
        select.innerHTML = '<option value="">Nenhuma pessoa com interação nos últimos 30 dias</option>';
        return;
      }

      // Ordena por interações decrescente
      speakers.sort((a, b) => (b.interactions_count || 0) - (a.interactions_count || 0));

      select.innerHTML = '<option value="">Selecione uma pessoa (ordenada por mais interações)...</option>' +
        speakers.map(s => `<option value="${s.speaker}">${s.speaker} (${s.interactions_count} msgs • ${s.dominant_sentiment})</option>`).join('');
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

// ==========================================================================
// Analytics & Dashboard Executivo (Chart.js & NLP WordMap)
// ==========================================================================

let chartTimeseriesInstance = null;
let chartSendersInstance = null;
let chartSizeInstance = null;

async function loadAnalyticsDashboard() {
  const periodSelect = document.getElementById('analytics-period');
  const groupSelect = document.getElementById('analytics-groupby');

  const period = periodSelect ? periodSelect.value : '30d';
  const groupBy = groupSelect ? groupSelect.value : 'day';

  try {
    const res = await fetch(`/api/v1/analytics/dashboard?period=${period}&group_by=${groupBy}`);
    if (!res.ok) throw new Error('Falha na requisição analítica');

    const data = await res.json();
    renderHeroKPIs(data);
    renderTimeseriesChart(data);
    renderTopSendersChart(data);
    renderMessageSizeChart(data);
    renderHeatmapGrid(data.heatmap || []);
    renderWordMapCloud(data.wordmap || []);

    const summaryEl = document.getElementById('analytics-summary-text');
    if (summaryEl) {
      summaryEl.textContent = data.summary_text || 'Sem dados suficientes para gerar resumo.';
    }
  } catch (err) {
    console.error('Erro ao carregar Dashboard Analítico:', err);
    showToast('Erro ao carregar métricas analíticas', true);
  }
}
window.loadAnalyticsDashboard = loadAnalyticsDashboard;

function renderHeroKPIs(data) {
  const setKpi = (idVal, idSub, kpi) => {
    const valEl = document.getElementById(idVal);
    const subEl = document.getElementById(idSub);
    if (!valEl || !subEl || !kpi) return;

    valEl.textContent = kpi.value !== undefined ? kpi.value : '--';
    
    let trendBadge = '';
    if (kpi.trend_pct !== null && kpi.trend_pct !== undefined) {
      const isUp = kpi.trend_direction === 'UP';
      const color = isUp ? '#10b981' : '#ef4444';
      const arrow = isUp ? '↑' : '↓';
      trendBadge = ` <span style="color: ${color}; font-weight: 700;">${arrow} ${Math.abs(kpi.trend_pct)}%</span>`;
    }
    subEl.innerHTML = (kpi.subtitle || '') + trendBadge;
  };

  setKpi('kpi-val-senders', 'kpi-sub-senders', data.kpi_unique_senders);
  setKpi('kpi-val-messages', 'kpi-sub-messages', data.kpi_total_messages);
  setKpi('kpi-val-duration', 'kpi-sub-duration', data.kpi_audio_duration);
  setKpi('kpi-val-actionability', 'kpi-sub-actionability', data.kpi_actionability_rate);
  setKpi('kpi-val-sentiment', 'kpi-sub-sentiment', data.kpi_sentiment_health);
}

function renderTimeseriesChart(data) {
  const canvas = document.getElementById('chart-analytics-timeseries');
  if (!canvas || typeof Chart === 'undefined') return;

  if (chartTimeseriesInstance) {
    chartTimeseriesInstance.destroy();
  }

  const labels = (data.timeseries || []).map(p => p.period_label);
  const sendersData = (data.timeseries || []).map(p => p.unique_senders);
  const messagesData = (data.timeseries || []).map(p => p.total_messages);
  const audioData = (data.timeseries || []).map(p => p.audio_messages);

  const ctx = canvas.getContext('2d');
  chartTimeseriesInstance = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Total Mensagens',
          data: messagesData,
          borderColor: '#0ea5e9',
          backgroundColor: 'rgba(14, 165, 233, 0.15)',
          fill: true,
          tension: 0.35,
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: '#0ea5e9',
        },
        {
          label: 'Áudios (Voz)',
          data: audioData,
          borderColor: '#10b981',
          backgroundColor: 'transparent',
          borderDash: [4, 4],
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: '#10b981',
        },
        {
          label: 'Pessoas Distintas',
          data: sendersData,
          borderColor: '#f59e0b',
          backgroundColor: 'transparent',
          tension: 0.3,
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: '#f59e0b',
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } }
        },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#38bdf8',
          bodyColor: '#f8fafc',
          borderColor: '#334155',
          borderWidth: 1
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { size: 11 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { size: 11 }, precision: 0 }
        }
      }
    }
  });
}

function renderTopSendersChart(data) {
  const canvas = document.getElementById('chart-analytics-senders');
  if (!canvas || typeof Chart === 'undefined') return;

  if (chartSendersInstance) {
    chartSendersInstance.destroy();
  }

  const senders = (data.top_senders || []).slice(0, 10);
  const labels = senders.map(s => s.speaker);
  const msgCounts = senders.map(s => s.total_messages);
  const audioCounts = senders.map(s => s.audio_count);

  const ctx = canvas.getContext('2d');
  chartSendersInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Total de Mensagens',
          data: msgCounts,
          backgroundColor: 'rgba(14, 165, 233, 0.75)',
          borderRadius: 4,
        },
        {
          label: 'Mensagens de Áudio',
          data: audioCounts,
          backgroundColor: 'rgba(16, 185, 129, 0.75)',
          borderRadius: 4,
        }
      ]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } }
        },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#38bdf8',
          bodyColor: '#f8fafc',
          borderColor: '#334155',
          borderWidth: 1,
          callbacks: {
            afterBody: function(items) {
              const idx = items[0].dataIndex;
              const sender = senders[idx];
              if (!sender) return '';
              const roleLabel = sender.role ? `\nCargo: ${sender.role}` : '';
              const tasksLabel = `\nTarefas geradas: ${sender.tasks_count}`;
              const durLabel = sender.total_duration_s ? `\nDuração áudios: ${Math.round(sender.total_duration_s)}s` : '';
              return roleLabel + tasksLabel + durLabel;
            }
          }
        }
      },
      scales: {
        x: {
          beginAtZero: true,
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { size: 11 }, precision: 0 }
        },
        y: {
          grid: { display: false },
          ticks: { color: '#f8fafc', font: { size: 11, weight: '600' } }
        }
      }
    }
  });
}

function renderMessageSizeChart(data) {
  const canvas = document.getElementById('chart-analytics-size');
  if (!canvas || typeof Chart === 'undefined') return;

  if (chartSizeInstance) {
    chartSizeInstance.destroy();
  }

  const labels = (data.timeseries || []).map(p => p.period_label);
  const audioDuration = (data.timeseries || []).map(p => p.avg_audio_duration_s);
  const textChars = (data.timeseries || []).map(p => p.avg_chars);

  const ctx = canvas.getContext('2d');
  chartSizeInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        {
          type: 'bar',
          label: 'Duração Média Áudio (seg)',
          data: audioDuration,
          backgroundColor: 'rgba(245, 158, 11, 0.65)',
          yAxisID: 'yAudio',
          borderRadius: 4,
        },
        {
          type: 'line',
          label: 'Tamanho Médio Texto (caracteres)',
          data: textChars,
          borderColor: '#a855f7',
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 4,
          pointBackgroundColor: '#a855f7',
          yAxisID: 'yText',
          tension: 0.3,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } }
        },
        tooltip: {
          backgroundColor: '#0f172a',
          titleColor: '#38bdf8',
          bodyColor: '#f8fafc',
          borderColor: '#334155',
          borderWidth: 1
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { size: 11 } }
        },
        yAudio: {
          type: 'linear',
          position: 'left',
          beginAtZero: true,
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: {
            color: '#f59e0b',
            callback: v => `${v}s`
          }
        },
        yText: {
          type: 'linear',
          position: 'right',
          beginAtZero: true,
          grid: { display: false },
          ticks: {
            color: '#a855f7',
            callback: v => `${v} char`
          }
        }
      }
    }
  });
}

function renderHeatmapGrid(cells) {
  const container = document.getElementById('analytics-heatmap-container');
  if (!container) return;

  if (!cells || cells.length === 0) {
    container.innerHTML = '<p class="text-muted" style="text-align:center; padding: 2rem;">Sem dados de horário registrados no período.</p>';
    return;
  }

  const maxCount = Math.max(...cells.map(c => c.count), 1);
  const dayNames = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo'];

  // Agrupa por dia
  const byDay = {};
  cells.forEach(c => {
    if (!byDay[c.day_of_week]) byDay[c.day_of_week] = [];
    byDay[c.day_of_week].push(c);
  });

  // Cabeçalho de horas
  let hoursHeader = '<div class="heatmap-hours-header">';
  for (let h = 0; h < 24; h += 2) {
    hoursHeader += `<div class="heatmap-hour-label" style="flex: 2;">${h}h</div>`;
  }
  hoursHeader += '</div>';

  let rowsHtml = '';
  for (let d = 0; d < 7; d++) {
    const dayCells = byDay[d] || [];
    dayCells.sort((a, b) => a.hour - b.hour);

    let cellsHtml = '';
    dayCells.forEach(cell => {
      const opacity = cell.count === 0 ? 0.04 : Math.min(0.2 + (cell.count / maxCount) * 0.8, 1.0);
      const bg = cell.count === 0 ? 'rgba(255,255,255,0.03)' : `rgba(14, 165, 233, ${opacity})`;
      const title = `${dayNames[d]} às ${cell.hour}:00 - ${cell.count} mensagem(ns)`;
      cellsHtml += `<div class="heatmap-cell" style="background: ${bg};" title="${title}"></div>`;
    });

    rowsHtml += `
      <div class="heatmap-row">
        <div class="heatmap-day-label">${dayNames[d].substring(0, 3)}</div>
        ${cellsHtml}
      </div>
    `;
  }

  container.innerHTML = hoursHeader + rowsHtml;
}

function openWordMapModal(itemEncoded) {
  try {
    const item = JSON.parse(decodeURIComponent(itemEncoded));
    selectedWordMapTopic = item;

    const modal = document.getElementById('modal-wordmap-action');
    const titleEl = document.getElementById('wordmap-modal-title');
    const metaEl = document.getElementById('wordmap-modal-meta');
    const contextEl = document.getElementById('wordmap-modal-context');

    if (!modal) return;

    if (titleEl) {
      titleEl.innerHTML = `${item.is_compound ? '🔗 ' : '🏷️ '} Tópico: <b>${item.word}</b>`;
    }

    if (metaEl) {
      metaEl.innerHTML = `
        <span><b>Categoria:</b> ${item.category}</span> • 
        <span><b>Ocorrências:</b> ${item.count} menção(ões)</span>
        ${item.is_compound ? ' • <span class="badge badge-info" style="font-size: 0.72rem;">Sintagma Composto</span>' : ''}
      `;
    }

    if (contextEl) {
      contextEl.innerHTML = item.sample_context
        ? `"${item.sample_context}..."`
        : 'Nenhum trecho textual específico isolado.';
    }

    modal.classList.add('active');
  } catch (err) {
    console.error('Erro ao abrir modal do WordMap:', err);
  }
}
window.openWordMapModal = openWordMapModal;

function renderWordMapCloud(wordItems) {
  const container = document.getElementById('analytics-wordmap-container');
  const countTag = document.getElementById('wordmap-count-tag');
  if (!container) return;

  if (wordItems) {
    currentWordMapItems = wordItems;
  }

  const xmlGarbageRegex = /^(mxcell|parent|mxgeometry|vertex|style|geometry|target|source|edge|value|points|array|root|model|diagram|page|grid|xml|html|http|https|drawio|node|label|width|height|rel|true|false|null|undefined|none|nan|xmlns|doctype|svg|fill|stroke)$/i;

  // Filtra itens vazios ou ruídos residuais de diagramas/XML
  let validItems = (currentWordMapItems || []).filter(item => {
    if (!item.word || item.word.trim().length < 3) return false;
    if (xmlGarbageRegex.test(item.word.trim())) return false;
    return true;
  });

  // Aplica filtro do pilar selecionado
  let displayed = validItems;
  if (currentWordMapFilter === 'COMPOUND') {
    displayed = validItems.filter(item => item.is_compound);
  } else if (currentWordMapFilter !== 'ALL') {
    displayed = validItems.filter(item => item.category === currentWordMapFilter);
  }

  if (countTag) {
    countTag.textContent = `${displayed.length} Tópico(s) Exibido(s)`;
  }

  if (displayed.length === 0) {
    container.innerHTML = `<p class="text-muted" style="text-align:center; padding: 2rem;">Nenhum termo encontrado para o filtro <strong>${currentWordMapFilter}</strong> no período.</p>`;
    return;
  }

  const categoryStyles = {
    'GARGALOS': 'legend-gargalos',
    'AGRONEGOCIO': 'legend-agronegocio',
    'ZOOTECNIA': 'legend-zootecnia',
    'LOGISTICA': 'legend-logistica',
    'GESTAO': 'legend-gestao',
    'SISTEMAS': 'legend-sistemas',
    'TECNOLOGIA': 'legend-tecnologia',
    'PESSOAL': 'legend-pessoal',
    'OPERACOES': 'legend-operacoes',
    'TEMAS': 'legend-temas',
  };

  container.innerHTML = displayed.map(item => {
    const chipClass = categoryStyles[item.category] || 'legend-temas';
    // Tamanho proporcional entre 0.85rem e 1.70rem
    const fontSize = 0.85 + (item.weight_pct / 100) * 0.85;
    const compoundBadge = item.is_compound ? '<span style="font-size: 0.8em; opacity: 0.9;">🔗</span>' : '';
    const itemEncoded = encodeURIComponent(JSON.stringify(item));

    return `
      <span class="word-cloud-tag ${chipClass} ${item.is_compound ? 'is-compound' : ''}" 
            style="font-size: ${fontSize.toFixed(2)}rem;" 
            title="Clique para ver ações • Termo: '${item.word}' • ${item.category} • ${item.count} menções"
            onclick="openWordMapModal('${itemEncoded}')">
        ${compoundBadge}
        <span>${item.word}</span>
        <span class="word-tag-count">${item.count}</span>
      </span>
    `;
  }).join('');
}
