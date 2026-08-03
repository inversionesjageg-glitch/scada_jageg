import React, { useState, useEffect } from "react";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
} from "chart.js";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const HistoricalAnalyticsPanel = () => {
  const [linea, setLinea] = useState("spunbond_1");
  const [agruparPor, setAgruparPor] = useState("1m");
  const [fechaInicio, setFechaInicio] = useState("");
  const [fechaFin, setFechaFin] = useState("");
  const [variableActiva, setVariableActiva] = useState("pv_zona1");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [rawTimeline, setRawTimeline] = useState([]);
  const [stats, setStats] = useState({});

  useEffect(() => {
    const fin = new Date();
    const inicio = new Date(fin.getTime() - 2 * 60 * 60 * 1000);
    
    const formatDateTime = (date) => {
      const tzOffset = date.getTimezoneOffset() * 60000;
      return new Date(date - tzOffset).toISOString().slice(0, 16);
    };

    setFechaFin(formatDateTime(fin));
    setFechaInicio(formatDateTime(inicio));
  }, []);

  const consultarHistorial = async () => {
    setLoading(true);
    setError(null);

    let fechaInicioLimpia = fechaInicio;
    let fechaFinLimpia = fechaFin;

    if (fechaInicioLimpia && fechaInicioLimpia.length === 16) {
      fechaInicioLimpia += ":00";
    }
    if (fechaFinLimpia && fechaFinLimpia.length === 16) {
      fechaFinLimpia += ":00";
    }

    if (new Date(fechaInicioLimpia) >= new Date(fechaFinLimpia)) {
      alert("La fecha de inicio debe ser estrictamente anterior a la fecha de fin.");
      setLoading(false);
      return;
    }

    try {
      const baseUrl = import.meta.env.VITE_API_URL || "http://app.grupopolytex.com:8080";    
   
      // CORREGIDO: Removido el fragmento "Linter" que causaba el quiebre de la referencia
      const url = `${baseUrl}/api/v1/analytics/trends?linea=${linea}&fecha_inicio=${fechaInicioLimpia}&fecha_fin=${fechaFinLimpia}&agrupar_por=${agruparPor}`;

      const response = await fetch(url);
      const resData = await response.json();

      if (!response.ok) {
        throw new Error(resData.detail || "Fallo en la comunicación con el servidor SCADA.");
      }
      
      if (resData.status === "success") {
        setRawTimeline(resData.data);
        setStats(resData.statistics || {});
        
        if (resData.data.length > 0) {
          const llavesDisponibles = Object.keys(resData.data[0]).filter(k => k !== "timestamp" && k !== "id");
          if (!llavesDisponibles.includes(variableActiva)) {
            setVariableActiva(llavesDisponibles[0]);
          }
        }
      }
    } catch (err) {
      console.error("Error analítico:", err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const prepararDatosGrafica = () => {
    const labels = rawTimeline.map(r => 
      new Date(r.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    );
    const dataPuntos = rawTimeline.map(r => r[variableActiva] ?? null);
    const varStats = stats[variableActiva] || { promedio: null, lsc: null, lic: null };

    const datasets = [
      {
        label: `Valor Variable Real (${variableActiva.toUpperCase()})`,
        data: dataPuntos,
        borderColor: "#3498db",
        backgroundColor: "rgba(52, 152, 219, 0.05)",
        tension: 0.1,
        pointRadius: agruparPor === "crudo" ? 1 : 2,
        borderWidth: 2,
        yAxisID: "y"
      }
    ];

    if (varStats.promedio !== null) {
      datasets.push({
        label: `Media Global SPC (${varStats.promedio})`,
        data: Array(labels.length).fill(varStats.promedio),
        borderColor: "#f1c40f",
        borderWidth: 1.5,
        borderDash: [6, 4],
        pointRadius: 0,
        fill: false
      });
    }
    if (varStats.lsc !== null) {
      datasets.push({
        label: `Límite Sup. Control LSC (${varStats.lsc})`,
        data: Array(labels.length).fill(varStats.lsc),
        borderColor: "#e74c3c",
        borderWidth: 1.5,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false
      });
    }
    if (varStats.lic !== null) {
      datasets.push({
        label: `Límite Inf. Control LIC (${varStats.lic})`,
        data: Array(labels.length).fill(varStats.lic),
        borderColor: "#e74c3c",
        borderWidth: 1.5,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false
      });
    }

    return { labels, datasets };
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false, 
    plugins: {
      legend: { 
        position: "top",
        labels: { color: "#ffffff", font: { family: "Segoe UI", size: 11 } } 
      },
      tooltip: { mode: "index", intersect: false }
    },
    scales: {
      x: { 
        grid: { color: "rgba(255, 255, 255, 0.03)" }, 
        ticks: { color: "#aaaaaa", font: { family: "Segoe UI" } } 
      },
      y: { 
        grid: { color: "rgba(255, 255, 255, 0.07)" }, 
        ticks: { color: "#ffffff", font: { family: "Segoe UI" } } 
      }
    }
  };

  const activeVarStats = stats[variableActiva] || { maximo: 0, minimo: 0, promedio: 0, desviacion_estandar: 0 };

  return (
    <div style={{ padding: "20px", backgroundColor: "#121212", minHeight: "100vh", color: "#ffffff", fontFamily: "Segoe UI, sans-serif" }}>
      
      {/* SECCIÓN 1: PANEL DE CONTROL */}
      <div style={{ 
        backgroundColor: "#1e1e1e", 
        padding: "15px", 
        borderRadius: "8px", 
        border: "1px solid #333", 
        marginBottom: "20px", 
        display: "flex", 
        gap: "15px", 
        flexWrap: "wrap", 
        alignItems: "flex-end" 
      }}>
        <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
          <label style={{ fontSize: "12px", color: "#aaa" }}>Línea / Componente</label>
          <select value={linea} onChange={(e) => setLinea(e.target.value)} style={{ padding: "8px", backgroundColor: "#2b2b2b", color: "#fff", border: "1px solid #444", borderRadius: "4px" }}>
            <option value="spunbond_1">Spunbond 1 (S1)</option>
            <option value="spunbond_2">Spunbond 2 (S2)</option>
            <option value="meltblown">Meltblown (M)</option>
            <option value="dosificacion_global">Dosificación Global</option>
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
          <label style={{ fontSize: "12px", color: "#aaa" }}>Remuestreo (Downsampling)</label>
          <select value={agruparPor} onChange={(e) => setAgruparPor(e.target.value)} style={{ padding: "8px", backgroundColor: "#2b2b2b", color: "#fff", border: "1px solid #444", borderRadius: "4px" }}>
            <option value="crudo">Datos Crudos</option>
            <option value="1m">1 Minuto (Producción)</option>
            <option value="5m">5 Minutos</option>
            <option value="1h">1 Hora (Gerencial)</option>
            <option value="1d">1 Día (Histórico Largo)</option>
          </select>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
          <label style={{ fontSize: "12px", color: "#aaa" }}>Fecha Inicial</label>
          <input type="datetime-local" value={fechaInicio} onChange={(e) => setFechaInicio(e.target.value)} style={{ padding: "7px", backgroundColor: "#2b2b2b", color: "#fff", border: "1px solid #444", borderRadius: "4px" }} />
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
          <label style={{ fontSize: "12px", color: "#aaa" }}>Fecha Final</label>
          <input type="datetime-local" value={fechaFin} onChange={(e) => setFechaFin(e.target.value)} style={{ padding: "7px", backgroundColor: "#2b2b2b", color: "#fff", border: "1px solid #444", borderRadius: "4px" }} />
        </div>

        <button 
          onClick={consultarHistorial} 
          disabled={loading} 
          style={{ padding: "9px 20px", backgroundColor: "#3498db", color: "#fff", border: "none", borderRadius: "4px", fontWeight: "bold", cursor: loading ? "not-allowed" : "pointer" }}
        >
          {loading ? "Procesando..." : "Analizar Tendencias"}
        </button>

        <button 
          onClick={() => {
            const baseUrl = import.meta.env.VITE_API_URL || "http://app.grupopolytex.com:8080";
            let fInicioExcel = fechaInicio;
            let fFinExcel = fechaFin;
            if (fInicioExcel && fInicioExcel.length === 16) fInicioExcel += ":00";
            if (fFinExcel && fFinExcel.length === 16) fFinExcel += ":00";
    
            const downloadUrl = `${baseUrl}/api/v1/analytics/export?linea=${linea}&fecha_inicio=${fInicioExcel}&fecha_fin=${fFinExcel}&agrupar_por=${agruparPor}`;
            window.location.href = downloadUrl;
          }}
          disabled={loading || rawTimeline.length === 0}
          style={{ 
            padding: "9px 20px", 
            backgroundColor: rawTimeline.length === 0 ? "#333" : "#2ecc71", 
            color: "#fff", 
            border: "none", 
            borderRadius: "4px", 
            fontWeight: "bold", 
            cursor: rawTimeline.length === 0 ? "not-allowed" : "pointer"
          }}
        >
          📥 Descargar Excel
        </button>
      </div>

      {error && <div style={{ color: "#ff4d4d", marginBottom: "15px", fontWeight: "bold" }}>⚠️ Error: {error}</div>}

      {/* SECCIÓN 2: SECTOR ESTADÍSTICO INTERACTIVO */}
      {rawTimeline.length > 0 && (
        <>
          <div style={{ marginBottom: "15px", display: "flex", gap: "10px", alignItems: "center" }}>
            <span style={{ fontSize: "14px", color: "#bbb" }}>Variable de Inspección SPC activa:</span>
            <select value={variableActiva} onChange={(e) => setVariableActiva(e.target.value)} style={{ padding: "5px 10px", backgroundColor: "#1e1e1e", color: "#3498db", border: "1px solid #3498db", borderRadius: "4px", fontWeight: "bold" }}>
              {Object.keys(rawTimeline[0]).filter(k => k !== "timestamp" && k !== "id").map(key => (
                <option key={key} value={key}>{key.toUpperCase()}</option>
              ))}
            </select>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "15px", marginBottom: "20px" }}>
            <div style={{ backgroundColor: "#1e1e1e", padding: "15px", borderRadius: "6px", border: "1px solid #333", borderLeft: "4px solid #f1c40f" }}>
              <div style={{ fontSize: "11px", color: "#aaa", textTransform: "uppercase" }}>Promedio Central</div>
              <div style={{ fontSize: "24px", fontWeight: "bold", marginTop: "5px", color: "#f1c40f" }}>{activeVarStats.promedio}</div>
            </div>
            <div style={{ backgroundColor: "#1e1e1e", padding: "15px", borderRadius: "6px", border: "1px solid #333", borderLeft: "4px solid #9b59b6" }}>
              <div style={{ fontSize: "11px", color: "#aaa", textTransform: "uppercase" }}>Desviación Estándar (Sigma)</div>
              <div style={{ fontSize: "24px", fontWeight: "bold", marginTop: "5px", color: "#9b59b6" }}>± {activeVarStats.desviacion_estandar}</div>
            </div>
            <div style={{ backgroundColor: "#1e1e1e", padding: "15px", borderRadius: "6px", border: "1px solid #333", borderLeft: "4px solid #2ecc71" }}>
              <div style={{ fontSize: "11px", color: "#aaa", textTransform: "uppercase" }}>Valor Máximo</div>
              <div style={{ fontSize: "24px", fontWeight: "bold", marginTop: "5px", color: "#2ecc71" }}>{activeVarStats.maximo}</div>
            </div>
            <div style={{ backgroundColor: "#1e1e1e", padding: "15px", borderRadius: "6px", border: "1px solid #333", borderLeft: "4px solid #e74c3c" }}>
              <div style={{ fontSize: "11px", color: "#aaa", textTransform: "uppercase" }}>Valor Mínimo</div>
              <div style={{ fontSize: "24px", fontWeight: "bold", marginTop: "5px", color: "#e74c3c" }}>{activeVarStats.minimo}</div>
            </div>
          </div>

          <div style={{ backgroundColor: "#1e1e1e", height: "450px", padding: "15px", borderRadius: "8px", border: "1px solid #333" }}>
            <Line data={prepararDatosGrafica()} options={chartOptions} />
          </div>
        </>
      )}

      {rawTimeline.length === 0 && !loading && (
        <div style={{ textAlign: "center", padding: "60px", color: "#555", border: "2px dashed #222", borderRadius: "8px", fontSize: "15px" }}>
          Defina el rango de fechas e histórico industrial arriba y haga clic en "Analizar Tendencias".
        </div>
      )}
    </div>
  );
};

export default HistoricalAnalyticsPanel;