var VoiceFormFiller=function(){"use strict";var ye=Object.defineProperty;var ve=(x,k,V)=>k in x?ye(x,k,{enumerable:!0,configurable:!0,writable:!0,value:V}):x[k]=V;var E=(x,k,V)=>ve(x,typeof k!="symbol"?k+"":k,V);/*! Voice Form Filler Bookmarklet v0.1.0 | 2025-10-10T05:12:12.394Z */class x{static init(e){const t=this.load();if(t&&t.schema.form_metadata.url===e.form_metadata.url&&Date.now()-t.last_updated<36e5)return console.log("[WebFormState] Resuming existing session",{url:e.form_metadata.url,fieldsWithValues:Object.keys(t.current_values).length}),t;const n={schema:e,current_values:{},last_updated:Date.now()};return this.save(n),console.log("[WebFormState] Created new session",{url:e.form_metadata.url,fields:e.fields.length}),n}static load(){try{const e=sessionStorage.getItem(this.STORAGE_KEY);return e?JSON.parse(e):null}catch(e){return console.error("[WebFormState] Failed to load state",e),null}}static save(e){try{e.last_updated=Date.now(),sessionStorage.setItem(this.STORAGE_KEY,JSON.stringify(e))}catch(t){console.error("[WebFormState] Failed to save state",t)}}static updateField(e,t,n,r){const i=e.current_values[t]||{},l=r?.confirmed!==void 0?r.confirmed:typeof i.confirmed=="boolean"?i.confirmed:!1,a={...e,current_values:{...e.current_values,[t]:{...i,value:n,confirmed:l,lastModified:Date.now()}}};return this.save(a),a}static markConfirmed(e,t){const n={...e,current_values:{...e.current_values}};for(const r of t)n.current_values[r]&&(n.current_values[r]={...n.current_values[r],confirmed:!0});return this.save(n),n}static getHandshakePayload(e){return{type:"handshake",schema:e.schema,current_values:e.current_values}}static setSessionId(e,t){const n={...e,session_id:t};return this.save(n),n}static clear(){sessionStorage.removeItem(this.STORAGE_KEY),console.log("[WebFormState] Cleared state")}static getUnconfirmedFields(e){return e.schema.fields.filter(t=>{const n=e.current_values[t.id];return!n||!n.confirmed}).map(t=>t.id)}static getCompletionPercentage(e){const t=e.schema.fields.length;if(t===0)return 100;const n=e.schema.fields.filter(r=>{const i=e.current_values[r.id];return i&&i.value!==null&&i.value!==""}).length;return Math.round(n/t*100)}static debug(e){console.group("[WebFormState] Debug Info"),console.log("Schema:",e.schema.form_metadata),console.log("Session ID:",e.session_id),console.log("Fields:",e.schema.fields.length),console.log("Filled:",Object.keys(e.current_values).length),console.log("Completion:",`${this.getCompletionPercentage(e)}%`),console.log("Current Values:",e.current_values),console.groupEnd()}}E(x,"STORAGE_KEY","web_form_state");function k(o,e){const{requiredOnly:t=!1,skipConfirmed:n=!0}=e||{};if(!o.schema||!o.schema.fields||o.schema.fields.length===0)return null;console.log("[Navigation] Computing next field:",{totalFields:o.schema.fields.length,requiredOnly:t,skipConfirmed:n,currentValues:Object.keys(o.current_values).length});for(const r of o.schema.fields){if(t&&!r.required)continue;const i=o.current_values[r.id],l=i?.confirmed===!0;if(console.log(`[Navigation] Checking field "${r.id}":`,{hasCurrentValue:!!i,value:i?.value,isConfirmed:l,skipConfirmed:n}),n&&l){console.log(`[Navigation] Skipping "${r.id}" - already confirmed`);continue}const a=i?.value!==null&&i?.value!==void 0&&i?.value!=="";if(!l||!a)return console.log(`[Navigation] Selected next field: "${r.id}" (${r.name})`),r}return console.log("[Navigation] No next field - all fields confirmed/filled"),null}function V(o){if(!o.schema||!o.schema.fields||o.schema.fields.length===0)return!0;if(o.schema.fields.some(t=>t.required)){for(const t of o.schema.fields)if(t.required&&!(o.current_values[t.id]?.confirmed===!0))return!1;return!0}else{for(const t of o.schema.fields)if(!(o.current_values[t.id]?.confirmed===!0))return!1;return!0}}function j(o,e){const t=e?`#${e}`:"",n=o.required?", required":"",r=o.options&&o.options.length>0?`, options: [${o.options.join(", ")}]`:"";return`Next field to fill is ${t}: '${o.name}' (type: ${o.type}${n}${r})`}function K(o,e){if(!o.schema||!o.schema.fields)return null;const t=o.schema.fields.findIndex(n=>n.id===e);return t>=0?t+1:null}class H{constructor(e,t={}){E(this,"ws",null);E(this,"state");E(this,"callbacks");E(this,"status","disconnected");E(this,"reconnectAttempts",0);E(this,"maxReconnectAttempts",5);E(this,"reconnectDelay",1e3);E(this,"reconnectTimer",null);E(this,"audioQueue",[]);E(this,"isProcessingAudio",!1);E(this,"warmConnection",null);E(this,"warmupState","idle");E(this,"warmupSessionId",null);this.state=x.init(e),this.callbacks=t}async warmup(e="ws://localhost:8000/ws/fill"){if(this.warmupState==="ready"){console.log("[Warmup] Already ready, skipping");return}return this.warmupState==="warming"?(console.log("[Warmup] Already warming, waiting for ready..."),new Promise((t,n)=>{const r=()=>{this.warmupState==="ready"?t():this.warmupState==="failed"?n(new Error("Warmup failed")):setTimeout(r,100)};r()})):(this.warmupState="warming",console.log("🔥 [Warmup] Pre-warming Gemini connection..."),new Promise((t,n)=>{try{this.warmConnection=new WebSocket(e),this.warmConnection.onopen=()=>{console.log("[Warmup] WebSocket opened, sending minimal handshake");const r={type:"warmup",timestamp:Date.now()};this.warmConnection.send(JSON.stringify(r))},this.warmConnection.onmessage=r=>{if(typeof r.data=="string")try{const i=JSON.parse(r.data);i.type==="warmup_ready"&&(this.warmupSessionId=i.session_id,this.warmupState="ready",console.log("✅ [Warmup] Gemini connection pre-warmed!",i.session_id),this.callbacks.onWarmupReady&&this.callbacks.onWarmupReady(),t())}catch(i){console.error("[Warmup] Failed to parse message",i)}},this.warmConnection.onerror=r=>{console.error("[Warmup] Connection error",r),this.warmupState="failed",n(r)},this.warmConnection.onclose=()=>{this.warmupState==="warming"&&(console.warn("[Warmup] Connection closed before ready"),this.warmupState="failed",n(new Error("Warmup connection closed")))}}catch(r){console.error("[Warmup] Failed to start",r),this.warmupState="failed",n(r)}}))}getWarmupStatus(){return this.warmupState}async connect(e="ws://localhost:8000/ws/fill"){if(!(this.ws&&this.ws.readyState===WebSocket.OPEN))return this.warmupState==="ready"&&this.warmConnection?(console.log("⚡ [Connect] Using pre-warmed connection!"),this.upgradeWarmConnection()):(console.log("[Connect] Warmup not ready, connecting normally..."),this.connectNormally(e))}async upgradeWarmConnection(){if(console.log("[Upgrade] Upgrading warm connection with form schema..."),this.setStatus("connecting"),this.ws=this.warmConnection,this.warmConnection=null,!this.ws)throw new Error("Warm connection is null");const e={type:"upgrade_session",session_id:this.warmupSessionId,schema:this.state.schema,current_values:this.state.current_values};console.log("🚀 [Upgrade] Sending upgrade with schema:",{type:e.type,session_id:e.session_id,fieldCount:e.schema?.fields?.length||0,sampleFields:e.schema?.fields?.slice(0,3).map(t=>({id:t.id,name:t.name,type:t.type,filled:t.filled}))||[],allFieldIds:e.schema?.fields?.map(t=>t.id)||[]}),this.ws.send(JSON.stringify(e)),console.log("[Upgrade] Upgrade message sent, waiting for session_ready..."),this.ws.onmessage=t=>this.handleMessage(t),this.ws.onerror=t=>this.handleError(t),this.ws.onclose=()=>this.handleClose()}async connectNormally(e){this.setStatus("connecting");try{this.ws=new WebSocket(e),this.ws.onopen=()=>this.handleOpen(),this.ws.onmessage=t=>this.handleMessage(t),this.ws.onerror=t=>this.handleError(t),this.ws.onclose=()=>this.handleClose()}catch(t){this.handleError(t)}}disconnect(){this.reconnectTimer&&(clearTimeout(this.reconnectTimer),this.reconnectTimer=null),this.ws&&(this.ws.close(),this.ws=null),this.setStatus("disconnected")}handleOpen(){this.reconnectAttempts=0,this.reconnectDelay=1e3;const e=x.getHandshakePayload(this.state);this.send(e)}async handleMessage(e){if(e.data instanceof ArrayBuffer||e.data instanceof Blob){await this.handleAudioFrame(e.data);return}try{const t=JSON.parse(e.data);switch(console.log("[WebFormConnection] 📨 Received message:",t.type,t),t.type){case"session_ready":this.handleSessionReady(t);break;case"field_update":console.log("[WebFormConnection] 🔧 TOOL CALL - Field update received:",t.updates),this.handleFieldUpdate(t);break;case"form_updated":console.log("[WebFormConnection] 📝 Form updated from backend:",{applied:t.data?.applied_fields,formState:t.data?.form_state,hasApplied:(t.data?.applied_fields?.length||0)>0}),this.handleFormUpdated(t);break;case"form_state_ack":break;case"hint_ack":break;case"get_form_state":this.handleGetFormStateRequest(t);break;case"error":this.handleServerError(t);break;case"ai_response":break;default:console.warn("[WebFormConnection] ⚠️ Unknown message type:",t.type,t);break}}catch(t){console.error("[WebFormConnection] Failed to parse message",t)}}handleSessionReady(e){const{session_id:t,ephemeral:n}=e;this.state=x.setSessionId(this.state,t),this.setStatus("connected"),this.callbacks.onSessionReady&&this.callbacks.onSessionReady(t)}handleFieldUpdate(e){const{updates:t}=e;if(console.log("[WebFormConnection] 🔧 Field update details:",{rawUpdates:t,updateKeys:Object.keys(t||{}),schemaFieldIds:this.state.schema.fields.map(r=>r.id),schemaFieldNames:this.state.schema.fields.map(r=>r.name)}),!t||typeof t!="object"){console.error("[WebFormConnection] Invalid updates format");return}const n=[];for(const[r,i]of Object.entries(t)){const l=this.state.schema.fields.find(a=>a.name===r||a.id===r);l?(console.log(`[WebFormConnection] ✅ Matched field: "${r}" → ${l.id} = ${i}`),this.updateField(l.id,i,{confirmed:!0,emit:!1}),n.push({fieldId:l.id,value:i})):console.warn(`[WebFormConnection] ❌ Unknown field in update: "${r}" (not found in schema)`)}this.callbacks.onFieldUpdate&&n.length>0&&this.callbacks.onFieldUpdate(n)}handleFormUpdated(e){const t=e&&e.data||{},n=t.form_state||{},r=t.applied_fields||[];if(console.log("[WebFormConnection] 🔍 handleFormUpdated details:",{hasFormState:Object.keys(n).length>0,formStateKeys:Object.keys(n),appliedFields:r,appliedCount:r.length,rawData:t}),!n||typeof n!="object"){console.warn("[WebFormConnection] form_updated missing form_state payload");return}const i=new Set(r.map(c=>String(c))),l=i.size>0,a=[];for(const c of this.state.schema.fields){const d=n[c.id]??n[c.name??""];if(d===void 0)continue;const u=i.has(c.id)||(c.name?i.has(c.name):!1);if(l&&!u)continue;const p=this.state.current_values[c.id]?.value;(u||!Object.is(p,d))&&(console.log(`[WebFormConnection] ✅ Applying update: ${c.id} = ${d}`),this.updateField(c.id,d,{confirmed:u,emit:!1}),a.push({fieldId:c.id,value:d}))}a.length&&(this.callbacks.onFieldUpdate&&this.callbacks.onFieldUpdate(a),this.sendNextFieldHint())}handleGetFormStateRequest(e){const t=e.request_id,n=e.field_ids||[],r={};if(n.length===0)for(const[i,l]of Object.entries(this.state.current_values))r[i]={value:l.value,confirmed:l.confirmed};else for(const i of n){const l=this.state.current_values[i];l?r[i]={value:l.value,confirmed:l.confirmed}:r[i]={value:null,confirmed:!1}}console.log("[WebFormConnection] Sending form_state_response",{requestId:t,fieldCount:Object.keys(r).length}),this.send({type:"form_state_response",request_id:t,field_values:r})}sendNextFieldHint(){if(V(this.state)){console.log("[WebFormConnection] Form is complete - sending completion message"),this.sendCompletionMessage();return}const e=k(this.state,{skipConfirmed:!0});if(!e)return;const t=K(this.state,e.id),n=j(e,t||void 0);console.log("[WebFormConnection] Sending next field hint:",{fieldId:e.id,fieldName:e.name,order:t,hint:n}),this.send({type:"next_field_hint",hint:n})}sendCompletionMessage(){const e="Say the following: 'The form is complete. if all fields are correct, please press submit.'";console.log("[WebFormConnection] Sending completion message to AI"),this.send({type:"completion_message",message:e})}async handleAudioFrame(e){const t=e instanceof Blob?await e.arrayBuffer():e;this.audioQueue.push(t),this.isProcessingAudio||this.processAudioQueue()}async processAudioQueue(){for(this.isProcessingAudio=!0;this.audioQueue.length>0;){const e=this.audioQueue.shift();this.callbacks.onAudioData?this.callbacks.onAudioData(e):console.warn("[WebFormConnection] ⚠️ onAudioData callback not registered!")}this.isProcessingAudio=!1}handleServerError(e){const t=new Error(e.message||"Server error");console.error("[WebFormConnection] Server error:",e),this.callbacks.onError&&this.callbacks.onError(t)}handleError(e){console.error("[WebFormConnection] WebSocket error",e),this.setStatus("error"),this.callbacks.onError&&e instanceof Error&&this.callbacks.onError(e)}handleClose(){this.status!=="disconnected"&&this.reconnectAttempts<this.maxReconnectAttempts?this.attemptReconnect():this.setStatus("disconnected")}attemptReconnect(){this.reconnectAttempts++,this.setStatus("reconnecting");const e=Math.min(this.reconnectDelay*Math.pow(2,this.reconnectAttempts-1),3e4);this.reconnectTimer=window.setTimeout(()=>{this.connect()},e)}send(e){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.error("[WebFormConnection] Cannot send - WebSocket not open");return}e instanceof ArrayBuffer?this.ws.send(e):this.ws.send(JSON.stringify(e))}sendAudio(e){this.send(e)}sendManualFieldUpdate(e,t,n){!this.ws||this.ws.readyState!==WebSocket.OPEN||this.send({type:"manual_field_update",field_id:e,field_name:t,value:n})}updateField(e,t,n){const r=n?.confirmed,i=n?.emit??!1;this.state=x.updateField(this.state,e,t,{confirmed:r}),i&&this.flushField(e)}flushField(e){if(!this.ws||this.ws.readyState!==WebSocket.OPEN)return;const t=this.state.current_values[e];t&&(this.send({type:"form_state",fields:[{field_id:e,value:t.value,confirmed:!!t.confirmed}]}),t.confirmed&&this.sendNextFieldHint())}setStatus(e){this.status!==e&&(this.status=e,this.callbacks.onStatusChange&&this.callbacks.onStatusChange(e))}getStatus(){return this.status}getState(){return this.state}getCompletionPercentage(){return x.getCompletionPercentage(this.state)}reset(){this.disconnect(),x.clear()}}function Y(o={}){const e=new Set,t=new Map;function n(c){console.log("[VFF FieldManager] Applying",c.length,"updates");for(const d of c){const u=document.getElementById(d.fieldId);if(!u){console.warn("[VFF FieldManager] Field not found:",d.fieldId);continue}const p=d.value||"";if(u.tagName==="SELECT"){const m=u;let v=!1;for(let g=0;g<m.options.length;g++){const h=m.options[g];if(h.value===p||h.text===p){m.selectedIndex=g,v=!0,console.log("[VFF FieldManager] ✓ Exact match for select:",d.fieldId,"→",h.text);break}}if(!v){const g=p.toLowerCase();for(let h=0;h<m.options.length;h++){const s=m.options[h],f=s.text.toLowerCase(),F=s.value.toLowerCase();if(f.includes(g)||g.includes(f)||F.includes(g)||g.includes(F)){m.selectedIndex=h,v=!0,console.log("[VFF FieldManager] ≈ Fuzzy match for select:",d.fieldId,"→",s.text);break}}}v||console.warn("[VFF FieldManager] ⚠️ No matching option found for:",p,"in",d.fieldId),m.dispatchEvent(new Event("change",{bubbles:!0})),m.dispatchEvent(new Event("input",{bubbles:!0}))}else(u.tagName==="INPUT"||u.tagName==="TEXTAREA")&&(u.value=p,u.dispatchEvent(new Event("input",{bubbles:!0})),u.dispatchEvent(new Event("change",{bubbles:!0})));u.setAttribute("data-vff-confirmed","true"),e.add(d.fieldId),r(u),l(u,d.fieldId),console.log("[VFF FieldManager] Updated field:",d.fieldId,"→",p.substring(0,50))}}function r(c){if(c.style.outline="2px solid #10b981",c.style.outlineOffset="2px",c.parentElement?.querySelector(".vff-field-badge"))return;const u=document.createElement("span");u.className="vff-field-badge",u.textContent="✓",u.style.cssText=`
			position: absolute;
			top: 50%;
			right: 8px;
			transform: translateY(-50%);
			color: #10b981;
			font-weight: bold;
			font-size: 18px;
			pointer-events: none;
			z-index: 1000;
		`;const p=c.parentElement;p&&getComputedStyle(p).position==="static"&&(p.style.position="relative"),c.parentElement?.appendChild(u)}function i(c,d){c.style.outline="",c.style.outlineOffset="";const u=c.parentElement?.querySelector(".vff-field-badge");u&&u.remove(),c.removeAttribute("data-vff-confirmed"),e.delete(d),console.log("[VFF FieldManager] Cleared AI confirmation for:",d)}function l(c,d){if(t.has(c))return;const u=()=>{if(e.has(d)&&(i(c,d),o.onManualEdit)){const p=c.value;o.onManualEdit(d,p)}};c.addEventListener("input",u),c.addEventListener("change",u),t.set(c,u)}function a(){console.log("[VFF FieldManager] Destroying, cleaning up",t.size,"listeners");for(const[c,d]of t.entries())c.removeEventListener("input",d),c.removeEventListener("change",d);document.querySelectorAll("[data-vff-confirmed]").forEach(c=>{c.removeAttribute("data-vff-confirmed"),c.style.outline="",c.style.outlineOffset=""}),document.querySelectorAll(".vff-field-badge").forEach(c=>{c.remove()}),t.clear(),e.clear()}return{applyUpdates:n,destroy:a}}const $=16e3,M=24e3;function G(){const o={recordingContext:null,playbackContext:null,stream:null,processor:null,source:null};let e=!1,t=0,n=null;async function r(p){if(e){console.warn("[VFF Audio] Already recording");return}try{console.log("[VFF Audio] Requesting microphone access..."),o.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,sampleRate:$,echoCancellation:!0,noiseSuppression:!0}}),console.log("[VFF Audio] Microphone access granted"),o.recordingContext=new AudioContext({sampleRate:$}),o.source=o.recordingContext.createMediaStreamSource(o.stream);const m=4096;o.processor=o.recordingContext.createScriptProcessor(m,1,1),n=p,o.processor.onaudioprocess=v=>{if(!e||!n)return;const g=v.inputBuffer.getChannelData(0),h=new Int16Array(g.length);for(let s=0;s<g.length;s++){const f=Math.max(-1,Math.min(1,g[s]));h[s]=f<0?f*32768:f*32767}n(h.buffer)},o.source.connect(o.processor),o.processor.connect(o.recordingContext.destination),e=!0,console.log("[VFF Audio] Recording started (PCM 16kHz)")}catch(m){throw console.error("[VFF Audio] Failed to start recording:",m),d(),m}}function i(){if(!e){console.warn("[VFF Audio] Not recording");return}if(console.log("[VFF Audio] Stopping recording..."),e=!1,n=null,o.processor){try{o.processor.disconnect()}catch{}o.processor=null}if(o.source){try{o.source.disconnect()}catch{}o.source=null}if(o.recordingContext){try{o.recordingContext.close()}catch{}o.recordingContext=null}o.stream&&(o.stream.getTracks().forEach(p=>p.stop()),o.stream=null),console.log("[VFF Audio] Recording stopped")}async function l(p){try{o.playbackContext||(o.playbackContext=new AudioContext({sampleRate:M}),t=0);const m=o.playbackContext;m.state==="suspended"&&await m.resume();const v=a(p),g=new Int16Array(v);if(g.length===0){console.warn("[VFF Audio] Empty audio buffer, skipping");return}const h=new Float32Array(g.length);for(let y=0;y<g.length;y++)h[y]=g[y]/32768;const s=m.createBuffer(1,h.length,M);s.getChannelData(0).set(h);const f=m.currentTime+.01,F=Math.max(t,f),b=m.createBufferSource();b.buffer=s,b.connect(m.destination),b.start(F),t=F+s.duration,b.onended=()=>{t<m.currentTime&&(t=m.currentTime)}}catch(m){console.error("[VFF Audio] Playback failed:",m)}}function a(p){try{const m=new TextDecoder().decode(p);if(m.match(/^[A-Za-z0-9+/]+=*$/)){const v=atob(m),g=new Uint8Array(v.length);for(let h=0;h<v.length;h++)g[h]=v.charCodeAt(h);return g.buffer}}catch{}return p}function c(){return e}function d(){if(i(),o.playbackContext){try{o.playbackContext.close()}catch{}o.playbackContext=null}t=0}function u(){console.log("[VFF Audio] Destroying audio manager"),d()}return{startRecording:r,stopRecording:i,playAudio:l,isRecording:c,destroy:u}}function J(o,e){const t=X();let n=null,r=null,i=null;i=G(),console.log("[VFF Connection] Audio manager created");const l={onStatusChange:a=>{console.log("[VFF Connection] Status:",a),e(a)},onSessionReady:a=>{console.log("[VFF Connection] Session ready:",a),e("connected"),r||(r=Y({onManualEdit:(c,d)=>{console.log("[VFF Connection] Manual edit detected:",c,"→",d.substring(0,50))}}))},onFieldUpdate:a=>{console.log("[VFF Connection] Field updates:",a),r?r.applyUpdates(a):console.warn("[VFF Connection] No field manager available yet")},onAudioData:async a=>{i?await i.playAudio(a):console.warn("[VFF Connection] No audio manager available yet")},onError:a=>{console.error("[VFF Connection] Error:",a),e("error")},onWarmupReady:()=>{console.log("[VFF Connection] Warmup ready"),e("ready")}};return{async connect(){if(n&&n.getStatus()==="connected"){console.log("[VFF Connection] Already connected");return}try{console.log("[VFF Connection] Starting connection to:",t),e("connecting");const a={source:"web",form_metadata:{title:o.formMetadata.title||document.title,url:o.formMetadata.url||window.location.href},fields:o.fields.map(c=>({id:c.fieldId,name:c.name,type:c.type,required:c.required,options:c.options,value:c.placeholder,meta:c.constraints}))};console.log("[VFF Connection] FormSchema:",a),console.log("[VFF Connection] Creating WebFormConnection..."),n=new H(a,l),console.log("[VFF Connection] Starting warmup to:",t),await n.warmup(t),console.log("[VFF Connection] Warmup complete, upgrading to full connection..."),await n.connect(t),console.log("[VFF Connection] Connection established!")}catch(a){throw console.error("[VFF Connection] Connection failed:",a),console.error("[VFF Connection] Error details:",{message:a instanceof Error?a.message:String(a),stack:a instanceof Error?a.stack:void 0,wsUrl:t}),e("error"),a}},disconnect(){n&&(n.disconnect(),n=null),r&&(r.destroy(),r=null),i&&(i.destroy(),i=null),e("disconnected")},getStatus(){return n?.getStatus()??"disconnected"},sendAudio(a){n&&n.sendAudio(a)},getFieldManager(){return r},getAudioManager(){return i},async startRecording(){if(!i){console.error("[VFF Connection] Audio manager not initialized");return}console.log("[VFF Connection] Starting audio recording..."),await i.startRecording(a=>{n&&n.getStatus()==="connected"&&n.sendAudio(a)}),console.log("[VFF Connection] Audio recording started")},stopRecording(){i&&(i.stopRecording(),console.log("[VFF Connection] Audio recording stopped"))},isRecording(){return i?.isRecording()??!1}}}function X(){return"wss://voice-form-filler-4qyc6wagea-uc.a.run.app/ws/fill"}let L=null;function Q(){return L}function Z(o,e,t){const n=o.attachShadow({mode:"open"}),r=document.createElement("div");r.className="vff-panel";const i=document.createElement("style");i.textContent=ee(),n.appendChild(i),r.innerHTML=`
		<div class="vff-panel-header">
			<span class="vff-title">🎤 Voice Form Filler</span>
			<button class="vff-close" aria-label="Close">×</button>
		</div>
		<div class="vff-panel-body">
			<div class="vff-status">
				<span class="vff-status-icon">✅</span>
				<span class="vff-status-text">Found ${t.stats.fieldCount} fields</span>
			</div>
			<div class="vff-controls">
				<button class="vff-button vff-connect">Connect to Voice</button>
				<button class="vff-button vff-rescan">Rescan Form</button>
				<button class="vff-button vff-clear-form">🗑️ Clear Form</button>
			</div>
			<div class="vff-error" style="display: none;"></div>
			<div class="vff-info">
				<small>
					Fields: ${t.stats.fieldCount} 
					(${t.stats.requiredCount} required)<br>
					Parse time: ${t.stats.parseTime.toFixed(0)}ms
				</small>
			</div>
		</div>
	`,n.appendChild(r),te(r),t.schema&&(L=J(t.schema,l=>{T(n,l)})),oe(n,e,t,L)}function ee(){return`
		.vff-panel {
			position: fixed;
			top: 20px;
			right: 20px;
			width: 320px;
			background: white;
			border-radius: 12px;
			box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
			pointer-events: auto;
			user-select: none;
			z-index: 10000;
		}

		.vff-panel-header {
			display: flex;
			justify-content: space-between;
			align-items: center;
			padding: 16px;
			border-bottom: 1px solid #e0e0e0;
			cursor: move;
			background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
			color: white;
			border-radius: 12px 12px 0 0;
		}

		.vff-title {
			font-weight: 600;
			font-size: 16px;
		}

		.vff-close {
			background: none;
			border: none;
			color: white;
			font-size: 24px;
			cursor: pointer;
			padding: 0;
			width: 24px;
			height: 24px;
			line-height: 1;
			opacity: 0.8;
			transition: opacity 0.2s;
		}

		.vff-close:hover {
			opacity: 1;
		}

		.vff-panel-body {
			padding: 16px;
		}

		.vff-status {
			display: flex;
			align-items: center;
			gap: 8px;
			margin-bottom: 16px;
			padding: 12px;
			background: #f5f5f5;
			border-radius: 8px;
		}

		.vff-status-icon {
			font-size: 20px;
		}

		.vff-status-text {
			font-size: 14px;
			font-weight: 500;
		}

		.vff-controls {
			display: flex;
			flex-direction: column;
			gap: 8px;
		}

		.vff-button {
			padding: 10px 16px;
			border: none;
			border-radius: 6px;
			font-size: 14px;
			font-weight: 500;
			cursor: pointer;
			transition: all 0.2s;
			background: #667eea;
			color: white;
		}

		.vff-button:hover:not(:disabled) {
			background: #5568d3;
			transform: translateY(-1px);
		}

		.vff-button:disabled {
			opacity: 0.5;
			cursor: not-allowed;
			transform: none;
		}

		.vff-button.vff-recording {
			background: #dc2626;
			animation: pulse 2s ease-in-out infinite;
		}

		.vff-button.vff-recording:hover:not(:disabled) {
			background: #b91c1c;
		}
		
		.vff-button.vff-clear-form {
			background: #dc2626;
		}
		
		.vff-button.vff-clear-form:hover:not(:disabled) {
			background: #b91c1c;
		}

		@keyframes pulse {
			0%, 100% {
				opacity: 1;
			}
			50% {
				opacity: 0.8;
			}
		}

		.vff-error {
			margin-top: 12px;
			padding: 12px;
			background: #ffebee;
			color: #c62828;
			border-radius: 6px;
			font-size: 13px;
			line-height: 1.4;
		}

		.vff-info {
			margin-top: 12px;
			text-align: center;
			color: #666;
			font-size: 12px;
		}

		/* Field confirmation styles (injected into page DOM) */
	`}function te(o){const e=o.querySelector(".vff-panel-header");let t=!1,n=0,r=0,i=0,l=0;e.addEventListener("mousedown",a=>{t=!0,i=a.clientX-n,l=a.clientY-r,o.style.cursor="grabbing"}),document.addEventListener("mousemove",a=>{t&&(a.preventDefault(),n=a.clientX-i,r=a.clientY-l,o.style.transform=`translate(${n}px, ${r}px)`)}),document.addEventListener("mouseup",()=>{t=!1,o.style.cursor="default"})}function oe(o,e,t,n){o.querySelector(".vff-close").addEventListener("click",()=>{n&&n.disconnect(),window.VoiceFormFiller?.destroy()});const i=o.querySelector(".vff-connect");console.log("[VoiceFormFiller] Setting up connect button, manager exists:",!!n);let l=!1;i.addEventListener("click",async()=>{if(console.log("[VoiceFormFiller] Connect button clicked! Active:",l),!n){console.error("[VoiceFormFiller] No connection manager available"),R(o,"No connection manager - please refresh page");return}if(l){console.log("[VoiceFormFiller] Stopping recording..."),n.stopRecording(),i.textContent="🎤 Connect to Voice",i.classList.remove("vff-recording"),T(o,"connected"),l=!1,console.log("[VoiceFormFiller] Recording stopped");return}try{console.log("[VoiceFormFiller] Disabling button and starting connection..."),i.disabled=!0,i.textContent="Connecting...",console.log("[VoiceFormFiller] Step 1: Connecting WebSocket..."),await n.connect(),console.log("[VoiceFormFiller] WebSocket connected!"),console.log("[VoiceFormFiller] Step 2: Starting microphone..."),i.textContent="Starting microphone...",await n.startRecording(),console.log("[VoiceFormFiller] Microphone active!"),i.disabled=!1,i.textContent="⏹ Stop Recording",i.classList.add("vff-recording"),T(o,"recording"),l=!0,console.log("[VoiceFormFiller] Voice connection fully active!")}catch(d){console.error("[VoiceFormFiller] Connection/Recording failed:",d);let u="Connection failed. ";d instanceof Error&&(d.message.includes("Permission denied")||d.message.includes("NotAllowedError")?u="Microphone permission denied. Please allow microphone access and try again.":d.message.includes("NotFoundError")?u="No microphone found. Please connect a microphone and try again.":u=d.message),R(o,u),i.disabled=!1,i.textContent="🎤 Connect to Voice (Retry)",i.classList.remove("vff-recording"),l=!1}}),o.querySelector(".vff-rescan").addEventListener("click",()=>{console.log("[VoiceFormFiller] Rescan clicked - reloading page to rescan"),window.location.reload()}),o.querySelector(".vff-clear-form").addEventListener("click",()=>{if(console.log("[VoiceFormFiller] Clear Form clicked"),!confirm("Clear all form fields and saved data? This cannot be undone."))return;x.clear(),console.log("[VoiceFormFiller] ✅ Cleared sessionStorage");const u=document.querySelectorAll("input, textarea, select");let p=0;u.forEach(v=>{const g=v;if(g.tagName==="INPUT"){const h=g;h.type==="checkbox"||h.type==="radio"?h.checked=!1:h.type!=="submit"&&h.type!=="button"&&(h.value=""),p++}else g.tagName==="TEXTAREA"?(g.value="",p++):g.tagName==="SELECT"&&(g.selectedIndex=0,p++);g.removeAttribute("data-vff-confirmed"),g.style.outline="",g.style.outlineOffset=""}),document.querySelectorAll(".vff-field-badge").forEach(v=>v.remove()),console.log(`[VoiceFormFiller] ✅ Cleared ${p} DOM fields`);const m=document.createElement("div");m.style.cssText=`
			position: fixed;
			top: 20px;
			right: 20px;
			background: #10b981;
			color: white;
			padding: 16px 24px;
			border-radius: 8px;
			font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
			font-size: 14px;
			z-index: 999999;
			box-shadow: 0 4px 12px rgba(0,0,0,0.3);
		`,m.textContent=`✅ Form cleared (${p} fields)`,document.body.appendChild(m),setTimeout(()=>m.remove(),3e3)})}function T(o,e){const t=o.querySelector(".vff-status-icon"),n=o.querySelector(".vff-status-text");if(t&&n){const r={disconnected:{icon:"⭕",text:"Disconnected"},connecting:{icon:"🔄",text:"Connecting..."},connected:{icon:"✅",text:"Connected - Ready for voice"},recording:{icon:"🎤",text:"Listening... Speak now!"},error:{icon:"❌",text:"Connection error"},ready:{icon:"⚡",text:"Warmed up - Click Connect"}},i=r[e]||r.disconnected;t.textContent=i.icon,n.textContent=i.text}}function R(o,e){const t=o.querySelector(".vff-error");t&&(t.textContent=e,t.style.display="block",setTimeout(()=>{t.style.display="none"},5e3))}function ne(){try{new Function("return true")();const o=document.createElement("script");return o.textContent="// CSP test",{allowed:!0}}catch{return{allowed:!1,reason:"Site security policy blocks external scripts"}}}function re(o,e={}){const t={title:e.title??o.title??void 0,url:e.url??o.defaultView?.location?.href??void 0},n=[],r=new Set,i=ae(o),l=s=>s.replace(/([\\/:*?"<>|\[\]().#\s])/g,"\\$1"),a=s=>{if(s.tagName.toLowerCase()==="input"){const w=(s.getAttribute("type")||"").toLowerCase();if(!(!w||["text","checkbox","radio","email","tel","number","date","time","password","search"].includes(w)))return!0}if(s.type==="hidden"||s.hasAttribute("disabled")||s.getAttribute("aria-hidden")==="true"||s.closest('[aria-hidden="true"]')||s.closest(".FormCaptcha")||s.closest(".recaptcha"))return!0;const F=s.classList;return!!(F.contains("picker__input")||F.contains("cp_input_datetime")||s.getAttribute("role")==="presentation"||s.getAttribute("tabindex")==="-1"&&F.contains("picker__input")||q(s)||se(s))},c=s=>{const f=s.id;if(f){const w=`label[for="${l(f)}"]`,_=o.querySelector(w);if(_?.textContent)return _.textContent.trim()}const F=s.getAttribute("aria-labelledby");if(F){const w=o.getElementById(F);if(w?.textContent)return w.textContent.trim()}const b=s.getAttribute("aria-label");if(b)return b.trim();const y=s.closest("label");if(y?.textContent)return y.textContent.trim();const S=s.closest(".formFieldContainer, li");if(S){const w=S.querySelector(".labelForFieldElement");if(w?.textContent)return w.textContent.trim()}},d=s=>{const f=s.getAttribute("aria-describedby");if(f){const b=o.getElementById(f);if(b?.textContent)return b.textContent.trim()}const F=s.closest(".formFieldContainer, li");if(F){const b=F.querySelector(".tip");if(b?.textContent)return b.textContent.trim()}},u=s=>{if(!s)return;let f=s.replace(/\s+/g," ").trim();return f=f.replace(/\s*\*$/,"").trim(),f=f.replace(/\s*Required$/i,"").trim(),f.length?f:void 0},p=(s,f)=>{const F=s.tagName.toLowerCase();if(F==="textarea")return"textarea";if(F==="select")return"select";const b=s,y=(b.getAttribute("type")||"text").toLowerCase();if(y==="checkbox"||y==="radio"||y==="email"||y==="tel"||y==="number"||y==="date"||y==="time")return y;const S=(b.id||"").toLowerCase(),w=(b.name||"").toLowerCase(),_=(f||"").toLowerCase().replace(/-/g,""),C=(D,O)=>O.some(be=>D.includes(be));return C(S,["_date","date"])||C(w,["_date","date"])?"date":C(S,["_time","time"])||C(w,["_time","time"])?"time":C(_,["date of","date"])?"date":C(_,["time"])?"time":C(_,["email"])||C(S,["email"])||C(w,["email"])?"email":C(_,["phone","tel"])||C(S,["phone","tel"])||C(w,["phone","tel"])?"tel":"text"},m=s=>{if(s.tagName.toLowerCase()==="select"){const f=s;return Array.from(f.options).map(F=>F.textContent?.trim()||"").filter(Boolean)}},v=i??o,g=Array.from(v.querySelectorAll("input, textarea, select"));for(const s of g){if(a(s))continue;const f=s.id||s.getAttribute("name")||void 0;if(!f||r.has(f))continue;const F=u(c(s)),b=p(s,F),y=s.getAttribute("name"),S=y||F||f;if(!F&&!y||P(F,S))continue;const w=s.getAttribute("placeholder"),_=d(s),C=s.hasAttribute("required")||s.getAttribute("aria-required")==="true",D=m(s)||void 0,O=s.id?`#${l(s.id)}`:`[name="${l(S)}"]`;n.push({fieldId:f,name:S,label:F,type:b,required:C,options:D,placeholder:w??null,helpText:_??null,constraints:ie(s,b),selector:O}),r.add(f)}const h=Array.from(v.querySelectorAll('button[aria-haspopup="listbox"], [role="combobox"]'));for(const s of h){if(a(s)||i&&!i.contains(s))continue;const f=s.id||s.getAttribute("name")||void 0;if(!f||r.has(f))continue;const F=c(s),b=u(F),y=s.getAttribute("name"),S=y||b||f;if(!b&&!y||P(b,S))continue;const w=s.getAttribute("aria-required")==="true"||/required/i.test(F||"")||s.getAttribute("data-required")==="true",_=s.textContent?.trim()||null,C=s.id?`#${l(s.id)}`:void 0;n.push({fieldId:f,name:S,label:b,type:"select",required:w,options:void 0,placeholder:_,helpText:null,constraints:void 0,selector:C}),r.add(f)}return{source:"web",formMetadata:t,fields:n}}function ie(o,e){const t={};if(e==="date"){const l=o.getAttribute("data-cp-datetimepicker-format")||o.getAttribute("placeholder");l&&(t.format=l)}if(e==="time"){const l=o.getAttribute("data-cp-datetimepicker-interval");l&&(t.interval=Number(l));const a=o.getAttribute("placeholder");a&&(t.format=a)}const n=o.getAttribute("min");n&&(t.min=isNaN(Number(n))?n:Number(n));const r=o.getAttribute("max");r&&(t.max=isNaN(Number(r))?r:Number(r));const i=o.getAttribute("pattern");return i&&(t.pattern=i),Object.keys(t).length>0?t:void 0}function q(o){const e=o.getAttribute("style");return!!(e&&/display\s*:\s*none/i.test(e))}function se(o){let e=o.parentElement;for(;e;){if(q(e)||e.hasAttribute("hidden"))return!0;e=e.parentElement}return!1}function ae(o){const e=Array.from(o.querySelectorAll("form"));if(e.length===0)return null;const t=e.map(n=>{const r=n.querySelectorAll("input, textarea, select").length,i=n.getAttribute("data-drupal-selector")?.includes("webform-submission")?1e3:0;return{form:n,score:r+i}});return t.sort((n,r)=>r.score-n.score),t[0]?.form??null}function P(o,e){const t=(o||"").toLowerCase();return!!(t.includes("leave this field blank")||t.includes("honeypot")||e&&e.toLowerCase().includes("honeypot"))}function ce(){const o=performance.now();try{const e=re(document,{url:window.location.href,title:document.title}),t=performance.now()-o;if(e.fields.length===0)return{success:!1,error:"NO_FIELDS",stats:{fieldCount:0,requiredCount:0,parseTime:t}};const n=e.fields.length,r=e.fields.filter(l=>l.required).length,i=e.fields[0]?.fieldId;return n>150&&console.warn(`[VFF Parser] Large form detected: ${n} fields (>150 field warning threshold)`),console.log("[VFF Parser] Parse complete:",{fieldCount:n,requiredCount:r,firstFieldId:i,parseTime:`${t.toFixed(0)}ms`}),{success:!0,schema:e,stats:{fieldCount:n,requiredCount:r,parseTime:t,firstFieldId:i}}}catch(e){const t=performance.now()-o;return console.error("[VFF Parser] Parse failed:",e),{success:!1,error:"PARSE_FAILED",stats:{fieldCount:0,requiredCount:0,parseTime:t}}}}function le(o){return o>200?`Very large form detected (${o} fields). Performance may be degraded. Consider using "Scan visible only" option.`:o>150?`Large form detected (${o} fields). This may take longer to process.`:null}function N(o,e){return{CSP_BLOCKED:{code:"CSP_BLOCKED",icon:"🔒",title:"Site Security Restriction",message:"This website blocks external scripts for security.",action:"Try a different demo site or use a local test page."},MIC_DENIED:{code:"MIC_DENIED",icon:"🎤",title:"Microphone Access Denied",message:"Voice filling requires microphone permission.",action:"Click the 🎤 icon in your browser address bar → Allow → Retry"},NO_FIELDS:{code:"NO_FIELDS",icon:"📝",title:"No Form Fields Found",message:"No fillable form fields detected on this page.",action:"Navigate to a page with a form and try again."},WS_FAILED:{code:"WS_FAILED",icon:"🔌",title:"Connection Lost",message:e||"Lost connection to voice service.",action:"Click Reconnect to try again."},PARSE_FAILED:{code:"PARSE_FAILED",icon:"⚠️",title:"Form Parse Error",message:e||"Could not analyze form fields.",action:"Click Rescan or refresh the page."},INJECT_FAILED:{code:"INJECT_FAILED",icon:"❌",title:"Injection Failed",message:e||"Could not load voice form filler.",action:"Refresh the page and try again."},UNKNOWN:{code:"UNKNOWN",icon:"❓",title:"Unexpected Error",message:e||"Something went wrong.",action:"Refresh the page or contact support."}}[o]}function de(o,e){const t="";return o instanceof Error?`${t}${o.message} (${o.name})`:typeof o=="string"?`${t}${o}`:`${t}${String(o)}`}const U="__VFF_ACTIVE__",B="voice-form-filler-root";function ue(o={}){if(window[U]){console.log("[VoiceFormFiller] Already active, ignoring inject() call");return}const e=ne();if(!e.allowed){const t=N("CSP_BLOCKED");console.error("[VoiceFormFiller] CSP restriction detected:",e.reason),I(t);return}try{const t=ce();if(!t.success&&t.error==="NO_FIELDS"){const i=N("NO_FIELDS");console.warn("[VoiceFormFiller] No form fields found on page"),I(i);return}if(!t.success){const i=N("PARSE_FAILED",t.error);console.error("[VoiceFormFiller] Form parsing failed:",t.error),I(i);return}console.log("[VoiceFormFiller] Form parsed:",t.stats);const n=le(t.stats.fieldCount);n&&console.warn("[VoiceFormFiller]",n),fe(),console.log("[VoiceFormFiller] Restored form fields from sessionStorage");const r=document.createElement("div");r.id=B,r.style.cssText=`
			position: fixed;
			top: 0;
			left: 0;
			width: 100%;
			height: 100%;
			pointer-events: none;
			z-index: ${o.zIndex||9999};
		`,document.body.appendChild(r),Z(r,o,t),window[U]=!0,console.log("[VoiceFormFiller] Injection successful")}catch(t){console.error("[VoiceFormFiller] Injection failed:",t);const n=N("INJECT_FAILED",de(t));I(n);const r=document.getElementById(B);r&&r.remove()}}function I(o){const e=document.createElement("div"),t=["CSP_BLOCKED","NO_FIELDS"].includes(o.code);e.style.cssText=`
		position: fixed;
		top: ${t?"50%":"20px"};
		left: ${t?"50%":"auto"};
		right: ${t?"auto":"20px"};
		transform: ${t?"translate(-50%, -50%)":"none"};
		background: ${t?"#ff9800":"#f44336"};
		color: white;
		padding: 24px 32px;
		border-radius: 8px;
		font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
		font-size: 16px;
		z-index: 999999;
		max-width: 500px;
		box-shadow: 0 4px 12px rgba(0,0,0,0.3);
		text-align: ${t?"center":"left"};
	`,e.innerHTML=`
		<div style="font-size: 24px; margin-bottom: 8px;">${o.icon}</div>
		<strong style="display: block; margin-bottom: 8px;">${o.title}</strong>
		<div style="font-size: 14px; opacity: 0.9; margin-bottom: ${o.action?"12px":"0"};">
			${o.message}
		</div>
		${o.action?`<div style="font-size: 13px; font-weight: 500;">${o.action}</div>`:""}
	`,document.body.appendChild(e),setTimeout(()=>{e.remove()},t?1e4:7e3)}function fe(){const o=x.load();if(!o||!o.current_values||Object.keys(o.current_values).length===0){console.log("[VoiceFormFiller] No saved form state to restore");return}let e=0;for(const[t,n]of Object.entries(o.current_values)){if(!n.value)continue;const r=document.getElementById(t);if(!r){console.warn("[VoiceFormFiller] Saved field not found in DOM:",t);continue}if(r.tagName==="SELECT"){const i=r,l=String(n.value);for(let a=0;a<i.options.length;a++){const c=i.options[a];if(c.value===l||c.text===l){i.selectedIndex=a,e++;break}}}else r.tagName==="INPUT"&&r.type==="checkbox"?(r.checked=!!n.value,e++):r.tagName==="INPUT"&&r.type==="radio"?r.value===n.value&&(r.checked=!0,e++):(r.value=String(n.value),e++);n.confirmed&&(r.setAttribute("data-vff-confirmed","true"),r.style.outline="2px solid #10b981",r.style.outlineOffset="2px")}e>0&&console.log(`[VoiceFormFiller] ✅ Restored ${e} fields from sessionStorage`)}const W="__VFF_ACTIVE__",me="voice-form-filler-root",A={timers:[],listeners:[]};function pe(){if(!window[W]){console.log("[VoiceFormFiller] Not active, nothing to destroy");return}console.log("[VoiceFormFiller] Starting teardown...");try{A.websocket&&(A.websocket.close(),A.websocket=void 0),A.audioContext&&(A.audioContext.close(),A.audioContext=void 0),A.mediaStream&&(A.mediaStream.getTracks().forEach(e=>e.stop()),A.mediaStream=void 0),A.timers.forEach(e=>clearTimeout(e)),A.timers=[],A.listeners.forEach(({element:e,event:t,handler:n})=>{e.removeEventListener(t,n)}),A.listeners=[];const o=document.getElementById(me);o&&o.remove(),delete window[W],console.log("[VoiceFormFiller] Teardown complete")}catch(o){console.error("[VoiceFormFiller] Error during teardown:",o),delete window[W]}}const ge="1.0.0",he=new Date().toISOString();function Fe(){return`${ge} (${he})`}const z={inject:ue,destroy:pe,getVersion:Fe,isActive:()=>!!window.__VFF_ACTIVE__,_test_getConnectionManager:Q};return typeof window<"u"&&(window.VoiceFormFiller=z),z}();
