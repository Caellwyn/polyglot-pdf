/**
 * VAD Tuning Dashboard Entry Point
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import { VADTuningDashboard } from './VADTuningDashboard'

const root = ReactDOM.createRoot(document.getElementById('root') as HTMLElement)
root.render(
	<React.StrictMode>
		<VADTuningDashboard />
	</React.StrictMode>
)
