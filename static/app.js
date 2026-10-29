const queryInput = document.getElementById('query-input');
const graphElement = document.getElementById('graph-canvas');
let graph = null;
let relationshipChart = null;
let relationshipBars = null;
let noticeTimeout;
let initialSearchStarted = false;

function showNotice(message) {
    const notice = document.getElementById('notice');
    notice.textContent = message;
    notice.classList.add('visible');
    clearTimeout(noticeTimeout);
    noticeTimeout = setTimeout(() => notice.classList.remove('visible'), 4200);
}

async function getJson(url, options) {
    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || `Request failed (${response.status})`);
    return data;
}

async function loadStats() {
    try {
        const data = await getJson('/api/stats');
        document.getElementById('status-dot').className = 'status-dot online';
        document.getElementById('connection-label').textContent = `${data.database} · connected`;
        document.getElementById('metric-documents').textContent = data.documents.toLocaleString();
        document.getElementById('metric-edges').textContent = data.edges.toLocaleString();
        document.getElementById('metric-entities').textContent = data.entity_mentions.toLocaleString();
        document.getElementById('metric-indexes').innerHTML = `${data.indexes} <small>${data.ping_ms} ms</small>`;
        document.getElementById('refresh-note').textContent = `PING ${data.ping_ms} MS · REFRESHED JUST NOW`;
        renderEntities(data.top_entities);
        renderRelationshipCharts(data.relationships);
        if (data.documents && !initialSearchStarted) {
            initialSearchStarted = true;
            await search(queryInput.value);
        }
    } catch (error) {
        document.getElementById('status-dot').className = 'status-dot offline';
        document.getElementById('connection-label').textContent = 'MongoDB unavailable';
        document.getElementById('refresh-note').textContent = 'METRICS UNAVAILABLE';
        showNotice(error.message);
    }
}

function renderEntities(entities) {
    const list = document.getElementById('entity-list');
    list.replaceChildren();
    if (!entities.length) {
        const empty = document.createElement('div');
        empty.className = 'entity-item muted';
        empty.textContent = 'No entity mentions indexed yet';
        list.append(empty);
        return;
    }
    for (const entity of entities) {
        const button = document.createElement('button');
        button.className = 'entity-item';
        button.type = 'button';
        const name = document.createElement('span');
        name.className = 'entity-name';
        name.textContent = entity.name;
        const count = document.createElement('span');
        count.className = 'entity-count';
        count.textContent = `${entity.mentions}×`;
        button.append(name, count);
        button.addEventListener('click', () => search(entity.name));
        list.append(button);
    }
}

function renderRelationshipCharts(relationships) {
    const labels = relationships.map(item => item.type.replaceAll('_', ' ').toLowerCase());
    const values = relationships.map(item => item.count);
    const palette = ['#c9ef6b', '#e7735c', '#69c5bb', '#e1b660'];
    if (relationshipChart) relationshipChart.destroy();
    relationshipChart = new Chart(document.getElementById('relationship-chart'), {
        type: 'doughnut',
        data: { labels, datasets: [{ data: values, backgroundColor: palette, borderWidth: 0, hoverOffset: 4 }] },
        options: { maintainAspectRatio: false, cutout: '68%', plugins: { legend: { position: 'right', labels: { color: '#667168', boxWidth: 8, boxHeight: 8, padding: 9, font: { family: 'DM Mono', size: 9 } } } } }
    });
    if (relationshipBars) relationshipBars.destroy();
    relationshipBars = new Chart(document.getElementById('relationship-bars'), {
        type: 'bar',
        data: { labels, datasets: [{ data: values, backgroundColor: palette, borderRadius: 3, barThickness: 13 }] },
        options: {
            indexAxis: 'y', maintainAspectRatio: false,
            plugins: { legend: { display: false }, tooltip: { displayColors: false } },
            scales: {
                x: { beginAtZero: true, grid: { color: '#ecece4' }, ticks: { color: '#7b817b', font: { family: 'DM Mono', size: 9 }, precision: 0 } },
                y: { grid: { display: false }, ticks: { color: '#59635b', font: { family: 'DM Mono', size: 9 } } }
            }
        }
    });
    document.getElementById('relationship-total').textContent = `${values.reduce((sum, value) => sum + value, 0).toLocaleString()} EDGES`;
}

function renderGraph(data) {
    const anchorId = data.nodes.find(node => node.val === 25)?.id;
    const elements = data.nodes.map(node => ({
        data: { id: node.id, label: node.label, type: node.type, size: node.val, anchor: node.id === anchorId }
    }));
    for (const link of data.links) {
        elements.push({ data: { id: `${link.source}|${link.target}|${link.label}`, source: link.source, target: link.target, label: link.label } });
    }
    if (graph) graph.destroy();
    graph = cytoscape({
        container: graphElement,
        elements,
        minZoom: 0.25,
        maxZoom: 2.5,
        style: [
            { selector: 'node', style: { 'background-color': '#e7735c', 'label': 'data(label)', 'color': '#e7eee4', 'font-family': 'DM Mono', 'font-size': 9, 'text-wrap': 'wrap', 'text-max-width': 105, 'text-valign': 'bottom', 'text-margin-y': 7, 'width': 'mapData(size, 12, 25, 17, 35)', 'height': 'mapData(size, 12, 25, 17, 35)', 'border-width': 1, 'border-color': '#f4f3ec' } },
            { selector: 'node[type = "document"]', style: { 'background-color': '#c9ef6b', 'color': '#eef4e8' } },
            { selector: 'node[?anchor]', style: { 'border-width': 3, 'border-color': '#ffffff', 'width': 38, 'height': 38, 'font-size': 10, 'font-weight': 500 } },
            { selector: 'edge', style: { 'width': 1, 'line-color': '#688075', 'target-arrow-color': '#688075', 'target-arrow-shape': 'triangle', 'arrow-scale': 0.7, 'curve-style': 'bezier', 'opacity': 0.72 } },
            { selector: ':selected', style: { 'overlay-color': '#c9ef6b', 'overlay-opacity': 0.16 } }
        ],
        layout: { name: 'cose', animate: true, animationDuration: 500, nodeRepulsion: 7000, idealEdgeLength: 95, padding: 38 }
    });
    graph.on('tap', 'node', event => {
        const node = event.target;
        if (!node.data('anchor')) {
            queryInput.value = node.data('label');
            search(node.data('label'));
        }
    });
    document.getElementById('graph-empty').hidden = data.nodes.length > 0;
    document.getElementById('graph-counts').textContent = `${data.nodes.length} nodes · ${data.links.length} links`;
    document.getElementById('graph-caption').textContent = `Cosine similarity ${(data.anchor_score * 100).toFixed(1)}% · ${data.depth}-hop traversal`;
    document.getElementById('graph-hint').textContent = `${data.query_time_ms} ms · Select a node to recenter`;
    document.getElementById('anchor-title').textContent = data.anchor_title;
    document.getElementById('anchor-excerpt').textContent = data.anchor_excerpt;
    document.getElementById('anchor-score').textContent = `${(data.anchor_score * 100).toFixed(1)}% COSINE`;
    document.getElementById('anchor-time').textContent = `${data.query_time_ms} ms · ${data.depth} hops`;
}

async function search(intent) {
    const cleanIntent = intent.trim();
    if (!cleanIntent) {
        showNotice('Enter a topic or entity to search.');
        return;
    }
    const button = document.getElementById('query-button');
    button.disabled = true;
    button.textContent = '…';
    document.getElementById('graph-caption').textContent = 'Finding the closest vector match…';
    try {
        const depth = document.getElementById('depth-select').value;
        const data = await getJson(`/api/query?intent=${encodeURIComponent(cleanIntent)}&depth=${depth}`);
        if (data.status !== 'success') throw new Error(data.message || 'No matching document found.');
        renderGraph(data);
    } catch (error) {
        const noRelevantData = error.message.startsWith('No relevant data found');
        document.getElementById('graph-caption').textContent = noRelevantData
            ? 'No relevant data found'
            : 'Search could not be completed';
        if (noRelevantData) {
            if (graph) graph.destroy();
            graph = null;
            graphElement.replaceChildren();
            document.getElementById('graph-empty').hidden = false;
            document.getElementById('graph-counts').textContent = '0 nodes · 0 links';
            document.getElementById('graph-hint').textContent = 'Try a different search';
            document.getElementById('anchor-title').textContent = 'No relevant data found';
            document.getElementById('anchor-excerpt').textContent = 'No indexed passage matched this search closely enough.';
            document.getElementById('anchor-score').textContent = 'NO MATCH';
            document.getElementById('anchor-time').textContent = '';
        }
        showNotice(error.message);
    } finally {
        button.disabled = false;
        button.textContent = 'Find';
    }
}

document.getElementById('query-form').addEventListener('submit', event => {
    event.preventDefault();
    search(queryInput.value);
});

document.getElementById('ingest-button').addEventListener('click', async event => {
    const button = event.currentTarget;
    const limit = document.getElementById('ingest-limit').value;
    button.disabled = true;
    button.textContent = 'Streaming…';
    showNotice(`Streaming up to ${Number(limit).toLocaleString()} records. This can take several minutes.`);
    try {
        const result = await getJson(`/api/ingest?limit=${limit}`, { method: 'POST' });
        showNotice(`Indexed ${result.count.toLocaleString()} documents and ${result.edges.toLocaleString()} graph edges.`);
        await loadStats();
        await search(queryInput.value);
    } catch (error) {
        showNotice(`Ingestion failed: ${error.message}`);
        await loadStats();
    } finally {
        button.disabled = false;
        button.textContent = '↧  Stream data';
    }
});

loadStats();
setInterval(loadStats, 15000);
