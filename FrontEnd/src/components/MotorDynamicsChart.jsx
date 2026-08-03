import React, { useEffect, useState, useRef } from "react";
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

const MotorDynamicsChart = () => {
  const ws = useRef(null);
  const VENTANA_MUESTRAS = 20;

  // Inicializamos la estructura con colores de alto contraste industrial
  const [chartData, setChartData] = useState({
    labels: Array(VENTANA_MUESTRAS).fill(""),
    datasets: [
      {
        label: "Extrusor Principal (Valor PLC)",
        data: Array(VENTANA_MUESTRAS).fill(null),
        borderColor: "#9b59b6",
        backgroundColor: "rgba(155, 89, 182, 0.1)",
        tension: 0,
        pointRadius: 2,
        yAxisID: "y-motores"
      },
      {
        label: "Bomba Hiladora (VDF Real)",
        data: Array(VENTANA_MUESTRAS).fill(null),
        borderColor: "#3498db",
        backgroundColor: "rgba(52, 152, 219, 0.1)",
        tension: 0,
        pointRadius: 2,
        yAxisID: "y-motores"
      },
      {
        label: "Motor Succión / Arrastre",
        data: Array(VENTANA_MUESTRAS).fill(null),
        borderColor: "#e67e22",
        backgroundColor: "rgba(230, 126, 34, 0.1)",
        tension: 0,
        pointRadius: 2,
        yAxisID: "y-motores"
      }
    ]
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
        const tags = payload.tags || payload;

        if (!tags) return;

        const horaActual = payload.timestamp 
          ? new Date(payload.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) 
          : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

        // 🛡️ Mapeo robusto con búsqueda por aproximación de nombres si hay discrepancia en scada_tags
        const velExtrusor = tags.PV_M_INCOEX_RPM !== undefined ? tags.PV_M_INCOEX_RPM : 0;
        const velBomba = tags.PV_BOMBA_HILADORA !== undefined ? tags.PV_BOMBA_HILADORA : 0;
        
        // Fallback dinámico para el motor de arrastre/succión
        let velSuction = tags.PV_M_SUCTION;
        if (velSuction === undefined) {
          const altKey = Object.keys(tags).find(k => k.toUpperCase().includes("SUCTION") || k.toUpperCase().includes("ARRASTRE"));
          velSuction = altKey ? tags[altKey] : 0;
        }

        setChartData((prevData) => {
          const nuevasLabels = [...prevData.labels.slice(1), horaActual];
          const nuevaVelExt = [...prevData.datasets[0].data.slice(1), velExtrusor];
          const nuevaVelBom = [...prevData.datasets[1].data.slice(1), velBomba];
          const nuevaVelSuc = [...prevData.datasets[2].data.slice(1), velSuction];

          return {
            labels: nuevasLabels,
            datasets: [
              { ...prevData.datasets[0], data: nuevaVelExt },
              { ...prevData.datasets[1], data: nuevaVelBom },
              { ...prevData.datasets[2], data: nuevaVelSuc }
            ]
          };
        });
      } catch (error) {
        console.error("Error al procesar la dinámica de motores en SCADA V2:", error);
      }
    };

    return () => {
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        ws.current.close();
      }
    };
  }, []);

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: {
        position: "top",
        labels: { color: "#ffffff", font: { family: "Segoe UI", size: 12 } }
      },
      tooltip: { mode: "index", intersect: false }
    },
    scales: {
      x: {
        grid: { color: "rgba(255, 255, 255, 0.05)" },
        ticks: { 
          color: "#ffffff",
          autoSkip: true,      
          maxTicksLimit: 5,     
          maxRotation: 0,      
          minRotation: 0
        }
      },
      "y-motores": {
        type: "linear",
        position: "left",
        title: { display: true, text: "Frecuencia / Velocidad (Rango Dinámico)", color: "#ffffff" },
        min: 0,
        // 💡 Ajustamos a 300 para acomodar holgadamente los 230 Hz/RPM reales de la planta sin desbordar la escala
        suggestedMax: 300, 
        grid: { color: "rgba(255, 255, 255, 0.08)" },
        ticks: { color: "#ffffff" }
      }
    }
  };

  return (
    <div style={{ 
      width: "100%", 
      height: window.innerWidth <= 768 ? "300px" : "420px", 
      padding: "10px",
      backgroundColor: "#1e1e1e",
      borderRadius: "6px",
      border: "1px solid #333"
    }}>
      <Line data={chartData} options={options} />
    </div>
  );
};

export default MotorDynamicsChart;