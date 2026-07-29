/**
 * Dev-only visual harness for Sol (bd polyglot-pdf-2p4y).
 *
 * Renders the REAL shared component in every state, at both shipped sizes, on
 * both the near-white panel background and the mobile FAB treatment, so the
 * states can be eyeballed without a live Gemini session. Not part of any build
 * entry point that ships -- it is reachable only via /sol-preview.html in dev.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Sol, SOL_CSS, SOL_PLACEMENT_CSS } from '../shared/Sol'
import { deriveSolState, SOL_STATE_LABEL } from '../shared/solState'
import type { SolState } from '../shared/solState'

const STATES: SolState[] = [
  'idle', 'connecting', 'listening', 'thinking', 'speaking', 'paused', 'offline',
]

// A syllable-shaped envelope so the amplitude-driven states can be judged
// without a live model: attack, decay, word gaps, a breath in the middle.
const SYLL: Array<[number, number, number]> = [
	[0.0, 0.34, 72], [0.46, 0.3, 55],
	[1.05, 0.2, 62], [1.28, 0.22, 80], [1.54, 0.18, 50],
	[1.8, 0.2, 66], [2.02, 0.26, 85], [2.32, 0.2, 58],
	[2.6, 0.18, 60], [2.82, 0.2, 55],
	[3.2, 0.22, 74], [3.46, 0.24, 88], [3.74, 0.2, 62],
	[3.98, 0.22, 70], [4.24, 0.3, 44],
]
const DUR = 5.1

/**
 * Returns BOTH a re-rendering state value (for the `energy` prop, which
 * listening/idle/etc. consume) and a stable getter reading the same value from
 * a ref (for `getOutputEnergy`, which speaking consumes). Sol intentionally
 * takes the two amplitude sources through different shapes -- one is threaded
 * through React state, the other is a per-frame pull specifically so the
 * component does not re-render 50x/sec -- so the harness has to supply both
 * shapes or whichever state reads the getter goes static. That is exactly the
 * bug this fixes: after the listening/speaking swap, speaking started reading
 * getOutputEnergy, which this preview never supplied.
 */
function useFakeEnergy(): { energy: number; getEnergy: () => number } {
	const [e, setE] = useState(0)
	const ref = useRef(0)
	useEffect(() => {
		let raf = 0
		const t0 = performance.now()
		const tick = () => {
			const t = ((performance.now() - t0) / 1000) % DUR
			let v = 0
			for (const [s0, len, amp] of SYLL) {
				if (t >= s0 && t <= s0 + len) {
					const u = (t - s0) / len
					v = Math.max(v, amp * Math.sin(Math.PI * Math.pow(u, 0.7)))
				}
			}
			ref.current = v
			setE(v)
			raf = requestAnimationFrame(tick)
		}
		raf = requestAnimationFrame(tick)
		return () => cancelAnimationFrame(raf)
	}, [])
	const getEnergy = useCallback(() => ref.current, [])
	return { energy: e, getEnergy }
}

function App() {
	const { energy, getEnergy } = useFakeEnergy()
	const [rm, setRm] = useState(false)

	// Real status strings the overlays can emit -> the state each maps to.
	const statusProbe = [
		'Ready', 'connecting', 'connected', 'connected section_2', 'switching_section',
		'reconnecting', 'paused', 'disconnected', 'idle_timeout', 'error', 'reconnect_failed',
	]

	return (
		<div style={{ padding: 24, font: '14px system-ui, sans-serif', color: '#1c2233' }}>
			{/* The SHIPPED stylesheet + the SHIPPED placement rules, imported rather
			    than hand-copied -- a harness that silently diverges from production
			    is worse than no harness, since its whole job is to be signed off on. */}
			<style>{SOL_CSS}</style>
			<style>{SOL_PLACEMENT_CSS}</style>
			<style>{`
				body { background: #f3f4f6; margin: 0; }
				h2 { font-size: 12px; letter-spacing: .12em; text-transform: uppercase;
				     color: #6b7280; margin: 26px 0 10px; }
				.row { display: flex; flex-wrap: wrap; gap: 16px; }
				.cell { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px;
				        padding: 14px; width: 150px; text-align: center; }
				.nm { font-size: 11px; color: #6b7280; margin-top: 8px;
				      letter-spacing: .06em; text-transform: uppercase; }
				.statusrow { display: flex; align-items: center; gap: 10px; background: #f9fafb;
				             border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px 12px; }
				/* Harness-only scaffolding (a stand-in for the page the FAB floats over). */
				.fabwrap { width: 110px; height: 110px; border-radius: 16px;
				           background: linear-gradient(135deg,#7c3aed,#c084fc);
				           display: flex; align-items: center; justify-content: center; }
				.fab { position: relative; width: 56px; height: 56px; }
				.rm .sol * { animation: none !important; }
				table { border-collapse: collapse; font-size: 13px; background: #fff; }
				td, th { border: 1px solid #e5e7eb; padding: 5px 10px; text-align: left; }
			`}</style>
			<div className={rm ? 'rm' : ''}>
				<label style={{ display: 'block', marginBottom: 12 }}>
					<input type="checkbox" checked={rm} onChange={e => setRm(e.target.checked)} />{' '}
					simulate reduced motion (kills animations)
				</label>

				<h2>All {STATES.length} states -- panel size (40px), on white</h2>
				<div className="row">
					{STATES.map(s => (
						<div className="cell" key={s} data-probe={s}>
							<Sol state={s} energy={energy} getOutputEnergy={getEnergy} size={40} />
							<div className="nm">{s}</div>
						</div>
					))}
				</div>

				<h2>Large (120px) -- detail check</h2>
				<div className="row">
					{STATES.map(s => (
						<div className="cell" key={s} style={{ width: 170 }}>
							<Sol state={s} energy={energy} getOutputEnergy={getEnergy} size={120} />
							<div className="nm">{s}</div>
						</div>
					))}
				</div>

				<h2>Mobile FAB (56px) over page content</h2>
				<div className="row">
					{STATES.map(s => (
						<div key={s} style={{ textAlign: 'center' }}>
							<div className="fabwrap">
								<div className="fab">
									<Sol state={s} energy={energy} getOutputEnergy={getEnergy} size={56} className="vff-fab-sol" decorative />
								</div>
							</div>
							<div className="nm">{s}</div>
						</div>
					))}
				</div>

				<h2>Desktop status row in context</h2>
				<div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 360 }}>
					{STATES.map(s => (
						<div className="statusrow" key={s}>
							<Sol state={s} energy={energy} getOutputEnergy={getEnergy} size={40} className="vff-sol" />
							<span style={{ fontWeight: 500 }}>{SOL_STATE_LABEL[s]}</span>
						</div>
					))}
				</div>

				<h2>Status string -&gt; state mapping (live from deriveSolState)</h2>
				<table id="mapping">
					<thead><tr><th>status</th><th>+micSending</th><th>+thinking</th><th>+speaking</th></tr></thead>
					<tbody>
						{statusProbe.map(st => (
							<tr key={st}>
								<td><code>{st}</code></td>
								<td>{deriveSolState({ status: st, micSending: true })}</td>
								<td>{deriveSolState({ status: st, thinking: true })}</td>
								<td>{deriveSolState({ status: st, speaking: true })}</td>
							</tr>
						))}
					</tbody>
				</table>
			</div>
		</div>
	)
}

createRoot(document.getElementById('root')!).render(<App />)
