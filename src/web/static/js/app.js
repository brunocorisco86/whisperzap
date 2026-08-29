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
let tasksCurrentPage = 1;
let tasksPageSize = 10;
let tasksViewMode = 'active'; // 'active', 'vault', 'garden', 'radar'
let procrastinationRadarChart = null;
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
const countVaultTasksEl = document.getElementById('count-vault-tasks');
const statGraphNodesEl = document.getElementById('stat-graph-nodes');

const contactSearchInput = document.getElementById('contact-search');
const contactFilterRole = document.getElementById('contact-filter-role');
const contactFilterPeriod = document.getElementById('contact-filter-period');
const dictSearchInput = document.getElementById('dict-search');
const dictFilterCategory = document.getElementById('dict-filter-category');
const tasksSearchInput = document.getElementById('tasks-search');
const tasksFilterSpeaker = document.getElementById('tasks-filter-speaker');
const tasksFilterNature = document.getElementById('tasks-filter-nature');
const tasksFilterStatus = document.getElementById('tasks-filter-status');
const tasksFilterPriority = document.getElementById('tasks-filter-priority');
const msgSearchInput = document.getElementById('msg-search');
const msgFilterOrigin = document.getElementById('msg-filter-origin');
const msgFilterIntent = document.getElementById('msg-filter-intent');
const msgFilterSentiment = document.getElementById('msg-filter-sentiment');
const msgFilterProsody = document.getElementById('msg-filter-prosody');
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

// Tabs & State Persistence
const ACTIVE_MUSA_STORAGE_KEY = 'hermes_active_musa';

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    
    btn.classList.add('active');
    const targetId = btn.dataset.tab;
    const targetContent = document.getElementById(targetId);
    if (targetContent) targetContent.classList.add('active');

    try {
      localStorage.setItem(ACTIVE_MUSA_STORAGE_KEY, targetId);
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, '', '#' + targetId);
      }
    } catch (e) {}

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
    } else if (targetId === 'tab-contacts') {
      loadContacts();
    }
  });
});

function activateTab(tabId) {
  if (!tabId) return;
  const cleanId = tabId.replace('#', '');
  const btn = document.querySelector(`.tab-btn[data-tab="${cleanId}"]`);
  if (btn) btn.click();
}
window.activateTab = activateTab;

window.addEventListener('hashchange', () => {
  const targetId = window.location.hash.replace('#', '');
  if (targetId) activateTab(targetId);
});

// --- Authentication Management (WhisperZap Session & Token) ---
const AUTH_TOKEN_KEY = 'whisperzap_auth_token';

async function checkAuthStatus() {
  const overlay = document.getElementById('auth-overlay');
  const token = localStorage.getItem(AUTH_TOKEN_KEY) || '';

  try {
    const res = await fetch('/api/auth/check', {
      headers: { 'X-Dashboard-Token': token }
    });
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated) {
        if (overlay) overlay.style.display = 'none';
        return true;
      }
    }
  } catch (err) {
    console.warn('Verificação de autenticação falhou:', err);
  }

  // Se não autenticado, exibe tela de login
  if (overlay) {
    overlay.style.display = 'flex';
    const input = document.getElementById('auth-password-input');
    if (input) setTimeout(() => input.focus(), 100);
  }
  return false;
}

async function handleAuthLogin() {
  const input = document.getElementById('auth-password-input');
  const errorMsg = document.getElementById('auth-error-msg');
  const overlay = document.getElementById('auth-overlay');
  const btn = document.getElementById('btn-auth-submit');

  const password = input ? input.value.trim() : '';
  if (!password) {
    if (errorMsg) {
      errorMsg.textContent = '❌ Por favor, digite a senha.';
      errorMsg.style.display = 'block';
    }
    return;
  }

  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Verificando...';
  }

  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password })
    });

    if (res.ok) {
      const data = await res.json();
      localStorage.setItem(AUTH_TOKEN_KEY, data.token || '');
      if (overlay) overlay.style.display = 'none';
      if (errorMsg) errorMsg.style.display = 'none';
      showToast('✅ Acesso autorizado!');

      // Carrega os dados após login bem-sucedido
      loadStats();
      loadContacts();
      loadDictionary();
      loadGraphData();
    } else {
      if (errorMsg) {
        errorMsg.textContent = '❌ Senha incorreta. Tente novamente.';
        errorMsg.style.display = 'block';
      }
      if (input) {
        input.value = '';
        input.focus();
      }
    }
  } catch (err) {
    if (errorMsg) {
      errorMsg.textContent = '❌ Erro ao conectar ao servidor: ' + err.message;
      errorMsg.style.display = 'block';
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Entrar ➔';
    }
  }
}

async function handleAuthLogout() {
  localStorage.removeItem(AUTH_TOKEN_KEY);
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch (e) {
    // ignore
  }
  const overlay = document.getElementById('auth-overlay');
  if (overlay) {
    overlay.style.display = 'flex';
    const input = document.getElementById('auth-password-input');
    if (input) {
      input.value = '';
      input.focus();
    }
  }
  showToast('Sessão encerrada.');
}

window.handleAuthLogin = handleAuthLogin;
window.handleAuthLogout = handleAuthLogout;
window.checkAuthStatus = checkAuthStatus;

// Init
document.addEventListener('DOMContentLoaded', async () => {
  const isAuthenticated = await checkAuthStatus();
  if (isAuthenticated) {
    // Restaura imediatamente a musa ativa anterior (via URL hash ou localStorage)
    const savedMusa = window.location.hash.replace('#', '') || localStorage.getItem(ACTIVE_MUSA_STORAGE_KEY) || 'tab-contacts';
    if (savedMusa && savedMusa !== 'tab-contacts') {
      activateTab(savedMusa);
    }
    loadStats();
    loadContacts();
    loadDictionary();
    loadGraphData();
  }

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

  if (tasksSearchInput) tasksSearchInput.addEventListener('input', () => { tasksCurrentPage = 1; renderTasks(); });
  if (tasksFilterSpeaker) tasksFilterSpeaker.addEventListener('change', () => { tasksCurrentPage = 1; renderTasks(); });
  if (tasksFilterNature) tasksFilterNature.addEventListener('change', () => { tasksCurrentPage = 1; renderTasks(); });
  if (tasksFilterStatus) tasksFilterStatus.addEventListener('change', () => { tasksCurrentPage = 1; renderTasks(); });
  if (tasksFilterPriority) tasksFilterPriority.addEventListener('change', () => { tasksCurrentPage = 1; renderTasks(); });

  const tasksLimitSelect = document.getElementById('tasks-limit-select');
  if (tasksLimitSelect) {
    tasksLimitSelect.addEventListener('change', (e) => {
      tasksPageSize = e.target.value === 'all' ? 'all' : parseInt(e.target.value, 10);
      tasksLimit = tasksPageSize;
      tasksCurrentPage = 1;
      renderTasks();
    });
  }

  if (msgSearchInput) msgSearchInput.addEventListener('input', () => { messagesCurrentPage = 1; renderMessages(); });
  if (msgFilterOrigin) msgFilterOrigin.addEventListener('change', () => { messagesCurrentPage = 1; renderMessages(); });
  if (msgFilterIntent) msgFilterIntent.addEventListener('change', () => { messagesCurrentPage = 1; renderMessages(); });
  if (msgFilterSentiment) msgFilterSentiment.addEventListener('change', () => { messagesCurrentPage = 1; renderMessages(); });
  if (msgFilterProsody) msgFilterProsody.addEventListener('change', () => { messagesCurrentPage = 1; renderMessages(); });

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

  // Sentiment Tab Listeners (Érato)
  const sentimentDatePicker = document.getElementById('sentiment-date-picker');
  const btnEratoView3d = document.getElementById('btn-erato-view-3d');
  const btnEratoViewAll = document.getElementById('btn-erato-view-all');

  if (btnEratoView3d) {
    btnEratoView3d.addEventListener('click', () => {
      if (sentimentDatePicker) sentimentDatePicker.value = '';
      btnEratoView3d.className = 'btn btn-primary btn-sm';
      if (btnEratoViewAll) btnEratoViewAll.className = 'btn btn-secondary btn-sm';
      loadDailySentiments('3d');
    });
  }

  if (btnEratoViewAll) {
    btnEratoViewAll.addEventListener('click', () => {
      if (sentimentDatePicker) sentimentDatePicker.value = '';
      btnEratoViewAll.className = 'btn btn-primary btn-sm';
      if (btnEratoView3d) btnEratoView3d.className = 'btn btn-secondary btn-sm';
      loadDailySentiments('30d');
    });
  }

  if (sentimentDatePicker) {
    sentimentDatePicker.addEventListener('change', (e) => {
      if (btnEratoView3d) btnEratoView3d.className = 'btn btn-secondary btn-sm';
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

  const sentimentFilterDominant = document.getElementById('sentiment-filter-dominant');
  if (sentimentFilterDominant) {
    sentimentFilterDominant.addEventListener('change', applyEratoSentimentFilter);
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
  if (msgFilterOrigin) {
    msgFilterOrigin.addEventListener('change', renderMessages);
  }
  if (msgFilterIntent) {
    msgFilterIntent.addEventListener('change', renderMessages);
  }
  if (msgFilterSentiment) {
    msgFilterSentiment.addEventListener('change', renderMessages);
  }
  if (msgFilterProsody) {
    msgFilterProsody.addEventListener('change', renderMessages);
  }
  if (btnRefreshMessages) {
    btnRefreshMessages.addEventListener('click', () => {
      loadMessages();
      showToast('Feed de mensagens atualizado!');
    });
  }

  // Euterpe Contact Sync & Terminal Listeners
  const btnEuterpeTriggerUpload = document.getElementById('btn-euterpe-trigger-upload');
  const euterpeFileInput = document.getElementById('euterpe-vcard-file-input');
  const btnEuterpeUploadVCard = document.getElementById('btn-euterpe-upload-vcard');
  const euterpeFilenameSpan = document.getElementById('euterpe-selected-filename');
  const btnEuterpeImportDir = document.getElementById('btn-euterpe-import-dir');
  const btnEuterpeDeduplicate = document.getElementById('btn-euterpe-deduplicate');
  const btnEuterpeSyncAvatars = document.getElementById('btn-euterpe-sync-avatars');
  const btnEuterpePipeline = document.getElementById('btn-euterpe-pipeline');
  const btnEuterpeClearTerminal = document.getElementById('btn-euterpe-clear-terminal');
  const btnEuterpeCopyLogs = document.getElementById('btn-euterpe-copy-logs');

  if (btnEuterpeTriggerUpload && euterpeFileInput) {
    btnEuterpeTriggerUpload.addEventListener('click', () => euterpeFileInput.click());
    euterpeFileInput.addEventListener('change', (e) => {
      if (e.target.files && e.target.files.length > 0) {
        const file = e.target.files[0];
        if (euterpeFilenameSpan) euterpeFilenameSpan.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
        if (btnEuterpeUploadVCard) btnEuterpeUploadVCard.style.display = 'inline-flex';
      } else {
        if (euterpeFilenameSpan) euterpeFilenameSpan.textContent = 'Nenhum arquivo selecionado';
        if (btnEuterpeUploadVCard) btnEuterpeUploadVCard.style.display = 'none';
      }
    });
  }

  if (btnEuterpeUploadVCard) btnEuterpeUploadVCard.addEventListener('click', handleEuterpeVCardUpload);
  if (btnEuterpeImportDir) btnEuterpeImportDir.addEventListener('click', handleEuterpeImportDirectory);
  if (btnEuterpeDeduplicate) btnEuterpeDeduplicate.addEventListener('click', handleEuterpeDeduplicate);
  if (btnEuterpeSyncAvatars) btnEuterpeSyncAvatars.addEventListener('click', handleEuterpeSyncAvatars);
  if (btnEuterpePipeline) btnEuterpePipeline.addEventListener('click', handleEuterpeFullPipeline);

  if (btnEuterpeClearTerminal) {
    btnEuterpeClearTerminal.addEventListener('click', () => {
      const term = document.getElementById('euterpe-terminal-logs');
      if (term) term.innerHTML = '<div class="terminal-line text-muted">[00:00:00] ℹ️ Terminal limpo.</div>';
      setEuterpeStatus('IDLE', 'badge-info');
    });
  }

  if (btnEuterpeCopyLogs) {
    btnEuterpeCopyLogs.addEventListener('click', () => {
      const term = document.getElementById('euterpe-terminal-logs');
      if (term) {
        navigator.clipboard.writeText(term.innerText).then(() => {
          showToast('📋 Logs do terminal copiados!');
        });
      }
    });
  }
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

async function loadContacts(forceReload = false) {
  try {
    // 1. Render instantâneo do cache de sessão (0ms de latência percebida)
    const cached = sessionStorage.getItem('hermes_cached_contacts');
    if (cached && (!allContacts || allContacts.length === 0 || !forceReload)) {
      try {
        allContacts = JSON.parse(cached);
        if (countContactsEl) countContactsEl.textContent = allContacts.length;
        renderContacts();
      } catch (e) {}
    }

    // 2. Busca dados atualizados da API em background
    const res = await fetch('/api/v1/contacts');
    if (res.ok) {
      allContacts = await res.json();
      try {
        sessionStorage.setItem('hermes_cached_contacts', JSON.stringify(allContacts));
      } catch (e) {}
    }
    
    // Fallback se SQL vazio
    if (!allContacts || allContacts.length === 0) {
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

    if (countContactsEl) countContactsEl.textContent = allContacts.length;
    renderContacts();
  } catch (err) {
    console.error('Erro ao carregar contatos:', err);
  }
}

let allDictionaryCategories = [];

async function loadDictionaryCategories() {
  try {
    const res = await fetch('/api/v1/dictionary/categories');
    if (res.ok) {
      allDictionaryCategories = await res.json();
      updateCategoryDropdowns();
    }
  } catch (err) {
    console.error('Erro ao carregar categorias dinâmicas:', err);
  }
}

function updateCategoryDropdowns() {
  const filterSelect = document.getElementById('dict-filter-category');
  const modalSelect = document.getElementById('term-category');

  if (filterSelect) {
    const currentVal = filterSelect.value.toUpperCase();
    let optionsHtml = '<option value="">📁 Todas as Categorias</option>';
    allDictionaryCategories.forEach(c => {
      const selected = (c.code.toUpperCase() === currentVal) ? 'selected' : '';
      const countSuffix = (c.terms_count !== undefined && c.terms_count > 0) ? ` (${c.terms_count})` : '';
      optionsHtml += `<option value="${c.code}" ${selected}>${c.label}${countSuffix}</option>`;
    });
    filterSelect.innerHTML = optionsHtml;
  }

  if (modalSelect) {
    const currentVal = modalSelect.value.toUpperCase();
    let optionsHtml = '';
    allDictionaryCategories.forEach(c => {
      const selected = (c.code.toUpperCase() === currentVal) ? 'selected' : '';
      optionsHtml += `<option value="${c.code}" ${selected}>${c.label}</option>`;
    });
    modalSelect.innerHTML = optionsHtml;
  }
}

async function loadDictionary() {
  try {
    await loadDictionaryCategories();
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

function updateTasksSpeakerOptions() {
  const speakerSelect = document.getElementById('tasks-filter-speaker');
  if (!speakerSelect) return;
  const currentVal = speakerSelect.value;
  const speakersSet = new Set();
  allTasks.forEach(t => {
    if (t.speaker && t.speaker.trim()) {
      speakersSet.add(t.speaker.trim());
    }
  });
  const sortedSpeakers = Array.from(speakersSet).sort((a, b) => a.localeCompare(b));
  
  speakerSelect.innerHTML = '<option value="">👥 Todas as Pessoas (Origem)</option>' +
    sortedSpeakers.map(spk => `<option value="${spk}" ${spk === currentVal ? 'selected' : ''}>👤 ${spk}</option>`).join('');
}

async function loadTasks() {
  try {
    const res = await fetch(`/api/v1/memory/tasks?view_mode=${tasksViewMode}`);
    if (res.ok) {
      allTasks = await res.json();
      if (countTasksEl && tasksViewMode === 'active') {
        countTasksEl.textContent = allTasks.filter(t => t.status === 'PENDING').length;
      }
      updateTasksSpeakerOptions();
      renderTasks();
    }

    // Atualiza contador de itens ativos no Baú
    try {
      const vaultRes = await fetch('/api/v1/memory/tasks?view_mode=vault');
      if (vaultRes.ok) {
        const vaultTasks = await vaultRes.json();
        const vCount = vaultTasks.filter(t => t.status !== 'DONE').length;
        const countVaultEl = document.getElementById('count-vault-tasks');
        if (countVaultEl) countVaultEl.textContent = vCount;
      }
    } catch (_) {}
  } catch (err) {
    console.error('Erro ao carregar tarefas:', err);
  }
}

async function loadMessages() {
  try {
    if (!allContacts || allContacts.length === 0) {
      await loadContacts();
    }
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

function filterTasksByTag(tag) {
  if (tasksSearchInput) {
    tasksSearchInput.value = tag;
    renderTasks();
    showToast(`🔍 Filtrando tarefas por tag #${tag}`);
  }
}
window.filterTasksByTag = filterTasksByTag;

function renderTasks() {
  if (!tasksContainer) return;

  const searchTerm = (tasksSearchInput ? tasksSearchInput.value : '').toLowerCase().trim();
  const filterSpeaker = tasksFilterSpeaker ? tasksFilterSpeaker.value.toLowerCase().trim() : '';
  const filterNature = tasksFilterNature ? tasksFilterNature.value : '';
  const filterStatus = tasksFilterStatus ? tasksFilterStatus.value.toUpperCase() : '';
  const filterPriority = tasksFilterPriority ? tasksFilterPriority.value.toUpperCase() : '';

  const filtered = allTasks.filter(t => {
    const matchTags = t.tags && Array.isArray(t.tags) && t.tags.some(tag => tag.toLowerCase().includes(searchTerm));
    const matchSearch = (
      !searchTerm ||
      t.title.toLowerCase().includes(searchTerm) ||
      (t.assignee && t.assignee.toLowerCase().includes(searchTerm)) ||
      (t.speaker && t.speaker.toLowerCase().includes(searchTerm)) ||
      (t.message_summary && t.message_summary.toLowerCase().includes(searchTerm)) ||
      (t.vault_reason && t.vault_reason.toLowerCase().includes(searchTerm)) ||
      (t.stakeholder_link && t.stakeholder_link.toLowerCase().includes(searchTerm)) ||
      (t.project_link && t.project_link.toLowerCase().includes(searchTerm)) ||
      matchTags
    );
    const matchSpeaker = !filterSpeaker || (t.speaker && t.speaker.toLowerCase().trim() === filterSpeaker);
    const matchStatus = !filterStatus || t.status === filterStatus;
    const matchPriority = !filterPriority || t.priority === filterPriority;

    let matchNature = true;
    if (filterNature === 'FAVORITE') matchNature = Boolean(t.is_favorite);
    else if (filterNature === 'EPIC') matchNature = Boolean(t.is_epic);
    else if (filterNature === 'IDEA') matchNature = Boolean(t.is_idea);

    return matchSearch && matchSpeaker && matchStatus && matchPriority && matchNature;
  });

  const totalFiltered = filtered.length;
  const paginationBar = document.getElementById('tasks-pagination-bar');
  const paginationInfo = document.getElementById('tasks-pagination-info');
  const btnPrev = document.getElementById('btn-tasks-prev');
  const btnNext = document.getElementById('btn-tasks-next');

  if (totalFiltered === 0) {
    if (paginationBar) paginationBar.style.display = 'none';
    const emptyMsg = tasksViewMode === 'vault'
      ? 'Nenhuma tarefa no Baú de Espera (Vault)'
      : 'Nenhuma tarefa encontrada no fluxo imediato';
    const emptySub = tasksViewMode === 'vault'
      ? 'Tarefas com prazos superiores a 7 dias ou adiadas para reavaliação aparecerão aqui.'
      : 'Tarefas acionáveis de curto prazo extraídas de notas de voz aparecerão aqui com a ancoragem de quem solicitou.';

    tasksContainer.innerHTML = `
      <div class="empty-state" style="text-align: center; padding: 3rem; color: var(--text-muted);">
        <p style="font-size: 1.1rem; margin-bottom: 0.5rem;">${emptyMsg}</p>
        <small>${emptySub}</small>
      </div>
    `;
    return;
  }

  const effectivePageSize = tasksPageSize === 'all' ? totalFiltered : (parseInt(tasksPageSize, 10) || 10);
  const totalPages = Math.ceil(totalFiltered / effectivePageSize) || 1;
  if (tasksCurrentPage > totalPages) tasksCurrentPage = totalPages;
  if (tasksCurrentPage < 1) tasksCurrentPage = 1;

  const startIndex = tasksPageSize === 'all' ? 0 : (tasksCurrentPage - 1) * effectivePageSize;
  const displayedList = tasksPageSize === 'all' ? filtered : filtered.slice(startIndex, startIndex + effectivePageSize);

  if (paginationBar) paginationBar.style.display = 'flex';
  if (paginationInfo) {
    paginationInfo.innerHTML = `Página <strong>${tasksCurrentPage}</strong> de <strong>${totalPages}</strong> (Total: ${totalFiltered} tarefas)`;
  }
  if (btnPrev) btnPrev.disabled = tasksCurrentPage <= 1;
  if (btnNext) btnNext.disabled = tasksCurrentPage >= totalPages || tasksPageSize === 'all';

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

    // Formatadores do Baú
    let vaultBannerHtml = '';
    if (t.in_vault) {
      const delayStr = t.postponed_until ? `Adiada até ${typeof t.postponed_until === 'string' ? t.postponed_until.substring(0, 10) : ''}` : 'No Baú (Prazo estendido)';
      const reminderStr = t.reminder_scheduled_at ? ` • 🔔 Lembrete agendado` : '';
      const reasonStr = t.vault_reason ? ` • Motivo: ${t.vault_reason}` : '';
      const factorMap = {
        'LOW_URGENCY': '⏳ Baixa Urgência',
        'DEPENDENCY': '🤝 Dependência de Terceiros',
        'SCOPE_CLARITY': '🔍 Falta Clareza Escopo',
        'OVERLOAD_ANXIETY': '🧘 Sobrecarga Mental',
        'PERFECTIONISM': '✨ Perfeccionismo/Complexidade',
        'LACK_OF_RESOURCES': '📦 Recursos/Alinhamento',
      };
      const factorLabel = t.procrastination_factor ? (factorMap[t.procrastination_factor] || t.procrastination_factor) : null;

      vaultBannerHtml = `
        <div class="task-vault-highlight">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <span>🗝️ <b>${delayStr}</b>${reminderStr}</span>
            ${factorLabel ? `<span class="badge" style="background: rgba(254, 240, 138, 0.2); color: #fef08a;">${factorLabel}</span>` : ''}
          </div>
          ${t.stakeholder_link ? `<div>👥 <b>Stakeholder:</b> ${t.stakeholder_link}</div>` : ''}
          ${t.project_link ? `<div>🏢 <b>Projeto:</b> ${t.project_link}</div>` : ''}
          ${t.reassessment_notes ? `<div style="font-style: italic; opacity: 0.9;">📝 Propósito: "${t.reassessment_notes}"</div>` : ''}
        </div>
      `;
    }

    return `
      <div class="${cardClass}" id="task-card-${t.id}">
        <!-- Topo: Título da Tarefa, Ações Estratégicas e Solicitante (Gatilho) -->
        <div class="task-top-row">
          <div style="flex: 1;">
            <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.25rem;">
              <div class="task-quick-actions">
                <button type="button" class="btn-pill-action ${t.is_favorite ? 'active-fav' : ''}" onclick="window.toggleTaskFavorite('${t.id}')" title="Fixar como Favorito">
                  ${t.is_favorite ? '⭐ Favorito' : '☆ Favoritar'}
                </button>
                <button type="button" class="btn-pill-action ${t.is_epic ? 'active-epic' : ''}" onclick="window.toggleTaskEpic('${t.id}')" title="Marcar como Objetivo Épico">
                  ${t.is_epic ? '🏛️ Épico' : '🏛️ Épico'}
                </button>
                <button type="button" class="btn-pill-action ${t.is_idea ? 'active-idea' : ''}" onclick="window.toggleTaskIdea('${t.id}')" title="Marcar como Ideia / Semente">
                  ${t.is_idea ? '💡 Ideia' : '💡 Ideia'}
                </button>
              </div>
            </div>

            <div class="task-title">
              ${isCancelled ? '<span style="color: #ef4444; font-size: 0.85rem; margin-right: 0.4rem;">[IGNORADA]</span>' : ''}
              ${t.title}
            </div>

            ${(t.tags && t.tags.length > 0) ? `
              <div class="task-tags-container">
                ${t.tags.map(tag => `<span class="task-tag" onclick="filterTasksByTag('${tag.replace(/'/g, "\\'")}')" title="Filtrar tarefas por #${tag}">#${tag}</span>`).join('')}
              </div>
            ` : ''}

            ${vaultBannerHtml}
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

          <div style="display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap;">
            ${t.in_vault ? `
              <button class="btn btn-primary btn-sm" onclick="window.restoreTaskFromVault('${t.id}')" title="Resgatar do Baú de volta ao fluxo imediato">
                ⚡ Resgatar do Baú
              </button>
            ` : `
              <button class="btn btn-secondary btn-sm" onclick="window.openVaultModal('${t.id}')" title="Adiar ou guardar no Baú para reavaliação de propósito">
                🗝️ Guardar no Baú
              </button>
            `}

            <button class="btn btn-secondary btn-sm" onclick="generateTaskPDF('${t.id}')" title="Gerar visualização e PDF formatado desta tarefa para compartilhamento">
              📄 Gerar PDF
            </button>

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

function generateTaskPDF(taskId) {
  const t = allTasks.find(item => item.id === taskId);
  if (!t) {
    showToast('Tarefa não encontrada para geração de PDF.', 'error');
    return;
  }

  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    showToast('Pop-up bloqueado pelo navegador. Permita pop-ups para visualizar e imprimir o PDF.', 'error');
    return;
  }

  const priorityColor = t.priority === 'URGENT' ? '#dc2626' : t.priority === 'HIGH' ? '#d97706' : '#059669';
  const speakerName = t.speaker || 'Não identificado';
  const phoneClean = (t.sender_phone || '').replace(/[^0-9]/g, '');
  const roleBadge = t.sender_role || 'Contato';
  const emissionDate = new Date().toLocaleString('pt-BR');

  const tagsHtml = (t.tags && Array.isArray(t.tags) && t.tags.length > 0)
    ? t.tags.map(tag => `<span style="display:inline-block; padding: 4px 10px; border-radius: 9999px; background: #e0f2fe; color: #0369a1; font-size: 12px; font-weight: 600; margin-right: 6px; border: 1px solid #bae6fd;">#${tag}</span>`).join('')
    : '<span style="color:#64748b; font-size:12px;">Nenhuma tag vinculada</span>';

  const notesHtml = t.notes
    ? `<div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:14px; white-space:pre-wrap; font-size:13px; color:#334155; line-height:1.6;">${t.notes}</div>`
    : `<div style="color:#94a3b8; font-style:italic; font-size:13px;">Sem anotações ou observações adicionais.</div>`;

  const originalMsg = t.revised_text || t.raw_text || t.source_text_snippet || 'Texto original não disponível.';

  const htmlContent = `
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Tarefa: ${t.title} — MNEMOSINE</title>
  <style>
    @page { size: A4; margin: 16mm 14mm; }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #0f172a;
      background: #f1f5f9;
      padding: 24px;
    }
    .sheet {
      max-width: 800px;
      margin: 0 auto;
      background: #ffffff;
      padding: 32px 36px;
      border-radius: 12px;
      box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }
    .no-print-bar {
      max-width: 800px;
      margin: 0 auto 16px auto;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid #cbd5e1;
      background: #ffffff;
      color: #334155;
      text-decoration: none;
      transition: all 0.15s;
    }
    .btn:hover { background: #f8fafc; border-color: #94a3b8; }
    .btn-primary { background: #059669; color: #ffffff; border-color: #047857; }
    .btn-primary:hover { background: #047857; }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 2px solid #0f172a;
      padding-bottom: 16px;
      margin-bottom: 24px;
    }
    .brand-title { font-size: 20px; font-weight: 800; letter-spacing: 0.05em; color: #0f172a; }
    .brand-sub { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 2px; }
    .meta-doc { text-align: right; font-size: 11px; color: #64748b; line-height: 1.4; }
    .badge {
      display: inline-block;
      padding: 3px 8px;
      border-radius: 4px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
    }
    .task-title {
      font-size: 20px;
      font-weight: 700;
      color: #0f172a;
      line-height: 1.35;
      margin-bottom: 16px;
    }
    .section-box {
      margin-bottom: 20px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 16px;
    }
    .section-title {
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #475569;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .grid-info {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px 20px;
      font-size: 13px;
    }
    .grid-label { color: #64748b; font-size: 11px; margin-bottom: 2px; text-transform: uppercase; }
    .grid-value { font-weight: 600; color: #1e293b; }
    .quote-box {
      background: #f1f5f9;
      border-left: 4px solid #0284c7;
      padding: 12px 16px;
      border-radius: 0 6px 6px 0;
      font-size: 13px;
      line-height: 1.5;
      color: #1e293b;
      font-style: italic;
    }
    .footer {
      margin-top: 32px;
      padding-top: 14px;
      border-top: 1px dashed #cbd5e1;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: #94a3b8;
    }
    @media print {
      body { background: transparent; padding: 0; }
      .sheet { box-shadow: none; padding: 0; max-width: 100%; }
      .no-print-bar { display: none !important; }
    }
  </style>
</head>
<body>
  <div class="no-print-bar">
    <div>
      <button class="btn btn-primary" onclick="window.print()">🖨️ Salvar como PDF / Imprimir</button>
      <button class="btn" onclick="copyFormattedTaskText()">📋 Copiar Resumo</button>
      ${phoneClean.length >= 10 ? `<a href="https://wa.me/${phoneClean}?text=${encodeURIComponent('Olá, segue o protocolo da tarefa: ' + t.title)}" target="_blank" class="btn">💬 WhatsApp</a>` : ''}
    </div>
    <button class="btn" onclick="window.close()">✖️ Fechar</button>
  </div>

  <div class="sheet">
    <div class="header">
      <div>
        <div class="brand-title">MNEMOSINE</div>
        <div class="brand-sub">Neural Intelligence & Voice Engine • Terpsícore</div>
      </div>
      <div class="meta-doc">
        <div><strong>Protocolo:</strong> ${t.id.substring(0, 13)}</div>
        <div><strong>Emissão:</strong> ${emissionDate}</div>
      </div>
    </div>

    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px; gap:12px;">
      <h1 class="task-title" style="flex:1;">${t.title}</h1>
      <div style="display:flex; gap:6px; flex-shrink:0;">
        <span class="badge" style="background:#e2e8f0; color:#334155;">Status: ${t.status}</span>
        <span class="badge" style="background:${priorityColor}; color:#ffffff;">● ${t.priority}</span>
      </div>
    </div>

    <div style="margin-bottom: 20px;">
      ${tagsHtml}
    </div>

    <div class="section-box">
      <div class="section-title">👤 Rastreamento de Origem & Atribuição</div>
      <div class="grid-info">
        <div>
          <div class="grid-label">Gatilho / Solicitante</div>
          <div class="grid-value">${speakerName} (${roleBadge})</div>
        </div>
        <div>
          <div class="grid-label">Atribuído a / Responsável</div>
          <div class="grid-value">${t.assignee || 'Bruno Conter'} ${t.due_date ? '• Prazo: ' + t.due_date : ''}</div>
        </div>
        <div>
          <div class="grid-label">Contato / Telefone</div>
          <div class="grid-value">${t.sender_phone || 'Não informado'}</div>
        </div>
        <div>
          <div class="grid-label">Horário do Disparo</div>
          <div class="grid-value">${t.message_time || emissionDate} ${t.audio_duration_s ? '(' + Math.round(t.audio_duration_s) + 's de áudio)' : ''}</div>
        </div>
      </div>
    </div>

    <div class="section-box">
      <div class="section-title">🎙️ Transcrição / Mensagem Original do Gatilho</div>
      <div class="quote-box">
        "${originalMsg}"
      </div>
      ${t.message_summary ? `
        <div style="margin-top:12px; font-size:12.5px; color:#475569; background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; padding:10px 12px;">
          <strong>💡 Resumo Cognitivo:</strong> ${t.message_summary}
        </div>
      ` : ''}
    </div>

    <div class="section-box">
      <div class="section-title">📝 Anotações, Observações & Acompanhamentos</div>
      ${notesHtml}
    </div>

    <div class="footer">
      <div>MNEMOSINE Engine — Voice Assistant C.Vale & Homelab</div>
      <div>Autenticidade Verificada • ID ${t.id}</div>
    </div>
  </div>

  <script>
    function copyFormattedTaskText() {
      const text = '📋 *TAREFA MNEMOSINE*\\n*Título:* ' + ${JSON.stringify(t.title)} + '\\n*De:* ' + ${JSON.stringify(speakerName)} + '\\n*Responsável:* ' + ${JSON.stringify(t.assignee || 'Bruno Conter')} + '\\n*Prioridade:* ' + ${JSON.stringify(t.priority)} + '\\n*Status:* ' + ${JSON.stringify(t.status)} + '\\n*Mensagem:* ' + ${JSON.stringify(originalMsg)} + '\\n*Notas:* ' + ${JSON.stringify(t.notes || 'Sem anotações.')};
      navigator.clipboard.writeText(text).then(() => {
        alert('📋 Resumo formatado copiado para a área de transferência!');
      }).catch(err => {
        alert('Erro ao copiar: ' + err);
      });
    }
  </script>
</body>
</html>
  `;

  printWindow.document.open();
  printWindow.document.write(htmlContent);
  printWindow.document.close();
}
window.generateTaskPDF = generateTaskPDF;

async function mergeSimilarTasks() {
  const confirmMsg = "Deseja analisar e mesclar tarefas semelhantes com status PENDENTE agrupadas por pessoa de origem?\n\nOs títulos serão consolidados e todos os comentários e observações serão unificados na tarefa principal.";
  if (!confirm(confirmMsg)) return;

  try {
    showToast('🔄 Analisando similaridade lexical e semântica com spaCy...', false);
    const res = await fetch('/api/v1/memory/tasks/merge-similar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) {
      throw new Error(`Erro na requisição: ${res.statusText}`);
    }

    const data = await res.json();
    if (data.merged_groups_count > 0) {
      showToast(`🔀 ${data.message}`);
    } else {
      showToast(`ℹ️ ${data.message}`);
    }
    await loadTasks();
  } catch (err) {
    console.error('Erro ao mesclar tarefas:', err);
    showToast('Erro ao mesclar tarefas: ' + err.message, 'error');
  }
}
window.mergeSimilarTasks = mergeSimilarTasks;

// --- Terpsícore: Sub-visões, Paginação, Vault, Jardim & Radar ---

function goToTasksPage(page) {
  tasksCurrentPage = page;
  renderTasks();
  if (tasksContainer) tasksContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
window.goToTasksPage = goToTasksPage;

function handleTasksLimitChange(val) {
  tasksPageSize = val === 'all' ? 'all' : parseInt(val, 10);
  tasksLimit = tasksPageSize;
  tasksCurrentPage = 1;
  renderTasks();
}
window.handleTasksLimitChange = handleTasksLimitChange;

function switchTerpsicoreView(view) {
  tasksViewMode = view;
  tasksCurrentPage = 1;

  // Atualiza botões da sub-barra de navegação
  ['active', 'vault', 'garden', 'radar'].forEach(v => {
    const btn = document.getElementById(`btn-tasks-subview-${v}`);
    if (btn) {
      if (v === view) {
        btn.classList.remove('btn-secondary');
        btn.classList.add('btn-primary', 'active');
      } else {
        btn.classList.remove('btn-primary', 'active');
        btn.classList.add('btn-secondary');
      }
    }
  });

  const toolbar = document.getElementById('tasks-toolbar');
  const listSection = document.getElementById('tasks-list-section');
  const gardenSection = document.getElementById('garden-section');
  const radarSection = document.getElementById('radar-section');
  const btnMergeActive = document.getElementById('btn-merge-tasks');
  const btnMergeVault = document.getElementById('btn-merge-vault-embeddings');

  if (view === 'active' || view === 'vault') {
    if (toolbar) toolbar.style.display = 'flex';
    if (listSection) listSection.style.display = 'block';
    if (gardenSection) gardenSection.style.display = 'none';
    if (radarSection) radarSection.style.display = 'none';

    if (btnMergeActive) btnMergeActive.style.display = view === 'active' ? 'inline-flex' : 'none';
    if (btnMergeVault) btnMergeVault.style.display = view === 'vault' ? 'inline-flex' : 'none';

    loadTasks();
  } else if (view === 'garden') {
    if (toolbar) toolbar.style.display = 'none';
    if (listSection) listSection.style.display = 'none';
    if (gardenSection) gardenSection.style.display = 'block';
    if (radarSection) radarSection.style.display = 'none';
    loadGardenMetrics();
  } else if (view === 'radar') {
    if (toolbar) toolbar.style.display = 'none';
    if (listSection) listSection.style.display = 'none';
    if (gardenSection) gardenSection.style.display = 'none';
    if (radarSection) radarSection.style.display = 'block';
    loadProcrastinationRadar();
  }
}
window.switchTerpsicoreView = switchTerpsicoreView;

async function toggleTaskFavorite(taskId) {
  try {
    const res = await fetch(`/api/v1/memory/tasks/${taskId}/toggle-favorite`, { method: 'POST' });
    if (res.ok) {
      const updated = await res.json();
      showToast(updated.is_favorite ? '⭐ Tarefa fixada como Favorita!' : 'Tarefa removida dos favoritos.');
      await loadTasks();
    }
  } catch (err) {
    showToast('Erro ao favoritar tarefa: ' + err.message, 'error');
  }
}
window.toggleTaskFavorite = toggleTaskFavorite;

async function toggleTaskEpic(taskId) {
  try {
    const res = await fetch(`/api/v1/memory/tasks/${taskId}/toggle-epic`, { method: 'POST' });
    if (res.ok) {
      const updated = await res.json();
      showToast(updated.is_epic ? '🏛️ Marcado como Objetivo Épico!' : 'Objetivo Épico desmarcado.');
      await loadTasks();
    }
  } catch (err) {
    showToast('Erro ao atualizar Objetivo Épico: ' + err.message, 'error');
  }
}
window.toggleTaskEpic = toggleTaskEpic;

async function toggleTaskIdea(taskId) {
  try {
    const res = await fetch(`/api/v1/memory/tasks/${taskId}/toggle-idea`, { method: 'POST' });
    if (res.ok) {
      const updated = await res.json();
      showToast(updated.is_idea ? '💡 Registrado no Jardim de Ideias / Sementes!' : 'Removido das ideias.');
      await loadTasks();
    }
  } catch (err) {
    showToast('Erro ao atualizar Ideia: ' + err.message, 'error');
  }
}
window.toggleTaskIdea = toggleTaskIdea;

function openVaultModal(taskId) {
  const t = allTasks.find(item => item.id === taskId);
  if (!t) return;

  const modal = document.getElementById('modal-vault-action');
  const taskIdInput = document.getElementById('vault-task-id');
  const modalTitle = document.getElementById('vault-modal-title');
  const postponeDaysInput = document.getElementById('vault-postpone-days');
  const reminderInput = document.getElementById('vault-reminder-datetime');
  const factorSelect = document.getElementById('vault-procrastination-factor');
  const stakeholderInput = document.getElementById('vault-stakeholder-link');
  const projectInput = document.getElementById('vault-project-link');
  const notesTextarea = document.getElementById('vault-reassessment-notes');

  if (taskIdInput) taskIdInput.value = taskId;
  if (modalTitle) modalTitle.textContent = `🗝️ Guardar no Baú: "${t.title.substring(0, 35)}..."`;
  if (postponeDaysInput) postponeDaysInput.value = 8;
  if (reminderInput) reminderInput.value = '';
  if (factorSelect) factorSelect.value = t.procrastination_factor || 'LOW_URGENCY';
  if (stakeholderInput) stakeholderInput.value = t.speaker || '';
  if (projectInput) projectInput.value = '';
  if (notesTextarea) notesTextarea.value = '';

  if (modal) modal.style.display = 'flex';
}
window.openVaultModal = openVaultModal;

function closeVaultModal() {
  const modal = document.getElementById('modal-vault-action');
  if (modal) modal.style.display = 'none';
}
window.closeVaultModal = closeVaultModal;

function setVaultDelayPreset(days) {
  const postponeDaysInput = document.getElementById('vault-postpone-days');
  if (postponeDaysInput) postponeDaysInput.value = Math.max(days, 8);
}
window.setVaultDelayPreset = setVaultDelayPreset;

async function saveVaultAction(event) {
  if (event) event.preventDefault();
  const taskId = document.getElementById('vault-task-id').value;
  let postponeDays = parseInt(document.getElementById('vault-postpone-days').value, 10) || 8;
  if (postponeDays < 8) {
    postponeDays = 8;
    showToast('ℹ️ O prazo para o Baú deve ser de no mínimo 8 dias (> 1 semana). Ajustado para 8 dias.');
  }
  const reminderDateTime = document.getElementById('vault-reminder-datetime').value || null;
  const factor = document.getElementById('vault-procrastination-factor').value;
  const stakeholder = document.getElementById('vault-stakeholder-link').value.trim() || null;
  const project = document.getElementById('vault-project-link').value.trim() || null;
  const reassessment = document.getElementById('vault-reassessment-notes').value.trim() || null;

  try {
    const res = await fetch(`/api/v1/memory/tasks/${taskId}/vault`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        postpone_days: postponeDays,
        reminder_datetime: reminderDateTime ? reminderDateTime.replace('T', ' ') : null,
        procrastination_factor: factor,
        stakeholder_link: stakeholder,
        project_link: project,
        reassessment_notes: reassessment,
      }),
    });

    if (res.ok) {
      closeVaultModal();
      showToast('🗝️ Tarefa guardada com sucesso no Baú de Espera (Vault)!');
      await loadTasks();
    } else {
      showToast('Erro ao mover tarefa para o Baú', true);
    }
  } catch (err) {
    showToast('Falha na comunicação: ' + err.message, 'error');
  }
}
window.saveVaultAction = saveVaultAction;

async function restoreTaskFromVault(taskId) {
  try {
    const res = await fetch(`/api/v1/memory/tasks/${taskId}/unvault`, { method: 'POST' });
    if (res.ok) {
      showToast('⚡ Tarefa resgatada com sucesso do Baú para o fluxo ativo!');
      await loadTasks();
    }
  } catch (err) {
    showToast('Erro ao resgatar tarefa: ' + err.message, 'error');
  }
}
window.restoreTaskFromVault = restoreTaskFromVault;

async function mergeVaultTasksEmbeddings() {
  const confirmMsg = "Deseja agrupar e fundir tarefas no Baú utilizando cálculo vetorial de embeddings?\n\nPendências de longo prazo semelhantes serão unificadas para reduzir o ruído cognitivo.";
  if (!confirm(confirmMsg)) return;

  try {
    showToast('🧬 Executando fusão semântica por embeddings vetoriais...', false);
    const res = await fetch('/api/v1/memory/tasks/vault/merge-embeddings', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      showToast(`🧬 ${data.message}`);
      await loadTasks();
    }
  } catch (err) {
    showToast('Erro na fusão por embeddings: ' + err.message, 'error');
  }
}
window.mergeVaultTasksEmbeddings = mergeVaultTasksEmbeddings;

async function loadGardenMetrics() {
  try {
    const res = await fetch('/api/v1/memory/tasks/garden/metrics');
    if (res.ok) {
      const data = await res.json();
      renderGarden(data);
    }
  } catch (err) {
    console.error('Erro ao carregar Jardim de Realizações:', err);
  }
}
window.loadGardenMetrics = loadGardenMetrics;

function renderGarden(data) {
  const seedsEl = document.getElementById('garden-kpi-seeds');
  const activeEl = document.getElementById('garden-kpi-active');
  const vaultEl = document.getElementById('garden-kpi-vault');
  const harvestedEl = document.getElementById('garden-kpi-harvested');
  const rateEl = document.getElementById('garden-kpi-rate');
  const matEl = document.getElementById('garden-avg-maturation');

  if (seedsEl) seedsEl.textContent = data.total_seeds || 0;
  if (activeEl) activeEl.textContent = data.in_germination_active || 0;
  if (vaultEl) vaultEl.textContent = data.in_germination_vault || 0;
  if (harvestedEl) harvestedEl.textContent = data.total_harvested || 0;
  if (rateEl) rateEl.textContent = `Taxa de Concretização: ${data.conversion_rate_pct || 0}%`;
  if (matEl) matEl.textContent = `${data.avg_maturation_days || 0} dias`;

  // Colheitas Recentes
  const harvestContainer = document.getElementById('garden-harvest-list');
  if (harvestContainer) {
    if (!data.recent_harvests || data.recent_harvests.length === 0) {
      harvestContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem; text-align: center;">Nenhuma realização concluída recentemente no Jardim.</div>';
    } else {
      harvestContainer.innerHTML = data.recent_harvests.map(h => `
        <div class="garden-harvest-item-card">
          <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.35rem;">
            <strong style="color: #6ee7b7; font-size: 0.9rem;">✅ ${h.title}</strong>
            <span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #6ee7b7; font-size: 0.72rem;">${h.maturation_days}d maturação</span>
          </div>
          <div style="font-size: 0.78rem; color: var(--text-muted); display: flex; gap: 0.75rem; flex-wrap: wrap;">
            <span>🌱 Concepção: ${h.conceived_at}</span>
            <span>🌸 Realizado: ${h.realized_at}</span>
            <span>👤 ${h.speaker}</span>
            ${h.project ? `<span>🏢 ${h.project}</span>` : ''}
          </div>
        </div>
      `).join('');
    }
  }

  // Constelações
  const constContainer = document.getElementById('garden-constellations-list');
  if (constContainer) {
    if (!data.active_constellations || data.active_constellations.length === 0) {
      constContainer.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem; padding: 1rem; text-align: center;">Nenhuma constelação de ideias em incubação no momento.</div>';
    } else {
      constContainer.innerHTML = data.active_constellations.map(c => `
        <div class="garden-constellation-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.4rem;">
            <strong style="color: #93c5fd; font-size: 0.9rem;">✨ ${c.theme}</strong>
            <span class="badge" style="background: rgba(59, 130, 246, 0.2); color: #bfdbfe; font-size: 0.72rem;">${c.ideas_count} ideias</span>
          </div>
          <ul style="padding-left: 1.2rem; margin: 0; font-size: 0.8rem; color: var(--text-secondary);">
            ${c.sample_ideas.map(i => `<li>${i}</li>`).join('')}
          </ul>
        </div>
      `).join('');
    }
  }
}

async function loadProcrastinationRadar() {
  try {
    const res = await fetch('/api/v1/memory/tasks/vault/radar');
    if (res.ok) {
      const data = await res.json();
      renderProcrastinationRadar(data);
    }
  } catch (err) {
    console.error('Erro ao carregar Radar de Procrastinação:', err);
  }
}
window.loadProcrastinationRadar = loadProcrastinationRadar;

function renderProcrastinationRadar(data) {
  const canvas = document.getElementById('chart-procrastination-radar');
  if (!canvas || typeof Chart === 'undefined') return;

  const dims = data.dimensions || {};
  const labels = [
    'Clareza Escopo',
    'Dependência',
    'Ansiedade/Sobrecarga',
    'Perfeccionismo',
    'Baixa Urgência',
    'Recursos/Alinhamento'
  ];
  const values = [
    dims.SCOPE_CLARITY || 25,
    dims.DEPENDENCY || 25,
    dims.OVERLOAD_ANXIETY || 25,
    dims.PERFECTIONISM || 25,
    dims.LOW_URGENCY || 25,
    dims.LACK_OF_RESOURCES || 25
  ];

  if (procrastinationRadarChart) {
    procrastinationRadarChart.destroy();
  }

  const ctx = canvas.getContext('2d');
  procrastinationRadarChart = new Chart(ctx, {
    type: 'radar',
    data: {
      labels: labels,
      datasets: [{
        label: 'Vetor de Estagnação (%)',
        data: values,
        backgroundColor: 'rgba(234, 179, 8, 0.25)',
        borderColor: '#eab308',
        pointBackgroundColor: '#fef08a',
        pointBorderColor: '#090d16',
        pointHoverBackgroundColor: '#fff',
        pointHoverBorderColor: '#eab308',
        borderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        r: {
          angleLines: { color: 'rgba(255, 255, 255, 0.1)' },
          grid: { color: 'rgba(255, 255, 255, 0.08)' },
          pointLabels: {
            color: '#f8fafc',
            font: { size: 11, weight: '600' }
          },
          ticks: {
            backdropColor: 'transparent',
            color: '#64748b',
            stepSize: 20,
            max: 100,
            min: 0,
          }
        }
      },
      plugins: {
        legend: { display: false }
      }
    }
  });

  // Renderiza insights e top factors
  const insightsContainer = document.getElementById('radar-insights-container');
  if (insightsContainer) {
    const topFactorsHtml = (data.top_factors && data.top_factors.length > 0)
      ? `<div style="display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
          ${data.top_factors.slice(0, 3).map(tf => `<span class="badge" style="background: rgba(234, 179, 8, 0.15); color: #fef08a; font-size: 0.75rem;">${tf.factor}: ${tf.pct}%</span>`).join('')}
         </div>`
      : '';

    const insightsHtml = (data.insights && data.insights.length > 0)
      ? data.insights.map(ins => `<div class="radar-insight-pill">${ins}</div>`).join('')
      : '<div class="radar-insight-pill">🌿 Suas tarefas estão distribuídas de forma equilibrada no Baú.</div>';

    insightsContainer.innerHTML = topFactorsHtml + insightsHtml;
  }
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

// Localiza se o remetente da mensagem é o Dono ou um Contato cadastrado em Clio
function findContactForMessage(m) {
  if (!m) return { isRecognized: false, isOwner: false, contact: null, phone: '', name: '' };

  const ownerNames = ['bruno conter', 'bruno', 'user', 'admin', 'owner', 'proprietario', 'proprietário', 'mestre', 'deus'];
  const ownerPhones = ['554499214934', '4499214934', '99214934', '5544999214934', '44999214934', '999214934'];

  const meta = (m.meta_info && typeof m.meta_info === 'object') ? m.meta_info : {};
  const isFromMe = meta.fromMe === true || meta.fromMe === 1 || meta.from_me === true;

  // Extrai dígitos de telefone disponíveis
  let rawPhone = meta.phone || meta.sender_phone || meta.remoteJid || meta.remote_jid || '';
  if (!rawPhone && m.speaker && /^\+?[\d\s\-\(\)\.]+$/.test(m.speaker.trim())) {
    rawPhone = m.speaker.trim();
  }
  const cleanPhone = String(rawPhone).replace(/\D/g, '');

  const speakerRaw = String(m.speaker || '').trim();
  const speakerLower = speakerRaw.toLowerCase();
  const speakerNorm = speakerLower.normalize('NFD').replace(/[\u0300-\u036f]/g, '');

  // 1. Verificação se é o Dono
  if (isFromMe) {
    return { isRecognized: true, isOwner: true, contact: null, phone: cleanPhone, name: 'Bruno Conter' };
  }
  if (ownerNames.includes(speakerLower) || ownerNames.includes(speakerNorm) || speakerNorm.includes('bruno conter')) {
    return { isRecognized: true, isOwner: true, contact: null, phone: cleanPhone, name: 'Bruno Conter' };
  }
  if (cleanPhone && ownerPhones.some(op => cleanPhone === op || (cleanPhone.length >= 8 && (cleanPhone.endsWith(op.slice(-8)) || op.endsWith(cleanPhone.slice(-8)))))) {
    return { isRecognized: true, isOwner: true, contact: null, phone: cleanPhone, name: 'Bruno Conter' };
  }

  // 2. Busca nos contatos cadastrados de Clio (allContacts)
  if (Array.isArray(allContacts) && allContacts.length > 0) {
    for (const c of allContacts) {
      const cPhone = String(c.phone_number || '').replace(/\D/g, '');
      const cName = String(c.name || '').trim();
      const cNick = String(c.nickname || '').trim();
      const cNameNorm = cName.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
      const cNickNorm = cNick.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');

      // Match por telefone (exato ou 8 últimos dígitos)
      if (cleanPhone && cPhone) {
        if (cleanPhone === cPhone || (cleanPhone.length >= 8 && cPhone.length >= 8 && (cleanPhone.endsWith(cPhone.slice(-8)) || cPhone.endsWith(cleanPhone.slice(-8))))) {
          return { isRecognized: true, isOwner: false, contact: c, phone: cleanPhone || cPhone, name: c.name };
        }
      }

      // Match por nome ou apelido
      if (speakerNorm && (speakerNorm === cNameNorm || (cNickNorm && speakerNorm === cNickNorm))) {
        return { isRecognized: true, isOwner: false, contact: c, phone: cleanPhone || cPhone, name: c.name };
      }
    }
  }

  // 3. Contato Não Reconhecido
  const pushName = String(meta.pushName || meta.push_name || '').trim();
  const isSpeakerOnlyDigits = /^\+?[\d\s\-\(\)\.@]+$/.test(speakerRaw);
  const suggestedName = pushName || (!isSpeakerOnlyDigits && !['user', 'desconhecido'].includes(speakerLower) ? speakerRaw : '');

  return {
    isRecognized: false,
    isOwner: false,
    contact: null,
    phone: cleanPhone,
    suggestedName: suggestedName
  };
}
window.findContactForMessage = findContactForMessage;

function renderMessages() {
  if (!messagesContainer) return;

  const searchTerm = msgSearchInput ? msgSearchInput.value.toLowerCase().trim() : '';
  const filterOrigin = msgFilterOrigin ? msgFilterOrigin.value.toUpperCase() : '';
  const filterIntent = msgFilterIntent ? msgFilterIntent.value.toUpperCase() : '';
  const filterSentiment = msgFilterSentiment ? msgFilterSentiment.value.toUpperCase() : '';
  const filterProsody = msgFilterProsody ? msgFilterProsody.value.toUpperCase() : '';

  const filtered = allMessages.filter(m => {
    const revised = (m.revised_text || '').toLowerCase();
    const raw = (m.raw_text || '').toLowerCase();
    const textValid = (m.revised_text || m.raw_text || '').trim();
    if (!textValid) return false;

    const speaker = (m.speaker || '').toLowerCase();
    const summary = (m.summary || '').toLowerCase();

    // Verificação de Origem e Prosódia
    const isAudio = Boolean(m.audio_duration_s || (m.meta_info && m.meta_info.prosody) || m.audio_filename);
    const voiceTone = (m.meta_info && m.meta_info.prosody && m.meta_info.prosody.voice_tone) ? m.meta_info.prosody.voice_tone.toUpperCase() : '';

    const matchSearch = !searchTerm || speaker.includes(searchTerm) || revised.includes(searchTerm) || raw.includes(searchTerm) || summary.includes(searchTerm);
    const matchOrigin = !filterOrigin || (filterOrigin === 'AUDIO' ? isAudio : !isAudio);
    const matchIntent = !filterIntent || (m.intent && m.intent.toUpperCase() === filterIntent);
    const matchSentiment = !filterSentiment || (m.sentiment && m.sentiment.toUpperCase() === filterSentiment);
    const matchProsody = !filterProsody || (voiceTone === filterProsody);

    return matchSearch && matchOrigin && matchIntent && matchSentiment && matchProsody;
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
        <small>As notas de voz e mensagens enviadas aparecerão aqui em tempo real com análise semântica e métricas.</small>
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
    const contactInfo = findContactForMessage(m);
    const urgencyColor = m.urgency === 'URGENT' ? '#ef4444' : m.urgency === 'HIGH' ? '#f59e0b' : '#10b981';

    // Determina nome, avatar e badge de papel
    let displayName = m.speaker || 'Desconhecido';
    let avatarHtml = '';
    let roleBadgeHtml = '';

    if (contactInfo.isOwner) {
      displayName = 'Bruno Conter 👑';
      avatarHtml = '<span title="Proprietário & Arquiteto">👑</span>';
    } else if (contactInfo.isRecognized && contactInfo.contact) {
      const c = contactInfo.contact;
      displayName = c.name + (c.nickname ? ` <small style="color: var(--text-muted); font-weight: normal;">(${c.nickname})</small>` : '');
      if (c.role && c.role !== 'UNKNOWN') {
        roleBadgeHtml = `<span class="badge" style="font-size: 0.68rem; background: rgba(59, 130, 246, 0.15); color: #60a5fa;" title="Papel: ${c.role}">${c.role}</span>`;
      }
      if (c.avatar_url) {
        avatarHtml = `<img src="${c.avatar_url}" alt="${c.name}" class="message-avatar-img">`;
      } else {
        const initials = c.name.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
        avatarHtml = initials || 'C';
      }
    } else {
      const initials = (m.speaker || 'U').split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase();
      avatarHtml = initials || '❓';
    }

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

    // Origem (Áudio vs Texto)
    const isAudio = Boolean(m.audio_duration_s || (m.meta_info && m.meta_info.prosody) || m.audio_filename);
    const originBadgeHtml = isAudio ? `
      <span class="badge" style="font-size: 0.72rem; background: rgba(59, 130, 246, 0.15); color: #60a5fa;" title="Origem: Nota de Voz / Áudio (${m.audio_duration_s ? m.audio_duration_s + 's' : 'Áudio'})">
        🎙️ Áudio ${m.audio_duration_s ? `(${Math.round(m.audio_duration_s)}s)` : ''}
      </span>
    ` : `
      <span class="badge" style="font-size: 0.72rem; background: rgba(148, 163, 184, 0.15); color: #94a3b8;" title="Origem: Mensagem de Texto Direta">
        💬 Texto
      </span>
    `;

    // Prosódia Acústica
    const prosody = m.meta_info && m.meta_info.prosody;
    const prosodyHtml = prosody ? `
      <span class="badge ${prosody.tone_badge_class || 'badge-info'}" style="font-size: 0.72rem;" title="Prosódia Acústica: ${prosody.speech_rate_wps} pal/s • Pausas: ${Math.round(prosody.pause_ratio * 100)}% • Fala ativa: ${prosody.speech_duration_s}s">
        ${prosody.tone_label} (${prosody.speech_rate_wps} pal/s)
      </span>
    ` : '';

    // Telefone / WhatsApp
    let phoneClean = contactInfo.phone || '';
    if (!phoneClean) {
      if (m.meta_info && m.meta_info.remoteJid) {
        phoneClean = m.meta_info.remoteJid.replace(/[^0-9]/g, '');
      } else if (m.speaker && /^\d+$/.test(m.speaker.replace(/[^0-9]/g, ''))) {
        phoneClean = m.speaker.replace(/[^0-9]/g, '');
      }
    }
    const waLink = phoneClean.length >= 10 ? `https://wa.me/${phoneClean}` : null;

    // Badges e Botões de cadastro em Clio para contato não reconhecido
    const unrecognizedBadgeHtml = !contactInfo.isRecognized ? `
      <span class="badge badge-unrecognized" title="Contato não cadastrado no banco de dados de Clio">
        ⚠️ Não Cadastrado
      </span>
    ` : '';

    const registerButtonHeaderHtml = !contactInfo.isRecognized ? `
      <button type="button" class="btn-clio-register" onclick="openRegisterContactModal('${m.id}')" title="Cadastrar este contato em Clio">
        📜 + Cadastrar em Clio
      </button>
    ` : '';

    const registerButtonBarHtml = !contactInfo.isRecognized ? `
      <button type="button" class="btn btn-secondary btn-sm btn-clio-register-bar" onclick="openRegisterContactModal('${m.id}')" title="Cadastrar este contato em Clio">
        📜 Cadastrar em Clio
      </button>
    ` : '';

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
            <div class="message-avatar">${avatarHtml}</div>
            <div>
              <div class="message-speaker-name">
                <span>${displayName}</span>
                ${roleBadgeHtml}
                ${waLink ? `<a href="${waLink}" target="_blank" title="Abrir conversa no WhatsApp">💬 WhatsApp</a>` : ''}
                ${registerButtonHeaderHtml}
              </div>
              <small style="color: var(--text-muted); font-size: 0.78rem;">${m.created_at || 'Data desconhecida'}</small>
            </div>
          </div>

          <div class="message-badges">
            ${originBadgeHtml}
            ${unrecognizedBadgeHtml}
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
            ${registerButtonBarHtml}
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
    const catObj = allDictionaryCategories.find(c => c.code.toUpperCase() === (t.category || '').toUpperCase());
    const catLabel = catObj ? catObj.label : (t.category || 'GERAL');

    return `
      <div class="dict-card">
        <div class="dict-header">
          <span class="dict-term">${t.term}</span>
          <span class="badge badge-executive" title="${catObj ? catObj.description : ''}">${catLabel}</span>
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

async function mergeSimilarDictionaryTerms() {
  const confirmMsg = "Deseja analisar e mesclar termos semelhantes, duplicados ou flexionados (singular/plural, variações fonéticas e ortográficas) em Polímnia usando spaCy NLP?\n\nAs variações fonéticas, expansões e descrições serão unificadas no termo canônico ideal.";
  if (!confirm(confirmMsg)) return;

  try {
    showToast('🔄 Analisando semântica e morfologia com spaCy...', false);
    const res = await fetch('/api/v1/dictionary/merge-similar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) {
      throw new Error(`Erro na requisição: ${res.statusText}`);
    }

    const data = await res.json();
    if (data.merged_clusters_count > 0 || data.candidates_merged_count > 0) {
      showToast(`🔀 ${data.message}`);
    } else {
      showToast(`ℹ️ ${data.message}`);
    }
    await loadDictionary();
  } catch (err) {
    console.error('Erro ao mesclar termos do dicionário:', err);
    showToast('Erro ao mesclar termos: ' + err.message, 'error');
  }
}
window.mergeSimilarDictionaryTerms = mergeSimilarDictionaryTerms;

async function rationalizeCategoriesWithUrania() {
  const confirmMsg = "Deseja expandir e racionalizar as categorias de Polímnia utilizando o Grafo Neural de Urânia e spaCy NLP?\n\nO sistema analisará os conceitos de avicultura, silos, telemetria, C.Vale e ERPs, redistribuindo os termos nas categorias mais precisas (teto máximo de 12 categorias).";
  if (!confirm(confirmMsg)) return;

  try {
    showToast('🔮 Urânia & spaCy analisando topologia do grafo...', false);
    const res = await fetch('/api/v1/dictionary/rationalize-categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    });

    if (!res.ok) {
      throw new Error(`Erro na requisição: ${res.statusText}`);
    }

    const data = await res.json();
    showToast(`🔮 ${data.message}`);
    await loadDictionary();
  } catch (err) {
    console.error('Erro ao racionalizar categorias:', err);
    showToast('Erro ao racionalizar categorias: ' + err.message, 'error');
  }
}
window.rationalizeCategoriesWithUrania = rationalizeCategoriesWithUrania;

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
      await loadContacts();
      loadStats();
      loadGraphData();
      renderMessages();
    } else {
      const errData = await res.json().catch(() => ({}));
      showToast(`Erro ao salvar contato: ${errData.detail || res.statusText}`, true);
    }
  } catch (err) {
    console.error('Erro:', err);
    showToast('Erro de conexão ao salvar', true);
  }
}

// Abre o modal de Clio pré-preenchido com os dados da mensagem não reconhecida de Calíope
function openRegisterContactModal(msgId) {
  const msg = allMessages.find(m => String(m.id) === String(msgId));
  if (!msg) return;

  const contactInfo = findContactForMessage(msg);

  document.getElementById('modal-contact-title').textContent = '📜 Cadastrar Contato em Clio';
  formContact.reset();
  document.getElementById('contact-id').value = '';

  // Nome sugerido
  let nameVal = contactInfo.suggestedName || '';
  if (!nameVal && msg.speaker && !/^\+?[\d\s\-\(\)\.@]+$/.test(msg.speaker.trim())) {
    nameVal = msg.speaker.trim();
  }
  document.getElementById('contact-name').value = nameVal;

  // Telefone / WhatsApp formatado
  let phoneVal = contactInfo.phone || '';
  if (phoneVal) {
    if (phoneVal.startsWith('55') && phoneVal.length >= 12) {
      const ddd = phoneVal.substring(2, 4);
      const rest = phoneVal.substring(4);
      if (rest.length === 9) {
        phoneVal = `(${ddd}) ${rest.substring(0, 5)}-${rest.substring(5)}`;
      } else if (rest.length === 8) {
        phoneVal = `(${ddd}) ${rest.substring(0, 4)}-${rest.substring(4)}`;
      }
    }
  }
  document.getElementById('contact-phone').value = phoneVal;

  // Papel padrão para novos contatos
  document.getElementById('contact-role').value = 'PRODUCER_COOPERATED';

  // Observações contextuais de Calíope
  const snippet = (msg.revised_text || msg.raw_text || '').substring(0, 120).trim();
  document.getElementById('contact-notes').value = `Cadastrado via Calíope a partir da mensagem (${msg.created_at || 'recente'}): "${snippet}..."`;

  modalContact.classList.add('active');

  setTimeout(() => {
    if (!nameVal) {
      document.getElementById('contact-name').focus();
    } else if (!phoneVal) {
      document.getElementById('contact-phone').focus();
    } else {
      document.getElementById('contact-role').focus();
    }
  }, 100);
}
window.openRegisterContactModal = openRegisterContactModal;

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

let cachedDailySnapshots = [];
let currentEratoTargetDate = '3d';

async function loadDailySentiments(targetDate = '3d') {
  const container = document.getElementById('sentiment-daily-container');
  const badge = document.getElementById('sentiment-day-badge');
  if (!container) return;

  currentEratoTargetDate = targetDate;
  const is3d = !targetDate || targetDate === '3d' || targetDate === '3days';
  const is30d = targetDate === '30d' || targetDate === 'all' || targetDate === 'todos';
  
  let url = `/api/v1/memory/sentiment/daily?date=${targetDate}`;
  if (is3d) {
    url = '/api/v1/memory/sentiment/daily?date=3d&days=3';
    if (badge) badge.textContent = 'Últimos 3 Dias';
  } else if (is30d) {
    url = '/api/v1/memory/sentiment/daily?date=all&days=30';
    if (badge) badge.textContent = 'Últimos 30 Dias';
  } else {
    if (badge) badge.textContent = targetDate;
  }

  container.innerHTML = `
    <div style="grid-column: 1 / -1; text-align: center; padding: 2rem; color: var(--text-muted);">
      <p>⏳ Carregando termômetro e análise de sentimentos...</p>
    </div>
  `;

  try {
    const res = await fetch(url);
    if (res.ok) {
      cachedDailySnapshots = await res.json();
      applyEratoSentimentFilter();
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

function applyEratoSentimentFilter() {
  const filterSelect = document.getElementById('sentiment-filter-dominant');
  const selected = filterSelect ? filterSelect.value : '';

  let list = cachedDailySnapshots || [];
  if (selected) {
    list = list.filter(s => {
      const dom = (s.dominant_sentiment || '').toUpperCase();
      if (selected === 'NEGATIVE') {
        return dom === 'NEGATIVE' || dom === 'FRUSTRATED' || dom === 'URGENT';
      }
      return dom === selected;
    });
  }

  renderDailySentiments(list, currentEratoTargetDate);
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

  const period = periodSelect ? periodSelect.value : '3d';
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
      const hourFmt = String(cell.hour).padStart(2, '0');
      const title = `${dayNames[d]} às ${hourFmt}:00 (UTC-3) — ${cell.count} mensagem(ns)`;
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

// ==========================================================================
// EUTERPE — Central de Importação, Deduplicação & Terminal de Logs
// ==========================================================================

function logToEuterpeTerminal(message, type = 'info') {
  const terminalEl = document.getElementById('euterpe-terminal-logs');
  if (!terminalEl) return;

  const now = new Date();
  const timeStr = now.toTimeString().split(' ')[0];
  const line = document.createElement('div');
  line.className = `terminal-line ${type}`;
  line.textContent = `[${timeStr}] ${message}`;
  terminalEl.appendChild(line);
  terminalEl.scrollTop = terminalEl.scrollHeight;
}
window.logToEuterpeTerminal = logToEuterpeTerminal;

function setEuterpeStatus(statusText, badgeClass = 'badge-info') {
  const statusEl = document.getElementById('euterpe-terminal-status');
  if (statusEl) {
    statusEl.textContent = statusText;
    statusEl.className = `badge ${badgeClass}`;
  }
}
window.setEuterpeStatus = setEuterpeStatus;

// 1. Upload e Importação de Arquivo .vcf Local
async function handleEuterpeVCardUpload() {
  const fileInput = document.getElementById('euterpe-vcard-file-input');
  if (!fileInput || !fileInput.files || fileInput.files.length === 0) {
    showToast('Selecione um arquivo .vcf ou .vcard primeiro', true);
    return;
  }

  const file = fileInput.files[0];
  setEuterpeStatus('IMPORTANDO...', 'badge-warning');
  logToEuterpeTerminal(`📤 Enviando arquivo '${file.name}' (${(file.size / 1024).toFixed(1)} KB)...`, 'info');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/v1/contacts/import-vcard', {
      method: 'POST',
      body: formData,
    });

    if (res.ok) {
      const data = await res.json();
      (data.details || []).forEach(d => logToEuterpeTerminal(d, 'success'));
      logToEuterpeTerminal(`🎉 Importação concluída: ${data.imported_count} inseridos, ${data.updated_count} atualizados.`, 'success');
      showToast(`vCard importado: +${data.imported_count} novos contatos!`);
      setEuterpeStatus('CONCLUÍDO', 'badge-success');
      await loadContacts();
      loadStats();
      loadGraphData();
    } else {
      const err = await res.json().catch(() => ({}));
      logToEuterpeTerminal(`❌ Erro no upload: ${err.detail || res.statusText}`, 'error');
      setEuterpeStatus('ERRO', 'badge-danger');
      showToast('Erro ao importar vCard', true);
    }
  } catch (err) {
    logToEuterpeTerminal(`❌ Erro de conexão: ${err}`, 'error');
    setEuterpeStatus('ERRO', 'badge-danger');
  }
}
window.handleEuterpeVCardUpload = handleEuterpeVCardUpload;

// 2. Importação do Diretório data/vcards/ da VPS
async function handleEuterpeImportDirectory() {
  setEuterpeStatus('LENDO DIRETÓRIO...', 'badge-warning');
  logToEuterpeTerminal('📂 Solicitando importação da pasta data/vcards/ na VPS...', 'info');

  try {
    const res = await fetch('/api/v1/contacts/import-vcard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ directory: 'data/vcards' }),
    });

    if (res.ok) {
      const data = await res.json();
      (data.details || []).forEach(d => logToEuterpeTerminal(d, d.startsWith('❌') ? 'error' : d.startsWith('⚠️') ? 'warning' : 'success'));
      logToEuterpeTerminal(`🎉 Total: ${data.imported_count} novos inseridos, ${data.updated_count} atualizados.`, 'success');
      showToast(`Ingestão concluída: +${data.imported_count} novos contatos!`);
      setEuterpeStatus('CONCLUÍDO', 'badge-success');
      await loadContacts();
      loadStats();
      loadGraphData();
    } else {
      const err = await res.json().catch(() => ({}));
      logToEuterpeTerminal(`❌ Erro: ${err.detail || res.statusText}`, 'error');
      setEuterpeStatus('ERRO', 'badge-danger');
    }
  } catch (err) {
    logToEuterpeTerminal(`❌ Erro de conexão: ${err}`, 'error');
    setEuterpeStatus('ERRO', 'badge-danger');
  }
}
window.handleEuterpeImportDirectory = handleEuterpeImportDirectory;

// 3. Deduplicação e Fusão de Contatos
async function handleEuterpeDeduplicate() {
  setEuterpeStatus('DEDUPLICANDO...', 'badge-warning');
  logToEuterpeTerminal('🧹 Executando deduplicação, higienização e fusão canônica...', 'info');

  try {
    const res = await fetch('/api/v1/contacts/deduplicate', {
      method: 'POST',
    });

    if (res.ok) {
      const data = await res.json();
      const count = data.contacts_merged_count || 0;
      logToEuterpeTerminal(`✨ Deduplicação concluída: ${count} contatos duplicados fundidos.`, 'success');
      (data.merged_pairs || []).forEach(p => {
        logToEuterpeTerminal(`  ➔ Canônico: "${p.canonical_name}" ⟵ Mesclado: "${p.merged_name}"`, 'info');
      });
      showToast(`Deduplicação: ${count} contatos mesclados!`);
      setEuterpeStatus('CONCLUÍDO', 'badge-success');
      await loadContacts();
      loadStats();
      loadGraphData();
    } else {
      const err = await res.json().catch(() => ({}));
      logToEuterpeTerminal(`❌ Erro na deduplicação: ${err.detail || res.statusText}`, 'error');
      setEuterpeStatus('ERRO', 'badge-danger');
    }
  } catch (err) {
    logToEuterpeTerminal(`❌ Erro de conexão: ${err}`, 'error');
    setEuterpeStatus('ERRO', 'badge-danger');
  }
}
window.handleEuterpeDeduplicate = handleEuterpeDeduplicate;

// 4. Sincronização de Avatares e PushNames (Evolution API)
async function handleEuterpeSyncAvatars() {
  setEuterpeStatus('SINCRONIZANDO FOTOS...', 'badge-warning');
  logToEuterpeTerminal('📸 Conectando à Evolution API para buscar fotos de perfil e nomes...', 'info');

  try {
    const res = await fetch('/api/v1/contacts/sync-avatars', {
      method: 'POST',
    });

    if (res.ok) {
      const data = await res.json();
      (data.details || []).forEach(d => logToEuterpeTerminal(d, d.startsWith('❌') ? 'error' : 'success'));
      logToEuterpeTerminal(`🎉 Sincronização concluída: ${data.updated_avatars} fotos e ${data.updated_names} nomes atualizados.`, 'success');
      showToast(`Avatares: ${data.updated_avatars} fotos atualizadas!`);
      setEuterpeStatus('CONCLUÍDO', 'badge-success');
      await loadContacts();
      loadStats();
    } else {
      const err = await res.json().catch(() => ({}));
      logToEuterpeTerminal(`❌ Erro ao buscar fotos: ${err.detail || res.statusText}`, 'error');
      setEuterpeStatus('ERRO', 'badge-danger');
    }
  } catch (err) {
    logToEuterpeTerminal(`❌ Erro de conexão: ${err}`, 'error');
    setEuterpeStatus('ERRO', 'badge-danger');
  }
}
window.handleEuterpeSyncAvatars = handleEuterpeSyncAvatars;

// 5. Pipeline Mestre Completo (vCard + Dedup + Avatares + Grafo)
async function handleEuterpeFullPipeline() {
  setEuterpeStatus('EXECUTANDO PIPELINE...', 'badge-warning');
  logToEuterpeTerminal('🚀 Disparando Pipeline Mestre de Contatos...', 'info');

  try {
    const res = await fetch('/api/v1/contacts/pipeline', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ directory: 'data/vcards' }),
    });

    if (res.ok) {
      const data = await res.json();
      (data.details || []).forEach(d => {
        if (d.includes('===')) {
          logToEuterpeTerminal(d, 'info');
        } else if (d.startsWith('❌')) {
          logToEuterpeTerminal(d, 'error');
        } else if (d.startsWith('⚠️')) {
          logToEuterpeTerminal(d, 'warning');
        } else {
          logToEuterpeTerminal(d, 'success');
        }
      });
      showToast('🎉 Pipeline Mestre concluído com sucesso!');
      setEuterpeStatus('CONCLUÍDO', 'badge-success');
      await loadContacts();
      loadStats();
      loadGraphData();
      renderMessages();
    } else {
      const err = await res.json().catch(() => ({}));
      logToEuterpeTerminal(`❌ Falha no Pipeline: ${err.detail || res.statusText}`, 'error');
      setEuterpeStatus('ERRO', 'badge-danger');
    }
  } catch (err) {
    logToEuterpeTerminal(`❌ Erro de conexão no Pipeline: ${err}`, 'error');
    setEuterpeStatus('ERRO', 'badge-danger');
  }
}
window.handleEuterpeFullPipeline = handleEuterpeFullPipeline;

// ==========================================
// 6. Gerenciamento Dinâmico de Modelos de IA (ModelRegistry)
// ==========================================
async function openAiModelsModal() {
  const modal = document.getElementById('modal-ai-models');
  if (!modal) return;
  modal.classList.add('active');
  await loadAiModelsRegistry();
}
window.openAiModelsModal = openAiModelsModal;

function closeAiModelsModal() {
  const modal = document.getElementById('modal-ai-models');
  if (modal) modal.classList.remove('active');
}
window.closeAiModelsModal = closeAiModelsModal;

async function loadAiModelsRegistry() {
  try {
    const res = await fetch('/ai/models');
    if (!res.ok) return;
    const data = await res.json();

    const active = data.active_models || {};
    const setVal = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.value = val || '';
    };

    setVal('model-select-revise', active.revise || 'gemini-3.1-flash-lite');
    setVal('model-select-extract', active.extract || 'gemini-3.1-flash-lite');
    setVal('model-select-summarize', active.summarize || 'gemini-3.1-flash-lite');
    setVal('model-select-weekly', active.weekly || 'gemini-3.1-flash-lite');
    setVal('model-select-hermes', active.hermes || 'gemini-3.1-flash-lite');
    setVal('model-select-embedding', active.embedding || 'gemini-embedding-001');

    const chkAuto = document.getElementById('chk-auto-adopt-lite');
    if (chkAuto) chkAuto.checked = Boolean(data.auto_adopt_best_lite);

    const lblDisc = document.getElementById('ai-models-last-discovery');
    if (lblDisc) {
      if (data.last_discovery_at) {
        const dt = new Date(data.last_discovery_at);
        lblDisc.textContent = `Última varredura: ${dt.toLocaleDateString()} ${dt.toLocaleTimeString()}`;
      } else {
        lblDisc.textContent = 'Nenhuma varredura recente executada.';
      }
    }

    renderDiscoveredModelsTags(data.discovered_models || []);
  } catch (err) {
    console.error('Erro ao carregar registro de modelos de IA:', err);
  }
}

function renderDiscoveredModelsTags(models) {
  const container = document.getElementById('discovered-models-tags');
  if (!container) return;

  if (!models || models.length === 0) {
    container.innerHTML = '<span class="text-muted">Clique em "Varredura de Modelos Agora" para mapear os modelos da API.</span>';
    return;
  }

  container.innerHTML = models.map(m => {
    const isRec = m.is_recommended ? '⭐ ' : '';
    const tierBadge = m.tier === 'LITE' ? 'badge-success' : (m.tier === 'FLASH' ? 'badge-info' : 'badge-warning');
    return `
      <span class="badge ${tierBadge}" style="cursor: pointer; padding: 0.35rem 0.6rem;" onclick="window.applyModelToActiveInputs('${m.name}', '${m.tier}')" title="Score: ${m.cost_efficiency_score} | ${m.description}">
        ${isRec}<strong>${m.name}</strong> <small>(${m.tier})</small>
      </span>
    `;
  }).join('');
}

function applyModelToActiveInputs(modelName, tier) {
  if (tier === 'EMBEDDING') {
    const el = document.getElementById('model-select-embedding');
    if (el) el.value = modelName;
    showToast(`Modelo de embedding alterado para: ${modelName}`);
  } else if (tier === 'LITE') {
    const r = document.getElementById('model-select-revise');
    const e = document.getElementById('model-select-extract');
    if (r) r.value = modelName;
    if (e) e.value = modelName;
    showToast(`Modelo Lite aplicado para Revisão e Extração: ${modelName}`);
  } else {
    const s = document.getElementById('model-select-summarize');
    const w = document.getElementById('model-select-weekly');
    const h = document.getElementById('model-select-hermes');
    if (s) s.value = modelName;
    if (w) w.value = modelName;
    if (h) h.value = modelName;
    showToast(`Modelo aplicado para Síntese e RAG: ${modelName}`);
  }
}
window.applyModelToActiveInputs = applyModelToActiveInputs;

async function runAiModelDiscovery() {
  const btn = document.getElementById('btn-discover-models');
  if (btn) {
    btn.disabled = true;
    btn.textContent = '⏳ Varrendo API do Gemini...';
  }

  try {
    const res = await fetch('/ai/models/discover?auto_adopt=true', { method: 'POST' });
    if (res.ok) {
      const data = await res.json();
      showToast(`✨ Varredura concluída: ${data.discovered_count || 0} modelos mapeados!`);
      await loadAiModelsRegistry();
    } else {
      const err = await res.json().catch(() => ({}));
      showToast(`❌ Falha na varredura: ${err.message || res.statusText}`);
    }
  } catch (err) {
    showToast(`❌ Erro ao conectar com API de IA: ${err}`);
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = '🔍 Varredura de Modelos Agora';
    }
  }
}
window.runAiModelDiscovery = runAiModelDiscovery;

async function saveAiModelsConfig(event) {
  if (event) event.preventDefault();

  const getVal = id => {
    const el = document.getElementById(id);
    return el ? el.value.trim() : '';
  };

  const chkAuto = document.getElementById('chk-auto-adopt-lite');

  const updates = {
    revise: getVal('model-select-revise'),
    extract: getVal('model-select-extract'),
    summarize: getVal('model-select-summarize'),
    weekly: getVal('model-select-weekly'),
    hermes: getVal('model-select-hermes'),
    embedding: getVal('model-select-embedding'),
  };

  try {
    const res = await fetch('/ai/models/active', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        updates: updates,
        auto_adopt: chkAuto ? chkAuto.checked : true,
      }),
    });

    if (res.ok) {
      showToast('💾 Modelos de IA atualizados com sucesso na VPS!');
      closeAiModelsModal();
    } else {
      const err = await res.json().catch(() => ({}));
      showToast(`❌ Erro ao salvar modelos: ${err.detail || res.statusText}`);
    }
  } catch (err) {
    showToast(`❌ Erro de conexão: ${err}`);
  }
}
window.saveAiModelsConfig = saveAiModelsConfig;


