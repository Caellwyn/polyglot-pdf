/**
 * Sol -- the voice assistant's avatar and status indicator in one
 * (bd polyglot-pdf-2p4y).
 *
 * One SVG object replaced three widgets: the connection dot, the mic level meter,
 * and (on mobile) the pulsing blue circle on the FAB. Each of those was reporting
 * something the user had not asked about; Sol answers the only question they
 * actually have -- is it my turn?
 *
 * NO LETTERS ANYWHERE. Every state is legible to someone who cannot read English,
 * which matters because the app ships in 17+ spoken languages. Sleep is a crescent
 * moon with drifting stars, not "Zzz" (a Western comics convention, and more to
 * the point: reading).
 *
 * The state grammar, and why each state looks the way it does:
 *
 *   idle       Warm, awake, barely breathing. Rays turn very slowly.
 *   listening  The rays STOP DEAD and breathe in length with mic energy.
 *              Stillness is the correct grammar for attention -- a thing that
 *              keeps moving while you talk looks busy with something else.
 *   thinking   Rays turn (16s/rev, NOT 1s -- a fast spinner reads as "waiting",
 *              and the user has done enough waiting) and light catches on them.
 *   speaking   The halo does the talking: two rings swell out of the sphere and
 *              fade. A shape crossing empty space stays visible at 28px, where a
 *              few percent of scale on the disc does not.
 *   paused     Crescent moon + drifting stars. The user chose this; all is well.
 *   offline    Sol LEAVES. What is left is the cloud he lives in, crossed out.
 *              The only state allowed to be unreassuring, because it is the only
 *              one where something is actually wrong.
 *
 * This file is the single source of the SVG + CSS. The two overlays
 * (VoiceOverlay / VoiceOverlayMobile) are hand-duplicated of each other, so
 * pasting ~200 lines of avatar into both would guarantee drift -- they both
 * import this instead.
 *
 * ASCII-only source per CLAUDE.md scar #6.
 */

import React, { useEffect, useMemo, useRef } from 'react'
import type { SolState } from './solState'
import { SOL_STATE_LABEL } from './solState'

/**
 * Amplitude smoothing. Two constants, not one, and that is the whole trick:
 *
 *   FAST (~120ms) drives GEOMETRY -- scale, ray length, ring size -- where a
 *   quick response is exactly what makes the thing feel alive.
 *   SLOW (~230ms) drives LIGHT ONLY -- brightness and opacity. The eye
 *   integrates luminance over time, so a brightness swing that tracks every
 *   syllable reads as FLICKER even at tiny amplitude, while the same swing in
 *   SIZE at the same speed just reads as responsive.
 *
 * Splitting them lets motion stay snappy and light stay calm. Below roughly
 * 150ms on the slow value the flicker comes back.
 */
const FAST_ALPHA = 0.14
const SLOW_ALPHA = 0.075

/**
 * The amplitude swing is capped deliberately: the disc moves ~6% and brightens
 * ~7%, nowhere near a flash hazard, which matters a great deal on a large bright
 * shape. The visible work is done by the rings, which cost no luminance.
 */

export interface SolProps {
	/** Which of the six states to render. */
	state: SolState
	/**
	 * Live amplitude, 0-100 (the audio worklet's smoothed RMS scale). Drives the
	 * listening ray-breathing and the speaking halo. Ignored in states that do
	 * not use it.
	 */
	energy?: number
	/** Rendered pixel size. The motion multiplier scales inversely (see --k). */
	size?: number
	/**
	 * Motion multiplier override. Defaults to a size-derived value: SMALLER
	 * instances move MORE, which is the opposite of the usual instinct and the
	 * reason most small indicators read as static. At 3 inches across an 8% ray
	 * excursion is plenty; at half an inch it is invisible.
	 */
	motionScale?: number
	/** Extra class on the <svg>. */
	className?: string
	/**
	 * When true the avatar is decorative and the surrounding UI carries the
	 * accessible name (used on the mobile FAB, whose button is already labelled).
	 */
	decorative?: boolean
	/** Optional accessible-name override. */
	label?: string
}

/** Ray geometry: 8 long + 8 short, symmetrical. */
const RAYS_A = Array.from({ length: 8 }, (_, i) => {
	const a = (i / 8) * Math.PI * 2
	return {
		x1: 100 + Math.cos(a) * 53,
		y1: 100 + Math.sin(a) * 53,
		x2: 100 + Math.cos(a) * 70,
		y2: 100 + Math.sin(a) * 70,
	}
})
const RAYS_B = Array.from({ length: 8 }, (_, i) => {
	const a = (i / 8) * Math.PI * 2 + Math.PI / 8
	return {
		x1: 100 + Math.cos(a) * 52,
		y1: 100 + Math.sin(a) * 52,
		x2: 100 + Math.cos(a) * 62,
		y2: 100 + Math.sin(a) * 62,
	}
})

/** Four-point sparkles for the thinking state. */
const TWINKLES: Array<[number, number]> = [
	[62, 54], [146, 66], [54, 120], [142, 132], [100, 40],
]
/** Drifting stars for the paused (moon) state. */
const STARS: Array<[number, number, number]> = [
	[150, 72, 2.6], [58, 88, 2], [136, 44, 1.7],
]

/**
 * Gradient ids must be unique per document, but every Sol instance needs its own
 * <defs> only because SVG gradients cannot be shared across separate <svg> roots
 * reliably once one is removed from the DOM. A module-level counter keeps the ids
 * distinct without pulling in a uuid dependency.
 */
let solInstanceSeq = 0

export function Sol({
	state,
	energy = 0,
	size = 56,
	motionScale,
	className = '',
	decorative = false,
	label,
}: SolProps) {
	const svgRef = useRef<SVGSVGElement>(null)
	// Stable per-instance id suffix for the gradient / mask defs.
	const uid = useMemo(() => `sol${++solInstanceSeq}`, [])

	// Smaller renders need bolder motion to read at all. 56px (the FAB) lands at
	// ~2x, a 120px panel avatar at ~1x.
	const k = motionScale ?? Math.max(1, Math.min(2.4, 130 / Math.max(24, size)))

	/**
	 * Amplitude -> CSS custom properties, written straight to the node.
	 *
	 * This deliberately bypasses React state: the source updates ~50x/sec, and
	 * re-rendering a 40-node SVG at that rate to change two numbers would be
	 * pure waste. The rAF loop writes --e / --eb on the element and CSS does the
	 * rest, so React re-renders only when `state` changes.
	 */
	const energyRef = useRef(0)
	energyRef.current = Math.max(0, Math.min(1, energy / 100))

	useEffect(() => {
		const el = svgRef.current
		if (!el) return
		// States that do not consume amplitude: park the vars at 0 once and skip
		// the whole rAF loop rather than spinning every frame writing zeros.
		if (state !== 'listening' && state !== 'speaking') {
			el.style.setProperty('--e', '0')
			el.style.setProperty('--eb', '0')
			return
		}
		let fast = 0
		let slow = 0
		let raf = 0
		const tick = () => {
			const target = energyRef.current
			fast += (target - fast) * FAST_ALPHA
			slow += (fast - slow) * SLOW_ALPHA
			el.style.setProperty('--e', fast.toFixed(3))
			el.style.setProperty('--eb', slow.toFixed(3))
			raf = requestAnimationFrame(tick)
		}
		raf = requestAnimationFrame(tick)
		return () => cancelAnimationFrame(raf)
	}, [state])

	const accessible = label ?? SOL_STATE_LABEL[state]

	return (
		<svg
			ref={svgRef}
			className={`sol ${className}`}
			width={size}
			height={size}
			viewBox="0 0 200 200"
			data-state={state}
			data-testid="sol-avatar"
			style={{ ['--k' as string]: k }}
			role={decorative ? undefined : 'img'}
			aria-hidden={decorative ? true : undefined}
			aria-label={decorative ? undefined : accessible}
		>
			<defs>
				<radialGradient id={`${uid}-core`} cx="42%" cy="36%">
					<stop offset="0%" stopColor="#FFFDF2" />
					<stop offset="38%" stopColor="#FFF4CE" />
					<stop offset="72%" stopColor="#FFC24B" />
					<stop offset="100%" stopColor="#F5872B" />
				</radialGradient>
				<radialGradient id={`${uid}-moon`} cx="38%" cy="34%">
					<stop offset="0%" stopColor="#FBFDFF" />
					<stop offset="55%" stopColor="#E4ECFF" />
					<stop offset="100%" stopColor="#93A8DA" />
				</radialGradient>
				<radialGradient id={`${uid}-corona`}>
					<stop offset="40%" stopColor="#FFC24B" stopOpacity=".42" />
					<stop offset="70%" stopColor="#FF9A2E" stopOpacity=".14" />
					<stop offset="100%" stopColor="#FF9A2E" stopOpacity="0" />
				</radialGradient>
				{/* The crescent: a second circle bites into the disc. Parked far off
				    to the left for the sun, slid over the face for the moon. */}
				<mask id={`${uid}-cres`}>
					<circle cx="100" cy="100" r="41" fill="#fff" />
					<circle className="bite" cx="100" cy="100" r="38" fill="#000" />
				</mask>
			</defs>

			<g className="sunside">
				<circle className="corona" cx="100" cy="100" r="88" fill={`url(#${uid}-corona)`} />
				<g className="rayscale">
					<g className="rays rayA" stroke="#FFC24B" strokeWidth="5" strokeLinecap="round" opacity=".5">
						{RAYS_A.map((r, i) => (
							<line key={i} x1={r.x1} y1={r.y1} x2={r.x2} y2={r.y2} />
						))}
					</g>
					<g className="rays rayB" stroke="#FFE29A" strokeWidth="3" strokeLinecap="round" opacity=".5">
						{RAYS_B.map((r, i) => (
							<line key={i} x1={r.x1} y1={r.y1} x2={r.x2} y2={r.y2} />
						))}
					</g>
				</g>
				{/* The voice rings -- the cue that survives at icon size. */}
				<circle className="ring2" cx="100" cy="100" r="41" fill="none" />
				<circle className="ring" cx="100" cy="100" r="52" fill="none" />
				<g className="discwrap">
					<g className="disc" mask={`url(#${uid}-cres)`}>
						<circle className="sunFill" cx="100" cy="100" r="41" fill={`url(#${uid}-core)`} />
						<circle className="moonFill" cx="100" cy="100" r="41" fill={`url(#${uid}-moon)`} />
						<circle className="rim" cx="100" cy="100" r="39.9" />
					</g>
				</g>
				<g className="twinkles" fill="#FFF4CE">
					{TWINKLES.map(([x, y], i) => (
						<path
							key={i}
							className={`twinkle t${i + 1}`}
							d={`M${x} ${y - 8}q1.6 6.4 8 8-6.4 1.6-8 8-1.6-6.4-8-8 6.4-1.6 8-8z`}
						/>
					))}
				</g>
				<g className="stars" fill="#DCE6FF">
					{STARS.map(([x, y, r], i) => (
						<circle key={i} className={`star s${i + 1}`} cx={x} cy={y} r={r} />
					))}
				</g>
			</g>

			{/* OFFLINE: the cloud Sol lives in, struck through. The one graphic
			    convention that means "not available" almost everywhere. */}
			<g className="off">
				<g className="cloudbody" fill="#9AA6C4" opacity=".95">
					<ellipse cx="76" cy="104" rx="30" ry="20" />
					<ellipse cx="106" cy="93" rx="27" ry="24" />
					<ellipse cx="132" cy="106" rx="24" ry="17" />
					<rect x="48" y="102" width="106" height="22" rx="11" />
				</g>
				<line className="slashbg" x1="58" y1="140" x2="146" y2="62" />
				<line className="slash" x1="58" y1="140" x2="146" y2="62" />
			</g>
		</svg>
	)
}

/**
 * The Sol stylesheet, exported as a string so each overlay can drop it into its
 * existing inline <style> block (the established pattern in both overlay files --
 * neither imports a .css file).
 *
 * Mounting note: both overlays render this once. If both were mounted at the same
 * time the duplicate rules would be harmless (identical text), but they never are
 * -- SchemaForm picks desktop OR mobile on a breakpoint.
 */
export const SOL_CSS = `
.sol { --e: 0; --eb: 0; --k: 1; display: block; overflow: visible; flex: none; }
.sol .rays { transform-origin: 100px 100px; opacity: 0; transition: opacity .5s ease; }
.sol .rayA { animation: sol-spin 34s linear infinite; }
.sol .rayB { animation: sol-spin 52s linear infinite reverse; }
.sol .corona { transform-origin: 100px 100px; opacity: .85; transition: opacity .6s ease; }
.sol .disc { transform-origin: 100px 100px; transition: transform .5s cubic-bezier(.3,1.2,.4,1); }
.sol .sunFill, .sol .moonFill { transition: opacity .7s ease; }
.sol .moonFill { opacity: 0; }
.sol .bite { transform: translateX(-260px); transition: transform .85s cubic-bezier(.6,0,.2,1); }
.sol .twinkle { opacity: 0; transform-origin: center; transform-box: fill-box; }
.sol .star { opacity: 0; transition: opacity .6s ease; }

/* Edge treatment. The pale yellows have plenty of contrast on a dark stage and
   almost none on the near-white panel -- which is the background that actually
   ships. So every light element carries a thin warm-dark rim, sized in ABSOLUTE
   units so it stays hairline at 120px and still reads at 28px. */
.sol .rayscale { transform-origin: 100px 100px;
  filter: drop-shadow(0 0 1.6px rgba(146,72,10,.85)) drop-shadow(0 1px 1px rgba(120,60,8,.35)); }
.sol .rim { fill: none; stroke: #B8611A; stroke-width: 2.4; opacity: .5; transition: stroke .6s ease, opacity .6s ease; }
/* A warm brown edge on a cool moon looks like a mistake. */
.sol[data-state="paused"] .rim { stroke: #5E6E9C; opacity: .55; }
.sol .discwrap { filter: drop-shadow(0 2px 3px rgba(90,45,5,.30)); }
/* Deeper amber than the disc -- a pale ring on a pale card is no ring at all. */
.sol .ring { stroke: #D1731B; stroke-width: 5.5; }
.sol .ring2 { stroke: #B45E11; stroke-width: 3; }
.sol .ring, .sol .ring2 { transform-origin: 100px 100px; opacity: 0; transition: opacity .25s ease; }
.sol .off { opacity: 0; transform: scale(.86); transform-origin: 100px 100px;
  transition: opacity .45s ease, transform .5s cubic-bezier(.3,1.1,.4,1); pointer-events: none; }
.sol .off .slash { stroke: #E06A6A; stroke-width: 11; stroke-linecap: round; }
.sol .off .slashbg { stroke: #ffffff; stroke-width: 19; stroke-linecap: round; opacity: .65; }
.sol .sunside { transition: opacity .45s ease; }

/* Breathing -- always on, very slow, tiny. */
.sol .disc { animation: sol-breathe 6.5s ease-in-out infinite; }
@keyframes sol-breathe { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.028); } }
@keyframes sol-spin { to { transform: rotate(360deg); } }
@keyframes sol-twink { 0%, 100% { opacity: 0; transform: scale(.4); } 45% { opacity: .95; transform: scale(1); } }
@keyframes sol-drift { 0% { opacity: 0; transform: translate(0,6px) scale(.6); }
  30% { opacity: .9; } 100% { opacity: 0; transform: translate(6px,-22px) scale(1); } }

/* IDLE -- warm, awake, committing to nothing. */
.sol[data-state="idle"] .rays { opacity: .5; }
.sol[data-state="idle"] .rayA { animation-duration: 70s; }
.sol[data-state="idle"] .rayB { animation-duration: 95s; }

/* LISTENING -- the rays stop dead, then breathe in length with your voice.
   It listens with its rays. The disc holds perfectly still. */
.sol[data-state="listening"] .rays { opacity: calc(.72 + var(--eb) * .28); }
.sol[data-state="listening"] .rayA, .sol[data-state="listening"] .rayB { animation-play-state: paused; }
.sol[data-state="listening"] .rayscale { transform: scale(calc(1 + var(--e) * .22 * var(--k))); }
.sol[data-state="listening"] .corona { opacity: 1; transform: scale(calc(1 + var(--e) * .07)); }

/* THINKING -- slow rotation plus sparkles. Sixteen seconds a revolution, not one. */
.sol[data-state="thinking"] .rays { opacity: 1; }
.sol[data-state="thinking"] .rayA { animation-duration: 16s; }
.sol[data-state="thinking"] .rayB { animation-duration: 24s; }
.sol[data-state="thinking"] .twinkle { animation: sol-twink 2.1s ease-in-out infinite; }
.sol[data-state="thinking"] .t2 { animation-delay: .5s; }
.sol[data-state="thinking"] .t3 { animation-delay: 1.05s; }
.sol[data-state="thinking"] .t4 { animation-delay: 1.5s; }
.sol[data-state="thinking"] .t5 { animation-delay: .8s; }

/* SPEAKING -- the halo carries the voice; the orb only nods along (~6%). */
.sol[data-state="speaking"] .rays { opacity: .95; }
.sol[data-state="speaking"] .rayA { animation-duration: 26s; }
.sol[data-state="speaking"] .rayB { animation-duration: 38s; }
/* The orb only nods along, and deliberately does NOT take the --k boost: --k
   exists so the RAYS and RINGS stay visible when the avatar shrinks, but disc
   scale and brightness are the two capped quantities (~6% / ~7%), and the cap
   is a safety property on a large bright shape -- multiplying it by 2.4 on the
   FAB would put a bright orb at a 13% throb. The halo carries the amplitude
   instead; it costs no luminance. */
.sol[data-state="speaking"] .disc { animation: none;
  transform: scale(calc(1 + var(--e) * .055));
  filter: brightness(calc(1 + var(--eb) * .07)); }
.sol[data-state="speaking"] .corona { opacity: calc(.45 + var(--eb) * .35);
  transform: scale(calc(1 + var(--e) * .16 * var(--k))); }
.sol[data-state="speaking"] .ring { opacity: calc(.30 + var(--eb) * 1.7);
  filter: drop-shadow(0 0 1.4px rgba(140,72,12,.62));
  transform: scale(calc(1 + var(--e) * .23 * var(--k))); }
.sol[data-state="speaking"] .ring2 { opacity: calc(.12 + var(--eb) * .95);
  transform: scale(calc(1 + var(--e) * .26 * var(--k))); }

/* PAUSED -- crescent moon and drifting stars. Sleep with no letters in it. */
.sol[data-state="paused"] .rays { opacity: 0; }
.sol[data-state="paused"] .corona { opacity: .28; }
.sol[data-state="paused"] .sunFill { opacity: 0; }
.sol[data-state="paused"] .moonFill { opacity: 1; }
.sol[data-state="paused"] .bite { transform: translate(-23px,-5px); }
.sol[data-state="paused"] .disc { animation: sol-breathe 9.5s ease-in-out infinite; }
.sol[data-state="paused"] .star { opacity: 1; animation: sol-drift 4.4s ease-out infinite; }
.sol[data-state="paused"] .s2 { animation-delay: 1.4s; }
.sol[data-state="paused"] .s3 { animation-delay: 2.9s; }

/* OFFLINE -- Sol is gone, not dimmed. */
.sol[data-state="offline"] .sunside { opacity: 0; }
.sol[data-state="offline"] .off { opacity: 1; transform: scale(1); }
.sol[data-state="offline"] .off .cloudbody { animation: sol-sag 5s ease-in-out infinite; }
@keyframes sol-sag { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(3px); } }

/* Accessibility: kill all motion, keep every state legible.

   Shape and colour carry the meaning; motion only garnishes it. But three
   states lean on motion ALONE to tell themselves apart, so each needs a static
   substitute or the avatar collapses to "a sun" for half the state machine:

     listening  rays still + long        -> pinned FULLY EXTENDED (scale 1.18)
     thinking   rays rotating + twinkles -> twinkles pinned VISIBLE (static
                                            sparkles, the state's own motif)
     speaking   halo swelling            -> halo pinned to a steady ring

   With those three pinned, all six read apart with the clock stopped:
   idle = short rays; listening = long rays, no sparkles; thinking = sparkles;
   speaking = halo ring; paused = moon; offline = cloud. */
@media (prefers-reduced-motion: reduce) {
  .sol * { animation: none !important; }
  .sol .disc { transform: none !important; filter: none !important; }
  .sol .ring, .sol .ring2 { transform: none !important; }
  /* Listening: the rays cannot breathe, so hold them at full extension --
     visibly longer than idle's resting length. */
  .sol .rayscale { transform: none !important; }
  .sol[data-state="listening"] .rayscale { transform: scale(1.18) !important; }
  .sol[data-state="listening"] .rays { opacity: 1; }
  /* Thinking: the sparkles ARE the state's motif; show them steadily. */
  .sol[data-state="thinking"] .twinkle { opacity: .9; transform: none !important; }
  /* Speaking: pin the halo to a steady visible ring rather than an
     amplitude-driven one -- otherwise the cue vanishes completely. */
  .sol[data-state="speaking"] .ring { opacity: .55; }
  .sol[data-state="speaking"] .ring2 { opacity: .35; }
}
`
