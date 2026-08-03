import axios from 'axios';

// Usamos la variable de entorno que definimos en el paso anterior
const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  }
});

// Interceptor para manejar errores globalmente
api.interceptors.response.use(
  (response) => response,
  (error) => {
    let mensaje = "Ocurrió un error inesperado.";
    
    if (error.response) {
      // El servidor respondió con un estado fuera de 2xx
      const detail = error.response.data?.detail;
      mensaje = Array.isArray(detail) 
        ? detail.map(err => err.msg).join(" | ") 
        : (detail || `Error ${error.response.status}`);
    } else if (error.request) {
      // No hubo respuesta del servidor
      mensaje = "No se pudo conectar con el servidor. Verifique su red.";
    }
    
    // Aquí puedes disparar un evento global o usar un estado global si tienes Redux/Context
    console.error("Error capturado por interceptor:", mensaje);
    
    // Rechazamos la promesa con el mensaje limpio para que el componente lo use
    return Promise.reject(new Error(mensaje));
  }
);

export default api;
