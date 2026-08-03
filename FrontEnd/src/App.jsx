import React, { useState, useEffect } from 'react';
import { Button, Spinner, Tab, TabList } from '@fluentui/react-components';
import api from './api/axios';
import HmiDashboard from './components/HmiDashboard'; 
import ExtrusionChart from './components/ExtrusionChart'; 
import ThermalProfileChart from './components/ThermalProfileChart';
import MotorDynamicsChart from './components/MotorDynamicsChart';
// Importamos tu nuevo componente analítico matricial
import HistoricalAnalyticsPanel from './components/HistoricalAnalyticsPanel';

function App() {
  const [healthStatus, setHealthStatus] = useState('Desconectado');
  const [loading, setLoading] = useState(false);
  
  // 🔄 Estado para controlar la vista activa mediante pestañas ("live" o "history")
  const [activeTab, setActiveTab] = useState('live');
  
  // 📱 Estado para controlar el tamaño de pantalla de manera global
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  const verificarConexion = async () => {
    setLoading(true);
    try {
      const response = await api.get('/api/health');
      if (response.data.status === 'healthy') {
        setHealthStatus('Conectado Exitosamente a la API V2');
      } else {
        setHealthStatus('API responde con estado indeterminado');
      }
    } catch (error) {
      console.error("Error conectando al backend:", error);
      setHealthStatus('Error: No se pudo comunicar con el Backend');
    } finally {
      setLoading(false);
    }
  };

  const handleTabChange = (event, data) => {
    setActiveTab(data.value);
  };

  return (
    <div style={{ 
      padding: isMobile ? '10px' : '30px', 
      display: 'flex', 
      flexDirection: 'column', 
      gap: isMobile ? '15px' : '25px',
      alignItems: 'center',
      maxWidth: '1600px', 
      margin: '0 auto',
      fontFamily: 'Segoe UI, sans-serif',
      backgroundColor: '#1f1f1f',
      color: '#ffffff',
      boxSizing: 'border-box',
      width: '100%',
      overflowX: 'hidden'
    }}>
      {/* --- ENCABEZADO --- */}
      <div style={{ textAlign: 'center' }}>
        <h1 style={{ margin: '0 0 5px 0', fontSize: isMobile ? '20px' : '28px' }}>
          JAGEG - Sistema Producción (SCADA V2)
        </h1>
        <p style={{ margin: 0, color: '#a1a1a1', fontSize: isMobile ? '12px' : '14px' }}>
          Módulo de Control de Extrusión de Tela No Tejida
        </p>
      </div>
      
      {/* --- BARRA DE ESTADO DE CONEXIÓN Y NAVEGACIÓN --- */}
      <div style={{ 
        display: 'flex', 
        gap: '20px', 
        alignItems: 'center',
        justifyContent: 'space-between',
        flexDirection: isMobile ? 'column' : 'row',
        width: '100%',
        backgroundColor: '#252525',
        padding: '12px 20px',
        borderRadius: '8px',
        border: '1px solid #333',
        boxSizing: 'border-box'
      }}>
        {/* Lado Izquierdo: Diagnóstico de API */}
        <div style={{ display: 'flex', gap: '12px', alignItems: 'center', width: isMobile ? '100%' : 'auto', flexDirection: isMobile ? 'column' : 'row' }}>
          <div style={{ 
            padding: '8px 16px', 
            borderRadius: '4px', 
            backgroundColor: '#1f1f1f', 
            border: '1px solid #444',
            color: healthStatus.includes('Error') ? '#ff6b6b' : (healthStatus === 'Desconectado' ? '#ffbc42' : '#6bff6b'),
            fontSize: '13px',
            textAlign: 'center',
            width: isMobile ? '100%' : 'auto',
            boxSizing: 'border-box'
          }}>
            <strong>Estado API:</strong> {healthStatus}
          </div>

          <Button 
            appearance="subtle" 
            onClick={verificarConexion} 
            disabled={loading}
            style={{ width: isMobile ? '100%' : 'auto', color: '#fff', border: '1px solid #444' }}
          >
            {loading ? <Spinner size="tiny" /> : 'Verificar API'}
          </Button>
        </div>

        {/* Lado Derecho: Menú de Selección de Modos (Fluent UI) */}
        <div style={{ width: isMobile ? '100%' : 'auto', display: 'flex', justifyContent: 'center' }}>
          <TabList selectedValue={activeTab} onTabSelect={handleTabChange}>
            <Tab value="live" style={{ color: activeTab === 'live' ? '#3498db' : '#aaa' }}>
              📊 Operación en Tiempo Real
            </Tab>
            <Tab value="history" style={{ color: activeTab === 'history' ? '#2ecc71' : '#aaa' }}>
              📈 Históricos y Analítica SPC
            </Tab>
          </TabList>
        </div>
      </div>

      {/* --- RENDERIZADO CONDICIONAL DE VISTAS --- */}
      {activeTab === 'live' ? (
        /* ================= VISTA TIEMPO REAL ================= */
        <>
          {/* TABLERO NUMÉRICO HMI */}
          <div style={{ width: '100%', marginTop: '5px', boxSizing: 'border-box' }}>
            <HmiDashboard />
          </div>

          {/* DASHBOARD GENERAL DE GRÁFICAS DE FLUJO VIVO */}
          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: `repeat(auto-fit, minmax(${isMobile ? '280px' : '500px'}, 1fr))`, 
            gap: '20px', 
            width: '100%', 
            marginTop: '10px',
            boxSizing: 'border-box'
          }}>
            {/* PANEL 1: REOLOGÍA */}
            <div style={{ backgroundColor: '#252525', border: '1px solid #333', borderRadius: '8px', padding: '15px', minWidth: 0 }}>
              <h3 style={{ color: '#fff', margin: '0 0 15px 0', fontSize: '14px', borderBottom: '1px solid #3c3c3c', paddingBottom: '8px' }}>
                1. Variables de Reología en Tiempo Real
              </h3>
              <div style={{ width: '100%', overflow: 'hidden' }}>
                <ExtrusionChart />
              </div>
            </div>

            {/* PANEL 2: PERFIL TÉRMICO */}
            <div style={{ backgroundColor: '#252525', border: '1px solid #333', borderRadius: '8px', padding: '15px', minWidth: 0 }}>
              <h3 style={{ color: '#fff', margin: '0 0 15px 0', fontSize: '14px', borderBottom: '1px solid #3c3c3c', paddingBottom: '8px' }}>
                2. Perfil Térmico Completo del Cañón
              </h3>
              <div style={{ width: '100%', overflow: 'hidden' }}>
                <ThermalProfileChart />
              </div>
            </div>

            {/* PANEL 3: DINÁMICA DE MOTORES */}
            <div style={{ backgroundColor: '#252525', border: '1px solid #333', borderRadius: '8px', padding: '15px', minWidth: 0 }}>
              <h3 style={{ color: '#fff', margin: '0 0 15px 0', fontSize: '14px', borderBottom: '1px solid #3c3c3c', paddingBottom: '8px' }}>
                3. Control de Estirado y Dinámica de Motores
              </h3>
              <div style={{ width: '100%', overflow: 'hidden' }}>
                <MotorDynamicsChart />
              </div>
            </div>
          </div>
        </>
      ) : (
        /* ================= VISTA HISTÓRICOS (AISLADA) ================= */
        <div style={{ width: '100%', boxSizing: 'border-box' }}>
          <HistoricalAnalyticsPanel />
        </div>
      )}

    </div>
  );
}

export default App;