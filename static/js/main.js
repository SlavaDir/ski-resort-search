// Render list of resorts as horizontal "tickets"
function renderList(resorts) {
    const list = document.getElementById('resortList');
    const countEl = document.getElementById('resultsCount');
    
    countEl.textContent = `${resorts.length} Resort${resorts.length !== 1 ? 's' : ''} Found`;

    if (resorts.length === 0) {
        list.innerHTML = `<div style="text-align:center; padding: 3rem; color: #6b7280;">No resorts match your search criteria.</div>`;
        return;
    }

    list.innerHTML = resorts.map(r => `
        <div class="resort-card" onclick="openModal('${r.slug}')">
            <div class="card-main">
                <p>${r.country} ${r.region ? `• ${r.region}` : ''}</p>
                <h3>${r.name}</h3>
            </div>
            <div class="card-metrics">
                <div class="metric-block">
                    <span class="metric-value">${r.total_km ? r.total_km + ' km' : '—'}</span>
                    <span class="metric-label">Trails</span>
                </div>
                <div class="metric-block">
                    <span class="metric-value">${r.day_pass_adult_eur ? '€' + r.day_pass_adult_eur : '—'}</span>
                    <span class="metric-label">Day Pass</span>
                </div>
            </div>
        </div>
    `).join('');
}

// Aviasales-style Multi-filter
function applyFilters() {
    const country = document.getElementById('filterCountry').value.toLowerCase();
    const maxPrice = parseFloat(document.getElementById('filterPrice').value) || Infinity;
    const minTrails = parseFloat(document.getElementById('filterTrails').value) || 0;

    const filtered = ALL_RESORTS.filter(r => {
        const passCountry = !country || r.country.toLowerCase() === country;
        
        // Handle nulls gracefully: if we filter by price, exclude null prices 
        // unless the user left the filter empty (Infinity).
        const price = r.day_pass_adult_eur || Infinity; 
        const passPrice = price <= maxPrice;

        const trails = r.total_km || 0;
        const passTrails = trails >= minTrails;

        return passCountry && passPrice && passTrails;
    });

    renderList(filtered);
}

// Modal Logic
function openModal(slug) {
    const resort = ALL_RESORTS.find(r => r.slug === slug);
    if (!resort) return;

    const modalBody = document.getElementById('modalBody');
    modalBody.innerHTML = `
        <p style="text-transform: uppercase; font-size: 0.8rem; color: #6b7280; margin:0;">${resort.country}</p>
        <h2 style="margin: 0 0 1rem 0;">${resort.name}</h2>
        ${resort.summary ? `<p style="margin-bottom: 1.5rem; line-height: 1.6;">${resort.summary}</p>` : ''}
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; background: #f7f9fa; padding: 1rem; border-radius: 8px;">
            <div><strong>Altitude:</strong> ${resort.base_m || '?'}m - ${resort.peak_m || '?'}m</div>
            <div><strong>Total Trails:</strong> ${resort.total_km || '?'} km</div>
            <div><strong>Day Pass:</strong> ${resort.day_pass_adult_eur ? '€' + resort.day_pass_adult_eur : 'Unknown'}</div>
            <div><strong>Ski-in/Ski-out:</strong> ${resort.ski_in_ski_out ? 'Yes' : 'No / Unknown'}</div>
        </div>
    `;

    document.getElementById('resortModal').style.display = 'flex';
    document.body.style.overflow = 'hidden'; // Prevent background scrolling
}

function closeModal(event) {
    // If event exists, only close if clicking the background overlay
    if (event && event.target.id !== 'resortModal') return;
    document.getElementById('resortModal').style.display = 'none';
    document.body.style.overflow = '';
}

// Init
document.addEventListener('DOMContentLoaded', () => {
    renderList(ALL_RESORTS);
});