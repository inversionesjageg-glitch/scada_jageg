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

const ExtrusionChart = () => {
  const ws = useRef(null);
  
  // ⏱️ 20 muestras consecutivas en pantalla para evitar saturación de memoria
  const VENTANA_MUESTRAS = 20;

  // Inicializamos la estructura de datos compatible con Chart.js
  const [chartData, setChartData] = useState({
    labels: Array(VENTANA_MUESTRAS).fill(""),
    datasets: [
      {
        label: "Temp. Zona 4 Spunbond 1 (°C)",
        data: Array(VENTANA_MUESTRAS).fill(null),
        borderColor: "#ff9f43",
        backgroundColor: "rgba(255, 159, 67, 0.2)",
        yAxisID: "y-temp",
        tension: 0, // Líneas totalmente rectas sin curvas suavizadas (Estilo Siemens)
        pointRadius: 2
      },
      {
        label: "Presión de Masa en Dado (Bar)",
        data: Array(VENTANA_MUESTRAS).fill(null),
        borderColor: "#00d2d3",
        backgroundColor: "rgba(0, 210, 211, 0.2)",
        yAxisID: "y-presion",
        tension: 0,
        pointRadius: 2
      }
    ]
  });

  useEffect(() => {
    const backendUrl = import.meta.env.VITE_API_URL || "http://localhost:8080";
    // Corregimos la ruta del endpoint unificándolo con la del HMI (/api/v1/stream/ws/hmi)
    const wsUrl = backendUrl.replace(/^http/, "ws") + "/api/v1/stream/ws/hmi";
    
    if (ws.current && (ws.current.readyState === WebSocket.OPEN || ws.current.readyState === WebSocket.CONNECTING)) {
      return;
    }

    ws.current = new WebSocket(wsUrl);

    ws.current.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        // Tolerancia si viene empaquetado en "tags" o directo
        const tags = payload.tags || payload;

        if (!tags) return;

        // Extraer marca de tiempo local para el eje X
        const horaActual = payload.timestamp 
          ? new Date(payload.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) 
          : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });

        // 🛡️ Extracción de tags con tolerancia y fallback según la base de datos real
        const temperaturaZ4 = tags.S1_PV_Z4 !== undefined ? tags.S1_PV_Z4 : 0;
        
        // Buscamos PV_DIE_PRE, o variaciones como PV_FILTER_EX_PRE, por si cambia el tag en scada_tags
        const presionCabezal = tags.PV_DIE_PRE !== undefined 
          ? tags.PV_DIE_PRE 
          : (tags.PV_FILTER_EX_PRE !== undefined ? tags.PV_FILTER_EX_PRE : 0);

        setChartData((prevData) => {
          // Desplazamiento rígido de la cola (Ventana Deslizante)
          const nuevasLabels = [...prevData.labels.slice(1), horaActual];
          const nuevaTemp = [...prevData.datasets[0].data.slice(1), temperaturaZ4];
          const nuevaPresion = [...prevData.datasets[1].data.slice(1), presionCabezal];

          return {
            labels: nuevasLabels,
            datasets: [
              { ...prevData.datasets[0], data: nuevaTemp },
              { ...prevData.datasets[1], data: nuevaPresion }
            ]
          };
        });
      } catch (error) {
        console.error("Error al decodificar ráfaga en gráfica histórica:", error);
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
    animation: false, // Desactivar animaciones es crucial para evitar saltos en tiempo real
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
          maxTicksLimit: 5, // Evita que los tiempos se encimen en pantallas de celulares    
          maxRotation: 0,      
          minRotation: 0
        }
      },
      "y-temp": {
        type: "linear",
        position: "left",
        title: { display: true, text: "Temperatura (°C)", color: "#ff9f43" },
        min: 0,
        max: 300, // Escala ajustada para el rango de extrusión de polietileno/tela no tejida
        grid: { color: "rgba(255, 255, 255, 0.08)" },
        ticks: { color: "#ff9f43" }
      },
      "y-presion": {
        type: "linear",
        position: "right",
        title: { display: true, text: "Presión (Bar)", color: "#00d2d3" },
        min: 0,
        max: 200,
        grid: { drawOnChartArea: false }, // Evita que se cruce la cuadrícula con la de temperatura
        ticks: { color: "#00d2d3" }
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

export default ExtrusionChart;