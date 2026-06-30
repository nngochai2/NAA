/* ── Alpine.js root component ── */
function vaultApp() {
  return {

    // ── Screen ──────────────────────────────────────────────────────────────
    screen: localStorage.getItem('kg_screen') || 'setup',

    // ── Vault state ──────────────────────────────────────────────────────────
    vault: { connected: false, path: '', display_name: '', folder_count: 0, document_count: 0 },
    vaultPathInput: '',
    connecting:     false,
    connectError:   '',

    // ── Tree state ───────────────────────────────────────────────────────────
    tree:        null,
    expandedIds: new Set(),
    scanning:    false,

    // ── Selection state ──────────────────────────────────────────────────────
    selection: { ids: new Set(), count: 0, total_docs: 0 },

    // ── Compliance state ─────────────────────────────────────────────────────
    compliance: { scanned: false, pct: 0, compliant: 0, legacy: 0, unrecognized: 0 },
    complianceRows: [],   // [{folder, pass, warn, fail}]

    // ── Processing state ─────────────────────────────────────────────────────
    dryRun:         false,
    showClearModal: false,
    job: {
      status: 'idle',    // idle | in_progress | completed | failed | cancelled
      id: null, pct: 0, processed: 0, failed: 0, total: 0,
      eta: 0, current_folder: '', entities: 0, relationships: 0,
      duration: 0, error: '', failed_docs: [],
    },
    elapsed: 0,
    _elapsedTimer: null,

    // ── Terminal log ─────────────────────────────────────────────────────────
    logLines: [],

    // ── Dashboard state ──────────────────────────────────────────────────────
    dashSearch:      '',
    selectedFolder:  null,

    // ── Neo4j state ──────────────────────────────────────────────────────────
    neo4j: {
      uri:      '',
      user:     'neo4j',
      password: '',
      status:   'idle',   // idle | ok | err
      error:    '',
      testing:  false,
    },

    // ── MCP Servers state ────────────────────────────────────────────────────
    mcp: {
      servers:    [],
      selected:   null,
      configEdit: { host: '', port: '' },
      creds:      {},       // { [serverName]: [{key, label, secret, placeholder, is_set}] }
      credEdit:   {},       // { ['serverName.KEY']: value }
      credError:  '',
      credOk:     false,
      busy:       '',       // server name currently acting, or 'all'
      error:      '',
      _pollTimer: null,
    },

    // ── Settings state ───────────────────────────────────────────────────────
    settings: {
      webapp: { fields: [], values: {}, saving: false, error: '', ok: false },
      password: { current: '', new: '', confirm: '', saving: false, error: '', ok: false },
    },

    // ── Spec Docs state ──────────────────────────────────────────────────────
    docs: {
      rules:          [],
      rulePath:       '',
      customRulePath: '',
      docxPath:       '',
      sourceLabel:    '',
      flowName:       '',
      ucId:           '',
      docType:        '',
      status:         'idle',  // idle | parsing | done | error
      items:          [],
      contextLength:  0,
      ruleName:       '',
      nodeLabel:      '',
      ingested:        false,
      hierarchyBuilt:  false,
      error:           '',
      selectedItem:    null,
    },

    // ── Lifecycle ────────────────────────────────────────────────────────────
    async init() {
      _appRef = this;  // make app() work for inline x-html event handlers (Alpine 3 has no __x)
      this.$watch('screen', v => {
        localStorage.setItem('kg_screen', v);
        if (v === 'docs' && this.docs.rules.length === 0) this.loadRules();
        if (v === 'mcp') { this.loadMcpServers(); this.mcpStartPolling(); }
        else { this.mcpStopPolling(); }
        if (v === 'settings') this.loadWebappCreds();
      });
      try {
        const r = await fetch('/api/vault/current');
        if (r.status === 401) { window.location = '/login'; return; }
        if (r.ok) {
          const d = await r.json();
          if (d.vault) {
            this.vault.connected    = true;
            this.vault.path         = d.vault.path;
            this.vault.display_name = d.vault.display_name;
            await this.loadTree();
            await this.loadSelection();
          }
        }
      } catch (_) {}
      if (this.screen === 'mcp')      { await this.loadMcpServers(); this.mcpStartPolling(); }
      if (this.screen === 'settings') { await this.loadWebappCreds(); }
    },

    // ── Vault ────────────────────────────────────────────────────────────────
    async connectVault() {
      this.connectError = '';
      if (!this.vaultPathInput.trim()) return;
      this.connecting = true;
      try {
        const r = await fetch('/api/vault/connect', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ vault_path: this.vaultPathInput.trim() }),
        });
        const d = await r.json();
        if (!r.ok) { this.connectError = d.detail?.message || 'Connection failed.'; return; }
        this.vault.connected      = true;
        this.vault.path           = d.vault.path;
        this.vault.display_name   = d.vault.display_name;
        this.vault.folder_count   = d.folder_count;
        this.vault.document_count = d.document_count;
        this.vaultPathInput = '';
        await this.loadTree();
      } catch (_) {
        this.connectError = 'Could not reach server.';
      } finally {
        this.connecting = false;
      }
    },

    // ── Neo4j ────────────────────────────────────────────────────────────────
    async testNeo4j() {
      if (!this.neo4j.uri) return;
      this.neo4j.testing = true;
      this.neo4j.status  = 'idle';
      this.neo4j.error   = '';
      try {
        const r = await fetch('/api/neo4j/test', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            neo4j_uri:      this.neo4j.uri,
            neo4j_user:     this.neo4j.user,
            neo4j_password: this.neo4j.password,
          }),
        });
        const d = await r.json();
        if (r.ok && d.ok) {
          this.neo4j.status = 'ok';
        } else {
          this.neo4j.status = 'err';
          this.neo4j.error  = d.detail?.message || 'Connection failed.';
        }
      } catch (_) {
        this.neo4j.status = 'err';
        this.neo4j.error  = 'Could not reach server.';
      } finally {
        this.neo4j.testing = false;
      }
    },

    async changeVault() {
      await fetch('/api/vault/disconnect', { method: 'POST' });
      this.vault      = { connected: false, path: '', display_name: '', folder_count: 0, document_count: 0 };
      this.tree       = null;
      this.selection  = { ids: new Set(), count: 0, total_docs: 0 };
      this.compliance = { scanned: false, pct: 0, compliant: 0, legacy: 0, unrecognized: 0 };
      this.complianceRows = [];
      this.resetJob();
    },

    // ── Tree ─────────────────────────────────────────────────────────────────
    async loadTree() {
      try {
        const r = await fetch('/api/tree/structure');
        if (r.ok) {
          const d = await r.json();
          this.tree = d.tree;
          if (this.tree?.children) {
            this.tree.children.forEach(c => this.expandedIds.add(c.id));
          }
        }
      } catch (_) {}
    },

    async refreshTree() {
      await fetch('/api/tree/refresh', { method: 'POST' });
      await this.loadTree();
      await this.loadSelection();
    },

    async scanCompliance() {
      this.scanning = true;
      try {
        await fetch('/api/tree/scan-compliance', { method: 'POST' });
        await this.loadTree();
        await this._updateComplianceSummary();
        this._buildComplianceRows();
      } finally {
        this.scanning = false;
      }
    },

    _buildComplianceRows() {
      if (!this.tree) return;
      const rows = [];
      const walk = (node) => {
        if (node.compliance_status === 'SCANNED' && this.selection.ids.has(node.id)) {
          rows.push({
            folder: node.path || node.name,
            pass:   node.compliant_docs    || 0,
            warn:   node.legacy_docs       || 0,
            fail:   node.unrecognized_docs || 0,
          });
        }
        if (node.children) node.children.forEach(walk);
      };
      if (this.tree.children) this.tree.children.forEach(walk);
      this.complianceRows = rows;
    },

    toggleExpand(id) {
      if (this.expandedIds.has(id)) this.expandedIds.delete(id);
      else this.expandedIds.add(id);
    },

    // ── Render tree (returns full HTML string) ────────────────────────────────
    renderTree() {
      if (!this.tree?.children) return '';
      return this.tree.children.map(c => this._renderNode(c, 0)).join('');
    },

    _renderNode(node, depth) {
      const isExpanded  = this.expandedIds.has(node.id);
      const isSelected  = this.selection.ids.has(node.id);
      const hasChildren = node.children && node.children.length > 0;
      const indent      = 12 + depth * 16;

      const ck = `<div class="ck ${isSelected ? 'on' : ''}"
          onclick="event.stopPropagation();app().toggleFolder('${node.id}')"
          style="margin:0 auto">
          ${isSelected ? '<span style="color:#000;font-size:9px;line-height:1">✓</span>' : ''}
        </div>`;

      const arrow = hasChildren
        ? `<span onclick="event.stopPropagation();app().toggleExpand('${node.id}')"
             style="color:var(--text3);font-size:9px;cursor:pointer;user-select:none;width:10px;display:inline-block">
             ${isExpanded ? '▾' : '▸'}</span>`
        : `<span style="width:10px;display:inline-block"></span>`;

      const badge = isSelected
        ? `<span class="badge badge-accent">SELECTED</span>`
        : `<span class="badge badge-default">SKIP</span>`;

      const row = `<div class="fr ${isSelected ? 'selected' : ''}"
          style="padding:5px 12px 5px ${indent}px"
          onclick="app().toggleFolder('${node.id}')">
          ${ck}
          <div style="display:flex;align-items:center;gap:6px;padding-left:8px;overflow:hidden">
            ${arrow}
            <span style="font-size:11px;color:${isSelected ? 'var(--text)' : 'var(--text2)'}">
              ${this._esc(node.name)}/</span>
            <span style="font-size:10px;color:var(--text3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
              ${this._esc(node.path || '')}</span>
          </div>
          <div style="font-size:10px;color:var(--text3);text-align:right">${node.document_count}</div>
          <div style="text-align:right;padding-right:4px">${badge}</div>
        </div>`;

      let children = '';
      if (hasChildren && isExpanded) {
        children = node.children.map(c => this._renderNode(c, depth + 1)).join('');
      }
      return row + children;
    },

    _esc(s) {
      return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },

    // ── Selection ────────────────────────────────────────────────────────────
    async loadSelection() {
      try {
        const r = await fetch('/api/selection/current');
        if (r.ok) {
          const d = await r.json();
          if (d.selection) {
            this.selection.ids       = new Set(d.selection.selected_folder_ids);
            this.selection.count     = d.selection.selected_folder_ids.length;
            this.selection.total_docs= d.selection.total_selected_docs;
            this._applyComplianceFromSelection(d.selection);
          }
        }
      } catch (_) {}
    },

    async toggleFolder(folderId) {
      try {
        const r = await fetch(`/api/selection/toggle/${folderId}`, { method: 'POST' });
        if (r.ok) {
          const d = await r.json();
          if (d.is_selected) this.selection.ids.add(folderId);
          else               this.selection.ids.delete(folderId);
          this.selection.count      = d.total_selected_folders;
          this.selection.total_docs = d.total_selected_docs;
          this.tree = { ...this.tree };
        }
      } catch (_) {}
    },

    async selectAll() {
      const r = await fetch('/api/selection/select-all', { method: 'POST' });
      if (r.ok) {
        const d = await r.json();
        this.selection.count      = d.total_selected_folders;
        this.selection.total_docs = d.total_selected_docs;
        await this.loadSelection();
        this.tree = { ...this.tree };
      }
    },

    async clearAll() {
      const r = await fetch('/api/selection/clear-all', { method: 'POST' });
      if (r.ok) {
        this.selection.ids        = new Set();
        this.selection.count      = 0;
        this.selection.total_docs = 0;
        this.tree = { ...this.tree };
      }
    },

    async _updateComplianceSummary() {
      if (!this.selection.count) return;
      try {
        const r = await fetch('/api/compliance/report?scope=selection');
        if (r.ok) {
          const d = await r.json();
          this.compliance.scanned      = true;
          this.compliance.pct          = d.compliance_percentage;
          this.compliance.compliant    = d.compliance_stats.compliant;
          this.compliance.legacy       = d.compliance_stats.legacy;
          this.compliance.unrecognized = d.compliance_stats.unrecognized;
        }
      } catch (_) {}
    },

    _applyComplianceFromSelection(sel) {
      if (!sel) return;
      if (sel.total_selected_docs > 0 && sel.total_selected_compliant !== undefined) {
        this.compliance.scanned      = true;
        this.compliance.pct          = sel.compliance_percentage;
        this.compliance.compliant    = sel.total_selected_compliant;
        this.compliance.legacy       = sel.total_selected_legacy;
        this.compliance.unrecognized = sel.total_selected_unrecognized;
      }
    },

    // ── Processing ───────────────────────────────────────────────────────────
    async startProcessing(clearGraph = false) {
      if (this.selection.count === 0) return;

      this.job = {
        status: 'in_progress', id: null, pct: 0, processed: 0, failed: 0,
        total: 0, eta: 0, current_folder: '', entities: 0, relationships: 0,
        duration: 0, error: '', failed_docs: [],
      };
      this.logLines = [];
      this.elapsed  = 0;

      this._elapsedTimer = setInterval(() => { this.elapsed++; }, 1000);

      this._log('info', `◆ Starting graph build — vault: ${this.vault.path}`);
      this._log('dim',  `  Neo4j: ${this.neo4j.uri || '(server default)'} · user: ${this.neo4j.user || 'neo4j'}`);
      this._log('dim',  `  Mode: ${this.dryRun ? 'dry-run' : 'incremental'} · clear: ${clearGraph} · dry-run: ${this.dryRun}`);
      if (clearGraph) {
        this._log('warn', '  ⚠ Existing graph will be cleared before writing.');
      }

      try {
        const r = await fetch('/api/processing/start', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            dry_run:       this.dryRun,
            clear_graph:   clearGraph,
            neo4j_uri:      this.neo4j.uri      || undefined,
            neo4j_user:     this.neo4j.user     || undefined,
            neo4j_password: this.neo4j.password || undefined,
          }),
        });
        const d = await r.json();
        if (!r.ok) {
          this._stopElapsed();
          this.job.status = 'failed';
          this.job.error  = d.detail?.message || 'Failed to start.';
          this._log('err', `✗ ${this.job.error}`);
          return;
        }
        this.job.id    = d.job_id;
        this.job.total = d.total_documents_estimate;
        this._subscribeSSE(d.stream_url);
      } catch (_) {
        this._stopElapsed();
        this.job.status = 'failed';
        this.job.error  = 'Could not reach server.';
        this._log('err', '✗ Could not reach server.');
      }
    },

    _log(type, text) {
      this.logLines.push({ type, text });
      setTimeout(() => {
        const el = document.getElementById('log-body');
        if (el) el.scrollTop = el.scrollHeight;
      }, 0);
    },

    _stopElapsed() {
      if (this._elapsedTimer) { clearInterval(this._elapsedTimer); this._elapsedTimer = null; }
    },

    _subscribeSSE(url) {
      const es = new EventSource(url);
      this._es = es;

      let currentFolder  = null;
      let docCount       = 0;
      let wroteParseHdr  = false;

      es.addEventListener('graph_clearing', () => {
        this._log('warn', '  Clearing existing graph (MATCH (n) DETACH DELETE n) …');
      });

      es.addEventListener('processing_started', (e) => {
        const d = JSON.parse(e.data);
        this.job.total = d.total_documents;
        this._log('section', '── PHASE 1: VAULT SCAN ─────────────────────────────────────────');
      });

      es.addEventListener('folder_started', (e) => {
        const d = JSON.parse(e.data);
        this.job.current_folder = d.current_folder;
        if (d.current_folder !== currentFolder) {
          currentFolder = d.current_folder;
          docCount = 0;
          this._log('info', `  Scanning ${d.current_folder} …`);
        }
      });

      es.addEventListener('document_processed', (e) => {
        const d = JSON.parse(e.data);
        this.job.processed      = d.documents_processed_so_far;
        this.job.failed         = d.documents_failed_so_far;
        this.job.pct            = this.job.total > 0
          ? Math.round(this.job.processed / this.job.total * 100) : 0;
        this.job.eta            = d.estimated_time_remaining_seconds || 0;
        this.job.entities       = d.entities_created || 0;
        this.job.relationships  = d.relationships_created || 0;
        docCount++;

        if (!wroteParseHdr && d.documents_processed_so_far === 1) {
          wroteParseHdr = true;
          this._log('section', '── PHASE 2: PARSE & CLASSIFY ───────────────────────────────────');
        }
        if (docCount % 20 === 1) {
          this._log('dim', `  [${d.documents_processed_so_far}/${d.total_documents}] ${d.relative_path}`);
        }
      });

      es.addEventListener('processing_error', (e) => {
        const d = JSON.parse(e.data);
        this.job.failed = d.documents_failed_so_far;
        this.job.failed_docs.push({ filename: d.document, error: d.error_message });
        this._log('err', `  ⚠ ${d.document}: ${d.error_message}`);
      });

      es.addEventListener('processing_completed', (e) => {
        const d = JSON.parse(e.data);
        this._stopElapsed();
        this.job.status        = 'completed';
        this.job.pct           = 100;
        this.job.processed     = d.total_documents_processed;
        this.job.failed        = d.total_documents_failed;
        this.job.entities      = d.total_entities_created;
        this.job.relationships = d.total_relationships_created;
        this.job.duration      = d.duration_seconds;
        this.job.failed_docs   = d.failed_documents || [];

        this._log('section', '── PHASE 3: WRITE TO NEO4J ─────────────────────────────────────');
        this._log('ok',      `  ✓ ${d.total_entities_created.toLocaleString()} nodes upserted`);
        this._log('ok',      `  ✓ ${d.total_relationships_created.toLocaleString()} edges created`);
        this._log('section', '── COMPLETE ────────────────────────────────────────────────────');
        this._log('ok',      `✓ Graph build complete — ${d.total_documents_processed} docs · ${d.total_entities_created} nodes · ${d.total_relationships_created} edges · ${d.total_documents_failed} errors`);
        this._log('dim',     `  Elapsed: ${d.duration_seconds}s · Neo4j: bolt://localhost:7687`);
        es.close();
      });

      es.addEventListener('processing_failed', (e) => {
        const d = JSON.parse(e.data);
        this._stopElapsed();
        this.job.status = 'failed';
        this.job.error  = d.error_message;
        this._log('err', `✗ Processing failed: ${d.error_message}`);
        es.close();
      });

      es.addEventListener('processing_cancelled', () => {
        this._stopElapsed();
        this.job.status = 'cancelled';
        this._log('warn', '⚠ Processing cancelled by user.');
        es.close();
      });

      es.onerror = () => {};
    },

    async cancelProcessing() {
      if (!this.job.id) return;
      await fetch(`/api/processing/cancel/${this.job.id}`, { method: 'POST' });
      if (this._es) this._es.close();
      this._stopElapsed();
      this.job.status = 'cancelled';
    },

    resetJob() {
      if (this._es) this._es.close();
      this._stopElapsed();
      this.job = {
        status: 'idle', id: null, pct: 0, processed: 0, failed: 0,
        total: 0, eta: 0, current_folder: '', entities: 0,
        relationships: 0, duration: 0, error: '', failed_docs: [],
      };
      this.logLines = [];
      this.elapsed  = 0;
    },

    // ── Spec Docs ────────────────────────────────────────────────────────────
    async loadRules() {
      try {
        const r = await fetch('/api/docs/rules');
        if (r.ok) {
          const d = await r.json();
          this.docs.rules = d.rules;
          if (d.rules.length > 0 && !this.docs.rulePath) {
            this.docs.rulePath = d.rules[0].path;
          }
        }
      } catch (_) {}
    },

    _inferDocsMetadata(path) {
      if (!path) {
        this.docs.flowName = '';
        this.docs.ucId     = '';
        this.docs.docType  = '';
        return;
      }
      // Extract filename without extension, normalise separators to " - "
      const fname = path.replace(/\\/g, '/').split('/').pop().replace(/\.docx$/i, '')
                        .replace(/[_]+/g, ' ').replace(/\s*[-–]\s*/g, ' - ');
      // Split on " - " or fall back to whitespace tokens
      const parts = fname.includes(' - ') ? fname.split(' - ') : fname.split(/\s+/);
      if (parts.length < 1) return;

      let flow = '', ucId = '', docType = '';

      for (let i = 0; i < parts.length; i++) {
        const p = parts[i].trim();
        if (/^UC\d+$/i.test(p)) {
          ucId = p.toUpperCase();
          // Use the part before the UC token as the flow candidate
          if (!flow) flow = (parts[i - 1] || '').trim();
        }
        if (/^(SDD|FDD|CRF|UC)$/i.test(p) && p.toUpperCase() !== ucId) {
          docType = p.toUpperCase();
          if (!flow) flow = (parts[i - 1] || '').trim();
        }
      }

      // If a UC was detected but no explicit doc_type found, default to "UC"
      if (ucId && !docType) docType = 'UC';

      // Drop any part that looks like a bare project ID (e.g. PRJ00445)
      if (/^PRJ\d+$/i.test(flow)) flow = '';

      // Only fill fields that the user has not already typed something into
      if (flow    && !this.docs.flowName) this.docs.flowName = flow;
      if (ucId    && !this.docs.ucId)     this.docs.ucId     = ucId;
      if (docType && !this.docs.docType)  this.docs.docType  = docType;
    },

    async dryParseDoc() { await this._parseDoc(true); },
    async ingestDoc() {
      if (!this.docs.flowName.trim() || !this.docs.ucId.trim() || !this.docs.docType.trim()) {
        this.docs.status = 'error';
        this.docs.error  = 'Flow, UC ID, and Type are all required to build the graph hierarchy. Fill them in before ingesting.';
        return;
      }
      await this._parseDoc(false);
    },

    _docsRule() {
      return this.docs.rulePath === '__custom__' ? this.docs.customRulePath : this.docs.rulePath;
    },

    async _parseDoc(dryRun) {
      const rulePath = this._docsRule();
      if (!rulePath || !this.docs.docxPath.trim()) return;
      this.docs.status      = 'parsing';
      this.docs.error       = '';
      this.docs.selectedItem = null;
      if (dryRun) { this.docs.items = []; this.docs.ingested = false; }
      try {
        const r = await fetch('/api/docs/parse', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            docx_path:    this.docs.docxPath.trim(),
            rule_file:    rulePath,
            source_label: this.docs.sourceLabel.trim(),
            flow_name:    this.docs.flowName.trim(),
            uc_id:        this.docs.ucId.trim(),
            doc_type:     this.docs.docType.trim(),
            dry_run:      dryRun,
          }),
        });
        const d = await r.json();
        if (!r.ok) {
          this.docs.status = 'error';
          this.docs.error  = d.detail?.message || d.detail || 'Parse failed.';
          return;
        }
        this.docs.status        = 'done';
        this.docs.items         = d.items;
        this.docs.contextLength = d.context_length;
        this.docs.ruleName      = d.rule_name;
        this.docs.nodeLabel     = d.node_label;
        this.docs.ingested        = d.ingested;
        this.docs.hierarchyBuilt  = d.hierarchy_built ?? false;
        this.docs.error           = '';
      } catch (_) {
        this.docs.status = 'error';
        this.docs.error  = 'Could not reach server.';
      }
    },

    docsCategoryBreakdown() {
      const counts = {};
      for (const item of this.docs.items) {
        for (const cat of (item.candidate_categories || [])) {
          counts[cat] = (counts[cat] || 0) + 1;
        }
      }
      return counts;
    },

    // ── Phase tracker ─────────────────────────────────────────────────────────
    phaseState(idx) {
      const running   = this.job.status === 'in_progress';
      const completed = this.job.status === 'completed';
      const p         = this.job.pct;
      if (idx === 0) {
        if (this.job.processed > 0 || completed) return 'done';
        if (running) return 'running';
      }
      if (idx === 1) {
        if (p >= 100 || completed) return 'done';
        if (running && p > 0) return 'running';
      }
      if (idx === 2) {
        if (completed) return 'done';
        if (running && p >= 99) return 'running';
      }
      return 'idle';
    },

    // ── Dashboard ─────────────────────────────────────────────────────────────
    allFolders() {
      if (!this.tree) return [];
      const out = [];
      const walk = (n) => { out.push(n); if (n.children) n.children.forEach(walk); };
      if (this.tree.children) this.tree.children.forEach(walk);
      return out;
    },

    filteredFolders() {
      const q = this.dashSearch.trim().toLowerCase();
      return this.allFolders().filter(f =>
        !q || f.name.toLowerCase().includes(q) || (f.path || '').toLowerCase().includes(q)
      );
    },

    dashBreakdown() {
      const max = Math.max(this.job.processed, this.job.entities, this.job.relationships, 1);
      return [
        { label: 'Documents parsed',   count: this.job.processed },
        { label: 'Entities (nodes)',    count: this.job.entities },
        { label: 'Relationships',       count: this.job.relationships },
        { label: 'Documents failed',    count: this.job.failed },
      ].map(r => ({ ...r, pct: Math.round(r.count / max * 100) }));
    },

    complianceBadgeClass(folder) {
      if (!folder || folder.compliance_status !== 'SCANNED') return 'badge-default';
      const total = (folder.compliant_docs || 0) + (folder.legacy_docs || 0) + (folder.unrecognized_docs || 0);
      if (total === 0) return 'badge-default';
      const pct = Math.round((folder.compliant_docs || 0) / total * 100);
      return pct >= 80 ? 'badge-accent' : pct >= 50 ? 'badge-warn' : 'badge-err';
    },

    complianceBadgeLabel(folder) {
      if (!folder || folder.compliance_status !== 'SCANNED') return 'PENDING';
      const total = (folder.compliant_docs || 0) + (folder.legacy_docs || 0) + (folder.unrecognized_docs || 0);
      if (total === 0) return 'EMPTY';
      const pct = Math.round((folder.compliant_docs || 0) / total * 100);
      return `${pct}%`;
    },

    fmtNum(n) { return (n || 0).toLocaleString(); },
    fmtElapsed(s) { return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`; },

    // ── MCP Servers ──────────────────────────────────────────────────────────
    mcpStartPolling() {
      if (this.mcp._pollTimer) return;
      this.mcp._pollTimer = setInterval(() => this.loadMcpServers(), 5000);
    },

    mcpStopPolling() {
      if (this.mcp._pollTimer) { clearInterval(this.mcp._pollTimer); this.mcp._pollTimer = null; }
    },

    async loadMcpServers() {
      try {
        const r = await fetch('/api/mcp/servers');
        if (r.ok) {
          const d = await r.json();
          this.mcp.servers = d.servers;
        }
      } catch (_) {}
    },

    mcpSelect(name) {
      this.mcp.selected  = name;
      this.mcp.credError = '';
      this.mcp.credOk    = false;
      const s = this.mcpSelectedServer();
      if (s) { this.mcp.configEdit.host = s.host; this.mcp.configEdit.port = String(s.port); }
      this.loadMcpCreds(name);
    },

    mcpSelectedServer() {
      return this.mcp.servers.find(s => s.name === this.mcp.selected) || null;
    },

    async mcpAction(name, action) {
      this.mcp.busy  = name;
      this.mcp.error = '';
      try {
        const r = await fetch(`/api/mcp/${name}/${action}`, { method: 'POST' });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) {
          this.mcp.error = d.detail || `${action} failed`;
        } else {
          const idx = this.mcp.servers.findIndex(s => s.name === name);
          if (idx !== -1) this.mcp.servers[idx] = d;
          setTimeout(() => this.loadMcpServers(), 1000);
        }
      } catch (_) {
        this.mcp.error = 'Could not reach server.';
      } finally {
        this.mcp.busy = '';
      }
    },

    async mcpStartAll() {
      this.mcp.busy  = 'all';
      this.mcp.error = '';
      try {
        const r = await fetch('/api/mcp/start-all', { method: 'POST' });
        if (r.ok) {
          const d = await r.json().catch(() => ({}));
          if (d.servers) this.mcp.servers = d.servers;
          setTimeout(() => this.loadMcpServers(), 1000);
        }
      } catch (_) {
        this.mcp.error = 'Could not reach server.';
      } finally {
        this.mcp.busy = '';
      }
    },

    async mcpStopAll() {
      this.mcp.busy  = 'all';
      this.mcp.error = '';
      try {
        const r = await fetch('/api/mcp/stop-all', { method: 'POST' });
        if (r.ok) {
          const d = await r.json().catch(() => ({}));
          if (d.servers) this.mcp.servers = d.servers;
          setTimeout(() => this.loadMcpServers(), 1000);
        }
      } catch (_) {
        this.mcp.error = 'Could not reach server.';
      } finally {
        this.mcp.busy = '';
      }
    },

    async mcpSaveConfig(name) {
      this.mcp.busy  = name;
      this.mcp.error = '';
      try {
        const r = await fetch(`/api/mcp/${name}/config`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({
            host: this.mcp.configEdit.host,
            port: parseInt(this.mcp.configEdit.port, 10),
          }),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) {
          this.mcp.error = d.detail || 'Config save failed.';
        } else {
          const idx = this.mcp.servers.findIndex(s => s.name === name);
          if (idx !== -1) this.mcp.servers[idx] = d;
          setTimeout(() => this.loadMcpServers(), 1000);
        }
      } catch (_) {
        this.mcp.error = 'Could not reach server.';
      } finally {
        this.mcp.busy = '';
      }
    },

    async loadMcpCreds(name) {
      try {
        const r = await fetch(`/api/credentials/${name}`);
        if (r.ok) {
          const d = await r.json();
          this.mcp.creds = { ...this.mcp.creds, [name]: d.fields };
        }
      } catch (_) {}
    },

    async mcpSaveCreds(name) {
      this.mcp.busy      = name;
      this.mcp.credError = '';
      this.mcp.credOk    = false;
      const fields  = this.mcp.creds[name] || [];
      const payload = {};
      for (const f of fields) {
        const val = this.mcp.credEdit[`${name}.${f.key}`];
        if (val) payload[f.key] = val;
      }
      try {
        const r = await fetch(`/api/credentials/${name}`, {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ credentials: payload }),
        });
        const d = await r.json();
        if (!r.ok) {
          this.mcp.credError = d.detail?.message || 'Save failed.';
        } else {
          this.mcp.creds = { ...this.mcp.creds, [name]: d.fields };
          // Clear filled inputs after save
          for (const f of fields) { delete this.mcp.credEdit[`${name}.${f.key}`]; }
          this.mcp.credOk = true;
          setTimeout(() => { this.mcp.credOk = false; }, 3000);
        }
      } catch (_) {
        this.mcp.credError = 'Could not reach server.';
      } finally {
        this.mcp.busy = '';
        await this.loadMcpServers();
      }
    },

    // ── Settings ─────────────────────────────────────────────────────────────
    async loadWebappCreds() {
      try {
        const r = await fetch('/api/credentials/webapp');
        if (r.ok) {
          const d = await r.json();
          this.settings.webapp.fields = d.fields;
          this.settings.webapp.values = {};
        }
      } catch (_) {}
    },

    async saveWebappCreds() {
      this.settings.webapp.saving = true;
      this.settings.webapp.error  = '';
      this.settings.webapp.ok     = false;
      const payload = {};
      for (const f of this.settings.webapp.fields) {
        const val = this.settings.webapp.values[f.key];
        if (val) payload[f.key] = val;
      }
      try {
        const r = await fetch('/api/credentials/webapp', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ credentials: payload }),
        });
        const d = await r.json();
        if (!r.ok) {
          this.settings.webapp.error = d.detail?.message || 'Save failed.';
        } else {
          this.settings.webapp.fields = d.fields;
          this.settings.webapp.values = {};
          this.settings.webapp.ok     = true;
          setTimeout(() => { this.settings.webapp.ok = false; }, 3000);
        }
      } catch (_) {
        this.settings.webapp.error = 'Could not reach server.';
      } finally {
        this.settings.webapp.saving = false;
      }
    },

    async changePassword() {
      const pw = this.settings.password;
      pw.error = '';
      pw.ok    = false;
      if (!pw.current || !pw.new) { pw.error = 'All fields are required.'; return; }
      if (pw.new !== pw.confirm)  { pw.error = 'New passwords do not match.'; return; }
      if (pw.new.length < 8)      { pw.error = 'Password must be at least 8 characters.'; return; }
      pw.saving = true;
      try {
        const r = await fetch('/api/auth/change-password', {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body:    JSON.stringify({ current_password: pw.current, new_password: pw.new }),
        });
        const d = await r.json();
        if (!r.ok) {
          pw.error = d.detail?.message || 'Change failed.';
        } else {
          pw.current = ''; pw.new = ''; pw.confirm = '';
          pw.ok = true;
        }
      } catch (_) {
        pw.error = 'Could not reach server.';
      } finally {
        pw.saving = false;
      }
    },

    fmtUptime(s) {
      if (!s || s < 0) return '—';
      const h   = Math.floor(s / 3600);
      const m   = Math.floor((s % 3600) / 60);
      const sec = s % 60;
      if (h > 0) return `${h}h ${m}m`;
      if (m > 0) return `${m}m ${sec}s`;
      return `${sec}s`;
    },
  };
}

// Stable reference for inline event handlers in x-html rendered trees
let _appRef = null;
function app() { return _appRef; }

document.addEventListener('alpine:init', () => { Alpine.data('vaultApp', vaultApp); });
