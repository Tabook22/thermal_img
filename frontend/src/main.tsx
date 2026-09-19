import React from 'react'; import {createRoot} from 'react-dom/client'; import './styles.css'; import './interaction.css'; import './delete-mode.css'; import './transparent-labels.css'; import './resize-region.css'; import './rotate-region.css'; import './precision-controls.css'; import './undo.css'; import './zoom.css'; import './hotspot-snapshot.css'; import './image-details.css'; import App from './App';
import AuthGate from './Auth';
createRoot(document.getElementById('root')!).render(<React.StrictMode><AuthGate><App/></AuthGate></React.StrictMode>);
