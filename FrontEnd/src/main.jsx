import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { FluentProvider, webDarkTheme } from '@fluentui/react-components'
import App from './App.jsx'
import './index.css' // Quita esta línea si aún no tienes un archivo CSS global

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {/* El FluentProvider aplica los estilos y el tema visual de Microsoft Fluent UI */}
    <FluentProvider theme={webDarkTheme}>
      <App />
    </FluentProvider>
  </StrictMode>,
)