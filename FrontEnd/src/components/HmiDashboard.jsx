import React, { useEffect, useState, useRef } from "react";

const HmiDashboard = () => {
  const ws = useRef(null);
  
  // 🎛️ Estado de navegación para emular las pestañas del panel Siemens
  const [activeTab, setActiveTab] = useState("S1"); // Opciones: "S1", "S2", "M"
  
  // 📱 Estado dinámico para detectar si la pantalla es móvil (Break-point industrial a 768px)
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Inicializamos el estado con las variables generales y bloques térmicos por sección
  const [metrics, setMetrics] = useState({
    extruderSpeed: 0,
    diePre: 0,
    mFilterExPre: 0,     // Conectado a PV_FILTER_EX_PRE
    s1OilPumpsSw: 0,     // Emulado dinámicamente según presión
    s2OilPumpsSw: 0,     // Emulado dinámicamente según presión
    
    // Bloque Spunbond 1: Z1-Z5 (Cañón) + Z6 (Aceite Dado / DIE OIL)
    S1: {
      Z1: { pv: 0, sv: 0 }, Z2: { pv: 0, sv: 0 }, Z3: { pv: 0, sv: 0 },
      Z4: { pv: 0, sv: 0 }, Z5: { pv: 0, sv: 0 }, Z6: { pv: 0, sv: 0 }
    },
    // Bloque Spunbond 2: Z1-Z5 (Cañón) + Z6 (Aceite Dado) + Rodillos Calandria (Rbody / CoolArea)
    S2: {
      Z1: { pv: 0, sv: 0 }, Z2: { pv: 0, sv: 0 }, Z3: { pv: 0, sv: 0 },
      Z4: { pv: 0, sv: 0 }, Z5: { pv: 0, sv: 0 }, Z6: { pv: 0, sv: 0 },
      upRol: { pv: 0, sv: 0 },   // Mapeado a Rong Body
      downRol: { pv: 0, sv: 0 }  // Mapeado a Cool Area
    },
    // Bloque Meltblown: Fila Superior Cañón (Z1-Z6) / Fila Inferior Dado P_ZONE (Z1-Z6)
    M: {
      Z1: { pv: 0, sv: 0 }, Z2: { pv: 0, sv: 0 }, Z3: { pv: 0, sv: 0 },
      Z4: { pv: 0, sv: 0 }, Z5: { pv: 0, sv: 0 }, Z6: { pv: 0, sv: 0 },
      P_Z1: { pv: 0, sv: 0 }, P_Z2: { pv: 0, sv: 0 }, P_Z3: { pv: 0, sv: 0 },
      P_Z4: { pv: 0, sv: 0 }, P_Z5: { pv: 0, sv: 0 }, P_Z6: { pv: 0, sv: 0 }
    }
  });

  useEffect(() => {
    const backendUrl = import.meta.env.VITE_API_URL || "http://localhost:8080";
    const wsUrl = backendUrl.replace(/^http/, "ws") + "/api/v1/stream/ws/hmi";
    
    if (ws.current && (ws.current.readyState === WebSocket.OPEN || ws.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    ws.current = new WebSocket(wsUrl);

    ws.current.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        // Tolerancia si el backend envía el payload directo o envuelto en "tags"
        const tags = payload.tags || payload;

        if (!tags) return;

        setMetrics((prev) => {
          // 🔄 FUNCIÓN DE MAPEO CORREGIDA: Resuelve el desajuste de Meltblown y completa la Zona 6
          const mapLineZones = (prefix, isMeltblownDado = false) => {
            const result = {};
            
            if (prefix === "M") {
              // 💡 AJUSTE PARA MELTBLOWN: Como solo hay 6 tags en BD pero 12 tarjetas en el HMI:
              // Fila Cañón (isMeltblownDado = false) -> Muestra zonas 1, 2, 3
              // Fila Dado (isMeltblownDado = true)   -> Muestra zonas 4, 5, 6
              const subPrefix = isMeltblownDado ? "P_Z" : "Z";
              const startZone = isMeltblownDado ? 4 : 1;

              for (let i = 1; i <= 6; i++) {
                // Mapeamos las tarjetas del HMI (1-6) usando los bloques de tags disponibles en tu JSON
                const tagIndex = isMeltblownDado ? (i > 3 ? i : i + 3) : (i > 3 ? i - 3 : i);
                
                const pvKey = `M_PV_Z${tagIndex}`;
                const spKey = `M_SP_Z${tagIndex}`;

                result[`${subPrefix}${i}`] = {
                  pv: tags[pvKey] !== undefined ? tags[pvKey] : prev.M[`${subPrefix}${i}`].pv,
                  sv: tags[spKey] !== undefined ? tags[spKey] : prev.M[`${subPrefix}${i}`].sv
                };
              }
            } else {
              // 💡 AJUSTE PARA SPUNBOND 1 Y 2: Mapeo directo 1 a 1 de la Zona 1 a la 6 (Clavado con tu BD)
              for (let i = 1; i <= 6; i++) {
                const pvKey = `${prefix}_PV_Z${i}`;
                const spKey = `${prefix}_SP_Z${i}`;

                result[`Z${i}`] = {
                  pv: tags[pvKey] !== undefined ? tags[pvKey] : prev[prefix][`Z${i}`].pv,
                  sv: tags[spKey] !== undefined ? tags[spKey] : prev[prefix][`Z${i}`].sv
                };
              }
            }
            
            return result;
          };

          // Extraer variables analógicas críticas para las emulaciones de switches
          const currentDiePre = tags.PV_DIE_PRE !== undefined ? tags.PV_DIE_PRE : prev.diePre;
          const currentFilterPre = tags.PV_FILTER_EX_PRE !== undefined ? tags.PV_FILTER_EX_PRE : prev.mFilterExPre;

          return {
            ...prev,
            // 💡 AJUSTE 1: Velocidad mapeada al VDF real (PV_BOMBA_HILADORA) que marca 230 Hz
            extruderSpeed: tags.PV_BOMBA_HILADORA !== undefined ? tags.PV_BOMBA_HILADORA : prev.extruderSpeed,
            
            // 💡 AJUSTE 2: Presión de Hilera Post-Bomba
            diePre: currentDiePre,
            
            // 💡 AJUSTE 3: Presión de Prefiltro de la Extrusora (Alineado con el nombre de BD)
            mFilterExPre: currentFilterPre,
            
            // 💡 AJUSTE 4: Emulación inteligente de Switches de flujo (Activo si hay presión analógica > 0.5 Bar)
            s1OilPumpsSw: currentFilterPre > 0.5 ? 1 : 0,
            s2OilPumpsSw: currentDiePre > 0.5 ? 1 : 0,
            
            // --- Bloques Térmicos Sincronizados ---
            S1: { ...prev.S1, ...mapLineZones("S1") },
            
            S2: { 
              ...prev.S2, 
              ...mapLineZones("S2"),
              // 💡 AJUSTE 5: Mapeo de Rodillos Térmicos auxiliares a las variables reales de retorno de aceite
              upRol: {
                pv: tags.PV_RBODY !== undefined ? tags.PV_RBODY : prev.S2.upRol.pv,
                sv: tags.SP_RBODY !== undefined ? tags.SP_RBODY : prev.S2.upRol.sv
              },
              downRol: {
                pv: tags.PV_COOLAREA !== undefined ? tags.PV_COOLAREA : prev.S2.downRol.pv,
                sv: tags.SP_COOLAREA !== undefined ? tags.SP_COOLAREA : prev.S2.downRol.sv
              }
            },
            
            M: { 
              ...prev.M, 
              // Al compartir nomenclaturas en la base de datos para Meltblown, mapeamos con fallback seguro
              ...mapLineZones("M", false),
              ...mapLineZones("M", true) 
            }
          };
        });
      } catch (error) {
        console.error("Error en lectura dinámica del tablero HMI:", error);
      }
    };

    return () => {
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        ws.current.close();
      }
    };
  }, []);

  // Sub-componente de tarjeta visual (HmiCard)
  const HmiCard = ({ title, pv, sv, isSpecialZone = false }) => (
    <div style={{
      backgroundColor: "#1a1a1a",
      border: isSpecialZone ? "2px solid #e67e22" : "2px solid #00aa7f",
      borderRadius: "4px",
      padding: "8px",
      textAlign: "center",
      minWidth: isMobile ? "calc(50% - 5px)" : "115px",
      flex: "1 1 auto",
      fontFamily: "'Courier New', Courier, monospace",
      boxSizing: "border-box"
    }}>
      <div style={{ color: isSpecialZone ? "#e67e22" : "#ffffff", fontSize: "10px", fontWeight: "bold", marginBottom: "5px" }}>{title}</div>
      <div style={{ backgroundColor: "#000000", color: "#38b6ff", fontSize: isMobile ? "18px" : "22px", fontWeight: "bold", padding: "4px 0", borderRadius: "3px", marginBottom: "4px" }}>
        {pv !== undefined && pv !== null ? Number(pv).toFixed(1) : "0.0"}
      </div>
      <div style={{ backgroundColor: "#000000", color: "#ff4d4d", fontSize: isMobile ? "13px" : "16px", fontWeight: "bold", padding: "2px 0", borderRadius: "3px" }}>
        {sv !== undefined && sv !== null ? Number(sv).toFixed(0) : "0"}
      </div>
    </div>
  );

  const renderThermalBlocks = () => {
    if (activeTab === "M") {
      return (
        <div style={{ display: "flex", flexDirection: "column", gap: "15px" }}>
          {/* Fila Cañón Meltblown */}
          <div>
            <div style={{ color: "#aaa", fontSize: "11px", marginBottom: "5px", fontWeight: "bold" }}>M Extrud. Zone (Cañón)</div>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              {[1, 2, 3, 4, 5, 6].map(z => (
                <HmiCard key={`M_Z${z}`} title={`M ZONE ${z}`} pv={metrics.M[`Z${z}`].pv} sv={metrics.M[`Z${z}`].sv} />
              ))}
            </div>
          </div>
          {/* Fila Dado Meltblown */}
          <div>
            <div style={{ color: "#aaa", fontSize: "11px", marginBottom: "5px", fontWeight: "bold" }}>M P ZONE (Dado / Die Plates)</div>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
              {[1, 2, 3, 4, 5, 6].map(z => (
                <HmiCard key={`M_PZ${z}`} title={`M P ZONE ${z}`} pv={metrics.M[`P_Z${z}`].pv} sv={metrics.M[`P_Z${z}`].sv} isSpecialZone />
              ))}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "15px" }}>
        <div>
          <div style={{ color: "#aaa", fontSize: "11px", marginBottom: "5px", fontWeight: "bold" }}>Perfil de Calentamiento del Cañón ({activeTab})</div>
          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            {[1, 2, 3, 4, 5].map(z => (
              <HmiCard key={`${activeTab}_Z${z}`} title={`${activeTab} ZONE ${z}`} pv={metrics[activeTab][`Z${z}`].pv} sv={metrics[activeTab][`Z${z}`].sv} />
            ))}
            {/* Zona 6 adaptada dinámicamente sin romper el componente */}
            <HmiCard 
              title="DIE OIL TMP" 
              pv={metrics[activeTab]["Z6"].pv} 
              sv={metrics[activeTab]["Z6"].sv} 
              isSpecialZone 
            />
          </div>
        </div>

        {activeTab === "S2" && (
          <div>
            <div style={{ color: "#aaa", fontSize: "11px", marginBottom: "5px", fontWeight: "bold" }}>Control Técnico Rodillos de Calandria (Calander)</div>
            <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", maxWidth: isMobile ? "100%" : "300px" }}>
              <HmiCard title="UP ROL. TMP" pv={metrics.S2.upRol.pv} sv={metrics.S2.upRol.sv} isSpecialZone />
              <HmiCard title="DOWN ROL. TMP" pv={metrics.S2.downRol.pv} sv={metrics.S2.downRol.sv} isSpecialZone />
            </div>
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ 
      width: "100%", 
      display: "flex", 
      flexDirection: "column", 
      gap: "15px", 
      marginBottom: "10px",
      padding: isMobile ? "5px" : "0px",
      boxSizing: "border-box"
    }}>
      
      {/* Botonera de navegación estilo Siemens */}
      <div style={{ 
        display: "flex", 
        gap: "6px", 
        borderBottom: "2px solid #444", 
        paddingBottom: "10px",
        justifyContent: isMobile ? "space-between" : "flex-start"
      }}>
        {["S1", "S2", "M"].map((tab) => (
          <button 
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              backgroundColor: activeTab === tab ? "#00aa7f" : "#222",
              color: activeTab === tab ? "#000000" : "#ffffff",
              border: "1px solid #444", 
              borderRadius: "4px", 
              padding: isMobile ? "8px 10px" : "8px 16px", 
              cursor: "pointer", 
              fontWeight: "bold", 
              fontSize: isMobile ? "11px" : "12px", 
              transition: "all 0.2s",
              flex: isMobile ? "1" : "none",
              textAlign: "center"
            }}
          >
            {tab === "M" ? (isMobile ? "M Extd." : "M Extd. Ctrl.") : `${tab} Ctrl.`}
          </button>
        ))}
      </div>

      {/* Fila Superior: Instrumentos Dinámicos */}
      <div style={{ 
        display: "flex", 
        gap: "10px", 
        justifyContent: "center", 
        flexDirection: isMobile ? "column" : "row"
      }}>
        <div style={{ backgroundColor: "#252525", border: "1px solid #444", borderRadius: "6px", padding: "10px", textAlign: "center", flex: "1" }}>
          <span style={{ fontSize: "11px", color: "#aaa", fontWeight: "bold" }}>VEL. EXTRUSOR</span>
          <h2 style={{ margin: "5px 0 0 0", color: "#9b59b6", fontSize: "24px", fontFamily: "monospace" }}>
            {Number(metrics.extruderSpeed).toFixed(1)} <span style={{ fontSize: "13px" }}>Hz</span>
          </h2>
        </div>

        {activeTab === "M" ? (
          <div style={{ backgroundColor: "#252525", border: "1px solid #e74c3c", borderRadius: "6px", padding: "10px", textAlign: "center", flex: "1" }}>
            <span style={{ fontSize: "11px", color: "#aaa", fontWeight: "bold" }}>M FILTER EX- PRE.</span>
            <h2 style={{ margin: "5px 0 0 0", color: "#e74c3c", fontSize: "24px", fontFamily: "monospace" }}>
              {Number(metrics.mFilterExPre).toFixed(1)} <span style={{ fontSize: "13px" }}>Bar</span>
            </h2>
          </div>
        ) : (
          <div style={{ backgroundColor: "#252525", border: "1px solid #444", borderRadius: "6px", padding: "10px", textAlign: "center", flex: "1" }}>
            <span style={{ fontSize: "11px", color: "#aaa", fontWeight: "bold" }}>PRESIÓN DADO ({activeTab})</span>
            <h2 style={{ margin: "5px 0 0 0", color: "#00d2d3", fontSize: "24px", fontFamily: "monospace" }}>
              {Number(metrics.diePre).toFixed(1)} <span style={{ fontSize: "13px" }}>Bar</span>
            </h2>
          </div>
        )}

        {activeTab !== "M" && (
          <div style={{ backgroundColor: "#252525", border: "1px solid #444", borderRadius: "6px", padding: "10px", textAlign: "center", flex: "1", display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
            <span style={{ fontSize: "11px", color: "#aaa", fontWeight: "bold" }}>OIL PUMPS SW</span>
            <div style={{ 
              marginTop: "5px", 
              backgroundColor: (activeTab === "S1" ? metrics.s1OilPumpsSw : metrics.s2OilPumpsSw) ? "#00aa7f" : "#7f8c8d", 
              color: "#000", 
              padding: "2px 12px", 
              borderRadius: "4px", 
              fontSize: "11px", 
              fontWeight: "bold",
              fontFamily: "monospace" 
            }}>
              {(activeTab === "S1" ? metrics.s1OilPumpsSw : metrics.s2OilPumpsSw) ? "ACTIVE / 1" : "STOPPED / 0"}
            </div>
          </div>
        )}
      </div>

      {/* Matriz de Control Térmico */}
      <div style={{ backgroundColor: "#2d2d2d", padding: isMobile ? "12px" : "15px", borderRadius: "8px", border: "1px solid #444" }}>
        <div style={{ 
          display: "flex", 
          justifyContent: "space-between", 
          alignItems: "center", 
          marginBottom: "15px",
          flexDirection: isMobile ? "column" : "row",
          gap: isMobile ? "5px" : "0px",
          textAlign: "center"
        }}>
          <span style={{ fontSize: "12px", fontWeight: "bold", color: "#00aa7f", fontFamily: "sans-serif" }}>
            SCADA JAGEG — EXTRUSIÓN TELA NO TEJIDA (MÁQ 3)
          </span>
          <span style={{ fontSize: "10px", color: "#888", backgroundColor: "#1e1e1e", padding: "2px 8px", borderRadius: "10px" }}>
            VISTA ACTIVA: {activeTab === "M" ? "MELTBLOWN" : `SPUNBOND ${activeTab}`}
          </span>
        </div>
        
        {renderThermalBlocks()}
      </div>

    </div>
  );
};

export default HmiDashboard;