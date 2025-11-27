const API_BASE = '';
let currentUser = null;

// Verificar autenticación al cargar
window.addEventListener('DOMContentLoaded', async () => {
    const token = localStorage.getItem('access_token');
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    
    if (!token) {
        window.location.href = '/';
        return;
    }
    
    currentUser = user;
    
    // Mostrar datos guardados inmediatamente
    if (user && user.nombre) {
        mostrarDatosBasicos(user);
    }
    
    // Luego actualizar con datos frescos del servidor
    cargarDatosUsuario();
    actualizarFecha();
    
    // Inicializar menu responsive
    inicializarMenuResponsive();
});

// Cargar datos del usuario
async function cargarDatosUsuario() {
    try {
        const response = await fetchAPI('/api/perfil');
        const data = await response.json();
        
        if (response.ok) {
            currentUser = data.usuario;
            mostrarDatosUsuario(data);
            localStorage.setItem('user', JSON.stringify(data.usuario));
        } else {
            console.error('Error cargando perfil');
            // Si el token es inválido, redirigir al login
            if (response.status === 401) {
                localStorage.removeItem('access_token');
                localStorage.removeItem('user');
                window.location.href = '/';
            }
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

// Mostrar datos básicos desde localStorage (rápido)
function mostrarDatosBasicos(usuario) {
    if (document.getElementById('userName')) {
        document.getElementById('userName').textContent = usuario.nombre || '';
    }
    if (document.getElementById('userEmail')) {
        document.getElementById('userEmail').textContent = usuario.email || usuario.ci || '';
    }
    if (document.getElementById('saldoTotal') && usuario.saldo !== undefined) {
        document.getElementById('saldoTotal').textContent = usuario.saldo.toFixed(2);
    }
}

function mostrarDatosUsuario(data) {
    const usuario = data.usuario;
    
    document.getElementById('userName').textContent = usuario.nombre;
    document.getElementById('userEmail').textContent = usuario.email || usuario.ci;
    document.getElementById('saldoTotal').textContent = usuario.saldo.toFixed(2);
    document.getElementById('userCI').textContent = usuario.ci;
    
    // Perfil
    document.getElementById('perfilNombre').textContent = usuario.nombre;
    document.getElementById('perfilCI').textContent = usuario.ci;
    document.getElementById('perfilEmail').textContent = usuario.email || '-';
    document.getElementById('perfilTelefono').textContent = usuario.telefono || '-';
    
    if (usuario.fecha_registro) {
        const fecha = new Date(usuario.fecha_registro);
        document.getElementById('perfilFechaRegistro').textContent = fecha.toLocaleDateString('es-ES');
    }
    
    // Tarjetas
    if (data.tarjetas && data.tarjetas.length > 0) {
        mostrarTarjetas(data.tarjetas);
    }
    
    cargarTransaccionesRecientes();
}

function mostrarTarjetas(tarjetas) {
    const container = document.getElementById('tarjetasList');
    container.innerHTML = '';
    
    tarjetas.forEach(tarjeta => {
        const card = document.createElement('div');
        card.className = 'tarjeta-card';
        card.innerHTML = `
            <div class="tarjeta-icon">
                <svg viewBox="0 0 24 24" fill="none">
                    <rect x="1" y="4" width="22" height="16" rx="2" stroke="currentColor" stroke-width="2"/>
                    <path d="M1 10H23" stroke="currentColor" stroke-width="2"/>
                </svg>
            </div>
            <div class="tarjeta-info">
                <h4>Tarjeta RFID</h4>
                <p>UID: ${tarjeta.uid}</p>
                <span class="badge ${tarjeta.activa ? 'success' : 'danger'}">
                    ${tarjeta.activa ? 'Activa' : 'Inactiva'}
                </span>
            </div>
        `;
        container.appendChild(card);
    });
}

// Actualizar fecha actual
function actualizarFecha() {
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    const fecha = new Date().toLocaleDateString('es-ES', options);
    document.getElementById('currentDate').textContent = fecha.charAt(0).toUpperCase() + fecha.slice(1);
}

// Navegación entre vistas
document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
        const view = btn.dataset.view;
        cambiarVista(view);
    });
});

document.querySelectorAll('.quick-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const action = btn.dataset.action;
        cambiarVista(action);
    });
});

function cambiarVista(viewName) {
    // Ocultar todas las vistas
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    
    // Mostrar vista seleccionada
    const view = document.getElementById(`view-${viewName}`);
    if (view) {
        view.classList.add('active');
        
        const navItem = document.querySelector(`[data-view="${viewName}"]`);
        if (navItem) navItem.classList.add('active');
    }
}

// Cerrar sesión
document.getElementById('btnLogout').addEventListener('click', () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user');
    window.location.href = '/';
});

// Refrescar saldo
document.getElementById('btnRefreshBalance').addEventListener('click', cargarDatosUsuario);

// ========== TRANSFERENCIAS ==========
document.getElementById('formTransferir').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const ciDestino = document.getElementById('ciDestino').value.trim();
    const monto = parseFloat(document.getElementById('montoTransferir').value);
    const descripcion = document.getElementById('descripcionTransferir').value.trim();
    
    if (!ciDestino || !monto || monto <= 0) {
        mostrarAlerta('alertTransferir', 'Completa todos los campos correctamente', 'error');
        return;
    }
    
    try {
        const response = await fetchAPI('/api/transferir', {
            method: 'POST',
            body: JSON.stringify({ ci_destino: ciDestino, monto, descripcion })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            mostrarAlerta('alertTransferir', `Transferencia exitosa a ${data.destinatario}. Nuevo saldo: $${data.nuevo_saldo.toFixed(2)}`, 'success');
            document.getElementById('formTransferir').reset();
            setTimeout(() => {
                cargarDatosUsuario();
                cambiarVista('resumen');
            }, 2000);
        } else {
            mostrarAlerta('alertTransferir', data.error || 'Error en la transferencia', 'error');
        }
    } catch (error) {
        mostrarAlerta('alertTransferir', 'Error de conexión', 'error');
    }
});

// ========== CARGAR TARJETAS DISPONIBLES ==========
// Cargar al cambiar a vista recargar
document.querySelectorAll('.nav-item').forEach(btn => {
    const originalClick = btn.onclick;
    btn.addEventListener('click', () => {
        if (btn.dataset.view === 'recargar') {
            setTimeout(cargarTarjetasDisponibles, 100);
        }
    });
});

async function cargarTarjetasDisponibles() {
    try {
        const response = await fetchAPI('/api/tarjetas-disponibles');
        const data = await response.json();
        
        if (response.ok) {
            mostrarTarjetasDisponibles(data.tarjetas);
        }
    } catch (error) {
        console.error('Error cargando tarjetas:', error);
    }
}

function mostrarTarjetasDisponibles(tarjetas) {
    const container = document.getElementById('tarjetasDisponibles');
    
    if (tarjetas.length === 0) {
        container.innerHTML = '<p class="no-data">No hay tarjetas disponibles</p>';
        return;
    }
    
    container.innerHTML = '';
    tarjetas.forEach(t => {
        const card = document.createElement('div');
        card.className = 'tarjeta-recarga-card';
        card.innerHTML = `
            <div class="tarjeta-recarga-monto">$${t.monto.toFixed(0)}</div>
            <div class="tarjeta-recarga-info">
                <p>${t.cantidad} disponibles</p>
            </div>
        `;
        container.appendChild(card);
    });
}

// ========== CANJEAR TARJETA ==========
document.getElementById('formCanjearTarjeta').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const codigo = document.getElementById('codigoTarjeta').value.trim().toUpperCase();
    
    if (!codigo) {
        mostrarAlerta('alertCanjear', 'Ingresa un código de tarjeta', 'error');
        return;
    }
    
    try {
        const response = await fetchAPI('/api/canjear-tarjeta', {
            method: 'POST',
            body: JSON.stringify({ codigo })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            mostrarAlerta('alertCanjear', `¡Tarjeta canjeada! +$${data.monto.toFixed(2)}. Nuevo saldo: $${data.nuevo_saldo.toFixed(2)}`, 'success');
            document.getElementById('formCanjearTarjeta').reset();
            cargarTarjetasDisponibles();
            setTimeout(() => {
                cargarDatosUsuario();
                cambiarVista('resumen');
            }, 2000);
        } else {
            mostrarAlerta('alertCanjear', data.error || 'Error al canjear tarjeta', 'error');
        }
    } catch (error) {
        mostrarAlerta('alertCanjear', 'Error de conexión', 'error');
    }
});

// ========== HISTORIAL ==========
async function cargarTransaccionesRecientes() {
    try {
        const response = await fetchAPI('/api/historial_transacciones?limite=5');
        const data = await response.json();
        
        if (response.ok) {
            mostrarTransaccionesRecientes(data.transacciones);
        }
    } catch (error) {
        console.error('Error cargando transacciones:', error);
    }
}

function mostrarTransaccionesRecientes(transacciones) {
    const container = document.getElementById('recentTransactionsList');
    
    if (transacciones.length === 0) {
        container.innerHTML = '<p class="no-data">No hay transacciones</p>';
        return;
    }
    
    container.innerHTML = '';
    transacciones.forEach(tr => {
        const item = document.createElement('div');
        item.className = 'transaction-item';
        
        let icono, clase, titulo;
        
        if (tr.tipo === 'recarga') {
            icono = '+';
            clase = 'positive';
            titulo = 'Recarga';
        } else if (tr.tipo === 'transferencia_recibida') {
            icono = '+';
            clase = 'positive';
            titulo = `Transferencia de ${tr.remitente}`;
        } else if (tr.tipo === 'transferencia_enviada') {
            icono = '-';
            clase = 'negative';
            titulo = `Transferencia a ${tr.destinatario}`;
        } else {
            icono = '-';
            clase = 'negative';
            titulo = tr.tarjetero || tr.tipo;
        }
        
        item.innerHTML = `
            <div class="transaction-info">
                <h4>${titulo}</h4>
                <p>${new Date(tr.fecha).toLocaleDateString('es-ES')} ${new Date(tr.fecha).toLocaleTimeString('es-ES', {hour: '2-digit', minute: '2-digit'})}</p>
            </div>
            <div class="transaction-amount ${clase}">
                ${icono}$${tr.monto.toFixed(2)}
            </div>
        `;
        container.appendChild(item);
    });
}

// Eliminado: btnRefreshHistory ya no existe en el HTML
// document.getElementById('btnRefreshHistory').addEventListener('click', cargarHistorialCompleto);

async function cargarHistorialCompleto() {
    try {
        const response = await fetchAPI('/api/historial_transacciones?limite=50');
        const data = await response.json();
        
        if (response.ok) {
            mostrarHistorialCompleto(data.transacciones);
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

function mostrarHistorialCompleto(transacciones) {
    const container = document.getElementById('historialCompleto');
    
    if (transacciones.length === 0) {
        container.innerHTML = '<p class="no-data">No hay transacciones</p>';
        return;
    }
    
    container.innerHTML = '';
    transacciones.forEach(tr => {
        const item = document.createElement('div');
        item.className = 'transaction-item-full';
        
        let icono, clase, titulo;
        
        if (tr.tipo === 'recarga') {
            icono = '+';
            clase = 'positive';
            titulo = 'Recarga';
        } else if (tr.tipo === 'transferencia_recibida') {
            icono = '+';
            clase = 'positive';
            titulo = `Transferencia recibida de ${tr.remitente}`;
        } else if (tr.tipo === 'transferencia_enviada') {
            icono = '-';
            clase = 'negative';
            titulo = `Transferencia enviada a ${tr.destinatario}`;
        } else {
            icono = '-';
            clase = 'negative';
            titulo = tr.tarjetero || tr.tipo;
        }
        
        item.innerHTML = `
            <div class="transaction-date">
                ${new Date(tr.fecha).toLocaleDateString('es-ES')}
                <br>
                ${new Date(tr.fecha).toLocaleTimeString('es-ES', {hour: '2-digit', minute: '2-digit'})}
            </div>
            <div class="transaction-details">
                <h4>${titulo}</h4>
                <p>${tr.descripcion || '-'}</p>
                <span class="badge ${tr.estado === 'aprobada' || tr.estado === 'completada' ? 'success' : 'danger'}">${tr.estado}</span>
            </div>
            <div class="transaction-amount ${clase}">
                ${icono}$${tr.monto.toFixed(2)}
            </div>
        `;
        container.appendChild(item);
    });
}

// ========== CAMBIAR CONTRASEÑA ==========
document.getElementById('btnCambiarPassword').addEventListener('click', () => {
    document.getElementById('modalPassword').style.display = 'flex';
});

document.getElementById('btnCancelarPassword').addEventListener('click', () => {
    document.getElementById('modalPassword').style.display = 'none';
    document.getElementById('formCambiarPassword').reset();
});

document.getElementById('formCambiarPassword').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const actual = document.getElementById('passwordActual').value;
    const nueva = document.getElementById('passwordNueva').value;
    const confirmar = document.getElementById('passwordConfirmar').value;
    
    if (nueva !== confirmar) {
        mostrarAlerta('alertPassword', 'Las contraseñas no coinciden', 'error');
        return;
    }
    
    if (nueva.length < 6) {
        mostrarAlerta('alertPassword', 'La contraseña debe tener al menos 6 caracteres', 'error');
        return;
    }
    
    try {
        const response = await fetchAPI('/api/cambiar_password', {
            method: 'POST',
            body: JSON.stringify({ password_actual: actual, password_nueva: nueva })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            mostrarAlerta('alertPassword', 'Contraseña actualizada exitosamente', 'success');
            setTimeout(() => {
                document.getElementById('modalPassword').style.display = 'none';
                document.getElementById('formCambiarPassword').reset();
            }, 2000);
        } else {
            mostrarAlerta('alertPassword', data.error || 'Error al cambiar contraseña', 'error');
        }
    } catch (error) {
        mostrarAlerta('alertPassword', 'Error de conexión', 'error');
    }
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

function mostrarAlerta(elementId, mensaje, tipo) {
    const alert = document.getElementById(elementId);
    alert.textContent = mensaje;
    alert.className = `alert ${tipo}`;
    alert.style.display = 'block';
    
    setTimeout(() => {
        alert.style.display = 'none';
    }, 5000);
}

// ========== ASISTENTE IA ==========
document.getElementById('formAIChat').addEventListener('submit', async (e) => {
    e.preventDefault();
    
    const pregunta = document.getElementById('inputAIQuestion').value.trim();
    if (!pregunta) return;
    
    const btnSend = document.getElementById('btnSendQuestion');
    btnSend.disabled = true;
    
    // Mostrar mensaje del usuario
    agregarMensajeUsuario(pregunta);
    document.getElementById('inputAIQuestion').value = '';
    
    // Crear mensaje de IA vacío para streaming
    const mensajeId = crearMensajeIAVacio();
    
    try {
        const token = localStorage.getItem('access_token');
        const response = await fetch(API_BASE + '/api/ai-chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({ pregunta })
        });
        
        if (!response.ok) {
            throw new Error('Error en la respuesta del servidor');
        }
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        
        while (true) {
            const { done, value } = await reader.read();
            
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop(); // Guardar línea incompleta
            
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        
                        if (data.error) {
                            actualizarMensajeIA(mensajeId, `Error: ${data.error}`);
                            break;
                        }
                        
                        if (data.text) {
                            agregarTextoAMensajeIA(mensajeId, data.text);
                        }
                        
                        if (data.done) {
                            finalizarMensajeIA(mensajeId);
                            break;
                        }
                    } catch (e) {
                        console.error('Error parsing SSE:', e);
                    }
                }
            }
        }
    } catch (error) {
        console.error('Error:', error);
        actualizarMensajeIA(mensajeId, 'Error de conexión. Verifica que Ollama esté ejecutándose.');
    } finally {
        btnSend.disabled = false;
    }
});

// Botones de sugerencias
document.querySelectorAll('.suggestion-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const pregunta = btn.getAttribute('data-question');
        document.getElementById('inputAIQuestion').value = pregunta;
        document.getElementById('formAIChat').dispatchEvent(new Event('submit'));
    });
});

// Limpiar chat
document.getElementById('btnClearChat').addEventListener('click', () => {
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.innerHTML = `
        <div class="ai-message">
            <div class="message-avatar ai">
                <svg viewBox="0 0 24 24" fill="none">
                    <path d="M9.09 9C9.3251 8.33167 9.78915 7.76811 10.4 7.40913C11.0108 7.05016 11.7289 6.91894 12.4272 7.03871C13.1255 7.15849 13.7588 7.52152 14.2151 8.06353C14.6713 8.60553 14.9211 9.29152 14.92 10C14.92 12 11.92 13 11.92 13M12 17H12.01M22 12C22 17.5228 17.5228 22 12 22C6.47715 22 2 17.5228 2 12C2 6.47715 6.47715 2 12 2C17.5228 2 22 6.47715 22 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>
            <div class="message-content">
                <div class="message-header">
                    <span class="message-author">Asistente IA</span>
                    <span class="message-time">Ahora</span>
                </div>
                <p>Bienvenido. Soy tu asistente financiero profesional con acceso a tus datos de transacciones. Puedo analizar tus patrones de gasto, identificar oportunidades de ahorro y proporcionarte recomendaciones personalizadas basadas en tu historial financiero real.</p>
            </div>
        </div>
    `;
});

function agregarMensajeUsuario(texto) {
    const chatMessages = document.getElementById('chatMessages');
    const mensaje = document.createElement('div');
    mensaje.className = 'user-message';
    
    const ahora = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    
    mensaje.innerHTML = `
        <div class="message-avatar user">
            <svg viewBox="0 0 24 24" fill="none">
                <path d="M20 21V19C20 17.9391 19.5786 16.9217 18.8284 16.1716C18.0783 15.4214 17.0609 15 16 15H8C6.93913 15 5.92172 15.4214 5.17157 16.1716C4.42143 16.9217 4 17.9391 4 19V21M16 7C16 9.20914 14.2091 11 12 11C9.79086 11 8 9.20914 8 7C8 4.79086 9.79086 3 12 3C14.2091 3 16 4.79086 16 7Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-author">Tú</span>
                <span class="message-time">${ahora}</span>
            </div>
            <p>${escapeHtml(texto)}</p>
        </div>
    `;
    chatMessages.appendChild(mensaje);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function crearMensajeIAVacio() {
    const chatMessages = document.getElementById('chatMessages');
    const mensajeId = 'ai-msg-' + Date.now();
    const ahora = new Date().toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    
    const mensaje = document.createElement('div');
    mensaje.id = mensajeId;
    mensaje.className = 'ai-message';
    mensaje.innerHTML = `
        <div class="message-avatar ai">
            <svg viewBox="0 0 24 24" fill="none">
                <path d="M9.09 9C9.3251 8.33167 9.78915 7.76811 10.4 7.40913C11.0108 7.05016 11.7289 6.91894 12.4272 7.03871C13.1255 7.15849 13.7588 7.52152 14.2151 8.06353C14.6713 8.60553 14.9211 9.29152 14.92 10C14.92 12 11.92 13 11.92 13M12 17H12.01M22 12C22 17.5228 17.5228 22 12 22C6.47715 22 2 17.5228 2 12C2 6.47715 6.47715 2 12 2C17.5228 2 22 6.47715 22 12Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-author">Asistente IA</span>
                <span class="message-time">${ahora}</span>
            </div>
            <p class="message-text"><span class="typing-indicator">▊</span></p>
        </div>
    `;
    chatMessages.appendChild(mensaje);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return mensajeId;
}

function agregarTextoAMensajeIA(mensajeId, texto) {
    const mensaje = document.getElementById(mensajeId);
    if (!mensaje) return;
    
    const textElement = mensaje.querySelector('.message-text');
    if (!textElement) return;
    
    // Remover indicador de escritura si existe
    const indicator = textElement.querySelector('.typing-indicator');
    if (indicator) {
        indicator.remove();
    }
    
    // Agregar texto (escapar HTML)
    const currentText = textElement.textContent;
    textElement.textContent = currentText + texto;
    
    // Auto-scroll
    const chatMessages = document.getElementById('chatMessages');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function actualizarMensajeIA(mensajeId, texto) {
    const mensaje = document.getElementById(mensajeId);
    if (!mensaje) return;
    
    const textElement = mensaje.querySelector('.message-text');
    if (!textElement) return;
    
    textElement.innerHTML = `<p>${escapeHtml(texto)}</p>`;
}

function finalizarMensajeIA(mensajeId) {
    const mensaje = document.getElementById(mensajeId);
    if (!mensaje) return;
    
    const textElement = mensaje.querySelector('.message-text');
    if (!textElement) return;
    
    // Remover indicador de escritura
    const indicator = textElement.querySelector('.typing-indicator');
    if (indicator) {
        indicator.remove();
    }
    
    // Formatear texto final
    const textoFinal = textElement.textContent;
    textElement.innerHTML = formatearTextoIA(textoFinal);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function eliminarMensajeCargando(loadingId) {
    const loading = document.getElementById(loadingId);
    if (loading) {
        loading.remove();
    }
}

function formatearTextoIA(texto) {
    // Convertir saltos de línea a <br>
    let formateado = texto.replace(/\n/g, '<br>');
    
    // Detectar listas numeradas (1. 2. 3.)
    formateado = formateado.replace(/(\d+\.\s[^\n<]+)/g, '<li>$1</li>');
    if (formateado.includes('<li>')) {
        formateado = formateado.replace(/(<li>.*<\/li>)/s, '<ol>$1</ol>');
    }
    
    // Detectar listas con viñetas (- o *)
    formateado = formateado.replace(/([•\-\*]\s[^\n<]+)/g, '<li>$1</li>');
    if (formateado.includes('<li>') && !formateado.includes('<ol>')) {
        formateado = formateado.replace(/(<li>.*<\/li>)/s, '<ul>$1</ul>');
    }
    
    // Envolver en párrafo si no hay etiquetas HTML
    if (!formateado.includes('<')) {
        formateado = `<p>${formateado}</p>`;
    }
    
    return formateado;
}

// ========== RESPONSIVE MENU ==========
function inicializarMenuResponsive() {
    const menuToggle = document.getElementById('menuToggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const navItems = document.querySelectorAll('.nav-item');
    
    if (!menuToggle || !sidebar || !overlay) return;
    
    // Toggle menu
    menuToggle.addEventListener('click', () => {
        sidebar.classList.toggle('active');
        overlay.classList.toggle('active');
        document.body.style.overflow = sidebar.classList.contains('active') ? 'hidden' : '';
    });
    
    // Cerrar con overlay
    overlay.addEventListener('click', () => {
        sidebar.classList.remove('active');
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    });
    
    // Cerrar al hacer clic en un item de navegación (móvil)
    navItems.forEach(item => {
        item.addEventListener('click', () => {
            if (window.innerWidth <= 768) {
                sidebar.classList.remove('active');
                overlay.classList.remove('active');
                document.body.style.overflow = '';
            }
        });
    });
    
    // Cerrar sidebar al cambiar tamaño de ventana
    window.addEventListener('resize', () => {
        if (window.innerWidth > 768) {
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
            document.body.style.overflow = '';
        }
    });
}
