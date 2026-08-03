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

const ThermalProfileChart = ({ linePrefix = "S1" }) => {
  const ws = useRef(null);
  const VENTANA_MUESTRAS = 20;

  // Inicializamos la estructura base de los datasets
  const [chartData, setChartData] = useState({
    labels: Array(VENTANA_MUESTRAS).fill(""),
    datasets: [
      {
        label: "Zona 1",
        data: Array(VENTANA_MUESTRAS).fill(null),
        borderColor: "#ff4d4d",
        backgroundColor: "rgba(255, 77, 77, 0.1)",
        tension: 0,
        pointRadius: 2,
        yAxisID: "y-temp"
      },
      {
        label: "Zona 2",
        data: Array(VENTANA_MUESTRAS).fill(null),
        borderColor: "#ff9f43",
        backgroundColor: "rgba(255, 159, 67, 0.1)",
        tension: 0,
        pointRadius: 2,
        yAxisID: "y-temp"
      },
      {
        label: "Zona 3",
        data: Array(VENTANA_MUESTRAS).fill(null),
        borderColor: "#f1c40f",
        backgroundColor: "rgba(241, 196, 15, 0.1)",
        tension: 0,
        pointRadius: 2,
        yAxisID: "y-temp"
      },
      {
        label: "Zona 4",
        data: Array(VENTANA_MUESTRAS).fill(null),
        borderColor: "#2ecc71",
        backgroundColor: "rgba(46, 204, 113, 0.1)",
        tension: 0,
        pointRadius: 2,
        yAxisID: "y-temp"
      }
    ]
  });

  // 💡Efecto secundario para actualizar los textos de las leyendas dinámicamente si cambia de máquina
  useEffect(() => {
    const isM = linePrefix === "M";
    setChartData(prev => ({
      ...prev,
      datasets: [
        { ...prev.datasets[0], label: isM ? "Meltblown Z1 (Cañón)" : `${linePrefix} Z1 - Alimentación` },
        { ...prev.datasets[1], label: isM ? "Meltblown Z2 (Cañón)" : `${linePrefix} Z2 - Compresión` },
        { ...prev.datasets[2], label: isM ? "Meltblown Z3 (Cañón)" : `${linePrefix} Z3 - Dosificación` },
        { ...prev.datasets[3], label: isM ? "Meltblown Z4 (Dado)" : `${linePrefix} Z4 - Mezclado/Salida` }
      ]
    }));
  }, [linePrefix]);

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

        // Construcción dinámica de llaves exactamente igual a scada_tags
        const pz1 = `${linePrefix}_PV_Z1`;
        const pz2 = `${linePrefix}_PV_Z2`;
        const pz3 = `${linePrefix}_PV_Z3`;
        const pz4 = `${linePrefix}_PV_Z4`;

        setChartData((prevData) => {
          // 🛡️ Recuperamos el último valor en el arreglo para evitar caídas falsas a 0 si el paquete falla
          const lastZ1 = prevData.datasets[0].data[prevData.datasets[0].data.length - 1] || 0;
          const lastZ2 = prevData.datasets[1].data[prevData.datasets[1].data.length - 1] || 0;
          const lastZ3 = prevData.datasets[2].data[prevData.datasets[2].data.length - 1] || 0;
          const lastZ4 = prevData.datasets[3].data[prevData.datasets[3].data.length - 1] || 0;

          const z1 = tags[pz1] !== undefined ? tags[pz1] : lastZ1;
          const z2 = tags[pz2] !== undefined ? tags[pz2] : lastZ2;
          const z3 = tags[pz3] !== undefined ? tags[pz3] : lastZ3;
          const z4 = tags[pz4] !== undefined ? tags[pz4] : lastZ4;

          const nuevasLabels = [...prevData.labels.slice(1), horaActual];
          const nuevaZ1 = [...prevData.datasets[0].data.slice(1), z1];
          const nuevaZ2 = [...prevData.datasets[1].data.slice(1), z2];
          const nuevaZ3 = [...prevData.datasets[2].data.slice(1), z3];
          const nuevaZ4 = [...prevData.datasets[3].data.slice(1), z4];

          return {
            labels: nuevasLabels,
            datasets: [
              { ...prevData.datasets[0], data: nuevaZ1 },
              { ...prevData.datasets[1], data: nuevaZ2 },
              { ...prevData.datasets[2], data: nuevaZ3 },
              { ...prevData.datasets[3], data: nuevaZ4 }
            ]
          };
        });
      } catch (error) {
        console.error("Error al procesar el perfil térmico dinámico:", error);
      }
    };

    return () => {
      if (ws.current && ws.current.readyState === WebSocket.OPEN) {
        ws.current.close();
      }
    };
  }, [linePrefix]);

  const options = {
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
        grid: { color: "rgba(255, 255, 255, 0.05)" },
        ticks: { 
          color: "#ffffff",
          autoSkip: true,      
          maxTicksLimit: 5,     
          maxRotation: 0,      
          minRotation: 0
        }
      },
      "y-temp": {
        type: "linear",
        position: "left",
        title: { display: true, text: `Temperatura Linea ${linePrefix} (°C)`, color: "#ffffff" },
        min: 0,
        max: 300,
        grid: { color: "rgba(255, 255, 255, 0.08)" },
        ticks: { color: "#ffffff" }
      }
    }
  };

  return (
    <div style={{ 
      width: "100%", 
      height: window.innerWidth <= 768 ? "320px" : "420px", 
      padding: "10px",
      backgroundColor: "#1e1e1e",
      borderRadius: "6px",
      border: "1px solid #333"
    }}>
      <Line data={chartData} options={options} />
    </div>
  );
};

export default ThermalProfileChart;