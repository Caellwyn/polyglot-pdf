var vf=Object.defineProperty;var $f=(S,f,b)=>f in S?vf(S,f,{enumerable:!0,configurable:!0,writable:!0,value:b}):S[f]=b;var Ke=(S,f,b)=>$f(S,typeof f!="symbol"?f+"":f,b);import{r as Y,a as xf,c as et}from"./vendor-react-CfsYHMYl.js";(function(){const f=document.createElement("link").relList;if(f&&f.supports&&f.supports("modulepreload"))return;for(const k of document.querySelectorAll('link[rel="modulepreload"]'))v(k);new MutationObserver(k=>{for(const w of k)if(w.type==="childList")for(const I of w.addedNodes)I.tagName==="LINK"&&I.rel==="modulepreload"&&v(I)}).observe(document,{childList:!0,subtree:!0});function b(k){const w={};return k.integrity&&(w.integrity=k.integrity),k.referrerPolicy&&(w.referrerPolicy=k.referrerPolicy),k.crossOrigin==="use-credentials"?w.credentials="include":k.crossOrigin==="anonymous"?w.credentials="omit":w.credentials="same-origin",w}function v(k){if(k.ep)return;k.ep=!0;const w=b(k);fetch(k.href,w)}})();var Xc={exports:{}},Yi={};/**
 * @license React
 * react-jsx-runtime.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var Sf=Y,kf=Symbol.for("react.element"),Tf=Symbol.for("react.fragment"),Cf=Object.prototype.hasOwnProperty,Ef=Sf.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,If={key:!0,ref:!0,__self:!0,__source:!0};function Yc(S,f,b){var v,k={},w=null,I=null;b!==void 0&&(w=""+b),f.key!==void 0&&(w=""+f.key),f.ref!==void 0&&(I=f.ref);for(v in f)Cf.call(f,v)&&!If.hasOwnProperty(v)&&(k[v]=f[v]);if(S&&S.defaultProps)for(v in f=S.defaultProps,f)k[v]===void 0&&(k[v]=f[v]);return{$$typeof:kf,type:S,key:w,ref:I,props:k,_owner:Ef.current}}Yi.Fragment=Tf;Yi.jsx=Yc;Yi.jsxs=Yc;Xc.exports=Yi;var K=Xc.exports,Nr={},Lc=xf;Nr.createRoot=Lc.createRoot,Nr.hydrateRoot=Lc.hydrateRoot;class _e{static init(f){const b=this.load();if(b&&b.schema.form_metadata.url===f.form_metadata.url&&Date.now()-b.last_updated<60*60*1e3)return b;const v={schema:f,current_values:{},last_updated:Date.now()};return this.save(v),v}static load(){try{const f=sessionStorage.getItem(this.STORAGE_KEY);if(!f)return null;const b=JSON.parse(f);return b.completed_sections&&Array.isArray(b.completed_sections)&&(b.completed_sections=new Set(b.completed_sections)),b}catch{return null}}static save(f){try{f.last_updated=Date.now();const b={...f,completed_sections:f.completed_sections?Array.from(f.completed_sections):void 0};sessionStorage.setItem(this.STORAGE_KEY,JSON.stringify(b))}catch{}}static updateFieldValue(f,b,v,k){const w=f.current_values[b]||{value:null,confirmed:!1},I=k?.confirmed!==void 0?k.confirmed:typeof w.confirmed=="boolean"?w.confirmed:!1,A={...f,current_values:{...f.current_values,[b]:{...w,value:v,confirmed:I,lastModified:Date.now()}}};return this.save(A),A}static markConfirmed(f,b){const v={...f,current_values:{...f.current_values}};for(const k of b)v.current_values[k]&&(v.current_values[k]={...v.current_values[k],confirmed:!0});return this.save(v),v}static getHandshakePayload(f,b="English"){const v={type:"handshake",schema:f.schema,current_values:f.current_values,fill_language:b};if(f.section_index){v.section_number=f.current_section,v.total_sections=f.section_index.total_sections;const k=f.section_index.sections.find(I=>I.section_number===f.current_section);k&&(v.section_label=k.section_label);const w=this.getSpokenNameMap(f);v.previous_spoken_names=Array.from(w.keys())}return v}static setSessionId(f,b){const v={...f,session_id:b};return this.save(v),v}static clear(){sessionStorage.removeItem(this.STORAGE_KEY)}static getUnconfirmedFields(f){return f.schema.fields.filter(b=>{const v=f.current_values[b.id];return!v||!v.confirmed}).map(b=>b.id)}static getCompletionPercentage(f){const b=f.schema.fields.length;if(b===0)return 100;const v=f.schema.fields.filter(k=>{const w=f.current_values[k.id];return w&&w.value!==null&&w.value!==""}).length;return Math.round(v/b*100)}static debug(f){}static initWithSections(f,b){const v=this.load();if(v&&v.full_schema&&v.section_index&&v.full_schema.form_metadata.url===f.form_metadata.url&&Date.now()-v.last_updated<60*60*1e3)return v;const w={schema:this.getSectionSchema(f,b,1),current_values:{},last_updated:Date.now(),current_section:1,completed_sections:new Set,section_index:b,full_schema:f};return this.save(w),w}static getSectionSchema(f,b,v){const k=b.sections.find(I=>I.section_number===v);if(!k)throw new Error(`Section ${v} not found in index`);const w=k.field_indices.map(I=>f.fields[I]);return{...f,fields:w}}static switchSection(f,b){if(!f.section_index||!f.full_schema)throw new Error("Cannot switch sections: section_index or full_schema not initialized");if(b<1||b>f.section_index.total_sections)throw new Error(`Invalid section number: ${b}`);const v=this.getSectionSchema(f.full_schema,f.section_index,b),k={...f,schema:v,current_section:b};return this.save(k),k}static completeSection(f,b){const v=f.completed_sections||new Set,k={...f,completed_sections:new Set([...v,b])};return this.save(k),k}static getSpokenNameMap(f){const b=new Map;if(!f.full_schema||!f.section_index||!f.completed_sections)return b;const v=new Set([...f.completed_sections,f.current_section||1]);for(const k of v){const w=f.section_index.sections.find(I=>I.section_number===k);if(w)for(const I of w.field_indices){const A=f.full_schema.fields[I];if(!A)continue;A.spoken_name&&b.set(A.spoken_name.toLowerCase(),A.id);const C=A.spoken_aliases;if(Array.isArray(C))for(const Z of C)b.set(Z.toLowerCase(),A.id)}}return b}static getSectionLabel(f,b){return f.section_index&&f.section_index.sections.find(k=>k.section_number===b)?.section_label||null}static findSectionByLabel(f,b){if(!f.section_index)return null;const v=b.toLowerCase().trim();return f.section_index.sections.find(w=>w.section_label.toLowerCase()===v)?.section_number||null}static getSectionFieldCount(f){if(!f.section_index||!f.current_section)return{filled:0,total:f.schema.fields.length};const b=f.section_index.sections.find(k=>k.section_number===f.current_section);return b?{filled:f.schema.fields.filter(k=>{const w=f.current_values[k.id];return w&&w.value!==null&&w.value!==""}).length,total:b.field_count}:{filled:0,total:f.schema.fields.length}}}Ke(_e,"STORAGE_KEY","web_form_state"),Ke(_e,"SECTION_KEY","vff_current_section"),Ke(_e,"COMPLETED_SECTIONS_KEY","vff_completed_sections"),Ke(_e,"SPOKEN_NAME_MAP_KEY","vff_spoken_name_map");function Vr(S,f){const{requiredOnly:b=!1,skipConfirmed:v=!0}=f||{};if(!S.schema||!S.schema.fields||S.schema.fields.length===0)return null;for(const k of S.schema.fields){if(b&&!k.required)continue;const w=S.current_values[k.id],I=w?.confirmed===!0;if(!(v&&I||w?.value!==null&&w?.value!==void 0&&w?.value!==""))return k}return null}function Af(S){if(!S.schema||!S.schema.fields||S.schema.fields.length===0)return!0;if(S.schema.fields.some(b=>b.required)){for(const b of S.schema.fields)if(b.required&&!(S.current_values[b.id]?.confirmed===!0))return!1;return!0}else{for(const b of S.schema.fields)if(!(S.current_values[b.id]?.confirmed===!0))return!1;return!0}}function Lr(S,f){const b=f?`#${f}`:"",v=S.required?", required":"",k=S.options&&S.options.length>0?`, options: [${S.options.join(", ")}]`:"";return`Next field to fill is ${b}: '${S.name}' (type: ${S.type}${v}${k})`}function zf(S,f){if(!S.schema||!S.schema.fields)return null;const b=S.schema.fields.findIndex(v=>v.id===f);return b>=0?b+1:null}class Uc{constructor(f,b={},v="English"){Ke(this,"ws",null);Ke(this,"state");Ke(this,"callbacks");Ke(this,"status","disconnected");Ke(this,"reconnectAttempts",0);Ke(this,"maxReconnectAttempts",5);Ke(this,"reconnectDelay",1e3);Ke(this,"reconnectTimer",null);Ke(this,"audioQueue",[]);Ke(this,"audioChunkCount",0);Ke(this,"isProcessingAudio",!1);Ke(this,"enableAutoReconnect",!1);Ke(this,"isSectionSwitching",!1);Ke(this,"connectedUrl","");Ke(this,"idleTimedOut",!1);Ke(this,"fillLanguage","English");this.state=_e.init(f),this.callbacks=b,this.fillLanguage=v}async connect(f="ws://localhost:8000/ws/fill",b=1e4){if(!(this.ws&&this.ws.readyState===WebSocket.OPEN))return this.idleTimedOut&&(console.log("[WebFormConnection] 🔄 Clearing idle timeout flag for manual reconnect"),this.idleTimedOut=!1),this.connectedUrl=f,this.isSectionSwitching||this.setStatus("connecting"),new Promise((v,k)=>{const w=setTimeout(()=>{this.ws&&(this.ws.close(),this.ws=null),k(new Error(`Connection timeout after ${b}ms`))},b);try{this.ws=new WebSocket(f),this.ws.onopen=()=>{clearTimeout(w),this.handleOpen(),v()},this.ws.onmessage=I=>this.handleMessage(I),this.ws.onerror=I=>{clearTimeout(w),this.handleError(I),k(I)},this.ws.onclose=()=>{clearTimeout(w),this.handleClose()}}catch(I){clearTimeout(w),this.handleError(I),k(I)}})}disconnect(){this.reconnectTimer&&(clearTimeout(this.reconnectTimer),this.reconnectTimer=null),this.ws&&(this.ws.close(),this.ws=null),this.isSectionSwitching||this.setStatus("disconnected")}handleOpen(){if(this.reconnectAttempts=0,this.reconnectDelay=1e3,this.enableAutoReconnect=!0,this.isSectionSwitching)return;const f=_e.getHandshakePayload(this.state,this.fillLanguage);this.send(f)}async handleMessage(f){if(f.data instanceof ArrayBuffer||f.data instanceof Blob){await this.handleAudioFrame(f.data);return}try{const b=JSON.parse(f.data);switch(b.type){case"session_ready":this.handleSessionReady(b);break;case"field_update":this.handleFieldUpdate(b);break;case"form_updated":this.handleFormUpdated(b);break;case"form_state_ack":break;case"hint_ack":break;case"get_form_state":this.handleGetFormStateRequest(b);break;case"get_next_field_hint":this.handleGetNextFieldHintRequest(b);break;case"prepare_section_switch":this.handlePrepareSectionSwitchRequest(b);break;case"section_switched":this.handleSectionSwitched(b);break;case"switch_section":this.handleSwitchSectionRequest(b);break;case"get_field_value":this.handleGetFieldValueRequest(b);break;case"complete_section":this.handleCompleteSectionRequest(b);break;case"error":this.handleServerError(b);break;case"ai_response":break;case"turn_complete":window.vffOnTurnComplete&&window.vffOnTurnComplete();break;case"gemini_session_restarted":console.log("[WebFormConnection] ✅ Gemini session restarted successfully"),this.callbacks.onSessionRestarted&&this.callbacks.onSessionRestarted();break;case"idle_timeout":console.log("[WebFormConnection] ⏱️ Idle timeout received from backend:",b),this.idleTimedOut=!0,this.setStatus("idle_timeout");break;default:break}}catch{}}handleSessionReady(f){const{session_id:b,ephemeral:v}=f;this.state=_e.setSessionId(this.state,b),this.setStatus("connected"),this.callbacks.onSessionReady&&this.callbacks.onSessionReady(b)}handleFieldUpdate(f){const{updates:b}=f;if(!b||typeof b!="object")return;const v=[];for(const[k,w]of Object.entries(b)){const I=this.state.schema.fields.find(A=>A.name===k||A.id===k);I&&(this.updateField(I.id,w,{confirmed:!0,emit:!1}),v.push({fieldId:I.id,value:w}))}this.callbacks.onFieldUpdate&&v.length>0&&this.callbacks.onFieldUpdate(v)}handleFormUpdated(f){const b=f&&f.data||{},v=b.form_state||{},k=b.applied_fields||[],w=b.request_next_field_hint||!1,I=b.request_id;if(!v||typeof v!="object")return;const A=new Set(k.map(W=>String(W))),C=A.size>0,Z=[];for(const W of this.state.schema.fields){const H=v[W.id]??v[W.name??""];if(H===void 0)continue;const X=A.has(W.id)||(W.name?A.has(W.name):!1);if(C&&!X)continue;const J=this.state.current_values[W.id]?.value;(X||!Object.is(J,H))&&(this.updateField(W.id,H,{confirmed:X,emit:!1}),Z.push({fieldId:W.id,value:H}))}for(const[W,H]of Object.entries(v)){if(this.state.schema.fields.some(P=>P.id===W||P.name===W))continue;const X=W+"[]",J=this.state.schema.fields.find(P=>P.id===X||P.name===X);if(J){const P=A.has(W)||A.has(X);if(C&&!P)continue;const Q=this.state.current_values[J.id]?.value;if(!(P||!Object.is(Q,H)))continue;this.updateField(J.id,H,{confirmed:P,emit:!1}),Z.push({fieldId:J.id,value:H})}}if(Z.length&&this.callbacks.onFieldUpdate&&this.callbacks.onFieldUpdate(Z),w&&I){const W=this.computeNextFieldHintString();W&&sessionStorage.setItem("vff_last_field_hint",W),this.send({type:"next_field_hint_response",request_id:I,hint:W})}}handleGetFormStateRequest(f){const b=f.request_id,v=f.field_ids||[],k={};if(v.length===0)for(const[w,I]of Object.entries(this.state.current_values))k[w]={value:I.value,confirmed:I.confirmed};else for(const w of v){let I=this.state.current_values[w];!I&&!w.endsWith("[]")&&(I=this.state.current_values[w+"[]"]),!I&&w.endsWith("[]")&&(I=this.state.current_values[w.slice(0,-2)]),I?k[w]={value:I.value,confirmed:I.confirmed}:k[w]={value:null,confirmed:!1}}this.send({type:"form_state_response",request_id:b,field_values:k})}handleGetNextFieldHintRequest(f){const b=f.request_id,v=this.computeNextFieldHintString();v&&sessionStorage.setItem("vff_last_field_hint",v),this.send({type:"next_field_hint_response",request_id:b,hint:v})}computeNextFieldHintString(){if(Af(this.state))return null;const f=Vr(this.state,{skipConfirmed:!0});if(!f)return null;const b=zf(this.state,f.id);return Lr(f,b||void 0)}getNextFieldHint(){return this.computeNextFieldHintString()}async handleSwitchSectionRequest(f){const b=f.identifier;try{let v;if(typeof b=="number")v=b;else if(typeof b=="string"){const k=parseInt(b,10);if(!isNaN(k))v=k;else{const w=_e.load();if(w?.section_index){const I=b.toLowerCase(),A=w.section_index.sections.find(C=>C.section_label.toLowerCase()===I||C.section_id.toLowerCase()===I);A&&(v=A.section_number)}}}if(!v)return;await this.switchSection(v,this.connectedUrl)}catch{}}handlePrepareSectionSwitchRequest(f){const b=f.request_id,v=f.identifier;console.log("[WebFormConnection] handlePrepareSectionSwitchRequest START",{requestId:b,identifier:v});try{const k=_e.load();if(console.log("[WebFormConnection] Loaded state",{hasState:!!k,hasSectionIndex:!!k?.section_index}),!k||!k.section_index){console.log("[WebFormConnection] No state/section_index, sending null response"),this.send({type:"section_info_response",request_id:b,section_info:null});return}let w;if(typeof v=="number")w=v;else if(typeof v=="string"){const J=parseInt(v,10);if(!isNaN(J))w=J;else{const P=v.toLowerCase(),Q=k.section_index.sections.find(G=>G.section_label.toLowerCase()===P||G.section_id.toLowerCase()===P);Q&&(w=Q.section_number)}}if(console.log("[WebFormConnection] Parsed target number:",w),!w){console.log("[WebFormConnection] Invalid target number, sending null response"),this.send({type:"section_info_response",request_id:b,section_info:null});return}console.log("[WebFormConnection] Switching to section",w);const I=_e.switchSection(k,w);this.state=I,console.log("[WebFormConnection] Building section schema and values");const A=I.schema,C=new Set(A.fields.map(J=>J.id)),Z={};for(const[J,P]of Object.entries(I.current_values))C.has(J)&&(Z[J]=P);console.log("[WebFormConnection] Building previous spoken names");const W=_e.getSpokenNameMap(I),H=Array.from(W.keys());console.log("[WebFormConnection] Computing initial field hint");const X=this.computeNextFieldHintString();X&&sessionStorage.setItem("vff_last_field_hint",X),console.log("[WebFormConnection] Sending section_info_response",{requestId:b,sectionNumber:w,fieldCount:A.fields.length,valueCount:Object.keys(Z).length}),this.send({type:"section_info_response",request_id:b,section_info:{schema:A,current_values:Z,metadata:{section_number:w,total_sections:I.section_index.total_sections,section_label:_e.getSectionLabel(I,w)||"",previous_spoken_names:H},initial_field_hint:X}}),console.log("[WebFormConnection] handlePrepareSectionSwitchRequest COMPLETE")}catch(k){console.error("[WebFormConnection] Error preparing section switch:",k),this.send({type:"section_info_response",request_id:b,section_info:null})}}handleSectionSwitched(f){const b=f.section_number;console.log(`[WebFormConnection] Section switched confirmed: ${b}`),this.setStatus("connected")}handleGetFieldValueRequest(f){const b=f.request_id,v=f.spoken_name;try{const k=_e.load();if(!k){this.sendFieldValueResponse(b,null,!1);return}const I=_e.getSpokenNameMap(k).get(v.toLowerCase());if(!I){this.sendFieldValueResponse(b,null,!1);return}const A=k.current_values[I];A!=null&&String(A).trim()!==""?this.sendFieldValueResponse(b,A,!0):this.sendFieldValueResponse(b,null,!1)}catch{this.sendFieldValueResponse(b,null,!1)}}sendFieldValueResponse(f,b,v){this.send({type:"field_value_response",request_id:f,value:b,found:v})}async handleCompleteSectionRequest(f){try{const b=_e.load();if(!b||!b.current_section)throw new Error("Section state not initialized");const v=b.current_section,k=_e.completeSection(b,v);if(this.state=k,v>=k.section_index.total_sections){this.send({type:"section_completed",next_section:v,form_complete:!0});return}const w=v+1;await this.switchSection(w,this.connectedUrl),this.send({type:"section_completed",next_section:w,form_complete:!1})}catch(b){console.error("[WebFormConnection] Error completing section:",b),this.send({type:"section_completed",success:!1,error:b instanceof Error?b.message:String(b)})}}sendCompletionMessage(){this.send({type:"completion_message",message:"Say the following: 'The form is complete. if all fields are correct, please press submit.'"})}async handleAudioFrame(f){const b=f instanceof Blob?await f.arrayBuffer():f;this.audioChunkCount||(this.audioChunkCount=0),this.audioChunkCount++,this.audioChunkCount===1?console.log(`[WebFormConnection] 📥 First audio chunk received from server (${b.byteLength} bytes)`):this.audioChunkCount%10===0&&console.log(`[WebFormConnection] 📥 Audio chunk #${this.audioChunkCount} (${b.byteLength} bytes)`),this.audioQueue.push(b),this.isProcessingAudio||this.processAudioQueue()}async processAudioQueue(){for(this.isProcessingAudio=!0;this.audioQueue.length>0;){const f=this.audioQueue.shift();this.callbacks.onAudioData&&this.callbacks.onAudioData(f)}this.isProcessingAudio=!1}handleServerError(f){console.error("[WebFormConnection] Server error received:",{code:f.code,reason:f.reason,message:f.message,fullMessage:f});const b=f.message||f.reason||f.code||"Server error",v=new Error(b);this.callbacks.onError&&this.callbacks.onError(v)}handleError(f){this.isSectionSwitching||this.setStatus("error"),this.callbacks.onError&&f instanceof Error&&this.callbacks.onError(f)}handleClose(){if(!this.enableAutoReconnect){this.setStatus("disconnected");return}if(!this.isSectionSwitching){if(this.idleTimedOut){console.log("[WebFormConnection] ⏱️ Idle timeout - no auto-reconnect, user must manually reconnect"),this.setStatus("idle_timeout");return}this.status!=="disconnected"&&this.reconnectAttempts<this.maxReconnectAttempts?this.attemptReconnect():this.setStatus("disconnected")}}attemptReconnect(){this.reconnectAttempts++,this.setStatus("reconnecting");const f=Math.min(this.reconnectDelay*Math.pow(2,this.reconnectAttempts-1),3e4);this.reconnectTimer=window.setTimeout(()=>{this.connect()},f)}async waitForBufferDrain(f=1e3){if(!this.ws)return;const b=Date.now();for(;this.ws.bufferedAmount>0;){if(Date.now()-b>f){console.warn("[WebFormConnection] Buffer drain timeout",{bufferedAmount:this.ws.bufferedAmount,waitedMs:Date.now()-b});break}await new Promise(v=>setTimeout(v,10))}this.ws.bufferedAmount===0&&console.log("[WebFormConnection] Buffer drained successfully",{waitedMs:Date.now()-b})}send(f){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.error("[WebFormConnection] send() called but WebSocket not open!",{hasWs:!!this.ws,readyState:this.ws?.readyState,message:f});return}if(f instanceof ArrayBuffer)this.ws.send(f);else{const b=JSON.stringify(f);console.log("[WebFormConnection] Sending JSON message",{type:f.type,size:b.length,readyState:this.ws.readyState,bufferedAmount:this.ws.bufferedAmount}),this.ws.send(b)}}sendAudio(f){this.send(f)}sendManualFieldUpdate(f,b,v){!this.ws||this.ws.readyState!==WebSocket.OPEN||this.send({type:"manual_field_update",field_id:f,field_name:b,value:v})}sendActivityStart(){if(console.log(`[WebFormConnection] 📤 sendActivityStart() called - WebSocket state: ${this.ws?this.ws.readyState:"null"} (OPEN=${WebSocket.OPEN})`),!this.ws||this.ws.readyState!==WebSocket.OPEN){console.error(`[WebFormConnection] ❌ Cannot send activity_start - WebSocket not open (state: ${this.ws?this.ws.readyState:"null"})`);return}console.log("[WebFormConnection] 📤 Sending activity_start message to backend"),this.send({type:"vad_activity_start",timestamp:Date.now()})}sendActivityEnd(){if(console.log(`[WebFormConnection] 📤 sendActivityEnd() called - WebSocket state: ${this.ws?this.ws.readyState:"null"} (OPEN=${WebSocket.OPEN})`),!this.ws||this.ws.readyState!==WebSocket.OPEN){console.error(`[WebFormConnection] ❌ Cannot send activity_end - WebSocket not open (state: ${this.ws?this.ws.readyState:"null"})`);return}console.log("[WebFormConnection] 📤 Sending activity_end message to backend"),this.send({type:"vad_activity_end",timestamp:Date.now()})}sendPrompt(f){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.warn("[WebFormConnection] Cannot send prompt - not connected");return}console.log("[WebFormConnection] Sending prompt to Gemini:",f),this.send({type:"completion_message",message:f})}sendRecoveryPrompt(f,b){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.warn("[WebFormConnection] Cannot send recovery prompt - not connected");return}console.log(`[WebFormConnection] Sending recovery prompt level ${f}`,b?`with hint: ${b}`:""),this.send({type:"recovery_prompt",level:f,next_field_hint:b})}endGeminiSession(){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.warn("[WebFormConnection] Cannot end Gemini session - not connected");return}console.log("[WebFormConnection] 🚪 Ending Gemini session (keeping WebSocket alive)"),this.send({type:"end_gemini_session"})}async changeFillLanguage(f){!this.ws||this.ws.readyState!==WebSocket.OPEN||(this.fillLanguage=f,this.send({type:"change_fill_language",language:f}))}updateField(f,b,v){const k=v?.confirmed,w=v?.emit??!1;this.state=_e.updateFieldValue(this.state,f,b,{confirmed:k}),w&&this.flushField(f)}flushField(f){if(!this.ws||this.ws.readyState!==WebSocket.OPEN)return;const b=this.state.current_values[f];b&&this.send({type:"form_state",fields:[{field_id:f,value:b.value,confirmed:!!b.confirmed}]})}setStatus(f){this.status!==f&&(this.status=f,this.callbacks.onStatusChange&&this.callbacks.onStatusChange(f))}getStatus(){return this.status}getState(){return this.state}getCompletionPercentage(){return _e.getCompletionPercentage(this.state)}reset(){this.disconnect(),_e.clear()}async startSection(f,b="ws://localhost:8000/ws/fill"){try{this.isSectionSwitching=!0,this.setStatus("switching_section"),this.ws&&this.ws.readyState===WebSocket.OPEN&&(this.disconnect(),await new Promise(W=>setTimeout(W,100)));let v=_e.load();if(!v||!v.section_index||!v.full_schema)throw new Error("Section index or full schema not initialized");v=_e.switchSection(v,f),this.state=v;const k=v.schema,w={},I=new Set(k.fields.map(W=>W.id));for(const[W,H]of Object.entries(v.current_values))I.has(W)&&(w[W]=H);const A=_e.getSpokenNameMap(v),C=Array.from(A.keys());await this.connect(b),this.isSectionSwitching=!1;const Z=this.computeNextFieldHintString();this.send({type:"handshake",schema:k,current_values:w,fill_language:this.fillLanguage,section_number:f,total_sections:v.section_index.total_sections,section_label:_e.getSectionLabel(v,f)||"",previous_spoken_names:C,initial_field_hint:Z})}catch(v){throw this.isSectionSwitching=!1,v}}async switchSection(f,b){const v=_e.load();if(!v||!v.section_index)throw new Error("Section index not initialized");let k;if(typeof f=="number")k=f;else{const X=_e.findSectionByLabel(v,f);if(!X)throw new Error(`Section not found: ${f}`);k=X}if(k<1||k>v.section_index.total_sections)throw new Error(`Invalid section number: ${k} (must be 1-${v.section_index.total_sections})`);console.log("[WebFormConnection] Waiting for buffer to drain before section switch"),await this.waitForBufferDrain(1e3),this.setStatus("switching_section");const w=_e.switchSection(v,k);this.state=w;const I=w.schema,A=new Set(I.fields.map(X=>X.id)),C={};for(const[X,J]of Object.entries(w.current_values))A.has(X)&&(C[X]=J);const Z=_e.getSpokenNameMap(w),W=Array.from(Z.keys()),H=this.computeNextFieldHintString();console.log("[WebFormConnection] Sending section switch with embedded info",{sectionNumber:k,fieldCount:I.fields.length,valueCount:Object.keys(C).length}),this.send({type:"manual_section_switch",identifier:k.toString(),section_info:{schema:I,current_values:C,metadata:{section_number:k,total_sections:w.section_index.total_sections,section_label:_e.getSectionLabel(w,k)||"",previous_spoken_names:W},initial_field_hint:H}})}async completeSection(f){if(!f)throw new Error("wsUrl is required for completeSection - must pass the connected backend URL");const b=_e.load();if(!b||!b.current_section||!b.section_index)throw new Error("Section state not initialized");const v=b.current_section,k=_e.completeSection(b,v);if(this.state=k,v>=k.section_index.total_sections){this.setStatus("connected");return}const w=v+1;await this.startSection(w,f)}getCurrentSection(){return this.state.current_section}getCompletedSections(){return this.state.completed_sections||new Set}}function qc(S={}){const f=new Set,b=new Map,v=new Map,k=new Set;function w(R,D){if(b.has(R))return;const B=()=>{if(k.has(D))return;const j=Date.now(),V=v.get(D)||0;if(!(j-V<100)&&(v.set(D,j),f.has(D)&&A(R,D),S.onManualEdit)){const q=R.value;q&&q.trim()&&S.onManualEdit(D,q)}};R.addEventListener("blur",B),R.addEventListener("change",B),b.set(R,B)}function I(R){console.log("[VFF FieldManager] Setting up listeners on",R.length,"schema fields");for(const D of R){const B=D.id;if(!B)continue;let j=document.getElementById(B);if(!j){const V=document.querySelectorAll(`input[name="${B}"], textarea[name="${B}"], select[name="${B}"]`);if(V.length>0){V.forEach(q=>{w(q,B)});continue}}j&&w(j,B)}}function A(R,D){R.style.outline="",R.style.outlineOffset="";const B=R.parentElement?.querySelector(".vff-field-badge");B&&B.remove(),R.removeAttribute("data-vff-confirmed"),f.delete(D),console.log("[VFF FieldManager] Cleared AI confirmation for:",D)}S.schema?.fields&&I(S.schema.fields);function C(R){console.log("[VFF FieldManager] 📝 Applying",R.length,"field update(s)");const D={success:[],notFound:[],errors:[]};for(const B of R){k.add(B.fieldId);const j=B.value||"";let V=document.getElementById(B.fieldId);if(!V){const ye=document.querySelectorAll(`input[name="${B.fieldId}"], textarea[name="${B.fieldId}"], select[name="${B.fieldId}"]`);if(ye.length>0){const ue=ye[0];if(ye.length>1){if(ue.type==="radio"){J(ye,j,B.fieldId),D.success.push(B.fieldId);continue}else if(ue.type==="checkbox"){H(ye,j,B.fieldId),D.success.push(B.fieldId);continue}}V=ue}if(!V){const ue=document.querySelector(`[role="combobox"][id="${B.fieldId}"], button[aria-haspopup="listbox"][id="${B.fieldId}"]`);if(ue){Q(ue,j,B.fieldId),D.success.push(B.fieldId);continue}}if(!V){console.warn("[VFF FieldManager] ❌ Field not found:",B.fieldId),D.notFound.push(B.fieldId);continue}}const q=V,ne=q.type?.toLowerCase();if(V.tagName==="SELECT")Z(V,j,B.fieldId);else if(ne==="checkbox")W(q,j,B.fieldId);else if(ne==="radio")P(q,j,B.fieldId);else if(V.tagName==="INPUT"||V.tagName==="TEXTAREA"){const ye=String(j);V.value=ye,V.dispatchEvent(new Event("input",{bubbles:!0})),V.dispatchEvent(new Event("change",{bubbles:!0}));const ue=ye.substring(0,50);console.log("[VFF FieldManager] Updated text field:",B.fieldId,"→",ue)}V&&(V.setAttribute("data-vff-confirmed","true"),f.add(B.fieldId),G(V),w(V,B.fieldId),D.success.push(B.fieldId),setTimeout(()=>{k.delete(B.fieldId)},50))}console.log("[VFF FieldManager] 📊 Update summary:",{total:R.length,success:D.success.length,notFound:D.notFound.length,errors:D.errors.length}),D.notFound.length>0&&console.warn("[VFF FieldManager] ⚠️ Fields not found:",D.notFound),D.errors.length>0&&console.error("[VFF FieldManager] ❌ Errors:",D.errors),D.success.length>0&&console.log("[VFF FieldManager] ✅ Successfully updated:",D.success)}function Z(R,D,B){let j=!1;for(let V=0;V<R.options.length;V++){const q=R.options[V];if(q.value===D||q.text===D){R.selectedIndex=V,j=!0,console.log("[VFF FieldManager] ✓ Exact match for select:",B,"→",q.text);break}}if(!j){const V=D.toLowerCase();for(let q=0;q<R.options.length;q++){const ne=R.options[q],ye=ne.text.toLowerCase(),ue=ne.value.toLowerCase();if(ye.includes(V)||V.includes(ye)||ue.includes(V)||V.includes(ue)){R.selectedIndex=q,j=!0,console.log("[VFF FieldManager] ≈ Fuzzy match for select:",B,"→",ne.text);break}}}j||console.warn("[VFF FieldManager] ⚠️ No matching option found for:",D,"in",B),R.dispatchEvent(new Event("change",{bubbles:!0})),R.dispatchEvent(new Event("input",{bubbles:!0}))}function W(R,D,B){let j=!1;typeof D=="boolean"?j=D:typeof D=="string"&&(j=D==="true"||D==="True"||D==="1"||D==="yes"||D==="Yes"||D==="on"||D==="checked"),R.checked=j,R.dispatchEvent(new Event("change",{bubbles:!0})),R.dispatchEvent(new Event("input",{bubbles:!0})),console.log("[VFF FieldManager] ✓ Updated checkbox:",B,"→",j,`(from ${typeof D}: ${D})`)}function H(R,D,B){const j=Array.isArray(D)?D:[D];console.log("[VFF FieldManager] 📋 Checkbox group:",B),console.log("  Requested values:",j);const V=[];for(const ue of R)V.push(ue.value||X(ue));console.log("  Available checkboxes:",V);const q=[],ne=[],ye=new Map;for(const ue of j)ye.set(String(ue),!1);for(const ue of R){const Ce=ue.value||X(ue);let Ae=null;const Ne=j.some(ht=>{const Qe=String(ht);if(Ce===Qe||Ce.toLowerCase()===Qe.toLowerCase())return Ae=Qe,!0;const ve=Fe=>Fe.toLowerCase().replace(/[\/\-_,]/g," ").replace(/\s+/g," ").trim(),Ee=ve(Ce),Ue=ve(Qe);return Ee===Ue||Ee.includes(Ue)||Ue.includes(Ee)?(Ae=Qe,!0):!1});Ne&&Ae&&(ye.set(Ae,!0),q.push(Ce)),ue.checked=Ne,Ne&&(ue.setAttribute("data-vff-confirmed","true"),f.add(B),G(ue),w(ue,B)),ue.dispatchEvent(new Event("change",{bubbles:!0})),ue.dispatchEvent(new Event("input",{bubbles:!0}))}for(const[ue,Ce]of ye.entries())Ce||ne.push(ue);console.log("[VFF FieldManager] ✅ Checkbox group result:",{fieldId:B,requested:j.length,matched:q.length,unmatched:ne.length,total:R.length}),q.length>0&&console.log("  ✓ Matched & checked:",q),ne.length>0&&(console.warn("  ⚠️ Could not match:",ne),console.warn("  💡 Try one of:",V))}function X(R){const D=document.querySelector(`label[for="${R.id}"]`);if(D)return D.textContent?.trim()||"";const B=R.closest("label");if(B){const V=B.cloneNode(!0),q=V.querySelector("input");return q&&q.remove(),V.textContent?.trim()||""}const j=R.nextSibling;return j&&j.nodeType===Node.TEXT_NODE?j.textContent?.trim()||"":R.value}function J(R,D,B){let j=!1;for(const V of R)if(V.value===D){V.checked=!0,j=!0,V.dispatchEvent(new Event("change",{bubbles:!0})),V.dispatchEvent(new Event("input",{bubbles:!0})),V.setAttribute("data-vff-confirmed","true"),f.add(B),G(V),w(V,B),console.log("[VFF FieldManager] ✓ Selected radio:",B,"→",D);break}if(!j){const V=D.toLowerCase();for(const q of R){const ne=q.value.toLowerCase();if(ne.includes(V)||V.includes(ne)){q.checked=!0,j=!0,q.dispatchEvent(new Event("change",{bubbles:!0})),q.dispatchEvent(new Event("input",{bubbles:!0})),q.setAttribute("data-vff-confirmed","true"),f.add(B),G(q),w(q,B),console.log("[VFF FieldManager] ≈ Fuzzy match radio:",B,"→",q.value);break}}}j||console.warn("[VFF FieldManager] ⚠️ No matching radio option found for:",D,"in",B)}function P(R,D,B){R.value===D?(R.checked=!0,R.dispatchEvent(new Event("change",{bubbles:!0})),R.dispatchEvent(new Event("input",{bubbles:!0})),console.log("[VFF FieldManager] ✓ Selected single radio:",B)):console.warn("[VFF FieldManager] ⚠️ Radio value mismatch:",R.value,"!==",D)}function Q(R,D,B){console.warn("[VFF FieldManager] ⚠️ Combobox filling not fully supported yet:",B),console.log("[VFF FieldManager] Combobox should be filled with:",D),R.setAttribute("aria-valuenow",D),R.setAttribute("data-vff-value",D),R.click()}function G(R){if(R.style.outline="2px solid #10b981",R.style.outlineOffset="2px",R.parentElement?.querySelector(".vff-field-badge"))return;const B=document.createElement("span");B.className="vff-field-badge",B.textContent="✓",B.style.cssText=`
			position: absolute;
			top: 50%;
			right: 8px;
			transform: translateY(-50%);
			color: #10b981;
			font-weight: bold;
			font-size: 18px;
			pointer-events: none;
			z-index: 1000;
		`;const j=R.parentElement;j&&getComputedStyle(j).position==="static"&&(j.style.position="relative"),R.parentElement?.appendChild(B)}function ee(){console.log("[VFF FieldManager] Destroying, cleaning up",b.size,"listeners");for(const[R,D]of b.entries())R.removeEventListener("blur",D),R.removeEventListener("change",D);document.querySelectorAll("[data-vff-confirmed]").forEach(R=>{R.removeAttribute("data-vff-confirmed"),R.style.outline="",R.style.outlineOffset=""}),document.querySelectorAll(".vff-field-badge").forEach(R=>{R.remove()}),b.clear(),f.clear(),v.clear()}return{applyUpdates:C,destroy:ee}}const Qi=16e3,Br=24e3;function Wc(S){const f={recordingContext:null,playbackContext:null,stream:S||null,workletNode:null,source:null};let b=!1,v=0,k=0,w=null,I=!1,A=!1;const Z=Math.ceil(700/1e3*Qi),W=[];let H=0;const X=[];let J=!1,P=!1,Q=!1;async function G(ve){if(!b)try{f.stream?console.log("[AudioManager] 🔗 Reusing existing microphone stream (shared with VAD)"):(f.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,sampleRate:Qi,echoCancellation:!0,noiseSuppression:!0,autoGainControl:!0}}),console.log("[AudioManager] 🎤 Created new microphone stream")),f.recordingContext?(console.log("[AudioManager] ♻️ Reusing existing recording AudioContext"),f.recordingContext.state==="suspended"&&await f.recordingContext.resume()):(console.log("[AudioManager] 🎵 Creating AudioContext for recording (first time)"),f.recordingContext=new AudioContext({sampleRate:Qi})),f.source=f.recordingContext.createMediaStreamSource(f.stream),f.playbackContext?(console.log("[AudioManager] ♻️ Reusing existing playback AudioContext"),f.playbackContext.state==="suspended"&&await f.playbackContext.resume()):(console.log("[AudioManager] 🎵 Creating AudioContext for playback (eager initialization)"),f.playbackContext=new AudioContext({sampleRate:Br}),v=0);const Ue=!window.location.hostname.includes("localhost")&&!window.location.hostname.includes("127.0.0.1")?new URL("../shared/audio-processor.worklet.js",window.location.href).href:"/shared/audio-processor.worklet.js";console.log("[VFF Audio] Loading worklet from:",Ue),await f.recordingContext.audioWorklet.addModule(Ue),f.workletNode=new AudioWorkletNode(f.recordingContext,"voice-form-filler-audio-processor"),w=ve,f.workletNode.port.onmessage=Fe=>{if(!b||!w)return;const{type:Me,pcmData:ze}=Fe.data;if(Me!=="audio")return;const Ye=new Int16Array(ze);for(W.push(Ye),H+=Ye.length;H>Z;){const tt=W.shift();tt&&(H-=tt.length)}if(I){const tt=new Int16Array(Ye.length);w(tt.buffer)}else A&&w(ze)},f.source.connect(f.workletNode),f.workletNode.connect(f.recordingContext.destination),b=!0}catch(Ee){throw console.error("[VFF Audio] Failed to start recording:",Ee),ye(),Ee}}function ee(){if(b){if(b=!1,w=null,f.workletNode){try{f.workletNode.disconnect(),f.workletNode.port.close()}catch{}f.workletNode=null}if(f.source){try{f.source.disconnect()}catch{}f.source=null}if(f.recordingContext){try{f.recordingContext.close()}catch{}f.recordingContext=null}f.stream&&(f.stream.getTracks().forEach(ve=>ve.stop()),f.stream=null)}}async function R(ve){try{if(k||(k=0),k++,k===1&&console.log(`[AudioManager] 🔊 Playing first audio chunk (${ve.byteLength} bytes)`),J){console.log(`[AudioManager] 🚫 Discarding chunk #${k} (barge-in active)`);return}f.playbackContext||(console.log("[AudioManager] 🎵 Creating AudioContext for playback (lazy fallback)"),f.playbackContext=new AudioContext({sampleRate:Br}),v=0);const Ee=f.playbackContext;Ee.state==="suspended"&&(console.log("[AudioManager] ⏸️ Resuming suspended AudioContext"),await Ee.resume());const Ue=D(ve),Fe=new Int16Array(Ue);if(Fe.length===0){console.warn(`[AudioManager] ⚠️ Chunk #${k} decoded to 0 samples`);return}const Me=new Float32Array(Fe.length);for(let it=0;it<Fe.length;it++)Me[it]=Fe[it]/32768;const ze=Ee.createBuffer(1,Me.length,Br);ze.getChannelData(0).set(Me);const Ye=Ee.currentTime,tt=Math.max(v,Ye+.01),ct=Ee.createBufferSource();ct.buffer=ze,ct.connect(Ee.destination),ct.start(tt),X.push(ct);const st=!Q;Q=!0,st&&window.vffOnAudioPlaybackStart&&window.vffOnAudioPlaybackStart(),v=tt+ze.duration,ct.onended=()=>{v<Ee.currentTime&&(v=Ee.currentTime);const it=X.indexOf(ct);it>-1&&X.splice(it,1),X.length===0&&(Q=!1,!P&&window.vffOnAudioPlaybackEnd&&window.vffOnAudioPlaybackEnd())}}catch(Ee){Q=!1,console.error("[VFF Audio] Playback failed:",Ee)}}function D(ve){try{const Ee=new TextDecoder().decode(ve);if(Ee.match(/^[A-Za-z0-9+/]+=*$/)){const Ue=atob(Ee),Fe=new Uint8Array(Ue.length);for(let Me=0;Me<Ue.length;Me++)Fe[Me]=Ue.charCodeAt(Me);return Fe.buffer}}catch{}return ve}function B(){J=!0,P=!0,X.forEach(ve=>{try{ve.stop(),ve.disconnect()}catch{}}),X.length=0,f.playbackContext&&(v=f.playbackContext.currentTime),Q=!1,P=!1}function j(){J=!1}async function V(){if(f.playbackContext&&f.playbackContext.state==="running")try{await f.playbackContext.suspend(),console.log("[AudioManager] 🔇 Audio context paused (tentative barge-in)")}catch(ve){console.error("[AudioManager] Failed to pause audio context:",ve)}}async function q(){if(f.playbackContext&&f.playbackContext.state==="suspended")try{await f.playbackContext.resume(),console.log("[AudioManager] 🔊 Audio context resumed (false positive)")}catch(ve){console.error("[AudioManager] Failed to resume audio context:",ve)}}function ne(){return b}function ye(){if(ee(),f.playbackContext){try{f.playbackContext.close()}catch{}f.playbackContext=null}v=0}function ue(){ye()}function Ce(){return Q}function Ae(){console.log("[AudioManager] Muting input - sending silence"),I=!0}function Ne(){console.log("[AudioManager] Unmuting input - sending real audio"),I=!1}function ht(){return f.stream}function Qe(ve){const Ee=A;if(A=ve,ve&&!Ee&&w){console.log(`[AudioManager] VAD activated - flushing ${H} samples (${(H/Qi*1e3).toFixed(0)}ms) from pre-buffer`);for(const Ue of W){const Fe=new ArrayBuffer(Ue.byteLength);new Int16Array(Fe).set(Ue),w(Fe)}console.log("[AudioManager] Pre-buffer flushed, now sending live audio")}else!ve&&Ee&&console.log("[AudioManager] VAD deactivated - sending silence")}return{startRecording:G,stopRecording:ee,playAudio:R,flushAudioQueue:B,resumePlayback:j,pauseAudioContext:V,resumeAudioContext:q,isRecording:ne,isSpeaking:Ce,muteInput:Ae,unmuteInput:Ne,getStream:ht,setVADActive:Qe,destroy:ue}}function Ur(){const S=window.__VFF_LOCAL_DEV,f=window.__VFF_BACKEND_URL,b=window.__VFF_DEBUG_METRICS;return{enabled:!!S,backendUrl:f||"ws://localhost:8000/ws/fill",debugMetrics:!!b||!!S}}function Of(){const S=Ur();return S.enabled?(console.log("[VFF Config] 🔧 LOCAL DEV MODE ENABLED"),console.log("[VFF Config] Backend URL:",S.backendUrl),console.log("[VFF Config] Debug Metrics:",S.debugMetrics),S.backendUrl):"ws://localhost:8000/ws/fill"}function Rf(){return"wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill"}function Mf(){return Ur().debugMetrics}function Df(){console.log(`
`+"=".repeat(60)),console.log("🔧 VOICE FORM FILLER - LOCAL DEVELOPMENT MODE"),console.log("=".repeat(60)),console.log(`
To test locally without deploying:`),console.log(`
1. Start backend:`),console.log("   cd backend"),console.log("   source venv/bin/activate  # or venv\\Scripts\\activate on Windows"),console.log("   uvicorn main:app --reload --port 8000"),console.log(`
2. Enable local dev in browser console:`),console.log("   window.__VFF_LOCAL_DEV = true"),console.log(`
3. Load bookmarklet (will connect to localhost:8000)`),console.log(`
4. Test VAD tuning changes:`),console.log("   - Edit backend/adapters/live_ai_gemini.py"),console.log("   - Backend auto-reloads (--reload flag)"),console.log("   - Reconnect bookmarklet to test"),console.log(`
Optional environment variables:`),console.log('   window.__VFF_BACKEND_URL = "ws://localhost:8000/ws/fill"  // Custom URL'),console.log("   window.__VFF_DEBUG_METRICS = true                          // Extra logging"),console.log(`
`+"=".repeat(60)+`
`)}typeof window<"u"&&Ur().enabled&&Df();class Bf{constructor(){Ke(this,"sessionMetrics",null);Ke(this,"currentBargeIn",null);Ke(this,"lastBargeInTime",0);Ke(this,"BARGE_IN_GRACE_PERIOD_MS",150);Ke(this,"debugEnabled",!1)}startSession(f){this.debugEnabled=Mf(),this.sessionMetrics={sessionId:f,sessionStart:Date.now(),bargeIns:[],toolCalls:[],falseStarts:0,successfulBargeIns:0,timedOutBargeIns:0,hallucinatedToolCalls:0},this.currentBargeIn=null,this.lastBargeInTime=0,this.debugEnabled&&console.log("[VFF Metrics] 📊 Session started:",f,"(Debug mode: ON)")}recordMicActivity(){if(!this.sessionMetrics)return;const f=performance.now();this.currentBargeIn={timestamp:Date.now(),micActivityDetected:f,result:"pending"},console.log("[VFF Metrics] 🎤 Mic activity detected")}recordTTSPaused(){if(!this.sessionMetrics||!this.currentBargeIn)return;const f=performance.now();this.currentBargeIn.ttsPausedAt=f,this.currentBargeIn.bargeInLatency=f-this.currentBargeIn.micActivityDetected,console.log(`[VFF Metrics] 🔇 TTS paused - Barge-in latency: ${this.currentBargeIn.bargeInLatency.toFixed(1)}ms`,this.currentBargeIn.bargeInLatency<180?"✅":"⚠️ SLOW")}recordCancelSent(){if(!this.sessionMetrics||!this.currentBargeIn)return;const f=performance.now();this.currentBargeIn.cancelSentAt=f,console.log("[VFF Metrics] 📤 Cancel message sent to backend")}recordGeminiAck(){if(!this.sessionMetrics||!this.currentBargeIn)return;const f=performance.now();this.currentBargeIn.geminiAckAt=f,this.currentBargeIn.cancelSentAt&&(this.currentBargeIn.cancelAckLatency=f-this.currentBargeIn.cancelSentAt,console.log(`[VFF Metrics] ✅ Gemini acknowledged - Cancel latency: ${this.currentBargeIn.cancelAckLatency.toFixed(1)}ms`,this.currentBargeIn.cancelAckLatency<150?"✅":"⚠️ SLOW")),this.currentBargeIn.result="success",this.sessionMetrics.successfulBargeIns++,this.lastBargeInTime=f,this.sessionMetrics.bargeIns.push(this.currentBargeIn),this.currentBargeIn=null}recordBargeInTimeout(){!this.sessionMetrics||!this.currentBargeIn||(console.warn("[VFF Metrics] ⏱️ Barge-in timeout - Gemini did not acknowledge"),this.currentBargeIn.result="timeout",this.sessionMetrics.timedOutBargeIns++,this.sessionMetrics.bargeIns.push(this.currentBargeIn),this.currentBargeIn=null)}recordFalseStart(){!this.sessionMetrics||!this.currentBargeIn||(console.log("[VFF Metrics] 🔄 False start detected"),this.currentBargeIn.result="false_start",this.sessionMetrics.falseStarts++,this.sessionMetrics.bargeIns.push(this.currentBargeIn),this.currentBargeIn=null)}checkFalseStart(f,b){return b&&f?(console.warn("[VFF Metrics] ⚠️ FALSE START: Gemini speaking while user mic active!"),this.recordFalseStart(),!0):!1}recordToolCall(f,b){if(!this.sessionMetrics)return"accept";const v=performance.now(),k=v-this.lastBargeInTime,w=k<this.BARGE_IN_GRACE_PERIOD_MS,I={timestamp:Date.now(),toolName:f,callId:b,receivedAt:v,bargeInWindowActive:w,decision:"accepted"};return w?(I.decision="rejected_barge_in",I.rejectionReason=`Received ${k.toFixed(1)}ms after barge-in (< ${this.BARGE_IN_GRACE_PERIOD_MS}ms threshold)`,this.sessionMetrics.hallucinatedToolCalls++,this.sessionMetrics.toolCalls.push(I),console.warn("[VFF Metrics] 🚫 Tool call REJECTED (hallucination):",`${f} [${b.slice(0,8)}]`,`- ${I.rejectionReason}`),"reject"):(this.sessionMetrics.toolCalls.push(I),console.log("[VFF Metrics] ✅ Tool call ACCEPTED:",`${f} [${b.slice(0,8)}]`,`- ${k.toFixed(0)}ms after last barge-in`),"accept")}getStats(){if(!this.sessionMetrics)return null;const f=this.sessionMetrics.bargeIns,b=f.filter(C=>C.bargeInLatency!==void 0).map(C=>C.bargeInLatency),v=f.filter(C=>C.cancelAckLatency!==void 0).map(C=>C.cancelAckLatency),k=C=>C.length?C.reduce((Z,W)=>Z+W,0)/C.length:0,w=C=>{if(!C.length)return 0;const Z=[...C].sort((H,X)=>H-X),W=Math.floor(Z.length*.95);return Z[W]},I=f.length,A=this.sessionMetrics.toolCalls.length;return{totalBargeIns:I,successfulBargeIns:this.sessionMetrics.successfulBargeIns,timedOutBargeIns:this.sessionMetrics.timedOutBargeIns,falseStarts:this.sessionMetrics.falseStarts,avgBargeInLatency:k(b),p95BargeInLatency:w(b),avgCancelAckLatency:k(v),p95CancelAckLatency:w(v),totalToolCalls:A,hallucinatedToolCalls:this.sessionMetrics.hallucinatedToolCalls,toolCallHallucinationRate:A?this.sessionMetrics.hallucinatedToolCalls/A*100:0,falseStartRate:I?this.sessionMetrics.falseStarts/I*100:0}}printSummary(){const f=this.getStats();if(!f){console.log("[VFF Metrics] No session data");return}console.log(`
`+"=".repeat(60)),console.log("📊 VAD TUNING METRICS SUMMARY"),console.log("=".repeat(60)),console.log(`
🎤 BARGE-IN PERFORMANCE:`),console.log(`   Total Barge-Ins: ${f.totalBargeIns}`),console.log(`   Successful: ${f.successfulBargeIns} (${(f.successfulBargeIns/f.totalBargeIns*100).toFixed(1)}%)`),console.log(`   Timeouts: ${f.timedOutBargeIns}`),console.log(`   False Starts: ${f.falseStarts} (${f.falseStartRate.toFixed(1)}%)`),console.log(`   Avg Latency: ${f.avgBargeInLatency.toFixed(1)}ms ${f.avgBargeInLatency<180?"✅":"⚠️"}`),console.log(`   P95 Latency: ${f.p95BargeInLatency.toFixed(1)}ms ${f.p95BargeInLatency<180?"✅ TARGET MET":"❌ EXCEEDS TARGET"}`),console.log(`
🔄 CANCEL ACKNOWLEDGMENT:`),console.log(`   Avg Latency: ${f.avgCancelAckLatency.toFixed(1)}ms ${f.avgCancelAckLatency<150?"✅":"⚠️"}`),console.log(`   P95 Latency: ${f.p95CancelAckLatency.toFixed(1)}ms ${f.p95CancelAckLatency<150?"✅ TARGET MET":"❌ EXCEEDS TARGET"}`),console.log(`
🛠️ TOOL CALL SAFETY:`),console.log(`   Total Tool Calls: ${f.totalToolCalls}`),console.log(`   Hallucinated (rejected): ${f.hallucinatedToolCalls}`),console.log(`   Hallucination Rate: ${f.toolCallHallucinationRate.toFixed(1)}% ${f.toolCallHallucinationRate<1?"✅ EXCELLENT":f.toolCallHallucinationRate<5?"⚠️ ACCEPTABLE":"❌ TOO HIGH"}`),console.log(`
`+"=".repeat(60)+`
`)}endSession(){this.sessionMetrics&&(console.log("[VFF Metrics] 📊 Session ended:",this.sessionMetrics.sessionId),this.printSummary(),this.sessionMetrics=null,this.currentBargeIn=null,this.lastBargeInTime=0)}exportData(){return this.sessionMetrics?{...this.sessionMetrics}:null}}const Jt=new Bf;typeof window<"u"&&(window.__VFF_METRICS__=Jt);function Ff(S,f){console.log("[VFF Connection] 🔄 Restoring DOM from sessionStorage...");let b=0;for(const[v,k]of Object.entries(S.current_values)){const w=k.value;if(w==null||w==="")continue;let I=document.getElementById(v);if(!I){const A=document.querySelectorAll(`input[name="${v}"], textarea[name="${v}"], select[name="${v}"]`);A.length>0&&(I=A[0])}if(I){if(I.tagName==="SELECT")I.value=String(w);else if(I.tagName==="INPUT"){const A=I;A.type==="checkbox"?A.checked=!!w:A.value=String(w)}else I.tagName==="TEXTAREA"&&(I.value=String(w));b++}}console.log(`[VFF Connection] ✅ Restored ${b} fields from sessionStorage to DOM`)}function Gc(S,f){console.log("[VFF Connection] 🔍 Scanning DOM for pre-filled values...");let b=0;for(const v of f.fields){const k=v.id;let w=document.getElementById(k);if(!w){const A=document.querySelectorAll(`input[name="${k}"], textarea[name="${k}"], select[name="${k}"]`);A.length>0&&(w=A[0])}if(!w)continue;let I=null;if(w.tagName==="SELECT")I=w.value||null;else if(w.tagName==="INPUT"){const A=w;A.type==="checkbox"?I=A.checked:A.type==="radio"?A.checked&&(I=A.value):I=A.value||null}else w.tagName==="TEXTAREA"&&(I=w.value||null);I!==null&&I!==""&&I!==!1&&(S.updateField(k,I,{confirmed:!0,emit:!1}),b++,console.log("[VFF Connection] ✓ Captured pre-filled:",k,"=",I))}console.log(`[VFF Connection] ✅ Captured ${b} pre-filled values from DOM`)}function qr(S,f,b="English",v){const k=Nf();let w=null,I=null,A=null,C=b,Z=!1,W=k,H=!1;const X=_e.init(S);Ff(X),A=Wc(v),v&&console.log("[VFF Connection] 🔗 Audio manager using shared stream (VAD coordination)"),I=qc({schema:S,onManualEdit:(P,Q)=>{console.log("[VFF Connection] 🖊️ Manual edit detected:",P,"=",Q);const G=_e.updateFieldValue(X,P,Q,{confirmed:!0});if(Object.assign(X,G),console.log("[VFF Connection] ✓ Updated sessionStorage for:",P),w){const R=S.fields.find(D=>D.id===P)?.name||P;w.sendManualFieldUpdate(P,R,Q),console.log("[VFF Connection] ✓ Notified Gemini about:",P)}}}),console.log("[VFF Connection] ✅ Field manager created - listening for manual edits");const J={onStatusChange:P=>{f(P)},onSessionReady:P=>{f("connected"),Jt.startSession(P)},onSessionRestarted:()=>{console.log("[VFF Connection] ✅ Gemini session restarted - updating status"),f("connected")},onFieldUpdate:P=>{console.log("[VFF Connection] 📥 Tool call received: update_form_fields with",P.length,"field(s)"),P.forEach((ee,R)=>{console.log(`  [${R+1}] fieldId:`,ee.fieldId,"→ value:",ee.value)});const Q=[],G=[];for(const ee of P){const R=`field_${ee.fieldId}_${Date.now()}`;if(Jt.recordToolCall("update_form_fields",R)==="reject"){G.push(ee);continue}Q.push(ee)}G.length>0&&console.warn("[VFF Connection] ⚠️ Rejected",G.length,"hallucinated update(s):",G.map(ee=>ee.fieldId)),console.log("[VFF Connection] ✅ Accepted",Q.length,"update(s) for processing"),I&&Q.length>0&&I.applyUpdates(Q)},onAudioData:async P=>{A&&await A.playAudio(P)},onError:P=>{console.error("[VFF Connection] Error:",P),f("error")}};return{async connect(){if(w&&w.getStatus()==="connected"&&w){console.log("[VFF Connection] 🔄 WebSocket alive - restarting Gemini session");const Q=w.getNextFieldHint();try{f("reconnecting"),w.send({type:"restart_gemini_session",next_field_hint:Q}),console.log("[VFF Connection] ⏳ Gemini session restart requested",{nextFieldHint:Q});return}catch(G){console.error("[VFF Connection] Failed to restart Gemini:",G),f("disconnected")}}try{console.log("[VFF Connection] Attempting to connect to:",k),f("connecting"),A||(console.log("[VFF Connection] 🔄 Reinitializing audio manager (reconnect)"),A=Wc(v)),I||(console.log("[VFF Connection] 🔄 Reinitializing field manager (reconnect)"),I=qc({schema:S,onManualEdit:(Q,G)=>{console.log("[VFF Connection] 🖊️ Manual edit detected:",Q,"=",G);const ee=_e.updateFieldValue(X,Q,G,{confirmed:!0});if(Object.assign(X,ee),console.log("[VFF Connection] ✓ Updated sessionStorage for:",Q),w){const D=S.fields.find(B=>B.id===Q)?.name||Q;w.sendManualFieldUpdate(Q,D,G),console.log("[VFF Connection] ✓ Notified Gemini about:",Q)}}})),w||(w=new Uc(S,J,C)),Gc(w,S);try{console.log("[VFF Connection] Trying localhost..."),await w.connect(k),W=k,console.log("[VFF Connection] ✅ Connected to localhost")}catch(Q){const G=Rf();console.log("[VFF Connection] Localhost failed, trying cloud:",G),console.log("[VFF Connection] Local error was:",Q),w.disconnect(),w=new Uc(S,J,C),Gc(w,S),await w.connect(G),W=G,console.log("[VFF Connection] ✅ Connected to cloud")}}catch(Q){throw console.error("[VFF Connection] Connection failed:",Q),console.error("[VFF Connection] Error details:",{message:Q instanceof Error?Q.message:String(Q),stack:Q instanceof Error?Q.stack:void 0,wsUrl:k}),f("error"),Q}},pause(){console.log("[VFF Connection] Pausing (keeping connection warm)..."),Z=!0,A?.isRecording()&&A.stopRecording(),A&&A.flushAudioQueue(),f("paused")},async resume(){if(console.log("[VFF Connection] Resuming..."),!w||w.getStatus()!=="connected"){console.error("[VFF Connection] Cannot resume - not connected"),f("error");return}Z=!1,f("connected"),A&&!A.isRecording()&&await this.startRecording(),console.log("[VFF Connection] Resumed successfully")},disconnect(){Jt.endSession(),w&&(w.disconnect(),w=null),I&&(I.destroy(),I=null),A&&(A.destroy(),A=null),f("disconnected")},getStatus(){return w?.getStatus()??"disconnected"},sendAudio(P){w&&w.sendAudio(P)},sendActivityStart(){w&&w.sendActivityStart()},sendActivityEnd(){w&&w.sendActivityEnd()},sendPrompt(P){w&&w.sendPrompt(P)},sendRecoveryPrompt(P,Q){w&&w.sendRecoveryPrompt(P,Q)},endGeminiSession(){w&&w.endGeminiSession()},setPushToTalkMode(P){console.log(`[VFF Connection] Setting push-to-talk mode: ${P}`),H=P},getFieldManager(){return I},getAudioManager(){return A},async startRecording(){if(console.log("[VFF Connection] startRecording called"),!A){console.error("[VFF Connection] Audio manager not initialized");return}console.log("[VFF Connection] Requesting microphone access..."),await A.startRecording(P=>{w&&w.getStatus()==="connected"&&w.sendAudio(P)})},stopRecording(){A&&A.stopRecording()},isRecording(){return A?.isRecording()??!1},isPaused(){return Z},async changeFillLanguage(P){C=P,w&&w.getStatus()==="connected"?await w.changeFillLanguage(P):console.log("[VFF Connection] Language preference saved, will be used on next connect")},changeSpokenLanguage(P,Q){w&&w.getStatus()==="connected"?(w.send({type:"change_spoken_language",spoken_language:P,next_field_hint:Q}),console.log("[VFF Connection] ✓ Sent spoken language change to backend:",P)):console.warn("[VFF Connection] Cannot change spoken language - not connected")},async startSection(P){if(!w)throw new Error("Connection not initialized");A?.isRecording()&&A.stopRecording(),await w.startSection(P,k),!Z&&A&&await A.startRecording(Q=>{w&&w.sendAudio(Q)})},async switchSection(P){if(!w)throw new Error("Connection not initialized");A?.isRecording()&&A.stopRecording(),await w.switchSection(P,W),!Z&&A&&await A.startRecording(Q=>{w&&w.sendAudio(Q)})},async completeSection(){if(!w)throw new Error("Connection not initialized");await w.completeSection(k)},getCurrentSection(){return w?.getCurrentSection()},getCompletedSections(){return w?.getCompletedSections()||new Set},onVADSpeechStart(){if(!A||H)return;w&&w.sendActivityStart(),A.isSpeaking()&&(console.log("[VFF Connection] 🎤 VAD detected speech - flushing audio queue"),Jt.recordMicActivity(),A.flushAudioQueue(),Jt.recordTTSPaused(),Jt.recordCancelSent())},onVADSpeechEnd(){if(!A||H)return;A.isSpeaking()||(A.resumePlayback(),A.resumeAudioContext()),w&&w.sendActivityEnd(),console.log("[VFF Connection] 🎤 VAD speech ended - sent activity_end, audio playback resumed")}}}function Nf(){return Of()}var Jc={},Pr={},Ti={};Object.defineProperty(Ti,"__esModule",{value:!0});Ti.baseAssetPath=void 0;const Pf=typeof window<"u"&&typeof window.document<"u",jc=Pf?window.document.currentScript:null;let ep="/";jc&&(ep=jc.src.replace(/#.*$/,"").replace(/\?.*$/,"").replace(/\/[^\/]+$/,"/"));Ti.baseAssetPath=ep;var oi={};Object.defineProperty(oi,"__esModule",{value:!0});oi.defaultModelFetcher=void 0;const Vf=S=>fetch(S).then(f=>f.arrayBuffer());oi.defaultModelFetcher=Vf;var It={},li={};(function(S){Object.defineProperty(S,"__esModule",{value:!0}),S.log=S.LOG_PREFIX=void 0,S.LOG_PREFIX="[VAD]";const f=["error","debug","warn"];function b(k){return(...w)=>{console[k](S.LOG_PREFIX,...w)}}const v=f.reduce((k,w)=>(k[w]=b(w),k),{});S.log=v})(li);var ei={};Object.defineProperty(ei,"__esModule",{value:!0});ei.Message=void 0;var Hc;(function(S){S.AudioFrame="AUDIO_FRAME",S.SpeechStart="SPEECH_START",S.VADMisfire="VAD_MISFIRE",S.SpeechEnd="SPEECH_END",S.SpeechStop="SPEECH_STOP",S.SpeechRealStart="SPEECH_REAL_START",S.FrameProcessed="FRAME_PROCESSED"})(Hc||(ei.Message=Hc={}));Object.defineProperty(It,"__esModule",{value:!0});It.FrameProcessor=It.validateOptions=It.defaultFrameProcessorOptions=void 0;const Si=li,Yt=ei;It.defaultFrameProcessorOptions={positiveSpeechThreshold:.3,negativeSpeechThreshold:.25,preSpeechPadMs:800,redemptionMs:1400,minSpeechMs:400,submitUserSpeechOnPause:!1};function Lf(S){(S.positiveSpeechThreshold<0||S.positiveSpeechThreshold>1)&&Si.log.error("positiveSpeechThreshold should be a number between 0 and 1"),(S.negativeSpeechThreshold<0||S.negativeSpeechThreshold>S.positiveSpeechThreshold)&&Si.log.error("negativeSpeechThreshold should be between 0 and positiveSpeechThreshold"),S.preSpeechPadMs<0&&Si.log.error("preSpeechPadMs should be positive"),S.redemptionMs<0&&Si.log.error("redemptionMs should be positive"),S.minSpeechMs<0&&Si.log.error("minSpeechMs should be positive")}It.validateOptions=Lf;const Kc=S=>{const f=S.reduce((v,k)=>(v.push(v.at(-1)+k.length),v),[0]),b=new Float32Array(f.at(-1));return S.forEach((v,k)=>{const w=f[k];b.set(v,w)}),b};class Uf{constructor(f,b,v,k){this.modelProcessFunc=f,this.modelResetFunc=b,this.options=v,this.msPerFrame=k,this.speaking=!1,this.redemptionCounter=0,this.speechFrameCount=0,this.active=!1,this.speechRealStartFired=!1,this.reset=()=>{this.speaking=!1,this.speechRealStartFired=!1,this.audioBuffer=[],this.modelResetFunc(),this.redemptionCounter=0,this.speechFrameCount=0},this.pause=w=>{this.active=!1,this.options.submitUserSpeechOnPause?this.endSegment(w):this.reset()},this.resume=()=>{this.active=!0},this.endSegment=w=>{const I=this.audioBuffer;this.audioBuffer=[];const A=this.speaking;if(this.reset(),A)if(I.reduce((Z,W)=>W.isSpeech?Z+1:Z,0)>=this.minSpeechFrames){const Z=Kc(I.map(W=>W.frame));w({msg:Yt.Message.SpeechEnd,audio:Z})}else w({msg:Yt.Message.VADMisfire});return{}},this.process=async(w,I)=>{if(!this.active)return;const A=await this.modelProcessFunc(w),C=A.isSpeech>=this.options.positiveSpeechThreshold;if(I({probs:A,msg:Yt.Message.FrameProcessed,frame:w}),this.audioBuffer.push({frame:w,isSpeech:C}),C&&(this.speechFrameCount++,this.redemptionCounter=0),C&&!this.speaking&&(this.speaking=!0,I({msg:Yt.Message.SpeechStart})),this.speaking&&this.speechFrameCount===this.minSpeechFrames&&!this.speechRealStartFired&&(this.speechRealStartFired=!0,I({msg:Yt.Message.SpeechRealStart})),A.isSpeech<this.options.negativeSpeechThreshold&&this.speaking&&++this.redemptionCounter>=this.redemptionFrames){this.redemptionCounter=0,this.speechFrameCount=0,this.speaking=!1,this.speechRealStartFired=!1;const Z=this.audioBuffer;if(this.audioBuffer=[],Z.reduce((H,X)=>X.isSpeech?H+1:H,0)>=this.minSpeechFrames){const H=Kc(Z.map(X=>X.frame));I({msg:Yt.Message.SpeechEnd,audio:H})}else I({msg:Yt.Message.VADMisfire})}if(!this.speaking){for(;this.audioBuffer.length>this.preSpeechPadFrames;)this.audioBuffer.shift();this.speechFrameCount=0}},this.audioBuffer=[],this.redemptionFrames=Math.floor(v.redemptionMs/this.msPerFrame),this.preSpeechPadFrames=Math.floor(v.preSpeechPadMs/this.msPerFrame),this.minSpeechFrames=Math.floor(v.minSpeechMs/this.msPerFrame),this.reset()}}It.FrameProcessor=Uf;var tp={};function ai(S){throw new Error('Could not dynamically require "'+S+'". Please configure the dynamicRequireTargets or/and ignoreDynamicRequires option of @rollup/plugin-commonjs appropriately for this require call to work.')}var ip={exports:{}};/*!
 * ONNX Runtime Web v1.23.0
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License.
 */(function(S,f){var b=(()=>{var v=Object.defineProperty,k=Object.getOwnPropertyDescriptor,w=Object.getOwnPropertyNames,I=Object.prototype.hasOwnProperty,A=(e=>typeof ai<"u"?ai:typeof Proxy<"u"?new Proxy(e,{get:(t,i)=>(typeof ai<"u"?ai:t)[i]}):e)(function(e){if(typeof ai<"u")return ai.apply(this,arguments);throw Error('Dynamic require of "'+e+'" is not supported')}),C=(e,t)=>()=>(e&&(t=e(e=0)),t),Z=(e,t)=>{for(var i in t)v(e,i,{get:t[i],enumerable:!0})},W=(e,t,i,n)=>{if(t&&typeof t=="object"||typeof t=="function")for(let r of w(t))!I.call(e,r)&&r!==i&&v(e,r,{get:()=>t[r],enumerable:!(n=k(t,r))||n.enumerable});return e},H=e=>W(v({},"__esModule",{value:!0}),e),X,J,P,Q,G,ee=C(()=>{X=new Map,J=[],P=(e,t,i)=>{if(t&&typeof t.init=="function"&&typeof t.createInferenceSessionHandler=="function"){let n=X.get(e);if(n===void 0)X.set(e,{backend:t,priority:i});else{if(n.priority>i)return;if(n.priority===i&&n.backend!==t)throw new Error(`cannot register backend "${e}" using priority ${i}`)}if(i>=0){let r=J.indexOf(e);r!==-1&&J.splice(r,1);for(let s=0;s<J.length;s++)if(X.get(J[s]).priority<=i){J.splice(s,0,e);return}J.push(e)}return}throw new TypeError("not a valid backend")},Q=async e=>{let t=X.get(e);if(!t)return"backend not found.";if(t.initialized)return t.backend;if(t.aborted)return t.error;{let i=!!t.initPromise;try{return i||(t.initPromise=t.backend.init(e)),await t.initPromise,t.initialized=!0,t.backend}catch(n){return i||(t.error=`${n}`,t.aborted=!0),t.error}finally{delete t.initPromise}}},G=async e=>{let t=e.executionProviders||[],i=t.map(l=>typeof l=="string"?l:l.name),n=i.length===0?J:i,r,s=[],a=new Set;for(let l of n){let u=await Q(l);typeof u=="string"?s.push({name:l,err:u}):(r||(r=u),r===u&&a.add(l))}if(!r)throw new Error(`no available backend found. ERR: ${s.map(l=>`[${l.name}] ${l.err}`).join(", ")}`);for(let{name:l,err:u}of s)i.includes(l)&&console.warn(`removing requested execution provider "${l}" from session options because it is not available: ${u}`);let o=t.filter(l=>a.has(typeof l=="string"?l:l.name));return[r,new Proxy(e,{get:(l,u)=>u==="executionProviders"?o:Reflect.get(l,u)})]}}),R=C(()=>{ee()}),D,B=C(()=>{D="1.23.0"}),j,V,q=C(()=>{B(),j="warning",V={wasm:{},webgl:{},webgpu:{},versions:{common:D},set logLevel(e){if(e!==void 0){if(typeof e!="string"||["verbose","info","warning","error","fatal"].indexOf(e)===-1)throw new Error(`Unsupported logging level: ${e}`);j=e}},get logLevel(){return j}},Object.defineProperty(V,"logLevel",{enumerable:!0})}),ne,ye=C(()=>{q(),ne=V}),ue,Ce,Ae=C(()=>{ue=(e,t)=>{let i=typeof document<"u"?document.createElement("canvas"):new OffscreenCanvas(1,1);i.width=e.dims[3],i.height=e.dims[2];let n=i.getContext("2d");if(n!=null){let r,s;t?.tensorLayout!==void 0&&t.tensorLayout==="NHWC"?(r=e.dims[2],s=e.dims[3]):(r=e.dims[3],s=e.dims[2]);let a=t?.format!==void 0?t.format:"RGB",o=t?.norm,l,u;o===void 0||o.mean===void 0?l=[255,255,255,255]:typeof o.mean=="number"?l=[o.mean,o.mean,o.mean,o.mean]:(l=[o.mean[0],o.mean[1],o.mean[2],0],o.mean[3]!==void 0&&(l[3]=o.mean[3])),o===void 0||o.bias===void 0?u=[0,0,0,0]:typeof o.bias=="number"?u=[o.bias,o.bias,o.bias,o.bias]:(u=[o.bias[0],o.bias[1],o.bias[2],0],o.bias[3]!==void 0&&(u[3]=o.bias[3]));let d=s*r,c=0,p=d,h=d*2,m=-1;a==="RGBA"?(c=0,p=d,h=d*2,m=d*3):a==="RGB"?(c=0,p=d,h=d*2):a==="RBG"&&(c=0,h=d,p=d*2);for(let _=0;_<s;_++)for(let $=0;$<r;$++){let y=(e.data[c++]-u[0])*l[0],g=(e.data[p++]-u[1])*l[1],T=(e.data[h++]-u[2])*l[2],x=m===-1?255:(e.data[m++]-u[3])*l[3];n.fillStyle="rgba("+y+","+g+","+T+","+x+")",n.fillRect($,_,1,1)}if("toDataURL"in i)return i.toDataURL();throw new Error("toDataURL is not supported")}else throw new Error("Can not access image data")},Ce=(e,t)=>{let i=typeof document<"u"?document.createElement("canvas").getContext("2d"):new OffscreenCanvas(1,1).getContext("2d"),n;if(i!=null){let r,s,a;t?.tensorLayout!==void 0&&t.tensorLayout==="NHWC"?(r=e.dims[2],s=e.dims[1],a=e.dims[3]):(r=e.dims[3],s=e.dims[2],a=e.dims[1]);let o=t!==void 0&&t.format!==void 0?t.format:"RGB",l=t?.norm,u,d;l===void 0||l.mean===void 0?u=[255,255,255,255]:typeof l.mean=="number"?u=[l.mean,l.mean,l.mean,l.mean]:(u=[l.mean[0],l.mean[1],l.mean[2],255],l.mean[3]!==void 0&&(u[3]=l.mean[3])),l===void 0||l.bias===void 0?d=[0,0,0,0]:typeof l.bias=="number"?d=[l.bias,l.bias,l.bias,l.bias]:(d=[l.bias[0],l.bias[1],l.bias[2],0],l.bias[3]!==void 0&&(d[3]=l.bias[3]));let c=s*r;if(t!==void 0&&(t.format!==void 0&&a===4&&t.format!=="RGBA"||a===3&&t.format!=="RGB"&&t.format!=="BGR"))throw new Error("Tensor format doesn't match input tensor dims");let p=4,h=0,m=1,_=2,$=3,y=0,g=c,T=c*2,x=-1;o==="RGBA"?(y=0,g=c,T=c*2,x=c*3):o==="RGB"?(y=0,g=c,T=c*2):o==="RBG"&&(y=0,T=c,g=c*2),n=i.createImageData(r,s);for(let E=0;E<s*r;h+=p,m+=p,_+=p,$+=p,E++)n.data[h]=(e.data[y++]-d[0])*u[0],n.data[m]=(e.data[g++]-d[1])*u[1],n.data[_]=(e.data[T++]-d[2])*u[2],n.data[$]=x===-1?255:(e.data[x++]-d[3])*u[3]}else throw new Error("Can not access image data");return n}}),Ne,ht,Qe,ve,Ee,Ue,Fe=C(()=>{Vt(),Ne=(e,t)=>{if(e===void 0)throw new Error("Image buffer must be defined");if(t.height===void 0||t.width===void 0)throw new Error("Image height and width must be defined");if(t.tensorLayout==="NHWC")throw new Error("NHWC Tensor layout is not supported yet");let{height:i,width:n}=t,r=t.norm??{mean:255,bias:0},s,a;typeof r.mean=="number"?s=[r.mean,r.mean,r.mean,r.mean]:s=[r.mean[0],r.mean[1],r.mean[2],r.mean[3]??255],typeof r.bias=="number"?a=[r.bias,r.bias,r.bias,r.bias]:a=[r.bias[0],r.bias[1],r.bias[2],r.bias[3]??0];let o=t.format!==void 0?t.format:"RGBA",l=t.tensorFormat!==void 0&&t.tensorFormat!==void 0?t.tensorFormat:"RGB",u=i*n,d=l==="RGBA"?new Float32Array(u*4):new Float32Array(u*3),c=4,p=0,h=1,m=2,_=3,$=0,y=u,g=u*2,T=-1;o==="RGB"&&(c=3,p=0,h=1,m=2,_=-1),l==="RGBA"?T=u*3:l==="RBG"?($=0,g=u,y=u*2):l==="BGR"&&(g=0,y=u,$=u*2);for(let x=0;x<u;x++,p+=c,m+=c,h+=c,_+=c)d[$++]=(e[p]+a[0])/s[0],d[y++]=(e[h]+a[1])/s[1],d[g++]=(e[m]+a[2])/s[2],T!==-1&&_!==-1&&(d[T++]=(e[_]+a[3])/s[3]);return l==="RGBA"?new Ze("float32",d,[1,4,i,n]):new Ze("float32",d,[1,3,i,n])},ht=async(e,t)=>{let i=typeof HTMLImageElement<"u"&&e instanceof HTMLImageElement,n=typeof ImageData<"u"&&e instanceof ImageData,r=typeof ImageBitmap<"u"&&e instanceof ImageBitmap,s=typeof e=="string",a,o=t??{},l=()=>{if(typeof document<"u")return document.createElement("canvas");if(typeof OffscreenCanvas<"u")return new OffscreenCanvas(1,1);throw new Error("Canvas is not supported")},u=d=>typeof HTMLCanvasElement<"u"&&d instanceof HTMLCanvasElement||d instanceof OffscreenCanvas?d.getContext("2d"):null;if(i){let d=l();d.width=e.width,d.height=e.height;let c=u(d);if(c!=null){let p=e.height,h=e.width;if(t!==void 0&&t.resizedHeight!==void 0&&t.resizedWidth!==void 0&&(p=t.resizedHeight,h=t.resizedWidth),t!==void 0){if(o=t,t.tensorFormat!==void 0)throw new Error("Image input config format must be RGBA for HTMLImageElement");o.tensorFormat="RGBA",o.height=p,o.width=h}else o.tensorFormat="RGBA",o.height=p,o.width=h;c.drawImage(e,0,0),a=c.getImageData(0,0,h,p).data}else throw new Error("Can not access image data")}else if(n){let d,c;if(t!==void 0&&t.resizedWidth!==void 0&&t.resizedHeight!==void 0?(d=t.resizedHeight,c=t.resizedWidth):(d=e.height,c=e.width),t!==void 0&&(o=t),o.format="RGBA",o.height=d,o.width=c,t!==void 0){let p=l();p.width=c,p.height=d;let h=u(p);if(h!=null)h.putImageData(e,0,0),a=h.getImageData(0,0,c,d).data;else throw new Error("Can not access image data")}else a=e.data}else if(r){if(t===void 0)throw new Error("Please provide image config with format for Imagebitmap");let d=l();d.width=e.width,d.height=e.height;let c=u(d);if(c!=null){let p=e.height,h=e.width;return c.drawImage(e,0,0,h,p),a=c.getImageData(0,0,h,p).data,o.height=p,o.width=h,Ne(a,o)}else throw new Error("Can not access image data")}else{if(s)return new Promise((d,c)=>{let p=l(),h=u(p);if(!e||!h)return c();let m=new Image;m.crossOrigin="Anonymous",m.src=e,m.onload=()=>{p.width=m.width,p.height=m.height,h.drawImage(m,0,0,p.width,p.height);let _=h.getImageData(0,0,p.width,p.height);o.height=p.height,o.width=p.width,d(Ne(_.data,o))}});throw new Error("Input data provided is not supported - aborted tensor creation")}if(a!==void 0)return Ne(a,o);throw new Error("Input data provided is not supported - aborted tensor creation")},Qe=(e,t)=>{let{width:i,height:n,download:r,dispose:s}=t,a=[1,n,i,4];return new Ze({location:"texture",type:"float32",texture:e,dims:a,download:r,dispose:s})},ve=(e,t)=>{let{dataType:i,dims:n,download:r,dispose:s}=t;return new Ze({location:"gpu-buffer",type:i??"float32",gpuBuffer:e,dims:n,download:r,dispose:s})},Ee=(e,t)=>{let{dataType:i,dims:n,download:r,dispose:s}=t;return new Ze({location:"ml-tensor",type:i??"float32",mlTensor:e,dims:n,download:r,dispose:s})},Ue=(e,t,i)=>new Ze({location:"cpu-pinned",type:e,data:t,dims:i??[t.length]})}),Me,ze,Ye,tt,ct=C(()=>{Me=new Map([["float32",Float32Array],["uint8",Uint8Array],["int8",Int8Array],["uint16",Uint16Array],["int16",Int16Array],["int32",Int32Array],["bool",Uint8Array],["float64",Float64Array],["uint32",Uint32Array],["int4",Uint8Array],["uint4",Uint8Array]]),ze=new Map([[Float32Array,"float32"],[Uint8Array,"uint8"],[Int8Array,"int8"],[Uint16Array,"uint16"],[Int16Array,"int16"],[Int32Array,"int32"],[Float64Array,"float64"],[Uint32Array,"uint32"]]),Ye=!1,tt=()=>{if(!Ye){Ye=!0;let e=typeof BigInt64Array<"u"&&BigInt64Array.from,t=typeof BigUint64Array<"u"&&BigUint64Array.from,i=globalThis.Float16Array,n=typeof i<"u"&&i.from;e&&(Me.set("int64",BigInt64Array),ze.set(BigInt64Array,"int64")),t&&(Me.set("uint64",BigUint64Array),ze.set(BigUint64Array,"uint64")),n?(Me.set("float16",i),ze.set(i,"float16")):Me.set("float16",Uint16Array)}}}),st,it,rt=C(()=>{Vt(),st=e=>{let t=1;for(let i=0;i<e.length;i++){let n=e[i];if(typeof n!="number"||!Number.isSafeInteger(n))throw new TypeError(`dims[${i}] must be an integer, got: ${n}`);if(n<0)throw new RangeError(`dims[${i}] must be a non-negative integer, got: ${n}`);t*=n}return t},it=(e,t)=>{switch(e.location){case"cpu":return new Ze(e.type,e.data,t);case"cpu-pinned":return new Ze({location:"cpu-pinned",data:e.data,type:e.type,dims:t});case"texture":return new Ze({location:"texture",texture:e.texture,type:e.type,dims:t});case"gpu-buffer":return new Ze({location:"gpu-buffer",gpuBuffer:e.gpuBuffer,type:e.type,dims:t});case"ml-tensor":return new Ze({location:"ml-tensor",mlTensor:e.mlTensor,type:e.type,dims:t});default:throw new Error(`tensorReshape: tensor location ${e.location} is not supported`)}}}),Ze,Vt=C(()=>{Ae(),Fe(),ct(),rt(),Ze=class{constructor(e,t,i){tt();let n,r;if(typeof e=="object"&&"location"in e)switch(this.dataLocation=e.location,n=e.type,r=e.dims,e.location){case"cpu-pinned":{let a=Me.get(n);if(!a)throw new TypeError(`unsupported type "${n}" to create tensor from pinned buffer`);if(!(e.data instanceof a))throw new TypeError(`buffer should be of type ${a.name}`);this.cpuData=e.data;break}case"texture":{if(n!=="float32")throw new TypeError(`unsupported type "${n}" to create tensor from texture`);this.gpuTextureData=e.texture,this.downloader=e.download,this.disposer=e.dispose;break}case"gpu-buffer":{if(n!=="float32"&&n!=="float16"&&n!=="int32"&&n!=="int64"&&n!=="uint32"&&n!=="uint8"&&n!=="bool"&&n!=="uint4"&&n!=="int4")throw new TypeError(`unsupported type "${n}" to create tensor from gpu buffer`);this.gpuBufferData=e.gpuBuffer,this.downloader=e.download,this.disposer=e.dispose;break}case"ml-tensor":{if(n!=="float32"&&n!=="float16"&&n!=="int32"&&n!=="int64"&&n!=="uint32"&&n!=="uint64"&&n!=="int8"&&n!=="uint8"&&n!=="bool"&&n!=="uint4"&&n!=="int4")throw new TypeError(`unsupported type "${n}" to create tensor from MLTensor`);this.mlTensorData=e.mlTensor,this.downloader=e.download,this.disposer=e.dispose;break}default:throw new Error(`Tensor constructor: unsupported location '${this.dataLocation}'`)}else{let a,o;if(typeof e=="string")if(n=e,o=i,e==="string"){if(!Array.isArray(t))throw new TypeError("A string tensor's data must be a string array.");a=t}else{let l=Me.get(e);if(l===void 0)throw new TypeError(`Unsupported tensor type: ${e}.`);if(Array.isArray(t)){if(e==="float16"&&l===Uint16Array||e==="uint4"||e==="int4")throw new TypeError(`Creating a ${e} tensor from number array is not supported. Please use ${l.name} as data.`);e==="uint64"||e==="int64"?a=l.from(t,BigInt):a=l.from(t)}else if(t instanceof l)a=t;else if(t instanceof Uint8ClampedArray)if(e==="uint8")a=Uint8Array.from(t);else throw new TypeError("A Uint8ClampedArray tensor's data must be type of uint8");else if(e==="float16"&&t instanceof Uint16Array&&l!==Uint16Array)a=new globalThis.Float16Array(t.buffer,t.byteOffset,t.length);else throw new TypeError(`A ${n} tensor's data must be type of ${l}`)}else if(o=t,Array.isArray(e)){if(e.length===0)throw new TypeError("Tensor type cannot be inferred from an empty array.");let l=typeof e[0];if(l==="string")n="string",a=e;else if(l==="boolean")n="bool",a=Uint8Array.from(e);else throw new TypeError(`Invalid element type of data array: ${l}.`)}else if(e instanceof Uint8ClampedArray)n="uint8",a=Uint8Array.from(e);else{let l=ze.get(e.constructor);if(l===void 0)throw new TypeError(`Unsupported type for tensor data: ${e.constructor}.`);n=l,a=e}if(o===void 0)o=[a.length];else if(!Array.isArray(o))throw new TypeError("A tensor's dims must be a number array");r=o,this.cpuData=a,this.dataLocation="cpu"}let s=st(r);if(this.cpuData&&s!==this.cpuData.length&&!((n==="uint4"||n==="int4")&&Math.ceil(s/2)===this.cpuData.length))throw new Error(`Tensor's size(${s}) does not match data length(${this.cpuData.length}).`);this.type=n,this.dims=r,this.size=s}static async fromImage(e,t){return ht(e,t)}static fromTexture(e,t){return Qe(e,t)}static fromGpuBuffer(e,t){return ve(e,t)}static fromMLTensor(e,t){return Ee(e,t)}static fromPinnedBuffer(e,t,i){return Ue(e,t,i)}toDataURL(e){return ue(this,e)}toImageData(e){return Ce(this,e)}get data(){if(this.ensureValid(),!this.cpuData)throw new Error("The data is not on CPU. Use `getData()` to download GPU data to CPU, or use `texture` or `gpuBuffer` property to access the GPU data directly.");return this.cpuData}get location(){return this.dataLocation}get texture(){if(this.ensureValid(),!this.gpuTextureData)throw new Error("The data is not stored as a WebGL texture.");return this.gpuTextureData}get gpuBuffer(){if(this.ensureValid(),!this.gpuBufferData)throw new Error("The data is not stored as a WebGPU buffer.");return this.gpuBufferData}get mlTensor(){if(this.ensureValid(),!this.mlTensorData)throw new Error("The data is not stored as a WebNN MLTensor.");return this.mlTensorData}async getData(e){switch(this.ensureValid(),this.dataLocation){case"cpu":case"cpu-pinned":return this.data;case"texture":case"gpu-buffer":case"ml-tensor":{if(!this.downloader)throw new Error("The current tensor is not created with a specified data downloader.");if(this.isDownloading)throw new Error("The current tensor is being downloaded.");try{this.isDownloading=!0;let t=await this.downloader();return this.downloader=void 0,this.dataLocation="cpu",this.cpuData=t,e&&this.disposer&&(this.disposer(),this.disposer=void 0),t}finally{this.isDownloading=!1}}default:throw new Error(`cannot get data from location: ${this.dataLocation}`)}}dispose(){if(this.isDownloading)throw new Error("The current tensor is being downloaded.");this.disposer&&(this.disposer(),this.disposer=void 0),this.cpuData=void 0,this.gpuTextureData=void 0,this.gpuBufferData=void 0,this.mlTensorData=void 0,this.downloader=void 0,this.isDownloading=void 0,this.dataLocation="none"}ensureValid(){if(this.dataLocation==="none")throw new Error("The tensor is disposed.")}reshape(e){if(this.ensureValid(),this.downloader||this.disposer)throw new Error("Cannot reshape a tensor that owns GPU resource.");return it(this,e)}}}),pt,Mt=C(()=>{Vt(),pt=Ze}),Te,qe,Pe,je,mt,se,fe=C(()=>{q(),Te=(e,t)=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||console.timeStamp(`${e}::ORT::${t}`)},qe=(e,t)=>{let i=new Error().stack?.split(/\r\n|\r|\n/g)||[],n=!1;for(let r=0;r<i.length;r++){if(n&&!i[r].includes("TRACE_FUNC")){let s=`FUNC_${e}::${i[r].trim().split(" ")[1]}`;t&&(s+=`::${t}`),Te("CPU",s);return}i[r].includes("TRACE_FUNC")&&(n=!0)}},Pe=e=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||qe("BEGIN",e)},je=e=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||qe("END",e)},mt=e=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||console.time(`ORT::${e}`)},se=e=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||console.timeEnd(`ORT::${e}`)}}),Se,De=C(()=>{ee(),Mt(),fe(),Se=class np{constructor(t){this.handler=t}async run(t,i,n){Pe(),mt("InferenceSession.run");let r={},s={};if(typeof t!="object"||t===null||t instanceof pt||Array.isArray(t))throw new TypeError("'feeds' must be an object that use input names as keys and OnnxValue as corresponding values.");let a=!0;if(typeof i=="object"){if(i===null)throw new TypeError("Unexpected argument[1]: cannot be null.");if(i instanceof pt)throw new TypeError("'fetches' cannot be a Tensor");if(Array.isArray(i)){if(i.length===0)throw new TypeError("'fetches' cannot be an empty array.");a=!1;for(let u of i){if(typeof u!="string")throw new TypeError("'fetches' must be a string array or an object.");if(this.outputNames.indexOf(u)===-1)throw new RangeError(`'fetches' contains invalid output name: ${u}.`);r[u]=null}if(typeof n=="object"&&n!==null)s=n;else if(typeof n<"u")throw new TypeError("'options' must be an object.")}else{let u=!1,d=Object.getOwnPropertyNames(i);for(let c of this.outputNames)if(d.indexOf(c)!==-1){let p=i[c];(p===null||p instanceof pt)&&(u=!0,a=!1,r[c]=p)}if(u){if(typeof n=="object"&&n!==null)s=n;else if(typeof n<"u")throw new TypeError("'options' must be an object.")}else s=i}}else if(typeof i<"u")throw new TypeError("Unexpected argument[1]: must be 'fetches' or 'options'.");for(let u of this.inputNames)if(typeof t[u]>"u")throw new Error(`input '${u}' is missing in 'feeds'.`);if(a)for(let u of this.outputNames)r[u]=null;let o=await this.handler.run(t,r,s),l={};for(let u in o)if(Object.hasOwnProperty.call(o,u)){let d=o[u];d instanceof pt?l[u]=d:l[u]=new pt(d.type,d.data,d.dims)}return se("InferenceSession.run"),je(),l}async release(){return this.handler.dispose()}static async create(t,i,n,r){Pe(),mt("InferenceSession.create");let s,a={};if(typeof t=="string"){if(s=t,typeof i=="object"&&i!==null)a=i;else if(typeof i<"u")throw new TypeError("'options' must be an object.")}else if(t instanceof Uint8Array){if(s=t,typeof i=="object"&&i!==null)a=i;else if(typeof i<"u")throw new TypeError("'options' must be an object.")}else if(t instanceof ArrayBuffer||typeof SharedArrayBuffer<"u"&&t instanceof SharedArrayBuffer){let d=t,c=0,p=t.byteLength;if(typeof i=="object"&&i!==null)a=i;else if(typeof i=="number"){if(c=i,!Number.isSafeInteger(c))throw new RangeError("'byteOffset' must be an integer.");if(c<0||c>=d.byteLength)throw new RangeError(`'byteOffset' is out of range [0, ${d.byteLength}).`);if(p=t.byteLength-c,typeof n=="number"){if(p=n,!Number.isSafeInteger(p))throw new RangeError("'byteLength' must be an integer.");if(p<=0||c+p>d.byteLength)throw new RangeError(`'byteLength' is out of range (0, ${d.byteLength-c}].`);if(typeof r=="object"&&r!==null)a=r;else if(typeof r<"u")throw new TypeError("'options' must be an object.")}else if(typeof n<"u")throw new TypeError("'byteLength' must be a number.")}else if(typeof i<"u")throw new TypeError("'options' must be an object.");s=new Uint8Array(d,c,p)}else throw new TypeError("Unexpected argument[0]: must be 'path' or 'buffer'.");let[o,l]=await G(a),u=await o.createInferenceSessionHandler(s,l);return se("InferenceSession.create"),je(),new np(u)}startProfiling(){this.handler.startProfiling()}endProfiling(){this.handler.endProfiling()}get inputNames(){return this.handler.inputNames}get outputNames(){return this.handler.outputNames}get inputMetadata(){return this.handler.inputMetadata}get outputMetadata(){return this.handler.outputMetadata}}}),We,Dt=C(()=>{De(),We=Se}),ti=C(()=>{}),hp=C(()=>{}),mp=C(()=>{}),gp=C(()=>{}),Hr={};Z(Hr,{InferenceSession:()=>We,TRACE:()=>Te,TRACE_EVENT_BEGIN:()=>mt,TRACE_EVENT_END:()=>se,TRACE_FUNC_BEGIN:()=>Pe,TRACE_FUNC_END:()=>je,Tensor:()=>pt,env:()=>ne,registerBackend:()=>P});var yt=C(()=>{R(),ye(),Dt(),Mt(),ti(),hp(),fe(),mp(),gp()}),tn=C(()=>{}),Kr={};Z(Kr,{default:()=>Qr});var nn,rn,Qr,_p=C(()=>{Tc(),Lt(),un(),nn="ort-wasm-proxy-worker",rn=globalThis.self?.name===nn,rn&&(self.onmessage=e=>{let{type:t,in:i}=e.data;try{switch(t){case"init-wasm":pn(i.wasm).then(()=>{xr(i).then(()=>{postMessage({type:t})},n=>{postMessage({type:t,err:n})})},n=>{postMessage({type:t,err:n})});break;case"init-ep":{let{epName:n,env:r}=i;Sr(r,n).then(()=>{postMessage({type:t})},s=>{postMessage({type:t,err:s})});break}case"copy-from":{let{buffer:n}=i,r=ji(n);postMessage({type:t,out:r});break}case"create":{let{model:n,options:r}=i;Tr(n,r).then(s=>{postMessage({type:t,out:s})},s=>{postMessage({type:t,err:s})});break}case"release":Cr(i),postMessage({type:t});break;case"run":{let{sessionId:n,inputIndices:r,inputs:s,outputIndices:a,options:o}=i;Ir(n,r,s,a,new Array(a.length).fill(null),o).then(l=>{l.some(u=>u[3]!=="cpu")?postMessage({type:t,err:"Proxy does not support non-cpu tensor location."}):postMessage({type:t,out:l},zr([...s,...l]))},l=>{postMessage({type:t,err:l})});break}case"end-profiling":Ar(i),postMessage({type:t});break;default:}}catch(n){postMessage({type:t,err:n})}}),Qr=rn?null:e=>new Worker(e??gt,{type:"classic",name:nn})}),Zr,Xr,gt,sn,Ei,Yr,Jr,an,es,on,ts,ln,is,un=C(()=>{tn(),Zr=typeof location>"u"?void 0:location.origin,Xr=()=>typeof document<"u"?document.currentScript?.src:typeof self<"u"?self.location?.href:void 0,gt=Xr(),sn=()=>{if(gt&&!gt.startsWith("blob:"))return gt.substring(0,gt.lastIndexOf("/")+1)},Ei=(e,t)=>{try{let i=t??gt;return(i?new URL(e,i):new URL(e)).origin===Zr}catch{return!1}},Yr=(e,t)=>{let i=t??gt;try{return(i?new URL(e,i):new URL(e)).href}catch{return}},Jr=(e,t)=>`${t??"./"}${e}`,an=async e=>{let t=await(await fetch(e,{credentials:"same-origin"})).blob();return URL.createObjectURL(t)},es=async e=>(await import(e)).default,on=(_p(),H(Kr)).default,ts=async()=>{if(!gt)throw new Error("Failed to load proxy worker: cannot determine the script source URL.");if(Ei(gt))return[void 0,on()];let e=await an(gt);return[e,on(e)]},ln=void 0,is=async(e,t,i,n)=>{let r=ln&&!(e||t);if(r)if(gt)r=Ei(gt);else if(n&&!i)r=!0;else throw new Error("cannot determine the script source URL.");if(r)return[void 0,ln];{let s="ort-wasm-simd-threaded.jsep.mjs",a=e??Yr(s,t),o=i&&a&&!Ei(a,t),l=o?await an(a):a??Jr(s,t);return[o?l:void 0,await es(l)]}}}),dn,Ii,ui,cn,ns,rs,ss,pn,Ge,Lt=C(()=>{un(),Ii=!1,ui=!1,cn=!1,ns=()=>{if(typeof SharedArrayBuffer>"u")return!1;try{return typeof MessageChannel<"u"&&new MessageChannel().port1.postMessage(new SharedArrayBuffer(1)),WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,4,1,96,0,0,3,2,1,0,5,4,1,3,1,1,10,11,1,9,0,65,0,254,16,2,0,26,11]))}catch{return!1}},rs=()=>{try{return WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,4,1,96,0,0,3,2,1,0,10,30,1,28,0,65,0,253,15,253,12,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,253,186,1,26,11]))}catch{return!1}},ss=()=>{try{return WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,10,19,1,17,0,65,1,253,15,65,2,253,15,65,3,253,15,253,147,2,11]))}catch{return!1}},pn=async e=>{if(Ii)return Promise.resolve();if(ui)throw new Error("multiple calls to 'initializeWebAssembly()' detected.");if(cn)throw new Error("previous call to 'initializeWebAssembly()' failed.");ui=!0;let t=e.initTimeout,i=e.numThreads;if(e.simd!==!1){if(e.simd==="relaxed"){if(!ss())throw new Error("Relaxed WebAssembly SIMD is not supported in the current environment.")}else if(!rs())throw new Error("WebAssembly SIMD is not supported in the current environment.")}let n=ns();i>1&&!n&&(typeof self<"u"&&!self.crossOriginIsolated&&console.warn("env.wasm.numThreads is set to "+i+", but this will not work unless you enable crossOriginIsolated mode. See https://web.dev/cross-origin-isolation-guide/ for more info."),console.warn("WebAssembly multi-threading is not supported in the current environment. Falling back to single-threading."),e.numThreads=i=1);let r=e.wasmPaths,s=typeof r=="string"?r:void 0,a=r?.mjs,o=a?.href??a,l=r?.wasm,u=l?.href??l,d=e.wasmBinary,[c,p]=await is(o,s,i>1,!!d||!!u),h=!1,m=[];if(t>0&&m.push(new Promise(_=>{setTimeout(()=>{h=!0,_()},t)})),m.push(new Promise((_,$)=>{let y={numThreads:i};if(d)y.wasmBinary=d;else if(u||s)y.locateFile=g=>u??s+g;else if(o&&o.indexOf("blob:")!==0)y.locateFile=g=>new URL(g,o).href;else if(c){let g=sn();g&&(y.locateFile=T=>g+T)}p(y).then(g=>{ui=!1,Ii=!0,dn=g,_(),c&&URL.revokeObjectURL(c)},g=>{ui=!1,cn=!0,$(g)})})),await Promise.race(m),h)throw new Error(`WebAssembly backend initializing failed due to timeout: ${t}ms`)},Ge=()=>{if(Ii&&dn)return dn;throw new Error("WebAssembly is not initialized yet.")}}),bt,Ai,Ve,fn=C(()=>{Lt(),bt=(e,t)=>{let i=Ge(),n=i.lengthBytesUTF8(e)+1,r=i._malloc(n);return i.stringToUTF8(e,r,n),t.push(r),r},Ai=(e,t,i,n)=>{if(typeof e=="object"&&e!==null){if(i.has(e))throw new Error("Circular reference in options");i.add(e)}Object.entries(e).forEach(([r,s])=>{let a=t?t+r:r;if(typeof s=="object")Ai(s,a+".",i,n);else if(typeof s=="string"||typeof s=="number")n(a,s.toString());else if(typeof s=="boolean")n(a,s?"1":"0");else throw new Error(`Can't handle extra config type: ${typeof s}`)})},Ve=e=>{let t=Ge(),i=t.stackSave();try{let n=t.PTR_SIZE,r=t.stackAlloc(2*n);t._OrtGetLastError(r,r+n);let s=Number(t.getValue(r,n===4?"i32":"i64")),a=t.getValue(r+n,"*"),o=a?t.UTF8ToString(a):"";throw new Error(`${e} ERROR_CODE: ${s}, ERROR_MESSAGE: ${o}`)}finally{t.stackRestore(i)}}}),as,yp=C(()=>{Lt(),fn(),as=e=>{let t=Ge(),i=0,n=[],r=e||{};try{if(e?.logSeverityLevel===void 0)r.logSeverityLevel=2;else if(typeof e.logSeverityLevel!="number"||!Number.isInteger(e.logSeverityLevel)||e.logSeverityLevel<0||e.logSeverityLevel>4)throw new Error(`log severity level is not valid: ${e.logSeverityLevel}`);if(e?.logVerbosityLevel===void 0)r.logVerbosityLevel=0;else if(typeof e.logVerbosityLevel!="number"||!Number.isInteger(e.logVerbosityLevel))throw new Error(`log verbosity level is not valid: ${e.logVerbosityLevel}`);e?.terminate===void 0&&(r.terminate=!1);let s=0;return e?.tag!==void 0&&(s=bt(e.tag,n)),i=t._OrtCreateRunOptions(r.logSeverityLevel,r.logVerbosityLevel,!!r.terminate,s),i===0&&Ve("Can't create run options."),e?.extra!==void 0&&Ai(e.extra,"",new WeakSet,(a,o)=>{let l=bt(a,n),u=bt(o,n);t._OrtAddRunConfigEntry(i,l,u)!==0&&Ve(`Can't set a run config entry: ${a} - ${o}.`)}),[i,n]}catch(s){throw i!==0&&t._OrtReleaseRunOptions(i),n.forEach(a=>t._free(a)),s}}}),os,ls,us,di,ds,cs,wp=C(()=>{Lt(),fn(),os=e=>{switch(e){case"disabled":return 0;case"basic":return 1;case"extended":return 2;case"layout":return 3;case"all":return 99;default:throw new Error(`unsupported graph optimization level: ${e}`)}},ls=e=>{switch(e){case"sequential":return 0;case"parallel":return 1;default:throw new Error(`unsupported execution mode: ${e}`)}},us=e=>{e.extra||(e.extra={}),e.extra.session||(e.extra.session={});let t=e.extra.session;t.use_ort_model_bytes_directly||(t.use_ort_model_bytes_directly="1"),e.executionProviders&&e.executionProviders.some(i=>(typeof i=="string"?i:i.name)==="webgpu")&&(e.enableMemPattern=!1)},di=(e,t,i,n)=>{let r=bt(t,n),s=bt(i,n);Ge()._OrtAddSessionConfigEntry(e,r,s)!==0&&Ve(`Can't set a session config entry: ${t} - ${i}.`)},ds=async(e,t,i)=>{for(let n of t){let r=typeof n=="string"?n:n.name,s=[];switch(r){case"webnn":if(r="WEBNN",typeof n!="string"){let d=n?.deviceType;d&&di(e,"deviceType",d,i)}break;case"webgpu":if(r="JS",typeof n!="string"){let d=n;if(d?.preferredLayout){if(d.preferredLayout!=="NCHW"&&d.preferredLayout!=="NHWC")throw new Error(`preferredLayout must be either 'NCHW' or 'NHWC': ${d.preferredLayout}`);di(e,"preferredLayout",d.preferredLayout,i)}}break;case"wasm":case"cpu":continue;default:throw new Error(`not supported execution provider: ${r}`)}let a=bt(r,i),o=s.length,l=0,u=0;if(o>0){l=Ge()._malloc(o*Ge().PTR_SIZE),i.push(l),u=Ge()._malloc(o*Ge().PTR_SIZE),i.push(u);for(let d=0;d<o;d++)Ge().setValue(l+d*Ge().PTR_SIZE,s[d][0],"*"),Ge().setValue(u+d*Ge().PTR_SIZE,s[d][1],"*")}await Ge()._OrtAppendExecutionProvider(e,a,l,u,o)!==0&&Ve(`Can't append execution provider: ${r}.`)}},cs=async e=>{let t=Ge(),i=0,n=[],r=e||{};us(r);try{let s=os(r.graphOptimizationLevel??"all"),a=ls(r.executionMode??"sequential"),o=typeof r.logId=="string"?bt(r.logId,n):0,l=r.logSeverityLevel??2;if(!Number.isInteger(l)||l<0||l>4)throw new Error(`log severity level is not valid: ${l}`);let u=r.logVerbosityLevel??0;if(!Number.isInteger(u)||u<0||u>4)throw new Error(`log verbosity level is not valid: ${u}`);let d=typeof r.optimizedModelFilePath=="string"?bt(r.optimizedModelFilePath,n):0;if(i=t._OrtCreateSessionOptions(s,!!r.enableCpuMemArena,!!r.enableMemPattern,a,!!r.enableProfiling,0,o,l,u,d),i===0&&Ve("Can't create session options."),r.executionProviders&&await ds(i,r.executionProviders,n),r.enableGraphCapture!==void 0){if(typeof r.enableGraphCapture!="boolean")throw new Error(`enableGraphCapture must be a boolean value: ${r.enableGraphCapture}`);di(i,"enableGraphCapture",r.enableGraphCapture.toString(),n)}if(r.freeDimensionOverrides)for(let[c,p]of Object.entries(r.freeDimensionOverrides)){if(typeof c!="string")throw new Error(`free dimension override name must be a string: ${c}`);if(typeof p!="number"||!Number.isInteger(p)||p<0)throw new Error(`free dimension override value must be a non-negative integer: ${p}`);let h=bt(c,n);t._OrtAddFreeDimensionOverride(i,h,p)!==0&&Ve(`Can't set a free dimension override: ${c} - ${p}.`)}return r.extra!==void 0&&Ai(r.extra,"",new WeakSet,(c,p)=>{di(i,c,p,n)}),[i,n]}catch(s){throw i!==0&&t._OrtReleaseSessionOptions(i)!==0&&Ve("Can't release session options."),n.forEach(a=>t._free(a)),s}}}),Ut,At,qt,zi,Oi,hn,mn,gn,me=C(()=>{Ut=e=>{switch(e){case"int8":return 3;case"uint8":return 2;case"bool":return 9;case"int16":return 5;case"uint16":return 4;case"int32":return 6;case"uint32":return 12;case"float16":return 10;case"float32":return 1;case"float64":return 11;case"string":return 8;case"int64":return 7;case"uint64":return 13;case"int4":return 22;case"uint4":return 21;default:throw new Error(`unsupported data type: ${e}`)}},At=e=>{switch(e){case 3:return"int8";case 2:return"uint8";case 9:return"bool";case 5:return"int16";case 4:return"uint16";case 6:return"int32";case 12:return"uint32";case 10:return"float16";case 1:return"float32";case 11:return"float64";case 8:return"string";case 7:return"int64";case 13:return"uint64";case 22:return"int4";case 21:return"uint4";default:throw new Error(`unsupported data type: ${e}`)}},qt=(e,t)=>{let i=[-1,4,1,1,2,2,4,8,-1,1,2,8,4,8,-1,-1,-1,-1,-1,-1,-1,.5,.5][e],n=typeof t=="number"?t:t.reduce((r,s)=>r*s,1);return i>0?Math.ceil(n*i):void 0},zi=e=>{switch(e){case"float16":return typeof Float16Array<"u"&&Float16Array.from?Float16Array:Uint16Array;case"float32":return Float32Array;case"uint8":return Uint8Array;case"int8":return Int8Array;case"uint16":return Uint16Array;case"int16":return Int16Array;case"int32":return Int32Array;case"bool":return Uint8Array;case"float64":return Float64Array;case"uint32":return Uint32Array;case"int64":return BigInt64Array;case"uint64":return BigUint64Array;default:throw new Error(`unsupported type: ${e}`)}},Oi=e=>{switch(e){case"verbose":return 0;case"info":return 1;case"warning":return 2;case"error":return 3;case"fatal":return 4;default:throw new Error(`unsupported logging level: ${e}`)}},hn=e=>e==="float32"||e==="float16"||e==="int32"||e==="int64"||e==="uint32"||e==="uint8"||e==="bool"||e==="uint4"||e==="int4",mn=e=>e==="float32"||e==="float16"||e==="int32"||e==="int64"||e==="uint32"||e==="uint64"||e==="int8"||e==="uint8"||e==="bool"||e==="uint4"||e==="int4",gn=e=>{switch(e){case"none":return 0;case"cpu":return 1;case"cpu-pinned":return 2;case"texture":return 3;case"gpu-buffer":return 4;case"ml-tensor":return 5;default:throw new Error(`unsupported data location: ${e}`)}}}),_n,ps=C(()=>{tn(),_n=async e=>{if(typeof e=="string"){let t=await fetch(e);if(!t.ok)throw new Error(`failed to load external data file: ${e}`);let i=t.headers.get("Content-Length"),n=i?parseInt(i,10):0;if(n<1073741824)return new Uint8Array(await t.arrayBuffer());{if(!t.body)throw new Error(`failed to load external data file: ${e}, no response body.`);let r=t.body.getReader(),s;try{s=new ArrayBuffer(n)}catch(o){if(o instanceof RangeError){let l=Math.ceil(n/65536);s=new WebAssembly.Memory({initial:l,maximum:l}).buffer}else throw o}let a=0;for(;;){let{done:o,value:l}=await r.read();if(o)break;let u=l.byteLength;new Uint8Array(s,a,u).set(l),a+=u}return new Uint8Array(s,0,n)}}else return e instanceof Blob?new Uint8Array(await e.arrayBuffer()):e instanceof Uint8Array?e:new Uint8Array(e)}}),fs,hs,ms,gs,yn,_s,Ie,zt=C(()=>{me(),fs=["V","I","W","E","F"],hs=(e,t)=>{console.log(`[${fs[e]},${new Date().toISOString()}]${t}`)},yn=(e,t)=>{ms=e,gs=t},_s=(e,t)=>{let i=Oi(e),n=Oi(ms);i>=n&&hs(i,typeof t=="function"?t():t)},Ie=(...e)=>{gs&&_s(...e)}}),ys,ii,M,Ri,ws,bs,vs,be=C(()=>{ys=class{static calcMatMulShape(e,t){return e[1]!==t[0]?void 0:[e[0],t[1]]}},ii=class{static calcShape(e,t,i=!1){let n=e.length,r=t.length;if(n===0)return t;if(r===0)return e;let s=Math.max(e.length,t.length),a=new Array(s);if(i){if(n<2||r<2)return;let o=ys.calcMatMulShape([e[n-2],e[n-1]],[t[r-2],t[r-1]]);if(o===void 0)return;[a[s-2],a[s-1]]=o}for(let o=i?3:1;o<=s;o++){let l=n-o<0?1:e[n-o],u=r-o<0?1:t[r-o];if(l!==u&&l>1&&u>1)return;let d=Math.max(l,u);if(l&&u)a[s-o]=Math.max(l,u);else{if(d>1)return;a[s-o]=0}}return a}static isValidBroadcast(e,t){let i=e.length,n=t.length;if(i>n)return!1;for(let r=1;r<=i;r++)if(e[i-r]!==1&&e[i-r]!==t[n-r])return!1;return!0}},M=class Xi{static size(t){return Xi.getSizeFromDimensionRange(t,0,t.length)}static convertShape(t,i=4){let n=t.length;if(n===0)return[];let r=new Array(n),s=n-1;for(;s>=0;){if(t[s]%i===0){r[s]=t[s]/i;break}if(i%t[s]!==0)throw new Error("cannot convert shape");r[s]=1,i/=t[s],s--}for(s--;s>=0;s--)r[s]=t[s];return r}static sizeFromDimension(t,i){if(i<0||i>t.length)throw new Error(`invalid dimension of ${i} for sizeFromDimension as Tensor has ${t.length} dimensions.`);return Xi.getSizeFromDimensionRange(t,i,t.length)}static sizeToDimension(t,i){if(i<0||i>t.length)throw new Error(`invalid dimension of ${i} for sizeToDimension as Tensor has ${t.length} dimensions.`);return Xi.getSizeFromDimensionRange(t,0,i)}static getSizeFromDimensionRange(t,i,n){let r=1;for(let s=i;s<n;s++){if(t[s]<0)throw new Error("cannot get valid size from specified dimension range. Most likely the range contains negative values in them.");r*=Number(t[s])}return r}static computeStrides(t){let i=t.length;if(i===0)return[];if(i===1)return[1];let n=new Array(i);n[i-1]=1,n[i-2]=t[i-1];for(let r=i-3;r>=0;--r)n[r]=n[r+1]*t[r+1];return n}static normalizeAxis(t,i){if(t<-i&&t>=i)throw new Error("unsupported axis for this operation.");return t<0?t+i:t}static normalizeAxes(t,i){return t.map(n=>this.normalizeAxis(n,i??t.length))}static sortBasedOnPerm(t,i){return i?i.map(n=>t[n]):t.slice().reverse()}static padShape(t,i){let n=t.length;return t.map((r,s)=>r+i[s]+i[s+n])}static areEqual(t,i){return t.length!==i.length?!1:t.every((n,r)=>n===i[r])}},Ri=class ki{static adjustPoolAttributes(t,i,n,r,s,a){if(!t&&n.length!==i.length-2)throw new Error("length of specified kernel shapes should be 2 less than length of input dimensions");if(t)for(let o=0;o<i.length-2;o++)o>=n.length?n.push(i[o+2]):n[o]=i[o+2];for(let o=0;o<n.length;o++)if(o<r.length){if(r[o]<0)throw new Error("strides should be greater than or equal to 1")}else r.push(1);for(let o=0;o<n.length;o++)if(o<s.length){if(s[o]<0)throw new Error("dilations should be greater than or equal to 1")}else s.push(1);for(let o=0;o<n.length*2;o++)if(o<a.length){if(a[o]<0)throw new Error("pad should be greater than or equal to 1")}else a.push(0);for(let o=0;o<n.length;o++){if(n[o]<=0)throw new Error("kernel shapes need to be greater than 0");if(a[o]>=n[o]||a[o+n.length]>=n[o])throw new Error("pads should be smaller than kernel")}}static adjustPadsBasedOnAutoPad(t,i,n,r,s,a,o){if(o){if(s.length!==2*(t.length-2))throw new Error("length of pads should be twice the length of data dimensions");if(i.length!==t.length-2)throw new Error("length of strides should be the length of data dimensions");if(r.length!==t.length-2)throw new Error("length of kernel shapes should be the length of data dimensions");for(let l=0;l<t.length-2;l++)ki.adjustPadAndReturnShape(t[l+(a?1:2)],i[l],n[l],r[l],s,l,l+t.length-2,o)}}static computePoolOutputShape(t,i,n,r,s,a,o){if(i.length<=0)throw new Error("input shape must be of size greater than 0");let l=[i[0],i[1]];return ki.computeShapeHelper(t,i,l,n,r,s,a,o),l}static computeConvOutputShape(t,i,n,r,s,a,o){if(t.length<=0||i.length<=0)throw new Error("invalid input tensor dims or invalid filter tensor dims");let l=[t[0],i[0]];return ki.computeShapeHelper(!1,t,l,n,r,s,a,o),l}static computeShapeHelper(t,i,n,r,s,a,o,l){if(t)for(let u=0;u<i.length-2;u++)n.push(1);else for(let u=0;u<i.length-2;u++)n.push(ki.adjustPadAndReturnShape(i[u+2],r[u],s[u],a[u],o,u,u+i.length-2,l))}static adjustPadAndReturnShape(t,i,n,r,s,a,o,l){let u=n*(r-1)+1;if(l&&l!=="NOTSET")switch(l){case"VALID":return s[a]=0,s[o]=0,Math.floor((t-u)/i+1);case"SAME_LOWER":case"SAME_UPPER":if(n!==1)throw new Error("Dilation not supported for SAME_UPPER or SAME_LOWER");{let d=((t+i-1)/i-1)*i+r-t;return s[a]=Math.floor(l==="SAME_LOWER"?(d+1)/2:d/2),s[o]=d-s[a],Math.floor((t+d-r)/i+1)}default:throw new Error("Unsupported AutoPad type")}else return Math.floor((t+s[a]+s[o]-u)/i+1)}},ws=class{static getShapeOfGemmResult(e,t,i,n,r){if(e.length!==2||i.length!==2)throw new Error("shape need to be of size 2");let s,a,o;t?(s=e[1],a=e[0]):(s=e[0],a=e[1]);let l=-1;if(n?(o=i[0],l=1):(o=i[1],l=0),i[l]!==a)throw new Error("dimension mismatch");if(s<=0||o<=0||a<=0)throw new Error("invalid shape specified");if(r&&!ii.isValidBroadcast(r,[s,o]))throw new Error("gemm: invalid bias shape for broadcast");return[s,o,a]}},bs=-34028234663852886e22,vs=34028234663852886e22}),wn,$s=C(()=>{me(),wn=(e,t)=>new(zi(t))(e)}),bn,vn,$n,xs,xn,Ss,Sn,kn,Tn,ks,Ts,bp=C(()=>{me(),zt(),bn=new Map([["float32",32],["float16",16],["int32",32],["uint32",32],["int64",64],["uint64",64],["int8",8],["uint8",8],["int4",4],["uint4",4]]),vn=(e,t)=>{if(t==="int32")return e;let i=bn.get(t);if(!i)throw new Error(`WebNN backend does not support data type: ${t}`);let n=i/8;if(e.byteLength%n!==0)throw new Error(`Invalid Uint8Array length - must be a multiple of ${n}.`);let r=e.byteLength/n,s=new(zi(t))(e.buffer,e.byteOffset,r);switch(t){case"int64":case"uint64":{let a=new Int32Array(r);for(let o=0;o<r;o++){let l=s[o];if(l>2147483647n||l<-2147483648n)throw new Error("Can not convert int64 data to int32 - value out of range.");a[o]=Number(l)}return new Uint8Array(a.buffer)}case"int8":case"uint8":case"uint32":{if(t==="uint32"&&s.some(o=>o>2147483647))throw new Error("Can not convert uint32 data to int32 - value out of range.");let a=Int32Array.from(s,Number);return new Uint8Array(a.buffer)}default:throw new Error(`Unsupported data conversion from ${t} to 'int32'`)}},$n=(e,t)=>{if(t==="int32")return e;if(e.byteLength%4!==0)throw new Error("Invalid Uint8Array length - must be a multiple of 4 (int32).");let i=e.byteLength/4,n=new Int32Array(e.buffer,e.byteOffset,i);switch(t){case"int64":{let r=BigInt64Array.from(n,BigInt);return new Uint8Array(r.buffer)}case"uint64":{if(n.some(s=>s<0))throw new Error("Can not convert int32 data to uin64 - negative value found.");let r=BigUint64Array.from(n,BigInt);return new Uint8Array(r.buffer)}case"int8":{if(n.some(s=>s<-128||s>127))throw new Error("Can not convert int32 data to int8 - value out of range.");let r=Int8Array.from(n,Number);return new Uint8Array(r.buffer)}case"uint8":{if(n.some(r=>r<0||r>255))throw new Error("Can not convert int32 data to uint8 - value out of range.");return Uint8Array.from(n,Number)}case"uint32":{if(n.some(s=>s<0))throw new Error("Can not convert int32 data to uint32 - negative value found.");let r=Uint32Array.from(n,Number);return new Uint8Array(r.buffer)}default:throw new Error(`Unsupported data conversion from 'int32' to ${t}`)}},xs=1,xn=()=>xs++,Ss=new Map([["int8","int32"],["uint8","int32"],["uint32","int32"],["int64","int32"]]),Sn=(e,t)=>{let i=bn.get(e);if(!i)throw new Error(`WebNN backend does not support data type: ${e}`);return t.length>0?Math.ceil(t.reduce((n,r)=>n*r)*i/8):0},kn=class{constructor(e){this.isDataConverted=!1;let{sessionId:t,context:i,tensor:n,dataType:r,shape:s,fallbackDataType:a}=e;this.sessionId=t,this.mlContext=i,this.mlTensor=n,this.dataType=r,this.tensorShape=s,this.fallbackDataType=a}get tensor(){return this.mlTensor}get type(){return this.dataType}get fallbackType(){return this.fallbackDataType}get shape(){return this.tensorShape}get byteLength(){return Sn(this.dataType,this.tensorShape)}destroy(){Ie("verbose",()=>"[WebNN] TensorWrapper.destroy"),this.mlTensor.destroy()}write(e){this.mlContext.writeTensor(this.mlTensor,e)}async read(e){if(this.fallbackDataType){let t=await this.mlContext.readTensor(this.mlTensor),i=$n(new Uint8Array(t),this.dataType);if(e){(e instanceof ArrayBuffer?new Uint8Array(e):new Uint8Array(e.buffer,e.byteOffset,e.byteLength)).set(i);return}else return i.buffer}else return e?this.mlContext.readTensor(this.mlTensor,e):this.mlContext.readTensor(this.mlTensor)}canReuseTensor(e,t,i){return this.mlContext===e&&this.dataType===t&&this.tensorShape.length===i.length&&this.tensorShape.every((n,r)=>n===i[r])}setIsDataConverted(e){this.isDataConverted=e}},Tn=class{constructor(e,t){this.tensorManager=e,this.wrapper=t}get tensorWrapper(){return this.wrapper}releaseTensor(){this.tensorWrapper&&(this.tensorManager.releaseTensor(this.tensorWrapper),this.wrapper=void 0)}async ensureTensor(e,t,i,n){let r=this.tensorManager.getMLContext(e),s;if(!r.opSupportLimits().input.dataTypes.includes(t)){if(s=Ss.get(t),!s||!r.opSupportLimits().input.dataTypes.includes(s))throw new Error(`WebNN backend does not support data type: ${t}`);Ie("verbose",()=>`[WebNN] TensorIdTracker.ensureTensor: fallback dataType from ${t} to ${s}`)}if(this.wrapper){if(this.wrapper.canReuseTensor(r,t,i))return this.wrapper.tensor;if(n){if(this.wrapper.byteLength!==Sn(t,i))throw new Error("Unable to copy data to tensor with different size.");this.activeUpload=new Uint8Array(await this.wrapper.read())}this.tensorManager.releaseTensor(this.wrapper)}let a=typeof MLTensorUsage>"u"?void 0:MLTensorUsage.READ|MLTensorUsage.WRITE;return this.wrapper=await this.tensorManager.getCachedTensor(e,t,i,a,!0,!0,s),n&&this.activeUpload&&(this.wrapper.write(this.activeUpload),this.activeUpload=void 0),this.wrapper.tensor}upload(e){let t=e;if(this.wrapper){if(this.wrapper.fallbackType)if(this.wrapper.fallbackType==="int32")t=vn(e,this.wrapper.type),this.wrapper.setIsDataConverted(!0);else throw new Error(`Unsupported fallback data type: ${this.wrapper.fallbackType}`);if(e.byteLength===this.wrapper.byteLength){this.wrapper.write(t);return}else Ie("verbose",()=>"Data size does not match tensor size. Releasing tensor."),this.releaseTensor()}this.activeUpload?this.activeUpload.set(t):this.activeUpload=new Uint8Array(t)}async download(e){if(this.activeUpload){let t=this.wrapper?.isDataConverted?$n(this.activeUpload,this.wrapper?.type):this.activeUpload;if(e){e instanceof ArrayBuffer?new Uint8Array(e).set(t):new Uint8Array(e.buffer,e.byteOffset,e.byteLength).set(t);return}else return t.buffer}if(!this.wrapper)throw new Error("Tensor has not been created.");return e?this.wrapper.read(e):this.wrapper.read()}},ks=class{constructor(e){this.backend=e,this.tensorTrackersById=new Map,this.freeTensors=[],this.externalTensors=new Set}getMLContext(e){let t=this.backend.getMLContext(e);if(!t)throw new Error("MLContext not found for session.");return t}reserveTensorId(){let e=xn();return this.tensorTrackersById.set(e,new Tn(this)),e}releaseTensorId(e){let t=this.tensorTrackersById.get(e);t&&(this.tensorTrackersById.delete(e),t.tensorWrapper&&this.releaseTensor(t.tensorWrapper))}async ensureTensor(e,t,i,n,r){Ie("verbose",()=>`[WebNN] TensorManager.ensureTensor {tensorId: ${t}, dataType: ${i}, shape: ${n}, copyOld: ${r}}`);let s=this.tensorTrackersById.get(t);if(!s)throw new Error("Tensor not found.");return s.ensureTensor(e,i,n,r)}upload(e,t){let i=this.tensorTrackersById.get(e);if(!i)throw new Error("Tensor not found.");i.upload(t)}async download(e,t){Ie("verbose",()=>`[WebNN] TensorManager.download {tensorId: ${e}, dstBuffer: ${t?.byteLength}}`);let i=this.tensorTrackersById.get(e);if(!i)throw new Error("Tensor not found.");return i.download(t)}releaseTensorsForSession(e){for(let t of this.freeTensors)t.sessionId===e&&t.destroy();this.freeTensors=this.freeTensors.filter(t=>t.sessionId!==e)}registerTensor(e,t,i,n){let r=this.getMLContext(e),s=xn(),a=new kn({sessionId:e,context:r,tensor:t,dataType:i,shape:n});return this.tensorTrackersById.set(s,new Tn(this,a)),this.externalTensors.add(a),s}async getCachedTensor(e,t,i,n,r,s,a){let o=this.getMLContext(e);for(let[u,d]of this.freeTensors.entries())if(d.canReuseTensor(o,t,i)){Ie("verbose",()=>`[WebNN] Reusing tensor {dataType: ${t}, ${a?`fallbackDataType: ${a},`:""} shape: ${i}`);let c=this.freeTensors.splice(u,1)[0];return c.sessionId=e,c}Ie("verbose",()=>`[WebNN] MLContext.createTensor {dataType: ${t}, ${a?`fallbackDataType: ${a},`:""} shape: ${i}}`);let l=await o.createTensor({dataType:a??t,shape:i,dimensions:i,usage:n,writable:r,readable:s});return new kn({sessionId:e,context:o,tensor:l,dataType:t,shape:i,fallbackDataType:a})}releaseTensor(e){this.externalTensors.has(e)&&this.externalTensors.delete(e),this.freeTensors.push(e)}},Ts=(...e)=>new ks(...e)}),ci,Cs,Es,vp=C(()=>{me(),Lt(),$s(),bp(),zt(),ci=new Map([[1,"float32"],[10,"float16"],[6,"int32"],[12,"uint32"],[7,"int64"],[13,"uint64"],[22,"int4"],[21,"uint4"],[3,"int8"],[2,"uint8"],[9,"uint8"]]),Cs=(e,t)=>{if(e===t)return!0;if(e===void 0||t===void 0)return!1;let i=Object.keys(e).sort(),n=Object.keys(t).sort();return i.length===n.length&&i.every((r,s)=>r===n[s]&&e[r]===t[r])},Es=class{constructor(e){this.tensorManager=Ts(this),this.mlContextBySessionId=new Map,this.sessionIdsByMLContext=new Map,this.mlContextCache=[],this.sessionGraphInputs=new Map,this.sessionGraphOutputs=new Map,this.temporaryGraphInputs=[],this.temporaryGraphOutputs=[],this.temporarySessionTensorIds=new Map,yn(e.logLevel,!!e.debug)}get currentSessionId(){if(this.activeSessionId===void 0)throw new Error("No active session");return this.activeSessionId}onRunStart(e){Ie("verbose",()=>`[WebNN] onRunStart {sessionId: ${e}}`),this.activeSessionId=e}onRunEnd(e){Ie("verbose",()=>`[WebNN] onRunEnd {sessionId: ${e}}`);let t=this.temporarySessionTensorIds.get(e);if(t){for(let i of t)Ie("verbose",()=>`[WebNN] releasing temporary tensor {tensorId: ${i}}`),this.tensorManager.releaseTensorId(i);this.temporarySessionTensorIds.delete(e),this.activeSessionId=void 0}}async createMLContext(e){if(e instanceof GPUDevice){let i=this.mlContextCache.findIndex(n=>n.gpuDevice===e);if(i!==-1)return this.mlContextCache[i].mlContext;{let n=await navigator.ml.createContext(e);return this.mlContextCache.push({gpuDevice:e,mlContext:n}),n}}else if(e===void 0){let i=this.mlContextCache.findIndex(n=>n.options===void 0&&n.gpuDevice===void 0);if(i!==-1)return this.mlContextCache[i].mlContext;{let n=await navigator.ml.createContext();return this.mlContextCache.push({mlContext:n}),n}}let t=this.mlContextCache.findIndex(i=>Cs(i.options,e));if(t!==-1)return this.mlContextCache[t].mlContext;{let i=await navigator.ml.createContext(e);return this.mlContextCache.push({options:e,mlContext:i}),i}}registerMLContext(e,t){this.mlContextBySessionId.set(e,t);let i=this.sessionIdsByMLContext.get(t);i||(i=new Set,this.sessionIdsByMLContext.set(t,i)),i.add(e),this.temporaryGraphInputs.length>0&&(this.sessionGraphInputs.set(e,this.temporaryGraphInputs),this.temporaryGraphInputs=[]),this.temporaryGraphOutputs.length>0&&(this.sessionGraphOutputs.set(e,this.temporaryGraphOutputs),this.temporaryGraphOutputs=[])}onReleaseSession(e){this.sessionGraphInputs.delete(e),this.sessionGraphOutputs.delete(e);let t=this.mlContextBySessionId.get(e);if(!t)return;this.tensorManager.releaseTensorsForSession(e),this.mlContextBySessionId.delete(e);let i=this.sessionIdsByMLContext.get(t);if(i.delete(e),i.size===0){this.sessionIdsByMLContext.delete(t);let n=this.mlContextCache.findIndex(r=>r.mlContext===t);n!==-1&&this.mlContextCache.splice(n,1)}}getMLContext(e){return this.mlContextBySessionId.get(e)}reserveTensorId(){return this.tensorManager.reserveTensorId()}releaseTensorId(e){Ie("verbose",()=>`[WebNN] releaseTensorId {tensorId: ${e}}`),this.tensorManager.releaseTensorId(e)}async ensureTensor(e,t,i,n,r){let s=ci.get(i);if(!s)throw new Error(`Unsupported ONNX data type: ${i}`);return this.tensorManager.ensureTensor(e??this.currentSessionId,t,s,n,r)}async createTemporaryTensor(e,t,i){Ie("verbose",()=>`[WebNN] createTemporaryTensor {onnxDataType: ${t}, shape: ${i}}`);let n=ci.get(t);if(!n)throw new Error(`Unsupported ONNX data type: ${t}`);let r=this.tensorManager.reserveTensorId();await this.tensorManager.ensureTensor(e,r,n,i,!1);let s=this.temporarySessionTensorIds.get(e);return s?s.push(r):this.temporarySessionTensorIds.set(e,[r]),r}uploadTensor(e,t){if(!Ge().shouldTransferToMLTensor)throw new Error("Trying to upload to a MLTensor while shouldTransferToMLTensor is false");Ie("verbose",()=>`[WebNN] uploadTensor {tensorId: ${e}, data: ${t.byteLength}}`),this.tensorManager.upload(e,t)}async downloadTensor(e,t){return this.tensorManager.download(e,t)}createMLTensorDownloader(e,t){return async()=>{let i=await this.tensorManager.download(e);return wn(i,t)}}registerMLTensor(e,t,i,n){let r=ci.get(i);if(!r)throw new Error(`Unsupported ONNX data type: ${i}`);let s=this.tensorManager.registerTensor(e,t,r,n);return Ie("verbose",()=>`[WebNN] registerMLTensor {tensor: ${t}, dataType: ${r}, dimensions: ${n}} -> {tensorId: ${s}}`),s}registerMLConstant(e,t,i,n,r,s,a=!1){if(!s)throw new Error("External mounted files are not available.");let o=e;e.startsWith("./")&&(o=e.substring(2));let l=s.get(o);if(!l)throw new Error(`File with name ${o} not found in preloaded files.`);if(t+i>l.byteLength)throw new Error("Out of bounds: data offset and length exceed the external file data size.");let u=l.slice(t,t+i).buffer,d;switch(r.dataType){case"float32":d=new Float32Array(u);break;case"float16":d=typeof Float16Array<"u"&&Float16Array.from?new Float16Array(u):new Uint16Array(u);break;case"int32":d=new Int32Array(u);break;case"uint32":d=new Uint32Array(u);break;case"int64":if(a){let c=vn(new Uint8Array(u),"int64");d=new Int32Array(c.buffer),r.dataType="int32"}else d=new BigInt64Array(u);break;case"uint64":d=new BigUint64Array(u);break;case"int8":d=new Int8Array(u);break;case"int4":case"uint4":case"uint8":d=new Uint8Array(u);break;default:throw new Error(`Unsupported data type: ${r.dataType} in creating WebNN Constant from external data.`)}return Ie("verbose",()=>`[WebNN] registerMLConstant {dataType: ${r.dataType}, shape: ${r.shape}}} ${a?"(Note: it was int64 data type and registered to int32 as workaround)":""}`),n.constant(r,d)}registerGraphInput(e){this.temporaryGraphInputs.push(e)}registerGraphOutput(e){this.temporaryGraphOutputs.push(e)}isGraphInput(e,t){let i=this.sessionGraphInputs.get(e);return i?i.includes(t):!1}isGraphOutput(e,t){let i=this.sessionGraphOutputs.get(e);return i?i.includes(t):!1}isGraphInputOutputTypeSupported(e,t,i=!0){let n=this.mlContextBySessionId.get(e),r=ci.get(Ut(t));return typeof r>"u"?!1:i?!!n?.opSupportLimits().input.dataTypes.includes(r):!!n?.opSupportLimits().output.dataTypes.includes(r)}flush(){}}}),Cn=C(()=>{}),En,Mi,Di,Is,As,In,An,zs,Os,$p=C(()=>{zt(),Cn(),En=new Map([[64,250],[128,200],[256,200],[512,200],[2048,230],[4096,200],[8192,50],[16384,50],[32768,50],[65536,50],[131072,50],[262144,50],[524288,50],[1048576,50],[2097152,30],[4194304,20],[8388608,10],[12582912,10],[16777216,10],[26214400,15],[33554432,22],[44236800,2],[58982400,6],[67108864,6],[134217728,6],[167772160,6]]),Mi=[],Di=e=>Math.ceil(Number(e)/16)*16,Is=e=>{for(let t=0;t<Mi.length;t++){let i=Mi[t];if(e<=i)return i}return Math.ceil(e/16)*16},As=1,In=()=>As++,An=async(e,t,i,n)=>{let r=Di(i),s=e.device.createBuffer({size:r,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});try{let a=e.getCommandEncoder();e.endComputePass(),a.copyBufferToBuffer(t,0,s,0,r),e.flush(),await s.mapAsync(GPUMapMode.READ);let o=s.getMappedRange();if(n){let l=n();return l.set(new Uint8Array(o,0,i)),l}else return new Uint8Array(o.slice(0,i))}finally{s.destroy()}},zs=class{constructor(e){this.backend=e,this.storageCache=new Map,this.freeBuffers=new Map,this.freeUniformBuffers=new Map,this.buffersPending=[],this.capturedPendingBuffers=new Map;for(let[t]of En)Mi.push(t),this.freeBuffers.set(t,[]),this.freeUniformBuffers.set(t,[]);this.sessionCount=0}upload(e,t){let i=t.buffer,n=t.byteOffset,r=t.byteLength,s=Di(r),a=this.storageCache.get(e);if(!a)throw new Error("gpu data for uploading does not exist");if(Number(a.originalSize)!==r)throw new Error(`inconsistent data size. gpu data size=${a.originalSize}, data size=${r}`);let o=this.backend.device.createBuffer({mappedAtCreation:!0,size:s,usage:GPUBufferUsage.MAP_WRITE|GPUBufferUsage.COPY_SRC}),l=o.getMappedRange();new Uint8Array(l).set(new Uint8Array(i,n,r)),o.unmap();let u=this.backend.device.createCommandEncoder();u.copyBufferToBuffer(o,0,a.gpuData.buffer,0,s),this.backend.device.queue.submit([u.finish()]),o.destroy(),Ie("verbose",()=>`[WebGPU] GpuDataManager.upload(id=${e})`)}memcpy(e,t){let i=this.storageCache.get(e);if(!i)throw new Error("source gpu data for memcpy does not exist");let n=this.storageCache.get(t);if(!n)throw new Error("destination gpu data for memcpy does not exist");if(i.originalSize!==n.originalSize)throw new Error("inconsistent source and destination gpu data size");let r=Di(i.originalSize),s=this.backend.getCommandEncoder();this.backend.endComputePass(),s.copyBufferToBuffer(i.gpuData.buffer,0,n.gpuData.buffer,0,r)}registerExternalBuffer(e,t,i){let n;if(i){if(n=i[0],e===i[1])return Ie("verbose",()=>`[WebGPU] GpuDataManager.registerExternalBuffer(size=${t}) => id=${n}, buffer is the same, skip.`),n;if(this.backend.capturedCommandList.has(this.backend.currentSessionId))throw new Error(`Registering a different external buffer under graph capture mode is not supported yet.
             Please use the previous external buffer!`)}else n=In();return this.storageCache.set(n,{gpuData:{id:n,type:0,buffer:e},originalSize:t}),Ie("verbose",()=>`[WebGPU] GpuDataManager.registerExternalBuffer(size=${t}) => id=${n}, registered.`),n}unregisterExternalBuffer(e){e!==void 0&&(this.storageCache.delete(e),Ie("verbose",()=>`[WebGPU] GpuDataManager.unregisterExternalBuffer() => id=${e}`))}create(e,t=GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_SRC|GPUBufferUsage.COPY_DST){let i=Is(e),n,r=(t&GPUBufferUsage.STORAGE)===GPUBufferUsage.STORAGE,s=(t&GPUBufferUsage.UNIFORM)===GPUBufferUsage.UNIFORM;if(r||s){let o=(r?this.freeBuffers:this.freeUniformBuffers).get(i);o?o.length>0?n=o.pop():n=this.backend.device.createBuffer({size:i,usage:t}):n=this.backend.device.createBuffer({size:i,usage:t})}else n=this.backend.device.createBuffer({size:i,usage:t});let a={id:In(),type:0,buffer:n};return this.storageCache.set(a.id,{gpuData:a,originalSize:Number(e)}),Ie("verbose",()=>`[WebGPU] GpuDataManager.create(size=${e}) => id=${a.id}`),a}get(e){return this.storageCache.get(e)?.gpuData}release(e){let t=typeof e=="bigint"?Number(e):e,i=this.storageCache.get(t);if(!i){if(this.storageCache.size===0)return 0;throw new Error("releasing data does not exist")}return Ie("verbose",()=>`[WebGPU] GpuDataManager.release(id=${t}), gpuDataId=${i.gpuData.id}`),this.storageCache.delete(t),this.buffersPending.push(i.gpuData.buffer),i.originalSize}async download(e,t){let i=this.storageCache.get(Number(e));if(!i)throw new Error("data does not exist");await An(this.backend,i.gpuData.buffer,i.originalSize,t)}refreshPendingBuffers(){if(this.buffersPending.length!==0)if(this.backend.sessionStatus==="default"){for(let e of this.buffersPending){let t=En.get(e.size);if((e.usage&GPUBufferUsage.STORAGE)===GPUBufferUsage.STORAGE){let i=this.freeBuffers.get(e.size)||[];t===void 0||i.length>=t?e.destroy():i.push(e)}else if((e.usage&GPUBufferUsage.UNIFORM)===GPUBufferUsage.UNIFORM){let i=this.freeUniformBuffers.get(e.size)||[];t===void 0||i.length>=t?e.destroy():i.push(e)}else e.destroy()}this.buffersPending=[]}else{let e=this.capturedPendingBuffers.get(this.backend.currentSessionId);e||(e=[],this.capturedPendingBuffers.set(this.backend.currentSessionId,e));for(let t of this.buffersPending)e.push(t);this.buffersPending=[]}}dispose(){this.freeBuffers.forEach(e=>{e.forEach(t=>{t.destroy()})}),this.freeUniformBuffers.forEach(e=>{e.forEach(t=>{t.destroy()})}),this.storageCache.forEach(e=>{e.gpuData.buffer.destroy()}),this.capturedPendingBuffers.forEach(e=>{e.forEach(t=>{t.destroy()})}),this.storageCache=new Map,this.freeBuffers=new Map,this.freeUniformBuffers=new Map,this.capturedPendingBuffers=new Map}onCreateSession(){this.sessionCount+=1}onReleaseSession(e){let t=this.capturedPendingBuffers.get(e);t&&(t.forEach(i=>{i.destroy()}),this.capturedPendingBuffers.delete(e)),this.sessionCount-=1,this.sessionCount===0&&(Ie("warning",()=>"[WebGPU] Clearing webgpu buffer cache"),this.storageCache.forEach(i=>{i.gpuData.buffer.destroy()}),this.storageCache=new Map)}},Os=(...e)=>new zs(...e)}),Rs,Be,Je=C(()=>{Rs=class{constructor(e){Object.assign(this,e)}get cacheKey(){return this.key||(this.key=Object.getOwnPropertyNames(this).sort().map(e=>`${this[e]}`).join(";")),this.key}},Be=e=>new Rs(e)}),ni,Bi,at,dt,de,Xe,zn,ri,Bt,oe,pi,F,ae,Ms,On,Ds,Bs,$e=C(()=>{me(),be(),ni=64,Bi=(e,t)=>{if(t===3)throw new Error("vec3 has same alignment as vec4, use vec4 instead");switch(Number(e)){case 10:return t>1?`vec${t}<f16>`:"f16";case 1:return t>1?`vec${t}<f32>`:"f32";case 6:return t>1?`vec${t}<i32>`:"i32";case 12:return t>1?`vec${t}<u32>`:"u32";case 7:if(t>1)throw new Error("currently not supported vecX of uint64 yet");return["vec2<u32>","i32"];case 13:if(t>1)throw new Error("currently not supported vecX of uint64 yet");return["vec2<u32>","u32"];case 9:if(t!==4)throw new Error("bool must be vec4");return["u32","vec4<bool>"];case 22:return"i32";case 21:return"u32";default:throw new Error(`Unknown data type: ${e}`)}},at=(e,t=1)=>{let i=Bi(e,t);return typeof i=="string"?i:i[0]},dt=(e,t=1)=>{let i=Bi(e,t);return typeof i=="string"?i:i[1]},de=(...e)=>{let t=[];return e.forEach(i=>{i.length!==0&&t.push({type:12,data:i},{type:12,data:M.computeStrides(i)})}),t},Xe=e=>e%4===0?4:e%2===0?2:1,zn=(e="f32",t,i="0")=>!t||t===1?`${e}(${i})`:`vec${t}<${e}>(${i})`,ri=(e,t,i)=>e==="f32"?i:t===1?`f32(${i})`:`vec${t}<f32>(${i})`,Bt=(e,t)=>t===4?`(${e}.x + ${e}.y + ${e}.z + ${e}.w)`:t===2?`(${e}.x + ${e}.y)`:t===3?`(${e}.x + ${e}.y + ${e}.z)`:e,oe=(e,t,i,n)=>e.startsWith("uniforms.")&&i>4?typeof t=="string"?n==="f16"?`${e}[(${t}) / 8][(${t}) % 8 / 4][(${t}) % 8 % 4]`:`${e}[(${t}) / 4][(${t}) % 4]`:n==="f16"?`${e}[${Math.floor(t/8)}][${Math.floor(t%8/4)}][${t%8%4}]`:`${e}[${Math.floor(t/4)}][${t%4}]`:i>1?`${e}[${t}]`:e,pi=(e,t,i,n,r)=>{let s=typeof i=="number",a=s?i:i.length,o=[...new Array(a).keys()],l=a<2?"u32":a<=4?`vec${a}<u32>`:`array<u32, ${a}>`,u=Bi(t,r),d=typeof u=="string"?u:u[1],c=typeof u=="string"?u:u[0],p={indices:l,value:d,storage:c,tensor:t},h=U=>typeof U=="string"?U:`${U}u`,m={offsetToIndices:!1,indicesToOffset:!1,broadcastedIndicesToOffset:!1,set:!1,setByIndices:!1,get:!1,getByIndices:!1},_=s?"uniforms.":"",$=`${_}${e}_shape`,y=`${_}${e}_strides`,g="";for(let U=0;U<a-1;U++)g+=`
    let dim${U} = current / ${oe(y,U,a)};
    let rest${U} = current % ${oe(y,U,a)};
    indices[${U}] = dim${U};
    current = rest${U};
    `;g+=`indices[${a-1}] = current;`;let T=a<2?"":`
  fn o2i_${e}(offset: u32) -> ${p.indices} {
    var indices: ${p.indices};
    var current = offset;
    ${g}
    return indices;
  }`,x=U=>(m.offsetToIndices=!0,a<2?U:`o2i_${e}(${U})`),E=[];if(a>=2)for(let U=a-1;U>=0;U--)E.push(`${oe(y,U,a)} * (indices[${U}])`);let O=a<2?"":`
  fn i2o_${e}(indices: ${p.indices}) -> u32 {
    return ${E.join("+")};
  }`,z=U=>(m.indicesToOffset=!0,a<2?U:`i2o_${e}(${U})`),N=(...U)=>a===0?"0u":`${p.indices}(${U.map(h).join(",")})`,L=(U,te)=>a<2?`${U}`:`${oe(U,te,a)}`,ie=(U,te,xe)=>a<2?`${U}=${xe};`:`${oe(U,te,a)}=${xe};`,ge={},ce=(U,te)=>{m.broadcastedIndicesToOffset=!0;let xe=`${te.name}broadcastedIndicesTo${e}Offset`;if(xe in ge)return`${xe}(${U})`;let Le=[];for(let lt=a-1;lt>=0;lt--){let Ct=te.indicesGet("outputIndices",lt+te.rank-a);Le.push(`${L(y,lt)} * (${Ct} % ${L($,lt)})`)}return ge[xe]=`fn ${xe}(outputIndices: ${te.type.indices}) -> u32 {
             return ${Le.length>0?Le.join("+"):"0u"};
           }`,`${xe}(${U})`},we=(U,te)=>(()=>{if(p.storage===p.value)return`${e}[${U}]=${te};`;if(p.storage==="vec2<u32>"&&p.value==="i32")return`${e}[${U}]=vec2<u32>(u32(${te}), select(0u, 0xFFFFFFFFu, ${te} < 0));`;if(p.storage==="vec2<u32>"&&p.value==="u32")return`${e}[${U}]=vec2<u32>(u32(${te}), 0u);`;if(p.storage==="u32"&&p.value==="vec4<bool>")return`${e}[${U}]=dot(vec4<u32>(0x1, 0x100, 0x10000, 0x1000000), vec4<u32>(${te}));`;throw new Error(`not supported combination of storage type ${p.storage} and value type ${p.value} yet`)})(),re=U=>(()=>{if(p.storage===p.value)return`${e}[${U}]`;if(p.storage==="vec2<u32>"&&p.value==="i32")return`i32(${e}[${U}].x)`;if(p.storage==="vec2<u32>"&&p.value==="u32")return`u32(${e}[${U}].x)`;if(p.storage==="u32"&&p.value==="vec4<bool>")return`vec4<bool>(bool(${e}[${U}] & 0xFFu), bool(${e}[${U}] & 0xFF00u), bool(${e}[${U}] & 0xFF0000u), bool(${e}[${U}] & 0xFF000000u))`;throw new Error(`not supported combination of storage type ${p.storage} and value type ${p.value} yet`)})(),ke=a<2?"":`
  fn get_${e}ByIndices(indices: ${p.indices}) -> ${d} {
    return ${re(`i2o_${e}(indices)`)};
  }`,he=a<2?"":(()=>{let U=o.map(xe=>`d${xe}: u32`).join(", "),te=o.map(xe=>`d${xe}`).join(", ");return`
  fn get_${e}(${U}) -> ${d} {
    return get_${e}ByIndices(${N(te)});
  }`})(),le=(...U)=>{if(U.length!==a)throw new Error(`indices length must be ${a}`);let te=U.map(h).join(",");return a===0?re("0u"):a===1?re(te[0]):(m.get=!0,m.getByIndices=!0,m.indicesToOffset=!0,`get_${e}(${te})`)},Re=U=>a<2?re(U):(m.getByIndices=!0,m.indicesToOffset=!0,`get_${e}ByIndices(${U})`),pe=a<2?"":`
  fn set_${e}ByIndices(indices: ${p.indices}, value: ${d}) {
    ${we(`i2o_${e}(indices)`,"value")}
  }`,He=a<2?"":(()=>{let U=o.map(xe=>`d${xe}: u32`).join(", "),te=o.map(xe=>`d${xe}`).join(", ");return`
  fn set_${e}(${U}, value: ${d}) {
    set_${e}ByIndices(${N(te)}, value);
  }`})();return{impl:()=>{let U=[],te=!1;return m.offsetToIndices&&(U.push(T),te=!0),m.indicesToOffset&&(U.push(O),te=!0),m.broadcastedIndicesToOffset&&(Object.values(ge).forEach(xe=>U.push(xe)),te=!0),m.set&&(U.push(He),te=!0),m.setByIndices&&(U.push(pe),te=!0),m.get&&(U.push(he),te=!0),m.getByIndices&&(U.push(ke),te=!0),!s&&te&&U.unshift(`const ${$} = ${p.indices}(${i.join(",")});`,`const ${y} = ${p.indices}(${M.computeStrides(i).join(",")});`),U.join(`
`)},type:p,offsetToIndices:x,indicesToOffset:z,broadcastedIndicesToOffset:ce,indices:N,indicesGet:L,indicesSet:ie,set:(...U)=>{if(U.length!==a+1)throw new Error(`indices length must be ${a}`);let te=U[a];if(typeof te!="string")throw new Error("value must be string");let xe=U.slice(0,a).map(h).join(",");return a===0?we("0u",te):a===1?we(xe[0],te):(m.set=!0,m.setByIndices=!0,m.indicesToOffset=!0,`set_${e}(${xe}, ${te})`)},setByOffset:we,setByIndices:(U,te)=>a<2?we(U,te):(m.setByIndices=!0,m.indicesToOffset=!0,`set_${e}ByIndices(${U}, ${te});`),get:le,getByOffset:re,getByIndices:Re,usage:n,name:e,strides:y,shape:$,rank:a}},F=(e,t,i,n=1)=>pi(e,t,i,"input",n),ae=(e,t,i,n=1)=>pi(e,t,i,"output",n),Ms=(e,t,i)=>pi(e,t,i,"atomicOutput",1),On=(e,t,i,n=1)=>pi(e,t,i,"internal",n),Ds=class{constructor(e,t){this.normalizedDispatchGroup=e,this.limits=t,this.internalVariables=[],this.variables=[],this.uniforms=[],this.variableIndex=0}guardAgainstOutOfBoundsWorkgroupSizes(e){return`if (global_idx >= ${typeof e=="number"?`${e}u`:e}) { return; }`}mainStart(e=ni){let t=typeof e=="number"?e:e[0],i=typeof e=="number"?1:e[1],n=typeof e=="number"?1:e[2];if(t>this.limits.maxComputeWorkgroupSizeX||i>this.limits.maxComputeWorkgroupSizeY||n>this.limits.maxComputeWorkgroupSizeZ)throw new Error(`workgroup size [${t}, ${i}, ${n}] exceeds the maximum workgroup size [${this.limits.maxComputeWorkgroupSizeX}, ${this.limits.maxComputeWorkgroupSizeY}, ${this.limits.maxComputeWorkgroupSizeZ}].`);if(t*i*n>this.limits.maxComputeInvocationsPerWorkgroup)throw new Error(`workgroup size [${t}, ${i}, ${n}] exceeds the maximum workgroup invocations ${this.limits.maxComputeInvocationsPerWorkgroup}.`);let r=this.normalizedDispatchGroup[1]===1&&this.normalizedDispatchGroup[2]===1,s=r?`@builtin(global_invocation_id) global_id : vec3<u32>,
    @builtin(workgroup_id) workgroup_id : vec3<u32>,
    @builtin(local_invocation_index) local_idx : u32,
    @builtin(local_invocation_id) local_id : vec3<u32>`:`@builtin(global_invocation_id) global_id : vec3<u32>,
                                             @builtin(local_invocation_id) local_id : vec3<u32>,
    @builtin(local_invocation_index) local_idx : u32,
    @builtin(workgroup_id) workgroup_id : vec3<u32>,
    @builtin(num_workgroups) num_workgroups : vec3<u32>`,a=r?`let global_idx = global_id.x;
         let workgroup_index = workgroup_id.x;`:`let workgroup_index = workgroup_id.z * num_workgroups[0] * num_workgroups[1] +
             workgroup_id.y * num_workgroups[0] + workgroup_id.x;
         let global_idx = workgroup_index * ${t*i*n}u + local_idx;`;return`@compute @workgroup_size(${t}, ${i}, ${n})
  fn main(${s}) {
    ${a}
  `}appendVariableUniforms(e){e.rank!==0&&(e.shape.startsWith("uniforms.")&&this.uniforms.push({name:e.shape.replace("uniforms.",""),type:"u32",length:e.rank}),e.strides.startsWith("uniforms.")&&this.uniforms.push({name:e.strides.replace("uniforms.",""),type:"u32",length:e.rank}))}declareVariable(e,t){if(e.usage==="internal")throw new Error("cannot use internal variable with declareVariable(). use registerInternalVariables() instead.");this.variables.push(e),this.appendVariableUniforms(e);let i=e.usage==="input"?"read":"read_write",n=e.usage==="atomicOutput"?"atomic<i32>":e.type.storage;return`@group(0) @binding(${t}) var<storage, ${i}> ${e.name}: array<${n}>;`}declareVariables(...e){return e.map(t=>this.declareVariable(t,this.variableIndex++)).join(`
`)}registerInternalVariable(e){if(e.usage!=="internal")throw new Error("cannot use input or output variable with registerInternalVariable(). use declareVariables() instead.");this.internalVariables.push(e),this.appendVariableUniforms(e)}registerInternalVariables(...e){return e.forEach(t=>this.registerInternalVariable(t)),this}registerUniform(e,t,i=1){return this.uniforms.push({name:e,type:t,length:i}),this}registerUniforms(e){return this.uniforms=this.uniforms.concat(e),this}uniformDeclaration(){if(this.uniforms.length===0)return"";let e=[];for(let{name:t,type:i,length:n}of this.uniforms)if(n&&n>4)i==="f16"?e.push(`@align(16) ${t}:array<mat2x4<${i}>, ${Math.ceil(n/8)}>`):e.push(`${t}:array<vec4<${i}>, ${Math.ceil(n/4)}>`);else{let r=n==null||n===1?i:`vec${n}<${i}>`;e.push(`${t}:${r}`)}return`
      struct Uniforms { ${e.join(", ")} };
      @group(0) @binding(${this.variableIndex}) var<uniform> uniforms: Uniforms;`}get additionalImplementations(){return this.uniformDeclaration()+this.variables.map(e=>e.impl()).join(`
`)+this.internalVariables.map(e=>e.impl()).join(`
`)}get variablesInfo(){if(this.uniforms.length===0)return;let e=t=>[12,10,1,6][["u32","f16","f32","i32"].indexOf(t)];return this.uniforms.map(t=>[e(t.type),t.length??1])}},Bs=(e,t)=>new Ds(e,t)}),Fs,Rn,Ns,Ps,Vs,Ls,_t,Us,qs,Ft=C(()=>{me(),be(),Je(),$e(),Fs=(e,t)=>{if(!e||e.length!==1)throw new Error("Transpose requires 1 input.");if(t.length!==0&&t.length!==e[0].dims.length)throw new Error(`perm size ${t.length} does not match input rank ${e[0].dims.length}`)},Rn=(e,t)=>t.length!==0?t:[...new Array(e).keys()].reverse(),Ns=(e,t)=>M.sortBasedOnPerm(e,Rn(e.length,t)),Ps=(e,t,i,n)=>{let r=`fn perm(i: ${n.type.indices}) -> ${i.type.indices} {
    var a: ${i.type.indices};`;for(let s=0;s<t;++s)r+=`a[${e[s]}]=i[${s}];`;return r+="return a;}"},Vs=(e,t)=>{let i=[],n=[];for(let r=0;r<e.length;++r)e[r]!==1&&i.push(e[r]),e[t[r]]!==1&&n.push(t[r]);return{newShape:i,newPerm:n}},Ls=(e,t)=>{let i=0;for(let n=0;n<e.length;++n)if(t[e[n]]!==1){if(e[n]<i)return!1;i=e[n]}return!0},_t=(e,t)=>{let i=e.dataType,n=e.dims.length,r=Rn(n,t),s=Ns(e.dims,r),a=e.dims,o=s,l=n<2||Ls(r,e.dims),u;if(l)return u=m=>{let _=F("input",i,a,4),$=ae("output",i,o,4);return`
  ${m.registerUniform("output_size","u32").declareVariables(_,$)}
  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    output[global_idx] = input[global_idx];
  }`},{name:"TransposeCopy",shaderCache:{inputDependencies:["type"]},getRunData:()=>{let m=M.size(s);return{outputs:[{dims:s,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(m/64/4)},programUniforms:[{type:12,data:Math.ceil(m/4)}]}},getShaderSource:u};let{newShape:d,newPerm:c}=Vs(e.dims,r),p=M.areEqual(c,[2,3,1]),h=M.areEqual(c,[3,1,2]);if(d.length===2||p||h){a=p?[d[0],d[1]*d[2]]:h?[d[0]*d[1],d[2]]:d,o=[a[1],a[0]];let m=16;return u=_=>{let $=F("a",i,a.length),y=ae("output",i,o.length);return`
  ${_.registerUniform("output_size","u32").declareVariables($,y)}
  var<workgroup> tile : array<array<${y.type.value}, ${m+1}>, ${m}>;
  ${_.mainStart([m,m,1])}
    let stride = (uniforms.output_shape[1] - 1) / ${m} + 1;
    let workgroup_id_x = workgroup_index % stride;
    let workgroup_id_y = workgroup_index / stride;
    let input_col = workgroup_id_y * ${m}u + local_id.x;
    let input_row = workgroup_id_x * ${m}u + local_id.y;
    if (input_row < uniforms.a_shape[0] && input_col < uniforms.a_shape[1]) {
      tile[local_id.y][local_id.x] = ${$.getByIndices(`${$.type.indices}(input_row, input_col)`)};
    }
    workgroupBarrier();

    let output_col = workgroup_id_x * ${m}u + local_id.x;
    let output_row = workgroup_id_y * ${m}u + local_id.y;
    if (output_row < uniforms.output_shape[0] && output_col < uniforms.output_shape[1]) {
      ${y.setByIndices(`${y.type.indices}(output_row, output_col)`,"tile[local_id.x][local_id.y]")}
    }
  }`},{name:"TransposeShared",shaderCache:{inputDependencies:["type"]},getRunData:()=>{let _=M.size(s);return{outputs:[{dims:s,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(o[1]/m),y:Math.ceil(o[0]/m)},programUniforms:[{type:12,data:_},...de(a,o)]}},getShaderSource:u}}return u=m=>{let _=F("a",i,a.length),$=ae("output",i,o.length);return`
  ${m.registerUniform("output_size","u32").declareVariables(_,$)}

  ${Ps(r,n,_,$)}

  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let indices = ${$.offsetToIndices("global_idx")};
    let aIndices = perm(indices);

    ${$.setByOffset("global_idx",_.getByIndices("aIndices"))}
  }`},{name:"Transpose",shaderCache:{hint:`${t}`,inputDependencies:["rank"]},getRunData:()=>{let m=M.size(s);return{outputs:[{dims:s,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(m/64)},programUniforms:[{type:12,data:m},...de(a,o)]}},getShaderSource:u}},Us=(e,t)=>{Fs(e.inputs,t.perm),e.compute(_t(e.inputs[0],t.perm))},qs=e=>Be({perm:e.perm})}),Ws,Gs,js,Hs,Ks,Qs,Zs,Xs,Ys,Js,vt,ea,ta,ia,na,ra,sa,aa,oa,la,ua,xp=C(()=>{me(),be(),$e(),Dn(),Ft(),Ws={max:"select(bestValue, candidate, candidate > bestValue)",min:"select(bestValue, candidate, candidate < bestValue)",mean:"bestValue + candidate",sum:"bestValue + candidate",prod:"bestValue * candidate",sumSquare:"bestValue + candidate * candidate",logSumExp:"bestValue + exp(candidate)",l1:"bestValue + abs(candidate)",l2:"bestValue + candidate * candidate",logSum:"bestValue + candidate"},Gs={max:"select(bestValue, candidate, candidate > bestValue)",min:"select(bestValue, candidate, candidate < bestValue)",mean:"bestValue + candidate",sum:"bestValue + candidate",prod:"bestValue * candidate",sumSquare:"bestValue + candidate",logSumExp:"bestValue + candidate",l1:"bestValue + candidate",l2:"bestValue + candidate",logSum:"bestValue + candidate"},js={max:"_A[offset]",min:"_A[offset]",mean:"0",sum:"0",prod:"1",sumSquare:"0",logSumExp:"0",l1:"0",l2:"0",logSum:"0"},Hs={max:"bestValue",min:"bestValue",sum:"bestValue",prod:"bestValue",sumSquare:"bestValue",logSumExp:"log(bestValue)",l1:"bestValue",l2:"sqrt(bestValue)",logSum:"log(bestValue)"},Ks=(e,t)=>{let i=[];for(let n=t-e;n<t;++n)i.push(n);return i},Qs=(e,t)=>{let i=[],n=e.length;for(let s=0;s<n;s++)t.indexOf(s)===-1&&i.push(e[s]);let r=t.map(s=>e[s]);return[i,r]},Zs=(e,t)=>{let i=e.length+t.length,n=[],r=0;for(let s=0;s<i;s++)t.indexOf(s)===-1?n.push(e[r++]):n.push(1);return n},Xs=(e,t)=>{for(let i=0;i<e.length;++i)if(e[e.length-i-1]!==t-1-i)return!1;return!0},Ys=(e,t)=>{let i=[];if(!Xs(e,t)){for(let n=0;n<t;++n)e.indexOf(n)===-1&&i.push(n);e.forEach(n=>i.push(n))}return i},Js=(e,t,i,n,r,s,a)=>{let o=i[0].dims,l=M.size(s),u=M.size(a),d=F("_A",i[0].dataType,o),c=ae("output",r,s),p=64;l===1&&(p=256);let h=`
          var<workgroup> aBestValues : array<f32, ${p}>;
       `,m=_=>`
        ${_.registerUniform("reduceSize","u32").declareVariables(d,c)}
        ${h}
        fn DIV_CEIL(a : u32, b : u32) -> u32 {
          return ((a - 1u) / b + 1u);
         }
         ${_.mainStart(p)}

          let outputIndex = global_idx / ${p};
          let offset = outputIndex * uniforms.reduceSize;

          var bestValue = f32(${js[n]});
          let Length = uniforms.reduceSize;
          for (var k = local_idx; k < Length; k = k + ${p}) {
           let candidate = f32(${d.getByOffset("offset + k")});
           bestValue = ${Ws[n]};
          }
          aBestValues[local_idx] = bestValue;
          workgroupBarrier();

         var reduceSize = min(Length, ${p}u);
         for (var currentSize = reduceSize / 2u; reduceSize > 1u;
             currentSize = reduceSize / 2u) {
           let interval = DIV_CEIL(reduceSize, 2u);
           if (local_idx < currentSize) {
            let candidate = aBestValues[local_idx + interval];
            bestValue = ${Gs[n]};
            aBestValues[local_idx] = bestValue;
           }
           reduceSize = interval;
           workgroupBarrier();
         }

         if (local_idx == 0u) {
          ${c.setByOffset("outputIndex",`${n==="mean"?`${c.type.storage}(bestValue / f32(uniforms.reduceSize))`:`${c.type.storage}(${Hs[n]})`}`)};
         }
        }`;return{name:e,shaderCache:{hint:`${t};${p}`,inputDependencies:["type"]},getShaderSource:m,getRunData:()=>({outputs:[{dims:s,dataType:r}],dispatchGroup:{x:l},programUniforms:[{type:12,data:u}]})}},vt=(e,t,i,n)=>{let r=e.inputs.length===1?i:Mn(e.inputs,i),s=r.axes;s.length===0&&!r.noopWithEmptyAxes&&(s=e.inputs[0].dims.map((h,m)=>m));let a=M.normalizeAxes(s,e.inputs[0].dims.length),o=a,l=e.inputs[0],u=Ys(o,e.inputs[0].dims.length);u.length>0&&(l=e.compute(_t(e.inputs[0],u),{inputs:[0],outputs:[-1]})[0],o=Ks(o.length,l.dims.length));let[d,c]=Qs(l.dims,o),p=d;r.keepDims&&(p=Zs(d,a)),e.compute(Js(t,r.cacheKey,[l],n,e.inputs[0].dataType,p,c),{inputs:[l]})},ea=(e,t)=>{vt(e,"ReduceMeanShared",t,"mean")},ta=(e,t)=>{vt(e,"ReduceL1Shared",t,"l1")},ia=(e,t)=>{vt(e,"ReduceL2Shared",t,"l2")},na=(e,t)=>{vt(e,"ReduceLogSumExpShared",t,"logSumExp")},ra=(e,t)=>{vt(e,"ReduceMaxShared",t,"max")},sa=(e,t)=>{vt(e,"ReduceMinShared",t,"min")},aa=(e,t)=>{vt(e,"ReduceProdShared",t,"prod")},oa=(e,t)=>{vt(e,"ReduceSumShared",t,"sum")},la=(e,t)=>{vt(e,"ReduceSumSquareShared",t,"sumSquare")},ua=(e,t)=>{vt(e,"ReduceLogSumShared",t,"logSum")}}),$t,da,Fi,Mn,xt,ca,pa,fa,ha,ma,ga,_a,ya,wa,ba,St,va,$a,xa,Sa,ka,Ta,Ca,Ea,Ia,Aa,Dn=C(()=>{me(),be(),Je(),$e(),xp(),$t=e=>{if(!e||e.length===0||e.length>2)throw new Error("Reduce op requires 1 or 2 inputs.");if(e.length===2&&e[1].dims.length!==1)throw new Error("Invalid axes input dims.")},da=e=>["","",`var value = ${e.getByIndices("input_indices")};`,""],Fi=(e,t,i,n,r,s,a=!1,o=!1)=>{let l=[],u=i[0].dims,d=u.length,c=M.normalizeAxes(r,d),p=!o&&c.length===0;u.forEach((_,$)=>{p||c.indexOf($)>=0?a&&l.push(1):l.push(_)});let h=l.length,m=M.size(l);return{name:e,shaderCache:t,getShaderSource:_=>{let $=[],y=F("_A",i[0].dataType,d),g=ae("output",s,h),T=n(y,g,c),x=T[2];for(let E=0,O=0;E<d;E++)p||c.indexOf(E)>=0?(a&&O++,x=`for(var j${E}: u32 = 0; j${E} < ${u[E]}; j${E}++) {
                  ${T[2].includes("last_index")?`let last_index = j${E};`:""}
                  ${y.indicesSet("input_indices",E,`j${E}`)}
                  ${x}
                }`):($.push(`${y.indicesSet("input_indices",E,g.indicesGet("output_indices",O))};`),O++);return`

        ${_.registerUniform("output_size","u32").declareVariables(y,g)}

        ${_.mainStart()}
          ${_.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
          var input_indices: ${y.type.indices};
          let output_indices = ${g.offsetToIndices("global_idx")};

          ${$.join(`
`)}
          ${T[0]}       // init ops for reduce max/min
          ${T[1]}
          ${x}
          ${T[3]}
          ${T.length===4?g.setByOffset("global_idx","value"):T.slice(4).join(`
`)}
        }`},getRunData:()=>({outputs:[{dims:l,dataType:s}],dispatchGroup:{x:Math.ceil(m/64)},programUniforms:[{type:12,data:m},...de(u,l)]})}},Mn=(e,t)=>{let i=[];return e[1].dims[0]>0&&e[1].getBigInt64Array().forEach(n=>i.push(Number(n))),Be({axes:i,keepDims:t.keepDims,noopWithEmptyAxes:t.noopWithEmptyAxes})},xt=(e,t,i,n)=>{let r=e.inputs,s=r.length===1?i:Mn(r,i);e.compute(Fi(t,{hint:s.cacheKey,inputDependencies:["rank"]},[r[0]],s.noopWithEmptyAxes&&s.axes.length===0?da:n,s.axes,r[0].dataType,s.keepDims,s.noopWithEmptyAxes),{inputs:[0]})},ca=(e,t)=>{$t(e.inputs),xt(e,"ReduceLogSum",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += ${i.getByIndices("input_indices")};`,"value = log(value);"])},pa=(e,t)=>{$t(e.inputs),xt(e,"ReduceL1",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += abs(${i.getByIndices("input_indices")});`,""])},fa=(e,t)=>{$t(e.inputs),xt(e,"ReduceL2",t,(i,n)=>[`var t = ${n.type.value}(0); var value = ${n.type.value}(0);`,"",`t = ${i.getByIndices("input_indices")}; value += (t * t);`,"value = sqrt(value);"])},ha=(e,t)=>{$t(e.inputs),xt(e,"ReduceLogSumExp",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += exp(${i.getByIndices("input_indices")});`,"value = log(value);"])},ma=(e,t)=>{$t(e.inputs),xt(e,"ReduceMax",t,(i,n,r)=>{let s=[];for(let a=0;a<i.rank;a++)(r.indexOf(a)>=0||r.length===0)&&s.push(i.indicesSet("input_indices",a,0));return[`${s.join(`
`)}`,`var value = ${i.getByIndices("input_indices")};`,`value = max(value, ${i.getByIndices("input_indices")});`,""]})},ga=(e,t)=>{$t(e.inputs),xt(e,"ReduceMean",t,(i,n,r)=>{let s=1;for(let a=0;a<i.rank;a++)(r.indexOf(a)>=0||r.length===0)&&(s*=e.inputs[0].dims[a]);return["var sum = f32(0);","",`sum += f32(${i.getByIndices("input_indices")});`,`let value = ${n.type.value}(sum / ${s});`]})},_a=(e,t)=>{$t(e.inputs),xt(e,"ReduceMin",t,(i,n,r)=>{let s=[];for(let a=0;a<i.rank;a++)(r.indexOf(a)>=0||r.length===0)&&s.push(`input_indices[${a}] = 0;`);return[`${s.join(`
`)}`,`var value = ${i.getByIndices("input_indices")};`,`value = min(value, ${i.getByIndices("input_indices")});`,""]})},ya=(e,t)=>{$t(e.inputs),xt(e,"ReduceProd",t,(i,n)=>[`var value = ${n.type.storage}(1);`,"",`value *= ${i.getByIndices("input_indices")};`,""])},wa=(e,t)=>{$t(e.inputs),xt(e,"ReduceSum",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += ${i.getByIndices("input_indices")};`,""])},ba=(e,t)=>{$t(e.inputs),xt(e,"ReduceSumSquare",t,(i,n)=>[`var t = ${n.type.value}(0); var value = ${n.type.value}(0);`,"",`t = ${i.getByIndices("input_indices")}; value += t * t;`,""])},St=(e,t,i)=>{if(t.length===0)return i;let n=1,r=1;for(let s=0;s<t.length;s++)t.indexOf(s)===-1?n*=e[s]:r*=e[s];return r<32&&n>1024},va=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ga(e,t):ea(e,t)},$a=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?pa(e,t):ta(e,t)},xa=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?fa(e,t):ia(e,t)},Sa=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ha(e,t):na(e,t)},ka=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ma(e,t):ra(e,t)},Ta=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?_a(e,t):sa(e,t)},Ca=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ya(e,t):aa(e,t)},Ea=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?wa(e,t):oa(e,t)},Ia=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ba(e,t):la(e,t)},Aa=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ca(e,t):ua(e,t)}}),Bn,za,Oa,Fn,Sp=C(()=>{me(),Je(),Dn(),Bn=e=>{if(!e||e.length===0||e.length>2)throw new Error("ArgMinMaxOp op requires 1 or 2 inputs.");if(e[0].dataType!==1)throw new Error("Invalid input type.")},za=(e,t)=>{Bn(e.inputs);let i=(n,r,s)=>{let a=[];for(let o=0;o<n.rank;o++)(s.indexOf(o)>=0||s.length===0)&&a.push(`input_indices[${o}] = 0;`);return[`${a.join(`
`)}`,`var value = ${n.getByIndices("input_indices")};
var best_index : i32 = 0;`,`if (${n.getByIndices("input_indices")} ${t.selectLastIndex>0?"<=":"<"} value) {
         value = ${n.getByIndices("input_indices")};
         best_index = i32(last_index);
       }`,"",r.setByOffset("global_idx","best_index")]};e.compute(Fi("ArgMin",{hint:t.cacheKey,inputDependencies:["rank"]},[e.inputs[0]],i,[t.axis],7,t.keepDims),{inputs:[0]})},Oa=(e,t)=>{Bn(e.inputs);let i=(n,r,s)=>{let a=[];for(let o=0;o<n.rank;o++)(s.indexOf(o)>=0||s.length===0)&&a.push(`input_indices[${o}] = 0;`);return[`${a.join(`
`)}`,`var value = ${n.getByIndices("input_indices")};
var best_index : i32 = 0;`,`if (${n.getByIndices("input_indices")} ${t.selectLastIndex>0?">=":">"} value) {
         value = ${n.getByIndices("input_indices")};
         best_index = i32(last_index);
       }`,"",r.setByOffset("global_idx","best_index")]};e.compute(Fi("argMax",{hint:t.cacheKey,inputDependencies:["rank"]},[e.inputs[0]],i,[t.axis],7,t.keepDims),{inputs:[0]})},Fn=e=>Be(e)}),Ra,Ni,Ma,Da,Ba,fi,Fa,Na,Nn=C(()=>{me(),be(),Cn(),$e(),Ra=(e,t)=>{let i=e[0],n=e[1],r=e[2],s=e[3],a=e[4],o=e[5];if(a&&o)throw new Error("Attention cannot have both past and attention_bias");if(i.dims.length!==3)throw new Error('Input "input" must have 3 dimensions');let l=i.dims[0],u=i.dims[1],d=i.dims[2];if(r.dims.length!==1)throw new Error('Input "bias" is expected to have 1 dimensions');if(n.dims.length!==2)throw new Error('Input "weights" is expected to have 2 dimensions');if(n.dims[0]!==d)throw new Error("Input 1 dimension 0 should have same length as dimension 2 of input 0");if(r.dims[0]!==n.dims[1])throw new Error('Input "bias" dimension 0 should have same length as dimension 1 of input "weights"');let c=r.dims[0]/3,p=c,h=p;if(t.qkvHiddenSizes.length>0){if(t.qkvHiddenSizes.length!==3)throw new Error("qkv_hidden_sizes attribute should have 3 elements");for(let T of t.qkvHiddenSizes)if(T%t.numHeads!==0)throw new Error("qkv_hidden_sizes should be divisible by num_heads");c=t.qkvHiddenSizes[0],p=t.qkvHiddenSizes[1],h=t.qkvHiddenSizes[2]}let m=u;if(c!==p)throw new Error("qkv_hidden_sizes first element should be same as the second");if(r.dims[0]!==c+p+h)throw new Error('Input "bias" dimension 0 should have same length as sum of Q/K/V hidden sizes');let _=0;if(a){if(p!==h)throw new Error('Input "past" expect k_hidden_size == v_hidden_size');if(a.dims.length!==5)throw new Error('Input "past" must have 5 dimensions');if(a.dims[0]!==2)throw new Error('Input "past" first dimension must be 2');if(a.dims[1]!==l)throw new Error('Input "past" second dimension must be batch_size');if(a.dims[2]!==t.numHeads)throw new Error('Input "past" third dimension must be num_heads');if(a.dims[4]!==p/t.numHeads)throw new Error('Input "past" fifth dimension must be k_hidden_size / num_heads');t.pastPresentShareBuffer||(_=a.dims[3])}let $=m+_,y=-1,g=0;if(s)throw new Error("Mask not supported");if(a)throw new Error("past is not supported");if(o){if(o.dims.length!==4)throw new Error('Input "attention_bias" must have 4 dimensions');if(o.dims[0]!==l||o.dims[1]!==t.numHeads||o.dims[2]!==u||o.dims[3]!==$)throw new Error('Expect "attention_bias" shape (batch_size, num_heads, sequence_length, total_sequence_length)')}return{batchSize:l,sequenceLength:u,pastSequenceLength:_,kvSequenceLength:m,totalSequenceLength:$,maxSequenceLength:y,inputHiddenSize:d,hiddenSize:c,vHiddenSize:h,headSize:Math.floor(c/t.numHeads),vHeadSize:Math.floor(h/t.numHeads),numHeads:t.numHeads,isUnidirectional:!1,pastPresentShareBuffer:!1,maskFilterValue:t.maskFilterValue,maskType:g,scale:t.scale,broadcastResPosBias:!1,passPastInKv:!1,qkvFormat:1}},Ni=(e,t,i)=>t&&e?`
      let total_sequence_length_input = u32(${t.getByOffset("0")});
      let present_sequence_length = max(total_sequence_length_input, uniforms.past_sequence_length);
      let is_subsequent_prompt: bool = sequence_length > 1 && sequence_length != total_sequence_length_input;
      let is_first_prompt: bool = is_subsequent_prompt == false && sequence_length == total_sequence_length_input;
      total_sequence_length = u32(${e?.getByOffset("batchIdx")}) + 1;
      var past_sequence_length: u32 = 0;
      if (is_first_prompt == false) {
        past_sequence_length = total_sequence_length - sequence_length;
      }
       `:`
    ${i?"let past_sequence_length = uniforms.past_sequence_length":""};
    let present_sequence_length = total_sequence_length;
    `,Ma=(e,t,i,n,r,s,a,o)=>{let l=Xe(a?1:s),u=64,d=s/l;d<u&&(u=32);let c=Math.ceil(s/l/u),p=[{type:12,data:t},{type:12,data:i},{type:12,data:n},{type:12,data:r},{type:12,data:d},{type:12,data:c}],h=at(e.dataType,l),m=dt(1,l),_=["type"];a&&_.push("type"),o&&_.push("type");let $=y=>{let g=ae("x",e.dataType,e.dims,l),T=[g],x=a?F("seq_lens",a.dataType,a.dims):void 0;x&&T.push(x);let E=o?F("total_sequence_length_input",o.dataType,o.dims):void 0;E&&T.push(E);let O=dt(e.dataType),z=[{name:"batch_size",type:"u32"},{name:"num_heads",type:"u32"},{name:"past_sequence_length",type:"u32"},{name:"sequence_length",type:"u32"},{name:"total_sequence_length",type:"u32"},{name:"elements_per_thread",type:"u32"}];return`
  var<workgroup> thread_max: array<f32, ${u}>;
  var<workgroup> thread_sum: array<f32, ${u}>;
  ${y.registerUniforms(z).declareVariables(...T)}
  ${y.mainStart([u,1,1])}
    let batchIdx = workgroup_id.z / uniforms.num_heads;
    let headIdx = workgroup_id.z % uniforms.num_heads;
    let sequence_length = uniforms.sequence_length;
    var total_sequence_length = uniforms.total_sequence_length;
    ${Ni(x,E,!1)}
    let local_offset = local_idx * uniforms.elements_per_thread;
    let offset = (global_idx / ${u}) * uniforms.total_sequence_length + local_offset;
    let seq_causal_length = ${a?"u32(past_sequence_length + workgroup_id.y + 1)":"total_sequence_length"};
    var thread_max_vector = ${m}(-3.402823e+38f);
    for (var i: u32 = 0; i < uniforms.elements_per_thread && i + local_offset < seq_causal_length; i++) {
      thread_max_vector = max(${m}(x[offset + i]), thread_max_vector);
    }
    thread_max[local_idx] = ${(()=>{switch(l){case 1:return"thread_max_vector";case 2:return"max(thread_max_vector.x, thread_max_vector.y)";case 4:return"max(max(thread_max_vector.x, thread_max_vector.y), max(thread_max_vector.z, thread_max_vector.w))";default:throw new Error(`Unsupported components: ${l}`)}})()};
    workgroupBarrier();

    var max_value =  f32(-3.402823e+38f);
    for (var i = 0u; i < ${u}; i++) {
      max_value = max(thread_max[i], max_value);
    }

    var sum_vector = ${m}(0);
    for (var i: u32 = 0; i < uniforms.elements_per_thread && i + local_offset < seq_causal_length; i++) {
      sum_vector += exp(${m}(x[offset + i]) - max_value);
    }
    thread_sum[local_idx] = ${(()=>{switch(l){case 1:return"sum_vector";case 2:return"sum_vector.x + sum_vector.y";case 4:return"sum_vector.x + sum_vector.y + sum_vector.z + sum_vector.w";default:throw new Error(`Unsupported components: ${l}`)}})()};
    workgroupBarrier();

    var sum: f32 = 0;
    for (var i = 0u; i < ${u}; i++) {
      sum += thread_sum[i];
    }

    if (sum == 0) {
      for (var i: u32 = 0; i < uniforms.elements_per_thread && i + local_offset < seq_causal_length; i++) {
        x[offset + i] = ${g.type.value}(${O}(1.0) / ${O}(seq_causal_length));
      }
    } else {
      for (var i: u32 = 0; i < uniforms.elements_per_thread && i + local_offset < seq_causal_length; i++) {
        var f32input = ${m}(x[offset + i]);
        x[offset + i] = ${g.type.value}(exp(f32input - max_value) / sum);
      }
    }
      ${a?`
        for (var total_seq_id: u32 = seq_causal_length; total_seq_id + local_offset < uniforms.total_sequence_length; total_seq_id++) {
          x[offset + total_seq_id] = ${g.type.value}(${O}(0));
        }`:""};
  }`};return{name:"AttentionProbsSoftmax",shaderCache:{hint:`${u};${h};${l}`,inputDependencies:_},getShaderSource:$,getRunData:()=>({outputs:[],dispatchGroup:{x:1,y:r,z:t*i},programUniforms:p})}},Da=(e,t,i,n,r,s,a,o,l)=>{let u=a+s.kvSequenceLength,d=[s.batchSize,s.numHeads,s.sequenceLength,u],c=e>1&&n,p=s.kvNumHeads?s.kvNumHeads:s.numHeads,h=c?[s.batchSize,p,u,s.headSize]:void 0,m=s.nReps?s.nReps:1,_=s.scale===0?1/Math.sqrt(s.headSize):s.scale,$=Xe(s.headSize),y=s.headSize/$,g=12,T={x:Math.ceil(u/g),y:Math.ceil(s.sequenceLength/g),z:s.batchSize*s.numHeads},x=[{type:12,data:s.sequenceLength},{type:12,data:y},{type:12,data:u},{type:12,data:s.numHeads},{type:12,data:s.headSize},{type:1,data:_},{type:12,data:a},{type:12,data:s.kvSequenceLength},{type:12,data:m}],E=c&&n&&M.size(n.dims)>0,O=["type","type"];E&&O.push("type"),r&&O.push("type"),o&&O.push("type"),l&&O.push("type");let z=[{dims:d,dataType:t.dataType,gpuDataType:0}];c&&z.push({dims:h,dataType:t.dataType,gpuDataType:0});let N=L=>{let ie=F("q",t.dataType,t.dims,$),ge=F("key",i.dataType,i.dims,$),ce=[ie,ge];if(E){let pe=F("past_key",n.dataType,n.dims,$);ce.push(pe)}r&&ce.push(F("attention_bias",r.dataType,r.dims));let we=o?F("seq_lens",o.dataType,o.dims):void 0;we&&ce.push(we);let re=l?F("total_sequence_length_input",l.dataType,l.dims):void 0;re&&ce.push(re);let ke=ae("output",t.dataType,d),he=[ke];c&&he.push(ae("present_key",t.dataType,h,$));let le=dt(1,$),Re=[{name:"M",type:"u32"},{name:"K",type:"u32"},{name:"N",type:"u32"},{name:"num_heads",type:"u32"},{name:"head_size",type:"u32"},{name:"alpha",type:"f32"},{name:"past_sequence_length",type:"u32"},{name:"kv_sequence_length",type:"u32"},{name:"n_reps",type:"u32"}];return`
  const TILE_SIZE = ${g}u;

  var<workgroup> tileQ: array<${ie.type.storage}, ${g*g}>;
  var<workgroup> tileK: array<${ie.type.storage}, ${g*g}>;
  ${L.registerUniforms(Re).declareVariables(...ce,...he)}
  ${L.mainStart([g,g,1])}
    // x holds the N and y holds the M
    let headIdx = workgroup_id.z % uniforms.num_heads;
    let kvHeadIdx = ${m===1?"headIdx":"headIdx / uniforms.n_reps"};
    let kv_num_heads = ${m===1?"uniforms.num_heads":"uniforms.num_heads / uniforms.n_reps"};
    let batchIdx = workgroup_id.z / uniforms.num_heads;
    let m = workgroup_id.y * TILE_SIZE;
    let n = workgroup_id.x * TILE_SIZE;
    let sequence_length = uniforms.M;
    var total_sequence_length = uniforms.N;
    ${Ni(we,re,!0)}
    let absKvHeadIdx = batchIdx * kv_num_heads + kvHeadIdx;
    let qOffset = workgroup_id.z * uniforms.M * uniforms.K + m * uniforms.K;
    ${E&&c?"let pastKeyOffset = absKvHeadIdx * uniforms.past_sequence_length * uniforms.K;":""};
    let kOffset = absKvHeadIdx * uniforms.kv_sequence_length * uniforms.K;
    ${c?"let presentKeyOffset = absKvHeadIdx * uniforms.N * uniforms.K;":""}
    var value = ${le}(0);
    for (var w: u32 = 0u; w < uniforms.K; w += TILE_SIZE) {
      if (global_id.y < uniforms.M && w + local_id.x < uniforms.K) {
        tileQ[TILE_SIZE * local_id.y + local_id.x] = q[qOffset + local_id.y * uniforms.K + w + local_id.x];
      }
      if (n + local_id.y < uniforms.N && w + local_id.x < uniforms.K) {
        var idx = TILE_SIZE * local_id.y + local_id.x;
      ${E&&c?`
              if (n + local_id.y < past_sequence_length) {
                tileK[idx] = past_key[pastKeyOffset + (n + local_id.y) * uniforms.K + w + local_id.x];
              } else if (n + local_id.y - past_sequence_length < uniforms.kv_sequence_length) {
                tileK[idx] = key[kOffset + (n + local_id.y - past_sequence_length) * uniforms.K + w + local_id.x];
              }`:`
          if (n + local_id.y < uniforms.kv_sequence_length) {
            tileK[idx] = key[kOffset + (n + local_id.y) * uniforms.K + w + local_id.x];
          }`}
      ${c?`if (n + local_id.y < present_sequence_length) {
        present_key[presentKeyOffset + (n + local_id.y) * uniforms.K + w + local_id.x] = tileK[idx];
      }`:""}
      }
      workgroupBarrier();

      for (var k: u32 = 0u; k < TILE_SIZE && w+k < uniforms.K; k++) {
          value += ${le}(tileQ[TILE_SIZE * local_id.y + k] * tileK[TILE_SIZE * local_id.x + k]);
      }

      workgroupBarrier();
    }

    if (global_id.y < uniforms.M && global_id.x < total_sequence_length) {
      let headOffset = workgroup_id.z * uniforms.M * uniforms.N;
      let outputIdx = headOffset + global_id.y * uniforms.N + global_id.x;
      var sum: f32 = ${(()=>{switch($){case 1:return"value";case 2:return"value.x + value.y";case 4:return"value.x + value.y + value.z + value.w";default:throw new Error(`Unsupported components: ${$}`)}})()};
        output[outputIdx] = ${ke.type.value} (sum * uniforms.alpha) + ${r?"attention_bias[outputIdx]":"0.0"};
    }
  }`};return{name:"AttentionProbs",shaderCache:{hint:`${$};${r!==void 0};${n!==void 0};${e}`,inputDependencies:O},getRunData:()=>({outputs:z,dispatchGroup:T,programUniforms:x}),getShaderSource:N}},Ba=(e,t,i,n,r,s,a=void 0,o=void 0)=>{let l=s+r.kvSequenceLength,u=r.nReps?r.nReps:1,d=r.vHiddenSize*u,c=e>1&&n,p=r.kvNumHeads?r.kvNumHeads:r.numHeads,h=c?[r.batchSize,p,l,r.headSize]:void 0,m=[r.batchSize,r.sequenceLength,d],_=12,$={x:Math.ceil(r.vHeadSize/_),y:Math.ceil(r.sequenceLength/_),z:r.batchSize*r.numHeads},y=[{type:12,data:r.sequenceLength},{type:12,data:l},{type:12,data:r.vHeadSize},{type:12,data:r.numHeads},{type:12,data:r.headSize},{type:12,data:d},{type:12,data:s},{type:12,data:r.kvSequenceLength},{type:12,data:u}],g=c&&n&&M.size(n.dims)>0,T=["type","type"];g&&T.push("type"),a&&T.push("type"),o&&T.push("type");let x=[{dims:m,dataType:t.dataType,gpuDataType:0}];c&&x.push({dims:h,dataType:t.dataType,gpuDataType:0});let E=O=>{let z=F("probs",t.dataType,t.dims),N=F("v",i.dataType,i.dims),L=[z,N];g&&L.push(F("past_value",n.dataType,n.dims));let ie=a?F("seq_lens",a.dataType,a.dims):void 0;a&&L.push(ie);let ge=o?F("total_sequence_length_input",o.dataType,o.dims):void 0;o&&L.push(ge);let ce=[ae("output",t.dataType,m)];c&&ce.push(ae("present_value",t.dataType,h));let we=[{name:"M",type:"u32"},{name:"K",type:"u32"},{name:"N",type:"u32"},{name:"num_heads",type:"u32"},{name:"head_size",type:"u32"},{name:"v_hidden_size",type:"u32"},{name:"past_sequence_length",type:"u32"},{name:"kv_sequence_length",type:"u32"},{name:"n_reps",type:"u32"}];return`
  const TILE_SIZE = ${_}u;
  var<workgroup> tileQ: array<${z.type.value}, ${_*_}>;
  var<workgroup> tileV: array<${z.type.value}, ${_*_}>;
  ${O.registerUniforms(we).declareVariables(...L,...ce)}
  ${O.mainStart([_,_,1])}
   let headIdx = workgroup_id.z % uniforms.num_heads;
   let batchIdx = workgroup_id.z / uniforms.num_heads;
   let kvHeadIdx = ${u===1?"headIdx":"headIdx / uniforms.n_reps"};
   let kv_num_heads = ${u===1?"uniforms.num_heads":"uniforms.num_heads / uniforms.n_reps"};
   let m = global_id.y;
   let n = global_id.x;
   let sequence_length = uniforms.M;
   var total_sequence_length = uniforms.K;
   ${Ni(ie,ge,!0)}
   let offsetA = workgroup_id.z * uniforms.M * uniforms.K + m * uniforms.K;
   let absKvHeadIdx = batchIdx * kv_num_heads + kvHeadIdx; // kvHeadIdx is relative to the batch
   ${g&&c?"let pastValueOffset = absKvHeadIdx * uniforms.N * uniforms.past_sequence_length + n;":""};
   let vOffset = absKvHeadIdx * uniforms.N * uniforms.kv_sequence_length + n;
   ${c?"let presentValueOffset = absKvHeadIdx * uniforms.N * uniforms.K + n;":""}
   var value = ${z.type.storage}(0);
   for (var w: u32 = 0u; w < uniforms.K; w += TILE_SIZE) {
      if (m < uniforms.M && w + local_id.x < uniforms.K) {
        tileQ[TILE_SIZE * local_id.y + local_id.x] = probs[offsetA + w + local_id.x];
      }
      if (n < uniforms.N && w + local_id.y < uniforms.K) {
        var idx = TILE_SIZE * local_id.y + local_id.x;
        ${g&&c?`
        if (w + local_id.y < past_sequence_length) {
          tileV[idx] = past_value[pastValueOffset + (w + local_id.y) * uniforms.N];
        } else if (w + local_id.y - past_sequence_length < uniforms.kv_sequence_length) {
          tileV[idx] = v[vOffset + (w + local_id.y - past_sequence_length) * uniforms.N];
        }
      `:`
            if (w + local_id.y < uniforms.kv_sequence_length) {
              tileV[idx] = v[vOffset + (w + local_id.y) * uniforms.N];
            }`}
        ${c?`
            if (w + local_id.y < present_sequence_length) {
          present_value[presentValueOffset + (w + local_id.y) * uniforms.N] = tileV[idx];
        }`:""}
      }
     workgroupBarrier();
     for (var k: u32 = 0u; k < TILE_SIZE && w+k < total_sequence_length; k++) {
       value += tileQ[TILE_SIZE * local_id.y + k] * tileV[TILE_SIZE * k + local_id.x];
     }
     workgroupBarrier();
   }

   // we need to transpose output from BNSH_v to BSND_v
   if (m < uniforms.M && n < uniforms.N) {
     let outputIdx = batchIdx * uniforms.M * uniforms.v_hidden_size + m * uniforms.v_hidden_size
       + headIdx * uniforms.N + n;
     output[outputIdx] = value;
   }
  }`};return{name:"AttentionScore",shaderCache:{hint:`${n!==void 0};${e}`,inputDependencies:T},getRunData:()=>({outputs:x,dispatchGroup:$,programUniforms:y}),getShaderSource:E}},fi=(e,t,i,n,r,s,a,o,l,u,d=void 0,c=void 0)=>{let p=Math.min(e.outputCount,1+(a?1:0)+(o?1:0)),h=p>1?u.pastSequenceLength:0,m=h+u.kvSequenceLength,_=l&&M.size(l.dims)>0?l:void 0,$=[t,i];p>1&&a&&M.size(a.dims)>0&&$.push(a),_&&$.push(_),d&&$.push(d),c&&$.push(c);let y=e.compute(Da(p,t,i,a,_,u,h,d,c),{inputs:$,outputs:p>1?[-1,1]:[-1]})[0];e.compute(Ma(y,u.batchSize,u.numHeads,h,u.sequenceLength,m,d,c),{inputs:d&&c?[y,d,c]:[y],outputs:[]});let g=[y,n];p>1&&o&&M.size(o.dims)>0&&g.push(o),d&&g.push(d),c&&g.push(c),e.compute(Ba(p,y,n,o,u,h,d,c),{inputs:g,outputs:p>1?[0,2]:[0]})},Fa=(e,t)=>{let i=[t.batchSize,t.numHeads,t.sequenceLength,t.headSize],n=t.sequenceLength,r=t.inputHiddenSize,s=t.headSize,a=12,o={x:Math.ceil(t.headSize/a),y:Math.ceil(t.sequenceLength/a),z:t.batchSize*t.numHeads},l=[e.inputs[0],e.inputs[1],e.inputs[2]],u=[{type:12,data:n},{type:12,data:r},{type:12,data:s},{type:12,data:t.numHeads},{type:12,data:t.headSize},{type:12,data:t.hiddenSize},{type:12,data:t.hiddenSize+t.hiddenSize+t.vHiddenSize}],d=c=>{let p=ae("output_q",l[0].dataType,i),h=ae("output_k",l[0].dataType,i),m=ae("output_v",l[0].dataType,i),_=F("input",l[0].dataType,l[0].dims),$=F("weight",l[1].dataType,l[1].dims),y=F("bias",l[2].dataType,l[2].dims),g=_.type.storage,T=[{name:"M",type:"u32"},{name:"K",type:"u32"},{name:"N",type:"u32"},{name:"num_heads",type:"u32"},{name:"head_size",type:"u32"},{name:"hidden_size",type:"u32"},{name:"ldb",type:"u32"}];return`
  const TILE_SIZE = ${a}u;
  var<workgroup> tileInput: array<${g}, ${a*a}>;
  var<workgroup> tileWeightQ: array<${g}, ${a*a}>;
  var<workgroup> tileWeightK: array<${g}, ${a*a}>;
  var<workgroup> tileWeightV: array<${g}, ${a*a}>;
  ${c.registerUniforms(T).declareVariables(_,$,y,p,h,m)}
  ${c.mainStart([a,a,1])}
    let batchIndex = workgroup_id.z / uniforms.num_heads;
    let headNumber = workgroup_id.z % uniforms.num_heads;
    let m = global_id.y;
    let n = global_id.x;

    let inputOffset = batchIndex * (uniforms.M * uniforms.K) + m * uniforms.K;
    let biasOffsetQ = headNumber * uniforms.head_size;
    let biasOffsetK = uniforms.hidden_size + biasOffsetQ;
    let biasOffsetV = uniforms.hidden_size + biasOffsetK;

    var valueQ = ${g}(0);
    var valueK = ${g}(0);
    var valueV = ${g}(0);
    for (var w: u32 = 0u; w < uniforms.K; w += TILE_SIZE) {
      if (m < uniforms.M && w + local_id.x < uniforms.K) {
        tileInput[TILE_SIZE * local_id.y + local_id.x] = input[inputOffset + w + local_id.x];
      }
      if (n < uniforms.N && w + local_id.y < uniforms.K) {
        let offset = n + (w + local_id.y) * uniforms.ldb;
        tileWeightQ[TILE_SIZE * local_id.y + local_id.x] = weight[biasOffsetQ + offset];
        tileWeightK[TILE_SIZE * local_id.y + local_id.x] = weight[biasOffsetK + offset];
        tileWeightV[TILE_SIZE * local_id.y + local_id.x] = weight[biasOffsetV + offset];
      }
      workgroupBarrier();
      for (var k: u32 = 0u; k<TILE_SIZE && w+k < uniforms.K; k++) {
        let inputTileOffset = TILE_SIZE * local_id.y + k;
        let weightTileOffset = TILE_SIZE * k + local_id.x;
        valueQ += tileInput[inputTileOffset] * tileWeightQ[weightTileOffset];
        valueK += tileInput[inputTileOffset] * tileWeightK[weightTileOffset];
        valueV += tileInput[inputTileOffset] * tileWeightV[weightTileOffset];
      }

      workgroupBarrier();
    }

    let headOffset = (m * uniforms.N + n) % uniforms.head_size;
    valueQ += bias[headOffset + biasOffsetQ];
    valueK += bias[headOffset + biasOffsetK];
    valueV += bias[headOffset + biasOffsetV];

    let offset = workgroup_id.z * uniforms.M * uniforms.N;
    if (m < uniforms.M && n < uniforms.N) {
      let outputIdx = offset + m * uniforms.N + n;
      output_q[outputIdx] = valueQ;
      output_k[outputIdx] = valueK;
      output_v[outputIdx] = valueV;
    }
  }`};return e.compute({name:"AttentionPrepare",shaderCache:{inputDependencies:["type","type","type"]},getRunData:()=>({outputs:[{dims:i,dataType:e.inputs[0].dataType,gpuDataType:0},{dims:i,dataType:e.inputs[0].dataType,gpuDataType:0},{dims:i,dataType:e.inputs[0].dataType,gpuDataType:0}],dispatchGroup:o,programUniforms:u}),getShaderSource:d},{inputs:l,outputs:[-1,-1,-1]})},Na=(e,t)=>{let i=Ra(e.inputs,t),[n,r,s]=Fa(e,i);return fi(e,n,r,s,e.inputs[4],void 0,void 0,void 0,e.inputs[5],i)}}),Pa,Va,La,Ua,kp=C(()=>{yt(),me(),be(),Je(),$e(),Pa=(e,t)=>{if(!e||e.length!==5)throw new Error("BatchNormalization requires 5 inputs");let i=(n,r,s)=>{let a=r.length;if(a!==n.length)throw new Error(`${s}: num dimensions != ${a}`);r.forEach((o,l)=>{if(o!==n[l])throw new Error(`${s}: dim[${l}] do not match`)})};if(e[0].dims.length>1){let n=t.format==="NHWC"?t.spatial?e[0].dims.slice(-1):e[0].dims.slice(-1).concat(e[0].dims.slice(1,e[0].dims.length-1)):e[0].dims.slice(1,t.spatial?2:void 0);i(e[1].dims,n,"Invalid input scale"),i(e[2].dims,n,"Invalid input B"),i(e[3].dims,n,"Invalid input mean"),i(e[4].dims,n,"Invalid input var")}else i(e[1].dims,[1],"Invalid input scale"),i(e[2].dims,[1],"Invalid input B"),i(e[3].dims,[1],"Invalid input mean"),i(e[4].dims,[1],"Invalid input var")},Va=(e,t)=>{let{epsilon:i,spatial:n,format:r}=t,s=e[0].dims,a=n?Xe(s[s.length-1]):1,o=r==="NHWC"&&s.length>1?a:1,l=M.size(s)/a,u=n,d=u?s.length:s,c=F("x",e[0].dataType,e[0].dims,a),p=F("scale",e[1].dataType,e[1].dims,o),h=F("bias",e[2].dataType,e[2].dims,o),m=F("inputMean",e[3].dataType,e[3].dims,o),_=F("inputVar",e[4].dataType,e[4].dims,o),$=ae("y",e[0].dataType,d,a),y=()=>{let T="";if(n)T=`let cOffset = ${s.length===1?"0u":r==="NHWC"?`outputIndices[${s.length-1}] / ${a}`:"outputIndices[1]"};`;else if(r==="NCHW")T=`
            ${$.indicesSet("outputIndices","0","0")}
            let cOffset = ${$.indicesToOffset("outputIndices")};`;else{T=`var cIndices = ${p.type.indices}(0);
                       cIndices[0] = outputIndices[${s.length-1}];`;for(let x=1;x<p.rank;x++)T+=`cIndices[${x}] = outputIndices[${x}];`;T+=`let cOffset = ${p.indicesToOffset("cIndices")};`}return T},g=T=>`
  const epsilon = ${i};
  ${T.registerUniform("outputSize","u32").declareVariables(c,p,h,m,_,$)}
  ${T.mainStart()}
  ${T.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
    var outputIndices = ${$.offsetToIndices(`global_idx * ${a}`)};
    ${y()}
    let scale = ${p.getByOffset("cOffset")};
    let bias = ${h.getByOffset("cOffset")};
    let inputMean = ${m.getByOffset("cOffset")};
    let inputVar = ${_.getByOffset("cOffset")};
    let x = ${c.getByOffset("global_idx")};
    let value = (x - inputMean) * inverseSqrt(inputVar + epsilon) * scale + bias;
    ${$.setByOffset("global_idx","value")}
  }`;return{name:"BatchNormalization",shaderCache:{hint:`${t.epsilon}_${t.format}_${n}_${a}`,inputDependencies:u?["rank","type","type","type","type"]:void 0},getShaderSource:g,getRunData:()=>({outputs:[{dims:e[0].dims,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:u?[{type:12,data:l},...de(s)]:[{type:12,data:l}]})}},La=e=>Be(e),Ua=(e,t)=>{let{inputs:i,outputCount:n}=e,r=La({...t,outputCount:n});if(ne.webgpu.validateInputContent&&Pa(i,r),t.trainingMode)throw new Error("BatchNormalization trainingMode is not supported yet.");e.compute(Va(i,r))}}),qa,Wa,Ga,Tp=C(()=>{be(),$e(),qa=e=>{if(e[0].dims.length!==3)throw new Error("input should have 3 dimensions");if(![320,640,1280].includes(e[0].dims[2]))throw new Error("number of channels should be 320, 640 or 1280");if(e[1].dims.length!==1)throw new Error("bias is expected to have 1 dimensions");if(e[0].dims[2]!==e[1].dims[0])throw new Error("last dimension of input and bias are not the same")},Wa=e=>{let t=e[0].dims,i=e[0].dims[2],n=M.size(t)/4,r=e[0].dataType,s=F("input",r,t,4),a=F("bias",r,[i],4),o=F("residual",r,t,4),l=ae("output",r,t,4);return{name:"BiasAdd",getRunData:()=>({outputs:[{dims:t,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(n/64)}}),getShaderSource:u=>`
  const channels = ${i}u / 4;
  ${u.declareVariables(s,a,o,l)}

  ${u.mainStart()}
    ${u.guardAgainstOutOfBoundsWorkgroupSizes(n)}
    let value = ${s.getByOffset("global_idx")}
      + ${a.getByOffset("global_idx % channels")} + ${o.getByOffset("global_idx")};
    ${l.setByOffset("global_idx","value")}
  }`}},Ga=e=>{qa(e.inputs),e.compute(Wa(e.inputs))}}),ja,Oe,Ha,Ka,Qa,Za,Xa,Ya,Ja,eo,to,io,no,ro,so,ao,hi,oo,Pi,lo,uo,co,po,fo,ho,mo,go,_o,yo,wo,bo,vo,$o,xo,So,Pn,ko,Vn,Ln,To,Co,Eo,Io,Ao,zo,Un=C(()=>{me(),be(),Je(),$e(),ja=(e,t,i,n,r,s,a)=>{let o=Math.ceil(t/4),l="";typeof r=="string"?l=`${r}(a)`:l=r("a");let u=F("inputData",i,[o],4),d=ae("outputData",n,[o],4),c=[{name:"vec_size",type:"u32"}];return a&&c.push(...a),`
      ${e.registerUniforms(c).declareVariables(u,d)}

  ${s??""}

  ${e.mainStart()}
    ${e.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.vec_size")}

    let a = ${u.getByOffset("global_idx")};
    ${d.setByOffset("global_idx",l)}
  }`},Oe=(e,t,i,n,r,s=e.dataType,a,o)=>{let l=[{type:12,data:Math.ceil(M.size(e.dims)/4)}];return a&&l.push(...a),{name:t,shaderCache:{hint:r,inputDependencies:["type"]},getShaderSource:u=>ja(u,M.size(e.dims),e.dataType,s,i,n,o),getRunData:u=>({outputs:[{dims:e.dims,dataType:s}],dispatchGroup:{x:Math.ceil(M.size(u[0].dims)/64/4)},programUniforms:l})}},Ha=e=>{e.compute(Oe(e.inputs[0],"Abs","abs"))},Ka=e=>{e.compute(Oe(e.inputs[0],"Acos","acos"))},Qa=e=>{e.compute(Oe(e.inputs[0],"Acosh","acosh"))},Za=e=>{e.compute(Oe(e.inputs[0],"Asin","asin"))},Xa=e=>{e.compute(Oe(e.inputs[0],"Asinh","asinh"))},Ya=e=>{e.compute(Oe(e.inputs[0],"Atan","atan"))},Ja=e=>{e.compute(Oe(e.inputs[0],"Atanh","atanh"))},eo=e=>Be(e),to=(e,t)=>{let i;switch(t.to){case 10:i="vec4<f16>";break;case 1:i="vec4<f32>";break;case 12:i="vec4<u32>";break;case 6:i="vec4<i32>";break;case 9:i="vec4<bool>";break;default:throw new RangeError(`not supported type (specified in attribute 'to' from 'Cast' operator): ${t.to}`)}e.compute(Oe(e.inputs[0],"Cast",i,void 0,t.cacheKey,t.to))},io=e=>{let t,i,n=e.length>=2&&e[1].data!==0,r=e.length>=3&&e[2].data!==0;switch(e[0].dataType){case 1:t=n?e[1].getFloat32Array()[0]:-34028234663852886e22,i=r?e[2].getFloat32Array()[0]:34028234663852886e22;break;case 10:t=n?e[1].getUint16Array()[0]:64511,i=r?e[2].getUint16Array()[0]:31743;break;default:throw new Error("Unsupport data type")}return Be({min:t,max:i})},no=(e,t)=>{let i=t||io(e.inputs),n=dt(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Clip",r=>`clamp(${r}, vec4<${n}>(uniforms.min), vec4<${n}>(uniforms.max))`,void 0,i.cacheKey,void 0,[{type:e.inputs[0].dataType,data:i.min},{type:e.inputs[0].dataType,data:i.max}],[{name:"min",type:n},{name:"max",type:n}]),{inputs:[0]})},ro=e=>{e.compute(Oe(e.inputs[0],"Ceil","ceil"))},so=e=>{e.compute(Oe(e.inputs[0],"Cos","cos"))},ao=e=>{e.compute(Oe(e.inputs[0],"Cosh","cosh"))},hi=e=>Be(e),oo=(e,t)=>{let i=dt(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Elu",n=>`elu_vf32(${n})`,`
  const elu_alpha_ = ${i}(${t.alpha});

  fn elu_f32(a: ${i}) -> ${i} {
  return select((exp(a) - 1.0) * elu_alpha_, a, a >= 0.0);
  }

  fn elu_vf32(v: vec4<${i}>) -> vec4<${i}> {
  return vec4(elu_f32(v.x), elu_f32(v.y), elu_f32(v.z), elu_f32(v.w));
  }`,t.cacheKey))},Pi=(e="f32")=>`
const r0: ${e} = 0.3275911;
const r1: ${e} = 0.254829592;
const r2: ${e} = -0.284496736;
const r3: ${e} = 1.421413741;
const r4: ${e} = -1.453152027;
const r5: ${e} = 1.061405429;

fn erf_vf32(v: vec4<${e}>) -> vec4<${e}> {
  let absv = abs(v);
  let x = 1.0 / (1.0 + r0 * absv);
  return sign(v) * (1.0 - ((((r5 * x + r4) * x + r3) * x + r2) * x + r1) * x * exp(-absv * absv));
}`,lo=e=>{let t=dt(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Erf",i=>`erf_vf32(${i})`,Pi(t)))},uo=e=>{e.compute(Oe(e.inputs[0],"Exp","exp"))},co=e=>{e.compute(Oe(e.inputs[0],"Floor","floor"))},po=e=>{let t=dt(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Gelu",i=>`0.5 * ${i} * (1.0 + erf_vf32(${i} * 0.7071067811865475))`,Pi(t)))},fo=(e,t)=>{let i=dt(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"LeakyRelu",n=>`select(leaky_relu_alpha_ * ${n}, ${n}, ${n} >= vec4<${i}>(0.0))`,`const leaky_relu_alpha_ = ${i}(${t.alpha});`,t.cacheKey))},ho=e=>{e.compute(Oe(e.inputs[0],"Not",t=>`!${t}`))},mo=e=>{e.compute(Oe(e.inputs[0],"Neg",t=>`-${t}`))},go=e=>{e.compute(Oe(e.inputs[0],"Reciprocal",t=>`1.0/${t}`))},_o=e=>{let t=dt(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Relu",i=>`select(vec4<${t}>(0.0), ${i}, ${i} > vec4<${t}>(0.0))`))},yo=e=>{e.compute(Oe(e.inputs[0],"Sigmoid",t=>`(1.0 / (1.0 + exp(-${t})))`))},wo=e=>Be(e),bo=(e,t)=>{let i=dt(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"HardSigmoid",n=>`max(vec4<${i}>(0.0), min(vec4<${i}>(1.0), ${t.alpha} * ${n} + vec4<${i}>(${t.beta})))`,void 0,t.cacheKey))},vo=e=>{e.compute(Oe(e.inputs[0],"Sin","sin"))},$o=e=>{e.compute(Oe(e.inputs[0],"Sinh","sinh"))},xo=e=>{e.compute(Oe(e.inputs[0],"Sqrt","sqrt"))},So=e=>{e.compute(Oe(e.inputs[0],"Tan","tan"))},Pn=e=>`sign(${e}) * (1 - exp(-2 * abs(${e}))) / (1 + exp(-2 * abs(${e})))`,ko=e=>{e.compute(Oe(e.inputs[0],"Tanh",Pn))},Vn=(e="f32")=>`
const fast_gelu_a: ${e} = 0.5;
const fast_gelu_b: ${e} = 0.7978845608028654;
const fast_gelu_c: ${e} = 0.035677408136300125;

fn tanh_v(v: vec4<${e}>) -> vec4<${e}> {
  return ${Pn("v")};
}
`,Ln=e=>`(fast_gelu_a + fast_gelu_a * tanh_v(${e} * (fast_gelu_c * ${e} * ${e} + fast_gelu_b))) * ${e}`,To=e=>{let t=dt(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"FastGelu",Ln,Vn(t),void 0,e.inputs[0].dataType))},Co=(e,t)=>{let i=dt(e.inputs[0].dataType);return e.compute(Oe(e.inputs[0],"ThresholdedRelu",n=>`select(vec4<${i}>(0.0), ${n}, ${n} > thresholded_relu_alpha_)`,`const thresholded_relu_alpha_ = vec4<${i}>(${t.alpha});`,t.cacheKey)),0},Eo=e=>{e.compute(Oe(e.inputs[0],"Log","log"))},Io=(e,t)=>`
const alpha = vec4<${e}>(${t});
const one = ${e}(1.0);
const zero = ${e}(0.0);

fn quick_gelu_impl(x: vec4<${e}>) -> vec4<${e}> {
  let v = x *alpha;
  var x1 : vec4<${e}>;
  for (var i = 0; i < 4; i = i + 1) {
    if (v[i] >= zero) {
      x1[i] = one / (one + exp(-v[i]));
    } else {
      x1[i] = one - one / (one + exp(v[i]));
    }
  }
  return x * x1;
}
`,Ao=e=>`quick_gelu_impl(${e})`,zo=(e,t)=>{let i=dt(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"QuickGelu",Ao,Io(i,t.alpha),t.cacheKey,e.inputs[0].dataType))}}),Oo,Ro,Mo,Cp=C(()=>{be(),$e(),Un(),Oo=e=>{if(e[0].dims.length!==3)throw new Error("input should have 3 dimensions");if(![2560,5120,10240].includes(e[0].dims[2]))throw new Error("hidden state should be 2560, 5120 or 10240");if(e[1].dims.length!==1)throw new Error("bias is expected to have 1 dimensions");if(e[0].dims[2]!==e[1].dims[0])throw new Error("last dimension of input and bias are not the same")},Ro=e=>{let t=e[0].dims.slice();t[2]=t[2]/2;let i=F("input",e[0].dataType,e[0].dims,4),n=F("bias",e[0].dataType,[e[0].dims[2]],4),r=ae("output",e[0].dataType,t,4),s=M.size(t)/4,a=at(e[0].dataType);return{name:"BiasSplitGelu",getRunData:()=>({outputs:[{dims:t,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(s/64)}}),getShaderSource:o=>`
  const M_SQRT2 = sqrt(2.0);
  const halfChannels = ${e[0].dims[2]/4/2}u;

  ${o.declareVariables(i,n,r)}

  ${Pi(a)}

  ${o.mainStart()}
    ${o.guardAgainstOutOfBoundsWorkgroupSizes(s)}
    let biasIdx = global_idx % halfChannels;
    let batchIndex = global_idx / halfChannels;
    let inputOffset = biasIdx + batchIndex * halfChannels * 2;
    let valueLeft = input[inputOffset] + bias[biasIdx];
    let valueRight = input[inputOffset + halfChannels] + bias[biasIdx + halfChannels];
    let geluRight = valueRight * 0.5 * (erf_vf32(valueRight / M_SQRT2) + 1);

    ${r.setByOffset("global_idx","valueLeft * geluRight")}
  }`}},Mo=e=>{Oo(e.inputs),e.compute(Ro(e.inputs))}}),Do,Bo,kt,Fo,No,Po,Vo,Lo,Uo,qo,Wo,Go,jo,Ep=C(()=>{me(),be(),$e(),Do=(e,t,i,n,r,s,a,o,l,u,d,c)=>{let p,h;typeof o=="string"?p=h=(g,T)=>`${o}((${g}),(${T}))`:typeof o=="function"?p=h=o:(p=o.scalar,h=o.vector);let m=ae("outputData",d,n.length,4),_=F("aData",l,t.length,4),$=F("bData",u,i.length,4),y;if(r)if(s){let g=M.size(t)===1,T=M.size(i)===1,x=t.length>0&&t[t.length-1]%4===0,E=i.length>0&&i[i.length-1]%4===0;g||T?y=m.setByOffset("global_idx",h(g?`${_.type.value}(${_.getByOffset("0")}.x)`:_.getByOffset("global_idx"),T?`${$.type.value}(${$.getByOffset("0")}.x)`:$.getByOffset("global_idx"))):y=`
            let outputIndices = ${m.offsetToIndices("global_idx * 4u")};
            let offsetA = ${_.broadcastedIndicesToOffset("outputIndices",m)};
            let offsetB = ${$.broadcastedIndicesToOffset("outputIndices",m)};
            ${m.setByOffset("global_idx",h(a||x?_.getByOffset("offsetA / 4u"):`${_.type.value}(${_.getByOffset("offsetA / 4u")}[offsetA % 4u])`,a||E?$.getByOffset("offsetB / 4u"):`${$.type.value}(${$.getByOffset("offsetB / 4u")}[offsetB % 4u])`))}
          `}else y=m.setByOffset("global_idx",h(_.getByOffset("global_idx"),$.getByOffset("global_idx")));else{if(!s)throw new Error("no necessary to use scalar implementation for element-wise binary op implementation.");let g=(T,x,E="")=>{let O=`aData[indexA${x}][componentA${x}]`,z=`bData[indexB${x}][componentB${x}]`;return`
            let outputIndices${x} = ${m.offsetToIndices(`global_idx * 4u + ${x}u`)};
            let offsetA${x} = ${_.broadcastedIndicesToOffset(`outputIndices${x}`,m)};
            let offsetB${x} = ${$.broadcastedIndicesToOffset(`outputIndices${x}`,m)};
            let indexA${x} = offsetA${x} / 4u;
            let indexB${x} = offsetB${x} / 4u;
            let componentA${x} = offsetA${x} % 4u;
            let componentB${x} = offsetB${x} % 4u;
            ${T}[${x}] = ${E}(${p(O,z)});
          `};d===9?y=`
            var data = vec4<u32>(0);
            ${g("data",0,"u32")}
            ${g("data",1,"u32")}
            ${g("data",2,"u32")}
            ${g("data",3,"u32")}
            outputData[global_idx] = dot(vec4<u32>(0x1, 0x100, 0x10000, 0x1000000), vec4<u32>(data));`:y=`
            ${g("outputData[global_idx]",0)}
            ${g("outputData[global_idx]",1)}
            ${g("outputData[global_idx]",2)}
            ${g("outputData[global_idx]",3)}
          `}return`
        ${e.registerUniform("vec_size","u32").declareVariables(_,$,m)}

        ${c??""}

        ${e.mainStart()}
        ${e.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.vec_size")}
        ${y}
      }`},Bo=(e,t,i,n,r,s,a=i.dataType)=>{let o=i.dims.map(_=>Number(_)??1),l=n.dims.map(_=>Number(_)??1),u=!M.areEqual(o,l),d=o,c=M.size(o),p=!1,h=!1,m=[u];if(u){let _=ii.calcShape(o,l,!1);if(!_)throw new Error("Can't perform binary op on the given tensors");d=_.slice(),c=M.size(d);let $=M.size(o)===1,y=M.size(l)===1,g=o.length>0&&o[o.length-1]%4===0,T=l.length>0&&l[l.length-1]%4===0;m.push($),m.push(y),m.push(g),m.push(T);let x=1;for(let E=1;E<d.length;E++){let O=o[o.length-E],z=l[l.length-E];if(O===z)x*=O;else break}x%4===0?(h=!0,p=!0):($||y||g||T)&&(p=!0)}else p=!0;return m.push(p),{name:e,shaderCache:{hint:t+m.map(_=>_.toString()).join("_"),inputDependencies:["rank","rank"]},getShaderSource:_=>Do(_,o,l,d,p,u,h,r,i.dataType,n.dataType,a,s),getRunData:()=>({outputs:[{dims:d,dataType:a}],dispatchGroup:{x:Math.ceil(c/64/4)},programUniforms:[{type:12,data:Math.ceil(M.size(d)/4)},...de(o,l,d)]})}},kt=(e,t,i,n,r,s)=>{e.compute(Bo(t,r??"",e.inputs[0],e.inputs[1],i,n,s))},Fo=e=>{kt(e,"Add",(t,i)=>`${t}+${i}`)},No=e=>{kt(e,"Div",(t,i)=>`${t}/${i}`)},Po=e=>{kt(e,"Equal",{scalar:(t,i)=>`u32(${t}==${i})`,vector:(t,i)=>`vec4<u32>(${t}==${i})`},void 0,void 0,9)},Vo=e=>{kt(e,"Mul",(t,i)=>`${t}*${i}`)},Lo=e=>{let t=F("input",e.inputs[0].dataType,e.inputs[0].dims).type.value;kt(e,"Pow",{scalar:(i,n)=>`pow_custom(${i},${n})`,vector:(i,n)=>`pow_vector_custom(${i},${n})`},`
    fn pow_custom(a : ${t}, b : ${t}) -> ${t} {
      if (b == ${t}(0.0)) {
        return ${t}(1.0);
      } else if (a < ${t}(0.0) && f32(b) != floor(f32(b))) {
        return ${t}(pow(f32(a), f32(b))); // NaN
      }
      return select(sign(a), ${t}(1.0), round(f32(abs(b) % ${t}(2.0))) != 1.0) * ${t}(${t==="i32"?"round":""}(pow(f32(abs(a)), f32(b))));
    }
    fn pow_vector_custom(a : vec4<${t}>, b : vec4<${t}>) -> vec4<${t}> {
      // TODO: implement vectorized pow
      return vec4<${t}>(pow_custom(a.x, b.x), pow_custom(a.y, b.y), pow_custom(a.z, b.z), pow_custom(a.w, b.w));
    }
      `)},Uo=e=>{kt(e,"Sub",(t,i)=>`${t}-${i}`)},qo=e=>{kt(e,"Greater",{scalar:(t,i)=>`u32(${t}>${i})`,vector:(t,i)=>`vec4<u32>(${t}>${i})`},void 0,void 0,9)},Wo=e=>{kt(e,"Less",{scalar:(t,i)=>`u32(${t}<${i})`,vector:(t,i)=>`vec4<u32>(${t}<${i})`},void 0,void 0,9)},Go=e=>{kt(e,"GreaterOrEqual",{scalar:(t,i)=>`u32(${t}>=${i})`,vector:(t,i)=>`vec4<u32>(${t}>=${i})`},void 0,void 0,9)},jo=e=>{kt(e,"LessOrEqual",{scalar:(t,i)=>`u32(${t}<=${i})`,vector:(t,i)=>`vec4<u32>(${t}<=${i})`},void 0,void 0,9)}}),Ho,Ko,Qo,Zo,Xo,Yo,Ip=C(()=>{me(),be(),Je(),$e(),Ho=(e,t)=>{if(!e||e.length<1)throw new Error("too few inputs");let i=0,n=e[i],r=n.dataType,s=n.dims.length;e.forEach((a,o)=>{if(o!==i){if(a.dataType!==r)throw new Error("input tensors should be one type");if(a.dims.length!==s)throw new Error("input tensors should have the same shape");a.dims.forEach((l,u)=>{if(u!==t&&l!==n.dims[u])throw new Error("non concat dimensions must match")})}})},Ko=(e,t)=>`
  fn calculateInputIndex(index: u32) -> u32 {
    let sizeInConcatAxis = array<u32, ${e}u>(${t});
    for (var i: u32 = 0u; i < ${e}; i += 1u ) {
      if (index < sizeInConcatAxis[i]) {
        return i;
      }
    }
    return ${e}u;
  }`,Qo=(e,t)=>{let i=e.length,n=[];for(let r=0;r<i;++r){let s=t.setByOffset("global_idx",e[r].getByIndices("indices"));i===1?n.push(s):r===0?n.push(`if (inputIndex == ${r}u) { ${s} }`):r===i-1?n.push(`else { ${s} }`):n.push(`else if (inputIndex == ${r}) { ${s} }`)}return n.join(`
`)},Zo=(e,t,i,n)=>{let r=M.size(i),s=new Array(e.length),a=new Array(e.length),o=0,l=[],u=[],d=[{type:12,data:r}];for(let _=0;_<e.length;++_)o+=e[_].dims[t],s[_]=o,u.push(e[_].dims.length),a[_]=F(`input${_}`,n,u[_]),l.push("rank"),d.push({type:12,data:s[_]});for(let _=0;_<e.length;++_)d.push(...de(e[_].dims));d.push(...de(i));let c=ae("output",n,i.length),p=c.indicesGet("indices",t),h=Array.from(Array(s.length).keys()).map(_=>`uniforms.sizeInConcatAxis${_}`).join(","),m=_=>`

  ${(()=>{_.registerUniform("outputSize","u32");for(let $=0;$<e.length;$++)_.registerUniform(`sizeInConcatAxis${$}`,"u32");return _.declareVariables(...a,c)})()}

  ${Ko(s.length,h)}

  ${_.mainStart()}
    ${_.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}

    var indices = ${c.offsetToIndices("global_idx")};

    let inputIndex = calculateInputIndex(${p});
    if (inputIndex != 0u) {
      let sizeInConcatAxis = array<u32, ${s.length}u>(${h});
      ${p} -= sizeInConcatAxis[inputIndex - 1u];
    }

    ${Qo(a,c)}
  }`;return{name:"Concat",shaderCache:{hint:`${t}`,inputDependencies:l},getRunData:()=>({outputs:[{dims:i,dataType:n}],dispatchGroup:{x:Math.ceil(r/64)},programUniforms:d}),getShaderSource:m}},Xo=(e,t)=>{let i=e.inputs,n=i[0].dims,r=M.normalizeAxis(t.axis,n.length);Ho(i,r);let s=n.slice();s[r]=i.reduce((o,l)=>o+(l.dims.length>r?l.dims[r]:0),0);let a=i.filter(o=>M.size(o.dims)>0);e.compute(Zo(a,r,s,i[0].dataType),{inputs:a})},Yo=e=>Be({axis:e.axis})}),Wt,Gt,jt,qn,Ht=C(()=>{me(),be(),Wt=(e,t,i="f32")=>{switch(e.activation){case"Relu":return`value = max(value, ${t}(0.0));`;case"Sigmoid":return`value = (${t}(1.0) / (${t}(1.0) + exp(-value)));`;case"Clip":return`value = clamp(value, ${t}(${i}(uniforms.clip_min)), ${t}(${i}(uniforms.clip_max)));`;case"HardSigmoid":return`value = max(${t}(0.0), min(${t}(1.0), ${i}(uniforms.alpha) * value + ${i}(uniforms.beta)));`;case"LeakyRelu":return`value = select(${i}(uniforms.alpha) * value, value, value >= ${t}(0.0));`;case"Tanh":return`let e2x = exp(-2.0 * abs(value));
              value = sign(value) * (1.0 - e2x) / (1.0 + e2x);
        `;case"":return"";default:throw new Error(`Unsupported activation ${e.activation}`)}},Gt=(e,t)=>{e.activation==="Clip"?t.push({type:1,data:e.clipMax},{type:1,data:e.clipMin}):e.activation==="HardSigmoid"?t.push({type:1,data:e.alpha},{type:1,data:e.beta}):e.activation==="LeakyRelu"&&t.push({type:1,data:e.alpha})},jt=(e,t)=>{e.activation==="Clip"?t.push({name:"clip_max",type:"f32"},{name:"clip_min",type:"f32"}):e.activation==="HardSigmoid"?t.push({name:"alpha",type:"f32"},{name:"beta",type:"f32"}):e.activation==="LeakyRelu"&&t.push({name:"alpha",type:"f32"})},qn=e=>{let t=e?.activation||"";if(t==="HardSigmoid"){let[i,n]=e?.activation_params||[.2,.5];return{activation:t,alpha:i,beta:n}}else if(t==="Clip"){let[i,n]=e?.activation_params||[bs,vs];return{activation:t,clipMax:n,clipMin:i}}else if(t==="LeakyRelu"){let[i]=e?.activation_params||[.01];return{activation:t,alpha:i}}return{activation:t}}}),ot,Jo,Wn=C(()=>{ot=(e,t)=>{switch(e){case 1:return t;case 2:return`vec2<${t}>`;case 3:return`vec3<${t}>`;case 4:return`vec4<${t}>`;default:throw new Error(`${e}-component is not supported.`)}},Jo=e=>`
      ${e?"value = value + getBiasByOutputCoords(coords);":""}
      `}),el,Ap=C(()=>{el=e=>`
fn getIndexFromCoords4D(coords : vec4<i32>, shape : vec4<i32>) -> i32 {
  return dot(coords, vec4<i32>(
      shape.y * shape.z * shape.w, shape.z * shape.w, shape.w, 1));
}
fn getOutputIndexFromCoords(coords : vec4<i32>) -> i32 {
  return dot(coords, vec4<i32>(
    i32(${e}.x), i32(${e}.y), i32(${e}.z), 1));
}
`}),mi,Gn,jn=C(()=>{me(),be(),$e(),Ht(),mi=(e,t,i,n,r)=>{let s=n-i;return`
      ${Array.from({length:i}).map((a,o)=>`
      if (${oe(t.shape,o,t.rank)} != 1) {
        ${t.indicesSet(e,o,oe(r,o+s,n))}
      } else {
        ${t.indicesSet(e,o,0)}
      }`).join("")}
`},Gn=(e,t,i,n,r=!1,s)=>{let a=e[0].dims,o=e[1].dims,l=a[a.length-2],u=o[o.length-1],d=a[a.length-1],c=Xe(u),p=Xe(d),h=Xe(l),m=M.size(i)/c/h,_=e.length>2,$=n?n.slice(0,-2):i.slice(0,-2),y=[M.size($),l,u],g=[{type:12,data:m},{type:12,data:l},{type:12,data:u},{type:12,data:d}];Gt(t,g),g.push(...de($,a,o)),_&&g.push(...de(e[2].dims)),g.push(...de(y));let T=x=>{let E=On("batch_dims",e[0].dataType,$.length),O=F("a",e[0].dataType,a.length,p),z=F("b",e[1].dataType,o.length,c),N=ae("output",e[0].dataType,y.length,c),L=at(N.type.tensor),ie=Wt(t,N.type.value,L),ge=[O,z],ce="";if(_){let ke=r?c:1;ge.push(F("bias",e[2].dataType,e[2].dims.length,ke)),ce=`${r?`value += bias[col / ${ke}];`:`value += ${N.type.value}(bias[row + i]);`}`}let we=[{name:"output_size",type:"u32"},{name:"M",type:"u32"},{name:"N",type:"u32"},{name:"K",type:"u32"}];jt(t,we);let re=()=>{let ke=`var a_data: ${O.type.value};`;for(let he=0;he<p;he++)ke+=`
              let b_data${he} = b[(b_offset + (k + ${he}) * uniforms.N + col) / ${c}];`;for(let he=0;he<h;he++){ke+=`a_data = a[(a_offset + (row + ${he}) * uniforms.K + k) / ${p}];`;for(let le=0;le<p;le++)ke+=`
            values[${he}] = fma(${z.type.value}(a_data${p===1?"":`[${le}]`}), b_data${le}, values[${he}]);
`}return ke};return`
  ${x.registerUniforms(we).registerInternalVariables(E).declareVariables(...ge,N)}
  ${x.mainStart()}
    ${x.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    let col = (global_idx % (uniforms.N / ${c})) * ${c};
    var index1 = global_idx / (uniforms.N / ${c});
    let stride1 = uniforms.M / ${h};
    let row = (index1 % stride1) * ${h};
    let batch = index1 / stride1;

    ${i.length===2?"":`let batch_indices = ${E.offsetToIndices("batch")};`}

    var a_indices: ${O.type.indices};
    ${mi("a_indices",O,O.rank-2,E.rank,"batch_indices")}
    ${O.indicesSet("a_indices",O.rank-2,0)}
    ${O.indicesSet("a_indices",O.rank-1,0)}
    let a_offset = ${O.indicesToOffset("a_indices")};

    var b_indices: ${z.type.indices};
    ${mi("b_indices",z,z.rank-2,E.rank,"batch_indices")}
    ${z.indicesSet("b_indices",z.rank-2,0)}
    ${z.indicesSet("b_indices",z.rank-1,0)}
    let b_offset = ${z.indicesToOffset("b_indices")};
    var values: array<${N.type.value}, ${h}>;
    for (var k: u32 = 0u; k < uniforms.K; k = k + ${p}) {
      ${re()}
    }
    for (var i = 0u; i < ${h}u; i++) {
      var value = values[i];
      ${ce}
      ${ie}
      let cur_indices = ${N.type.indices}(batch, row + i, col);
      let offset = ${N.indicesToOffset("cur_indices")};
      ${N.setByOffset(`offset / ${c}`,"value")};
    }
  }
  `};return{name:"MatMulNaive",shaderCache:{hint:`${t.activation};${c};${p};${h};${r}`,inputDependencies:_?["rank","rank","rank"]:["rank","rank"]},getRunData:()=>({outputs:[{dims:s?s(i):i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(m/64)},programUniforms:g}),getShaderSource:T}}}),tl,il,Hn,Kn,nl,Qn,rl,Vi,Zn=C(()=>{me(),be(),$e(),Ht(),jn(),Wn(),tl=(e,t)=>e?`
        mm_Asub[inputRow][inputCol] = mm_readA(batch,
          kStart + inputRow,
          globalRowStart / innerElementSize + inputCol${t?", batchIndices":""});
        `:`
        mm_Asub[inputRow][inputCol] = mm_readA(batch,
          globalRow + innerRow,
          kStart / innerElementSize + inputCol${t?", batchIndices":""});
        `,il=(e,t)=>e?`
        let ACached0 = mm_Asub[k * innerElementSize][localRow];
        let ACached1 = mm_Asub[k * innerElementSize + 1][localRow];
        let ACached2 = mm_Asub[k * innerElementSize + 2][localRow];
        ${t===3?"":"let ACached3 = mm_Asub[k * innerElementSize + 3][localRow];"}
        for (var i = 0; i < rowPerThread; i = i + 1) {
          acc[i] = BCached0 * ACached0[i] + acc[i];
          acc[i] = BCached1 * ACached1[i] + acc[i];
          acc[i] = BCached2 * ACached2[i] + acc[i];
          ${t===3?"":"acc[i] = BCached3 * ACached3[i] + acc[i];"}
        }`:`
        for (var i = 0; i < rowPerThread; i = i + 1) {
          let ACached = mm_Asub[tileRow + i][k];
          acc[i] = BCached0 * ACached.x + acc[i];
          acc[i] = BCached1 * ACached.y + acc[i];
          acc[i] = BCached2 * ACached.z + acc[i];
          ${t===3?"":"acc[i] = BCached3 * ACached.w + acc[i];"}
        }`,Hn=(e,t,i="f32",n,r=!1,s=32,a=!1,o=32)=>{let l=t[1]*e[1],u=t[0]*e[0],d=r?l:s,c=r?s:l,p=d/t[0],h=s/t[1];if(!((r&&p===4&&e[1]===4||!r&&(p===3||p===4))&&d%t[0]===0&&s%t[1]===0&&e[0]===4))throw new Error(`If transposeA ${r} is true, innerElementSize ${p} and workPerThread[1] ${e[1]} must be 4.
      Otherwise, innerElementSize ${p} must be 3 or 4.
  tileAWidth ${d} must be divisible by workgroupSize[0]${t[0]}. tileInner ${s} must be divisible by workgroupSize[1] ${t[1]}. colPerThread ${e[0]} must be 4.`);return`
var<workgroup> mm_Asub: array<array<vec${p}<${i}>, ${d/p}>, ${c}>;
var<workgroup> mm_Bsub: array<array<vec4<${i}>, ${u/e[0]}>, ${s}>;

const rowPerThread = ${e[1]};
const colPerThread = ${e[0]};
const innerElementSize = ${p};
const tileInner = ${s};

@compute @workgroup_size(${t[0]}, ${t[1]}, ${t[2]})
fn main(@builtin(local_invocation_id) localId : vec3<u32>,
        @builtin(global_invocation_id) globalId : vec3<u32>,
        @builtin(workgroup_id) workgroupId : vec3<u32>) {
  let localRow = i32(localId.y);
  let tileRow = localRow * rowPerThread;
  let tileCol = i32(localId.x);

  let globalRow =i32(globalId.y) * rowPerThread;
  let globalCol = i32(globalId.x);
  let batch = ${a?"0":"i32(globalId.z)"};
  ${n?`let batchIndices = ${n.offsetToIndices("u32(batch)")};`:""}
  let globalRowStart = i32(workgroupId.y) * ${l};

  let num_tiles = ${a?`${Math.ceil(o/s)}`:"(uniforms.dim_inner - 1) / tileInner + 1"};
  var kStart = ${a?`i32(globalId.z) * ${o}`:"0"};

  var acc: array<vec4<${i}>, rowPerThread>;

  // Loop over shared dimension.
  let tileRowB = localRow * ${h};
  for (var t = 0; t < num_tiles; t = t + 1) {
      // Load one tile of A into local memory.
      for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
          let inputRow = tileRow + innerRow;
          let inputCol = tileCol;
          ${tl(r,n)}
      }

      // Load one tile of B into local memory.
      for (var innerRow = 0; innerRow < ${h}; innerRow = innerRow + 1) {
          let inputRow = tileRowB + innerRow;
          let inputCol = tileCol;
          mm_Bsub[inputRow][inputCol] = mm_readB(batch, kStart + inputRow, globalCol${n?", batchIndices":""});
      }
      kStart = kStart + tileInner;
      workgroupBarrier();

      // Compute acc values for a single thread.
      for (var k = 0; k < tileInner / innerElementSize; k = k + 1) {
          let BCached0 = mm_Bsub[k * innerElementSize][tileCol];
          let BCached1 = mm_Bsub[k * innerElementSize + 1][tileCol];
          let BCached2 = mm_Bsub[k * innerElementSize + 2][tileCol];
          ${p===3?"":"let BCached3 = mm_Bsub[k * innerElementSize + 3][tileCol];"}

          ${il(r,p)}
      }

      workgroupBarrier();
  }

  for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
      mm_write(batch, globalRow + innerRow, globalCol, acc[innerRow]);
  }
}`},Kn=(e,t)=>e?`
            mm_Asub[inputRow][inputCol] = mm_readA(batch,
              kStart + inputRow,
              globalRowStart + inputCol${t?", batchIndices":""});
            `:`
            mm_Asub[inputRow][inputCol] = mm_readA(batch,
              globalRowStart + inputRow,
              kStart + inputCol${t?", batchIndices":""});
            `,nl=e=>e?"let ACached = mm_Asub[k][tileRow + innerRow];":"let ACached = mm_Asub[tileRow + innerRow][k];",Qn=(e,t,i="f32",n,r=!1,s=32,a=!1,o=32,l=!1)=>{let u=e[1]*t[1],d=e[0]*t[0],c=r?u:s,p=r?s:u;if(!(p%t[1]===0&&c%t[0]===0&&s%t[1]===0))throw new Error(`tileAHight ${p} must be divisible by workgroupSize[1]${t[1]}, tileAWidth ${c} must be divisible by workgroupSize[0]${t[0]}, tileInner ${s} must be divisible by workgroupSize[1]${t[1]}`);let h=p/t[1],m=c/t[0],_=s/t[1],$=l?`
    let localRow = i32(localId.y);
    let localCol = i32(localId.x);
    let globalRowStart = i32(workgroupId.y) * ${u};
    let globalColStart = i32(workgroupId.x) * ${d};

    // Loop over shared dimension.
    for (var t = 0; t < num_tiles; t = t + 1) {
      // Load one tile of A into local memory.
      for (var inputRow = localRow; inputRow < ${p}; inputRow = inputRow + ${t[1]}) {
        for (var inputCol = localCol; inputCol < ${c}; inputCol = inputCol + ${t[0]}) {
          ${Kn(r,n)}
        }
      }
      // Load one tile of B into local memory.
      for (var inputRow = localRow; inputRow < ${s}; inputRow = inputRow + ${t[1]}) {
            for (var inputCol = localCol; inputCol < ${d}; inputCol = inputCol + ${t[0]}) {
          mm_Bsub[inputRow][inputCol] = mm_readB(batch,
            kStart + inputRow,
            globalColStart + inputCol${n?", batchIndices":""});
        }
      }
      kStart = kStart + tileInner;
      workgroupBarrier();

      // Compute acc values for a single thread.
      var BCached : array<${i}, colPerThread>;
      for (var k = 0; k < tileInner; k = k + 1) {
        for (var inner = 0; inner < colPerThread; inner = inner + 1) {
          BCached[inner] = mm_Bsub[k][localCol + inner * ${t[0]}];
        }
        for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
          let ACached = ${r?`mm_Asub[k][localRow + innerRow * ${t[1]}];`:`mm_Asub[localRow + innerRow * ${t[1]}][k];`}
          for (var innerCol = 0; innerCol < colPerThread; innerCol = innerCol + 1) {
            acc[innerRow][innerCol] = acc[innerRow][innerCol] +
                ACached * BCached[innerCol];
          }
        }
      }
      workgroupBarrier();
    }
    for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
      let gRow = globalRowStart + localRow + innerRow * ${t[1]};
      for (var innerCol = 0; innerCol < colPerThread; innerCol = innerCol + 1) {
        let gCol = globalColStart + localCol + innerCol * ${t[0]};
        mm_write(batch, gRow, gCol, acc[innerRow][innerCol]);
      }
    }
    `:`
let tileRow = i32(localId.y) * rowPerThread;
let tileCol = i32(localId.x) * colPerThread;

let globalRow = i32(globalId.y) * rowPerThread;
let globalCol = i32(globalId.x) * colPerThread;
let globalRowStart = i32(workgroupId.y) * ${u};

let tileRowA = i32(localId.y) * ${h};
let tileColA = i32(localId.x) * ${m};
let tileRowB = i32(localId.y) * ${_};
// Loop over shared dimension.
for (var t = 0; t < num_tiles; t = t + 1) {
  // Load one tile of A into local memory.
  for (var innerRow = 0; innerRow < ${h}; innerRow = innerRow + 1) {
    for (var innerCol = 0; innerCol < ${m}; innerCol = innerCol + 1) {
      let inputRow = tileRowA + innerRow;
      let inputCol = tileColA + innerCol;
      ${Kn(r,n)}
    }
  }

  // Load one tile of B into local memory.
  for (var innerRow = 0; innerRow < ${_}; innerRow = innerRow + 1) {
    for (var innerCol = 0; innerCol < colPerThread; innerCol = innerCol + 1) {
      let inputRow = tileRowB + innerRow;
      let inputCol = tileCol + innerCol;
      mm_Bsub[inputRow][inputCol] = mm_readB(batch,
        kStart + inputRow,
        globalCol + innerCol${n?", batchIndices":""});
    }
  }
  kStart = kStart + tileInner;
  workgroupBarrier();

  // Compute acc values for a single thread.
  var BCached : array<${i}, colPerThread>;
  for (var k = 0; k < tileInner; k = k + 1) {
    for (var inner = 0; inner < colPerThread; inner = inner + 1) {
      BCached[inner] = mm_Bsub[k][tileCol + inner];
    }

    for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
      ${nl(r)}
      for (var innerCol = 0; innerCol < colPerThread; innerCol = innerCol + 1) {
        acc[innerRow][innerCol] = acc[innerRow][innerCol] + ACached * BCached[innerCol];
      }
    }
  }

  workgroupBarrier();
}

for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
  for (var innerCol = 0; innerCol < colPerThread; innerCol = innerCol + 1) {
    mm_write(batch, globalRow + innerRow, globalCol + innerCol,
        acc[innerRow][innerCol]);
  }
}
`;return`
  var<workgroup> mm_Asub : array<array<${i}, ${c}>, ${p}>;
  var<workgroup> mm_Bsub : array<array<${i}, ${d}>, ${s}>;
  const rowPerThread = ${e[1]};
  const colPerThread = ${e[0]};
  const tileInner = ${s};

@compute @workgroup_size(${t[0]}, ${t[1]}, ${t[2]})
fn main(@builtin(local_invocation_id) localId : vec3<u32>,
        @builtin(global_invocation_id) globalId : vec3<u32>,
        @builtin(workgroup_id) workgroupId : vec3<u32>) {
    let batch = ${a?"0":"i32(globalId.z)"};
    ${n?`let batchIndices = ${n.offsetToIndices("u32(batch)")};`:""}
    let num_tiles = ${a?`${Math.ceil(o/s)}`:"(uniforms.dim_inner - 1) / tileInner + 1"};
    var kStart = ${a?`i32(globalId.z) * ${o}`:"0"};

    var acc : array<array<${i}, colPerThread>, rowPerThread>;
    ${$}
  }
`},rl=(e,t,i,n,r=!1)=>{let[s,a,o,l]=n,u=at(n[0].type.tensor);return`
    fn mm_readA(batch: i32, row: i32, colIn: i32, batchIndices: ${s.type.indices}) -> ${ot(e,u)} {
      var value = ${ot(e,u)}(0.0);
      let col = colIn * ${e};
      if(row < uniforms.dim_a_outer && col < uniforms.dim_inner)
      {
        var aIndices: ${a.type.indices};
        ${mi("aIndices",a,a.rank-2,s.rank,"batchIndices")}
        ${a.indicesSet("aIndices",a.rank-2,"u32(row)")}
        ${a.indicesSet("aIndices",a.rank-1,"u32(colIn)")}
        value = ${a.getByIndices("aIndices")};
      }
      return value;
    }

    fn mm_readB(batch: i32, row: i32, colIn: i32, batchIndices: ${s.type.indices}) -> ${ot(e,u)} {
      var value = ${ot(e,u)}(0.0);
      let col = colIn * ${e};
      if(row < uniforms.dim_inner && col < uniforms.dim_b_outer)
      {
        var bIndices: ${o.type.indices};
        ${mi("bIndices",o,o.rank-2,s.rank,"batchIndices")}
        ${o.indicesSet("bIndices",o.rank-2,"u32(row)")}
        ${o.indicesSet("bIndices",o.rank-1,"u32(colIn)")}
        value = ${o.getByIndices("bIndices")};
      }
      return value;
    }

    fn mm_write(batch: i32, row: i32, colIn: i32, valueIn: ${ot(e,u)}) {
      let col = colIn * ${e};
      if (row < uniforms.dim_a_outer && col < uniforms.dim_b_outer) {
        var value = valueIn;
        let coords = vec3<i32>(batch, row, colIn);
        ${t?`value = value + ${r?"bias[colIn]":`${ot(e,u)}(bias[row])`};`:""}
        ${i}
        ${l.setByIndices("vec3<u32>(coords)","value")}
      }
    }
    `},Vi=(e,t,i,n,r=!1,s)=>{let a=e[0].dims,o=e[1].dims,l=a.slice(0,-2),u=o.slice(0,-2),d=n?n.slice(0,-2):i.slice(0,-2),c=M.size(d),p=a[a.length-2],h=a[a.length-1],m=o[o.length-1],_=h%4===0&&m%4===0,$=p<=8?[4,1,1]:[4,4,1],y=[8,8,1],g=[Math.ceil(m/y[0]/$[0]),Math.ceil(p/y[1]/$[1]),Math.ceil(c/y[2]/$[2])],T=_?4:1,x=[...l,p,h/T],E=x.length,O=[...u,h,m/T],z=O.length,N=[c,p,m/T],L=[{type:6,data:p},{type:6,data:m},{type:6,data:h}];Gt(t,L),L.push(...de(d,x,O));let ie=["rank","rank"],ge=e.length>2;ge&&(L.push(...de(e[2].dims)),ie.push("rank")),L.push(...de(N));let ce=we=>{let re=d.length,ke=On("batchDims",e[0].dataType,re,1),he=at(e[0].dataType),le=F("a",e[0].dataType,E,T),Re=F("b",e[1].dataType,z,T),pe=ae("result",e[0].dataType,N.length,T),He=[le,Re];if(ge){let lt=r?T:1;He.push(F("bias",e[2].dataType,e[2].dims.length,lt))}let U=[{name:"dim_a_outer",type:"i32"},{name:"dim_b_outer",type:"i32"},{name:"dim_inner",type:"i32"}];jt(t,U);let te=at(pe.type.tensor),xe=Wt(t,pe.type.value,te),Le=rl(T,ge,xe,[ke,le,Re,pe],r);return`
  ${we.registerUniforms(U).registerInternalVariables(ke).declareVariables(...He,pe)}
  ${Le}
  ${_?Hn($,y,he,ke):Qn($,y,he,ke)}
                   `};return{name:"MatMul",shaderCache:{hint:`${$};${t.activation};${_};${r}`,inputDependencies:ie},getRunData:()=>({outputs:[{dims:s?s(i):i,dataType:e[0].dataType}],dispatchGroup:{x:g[0],y:g[1],z:g[2]},programUniforms:L}),getShaderSource:ce}}}),sl,al,zp=C(()=>{me(),zt(),$e(),Ht(),Wn(),Ap(),Zn(),sl=(e,t,i,n,r=!1,s,a=4,o=4,l=4,u="f32")=>{let d=L=>{switch(L){case 1:return"resData = x[xIndex];";case 3:return`resData = vec3<${u}>(x[xIndex], x[xIndex + 1], x[xIndex + 2]);`;case 4:return"resData = x[xIndex / 4];";default:throw new Error(`innerElementSize ${L} is not supported.`)}},c=L=>{switch(L){case 1:return"return w[row * i32(uniforms.w_shape[3]) + colIn];";case 4:return"return w[row * i32(uniforms.w_shape[3]) / 4 + colIn];";default:throw new Error(`innerElementSize ${L} is not supported.`)}},p=e?`
    let coord = vec4<i32>(batch, xRow, xCol, xCh);
    `:`
    let coord = vec4<i32>(batch, xCh, xRow, xCol);
    `,h=e?`
    let coords = vec4<i32>(
      batch,
      row / outWidth,
      row % outWidth,
      col);
    `:`
    let coords = vec4<i32>(
      batch,
      row,
      col / outWidth,
      col % outWidth);
    `,m=e?"i32(uniforms.x_shape[1])":"i32(uniforms.x_shape[2])",_=e?"i32(uniforms.x_shape[2])":"i32(uniforms.x_shape[3])",$=e?"row":"col",y=e?"col":"row",g=`
    let inChannels = i32(uniforms.w_shape[2]);
    let outWidth = ${e?"i32(uniforms.result_shape[2])":"i32(uniforms.result_shape[3])"};
    let outRow = ${$} / outWidth;
    let outCol = ${$} % outWidth;

    let WRow = ${y} / (i32(uniforms.w_shape[1]) * inChannels);
    let WCol = ${y} / inChannels % i32(uniforms.w_shape[1]);
    let xRow = outRow * uniforms.stride[0] + uniforms.dilation[0] * WRow - uniforms.pad[0];
    let xCol = outCol * uniforms.stride[1] + uniforms.dilation[1] * WCol - uniforms.pad[1];
    let xCh = ${y} % inChannels;
    var resData = ${ot(a,u)}(0.0);
    // The bounds checking is always needed since we use it to pad zero for
    // the 'same' padding type.
    if (xRow >= 0 && xRow < ${m} && xCol >= 0 && xCol < ${_}) {
      ${p}
      let xIndex = getIndexFromCoords4D(coord, vec4<i32>(uniforms.x_shape));
      ${d(a)}
    }
    return resData;`,T=e?t&&n?`
    let col = colIn * ${a};
    ${g}`:`
    let col = colIn * ${a};
    if (row < uniforms.dim_a_outer && col < uniforms.dim_inner) {
      ${g}
    }
    return ${ot(a,u)}(0.0);`:n&&i?`
    let col = colIn * ${a};
    ${g}`:`
    let col = colIn * ${a};
    if (row < uniforms.dim_inner && col < uniforms.dim_b_outer) {
      ${g}
    }
    return ${ot(a,u)}(0.0);`,x=e?n&&i?c(o):`
    let col = colIn * ${o};
    if (row < uniforms.dim_inner && col < uniforms.dim_b_outer) {
      ${c(o)}
    }
    return ${ot(o,u)}(0.0);`:`
    let col = colIn * ${o};
    if (row < uniforms.dim_inner && col < uniforms.dim_a_outer) {
      ${c(o)}
    }
    return ${ot(o,u)}(0.0);`,E=ot(l,u),O=ot(e?a:o,u),z=ot(e?o:a,u),N=Wt(s,E,u);return`
    fn mm_readA(batch: i32, row : i32, colIn : i32) -> ${O} {
      ${e?T:x}
    }

    fn mm_readB(batch: i32, row : i32, colIn : i32) -> ${z} {
      ${e?x:T}
    }

    fn mm_write(batch: i32, row : i32, colIn : i32, valueIn : ${E}) {
      let col = colIn * ${l};
      if (row < uniforms.dim_a_outer && col < uniforms.dim_b_outer)
      {
      var value = valueIn;
      let outWidth = ${e?"i32(uniforms.result_shape[2])":"i32(uniforms.result_shape[3])"};
      ${h}
      ${Jo(r)}
      ${N}
      setOutputAtCoords(coords[0], coords[1], coords[2], coords[3], value);
      }
    }`},al=(e,t,i,n,r,s,a,o,l)=>{let u=t.format==="NHWC",d=u?e[0].dims[3]:e[0].dims[1],c=i[0],p=u?i[2]:i[3],h=u?i[1]:i[2],m=u?i[3]:i[1],_=u&&(d%4===0||d%3===0)&&m%4===0,$=u?m:p*h,y=u?p*h:m,g=[8,8,1],T=n<=8?[4,1,1]:[4,4,1],x=[Math.ceil($/g[0]/T[0]),Math.ceil(y/g[1]/T[1]),Math.ceil(c/g[2]/T[2])];Ie("verbose",()=>`[conv2d_mm_webgpu] dispatch = ${x}`);let E=_?u&&d%4!==0?3:4:1,O=g[1]*T[1],z=g[0]*T[0],N=Math.max(g[0]*E,g[1]),L=n%O===0,ie=r%z===0,ge=s%N===0,ce=_?[E,4,4]:[1,1,1],we=[{type:6,data:n},{type:6,data:r},{type:6,data:s},{type:6,data:[t.pads[0],t.pads[1]]},{type:6,data:t.strides},{type:6,data:t.dilations}];Gt(t,we),we.push(...de(e[0].dims,e[1].dims));let re=["rank","rank"];a&&(we.push(...de(e[2].dims)),re.push("rank")),we.push(...de(i));let ke=he=>{let le=[{name:"dim_a_outer",type:"i32"},{name:"dim_b_outer",type:"i32"},{name:"dim_inner",type:"i32"},{name:"pad",type:"i32",length:2},{name:"stride",type:"i32",length:2},{name:"dilation",type:"i32",length:2}];jt(t,le);let Re=_?4:1,pe=at(e[0].dataType),He=`
      fn setOutputAtIndex(flatIndex : i32, value : ${_?`vec4<${pe}>`:pe}) {
        result[flatIndex] = ${_?`vec4<${pe}>`:pe}(value);
      }
      fn setOutputAtCoords(d0 : i32, d1 : i32, d2 : i32, d3 : i32, value : ${_?`vec4<${pe}>`:pe}) {
        let flatIndex = getOutputIndexFromCoords(vec4<i32>(d0, d1, d2, d3));
        setOutputAtIndex(flatIndex ${_?"/ 4":""}, value);
      }`,U=F("x",e[0].dataType,e[0].dims.length,E===3?1:E),te=F("w",e[1].dataType,e[1].dims.length,Re),xe=[U,te],Le=ae("result",e[0].dataType,i.length,Re);if(a){let lt=F("bias",e[2].dataType,e[2].dims.length,Re);xe.push(lt),He+=`
        fn getBiasByOutputCoords(coords : vec4<i32>) -> ${_?`vec4<${pe}>`:pe} {
          return bias[coords.${u?"w":"y"}${_?"/ 4":""}];
        }`}return`
        ${el("uniforms.result_strides")}
        //struct Uniforms { xShape : vec4<i32>, wShape : vec4<i32>, outShape : vec4<i32>,
        //  outShapeStrides: vec3<i32>, filterDims : vec2<i32>, pad : vec2<i32>, stride : vec2<i32>,
        //  dilation : vec2<i32>, dimAOuter : i32, dimBOuter : i32, dimInner : i32 };
        ${he.registerUniforms(le).declareVariables(...xe,Le)}
        ${He}
        ${sl(u,L,ie,ge,a,t,ce[0],ce[1],ce[2],pe)}
        ${_?Hn(T,g,pe,void 0,!u,N):Qn(T,g,pe,void 0,!u,N,!1,void 0,o)}`};return{name:"Conv2DMatMul",shaderCache:{hint:`${t.cacheKey};${E};${_};${L};${ie};${ge};${O};${z};${N}`,inputDependencies:re},getRunData:()=>({outputs:[{dims:l?l(i):i,dataType:e[0].dataType}],dispatchGroup:{x:x[0],y:x[1],z:x[2]},programUniforms:we}),getShaderSource:ke}}}),ol,Xn,gi,ll,Yn,ul,dl,cl,Op=C(()=>{me(),zt(),be(),$e(),Ht(),Wn(),ol=e=>{let t=1;for(let i=0;i<e.length;i++)t*=e[i];return t},Xn=e=>typeof e=="number"?[e,e,e]:e,gi=(e,t)=>t<=1?e:e+(e-1)*(t-1),ll=(e,t,i,n=1)=>{let r=gi(t,n);return Math.floor((e[0]*(i-1)-i+r)/2)},Yn=(e,t,i,n,r)=>{r==null&&(r=ll(e,t[0],n[0]));let s=[0,0,0,i];for(let a=0;a<3;a++)e[a]+2*r>=t[a]&&(s[a]=Math.trunc((e[a]-t[a]+2*r)/n[a]+1));return s},ul=(e,t,i,n,r,s,a,o,l,u)=>{let d,c,p,h;if(e==="VALID"&&(e=0),typeof e=="number"){d={top:e,bottom:e,left:e,right:e,front:e,back:e};let m=Yn([t,i,n,1],[o,l,u],1,[r,s,a],e);c=m[0],p=m[1],h=m[2]}else if(Array.isArray(e)){if(!e.every((_,$,y)=>_===y[0]))throw Error(`Unsupported padding parameter: ${e}`);d={top:e[0],bottom:e[1],left:e[2],right:e[3],front:e[4],back:e[5]};let m=Yn([t,i,n,1],[o,l,u],1,[r,s,a],e[0]);c=m[0],p=m[1],h=m[2]}else if(e==="SAME_UPPER"){c=Math.ceil(t/r),p=Math.ceil(i/s),h=Math.ceil(n/a);let m=(c-1)*r+o-t,_=(p-1)*s+l-i,$=(h-1)*a+u-n,y=Math.floor(m/2),g=m-y,T=Math.floor(_/2),x=_-T,E=Math.floor($/2),O=$-E;d={top:T,bottom:x,left:E,right:O,front:y,back:g}}else throw Error(`Unknown padding parameter: ${e}`);return{padInfo:d,outDepth:c,outHeight:p,outWidth:h}},dl=(e,t,i,n,r,s=!1,a="channelsLast")=>{let o,l,u,d,c;if(a==="channelsLast")[o,l,u,d,c]=e;else if(a==="channelsFirst")[o,c,l,u,d]=e;else throw new Error(`Unknown dataFormat ${a}`);let[p,,h,m,_]=t,[$,y,g]=Xn(i),[T,x,E]=Xn(n),O=gi(h,T),z=gi(m,x),N=gi(_,E),{padInfo:L,outDepth:ie,outHeight:ge,outWidth:ce}=ul(r,l,u,d,$,y,g,O,z,N),we=s?p*c:p,re=[0,0,0,0,0];return a==="channelsFirst"?re=[o,we,ie,ge,ce]:a==="channelsLast"&&(re=[o,ie,ge,ce,we]),{batchSize:o,dataFormat:a,inDepth:l,inHeight:u,inWidth:d,inChannels:c,outDepth:ie,outHeight:ge,outWidth:ce,outChannels:we,padInfo:L,strideDepth:$,strideHeight:y,strideWidth:g,filterDepth:h,filterHeight:m,filterWidth:_,effectiveFilterDepth:O,effectiveFilterHeight:z,effectiveFilterWidth:N,dilationDepth:T,dilationHeight:x,dilationWidth:E,inShape:e,outShape:re,filterShape:t}},cl=(e,t,i,n,r,s)=>{let a=s==="channelsLast";a?e[0].dims[3]:e[0].dims[1];let o=[64,1,1],l={x:i.map(($,y)=>y)},u=[Math.ceil(ol(l.x.map($=>i[$]))/o[0]),1,1];Ie("verbose",()=>`[conv3d_naive_webgpu] dispatch = ${u}`);let d=1,c=M.size(i),p=[{type:12,data:c},{type:12,data:n},{type:12,data:r},{type:12,data:t.strides},{type:12,data:t.dilations}];Gt(t,p),p.push(...de(e[0].dims,e[1].dims));let h=["rank","rank"],m=e.length===3;m&&(p.push(...de(e[2].dims)),h.push("rank")),p.push(...de(i));let _=$=>{let y=[{name:"output_size",type:"u32"},{name:"filter_dims",type:"u32",length:n.length},{name:"pads",type:"u32",length:r.length},{name:"strides",type:"u32",length:t.strides.length},{name:"dilations",type:"u32",length:t.dilations.length}];jt(t,y);let g=1,T=at(e[0].dataType),x=F("x",e[0].dataType,e[0].dims.length,d),E=F("W",e[1].dataType,e[1].dims.length,g),O=[x,E],z=ae("result",e[0].dataType,i.length,g),N="";if(m){let ge=F("bias",e[2].dataType,e[2].dims.length,g);O.push(ge),N+=`
        fn getBiasByOutputCoords(coords : array<u32, 5>) -> ${T} {
          return bias[${a?oe("coords",4,5):oe("coords",1,5)}];
        }`}let L=ot(d,T),ie=Wt(t,L,T);return`
            ${N}
            fn getX(d0 : u32, d1 : u32, d2 : u32, d3 : u32, d4 : u32) -> f32 {
              let aIndices = array<u32, 5>(d0, d1, d2, d3, d4);
              return ${x.getByIndices("aIndices")};
            }
            fn getW(d0 : u32, d1 : u32, d2 : u32, d3 : u32, d4 : u32) -> f32 {
              let aIndices = array<u32, 5>(d0, d1, d2, d3, d4);
              return ${E.getByIndices("aIndices")};
            }
          ${$.registerUniforms(y).declareVariables(...O,z)}
          ${$.mainStart()}
          ${$.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
              let coords = ${z.offsetToIndices("global_idx")};
              let batch = ${oe("coords",0,x.rank)};
              let d2 = ${a?oe("coords",x.rank-1,x.rank):oe("coords",1,x.rank)};
              let xFRCCorner = vec3<u32>(${a?oe("coords",1,x.rank):oe("coords",2,x.rank)},
              ${a?oe("coords",2,x.rank):oe("coords",3,x.rank)},
              ${a?oe("coords",3,x.rank):oe("coords",4,x.rank)}) * uniforms.strides - uniforms.pads;
              let xFCorner = xFRCCorner.x;
              let xRCorner = xFRCCorner.y;
              let xCCorner = xFRCCorner.z;
              let xShapeY = ${a?oe("uniforms.x_shape",1,x.rank):oe("uniforms.x_shape",2,x.rank)};
              let xShapeZ = ${a?oe("uniforms.x_shape",2,x.rank):oe("uniforms.x_shape",3,x.rank)};
              let xShapeW = ${a?oe("uniforms.x_shape",3,x.rank):oe("uniforms.x_shape",4,x.rank)};
              let xShapeU = ${a?oe("uniforms.x_shape",4,x.rank):oe("uniforms.x_shape",1,x.rank)};
              let inputDepthNearestVec4 = (xShapeU / 4) * 4;
              let inputDepthVec4Remainder = xShapeU % 4;

              var value = 0.0;
              for (var wF = 0u; wF < uniforms.filter_dims[0]; wF++) {
                let xF = xFCorner + wF * uniforms.dilations[0];
                if (xF < 0 || xF >= xShapeY) {
                  continue;
                }

                for (var wR = 0u; wR < uniforms.filter_dims[1]; wR++) {
                  let xR = xRCorner + wR * uniforms.dilations[1];
                  if (xR < 0 || xR >= xShapeZ) {
                    continue;
                  }

                  for (var wC = 0u; wC < uniforms.filter_dims[2]; wC++) {
                    let xC = xCCorner + wC * uniforms.dilations[2];
                    if (xC < 0 || xC >= xShapeW) {
                      continue;
                    }

                    for (var d1 = 0u; d1 < inputDepthNearestVec4; d1 += 4) {
                      ${a?`let xValues = vec4<f32>(
                               getX(batch, xF, xR, xC, d1),
                               getX(batch, xF, xR, xC, d1 + 1),
                               getX(batch, xF, xR, xC, d1 + 2),
                               getX(batch, xF, xR, xC, d1 + 3));
                            `:`let xValues = vec4<f32>(
                               getX(batch, d1, xF, xR, xC),
                               getX(batch, d1 + 1, xF, xR, xC),
                               getX(batch, d1 + 2, xF, xR, xC),
                               getX(batch, d1 + 3, xF, xR, xC));
                            `}
                            let wValues = vec4<f32>(
                              getW(d2, d1, wF, wR, wC),
                              getW(d2, d1 + 1, wF, wR, wC),
                              getW(d2, d1 + 2, wF, wR, wC),
                              getW(d2, d1 + 3, wF, wR, wC));
                      value += dot(xValues, wValues);
                    }
                    if (inputDepthVec4Remainder == 1) {
                        ${a?`value += getX(batch, xF, xR, xC, inputDepthNearestVec4)
                          * getW(d2, inputDepthNearestVec4, wF, wR, wC);`:`value += getX(batch, inputDepthNearestVec4, xF, xR, xC)
                          * getW(d2, inputDepthNearestVec4, wF, wR, wC);`}
                    } else if (inputDepthVec4Remainder == 2) {
                      ${a?`let xValues = vec2<f32>(
                        getX(batch, xF, xR, xC, inputDepthNearestVec4),
                        getX(batch, xF, xR, xC, inputDepthNearestVec4 + 1));
                      `:`let xValues = vec2<f32>(
                        getX(batch, inputDepthNearestVec4, xF, xR, xC),
                        getX(batch, inputDepthNearestVec4 + 1, xF, xR, xC));
                    `}
                    let wValues = vec2<f32>(
                      getW(d2, inputDepthNearestVec4, wF, wR, wC),
                      getW(d2, inputDepthNearestVec4 + 1, wF, wR, wC));
                      value += dot(xValues, wValues);
                    } else if (inputDepthVec4Remainder == 3) {
                      ${a?`let xValues = vec3<f32>(
                        getX(batch, xF, xR, xC, inputDepthNearestVec4),
                        getX(batch, xF, xR, xC, inputDepthNearestVec4 + 1),
                        getX(batch, xF, xR, xC, inputDepthNearestVec4 + 2));
                      `:`let xValues = vec3<f32>(
                        getX(batch, inputDepthNearestVec4, xF, xR, xC),
                        getX(batch, inputDepthNearestVec4 + 1, xF, xR, xC),
                        getX(batch, inputDepthNearestVec4 + 2, xF, xR, xC));
                    `}
                    let wValues = vec3<f32>(
                      getW(d2, inputDepthNearestVec4, wF, wR, wC),
                      getW(d2, inputDepthNearestVec4 + 1, wF, wR, wC),
                      getW(d2, inputDepthNearestVec4 + 2, wF, wR, wC));
                      value += dot(xValues, wValues);
                    }
                  }
                }
              }
              ${m?"value = value + getBiasByOutputCoords(coords)":""};
              ${ie}
              result[global_idx] = f32(value);
          }`};return{name:"Conv3DNaive",shaderCache:{hint:`${t.cacheKey};${a};${d};${m}`,inputDependencies:h},getRunData:()=>({outputs:[{dims:i,dataType:e[0].dataType}],dispatchGroup:{x:u[0],y:u[1],z:u[2]},programUniforms:p}),getShaderSource:_}}}),pl,fl,Rp=C(()=>{me(),be(),$e(),Ht(),pl=(e,t,i,n)=>{let r=e.length>2,s=r?"value += b[output_channel];":"",a=e[0].dims,o=e[1].dims,l=t.format==="NHWC",u=l?i[3]:i[1],d=u/t.group,c=l&&d>=4?Xe(u):1,p=M.size(i)/c,h=[{type:12,data:p},{type:12,data:t.dilations},{type:12,data:[t.strides[0],t.strides[1]]},{type:12,data:[t.pads[0],t.pads[1]]},{type:12,data:d}];Gt(t,h),h.push(...de(a,[o[0],o[1],o[2],o[3]/c]));let m=r?["rank","rank","rank"]:["rank","rank"];h.push(...de([i[0],i[1],i[2],i[3]/c]));let _=$=>{let y=ae("output",e[0].dataType,i.length,c),g=at(y.type.tensor),T=Wt(t,y.type.value,g),x=F("x",e[0].dataType,a.length),E=F("w",e[1].dataType,o.length,c),O=[x,E];r&&O.push(F("b",e[2].dataType,e[2].dims,c));let z=[{name:"output_size",type:"u32"},{name:"dilations",type:"u32",length:t.dilations.length},{name:"strides",type:"u32",length:2},{name:"pads",type:"u32",length:2},{name:"output_channels_per_group",type:"u32"}];jt(t,z);let N=l?`
      for (var wHeight: u32 = 0u; wHeight < uniforms.w_shape[0]; wHeight++) {
        let xHeight = xRCCorner.x + wHeight * uniforms.dilations[0];

        if (xHeight < 0u || xHeight >= uniforms.x_shape[1]) {
          continue;
        }

        for (var wWidth: u32 = 0u; wWidth < uniforms.w_shape[1]; wWidth++) {
          let xWidth = xRCCorner.y + wWidth * uniforms.dilations[1];
          if (xWidth < 0u || xWidth >= uniforms.x_shape[2]) {
            continue;
          }

          for (var wInChannel: u32 = 0u; wInChannel < uniforms.w_shape[2]; wInChannel++) {
            let input_channel = in_channel_offset + wInChannel;
            let xVal = ${x.get("batch","xHeight","xWidth","input_channel")};
            let wVal = ${E.get("wHeight","wWidth","wInChannel","output_channel")};
            value += xVal * wVal;
          }
        }
      }
      `:`
      for (var wInChannel: u32 = 0u; wInChannel < uniforms.w_shape[1]; wInChannel++) {
        let input_channel = in_channel_offset + wInChannel;
        for (var wHeight: u32 = 0u; wHeight < uniforms.w_shape[2]; wHeight++) {
          let xHeight = xRCCorner.x + wHeight * uniforms.dilations[0];

          if (xHeight < 0u || xHeight >= uniforms.x_shape[2]) {
            continue;
          }

          for (var wWidth: u32 = 0u; wWidth < uniforms.w_shape[3]; wWidth++) {
            let xWidth = xRCCorner.y + wWidth * uniforms.dilations[1];
            if (xWidth < 0u || xWidth >= uniforms.x_shape[3]) {
              continue;
            }

            let xVal = ${x.get("batch","input_channel","xHeight","xWidth")};
            let wVal = ${E.get("output_channel","wInChannel","wHeight","wWidth")};
            value += xVal * wVal;
          }
        }
      }
      `;return`
  ${$.registerUniforms(z).declareVariables(...O,y)}

  ${$.mainStart()}
    ${$.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let outputIndices = ${y.offsetToIndices("global_idx")};
    let batch: u32 = outputIndices[0];
    let output_channel: u32 = outputIndices[${l?3:1}];
    let xRCCorner: vec2<u32> = vec2<u32>(outputIndices[${l?1:2}], outputIndices[${l?2:3}]) * uniforms.strides - uniforms.pads;
    let group_id: u32 = output_channel * ${c} / uniforms.output_channels_per_group;
    var in_channel_offset = group_id * uniforms.w_shape[${l?2:1}];

    var value: ${y.type.value} = ${y.type.value}(0);
    ${N}
    ${s}
    ${T}
    ${y.setByOffset("global_idx","value")}
  }`};return{name:"GroupedConv",shaderCache:{hint:`${t.cacheKey}_${c}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:n?n(i):i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:h}),getShaderSource:_}},fl=(e,t,i,n)=>{let r=e.length>2,s=Xe(i[3]),a=Xe(i[2]),o=M.size(i)/s/a,l=[e[0].dims[0],e[0].dims[1],e[0].dims[2],e[0].dims[3]/s],u=[e[1].dims[0],e[1].dims[1],e[1].dims[2],e[1].dims[3]/s],d=[i[0],i[1],i[2],i[3]/s],c=[{type:12,data:o},{type:6,data:[t.strides[0],t.strides[1]]},{type:6,data:[t.pads[0],t.pads[1]]}];Gt(t,c),c.push(...de(l,u,d));let p=(a-1)*t.strides[1]+u[1],h=m=>{let _=ae("output",e[0].dataType,d.length,s),$=at(_.type.tensor),y=Wt(t,_.type.value,$),g=F("x",e[0].dataType,l.length,s),T=F("w",e[1].dataType,u.length,s),x=[g,T];r&&x.push(F("b",e[2].dataType,e[2].dims,s));let E=r?"value += b[output_channel];":"",O=[{name:"output_size",type:"u32"},{name:"strides",type:"i32",length:2},{name:"pads",type:"i32",length:2}];return jt(t,O),`
  ${m.registerUniforms(O).declareVariables(...x,_)}
  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    let width0 = uniforms.output_shape[3];
    let output_channel = global_idx % width0;
    var index1 = global_idx / width0;
    let width1 = uniforms.output_shape[2] / ${a}u;
    let col = (index1 % width1) * ${a}u;
    index1 = index1 / width1;
    let row = index1 % uniforms.output_shape[1];
    let batch = index1 / uniforms.output_shape[1];

    let x_corner = vec2<i32>(i32(row), i32(col)) * uniforms.strides - uniforms.pads;

    var x_vals: array<${g.type.value}, ${p}>;
    var values: array<${_.type.value}, ${a}>;
    let input_channel = output_channel;
    // Use constant instead of uniform can give better performance for w's height/width.
    for (var w_height: u32 = 0u; w_height < ${u[0]}; w_height++) {
      let x_height = x_corner.x + i32(w_height);
      if (x_height >= 0 && u32(x_height) < uniforms.x_shape[1]) {
        for (var i = 0; i < ${p}; i++) {
          let x_width = x_corner.y + i;
          if (x_width >= 0 && u32(x_width) < uniforms.x_shape[2]) {
            x_vals[i] = ${g.get("batch","u32(x_height)","u32(x_width)","input_channel")};
          } else {
            x_vals[i] = ${g.type.value}(0);
          }
        }
        for (var w_width: u32 = 0u; w_width < ${u[1]}; w_width++) {
          let w_val = ${T.get("w_height","w_width","0","output_channel")};
          for (var i = 0u; i < ${a}u; i++) {
            values[i] = fma(x_vals[i * u32(uniforms.strides[1]) + w_width], w_val, values[i]);
          }
        }
      }
    }

    for (var i = 0u; i < ${a}u; i++) {
      var value = values[i];
      ${E}
      ${y}
      ${_.set("batch","row","col + i","output_channel","value")};
    }
  }`};return{name:"GroupedConv-Vectorize",shaderCache:{hint:`${t.cacheKey};${s};${a};${p};${u[0]};${u[1]}`,inputDependencies:r?["rank","rank","type"]:["rank","rank"]},getRunData:()=>({outputs:[{dims:n?n(i):i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(o/64)},programUniforms:c}),getShaderSource:h}}}),hl,Li,ml,Ui,Jn,er,gl,_l,tr,Mp=C(()=>{be(),zp(),Op(),Zn(),Rp(),Ht(),jn(),Ft(),hl=(e,t,i,n,r,s)=>{let a=e[0],o=e.slice(s?1:2,s?3:4),l=o.length,u=t[0],d=t.slice(2).map((p,h)=>p+(p-1)*(i[h]-1)),c=o.map((p,h)=>p+n[h]+n[h+l]).map((p,h)=>Math.floor((p-d[h]+r[h])/r[h]));return c.splice(0,0,a),c.splice(s?3:1,0,u),c},Li=[2,3,1,0],ml=(e,t)=>{if(!e||e.length!==2&&e.length!==3)throw new Error("Conv requires 2 or 3 inputs");if(e[0].dims.length>5)throw new Error("greater than 5D is not supported");if(e[0].dims.length!==e[1].dims.length)throw new Error("filter does not have same dimension as input");let i=e[0].dims[t.format==="NHWC"?e[0].dims.length-1:1],n=e[1].dims[1]*t.group;if(i!==n)throw new Error("FILTER_IN_CHANNEL should be equal to DATA_CHANNEL");if(e.length===3&&(e[2].dims.length!==1||e[1].dims[0]!==e[2].dims[0]))throw new Error("invalid bias");let r=e[0].dims.length-2;if(t.dilations.length!==r)throw new Error(`dilations should be ${r}D`);if(t.strides.length!==r)throw new Error(`strides should be ${r}D`);if(t.pads.length!==r*2)throw new Error(`pads should be ${r*2}D`);if(t.kernelShape.length!==0&&t.kernelShape.length!==e[1].dims.length-2)throw new Error("invalid kernel shape")},Ui=(e,t)=>{let i=e.kernelShape.slice();i.length<t[1].dims.length-2&&i.push(...Array(t[1].dims.length-2-i.length).fill(0));for(let s=2;s<t[1].dims.length;++s)i[s-2]===0&&(i[s-2]=t[1].dims[s]);let n=e.pads.slice();Ri.adjustPadsBasedOnAutoPad(t[0].dims,e.strides,e.dilations,i,n,e.format==="NHWC",e.autoPad);let r=Object.assign({},e);return Object.assign(r,{kernelShape:i,pads:n}),r},Jn=e=>{let t=qn(e),i=e.format,n=["NOTSET","VALID","SAME_UPPER","SAME_LOWER"][e.auto_pad],r=e.dilations,s=e.group,a=e.kernel_shape,o=e.pads,l=e.strides,u=e.w_is_const();return{autoPad:n,format:i,dilations:r,group:s,kernelShape:a,pads:o,strides:l,wIsConst:u,...t,cacheKey:`${e.format};${t.activation};`}},er=(e,t,i,n)=>{let r=i.format==="NHWC",s=hl(t[0].dims,t[1].dims,i.dilations,i.pads,i.strides,r);if(i.group!==1){let O=[t[0]];if(r){let z=e.kernelCustomData.wT??e.compute(_t(t[1],Li),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=z),O.push(z)}else O.push(t[1]);t.length===3&&O.push(t[2]),!e.adapterInfo.isArchitecture("ampere")&&r&&t[1].dims[0]===i.group&&t[1].dims[1]===1&&i.dilations[0]===1&&i.dilations[1]===1?e.compute(fl(O,i,s,n),{inputs:O}):e.compute(pl(O,i,s,n),{inputs:O});return}let a=t.length===3,o=t[0].dims[r?1:2],l=t[0].dims[r?2:3],u=t[0].dims[r?3:1],d=t[1].dims[2],c=t[1].dims[3],p=s[r?1:2],h=s[r?2:3],m=s[r?3:1],_=r&&d===o&&c===l&&i.pads[0]===0&&i.pads[1]===0;if(_||d===1&&c===1&&i.dilations[0]===1&&i.dilations[1]===1&&i.strides[0]===1&&i.strides[1]===1&&i.pads[0]===0&&i.pads[1]===0){let O=s[0],z,N,L,ie=[];if(r){let we=e.kernelCustomData.wT??e.compute(_t(t[1],Li),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];if(i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=we),_){let re=o*l*u;z=t[0].reshape([1,O,re]),N=we.reshape([1,re,m]),L=[1,O,m]}else z=t[0].reshape([O,o*l,u]),N=we.reshape([1,u,m]),L=[O,p*h,m];ie.push(z),ie.push(N)}else z=t[0].reshape([O,u,o*l]),N=t[1].reshape([1,m,u]),L=[O,m,p*h],ie.push(N),ie.push(z);a&&ie.push(t[2]);let ge=L[2],ce=ie[0].dims[ie[0].dims.length-1];ge<8&&ce<8?e.compute(Gn(ie,i,s,L,r,n),{inputs:ie}):e.compute(Vi(ie,i,s,L,r,n),{inputs:ie});return}let $=!0,y=e.kernelCustomData.wT??e.compute(_t(t[1],Li),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=y);let g=[t[0],y];a&&g.push(t[2]);let T=r?p*h:m,x=r?m:p*h,E=d*c*u;e.compute(al(g,i,s,T,x,E,a,$,n),{inputs:g})},gl=(e,t)=>{let i=t.format==="NHWC",n=[e.inputs[0].reshape(i?[e.inputs[0].dims[0],1,e.inputs[0].dims[1],e.inputs[0].dims[2]]:[e.inputs[0].dims[0],e.inputs[0].dims[1],1,e.inputs[0].dims[2]]),e.inputs[1].reshape([e.inputs[1].dims[0],e.inputs[1].dims[1],1,e.inputs[1].dims[2]])];e.inputs.length===3&&n.push(e.inputs[2]);let r=[0,t.pads[0],0,t.pads[1]],s=[1].concat(t.strides),a=[1].concat(t.dilations),o=[1].concat(t.kernelShape),l=Ui({...t,pads:r,strides:s,dilations:a,kernelShape:o},n);er(e,n,l,u=>i?[u[0],u[2],u[3]]:[u[0],u[1],u[3]])},_l=(e,t,i)=>{let n=i.format==="NHWC"?"channelsLast":"channelsFirst",r=Ui(i,t),s=i.autoPad==="NOTSET"?i.pads:i.autoPad,a=dl(t[0].dims,t[1].dims,i.strides,i.dilations,s,!1,n);e.compute(cl(t,r,a.outShape,[a.filterDepth,a.filterHeight,a.filterWidth],[a.padInfo.front,a.padInfo.top,a.padInfo.left],n))},tr=(e,t)=>{if(ml(e.inputs,t),e.inputs[0].dims.length===3)gl(e,t);else if(e.inputs[0].dims.length===5)_l(e,e.inputs,t);else{let i=Ui(t,e.inputs);er(e,e.inputs,i)}}}),yl,Dp=C(()=>{me(),zt(),be(),$e(),yl=(e,t,i)=>{let n=e.length>2,r=t.outputShape,s=t.format==="NHWC",a=t.group,o=e[1].dims,l=o[2]/a,u=o[3],d=s?Xe(l):1,c=s&&u===1&&l>=4,p=c?Math.floor(l/4)*4:Math.floor(l/d)*d,h=l-p,m=s?Xe(u):1,_=s?u===1?d:m:1,$=M.size(r)/m,y=[Math.ceil($/64),1,1];Ie("verbose",()=>`[conv2d_backprop_webgpu] dispatch = ${y}`);let g=["rank","rank"],T=[t.strides[0],t.strides[1]],x=[t.kernelShape[s?1:2],t.kernelShape[s?2:3]],E=[t.dilations[0],t.dilations[1]],O=[x[0]+(t.dilations[0]<=1?0:(t.kernelShape[s?1:2]-1)*(t.dilations[0]-1)),x[1]+(t.dilations[1]<=1?0:(t.kernelShape[s?2:3]-1)*(t.dilations[1]-1))],z=[O[0]-1-Math.floor((t.pads[0]+t.pads[2])/2),O[1]-1-Math.floor((t.pads[1]+t.pads[3])/2)],N=[{type:12,data:$},{type:12,data:T},{type:12,data:x},{type:12,data:E},{type:12,data:O},{type:6,data:z},{type:12,data:p},{type:12,data:l},{type:12,data:u},...de(e[0].dims,e[1].dims)];n&&(N.push(...de(e[2].dims)),g.push("rank")),N.push(...de(r));let L=ie=>{let ge=[{name:"output_size",type:"u32"},{name:"strides",type:"u32",length:T.length},{name:"filter_dims",type:"u32",length:x.length},{name:"dilations",type:"u32",length:x.length},{name:"effective_filter_dims",type:"u32",length:O.length},{name:"pads",type:"i32",length:z.length},{name:"input_channels_per_group_int",type:"u32"},{name:"input_channels_per_group",type:"u32"},{name:"output_channels_per_group",type:"u32"}],ce=at(e[0].dataType),we=s?1:2,re=s?2:3,ke=s?3:1,he=F("W",e[1].dataType,e[1].dims.length,_),le=F("Dy",e[0].dataType,e[0].dims.length,d),Re=[le,he];n&&Re.push(F("bias",e[2].dataType,[r[ke]].length,m));let pe=ae("result",e[0].dataType,r.length,m),He=()=>{let xe="";if(c)d===4?xe+=`
        let xValue = ${le.getByOffset("x_offset")};
        let wValue = ${he.getByOffset("w_offset")};
        dotProd = dotProd + dot(xValue, wValue);
        x_offset += 1u;
        w_offset += 1u;`:d===2?xe+=`
          dotProd = dotProd + dot(vec4<${ce}>(${le.getByOffset("x_offset")}, ${le.getByOffset("x_offset + 1u")}), vec4<${ce}>(${he.getByOffset("w_offset")}, ${he.getByOffset("w_offset + 1u")}));
          x_offset += 2u;
          w_offset += 2u;`:d===1&&(xe+=`
          dotProd = dotProd + dot(vec4<${ce}>(${le.getByOffset("x_offset")}, ${le.getByOffset("x_offset + 1u")}, ${le.getByOffset("x_offset + 2u")}, ${le.getByOffset("x_offset + 3u")}), vec4<${ce}>(${he.getByOffset("w_offset")}, ${he.getByOffset("w_offset + 1u")}, ${he.getByOffset("w_offset + 2u")}, ${he.getByOffset("w_offset + 3u")}));
          x_offset += 4u;
          w_offset += 4u;`);else if(xe+=`
                  let xValue = ${s?le.getByOffset(`${le.indicesToOffset(`${le.type.indices}(batch, idyR, idyC, inputChannel)`)} / ${d}`):le.get("batch","inputChannel","idyR","idyC")};
        `,d===1)xe+=`
          let w_offset = ${he.indicesToOffset(`${he.type.indices}(u32(wRPerm), u32(wCPerm), inputChannel, wOutChannel)`)};
          let wValue = ${he.getByOffset(`w_offset / ${_}`)};
          dotProd = dotProd + xValue * wValue;`;else for(let Le=0;Le<d;Le++)xe+=`
            let wValue${Le} = ${he.getByOffset(`${he.indicesToOffset(`${he.type.indices}(u32(wRPerm), u32(wCPerm), inputChannel + ${Le}, wOutChannel)`)} / ${_}`)};
            dotProd = dotProd + xValue[${Le}] * wValue${Le};`;return xe},U=()=>{if(h===0)return"";if(!c)throw new Error(`packInputAs4 ${c} is not true.`);let xe="";if(d===1){xe+="dotProd = dotProd";for(let Le=0;Le<h;Le++)xe+=`
            + ${le.getByOffset(`x_offset + ${Le}`)} * ${he.getByOffset(`w_offset + ${Le}`)}`;xe+=";"}else if(d===2){if(h!==2)throw new Error(`Invalid inputChannelsRemainder ${h}.`);xe+=`
          let xValue = ${le.getByOffset("x_offset")};
          let wValue = ${he.getByOffset("w_offset")};
          dotProd = dotProd + dot(xValue, wValue);`}return xe},te=`
            let outputIndices = ${pe.offsetToIndices(`global_idx * ${m}`)};
            let batch = ${pe.indicesGet("outputIndices",0)};
            let d1 = ${pe.indicesGet("outputIndices",ke)};
            let r = ${pe.indicesGet("outputIndices",we)};
            let c = ${pe.indicesGet("outputIndices",re)};
            let dyCorner = vec2<i32>(i32(r), i32(c)) - uniforms.pads;
            let dyRCorner = dyCorner.x;
            let dyCCorner = dyCorner.y;
            let groupId = d1 / uniforms.output_channels_per_group;
            let wOutChannel = d1 - groupId * uniforms.output_channels_per_group;
            // Convolve dy(?, ?, d2) with w(:, :, d1, d2) to compute dx(xR, xC, d1).
            // ? = to be determined. : = across all values in that axis.
            var dotProd = ${pe.type.value}(0.0);
            var wR: u32 = 0;
            if (uniforms.dilations.x == 1) {
              // Minimum wR >= 0 that satisfies (dyRCorner + wR) % (uniforms.strides.x) == 0
              wR = u32(((dyRCorner + i32(uniforms.strides.x) - 1) / i32(uniforms.strides.x)) * i32(uniforms.strides.x) - dyRCorner);
            }
            for (; wR < uniforms.effective_filter_dims.x; wR = wR + 1) {
              if (wR % uniforms.dilations.x != 0) {
                continue;
              }
              let dyR = (${ce}(dyRCorner) + ${ce}(wR)) / ${ce}(uniforms.strides[0]);
              let wRPerm = uniforms.filter_dims.x - 1 - wR / uniforms.dilations.x;
              if (dyR < 0.0 || dyR >= ${ce}(uniforms.Dy_shape[${we}]) || fract(dyR) > 0.0 ||
                  wRPerm < 0) {
                continue;
              }
              let idyR: u32 = u32(dyR);
              var wC: u32 = 0;
              if (uniforms.dilations.y == 1) {
                // Minimum wC >= 0 that satisfies (dyCCorner + wC) % (uniforms.strides.y) == 0
                wC = u32(((dyCCorner + i32(uniforms.strides.y) - 1) / i32(uniforms.strides.y)) * i32(uniforms.strides.y) - dyCCorner);
              }
              for (; wC < uniforms.effective_filter_dims.y; wC = wC + 1) {
                if (wC % uniforms.dilations.y != 0) {
                  continue;
                }
                let dyC = (${ce}(dyCCorner) + ${ce}(wC)) / ${ce}(uniforms.strides.y);
                let wCPerm = uniforms.filter_dims.y - 1 - wC / uniforms.dilations.y;
                if (dyC < 0.0 || dyC >= ${ce}(uniforms.Dy_shape[${re}]) ||
                    fract(dyC) > 0.0 || wCPerm < 0) {
                  continue;
                }
                let idyC: u32 = u32(dyC);
                var inputChannel = groupId * uniforms.input_channels_per_group;
                ${c?`
                var x_offset = ${le.indicesToOffset(`${le.type.indices}(batch, idyR, idyC, inputChannel)`)} / ${d};
                var w_offset = ${he.indicesToOffset(`${he.type.indices}(wRPerm, wCPerm, inputChannel, wOutChannel)`)} / ${_};
                  `:""}
                for (var d2: u32 = 0; d2 < uniforms.input_channels_per_group_int; d2 = d2 + ${c?4:d}) {
                  ${He()}
                  inputChannel = inputChannel + ${c?4:d};
                }
                ${U()}
                wC = wC + uniforms.strides.y - 1;
              }
              wR = wR + uniforms.strides[0] - 1;
            }
            let value = dotProd${n?` + bias[d1 / ${m}]`:""};
            ${pe.setByOffset("global_idx","value")};
          `;return`
    ${ie.registerUniforms(ge).declareVariables(...Re,pe)}
      ${ie.mainStart()}
      ${ie.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")};
    ${te}}`};return{name:"ConvTranspose2D",shaderCache:{hint:`${t.cacheKey};${d}${_}${m}${c}${h}`,inputDependencies:g},getRunData:()=>({dispatchGroup:{x:y[0],y:y[1],z:y[2]},outputs:[{dims:i?i(r):r,dataType:e[0].dataType}],programUniforms:N}),getShaderSource:L}}}),wl,bl,vl,ir,$l,xl,nr,Sl,kl,Bp=C(()=>{Dp(),Ht(),Ft(),wl=(e,t,i,n,r,s)=>(e-1)*t+i+(n-1)*r+1-s,bl=(e,t,i,n,r)=>{let s=Math.floor(e/2);t==="SAME_UPPER"?(i[n]=s,i[r]=e-s):t==="SAME_LOWER"&&(i[n]=e-s,i[r]=s)},vl=(e,t,i,n,r,s,a,o,l,u)=>{let d=e.length-2,c=u.length===0;l.length<d&&l.push(...Array(d-l.length).fill(0));let p=e[0],h=t[o?3:1]*r;for(let m=0,_=e.length-d-(o?1:0);m<d;++m,++_){let $=e[_],y=c?$*a[m]:u[m],g=wl($,a[m],s[m],t[_],i[m],y);bl(g,n,s,m,m+d),c&&u.push(a[m]*($-1)+l[m]+(t[_]-1)*i[m]+1-s[m]-s[m+d])}u.splice(0,0,p),u.splice(o?3:1,0,h)},ir=(e,t)=>{let i=e.kernelShape.slice();if(e.kernelShape.length===0||e.kernelShape.reduce((c,p)=>c*p,1)===0){i.length=0;for(let c=2;c<t[1].dims.length;++c)i.push(t[1].dims[c])}let n=e.format==="NHWC";i.splice(0,0,t[1].dims[0]),i.splice(n?3:1,0,t[1].dims[1]);let r=e.pads.slice(),s=e.outputShape.slice(),a=e.outputPadding.slice(),o=t[0].dims,l=e.dilations.slice();if(l.reduce((c,p)=>c+p,0)===0){let c=t[0].dims.length-2;l=new Array(c).fill(1)}let u=e.strides.slice();if(u.reduce((c,p)=>c+p,0)===0){let c=t[0].dims.length-2;u=new Array(c).fill(1)}vl(o,i,l,e.autoPad,e.group,r,u,n,a,s);let d=Object.assign({},e);return Object.assign(d,{kernelShape:i,pads:r,outputPadding:a,outputShape:s,dilations:l,strides:u}),d},$l=e=>{let t=qn(e),i=e.format,n=["NOTSET","VALID","SAME_UPPER","SAME_LOWER"][typeof e.autoPad>"u"?0:e.autoPad],r=e.dilations,s=e.group,a=e.kernelShape,o=e.pads,l=e.strides,u=e.wIsConst(),d=e.outputPadding,c=e.outputShape;return{autoPad:n,format:i,dilations:r,group:s,kernelShape:a,outputPadding:d,outputShape:c,pads:o,strides:l,wIsConst:u,...t,cacheKey:`${e.format};${t.activation};`}},xl=(e,t)=>{if(!e||e.length!==2&&e.length!==3)throw new Error("Conv requires 2 or 3 inputs");if(e[0].dims.length!==4&&e[0].dims.length!==3)throw new Error("currently only support 2-dimensional conv");if(e[0].dims.length!==e[1].dims.length)throw new Error("filter does not have same dimension as input");let i=e[0].dims[t.format==="NHWC"?e[0].dims.length-1:1],n=e[1].dims[0];if(i!==n)throw new Error("FILTER_IN_CHANNEL should be equal to DATA_CHANNEL");let r=e[1].dims[1]*t.group;if(e.length===3&&(e[2].dims.length!==1||e[2].dims[0]!==r))throw new Error("invalid bias");let s=e[0].dims.length-2;if(t.dilations.reduce((a,o)=>a+o,0)>0&&t.dilations.length!==s)throw new Error(`dilations should be ${s}D`);if(t.strides.reduce((a,o)=>a+o,0)>0&&t.strides.length!==s)throw new Error(`strides should be ${s}D`);if(t.pads.reduce((a,o)=>a+o,0)>0&&t.pads.length!==s*2)throw new Error(`pads should be ${s*2}D`);if(t.outputPadding.length!==s&&t.outputPadding.length!==0)throw new Error(`output_padding should be ${s}D`);if(t.kernelShape.reduce((a,o)=>a+o,0)>0&&t.kernelShape.length!==0&&t.kernelShape.length!==e[1].dims.length-2)throw new Error("invalid kernel shape");if(t.outputShape.length!==0&&t.outputShape.length!==e[0].dims.length-2)throw new Error("invalid output shape")},nr=(e,t,i,n)=>{let r=e.kernelCustomData.wT??e.compute(_t(t[1],[2,3,0,1]),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=r);let s=[t[0],r];t.length===3&&s.push(t[2]),e.compute(yl(s,i,n),{inputs:s})},Sl=(e,t)=>{let i=t.format==="NHWC",n=[e.inputs[0].reshape(i?[e.inputs[0].dims[0],1,e.inputs[0].dims[1],e.inputs[0].dims[2]]:[e.inputs[0].dims[0],e.inputs[0].dims[1],1,e.inputs[0].dims[2]]),e.inputs[1].reshape([e.inputs[1].dims[0],e.inputs[1].dims[1],1,e.inputs[1].dims[2]])];e.inputs.length===3&&n.push(e.inputs[2]);let r=t.kernelShape;(r.length===0||r[0]===0)&&(r=[e.inputs[1].dims[2]]);let s=t.dilations;(s.length===0||s[0]===0)&&(s=[1]);let a=t.strides;(a.length===0||a[0]===0)&&(a=[1]);let o=t.pads;o.length===0&&(o=[0,0]),o=[0,o[0],0,o[1]],a=[1].concat(a),s=[1].concat(s),r=[1].concat(r);let l=t.outputPadding;l=[0].concat(l);let u=ir({...t,pads:o,strides:a,dilations:s,kernelShape:r,outputPadding:l},n);nr(e,n,u,d=>i?[d[0],d[2],d[3]]:[d[0],d[1],d[3]])},kl=(e,t)=>{if(xl(e.inputs,t),e.inputs[0].dims.length===3)Sl(e,t);else{let i=ir(t,e.inputs);nr(e,e.inputs,i)}}}),Tl,Cl,El,Fp=C(()=>{me(),be(),Je(),$e(),Tl=(e,t,i,n)=>{let r=M.size(t),s=t.length,a=F("input",e,s),o=ae("output",e,s),l=i.dataType===6?i.getInt32Array()[0]:Number(i.getBigInt64Array()[0]),u=M.normalizeAxis(l,s),d=c=>{let p=` i32(${a.indicesGet("inputIndices","uniforms.axis")}) `,h=oe("uniforms.input_shape","uniforms.axis",s),m=n.reverse?p+(n.exclusive?" + 1":""):"0",_=n.reverse?h:p+(n.exclusive?"":" + 1");return`
                ${c.registerUniform("outputSize","u32").registerUniform("axis","u32").declareVariables(a,o)}
                ${c.mainStart()}
                  ${c.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
                  var inputIndices = ${o.offsetToIndices("global_idx")};
                  var sum = ${o.type.value}(0);
                  let first : i32 = ${m};
                  let last : i32 = ${_};
                  for (var i : i32 = first; i < last; i++) {
                    ${a.indicesSet("inputIndices","uniforms.axis","u32(i)")};
                    sum = sum + ${a.getByIndices("inputIndices")};
                  }
                  ${o.setByOffset("global_idx","sum")};
                }`};return{name:"CumSum",shaderCache:{hint:n.cacheKey,inputDependencies:["rank"]},getRunData:()=>({outputs:[{dims:t,dataType:e}],dispatchGroup:{x:Math.ceil(r/64)},programUniforms:[{type:12,data:r},{type:12,data:u},...de(t,t)]}),getShaderSource:d}},Cl=(e,t)=>{let i=e.inputs[0].dims,n=e.inputs[0].dataType,r=e.inputs[1];e.compute(Tl(n,i,r,t),{inputs:[0]})},El=e=>{let t=e.exclusive===1,i=e.reverse===1;return Be({exclusive:t,reverse:i})}}),Il,Al,zl,Ol,Rl,Np=C(()=>{me(),be(),Je(),$e(),Il=e=>{if(!e||e.length!==1)throw new Error("DepthToSpace requires 1 input.");if(e[0].dims.length!==4)throw new Error("DepthToSpace requires 4D input.")},Al=(e,t,i,n)=>{let r=[];r.push(`fn perm(i: ${n.type.indices}) -> ${i.type.indices} {
    var a: ${i.type.indices};`);for(let s=0;s<t;++s)r.push(i.indicesSet("a",e[s],`i[${s}]`));return r.push("return a;}"),r.join(`
`)},zl=(e,t)=>{let i,n,r,s,a,o,l=t.format==="NHWC",u=t.blocksize,d=t.mode==="DCR";l?([i,n,r,s]=e.dims,a=d?[i,n,r,u,u,s/u**2]:[i,n,r,s/u**2,u,u],o=d?[0,1,3,2,4,5]:[0,1,4,2,5,3]):([i,n,r,s]=[e.dims[0],e.dims[2],e.dims[3],e.dims[1]],a=d?[i,u,u,s/u**2,n,r]:[i,s/u**2,u,u,n,r],o=d?[0,3,4,1,5,2]:[0,1,4,2,5,3]);let c=e.reshape(a),p=c.dims.length,h=e.dataType,m=F("a",h,p),_=ae("output",h,p),$=y=>`
  ${y.registerUniform("output_size","u32").declareVariables(m,_)}

  ${Al(o,p,m,_)}

  ${y.mainStart()}
    ${y.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let indices = ${_.offsetToIndices("global_idx")};
    let aIndices = perm(indices);

    ${_.setByOffset("global_idx",m.getByIndices("aIndices"))}
  }`;return{name:"DepthToSpace",shaderCache:{hint:`${e.dims};${t.blocksize};${t.mode}`,inputDependencies:["rank"]},getRunData:y=>{let g=l?[i,n*u,r*u,s/u**2]:[i,s/u**2,n*u,r*u],T=M.size(g),x=c.dims,E=M.sortBasedOnPerm(x,o);return{outputs:[{dims:g,dataType:y[0].dataType}],dispatchGroup:{x:Math.ceil(T/64)},programUniforms:[{type:12,data:T},...de(x,E)]}},getShaderSource:$}},Ol=(e,t)=>{Il(e.inputs),e.compute(zl(e.inputs[0],t))},Rl=e=>Be({blocksize:e.blocksize,mode:e.mode,format:e.format})}),qi,_i,rr,Ml,Dl,Bl,Fl,sr,Nl,Pl,Vl,Pp=C(()=>{me(),be(),Je(),$e(),qi="[a-zA-Z]|\\.\\.\\.",_i="("+qi+")+",rr="^"+_i+"$",Ml="("+_i+",)*"+_i,Dl="^"+Ml+"$",Bl=class{constructor(e=-1){this.symbolToIndices=new Map,this.inputIndex=e}addSymbol(e,t){let i=this.symbolToIndices.get(e);i===void 0?i=[t]:i.push(t),this.symbolToIndices.set(e,i)}},Fl=class{constructor(e,t){this.equation=t,this.hasEllipsis=!1,this.symbolToInfo=new Map,this.lhs=new Array,this.outputDims=[];let[i,n]=t.includes("->")?t.split("->",2):[t,""];if(!i.match(RegExp(Dl)))throw new Error("Invalid LHS term");if(i.split(",").forEach((r,s)=>{let a=e[s].dims.slice();if(!r.match(RegExp(rr)))throw new Error("Invalid LHS term");let o=this.processTerm(r,!0,a,s);this.lhs.push(o)}),n==="")n+=[...this.symbolToInfo.entries()].filter(([r,s])=>s.count===1||r==="...").map(([r])=>r).join("");else if(!n.match(RegExp(_i)))throw new Error("Invalid RHS");n.match(RegExp(qi,"g"))?.forEach(r=>{if(r==="...")this.outputDims=this.outputDims.concat(this.ellipsisDims);else{let s=this.symbolToInfo.get(r);if(s===void 0)throw new Error("Invalid RHS symbol");this.outputDims.push(s.dimValue)}}),this.rhs=this.processTerm(n,!1,this.outputDims)}addSymbol(e,t,i){let n=this.symbolToInfo.get(e);if(n!==void 0){if(n.dimValue!==t&&n.count!==1)throw new Error("Dimension mismatch");n.count++,n.inputIndices.push(i)}else n={count:1,dimValue:t,inputIndices:[i]};this.symbolToInfo.set(e,n)}processTerm(e,t,i,n=-1){let r=i.length,s=!1,a=[],o=0;if(!e.match(RegExp(rr))&&!t&&e!=="")throw new Error("Invalid LHS term");let l=e.match(RegExp(qi,"g")),u=new Bl(n);return l?.forEach((d,c)=>{if(d==="..."){if(s)throw new Error("Only one ellipsis is allowed per input term");s=!0;let p=r-l.length+1;if(p<0)throw new Error("Ellipsis out of bounds");if(a=i.slice(o,o+p),this.hasEllipsis){if(this.ellipsisDims.length!==a.length||this.ellipsisDims.toString()!==a.toString())throw new Error("Ellipsis dimensions mismatch")}else if(t)this.hasEllipsis=!0,this.ellipsisDims=a;else throw new Error("Ellipsis must be specified in the LHS");for(let h=0;h<a.length;h++){let m=String.fromCharCode(48+h);u.addSymbol(m,c+h),this.addSymbol(m,i[o++],n)}}else u.addSymbol(d,c+(this.hasEllipsis?this.ellipsisDims.length-1:0)),this.addSymbol(d,i[o++],n)}),u}},sr=e=>e+"_max",Nl=(e,t,i,n)=>{let r=e.map(u=>u.length).map((u,d)=>F(`input${d}`,t,u)),s=M.size(n),a=ae("output",t,n.length),o=[...i.symbolToInfo.keys()].filter(u=>!i.rhs.symbolToIndices.has(u)),l=u=>{let d=[],c="var prod = 1.0;",p="var sum = 0.0;",h="sum += prod;",m=[],_=[],$=[],y=[],g=i.symbolToInfo.size===i.rhs.symbolToIndices.size;i.symbolToInfo.forEach((x,E)=>{if(i.rhs.symbolToIndices.has(E)){let O=i.rhs.symbolToIndices.get(E)?.[0];O!==void 0&&i.lhs.forEach((z,N)=>{if(x.inputIndices.includes(N)){let L=z.symbolToIndices.get(E);if(L===void 0)throw new Error("Invalid symbol error");L.forEach(ie=>{d.push(`${r[N].indicesSet(`input${N}Indices`,ie,a.indicesGet("outputIndices",O))}`)})}})}else i.lhs.forEach((O,z)=>{if(x.inputIndices.includes(z)){let N=O.symbolToIndices.get(E);if(N===void 0)throw new Error("Invalid symbol error");N.forEach(L=>{m.push(`${r[z].indicesSet(`input${z}Indices`,L,`${E}`)}`)}),y.push(`prod *= ${r[z].getByIndices(`input${z}Indices`)};`)}}),_.push(`for(var ${E}: u32 = 0; ${E} < uniforms.${sr(E)}; ${E}++) {`),$.push("}")});let T=g?[...d,`let sum = ${r.map((x,E)=>x.getByIndices(`input${E}Indices`)).join(" * ")};`]:[...d,p,..._,...m,c,...y,h,...$];return`
            ${u.registerUniforms(o.map(x=>({name:`${sr(x)}`,type:"u32"}))).registerUniform("outputSize","u32").declareVariables(...r,a)}

            ${u.mainStart()}
            ${u.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
            var outputIndices = ${a.offsetToIndices("global_idx")};
            ${r.map((x,E)=>`var input${E}Indices: ${r[E].type.indices};`).join(`
`)}
            ${T.join(`
`)};
            ${a.setByOffset("global_idx","sum")};
          }`};return{name:"Einsum",shaderCache:{hint:i.equation,inputDependencies:e.map(()=>"rank")},getRunData:()=>{let u=o.filter(c=>i.symbolToInfo.has(c)).map(c=>({type:12,data:i.symbolToInfo.get(c)?.dimValue||0}));u.push({type:12,data:s});let d=e.map((c,p)=>[...de(c)]).reduce((c,p)=>c.concat(p),u);return d.push(...de(n)),{outputs:[{dims:n,dataType:t}],dispatchGroup:{x:Math.ceil(s/64)},programUniforms:d}},getShaderSource:l}},Pl=(e,t)=>{let i=new Fl(e.inputs,t.equation),n=i.outputDims,r=e.inputs.map((s,a)=>s.dims);e.compute(Nl(r,e.inputs[0].dataType,i,n))},Vl=e=>{let t=e.equation.replace(/\s+/g,"");return Be({equation:t})}}),Ll,ar,Ul,ql,Wl,Vp=C(()=>{me(),be(),$e(),Ll=e=>{if(!e||e.length!==2)throw new Error("Expand requires 2 input.");let t=e[0].dims,i=Array.from(e[1].getBigInt64Array(),Number),n=i.length<t.length?0:i.length-t.length,r=t.length<i.length?0:t.length-i.length;for(;n<i.length&&r<t.length;++n,++r)if(i[n]!==t[r]&&i[n]!==1&&t[r]!==1)throw new Error("Expand requires shape to be broadcastable to input")},ar=(e,t)=>{let i=e.length-t.length,n=[];for(let r=0;r<i;++r)n.push(e[r]);for(let r=0;r<t.length;++r)n.push(t[r]===1?e[r+i]:t[r]);return n},Ul=(e,t)=>e.length>t.length?ar(e,t):ar(t,e),ql=e=>{let t=e[0].dims,i=Array.from(e[1].getBigInt64Array(),Number),n=Ul(t,i),r=e[0].dataType,s=r===9||M.size(t)===1,a=r===9||t.length>0&&t[t.length-1]%4===0?4:1,o=s||n.length>0&&n[n.length-1]%4===0?4:1,l=Math.ceil(M.size(n)/o),u=c=>{let p=F("input",r,t.length,a),h=ae("output",r,n.length,o),m;if(r===9){let _=($,y,g="")=>`
          let outputIndices${y} = ${h.offsetToIndices(`outputOffset + ${y}u`)};
          let offset${y} = ${p.broadcastedIndicesToOffset(`outputIndices${y}`,h)};
          let index${y} = offset${y} / 4u;
          let component${y} = offset${y} % 4u;
          ${$}[${y}] = ${g}(${p.getByOffset(`index${y}`)}[component${y}]);
        `;m=`
        let outputOffset = global_idx * ${o};
        var data = vec4<u32>(0);
        ${_("data",0,"u32")}
        ${_("data",1,"u32")}
        ${_("data",2,"u32")}
        ${_("data",3,"u32")}
        ${h.setByOffset("global_idx","data")}
      }`}else m=`
        let outputIndices = ${h.offsetToIndices(`global_idx * ${o}`)};
        let inputOffset = ${p.broadcastedIndicesToOffset("outputIndices",h)};
        let data = ${h.type.value}(${p.getByOffset(`inputOffset / ${a}`)});
        ${h.setByOffset("global_idx","data")}
      }`;return`
    ${c.registerUniform("vec_size","u32").declareVariables(p,h)}
    ${c.mainStart()}
    ${c.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.vec_size")}
    ${m}`},d=[{type:12,data:l},...de(t,n)];return{name:"Expand",shaderCache:{hint:`${n.length};${a}${o}`,inputDependencies:["rank"]},getShaderSource:u,getRunData:()=>({outputs:[{dims:n,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:d})}},Wl=e=>{Ll(e.inputs),e.compute(ql(e.inputs),{inputs:[0]})}}),Gl,jl,Lp=C(()=>{me(),be(),$e(),Un(),Gl=e=>{let t=e[0].dataType,i=M.size(e[0].dims),n=M.size(e[1].dims),r=n%4===0,s=a=>{let o=F("x",t,[1],4),l=F("bias",t,[1],4),u=ae("y",t,[1],4),d=[{name:"output_vec_size",type:"u32"},{name:"bias_size",type:"u32"}],c=h=>`
      let bias${h}_offset: u32 = (global_idx * 4 + ${h}) % uniforms.bias_size;
      let bias${h} = ${l.getByOffset(`bias${h}_offset / 4`)}[bias${h}_offset % 4];`,p=r?`
      let bias = ${l.getByOffset("global_idx % (uniforms.bias_size / 4)")};`:`${c(0)}${c(1)}${c(2)}${c(3)}
      let bias = ${o.type.value}(bias0, bias1, bias2, bias3);`;return`${a.registerUniforms(d).declareVariables(o,l,u)}

    ${Vn(dt(t))}

    ${a.mainStart(ni)}
      ${a.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_vec_size")}

      let x = ${o.getByOffset("global_idx")};
      ${p}
      let x_in = x + bias;
      ${u.setByOffset("global_idx",Ln("x_in"))}
    }`};return{name:"FastGeluWithBias",shaderCache:{hint:`${r}`,inputDependencies:["type","type"]},getShaderSource:s,getRunData:a=>({outputs:[{dims:a[0].dims,dataType:a[0].dataType}],programUniforms:[{type:12,data:Math.ceil(i/4)},{type:12,data:n}],dispatchGroup:{x:Math.ceil(i/ni/4)}})}},jl=e=>{e.inputs.length<2||M.size(e.inputs[1].dims)===0?To(e):e.compute(Gl(e.inputs))}}),Hl,Kl,Ql,Zl,Up=C(()=>{me(),be(),Je(),$e(),Hl=e=>{if(!e||e.length!==2)throw new Error("Gather requires 2 inputs.")},Kl=(e,t)=>{let i=e[0].dims,n=e[1].dims,r=i.length,s=M.normalizeAxis(t.axis,r),a=i.slice(0);a.splice(s,1,...n);let o=i[s],l=e[0].dataType===9?4:1,u=Math.ceil(M.size(a)/l),d=[{type:12,data:u},{type:6,data:o},{type:12,data:s},...de(e[0].dims,e[1].dims,a)],c=p=>{let h=F("data",e[0].dataType,e[0].dims.length,l),m=F("inputIndices",e[1].dataType,e[1].dims.length),_=ae("output",e[0].dataType,a.length,l),$=g=>{let T=n.length,x=`var indicesIndices${g}  = ${m.type.indices}(0);`;for(let E=0;E<T;E++)x+=`${T>1?`indicesIndices${g}[${E}]`:`indicesIndices${g}`} = ${a.length>1?`outputIndices${g}[uniforms.axis + ${E}]`:`outputIndices${g}`};`;x+=`
          var idx${g} = ${m.getByIndices(`indicesIndices${g}`)};
          if (idx${g} < 0) {
            idx${g} = idx${g} + uniforms.axisDimLimit;
          }
          var dataIndices${g} : ${h.type.indices};
        `;for(let E=0,O=0;E<r;E++)E===s?(x+=`${r>1?`dataIndices${g}[${E}]`:`dataIndices${g}`} = u32(idx${g});`,O+=T):(x+=`${r>1?`dataIndices${g}[${E}]`:`dataIndices${g}`} = ${a.length>1?`outputIndices${g}[${O}]`:`outputIndices${g}`};`,O++);return x},y;if(e[0].dataType===9){let g=(T,x,E="")=>`
          let outputIndices${x} = ${_.offsetToIndices(`outputOffset + ${x}u`)};
          ${$(x)};
          let offset${x} = ${h.indicesToOffset(`dataIndices${x}`)};
          let index${x} = offset${x} / 4u;
          let component${x} = offset${x} % 4u;
          ${T}[${x}] = ${E}(${h.getByOffset(`index${x}`)}[component${x}]);
        `;y=`
        let outputOffset = global_idx * ${l};
        var value = vec4<u32>(0);
        ${g("value",0,"u32")}
        ${g("value",1,"u32")}
        ${g("value",2,"u32")}
        ${g("value",3,"u32")}
        ${_.setByOffset("global_idx","value")}
      `}else y=`
      let outputIndices = ${_.offsetToIndices("global_idx")};
      ${$("")};
      let value = ${h.getByIndices("dataIndices")};
      ${_.setByOffset("global_idx","value")};
      `;return`
      ${p.registerUniform("outputSize","u32").registerUniform("axisDimLimit","i32").registerUniform("axis","u32").declareVariables(h,m,_)}
      ${p.mainStart()}
        ${p.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
        ${y}
      }`};return{name:"Gather",shaderCache:{hint:t.cacheKey,inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:a,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(u/64)},programUniforms:d}),getShaderSource:c}},Ql=e=>Be({axis:e.axis}),Zl=(e,t)=>{let i=e.inputs;Hl(i),e.compute(Kl(e.inputs,t))}}),Xl,Yl,Jl,qp=C(()=>{me(),be(),$e(),Xl=(e,t,i,n,r,s,a,o,l)=>{let u=[{type:12,data:s},{type:12,data:n},{type:12,data:r},{type:12,data:i},{type:12,data:a},{type:12,data:o},{type:12,data:l}],d=[s];u.push(...de(t.dims,d));let c=p=>{let h=F("indices_data",t.dataType,t.dims.length),m=ae("input_slice_offsets_data",12,1,1),_=[h,m],$=[{name:"output_size",type:"u32"},{name:"batch_dims",type:"u32"},{name:"input_dims",type:"u32",length:r.length},{name:"sizes_from_slice_dims_data",type:"u32",length:i.length},{name:"num_slices_per_batch",type:"u32"},{name:"input_batch_stride",type:"u32"},{name:"num_slice_dims",type:"u32"}];return`
  ${p.registerUniforms($).declareVariables(..._)}
  ${p.mainStart()}
    ${p.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    let batch_idx = global_idx / uniforms.num_slices_per_batch;
    let base_offset = batch_idx * uniforms.input_batch_stride;

    let slice_indices_base_offset = global_idx * uniforms.num_slice_dims;
    var relative_slice_offset = 0;
    for (var dim_idx = 0u; dim_idx < uniforms.num_slice_dims; dim_idx ++) {
      var index = i32(indices_data[dim_idx + slice_indices_base_offset].x);
      let input_dim_idx = uniforms.batch_dims + dim_idx;
      if (index < 0) {
        ${r.length===1?"index += i32(uniforms.input_dims);":"index += i32(uniforms.input_dims[input_dim_idx]);"}
      }
      ${i.length===1?"relative_slice_offset += index * i32(uniforms.sizes_from_slice_dims_data);":"relative_slice_offset += index * i32(uniforms.sizes_from_slice_dims_data[dim_idx]);"}
    }

    input_slice_offsets_data[global_idx] =  base_offset + u32(relative_slice_offset);
  }`};return e.compute({name:"computeSliceOffsets",shaderCache:{hint:`${r.length}_${i.length}`,inputDependencies:["rank"]},getRunData:()=>({outputs:[{dims:d,dataType:e.inputs[1].dataType}],dispatchGroup:{x:Math.ceil(s/64)},programUniforms:u}),getShaderSource:c},{inputs:[t],outputs:[-1]})[0]},Yl=(e,t)=>{let i=e.inputs,n=i[0].dims,r=i[0].dataType,s=i[1].dims,a=s[s.length-1],o=M.sizeToDimension(s,s.length-1),l=M.sizeFromDimension(n,t.batchDims+a),u=M.sizeToDimension(n,t.batchDims),d=M.sizeFromDimension(n,t.batchDims),c=o/u,p=new Array(a),h=l;for(let x=0;x<a;++x)p[a-1-x]=h,h*=n[t.batchDims+a-1-x];let m=Xl(e,i[1],p,t.batchDims,n,o,c,d,a),_=t.batchDims+a;if(_>n.length)throw new Error("last dimension of indices must not be larger than rank of input tensor");let $=s.slice(0,-1).concat(n.slice(_)),y=M.size($),g=[{type:12,data:y},{type:12,data:l},...de(i[0].dims,m.dims,$)],T=x=>{let E=F("data",i[0].dataType,i[0].dims.length),O=F("slice_offsets",12,m.dims.length),z=ae("output",i[0].dataType,$.length);return`
          ${x.registerUniform("output_size","u32").registerUniform("slice_size","u32").declareVariables(E,O,z)}
            ${x.mainStart()}
            ${x.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
          let slice_offset = slice_offsets[global_idx / uniforms.slice_size];
          output[global_idx] = data[u32(slice_offset) + global_idx % uniforms.slice_size];
        }`};e.compute({name:"GatherND",shaderCache:{hint:t.cacheKey,inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:$,dataType:r}],dispatchGroup:{x:Math.ceil(y/64)},programUniforms:g}),getShaderSource:T},{inputs:[i[0],m]})},Jl=e=>({batchDims:e.batch_dims,cacheKey:""})}),eu,tu,iu,nu,Wp=C(()=>{me(),be(),Je(),$e(),eu=(e,t)=>{if(e.length<3||e.length>4)throw new Error("GatherBlockQuantized requires 3 or 4 inputs.");let i=M.normalizeAxis(t.quantizeAxis,e[0].dims.length),n=t.blockSize,r=e[0],s=e[2],a=e.length===4?e[3]:void 0;if(s.dims.length!==r.dims.length||!r.dims.map((o,l)=>l===i?Math.ceil(o/n)===s.dims[l]:o===s.dims[l]).reduce((o,l)=>o&&l,!0))throw new Error("Scales must have the same rank as the input tensor and the dims should match except on gatherAxis.");if(a){if(a.dataType!==r.dataType)throw new Error("Zero point must have the same data type as the input tensor.");if(a.dims.length!==s.dims.length||!a.dims.map((o,l)=>o===s.dims[l]).reduce((o,l)=>o&&l,!0))throw new Error("Zero point must have the same rank as the input tensor and the dims should match except on quantizeAxis.")}},tu=(e,t)=>{let i=e[0].dims,n=e[1].dims,r=i.length,s=M.normalizeAxis(t.gatherAxis,r),a=M.normalizeAxis(t.quantizeAxis,r),o=i.slice(0);o.splice(s,1,...n);let l=M.size(o),u=e[2].dataType,d=e[0].dataType===22,c=[{type:12,data:l},{type:12,data:a},{type:12,data:s},{type:12,data:t.blockSize},...de(...e.map((h,m)=>h.dims),o)],p=h=>{let m=F("data",e[0].dataType,e[0].dims.length),_=F("inputIndices",e[1].dataType,e[1].dims.length),$=F("scales",e[2].dataType,e[2].dims.length),y=e.length>3?F("zeroPoint",e[3].dataType,e[3].dims.length):void 0,g=ae("output",u,o.length),T=[m,_,$];y&&T.push(y);let x=[{name:"output_size",type:"u32"},{name:"quantize_axis",type:"u32"},{name:"gather_axis",type:"u32"},{name:"block_size",type:"u32"}];return`
        ${h.registerUniforms(x).declareVariables(...T,g)}
        ${h.mainStart()}
        let output_indices = ${g.offsetToIndices("global_idx")};
        var indices_indices = ${_.type.indices}(0);
        ${n.length>1?`
          for (var i: u32 = 0; i < ${n.length}; i++) {
            let index = ${g.indicesGet("output_indices","uniforms.gather_axis + i")};
            ${_.indicesSet("indices_indices","i","index")};
          }`:`indices_indices = ${g.indicesGet("output_indices","uniforms.gather_axis")};`};
        var data_indices = ${m.type.indices}(0);
        for (var i: u32 = 0; i < uniforms.gather_axis; i++) {
          let index = ${g.indicesGet("output_indices","i")};
          ${m.indicesSet("data_indices","i","index")};
        }
        var index_from_indices = ${_.getByIndices("indices_indices")};
        if (index_from_indices < 0) {
          index_from_indices += ${i[s]};
        }
        ${m.indicesSet("data_indices","uniforms.gather_axis","u32(index_from_indices)")};
        for (var i = uniforms.gather_axis + 1; i < ${o.length}; i++) {
          let index = ${g.indicesGet("output_indices",`i + ${n.length} - 1`)};
          ${m.indicesSet("data_indices","i","index")};
        }
        let data_offset = ${m.indicesToOffset("data_indices")};
        let data_index = data_offset % 8;
        // Convert 4-bit packed data to 8-bit packed data.
        let packed_4bit_quantized_data = ${m.getByOffset("data_offset / 8")};
        let packed_8bit_quantized_data = (packed_4bit_quantized_data >> (4 * (data_index % 2))) & 0x0f0f0f0f;
        let quantized_data_vec = ${d?"unpack4xI8":"unpack4xU8"}(u32(packed_8bit_quantized_data));
        let quantized_data = quantized_data_vec[data_index / 2];
        var scale_indices = data_indices;
        let quantize_axis_index = ${$.indicesGet("data_indices","uniforms.quantize_axis")} / uniforms.block_size;
        ${$.indicesSet("scale_indices","uniforms.quantize_axis","quantize_axis_index")};
        var scale = ${$.getByIndices("scale_indices")};
        ${y?`
              let zero_point_indices = scale_indices;
              let zero_point_offset = ${y.indicesToOffset("zero_point_indices")};
              let zero_point_index = zero_point_offset % 8;
              let packed_4bit_zero_points = ${y.getByOffset("zero_point_offset / 8")};
              let packed_8bit_zero_points = (packed_4bit_zero_points >> (4 * (zero_point_index % 2))) & 0x0f0f0f0f;
              let zero_point_vec = ${d?"unpack4xI8":"unpack4xU8"}(u32(packed_8bit_zero_points));
              let zero_point = zero_point_vec[zero_point_index / 2];`:"var zero_point = 0"};
        let dequantized_data = ${dt(u)}(quantized_data - zero_point) * scale;
        ${g.setByOffset("global_idx","dequantized_data")};
    }`};return{name:"GatherBlockQuantized",shaderCache:{hint:`${t.cacheKey};${e.filter((h,m)=>m!==1).map(h=>h.dims.join("_")).join(";")}`,inputDependencies:Array.from({length:e.length},(h,m)=>"rank")},getRunData:()=>({outputs:[{dims:o,dataType:u}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:c}),getShaderSource:p}},iu=(e,t)=>{let i=e.inputs;eu(i,t),e.compute(tu(e.inputs,t))},nu=e=>Be({blockSize:e.blockSize,gatherAxis:e.gatherAxis,quantizeAxis:e.quantizeAxis})}),ru,su,au,ou,Gp=C(()=>{me(),be(),Je(),$e(),ru=e=>{if(!e||e.length!==2)throw new Error("GatherElements requires 2 inputs.");if(e[0].dims.length<1)throw new Error("GatherElements requires that the data input be rank >= 1.");if(e[0].dims.length!==e[1].dims.length)throw new Error(`GatherElements requires that the data input and
                     indices input tensors be of same rank.`)},su=(e,t)=>{let i=e[0].dims,n=e[0].dataType,r=i.length,s=e[1].dims,a=e[1].dataType,o=M.normalizeAxis(t.axis,r),l=i[o],u=s.slice(0),d=M.size(u),c=F("input",n,r),p=F("indicesInput",a,s.length),h=ae("output",n,u.length),m=[{type:12,data:d},{type:6,data:l},{type:12,data:o}];return m.push(...de(i,s,u)),{name:"GatherElements",shaderCache:{inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:u,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(d/64)},programUniforms:m}),getShaderSource:_=>`
      ${_.registerUniform("outputSize","u32").registerUniform("axisDimLimit","i32").registerUniform("axis","u32").declareVariables(c,p,h)}
      ${_.mainStart()}
      ${_.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}

      let outputIndices = ${h.offsetToIndices("global_idx")};

      var idx = ${p.getByOffset("global_idx")};
      if (idx < 0) {
        idx = idx + uniforms.axisDimLimit;
      }
      var inputIndices = ${c.type.indices}(outputIndices);
      ${c.indicesSet("inputIndices","uniforms.axis","u32(idx)")};
      let value = ${c.getByIndices("inputIndices")};

      ${h.setByOffset("global_idx","value")};
  }`}},au=e=>Be({axis:e.axis}),ou=(e,t)=>{let i=e.inputs;ru(i),e.compute(su(e.inputs,t))}}),lu,uu,du,cu,jp=C(()=>{me(),be(),$e(),lu=e=>{if(!e)throw new Error("Input is missing");if(e.length<2||e.length>3)throw new Error("Invaid input number.");if(e.length===3&&e[2].dims.length>2)throw new Error("Invalid input shape of C");if(e[0].dataType!==e[1].dataType||e.length===3&&e[0].dataType!==e[2].dataType)throw new Error("Input types are mismatched")},uu=(e,t)=>{let i=e[0].dims.slice(),n=e[1].dims.slice(),[r,s,a]=ws.getShapeOfGemmResult(i,t.transA,n,t.transB,e.length===3?e[2].dims:void 0),o=[r,s];if(!o)throw new Error("Can't use gemm on the given tensors");let l=16,u=Math.ceil(s/l),d=Math.ceil(r/l),c=!0,p=M.size(o),h=[{type:12,data:c?u:p},{type:12,data:r},{type:12,data:s},{type:12,data:a},{type:1,data:t.alpha},{type:1,data:t.beta}],m=["type","type"];e.length===3&&(h.push(...de(e[2].dims)),m.push("rank")),h.push(...de(o));let _=y=>{let g="";t.transA&&t.transB?g="value += a[k * uniforms.M + m] * b[n * uniforms.K + k];":t.transA&&!t.transB?g="value += a[k * uniforms.M + m] * b[k * uniforms.N + n];":!t.transA&&t.transB?g="value += a[m * uniforms.K + k] * b[n * uniforms.K + k];":!t.transA&&!t.transB&&(g="value += a[m * uniforms.K + k] * b[k * uniforms.N + n];");let T=t.alpha===1?"":"value *= uniforms.alpha;",x=F("a",e[0].dataType,e[0].dims),E=F("b",e[1].dataType,e[1].dims),O=x.type.value,z=null,N=[x,E];e.length===3&&(z=F("c",e[2].dataType,e[2].dims.length),N.push(z));let L=ae("output",e[0].dataType,o.length);N.push(L);let ie=[{name:"output_size",type:"u32"},{name:"M",type:"u32"},{name:"N",type:"u32"},{name:"K",type:"u32"},{name:"alpha",type:"f32"},{name:"beta",type:"f32"}];return`
  ${y.registerUniforms(ie).declareVariables(...N)}

  ${y.mainStart()}
    ${y.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let m = global_idx / uniforms.N;
    let n = global_idx % uniforms.N;

    var value = ${O}(0);
    for (var k: u32 = 0u; k < uniforms.K; k++) {
      ${g}
    }

    ${T}
    ${z!=null?`let cOffset = ${z.broadcastedIndicesToOffset("vec2(m, n)",L)}; value += ${O}(uniforms.beta) * ${z.getByOffset("cOffset")};`:""}
    output[global_idx] = value;
  }`},$=y=>{let g=F("a",e[0].dataType,e[0].dims),T=F("b",e[1].dataType,e[1].dims),x=null,E=[g,T];e.length===3&&(x=F("c",e[2].dataType,e[2].dims.length),E.push(x));let O=ae("output",e[0].dataType,o.length);E.push(O);let z=[{name:"num_tile_n",type:"u32"},{name:"M",type:"u32"},{name:"N",type:"u32"},{name:"K",type:"u32"},{name:"alpha",type:"f32"},{name:"beta",type:"f32"}],N="",L="";t.transA&&t.transB?(L=`
      var col = tile_row_start + local_id.x;
      var row = k_start + local_id.y;
      if (col < uniforms.M && row < uniforms.K) {
        tile_a[local_id.y][local_id.x] = a[row * uniforms.M + col];
      } else {
        tile_a[local_id.y][local_id.x] = ${g.type.value}(0);
      }

      col = k_start + local_id.x;
      row = tile_col_start + local_id.y;
      if (col < uniforms.K && row < uniforms.N) {
        tile_b[local_id.y][local_id.x] = b[row * uniforms.K + col];
      } else {
        tile_b[local_id.y][local_id.x] = ${T.type.value}(0);
      }
      `,N="value += tile_a[k][local_id.y] * tile_b[local_id.x][k];"):t.transA&&!t.transB?(L=`
      var col = tile_row_start + local_id.x;
      var row = k_start + local_id.y;
      if (col < uniforms.M && row < uniforms.K) {
        tile_a[local_id.y][local_id.x] = a[row * uniforms.M + col];
      } else {
        tile_a[local_id.y][local_id.x] = ${g.type.value}(0);
      }

      col = tile_col_start + local_id.x;
      row = k_start + local_id.y;
      if (col < uniforms.N && row < uniforms.K) {
        tile_b[local_id.y][local_id.x] = b[row * uniforms.N + col];
      } else {
        tile_b[local_id.y][local_id.x] = ${T.type.value}(0);
      }
      `,N="value += tile_a[k][local_id.y] * tile_b[k][local_id.x];"):!t.transA&&t.transB?(L=`
      var col = k_start + local_id.x;
      var row = tile_row_start + local_id.y;
      if (col < uniforms.K && row < uniforms.M) {
        tile_a[local_id.y][local_id.x] = a[row * uniforms.K + col];
      } else {
        tile_a[local_id.y][local_id.x] = ${g.type.value}(0);
      }

      col = k_start + local_id.x;
      row = tile_col_start + local_id.y;
      if (col < uniforms.K && row < uniforms.N) {
        tile_b[local_id.y][local_id.x] = b[row * uniforms.K + col];
      } else {
        tile_b[local_id.y][local_id.x] = ${T.type.value}(0);
      }
      `,N="value += tile_a[local_id.y][k] * tile_b[local_id.x][k];"):!t.transA&&!t.transB&&(L=`
      var col = k_start + local_id.x;
      var row = tile_row_start + local_id.y;
      if (col < uniforms.K && row < uniforms.M) {
        tile_a[local_id.y][local_id.x] = a[row * uniforms.K + col];
      } else {
        tile_a[local_id.y][local_id.x] = ${g.type.value}(0);
      }

      col = tile_col_start + local_id.x;
      row = k_start + local_id.y;
      if (col < uniforms.N && row < uniforms.K) {
        tile_b[local_id.y][local_id.x] = b[row * uniforms.N + col];
      } else {
        tile_b[local_id.y][local_id.x] = ${T.type.value}(0);
      }
      `,N="value += tile_a[local_id.y][k] * tile_b[k][local_id.x];");let ie=t.alpha===1?"":"value *= uniforms.alpha;";return`
  ${y.registerUniforms(z).declareVariables(...E)}
  var<workgroup> tile_a: array<array<${g.type.storage}, ${l}>, ${l}>;
  var<workgroup> tile_b: array<array<${T.type.storage}, ${l}>, ${l}>;
  ${y.mainStart([l,l,1])}
    let tile_col_start = (workgroup_index % uniforms.num_tile_n) * ${l};
    let tile_row_start = (workgroup_index / uniforms.num_tile_n) * ${l};
    let num_tiles = (uniforms.K - 1) / ${l} + 1;
    var k_start = 0u;
    var value = ${O.type.value}(0);
    for (var t: u32 = 0u; t < num_tiles; t++) {
      ${L}
      k_start = k_start + ${l};
      workgroupBarrier();

      for (var k: u32 = 0u; k < ${l}; k++) {
        ${N}
      }
      workgroupBarrier();
    }

    ${ie}
    let m = tile_row_start + local_id.y;
    let n = tile_col_start + local_id.x;
    ${x!=null?`let cOffset = ${x.broadcastedIndicesToOffset("vec2(m, n)",O)}; value += ${O.type.value}(uniforms.beta) * ${x.getByOffset("cOffset")};`:""}
    if (m < uniforms.M && n < uniforms.N) {
      output[m * uniforms.N + n] = value;
    }
  }`};return c?{name:"GemmShared",shaderCache:{hint:`${t.cacheKey}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:o,dataType:e[0].dataType}],dispatchGroup:{x:u*d},programUniforms:h}),getShaderSource:$}:{name:"Gemm",shaderCache:{hint:`${t.cacheKey}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:o,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:h}),getShaderSource:_}},du=e=>{let t=e.transA,i=e.transB,n=e.alpha,r=e.beta;return{transA:t,transB:i,alpha:n,beta:r,cacheKey:`${e.transA};${e.transB};${e.alpha===1}`}},cu=(e,t)=>{lu(e.inputs),e.compute(uu(e.inputs,t))}}),Tt,Ot,Kt,Qt,pu,fu,hu,mu,gu,_u,yu,wu,bu,vu,Hp=C(()=>{me(),be(),Je(),$e(),[Tt,Ot,Kt,Qt]=[0,1,2,3],pu=e=>{if(e[0].dims.length!==4)throw new Error("only 4-D tensor is supported.");if(e[0].dims.length!==e[1].dims.length)throw new Error("input dimensions must be equal to grid dimensions");if(e[0].dims.length-2!==e[1].dims[e[1].dims.length-1])throw new Error(`last dimension of grid must be equal to ${e[0].dims.length-2}`);if(e[0].dims[0]!==e[1].dims[0])throw new Error("grid batch size must match input batch size")},fu=`
  fn gs_get_cubic_coeffs(x: f32) -> vec4<f32> {
    let cubic_alpha = -0.75f;
    let x_abs = abs(x);
    var coeffs: vec4<f32>;
    coeffs[0] = (((cubic_alpha * (x_abs + 1) - 5 * cubic_alpha) * (x_abs + 1) + 8 * cubic_alpha) * (x_abs + 1) - 4 * cubic_alpha);
    coeffs[1] = (((cubic_alpha + 2) * x_abs - (cubic_alpha + 3)) * x_abs * x_abs + 1);
    coeffs[2] = (((cubic_alpha + 2) * (1 - x_abs) - (cubic_alpha + 3)) * (1 - x_abs) * (1 - x_abs) + 1);
    coeffs[3] = (((cubic_alpha * (2 - x_abs) - 5 * cubic_alpha) * (2 - x_abs) + 8 * cubic_alpha) * (2 - x_abs) - 4 * cubic_alpha);
    return coeffs;
  }
`,hu=e=>`
  fn gs_bicubic_interpolate(p: mat4x4<${e}>, x: f32, y: f32) -> ${e} {
    var v: vec4<f32>;
    var coeffs = gs_get_cubic_coeffs(x);
    for (var i = 0; i < 4; i++) {
      v[i] = coeffs[0] * p[i][0] + coeffs[1] * p[i][1] + coeffs[2] * p[i][2] + coeffs[3] * p[i][3];
    }
    coeffs = gs_get_cubic_coeffs(y);
    let pixel = ${e}(coeffs[0] * v[0] + coeffs[1] * v[1] + coeffs[2] * v[2] + coeffs[3] * v[3]);
    return pixel;
  }
`,mu=e=>`
  fn gs_denormalize(n: f32, length: i32) -> f32 {
    ${e.alignCorners===0?`
    // alignCorners: false => [-1, 1] to [-0.5, length - 0.5]
    return ((n + 1.0) * f32(length) - 1.0) / 2.0;
    `:`
    // alignCorners: true => [-1, 1] to [0, length - 1]
    return (n + 1.0) / 2.0 * (f32(length - 1));
    `}
  }
`,gu=e=>`
  ${e.paddingMode==="reflection"?`
      fn gs_reflect(x: i32, x_min: f32, x_max: f32) -> u32 {
        var dx = 0.0;
        var fx = f32(x);
        let range = x_max - x_min;
        if (fx < x_min) {
          dx = x_min - fx;
          let n = u32(dx / range);
          let r = dx - f32(n) * range;
          if (n % 2 == 0) {
            fx = x_min + r;
          } else {
            fx = x_max - r;
          }
        } else if (fx > x_max) {
          dx = fx - x_max;
          let n = u32(dx / range);
          let r = dx - f32(n) * range;
          if (n % 2 == 0) {
            fx = x_max - r;
          } else {
            fx = x_min + r;
          }
        }
        return u32(fx);
      }`:""}
`,_u=(e,t,i)=>`
  fn pixel_at_grid(r: i32, c: i32, H: i32, W: i32, batch: u32, channel: u32, border: vec4<f32>) -> ${t} {
     var pixel = ${t}(0);
     var indices = vec4<u32>(0);
     indices[${Tt}] = batch;
     indices[${Ot}] = channel;`+(()=>{switch(i.paddingMode){case"zeros":return`
          if (r >= 0 && r < H && c >=0 && c < W) {
            indices[${Kt}] = u32(r);
            indices[${Qt}] = u32(c);
          } else {
            return ${t}(0);
          }
        `;case"border":return`
          indices[${Kt}] = u32(clamp(r, 0, H - 1));
          indices[${Qt}] = u32(clamp(c, 0, W - 1));
        `;case"reflection":return`
          indices[${Kt}] = gs_reflect(r, border[1], border[3]);
          indices[${Qt}] = gs_reflect(c, border[0], border[2]);
        `;default:throw new Error(`padding mode ${i.paddingMode} is not supported`)}})()+`
    return ${e.getByIndices("indices")};
  }
`,yu=(e,t,i)=>(()=>{switch(i.mode){case"nearest":return`
          let result = pixel_at_grid(i32(round(y)), i32(round(x)), H_in, W_in, indices[${Tt}], indices[${Ot}], border);
        `;case"bilinear":return`
          let x1 = i32(floor(x));
          let y1 = i32(floor(y));
          let x2 = x1 + 1;
          let y2 = y1 + 1;

          let p11 = pixel_at_grid(y1, x1, H_in, W_in, indices[${Tt}], indices[${Ot}], border);
          let p12 = pixel_at_grid(y1, x2, H_in, W_in, indices[${Tt}], indices[${Ot}], border);
          let p21 = pixel_at_grid(y2, x1, H_in, W_in, indices[${Tt}], indices[${Ot}], border);
          let p22 = pixel_at_grid(y2, x2, H_in, W_in, indices[${Tt}], indices[${Ot}], border);

          let dx2 = ${t}(f32(x2) - x);
          let dx1 = ${t}(x - f32(x1));
          let dy2 = ${t}(f32(y2) - y);
          let dy1 = ${t}(y - f32(y1));
          let result = dy2 * (dx2 * p11 + dx1 * p12) + dy1 * (dx2 * p21 + dx1 * p22);
        `;case"bicubic":return`
          let x0 = i32(floor(x)) - 1;
          let y0 = i32(floor(y)) - 1;
          var p: mat4x4<${t}>;
          for (var h = 0; h < 4; h++) {
            for (var w = 0; w < 4; w++) {
              p[h][w] = pixel_at_grid(h + y0, w + x0, H_in, W_in, indices[${Tt}], indices[${Ot}], border);
            }
          }

          let dx = x - f32(x0 + 1);
          let dy = y - f32(y0 + 1);
          let result = gs_bicubic_interpolate(p, dx, dy);
        `;default:throw new Error(`mode ${i.mode} is not supported`)}})()+`${e.setByOffset("global_idx","result")}`,wu=(e,t)=>{let i=F("x",e[0].dataType,e[0].dims.length),n=[e[1].dims[0],e[1].dims[1],e[1].dims[2]],r=F("grid",e[1].dataType,n.length,2),s=[e[0].dims[0],e[0].dims[1],e[1].dims[1],e[1].dims[2]];t.format==="NHWC"&&(s=[e[0].dims[0],e[1].dims[1],e[1].dims[2],e[0].dims[3]],[Tt,Ot,Kt,Qt]=[0,3,1,2]);let a=ae("output",e[0].dataType,s.length),o=i.type.value,l=M.size(s),u=[{type:12,data:l},...de(e[0].dims,n,s)],d=c=>`
  ${c.registerUniform("output_size","u32").declareVariables(i,r,a)}
  ${fu}
  ${hu(o)}
  ${mu(t)}
  ${gu(t)}
  ${_u(i,o,t)}

  ${c.mainStart()}
    ${c.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
      let H_in = i32(uniforms.x_shape[${Kt}]);
      let W_in = i32(uniforms.x_shape[${Qt}]);

      ${t.alignCorners===0?`
      let x_min = -0.5;
      let x_max = f32(W_in) - 0.5;
      let y_min = -0.5;
      let y_max = f32(H_in) - 0.5;
      `:`
      let x_min = 0.0;
      let x_max = f32(W_in) - 1.0;
      let y_min = 0.0;
      let y_max = f32(H_in) - 1.0;
      `};
      let border = vec4<f32>(x_min, y_min, x_max, y_max);

      let indices = ${a.offsetToIndices("global_idx")};
      var grid_indices = vec3<u32>(indices[${Tt}], indices[${Kt}], indices[${Qt}]);
      let nxy = ${r.getByIndices("grid_indices")};
      var x = gs_denormalize(f32(nxy[0]), W_in);
      var y = gs_denormalize(f32(nxy[1]), H_in);

      ${yu(a,o,t)}
  }`;return{name:"GridSample",shaderCache:{hint:`${t.cacheKey}`,inputDependencies:["type","type"]},getRunData:c=>{let p=M.size(s);return{outputs:[{dims:s,dataType:c[0].dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:u}},getShaderSource:d}},bu=(e,t)=>{pu(e.inputs),e.compute(wu(e.inputs,t))},vu=e=>Be({alignCorners:e.align_corners,mode:e.mode,paddingMode:e.padding_mode,format:e.format})}),ft,$u,xu,or,Su,yi,ku,Tu=C(()=>{me(),be(),Je(),Cn(),Nn(),$e(),Ft(),ft=(e,t)=>e.length>t&&e[t].dims.length>0?e[t]:void 0,$u=(e,t)=>{let i=e[0],n=ft(e,1),r=ft(e,2),s=ft(e,3),a=ft(e,4),o=ft(e,5),l=ft(e,6),u=ft(e,7);if(i.dims.length!==3&&i.dims.length!==5)throw new Error("Input query is expected to have 3 or 5 dimensions");let d=i.dims[0],c=i.dims[1],p=i.dims.length===3?i.dims[2]:t.numHeads*i.dims[4],h=c,m=0,_=0,$=Math.floor(p/t.numHeads);if(l&&u&&M.size(l.dims)&&M.size(u.dims)){if(l.dims.length!==4)throw new Error('Input "past_key" is expected to have 4 dimensions');if(l.dims[0]!==d||l.dims[1]!==t.numHeads||l.dims[3]!==$)throw new Error('Input "past_key" shape (batch_size, num_heads, past_sequence_length, head_size)');if(u.dims[0]!==d||u.dims[1]!==t.numHeads||u.dims[3]!==$)throw new Error('Input "past_value" shape (batch_size, num_heads, past_sequence_length, head_size)');if(l.dims[2]!==u.dims[2])throw new Error('Input "past_key" and "past_value" shall have same dim 2 (past_sequence_length)');if(u.dims.length!==4)throw new Error('Input "past_value" is expected to have 4 dimensions');m=l.dims[2],_=l.dims[2]}else if(l&&M.size(l.dims)||u&&M.size(u.dims))throw new Error('Input "past_key" and "past_value" shall be both present or both absent');let y;if(n&&M.size(n.dims)>0){if(i.dims.length!==3)throw new Error('Input "query" is expected to have 3 dimensions when key is given');if(n.dims.length<3||n.dims.length>5)throw new Error('Input "key" is expected to have 3, 4, or 5 dimensions');if(i.dims[0]!==n.dims[0])throw new Error('Input "query" and "key" shall have same dim 0 (batch size)');if(n.dims.length===3){if(n.dims[2]!==i.dims[2])throw new Error('Input "query" and "key" shall have same dim 2 (hidden_size)');y=2,h=n.dims[1]}else if(n.dims.length===5){if(n.dims[2]!==t.numHeads||n.dims[3]!==2||n.dims[4]!==$)throw new Error('Expect "key" shape (batch_size, kv_sequence_length, num_heads, 2, head_size) for packed kv');if(r)throw new Error('Expect "value" be none when "key" has packed kv format.');y=5,h=n.dims[1]}else{if(n.dims[1]!==t.numHeads||n.dims[3]!==$)throw new Error('Expect "key" shape (batch_size, num_heads, kv_sequence_length, head_size) for past_key');y=0,h=n.dims[2]}}else{if(i.dims.length!==5)throw new Error('Input "query" is expected to have 5 dimensions when key is empty');if(i.dims[2]!==t.numHeads||i.dims[3]!==3)throw new Error('Expect "query" shape (batch_size, kv_sequence_length, num_heads, 3, head_size) for packed kv');y=3}if(s&&M.size(s.dims)>0){if(s.dims.length!==1)throw new Error('Input "bias" is expected to have 1 dimension');if(n&&n.dims.length===5&&n.dims[3]===2)throw new Error("bias is not allowed for packed kv.")}let g=m+h,T=0;if(a&&M.size(a.dims)>0){T=8;let z=a.dims;throw z.length===1?z[0]===d?T=1:z[0]===3*d+2&&(T=3):z.length===2&&z[0]===d&&z[1]===g&&(T=5),T===8?new Error('Input "key_padding_mask" shape shall be (batch_size) or (batch_size, total_sequence_length)'):new Error("Mask not supported")}let x=!1,E=p;if(r&&M.size(r.dims)>0){if(r.dims.length!==3&&r.dims.length!==4)throw new Error('Input "value" is expected to have 3 or 4 dimensions');if(i.dims[0]!==r.dims[0])throw new Error('Input "query" and "value" shall have same dim 0 (batch_size)');if(r.dims.length===3){if(h!==r.dims[1])throw new Error('Input "key" and "value" shall have the same dim 1 (kv_sequence_length)');E=r.dims[2]}else{if(h!==r.dims[2])throw new Error('Input "key" and "value" shall have the same dim 2 (kv_sequence_length)');E=r.dims[1]*r.dims[3],x=!0}}let O=!1;if(a&&M.size(a.dims)>0)throw new Error("Key padding mask is not supported");if(o&&M.size(o.dims)>0){if(o.dims.length!==4)throw new Error('Input "attention_bias" is expected to have 4 dimensions');if(o.dims[0]!==d||o.dims[1]!==t.numHeads||o.dims[2]!==c||o.dims[3]!==g)throw new Error('Expect "attention_bias" shape (batch_size, num_heads, sequence_length, total_sequence_length)')}return{batchSize:d,sequenceLength:c,pastSequenceLength:m,kvSequenceLength:h,totalSequenceLength:g,maxSequenceLength:_,inputHiddenSize:0,hiddenSize:p,vHiddenSize:E,headSize:$,vHeadSize:Math.floor(E/t.numHeads),numHeads:t.numHeads,isUnidirectional:!1,pastPresentShareBuffer:!1,maskFilterValue:t.maskFilterValue,maskType:T,scale:t.scale,broadcastResPosBias:O,passPastInKv:x,qkvFormat:y}},xu=e=>Be({...e}),or=Be({perm:[0,2,1,3]}),Su=(e,t,i,n,r,s,a)=>{let o=[n,r,s],l=M.size(o),u=[{type:12,data:l},{type:12,data:a},{type:12,data:s}],d=c=>{let p=ae("qkv_with_bias",t.dataType,o),h=F("qkv",t.dataType,o),m=F("bias",i.dataType,o),_=[{name:"output_size",type:"u32"},{name:"bias_offset",type:"u32"},{name:"hidden_size",type:"u32"}];return`
  ${c.registerUniforms(_).declareVariables(h,m,p)}
  ${c.mainStart()}
    ${c.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    let bias_offset_idx = (global_idx % uniforms.hidden_size) + uniforms.bias_offset;

    qkv_with_bias[global_idx] = qkv[global_idx] + bias[bias_offset_idx];
  }`};return e.compute({name:"MultiHeadAttentionAddBias",shaderCache:{inputDependencies:["type","type"]},getRunData:()=>({outputs:[{dims:o,dataType:t.dataType,gpuDataType:0}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:u}),getShaderSource:d},{inputs:[t,i],outputs:[-1]})[0]},yi=(e,t,i,n,r,s,a,o)=>{let l=s;if(a&&M.size(a.dims)>0){if(n===1)throw new Error("AddBiasReshape is not implemented. Please export your model with packed QKV or KV");return l=Su(e,s,a,t,n,i*r,o),l=l.reshape([t,n,i,r]),i===1||n===1?l:e.compute(_t(l,or.perm),{inputs:[l],outputs:[-1]})[0]}else return s.dims.length===3&&(l=s.reshape([t,n,i,r])),i===1||n===1?l:e.compute(_t(l,or.perm),{inputs:[l],outputs:[-1]})[0]},ku=(e,t)=>{let i=$u(e.inputs,t),n=e.inputs[0],r=ft(e.inputs,1),s=ft(e.inputs,2),a=ft(e.inputs,3),o=ft(e.inputs,4),l=ft(e.inputs,5),u=ft(e.inputs,6),d=ft(e.inputs,7);if(n.dims.length===5)throw new Error("Packed QKV is not implemented");if(r?.dims.length===5)throw new Error("Packed KV is not implemented");let c=r&&s&&r.dims.length===4&&s.dims.length===4,p=yi(e,i.batchSize,i.numHeads,i.sequenceLength,i.headSize,n,a,0);if(c)return fi(e,p,r,s,o,void 0,u,d,l,i);if(!r||!s)throw new Error("key and value must be provided");let h=yi(e,i.batchSize,i.numHeads,i.kvSequenceLength,i.headSize,r,a,i.hiddenSize),m=yi(e,i.batchSize,i.numHeads,i.kvSequenceLength,i.vHeadSize,s,a,2*i.hiddenSize);fi(e,p,h,m,o,void 0,u,d,l,i)}}),Cu,Eu,Iu,Au,lr,zu,Ou,Ru=C(()=>{me(),be(),Je(),$e(),Cu=e=>{if(!e||e.length<1)throw new Error("too few inputs")},Eu=(e,t)=>{let i=[],n=t.numOutputs;return e[1].dims[0]>0&&(e[1].getBigInt64Array().forEach(r=>i.push(Number(r))),n=i.length),Be({numOutputs:n,axis:t.axis,splitSizes:i})},Iu=e=>`
fn calculateOutputIndex(index: u32) -> u32 {
    for (var i: u32 = 0u; i < ${e}u; i += 1u ) {
    if (index < ${oe("uniforms.size_in_split_axis","i",e)}) {
        return i;
    }
    }
    return ${e}u;
}`,Au=e=>{let t=e.length,i=[];for(let n=0;n<t;++n){let r=e[n].setByIndices("indices","input[global_idx]");t===1?i.push(r):n===0?i.push(`if (output_number == ${n}u) { ${r} }`):n===t-1?i.push(`else { ${r} }`):i.push(`else if (output_number == ${n}) { ${r} }`)}return`
      fn writeBufferData(output_number: u32, indices: ${e[0].type.indices}, global_idx: u32) {
        ${i.join(`
`)}
      }`},lr=(e,t)=>{let i=e[0].dims,n=M.size(i),r=e[0].dataType,s=M.normalizeAxis(t.axis,i.length),a=new Array(t.numOutputs),o=F("input",r,i.length),l=new Array(t.numOutputs),u=[],d=[],c=0,p=[{type:12,data:n}];for(let m=0;m<t.numOutputs;m++){c+=t.splitSizes[m],l[m]=c;let _=i.slice();_[s]=t.splitSizes[m],d.push(_),a[m]=ae(`output${m}`,r,_.length),u.push({dims:d[m],dataType:e[0].dataType})}p.push({type:12,data:l},...de(i,...d));let h=m=>`
  ${m.registerUniform("input_size","u32").registerUniform("size_in_split_axis","u32",l.length).declareVariables(o,...a)}
  ${Iu(l.length)}
  ${Au(a)}

  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.input_size")}

    var indices = ${o.offsetToIndices("global_idx")};
    var index = ${o.indicesGet("indices",s)};
    let output_number = calculateOutputIndex(index);
    if (output_number != 0) {
      index -= ${oe("uniforms.size_in_split_axis","output_number - 1u",l.length)};
      ${o.indicesSet("indices",s,"index")};
    }
    writeBufferData(output_number, indices, global_idx);
  }`;return{name:"Split",shaderCache:{hint:t.cacheKey,inputDependencies:["rank"]},getShaderSource:h,getRunData:()=>({outputs:u,dispatchGroup:{x:Math.ceil(n/64)},programUniforms:p})}},zu=(e,t)=>{Cu(e.inputs);let i=e.inputs.length===1?t:Eu(e.inputs,t);e.compute(lr(e.inputs,i),{inputs:[0]})},Ou=e=>{let t=e.axis,i=e.splitSizes,n=e.numOutputs<0?i.length:e.numOutputs;if(n!==i.length)throw new Error("numOutputs and splitSizes length must be equal");return Be({axis:t,numOutputs:n,splitSizes:i})}}),Mu,Wi,Du,Bu=C(()=>{me(),be(),Je(),$e(),Mu=(e,t)=>{let[i,n,r,s]=e,{numHeads:a,rotaryEmbeddingDim:o}=t;if(i.dims.length!==3&&i.dims.length!==4)throw new Error(`Input 'x' is expected to have 3 or 4 dimensions, got ${i.dims.length}`);if(!M.areEqual(n.dims,[])&&!M.areEqual(n.dims,[1])&&n.dims.length!==2)throw new Error(`Input 'position_ids' is expected to have 0, 1, or 2 dimensions, got ${n.dims.length}`);if(r.dims.length!==2)throw new Error(`Input 'cos_cache' is expected to have 2 dimensions, got ${r.dims.length}`);if(s.dims.length!==2)throw new Error(`Input 'sin_cache' is expected to have 2 dimensions, got ${s.dims.length}`);if(!M.areEqual(r.dims,s.dims))throw new Error("Inputs 'cos_cache' and 'sin_cache' are expected to have the same shape");if(o>0&&a===0)throw new Error("num_heads must be provided if rotary_embedding_dim is specified");let l=i.dims[0],u=i.dims[i.dims.length-2],d=r.dims[0],c=M.sizeFromDimension(i.dims,1)/u,p=o===0?r.dims[1]*2:c/a;if(o>p)throw new Error("rotary_embedding_dim must be less than or equal to head_size");if(n.dims.length===2){if(l!==n.dims[0])throw new Error(`Input 'position_ids' dimension 0 should be of size batch_size, got ${n.dims[0]}`);if(u!==n.dims[1])throw new Error(`Input 'position_ids' dimension 1 should be of size sequence_length, got ${n.dims[1]}`)}if(p/2!==r.dims[1]&&o/2!==r.dims[1])throw new Error(`Input 'cos_cache' dimension 1 should be same as head_size / 2 or rotary_embedding_dim / 2, got ${r.dims[1]}`);if(u>d)throw new Error("Updating cos_cache and sin_cache in RotaryEmbedding is not currently supported")},Wi=(e,t)=>{let{interleaved:i,numHeads:n,rotaryEmbeddingDim:r,scale:s}=t,a=e[0].dims[0],o=M.sizeFromDimension(e[0].dims,1),l=e[0].dims[e[0].dims.length-2],u=o/l,d=e[2].dims[1],c=r===0?d*2:u/n,p=new Array(a,l,u/c,c-d),h=M.computeStrides(p),m=[{type:1,data:s},{type:12,data:p},{type:12,data:h},...e[0].dims.length===3?new Array({type:12,data:[o,u,c,1]}):[],...e[0].dims.length===4?new Array({type:12,data:[o,c,l*c,1]}):[],...de(e[0].dims,e[1].dims,e[2].dims,e[3].dims,e[0].dims)],_=$=>{let y=F("input",e[0].dataType,e[0].dims.length),g=F("position_ids",e[1].dataType,e[1].dims.length),T=F("cos_cache",e[2].dataType,e[2].dims.length),x=F("sin_cache",e[3].dataType,e[3].dims.length),E=ae("output",e[0].dataType,e[0].dims.length);return $.registerUniforms([{name:"scale",type:"f32"},{name:"global_shape",type:"u32",length:p.length},{name:"global_strides",type:"u32",length:h.length},{name:"input_output_strides",type:"u32",length:h.length}]),`
        ${$.declareVariables(y,g,T,x,E)}

        ${$.mainStart(ni)}
          let half_rotary_emb_dim = uniforms.${T.name}_shape[1];
          let bsnh = global_idx / uniforms.global_strides % uniforms.global_shape;
          let size = uniforms.global_shape[0] * uniforms.global_strides[0];
          ${$.guardAgainstOutOfBoundsWorkgroupSizes("size")}

          if (bsnh[3] < half_rotary_emb_dim) {
            let position_ids_idx =
                ${g.broadcastedIndicesToOffset("bsnh.xy",ae("",g.type.tensor,2))};
            let position_id =
                u32(${g.getByOffset("position_ids_idx")}) + select(0, bsnh[1], position_ids_idx == 0);
            let i = dot(bsnh, uniforms.input_output_strides) + select(0, bsnh[3], ${i});
            let j = i + select(half_rotary_emb_dim, 1, ${i});
            let re = ${y.getByOffset("i")} * ${T.get("position_id","bsnh[3]")} -
                ${y.getByOffset("j")} * ${x.get("position_id","bsnh[3]")};
            ${E.setByOffset("i","re")}
            let im = ${y.getByOffset("i")} * ${x.get("position_id","bsnh[3]")} +
                ${y.getByOffset("j")} * ${T.get("position_id","bsnh[3]")};
            ${E.setByOffset("j","im")}
          } else {
            let k = dot(bsnh, uniforms.input_output_strides) + half_rotary_emb_dim;
            ${E.setByOffset("k",y.getByOffset("k"))}
          }
        }`};return{name:"RotaryEmbedding",shaderCache:{hint:Be({interleaved:i}).cacheKey,inputDependencies:["rank","rank","rank","rank"]},getShaderSource:_,getRunData:()=>({outputs:[{dims:e[0].dims,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(M.size(p)/ni)},programUniforms:m})}},Du=(e,t)=>{Mu(e.inputs,t),e.compute(Wi(e.inputs,t))}}),Fu,Nu,ur,Pu,Vu,Kp=C(()=>{Je(),me(),Nn(),Tu(),Ru(),Ft(),Bu(),$e(),Fu=(e,t)=>{if(t.doRotary&&e.length<=7)throw new Error("cos_cache and sin_cache inputs are required if do_rotary is specified");let i=e[0],n=e[1],r=e[2],s=e[3],a=e[4];if(t.doRotary!==0&&e.length<=7)throw new Error("cos_cast and sin_cache are expected if do_rotary attribute is non-zero");if(t.localWindowSize!==-1)throw new Error("Local attention is not supported");if(t.softcap!==0)throw new Error("Softcap is not supported");if(t.rotaryInterleaved!==0)throw new Error("Rotary interleaved is not supported");if(t.smoothSoftmax)throw new Error("Smooth softmax is not supported");if(i.dims.length!==3&&i.dims.length!==5)throw new Error("Input query is expected to have 3 or 5 dimensions");let o=!1,l=i.dims[0],u=i.dims[1],d=i.dims.length===3?o?i.dims[2]/3:i.dims[2]:t.numHeads*i.dims[4],c=u,p=0,h=!n||n.dims.length===0,m=Math.floor(h?d/(t.numHeads+2*t.kvNumHeads):d/t.numHeads);h&&(d=m*t.numHeads);let _=s&&s.dims.length!==0,$=a&&a.dims.length!==0;if(_&&s.dims.length===4&&s.dims[0]===l&&s.dims[1]!==t.kvNumHeads&&s.dims[2]===t.kvNumHeads&&s.dims[3]===m)throw new Error("BSNH pastKey/pastValue is not supported");if(_&&$){if(s.dims.length!==4)throw new Error('Input "past_key" is expected to have 4 dimensions');if(a.dims.length!==4)throw new Error('Input "past_value" is expected to have 4 dimensions');p=s.dims[2]}else if(_||$)throw new Error('Input "past_key" and "past_value" shall be both present or both absent');let y=1;if(n&&n.dims.length>0){if(i.dims.length!==3)throw new Error('Input "query" is expected to have 3 dimensions when key is given');if(n.dims.length<3||n.dims.length>5)throw new Error('Input "key" is expected to have 3, 4, or 5 dimensions');if(i.dims[0]!==n.dims[0])throw new Error('Input "query" and "key" shall have same dim 0 (batch size)');if(n.dims.length===3){if(i.dims[2]%n.dims[2]!==0)throw new Error('Dimension 2 of "query" should be a multiple of "key"');c=n.dims[1]}else if(n.dims.length===5){if(n.dims[2]!==t.numHeads||n.dims[3]!==2||n.dims[4]!==m)throw new Error('Expect "key" shape (batch_size, kv_sequence_length, num_heads, 2, head_size) for packed kv');if(r)throw new Error('Expect "value" be none when "key" has packed kv format.');c=n.dims[1]}else{if(n.dims[1]!==t.numHeads||n.dims[3]!==m)throw new Error('Expect "key" shape (batch_size, num_heads, kv_sequence_length, head_size) for past_key');c=n.dims[2]}}else{if(i.dims.length!==3&&i.dims.length!==5)throw new Error('Input "query" is expected to have 3 or 5 dimensions when key is empty');if(i.dims.length===5&&(i.dims[2]!==t.numHeads||i.dims[3]!==3))throw new Error('Expect "query" shape (batch_size, kv_sequence_length, num_heads, 3, head_size) for packed kv');y=3}let g=0,T=!1,x=t.kvNumHeads?m*t.kvNumHeads:d;if(r&&r.dims.length>0){if(r.dims.length!==3&&r.dims.length!==4)throw new Error('Input "value" is expected to have 3 or 4 dimensions');if(i.dims[0]!==r.dims[0])throw new Error('Input "query" and "value" shall have same dim 0 (batch_size)');if(r.dims.length===3){if(c!==r.dims[1])throw new Error('Input "key" and "value" shall have the same dim 1 (kv_sequence_length)');x=r.dims[2]}else{if(c!==r.dims[2])throw new Error('Input "past_key" and "past_value" shall have the same dim 2 (kv_sequence_length)');x=r.dims[1]*r.dims[3],T=!0}}let E=e.length>4?e[5]:void 0;if(E&&E.dims.length!==1&&E.dims[0]!==l)throw new Error('Input "seqlens" is expected to have 1 dimension and the same dim 0 as batch_size');return{batchSize:l,sequenceLength:u,pastSequenceLength:p,kvSequenceLength:c,totalSequenceLength:-1,maxSequenceLength:-1,inputHiddenSize:0,hiddenSize:d,vHiddenSize:x,headSize:m,vHeadSize:Math.floor(x/t.kvNumHeads),numHeads:t.numHeads,kvNumHeads:t.kvNumHeads,nReps:t.numHeads/t.kvNumHeads,pastPresentShareBuffer:!1,maskType:g,scale:t.scale,broadcastResPosBias:!1,passPastInKv:T,qkvFormat:y}},Nu=Be({perm:[0,2,1,3]}),ur=(e,t,i)=>{let n=t,r=i.kvNumHeads;return t.dims.length===3&&i.kvSequenceLength!==0&&(n=t.reshape([i.batchSize,i.kvSequenceLength,r,i.headSize]),n=e.compute(_t(n,Nu.perm),{inputs:[n],outputs:[-1]})[0]),n},Pu=(e,t,i,n)=>{let r=7,s=["type","type"],a=[e*t],o=e*t,l=[{type:12,data:o},{type:12,data:t},{type:12,data:e}],u=d=>{let c=F("seq_lens",i.dataType,i.dims),p=F("total_seq_lens",n.dataType,n.dims),h=ae("pos_ids",r,a),m=[{name:"output_size",type:"u32"},{name:"sequence_length",type:"u32"},{name:"batch_size",type:"u32"}];return`
  ${d.registerUniforms(m).declareVariables(c,p,h)}
  ${d.mainStart()}
    ${d.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    let total_sequence_length = u32(${p.getByOffset("0")});
    let is_subsequent_prompt = uniforms.sequence_length > 1 && uniforms.sequence_length != total_sequence_length;
    let is_first_prompt = !is_subsequent_prompt && uniforms.sequence_length == total_sequence_length;
    let batch_idx = global_idx / uniforms.sequence_length;
    let sequence_idx = i32(global_idx % uniforms.sequence_length);
    var pos_id: i32 = 0;
    let seqlen = ${c.getByOffset("batch_idx")};
    let total_seqlen = seqlen + 1;
    if (is_first_prompt) {
      if (sequence_idx < total_seqlen) {
        pos_id = sequence_idx;
      } else {
        pos_id = 1;
      }
      ${h.setByOffset("global_idx","pos_id")}
    } else if (is_subsequent_prompt) {
      let past_seqlen = total_seqlen - i32(uniforms.sequence_length);
      if (past_seqlen + sequence_idx < total_seqlen) {
        pos_id = past_seqlen + sequence_idx;
      } else {
        pos_id = 1;
      }
      ${h.setByOffset("global_idx","pos_id")}
    } else if (global_idx < uniforms.batch_size) {
      ${h.setByOffset("global_idx","seqlen")}
    };
  }
  `};return{name:"GeneratePositionIds",shaderCache:{hint:`${e};${t}`,inputDependencies:s},getRunData:()=>({outputs:[{dims:a,dataType:r}],dispatchGroup:{x:Math.ceil(o/64)},programUniforms:l}),getShaderSource:u}},Vu=(e,t)=>{let i=Fu(e.inputs,t);if(e.inputs[0].dims.length===5)throw new Error("Packed QKV is not implemented");if(e.inputs[1]?.dims.length===5)throw new Error("Packed KV is not implemented");let n=e.inputs[0],r=e.inputs[1]&&e.inputs[1].dims.length>0?e.inputs[1]:void 0,s=e.inputs[2]&&e.inputs[2].dims.length>0?e.inputs[2]:void 0,a=e.inputs[3]&&e.inputs[3].dims.length!==0?e.inputs[3]:void 0,o=e.inputs[4]&&e.inputs[4].dims.length!==0?e.inputs[4]:void 0,l=e.inputs.length>4?e.inputs[5]:void 0,u=e.inputs.length>5?e.inputs[6]:void 0,d=i.kvNumHeads?i.kvNumHeads:i.numHeads,c=Be({axis:2,numOutputs:3,splitSizes:[i.numHeads*i.headSize,d*i.headSize,d*i.headSize]}),[p,h,m]=!r&&!s?e.compute(lr([n],c),{inputs:[n],outputs:[-1,-1,-1]}):[n,r,s],_,$;if(t.doRotary){let x=e.compute(Pu(i.batchSize,i.sequenceLength,l,u),{inputs:[l,u],outputs:[-1]})[0],E=e.inputs[7],O=e.inputs[8],z=Be({interleaved:t.rotaryInterleaved!==0,numHeads:i.numHeads,rotaryEmbeddingDim:0,scale:t.scale}),N=[p,x,E,O],L=[-1];_=e.compute(Wi(N,z),{inputs:N,outputs:L})[0],N.splice(0,1,h);let ie=Be({interleaved:t.rotaryInterleaved!==0,numHeads:i.kvNumHeads,rotaryEmbeddingDim:0,scale:t.scale});$=e.compute(Wi(N,ie),{inputs:N,outputs:L})[0]}let y=yi(e,i.batchSize,i.numHeads,i.sequenceLength,i.headSize,t.doRotary?_:p,void 0,0),g=ur(e,t.doRotary?$:h,i),T=ur(e,m,i);fi(e,y,g,T,void 0,void 0,a,o,void 0,i,l,u)}}),dr,Lu,Uu,qu,Qp=C(()=>{me(),be(),Ft(),$e(),dr=(e,t,i,n,r,s,a,o)=>{let l=Xe(s),u=l===1?"f32":`vec${l}f`,d=l===1?"vec2f":`mat2x${l}f`,c=r*a,p=64;c===1&&(p=256);let h=[r,a,s/l],m=[r,a,2],_=["rank","type","type"],$=[];$.push(...de(h,m));let y=g=>{let T=F("x",t.dataType,3,l),x=F("scale",i.dataType,i.dims),E=F("bias",n.dataType,n.dims),O=ae("output",1,3,2),z=[T,x,E,O];return`
  var<workgroup> workgroup_shared : array<${d}, ${p}>;
  const workgroup_size = ${p}u;
  ${g.declareVariables(...z)}
  ${g.mainStart(p)}
    let batch = workgroup_index / uniforms.x_shape[1];
    let channel = workgroup_index % uniforms.x_shape[1];
    let hight = uniforms.x_shape[2];
    // initialize workgroup memory
    var sum = ${u}(0);
    var squared_sum = ${u}(0);
    for (var h = local_idx; h < hight; h += workgroup_size) {
      let value = ${u}(${T.get("batch","channel","h")});
      sum += value;
      squared_sum += value * value;
    }
    workgroup_shared[local_idx] = ${d}(sum, squared_sum);
    workgroupBarrier();

    for (var currSize = workgroup_size >> 1;  currSize > 0; currSize = currSize >> 1) {
      if (local_idx < currSize) {
        workgroup_shared[local_idx] = workgroup_shared[local_idx] + workgroup_shared[local_idx + currSize];
      }
      workgroupBarrier();
    }
    if (local_idx == 0) {
      let sum_final = ${Bt("workgroup_shared[0][0]",l)} / f32(hight * ${l});
      let squared_sum_final = ${Bt("workgroup_shared[0][1]",l)} / f32(hight * ${l});

      let inv_std_dev = inverseSqrt(squared_sum_final - sum_final * sum_final + f32(${o}));
      let channel_scale = inv_std_dev * f32(scale[channel]);
      let channel_shift = f32(bias[channel]) - sum_final * channel_scale;
      output[workgroup_index] = vec2f(channel_scale, channel_shift);
    }
  }`};return e.compute({name:"InstanceNormComputeChannelScaleShift",shaderCache:{hint:`${l};${o};${p}`,inputDependencies:_},getRunData:()=>({outputs:[{dims:m,dataType:1}],dispatchGroup:{x:c},programUniforms:$}),getShaderSource:y},{inputs:[t,i,n],outputs:[-1]})[0]},Lu=(e,t,i)=>{let n=t[0].dims,r=n,s=2,a=n[0],o=n[1],l=M.sizeFromDimension(n,s),u=Xe(l),d=M.size(r)/u,c=dr(e,t[0],t[1],t[2],a,l,o,i.epsilon),p=[a,o,l/u],h=[a,o],m=["type","none"],_=$=>{let y=F("x",t[0].dataType,p.length,u),g=F("scale_shift",1,h.length,2),T=ae("output",t[0].dataType,p.length,u),x=[y,g,T];return`
  ${$.registerUniform("output_size","u32").declareVariables(...x)}
  ${$.mainStart()}
  ${$.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
      let outputIndices = ${T.offsetToIndices("global_idx")};
      let batch = outputIndices[0];
      let channel = outputIndices[1];
      let scale_shift = ${g.getByIndices("vec2<u32>(batch, channel)")};
      let value = ${y.getByOffset("global_idx")} * ${T.type.value}(scale_shift.x) + ${T.type.value}(scale_shift.y);
      ${T.setByOffset("global_idx","value")};
  }`};e.compute({name:"InstanceNormalization",shaderCache:{hint:`${u}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:r,dataType:t[0].dataType}],dispatchGroup:{x:Math.ceil(d/64)},programUniforms:[{type:12,data:d},...de(p,h,p)]}),getShaderSource:_},{inputs:[t[0],c]})},Uu=(e,t,i)=>{let n=t[0].dims,r=n,s=n[0],a=n[n.length-1],o=M.sizeFromDimension(n,1)/a,l=Xe(a),u=M.size(r)/l,d=[{type:12,data:o},{type:12,data:Math.floor(a/l)}],c=["type","type"],p=!1,h=[0,n.length-1];for(let y=0;y<n.length-2;y++)p=p||n[y+1]!==1,h.push(y+1);p=p&&n[n.length-1]!==1;let m=p?e.compute(_t(e.inputs[0],h),{inputs:[e.inputs[0]],outputs:[-1]})[0]:e.inputs[0].reshape(Array.from({length:n.length},(y,g)=>n[h[g]])),_=dr(e,m,t[1],t[2],s,o,a,i.epsilon),$=y=>{let g=at(t[0].dataType),T=l===1?"vec2f":`mat${l}x2f`,x=z=>{let N=z===0?"x":"y",L=l===1?"f32":`vec${l}f`;switch(l){case 1:return`${g}(${L}(scale.${N}))`;case 2:return`vec2<${g}>(${L}(scale[0].${N}, scale[1].${N}))`;case 4:return`vec4<${g}>(${L}(scale[0].${N}, scale[1].${N}, scale[2].${N}, scale[3].${N}))`;default:throw new Error(`Not supported compoents ${l}`)}},E=F("input",t[0].dataType,t[0].dims,l),O=ae("output",t[0].dataType,r,l);return`
  @group(0) @binding(0) var<storage, read> input : array<${E.type.storage}>;
  @group(0) @binding(1) var<storage, read> scale_input : array<${T}>;
  @group(0) @binding(2) var<storage, read_write> output : array<${O.type.storage}>;
  struct Uniforms {H: u32, C : u32};
  @group(0) @binding(3) var<uniform> uniforms: Uniforms;

  ${y.mainStart()}
    let current_image_number = global_idx / (uniforms.C * uniforms.H);
    let current_channel_number = global_idx % uniforms.C;

    let scale_offset = current_image_number * uniforms.C + current_channel_number;
    let scale = scale_input[scale_offset];
    output[global_idx] = fma(input[global_idx], ${x(0)}, ${x(1)});
  }`};e.compute({name:"InstanceNormalizationNHWC",shaderCache:{hint:`${l}`,inputDependencies:c},getRunData:()=>({outputs:[{dims:r,dataType:t[0].dataType}],dispatchGroup:{x:Math.ceil(u/64)},programUniforms:d}),getShaderSource:$},{inputs:[t[0],_]})},qu=(e,t)=>{t.format==="NHWC"?Uu(e,e.inputs,t):Lu(e,e.inputs,t)}}),Wu,Gu,ju,Zp=C(()=>{me(),be(),$e(),Wu=e=>{if(!e||e.length<2)throw new Error("layerNorm requires at least 2 inputs.")},Gu=(e,t,i)=>{let n=t.simplified,r=e[0].dims,s=e[1],a=!n&&e[2],o=r,l=M.normalizeAxis(t.axis,r.length),u=M.sizeToDimension(r,l),d=M.sizeFromDimension(r,l),c=M.size(s.dims),p=a?M.size(a.dims):0;if(c!==d||a&&p!==d)throw new Error(`Size of X.shape()[axis:] == ${d}.
       Size of scale and bias (if provided) must match this.
       Got scale size of ${c} and bias size of ${p}`);let h=[];for(let E=0;E<r.length;++E)E<l?h.push(r[E]):h.push(1);let m=Xe(d),_=["type","type"],$=[{type:12,data:u},{type:1,data:d},{type:12,data:Math.floor(d/m)},{type:1,data:t.epsilon}];a&&_.push("type");let y=i>1,g=i>2,T=E=>{let O=at(e[0].dataType),z=[F("x",e[0].dataType,e[0].dims,m),F("scale",s.dataType,s.dims,m)];a&&z.push(F("bias",a.dataType,a.dims,m)),z.push(ae("output",e[0].dataType,o,m)),y&&z.push(ae("mean_data_output",1,h)),g&&z.push(ae("inv_std_output",1,h));let N=[{name:"norm_count",type:"u32"},{name:"norm_size",type:"f32"},{name:"norm_size_vectorized",type:"u32"},{name:"epsilon",type:"f32"}];return`
  ${E.registerUniforms(N).declareVariables(...z)}
  ${E.mainStart()}
    ${E.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.norm_count")}
    let offset = global_idx * uniforms.norm_size_vectorized;
    var mean_vector = ${zn("f32",m)};
    var mean_square_vector = ${zn("f32",m)};

    for (var h: u32 = 0u; h < uniforms.norm_size_vectorized; h++) {
      let value = ${ri(O,m,"x[h + offset]")};
      mean_vector += value;
      mean_square_vector += value * value;
    }
    let mean = ${Bt("mean_vector",m)} / uniforms.norm_size;
    let inv_std_dev = inverseSqrt(${Bt("mean_square_vector",m)} / uniforms.norm_size ${n?"":"- mean * mean"} + uniforms.epsilon);

    for (var j: u32 = 0; j < uniforms.norm_size_vectorized; j++) {
      let f32input = ${ri(O,m,"x[j + offset]")};
      let f32scale = ${ri(O,m,"scale[j]")};
      output[j + offset] = ${z[0].type.value}((f32input ${n?"":"- mean"}) * inv_std_dev * f32scale
        ${a?`+ ${ri(O,m,"bias[j]")}`:""}
      );
    }

    ${y?"mean_data_output[global_idx] = mean":""};
    ${g?"inv_std_output[global_idx] = inv_std_dev":""};
  }`},x=[{dims:o,dataType:e[0].dataType}];return y&&x.push({dims:h,dataType:1}),g&&x.push({dims:h,dataType:1}),{name:"LayerNormalization",shaderCache:{hint:`${m};${i};${n}`,inputDependencies:_},getRunData:()=>({outputs:x,dispatchGroup:{x:Math.ceil(u/64)},programUniforms:$}),getShaderSource:T}},ju=(e,t)=>{Wu(e.inputs),e.compute(Gu(e.inputs,t,e.outputCount))}}),Hu,Ku,Xp=C(()=>{be(),jn(),Zn(),Hu=e=>{if(!e||e.length!==2)throw new Error("MatMul requires 2 inputs.");if(e[0].dims[e[0].dims.length-1]!==e[1].dims[e[1].dims.length-2])throw new Error("shared dimension does not match.")},Ku=e=>{Hu(e.inputs);let t=ii.calcShape(e.inputs[0].dims,e.inputs[1].dims,!0);if(!t)throw new Error("Can't use matmul on the given tensors");let i=t[t.length-1],n=e.inputs[0].dims[e.inputs[0].dims.length-1];if(i<8&&n<8)e.compute(Gn(e.inputs,{activation:""},t));else{let r=t[t.length-2],s=M.size(e.inputs[0].dims.slice(0,-2)),a=M.size(e.inputs[1].dims.slice(0,-2));if(s!==1&&r===1&&a===1){let o=e.inputs[0].reshape([1,s,n]),l=e.inputs[1].reshape([1,n,i]),u=[1,s,i],d=[o,l];e.compute(Vi(d,{activation:""},t,u),{inputs:d})}else e.compute(Vi(e.inputs,{activation:""},t))}}}),Qu,Zu,Xu,Yu,Ju,Yp=C(()=>{me(),be(),Je(),$e(),Qu=(e,t)=>{if(e.length<3||e.length>4)throw new Error("MatMulNBits requires 3 or 4 inputs");let i=e[0],n=i.dims.length;if(i.dims[n-1]!==t.k)throw new Error("The last dim of input shape does not match the k value");let r=Math.floor((t.k+t.blockSize-1)/t.blockSize),s=t.blockSize/8*t.bits,a=e[1];if(!M.areEqual(a.dims,[t.n,r,s]))throw new Error("The second inputs must be 3D tensor with shape N X nBlocksPerCol X blobSize");let o=e[2].dims;if(M.size(o)!==t.n*r)throw new Error("scales input size error.");if(e.length===4){let l=e[3].dims,u=t.n*(t.bits===8?r:Math.floor((r*t.bits+7)/8));if(M.size(l)!==u)throw new Error("zeroPoints input size error.")}},Zu=(e,t)=>{let i=e[0].dims,n=i.length,r=i[n-2],s=t.k,a=t.n,o=i.slice(0,n-2),l=M.size(o),u=e[1].dims[2]/4,d=e[0].dataType,c=Xe(t.k),p=Xe(u),h=Xe(a),m=o.concat([r,a]),_=r>1&&a/h%2===0?2:1,$=M.size(m)/h/_,y=64,g=[],T=[l,r,s/c],x=M.convertShape(e[1].dims).slice();x.splice(-1,1,u/p),g.push(...de(T)),g.push(...de(x)),g.push(...de(e[2].dims)),e.length===4&&g.push(...de(M.convertShape(e[3].dims)));let E=[l,r,a/h];g.push(...de(E));let O=z=>{let N=T.length,L=F("a",e[0].dataType,N,c),ie=F("b",12,x.length,p),ge=F("scales",e[2].dataType,e[2].dims.length),ce=[L,ie,ge],we=e.length===4?F("zero_points",12,e[3].dims.length):void 0;we&&ce.push(we);let re=E.length,ke=ae("output",e[0].dataType,re,h),he=at(e[0].dataType),le=(()=>{switch(c){case 1:return`array<${he}, 8>`;case 2:return`mat4x2<${he}>`;case 4:return`mat2x4<${he}>`;default:throw new Error(`${c}-component is not supported.`)}})(),Re=()=>{let U=`
          // reuse a data
            var input_offset = ${L.indicesToOffset(`${L.type.indices}(batch, row, word_offset)`)};
            var a_data: ${le};
            for (var j: u32 = 0; j < ${8/c}; j++) {
              a_data[j] = ${L.getByOffset("input_offset")};
              input_offset++;
            }
          `;for(let te=0;te<h*_;te++)U+=`
            b_value = ${p===1?`b${te}_data`:`b${te}_data[i]`};
            b_value_lower = unpack4xU8(b_value & b_mask);
            b_value_upper = unpack4xU8((b_value >> 4) & b_mask);
            b_quantized_values = ${le}(${Array.from({length:4},(xe,Le)=>`${he}(b_value_lower[${Le}]), ${he}(b_value_upper[${Le}])`).join(", ")});
            b_dequantized_values = ${c===1?`${le}(${Array.from({length:8},(xe,Le)=>`(b_quantized_values[${Le}] - ${we?`zero_point${te}`:"zero_point"}) * scale${te}`).join(", ")});`:`(b_quantized_values - ${le}(${Array(8).fill(`${we?`zero_point${te}`:"zero_point"}`).join(",")})) * scale${te};`};
            workgroup_shared[local_id.x * ${_} + ${Math.floor(te/h)}]${h>1?`[${te%h}]`:""} += ${Array.from({length:8/c},(xe,Le)=>`${c===1?`a_data[${Le}] * b_dequantized_values[${Le}]`:`dot(a_data[${Le}], b_dequantized_values[${Le}])`}`).join(" + ")};
          `;return U},pe=()=>{let U=`
            var col_index = col * ${h};
            ${we?`
            let zero_point_bytes_per_col = (nBlocksPerCol + 1) / 2;
            var zero_point_byte_count: u32;
            var zero_point_word_index: u32;
            var zero_point_byte_offset: u32;
            let zero_point_nibble_offset: u32 = block & 0x1u;
            var zero_point_bits_offset: u32;
            var zero_point_word: u32;`:`
            // The default zero point is 8 for unsigned 4-bit quantization.
            let zero_point = ${he}(8);`}
            `;for(let te=0;te<h*_;te++)U+=`
            let scale${te} = ${ge.getByOffset("col_index * nBlocksPerCol + block")};
            ${we?`
            zero_point_byte_count = col_index * zero_point_bytes_per_col + (block >> 0x1u);
            zero_point_word_index = zero_point_byte_count >> 0x2u;
            zero_point_byte_offset = zero_point_byte_count & 0x3u;
            zero_point_bits_offset = (zero_point_byte_offset << 3) + (zero_point_nibble_offset << 2);
            zero_point_word = ${we.getByOffset("zero_point_word_index")} >> zero_point_bits_offset;
            let zero_point${te} = ${he}((zero_point_word) & 0xFu);`:""}
            col_index += 1;`;return U},He=()=>{let U=`col_index = col * ${h};`;for(let te=0;te<h*_;te++)U+=`
            let b${te}_data = ${ie.getByIndices(`${ie.type.indices}(col_index, block, word)`)};
            col_index += 1;`;return U+=`
            var b_value: u32;
            let b_mask: u32 = 0x0F0F0F0Fu;
            var b_value_lower: vec4<u32>;
            var b_value_upper: vec4<u32>;
            var b_quantized_values: ${le};
            var b_dequantized_values: ${le};`,U};return`
        var<workgroup> workgroup_shared: array<${ke.type.value}, ${_*y}>;
        ${z.declareVariables(...ce,ke)}
        ${z.mainStart([y,1,1])}
          let output_indices = ${ke.offsetToIndices(`(global_idx / ${y}) * ${_}`)};
          let col = output_indices[2];
          let row = output_indices[1];
          let batch = output_indices[0];
          let nBlocksPerCol = uniforms.b_shape[1];

          for (var block = local_id.x; block < nBlocksPerCol; block += ${y}) {
            //process one block
            var word_offset: u32 = block * ${t.blockSize/c};
            ${pe()}
            for (var word: u32 = 0; word < ${u}; word += ${p}) {
              ${He()}
              for (var i: u32 = 0; i < ${p}; i++) {
                ${Re()}
                word_offset += ${8/c};
              }
            }
          }
          workgroupBarrier();

          if (local_id.x < ${_}) {
            var output_value: ${ke.type.value} = ${ke.type.value}(0);
            var workgroup_shared_offset: u32 = local_id.x;
            for (var b: u32 = 0u; b < ${y}u; b++) {
              output_value += workgroup_shared[workgroup_shared_offset];
              workgroup_shared_offset += ${_};
            }
            ${ke.setByIndices(`${ke.type.indices}(batch, row, col + local_id.x)`,"output_value")};
          }
        }`};return{name:"MatMulNBits",shaderCache:{hint:`${t.blockSize};${t.bits};${c};${p};${h};${_};${y}`,inputDependencies:Array(e.length).fill("rank")},getRunData:()=>({outputs:[{dims:m,dataType:d}],dispatchGroup:{x:$},programUniforms:g}),getShaderSource:O}},Xu=(e,t)=>{let i=e[0].dims,n=i.length,r=i[n-2],s=t.k,a=t.n,o=i.slice(0,n-2),l=M.size(o),u=e[1].dims[2]/4,d=e[0].dataType,c=Xe(t.k),p=Xe(u),h=o.concat([r,a]),m=128,_=a%8===0?8:a%4===0?4:1,$=m/_,y=$*p*8,g=y/c,T=y/t.blockSize,x=M.size(h)/_,E=[],O=[l,r,s/c],z=M.convertShape(e[1].dims).slice();z.splice(-1,1,u/p),E.push(...de(O)),E.push(...de(z)),E.push(...de(e[2].dims)),e.length===4&&E.push(...de(M.convertShape(e[3].dims)));let N=[l,r,a];E.push(...de(N));let L=ie=>{let ge=O.length,ce=F("a",e[0].dataType,ge,c),we=F("b",12,z.length,p),re=F("scales",e[2].dataType,e[2].dims.length),ke=[ce,we,re],he=e.length===4?F("zero_points",12,e[3].dims.length):void 0;he&&ke.push(he);let le=N.length,Re=ae("output",e[0].dataType,le),pe=at(e[0].dataType),He=()=>{switch(c){case 1:return`
          let a_data0 = vec4<${pe}>(sub_a[word_offset], sub_a[word_offset + 1], sub_a[word_offset + 2], sub_a[word_offset + 3]);
          let a_data1 = vec4<${pe}>(sub_a[word_offset + 4], sub_a[word_offset + 5], sub_a[word_offset + 6], sub_a[word_offset + 7]);`;case 2:return`
          let a_data0 = vec4<${pe}>(sub_a[word_offset], sub_a[word_offset + 1]);
          let a_data1 = vec4<${pe}>(sub_a[word_offset + 2], sub_a[word_offset + 3]);`;case 4:return`
          let a_data0 = sub_a[word_offset];
          let a_data1 = sub_a[word_offset + 1];`;default:throw new Error(`${c}-component is not supported.`)}};return`
        var<workgroup> sub_a: array<${ce.type.value}, ${g}>;
        var<workgroup> inter_results: array<array<${Re.type.value}, ${$}>, ${_}>;
        ${ie.declareVariables(...ke,Re)}
        ${ie.mainStart([$,_,1])}
          let output_indices = ${Re.offsetToIndices(`workgroup_index * ${_}`)};
          let col = output_indices[2];
          let row = output_indices[1];
          let batch = output_indices[0];
          let n_blocks_per_col = uniforms.b_shape[1];
          let num_tiles =  (n_blocks_per_col - 1) / ${T} + 1;

          // Loop over shared dimension.
          for (var tile: u32 = 0; tile < num_tiles; tile += 1) {
            let a_col_start = tile * ${g};
            // load one tile A data into shared memory.
            for (var a_offset = local_idx; a_offset < ${g}; a_offset += ${m})
            {
              let a_col = a_col_start + a_offset;
              if (a_col < uniforms.a_shape[2])
              {
                sub_a[a_offset] = ${ce.getByIndices(`${ce.type.indices}(batch, row, a_col)`)};
              } else {
                sub_a[a_offset] = ${ce.type.value}(0);
              }
            }
            workgroupBarrier();

            // each thread process one block
            let b_row = col + local_id.y;
            let block = tile * ${T} + local_id.x;
            ${he?`
            let zero_point_bytes_per_col = (n_blocks_per_col + 1) / 2;
            let zero_point_byte_count = b_row * zero_point_bytes_per_col + (block >> 0x1u);
            let zero_point_word_index = zero_point_byte_count >> 0x2u;
            let zero_point_byte_offset = zero_point_byte_count & 0x3u;
            let zero_point_nibble_offset: u32 = block & 0x1u;
            let zero_point_bits_offset = (zero_point_byte_offset << 3) + (zero_point_nibble_offset << 2);
            let zero_point_word = ${he.getByOffset("zero_point_word_index")} >> zero_point_bits_offset;
            let zero_point = ${pe}((zero_point_word) & 0xFu);`:`
            // The default zero point is 8 for unsigned 4-bit quantization.
            let zero_point = ${pe}(8);`}
            let scale = ${re.getByOffset("b_row * n_blocks_per_col + block")};
            let b_data = ${we.getByIndices(`${we.type.indices}(b_row, block, 0)`)};
            var word_offset = local_id.x * ${t.blockSize/c};
            for (var i: u32 = 0; i < ${p}; i++) {
              ${He()}
              let b_value = ${p===1?"b_data":"b_data[i]"};
              let b_value_lower = unpack4xU8(b_value & 0x0F0F0F0Fu);
              let b_value_upper = unpack4xU8((b_value >> 4) & 0x0F0F0F0Fu);
              let b_quantized_values = mat2x4<${pe}>(${Array.from({length:4},(U,te)=>`${pe}(b_value_lower[${te}]), ${pe}(b_value_upper[${te}])`).join(", ")});
              let b_dequantized_values = (b_quantized_values - mat2x4<${pe}>(${Array(8).fill("zero_point").join(",")})) * scale;
              inter_results[local_id.y][local_id.x] += ${Array.from({length:2},(U,te)=>`${`dot(a_data${te}, b_dequantized_values[${te}])`}`).join(" + ")};
              word_offset += ${8/c};
            }
            workgroupBarrier();
          }

          if (local_idx < ${_}) {
            var output_value: ${Re.type.value} = ${Re.type.value}(0);
            for (var b = 0u; b < ${$}; b++) {
              output_value += inter_results[local_idx][b];
            }
            if (col + local_idx < uniforms.output_shape[2])
            {
              ${Re.setByIndices(`${Re.type.indices}(batch, row, col + local_idx)`,"output_value")}
            }
          }
        }`};return{name:"BlockwiseMatMulNBits32",shaderCache:{hint:`${t.blockSize};${c};${p};${$};${_}`,inputDependencies:Array(e.length).fill("rank")},getRunData:()=>({outputs:[{dims:h,dataType:d}],dispatchGroup:{x},programUniforms:E}),getShaderSource:L}},Yu=(e,t)=>{Qu(e.inputs,t),t.blockSize===32&&e.adapterInfo.isVendor("intel")&&e.adapterInfo.isArchitecture("gen-12lp")?e.compute(Xu(e.inputs,t)):e.compute(Zu(e.inputs,t))},Ju=e=>Be(e)}),ed,td,id,nd,rd,sd,ad,od,ld,Jp=C(()=>{me(),be(),$e(),ed=e=>{if(!e||e.length<1)throw new Error("Too few inputs");if(e[0].dataType!==1&&e[0].dataType!==10)throw new Error("Input type must be float or float16.");if(e.length>=2){let t=e[0].dims.length*2===e[1].dims[0];if(e.length===4&&(t=e[3].dims[0]*2===e[1].dims[0]),!t)throw new Error("The pads should be a 1D tensor of shape [2 * input_rank] or [2 * num_axes].")}},td=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
            k = i32(${e.indicesGet("indices",r)}) - ${oe("uniforms.pads",r,i)};
            if (k < 0) {
              break;
            }
            if (k >= i32(${oe("uniforms.x_shape",r,t)})) {
              break;
            }
            offset += k * i32(${oe("uniforms.x_strides",r,t)});
        `;return`
          value = ${e.type.value}(uniforms.constant_value);
          for (var i = 0; i < 1; i++) {
            var offset = 0;
            var k = 0;
            ${n}
            value = x[offset];
          }
      `},id=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
                k = i32(${e.indicesGet("indices",r)}) - ${oe("uniforms.pads",r,i)};
                if (k < 0) {
                  k = -k;
                }
                {
                  let _2n_1 = 2 * (i32(${oe("uniforms.x_shape",r,t)}) - 1);
                  k = k % _2n_1;
                  if(k >= i32(${oe("uniforms.x_shape",r,t)})) {
                    k = _2n_1 - k;
                  }
                }
                offset += k * i32(${oe("uniforms.x_strides",r,t)});
            `;return`
              var offset = 0;
              var k = 0;
              ${n}
              value = x[offset];
          `},nd=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
                k = i32(${e.indicesGet("indices",r)}) - ${oe("uniforms.pads",r,i)};
                if (k < 0) {
                  k = 0;
                }
                if (k >= i32(${oe("uniforms.x_shape",r,t)})) {
                  k = i32(${oe("uniforms.x_shape",r,t)}) - 1;
                }
                offset += k * i32(${oe("uniforms.x_strides",r,t)});
            `;return`
              var offset = 0;
              var k = 0;
              ${n}
              value = x[offset];
          `},rd=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
                k = i32(${e.indicesGet("indices",r)}) - ${oe("uniforms.pads",r,i)};
                if (k < 0)  {
                  k += i32(${oe("uniforms.x_shape",r,t)}]);
                }
                if (k >= i32(${oe("uniforms.x_shape",r,t)})) {
                  k -= i32(${oe("uniforms.x_shape",r,t)});
                }
                offset += k * i32(${oe("uniforms.x_strides",r,t)});
            `;return`
              var offset = 0;
              var k = 0;
              ${n}
              value = x[offset];
          `},sd=(e,t,i)=>{switch(i.mode){case 0:return td(e,t,i.pads.length);case 1:return id(e,t,i.pads.length);case 2:return nd(e,t,i.pads.length);case 3:return rd(e,t,i.pads.length);default:throw new Error("Invalid mode")}},ad=(e,t)=>{let i=M.padShape(e[0].dims.slice(),t.pads),n=e[0].dims,r=M.size(i),s=[{type:12,data:r},{type:6,data:t.pads}],a=e.length>=3&&e[2].data;t.mode===0&&s.push({type:a?e[2].dataType:1,data:t.value}),s.push(...de(e[0].dims,i));let o=["rank"],l=u=>{let d=ae("output",e[0].dataType,i.length),c=F("x",e[0].dataType,n.length),p=c.type.value,h=sd(d,n.length,t),m=[{name:"output_size",type:"u32"},{name:"pads",type:"i32",length:t.pads.length}];return t.mode===0&&m.push({name:"constant_value",type:a?p:"f32"}),`
            ${u.registerUniforms(m).declareVariables(c,d)}
            ${u.mainStart()}
            ${u.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

            let indices = ${d.offsetToIndices("global_idx")};

            var value = ${p}(0);
            ${h}
            output[global_idx] = value;
        }`};return{name:"Pad",shaderCache:{hint:`${t.mode}${a}`,inputDependencies:o},getRunData:()=>({outputs:[{dims:i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(M.size(i)/64)},programUniforms:s}),getShaderSource:l}},od=(e,t)=>{if(e.length>1){let i=e[1].getBigInt64Array(),n=e.length>=3&&e[2].data?e[2].dataType===10?e[2].getUint16Array()[0]:e[2].getFloat32Array()[0]:0,r=e[0].dims.length,s=new Int32Array(2*r).fill(0);if(e.length>=4){let o=e[3].getBigInt64Array();for(let l=0;l<o.length;l++)s[Number(o[l])]=Number(i[l]),s[Number(o[l])+r]=Number(i[l+o.length])}else i.forEach((o,l)=>s[Number(l)]=Number(o));let a=[];return s.forEach(o=>a.push(o)),{mode:t.mode,value:n,pads:a}}else return t},ld=(e,t)=>{ed(e.inputs);let i=od(e.inputs,t);e.compute(ad(e.inputs,i),{inputs:[0]})}}),wi,cr,pr,fr,hr,ud,dd,mr,gr,cd,pd,_r,fd,hd,yr,md,gd,_d,yd,ef=C(()=>{yt(),me(),be(),$e(),wi=e=>{if(ne.webgpu.validateInputContent&&(!e||e.length!==1))throw new Error("Pool ops requires 1 input.")},cr=(e,t,i)=>{let n=t.format==="NHWC",r=e.dims.slice();n&&r.splice(1,0,r.pop());let s=Object.hasOwnProperty.call(t,"dilations"),a=t.kernelShape.slice(),o=t.strides.slice(),l=s?t.dilations.slice():[],u=t.pads.slice();Ri.adjustPoolAttributes(i,r,a,o,l,u);let d=Ri.computePoolOutputShape(i,r,o,l,a,u,t.autoPad),c=Object.assign({},t);s?Object.assign(c,{kernelShape:a,strides:o,pads:u,dilations:l,cacheKey:t.cacheKey}):Object.assign(c,{kernelShape:a,strides:o,pads:u,cacheKey:t.cacheKey});let p=d.slice();return p.push(p.splice(1,1)[0]),[c,n?p:d]},pr=(e,t)=>{let i=t.format==="NHWC",n=M.size(e),r=M.size(t.kernelShape),s=[{type:12,data:n},{type:12,data:r}],a=[{name:"outputSize",type:"u32"},{name:"kernelSize",type:"u32"}];if(t.kernelShape.length<=2){let o=t.kernelShape[t.kernelShape.length-1],l=t.strides[t.strides.length-1],u=t.pads[t.pads.length/2-1],d=t.pads[t.pads.length-1],c=!!(u+d);s.push({type:12,data:o},{type:12,data:l},{type:12,data:u},{type:12,data:d}),a.push({name:"kw",type:"u32"},{name:"sw",type:"u32"},{name:"pwStart",type:"u32"},{name:"pwEnd",type:"u32"});let p=!1;if(t.kernelShape.length===2){let h=t.kernelShape[t.kernelShape.length-2],m=t.strides[t.strides.length-2],_=t.pads[t.pads.length/2-2],$=t.pads[t.pads.length-2];p=!!(_+$),s.push({type:12,data:h},{type:12,data:m},{type:12,data:_},{type:12,data:$}),a.push({name:"kh",type:"u32"},{name:"sh",type:"u32"},{name:"phStart",type:"u32"},{name:"phEnd",type:"u32"})}return[s,a,!0,c,p]}else{if(i)throw new Error("Pooling with kernelShape.length > 2 is not supported for NHWC format.");let o=M.computeStrides(t.kernelShape);s.push({type:12,data:o},{type:12,data:t.pads},{type:12,data:t.strides}),a.push({name:"kernelStrides",type:"u32",length:o.length},{name:"pads",type:"u32",length:t.pads.length},{name:"strides",type:"u32",length:t.strides.length});let l=t.pads.reduce((u,d)=>u+d);return[s,a,!!l,!1,!1]}},fr=(e,t,i,n,r,s,a,o,l,u,d,c)=>{let p=r.format==="NHWC",h=t.type.value,m=ae("output",t.type.tensor,n);if(r.kernelShape.length<=2){let _="",$="",y="",g=i-(p?2:1);if(d?_=`
                for (var i: u32 = 0u; i < uniforms.kw; i++) {
                  xIndices[${g}] = indices[${g}] * uniforms.sw - uniforms.pwStart + i;
                  if (xIndices[${g}] < 0 || xIndices[${g}]
                      >= uniforms.x_shape[${g}]) {
                    pad++;
                    continue;
                  }
                  let x_val = x[${t.indicesToOffset("xIndices")}];
                  ${s}
                }`:_=`
                for (var i: u32 = 0u; i < uniforms.kw; i++) {
                  xIndices[${g}] = indices[${g}] * uniforms.sw - uniforms.pwStart + i;
                  let x_val = x[${t.indicesToOffset("xIndices")}];
                  ${s}
                }`,r.kernelShape.length===2){let T=i-(p?3:2);c?$=`
                for (var j: u32 = 0u; j < uniforms.kh; j++) {
                  xIndices[${T}] = indices[${T}] * uniforms.sh - uniforms.phStart + j;
                  if (xIndices[${T}] < 0 || xIndices[${T}] >= uniforms.x_shape[${T}]) {
                    pad += i32(uniforms.kw);
                    continue;
                  }
              `:$=`
                for (var j: u32 = 0u; j < uniforms.kh; j++) {
                  xIndices[${T}] = indices[${T}] * uniforms.sh - uniforms.phStart + j;
                `,y=`
              }
            `}return`
            ${e.registerUniforms(l).declareVariables(t,m)}

            ${e.mainStart()}
              ${e.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}

              let indices = ${m.offsetToIndices("global_idx")};
              var xIndices = ${m.offsetToIndices("global_idx")};

              var value = ${h}(${o});
              var pad = 0;
              ${$}
              ${_}
              ${y}
              ${a}

              output[global_idx] = value;
            }`}else{if(p)throw new Error("Pooling with kernelShape.length > 2 is not supported for NHWC format.");let _=r.kernelShape.length,$=r.pads.length,y="";return u?y=`
                if (xIndices[j] >= uniforms.x_shape[j]) {
                  pad++;
                  isPad = true;
                  break;
                }
              }
              if (!isPad) {
                let x_val = x[${t.indicesToOffset("xIndices")}];
                ${s}
              }`:y=`
              }
              let x_val = x[${t.indicesToOffset("xIndices")}];
              ${s}
            `,`
            ${e.registerUniforms(l).declareVariables(t,m)}

            ${e.mainStart()}
              ${e.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
              let indices = ${m.offsetToIndices("global_idx")};
              var xIndices = ${m.offsetToIndices("global_idx")};

              var offsets: array<u32, ${_}>;

              var value = ${h}(${o});
              var pad = 0;
              var isPad = false;

              for (var i: u32 = 0u; i < uniforms.kernelSize; i++) {
                var offset = i;
                for (var j = 0u; j < ${_-1}u; j++) {
                  offsets[j] = offset / ${oe("uniforms.kernelStrides","j",_)};
                  offset -= offsets[j] * ${oe("uniforms.kernelStrides","j",_)};
                }
                offsets[${_-1}] = offset;

                isPad = false;
                for (var j = ${i-_}u; j < ${i}u; j++) {
                  xIndices[j] = indices[j] * ${oe("uniforms.strides",`j - ${i-_}u`,_)}
                    + offsets[j - ${i-_}u] - ${oe("uniforms.pads","j - 2u",$)};
                  ${y}
              }
              ${a}

              output[global_idx] = value;
            }`}},hr=e=>`${e.format};${e.ceilMode};${e.autoPad};${e.kernelShape.length}`,ud=e=>`${hr(e)};${e.countIncludePad}`,dd=e=>`${hr(e)};${e.storageOrder};${e.dilations}`,mr=e=>({format:e.format,autoPad:["NOTSET","VALID","SAME_UPPER","SAME_LOWER"][e.auto_pad],ceilMode:e.ceil_mode,kernelShape:e.kernel_shape,strides:e.strides,pads:e.pads}),gr=(e,t,i,n)=>{let[r,s]=cr(t,n,i),a=F("x",t.dataType,t.dims.length),o=a.type.value,l="value += x_val;",u="";r.countIncludePad?u+=`value /= ${o}(uniforms.kernelSize);`:u+=`value /= ${o}(i32(uniforms.kernelSize) - pad);`;let[d,c,p,h,m]=pr(s,r);d.push(...de(t.dims,s));let _=["rank"];return{name:e,shaderCache:{hint:`${n.cacheKey};${p};${h};${m}`,inputDependencies:_},getRunData:()=>({outputs:[{dims:s,dataType:t.dataType}],dispatchGroup:{x:Math.ceil(M.size(s)/64)},programUniforms:d}),getShaderSource:$=>fr($,a,t.dims.length,s.length,r,l,u,0,c,p,h,m)}},cd=e=>{let t=e.count_include_pad!==0,i=mr(e);if(i.ceilMode!==0)throw new Error("using ceil() in shape computation is not yet supported for AveragePool");let n={countIncludePad:t,...i,cacheKey:""};return{...n,cacheKey:ud(n)}},pd=(e,t)=>{wi(e.inputs),e.compute(gr("AveragePool",e.inputs[0],!1,t))},_r={autoPad:"",ceilMode:0,countIncludePad:!1,kernelShape:[],strides:[],pads:[],storageOrder:0,dilations:[]},fd=e=>{let t=e.format;return{format:t,..._r,cacheKey:t}},hd=(e,t)=>{wi(e.inputs),e.compute(gr("GlobalAveragePool",e.inputs[0],!0,t))},yr=(e,t,i,n)=>{let[r,s]=cr(t,n,i),a=`
      value = max(x_val, value);
    `,o="",l=F("x",t.dataType,t.dims.length),u=["rank"],[d,c,p,h,m]=pr(s,r);return d.push(...de(t.dims,s)),{name:e,shaderCache:{hint:`${n.cacheKey};${p};${h};${m}`,inputDependencies:u},getRunData:()=>({outputs:[{dims:s,dataType:t.dataType}],dispatchGroup:{x:Math.ceil(M.size(s)/64)},programUniforms:d}),getShaderSource:_=>fr(_,l,t.dims.length,s.length,r,a,o,t.dataType===10?-65504:-1e5,c,p,h,m)}},md=(e,t)=>{wi(e.inputs),e.compute(yr("MaxPool",e.inputs[0],!1,t))},gd=e=>{let t=e.storage_order,i=e.dilations,n=mr(e);if(t!==0)throw new Error("column major storage order is not yet supported for MaxPool");if(n.ceilMode!==0)throw new Error("using ceil() in shape computation is not yet supported for MaxPool");let r={storageOrder:t,dilations:i,...n,cacheKey:""};return{...r,cacheKey:dd(r)}},_d=e=>{let t=e.format;return{format:t,..._r,cacheKey:t}},yd=(e,t)=>{wi(e.inputs),e.compute(yr("GlobalMaxPool",e.inputs[0],!0,t))}}),wd,bd,vd,$d,tf=C(()=>{me(),be(),Je(),$e(),wd=(e,t)=>{if(e.length<2||e.length>3)throw new Error("DequantizeLinear requires 2 or 3 inputs.");if(e.length===3&&e[1].dims===e[2].dims)throw new Error("x-scale and x-zero-point must have the same shape.");if(e.length===3&&e[0].dataType!==e[2].dataType)throw new Error("x and x-zero-point must have the same data type.");if(e[0].dataType===6&&e.length>2)throw new Error("In the case of dequantizing int32 there is no zero point.");if(e[1].dims.length!==0&&e[1].dims.length!==1&&e[1].dims.length!==e[0].dims.length)throw new Error("scale input must be a scalar, a 1D tensor, or have the same rank as the input tensor.");if(e.length>2){if(e[0].dataType!==e[2].dataType)throw new Error("x and x-zero-point must have the same data type.");if(e[1].dims.length!==e[2].dims.length)throw new Error("scale and zero-point inputs must have the same rank.");if(!e[1].dims.map((i,n)=>i===e[2].dims[n]).reduce((i,n)=>i&&n,!0))throw new Error("scale and zero-point inputs must have the same shape.")}if(t.blockSize>0){if(e[1].dims.length===0||e[1].dims.length===1&&e[1].dims[0]===1)throw new Error("blockSize must be set only for block quantization.");if(!e[1].dims.map((r,s)=>s===t.axis||r===e[0].dims[s]).reduce((r,s)=>r&&s,!0))throw new Error("For block qunatization, scale input shape to match the input shape except for the axis");if(e[1].dims.length!==e[0].dims.length)throw new Error("For block qunatization the scale input rank must be the same as the x rank.");let i=e[0].dims[t.axis],n=e[1].dims[t.axis];if(t.blockSize<Math.ceil(i/n)||t.blockSize>Math.ceil(i/(n-1)-1))throw new Error("blockSize must be with in the range [ceil(dI / Si), ceil(dI / (Si - 1) - 1)].")}},bd=(e,t)=>{let i=M.normalizeAxis(t.axis,e[0].dims.length),n=e[0].dataType,r=n===3,s=e[0].dims,a=e[1].dataType,o=M.size(s),l=n===3||n===2,u=l?[Math.ceil(M.size(e[0].dims)/4)]:e[0].dims,d=e[1].dims,c=e.length>2?e[2]:void 0,p=c?l?[Math.ceil(M.size(c.dims)/4)]:c.dims:void 0,h=d.length===0||d.length===1&&d[0]===1,m=h===!1&&d.length===1,_=Xe(o),$=h&&(!l||_===4),y=$?_:1,g=$&&!l?_:1,T=F("input",l?12:n,u.length,g),x=F("scale",a,d.length),E=c?F("zero_point",l?12:n,p.length):void 0,O=ae("output",a,s.length,y),z=[T,x];E&&z.push(E);let N=[u,d];c&&N.push(p);let L=[{type:12,data:o/y},{type:12,data:i},{type:12,data:t.blockSize},...de(...N,s)],ie=ge=>{let ce=[{name:"output_size",type:"u32"},{name:"axis",type:"u32"},{name:"block_size",type:"u32"}];return`
      ${ge.registerUniforms(ce).declareVariables(...z,O)}
      ${ge.mainStart()}
          ${ge.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
          let output_indices = ${O.offsetToIndices("global_idx")};

          // Set input x
          ${l?`
            let input = ${T.getByOffset("global_idx / 4")};
            let x_vec = ${r?"unpack4xI8(input)":"unpack4xU8(input)"};
            let x_value = ${y===1?"x_vec[global_idx % 4]":"x_vec"};`:`let x_value = ${T.getByOffset("global_idx")};`};

          // Set scale input
          ${h?`let scale_value= ${x.getByOffset("0")}`:m?`
            let scale_index = ${O.indicesGet("output_indices","uniforms.axis")};
            let scale_value= ${x.getByOffset("scale_index")};`:`
            var scale_indices: ${x.type.indices} = output_indices;
            let index = ${x.indicesGet("scale_indices","uniforms.axis")} / uniforms.block_size;
            ${x.indicesSet("scale_indices","uniforms.axis","index")};
            let scale_value= ${x.getByIndices("scale_indices")};`};

          // Set zero-point input
          ${E?h?l?`
                let zero_point_input = ${E.getByOffset("0")};
                let zero_point_vec =  ${r?"unpack4xI8(zero_point_input)":"unpack4xU8(zero_point_input)"};
                let zero_point_value= zero_point_vec[0]`:`let zero_point_value = ${E.getByOffset("0")}`:m?l?`
                let zero_point_index = ${O.indicesGet("output_indices","uniforms.axis")};
                let zero_point_input = ${E.getByOffset("zero_point_index / 4")};
                let zero_point_vec =  ${r?"unpack4xI8(zero_point_input)":"unpack4xU8(zero_point_input)"};
                let zero_point_value = zero_point_vec[zero_point_index % 4]`:`
                let zero_point_index = ${O.indicesGet("output_indices","uniforms.axis")};
                let zero_point_value = ${E.getByOffset("zero_point_index")};`:l?`
                let zero_point_offset = ${x.indicesToOffset("scale_indices")};
                let zero_point_input = ${E.getByOffset("zero_point_offset / 4")};
                let zero_point_vec = ${r?"unpack4xI8(zero_point_input)":"unpack4xU8(zero_point_input)"};
                let zero_point_value = zero_point_vec[zero_point_offset % 4];`:`let zero_point_value = ${E.getByIndices("scale_indices")};`:`let zero_point_value = ${l?r?"i32":"u32":T.type.value}(0);`};
      // Compute and write output
      ${O.setByOffset("global_idx",`${O.type.value}(x_value - zero_point_value) * scale_value`)};
      }`};return{name:"DequantizeLinear",shaderCache:{hint:t.cacheKey,inputDependencies:E?["rank","rank","rank"]:["rank","rank"]},getShaderSource:ie,getRunData:()=>({outputs:[{dims:s,dataType:a}],dispatchGroup:{x:Math.ceil(o/y/64),y:1,z:1},programUniforms:L})}},vd=(e,t)=>{wd(e.inputs,t),e.compute(bd(e.inputs,t))},$d=e=>Be({axis:e.axis,blockSize:e.blockSize})}),xd,Sd,kd,nf=C(()=>{yt(),me(),$e(),xd=(e,t,i)=>{let n=e===t,r=e<t&&i<0,s=e>t&&i>0;if(n||r||s)throw new Error("Range these inputs' contents are invalid.")},Sd=(e,t,i,n)=>{let r=Math.abs(Math.ceil((t-e)/i)),s=[r],a=r,o=[{type:12,data:a},{type:n,data:e},{type:n,data:i},...de(s)],l=u=>{let d=ae("output",n,s.length),c=d.type.value,p=[{name:"outputSize",type:"u32"},{name:"start",type:c},{name:"delta",type:c}];return`
        ${u.registerUniforms(p).declareVariables(d)}
        ${u.mainStart()}
        ${u.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
        output[global_idx] = uniforms.start + ${c}(global_idx) * uniforms.delta;
      }`};return{name:"Range",shaderCache:{hint:`${n}`},getShaderSource:l,getRunData:()=>({outputs:[{dims:s,dataType:n}],dispatchGroup:{x:Math.ceil(a/64)},programUniforms:o})}},kd=e=>{let t=0,i=0,n=0;e.inputs[0].dataType===6?(t=e.inputs[0].getInt32Array()[0],i=e.inputs[1].getInt32Array()[0],n=e.inputs[2].getInt32Array()[0]):e.inputs[0].dataType===1&&(t=e.inputs[0].getFloat32Array()[0],i=e.inputs[1].getFloat32Array()[0],n=e.inputs[2].getFloat32Array()[0]),ne.webgpu.validateInputContent&&xd(t,i,n),e.compute(Sd(t,i,n,e.inputs[0].dataType),{inputs:[]})}}),Td,Cd,Ed,Id,rf=C(()=>{me(),be(),Je(),$e(),Td=(e,t,i,n)=>{if(e!=="none"&&n!=="i32"&&n!=="u32"&&n!=="f32")throw new Error(`Input ${n} is not supported with reduction ${e}.`);let r=`{
                var oldValue = 0;
                loop {
                  let newValueF32 =`,s=`;
                  let newValue = bitcast<i32>(newValueF32);
                  let res = atomicCompareExchangeWeak(&${t}, oldValue, newValue);
                  if res.exchanged {
                    break;
                  }
                  oldValue = res.old_value;
                }
              }`;switch(e){case"none":return`${t}=${i};`;case"add":return n==="i32"||n==="u32"?`atomicAdd(&${t}, bitcast<${n}>(${i}));`:`
              ${r}bitcast<${n}>(oldValue) + (${i})${s}`;case"max":return n==="i32"||n==="u32"?`atomicMax(&${t}, bitcast<${n}>(${i}));`:`
                ${r}max(bitcast<f32>(oldValue), (${i}))${s}`;case"min":return n==="i32"||n==="u32"?`atomicMin(&${t}, bitcast<${n}>(${i}));`:`${r}min(bitcast<${n}>(oldValue), (${i}))${s}`;case"mul":return`${r}(bitcast<${n}>(oldValue) * (${i}))${s}`;default:throw new Error(`Reduction ${e} is not supported.`)}},Cd=(e,t)=>{let i=e[0].dims,n=e[1].dims,r=i,s=1,a=Math.ceil(M.sizeToDimension(n,n.length-1)/s),o=n[n.length-1],l=M.sizeFromDimension(i,o),u=[{type:12,data:a},{type:12,data:o},{type:12,data:l},...de(e[1].dims,e[2].dims,r)],d=c=>{let p=F("indices",e[1].dataType,e[1].dims.length),h=F("updates",e[2].dataType,e[2].dims.length,s),m=t.reduction!=="none"&&t.reduction!==""?Ms("output",e[0].dataType,r.length):ae("output",e[0].dataType,r.length,s);return`
      ${c.registerUniform("output_size","u32").registerUniform("last_index_dimension","u32").registerUniform("num_updates_elements","u32").declareVariables(p,h,m)}
      ${c.mainStart()}
        ${c.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
  var data_offset = 0u;
  let indices_start = uniforms.last_index_dimension * global_idx;
  let indices_end = indices_start + uniforms.last_index_dimension;
  for (var i = indices_start; i < indices_end; i++) {
    var index = i32(indices[i].x);
    ${e[0].dims.length===1?`
    let element_count_dim = uniforms.output_strides;
    let dim_value = uniforms.output_shape;`:`
    let element_count_dim = uniforms.output_strides[i - indices_start];
    let dim_value = uniforms.output_shape[i - indices_start];`}
    if (index >= 0) {
      if (index >= i32(dim_value)) {
        index = i32(dim_value - 1);
      }
    } else {
      if (index < -i32(dim_value)) {
        index = 0;
      } else {
        index += i32(dim_value);
      }
    }
    data_offset += u32((u32(index) * element_count_dim));
  }

  for (var i = 0u; i < uniforms.num_updates_elements; i++) {
    let value = updates[uniforms.num_updates_elements * global_idx + i];
    ${Td(t.reduction,"output[data_offset + i]","value",m.type.value)}
  }

      }`};return{name:"ScatterND",shaderCache:{hint:`${t.cacheKey}_${t.reduction}`,inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:r,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(a/64)},programUniforms:u}),getShaderSource:d}},Ed=e=>Be({reduction:e.reduction}),Id=(e,t)=>{e.compute(Cd(e.inputs,t),{inputs:[e.inputs[1],e.inputs[2]],outputs:[]})}}),Ad,zd,Od,wr,Rd,Md,Dd,Bd,Fd,Nd,Pd,Vd,br,Ld,Ud,qd,Wd,Gd,jd,Hd,sf=C(()=>{me(),be(),Je(),$e(),Ad=(e,t)=>{if(e.every(i=>i>0||(()=>{throw new Error("Resize requires scales input values to be positive")})),e.length>0){if(t.mode==="linear"){if(!(e.length===2||e.length===3||e.length===4&&e[0]===1&&e[1]===1||e.length===4&&e[0]===1&&e[3]===1||e.length===5&&e[0]===1&&e[1]===1))throw new Error(`For linear mode, Resize requires scales to be 2D, 3D, 4D with either two outermost or one innermost and
            one outermost scale values equal to 1, or 5D with two outermost scale values equal to 1`)}else if(t.mode==="cubic"&&!(e.length===2||e.length===4&&e[0]===1&&e[1]===1||e.length===4&&e[0]===1&&e[3]===1))throw new Error("Resize requires scales input size to be 2 or 4 for cubic mode")}},zd=(e,t,i)=>{t.every(r=>r>=0&&r<i||(()=>{throw new Error("Resize requires axes input values to be positive and less than rank")}));let n=new Array(i).fill(1);return t.forEach((r,s)=>n[r]=e[s]),n},Od=(e,t,i,n,r,s)=>{let[a,o,l]=i>10?[1,2,3]:[-1,e.length>1?1:-1,-1],u=e[0].dims.length;if(a>0&&e.length>a&&e[a].dims.length>0)e[a].getFloat32Array().forEach(d=>s.push(d));else if(t.coordinateTransformMode==="tf_crop_and_resize")throw new Error("Resize requires RoI input to be specified when coordinateTransformMode is tfCropAndResize");if(o>0&&e.length>o&&e[o].dims.length===1&&e[o].dims[0]>0){if(e[o].getFloat32Array().forEach(d=>n.push(d)),n.length!==0&&n.length!==u&&i>=18&&n.length!==t.axes.length)throw new Error("Resize requires scales input size to be same as input rank or axes size for opset 18 and up");Ad(n,t),t.axes.length>0&&zd(n,t.axes,u).forEach((d,c)=>n[c]=d)}if(l>0&&e.length>l&&e[l].dims.length===1&&e[l].dims[0]>0&&(e[l].getBigInt64Array().forEach(d=>r.push(Number(d))),r.length!==0&&r.length!==u&&i>=18&&r.length!==t.axes.length))throw new Error("Resize requires sizes input size to be same as input rank or axes size for opset 18 and up");if(t.axes.length>0){if(n.length!==0&&n.length!==t.axes.length)throw new Error('Resize requires "scales" input size to be of axes rank when axes attributes is specified');if(r.length!==0&&r.length!==t.axes.length)throw new Error('Resize requires "sizes" input size to be of rank axes rank when axes attributes is specified')}if(typeof n<"u"&&typeof r<"u"&&n.length>0&&r.length>u)throw new Error("Resize requires only of scales or sizes to be specified")},wr=(e,t,i,n)=>`
  // The whole part and the fractional part are calculated separately due to inaccuracy of floating
  // point division. As an example, f32(21) / f32(7) may evaluate to 2.99... instead of 3, causing an
  // offset-by-one error later in floor().
  let big = (${e}) * (${t});
  let whole = ${n}(big / (${i}));
  let fract = ${n}(big % (${i})) / ${n}(${i});
  return whole + fract;
`,Rd=(e,t)=>`fn getOriginalCoordinateFromResizedCoordinate(xResized: u32, xScale: f32, lengthResized: u32,
     lengthOriginal: u32, roiStart: f32, roiEnd: f32) -> ${t} { `+(()=>{switch(e){case"asymmetric":return`
          if (xScale < 1.0 || floor(xScale) != xScale) {
            return ${t}(xResized) / ${t}(xScale);
          } else {
            ${wr("xResized","lengthOriginal","lengthResized",t)}
          }
        `;case"pytorch_half_pixel":return`if (lengthResized > 1) {
                    return (${t}(xResized) + 0.5) / ${t}(xScale) - 0.5;
                  } else {
                    return 0.0;
                  }`;case"tf_half_pixel_for_nn":return`return (${t}(xResized) + 0.5) / ${t}(xScale);`;case"align_corners":return`if (lengthResized == 1) {
                    return 0.0;
                  } else {
                    ${wr("xResized","lengthOriginal - 1","lengthResized - 1",t)}
                  }`;case"tf_crop_and_resize":return`if (lengthResized > 1) {
                    return ${t}(roiStart) * ${t}(lengthOriginal - 1) +
                        (${t}(xResized) * ${t}(roiEnd - roiStart) * ${t}(lengthOriginal - 1)) /
                        ${t}(lengthResized - 1);
                  } else {
                    return 0.5 * ${t}(roiStart + roiEnd) * ${t}(lengthOriginal - 1);
                  }`;case"half_pixel_symmetric":return`const outputWidth = ${t}xScale * ${t}(lengthResized);
                  const adjustment = ${t}(lengthResized) / outputWidth;
                  const center = ${t}(lengthOriginal) / 2;
                  const offset = center * (1 - adjustment);
                  return offset + ((${t}(xResized) + 0.5) / ${t}(xScale)) - 0.5;`;case"half_pixel":return`return ((${t}(xResized) + 0.5) / ${t}(xScale)) - 0.5;`;default:throw new Error(`Coordinate transform mode ${e} is not supported`)}})()+"}",Md=(e,t,i)=>`fn getNearestPixelFromOriginal(xOriginal: ${i}, isDownSample: bool) -> ${i} {`+(()=>{switch(e){case"round_prefer_ceil":return"if (fract(xOriginal) == 0.5) {             return ceil(xOriginal);           } else {             return round(xOriginal);           }";case"floor":return"return floor(xOriginal);";case"ceil":return"return ceil(xOriginal);";case"round_prefer_floor":return"if (fract(xOriginal) == 0.5) {                     return floor(xOriginal);                   } else {                     return round(xOriginal);                   }";case"simple":default:if(t<11)return"if (isDownSample)                     {                       return ceil(xOriginal);                     } else {                       return xOriginal;                     }";throw new Error(`Nearest mode ${e} is not supported`)}})()+"}",Dd=(e,t,i)=>{let n=new Array(i).fill(0).concat(new Array(i).fill(1)),r=e.length===0?n:e.slice();return t.length>0?(t.forEach((s,a)=>{n[s]=r[a],n[a+i]=r[t.length+a]}),n):r},Bd=(e,t,i,n)=>{let r=[];if(i.length>0)if(n.length>0){if(e.forEach(s=>r.push(s)),Math.max(...n)>e.length)throw new Error("axes is out of bound");n.forEach((s,a)=>r[s]=i[a])}else i.forEach(s=>r.push(s));else{if(t.length===0)throw new Error("Resize requires either scales or sizes.");r=e.map((s,a)=>Math.round(s*t[a]))}return r},Fd=(e,t,i)=>{let n=(()=>{switch(i.keepAspectRatioPolicy){case"not_larger":return i.axes.length>0?Math.min(...i.axes.map(s=>t[s]),Number.MAX_VALUE):Math.min(...t,Number.MAX_VALUE);case"not_smaller":return i.axes.length>0?Math.max(...i.axes.map(s=>t[s]),Number.MIN_VALUE):Math.max(...t,Number.MIN_VALUE);default:throw new Error(`Keep aspect ratio policy ${i.keepAspectRatioPolicy} is not supported`)}})();t.fill(1,0,t.length);let r=e.slice();return i.axes.length>0?(i.axes.forEach(s=>t[s]=n),i.axes.forEach(s=>r[s]=Math.round(e[s]*t[s]))):(t.fill(n,0,t.length),r.forEach((s,a)=>r[a]=Math.round(s*t[a]))),r},Nd=(e,t,i,n,r)=>`
    fn calculateOriginalIndicesFromOutputIndices(output_indices: ${e.type.indices}) -> array<${e.type.value}, ${i.length}> {
      var original_indices: array<${e.type.value}, ${i.length}>;
      for (var i:u32 = 0; i < ${i.length}; i++) {
        var output_index = ${e.indicesGet("output_indices","i")};
        var scale = ${oe("uniforms.scales","i",n)};
        var roi_low = ${oe("uniforms.roi","i",r)};
        var roi_hi = ${oe("uniforms.roi",`i + ${t.length}`,r)};
        if (scale == 1.0) {
          original_indices[i] = ${e.type.value}(output_index);
        } else {
          var input_shape_i = ${oe("uniforms.input_shape","i",t.length)};
          var output_shape_i = ${oe("uniforms.output_shape","i",i.length)};
          original_indices[i] = getOriginalCoordinateFromResizedCoordinate(output_index, scale, output_shape_i,
                                                                           input_shape_i, roi_low, roi_hi);
        }
      }
      return original_indices;
    }`,Pd=(e,t,i,n,r,s,a)=>`
    fn calculateInputIndicesFromOutputIndices(output_indices: ${t.type.indices}) -> ${e.type.indices} {
      var input_indices: ${e.type.indices};
      for (var i:u32 = 0; i < ${n.length}; i++) {
        var output_index = ${t.indicesGet("output_indices","i")};
        var input_index: u32;
        var scale = ${oe("uniforms.scales","i",r)};
        if (scale == 1.0) {
          input_index = output_index;
        } else {
          var roi_low = ${oe("uniforms.roi","i",s)};
          var roi_hi = ${oe("uniforms.roi",`i + ${i.length}`,s)};
          var input_shape_i = ${oe("uniforms.input_shape","i",i.length)};
          var output_shape_i = ${oe("uniforms.output_shape","i",n.length)};
          var original_idx = getOriginalCoordinateFromResizedCoordinate(output_index, scale, output_shape_i,
                                                                        input_shape_i, roi_low, roi_hi);
          if (!${a} || (original_idx >= 0 && original_idx < ${t.type.value}(input_shape_i))) {
            if (original_idx < 0) {
              input_index = 0;
            } else if (original_idx > ${t.type.value}(input_shape_i - 1)) {
              input_index = input_shape_i - 1;
            } else {
              input_index = u32(getNearestPixelFromOriginal(original_idx, scale < 1));
            }
          } else {
            input_index = u32(original_idx);
          }
        }
        ${e.indicesSet("input_indices","i","input_index")}
      }
      return input_indices;
    }`,Vd=(e,t)=>`
    fn checkInputIndices(input_indices: ${e.type.indices}) -> bool {
      for (var i:u32 = 0; i < ${t.length}; i++) {
        var input_index = ${e.indicesGet("input_indices","i")};
        if (input_index < 0 || input_index >= ${oe("uniforms.input_shape","i",t.length)}) {
          return false;
        }
      }
      return true;
    }`,br=(e,t,i,n)=>e.rank>n?`
    ${e.indicesSet("input_indices",t,"channel")};
    ${e.indicesSet("input_indices",i,"batch")};
`:"",Ld=(e,t,i,n,r)=>{let[s,a,o,l]=i.length===2?[-1,0,1,-1]:[0,2,3,1],u=e.type.value;return`
    fn getInputValue(batch: u32, channel: u32, row: u32, col: u32) -> ${u} {
      var input_indices: ${e.type.indices};
      ${e.indicesSet("input_indices",a,`max(0, min(row, ${i[a]} - 1))`)};
      ${e.indicesSet("input_indices",o,`max(0, min(col, ${i[o]} - 1))`)};
      ${br(e,l,s,2)}
      return ${e.getByIndices("input_indices")};
    }

    fn bilinearInterpolation(output_indices: ${t.type.indices}) -> ${u} {
      var originalIndices = calculateOriginalIndicesFromOutputIndices(output_indices);
      var row:${u} = originalIndices[${a}];
      var col:${u} = originalIndices[${o}];
      ${n?`if (row < 0 || row > (${i[a]} - 1) || col < 0 || col > (${i[o]} - 1)) {
        return ${r};
      }`:""};
      row = max(0, min(row, ${i[a]} - 1));
      col = max(0, min(col, ${i[o]} - 1));
      var row1: u32 = u32(row);
      var col1: u32 = u32(col);
      var row2: u32 = u32(row + 1);
      var col2: u32 = u32(col + 1);
      var channel: u32 = ${i.length>2?`u32(originalIndices[${l}])`:"0"};
      var batch: u32 =  ${i.length>2?`u32(originalIndices[${s}])`:"0"};
      var x11: ${u} = getInputValue(batch, channel, row1, col1);
      var x12: ${u} = getInputValue(batch, channel, row1, col2);
      var x21: ${u} = getInputValue(batch, channel, row2, col1);
      var x22: ${u} = getInputValue(batch, channel, row2, col2);
      var dx1: ${u} = abs(row - ${u}(row1));
      var dx2: ${u} = abs(${u}(row2) - row);
      var dy1: ${u} = abs(col - ${u}(col1));
      var dy2: ${u} = abs(${u}(col2) - col);
      if (row1 == row2) {
        dx1 = 0.5;
        dx2 = 0.5;
      }
      if (col1 == col2) {
        dy1 = 0.5;
        dy2 = 0.5;
      }
      return (x11 * dx2 * dy2 + x12 * dx2 * dy1 + x21 * dx1 * dy2 + x22 * dx1 * dy1);
    }`},Ud=(e,t,i,n,r,s,a,o,l,u)=>{let d=i.length===2,[c,p]=d?[0,1]:[2,3],h=e.type.value,m=_=>{let $=_===c?"row":"col";return`
      fn ${$}CubicInterpolation(input_indices: ${e.type.indices}, output_indices: ${t.type.indices}) -> ${h} {
        var output_index = ${t.indicesGet("output_indices",_)};
        var originalIdx: ${h} = getOriginalCoordinateFromResizedCoordinate(output_index, ${r[_]},
        ${n[_]}, ${i[_]}, ${s[_]}, ${s[_]} + ${i.length});
        var fractOriginalIdx: ${h} = originalIdx - floor(originalIdx);
        var coefs = getCubicInterpolationCoefs(fractOriginalIdx);

        if (${o} && (originalIdx < 0 || originalIdx > (${i[_]} - 1))) {
          return ${l};
        }
        var data: array<${h}, 4> = array<${h}, 4>(0.0, 0.0, 0.0, 0.0);
        for (var i: i32 = -1; i < 3; i++) {
          var ${$}: ${h} = originalIdx + ${h}(i);
          if (${$} < 0 || ${$} >= ${i[_]}) {
            ${u?`coefs[i + 1] = 0.0;
                        continue;`:o?`return ${l};`:`${$} = max(0, min(${$}, ${i[_]} - 1));`};
          }
        var input_indices_copy: ${e.type.indices} = input_indices;
          ${e.indicesSet("input_indices_copy",_,`u32(${$})`)};
          data[i + 1] = ${_===c?e.getByIndices("input_indices_copy"):"rowCubicInterpolation(input_indices_copy, output_indices)"};
        }
        return cubicInterpolation1D(data, coefs);
      }`};return`
    ${m(c)};
    ${m(p)};
  fn getCubicInterpolationCoefs(s: ${h}) -> array<${h}, 4> {
    var absS = abs(s);
    var coeffs: array<${h}, 4> = array<${h}, 4>(0.0, 0.0, 0.0, 0.0);
    var oneMinusAbsS: ${h} = 1.0 - absS;
    var twoMinusAbsS: ${h} = 2.0 - absS;
    var onePlusAbsS: ${h} = 1.0 + absS;
    coeffs[0] = ((${a} * onePlusAbsS - 5 * ${a}) * onePlusAbsS + 8 * ${a}) * onePlusAbsS - 4 * ${a};
    coeffs[1] = ((${a} + 2) * absS - (${a} + 3)) * absS * absS + 1;
    coeffs[2] = ((${a} + 2) * oneMinusAbsS - (${a} + 3)) * oneMinusAbsS * oneMinusAbsS + 1;
    coeffs[3] = ((${a} * twoMinusAbsS - 5 * ${a}) * twoMinusAbsS + 8 * ${a}) * twoMinusAbsS - 4 * ${a};
    return coeffs;
  }

  fn cubicInterpolation1D(x: array<${h}, 4>, coefs: array<${h}, 4>) -> ${h} {
    var coefsSum: ${h} = coefs[0] + coefs[1] + coefs[2] + coefs[3];
    return (x[0] * coefs[0] + x[1] * coefs[1]+ x[2] * coefs[2]+ x[3] * coefs[3]) / coefsSum;
  }

  fn bicubicInterpolation(output_indices: ${t.type.indices}) -> ${h} {
    var input_indices: ${e.type.indices} = output_indices;
    return colCubicInterpolation(input_indices, output_indices);
  }
    `},qd=(e,t,i,n,r)=>{let[s,a,o,l,u]=i.length===3?[-1,0,1,2,-1]:[0,2,3,4,1],d=e.type.value;return`
    fn getInputValue(batch: u32, channel: u32, depth:u32, height: u32, width: u32) -> ${d} {
      var input_indices: ${e.type.indices};
      ${e.indicesSet("input_indices",a,`max(0, min(depth, ${i[a]} - 1))`)};
      ${e.indicesSet("input_indices",o,`max(0, min(height, ${i[o]} - 1))`)};
      ${e.indicesSet("input_indices",l,`max(0, min(width, ${i[l]} - 1))`)};
      ${br(e,u,s,3)}
      return ${e.getByIndices("input_indices")};
    }

    fn trilinearInterpolation(output_indices: ${t.type.indices}) -> ${d} {
      var originalIndices = calculateOriginalIndicesFromOutputIndices(output_indices);
      var depth:${d} = originalIndices[${a}];
      var height:${d} = originalIndices[${o}];
      var width:${d} = originalIndices[${l}];
      ${n?`if (depth < 0 || depth > (${i[a]} - 1) || height < 0 || height > (${i[o]} - 1) || width < 0 || (width > ${i[l]} - 1)) {
      return ${r};
        }`:""};

    depth = max(0, min(depth, ${i[a]} - 1));
      height = max(0, min(height, ${i[o]} - 1));
      width = max(0, min(width, ${i[l]} - 1));
      var depth1: u32 = u32(depth);
      var height1: u32 = u32(height);
      var width1: u32 = u32(width);
      var depth2: u32 = u32(depth + 1);
      var height2: u32 = u32(height + 1);
      var width2: u32 = u32(width + 1);
      var channel: u32 = ${i.length>3?`u32(originalIndices[${u}])`:"0"};
      var batch: u32 =  ${i.length>3?`u32(originalIndices[${s}])`:"0"};

      var x111: ${d} = getInputValue(batch, channel, depth1, height1, width1);
      var x112: ${d} = getInputValue(batch, channel, depth1, height1, width2);
      var x121: ${d} = getInputValue(batch, channel, depth1, height2, width1);
      var x122: ${d} = getInputValue(batch, channel, depth1, height2, width2);
      var x211: ${d} = getInputValue(batch, channel, depth2, height1, width1);
      var x212: ${d} = getInputValue(batch, channel, depth2, height1, width2);
      var x221: ${d} = getInputValue(batch, channel, depth2, height2, width1);
      var x222: ${d} = getInputValue(batch, channel, depth2, height2, width2);
      var dx1: ${d} = abs(depth - ${d}(depth1));
      var dx2: ${d} = abs(${d}(depth2) - depth);
      var dy1: ${d} = abs(height - ${d}(height1));
      var dy2: ${d} = abs(${d}(height2) - height);
      var dz1: ${d} = abs(width - ${d}(width1));
      var dz2: ${d} = abs(${d}(width2) - width);
      if (depth1 == depth2) {
        dx1 = 0.5;
        dx2 = 0.5;
      }
      if (height1 == height2) {
        dy1 = 0.5;
        dy2 = 0.5;
      }
      if (width1 == width2) {
        dz1 = 0.5;
        dz2 = 0.5;
      }
      return (x111 * dx2 * dy2 * dz2 + x112 * dx2 * dy2 * dz1 + x121 * dx2 * dy1 *dz2 + x122 * dx2 * dy1 * dz1 +
              x211 * dx1 * dy2 * dz2 + x212 * dx1 * dy2 * dz1 + x221 * dx1 * dy1 *dz2 + x222 * dx1 * dy1 * dz1);
    }`},Wd=(e,t,i,n,r,s)=>{let a=e.dims,o=Dd(s,t.axes,a.length),l=Bd(a,n,r,t.axes),u=n.slice();n.length===0&&(u=a.map((g,T)=>g===0?1:l[T]/g),t.keepAspectRatioPolicy!=="stretch"&&(l=Fd(a,u,t)));let d=ae("output",e.dataType,l.length),c=F("input",e.dataType,a.length),p=M.size(l),h=a.length===l.length&&a.every((g,T)=>g===l[T]),m=t.coordinateTransformMode==="tf_crop_and_resize",_=t.extrapolationValue,$=c.type.value,y=g=>`
      ${h?"":`
      ${Rd(t.coordinateTransformMode,$)};
      ${(()=>{switch(t.mode){case"nearest":return`
              ${Vd(c,a)};
              ${Md(t.nearestMode,i,$)};
              ${Pd(c,d,a,l,u.length,o.length,m)};
              `;case"linear":return`
              ${Nd(d,a,l,u.length,o.length)};
              ${(()=>{if(a.length===2||a.length===4)return`${Ld(c,d,a,m,_)}`;if(a.length===3||a.length===5)return`${qd(c,d,a,m,_)}`;throw Error("Linear mode only supports input dims 2, 3, 4 and 5 are supported in linear mode.")})()};
            `;case"cubic":return`
            ${(()=>{if(a.length===2||a.length===4)return`${Ud(c,d,a,l,u,o,t.cubicCoeffA,m,t.extrapolationValue,t.excludeOutside)}`;throw Error("Cubic mode only supports input dims 2 and 4 are supported in linear mode.")})()};
            `;default:throw Error("Invalid resize mode")}})()};
      `}
      ${g.registerUniform("output_size","u32").registerUniform("scales","f32",u.length).registerUniform("roi","f32",o.length).declareVariables(c,d)}
      ${g.mainStart()}
        ${g.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
        ${h?"output[global_idx] = input[global_idx];":`
        let output_indices = ${d.offsetToIndices("global_idx")};
        var input_indices: ${c.type.indices};
        ${(()=>{switch(t.mode){case"nearest":return`input_indices = calculateInputIndicesFromOutputIndices(output_indices);
                if (checkInputIndices(input_indices)) {
                  output[global_idx] = ${c.getByIndices("input_indices")};
                } else {
                  output[global_idx] = ${t.extrapolationValue};
                }`;case"linear":return`output[global_idx] = ${a.length===2||a.length===4?"bilinearInterpolation":"trilinearInterpolation"}(output_indices);`;case"cubic":return"output[global_idx] = bicubicInterpolation(output_indices);";default:throw Error(`Unsupported resize mode: ${t.mode}`)}})()};
`}
      }`;return{name:"Resize",shaderCache:{hint:`${t.cacheKey}|${i}|${u.length>0?t.mode==="cubic"?u:u.length:""}|${r.length>0?r:""}|${o.length>0?o:""}|${h}|${t.mode==="nearest"?a.length:a}`,inputDependencies:["rank"]},getShaderSource:y,getRunData:()=>({outputs:[{dims:l,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:[{type:12,data:p},{type:1,data:u},{type:1,data:o},...de(a,l)]})}},Gd=e=>{let t=e.customDataBuffer;return new Uint32Array(t,t.byteOffset,1)[0]},jd=(e,t)=>{let i=[],n=[],r=[],s=Gd(e);if(t.antialias!==0)throw Error("Only default value (0) for Antialias attribute is supported");Od(e.inputs,t,s,i,n,r),e.compute(Wd(e.inputs[0],t,s,i,n,r),{inputs:[0]})},Hd=e=>{let t=e.antialias,i=e.axes,n=e.coordinateTransformMode,r=e.cubicCoeffA,s=e.excludeOutside!==0,a=e.extrapolationValue,o=e.keepAspectRatioPolicy,l=e.mode,u=e.nearestMode===""?"simple":e.nearestMode;return Be({antialias:t,axes:i,coordinateTransformMode:n,cubicCoeffA:r,excludeOutside:s,extrapolationValue:a,keepAspectRatioPolicy:o,mode:l,nearestMode:u})}}),Kd,Qd,Zd,af=C(()=>{me(),be(),$e(),Kd=e=>{if(!e||e.length<3)throw new Error("layerNorm requires at least 3 inputs.");let t=e[0],i=e[1],n=e[2];if(t.dataType!==i.dataType||t.dataType!==n.dataType)throw new Error("All inputs must have the same data type");if(t.dims.length!==3&&t.dims.length!==2)throw new Error("Input must be 2D or 3D");if(i.dims.length!==3&&i.dims.length!==2)throw new Error("Skip must be 2D or 3D");let r=t.dims[t.dims.length-1],s=t.dims[t.dims.length-2];if(i.dims[i.dims.length-1]!==r)throw new Error("Skip must have the same hidden size as input");if(i.dims[i.dims.length-2]!==s)throw new Error("Skip must have the same sequence length as input");if(n.dims.length!==1)throw new Error("Gamma must be 1D");if(n.dims[n.dims.length-1]!==r)throw new Error("Gamma must have the same hidden size as input");if(e.length>3){let a=e[3];if(a.dims.length!==1)throw new Error("Beta must be 1D");if(a.dims[a.dims.length-1]!==r)throw new Error("Beta must have the same hidden size as input")}if(e.length>4){let a=e[4];if(a.dims.length!==1)throw new Error("Bias must be 1D");if(a.dims[a.dims.length-1]!==r)throw new Error("Bias must have the same hidden size as input")}},Qd=(e,t,i,n)=>{let r=t.simplified,s=e[0].dims,a=M.size(s),o=s,l=a,u=s.slice(-1)[0],d=n?s.slice(0,-1).concat(1):[],c=!r&&e.length>3,p=e.length>4,h=n&&i>1,m=n&&i>2,_=i>3,$=64,y=Xe(u),g=[{type:12,data:l},{type:12,data:y},{type:12,data:u},{type:1,data:t.epsilon}],T=E=>{let O=[{name:"output_size",type:"u32"},{name:"components",type:"u32"},{name:"hidden_size",type:"u32"},{name:"epsilon",type:"f32"}],z=[F("x",e[0].dataType,e[0].dims,y),F("skip",e[1].dataType,e[1].dims,y),F("gamma",e[2].dataType,e[2].dims,y)];c&&z.push(F("beta",e[3].dataType,e[3].dims,y)),p&&z.push(F("bias",e[4].dataType,e[4].dims,y)),z.push(ae("output",e[0].dataType,o,y)),h&&z.push(ae("mean_output",1,d)),m&&z.push(ae("inv_std_output",1,d)),_&&z.push(ae("input_skip_bias_sum",e[0].dataType,o,y));let N=at(e[0].dataType),L=at(1,y);return`

      ${E.registerUniforms(O).declareVariables(...z)}
      var<workgroup> sum_shared : array<${L}, ${$}>;
      var<workgroup> sum_squared_shared : array<${L}, ${$}>;

      ${E.mainStart([$,1,1])}
        let ix = local_id.x;
        let iy = global_id.x / ${$};

        let hidden_size_vectorized: u32 = uniforms.hidden_size / uniforms.components;
        var stride = hidden_size_vectorized / ${$};
        let offset = ix * stride + iy * hidden_size_vectorized;
        let offset1d = stride * ix;
        if (ix == ${$-1}) {
          stride = hidden_size_vectorized - stride * ix;
        }
        for (var i: u32 = 0; i < stride; i++) {
          let skip_value = skip[offset + i];
          let bias_value = ${p?"bias[offset1d + i]":N+"(0.0)"};
          let input_value = x[offset + i];
          let value = input_value + skip_value + bias_value;
          ${_?"input_skip_bias_sum[offset + i] = value;":""}
          output[offset + i] = value;
          let f32_value = ${ri(N,y,"value")};
          sum_shared[ix] += f32_value;
          sum_squared_shared[ix] += f32_value * f32_value;
        }
        workgroupBarrier();

        var reduce_size : u32 = ${$};
        for (var curr_size = reduce_size >> 1;  curr_size > 0; curr_size = reduce_size >> 1) {
          reduce_size = curr_size + (reduce_size & 1);
          if (ix < curr_size) {
            sum_shared[ix] += sum_shared[ix + reduce_size];
            sum_squared_shared[ix] += sum_squared_shared[ix + reduce_size];
          }
          workgroupBarrier();
        }

        let sum = sum_shared[0];
        let square_sum = sum_squared_shared[0];
        let mean = ${Bt("sum",y)} / f32(uniforms.hidden_size);
        let inv_std_dev = inverseSqrt(${Bt("square_sum",y)} / f32(uniforms.hidden_size) ${r?"":"- mean * mean"} + uniforms.epsilon);
        ${h?"mean_output[global_idx] = mean;":""}
        ${m?"inv_std_output[global_idx] = inv_std_dev;":""}

        for (var i: u32 = 0; i < stride; i++) {
          output[offset + i] = (output[offset + i] ${r?"":`- ${N}(mean)`}) *
            ${N}(inv_std_dev) * gamma[offset1d + i]
            ${c?"+ beta[offset1d + i]":""};
        }
      }`},x=[{dims:o,dataType:e[0].dataType}];return i>1&&x.push({dims:d,dataType:1}),i>2&&x.push({dims:d,dataType:1}),i>3&&x.push({dims:s,dataType:e[0].dataType}),{name:"SkipLayerNormalization",shaderCache:{hint:`${y};${h};${m};${_}`,inputDependencies:e.map((E,O)=>"type")},getShaderSource:T,getRunData:()=>({outputs:x,dispatchGroup:{x:Math.ceil(l/u)},programUniforms:g})}},Zd=(e,t)=>{Kd(e.inputs);let i=[0];e.outputCount>1&&i.push(-3),e.outputCount>2&&i.push(-3),e.outputCount>3&&i.push(3),e.compute(Qd(e.inputs,t,e.outputCount,!1),{outputs:i})}}),Xd,bi,Yd,vr,Jd,ec,tc,ic,of=C(()=>{me(),be(),Je(),$e(),Xd=(e,t)=>{if(!e||e.length<1)throw new Error("too few inputs");if(t.axes.length!==0){if(t.axes.length!==t.starts.length||t.axes.length!==t.ends.length)throw new Error("axes, starts and ends must have the same length")}else if(t.starts.length!==t.ends.length)throw new Error("starts and ends must have the same length");e.slice(1).forEach((i,n)=>{if(e[n+1].dataType!==6&&e[n+1].dataType!==7)throw new Error(`Input ${n} must be an array of int32 or int64`)})},bi=(e,t)=>{let i=[];if(e.length>t)if(e[t].dataType===7)e[t].getBigInt64Array().forEach(n=>i.push(Number(n)));else if(e[t].dataType===6)e[t].getInt32Array().forEach(n=>i.push(Number(n)));else throw new Error(`Input ${t} must be an array of int32 or int64`);return i},Yd=(e,t)=>{if(e.length>1){let i=bi(e,1),n=bi(e,2),r=bi(e,3);return r.length===0&&(r=[...Array(e[0].dims.length).keys()]),Be({starts:i,ends:n,axes:r})}else return t},vr=(e,t,i,n,r)=>{let s=e;return e<0&&(s+=i[n[t]]),r[t]<0?Math.max(0,Math.min(s,i[n[t]]-1)):Math.max(0,Math.min(s,i[n[t]]))},Jd=(e,t,i)=>`fn calculateInputIndices(output_indices: ${t.type.indices}) -> ${e.type.indices} {
          var input_indices: ${e.type.indices};
          var carry = 0u;
          for (var i = ${i.length-1}; i >= 0; i--) {
            let input_shape_i = ${oe("uniforms.input_shape","i",i.length)};
            let steps_i = ${oe("uniforms.steps","i",i.length)};
            let signs_i = ${oe("uniforms.signs","i",i.length)};
            let starts_i = ${oe("uniforms.starts","i",i.length)};
            var output_index = ${t.indicesGet("output_indices","i")};
            var input_index = output_index * steps_i + starts_i + carry;
            carry = input_index / input_shape_i;
            input_index = input_index % input_shape_i;
            if (signs_i < 0) {
              input_index = input_shape_i - input_index - 1u + starts_i;
            }
            ${e.indicesSet("input_indices","i","input_index")};
          }
          return input_indices;
      }`,ec=(e,t)=>{let i=e[0].dims,n=M.size(i),r=t.axes.length>0?M.normalizeAxes(t.axes,i.length):[...Array(i.length).keys()],s=bi(e,4);s.forEach(y=>y!==0||(()=>{throw new Error("step cannot be 0")})),s.length===0&&(s=Array(r.length).fill(1));let a=t.starts.map((y,g)=>vr(y,g,i,r,s)),o=t.ends.map((y,g)=>vr(y,g,i,r,s));if(r.length!==a.length||r.length!==o.length)throw new Error("start, ends and axes should have the same number of elements");if(r.length!==i.length)for(let y=0;y<i.length;++y)r.includes(y)||(a.splice(y,0,0),o.splice(y,0,i[y]),s.splice(y,0,1));let l=s.map(y=>Math.sign(y));s.forEach((y,g,T)=>{if(y<0){let x=(o[g]-a[g])/y,E=a[g],O=E+x*s[g];a[g]=O,o[g]=E,T[g]=-y}});let u=i.slice(0);r.forEach((y,g)=>{u[y]=Math.ceil((o[y]-a[y])/s[y])});let d={dims:u,dataType:e[0].dataType},c=ae("output",e[0].dataType,u.length),p=F("input",e[0].dataType,e[0].dims.length),h=M.size(u),m=[{name:"outputSize",type:"u32"},{name:"starts",type:"u32",length:a.length},{name:"signs",type:"i32",length:l.length},{name:"steps",type:"u32",length:s.length}],_=[{type:12,data:h},{type:12,data:a},{type:6,data:l},{type:12,data:s},...de(e[0].dims,u)],$=y=>`
      ${y.registerUniforms(m).declareVariables(p,c)}
        ${Jd(p,c,i)}
        ${y.mainStart()}
          ${y.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
          let output_indices = ${c.offsetToIndices("global_idx")};
          let input_indices = calculateInputIndices(output_indices);
          ${c.setByOffset("global_idx",p.getByIndices("input_indices"))}
      }`;return{name:"Slice",shaderCache:{hint:`${l.length}_${a.length}_${s.length}`,inputDependencies:["rank"]},getShaderSource:$,getRunData:()=>({outputs:[d],dispatchGroup:{x:Math.ceil(n/64)},programUniforms:_})}},tc=(e,t)=>{Xd(e.inputs,t);let i=Yd(e.inputs,t);e.compute(ec(e.inputs,i),{inputs:[0]})},ic=e=>{let t=e.starts,i=e.ends,n=e.axes;return Be({starts:t,ends:i,axes:n})}}),nc,rc,sc,ac,lf=C(()=>{me(),be(),Je(),Ft(),$e(),nc=e=>{if(!e||e.length!==1)throw new Error("Softmax op requires 1 input.")},rc=(e,t)=>{let i=e.inputs[0],n=i.dims,r=M.size(n),s=n.length,a=M.normalizeAxis(t.axis,s),o=a<n.length-1,l,u=[];o?(u=Array.from({length:s},(z,N)=>N),u[a]=s-1,u[s-1]=a,l=e.compute(_t(i,u),{inputs:[i],outputs:[-1]})[0]):l=i;let d=l.dims,c=d[s-1],p=r/c,h=Xe(c),m=c/h,_=64;p===1&&(_=256);let $=(z,N)=>N===4?`max(max(${z}.x, ${z}.y), max(${z}.z, ${z}.w))`:N===2?`max(${z}.x, ${z}.y)`:N===3?`max(max(${z}.x, ${z}.y), ${z}.z)`:z,y=F("x",l.dataType,l.dims,h),g=ae("result",l.dataType,l.dims,h),T=y.type.value,x=at(l.dataType)==="f32"?`var threadMax = ${T}(-3.402823e+38f);`:`var threadMax = ${T}(-65504.0h);`,E=z=>`
      var<workgroup> rowMaxShared : ${T};
      var<workgroup> rowSumShared : ${T};
      var<workgroup> threadShared : array<${T}, ${_}>;

      fn getValue(row: i32, col: i32, row_stride: i32) -> ${T} {
        let index = row * row_stride + col;
        return x[index];
      }

      fn setValue(row: i32, col: i32, row_stride: i32, value: ${T}) {
        let index = row * row_stride + col;
        result[index] = value;
      }
      ${z.registerUniform("packedCols","i32").declareVariables(y,g)}
      ${z.mainStart(_)}
        let gindex = i32(global_idx);
        let lindex = i32(local_idx);
        const wg = ${_};
        let row = gindex / wg;
        let cols = uniforms.packedCols;
        let row_stride : i32 = uniforms.packedCols;

        // find the rows max
        ${x}
        for (var col = lindex; col < cols; col += wg) {
          let value = getValue(row, col, row_stride);
          threadMax = max(threadMax, value);
        }
        if (lindex < cols) {
          threadShared[lindex] = threadMax;
        }
        workgroupBarrier();

        var reduceSize = min(cols, wg);
        for (var currSize = reduceSize >> 1;  currSize > 0; currSize = reduceSize >> 1) {
          reduceSize = currSize + (reduceSize & 1);
          if (lindex < currSize) {
            threadShared[lindex] = max(threadShared[lindex], threadShared[lindex + reduceSize]);
          }
          workgroupBarrier();
        }
        if (lindex == 0) {
          rowMaxShared = ${T}(${$("threadShared[0]",h)});
        }
        workgroupBarrier();

        // find the rows sum
        var threadSum = ${T}(0.0);
        for (var col = lindex; col < cols; col += wg) {
          let subExp = exp(getValue(row, col, row_stride) - rowMaxShared);
          threadSum += subExp;
        }
        threadShared[lindex] = threadSum;
        workgroupBarrier();

        for (var currSize = wg >> 1;  currSize > 0; currSize = currSize >> 1) {
          if (lindex < currSize) {
            threadShared[lindex] = threadShared[lindex] + threadShared[lindex + currSize];
          }
          workgroupBarrier();
        }
        if (lindex == 0) {
          rowSumShared = ${T}(${Bt("threadShared[0]",h)});
        }
        workgroupBarrier();

        // calculate final value for each element in the row
        for (var col = lindex; col < cols; col += wg) {
          var value = exp(getValue(row, col, row_stride) - rowMaxShared) / rowSumShared;
          // max operation protects against NaN since all values should be >=0
          value = max(value, ${T}(0.0));
          setValue(row, col, row_stride, value);
        }
      }`,O=e.compute({name:"Softmax",shaderCache:{hint:`${h};${_}`,inputDependencies:["type"]},getRunData:()=>({outputs:[{dims:d,dataType:l.dataType}],dispatchGroup:{x:p},programUniforms:[{type:6,data:m}]}),getShaderSource:E},{inputs:[l],outputs:[o?-1:0]})[0];o&&e.compute(_t(O,u),{inputs:[O]})},sc=(e,t)=>{nc(e.inputs),rc(e,t)},ac=e=>Be({axis:e.axis})}),$r,oc,lc,uc,dc,uf=C(()=>{me(),be(),$e(),$r=e=>Array.from(e.getBigInt64Array(),Number),oc=e=>{if(!e||e.length!==2)throw new Error("Tile requires 2 inputs.");if(e[0].dataType!==1&&e[0].dataType!==10&&e[0].dataType!==6&&e[0].dataType!==12)throw new Error("Tile only support float, float16, int32, and uint32 data types");if(e[1].dataType!==7)throw new Error("Tile `repeats` input should be of int64 data type");if(e[1].dims.length!==1)throw new Error("Tile `repeats` input should be 1-D");if($r(e[1]).length!==e[0].dims.length)throw new Error("Tile `repeats` input should have same number of elements as rank of input data tensor")},lc=(e,t)=>{let i=[];for(let n=0;n<e.length;++n)i.push(e[n]*t[n]);return i},uc=(e,t)=>{let i=e[0].dims,n=t??$r(e[1]),r=lc(i,n),s=M.size(r),a=e[0].dataType,o=F("input",a,i.length),l=ae("output",a,r.length),u=d=>`
      const inputShape = ${o.indices(...i)};
      ${d.registerUniform("output_size","u32").declareVariables(o,l)}
      ${d.mainStart()}
      ${d.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
      let output_indices = ${l.offsetToIndices("global_idx")};
      var input_indices: ${o.type.indices};
      for (var i = 0; i < ${i.length}; i++) {
        let input_dim_i = ${o.indicesGet("uniforms.input_shape","i")};
        let input_dim_value = ${l.indicesGet("output_indices","i")}  % input_dim_i;

        ${o.indicesSet("input_indices","i","input_dim_value")}
      }
      ${l.setByOffset("global_idx",o.getByIndices("input_indices"))}
    }`;return{name:"Tile",shaderCache:{hint:`${n}`,inputDependencies:["rank"]},getRunData:()=>({outputs:[{dims:r,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(s/64)},programUniforms:[{type:12,data:s},...de(e[0].dims,r)]}),getShaderSource:u}},dc=e=>{oc(e.inputs),e.compute(uc(e.inputs),{inputs:[0]})}}),cc,pc,fc,df=C(()=>{me(),be(),$e(),cc=(e,t,i,n,r)=>{let s=ae("output_data",r,i.length,4),a=F("a_data",t[1].dataType,t[1].dims.length,4),o=F("b_data",t[2].dataType,t[2].dims.length,4),l=F("c_data",t[0].dataType,t[0].dims.length,4),u,d=(c,p,h)=>`select(${p}, ${c}, ${h})`;if(!n)u=s.setByOffset("global_idx",d(a.getByOffset("global_idx"),o.getByOffset("global_idx"),l.getByOffset("global_idx")));else{let c=(p,h,m="")=>{let _=`a_data[index_a${h}][component_a${h}]`,$=`b_data[index_b${h}][component_b${h}]`,y=`bool(c_data[index_c${h}] & (0xffu << (component_c${h} * 8)))`;return`
            let output_indices${h} = ${s.offsetToIndices(`global_idx * 4u + ${h}u`)};
            let offset_a${h} = ${a.broadcastedIndicesToOffset(`output_indices${h}`,s)};
            let offset_b${h} = ${o.broadcastedIndicesToOffset(`output_indices${h}`,s)};
            let offset_c${h} = ${l.broadcastedIndicesToOffset(`output_indices${h}`,s)};
            let index_a${h} = offset_a${h} / 4u;
            let index_b${h} = offset_b${h} / 4u;
            let index_c${h} = offset_c${h} / 4u;
            let component_a${h} = offset_a${h} % 4u;
            let component_b${h} = offset_b${h} % 4u;
            let component_c${h} = offset_c${h} % 4u;
            ${p}[${h}] = ${m}(${d(_,$,y)});
          `};r===9?u=`
            var data = vec4<u32>(0);
            ${c("data",0,"u32")}
            ${c("data",1,"u32")}
            ${c("data",2,"u32")}
            ${c("data",3,"u32")}
            output_data[global_idx] = dot(vec4<u32>(0x1, 0x100, 0x10000, 0x1000000), vec4<u32>(data));`:u=`
            ${c("output_data[global_idx]",0)}
            ${c("output_data[global_idx]",1)}
            ${c("output_data[global_idx]",2)}
            ${c("output_data[global_idx]",3)}
          `}return`
        ${e.registerUniform("vec_size","u32").declareVariables(l,a,o,s)}
        ${e.mainStart()}
        ${e.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.vec_size")}
        ${u}
      }`},pc=e=>{let t=e[1].dims,i=e[2].dims,n=e[0].dims,r=e[1].dataType,s=!(M.areEqual(t,i)&&M.areEqual(i,n)),a=t,o=M.size(t);if(s){let u=ii.calcShape(ii.calcShape(t,i,!1),n,!1);if(!u)throw new Error("Can't perform where op on the given tensors");a=u,o=M.size(a)}let l=Math.ceil(o/4);return{name:"Where",shaderCache:{inputDependencies:["rank","rank","rank"]},getShaderSource:u=>cc(u,e,a,s,r),getRunData:()=>({outputs:[{dims:a,dataType:r}],dispatchGroup:{x:Math.ceil(o/64/4)},programUniforms:[{type:12,data:l},...de(n,t,i,a)]})}},fc=e=>{e.compute(pc(e.inputs))}}),hc,cf=C(()=>{Sp(),Nn(),kp(),Tp(),Cp(),Ep(),Ip(),Mp(),Bp(),Fp(),Np(),Pp(),Vp(),Lp(),Up(),qp(),Wp(),Gp(),jp(),Hp(),Kp(),Qp(),Zp(),Xp(),Yp(),Tu(),Jp(),ef(),tf(),nf(),rf(),Dn(),sf(),Bu(),af(),of(),lf(),Ru(),uf(),Ft(),Un(),df(),hc=new Map([["Abs",[Ha]],["Acos",[Ka]],["Acosh",[Qa]],["Add",[Fo]],["ArgMax",[Oa,Fn]],["ArgMin",[za,Fn]],["Asin",[Za]],["Asinh",[Xa]],["Atan",[Ya]],["Atanh",[Ja]],["Attention",[Na]],["AveragePool",[pd,cd]],["BatchNormalization",[Ua]],["BiasAdd",[Ga]],["BiasSplitGelu",[Mo]],["Cast",[to,eo]],["Ceil",[ro]],["Clip",[no]],["Concat",[Xo,Yo]],["Conv",[tr,Jn]],["ConvTranspose",[kl,$l]],["Cos",[so]],["Cosh",[ao]],["CumSum",[Cl,El]],["DepthToSpace",[Ol,Rl]],["DequantizeLinear",[vd,$d]],["Div",[No]],["Einsum",[Pl,Vl]],["Elu",[oo,hi]],["Equal",[Po]],["Erf",[lo]],["Exp",[uo]],["Expand",[Wl]],["FastGelu",[jl]],["Floor",[co]],["FusedConv",[tr,Jn]],["Gather",[Zl,Ql]],["GatherElements",[ou,au]],["GatherBlockQuantized",[iu,nu]],["GatherND",[Yl,Jl]],["Gelu",[po]],["Gemm",[cu,du]],["GlobalAveragePool",[hd,fd]],["GlobalMaxPool",[yd,_d]],["Greater",[qo]],["GreaterOrEqual",[Go]],["GridSample",[bu,vu]],["GroupQueryAttention",[Vu]],["HardSigmoid",[bo,wo]],["InstanceNormalization",[qu]],["LayerNormalization",[ju]],["LeakyRelu",[fo,hi]],["Less",[Wo]],["LessOrEqual",[jo]],["Log",[Eo]],["MatMul",[Ku]],["MatMulNBits",[Yu,Ju]],["MaxPool",[md,gd]],["Mul",[Vo]],["MultiHeadAttention",[ku,xu]],["Neg",[mo]],["Not",[ho]],["Pad",[ld]],["Pow",[Lo]],["QuickGelu",[zo,hi]],["Range",[kd]],["Reciprocal",[go]],["ReduceMin",[Ta]],["ReduceMean",[va]],["ReduceMax",[ka]],["ReduceSum",[Ea]],["ReduceProd",[Ca]],["ReduceL1",[$a]],["ReduceL2",[xa]],["ReduceLogSum",[Aa]],["ReduceLogSumExp",[Sa]],["ReduceSumSquare",[Ia]],["Relu",[_o]],["Resize",[jd,Hd]],["RotaryEmbedding",[Du]],["ScatterND",[Id,Ed]],["Sigmoid",[yo]],["Sin",[vo]],["Sinh",[$o]],["Slice",[tc,ic]],["SkipLayerNormalization",[Zd]],["Split",[zu,Ou]],["Sqrt",[xo]],["Softmax",[sc,ac]],["Sub",[Uo]],["Tan",[So]],["Tanh",[ko]],["ThresholdedRelu",[Co,hi]],["Tile",[dc]],["Transpose",[Us,qs]],["Where",[fc]]])}),mc,pf=C(()=>{yt(),zt(),$e(),mc=class{constructor(e){this.backend=e,this.repo=new Map,this.attributesBound=!1}getArtifact(e){return this.repo.get(e)}setArtifact(e,t){this.repo.set(e,t)}run(e,t,i,n,r){Pe(e.programInfo.name);let s=this.backend.device,a=this.backend.getComputePassEncoder();this.backend.writeTimestamp(this.backend.pendingDispatchNumber*2);let o=[];for(let u of t)o.push({binding:o.length,resource:{buffer:u.buffer}});for(let u of i)o.push({binding:o.length,resource:{buffer:u.buffer}});r&&o.push({binding:o.length,resource:r});let l=s.createBindGroup({layout:e.computePipeline.getBindGroupLayout(0),entries:o,label:e.programInfo.name});if(this.backend.sessionStatus==="capturing"){let u={kernelId:this.backend.currentKernelId,computePipeline:e.computePipeline,bindGroup:l,dispatchGroup:n};this.backend.capturedCommandList.get(this.backend.currentSessionId).push(u)}a.setPipeline(e.computePipeline),a.setBindGroup(0,l),a.dispatchWorkgroups(...n),this.backend.writeTimestamp(this.backend.pendingDispatchNumber*2+1),this.backend.pendingDispatchNumber++,(this.backend.pendingDispatchNumber>=this.backend.maxDispatchNumber||this.backend.queryType==="at-passes")&&this.backend.endComputePass(),this.backend.pendingDispatchNumber>=this.backend.maxDispatchNumber&&this.backend.flush(),je(e.programInfo.name)}dispose(){}build(e,t){Pe(e.name);let i=this.backend.device,n=[];[{feature:"shader-f16",extension:"f16"},{feature:"subgroups",extension:"subgroups"}].forEach(u=>{i.features.has(u.feature)&&n.push(`enable ${u.extension};`)});let r=Bs(t,this.backend.device.limits),s=e.getShaderSource(r),a=`${n.join(`
`)}
${r.additionalImplementations}
${s}`,o=i.createShaderModule({code:a,label:e.name});Ie("verbose",()=>`[WebGPU] ${e.name} shader code: ${a}`);let l=i.createComputePipeline({compute:{module:o,entryPoint:"main"},layout:"auto",label:e.name});return je(e.name),{programInfo:e,computePipeline:l,uniformVariablesInfo:r.variablesInfo}}normalizeDispatchGroupSize(e){let t=typeof e=="number"?e:e.x,i=typeof e=="number"?1:e.y||1,n=typeof e=="number"?1:e.z||1,r=this.backend.device.limits.maxComputeWorkgroupsPerDimension;if(t<=r&&i<=r&&n<=r)return[t,i,n];let s=t*i*n,a=Math.ceil(Math.sqrt(s));if(a>r){if(a=Math.ceil(Math.cbrt(s)),a>r)throw new Error("Total dispatch size exceeds WebGPU maximum.");return[a,a,a]}else return[a,a,1]}}}),gc={};Z(gc,{WebGpuBackend:()=>bc});var _c,yc,wc,bc,ff=C(()=>{yt(),me(),zt(),$s(),$p(),cf(),pf(),_c=(e,t)=>{if(t.length!==e.length)throw new Error(`inputDependencies length ${t.length} is not equal to inputTensors length ${e.length}.`);let i=[];for(let n=0;n<e.length;++n){let r=e[n].dataType;switch(t[n]){case"none":{i.push("");break}case"type":{i.push(`${r}`);break}case"rank":{let s=e[n].dims.length;i.push(`${r};${s}`);break}case"dims":{let s=e[n].dims.join(",");i.push(`${r};${s}`);break}default:throw new Error(`unsupported input dependency: ${t[n]}`)}}return i.join("|")},yc=(e,t,i)=>{let n=e.name;return e.shaderCache?.hint&&(n+="["+e.shaderCache.hint+"]"),n+=":"+i+`:${_c(t,e.shaderCache?.inputDependencies??new Array(t.length).fill("dims"))}`,n},wc=class{constructor(e){e&&(this.architecture=e.architecture,this.vendor=e.vendor)}isArchitecture(e){return this.architecture===e}isVendor(e){return this.vendor===e}},bc=class{constructor(){this.currentSessionId=null,this.currentKernelId=null,this.commandEncoder=null,this.computePassEncoder=null,this.maxDispatchNumber=16,this.pendingDispatchNumber=0,this.pendingKernels=[],this.pendingQueries=new Map,this.sessionStatus="default",this.capturedCommandList=new Map,this.capturedPendingKernels=new Map,this.sessionExternalDataMapping=new Map}get currentKernelCustomData(){if(this.currentKernelId===null)throw new Error("currentKernelCustomData(): currentKernelId is null. (should not happen)");let e=this.kernelCustomData.get(this.currentKernelId);return e||(e={},this.kernelCustomData.set(this.currentKernelId,e)),e}async initialize(e,t){this.env=e;let i=[],n={requiredLimits:{maxComputeWorkgroupStorageSize:t.limits.maxComputeWorkgroupStorageSize,maxComputeWorkgroupsPerDimension:t.limits.maxComputeWorkgroupsPerDimension,maxStorageBufferBindingSize:t.limits.maxStorageBufferBindingSize,maxBufferSize:t.limits.maxBufferSize,maxComputeInvocationsPerWorkgroup:t.limits.maxComputeInvocationsPerWorkgroup,maxComputeWorkgroupSizeX:t.limits.maxComputeWorkgroupSizeX,maxComputeWorkgroupSizeY:t.limits.maxComputeWorkgroupSizeY,maxComputeWorkgroupSizeZ:t.limits.maxComputeWorkgroupSizeZ},requiredFeatures:i},r=s=>t.features.has(s)&&i.push(s)&&!0;r("chromium-experimental-timestamp-query-inside-passes")||r("timestamp-query"),r("shader-f16"),r("subgroups"),this.device=await t.requestDevice(n),this.adapterInfo=new wc(t.info||await t.requestAdapterInfo()),this.gpuDataManager=Os(this),this.programManager=new mc(this),this.kernels=new Map,this.kernelPersistentData=new Map,this.kernelCustomData=new Map,yn(e.logLevel,!!e.debug),this.device.onuncapturederror=s=>{s.error instanceof GPUValidationError&&console.error(`An uncaught WebGPU validation error was raised: ${s.error.message}`)},Object.defineProperty(this.env.webgpu,"device",{value:this.device,writable:!1,enumerable:!0,configurable:!1}),Object.defineProperty(this.env.webgpu,"adapter",{value:t,writable:!1,enumerable:!0,configurable:!1}),this.setQueryType()}dispose(){typeof this.querySet<"u"&&this.querySet.destroy(),this.gpuDataManager.dispose()}getCommandEncoder(){return this.commandEncoder||(this.commandEncoder=this.device.createCommandEncoder()),this.commandEncoder}getComputePassEncoder(){if(!this.computePassEncoder){let e=this.getCommandEncoder(),t={};this.queryType==="at-passes"&&(t.timestampWrites={querySet:this.querySet,beginningOfPassWriteIndex:this.pendingDispatchNumber*2,endOfPassWriteIndex:this.pendingDispatchNumber*2+1}),this.computePassEncoder=e.beginComputePass(t)}return this.computePassEncoder}endComputePass(){this.computePassEncoder&&(this.computePassEncoder.end(),this.computePassEncoder=null)}flush(){if(!this.commandEncoder)return;Pe(),this.endComputePass();let e;this.queryType!=="none"&&(this.commandEncoder.resolveQuerySet(this.querySet,0,this.pendingDispatchNumber*2,this.queryResolveBuffer,0),e=this.device.createBuffer({size:this.pendingDispatchNumber*2*8,usage:GPUBufferUsage.MAP_READ|GPUBufferUsage.COPY_DST}),this.pendingQueries.set(e,this.pendingKernels),this.pendingKernels=[],this.commandEncoder.copyBufferToBuffer(this.queryResolveBuffer,0,e,0,this.pendingDispatchNumber*2*8)),this.device.queue.submit([this.commandEncoder.finish()]),this.gpuDataManager.refreshPendingBuffers(),this.commandEncoder=null,this.pendingDispatchNumber=0,this.queryType!=="none"&&e.mapAsync(GPUMapMode.READ).then(()=>{let t=new BigUint64Array(e.getMappedRange()),i=this.pendingQueries.get(e);for(let n=0;n<t.length/2;n++){let r=i[n],s=r.kernelId,a=this.kernels.get(s),o=a.kernelType,l=a.kernelName,u=r.programName,d=r.inputTensorViews,c=r.outputTensorViews,p=t[n*2],h=t[n*2+1];typeof this.queryTimeBase>"u"&&(this.queryTimeBase=p);let m=Number(p-this.queryTimeBase),_=Number(h-this.queryTimeBase);if(!Number.isSafeInteger(m)||!Number.isSafeInteger(_))throw new RangeError("incorrect timestamp range");if(this.env.webgpu.profiling?.ondata)this.env.webgpu.profiling.ondata({version:1,inputsMetadata:d.map($=>({dims:$.dims,dataType:At($.dataType)})),outputsMetadata:c.map($=>({dims:$.dims,dataType:At($.dataType)})),kernelId:s,kernelType:o,kernelName:l,programName:u,startTime:m,endTime:_});else{let $="";d.forEach((g,T)=>{$+=`input[${T}]: [${g.dims}] | ${At(g.dataType)}, `});let y="";c.forEach((g,T)=>{y+=`output[${T}]: [${g.dims}] | ${At(g.dataType)}, `}),console.log(`[profiling] kernel "${s}|${o}|${l}|${u}" ${$}${y}start time: ${m} ns, execution time: ${_-m} ns`)}Te("GPU",`${u}::${p}::${h}`)}e.unmap(),this.pendingQueries.delete(e)}),je()}run(e,t,i,n,r,s){Pe(e.name);let a=[];for(let g=0;g<t.length;++g){let T=t[g].data;if(T===0)continue;let x=this.gpuDataManager.get(T);if(!x)throw new Error(`no GPU data for input: ${T}`);a.push(x)}let{outputs:o,dispatchGroup:l,programUniforms:u}=e.getRunData(t),d=i.length===0?o.map((g,T)=>T):i;if(d.length!==o.length)throw new Error(`Output size ${d.length} must be equal to ${o.length}.`);let c=[],p=[];for(let g=0;g<o.length;++g){if(!Number.isInteger(d[g])||d[g]<-3||d[g]>=s)throw new Error(`Invalid output index: ${d[g]}`);if(d[g]===-3)continue;let T=d[g]===-1,x=d[g]===-2,E=T||x?r(o[g].dataType,o[g].dims):n(d[g],o[g].dataType,o[g].dims);if(c.push(E),E.data===0)continue;let O=this.gpuDataManager.get(E.data);if(!O)throw new Error(`no GPU data for output: ${E.data}`);if(T&&this.temporaryData.push(O),x){let z=this.kernelPersistentData.get(this.currentKernelId);z||(z=[],this.kernelPersistentData.set(this.currentKernelId,z)),z.push(O)}p.push(O)}if(a.length!==t.length||p.length!==c.length){if(p.length===0)return je(e.name),c;throw new Error(`Program ${e.name} has zero-sized tensor(s) in inputs or outputs. This is not supported now.`)}let h;if(u){let g=0,T=[];u.forEach(z=>{let N=typeof z.data=="number"?[z.data]:z.data;if(N.length===0)return;let L=z.type===10?2:4,ie,ge;z.type===10?(ge=N.length>4?16:N.length>2?8:N.length*L,ie=N.length>4?16:L*N.length):(ge=N.length<=2?N.length*L:16,ie=16),g=Math.ceil(g/ge)*ge,T.push(g);let ce=z.type===10?8:4;g+=N.length>4?Math.ceil(N.length/ce)*ie:N.length*L});let x=16;g=Math.ceil(g/x)*x;let E=new ArrayBuffer(g);u.forEach((z,N)=>{let L=T[N],ie=typeof z.data=="number"?[z.data]:z.data;if(z.type===6)new Int32Array(E,L,ie.length).set(ie);else if(z.type===12)new Uint32Array(E,L,ie.length).set(ie);else if(z.type===10)new Uint16Array(E,L,ie.length).set(ie);else if(z.type===1)new Float32Array(E,L,ie.length).set(ie);else throw new Error(`Unsupported uniform type: ${At(z.type)}`)});let O=this.gpuDataManager.create(g,GPUBufferUsage.COPY_DST|GPUBufferUsage.UNIFORM);this.device.queue.writeBuffer(O.buffer,0,E,0,g),this.gpuDataManager.release(O.id),h={offset:0,size:g,buffer:O.buffer}}let m=this.programManager.normalizeDispatchGroupSize(l),_=m[1]===1&&m[2]===1,$=yc(e,t,_),y=this.programManager.getArtifact($);if(y||(y=this.programManager.build(e,m),this.programManager.setArtifact($,y),Ie("info",()=>`[artifact] key: ${$}, programName: ${e.name}`)),u&&y.uniformVariablesInfo){if(u.length!==y.uniformVariablesInfo.length)throw new Error(`Uniform variables count mismatch: expect ${y.uniformVariablesInfo.length}, got ${u.length} in program "${y.programInfo.name}".`);for(let g=0;g<u.length;g++){let T=u[g],x=T.type,E=typeof T.data=="number"?1:T.data.length,[O,z]=y.uniformVariablesInfo[g];if(x!==O||E!==z)throw new Error(`Uniform variable ${g} mismatch: expect type ${O} with size ${z}, got type ${x} with size ${E} in program "${y.programInfo.name}".`)}}if(Ie("info",()=>`[ProgramManager] run "${e.name}" (key=${$}) with ${m[0]}x${m[1]}x${m[2]}`),this.queryType!=="none"||this.sessionStatus==="capturing"){let g={kernelId:this.currentKernelId,programName:y.programInfo.name,inputTensorViews:t,outputTensorViews:c};this.pendingKernels.push(g),this.sessionStatus==="capturing"&&this.capturedPendingKernels.get(this.currentSessionId).push(g)}return this.programManager.run(y,a,p,m,h),je(e.name),c}upload(e,t){this.gpuDataManager.upload(e,t)}memcpy(e,t){this.gpuDataManager.memcpy(e,t)}async download(e,t){await this.gpuDataManager.download(e,t)}alloc(e){return this.gpuDataManager.create(e).id}free(e){return this.gpuDataManager.release(e)}createKernel(e,t,i,n){let r=hc.get(e);if(!r)throw new Error(`kernel not implemented: ${e}`);let s={kernelType:e,kernelName:n,kernelEntry:r[0],attributes:[r[1],i]};this.kernels.set(t,s)}releaseKernel(e){let t=this.kernelPersistentData.get(e);if(t){for(let i of t)this.gpuDataManager.release(i.id);this.kernelPersistentData.delete(e)}this.kernelCustomData.delete(e),this.kernels.delete(e)}computeKernel(e,t,i){let n=this.kernels.get(e);if(!n)throw new Error(`kernel not created: ${e}`);let r=n.kernelType,s=n.kernelName,a=n.kernelEntry,o=n.attributes;if(this.currentKernelId!==null)throw new Error(`kernel "[${r}] ${s}" is not allowed to be called recursively`);this.currentKernelId=e,o[0]&&(o[1]=o[0](o[1]),o[0]=void 0),Ie("info",()=>`[WebGPU] Start to run kernel "[${r}] ${s}"...`);let l=this.env.debug;this.temporaryData=[];try{return l&&this.device.pushErrorScope("validation"),a(t,o[1]),0}catch(u){return i.push(Promise.resolve(`[WebGPU] Kernel "[${r}] ${s}" failed. ${u}`)),1}finally{l&&i.push(this.device.popErrorScope().then(u=>u?`GPU validation error for kernel "[${r}] ${s}": ${u.message}`:null));for(let u of this.temporaryData)this.gpuDataManager.release(u.id);this.temporaryData=[],this.currentKernelId=null}}registerBuffer(e,t,i,n){let r=this.sessionExternalDataMapping.get(e);r||(r=new Map,this.sessionExternalDataMapping.set(e,r));let s=r.get(t),a=this.gpuDataManager.registerExternalBuffer(i,n,s);return r.set(t,[a,i]),a}unregisterBuffers(e){let t=this.sessionExternalDataMapping.get(e);t&&(t.forEach(i=>this.gpuDataManager.unregisterExternalBuffer(i[0])),this.sessionExternalDataMapping.delete(e))}getBuffer(e){let t=this.gpuDataManager.get(e);if(!t)throw new Error(`no GPU data for buffer: ${e}`);return t.buffer}createDownloader(e,t,i){return async()=>{let n=await An(this,e,t);return wn(n.buffer,i)}}writeTimestamp(e){this.queryType==="inside-passes"&&this.computePassEncoder.writeTimestamp(this.querySet,e)}setQueryType(){this.queryType="none",(this.env.webgpu.profiling?.mode==="default"||(typeof this.env.trace>"u"?this.env.wasm.trace:this.env.trace))&&(this.device.features.has("chromium-experimental-timestamp-query-inside-passes")?this.queryType="inside-passes":this.device.features.has("timestamp-query")&&(this.queryType="at-passes"),this.queryType!=="none"&&typeof this.querySet>"u"&&(this.querySet=this.device.createQuerySet({type:"timestamp",count:this.maxDispatchNumber*2}),this.queryResolveBuffer=this.device.createBuffer({size:this.maxDispatchNumber*2*8,usage:GPUBufferUsage.COPY_SRC|GPUBufferUsage.QUERY_RESOLVE})))}captureBegin(){Ie("info","captureBegin"),this.capturedCommandList.get(this.currentSessionId)||this.capturedCommandList.set(this.currentSessionId,[]),this.capturedPendingKernels.get(this.currentSessionId)||this.capturedPendingKernels.set(this.currentSessionId,[]),this.flush(),this.sessionStatus="capturing"}captureEnd(){Ie("info","captureEnd"),this.flush(),this.sessionStatus="default"}replay(){Ie("info","replay"),this.sessionStatus="replaying";let e=this.capturedCommandList.get(this.currentSessionId),t=this.capturedPendingKernels.get(this.currentSessionId),i=e.length;this.pendingKernels=[];for(let n=0;n<i;n++){let r=this.getComputePassEncoder(),s=e[n];this.writeTimestamp(this.pendingDispatchNumber*2),r.setPipeline(s.computePipeline),r.setBindGroup(0,s.bindGroup),r.dispatchWorkgroups(...s.dispatchGroup),this.writeTimestamp(this.pendingDispatchNumber*2+1),this.pendingDispatchNumber++,this.queryType!=="none"&&this.pendingKernels.push(t[n]),(this.pendingDispatchNumber>=this.maxDispatchNumber||this.queryType==="at-passes")&&this.endComputePass(),this.pendingDispatchNumber>=this.maxDispatchNumber&&this.flush()}this.flush(),this.sessionStatus="default"}onCreateSession(){this.gpuDataManager.onCreateSession()}onReleaseSession(e){this.unregisterBuffers(e),this.capturedCommandList.has(e)&&this.capturedCommandList.delete(e),this.capturedPendingKernels.has(e)&&this.capturedPendingKernels.delete(e),this.gpuDataManager.onReleaseSession(e)}onRunStart(e){this.currentSessionId=e,this.setQueryType()}}}),vc={};Z(vc,{init:()=>xc});var Gi,$c,xc,hf=C(()=>{me(),zt(),be(),vp(),Gi=class rp{constructor(t,i,n,r){this.module=t,this.dataType=i,this.data=n,this.dims=r}getFloat32Array(){if(this.dataType!==1)throw new Error("Invalid data type");let t=M.size(this.dims);return t===0?new Float32Array:new Float32Array(this.module.HEAP8.buffer,this.data,t)}getBigInt64Array(){if(this.dataType!==7)throw new Error("Invalid data type");let t=M.size(this.dims);return t===0?new BigInt64Array:new BigInt64Array(this.module.HEAP8.buffer,this.data,t)}getInt32Array(){if(this.dataType!==6)throw new Error("Invalid data type");let t=M.size(this.dims);return t===0?new Int32Array:new Int32Array(this.module.HEAP8.buffer,this.data,t)}getUint16Array(){if(this.dataType!==10&&this.dataType!==4)throw new Error("Invalid data type");let t=M.size(this.dims);return t===0?new Uint16Array:new Uint16Array(this.module.HEAP8.buffer,this.data,t)}reshape(t){if(M.size(t)!==M.size(this.dims))throw new Error("Invalid new shape");return new rp(this.module,this.dataType,this.data,t)}},$c=class{constructor(e,t,i){this.module=e,this.backend=t,this.customDataOffset=0,this.customDataSize=0,this.adapterInfo=t.adapterInfo;let n=e.PTR_SIZE,r=i/e.PTR_SIZE,s=n===4?"i32":"i64";this.opKernelContext=Number(e.getValue(n*r++,s));let a=Number(e.getValue(n*r++,s));this.outputCount=Number(e.getValue(n*r++,s)),this.customDataOffset=Number(e.getValue(n*r++,"*")),this.customDataSize=Number(e.getValue(n*r++,s));let o=[];for(let l=0;l<a;l++){let u=Number(e.getValue(n*r++,s)),d=Number(e.getValue(n*r++,"*")),c=Number(e.getValue(n*r++,s)),p=[];for(let h=0;h<c;h++)p.push(Number(e.getValue(n*r++,s)));o.push(new Gi(e,u,d,p))}this.inputs=o}get kernelCustomData(){return this.backend.currentKernelCustomData}get customDataBuffer(){return this.module.HEAPU8.subarray(this.customDataOffset,this.customDataOffset+this.customDataSize)}compute(e,t){let i=t?.inputs?.map(a=>typeof a=="number"?this.inputs[a]:a)??this.inputs,n=t?.outputs??[],r=(a,o,l)=>new Gi(this.module,o,this.output(a,l),l),s=(a,o)=>{let l=qt(a,o);if(!l)throw new Error(`Unsupported data type: ${a}`);let u=l>0?this.backend.gpuDataManager.create(l).id:0;return new Gi(this.module,a,u,o)};return this.backend.run(e,i,n,r,s,this.outputCount)}output(e,t){let i=this.module.stackSave();try{let n=this.module.PTR_SIZE,r=n===4?"i32":"i64",s=this.module.stackAlloc((1+t.length)*n);this.module.setValue(s,t.length,r);for(let a=0;a<t.length;a++)this.module.setValue(s+n*(a+1),t[a],r);return this.module._JsepOutput(this.opKernelContext,e,s)}catch(n){throw new Error(`Failed to generate kernel's output[${e}] with dims [${t}]. If you are running with pre-allocated output, please make sure the output type/dims are correct. Error: ${n}`)}finally{this.module.stackRestore(i)}}},xc=async(e,t,i,n)=>{let r=t.jsepInit;if(!r)throw new Error("Failed to initialize JSEP. The WebAssembly module is not built with JSEP support.");if(e==="webgpu"){let s=(ff(),H(gc)).WebGpuBackend,a=new s;await a.initialize(i,n),r("webgpu",[a,o=>a.alloc(Number(o)),o=>a.free(o),(o,l,u,d=!1)=>{if(d)Ie("verbose",()=>`[WebGPU] jsepCopyGpuToGpu: src=${Number(o)}, dst=${Number(l)}, size=${Number(u)}`),a.memcpy(Number(o),Number(l));else{Ie("verbose",()=>`[WebGPU] jsepCopyCpuToGpu: dataOffset=${Number(o)}, gpuDataId=${Number(l)}, size=${Number(u)}`);let c=t.HEAPU8.subarray(Number(o>>>0),Number(o>>>0)+Number(u));a.upload(Number(l),c)}},async(o,l,u)=>{Ie("verbose",()=>`[WebGPU] jsepCopyGpuToCpu: gpuDataId=${o}, dataOffset=${l}, size=${u}`),await a.download(Number(o),()=>t.HEAPU8.subarray(Number(l)>>>0,Number(l+u)>>>0))},(o,l,u)=>a.createKernel(o,Number(l),u,t.UTF8ToString(t._JsepGetNodeName(Number(l)))),o=>a.releaseKernel(o),(o,l,u,d)=>{Ie("verbose",()=>`[WebGPU] jsepRun: sessionHandle=${u}, kernel=${o}, contextDataOffset=${l}`);let c=new $c(t,a,Number(l));return a.computeKernel(Number(o),c,d)},()=>a.captureBegin(),()=>a.captureEnd(),()=>a.replay()])}else{let s=new Es(i);r("webnn",[s,()=>s.reserveTensorId(),a=>s.releaseTensorId(a),async(a,o,l,u,d)=>s.ensureTensor(a,o,l,u,d),(a,o)=>{s.uploadTensor(a,o)},async(a,o)=>s.downloadTensor(a,o),(a,o)=>s.registerMLContext(a,o),!!i.trace])}}}),Sc,xr,Sr,Nt,kc,kr,ji,Tr,Cr,Er,Ir,Ar,zr,Tc=C(()=>{yt(),yp(),wp(),me(),Lt(),fn(),ps(),Sc=(e,t)=>{Ge()._OrtInit(e,t)!==0&&Ve("Can't initialize onnxruntime.")},xr=async e=>{Sc(e.wasm.numThreads,Oi(e.logLevel))},Sr=async(e,t)=>{Ge().asyncInit?.();let i=e.webgpu.adapter;if(t==="webgpu"){if(typeof navigator>"u"||!navigator.gpu)throw new Error("WebGPU is not supported in current environment");if(i){if(typeof i.limits!="object"||typeof i.features!="object"||typeof i.requestDevice!="function")throw new Error("Invalid GPU adapter set in `env.webgpu.adapter`. It must be a GPUAdapter object.")}else{let n=e.webgpu.powerPreference;if(n!==void 0&&n!=="low-power"&&n!=="high-performance")throw new Error(`Invalid powerPreference setting: "${n}"`);let r=e.webgpu.forceFallbackAdapter;if(r!==void 0&&typeof r!="boolean")throw new Error(`Invalid forceFallbackAdapter setting: "${r}"`);if(i=await navigator.gpu.requestAdapter({powerPreference:n,forceFallbackAdapter:r}),!i)throw new Error('Failed to get GPU adapter. You may need to enable flag "--enable-unsafe-webgpu" if you are using Chrome.')}}if(t==="webnn"&&(typeof navigator>"u"||!navigator.ml))throw new Error("WebNN is not supported in current environment");{let n=(hf(),H(vc)).init;t==="webgpu"&&await n("webgpu",Ge(),e,i),t==="webnn"&&await n("webnn",Ge(),e)}},Nt=new Map,kc=e=>{let t=Ge(),i=t.stackSave();try{let n=t.PTR_SIZE,r=t.stackAlloc(2*n);t._OrtGetInputOutputCount(e,r,r+n)!==0&&Ve("Can't get session input/output count.");let s=n===4?"i32":"i64";return[Number(t.getValue(r,s)),Number(t.getValue(r+n,s))]}finally{t.stackRestore(i)}},kr=(e,t)=>{let i=Ge(),n=i.stackSave(),r=0;try{let s=i.PTR_SIZE,a=i.stackAlloc(2*s);i._OrtGetInputOutputMetadata(e,t,a,a+s)!==0&&Ve("Can't get session input/output metadata.");let o=Number(i.getValue(a,"*"));r=Number(i.getValue(a+s,"*"));let l=i.HEAP32[r/4];if(l===0)return[o,0];let u=i.HEAPU32[r/4+1],d=[];for(let c=0;c<u;c++){let p=Number(i.getValue(r+8+c*s,"*"));d.push(p!==0?i.UTF8ToString(p):Number(i.getValue(r+8+(c+u)*s,"*")))}return[o,l,d]}finally{i.stackRestore(n),r!==0&&i._OrtFree(r)}},ji=e=>{let t=Ge(),i=t._malloc(e.byteLength);if(i===0)throw new Error(`Can't create a session. failed to allocate a buffer of size ${e.byteLength}.`);return t.HEAPU8.set(e,i),[i,e.byteLength]},Tr=async(e,t)=>{let i,n,r=Ge();Array.isArray(e)?[i,n]=e:e.buffer===r.HEAPU8.buffer?[i,n]=[e.byteOffset,e.byteLength]:[i,n]=ji(e);let s=0,a=0,o=0,l=[],u=[],d=[];try{if([a,l]=await cs(t),t?.externalData&&r.mountExternalData){let x=[];for(let E of t.externalData){let O=typeof E=="string"?E:E.path;x.push(_n(typeof E=="string"?E:E.data).then(z=>{r.mountExternalData(O,z)}))}await Promise.all(x)}for(let x of t?.executionProviders??[])if((typeof x=="string"?x:x.name)==="webnn"){if(r.shouldTransferToMLTensor=!1,typeof x!="string"){let E=x,O=E?.context,z=E?.gpuDevice,N=E?.deviceType,L=E?.powerPreference;O?r.currentContext=O:z?r.currentContext=await r.webnnCreateMLContext(z):r.currentContext=await r.webnnCreateMLContext({deviceType:N,powerPreference:L})}else r.currentContext=await r.webnnCreateMLContext();break}s=await r._OrtCreateSession(i,n,a),r.webgpuOnCreateSession?.(s),s===0&&Ve("Can't create a session."),r.jsepOnCreateSession?.(),r.currentContext&&(r.webnnRegisterMLContext(s,r.currentContext),r.currentContext=void 0,r.shouldTransferToMLTensor=!0);let[c,p]=kc(s),h=!!t?.enableGraphCapture,m=[],_=[],$=[],y=[],g=[];for(let x=0;x<c;x++){let[E,O,z]=kr(s,x);E===0&&Ve("Can't get an input name."),u.push(E);let N=r.UTF8ToString(E);m.push(N),$.push(O===0?{name:N,isTensor:!1}:{name:N,isTensor:!0,type:At(O),shape:z})}for(let x=0;x<p;x++){let[E,O,z]=kr(s,x+c);E===0&&Ve("Can't get an output name."),d.push(E);let N=r.UTF8ToString(E);_.push(N),y.push(O===0?{name:N,isTensor:!1}:{name:N,isTensor:!0,type:At(O),shape:z});{if(h&&t?.preferredOutputLocation===void 0){g.push("gpu-buffer");continue}let L=typeof t?.preferredOutputLocation=="string"?t.preferredOutputLocation:t?.preferredOutputLocation?.[N]??"cpu",ie=r.webnnIsGraphOutput;if(L==="cpu"&&ie&&ie(s,N)){g.push("ml-tensor-cpu-output");continue}if(L!=="cpu"&&L!=="cpu-pinned"&&L!=="gpu-buffer"&&L!=="ml-tensor")throw new Error(`Not supported preferred output location: ${L}.`);if(h&&L!=="gpu-buffer")throw new Error(`Not supported preferred output location: ${L}. Only 'gpu-buffer' location is supported when enableGraphCapture is true.`);g.push(L)}}let T=null;return g.some(x=>x==="gpu-buffer"||x==="ml-tensor"||x==="ml-tensor-cpu-output")&&(o=r._OrtCreateBinding(s),o===0&&Ve("Can't create IO binding."),T={handle:o,outputPreferredLocations:g,outputPreferredLocationsEncoded:g.map(x=>x==="ml-tensor-cpu-output"?"ml-tensor":x).map(x=>gn(x))}),Nt.set(s,[s,u,d,T,h,!1]),[s,m,_,$,y]}catch(c){throw u.forEach(p=>r._OrtFree(p)),d.forEach(p=>r._OrtFree(p)),o!==0&&r._OrtReleaseBinding(o)!==0&&Ve("Can't release IO binding."),s!==0&&r._OrtReleaseSession(s)!==0&&Ve("Can't release session."),c}finally{r._free(i),a!==0&&r._OrtReleaseSessionOptions(a)!==0&&Ve("Can't release session options."),l.forEach(c=>r._free(c)),r.unmountExternalData?.()}},Cr=e=>{let t=Ge(),i=Nt.get(e);if(!i)throw new Error(`cannot release session. invalid session id: ${e}`);let[n,r,s,a,o]=i;a&&(o&&t._OrtClearBoundOutputs(a.handle)!==0&&Ve("Can't clear bound outputs."),t._OrtReleaseBinding(a.handle)!==0&&Ve("Can't release IO binding.")),t.jsepOnReleaseSession?.(e),t.webnnOnReleaseSession?.(e),t.webgpuOnReleaseSession?.(e),r.forEach(l=>t._OrtFree(l)),s.forEach(l=>t._OrtFree(l)),t._OrtReleaseSession(n)!==0&&Ve("Can't release session."),Nt.delete(e)},Er=async(e,t,i,n,r,s,a=!1)=>{if(!e){t.push(0);return}let o=Ge(),l=o.PTR_SIZE,u=e[0],d=e[1],c=e[3],p=c,h,m;if(u==="string"&&(c==="gpu-buffer"||c==="ml-tensor"))throw new Error("String tensor is not supported on GPU.");if(a&&c!=="gpu-buffer")throw new Error(`External buffer must be provided for input/output index ${s} when enableGraphCapture is true.`);if(c==="gpu-buffer"){let y=e[2].gpuBuffer;m=qt(Ut(u),d);{let g=o.jsepRegisterBuffer;if(!g)throw new Error('Tensor location "gpu-buffer" is not supported without using WebGPU.');h=g(n,s,y,m)}}else if(c==="ml-tensor"){let y=e[2].mlTensor;m=qt(Ut(u),d);let g=o.webnnRegisterMLTensor;if(!g)throw new Error('Tensor location "ml-tensor" is not supported without using WebNN.');h=g(n,y,Ut(u),d)}else{let y=e[2];if(Array.isArray(y)){m=l*y.length,h=o._malloc(m),i.push(h);for(let g=0;g<y.length;g++){if(typeof y[g]!="string")throw new TypeError(`tensor data at index ${g} is not a string`);o.setValue(h+g*l,bt(y[g],i),"*")}}else{let g=o.webnnIsGraphInput,T=o.webnnIsGraphOutput;if(u!=="string"&&g&&T){let x=o.UTF8ToString(r);if(g(n,x)||T(n,x)){let E=Ut(u);m=qt(E,d),p="ml-tensor";let O=o.webnnCreateTemporaryTensor,z=o.webnnUploadTensor;if(!O||!z)throw new Error('Tensor location "ml-tensor" is not supported without using WebNN.');let N=await O(n,E,d);z(N,new Uint8Array(y.buffer,y.byteOffset,y.byteLength)),h=N}else m=y.byteLength,h=o._malloc(m),i.push(h),o.HEAPU8.set(new Uint8Array(y.buffer,y.byteOffset,m),h)}else m=y.byteLength,h=o._malloc(m),i.push(h),o.HEAPU8.set(new Uint8Array(y.buffer,y.byteOffset,m),h)}}let _=o.stackSave(),$=o.stackAlloc(4*d.length);try{d.forEach((g,T)=>o.setValue($+T*l,g,l===4?"i32":"i64"));let y=o._OrtCreateTensor(Ut(u),h,m,$,d.length,gn(p));y===0&&Ve(`Can't create tensor for input/output. session=${n}, index=${s}.`),t.push(y)}finally{o.stackRestore(_)}},Ir=async(e,t,i,n,r,s)=>{let a=Ge(),o=a.PTR_SIZE,l=Nt.get(e);if(!l)throw new Error(`cannot run inference. invalid session id: ${e}`);let u=l[0],d=l[1],c=l[2],p=l[3],h=l[4],m=l[5],_=t.length,$=n.length,y=0,g=[],T=[],x=[],E=[],O=a.stackSave(),z=a.stackAlloc(_*o),N=a.stackAlloc(_*o),L=a.stackAlloc($*o),ie=a.stackAlloc($*o);try{[y,g]=as(s),mt("wasm prepareInputOutputTensor");for(let re=0;re<_;re++)await Er(i[re],T,E,e,d[t[re]],t[re],h);for(let re=0;re<$;re++)await Er(r[re],x,E,e,c[n[re]],_+n[re],h);se("wasm prepareInputOutputTensor");for(let re=0;re<_;re++)a.setValue(z+re*o,T[re],"*"),a.setValue(N+re*o,d[t[re]],"*");for(let re=0;re<$;re++)a.setValue(L+re*o,x[re],"*"),a.setValue(ie+re*o,c[n[re]],"*");if(p&&!m){let{handle:re,outputPreferredLocations:ke,outputPreferredLocationsEncoded:he}=p;if(d.length!==_)throw new Error(`input count from feeds (${_}) is expected to be always equal to model's input count (${d.length}).`);mt("wasm bindInputsOutputs");for(let le=0;le<_;le++){let Re=t[le];await a._OrtBindInput(re,d[Re],T[le])!==0&&Ve(`Can't bind input[${le}] for session=${e}.`)}for(let le=0;le<$;le++){let Re=n[le];r[le]?.[3]?a._OrtBindOutput(re,c[Re],x[le],0)!==0&&Ve(`Can't bind pre-allocated output[${le}] for session=${e}.`):a._OrtBindOutput(re,c[Re],0,he[Re])!==0&&Ve(`Can't bind output[${le}] to ${ke[le]} for session=${e}.`)}se("wasm bindInputsOutputs"),Nt.set(e,[u,d,c,p,h,!0])}a.jsepOnRunStart?.(u),a.webnnOnRunStart?.(u);let ge;p?ge=await a._OrtRunWithBinding(u,p.handle,$,L,y):ge=await a._OrtRun(u,N,z,_,ie,$,L,y),ge!==0&&Ve("failed to call OrtRun().");let ce=[],we=[];mt("wasm ProcessOutputTensor");for(let re=0;re<$;re++){let ke=Number(a.getValue(L+re*o,"*"));if(ke===x[re]){ce.push(r[re]);continue}let he=a.stackSave(),le=a.stackAlloc(4*o),Re=!1,pe,He=0;try{a._OrtGetTensorData(ke,le,le+o,le+2*o,le+3*o)!==0&&Ve(`Can't access output tensor data on index ${re}.`);let U=o===4?"i32":"i64",te=Number(a.getValue(le,U));He=a.getValue(le+o,"*");let xe=a.getValue(le+o*2,"*"),Le=Number(a.getValue(le+o*3,U)),lt=[];for(let ut=0;ut<Le;ut++)lt.push(Number(a.getValue(xe+ut*o,U)));a._OrtFree(xe)!==0&&Ve("Can't free memory for tensor dims.");let Ct=lt.reduce((ut,nt)=>ut*nt,1);pe=At(te);let xi=p?.outputPreferredLocations[n[re]];if(pe==="string"){if(xi==="gpu-buffer"||xi==="ml-tensor")throw new Error("String tensor is not supported on GPU.");let ut=[];for(let nt=0;nt<Ct;nt++){let Rt=a.getValue(He+nt*o,"*"),wf=a.getValue(He+(nt+1)*o,"*"),bf=nt===Ct-1?void 0:wf-Rt;ut.push(a.UTF8ToString(Rt,bf))}ce.push([pe,lt,ut,"cpu"])}else if(xi==="gpu-buffer"&&Ct>0){let ut=a.jsepGetBuffer;if(!ut)throw new Error('preferredLocation "gpu-buffer" is not supported without using WebGPU.');let nt=ut(He),Rt=qt(te,Ct);if(Rt===void 0||!hn(pe))throw new Error(`Unsupported data type: ${pe}`);Re=!0,ce.push([pe,lt,{gpuBuffer:nt,download:a.jsepCreateDownloader(nt,Rt,pe),dispose:()=>{a._OrtReleaseTensor(ke)!==0&&Ve("Can't release tensor.")}},"gpu-buffer"])}else if(xi==="ml-tensor"&&Ct>0){let ut=a.webnnEnsureTensor,nt=a.webnnIsGraphInputOutputTypeSupported;if(!ut||!nt)throw new Error('preferredLocation "ml-tensor" is not supported without using WebNN.');if(qt(te,Ct)===void 0||!mn(pe))throw new Error(`Unsupported data type: ${pe}`);if(!nt(e,pe,!1))throw new Error(`preferredLocation "ml-tensor" for ${pe} output is not supported by current WebNN Context.`);let Rt=await ut(e,He,te,lt,!1);Re=!0,ce.push([pe,lt,{mlTensor:Rt,download:a.webnnCreateMLTensorDownloader(He,pe),dispose:()=>{a.webnnReleaseTensorId(He),a._OrtReleaseTensor(ke)}},"ml-tensor"])}else if(xi==="ml-tensor-cpu-output"&&Ct>0){let ut=a.webnnCreateMLTensorDownloader(He,pe)(),nt=ce.length;Re=!0,we.push((async()=>{let Rt=[nt,await ut];return a.webnnReleaseTensorId(He),a._OrtReleaseTensor(ke),Rt})()),ce.push([pe,lt,[],"cpu"])}else{let ut=zi(pe),nt=new ut(Ct);new Uint8Array(nt.buffer,nt.byteOffset,nt.byteLength).set(a.HEAPU8.subarray(He,He+nt.byteLength)),ce.push([pe,lt,nt,"cpu"])}}finally{a.stackRestore(he),pe==="string"&&He&&a._free(He),Re||a._OrtReleaseTensor(ke)}}p&&!h&&(a._OrtClearBoundOutputs(p.handle)!==0&&Ve("Can't clear bound outputs."),Nt.set(e,[u,d,c,p,h,!1]));for(let[re,ke]of await Promise.all(we))ce[re][2]=ke;return se("wasm ProcessOutputTensor"),ce}finally{a.webnnOnRunEnd?.(u),a.stackRestore(O),T.forEach(ge=>a._OrtReleaseTensor(ge)),x.forEach(ge=>a._OrtReleaseTensor(ge)),E.forEach(ge=>a._free(ge)),y!==0&&a._OrtReleaseRunOptions(y),g.forEach(ge=>a._free(ge))}},Ar=e=>{let t=Ge(),i=Nt.get(e);if(!i)throw new Error("invalid session id");let n=i[0],r=t._OrtEndProfiling(n);r===0&&Ve("Can't get an profile file name."),t._OrtFree(r)},zr=e=>{let t=[];for(let i of e){let n=i[2];!Array.isArray(n)&&"buffer"in n&&t.push(n.buffer)}return t}}),Pt,wt,si,vi,$i,Hi,Or,Ki,Zt,Xt,Cc,Ec,Ic,Ac,zc,Oc,Rc,Mc,Dc=C(()=>{yt(),Tc(),Lt(),un(),Pt=()=>!!ne.wasm.proxy&&typeof document<"u",si=!1,vi=!1,$i=!1,Ki=new Map,Zt=(e,t)=>{let i=Ki.get(e);i?i.push(t):Ki.set(e,[t])},Xt=()=>{if(si||!vi||$i||!wt)throw new Error("worker not ready")},Cc=e=>{switch(e.data.type){case"init-wasm":si=!1,e.data.err?($i=!0,Or[1](e.data.err)):(vi=!0,Or[0]()),Hi&&(URL.revokeObjectURL(Hi),Hi=void 0);break;case"init-ep":case"copy-from":case"create":case"release":case"run":case"end-profiling":{let t=Ki.get(e.data.type);e.data.err?t.shift()[1](e.data.err):t.shift()[0](e.data.out);break}}},Ec=async()=>{if(!vi){if(si)throw new Error("multiple calls to 'initWasm()' detected.");if($i)throw new Error("previous call to 'initWasm()' failed.");if(si=!0,Pt())return new Promise((e,t)=>{wt?.terminate(),ts().then(([i,n])=>{try{wt=n,wt.onerror=s=>t(s),wt.onmessage=Cc,Or=[e,t];let r={type:"init-wasm",in:ne};if(!r.in.wasm.wasmPaths&&i){let s=sn();s&&(r.in.wasm.wasmPaths=s)}wt.postMessage(r),Hi=i}catch(r){t(r)}},t)});try{await pn(ne.wasm),await xr(ne),vi=!0}catch(e){throw $i=!0,e}finally{si=!1}}},Ic=async e=>{if(Pt())return Xt(),new Promise((t,i)=>{Zt("init-ep",[t,i]);let n={type:"init-ep",in:{epName:e,env:ne}};wt.postMessage(n)});await Sr(ne,e)},Ac=async e=>Pt()?(Xt(),new Promise((t,i)=>{Zt("copy-from",[t,i]);let n={type:"copy-from",in:{buffer:e}};wt.postMessage(n,[e.buffer])})):ji(e),zc=async(e,t)=>{if(Pt()){if(t?.preferredOutputLocation)throw new Error('session option "preferredOutputLocation" is not supported for proxy.');return Xt(),new Promise((i,n)=>{Zt("create",[i,n]);let r={type:"create",in:{model:e,options:{...t}}},s=[];e instanceof Uint8Array&&s.push(e.buffer),wt.postMessage(r,s)})}else return Tr(e,t)},Oc=async e=>{if(Pt())return Xt(),new Promise((t,i)=>{Zt("release",[t,i]);let n={type:"release",in:e};wt.postMessage(n)});Cr(e)},Rc=async(e,t,i,n,r,s)=>{if(Pt()){if(i.some(a=>a[3]!=="cpu"))throw new Error("input tensor on GPU is not supported for proxy.");if(r.some(a=>a))throw new Error("pre-allocated output tensor is not supported for proxy.");return Xt(),new Promise((a,o)=>{Zt("run",[a,o]);let l=i,u={type:"run",in:{sessionId:e,inputIndices:t,inputs:l,outputIndices:n,options:s}};wt.postMessage(u,zr(l))})}else return Ir(e,t,i,n,r,s)},Mc=async e=>{if(Pt())return Xt(),new Promise((t,i)=>{Zt("end-profiling",[t,i]);let n={type:"end-profiling",in:e};wt.postMessage(n)});Ar(e)}}),Rr,Bc,Fc,mf=C(()=>{yt(),Dc(),me(),tn(),ps(),Rr=(e,t)=>{switch(e.location){case"cpu":return[e.type,e.dims,e.data,"cpu"];case"gpu-buffer":return[e.type,e.dims,{gpuBuffer:e.gpuBuffer},"gpu-buffer"];case"ml-tensor":return[e.type,e.dims,{mlTensor:e.mlTensor},"ml-tensor"];default:throw new Error(`invalid data location: ${e.location} for ${t()}`)}},Bc=e=>{switch(e[3]){case"cpu":return new pt(e[0],e[2],e[1]);case"gpu-buffer":{let t=e[0];if(!hn(t))throw new Error(`not supported data type: ${t} for deserializing GPU tensor`);let{gpuBuffer:i,download:n,dispose:r}=e[2];return pt.fromGpuBuffer(i,{dataType:t,dims:e[1],download:n,dispose:r})}case"ml-tensor":{let t=e[0];if(!mn(t))throw new Error(`not supported data type: ${t} for deserializing MLTensor tensor`);let{mlTensor:i,download:n,dispose:r}=e[2];return pt.fromMLTensor(i,{dataType:t,dims:e[1],download:n,dispose:r})}default:throw new Error(`invalid data location: ${e[3]}`)}},Fc=class{async fetchModelAndCopyToWasmMemory(e){return Ac(await _n(e))}async loadModel(e,t){Pe();let i;typeof e=="string"?i=await this.fetchModelAndCopyToWasmMemory(e):i=e,[this.sessionId,this.inputNames,this.outputNames,this.inputMetadata,this.outputMetadata]=await zc(i,t),je()}async dispose(){return Oc(this.sessionId)}async run(e,t,i){Pe();let n=[],r=[];Object.entries(e).forEach(c=>{let p=c[0],h=c[1],m=this.inputNames.indexOf(p);if(m===-1)throw new Error(`invalid input '${p}'`);n.push(h),r.push(m)});let s=[],a=[];Object.entries(t).forEach(c=>{let p=c[0],h=c[1],m=this.outputNames.indexOf(p);if(m===-1)throw new Error(`invalid output '${p}'`);s.push(h),a.push(m)});let o=n.map((c,p)=>Rr(c,()=>`input "${this.inputNames[r[p]]}"`)),l=s.map((c,p)=>c?Rr(c,()=>`output "${this.outputNames[a[p]]}"`):null),u=await Rc(this.sessionId,r,o,a,l,i),d={};for(let c=0;c<u.length;c++)d[this.outputNames[a[c]]]=s[c]??Bc(u[c]);return je(),d}startProfiling(){}endProfiling(){Mc(this.sessionId)}}}),Nc={};Z(Nc,{OnnxruntimeWebAssemblyBackend:()=>Dr,initializeFlags:()=>Mr,wasmBackend:()=>Pc});var Mr,Dr,Pc,gf=C(()=>{yt(),Dc(),mf(),Mr=()=>{(typeof ne.wasm.initTimeout!="number"||ne.wasm.initTimeout<0)&&(ne.wasm.initTimeout=0);let e=ne.wasm.simd;if(typeof e!="boolean"&&e!==void 0&&e!=="fixed"&&e!=="relaxed"&&(console.warn(`Property "env.wasm.simd" is set to unknown value "${e}". Reset it to \`false\` and ignore SIMD feature checking.`),ne.wasm.simd=!1),typeof ne.wasm.proxy!="boolean"&&(ne.wasm.proxy=!1),typeof ne.wasm.trace!="boolean"&&(ne.wasm.trace=!1),typeof ne.wasm.numThreads!="number"||!Number.isInteger(ne.wasm.numThreads)||ne.wasm.numThreads<=0)if(typeof self<"u"&&!self.crossOriginIsolated)ne.wasm.numThreads=1;else{let t=typeof navigator>"u"?A("node:os").cpus().length:navigator.hardwareConcurrency;ne.wasm.numThreads=Math.min(4,Math.ceil((t||1)/2))}},Dr=class{async init(e){Mr(),await Ec(),await Ic(e)}async createInferenceSessionHandler(e,t){let i=new Fc;return await i.loadModel(e,t),i}},Pc=new Dr}),Vc={};Z(Vc,{InferenceSession:()=>We,TRACE:()=>Te,TRACE_EVENT_BEGIN:()=>mt,TRACE_EVENT_END:()=>se,TRACE_FUNC_BEGIN:()=>Pe,TRACE_FUNC_END:()=>je,Tensor:()=>pt,default:()=>yf,env:()=>ne,registerBackend:()=>P}),yt(),yt(),yt();var _f="1.23.0",yf=Hr;{let e=(gf(),H(Nc)).wasmBackend;P("webgpu",e,5),P("webnn",e,5),P("cpu",e,10),P("wasm",e,10)}return Object.defineProperty(ne.versions,"web",{value:_f,enumerable:!0}),H(Vc)})();/**
 * @license
 * Copyright 2021 Google LLC. All Rights Reserved.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * =============================================================================
 *//**
 * @license
 * Copyright 2020 Google LLC. All Rights Reserved.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * =============================================================================
 *//**
 * @license
 * Copyright 2019 Google LLC. All Rights Reserved.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 * =============================================================================
 */S.exports=b})(ip);var sp=ip.exports,Wr={},ap={};Object.defineProperty(ap,"__esModule",{value:!0});var Ji={},op;Object.defineProperty(Ji,"__esModule",{value:!0});Ji.SileroLegacy=void 0;const Qc=li;class Gr{constructor(f,b,v,k,w){this.ortInstance=f,this._session=b,this._h=v,this._c=k,this._sr=w,this.reset_state=()=>{const I=Array(128).fill(0);this._h=new this.ortInstance.Tensor("float32",I,[2,1,64]),this._c=new this.ortInstance.Tensor("float32",I,[2,1,64])},this.process=async I=>{const C={input:new this.ortInstance.Tensor("float32",I,[1,I.length]),h:this._h,c:this._c,sr:this._sr},Z=await this._session.run(C);this._h=Z.hn,this._c=Z.cn;const[W]=Z.output?.data;return{notSpeech:1-W,isSpeech:W}}}}Ji.SileroLegacy=Gr;op=Gr;Gr.new=async(S,f)=>{Qc.log.debug("initializing vad");const b=await f(),v=await S.InferenceSession.create(b),k=new S.Tensor("int64",[16000n]),w=Array(2*64).fill(0),I=new S.Tensor("float32",w,[2,1,64]),A=new S.Tensor("float32",w,[2,1,64]);return Qc.log.debug("vad is initialized"),new op(S,v,I,A,k)};var en={},lp;Object.defineProperty(en,"__esModule",{value:!0});en.SileroV5=void 0;const Zc=li;function up(S){const f=Array(256).fill(0);return new S.Tensor("float32",f,[2,1,128])}class jr{constructor(f,b,v,k){this._session=f,this._state=b,this._sr=v,this.ortInstance=k,this.reset_state=()=>{this._state=up(this.ortInstance)},this.process=async w=>{const A={input:new this.ortInstance.Tensor("float32",w,[1,w.length]),state:this._state,sr:this._sr},C=await this._session.run(A);this._state=C.stateN;const[Z]=C.output?.data;return{notSpeech:1-Z,isSpeech:Z}}}}en.SileroV5=jr;lp=jr;jr.new=async(S,f)=>{Zc.log.debug("Loading VAD...");const b=await f(),v=await S.InferenceSession.create(b),k=new S.Tensor("int64",[16000n]),w=up(S);return Zc.log.debug("...finished loading VAD"),new lp(v,w,k,S)};(function(S){var f=et&&et.__createBinding||(Object.create?function(w,I,A,C){C===void 0&&(C=A);var Z=Object.getOwnPropertyDescriptor(I,A);(!Z||("get"in Z?!I.__esModule:Z.writable||Z.configurable))&&(Z={enumerable:!0,get:function(){return I[A]}}),Object.defineProperty(w,C,Z)}:function(w,I,A,C){C===void 0&&(C=A),w[C]=I[A]}),b=et&&et.__exportStar||function(w,I){for(var A in w)A!=="default"&&!Object.prototype.hasOwnProperty.call(I,A)&&f(I,w,A)};Object.defineProperty(S,"__esModule",{value:!0}),S.SileroV5=S.SileroLegacy=void 0,b(ap,S);var v=Ji;Object.defineProperty(S,"SileroLegacy",{enumerable:!0,get:function(){return v.SileroLegacy}});var k=en;Object.defineProperty(S,"SileroV5",{enumerable:!0,get:function(){return k.SileroV5}})})(Wr);var Ci={};Object.defineProperty(Ci,"__esModule",{value:!0});Ci.Resampler=void 0;const qf=li;class Wf{constructor(f){this.options=f,this.process=b=>{const v=[];for(const k of b)for(this.inputBuffer.push(k);this.hasEnoughDataForFrame();){const w=this.generateOutputFrame();v.push(w)}return v},f.nativeSampleRate<16e3&&qf.log.error("nativeSampleRate is too low. Should have 16000 = targetSampleRate <= nativeSampleRate"),this.inputBuffer=[]}async*stream(f){for(const b of f)for(this.inputBuffer.push(b);this.hasEnoughDataForFrame();)yield this.generateOutputFrame()}hasEnoughDataForFrame(){return this.inputBuffer.length*this.options.targetSampleRate/this.options.nativeSampleRate>=this.options.targetFrameSize}generateOutputFrame(){const f=new Float32Array(this.options.targetFrameSize);let b=0,v=0;for(;b<this.options.targetFrameSize;){let k=0,w=0;for(;v<Math.min(this.inputBuffer.length,(b+1)*this.options.nativeSampleRate/this.options.targetSampleRate);){const I=this.inputBuffer[v];I!==void 0&&(k+=I,w++),v++}f[b]=k/w,b++}return this.inputBuffer=this.inputBuffer.slice(v),f}}Ci.Resampler=Wf;(function(S){var f=et&&et.__createBinding||(Object.create?function(X,J,P,Q){Q===void 0&&(Q=P);var G=Object.getOwnPropertyDescriptor(J,P);(!G||("get"in G?!J.__esModule:G.writable||G.configurable))&&(G={enumerable:!0,get:function(){return J[P]}}),Object.defineProperty(X,Q,G)}:function(X,J,P,Q){Q===void 0&&(Q=P),X[Q]=J[P]}),b=et&&et.__setModuleDefault||(Object.create?function(X,J){Object.defineProperty(X,"default",{enumerable:!0,value:J})}:function(X,J){X.default=J}),v=et&&et.__importStar||function(X){if(X&&X.__esModule)return X;var J={};if(X!=null)for(var P in X)P!=="default"&&Object.prototype.hasOwnProperty.call(X,P)&&f(J,X,P);return b(J,X),J};Object.defineProperty(S,"__esModule",{value:!0}),S.NonRealTimeVAD=S.defaultNonRealTimeVADOptions=void 0;const k=v(sp),w=Ti,I=oi,A=It,C=ei,Z=Wr,W=Ci;S.defaultNonRealTimeVADOptions={...A.defaultFrameProcessorOptions,modelURL:w.baseAssetPath+"silero_vad_legacy.onnx",modelFetcher:I.defaultModelFetcher};class H{static async new(J={}){const P={...S.defaultNonRealTimeVADOptions,...J};(0,A.validateOptions)(P),P.ortConfig!==void 0&&P.ortConfig(k);const Q=()=>P.modelFetcher(P.modelURL),G=await Z.SileroLegacy.new(k,Q),ee=new A.FrameProcessor(G.process,G.reset_state,{positiveSpeechThreshold:P.positiveSpeechThreshold,negativeSpeechThreshold:P.negativeSpeechThreshold,redemptionMs:P.redemptionMs,preSpeechPadMs:P.preSpeechPadMs,minSpeechMs:P.minSpeechMs,submitUserSpeechOnPause:P.submitUserSpeechOnPause},1536/16);return ee.resume(),new this(Q,k,P,ee)}constructor(J,P,Q,G){this.modelFetcher=J,this.ort=P,this.options=Q,this.frameProcessor=G,this.frameSamples=1536}async*run(J,P){const Q={nativeSampleRate:P,targetSampleRate:16e3,targetFrameSize:this.frameSamples},G=new W.Resampler(Q);let ee=0,R=0,D=0;for await(const j of G.stream(J)){const V=[];await this.frameProcessor.process(j,q=>{V.push(q)});for(const q of V)switch(q.msg){case C.Message.SpeechStart:ee=D*this.frameSamples/16;break;case C.Message.SpeechEnd:R=(D+1)*this.frameSamples/16,yield{audio:q.audio,start:ee,end:R};break}D++}const B=[];this.frameProcessor.endSegment(j=>{B.push(j)});for(const j of B)switch(j.msg){case C.Message.SpeechEnd:yield{audio:j.audio,start:ee,end:D*this.frameSamples/16}}}}S.NonRealTimeVAD=H})(tp);var Et={};Object.defineProperty(Et,"__esModule",{value:!0});Et.audioFileToArray=Et.encodeWAV=Et.arrayBufferToBase64=Et.minFramesForTargetMS=void 0;function Gf(S,f,b=16e3){return Math.ceil(S*b/1e3/f)}Et.minFramesForTargetMS=Gf;function jf(S){const f=new Uint8Array(S),b=f.byteLength,v=new Array(b);for(var k=0;k<b;k++){const w=f[k];if(w===void 0)break;v[k]=String.fromCharCode(w)}return btoa(v.join(""))}Et.arrayBufferToBase64=jf;function Hf(S,f=3,b=16e3,v=1,k=32){var w=k/8,I=v*w,A=new ArrayBuffer(44+S.length*w),C=new DataView(A);return Zi(C,0,"RIFF"),C.setUint32(4,36+S.length*w,!0),Zi(C,8,"WAVE"),Zi(C,12,"fmt "),C.setUint32(16,16,!0),C.setUint16(20,f,!0),C.setUint16(22,v,!0),C.setUint32(24,b,!0),C.setUint32(28,b*I,!0),C.setUint16(32,I,!0),C.setUint16(34,k,!0),Zi(C,36,"data"),C.setUint32(40,S.length*w,!0),f===1?Qf(C,44,S):Kf(C,44,S),A}Et.encodeWAV=Hf;function Kf(S,f,b){for(var v=0;v<b.length;v++,f+=4)S.setFloat32(f,b[v],!0)}function Qf(S,f,b){for(var v=0;v<b.length;v++,f+=2){var k=Math.max(-1,Math.min(1,b[v]));S.setInt16(f,k<0?k*32768:k*32767,!0)}}function Zi(S,f,b){for(var v=0;v<b.length;v++)S.setUint8(f+v,b.charCodeAt(v))}async function Zf(S){const f=new OfflineAudioContext(1,1,44100),b=new FileReader;let v=null;if(await new Promise(I=>{b.addEventListener("loadend",A=>{const C=b.result;f.decodeAudioData(C,Z=>{v=Z,f.startRendering().then(W=>{console.log("Rendering completed successfully"),I()}).catch(W=>{console.error(`Rendering failed: ${W}`)})},Z=>{console.log(`Error with decoding audio data: ${Z}`)})}),b.readAsArrayBuffer(S)}),v===null)throw Error("some shit");let k=v,w=new Float32Array(k.length);for(let I=0;I<k.length;I++)for(let A=0;A<k.numberOfChannels;A++)w[I]+=k.getChannelData(A)[I];return{audio:w,sampleRate:k.sampleRate}}Et.audioFileToArray=Zf;var dp={};(function(S){var f=et&&et.__createBinding||(Object.create?function(ee,R,D,B){B===void 0&&(B=D);var j=Object.getOwnPropertyDescriptor(R,D);(!j||("get"in j?!R.__esModule:j.writable||j.configurable))&&(j={enumerable:!0,get:function(){return R[D]}}),Object.defineProperty(ee,B,j)}:function(ee,R,D,B){B===void 0&&(B=D),ee[B]=R[D]}),b=et&&et.__setModuleDefault||(Object.create?function(ee,R){Object.defineProperty(ee,"default",{enumerable:!0,value:R})}:function(ee,R){ee.default=R}),v=et&&et.__importStar||function(ee){if(ee&&ee.__esModule)return ee;var R={};if(ee!=null)for(var D in ee)D!=="default"&&Object.prototype.hasOwnProperty.call(ee,D)&&f(R,ee,D);return b(R,ee),R};Object.defineProperty(S,"__esModule",{value:!0}),S.AudioNodeVAD=S.MicVAD=S.getDefaultRealTimeVADOptions=S.ort=S.DEFAULT_MODEL=void 0;const k=v(sp),w=oi,I=It,A=li,C=ei,Z=Wr,W=Ci;S.DEFAULT_MODEL="legacy",S.ort=k;const H="vad.worklet.bundle.min.js",X="silero_vad_v5.onnx",J="silero_vad_legacy.onnx",P=ee=>({...I.defaultFrameProcessorOptions,onFrameProcessed:(R,D)=>{},onVADMisfire:()=>{A.log.debug("VAD misfire")},onSpeechStart:()=>{A.log.debug("Detected speech start")},onSpeechEnd:()=>{A.log.debug("Detected speech end")},onSpeechRealStart:()=>{A.log.debug("Detected real speech start")},baseAssetPath:"./",onnxWASMBasePath:"./",model:ee,workletOptions:{},getStream:async()=>await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:!0,autoGainControl:!0,noiseSuppression:!0}}),pauseStream:async R=>{R.getTracks().forEach(D=>{D.stop()})},resumeStream:async R=>await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:!0,autoGainControl:!0,noiseSuppression:!0}}),ortConfig:R=>{R.env.logLevel="error"},startOnLoad:!0});S.getDefaultRealTimeVADOptions=P;class Q{static async new(R={}){const D={...(0,S.getDefaultRealTimeVADOptions)(R.model??S.DEFAULT_MODEL),...R};(0,I.validateOptions)(D);const B=new AudioContext,j=await G.new(B,D),V=new Q(D,B,j);if(D.startOnLoad)try{await V.start()}catch(q){console.error("Error starting micVad",q)}return V}constructor(R,D,B,j=!1){this.options=R,this.audioContext=D,this.audioNodeVAD=B,this.listening=j,this.initialized=!1,this.pause=()=>{this.stream&&this.options.pauseStream(this.stream),this.audioNodeVAD.pause(),this.listening=!1},this.resume=async()=>{if(!this.stream){console.warn("Stream not initialized");return}this.stream=await this.options.resumeStream(this.stream),this.sourceNode&&this.sourceNode.disconnect(),this.sourceNode=new MediaStreamAudioSourceNode(this.audioContext,{mediaStream:this.stream}),this.audioNodeVAD.receive(this.sourceNode)},this.start=async()=>{this.initialized||(this.initialized=!0,this.stream=await this.options.getStream(),this.sourceNode=new MediaStreamAudioSourceNode(this.audioContext,{mediaStream:this.stream}),this.audioNodeVAD.receive(this.sourceNode)),this.stream?.active?(this.audioNodeVAD.start(),this.listening=!0):(await this.resume(),this.audioNodeVAD.start(),this.listening=!0)},this.destroy=()=>{this.listening&&this.pause(),this.stream?this.options.pauseStream(this.stream):console.warn("Stream not initialized"),this.sourceNode?this.sourceNode.disconnect():console.warn("Source node not initialized"),this.audioNodeVAD.destroy(),this.audioContext.close()},this.setOptions=V=>{this.audioNodeVAD.setFrameProcessorOptions(V)}}}S.MicVAD=Q;class G{static async new(R,D={}){const B={...(0,S.getDefaultRealTimeVADOptions)(D.model??S.DEFAULT_MODEL),...D};(0,I.validateOptions)(B),S.ort.env.wasm.wasmPaths=B.onnxWASMBasePath,B.ortConfig!==void 0&&B.ortConfig(S.ort);const j=B.model==="v5"?X:J,V=B.baseAssetPath+j,q=B.model==="v5"?Z.SileroV5.new:Z.SileroLegacy.new;let ne;try{ne=await q(S.ort,()=>(0,w.defaultModelFetcher)(V))}catch(Ne){throw console.error(`Encountered an error while loading model file ${V}`),Ne}const ye=B.model==="v5"?512:1536,ue=ye/16,Ce=new I.FrameProcessor(ne.process,ne.reset_state,{positiveSpeechThreshold:B.positiveSpeechThreshold,negativeSpeechThreshold:B.negativeSpeechThreshold,redemptionMs:B.redemptionMs,preSpeechPadMs:B.preSpeechPadMs,minSpeechMs:B.minSpeechMs,submitUserSpeechOnPause:B.submitUserSpeechOnPause},ue),Ae=new G(R,B,Ce,ye,ue);return await Ae.setupAudioNode(),Ae}constructor(R,D,B,j,V){this.ctx=R,this.options=D,this.frameSamples=j,this.msPerFrame=V,this.pause=()=>{this.frameProcessor.pause(this.handleFrameProcessorEvent)},this.start=()=>{this.frameProcessor.resume()},this.receive=q=>{q.connect(this.audioNode)},this.processFrame=async q=>{await this.frameProcessor.process(q,this.handleFrameProcessorEvent)},this.handleFrameProcessorEvent=q=>{switch(q.msg){case C.Message.FrameProcessed:this.options.onFrameProcessed(q.probs,q.frame);break;case C.Message.SpeechStart:this.options.onSpeechStart();break;case C.Message.SpeechRealStart:this.options.onSpeechRealStart();break;case C.Message.VADMisfire:this.options.onVADMisfire();break;case C.Message.SpeechEnd:this.options.onSpeechEnd(q.audio);break}},this.destroy=()=>{this.audioNode instanceof AudioWorkletNode&&this.audioNode.port.postMessage({message:C.Message.SpeechStop}),this.audioNode.disconnect(),this.gainNode?.disconnect()},this.setFrameProcessorOptions=q=>{this.frameProcessor.options={...this.frameProcessor.options,...q}},this.frameProcessor=B}async setupAudioNode(){if("audioWorklet"in this.ctx&&typeof AudioWorkletNode=="function")try{const j=this.options.baseAssetPath+H;await this.ctx.audioWorklet.addModule(j);const V=this.options.workletOptions??{};V.processorOptions={...V.processorOptions??{},frameSamples:this.frameSamples},this.audioNode=new AudioWorkletNode(this.ctx,"vad-helper-worklet",V),this.audioNode.port.onmessage=async q=>{switch(q.data?.message){case C.Message.AudioFrame:let ne=q.data.data;ne instanceof ArrayBuffer||(ne=new ArrayBuffer(q.data.data.byteLength),new Uint8Array(ne).set(new Uint8Array(q.data.data)));const ye=new Float32Array(ne);await this.processFrame(ye);break}};return}catch(j){console.log("AudioWorklet setup failed, falling back to ScriptProcessor",j)}this.resampler=new W.Resampler({nativeSampleRate:this.ctx.sampleRate,targetSampleRate:16e3,targetFrameSize:this.frameSamples??480});const D=4096;this.audioNode=this.ctx.createScriptProcessor(D,1,1),this.gainNode=this.ctx.createGain(),this.gainNode.gain.value=0;let B=!1;this.audioNode.onaudioprocess=async j=>{if(!B){B=!0;try{const V=j.inputBuffer.getChannelData(0);if(j.outputBuffer.getChannelData(0).fill(0),this.resampler){const ne=this.resampler.process(V);for(const ye of ne)await this.processFrame(ye)}}catch(V){console.error("Error processing audio:",V)}finally{B=!1}}},this.audioNode.connect(this.gainNode),this.gainNode.connect(this.ctx.destination)}}S.AudioNodeVAD=G})(dp);(function(S){Object.defineProperty(S,"__esModule",{value:!0}),S.getDefaultRealTimeVADOptions=S.MicVAD=S.DEFAULT_MODEL=S.AudioNodeVAD=S.utils=S.NonRealTimeVAD=S.Message=S.FrameProcessor=S.defaultModelFetcher=S.baseAssetPath=void 0;var f=Ti;Object.defineProperty(S,"baseAssetPath",{enumerable:!0,get:function(){return f.baseAssetPath}});var b=oi;Object.defineProperty(S,"defaultModelFetcher",{enumerable:!0,get:function(){return b.defaultModelFetcher}});var v=It;Object.defineProperty(S,"FrameProcessor",{enumerable:!0,get:function(){return v.FrameProcessor}});var k=ei;Object.defineProperty(S,"Message",{enumerable:!0,get:function(){return k.Message}});var w=tp;Object.defineProperty(S,"NonRealTimeVAD",{enumerable:!0,get:function(){return w.NonRealTimeVAD}});const I=Et;S.utils={audioFileToArray:I.audioFileToArray,minFramesForTargetMS:I.minFramesForTargetMS,arrayBufferToBase64:I.arrayBufferToBase64,encodeWAV:I.encodeWAV};var A=dp;Object.defineProperty(S,"AudioNodeVAD",{enumerable:!0,get:function(){return A.AudioNodeVAD}}),Object.defineProperty(S,"DEFAULT_MODEL",{enumerable:!0,get:function(){return A.DEFAULT_MODEL}}),Object.defineProperty(S,"MicVAD",{enumerable:!0,get:function(){return A.MicVAD}}),Object.defineProperty(S,"getDefaultRealTimeVADOptions",{enumerable:!0,get:function(){return A.getDefaultRealTimeVADOptions}})})(Pr);(function(S){var f=et&&et.__createBinding||(Object.create?function(G,ee,R,D){D===void 0&&(D=R);var B=Object.getOwnPropertyDescriptor(ee,R);(!B||("get"in B?!ee.__esModule:B.writable||B.configurable))&&(B={enumerable:!0,get:function(){return ee[R]}}),Object.defineProperty(G,D,B)}:function(G,ee,R,D){D===void 0&&(D=R),G[D]=ee[R]}),b=et&&et.__setModuleDefault||(Object.create?function(G,ee){Object.defineProperty(G,"default",{enumerable:!0,value:ee})}:function(G,ee){G.default=ee}),v=et&&et.__importStar||function(G){if(G&&G.__esModule)return G;var ee={};if(G!=null)for(var R in G)R!=="default"&&Object.prototype.hasOwnProperty.call(G,R)&&f(ee,G,R);return b(ee,G),ee};Object.defineProperty(S,"__esModule",{value:!0}),S.useMicVAD=S.getDefaultReactRealTimeVADOptions=S.utils=void 0;const k=Pr,w=v(Y);var I=Pr;Object.defineProperty(S,"utils",{enumerable:!0,get:function(){return I.utils}});const A={userSpeakingThreshold:.6},C=G=>({...(0,k.getDefaultRealTimeVADOptions)(G),...A});S.getDefaultReactRealTimeVADOptions=C;const Z=Object.keys(A),W=Object.keys((0,k.getDefaultRealTimeVADOptions)("v5")),H=(G,ee)=>G.reduce((R,D)=>(R[D]=ee[D],R),{});function X(G){const ee=G.model??k.DEFAULT_MODEL;G={...(0,S.getDefaultReactRealTimeVADOptions)(ee),...G};const R=H(Z,G),D=H(W,G);return[R,D]}function J(G){const ee=w.default.useRef(G);return Q(()=>{ee.current=G}),w.default.useCallback((...R)=>ee.current.apply(void 0,R),[])}function P(G){const[ee,R]=X(G),[D,B]=(0,w.useState)(!1),[j,V]=(0,w.useState)(!0),[q,ne]=(0,w.useState)(!1),[ye,ue]=(0,w.useState)(!1),[Ce,Ae]=(0,w.useState)(null),Ne=J(R.onFrameProcessed);R.onFrameProcessed=J((st,it)=>{const rt=st.isSpeech>ee.userSpeakingThreshold;B(rt),Ne(st,it)});const{onSpeechEnd:ht,onSpeechStart:Qe,onSpeechRealStart:ve,onVADMisfire:Ee}=R,Ue=J(ht),Fe=J(Qe),Me=J(Ee),ze=J(ve);R.onSpeechEnd=Ue,R.onSpeechStart=Fe,R.onVADMisfire=Me,R.onSpeechRealStart=ze,(0,w.useEffect)(()=>{let st,it=!1;return(async()=>{try{if(st=await k.MicVAD.new(R),it){st.destroy();return}}catch(Ze){V(!1),Ze instanceof Error?ne(Ze.message):ne(String(Ze));return}Ae(st),V(!1),R.startOnLoad&&(st?.start(),ue(!0))})().catch(Ze=>{console.log("Well that didn't work")}),function(){st?.destroy(),it=!0,!j&&!q&&ue(!1)}},[]);const Ye=()=>{!j&&!q&&(Ce?.pause(),ue(!1))},tt=()=>{!j&&!q&&(Ce?.start(),ue(!0))};return{listening:ye,errored:q,loading:j,userSpeaking:D,pause:Ye,start:tt,toggle:()=>{ye?Ye():tt()}}}S.useMicVAD=P;const Q=typeof window<"u"&&typeof window.document<"u"&&typeof window.document.createElement<"u"?w.default.useLayoutEffect:w.default.useEffect})(Jc);function Xf(){return"https://storage.googleapis.com/voice-form-filler-demo/vad-assets/vad-web/"}function Yf(){return"https://storage.googleapis.com/voice-form-filler-demo/vad-assets/onnxruntime/"}const Jf=Xf(),eh=Yf();function cp(S){const f=S?.callbacks,b=S?.sharedStream,v=S?.sensitivity||{},k=Y.useRef(b);Y.useEffect(()=>{k.current=b,console.log("[useDemoVAD] Stream updated:",!!b)},[b]);const w=Jc.useMicVAD({startOnLoad:!1,baseAssetPath:Jf,onnxWASMBasePath:eh,getStream:async()=>(console.log("[useDemoVAD] getStream called, streamRef.current:",!!k.current),k.current?(console.log("[useDemoVAD] Using shared stream"),k.current):(console.log("[useDemoVAD] Creating new stream"),await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:!0,noiseSuppression:!0,autoGainControl:!0,channelCount:1}}))),positiveSpeechThreshold:v.positiveSpeechThreshold??.9,negativeSpeechThreshold:v.negativeSpeechThreshold??.7,minSpeechMs:v.minSpeechMs??250,redemptionMs:v.redemptionMs??400,onSpeechStart:()=>{f?.onSpeechStart?.()},onSpeechEnd:I=>{f?.onSpeechEnd?.(I)},onVADMisfire:()=>{f?.onVADMisfire?.()},onFrameProcessed:(I,A)=>{const C=I.isSpeech;f?.onFrameProcessed?.(C,A)}});return{userSpeaking:w.userSpeaking,loading:w.loading,errored:w.errored,pause:w.pause,start:w.start}}const Fr=[{language:"English",code:"en",text:"Hello Gemini, please speak English"},{language:"Español",code:"es",text:"Hola Gemini, por favor habla español"},{language:"中文",code:"zh-Hans",text:"你好 Gemini, 请说中文"},{language:"Tagalog",code:"tl",text:"Kumusta Gemini, pakisabi sa Tagalog"},{language:"العربية",code:"ar",text:"مرحباً يا جيميناي، من فضلك تحدث العربية"},{language:"Français",code:"fr",text:"Bonjour Gemini, veuillez parler français"},{language:"한국어",code:"ko",text:"안녕하세요 Gemini, 한국어로 말해주세요"},{language:"Deutsch",code:"de",text:"Hallo Gemini, sprich bitte Deutsch"},{language:"Português",code:"pt",text:"Olá Gemini, por favor, fale português"},{language:"हिन्दी",code:"hi",text:"नमस्ते जेमिनी, कृपया हिंदी बोलें"},{language:"Italiano",code:"it",text:"Ciao Gemini, parla italiano per favore"},{language:"اردو",code:"ur",text:"ہیلو جیمنی، برائے مہربانی اردو بولیں"},{language:"فارسی",code:"fa",text:"سلام جیمینی، لطفا فارسی صحبت کن"},{language:"Nederlands",code:"nl",text:"Hallo Gemini, spreek alstublieft Nederlands"},{language:"Українська",code:"uk",text:"Привіт Gemini, будь ласка, говори українською"},{language:"Svenska",code:"sv",text:"Hej Gemini, tala svenska tack"},{language:"Afrikaans",code:"af",text:"Hallo Gemini, praat asseblief Afrikaans"},{language:"Qhichwa",code:"qu",text:"Allillanchu Gemini, ama hina kaychu, Qhichwa rimay"}];function pp({intervalMs:S=3e3,onDismiss:f}){const[b,v]=Y.useState(0),[k,w]=Y.useState("in");Y.useEffect(()=>{const A=setInterval(()=>{w("out"),setTimeout(()=>{v(C=>(C+1)%Fr.length),w("in")},300)},S);return()=>clearInterval(A)},[S]);const I=Fr[b];return K.jsxs("div",{className:"greeting-carousel",children:[K.jsxs("div",{className:"greeting-carousel__content",children:[K.jsx("div",{className:"greeting-carousel__icon",children:K.jsxs("svg",{width:"48",height:"48",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",strokeLinecap:"round",strokeLinejoin:"round",children:[K.jsx("path",{d:"M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"}),K.jsx("path",{d:"M19 10v2a7 7 0 0 1-14 0v-2"}),K.jsx("line",{x1:"12",x2:"12",y1:"19",y2:"22"})]})}),K.jsxs("div",{className:`greeting-carousel__text greeting-carousel__text--${k}`,children:[K.jsx("div",{className:"greeting-carousel__language",children:I.language}),K.jsx("div",{className:"greeting-carousel__prompt",children:I.text})]},b),K.jsx("div",{className:"greeting-carousel__progress",children:Fr.map((A,C)=>K.jsx("div",{className:`greeting-carousel__dot ${C===b?"greeting-carousel__dot--active":""}`},C))})]}),f&&K.jsx("button",{className:"greeting-carousel__dismiss",onClick:f,"aria-label":"Dismiss greeting prompt",children:"×"}),K.jsx("style",{children:`
        .greeting-carousel {
          position: fixed;
          top: 50%;
          left: 50%;
          transform: translate(-50%, -50%);
          background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
          color: white;
          padding: 3rem 4rem;
          border-radius: 20px;
          box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
          z-index: 1000;
          max-width: 600px;
          width: 90%;
        }
        
        .greeting-carousel__content {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1.5rem;
        }
        
        .greeting-carousel__icon {
          animation: pulse 2s ease-in-out infinite;
        }
        
        .greeting-carousel__icon svg {
          color: white;
          filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.2));
        }
        
        @keyframes pulse {
          0%, 100% { transform: scale(1); opacity: 1; }
          50% { transform: scale(1.05); opacity: 0.9; }
        }
        
        .greeting-carousel__text {
          text-align: center;
          min-height: 120px;
          display: flex;
          flex-direction: column;
          justify-content: center;
          transition: opacity 0.3s ease-in-out, transform 0.3s ease-in-out;
        }
        
        .greeting-carousel__text--in {
          opacity: 1;
          transform: translateY(0);
        }
        
        .greeting-carousel__text--out {
          opacity: 0;
          transform: translateY(-10px);
        }
        
        .greeting-carousel__language {
          font-size: 0.875rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.1em;
          opacity: 0.9;
          margin-bottom: 0.5rem;
        }
        
        .greeting-carousel__prompt {
          font-size: 1.5rem;
          font-weight: 500;
          line-height: 1.4;
          text-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
        }
        
        .greeting-carousel__progress {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
          justify-content: center;
          max-width: 300px;
        }
        
        .greeting-carousel__dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: rgba(255, 255, 255, 0.3);
          transition: all 0.3s ease;
        }
        
        .greeting-carousel__dot--active {
          width: 24px;
          border-radius: 3px;
          background: white;
        }
        
        .greeting-carousel__dismiss {
          position: absolute;
          top: 1rem;
          right: 1rem;
          background: rgba(255, 255, 255, 0.2);
          border: none;
          color: white;
          font-size: 2rem;
          line-height: 1;
          width: 36px;
          height: 36px;
          border-radius: 50%;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background 0.2s;
        }
        
        .greeting-carousel__dismiss:hover {
          background: rgba(255, 255, 255, 0.3);
        }
        
        @media (max-width: 640px) {
          .greeting-carousel {
            padding: 2rem;
          }
          
          .greeting-carousel__prompt {
            font-size: 1.25rem;
          }
          
          .greeting-carousel__progress {
            display: none; /* Too many dots on mobile */
          }
        }
      `})]})}const fp=[{name:"English",nativeName:"English"},{name:"Spanish",nativeName:"Español"},{name:"Chinese",nativeName:"中文 (Zhōngwén)"},{name:"Tagalog",nativeName:"Tagalog"},{name:"Arabic",nativeName:"العربية (al-ʿArabīyah)"},{name:"French",nativeName:"Français"},{name:"Korean",nativeName:"한국어 (Hangugeo)"},{name:"German",nativeName:"Deutsch"},{name:"Portuguese",nativeName:"Português"},{name:"Hindi",nativeName:"हिन्दी (Hindī)"},{name:"Italian",nativeName:"Italiano"},{name:"Urdu",nativeName:"اردو (Urdū)"},{name:"Persian",nativeName:"فارسی (Fārsī)"},{name:"Dutch",nativeName:"Nederlands"},{name:"Ukrainian",nativeName:"Українська (Ukrayins'ka)"},{name:"Swedish",nativeName:"Svenska"},{name:"Afrikaans",nativeName:"Afrikaans"},{name:"Quechua",nativeName:"Qhichwa"}];function th({schema:S,sectionIndex:f,wsUrl:b,onClose:v,connectionManager:k,status:w,sharedStream:I,streamError:A}){const[C,Z]=Y.useState(k||null),W=Y.useRef(k||null),[H,X]=Y.useState(w||"Ready"),[J,P]=Y.useState(null),[Q,G]=Y.useState(1),[ee,R]=Y.useState(new Set),[D,B]=Y.useState({filled:0,total:12}),[j,V]=Y.useState(!1),[q,ne]=Y.useState(!1),[ye,ue]=Y.useState(!1),[Ce,Ae]=Y.useState(!1),[Ne,ht]=Y.useState(!1),Qe=Y.useRef(!1),[ve,Ee]=Y.useState(""),Ue=Y.useRef(null),Fe=Y.useRef(!1),Me=Y.useRef({x:0,y:0}),ze=Y.useRef(I||null),Ye=Y.useRef(null),tt=Y.useRef(!1),ct=450;Y.useEffect(()=>{ze.current=I||null,console.log("[VoiceOverlay] 🔗 Using shared stream from parent:",!!I)},[I]);const st=Y.useMemo(()=>({onSpeechStart:()=>{if(q)return;console.log("[VFF VAD] 🎤 User speech started - buffering audio...");const se=performance.now();Ye.current=Date.now(),tt.current=!1,console.log(`[VFF VAD] 🎤 Speech detected at t=${se.toFixed(2)}ms`),Ce&&(console.log("[VoiceOverlay] 🌍 User speaking - hiding greeting carousel"),Ae(!1),Qe.current=!0);const fe=C?.getAudioManager();fe&&fe.isSpeaking()&&(fe.pauseAudioContext(),console.log(`[VFF VAD] 🔇 Tentative pause at t=${performance.now().toFixed(2)}ms - waiting to confirm speech duration`)),setTimeout(()=>{const Se=Ye.current?Date.now()-Ye.current:0;if(Ye.current!==null&&Se>=ct){if(console.log(`[VFF VAD] ✅ Valid speech detected (${Se}ms) - starting turn`),tt.current=!0,C){const We=performance.now();C.sendActivityStart(),console.log(`[VFF VAD] 📤 Sent activity_start signal at t=${We.toFixed(2)}ms (user turn begins)`)}if(fe){const We=performance.now();console.log(`[VFF VAD] 🚪 Opening audio gate at t=${We.toFixed(2)}ms`),fe.setVADActive(!0),console.log("[VFF VAD] 🚪 Audio gate opened, pre-buffer flushed, live audio now flowing")}fe?.isSpeaking()&&fe&&(console.log("[VFF VAD] 🔇 Flushing Gemini audio queue (full barge-in)"),fe.flushAudioQueue())}},ct)},onSpeechEnd:se=>{if(q)return;const fe=Ye.current?Date.now()-Ye.current:0,Se=C?.getAudioManager();tt.current?(console.log(`[VFF VAD] ✅ Valid turn completed (${fe}ms) - closing turn`),Se&&Se.setVADActive(!1),C?.onVADSpeechEnd()):(console.log(`[VFF VAD] ⚠️ Speech too short (${fe}ms < ${ct}ms) - no turn started, false positive`),Se&&(Se.resumeAudioContext(),console.log("[VFF VAD] 🔊 Resuming audio - false positive"))),Ye.current=null,tt.current=!1},onVADMisfire:()=>{console.log("[VFF VAD] ⚠️ VAD misfire detected"),Ye.current=null}}),[q,C]),it=Y.useMemo(()=>({sharedStream:ze.current,callbacks:st}),[st,I]),rt=cp(it);Y.useEffect(()=>{if(k){W.current=k,Z(k);return}if(W.current)return;const se=_e.initWithSections(S,f),fe=qr(se.schema,Se=>{X(Se),P(null)},"English",I||void 0);return W.current=fe,Z(fe),()=>{k||(W.current&&(W.current.disconnect(),W.current=null),Z(null))}},[S,f,k]),Y.useEffect(()=>{w!==void 0&&X(w)},[w]),Y.useEffect(()=>{const se=H.toLowerCase()==="connected"||H.toLowerCase().startsWith("connected ");se&&!Qe.current&&!Ce&&(console.log("[VoiceOverlay] 🌍 Connection established - showing greeting carousel"),Ae(!0)),!se&&Qe.current&&(Qe.current=!1)},[H,Ce]),Y.useEffect(()=>{const fe=(H.toLowerCase()==="connected"||H.toLowerCase().startsWith("connected "))&&!q&&!rt.loading&&!rt.errored;fe&&!rt.userSpeaking?(console.log("[VoiceOverlay] 🎙️ Starting VAD (conditions met)"),rt.start()):!fe&&rt.userSpeaking&&(console.log("[VoiceOverlay] ⏸️ Pausing VAD (conditions not met)"),rt.pause()),rt.errored&&P(`Voice detection error: ${rt.errored}`)},[H,q,rt.loading,rt.errored,rt.userSpeaking]),Y.useEffect(()=>(window.vffOnAudioPlaybackStart=()=>{Ce&&(console.log("[VoiceOverlay] 🌍 Gemini speaking - hiding greeting carousel"),Ae(!1),Qe.current=!0)},()=>{delete window.vffOnAudioPlaybackStart}),[Ce]);const Ze=async()=>{if(C)try{if(P(null),C.isPaused()){await C.resume();return}await C.connect();const se=5e3,fe=Date.now();for(;Date.now()-fe<se;){const De=C.getStatus();if(De==="connected"||De==="switching_section"){console.log("[VoiceOverlay] ✅ WebSocket connected, setting up audio..."),X("Setting up audio..."),await C.startRecording(),X("connected"),console.log("[VoiceOverlay] ✅ Audio ready - fully connected");break}await new Promise(Dt=>setTimeout(Dt,50))}const Se=C.getStatus();Se!=="connected"&&Se!=="switching_section"&&(console.error("[VoiceOverlay] ❌ Connection timeout, final status:",Se),P("Connection timed out - please try again"))}catch(se){console.error("[VoiceOverlay] Connection error:",se),P(se instanceof Error?se.message:"Connection failed"),X("Connection failed")}},Vt=()=>{C&&(C.pause(),rt.pause())},pt=async()=>{if(!q||!(H.toLowerCase()==="connected"||H.toLowerCase().startsWith("connected ")||H.toLowerCase()==="switching_section"||H.toLowerCase().startsWith("reconnecting")))return;ue(!0);const fe=C?.getAudioManager();fe?.unmuteInput(),fe?.isSpeaking()&&fe.flushAudioQueue()},Mt=()=>{if(!q||!(H.toLowerCase()==="connected"||H.toLowerCase().startsWith("connected ")||H.toLowerCase()==="switching_section"||H.toLowerCase().startsWith("reconnecting")))return;ue(!1),C?.getAudioManager()?.muteInput(),C?.sendActivityEnd()};Y.useEffect(()=>{if(!q)return;const se=H.toLowerCase()==="connected"||H.toLowerCase().startsWith("connected ")||H.toLowerCase()==="switching_section"||H.toLowerCase().startsWith("reconnecting"),fe=De=>{if(De.code==="Space"){const We=De.target;if(We.tagName==="INPUT"||We.tagName==="TEXTAREA")return;De.preventDefault(),!De.repeat&&se&&pt()}},Se=De=>{if(De.code==="Space"){const We=De.target;if(We.tagName==="INPUT"||We.tagName==="TEXTAREA")return;De.preventDefault(),se&&Mt()}};return window.addEventListener("keydown",fe),window.addEventListener("keyup",Se),()=>{window.removeEventListener("keydown",fe),window.removeEventListener("keyup",Se)}},[q,H]),Y.useEffect(()=>{const se=_e.initWithSections(S,f);G(se.current_section||1),R(se.completed_sections||new Set);const fe=_e.getSectionFieldCount(se);B(fe)},[S,f]),Y.useEffect(()=>{const se=setInterval(()=>{const fe=_e.load();if(fe){const Se=_e.getSectionFieldCount(fe);if(B(Se),fe.current_section&&fe.current_section!==Q&&G(fe.current_section),fe.completed_sections){const De=new Set(Array.from(ee)),We=new Set(Array.from(fe.completed_sections));(De.size!==We.size||![...De].every(Dt=>We.has(Dt)))&&R(We)}}},1e3);return()=>clearInterval(se)},[Q,ee]);const Te=async se=>{const fe=se.target.value;if(Ee(fe),console.log("[VoiceOverlay] Language changed to:",fe),C&&Pe)try{const Se=_e.load();if(!Se){console.error("[VoiceOverlay] No state found for next field hint");return}const De=Vr(Se.schema,Se.current_values),We=De?Lr(De,Se.schema):"all fields are complete";C.changeSpokenLanguage(fe,We)}catch(Se){console.error("[VoiceOverlay] Failed to change spoken language:",Se),P(Se instanceof Error?Se.message:"Failed to change language")}},qe=()=>{if(!confirm(`⚠️ Clear all form data?

This will delete all fields and reload the page.
This action cannot be undone.`))return;_e.clear(),document.querySelectorAll("input, textarea, select").forEach(fe=>{const Se=fe;if(Se.tagName==="INPUT"){const De=Se;De.type==="checkbox"||De.type==="radio"?De.checked=!1:De.type!=="submit"&&De.type!=="button"&&De.type!=="hidden"&&(De.value="")}else Se.tagName==="TEXTAREA"?Se.value="":Se.tagName==="SELECT"&&(Se.selectedIndex=0);Se.removeAttribute("data-vff-confirmed"),Se.style.outline="",Se.style.outlineOffset=""}),document.querySelectorAll(".vff-field-badge").forEach(fe=>fe.remove()),window.location.reload()};Y.useEffect(()=>{const se=Ue.current;if(!se)return;const fe=We=>{if(!We.target.closest(".vff-panel-header"))return;Fe.current=!0;const ti=se.getBoundingClientRect();Me.current={x:We.clientX-ti.left,y:We.clientY-ti.top},We.preventDefault()},Se=We=>{if(!Fe.current)return;const Dt=We.clientX-Me.current.x,ti=We.clientY-Me.current.y;se.style.left=`${Dt}px`,se.style.top=`${ti}px`,se.style.right="auto"},De=()=>{Fe.current=!1};return se.addEventListener("mousedown",fe),document.addEventListener("mousemove",Se),document.addEventListener("mouseup",De),()=>{se.removeEventListener("mousedown",fe),document.removeEventListener("mousemove",Se),document.removeEventListener("mouseup",De)}},[]);const Pe=H.toLowerCase()==="connected"||H.toLowerCase().startsWith("connected ")||H.toLowerCase()==="switching_section"||H.toLowerCase().startsWith("reconnecting"),je=H.toLowerCase()==="paused";H.toLowerCase().includes("warming");const mt=H.toLowerCase()==="ready";return S.fields.length,S.fields.filter(se=>se.required).length,K.jsxs(K.Fragment,{children:[Ce&&K.jsx(pp,{intervalMs:3e3,onDismiss:()=>{console.log("[VoiceOverlay] 🌍 User dismissed greeting carousel"),Ae(!1),Qe.current=!0}}),K.jsxs("div",{ref:Ue,className:`vff-panel ${Ne?"collapsed":""}`,children:[K.jsxs("div",{className:"vff-panel-header",children:[K.jsx("span",{className:"vff-title",children:"🎤 Voice Form Filler"}),K.jsxs("div",{style:{display:"flex",gap:"8px"},children:[K.jsx("button",{className:"vff-collapse",onClick:()=>ht(!Ne),"aria-label":Ne?"Expand":"Collapse",children:Ne?"▼":"▲"}),v&&K.jsx("button",{className:"vff-close",onClick:v,"aria-label":"Close",children:"×"})]})]}),K.jsxs("div",{className:"vff-panel-body",children:[K.jsxs("div",{className:"vff-status",children:[K.jsx("span",{className:"vff-status-icon",children:Pe?"🟢":H==="idle_timeout"?"⏱️":"⚪"}),K.jsx("span",{className:"vff-status-text",children:H==="idle_timeout"?"Disconnected due to inactivity":H}),rt.userSpeaking&&!q&&K.jsxs("span",{className:"vff-vad-indicator",title:"Voice detected",children:[K.jsx("span",{className:"vff-vad-light"}),K.jsx("span",{className:"vff-vad-label",children:"Listening"})]})]}),!mt&&H!=="disconnected"&&H!=="paused"&&K.jsxs("div",{className:"vff-language-selector",children:[K.jsx("label",{htmlFor:"vff-language-select",className:"vff-language-label",children:"🌍 Spoken Language"}),K.jsxs("select",{id:"vff-language-select",className:"vff-language-select",value:ve,onChange:Te,children:[K.jsx("option",{value:"",children:"Select language..."}),fp.map(se=>K.jsx("option",{value:se.name,children:se.nativeName},se.name))]})]}),K.jsxs("div",{className:"vff-section-nav",children:[K.jsxs("div",{className:"vff-section-display",onClick:()=>V(!j),children:[K.jsxs("span",{className:"vff-section-label",children:["Section ",Q," of ",f.total_sections,": ",f.sections[Q-1]?.section_label]}),K.jsx("span",{className:"vff-dropdown-arrow",children:j?"▲":"▼"})]}),K.jsxs("div",{className:"vff-field-counter",children:["📊 ",D.filled," of ",D.total," fields completed"]}),j&&K.jsx("div",{className:"vff-section-dropdown",children:f.sections.map(se=>K.jsxs("div",{className:`vff-section-item ${Q===se.section_number?"active":""}`,onClick:async()=>{if(C&&(V(!1),se.section_number!==Q))try{P(null),G(se.section_number),X("Reconnecting to section "+se.section_number);const fe=_e.load();if(fe){const Se=_e.switchSection(fe,se.section_number),De=_e.getSectionFieldCount(Se);B(De)}await C.switchSection(se.section_number)}catch(fe){console.error("[VoiceOverlay] Section switch error:",fe),P(fe instanceof Error?fe.message:"Section switch failed")}},children:[K.jsx("span",{className:"vff-section-status",children:ee.has(se.section_number)?"✓":Q===se.section_number?"→":"○"}),K.jsxs("span",{className:"vff-section-text",children:[se.section_number,". ",se.section_label]})]},se.section_number))})]}),K.jsxs("div",{className:"vff-controls",children:[!Pe&&!je?K.jsx("button",{className:"vff-button vff-connect",onClick:Ze,children:H==="idle_timeout"?"Reconnect to Voice":"Connect to Voice"}):je?K.jsx("button",{className:"vff-button vff-resume",onClick:Ze,children:"▶️ Resume"}):K.jsx("button",{className:"vff-button vff-pause",onClick:Vt,children:"⏸️ Pause"}),K.jsx("button",{className:"vff-button vff-clear-form",onClick:qe,children:"🗑️ Clear Form"})]}),(J||A)&&K.jsxs("div",{className:"vff-error",children:[A&&K.jsxs("div",{children:[K.jsx("strong",{children:"🎤 Microphone Error:"})," ",A]}),J&&K.jsx("div",{children:J})]})]}),K.jsx("style",{children:`
				.vff-panel {
					position: fixed;
					top: 20px;
					right: 20px;
					width: 320px;
					background: white;
					border-radius: 12px;
					box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
					font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
					z-index: 10000;
					transition: height 0.3s ease;
				}

				.vff-panel.collapsed .vff-panel-body {
					display: none;
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

				.vff-collapse,
				.vff-close {
					background: none;
					border: none;
					color: white;
					font-size: 20px;
					cursor: pointer;
					padding: 0;
					width: 24px;
					height: 24px;
					line-height: 1;
					opacity: 0.8;
					transition: opacity 0.2s;
				}

				.vff-collapse:hover,
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

				.vff-language-selector {
					margin-bottom: 16px;
					padding: 12px;
					background: #f0f9ff;
					border-radius: 8px;
					border: 1px solid #bae6fd;
				}

				.vff-language-label {
					display: block;
					font-size: 13px;
					font-weight: 600;
					color: #0369a1;
					margin-bottom: 8px;
				}

				.vff-language-select {
					width: 100%;
					padding: 8px 12px;
					font-size: 14px;
					border: 1px solid #7dd3fc;
					border-radius: 6px;
					background: white;
					color: #0c4a6e;
					cursor: pointer;
					transition: all 0.2s;
				}

				.vff-language-select:hover {
					border-color: #0ea5e9;
					box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.1);
				}

				.vff-language-select:focus {
					outline: none;
					border-color: #0284c7;
					box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.2);
				}

				.vff-status-icon {
					font-size: 20px;
				}

				.vff-status-text {
					font-size: 14px;
					font-weight: 500;
					flex: 1;
				}

				/* VAD Speech Detection Indicator */
				.vff-vad-indicator {
					display: flex;
					align-items: center;
					gap: 6px;
					padding: 4px 12px;
					background: #d1fae5;
					border-radius: 12px;
					border: 1px solid #10b981;
				}

				.vff-vad-label {
					font-size: 12px;
					color: #059669;
					font-weight: 600;
					text-transform: uppercase;
					letter-spacing: 0.5px;
				}

				.vff-vad-light {
					display: inline-block;
					width: 10px;
					height: 10px;
					border-radius: 50%;
					background: #10b981;
					animation: vff-vad-pulse 1s ease-in-out infinite;
					box-shadow: 0 0 4px #10b981;
				}

				@keyframes vff-vad-pulse {
					0%, 100% {
						opacity: 1;
						box-shadow: 0 0 4px #10b981;
					}
					50% {
						opacity: 0.6;
						box-shadow: 0 0 12px #10b981, 0 0 20px rgba(16, 185, 129, 0.4);
					}
				}

				.vff-section-nav {
					position: relative;
					margin-bottom: 16px;
					padding: 12px;
					background: #f0f4ff;
					border-radius: 8px;
					border: 1px solid #d0dbff;
				}

				.vff-section-display {
					display: flex;
					justify-content: space-between;
					align-items: center;
					cursor: pointer;
					padding: 4px;
					border-radius: 4px;
					transition: background 0.2s;
				}

				.vff-section-display:hover {
					background: rgba(102, 126, 234, 0.1);
				}

				.vff-section-label {
					font-size: 13px;
					font-weight: 600;
					color: #4c51bf;
					flex: 1;
				}

				.vff-dropdown-arrow {
					font-size: 10px;
					color: #667eea;
					margin-left: 8px;
				}

				.vff-field-counter {
					font-size: 12px;
					color: #666;
					margin-top: 8px;
					font-weight: 500;
				}

				.vff-section-dropdown {
					position: absolute;
					top: 100%;
					left: 0;
					right: 0;
					background: white;
					border: 1px solid #d0dbff;
					border-radius: 8px;
					margin-top: 4px;
					max-height: 300px;
					overflow-y: auto;
					box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
					z-index: 1000;
				}

				.vff-section-item {
					display: flex;
					align-items: center;
					gap: 8px;
					padding: 10px 12px;
					cursor: pointer;
					transition: background 0.2s;
					border-bottom: 1px solid #f0f0f0;
				}

				.vff-section-item:last-child {
					border-bottom: none;
				}

				.vff-section-item:hover {
					background: #f8f9ff;
				}

				.vff-section-item.active {
					background: #e0e7ff;
					font-weight: 600;
				}

				.vff-section-status {
					font-size: 14px;
					width: 20px;
					text-align: center;
				}

				.vff-section-text {
					font-size: 13px;
					flex: 1;
				}

				.vff-controls {
					display: flex;
					flex-direction: column;
					gap: 8px;
					margin-bottom: 16px;
				}

				.vff-ptt-toggle {
					padding: 12px;
					background: #f8f9ff;
					border-radius: 8px;
					border: 1px solid #d0dbff;
				}

				.vff-toggle-label-row {
					display: flex;
					align-items: center;
					justify-content: center;
					gap: 12px;
				}

				.vff-toggle-mode-label {
					font-size: 13px;
					font-weight: 600;
					color: #6b7280;
					min-width: 60px;
					text-align: center;
				}

				.vff-toggle-switch {
					position: relative;
					display: inline-block;
					width: 50px;
					height: 24px;
				}

				.vff-toggle-switch input {
					opacity: 0;
					width: 0;
					height: 0;
				}

				.vff-toggle-slider {
					position: absolute;
					cursor: pointer;
					top: 0;
					left: 0;
					right: 0;
					bottom: 0;
					background-color: #667eea;
					transition: 0.3s;
					border-radius: 24px;
				}

				.vff-toggle-slider:before {
					position: absolute;
					content: "";
					height: 18px;
					width: 18px;
					left: 3px;
					bottom: 3px;
					background-color: white;
					transition: 0.3s;
					border-radius: 50%;
					box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
				}

				.vff-toggle-switch input:checked + .vff-toggle-slider {
					background-color: #4c51bf;
				}

				.vff-toggle-switch input:checked + .vff-toggle-slider:before {
					transform: translateX(26px);
				}

				.vff-toggle-switch input:focus + .vff-toggle-slider {
					box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.3);
				}

				.vff-ptt-hint {
					display: block;
					margin-top: 6px;
					font-size: 11px;
					color: #666;
					font-style: italic;
					text-align: center;
				}

				.vff-ptt-button {
					background: linear-gradient(135deg, #4c51bf 0%, #667eea 100%);
					color: white;
					font-size: 15px;
					padding: 16px;
					user-select: none;
					-webkit-user-select: none;
					-webkit-touch-callout: none;
				}

				.vff-ptt-button:active,
				.vff-ptt-button.active {
					background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
					transform: scale(0.98);
				}

				.vff-ptt-button:hover:not(:active) {
					background: linear-gradient(135deg, #5a67d8 0%, #7c3aed 100%);
					transform: translateY(-1px);
				}

				.vff-button {
					padding: 12px 16px;
					border: none;
					border-radius: 8px;
					font-size: 14px;
					font-weight: 600;
					cursor: pointer;
					transition: all 0.2s;
					font-family: inherit;
				}

				.vff-connect {
					background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
					color: white;
				}

				.vff-connect:hover {
					transform: translateY(-1px);
					box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
				}

				.vff-pause {
					background: #f59e0b;
					color: white;
				}

				.vff-pause:hover {
					background: #d97706;
					transform: translateY(-1px);
				}

				.vff-resume {
					background: #10b981;
					color: white;
				}

				.vff-resume:hover {
					background: #059669;
					transform: translateY(-1px);
				}

				.vff-disconnect {
					background: #dc3545;
					color: white;
				}

				.vff-disconnect:hover {
					background: #c82333;
					transform: translateY(-1px);
				}

				.vff-clear-form {
					background: #6c757d;
					color: white;
				}

				.vff-clear-form:hover {
					background: #5a6268;
				}

				.vff-error {
					padding: 12px;
					background: #f8d7da;
					border: 1px solid #f5c6cb;
					border-radius: 8px;
					color: #721c24;
					font-size: 13px;
					margin-bottom: 16px;
				}

				.vff-info {
					text-align: center;
					opacity: 0.6;
				}

				.vff-info small {
					font-size: 12px;
					line-height: 1.4;
				}

				/* Mobile responsiveness */
				@media (max-width: 768px) {
					.vff-panel {
						width: calc(100% - 32px);
						max-width: 320px;
						right: 16px;
						top: 16px;
					}
				}
			`})]})]})}function ih({schema:S,sectionIndex:f,wsUrl:b,connectionManager:v,status:k,sharedStream:w,streamError:I}){const[A,C]=Y.useState(v||null),Z=Y.useRef(v||null),[W,H]=Y.useState(k||"Ready"),[X,J]=Y.useState(null),[P,Q]=Y.useState(!1),[G,ee]=Y.useState(1),[R,D]=Y.useState(new Set),[B,j]=Y.useState({filled:0,total:12}),[V,q]=Y.useState(!1),[ne,ye]=Y.useState(!1),[ue,Ce]=Y.useState(!1),Ae=Y.useRef(!1),[Ne,ht]=Y.useState(""),Qe=Y.useRef(w||null),ve=Y.useRef(null),Ee=Y.useRef(!1),Ue=450;Y.useEffect(()=>{Qe.current=w||null,console.log("[VoiceOverlayMobile] 🔗 Using shared stream from parent:",!!w)},[w]);const Fe=Y.useMemo(()=>({onSpeechStart:()=>{if(V)return;console.log("[VFF VAD] 🎤 User speech started - buffering audio..."),ve.current=Date.now(),Ee.current=!1,ue&&(console.log("[VoiceOverlayMobile] 🌍 User speaking - hiding greeting carousel"),Ce(!1),Ae.current=!0);const Te=A?.getAudioManager();Te&&Te.isSpeaking()&&(Te.pauseAudioContext(),console.log("[VFF VAD Mobile] 🔇 Tentative pause - waiting to confirm speech duration")),setTimeout(()=>{const qe=ve.current?Date.now()-ve.current:0;ve.current!==null&&qe>=Ue&&(console.log(`[VFF VAD Mobile] ✅ Valid speech detected (${qe}ms) - starting turn`),Ee.current=!0,A&&(A.sendActivityStart(),console.log("[VFF VAD Mobile] 📤 Sent activity_start signal (user turn begins)")),Te&&Te.setVADActive(!0),Te?.isSpeaking()&&Te&&(console.log("[VFF VAD Mobile] 🔇 Flushing Gemini audio queue (full barge-in)"),Te.flushAudioQueue()))},Ue)},onSpeechEnd:Te=>{if(V)return;const qe=ve.current?Date.now()-ve.current:0,Pe=A?.getAudioManager();Ee.current?(console.log(`[VFF VAD Mobile] ✅ Valid turn completed (${qe}ms) - closing turn`),Pe&&Pe.setVADActive(!1),A?.onVADSpeechEnd()):(console.log(`[VFF VAD Mobile] ⚠️ Speech too short (${qe}ms < ${Ue}ms) - no turn started, false positive`),Pe&&(Pe.resumeAudioContext(),console.log("[VFF VAD Mobile] 🔊 Resuming audio - false positive"))),ve.current=null,Ee.current=!1},onVADMisfire:()=>{console.log("[VFF VAD] ⚠️ VAD misfire detected"),ve.current=null}}),[V,A]),Me=Y.useMemo(()=>({sharedStream:Qe.current,callbacks:Fe}),[Fe,w]),ze=cp(Me);Y.useEffect(()=>{if(v){Z.current=v,C(v);return}if(Z.current)return;const Te=_e.initWithSections(S,f),qe=qr(Te.schema,Pe=>{H(Pe),J(null)},"English",w||void 0);return Z.current=qe,C(qe),()=>{v||(Z.current&&(Z.current.disconnect(),Z.current=null),C(null))}},[S,f,v]),Y.useEffect(()=>{k!==void 0&&H(k)},[k]),Y.useEffect(()=>{const Te=W.toLowerCase()==="connected"||W.toLowerCase().startsWith("connected ");Te&&!Ae.current&&!ue&&(console.log("[VoiceOverlayMobile] 🌍 Connected - showing greeting carousel"),Ce(!0)),!Te&&Ae.current&&(Ae.current=!1)},[W,ue]),Y.useEffect(()=>{const qe=(W.toLowerCase()==="connected"||W.toLowerCase().startsWith("connected "))&&!V&&!ze.loading&&!ze.errored;qe&&!ze.userSpeaking?(console.log("[VoiceOverlayMobile] 🎙️ Starting VAD (conditions met)"),ze.start()):!qe&&ze.userSpeaking&&(console.log("[VoiceOverlayMobile] ⏸️ Pausing VAD (conditions not met)"),ze.pause()),ze.errored&&J(`Voice detection error: ${ze.errored}`)},[W,V,ze.loading,ze.errored,ze.userSpeaking]),Y.useEffect(()=>(window.vffOnAudioPlaybackStart=()=>{ue&&(console.log("[VoiceOverlayMobile] 🌍 Gemini speaking - hiding greeting carousel"),Ce(!1),Ae.current=!0)},()=>{delete window.vffOnAudioPlaybackStart}),[ue]);const Ye=async Te=>{const qe=Te.target.value;ht(qe),console.log("[VoiceOverlayMobile] Language changed to:",qe);const Pe=W.toLowerCase()==="connected"||W.toLowerCase().startsWith("connected ");if(A&&Pe)try{const je=_e.load();if(!je){console.error("[VoiceOverlayMobile] No state found for next field hint");return}const mt=Vr(je.schema,je.current_values),se=mt?Lr(mt,je.schema):"all fields are complete";A.changeSpokenLanguage(qe,se)}catch(je){console.error("[VoiceOverlayMobile] Failed to change spoken language:",je),J(je instanceof Error?je.message:"Failed to change language")}},tt=async()=>{if(A)try{if(J(null),A.isPaused()){await A.resume();return}await A.connect();const Te=5e3,qe=Date.now();for(;Date.now()-qe<Te;){const je=A.getStatus();if(je==="connected"||je==="switching_section"){console.log("[VoiceOverlayMobile] ✅ WebSocket connected, setting up audio..."),H("Setting up audio..."),await A.startRecording(),H("connected"),console.log("[VoiceOverlayMobile] ✅ Audio ready - fully connected");break}await new Promise(se=>setTimeout(se,50))}const Pe=A.getStatus();Pe!=="connected"&&Pe!=="switching_section"&&(console.error("[VoiceOverlayMobile] ❌ Connection timeout, final status:",Pe),J("Connection timed out - please try again"))}catch(Te){console.error("[VoiceOverlay] Connection error:",Te),J(Te instanceof Error?Te.message:"Connection failed")}},ct=()=>{A&&(A.pause(),ze.pause())};Y.useEffect(()=>{const Te=_e.initWithSections(S,f);ee(Te.current_section||1),D(Te.completed_sections||new Set);const qe=_e.getSectionFieldCount(Te);j(qe)},[S,f]),Y.useEffect(()=>{const Te=setInterval(()=>{const qe=_e.load();if(qe){const Pe=_e.getSectionFieldCount(qe);j(Pe)}},1e3);return()=>clearInterval(Te)},[]);const st=W.toLowerCase()==="connected"||W.toLowerCase().startsWith("connected "),it=W.toLowerCase()==="paused",rt=W.toLowerCase().includes("warming"),Ze=W.toLowerCase()==="ready",Vt=S.fields.length,pt=S.fields.filter(Te=>Te.required).length,Mt=st?"#10b981":it||rt?"#f59e0b":Ze?"#3b82f6":"#6b7280";return K.jsxs(K.Fragment,{children:[ue&&K.jsx(pp,{intervalMs:3e3,onDismiss:()=>{console.log("[VoiceOverlayMobile] 🌍 User dismissed greeting carousel"),Ce(!1),Ae.current=!0}}),K.jsxs("div",{className:"vff-fab",onClick:()=>Q(!P),children:[K.jsx("div",{className:"vff-fab-pulse",style:{borderColor:Mt}}),ze.userSpeaking&&!V&&K.jsx("div",{className:"vff-fab-vad-badge",children:K.jsx("div",{className:"vff-fab-vad-dot"})}),K.jsx("div",{className:"vff-fab-icon",style:{background:Mt},children:"🎤"})]}),P&&K.jsxs("div",{className:"vff-panel-mobile",children:[K.jsxs("div",{className:"vff-panel-header",children:[K.jsx("span",{className:"vff-title",children:"Voice Form Filler"}),K.jsx("button",{className:"vff-close",onClick:()=>Q(!1),children:"×"})]}),K.jsxs("div",{className:"vff-panel-body",children:[K.jsxs("div",{className:"vff-status-compact",children:[K.jsx("div",{className:"vff-status-dot",style:{background:W==="idle_timeout"?"#6b7280":Mt}}),K.jsx("span",{className:"vff-status-text",children:W==="idle_timeout"?"Idle timeout":W})]}),!Ze&&W!=="disconnected"&&W!=="paused"&&K.jsxs("div",{className:"vff-language-selector-mobile",children:[K.jsx("label",{htmlFor:"vff-language-select-mobile",className:"vff-language-label-mobile",children:"🌍 Spoken Language"}),K.jsxs("select",{id:"vff-language-select-mobile",className:"vff-language-select-mobile",value:Ne,onChange:Ye,children:[K.jsx("option",{value:"",children:"Select language..."}),fp.map(Te=>K.jsx("option",{value:Te.name,children:Te.nativeName},Te.name))]})]}),!st&&!it?K.jsx("button",{className:"vff-action-btn vff-connect-btn",onClick:tt,children:W==="idle_timeout"?"🔄 Reconnect":"🎙️ Connect"}):it?K.jsx("button",{className:"vff-action-btn vff-resume-btn",onClick:tt,children:"▶️ Resume"}):K.jsx("button",{className:"vff-action-btn vff-pause-btn",onClick:ct,children:"⏸️ Pause"}),"						",(X||I)&&K.jsxs("div",{className:"vff-error-compact",children:[I&&K.jsxs("div",{children:[K.jsx("strong",{children:"🎤 Mic Error:"})," ",I]}),X&&K.jsx("div",{children:X})]}),K.jsxs("div",{className:"vff-info-compact",children:[Vt," fields · ",pt," required"]})]})]}),K.jsx("style",{children:`
				/* Floating Action Button */
				.vff-fab {
					position: fixed;
					bottom: 20px;
					right: 20px;
					width: 56px;
					height: 56px;
					cursor: pointer;
					z-index: 9999;
					filter: drop-shadow(0 4px 12px rgba(0, 0, 0, 0.15));
				}

				.vff-fab-pulse {
					position: absolute;
					width: 100%;
					height: 100%;
					border-radius: 50%;
					border: 3px solid;
					animation: vff-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
				}

				@keyframes vff-pulse {
					0%, 100% {
						opacity: 1;
						transform: scale(1);
					}
					50% {
						opacity: 0.3;
						transform: scale(1.1);
					}
				}

				.vff-fab-icon {
					position: absolute;
					width: 100%;
					height: 100%;
					border-radius: 50%;
					display: flex;
					align-items: center;
					justify-content: center;
					font-size: 24px;
					transition: transform 0.2s;
				}

				.vff-fab:active .vff-fab-icon {
					transform: scale(0.9);
				}

				/* VAD Speech Detection Badge - Small green dot in top-right */
				.vff-fab-vad-badge {
					position: absolute;
					top: -4px;
					right: -4px;
					width: 20px;
					height: 20px;
					background: white;
					border-radius: 50%;
					display: flex;
					align-items: center;
					justify-content: center;
					z-index: 10;
					box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
				}

				.vff-fab-vad-dot {
					width: 12px;
					height: 12px;
					border-radius: 50%;
					background: #10b981;
					animation: vff-vad-pulse 1s ease-in-out infinite;
				}

				@keyframes vff-vad-pulse {
					0%, 100% {
						opacity: 1;
						transform: scale(1);
						box-shadow: 0 0 4px #10b981;
					}
					50% {
						opacity: 0.6;
						transform: scale(1.2);
						box-shadow: 0 0 8px #10b981;
					}
				}

				/* Compact Panel */
				.vff-panel-mobile {
					position: fixed;
					bottom: 90px;
					right: 20px;
					width: 240px;
					background: white;
					border-radius: 16px;
					box-shadow: 0 8px 24px rgba(0, 0, 0, 0.2);
					z-index: 9998;
					font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
					animation: vff-slide-up 0.2s ease-out;
				}

				@keyframes vff-slide-up {
					from {
						opacity: 0;
						transform: translateY(10px);
					}
					to {
						opacity: 1;
						transform: translateY(0);
					}
				}

				.vff-panel-header {
					display: flex;
					justify-content: space-between;
					align-items: center;
					padding: 12px 16px;
					border-bottom: 1px solid #e5e7eb;
				}

				.vff-title {
					font-weight: 600;
					font-size: 14px;
					color: #111827;
				}

				.vff-close {
					background: none;
					border: none;
					font-size: 24px;
					color: #6b7280;
					cursor: pointer;
					padding: 0;
					width: 24px;
					height: 24px;
					line-height: 1;
				}

				.vff-panel-body {
					padding: 16px;
					display: flex;
					flex-direction: column;
					gap: 12px;
				}

				.vff-status-compact {
					display: flex;
					align-items: center;
					gap: 8px;
					padding: 8px 12px;
					background: #f9fafb;
					border-radius: 8px;
					margin-bottom: 12px;
				}

				.vff-status-dot {
					width: 8px;
					height: 8px;
					border-radius: 50%;
				}

				.vff-status-text {
					font-size: 12px;
					font-weight: 500;
					color: #374151;
				}

				.vff-language-selector-mobile {
					margin-bottom: 12px;
					padding: 10px;
					background: #f0f9ff;
					border-radius: 8px;
					border: 1px solid #bae6fd;
				}

				.vff-language-label-mobile {
					display: block;
					font-size: 12px;
					font-weight: 600;
					color: #0369a1;
					margin-bottom: 6px;
				}

				.vff-language-select-mobile {
					width: 100%;
					padding: 6px 10px;
					font-size: 13px;
					border: 1px solid #7dd3fc;
					border-radius: 6px;
					background: white;
					color: #0c4a6e;
					cursor: pointer;
					transition: all 0.2s;
				}

				.vff-language-select-mobile:hover {
					border-color: #0ea5e9;
					box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.1);
				}

				.vff-language-select-mobile:focus {
					outline: none;
					border-color: #0284c7;
					box-shadow: 0 0 0 3px rgba(14, 165, 233, 0.2);
				}

				.vff-ptt-toggle-mobile {
					padding: 10px 12px;
					background: #f8f9ff;
					border-radius: 8px;
					border: 1px solid #d0dbff;
				}

				.vff-toggle-label-row {
					display: flex;
					align-items: center;
					justify-content: center;
					gap: 10px;
				}

				.vff-toggle-mode-label {
					font-size: 12px;
					font-weight: 600;
					color: #6b7280;
					min-width: 50px;
					text-align: center;
				}

				.vff-toggle-switch {
					position: relative;
					display: inline-block;
					width: 44px;
					height: 22px;
				}

				.vff-toggle-switch input {
					opacity: 0;
					width: 0;
					height: 0;
				}

				.vff-toggle-slider {
					position: absolute;
					cursor: pointer;
					top: 0;
					left: 0;
					right: 0;
					bottom: 0;
					background-color: #667eea;
					transition: 0.3s;
					border-radius: 22px;
				}

				.vff-toggle-slider:before {
					position: absolute;
					content: "";
					height: 16px;
					width: 16px;
					left: 3px;
					bottom: 3px;
					background-color: white;
					transition: 0.3s;
					border-radius: 50%;
					box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
				}

				.vff-toggle-switch input:checked + .vff-toggle-slider {
					background-color: #4c51bf;
				}

				.vff-toggle-switch input:checked + .vff-toggle-slider:before {
					transform: translateX(22px);
				}

				.vff-toggle-switch input:focus + .vff-toggle-slider {
					box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.3);
				}

				.vff-action-btn {
					width: 100%;
					padding: 12px;
					border: none;
					border-radius: 8px;
					font-size: 14px;
					font-weight: 600;
					cursor: pointer;
					transition: all 0.2s;
					user-select: none;
					-webkit-user-select: none;
					-webkit-touch-callout: none;
				}

				.vff-ptt-btn {
					background: linear-gradient(135deg, #4c51bf 0%, #667eea 100%);
					color: white;
					font-size: 14px;
					padding: 14px;
				}

				.vff-ptt-btn:active,
				.vff-ptt-btn.active {
					background: linear-gradient(135deg, #dc2626 0%, #ef4444 100%);
					transform: scale(0.95);
				}

				.vff-connect-btn {
					background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
					color: white;
				}

				.vff-connect-btn:active {
					transform: scale(0.98);
				}

				.vff-pause-btn {
					background: #f59e0b;
					color: white;
				}

				.vff-pause-btn:active {
					transform: scale(0.98);
				}

				.vff-resume-btn {
					background: #10b981;
					color: white;
				}

				.vff-resume-btn:active {
					transform: scale(0.98);
				}

				.vff-disconnect-btn {
					background: #ef4444;
					color: white;
				}

				.vff-disconnect-btn:active {
					transform: scale(0.98);
				}

				.vff-error-compact {
					padding: 8px 12px;
					background: #fef2f2;
					border: 1px solid #fecaca;
					border-radius: 8px;
					color: #991b1b;
					font-size: 12px;
				}

				.vff-info-compact {
					text-align: center;
					font-size: 11px;
					color: #6b7280;
				}

				/* Mobile Adjustments */
				@media (max-width: 480px) {
					.vff-panel-mobile {
						right: 10px;
						width: calc(100vw - 20px);
						max-width: 280px;
					}

					.vff-fab {
						bottom: 16px;
						right: 16px;
					}
				}
			`})]})}function nh(){const S=Y.useRef(null),[f,b]=Y.useState(null),[v,k]=Y.useState(null),[w,I]=Y.useState(!1),[A,C]=Y.useState(!1),[Z,W]=Y.useState(!1),[H,X]=Y.useState(null),J=Y.useRef(null),[P,Q]=Y.useState("Ready"),[G,ee]=Y.useState(null),[R,D]=Y.useState(null),[B,j]=Y.useState(!1);Y.useEffect(()=>{const q=()=>{C(window.innerWidth<=768)};return q(),window.addEventListener("resize",q),()=>window.removeEventListener("resize",q)},[]),Y.useEffect(()=>{let q=!0;async function ne(){try{console.log("[AdultIntakeDemo] 🎤 Creating shared audio stream early...");const ye=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:!0,noiseSuppression:!0,autoGainControl:!0,channelCount:1,sampleRate:16e3}}),ue=ye.getAudioTracks()[0];if(ue){const Ce=ue.getSettings();console.log("[AdultIntakeDemo] 🔍 Actual audio settings:",{sampleRate:Ce.sampleRate,channelCount:Ce.channelCount,echoCancellation:Ce.echoCancellation,noiseSuppression:Ce.noiseSuppression,autoGainControl:Ce.autoGainControl})}q?(ee(ye),j(!0),console.log("[AdultIntakeDemo] ✅ Shared stream ready (AEC enabled)")):ye.getTracks().forEach(Ce=>Ce.stop())}catch(ye){if(console.error("[AdultIntakeDemo] ❌ Failed to create shared stream:",ye),q){const ue=ye instanceof Error?ye.message:"Microphone access denied";D(ue),j(!0)}}}return ne(),()=>{q=!1,G&&(console.log("[AdultIntakeDemo] 🧹 Cleaning up shared stream"),G.getTracks().forEach(ye=>ye.stop()))}},[]),Y.useEffect(()=>{const q=ne=>{if(Z)return;const ye=document.querySelectorAll("input, textarea, select");let ue=!1;for(const Ce of ye){const Ae=Ce;if(Ae.tagName==="INPUT"){const Ne=Ae;Ne.type==="checkbox"||Ne.type==="radio"?Ne.checked&&(ue=!0):Ne.type!=="submit"&&Ne.type!=="button"&&Ne.type!=="hidden"&&Ne.value.trim()&&(ue=!0)}else Ae.tagName==="TEXTAREA"?Ae.value.trim()&&(ue=!0):Ae.tagName==="SELECT"&&Ae.selectedIndex>0&&(ue=!0);if(ue)break}ue&&(ne.preventDefault(),ne.returnValue="")};return window.addEventListener("beforeunload",q),()=>window.removeEventListener("beforeunload",q)},[w,Z]),Y.useEffect(()=>{(async()=>{try{const ye=await(await fetch("./adult_intake_demo.html")).text(),Ce=new DOMParser().parseFromString(ye,"text/html"),Ae=Ce.querySelector("style")?.textContent||"",Ne=Ce.querySelector(".clinic-header")?.outerHTML||"",ht=Ce.querySelector(".form-container")?.outerHTML||"";if(S.current){const Fe=document.createElement("style");Fe.textContent=Ae,document.head.appendChild(Fe),S.current.innerHTML=Ne+ht,I(!0)}const ve=await(await fetch("./adult_intake_demo_schema.json")).json();ve.form_metadata.url=window.location.href;const Ue=await(await fetch("./adult_intake_sections_index.json")).json();b(ve),k(Ue),setTimeout(()=>{const Fe=document.querySelector("form");Fe&&(Fe.addEventListener("submit",Me=>(Me.preventDefault(),W(!0),window.location.href="thank-you.html",!1)),Fe.addEventListener("keydown",Me=>{if(Me.key==="Enter"){const ze=Me.target;(ze.tagName==="INPUT"||ze.tagName==="TEXTAREA")&&(Me.preventDefault(),ze.blur())}}))},100)}catch(ne){console.error("Failed to load form, schema, or section index:",ne)}})()},[]),Y.useEffect(()=>{if(!f||!v||!B||J.current)return;const q=_e.initWithSections(f,v),ne=qr(q.schema,ye=>{Q(ye)},"English",G||void 0);return J.current=ne,X(ne),()=>{J.current&&(J.current.disconnect(),J.current=null),X(null)}},[f,v,B,G]);const V="ws://localhost:8000/ws/fill";return K.jsxs("div",{className:"demo-container",children:[K.jsx("div",{ref:S,className:"form-content"}),w&&f&&v&&H&&B&&(A?K.jsx(ih,{schema:f,sectionIndex:v,wsUrl:V,connectionManager:H,sharedStream:G,streamError:R,status:P}):K.jsx(th,{schema:f,sectionIndex:v,wsUrl:V,connectionManager:H,status:P,sharedStream:G,streamError:R}))]})}Nr.createRoot(document.getElementById("root")).render(K.jsx(nh,{}));
