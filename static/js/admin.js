const API_BASE = '';

window.addEventListener('DOMContentLoaded', () => {
    const token = localStorage.getItem('access_token');
    
    if (!token) {
        window.location.href = '/';
        return;
    }
    
    cargarTabs();
});

// Navegación entre tabs
document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const tabName = tab.dataset.tab;
        cambiarTab(tabName);
    });
});

function cambiarTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    
    document.getElementById(`tab-${tabName}`).classList.add('active');
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    
    cargarDatosTab(tabName);
}

function cargarTabs() {
    cargarDatosTab('usuarios');
}

async function cargarDatosTab(tabName) {
    switch(tabName) {
        case 'usuarios':
            await cargarUsuarios();
            break;
        case 'transacciones':
            await cargarTransacciones();
            break;
        case 'tarjetas':
            await cargarTarjetas();
            break;
        case 'tarjeteros':
            await cargarTarjeteros();
            break;
        case 'estadisticas':
            await cargarEstadisticas();
            break;
    }
}

// ========== USUARIOS ==========
async function cargarUsuarios() {
    try {
        const response = await fetchAPI('/buscar_usuario_por_ci', {
            method: 'POST',
            body: JSON.stringify({ ci: '1234567' })
        });
        
        // Simulación de carga (adaptar a tu API)
        const tbody = document.querySelector('#tablaUsuarios tbody');
        tbody.innerHTML = '<tr><td colspan="9" class="loading">Función de admin disponible en backend</td></tr>';
    } catch (error) {
        console.error('Error:', error);
    }
}

// ========== TRANSACCIONES ==========
async function cargarTransacciones() {
    const tbody = document.querySelector('#tablaTransacciones tbody');
    tbody.innerHTML = '<tr><td colspan="8" class="loading">Función de admin disponible en backend</td></tr>';
}

// ========== TARJETAS ==========
async function cargarTarjetas() {
    const tbody = document.querySelector('#tablaTarjetas tbody');
    tbody.innerHTML = '<tr><td colspan="7" class="loading">Función de admin disponible en backend</td></tr>';
}

// ========== TARJETEROS ==========
async function cargarTarjeteros() {
    try {
        const response = await fetchAPI('/tarjetero/1');
        const data = await response.json();
        
        if (response.ok) {
            const tbody = document.querySelector('#tablaTarjeteros tbody');
            tbody.innerHTML = `
                <tr>
                    <td>${data.tarjetero.id}</td>
                    <td>${data.tarjetero.nombre}</td>
                    <td>${data.tarjetero.ubicacion || '-'}</td>
                    <td>$${parseFloat(data.tarjetero.saldo).toFixed(2)}</td>
                    <td><span class="badge ${data.tarjetero.activo ? 'success' : 'danger'}">${data.tarjetero.activo ? 'Activo' : 'Inactivo'}</span></td>
                    <td>${new Date(data.tarjetero.fecha_creacion).toLocaleDateString('es-ES')}</td>
                    <td>
                        <button class="btn-action">Ver</button>
                    </td>
                </tr>
            `;
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

// ========== ESTADÍSTICAS ==========
async function cargarEstadisticas() {
    document.getElementById('statUsuarios').textContent = '1';
    document.getElementById('statTarjetas').textContent = '1';
    document.getElementById('statTransacciones').textContent = '0';
    document.getElementById('statMontoTotal').textContent = '$0.00';
}

// ========== MODALES ==========
document.getElementById('btnNuevoUsuario').addEventListener('click', () => {
    document.getElementById('modalNuevoUsuario').style.display = 'flex';
});

document.getElementById('btnNuevoTarjetero').addEventListener('click', () => {
    document.getElementById('modalNuevoTarjetero').style.display = 'flex';
});

document.querySelectorAll('.modal-close, .modal-actions .btn-secondary').forEach(btn => {
    btn.addEventListener('click', (e) => {
        const modal = e.target.closest('.modal') || document.getElementById(e.target.dataset.modal);
        if (modal) modal.style.display = 'none';
    });
});

// ========== LOGOUT ==========
document.getElementById('btnLogout').addEventListener('click', () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = '/';
});

// ========== REFRESH ==========
document.getElementById('btnRefreshTransacciones').addEventListener('click', () => {
    cargarTransacciones();
});

// ========== UTILIDADES ==========
async function fetchAPI(endpoint, options = {}) {
    const token = localStorage.getItem('access_token');
    
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        }
    };
    
    return fetch(API_BASE + endpoint, { ...defaultOptions, ...options });
}
