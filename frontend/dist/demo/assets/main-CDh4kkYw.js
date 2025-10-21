var wf=Object.defineProperty;var bf=(E,f,b)=>f in E?wf(E,f,{enumerable:!0,configurable:!0,writable:!0,value:b}):E[f]=b;var He=(E,f,b)=>bf(E,typeof f!="symbol"?f+"":f,b);import{r as Z,a as vf,c as et}from"./vendor-react-CfsYHMYl.js";(function(){const f=document.createElement("link").relList;if(f&&f.supports&&f.supports("modulepreload"))return;for(const S of document.querySelectorAll('link[rel="modulepreload"]'))v(S);new MutationObserver(S=>{for(const y of S)if(y.type==="childList")for(const C of y.addedNodes)C.tagName==="LINK"&&C.rel==="modulepreload"&&v(C)}).observe(document,{childList:!0,subtree:!0});function b(S){const y={};return S.integrity&&(y.integrity=S.integrity),S.referrerPolicy&&(y.referrerPolicy=S.referrerPolicy),S.crossOrigin==="use-credentials"?y.credentials="include":S.crossOrigin==="anonymous"?y.credentials="omit":y.credentials="same-origin",y}function v(S){if(S.ep)return;S.ep=!0;const y=b(S);fetch(S.href,y)}})();var tp={exports:{}},dn={};/**
 * @license React
 * react-jsx-runtime.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var $f=Z,xf=Symbol.for("react.element"),Sf=Symbol.for("react.fragment"),kf=Object.prototype.hasOwnProperty,Tf=$f.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,Ef={key:!0,ref:!0,__self:!0,__source:!0};function ip(E,f,b){var v,S={},y=null,C=null;b!==void 0&&(y=""+b),f.key!==void 0&&(y=""+f.key),f.ref!==void 0&&(C=f.ref);for(v in f)kf.call(f,v)&&!Ef.hasOwnProperty(v)&&(S[v]=f[v]);if(E&&E.defaultProps)for(v in f=E.defaultProps,f)S[v]===void 0&&(S[v]=f[v]);return{$$typeof:xf,type:E,key:y,ref:C,props:S,_owner:Tf.current}}dn.Fragment=Sf;dn.jsx=ip;dn.jsxs=ip;tp.exports=dn;var Q=tp.exports,jr={},Gc=vf;jr.createRoot=Gc.createRoot,jr.hydrateRoot=Gc.hydrateRoot;class ve{static init(f){const b=this.load();if(b&&b.schema.form_metadata.url===f.form_metadata.url&&Date.now()-b.last_updated<60*60*1e3)return b;const v={schema:f,current_values:{},last_updated:Date.now()};return this.save(v),v}static load(){try{const f=sessionStorage.getItem(this.STORAGE_KEY);if(!f)return null;const b=JSON.parse(f);return b.completed_sections&&Array.isArray(b.completed_sections)&&(b.completed_sections=new Set(b.completed_sections)),b}catch{return null}}static save(f){try{f.last_updated=Date.now();const b={...f,completed_sections:f.completed_sections?Array.from(f.completed_sections):void 0};sessionStorage.setItem(this.STORAGE_KEY,JSON.stringify(b))}catch{}}static updateFieldValue(f,b,v,S){const y=f.current_values[b]||{value:null,confirmed:!1},C=S?.confirmed!==void 0?S.confirmed:typeof y.confirmed=="boolean"?y.confirmed:!1,A={...f,current_values:{...f.current_values,[b]:{...y,value:v,confirmed:C,lastModified:Date.now()}}};return this.save(A),A}static markConfirmed(f,b){const v={...f,current_values:{...f.current_values}};for(const S of b)v.current_values[S]&&(v.current_values[S]={...v.current_values[S],confirmed:!0});return this.save(v),v}static getHandshakePayload(f,b="English"){const v={type:"handshake",schema:f.schema,current_values:f.current_values,fill_language:b};if(f.section_index){v.section_number=f.current_section,v.total_sections=f.section_index.total_sections;const S=f.section_index.sections.find(C=>C.section_number===f.current_section);S&&(v.section_label=S.section_label);const y=this.getSpokenNameMap(f);v.previous_spoken_names=Array.from(y.keys())}return v}static setSessionId(f,b){const v={...f,session_id:b};return this.save(v),v}static clear(){sessionStorage.removeItem(this.STORAGE_KEY)}static getUnconfirmedFields(f){return f.schema.fields.filter(b=>{const v=f.current_values[b.id];return!v||!v.confirmed}).map(b=>b.id)}static getCompletionPercentage(f){const b=f.schema.fields.length;if(b===0)return 100;const v=f.schema.fields.filter(S=>{const y=f.current_values[S.id];return y&&y.value!==null&&y.value!==""}).length;return Math.round(v/b*100)}static debug(f){}static initWithSections(f,b){const v=this.load();if(v&&v.full_schema&&v.section_index&&v.full_schema.form_metadata.url===f.form_metadata.url&&Date.now()-v.last_updated<60*60*1e3)return v;const y={schema:this.getSectionSchema(f,b,1),current_values:{},last_updated:Date.now(),current_section:1,completed_sections:new Set,section_index:b,full_schema:f};return this.save(y),y}static getSectionSchema(f,b,v){const S=b.sections.find(C=>C.section_number===v);if(!S)throw new Error(`Section ${v} not found in index`);const y=S.field_indices.map(C=>f.fields[C]);return{...f,fields:y}}static switchSection(f,b){if(!f.section_index||!f.full_schema)throw new Error("Cannot switch sections: section_index or full_schema not initialized");if(b<1||b>f.section_index.total_sections)throw new Error(`Invalid section number: ${b}`);const v=this.getSectionSchema(f.full_schema,f.section_index,b),S={...f,schema:v,current_section:b};return this.save(S),S}static completeSection(f,b){const v=f.completed_sections||new Set,S={...f,completed_sections:new Set([...v,b])};return this.save(S),S}static getSpokenNameMap(f){const b=new Map;if(!f.full_schema||!f.section_index||!f.completed_sections)return b;const v=new Set([...f.completed_sections,f.current_section||1]);for(const S of v){const y=f.section_index.sections.find(C=>C.section_number===S);if(y)for(const C of y.field_indices){const A=f.full_schema.fields[C];if(!A)continue;A.spoken_name&&b.set(A.spoken_name.toLowerCase(),A.id);const k=A.spoken_aliases;if(Array.isArray(k))for(const L of k)b.set(L.toLowerCase(),A.id)}}return b}static getSectionLabel(f,b){return f.section_index&&f.section_index.sections.find(S=>S.section_number===b)?.section_label||null}static findSectionByLabel(f,b){if(!f.section_index)return null;const v=b.toLowerCase().trim();return f.section_index.sections.find(y=>y.section_label.toLowerCase()===v)?.section_number||null}static getSectionFieldCount(f){if(!f.section_index||!f.current_section)return{filled:0,total:f.schema.fields.length};const b=f.section_index.sections.find(S=>S.section_number===f.current_section);return b?{filled:f.schema.fields.filter(S=>{const y=f.current_values[S.id];return y&&y.value!==null&&y.value!==""}).length,total:b.field_count}:{filled:0,total:f.schema.fields.length}}}He(ve,"STORAGE_KEY","web_form_state"),He(ve,"SECTION_KEY","vff_current_section"),He(ve,"COMPLETED_SECTIONS_KEY","vff_completed_sections"),He(ve,"SPOKEN_NAME_MAP_KEY","vff_spoken_name_map");function Kr(E,f){const{requiredOnly:b=!1,skipConfirmed:v=!0}=f||{};if(!E.schema||!E.schema.fields||E.schema.fields.length===0)return null;for(const S of E.schema.fields){if(b&&!S.required)continue;const y=E.current_values[S.id],C=y?.confirmed===!0;if(!(v&&C||y?.value!==null&&y?.value!==void 0&&y?.value!==""))return S}return null}function Cf(E){if(!E.schema||!E.schema.fields||E.schema.fields.length===0)return!0;if(E.schema.fields.some(b=>b.required)){for(const b of E.schema.fields)if(b.required&&!(E.current_values[b.id]?.confirmed===!0))return!1;return!0}else{for(const b of E.schema.fields)if(!(E.current_values[b.id]?.confirmed===!0))return!1;return!0}}function Zr(E,f){const b=f?`#${f}`:"",v=E.required?", required":"",S=E.options&&E.options.length>0?`, options: [${E.options.join(", ")}]`:"";return`Next field to fill is ${b}: '${E.name}' (type: ${E.type}${v}${S})`}function If(E,f){if(!E.schema||!E.schema.fields)return null;const b=E.schema.fields.findIndex(v=>v.id===f);return b>=0?b+1:null}class jc{constructor(f,b={},v="English"){He(this,"ws",null);He(this,"state");He(this,"callbacks");He(this,"status","disconnected");He(this,"reconnectAttempts",0);He(this,"maxReconnectAttempts",5);He(this,"reconnectDelay",1e3);He(this,"reconnectTimer",null);He(this,"audioQueue",[]);He(this,"audioChunkCount",0);He(this,"isProcessingAudio",!1);He(this,"enableAutoReconnect",!1);He(this,"isSectionSwitching",!1);He(this,"connectedUrl","");He(this,"fillLanguage","English");this.state=ve.init(f),this.callbacks=b,this.fillLanguage=v}async connect(f="ws://localhost:8000/ws/fill",b=1e4){if(!(this.ws&&this.ws.readyState===WebSocket.OPEN))return this.connectedUrl=f,this.isSectionSwitching||this.setStatus("connecting"),new Promise((v,S)=>{const y=setTimeout(()=>{this.ws&&(this.ws.close(),this.ws=null),S(new Error(`Connection timeout after ${b}ms`))},b);try{this.ws=new WebSocket(f),this.ws.onopen=()=>{clearTimeout(y),this.handleOpen(),v()},this.ws.onmessage=C=>this.handleMessage(C),this.ws.onerror=C=>{clearTimeout(y),this.handleError(C),S(C)},this.ws.onclose=()=>{clearTimeout(y),this.handleClose()}}catch(C){clearTimeout(y),this.handleError(C),S(C)}})}disconnect(){this.reconnectTimer&&(clearTimeout(this.reconnectTimer),this.reconnectTimer=null),this.ws&&(this.ws.close(),this.ws=null),this.isSectionSwitching||this.setStatus("disconnected")}handleOpen(){if(this.reconnectAttempts=0,this.reconnectDelay=1e3,this.enableAutoReconnect=!0,this.isSectionSwitching)return;const f=ve.getHandshakePayload(this.state,this.fillLanguage);this.send(f)}async handleMessage(f){if(f.data instanceof ArrayBuffer||f.data instanceof Blob){await this.handleAudioFrame(f.data);return}try{const b=JSON.parse(f.data);switch(b.type){case"session_ready":this.handleSessionReady(b);break;case"field_update":this.handleFieldUpdate(b);break;case"form_updated":this.handleFormUpdated(b);break;case"form_state_ack":break;case"hint_ack":break;case"get_form_state":this.handleGetFormStateRequest(b);break;case"get_next_field_hint":this.handleGetNextFieldHintRequest(b);break;case"prepare_section_switch":this.handlePrepareSectionSwitchRequest(b);break;case"section_switched":this.handleSectionSwitched(b);break;case"switch_section":this.handleSwitchSectionRequest(b);break;case"get_field_value":this.handleGetFieldValueRequest(b);break;case"complete_section":this.handleCompleteSectionRequest(b);break;case"error":this.handleServerError(b);break;case"ai_response":break;case"turn_complete":window.vffOnTurnComplete&&window.vffOnTurnComplete();break;case"gemini_session_restarted":console.log("[WebFormConnection] ✅ Gemini session restarted successfully"),this.callbacks.onSessionRestarted&&this.callbacks.onSessionRestarted();break;default:break}}catch{}}handleSessionReady(f){const{session_id:b,ephemeral:v}=f;this.state=ve.setSessionId(this.state,b),this.setStatus("connected"),this.callbacks.onSessionReady&&this.callbacks.onSessionReady(b)}handleFieldUpdate(f){const{updates:b}=f;if(!b||typeof b!="object")return;const v=[];for(const[S,y]of Object.entries(b)){const C=this.state.schema.fields.find(A=>A.name===S||A.id===S);C&&(this.updateField(C.id,y,{confirmed:!0,emit:!1}),v.push({fieldId:C.id,value:y}))}this.callbacks.onFieldUpdate&&v.length>0&&this.callbacks.onFieldUpdate(v)}handleFormUpdated(f){const b=f&&f.data||{},v=b.form_state||{},S=b.applied_fields||[],y=b.request_next_field_hint||!1,C=b.request_id;if(!v||typeof v!="object")return;const A=new Set(S.map(X=>String(X))),k=A.size>0,L=[];for(const X of this.state.schema.fields){const we=v[X.id]??v[X.name??""];if(we===void 0)continue;const Y=A.has(X.id)||(X.name?A.has(X.name):!1);if(k&&!Y)continue;const J=this.state.current_values[X.id]?.value;(Y||!Object.is(J,we))&&(this.updateField(X.id,we,{confirmed:Y,emit:!1}),L.push({fieldId:X.id,value:we}))}for(const[X,we]of Object.entries(v)){if(this.state.schema.fields.some(V=>V.id===X||V.name===X))continue;const Y=X+"[]",J=this.state.schema.fields.find(V=>V.id===Y||V.name===Y);if(J){const V=A.has(X)||A.has(Y);if(k&&!V)continue;const H=this.state.current_values[J.id]?.value;if(!(V||!Object.is(H,we)))continue;this.updateField(J.id,we,{confirmed:V,emit:!1}),L.push({fieldId:J.id,value:we})}}if(L.length&&this.callbacks.onFieldUpdate&&this.callbacks.onFieldUpdate(L),y&&C){const X=this.computeNextFieldHintString();X&&sessionStorage.setItem("vff_last_field_hint",X),this.send({type:"next_field_hint_response",request_id:C,hint:X})}}handleGetFormStateRequest(f){const b=f.request_id,v=f.field_ids||[],S={};if(v.length===0)for(const[y,C]of Object.entries(this.state.current_values))S[y]={value:C.value,confirmed:C.confirmed};else for(const y of v){let C=this.state.current_values[y];!C&&!y.endsWith("[]")&&(C=this.state.current_values[y+"[]"]),!C&&y.endsWith("[]")&&(C=this.state.current_values[y.slice(0,-2)]),C?S[y]={value:C.value,confirmed:C.confirmed}:S[y]={value:null,confirmed:!1}}this.send({type:"form_state_response",request_id:b,field_values:S})}handleGetNextFieldHintRequest(f){const b=f.request_id,v=this.computeNextFieldHintString();v&&sessionStorage.setItem("vff_last_field_hint",v),this.send({type:"next_field_hint_response",request_id:b,hint:v})}computeNextFieldHintString(){if(Cf(this.state))return null;const f=Kr(this.state,{skipConfirmed:!0});if(!f)return null;const b=If(this.state,f.id);return Zr(f,b||void 0)}getNextFieldHint(){return this.computeNextFieldHintString()}async handleSwitchSectionRequest(f){const b=f.identifier;try{let v;if(typeof b=="number")v=b;else if(typeof b=="string"){const S=parseInt(b,10);if(!isNaN(S))v=S;else{const y=ve.load();if(y?.section_index){const C=b.toLowerCase(),A=y.section_index.sections.find(k=>k.section_label.toLowerCase()===C||k.section_id.toLowerCase()===C);A&&(v=A.section_number)}}}if(!v)return;await this.switchSection(v,this.connectedUrl)}catch{}}handlePrepareSectionSwitchRequest(f){const b=f.request_id,v=f.identifier;console.log("[WebFormConnection] handlePrepareSectionSwitchRequest START",{requestId:b,identifier:v});try{const S=ve.load();if(console.log("[WebFormConnection] Loaded state",{hasState:!!S,hasSectionIndex:!!S?.section_index}),!S||!S.section_index){console.log("[WebFormConnection] No state/section_index, sending null response"),this.send({type:"section_info_response",request_id:b,section_info:null});return}let y;if(typeof v=="number")y=v;else if(typeof v=="string"){const J=parseInt(v,10);if(!isNaN(J))y=J;else{const V=v.toLowerCase(),H=S.section_index.sections.find(j=>j.section_label.toLowerCase()===V||j.section_id.toLowerCase()===V);H&&(y=H.section_number)}}if(console.log("[WebFormConnection] Parsed target number:",y),!y){console.log("[WebFormConnection] Invalid target number, sending null response"),this.send({type:"section_info_response",request_id:b,section_info:null});return}console.log("[WebFormConnection] Switching to section",y);const C=ve.switchSection(S,y);this.state=C,console.log("[WebFormConnection] Building section schema and values");const A=C.schema,k=new Set(A.fields.map(J=>J.id)),L={};for(const[J,V]of Object.entries(C.current_values))k.has(J)&&(L[J]=V);console.log("[WebFormConnection] Building previous spoken names");const X=ve.getSpokenNameMap(C),we=Array.from(X.keys());console.log("[WebFormConnection] Computing initial field hint");const Y=this.computeNextFieldHintString();Y&&sessionStorage.setItem("vff_last_field_hint",Y),console.log("[WebFormConnection] Sending section_info_response",{requestId:b,sectionNumber:y,fieldCount:A.fields.length,valueCount:Object.keys(L).length}),this.send({type:"section_info_response",request_id:b,section_info:{schema:A,current_values:L,metadata:{section_number:y,total_sections:C.section_index.total_sections,section_label:ve.getSectionLabel(C,y)||"",previous_spoken_names:we},initial_field_hint:Y}}),console.log("[WebFormConnection] handlePrepareSectionSwitchRequest COMPLETE")}catch(S){console.error("[WebFormConnection] Error preparing section switch:",S),this.send({type:"section_info_response",request_id:b,section_info:null})}}handleSectionSwitched(f){const b=f.section_number;console.log(`[WebFormConnection] Section switched confirmed: ${b}`),this.setStatus("connected")}handleGetFieldValueRequest(f){const b=f.request_id,v=f.spoken_name;try{const S=ve.load();if(!S){this.sendFieldValueResponse(b,null,!1);return}const C=ve.getSpokenNameMap(S).get(v.toLowerCase());if(!C){this.sendFieldValueResponse(b,null,!1);return}const A=S.current_values[C];A!=null&&String(A).trim()!==""?this.sendFieldValueResponse(b,A,!0):this.sendFieldValueResponse(b,null,!1)}catch{this.sendFieldValueResponse(b,null,!1)}}sendFieldValueResponse(f,b,v){this.send({type:"field_value_response",request_id:f,value:b,found:v})}async handleCompleteSectionRequest(f){try{const b=ve.load();if(!b||!b.current_section)throw new Error("Section state not initialized");const v=b.current_section,S=ve.completeSection(b,v);if(this.state=S,v>=S.section_index.total_sections){this.send({type:"section_completed",next_section:v,form_complete:!0});return}const y=v+1;await this.switchSection(y,this.connectedUrl),this.send({type:"section_completed",next_section:y,form_complete:!1})}catch(b){console.error("[WebFormConnection] Error completing section:",b),this.send({type:"section_completed",success:!1,error:b instanceof Error?b.message:String(b)})}}sendCompletionMessage(){this.send({type:"completion_message",message:"Say the following: 'The form is complete. if all fields are correct, please press submit.'"})}async handleAudioFrame(f){const b=f instanceof Blob?await f.arrayBuffer():f;this.audioChunkCount||(this.audioChunkCount=0),this.audioChunkCount++,this.audioChunkCount===1?console.log(`[WebFormConnection] 📥 First audio chunk received from server (${b.byteLength} bytes)`):this.audioChunkCount%10===0&&console.log(`[WebFormConnection] 📥 Audio chunk #${this.audioChunkCount} (${b.byteLength} bytes)`),this.audioQueue.push(b),this.isProcessingAudio||this.processAudioQueue()}async processAudioQueue(){for(this.isProcessingAudio=!0;this.audioQueue.length>0;){const f=this.audioQueue.shift();this.callbacks.onAudioData&&this.callbacks.onAudioData(f)}this.isProcessingAudio=!1}handleServerError(f){console.error("[WebFormConnection] Server error received:",{code:f.code,reason:f.reason,message:f.message,fullMessage:f});const b=f.message||f.reason||f.code||"Server error",v=new Error(b);this.callbacks.onError&&this.callbacks.onError(v)}handleError(f){this.isSectionSwitching||this.setStatus("error"),this.callbacks.onError&&f instanceof Error&&this.callbacks.onError(f)}handleClose(){if(!this.enableAutoReconnect){this.setStatus("disconnected");return}this.isSectionSwitching||(this.status!=="disconnected"&&this.reconnectAttempts<this.maxReconnectAttempts?this.attemptReconnect():this.setStatus("disconnected"))}attemptReconnect(){this.reconnectAttempts++,this.setStatus("reconnecting");const f=Math.min(this.reconnectDelay*Math.pow(2,this.reconnectAttempts-1),3e4);this.reconnectTimer=window.setTimeout(()=>{this.connect()},f)}async waitForBufferDrain(f=1e3){if(!this.ws)return;const b=Date.now();for(;this.ws.bufferedAmount>0;){if(Date.now()-b>f){console.warn("[WebFormConnection] Buffer drain timeout",{bufferedAmount:this.ws.bufferedAmount,waitedMs:Date.now()-b});break}await new Promise(v=>setTimeout(v,10))}this.ws.bufferedAmount===0&&console.log("[WebFormConnection] Buffer drained successfully",{waitedMs:Date.now()-b})}send(f){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.error("[WebFormConnection] send() called but WebSocket not open!",{hasWs:!!this.ws,readyState:this.ws?.readyState,message:f});return}if(f instanceof ArrayBuffer)this.ws.send(f);else{const b=JSON.stringify(f);console.log("[WebFormConnection] Sending JSON message",{type:f.type,size:b.length,readyState:this.ws.readyState,bufferedAmount:this.ws.bufferedAmount}),this.ws.send(b)}}sendAudio(f){this.send(f)}sendManualFieldUpdate(f,b,v){!this.ws||this.ws.readyState!==WebSocket.OPEN||this.send({type:"manual_field_update",field_id:f,field_name:b,value:v})}sendActivityStart(){!this.ws||this.ws.readyState!==WebSocket.OPEN||this.send({type:"vad_activity_start",timestamp:Date.now()})}sendActivityEnd(){!this.ws||this.ws.readyState!==WebSocket.OPEN||this.send({type:"vad_activity_end",timestamp:Date.now()})}sendPrompt(f){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.warn("[WebFormConnection] Cannot send prompt - not connected");return}console.log("[WebFormConnection] Sending prompt to Gemini:",f),this.send({type:"completion_message",message:f})}sendRecoveryPrompt(f,b){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.warn("[WebFormConnection] Cannot send recovery prompt - not connected");return}console.log(`[WebFormConnection] Sending recovery prompt level ${f}`,b?`with hint: ${b}`:""),this.send({type:"recovery_prompt",level:f,next_field_hint:b})}endGeminiSession(){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.warn("[WebFormConnection] Cannot end Gemini session - not connected");return}console.log("[WebFormConnection] 🚪 Ending Gemini session (keeping WebSocket alive)"),this.send({type:"end_gemini_session"})}async changeFillLanguage(f){!this.ws||this.ws.readyState!==WebSocket.OPEN||(this.fillLanguage=f,this.send({type:"change_fill_language",language:f}))}updateField(f,b,v){const S=v?.confirmed,y=v?.emit??!1;this.state=ve.updateFieldValue(this.state,f,b,{confirmed:S}),y&&this.flushField(f)}flushField(f){if(!this.ws||this.ws.readyState!==WebSocket.OPEN)return;const b=this.state.current_values[f];b&&this.send({type:"form_state",fields:[{field_id:f,value:b.value,confirmed:!!b.confirmed}]})}setStatus(f){this.status!==f&&(this.status=f,this.callbacks.onStatusChange&&this.callbacks.onStatusChange(f))}getStatus(){return this.status}getState(){return this.state}getCompletionPercentage(){return ve.getCompletionPercentage(this.state)}reset(){this.disconnect(),ve.clear()}async startSection(f,b="ws://localhost:8000/ws/fill"){try{this.isSectionSwitching=!0,this.setStatus("switching_section"),this.ws&&this.ws.readyState===WebSocket.OPEN&&(this.disconnect(),await new Promise(X=>setTimeout(X,100)));let v=ve.load();if(!v||!v.section_index||!v.full_schema)throw new Error("Section index or full schema not initialized");v=ve.switchSection(v,f),this.state=v;const S=v.schema,y={},C=new Set(S.fields.map(X=>X.id));for(const[X,we]of Object.entries(v.current_values))C.has(X)&&(y[X]=we);const A=ve.getSpokenNameMap(v),k=Array.from(A.keys());await this.connect(b),this.isSectionSwitching=!1;const L=this.computeNextFieldHintString();this.send({type:"handshake",schema:S,current_values:y,fill_language:this.fillLanguage,section_number:f,total_sections:v.section_index.total_sections,section_label:ve.getSectionLabel(v,f)||"",previous_spoken_names:k,initial_field_hint:L})}catch(v){throw this.isSectionSwitching=!1,v}}async switchSection(f,b){const v=ve.load();if(!v||!v.section_index)throw new Error("Section index not initialized");let S;if(typeof f=="number")S=f;else{const Y=ve.findSectionByLabel(v,f);if(!Y)throw new Error(`Section not found: ${f}`);S=Y}if(S<1||S>v.section_index.total_sections)throw new Error(`Invalid section number: ${S} (must be 1-${v.section_index.total_sections})`);console.log("[WebFormConnection] Waiting for buffer to drain before section switch"),await this.waitForBufferDrain(1e3),this.setStatus("switching_section");const y=ve.switchSection(v,S);this.state=y;const C=y.schema,A=new Set(C.fields.map(Y=>Y.id)),k={};for(const[Y,J]of Object.entries(y.current_values))A.has(Y)&&(k[Y]=J);const L=ve.getSpokenNameMap(y),X=Array.from(L.keys()),we=this.computeNextFieldHintString();console.log("[WebFormConnection] Sending section switch with embedded info",{sectionNumber:S,fieldCount:C.fields.length,valueCount:Object.keys(k).length}),this.send({type:"manual_section_switch",identifier:S.toString(),section_info:{schema:C,current_values:k,metadata:{section_number:S,total_sections:y.section_index.total_sections,section_label:ve.getSectionLabel(y,S)||"",previous_spoken_names:X},initial_field_hint:we}})}async completeSection(f){if(!f)throw new Error("wsUrl is required for completeSection - must pass the connected backend URL");const b=ve.load();if(!b||!b.current_section||!b.section_index)throw new Error("Section state not initialized");const v=b.current_section,S=ve.completeSection(b,v);if(this.state=S,v>=S.section_index.total_sections){this.setStatus("connected");return}const y=v+1;await this.startSection(y,f)}getCurrentSection(){return this.state.current_section}getCompletedSections(){return this.state.completed_sections||new Set}}function Hc(E={}){const f=new Set,b=new Map,v=new Map,S=new Set;function y(R,D){if(b.has(R))return;const F=()=>{if(S.has(D))return;const U=Date.now(),P=v.get(D)||0;if(!(U-P<100)&&(v.set(D,U),f.has(D)&&A(R,D),E.onManualEdit)){const G=R.value;G&&G.trim()&&E.onManualEdit(D,G)}};R.addEventListener("blur",F),R.addEventListener("change",F),b.set(R,F)}function C(R){console.log("[VFF FieldManager] Setting up listeners on",R.length,"schema fields");for(const D of R){const F=D.id;if(!F)continue;let U=document.getElementById(F);if(!U){const P=document.querySelectorAll(`input[name="${F}"], textarea[name="${F}"], select[name="${F}"]`);if(P.length>0){P.forEach(G=>{y(G,F)});continue}}U&&y(U,F)}}function A(R,D){R.style.outline="",R.style.outlineOffset="";const F=R.parentElement?.querySelector(".vff-field-badge");F&&F.remove(),R.removeAttribute("data-vff-confirmed"),f.delete(D),console.log("[VFF FieldManager] Cleared AI confirmation for:",D)}E.schema?.fields&&C(E.schema.fields);function k(R){console.log("[VFF FieldManager] 📝 Applying",R.length,"field update(s)");const D={success:[],notFound:[],errors:[]};for(const F of R){S.add(F.fieldId);const U=F.value||"";let P=document.getElementById(F.fieldId);if(!P){const Ae=document.querySelectorAll(`input[name="${F.fieldId}"], textarea[name="${F.fieldId}"], select[name="${F.fieldId}"]`);if(Ae.length>0){const me=Ae[0];if(Ae.length>1){if(me.type==="radio"){J(Ae,U,F.fieldId),D.success.push(F.fieldId);continue}else if(me.type==="checkbox"){we(Ae,U,F.fieldId),D.success.push(F.fieldId);continue}}P=me}if(!P){const me=document.querySelector(`[role="combobox"][id="${F.fieldId}"], button[aria-haspopup="listbox"][id="${F.fieldId}"]`);if(me){H(me,U,F.fieldId),D.success.push(F.fieldId);continue}}if(!P){console.warn("[VFF FieldManager] ❌ Field not found:",F.fieldId),D.notFound.push(F.fieldId);continue}}const G=P,oe=G.type?.toLowerCase();if(P.tagName==="SELECT")L(P,U,F.fieldId);else if(oe==="checkbox")X(G,U,F.fieldId);else if(oe==="radio")V(G,U,F.fieldId);else if(P.tagName==="INPUT"||P.tagName==="TEXTAREA"){const Ae=String(U);P.value=Ae,P.dispatchEvent(new Event("input",{bubbles:!0})),P.dispatchEvent(new Event("change",{bubbles:!0}));const me=Ae.substring(0,50);console.log("[VFF FieldManager] Updated text field:",F.fieldId,"→",me)}P&&(P.setAttribute("data-vff-confirmed","true"),f.add(F.fieldId),j(P),y(P,F.fieldId),D.success.push(F.fieldId),setTimeout(()=>{S.delete(F.fieldId)},50))}console.log("[VFF FieldManager] 📊 Update summary:",{total:R.length,success:D.success.length,notFound:D.notFound.length,errors:D.errors.length}),D.notFound.length>0&&console.warn("[VFF FieldManager] ⚠️ Fields not found:",D.notFound),D.errors.length>0&&console.error("[VFF FieldManager] ❌ Errors:",D.errors),D.success.length>0&&console.log("[VFF FieldManager] ✅ Successfully updated:",D.success)}function L(R,D,F){let U=!1;for(let P=0;P<R.options.length;P++){const G=R.options[P];if(G.value===D||G.text===D){R.selectedIndex=P,U=!0,console.log("[VFF FieldManager] ✓ Exact match for select:",F,"→",G.text);break}}if(!U){const P=D.toLowerCase();for(let G=0;G<R.options.length;G++){const oe=R.options[G],Ae=oe.text.toLowerCase(),me=oe.value.toLowerCase();if(Ae.includes(P)||P.includes(Ae)||me.includes(P)||P.includes(me)){R.selectedIndex=G,U=!0,console.log("[VFF FieldManager] ≈ Fuzzy match for select:",F,"→",oe.text);break}}}U||console.warn("[VFF FieldManager] ⚠️ No matching option found for:",D,"in",F),R.dispatchEvent(new Event("change",{bubbles:!0})),R.dispatchEvent(new Event("input",{bubbles:!0}))}function X(R,D,F){let U=!1;typeof D=="boolean"?U=D:typeof D=="string"&&(U=D==="true"||D==="True"||D==="1"||D==="yes"||D==="Yes"||D==="on"||D==="checked"),R.checked=U,R.dispatchEvent(new Event("change",{bubbles:!0})),R.dispatchEvent(new Event("input",{bubbles:!0})),console.log("[VFF FieldManager] ✓ Updated checkbox:",F,"→",U,`(from ${typeof D}: ${D})`)}function we(R,D,F){const U=Array.isArray(D)?D:[D];console.log("[VFF FieldManager] 📋 Checkbox group:",F),console.log("  Requested values:",U);const P=[];for(const me of R)P.push(me.value||Y(me));console.log("  Available checkboxes:",P);const G=[],oe=[],Ae=new Map;for(const me of U)Ae.set(String(me),!1);for(const me of R){const qe=me.value||Y(me);let Ne=null;const Ce=U.some(Ke=>{const ze=String(Ke);if(qe===ze||qe.toLowerCase()===ze.toLowerCase())return Ne=ze,!0;const Ye=rt=>rt.toLowerCase().replace(/[\/\-_,]/g," ").replace(/\s+/g," ").trim(),tt=Ye(qe),ft=Ye(ze);return tt===ft||tt.includes(ft)||ft.includes(tt)?(Ne=ze,!0):!1});Ce&&Ne&&(Ae.set(Ne,!0),G.push(qe)),me.checked=Ce,Ce&&(me.setAttribute("data-vff-confirmed","true"),f.add(F),j(me),y(me,F)),me.dispatchEvent(new Event("change",{bubbles:!0})),me.dispatchEvent(new Event("input",{bubbles:!0}))}for(const[me,qe]of Ae.entries())qe||oe.push(me);console.log("[VFF FieldManager] ✅ Checkbox group result:",{fieldId:F,requested:U.length,matched:G.length,unmatched:oe.length,total:R.length}),G.length>0&&console.log("  ✓ Matched & checked:",G),oe.length>0&&(console.warn("  ⚠️ Could not match:",oe),console.warn("  💡 Try one of:",P))}function Y(R){const D=document.querySelector(`label[for="${R.id}"]`);if(D)return D.textContent?.trim()||"";const F=R.closest("label");if(F){const P=F.cloneNode(!0),G=P.querySelector("input");return G&&G.remove(),P.textContent?.trim()||""}const U=R.nextSibling;return U&&U.nodeType===Node.TEXT_NODE?U.textContent?.trim()||"":R.value}function J(R,D,F){let U=!1;for(const P of R)if(P.value===D){P.checked=!0,U=!0,P.dispatchEvent(new Event("change",{bubbles:!0})),P.dispatchEvent(new Event("input",{bubbles:!0})),P.setAttribute("data-vff-confirmed","true"),f.add(F),j(P),y(P,F),console.log("[VFF FieldManager] ✓ Selected radio:",F,"→",D);break}if(!U){const P=D.toLowerCase();for(const G of R){const oe=G.value.toLowerCase();if(oe.includes(P)||P.includes(oe)){G.checked=!0,U=!0,G.dispatchEvent(new Event("change",{bubbles:!0})),G.dispatchEvent(new Event("input",{bubbles:!0})),G.setAttribute("data-vff-confirmed","true"),f.add(F),j(G),y(G,F),console.log("[VFF FieldManager] ≈ Fuzzy match radio:",F,"→",G.value);break}}}U||console.warn("[VFF FieldManager] ⚠️ No matching radio option found for:",D,"in",F)}function V(R,D,F){R.value===D?(R.checked=!0,R.dispatchEvent(new Event("change",{bubbles:!0})),R.dispatchEvent(new Event("input",{bubbles:!0})),console.log("[VFF FieldManager] ✓ Selected single radio:",F)):console.warn("[VFF FieldManager] ⚠️ Radio value mismatch:",R.value,"!==",D)}function H(R,D,F){console.warn("[VFF FieldManager] ⚠️ Combobox filling not fully supported yet:",F),console.log("[VFF FieldManager] Combobox should be filled with:",D),R.setAttribute("aria-valuenow",D),R.setAttribute("data-vff-value",D),R.click()}function j(R){if(R.style.outline="2px solid #10b981",R.style.outlineOffset="2px",R.parentElement?.querySelector(".vff-field-badge"))return;const F=document.createElement("span");F.className="vff-field-badge",F.textContent="✓",F.style.cssText=`
			position: absolute;
			top: 50%;
			right: 8px;
			transform: translateY(-50%);
			color: #10b981;
			font-weight: bold;
			font-size: 18px;
			pointer-events: none;
			z-index: 1000;
		`;const U=R.parentElement;U&&getComputedStyle(U).position==="static"&&(U.style.position="relative"),R.parentElement?.appendChild(F)}function K(){console.log("[VFF FieldManager] Destroying, cleaning up",b.size,"listeners");for(const[R,D]of b.entries())R.removeEventListener("blur",D),R.removeEventListener("change",D);document.querySelectorAll("[data-vff-confirmed]").forEach(R=>{R.removeAttribute("data-vff-confirmed"),R.style.outline="",R.style.outlineOffset=""}),document.querySelectorAll(".vff-field-badge").forEach(R=>{R.remove()}),b.clear(),f.clear(),v.clear()}return{applyUpdates:k,destroy:K}}const on=16e3,Wr=24e3;function Kc(E){const f={recordingContext:null,playbackContext:null,stream:E||null,workletNode:null,source:null};let b=!1,v=0,S=0,y=!1,C=null,A=null,k=!1,L=!1,X=!1;const Y=Math.ceil(600/1e3*on),J=[];let V=0;const H=[];let j=!1,K=!1,R=0,D=[],F=!1,U=!1,P=0;const G=2.5,oe=1.7,Ae=1.4,me=45,qe=200;let Ne=0,Ce=0;const Ke=.9,ze=.5,Ye=2e3;async function tt(Be,ue){if(!b)try{f.stream?console.log("[AudioManager] 🔗 Reusing existing microphone stream (shared with VAD)"):(f.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,sampleRate:on,echoCancellation:!0,noiseSuppression:!0,autoGainControl:!0}}),console.log("[AudioManager] 🎤 Created new microphone stream")),f.recordingContext=new AudioContext({sampleRate:on}),f.source=f.recordingContext.createMediaStreamSource(f.stream),f.playbackContext||(console.log("[AudioManager] 🎵 Creating AudioContext for playback (eager initialization)"),f.playbackContext=new AudioContext({sampleRate:Wr}),v=0);const Ue=!window.location.hostname.includes("localhost")&&!window.location.hostname.includes("127.0.0.1")?new URL("../shared/audio-processor.worklet.js",window.location.href).href:"/shared/audio-processor.worklet.js";console.log("[VFF Audio] Loading worklet from:",Ue),await f.recordingContext.audioWorklet.addModule(Ue),f.workletNode=new AudioWorkletNode(f.recordingContext,"voice-form-filler-audio-processor"),C=Be,A=ue||null,R=0,D=[],F=!1,P=0,Ne=0,Ce=0;const je=Date.now();f.workletNode.port.onmessage=mt=>{if(!b||!C)return;const{type:Ft,pcmData:Ct,energy:ut}=mt.data;if(Ft!=="audio")return;if(P=ut,R===0)if(Date.now()-je<Ye)D.push(P);else{const Ze=D.reduce((Dt,Bt)=>Dt+Bt,0);R=Math.max(Ze/D.length||ze,ze),P=R,A?.onCalibrationComplete&&A.onCalibrationComplete(R)}if(R>0){const ge=Date.now(),Ze=U?Ae:1,Dt=R*G*Ze,Bt=R*oe;if(F)P<Bt?Ce===0?Ce=ge:ge-Ce>=qe&&(F=!1,Ne=0,A?.onEnergyChange&&A.onEnergyChange(P,!1,"release")):Ce=0;else if(P>Dt){if(Ne===0)Ne=ge;else if(ge-Ne>=me){F=!0,Ce=0;const Ut=U?"tts_bleed_guard":"attack";A?.onEnergyChange&&A.onEnergyChange(P,!0,Ut)}}else Ne=0;if(!F&&P<Bt){const Ut=Ke*R+(1-Ke)*P;R=Math.max(Ut,ze)}}const pe=new Int16Array(Ct);for(J.push(pe),V+=pe.length;V>Y;){const ge=J.shift();ge&&(V-=ge.length)}if(k){const ge=new Int16Array(pe.length);C(ge.buffer)}else if(L)C(Ct);else if(X){y||(console.log("[AudioManager] 🔊 Sending warmup noise to Gemini (VAD inactive, warmup mode enabled)"),y=!0);const ge=new Int16Array(pe.length);for(let Ze=0;Ze<ge.length;Ze++)ge[Ze]=Math.floor((Math.random()*2-1)*300);C(ge.buffer)}else{const ge=new Int16Array(pe.length);C(ge.buffer)}},f.source.connect(f.workletNode),f.workletNode.connect(f.recordingContext.destination),b=!0}catch(Pe){throw console.error("[VFF Audio] Failed to start recording:",Pe),Tt(),Pe}}function ft(){if(b){if(b=!1,C=null,f.workletNode){try{f.workletNode.disconnect(),f.workletNode.port.close()}catch{}f.workletNode=null}if(f.source){try{f.source.disconnect()}catch{}f.source=null}if(f.recordingContext){try{f.recordingContext.close()}catch{}f.recordingContext=null}f.stream&&(f.stream.getTracks().forEach(Be=>Be.stop()),f.stream=null)}}async function rt(Be){try{if(S||(S=0),S++,S===1&&console.log(`[AudioManager] 🔊 Playing first audio chunk (${Be.byteLength} bytes)`),j){console.log(`[AudioManager] 🚫 Discarding chunk #${S} (barge-in active)`);return}f.playbackContext||(console.log("[AudioManager] 🎵 Creating AudioContext for playback (lazy fallback)"),f.playbackContext=new AudioContext({sampleRate:Wr}),v=0);const ue=f.playbackContext;ue.state==="suspended"&&(console.log("[AudioManager] ⏸️ Resuming suspended AudioContext"),await ue.resume());const Pe=gt(Be),Ue=new Int16Array(Pe);if(Ue.length===0){console.warn(`[AudioManager] ⚠️ Chunk #${S} decoded to 0 samples`);return}const je=new Float32Array(Ue.length);for(let ge=0;ge<Ue.length;ge++)je[ge]=Ue[ge]/32768;const mt=ue.createBuffer(1,je.length,Wr);mt.getChannelData(0).set(je);const Ft=ue.currentTime,Ct=Math.max(v,Ft+.01),ut=ue.createBufferSource();ut.buffer=mt,ut.connect(ue.destination),ut.start(Ct),H.push(ut);const pe=!U;U=!0,pe&&window.vffOnAudioPlaybackStart&&window.vffOnAudioPlaybackStart(),v=Ct+mt.duration,ut.onended=()=>{v<ue.currentTime&&(v=ue.currentTime);const ge=H.indexOf(ut);ge>-1&&H.splice(ge,1),H.length===0&&(U=!1,!K&&window.vffOnAudioPlaybackEnd&&window.vffOnAudioPlaybackEnd())}}catch(ue){U=!1,console.error("[VFF Audio] Playback failed:",ue)}}function gt(Be){try{const ue=new TextDecoder().decode(Be);if(ue.match(/^[A-Za-z0-9+/]+=*$/)){const Pe=atob(ue),Ue=new Uint8Array(Pe.length);for(let je=0;je<Pe.length;je++)Ue[je]=Pe.charCodeAt(je);return Ue.buffer}}catch{}return Be}function Ee(){j=!0,K=!0,H.forEach(Be=>{try{Be.stop(),Be.disconnect()}catch{}}),H.length=0,f.playbackContext&&(v=f.playbackContext.currentTime),U=!1,K=!1}function st(){j=!1}function vt(){return b}function Tt(){if(ft(),f.playbackContext){try{f.playbackContext.close()}catch{}f.playbackContext=null}v=0}function it(){Tt()}function ht(){return U}function ot(){return F}function Me(){console.log("[AudioManager] Muting input - sending silence"),k=!0}function yt(){console.log("[AudioManager] Unmuting input - sending real audio"),k=!1}function lt(){return f.stream}function Et(Be){const ue=L;if(L=Be,Be&&!ue&&C){console.log(`[AudioManager] VAD activated - flushing ${V} samples (${(V/on*1e3).toFixed(0)}ms) from pre-buffer`);for(const Pe of J){const Ue=new ArrayBuffer(Pe.byteLength);new Int16Array(Ue).set(Pe),C(Ue)}console.log("[AudioManager] Pre-buffer flushed, now sending live audio")}else!Be&&ue&&console.log("[AudioManager] VAD deactivated - sending silence")}function St(Be){X=Be,console.log(`[AudioManager] VAD warmup mode ${Be?"enabled":"disabled"}`)}return{startRecording:tt,stopRecording:ft,playAudio:rt,flushAudioQueue:Ee,resumePlayback:st,isRecording:vt,isSpeaking:ht,getUserSpeaking:ot,muteInput:Me,unmuteInput:yt,getStream:lt,setVADActive:Et,setVADWarmupMode:St,destroy:it}}function Qr(){const E=window.__VFF_LOCAL_DEV,f=window.__VFF_BACKEND_URL,b=window.__VFF_DEBUG_METRICS;return{enabled:!!E,backendUrl:f||"ws://localhost:8000/ws/fill",debugMetrics:!!b||!!E}}function Af(){const E=Qr();return E.enabled?(console.log("[VFF Config] 🔧 LOCAL DEV MODE ENABLED"),console.log("[VFF Config] Backend URL:",E.backendUrl),console.log("[VFF Config] Debug Metrics:",E.debugMetrics),E.backendUrl):"wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill"}function zf(){return"wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill"}function Rf(){return Qr().debugMetrics}function Of(){console.log(`
`+"=".repeat(60)),console.log("🔧 VOICE FORM FILLER - LOCAL DEVELOPMENT MODE"),console.log("=".repeat(60)),console.log(`
To test locally without deploying:`),console.log(`
1. Start backend:`),console.log("   cd backend"),console.log("   source venv/bin/activate  # or venv\\Scripts\\activate on Windows"),console.log("   uvicorn main:app --reload --port 8000"),console.log(`
2. Enable local dev in browser console:`),console.log("   window.__VFF_LOCAL_DEV = true"),console.log(`
3. Load bookmarklet (will connect to localhost:8000)`),console.log(`
4. Test VAD tuning changes:`),console.log("   - Edit backend/adapters/live_ai_gemini.py"),console.log("   - Backend auto-reloads (--reload flag)"),console.log("   - Reconnect bookmarklet to test"),console.log(`
Optional environment variables:`),console.log('   window.__VFF_BACKEND_URL = "ws://localhost:8000/ws/fill"  // Custom URL'),console.log("   window.__VFF_DEBUG_METRICS = true                          // Extra logging"),console.log(`
`+"=".repeat(60)+`
`)}typeof window<"u"&&Qr().enabled&&Of();class Mf{constructor(){He(this,"sessionMetrics",null);He(this,"currentBargeIn",null);He(this,"lastBargeInTime",0);He(this,"BARGE_IN_GRACE_PERIOD_MS",150);He(this,"debugEnabled",!1)}startSession(f){this.debugEnabled=Rf(),this.sessionMetrics={sessionId:f,sessionStart:Date.now(),bargeIns:[],toolCalls:[],falseStarts:0,successfulBargeIns:0,timedOutBargeIns:0,hallucinatedToolCalls:0},this.currentBargeIn=null,this.lastBargeInTime=0,this.debugEnabled&&console.log("[VFF Metrics] 📊 Session started:",f,"(Debug mode: ON)")}recordMicActivity(){if(!this.sessionMetrics)return;const f=performance.now();this.currentBargeIn={timestamp:Date.now(),micActivityDetected:f,result:"pending"},console.log("[VFF Metrics] 🎤 Mic activity detected")}recordTTSPaused(){if(!this.sessionMetrics||!this.currentBargeIn)return;const f=performance.now();this.currentBargeIn.ttsPausedAt=f,this.currentBargeIn.bargeInLatency=f-this.currentBargeIn.micActivityDetected,console.log(`[VFF Metrics] 🔇 TTS paused - Barge-in latency: ${this.currentBargeIn.bargeInLatency.toFixed(1)}ms`,this.currentBargeIn.bargeInLatency<180?"✅":"⚠️ SLOW")}recordCancelSent(){if(!this.sessionMetrics||!this.currentBargeIn)return;const f=performance.now();this.currentBargeIn.cancelSentAt=f,console.log("[VFF Metrics] 📤 Cancel message sent to backend")}recordGeminiAck(){if(!this.sessionMetrics||!this.currentBargeIn)return;const f=performance.now();this.currentBargeIn.geminiAckAt=f,this.currentBargeIn.cancelSentAt&&(this.currentBargeIn.cancelAckLatency=f-this.currentBargeIn.cancelSentAt,console.log(`[VFF Metrics] ✅ Gemini acknowledged - Cancel latency: ${this.currentBargeIn.cancelAckLatency.toFixed(1)}ms`,this.currentBargeIn.cancelAckLatency<150?"✅":"⚠️ SLOW")),this.currentBargeIn.result="success",this.sessionMetrics.successfulBargeIns++,this.lastBargeInTime=f,this.sessionMetrics.bargeIns.push(this.currentBargeIn),this.currentBargeIn=null}recordBargeInTimeout(){!this.sessionMetrics||!this.currentBargeIn||(console.warn("[VFF Metrics] ⏱️ Barge-in timeout - Gemini did not acknowledge"),this.currentBargeIn.result="timeout",this.sessionMetrics.timedOutBargeIns++,this.sessionMetrics.bargeIns.push(this.currentBargeIn),this.currentBargeIn=null)}recordFalseStart(){!this.sessionMetrics||!this.currentBargeIn||(console.log("[VFF Metrics] 🔄 False start detected"),this.currentBargeIn.result="false_start",this.sessionMetrics.falseStarts++,this.sessionMetrics.bargeIns.push(this.currentBargeIn),this.currentBargeIn=null)}checkFalseStart(f,b){return b&&f?(console.warn("[VFF Metrics] ⚠️ FALSE START: Gemini speaking while user mic active!"),this.recordFalseStart(),!0):!1}recordToolCall(f,b){if(!this.sessionMetrics)return"accept";const v=performance.now(),S=v-this.lastBargeInTime,y=S<this.BARGE_IN_GRACE_PERIOD_MS,C={timestamp:Date.now(),toolName:f,callId:b,receivedAt:v,bargeInWindowActive:y,decision:"accepted"};return y?(C.decision="rejected_barge_in",C.rejectionReason=`Received ${S.toFixed(1)}ms after barge-in (< ${this.BARGE_IN_GRACE_PERIOD_MS}ms threshold)`,this.sessionMetrics.hallucinatedToolCalls++,this.sessionMetrics.toolCalls.push(C),console.warn("[VFF Metrics] 🚫 Tool call REJECTED (hallucination):",`${f} [${b.slice(0,8)}]`,`- ${C.rejectionReason}`),"reject"):(this.sessionMetrics.toolCalls.push(C),console.log("[VFF Metrics] ✅ Tool call ACCEPTED:",`${f} [${b.slice(0,8)}]`,`- ${S.toFixed(0)}ms after last barge-in`),"accept")}getStats(){if(!this.sessionMetrics)return null;const f=this.sessionMetrics.bargeIns,b=f.filter(k=>k.bargeInLatency!==void 0).map(k=>k.bargeInLatency),v=f.filter(k=>k.cancelAckLatency!==void 0).map(k=>k.cancelAckLatency),S=k=>k.length?k.reduce((L,X)=>L+X,0)/k.length:0,y=k=>{if(!k.length)return 0;const L=[...k].sort((we,Y)=>we-Y),X=Math.floor(L.length*.95);return L[X]},C=f.length,A=this.sessionMetrics.toolCalls.length;return{totalBargeIns:C,successfulBargeIns:this.sessionMetrics.successfulBargeIns,timedOutBargeIns:this.sessionMetrics.timedOutBargeIns,falseStarts:this.sessionMetrics.falseStarts,avgBargeInLatency:S(b),p95BargeInLatency:y(b),avgCancelAckLatency:S(v),p95CancelAckLatency:y(v),totalToolCalls:A,hallucinatedToolCalls:this.sessionMetrics.hallucinatedToolCalls,toolCallHallucinationRate:A?this.sessionMetrics.hallucinatedToolCalls/A*100:0,falseStartRate:C?this.sessionMetrics.falseStarts/C*100:0}}printSummary(){const f=this.getStats();if(!f){console.log("[VFF Metrics] No session data");return}console.log(`
`+"=".repeat(60)),console.log("📊 VAD TUNING METRICS SUMMARY"),console.log("=".repeat(60)),console.log(`
🎤 BARGE-IN PERFORMANCE:`),console.log(`   Total Barge-Ins: ${f.totalBargeIns}`),console.log(`   Successful: ${f.successfulBargeIns} (${(f.successfulBargeIns/f.totalBargeIns*100).toFixed(1)}%)`),console.log(`   Timeouts: ${f.timedOutBargeIns}`),console.log(`   False Starts: ${f.falseStarts} (${f.falseStartRate.toFixed(1)}%)`),console.log(`   Avg Latency: ${f.avgBargeInLatency.toFixed(1)}ms ${f.avgBargeInLatency<180?"✅":"⚠️"}`),console.log(`   P95 Latency: ${f.p95BargeInLatency.toFixed(1)}ms ${f.p95BargeInLatency<180?"✅ TARGET MET":"❌ EXCEEDS TARGET"}`),console.log(`
🔄 CANCEL ACKNOWLEDGMENT:`),console.log(`   Avg Latency: ${f.avgCancelAckLatency.toFixed(1)}ms ${f.avgCancelAckLatency<150?"✅":"⚠️"}`),console.log(`   P95 Latency: ${f.p95CancelAckLatency.toFixed(1)}ms ${f.p95CancelAckLatency<150?"✅ TARGET MET":"❌ EXCEEDS TARGET"}`),console.log(`
🛠️ TOOL CALL SAFETY:`),console.log(`   Total Tool Calls: ${f.totalToolCalls}`),console.log(`   Hallucinated (rejected): ${f.hallucinatedToolCalls}`),console.log(`   Hallucination Rate: ${f.toolCallHallucinationRate.toFixed(1)}% ${f.toolCallHallucinationRate<1?"✅ EXCELLENT":f.toolCallHallucinationRate<5?"⚠️ ACCEPTABLE":"❌ TOO HIGH"}`),console.log(`
`+"=".repeat(60)+`
`)}endSession(){this.sessionMetrics&&(console.log("[VFF Metrics] 📊 Session ended:",this.sessionMetrics.sessionId),this.printSummary(),this.sessionMetrics=null,this.currentBargeIn=null,this.lastBargeInTime=0)}exportData(){return this.sessionMetrics?{...this.sessionMetrics}:null}}const di=new Mf;typeof window<"u"&&(window.__VFF_METRICS__=di);function Ff(E,f){console.log("[VFF Connection] 🔄 Restoring DOM from sessionStorage...");let b=0;for(const[v,S]of Object.entries(E.current_values)){const y=S.value;if(y==null||y==="")continue;let C=document.getElementById(v);if(!C){const A=document.querySelectorAll(`input[name="${v}"], textarea[name="${v}"], select[name="${v}"]`);A.length>0&&(C=A[0])}if(C){if(C.tagName==="SELECT")C.value=String(y);else if(C.tagName==="INPUT"){const A=C;A.type==="checkbox"?A.checked=!!y:A.value=String(y)}else C.tagName==="TEXTAREA"&&(C.value=String(y));b++}}console.log(`[VFF Connection] ✅ Restored ${b} fields from sessionStorage to DOM`)}function Zc(E,f){console.log("[VFF Connection] 🔍 Scanning DOM for pre-filled values...");let b=0;for(const v of f.fields){const S=v.id;let y=document.getElementById(S);if(!y){const A=document.querySelectorAll(`input[name="${S}"], textarea[name="${S}"], select[name="${S}"]`);A.length>0&&(y=A[0])}if(!y)continue;let C=null;if(y.tagName==="SELECT")C=y.value||null;else if(y.tagName==="INPUT"){const A=y;A.type==="checkbox"?C=A.checked:A.type==="radio"?A.checked&&(C=A.value):C=A.value||null}else y.tagName==="TEXTAREA"&&(C=y.value||null);C!==null&&C!==""&&C!==!1&&(E.updateField(S,C,{confirmed:!0,emit:!1}),b++,console.log("[VFF Connection] ✓ Captured pre-filled:",S,"=",C))}console.log(`[VFF Connection] ✅ Captured ${b} pre-filled values from DOM`)}function Xr(E,f,b="English",v){const S=Df();let y=null,C=null,A=null,k=b,L=!1,X=S,we=!1;const Y=ve.init(E);Ff(Y),A=Kc(v),v&&console.log("[VFF Connection] 🔗 Audio manager using shared stream (VAD coordination)"),C=Hc({schema:E,onManualEdit:(V,H)=>{console.log("[VFF Connection] 🖊️ Manual edit detected:",V,"=",H);const j=ve.updateFieldValue(Y,V,H,{confirmed:!0});if(Object.assign(Y,j),console.log("[VFF Connection] ✓ Updated sessionStorage for:",V),y){const R=E.fields.find(D=>D.id===V)?.name||V;y.sendManualFieldUpdate(V,R,H),console.log("[VFF Connection] ✓ Notified Gemini about:",V)}}}),console.log("[VFF Connection] ✅ Field manager created - listening for manual edits");const J={onStatusChange:V=>{f(V)},onSessionReady:V=>{f("connected"),di.startSession(V)},onSessionRestarted:()=>{console.log("[VFF Connection] ✅ Gemini session restarted - updating status"),f("connected")},onFieldUpdate:V=>{console.log("[VFF Connection] 📥 Tool call received: update_form_fields with",V.length,"field(s)"),V.forEach((K,R)=>{console.log(`  [${R+1}] fieldId:`,K.fieldId,"→ value:",K.value)});const H=[],j=[];for(const K of V){const R=`field_${K.fieldId}_${Date.now()}`;if(di.recordToolCall("update_form_fields",R)==="reject"){j.push(K);continue}H.push(K)}j.length>0&&console.warn("[VFF Connection] ⚠️ Rejected",j.length,"hallucinated update(s):",j.map(K=>K.fieldId)),console.log("[VFF Connection] ✅ Accepted",H.length,"update(s) for processing"),C&&H.length>0&&C.applyUpdates(H)},onAudioData:async V=>{A&&await A.playAudio(V)},onError:V=>{console.error("[VFF Connection] Error:",V),f("error")}};return{async connect(){if(y&&y.getStatus()==="connected"&&y){console.log("[VFF Connection] 🔄 WebSocket alive - restarting Gemini session");const H=y.getNextFieldHint();try{f("reconnecting"),y.send({type:"restart_gemini_session",next_field_hint:H}),console.log("[VFF Connection] ⏳ Gemini session restart requested",{nextFieldHint:H});return}catch(j){console.error("[VFF Connection] Failed to restart Gemini:",j),f("disconnected")}}try{console.log("[VFF Connection] Attempting to connect to:",S),f("connecting"),A||(console.log("[VFF Connection] 🔄 Reinitializing audio manager (reconnect)"),A=Kc(v)),C||(console.log("[VFF Connection] 🔄 Reinitializing field manager (reconnect)"),C=Hc({schema:E,onManualEdit:(H,j)=>{console.log("[VFF Connection] 🖊️ Manual edit detected:",H,"=",j);const K=ve.updateFieldValue(Y,H,j,{confirmed:!0});if(Object.assign(Y,K),console.log("[VFF Connection] ✓ Updated sessionStorage for:",H),y){const D=E.fields.find(F=>F.id===H)?.name||H;y.sendManualFieldUpdate(H,D,j),console.log("[VFF Connection] ✓ Notified Gemini about:",H)}}})),y||(y=new jc(E,J,k)),Zc(y,E);try{console.log("[VFF Connection] Trying localhost..."),await y.connect(S),X=S,console.log("[VFF Connection] ✅ Connected to localhost")}catch(H){const j=zf();console.log("[VFF Connection] Localhost failed, trying cloud:",j),console.log("[VFF Connection] Local error was:",H),y.disconnect(),y=new jc(E,J,k),Zc(y,E),await y.connect(j),X=j,console.log("[VFF Connection] ✅ Connected to cloud")}}catch(H){throw console.error("[VFF Connection] Connection failed:",H),console.error("[VFF Connection] Error details:",{message:H instanceof Error?H.message:String(H),stack:H instanceof Error?H.stack:void 0,wsUrl:S}),f("error"),H}},pause(){console.log("[VFF Connection] Pausing (keeping connection warm)..."),L=!0,A?.isRecording()&&A.stopRecording(),A&&A.flushAudioQueue(),f("paused")},async resume(){if(console.log("[VFF Connection] Resuming..."),!y||y.getStatus()!=="connected"){console.error("[VFF Connection] Cannot resume - not connected"),f("error");return}L=!1,f("connected"),A&&!A.isRecording()&&await this.startRecording(),console.log("[VFF Connection] Resumed successfully")},disconnect(){di.endSession(),y&&(y.disconnect(),y=null),C&&(C.destroy(),C=null),A&&(A.destroy(),A=null),f("disconnected")},getStatus(){return y?.getStatus()??"disconnected"},sendAudio(V){y&&y.sendAudio(V)},sendActivityStart(){y&&y.sendActivityStart()},sendActivityEnd(){y&&y.sendActivityEnd()},sendPrompt(V){y&&y.sendPrompt(V)},sendRecoveryPrompt(V,H){y&&y.sendRecoveryPrompt(V,H)},endGeminiSession(){y&&y.endGeminiSession()},setPushToTalkMode(V){console.log(`[VFF Connection] Setting push-to-talk mode: ${V}`),we=V},getFieldManager(){return C},getAudioManager(){return A},async startRecording(){if(console.log("[VFF Connection] startRecording called"),!A){console.error("[VFF Connection] Audio manager not initialized");return}console.log("[VFF Connection] Requesting microphone access..."),await A.startRecording(V=>{y&&y.getStatus()==="connected"&&y.sendAudio(V)},{onEnergyChange:(V,H,j)=>{},onCalibrationComplete:V=>{console.log("[VFF Connection] 🎤 Audio calibration complete, baseline:",V)}})},stopRecording(){A&&A.stopRecording()},isRecording(){return A?.isRecording()??!1},isPaused(){return L},async changeFillLanguage(V){k=V,y&&y.getStatus()==="connected"?await y.changeFillLanguage(V):console.log("[VFF Connection] Language preference saved, will be used on next connect")},async startSection(V){if(!y)throw new Error("Connection not initialized");A?.isRecording()&&A.stopRecording(),await y.startSection(V,S),!L&&A&&await A.startRecording(H=>{y&&y.sendAudio(H)})},async switchSection(V){if(!y)throw new Error("Connection not initialized");A?.isRecording()&&A.stopRecording(),await y.switchSection(V,X),!L&&A&&await A.startRecording(H=>{y&&y.sendAudio(H)})},async completeSection(){if(!y)throw new Error("Connection not initialized");await y.completeSection(S)},getCurrentSection(){return y?.getCurrentSection()},getCompletedSections(){return y?.getCompletedSections()||new Set},onVADSpeechStart(){if(!A||we)return;A.isSpeaking()&&(console.log("[VFF Connection] 🎤 VAD detected speech - interrupting Gemini"),di.recordMicActivity(),A.flushAudioQueue(),di.recordTTSPaused(),y&&y.sendActivityStart(),di.recordCancelSent())},onVADSpeechEnd(){if(!A||we)return;A.isSpeaking()||A.resumePlayback(),y&&y.sendActivityEnd(),console.log("[VFF Connection] 🎤 VAD speech ended - sent activity_end")}}}function Df(){return Af()}var np={},Hr={},Bi={};Object.defineProperty(Bi,"__esModule",{value:!0});Bi.baseAssetPath=void 0;const Bf=typeof window<"u"&&typeof window.document<"u",Qc=Bf?window.document.currentScript:null;let rp="/";Qc&&(rp=Qc.src.replace(/#.*$/,"").replace(/\?.*$/,"").replace(/\/[^\/]+$/,"/"));Bi.baseAssetPath=rp;var yi={};Object.defineProperty(yi,"__esModule",{value:!0});yi.defaultModelFetcher=void 0;const Pf=E=>fetch(E).then(f=>f.arrayBuffer());yi.defaultModelFetcher=Pf;var Lt={},wi={};(function(E){Object.defineProperty(E,"__esModule",{value:!0}),E.log=E.LOG_PREFIX=void 0,E.LOG_PREFIX="[VAD]";const f=["error","debug","warn"];function b(S){return(...y)=>{console[S](E.LOG_PREFIX,...y)}}const v=f.reduce((S,y)=>(S[y]=b(y),S),{});E.log=v})(wi);var ci={};Object.defineProperty(ci,"__esModule",{value:!0});ci.Message=void 0;var Xc;(function(E){E.AudioFrame="AUDIO_FRAME",E.SpeechStart="SPEECH_START",E.VADMisfire="VAD_MISFIRE",E.SpeechEnd="SPEECH_END",E.SpeechStop="SPEECH_STOP",E.SpeechRealStart="SPEECH_REAL_START",E.FrameProcessed="FRAME_PROCESSED"})(Xc||(ci.Message=Xc={}));Object.defineProperty(Lt,"__esModule",{value:!0});Lt.FrameProcessor=Lt.validateOptions=Lt.defaultFrameProcessorOptions=void 0;const Fi=wi,ui=ci;Lt.defaultFrameProcessorOptions={positiveSpeechThreshold:.3,negativeSpeechThreshold:.25,preSpeechPadMs:800,redemptionMs:1400,minSpeechMs:400,submitUserSpeechOnPause:!1};function Nf(E){(E.positiveSpeechThreshold<0||E.positiveSpeechThreshold>1)&&Fi.log.error("positiveSpeechThreshold should be a number between 0 and 1"),(E.negativeSpeechThreshold<0||E.negativeSpeechThreshold>E.positiveSpeechThreshold)&&Fi.log.error("negativeSpeechThreshold should be between 0 and positiveSpeechThreshold"),E.preSpeechPadMs<0&&Fi.log.error("preSpeechPadMs should be positive"),E.redemptionMs<0&&Fi.log.error("redemptionMs should be positive"),E.minSpeechMs<0&&Fi.log.error("minSpeechMs should be positive")}Lt.validateOptions=Nf;const Yc=E=>{const f=E.reduce((v,S)=>(v.push(v.at(-1)+S.length),v),[0]),b=new Float32Array(f.at(-1));return E.forEach((v,S)=>{const y=f[S];b.set(v,y)}),b};class Vf{constructor(f,b,v,S){this.modelProcessFunc=f,this.modelResetFunc=b,this.options=v,this.msPerFrame=S,this.speaking=!1,this.redemptionCounter=0,this.speechFrameCount=0,this.active=!1,this.speechRealStartFired=!1,this.reset=()=>{this.speaking=!1,this.speechRealStartFired=!1,this.audioBuffer=[],this.modelResetFunc(),this.redemptionCounter=0,this.speechFrameCount=0},this.pause=y=>{this.active=!1,this.options.submitUserSpeechOnPause?this.endSegment(y):this.reset()},this.resume=()=>{this.active=!0},this.endSegment=y=>{const C=this.audioBuffer;this.audioBuffer=[];const A=this.speaking;if(this.reset(),A)if(C.reduce((L,X)=>X.isSpeech?L+1:L,0)>=this.minSpeechFrames){const L=Yc(C.map(X=>X.frame));y({msg:ui.Message.SpeechEnd,audio:L})}else y({msg:ui.Message.VADMisfire});return{}},this.process=async(y,C)=>{if(!this.active)return;const A=await this.modelProcessFunc(y),k=A.isSpeech>=this.options.positiveSpeechThreshold;if(C({probs:A,msg:ui.Message.FrameProcessed,frame:y}),this.audioBuffer.push({frame:y,isSpeech:k}),k&&(this.speechFrameCount++,this.redemptionCounter=0),k&&!this.speaking&&(this.speaking=!0,C({msg:ui.Message.SpeechStart})),this.speaking&&this.speechFrameCount===this.minSpeechFrames&&!this.speechRealStartFired&&(this.speechRealStartFired=!0,C({msg:ui.Message.SpeechRealStart})),A.isSpeech<this.options.negativeSpeechThreshold&&this.speaking&&++this.redemptionCounter>=this.redemptionFrames){this.redemptionCounter=0,this.speechFrameCount=0,this.speaking=!1,this.speechRealStartFired=!1;const L=this.audioBuffer;if(this.audioBuffer=[],L.reduce((we,Y)=>Y.isSpeech?we+1:we,0)>=this.minSpeechFrames){const we=Yc(L.map(Y=>Y.frame));C({msg:ui.Message.SpeechEnd,audio:we})}else C({msg:ui.Message.VADMisfire})}if(!this.speaking){for(;this.audioBuffer.length>this.preSpeechPadFrames;)this.audioBuffer.shift();this.speechFrameCount=0}},this.audioBuffer=[],this.redemptionFrames=Math.floor(v.redemptionMs/this.msPerFrame),this.preSpeechPadFrames=Math.floor(v.preSpeechPadMs/this.msPerFrame),this.minSpeechFrames=Math.floor(v.minSpeechMs/this.msPerFrame),this.reset()}}Lt.FrameProcessor=Vf;var sp={};function _i(E){throw new Error('Could not dynamically require "'+E+'". Please configure the dynamicRequireTargets or/and ignoreDynamicRequires option of @rollup/plugin-commonjs appropriately for this require call to work.')}var ap={exports:{}};/*!
 * ONNX Runtime Web v1.23.0
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License.
 */(function(E,f){var b=(()=>{var v=Object.defineProperty,S=Object.getOwnPropertyDescriptor,y=Object.getOwnPropertyNames,C=Object.prototype.hasOwnProperty,A=(e=>typeof _i<"u"?_i:typeof Proxy<"u"?new Proxy(e,{get:(t,i)=>(typeof _i<"u"?_i:t)[i]}):e)(function(e){if(typeof _i<"u")return _i.apply(this,arguments);throw Error('Dynamic require of "'+e+'" is not supported')}),k=(e,t)=>()=>(e&&(t=e(e=0)),t),L=(e,t)=>{for(var i in t)v(e,i,{get:t[i],enumerable:!0})},X=(e,t,i,n)=>{if(t&&typeof t=="object"||typeof t=="function")for(let r of y(t))!C.call(e,r)&&r!==i&&v(e,r,{get:()=>t[r],enumerable:!(n=S(t,r))||n.enumerable});return e},we=e=>X(v({},"__esModule",{value:!0}),e),Y,J,V,H,j,K=k(()=>{Y=new Map,J=[],V=(e,t,i)=>{if(t&&typeof t.init=="function"&&typeof t.createInferenceSessionHandler=="function"){let n=Y.get(e);if(n===void 0)Y.set(e,{backend:t,priority:i});else{if(n.priority>i)return;if(n.priority===i&&n.backend!==t)throw new Error(`cannot register backend "${e}" using priority ${i}`)}if(i>=0){let r=J.indexOf(e);r!==-1&&J.splice(r,1);for(let s=0;s<J.length;s++)if(Y.get(J[s]).priority<=i){J.splice(s,0,e);return}J.push(e)}return}throw new TypeError("not a valid backend")},H=async e=>{let t=Y.get(e);if(!t)return"backend not found.";if(t.initialized)return t.backend;if(t.aborted)return t.error;{let i=!!t.initPromise;try{return i||(t.initPromise=t.backend.init(e)),await t.initPromise,t.initialized=!0,t.backend}catch(n){return i||(t.error=`${n}`,t.aborted=!0),t.error}finally{delete t.initPromise}}},j=async e=>{let t=e.executionProviders||[],i=t.map(l=>typeof l=="string"?l:l.name),n=i.length===0?J:i,r,s=[],a=new Set;for(let l of n){let u=await H(l);typeof u=="string"?s.push({name:l,err:u}):(r||(r=u),r===u&&a.add(l))}if(!r)throw new Error(`no available backend found. ERR: ${s.map(l=>`[${l.name}] ${l.err}`).join(", ")}`);for(let{name:l,err:u}of s)i.includes(l)&&console.warn(`removing requested execution provider "${l}" from session options because it is not available: ${u}`);let o=t.filter(l=>a.has(typeof l=="string"?l:l.name));return[r,new Proxy(e,{get:(l,u)=>u==="executionProviders"?o:Reflect.get(l,u)})]}}),R=k(()=>{K()}),D,F=k(()=>{D="1.23.0"}),U,P,G=k(()=>{F(),U="warning",P={wasm:{},webgl:{},webgpu:{},versions:{common:D},set logLevel(e){if(e!==void 0){if(typeof e!="string"||["verbose","info","warning","error","fatal"].indexOf(e)===-1)throw new Error(`Unsupported logging level: ${e}`);U=e}},get logLevel(){return U}},Object.defineProperty(P,"logLevel",{enumerable:!0})}),oe,Ae=k(()=>{G(),oe=P}),me,qe,Ne=k(()=>{me=(e,t)=>{let i=typeof document<"u"?document.createElement("canvas"):new OffscreenCanvas(1,1);i.width=e.dims[3],i.height=e.dims[2];let n=i.getContext("2d");if(n!=null){let r,s;t?.tensorLayout!==void 0&&t.tensorLayout==="NHWC"?(r=e.dims[2],s=e.dims[3]):(r=e.dims[3],s=e.dims[2]);let a=t?.format!==void 0?t.format:"RGB",o=t?.norm,l,u;o===void 0||o.mean===void 0?l=[255,255,255,255]:typeof o.mean=="number"?l=[o.mean,o.mean,o.mean,o.mean]:(l=[o.mean[0],o.mean[1],o.mean[2],0],o.mean[3]!==void 0&&(l[3]=o.mean[3])),o===void 0||o.bias===void 0?u=[0,0,0,0]:typeof o.bias=="number"?u=[o.bias,o.bias,o.bias,o.bias]:(u=[o.bias[0],o.bias[1],o.bias[2],0],o.bias[3]!==void 0&&(u[3]=o.bias[3]));let d=s*r,c=0,p=d,h=d*2,m=-1;a==="RGBA"?(c=0,p=d,h=d*2,m=d*3):a==="RGB"?(c=0,p=d,h=d*2):a==="RBG"&&(c=0,h=d,p=d*2);for(let _=0;_<s;_++)for(let $=0;$<r;$++){let w=(e.data[c++]-u[0])*l[0],g=(e.data[p++]-u[1])*l[1],T=(e.data[h++]-u[2])*l[2],x=m===-1?255:(e.data[m++]-u[3])*l[3];n.fillStyle="rgba("+w+","+g+","+T+","+x+")",n.fillRect($,_,1,1)}if("toDataURL"in i)return i.toDataURL();throw new Error("toDataURL is not supported")}else throw new Error("Can not access image data")},qe=(e,t)=>{let i=typeof document<"u"?document.createElement("canvas").getContext("2d"):new OffscreenCanvas(1,1).getContext("2d"),n;if(i!=null){let r,s,a;t?.tensorLayout!==void 0&&t.tensorLayout==="NHWC"?(r=e.dims[2],s=e.dims[1],a=e.dims[3]):(r=e.dims[3],s=e.dims[2],a=e.dims[1]);let o=t!==void 0&&t.format!==void 0?t.format:"RGB",l=t?.norm,u,d;l===void 0||l.mean===void 0?u=[255,255,255,255]:typeof l.mean=="number"?u=[l.mean,l.mean,l.mean,l.mean]:(u=[l.mean[0],l.mean[1],l.mean[2],255],l.mean[3]!==void 0&&(u[3]=l.mean[3])),l===void 0||l.bias===void 0?d=[0,0,0,0]:typeof l.bias=="number"?d=[l.bias,l.bias,l.bias,l.bias]:(d=[l.bias[0],l.bias[1],l.bias[2],0],l.bias[3]!==void 0&&(d[3]=l.bias[3]));let c=s*r;if(t!==void 0&&(t.format!==void 0&&a===4&&t.format!=="RGBA"||a===3&&t.format!=="RGB"&&t.format!=="BGR"))throw new Error("Tensor format doesn't match input tensor dims");let p=4,h=0,m=1,_=2,$=3,w=0,g=c,T=c*2,x=-1;o==="RGBA"?(w=0,g=c,T=c*2,x=c*3):o==="RGB"?(w=0,g=c,T=c*2):o==="RBG"&&(w=0,T=c,g=c*2),n=i.createImageData(r,s);for(let I=0;I<s*r;h+=p,m+=p,_+=p,$+=p,I++)n.data[h]=(e.data[w++]-d[0])*u[0],n.data[m]=(e.data[g++]-d[1])*u[1],n.data[_]=(e.data[T++]-d[2])*u[2],n.data[$]=x===-1?255:(e.data[x++]-d[3])*u[3]}else throw new Error("Can not access image data");return n}}),Ce,Ke,ze,Ye,tt,ft,rt=k(()=>{yt(),Ce=(e,t)=>{if(e===void 0)throw new Error("Image buffer must be defined");if(t.height===void 0||t.width===void 0)throw new Error("Image height and width must be defined");if(t.tensorLayout==="NHWC")throw new Error("NHWC Tensor layout is not supported yet");let{height:i,width:n}=t,r=t.norm??{mean:255,bias:0},s,a;typeof r.mean=="number"?s=[r.mean,r.mean,r.mean,r.mean]:s=[r.mean[0],r.mean[1],r.mean[2],r.mean[3]??255],typeof r.bias=="number"?a=[r.bias,r.bias,r.bias,r.bias]:a=[r.bias[0],r.bias[1],r.bias[2],r.bias[3]??0];let o=t.format!==void 0?t.format:"RGBA",l=t.tensorFormat!==void 0&&t.tensorFormat!==void 0?t.tensorFormat:"RGB",u=i*n,d=l==="RGBA"?new Float32Array(u*4):new Float32Array(u*3),c=4,p=0,h=1,m=2,_=3,$=0,w=u,g=u*2,T=-1;o==="RGB"&&(c=3,p=0,h=1,m=2,_=-1),l==="RGBA"?T=u*3:l==="RBG"?($=0,g=u,w=u*2):l==="BGR"&&(g=0,w=u,$=u*2);for(let x=0;x<u;x++,p+=c,m+=c,h+=c,_+=c)d[$++]=(e[p]+a[0])/s[0],d[w++]=(e[h]+a[1])/s[1],d[g++]=(e[m]+a[2])/s[2],T!==-1&&_!==-1&&(d[T++]=(e[_]+a[3])/s[3]);return l==="RGBA"?new Me("float32",d,[1,4,i,n]):new Me("float32",d,[1,3,i,n])},Ke=async(e,t)=>{let i=typeof HTMLImageElement<"u"&&e instanceof HTMLImageElement,n=typeof ImageData<"u"&&e instanceof ImageData,r=typeof ImageBitmap<"u"&&e instanceof ImageBitmap,s=typeof e=="string",a,o=t??{},l=()=>{if(typeof document<"u")return document.createElement("canvas");if(typeof OffscreenCanvas<"u")return new OffscreenCanvas(1,1);throw new Error("Canvas is not supported")},u=d=>typeof HTMLCanvasElement<"u"&&d instanceof HTMLCanvasElement||d instanceof OffscreenCanvas?d.getContext("2d"):null;if(i){let d=l();d.width=e.width,d.height=e.height;let c=u(d);if(c!=null){let p=e.height,h=e.width;if(t!==void 0&&t.resizedHeight!==void 0&&t.resizedWidth!==void 0&&(p=t.resizedHeight,h=t.resizedWidth),t!==void 0){if(o=t,t.tensorFormat!==void 0)throw new Error("Image input config format must be RGBA for HTMLImageElement");o.tensorFormat="RGBA",o.height=p,o.width=h}else o.tensorFormat="RGBA",o.height=p,o.width=h;c.drawImage(e,0,0),a=c.getImageData(0,0,h,p).data}else throw new Error("Can not access image data")}else if(n){let d,c;if(t!==void 0&&t.resizedWidth!==void 0&&t.resizedHeight!==void 0?(d=t.resizedHeight,c=t.resizedWidth):(d=e.height,c=e.width),t!==void 0&&(o=t),o.format="RGBA",o.height=d,o.width=c,t!==void 0){let p=l();p.width=c,p.height=d;let h=u(p);if(h!=null)h.putImageData(e,0,0),a=h.getImageData(0,0,c,d).data;else throw new Error("Can not access image data")}else a=e.data}else if(r){if(t===void 0)throw new Error("Please provide image config with format for Imagebitmap");let d=l();d.width=e.width,d.height=e.height;let c=u(d);if(c!=null){let p=e.height,h=e.width;return c.drawImage(e,0,0,h,p),a=c.getImageData(0,0,h,p).data,o.height=p,o.width=h,Ce(a,o)}else throw new Error("Can not access image data")}else{if(s)return new Promise((d,c)=>{let p=l(),h=u(p);if(!e||!h)return c();let m=new Image;m.crossOrigin="Anonymous",m.src=e,m.onload=()=>{p.width=m.width,p.height=m.height,h.drawImage(m,0,0,p.width,p.height);let _=h.getImageData(0,0,p.width,p.height);o.height=p.height,o.width=p.width,d(Ce(_.data,o))}});throw new Error("Input data provided is not supported - aborted tensor creation")}if(a!==void 0)return Ce(a,o);throw new Error("Input data provided is not supported - aborted tensor creation")},ze=(e,t)=>{let{width:i,height:n,download:r,dispose:s}=t,a=[1,n,i,4];return new Me({location:"texture",type:"float32",texture:e,dims:a,download:r,dispose:s})},Ye=(e,t)=>{let{dataType:i,dims:n,download:r,dispose:s}=t;return new Me({location:"gpu-buffer",type:i??"float32",gpuBuffer:e,dims:n,download:r,dispose:s})},tt=(e,t)=>{let{dataType:i,dims:n,download:r,dispose:s}=t;return new Me({location:"ml-tensor",type:i??"float32",mlTensor:e,dims:n,download:r,dispose:s})},ft=(e,t,i)=>new Me({location:"cpu-pinned",type:e,data:t,dims:i??[t.length]})}),gt,Ee,st,vt,Tt=k(()=>{gt=new Map([["float32",Float32Array],["uint8",Uint8Array],["int8",Int8Array],["uint16",Uint16Array],["int16",Int16Array],["int32",Int32Array],["bool",Uint8Array],["float64",Float64Array],["uint32",Uint32Array],["int4",Uint8Array],["uint4",Uint8Array]]),Ee=new Map([[Float32Array,"float32"],[Uint8Array,"uint8"],[Int8Array,"int8"],[Uint16Array,"uint16"],[Int16Array,"int16"],[Int32Array,"int32"],[Float64Array,"float64"],[Uint32Array,"uint32"]]),st=!1,vt=()=>{if(!st){st=!0;let e=typeof BigInt64Array<"u"&&BigInt64Array.from,t=typeof BigUint64Array<"u"&&BigUint64Array.from,i=globalThis.Float16Array,n=typeof i<"u"&&i.from;e&&(gt.set("int64",BigInt64Array),Ee.set(BigInt64Array,"int64")),t&&(gt.set("uint64",BigUint64Array),Ee.set(BigUint64Array,"uint64")),n?(gt.set("float16",i),Ee.set(i,"float16")):gt.set("float16",Uint16Array)}}}),it,ht,ot=k(()=>{yt(),it=e=>{let t=1;for(let i=0;i<e.length;i++){let n=e[i];if(typeof n!="number"||!Number.isSafeInteger(n))throw new TypeError(`dims[${i}] must be an integer, got: ${n}`);if(n<0)throw new RangeError(`dims[${i}] must be a non-negative integer, got: ${n}`);t*=n}return t},ht=(e,t)=>{switch(e.location){case"cpu":return new Me(e.type,e.data,t);case"cpu-pinned":return new Me({location:"cpu-pinned",data:e.data,type:e.type,dims:t});case"texture":return new Me({location:"texture",texture:e.texture,type:e.type,dims:t});case"gpu-buffer":return new Me({location:"gpu-buffer",gpuBuffer:e.gpuBuffer,type:e.type,dims:t});case"ml-tensor":return new Me({location:"ml-tensor",mlTensor:e.mlTensor,type:e.type,dims:t});default:throw new Error(`tensorReshape: tensor location ${e.location} is not supported`)}}}),Me,yt=k(()=>{Ne(),rt(),Tt(),ot(),Me=class{constructor(e,t,i){vt();let n,r;if(typeof e=="object"&&"location"in e)switch(this.dataLocation=e.location,n=e.type,r=e.dims,e.location){case"cpu-pinned":{let a=gt.get(n);if(!a)throw new TypeError(`unsupported type "${n}" to create tensor from pinned buffer`);if(!(e.data instanceof a))throw new TypeError(`buffer should be of type ${a.name}`);this.cpuData=e.data;break}case"texture":{if(n!=="float32")throw new TypeError(`unsupported type "${n}" to create tensor from texture`);this.gpuTextureData=e.texture,this.downloader=e.download,this.disposer=e.dispose;break}case"gpu-buffer":{if(n!=="float32"&&n!=="float16"&&n!=="int32"&&n!=="int64"&&n!=="uint32"&&n!=="uint8"&&n!=="bool"&&n!=="uint4"&&n!=="int4")throw new TypeError(`unsupported type "${n}" to create tensor from gpu buffer`);this.gpuBufferData=e.gpuBuffer,this.downloader=e.download,this.disposer=e.dispose;break}case"ml-tensor":{if(n!=="float32"&&n!=="float16"&&n!=="int32"&&n!=="int64"&&n!=="uint32"&&n!=="uint64"&&n!=="int8"&&n!=="uint8"&&n!=="bool"&&n!=="uint4"&&n!=="int4")throw new TypeError(`unsupported type "${n}" to create tensor from MLTensor`);this.mlTensorData=e.mlTensor,this.downloader=e.download,this.disposer=e.dispose;break}default:throw new Error(`Tensor constructor: unsupported location '${this.dataLocation}'`)}else{let a,o;if(typeof e=="string")if(n=e,o=i,e==="string"){if(!Array.isArray(t))throw new TypeError("A string tensor's data must be a string array.");a=t}else{let l=gt.get(e);if(l===void 0)throw new TypeError(`Unsupported tensor type: ${e}.`);if(Array.isArray(t)){if(e==="float16"&&l===Uint16Array||e==="uint4"||e==="int4")throw new TypeError(`Creating a ${e} tensor from number array is not supported. Please use ${l.name} as data.`);e==="uint64"||e==="int64"?a=l.from(t,BigInt):a=l.from(t)}else if(t instanceof l)a=t;else if(t instanceof Uint8ClampedArray)if(e==="uint8")a=Uint8Array.from(t);else throw new TypeError("A Uint8ClampedArray tensor's data must be type of uint8");else if(e==="float16"&&t instanceof Uint16Array&&l!==Uint16Array)a=new globalThis.Float16Array(t.buffer,t.byteOffset,t.length);else throw new TypeError(`A ${n} tensor's data must be type of ${l}`)}else if(o=t,Array.isArray(e)){if(e.length===0)throw new TypeError("Tensor type cannot be inferred from an empty array.");let l=typeof e[0];if(l==="string")n="string",a=e;else if(l==="boolean")n="bool",a=Uint8Array.from(e);else throw new TypeError(`Invalid element type of data array: ${l}.`)}else if(e instanceof Uint8ClampedArray)n="uint8",a=Uint8Array.from(e);else{let l=Ee.get(e.constructor);if(l===void 0)throw new TypeError(`Unsupported type for tensor data: ${e.constructor}.`);n=l,a=e}if(o===void 0)o=[a.length];else if(!Array.isArray(o))throw new TypeError("A tensor's dims must be a number array");r=o,this.cpuData=a,this.dataLocation="cpu"}let s=it(r);if(this.cpuData&&s!==this.cpuData.length&&!((n==="uint4"||n==="int4")&&Math.ceil(s/2)===this.cpuData.length))throw new Error(`Tensor's size(${s}) does not match data length(${this.cpuData.length}).`);this.type=n,this.dims=r,this.size=s}static async fromImage(e,t){return Ke(e,t)}static fromTexture(e,t){return ze(e,t)}static fromGpuBuffer(e,t){return Ye(e,t)}static fromMLTensor(e,t){return tt(e,t)}static fromPinnedBuffer(e,t,i){return ft(e,t,i)}toDataURL(e){return me(this,e)}toImageData(e){return qe(this,e)}get data(){if(this.ensureValid(),!this.cpuData)throw new Error("The data is not on CPU. Use `getData()` to download GPU data to CPU, or use `texture` or `gpuBuffer` property to access the GPU data directly.");return this.cpuData}get location(){return this.dataLocation}get texture(){if(this.ensureValid(),!this.gpuTextureData)throw new Error("The data is not stored as a WebGL texture.");return this.gpuTextureData}get gpuBuffer(){if(this.ensureValid(),!this.gpuBufferData)throw new Error("The data is not stored as a WebGPU buffer.");return this.gpuBufferData}get mlTensor(){if(this.ensureValid(),!this.mlTensorData)throw new Error("The data is not stored as a WebNN MLTensor.");return this.mlTensorData}async getData(e){switch(this.ensureValid(),this.dataLocation){case"cpu":case"cpu-pinned":return this.data;case"texture":case"gpu-buffer":case"ml-tensor":{if(!this.downloader)throw new Error("The current tensor is not created with a specified data downloader.");if(this.isDownloading)throw new Error("The current tensor is being downloaded.");try{this.isDownloading=!0;let t=await this.downloader();return this.downloader=void 0,this.dataLocation="cpu",this.cpuData=t,e&&this.disposer&&(this.disposer(),this.disposer=void 0),t}finally{this.isDownloading=!1}}default:throw new Error(`cannot get data from location: ${this.dataLocation}`)}}dispose(){if(this.isDownloading)throw new Error("The current tensor is being downloaded.");this.disposer&&(this.disposer(),this.disposer=void 0),this.cpuData=void 0,this.gpuTextureData=void 0,this.gpuBufferData=void 0,this.mlTensorData=void 0,this.downloader=void 0,this.isDownloading=void 0,this.dataLocation="none"}ensureValid(){if(this.dataLocation==="none")throw new Error("The tensor is disposed.")}reshape(e){if(this.ensureValid(),this.downloader||this.disposer)throw new Error("Cannot reshape a tensor that owns GPU resource.");return ht(this,e)}}}),lt,Et=k(()=>{yt(),lt=Me}),St,Be,ue,Pe,Ue,je,mt=k(()=>{G(),St=(e,t)=>{(typeof P.trace>"u"?!P.wasm.trace:!P.trace)||console.timeStamp(`${e}::ORT::${t}`)},Be=(e,t)=>{let i=new Error().stack?.split(/\r\n|\r|\n/g)||[],n=!1;for(let r=0;r<i.length;r++){if(n&&!i[r].includes("TRACE_FUNC")){let s=`FUNC_${e}::${i[r].trim().split(" ")[1]}`;t&&(s+=`::${t}`),St("CPU",s);return}i[r].includes("TRACE_FUNC")&&(n=!0)}},ue=e=>{(typeof P.trace>"u"?!P.wasm.trace:!P.trace)||Be("BEGIN",e)},Pe=e=>{(typeof P.trace>"u"?!P.wasm.trace:!P.trace)||Be("END",e)},Ue=e=>{(typeof P.trace>"u"?!P.wasm.trace:!P.trace)||console.time(`ORT::${e}`)},je=e=>{(typeof P.trace>"u"?!P.wasm.trace:!P.trace)||console.timeEnd(`ORT::${e}`)}}),Ft,Ct=k(()=>{K(),Et(),mt(),Ft=class op{constructor(t){this.handler=t}async run(t,i,n){ue(),Ue("InferenceSession.run");let r={},s={};if(typeof t!="object"||t===null||t instanceof lt||Array.isArray(t))throw new TypeError("'feeds' must be an object that use input names as keys and OnnxValue as corresponding values.");let a=!0;if(typeof i=="object"){if(i===null)throw new TypeError("Unexpected argument[1]: cannot be null.");if(i instanceof lt)throw new TypeError("'fetches' cannot be a Tensor");if(Array.isArray(i)){if(i.length===0)throw new TypeError("'fetches' cannot be an empty array.");a=!1;for(let u of i){if(typeof u!="string")throw new TypeError("'fetches' must be a string array or an object.");if(this.outputNames.indexOf(u)===-1)throw new RangeError(`'fetches' contains invalid output name: ${u}.`);r[u]=null}if(typeof n=="object"&&n!==null)s=n;else if(typeof n<"u")throw new TypeError("'options' must be an object.")}else{let u=!1,d=Object.getOwnPropertyNames(i);for(let c of this.outputNames)if(d.indexOf(c)!==-1){let p=i[c];(p===null||p instanceof lt)&&(u=!0,a=!1,r[c]=p)}if(u){if(typeof n=="object"&&n!==null)s=n;else if(typeof n<"u")throw new TypeError("'options' must be an object.")}else s=i}}else if(typeof i<"u")throw new TypeError("Unexpected argument[1]: must be 'fetches' or 'options'.");for(let u of this.inputNames)if(typeof t[u]>"u")throw new Error(`input '${u}' is missing in 'feeds'.`);if(a)for(let u of this.outputNames)r[u]=null;let o=await this.handler.run(t,r,s),l={};for(let u in o)if(Object.hasOwnProperty.call(o,u)){let d=o[u];d instanceof lt?l[u]=d:l[u]=new lt(d.type,d.data,d.dims)}return je("InferenceSession.run"),Pe(),l}async release(){return this.handler.dispose()}static async create(t,i,n,r){ue(),Ue("InferenceSession.create");let s,a={};if(typeof t=="string"){if(s=t,typeof i=="object"&&i!==null)a=i;else if(typeof i<"u")throw new TypeError("'options' must be an object.")}else if(t instanceof Uint8Array){if(s=t,typeof i=="object"&&i!==null)a=i;else if(typeof i<"u")throw new TypeError("'options' must be an object.")}else if(t instanceof ArrayBuffer||typeof SharedArrayBuffer<"u"&&t instanceof SharedArrayBuffer){let d=t,c=0,p=t.byteLength;if(typeof i=="object"&&i!==null)a=i;else if(typeof i=="number"){if(c=i,!Number.isSafeInteger(c))throw new RangeError("'byteOffset' must be an integer.");if(c<0||c>=d.byteLength)throw new RangeError(`'byteOffset' is out of range [0, ${d.byteLength}).`);if(p=t.byteLength-c,typeof n=="number"){if(p=n,!Number.isSafeInteger(p))throw new RangeError("'byteLength' must be an integer.");if(p<=0||c+p>d.byteLength)throw new RangeError(`'byteLength' is out of range (0, ${d.byteLength-c}].`);if(typeof r=="object"&&r!==null)a=r;else if(typeof r<"u")throw new TypeError("'options' must be an object.")}else if(typeof n<"u")throw new TypeError("'byteLength' must be a number.")}else if(typeof i<"u")throw new TypeError("'options' must be an object.");s=new Uint8Array(d,c,p)}else throw new TypeError("Unexpected argument[0]: must be 'path' or 'buffer'.");let[o,l]=await j(a),u=await o.createInferenceSessionHandler(s,l);return je("InferenceSession.create"),Pe(),new op(u)}startProfiling(){this.handler.startProfiling()}endProfiling(){this.handler.endProfiling()}get inputNames(){return this.handler.inputNames}get outputNames(){return this.handler.outputNames}get inputMetadata(){return this.handler.inputMetadata}get outputMetadata(){return this.handler.outputMetadata}}}),ut,pe=k(()=>{Ct(),ut=Ft}),ge=k(()=>{}),Ze=k(()=>{}),Dt=k(()=>{}),Bt=k(()=>{}),Ut={};L(Ut,{InferenceSession:()=>ut,TRACE:()=>St,TRACE_EVENT_BEGIN:()=>Ue,TRACE_EVENT_END:()=>je,TRACE_FUNC_BEGIN:()=>ue,TRACE_FUNC_END:()=>Pe,Tensor:()=>lt,env:()=>oe,registerBackend:()=>V});var wt=k(()=>{R(),Ae(),pe(),Et(),ge(),Ze(),mt(),Dt(),Bt()}),ie=k(()=>{}),fe={};L(fe,{default:()=>Je});var ke,Fe,Je,pi=k(()=>{Ac(),Yt(),_n(),ke="ort-wasm-proxy-worker",Fe=globalThis.self?.name===ke,Fe&&(self.onmessage=e=>{let{type:t,in:i}=e.data;try{switch(t){case"init-wasm":bn(i.wasm).then(()=>{zr(i).then(()=>{postMessage({type:t})},n=>{postMessage({type:t,err:n})})},n=>{postMessage({type:t,err:n})});break;case"init-ep":{let{epName:n,env:r}=i;Rr(r,n).then(()=>{postMessage({type:t})},s=>{postMessage({type:t,err:s})});break}case"copy-from":{let{buffer:n}=i,r=rn(n);postMessage({type:t,out:r});break}case"create":{let{model:n,options:r}=i;Mr(n,r).then(s=>{postMessage({type:t,out:s})},s=>{postMessage({type:t,err:s})});break}case"release":Fr(i),postMessage({type:t});break;case"run":{let{sessionId:n,inputIndices:r,inputs:s,outputIndices:a,options:o}=i;Br(n,r,s,a,new Array(a.length).fill(null),o).then(l=>{l.some(u=>u[3]!=="cpu")?postMessage({type:t,err:"Proxy does not support non-cpu tensor location."}):postMessage({type:t,out:l},Nr([...s,...l]))},l=>{postMessage({type:t,err:l})});break}case"end-profiling":Pr(i),postMessage({type:t});break;default:}}catch(n){postMessage({type:t,err:n})}}),Je=Fe?null:e=>new Worker(e??$t,{type:"classic",name:ke})}),Xt,ts,$t,fn,Ni,is,ns,hn,rs,mn,ss,gn,as,_n=k(()=>{ie(),Xt=typeof location>"u"?void 0:location.origin,ts=()=>typeof document<"u"?document.currentScript?.src:typeof self<"u"?self.location?.href:void 0,$t=ts(),fn=()=>{if($t&&!$t.startsWith("blob:"))return $t.substring(0,$t.lastIndexOf("/")+1)},Ni=(e,t)=>{try{let i=t??$t;return(i?new URL(e,i):new URL(e)).origin===Xt}catch{return!1}},is=(e,t)=>{let i=t??$t;try{return(i?new URL(e,i):new URL(e)).href}catch{return}},ns=(e,t)=>`${t??"./"}${e}`,hn=async e=>{let t=await(await fetch(e,{credentials:"same-origin"})).blob();return URL.createObjectURL(t)},rs=async e=>(await import(e)).default,mn=(pi(),we(fe)).default,ss=async()=>{if(!$t)throw new Error("Failed to load proxy worker: cannot determine the script source URL.");if(Ni($t))return[void 0,mn()];let e=await hn($t);return[e,mn(e)]},gn=void 0,as=async(e,t,i,n)=>{let r=gn&&!(e||t);if(r)if($t)r=Ni($t);else if(n&&!i)r=!0;else throw new Error("cannot determine the script source URL.");if(r)return[void 0,gn];{let s="ort-wasm-simd-threaded.jsep.mjs",a=e??is(s,t),o=i&&a&&!Ni(a,t),l=o?await hn(a):a??ns(s,t);return[o?l:void 0,await rs(l)]}}}),yn,Vi,bi,wn,os,ls,us,bn,We,Yt=k(()=>{_n(),Vi=!1,bi=!1,wn=!1,os=()=>{if(typeof SharedArrayBuffer>"u")return!1;try{return typeof MessageChannel<"u"&&new MessageChannel().port1.postMessage(new SharedArrayBuffer(1)),WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,4,1,96,0,0,3,2,1,0,5,4,1,3,1,1,10,11,1,9,0,65,0,254,16,2,0,26,11]))}catch{return!1}},ls=()=>{try{return WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,4,1,96,0,0,3,2,1,0,10,30,1,28,0,65,0,253,15,253,12,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,253,186,1,26,11]))}catch{return!1}},us=()=>{try{return WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,10,19,1,17,0,65,1,253,15,65,2,253,15,65,3,253,15,253,147,2,11]))}catch{return!1}},bn=async e=>{if(Vi)return Promise.resolve();if(bi)throw new Error("multiple calls to 'initializeWebAssembly()' detected.");if(wn)throw new Error("previous call to 'initializeWebAssembly()' failed.");bi=!0;let t=e.initTimeout,i=e.numThreads;if(e.simd!==!1){if(e.simd==="relaxed"){if(!us())throw new Error("Relaxed WebAssembly SIMD is not supported in the current environment.")}else if(!ls())throw new Error("WebAssembly SIMD is not supported in the current environment.")}let n=os();i>1&&!n&&(typeof self<"u"&&!self.crossOriginIsolated&&console.warn("env.wasm.numThreads is set to "+i+", but this will not work unless you enable crossOriginIsolated mode. See https://web.dev/cross-origin-isolation-guide/ for more info."),console.warn("WebAssembly multi-threading is not supported in the current environment. Falling back to single-threading."),e.numThreads=i=1);let r=e.wasmPaths,s=typeof r=="string"?r:void 0,a=r?.mjs,o=a?.href??a,l=r?.wasm,u=l?.href??l,d=e.wasmBinary,[c,p]=await as(o,s,i>1,!!d||!!u),h=!1,m=[];if(t>0&&m.push(new Promise(_=>{setTimeout(()=>{h=!0,_()},t)})),m.push(new Promise((_,$)=>{let w={numThreads:i};if(d)w.wasmBinary=d;else if(u||s)w.locateFile=g=>u??s+g;else if(o&&o.indexOf("blob:")!==0)w.locateFile=g=>new URL(g,o).href;else if(c){let g=fn();g&&(w.locateFile=T=>g+T)}p(w).then(g=>{bi=!1,Vi=!0,yn=g,_(),c&&URL.revokeObjectURL(c)},g=>{bi=!1,wn=!0,$(g)})})),await Promise.race(m),h)throw new Error(`WebAssembly backend initializing failed due to timeout: ${t}ms`)},We=()=>{if(Vi&&yn)return yn;throw new Error("WebAssembly is not initialized yet.")}}),It,Li,Ve,vn=k(()=>{Yt(),It=(e,t)=>{let i=We(),n=i.lengthBytesUTF8(e)+1,r=i._malloc(n);return i.stringToUTF8(e,r,n),t.push(r),r},Li=(e,t,i,n)=>{if(typeof e=="object"&&e!==null){if(i.has(e))throw new Error("Circular reference in options");i.add(e)}Object.entries(e).forEach(([r,s])=>{let a=t?t+r:r;if(typeof s=="object")Li(s,a+".",i,n);else if(typeof s=="string"||typeof s=="number")n(a,s.toString());else if(typeof s=="boolean")n(a,s?"1":"0");else throw new Error(`Can't handle extra config type: ${typeof s}`)})},Ve=e=>{let t=We(),i=t.stackSave();try{let n=t.PTR_SIZE,r=t.stackAlloc(2*n);t._OrtGetLastError(r,r+n);let s=Number(t.getValue(r,n===4?"i32":"i64")),a=t.getValue(r+n,"*"),o=a?t.UTF8ToString(a):"";throw new Error(`${e} ERROR_CODE: ${s}, ERROR_MESSAGE: ${o}`)}finally{t.stackRestore(i)}}}),ds,gp=k(()=>{Yt(),vn(),ds=e=>{let t=We(),i=0,n=[],r=e||{};try{if(e?.logSeverityLevel===void 0)r.logSeverityLevel=2;else if(typeof e.logSeverityLevel!="number"||!Number.isInteger(e.logSeverityLevel)||e.logSeverityLevel<0||e.logSeverityLevel>4)throw new Error(`log severity level is not valid: ${e.logSeverityLevel}`);if(e?.logVerbosityLevel===void 0)r.logVerbosityLevel=0;else if(typeof e.logVerbosityLevel!="number"||!Number.isInteger(e.logVerbosityLevel))throw new Error(`log verbosity level is not valid: ${e.logVerbosityLevel}`);e?.terminate===void 0&&(r.terminate=!1);let s=0;return e?.tag!==void 0&&(s=It(e.tag,n)),i=t._OrtCreateRunOptions(r.logSeverityLevel,r.logVerbosityLevel,!!r.terminate,s),i===0&&Ve("Can't create run options."),e?.extra!==void 0&&Li(e.extra,"",new WeakSet,(a,o)=>{let l=It(a,n),u=It(o,n);t._OrtAddRunConfigEntry(i,l,u)!==0&&Ve(`Can't set a run config entry: ${a} - ${o}.`)}),[i,n]}catch(s){throw i!==0&&t._OrtReleaseRunOptions(i),n.forEach(a=>t._free(a)),s}}}),cs,ps,fs,vi,hs,ms,_p=k(()=>{Yt(),vn(),cs=e=>{switch(e){case"disabled":return 0;case"basic":return 1;case"extended":return 2;case"layout":return 3;case"all":return 99;default:throw new Error(`unsupported graph optimization level: ${e}`)}},ps=e=>{switch(e){case"sequential":return 0;case"parallel":return 1;default:throw new Error(`unsupported execution mode: ${e}`)}},fs=e=>{e.extra||(e.extra={}),e.extra.session||(e.extra.session={});let t=e.extra.session;t.use_ort_model_bytes_directly||(t.use_ort_model_bytes_directly="1"),e.executionProviders&&e.executionProviders.some(i=>(typeof i=="string"?i:i.name)==="webgpu")&&(e.enableMemPattern=!1)},vi=(e,t,i,n)=>{let r=It(t,n),s=It(i,n);We()._OrtAddSessionConfigEntry(e,r,s)!==0&&Ve(`Can't set a session config entry: ${t} - ${i}.`)},hs=async(e,t,i)=>{for(let n of t){let r=typeof n=="string"?n:n.name,s=[];switch(r){case"webnn":if(r="WEBNN",typeof n!="string"){let d=n?.deviceType;d&&vi(e,"deviceType",d,i)}break;case"webgpu":if(r="JS",typeof n!="string"){let d=n;if(d?.preferredLayout){if(d.preferredLayout!=="NCHW"&&d.preferredLayout!=="NHWC")throw new Error(`preferredLayout must be either 'NCHW' or 'NHWC': ${d.preferredLayout}`);vi(e,"preferredLayout",d.preferredLayout,i)}}break;case"wasm":case"cpu":continue;default:throw new Error(`not supported execution provider: ${r}`)}let a=It(r,i),o=s.length,l=0,u=0;if(o>0){l=We()._malloc(o*We().PTR_SIZE),i.push(l),u=We()._malloc(o*We().PTR_SIZE),i.push(u);for(let d=0;d<o;d++)We().setValue(l+d*We().PTR_SIZE,s[d][0],"*"),We().setValue(u+d*We().PTR_SIZE,s[d][1],"*")}await We()._OrtAppendExecutionProvider(e,a,l,u,o)!==0&&Ve(`Can't append execution provider: ${r}.`)}},ms=async e=>{let t=We(),i=0,n=[],r=e||{};fs(r);try{let s=cs(r.graphOptimizationLevel??"all"),a=ps(r.executionMode??"sequential"),o=typeof r.logId=="string"?It(r.logId,n):0,l=r.logSeverityLevel??2;if(!Number.isInteger(l)||l<0||l>4)throw new Error(`log severity level is not valid: ${l}`);let u=r.logVerbosityLevel??0;if(!Number.isInteger(u)||u<0||u>4)throw new Error(`log verbosity level is not valid: ${u}`);let d=typeof r.optimizedModelFilePath=="string"?It(r.optimizedModelFilePath,n):0;if(i=t._OrtCreateSessionOptions(s,!!r.enableCpuMemArena,!!r.enableMemPattern,a,!!r.enableProfiling,0,o,l,u,d),i===0&&Ve("Can't create session options."),r.executionProviders&&await hs(i,r.executionProviders,n),r.enableGraphCapture!==void 0){if(typeof r.enableGraphCapture!="boolean")throw new Error(`enableGraphCapture must be a boolean value: ${r.enableGraphCapture}`);vi(i,"enableGraphCapture",r.enableGraphCapture.toString(),n)}if(r.freeDimensionOverrides)for(let[c,p]of Object.entries(r.freeDimensionOverrides)){if(typeof c!="string")throw new Error(`free dimension override name must be a string: ${c}`);if(typeof p!="number"||!Number.isInteger(p)||p<0)throw new Error(`free dimension override value must be a non-negative integer: ${p}`);let h=It(c,n);t._OrtAddFreeDimensionOverride(i,h,p)!==0&&Ve(`Can't set a free dimension override: ${c} - ${p}.`)}return r.extra!==void 0&&Li(r.extra,"",new WeakSet,(c,p)=>{vi(i,c,p,n)}),[i,n]}catch(s){throw i!==0&&t._OrtReleaseSessionOptions(i)!==0&&Ve("Can't release session options."),n.forEach(a=>t._free(a)),s}}}),Jt,qt,ei,Ui,qi,$n,xn,Sn,_e=k(()=>{Jt=e=>{switch(e){case"int8":return 3;case"uint8":return 2;case"bool":return 9;case"int16":return 5;case"uint16":return 4;case"int32":return 6;case"uint32":return 12;case"float16":return 10;case"float32":return 1;case"float64":return 11;case"string":return 8;case"int64":return 7;case"uint64":return 13;case"int4":return 22;case"uint4":return 21;default:throw new Error(`unsupported data type: ${e}`)}},qt=e=>{switch(e){case 3:return"int8";case 2:return"uint8";case 9:return"bool";case 5:return"int16";case 4:return"uint16";case 6:return"int32";case 12:return"uint32";case 10:return"float16";case 1:return"float32";case 11:return"float64";case 8:return"string";case 7:return"int64";case 13:return"uint64";case 22:return"int4";case 21:return"uint4";default:throw new Error(`unsupported data type: ${e}`)}},ei=(e,t)=>{let i=[-1,4,1,1,2,2,4,8,-1,1,2,8,4,8,-1,-1,-1,-1,-1,-1,-1,.5,.5][e],n=typeof t=="number"?t:t.reduce((r,s)=>r*s,1);return i>0?Math.ceil(n*i):void 0},Ui=e=>{switch(e){case"float16":return typeof Float16Array<"u"&&Float16Array.from?Float16Array:Uint16Array;case"float32":return Float32Array;case"uint8":return Uint8Array;case"int8":return Int8Array;case"uint16":return Uint16Array;case"int16":return Int16Array;case"int32":return Int32Array;case"bool":return Uint8Array;case"float64":return Float64Array;case"uint32":return Uint32Array;case"int64":return BigInt64Array;case"uint64":return BigUint64Array;default:throw new Error(`unsupported type: ${e}`)}},qi=e=>{switch(e){case"verbose":return 0;case"info":return 1;case"warning":return 2;case"error":return 3;case"fatal":return 4;default:throw new Error(`unsupported logging level: ${e}`)}},$n=e=>e==="float32"||e==="float16"||e==="int32"||e==="int64"||e==="uint32"||e==="uint8"||e==="bool"||e==="uint4"||e==="int4",xn=e=>e==="float32"||e==="float16"||e==="int32"||e==="int64"||e==="uint32"||e==="uint64"||e==="int8"||e==="uint8"||e==="bool"||e==="uint4"||e==="int4",Sn=e=>{switch(e){case"none":return 0;case"cpu":return 1;case"cpu-pinned":return 2;case"texture":return 3;case"gpu-buffer":return 4;case"ml-tensor":return 5;default:throw new Error(`unsupported data location: ${e}`)}}}),kn,gs=k(()=>{ie(),kn=async e=>{if(typeof e=="string"){let t=await fetch(e);if(!t.ok)throw new Error(`failed to load external data file: ${e}`);let i=t.headers.get("Content-Length"),n=i?parseInt(i,10):0;if(n<1073741824)return new Uint8Array(await t.arrayBuffer());{if(!t.body)throw new Error(`failed to load external data file: ${e}, no response body.`);let r=t.body.getReader(),s;try{s=new ArrayBuffer(n)}catch(o){if(o instanceof RangeError){let l=Math.ceil(n/65536);s=new WebAssembly.Memory({initial:l,maximum:l}).buffer}else throw o}let a=0;for(;;){let{done:o,value:l}=await r.read();if(o)break;let u=l.byteLength;new Uint8Array(s,a,u).set(l),a+=u}return new Uint8Array(s,0,n)}}else return e instanceof Blob?new Uint8Array(await e.arrayBuffer()):e instanceof Uint8Array?e:new Uint8Array(e)}}),_s,ys,ws,bs,Tn,vs,Ie,Wt=k(()=>{_e(),_s=["V","I","W","E","F"],ys=(e,t)=>{console.log(`[${_s[e]},${new Date().toISOString()}]${t}`)},Tn=(e,t)=>{ws=e,bs=t},vs=(e,t)=>{let i=qi(e),n=qi(ws);i>=n&&ys(i,typeof t=="function"?t():t)},Ie=(...e)=>{bs&&vs(...e)}}),$s,fi,M,Wi,xs,Ss,ks,$e=k(()=>{$s=class{static calcMatMulShape(e,t){return e[1]!==t[0]?void 0:[e[0],t[1]]}},fi=class{static calcShape(e,t,i=!1){let n=e.length,r=t.length;if(n===0)return t;if(r===0)return e;let s=Math.max(e.length,t.length),a=new Array(s);if(i){if(n<2||r<2)return;let o=$s.calcMatMulShape([e[n-2],e[n-1]],[t[r-2],t[r-1]]);if(o===void 0)return;[a[s-2],a[s-1]]=o}for(let o=i?3:1;o<=s;o++){let l=n-o<0?1:e[n-o],u=r-o<0?1:t[r-o];if(l!==u&&l>1&&u>1)return;let d=Math.max(l,u);if(l&&u)a[s-o]=Math.max(l,u);else{if(d>1)return;a[s-o]=0}}return a}static isValidBroadcast(e,t){let i=e.length,n=t.length;if(i>n)return!1;for(let r=1;r<=i;r++)if(e[i-r]!==1&&e[i-r]!==t[n-r])return!1;return!0}},M=class un{static size(t){return un.getSizeFromDimensionRange(t,0,t.length)}static convertShape(t,i=4){let n=t.length;if(n===0)return[];let r=new Array(n),s=n-1;for(;s>=0;){if(t[s]%i===0){r[s]=t[s]/i;break}if(i%t[s]!==0)throw new Error("cannot convert shape");r[s]=1,i/=t[s],s--}for(s--;s>=0;s--)r[s]=t[s];return r}static sizeFromDimension(t,i){if(i<0||i>t.length)throw new Error(`invalid dimension of ${i} for sizeFromDimension as Tensor has ${t.length} dimensions.`);return un.getSizeFromDimensionRange(t,i,t.length)}static sizeToDimension(t,i){if(i<0||i>t.length)throw new Error(`invalid dimension of ${i} for sizeToDimension as Tensor has ${t.length} dimensions.`);return un.getSizeFromDimensionRange(t,0,i)}static getSizeFromDimensionRange(t,i,n){let r=1;for(let s=i;s<n;s++){if(t[s]<0)throw new Error("cannot get valid size from specified dimension range. Most likely the range contains negative values in them.");r*=Number(t[s])}return r}static computeStrides(t){let i=t.length;if(i===0)return[];if(i===1)return[1];let n=new Array(i);n[i-1]=1,n[i-2]=t[i-1];for(let r=i-3;r>=0;--r)n[r]=n[r+1]*t[r+1];return n}static normalizeAxis(t,i){if(t<-i&&t>=i)throw new Error("unsupported axis for this operation.");return t<0?t+i:t}static normalizeAxes(t,i){return t.map(n=>this.normalizeAxis(n,i??t.length))}static sortBasedOnPerm(t,i){return i?i.map(n=>t[n]):t.slice().reverse()}static padShape(t,i){let n=t.length;return t.map((r,s)=>r+i[s]+i[s+n])}static areEqual(t,i){return t.length!==i.length?!1:t.every((n,r)=>n===i[r])}},Wi=class Di{static adjustPoolAttributes(t,i,n,r,s,a){if(!t&&n.length!==i.length-2)throw new Error("length of specified kernel shapes should be 2 less than length of input dimensions");if(t)for(let o=0;o<i.length-2;o++)o>=n.length?n.push(i[o+2]):n[o]=i[o+2];for(let o=0;o<n.length;o++)if(o<r.length){if(r[o]<0)throw new Error("strides should be greater than or equal to 1")}else r.push(1);for(let o=0;o<n.length;o++)if(o<s.length){if(s[o]<0)throw new Error("dilations should be greater than or equal to 1")}else s.push(1);for(let o=0;o<n.length*2;o++)if(o<a.length){if(a[o]<0)throw new Error("pad should be greater than or equal to 1")}else a.push(0);for(let o=0;o<n.length;o++){if(n[o]<=0)throw new Error("kernel shapes need to be greater than 0");if(a[o]>=n[o]||a[o+n.length]>=n[o])throw new Error("pads should be smaller than kernel")}}static adjustPadsBasedOnAutoPad(t,i,n,r,s,a,o){if(o){if(s.length!==2*(t.length-2))throw new Error("length of pads should be twice the length of data dimensions");if(i.length!==t.length-2)throw new Error("length of strides should be the length of data dimensions");if(r.length!==t.length-2)throw new Error("length of kernel shapes should be the length of data dimensions");for(let l=0;l<t.length-2;l++)Di.adjustPadAndReturnShape(t[l+(a?1:2)],i[l],n[l],r[l],s,l,l+t.length-2,o)}}static computePoolOutputShape(t,i,n,r,s,a,o){if(i.length<=0)throw new Error("input shape must be of size greater than 0");let l=[i[0],i[1]];return Di.computeShapeHelper(t,i,l,n,r,s,a,o),l}static computeConvOutputShape(t,i,n,r,s,a,o){if(t.length<=0||i.length<=0)throw new Error("invalid input tensor dims or invalid filter tensor dims");let l=[t[0],i[0]];return Di.computeShapeHelper(!1,t,l,n,r,s,a,o),l}static computeShapeHelper(t,i,n,r,s,a,o,l){if(t)for(let u=0;u<i.length-2;u++)n.push(1);else for(let u=0;u<i.length-2;u++)n.push(Di.adjustPadAndReturnShape(i[u+2],r[u],s[u],a[u],o,u,u+i.length-2,l))}static adjustPadAndReturnShape(t,i,n,r,s,a,o,l){let u=n*(r-1)+1;if(l&&l!=="NOTSET")switch(l){case"VALID":return s[a]=0,s[o]=0,Math.floor((t-u)/i+1);case"SAME_LOWER":case"SAME_UPPER":if(n!==1)throw new Error("Dilation not supported for SAME_UPPER or SAME_LOWER");{let d=((t+i-1)/i-1)*i+r-t;return s[a]=Math.floor(l==="SAME_LOWER"?(d+1)/2:d/2),s[o]=d-s[a],Math.floor((t+d-r)/i+1)}default:throw new Error("Unsupported AutoPad type")}else return Math.floor((t+s[a]+s[o]-u)/i+1)}},xs=class{static getShapeOfGemmResult(e,t,i,n,r){if(e.length!==2||i.length!==2)throw new Error("shape need to be of size 2");let s,a,o;t?(s=e[1],a=e[0]):(s=e[0],a=e[1]);let l=-1;if(n?(o=i[0],l=1):(o=i[1],l=0),i[l]!==a)throw new Error("dimension mismatch");if(s<=0||o<=0||a<=0)throw new Error("invalid shape specified");if(r&&!fi.isValidBroadcast(r,[s,o]))throw new Error("gemm: invalid bias shape for broadcast");return[s,o,a]}},Ss=-34028234663852886e22,ks=34028234663852886e22}),En,Ts=k(()=>{_e(),En=(e,t)=>new(Ui(t))(e)}),Cn,In,An,Es,zn,Cs,Rn,On,Mn,Is,As,yp=k(()=>{_e(),Wt(),Cn=new Map([["float32",32],["float16",16],["int32",32],["uint32",32],["int64",64],["uint64",64],["int8",8],["uint8",8],["int4",4],["uint4",4]]),In=(e,t)=>{if(t==="int32")return e;let i=Cn.get(t);if(!i)throw new Error(`WebNN backend does not support data type: ${t}`);let n=i/8;if(e.byteLength%n!==0)throw new Error(`Invalid Uint8Array length - must be a multiple of ${n}.`);let r=e.byteLength/n,s=new(Ui(t))(e.buffer,e.byteOffset,r);switch(t){case"int64":case"uint64":{let a=new Int32Array(r);for(let o=0;o<r;o++){let l=s[o];if(l>2147483647n||l<-2147483648n)throw new Error("Can not convert int64 data to int32 - value out of range.");a[o]=Number(l)}return new Uint8Array(a.buffer)}case"int8":case"uint8":case"uint32":{if(t==="uint32"&&s.some(o=>o>2147483647))throw new Error("Can not convert uint32 data to int32 - value out of range.");let a=Int32Array.from(s,Number);return new Uint8Array(a.buffer)}default:throw new Error(`Unsupported data conversion from ${t} to 'int32'`)}},An=(e,t)=>{if(t==="int32")return e;if(e.byteLength%4!==0)throw new Error("Invalid Uint8Array length - must be a multiple of 4 (int32).");let i=e.byteLength/4,n=new Int32Array(e.buffer,e.byteOffset,i);switch(t){case"int64":{let r=BigInt64Array.from(n,BigInt);return new Uint8Array(r.buffer)}case"uint64":{if(n.some(s=>s<0))throw new Error("Can not convert int32 data to uin64 - negative value found.");let r=BigUint64Array.from(n,BigInt);return new Uint8Array(r.buffer)}case"int8":{if(n.some(s=>s<-128||s>127))throw new Error("Can not convert int32 data to int8 - value out of range.");let r=Int8Array.from(n,Number);return new Uint8Array(r.buffer)}case"uint8":{if(n.some(r=>r<0||r>255))throw new Error("Can not convert int32 data to uint8 - value out of range.");return Uint8Array.from(n,Number)}case"uint32":{if(n.some(s=>s<0))throw new Error("Can not convert int32 data to uint32 - negative value found.");let r=Uint32Array.from(n,Number);return new Uint8Array(r.buffer)}default:throw new Error(`Unsupported data conversion from 'int32' to ${t}`)}},Es=1,zn=()=>Es++,Cs=new Map([["int8","int32"],["uint8","int32"],["uint32","int32"],["int64","int32"]]),Rn=(e,t)=>{let i=Cn.get(e);if(!i)throw new Error(`WebNN backend does not support data type: ${e}`);return t.length>0?Math.ceil(t.reduce((n,r)=>n*r)*i/8):0},On=class{constructor(e){this.isDataConverted=!1;let{sessionId:t,context:i,tensor:n,dataType:r,shape:s,fallbackDataType:a}=e;this.sessionId=t,this.mlContext=i,this.mlTensor=n,this.dataType=r,this.tensorShape=s,this.fallbackDataType=a}get tensor(){return this.mlTensor}get type(){return this.dataType}get fallbackType(){return this.fallbackDataType}get shape(){return this.tensorShape}get byteLength(){return Rn(this.dataType,this.tensorShape)}destroy(){Ie("verbose",()=>"[WebNN] TensorWrapper.destroy"),this.mlTensor.destroy()}write(e){this.mlContext.writeTensor(this.mlTensor,e)}async read(e){if(this.fallbackDataType){let t=await this.mlContext.readTensor(this.mlTensor),i=An(new Uint8Array(t),this.dataType);if(e){(e instanceof ArrayBuffer?new Uint8Array(e):new Uint8Array(e.buffer,e.byteOffset,e.byteLength)).set(i);return}else return i.buffer}else return e?this.mlContext.readTensor(this.mlTensor,e):this.mlContext.readTensor(this.mlTensor)}canReuseTensor(e,t,i){return this.mlContext===e&&this.dataType===t&&this.tensorShape.length===i.length&&this.tensorShape.every((n,r)=>n===i[r])}setIsDataConverted(e){this.isDataConverted=e}},Mn=class{constructor(e,t){this.tensorManager=e,this.wrapper=t}get tensorWrapper(){return this.wrapper}releaseTensor(){this.tensorWrapper&&(this.tensorManager.releaseTensor(this.tensorWrapper),this.wrapper=void 0)}async ensureTensor(e,t,i,n){let r=this.tensorManager.getMLContext(e),s;if(!r.opSupportLimits().input.dataTypes.includes(t)){if(s=Cs.get(t),!s||!r.opSupportLimits().input.dataTypes.includes(s))throw new Error(`WebNN backend does not support data type: ${t}`);Ie("verbose",()=>`[WebNN] TensorIdTracker.ensureTensor: fallback dataType from ${t} to ${s}`)}if(this.wrapper){if(this.wrapper.canReuseTensor(r,t,i))return this.wrapper.tensor;if(n){if(this.wrapper.byteLength!==Rn(t,i))throw new Error("Unable to copy data to tensor with different size.");this.activeUpload=new Uint8Array(await this.wrapper.read())}this.tensorManager.releaseTensor(this.wrapper)}let a=typeof MLTensorUsage>"u"?void 0:MLTensorUsage.READ|MLTensorUsage.WRITE;return this.wrapper=await this.tensorManager.getCachedTensor(e,t,i,a,!0,!0,s),n&&this.activeUpload&&(this.wrapper.write(this.activeUpload),this.activeUpload=void 0),this.wrapper.tensor}upload(e){let t=e;if(this.wrapper){if(this.wrapper.fallbackType)if(this.wrapper.fallbackType==="int32")t=In(e,this.wrapper.type),this.wrapper.setIsDataConverted(!0);else throw new Error(`Unsupported fallback data type: ${this.wrapper.fallbackType}`);if(e.byteLength===this.wrapper.byteLength){this.wrapper.write(t);return}else Ie("verbose",()=>"Data size does not match tensor size. Releasing tensor."),this.releaseTensor()}this.activeUpload?this.activeUpload.set(t):this.activeUpload=new Uint8Array(t)}async download(e){if(this.activeUpload){let t=this.wrapper?.isDataConverted?An(this.activeUpload,this.wrapper?.type):this.activeUpload;if(e){e instanceof ArrayBuffer?new Uint8Array(e).set(t):new Uint8Array(e.buffer,e.byteOffset,e.byteLength).set(t);return}else return t.buffer}if(!this.wrapper)throw new Error("Tensor has not been created.");return e?this.wrapper.read(e):this.wrapper.read()}},Is=class{constructor(e){this.backend=e,this.tensorTrackersById=new Map,this.freeTensors=[],this.externalTensors=new Set}getMLContext(e){let t=this.backend.getMLContext(e);if(!t)throw new Error("MLContext not found for session.");return t}reserveTensorId(){let e=zn();return this.tensorTrackersById.set(e,new Mn(this)),e}releaseTensorId(e){let t=this.tensorTrackersById.get(e);t&&(this.tensorTrackersById.delete(e),t.tensorWrapper&&this.releaseTensor(t.tensorWrapper))}async ensureTensor(e,t,i,n,r){Ie("verbose",()=>`[WebNN] TensorManager.ensureTensor {tensorId: ${t}, dataType: ${i}, shape: ${n}, copyOld: ${r}}`);let s=this.tensorTrackersById.get(t);if(!s)throw new Error("Tensor not found.");return s.ensureTensor(e,i,n,r)}upload(e,t){let i=this.tensorTrackersById.get(e);if(!i)throw new Error("Tensor not found.");i.upload(t)}async download(e,t){Ie("verbose",()=>`[WebNN] TensorManager.download {tensorId: ${e}, dstBuffer: ${t?.byteLength}}`);let i=this.tensorTrackersById.get(e);if(!i)throw new Error("Tensor not found.");return i.download(t)}releaseTensorsForSession(e){for(let t of this.freeTensors)t.sessionId===e&&t.destroy();this.freeTensors=this.freeTensors.filter(t=>t.sessionId!==e)}registerTensor(e,t,i,n){let r=this.getMLContext(e),s=zn(),a=new On({sessionId:e,context:r,tensor:t,dataType:i,shape:n});return this.tensorTrackersById.set(s,new Mn(this,a)),this.externalTensors.add(a),s}async getCachedTensor(e,t,i,n,r,s,a){let o=this.getMLContext(e);for(let[u,d]of this.freeTensors.entries())if(d.canReuseTensor(o,t,i)){Ie("verbose",()=>`[WebNN] Reusing tensor {dataType: ${t}, ${a?`fallbackDataType: ${a},`:""} shape: ${i}`);let c=this.freeTensors.splice(u,1)[0];return c.sessionId=e,c}Ie("verbose",()=>`[WebNN] MLContext.createTensor {dataType: ${t}, ${a?`fallbackDataType: ${a},`:""} shape: ${i}}`);let l=await o.createTensor({dataType:a??t,shape:i,dimensions:i,usage:n,writable:r,readable:s});return new On({sessionId:e,context:o,tensor:l,dataType:t,shape:i,fallbackDataType:a})}releaseTensor(e){this.externalTensors.has(e)&&this.externalTensors.delete(e),this.freeTensors.push(e)}},As=(...e)=>new Is(...e)}),$i,zs,Rs,wp=k(()=>{_e(),Yt(),Ts(),yp(),Wt(),$i=new Map([[1,"float32"],[10,"float16"],[6,"int32"],[12,"uint32"],[7,"int64"],[13,"uint64"],[22,"int4"],[21,"uint4"],[3,"int8"],[2,"uint8"],[9,"uint8"]]),zs=(e,t)=>{if(e===t)return!0;if(e===void 0||t===void 0)return!1;let i=Object.keys(e).sort(),n=Object.keys(t).sort();return i.length===n.length&&i.every((r,s)=>r===n[s]&&e[r]===t[r])},Rs=class{constructor(e){this.tensorManager=As(this),this.mlContextBySessionId=new Map,this.sessionIdsByMLContext=new Map,this.mlContextCache=[],this.sessionGraphInputs=new Map,this.sessionGraphOutputs=new Map,this.temporaryGraphInputs=[],this.temporaryGraphOutputs=[],this.temporarySessionTensorIds=new Map,Tn(e.logLevel,!!e.debug)}get currentSessionId(){if(this.activeSessionId===void 0)throw new Error("No active session");return this.activeSessionId}onRunStart(e){Ie("verbose",()=>`[WebNN] onRunStart {sessionId: ${e}}`),this.activeSessionId=e}onRunEnd(e){Ie("verbose",()=>`[WebNN] onRunEnd {sessionId: ${e}}`);let t=this.temporarySessionTensorIds.get(e);if(t){for(let i of t)Ie("verbose",()=>`[WebNN] releasing temporary tensor {tensorId: ${i}}`),this.tensorManager.releaseTensorId(i);this.temporarySessionTensorIds.delete(e),this.activeSessionId=void 0}}async createMLContext(e){if(e instanceof GPUDevice){let i=this.mlContextCache.findIndex(n=>n.gpuDevice===e);if(i!==-1)return this.mlContextCache[i].mlContext;{let n=await navigator.ml.createContext(e);return this.mlContextCache.push({gpuDevice:e,mlContext:n}),n}}else if(e===void 0){let i=this.mlContextCache.findIndex(n=>n.options===void 0&&n.gpuDevice===void 0);if(i!==-1)return this.mlContextCache[i].mlContext;{let n=await navigator.ml.createContext();return this.mlContextCache.push({mlContext:n}),n}}let t=this.mlContextCache.findIndex(i=>zs(i.options,e));if(t!==-1)return this.mlContextCache[t].mlContext;{let i=await navigator.ml.createContext(e);return this.mlContextCache.push({options:e,mlContext:i}),i}}registerMLContext(e,t){this.mlContextBySessionId.set(e,t);let i=this.sessionIdsByMLContext.get(t);i||(i=new Set,this.sessionIdsByMLContext.set(t,i)),i.add(e),this.temporaryGraphInputs.length>0&&(this.sessionGraphInputs.set(e,this.temporaryGraphInputs),this.temporaryGraphInputs=[]),this.temporaryGraphOutputs.length>0&&(this.sessionGraphOutputs.set(e,this.temporaryGraphOutputs),this.temporaryGraphOutputs=[])}onReleaseSession(e){this.sessionGraphInputs.delete(e),this.sessionGraphOutputs.delete(e);let t=this.mlContextBySessionId.get(e);if(!t)return;this.tensorManager.releaseTensorsForSession(e),this.mlContextBySessionId.delete(e);let i=this.sessionIdsByMLContext.get(t);if(i.delete(e),i.size===0){this.sessionIdsByMLContext.delete(t);let n=this.mlContextCache.findIndex(r=>r.mlContext===t);n!==-1&&this.mlContextCache.splice(n,1)}}getMLContext(e){return this.mlContextBySessionId.get(e)}reserveTensorId(){return this.tensorManager.reserveTensorId()}releaseTensorId(e){Ie("verbose",()=>`[WebNN] releaseTensorId {tensorId: ${e}}`),this.tensorManager.releaseTensorId(e)}async ensureTensor(e,t,i,n,r){let s=$i.get(i);if(!s)throw new Error(`Unsupported ONNX data type: ${i}`);return this.tensorManager.ensureTensor(e??this.currentSessionId,t,s,n,r)}async createTemporaryTensor(e,t,i){Ie("verbose",()=>`[WebNN] createTemporaryTensor {onnxDataType: ${t}, shape: ${i}}`);let n=$i.get(t);if(!n)throw new Error(`Unsupported ONNX data type: ${t}`);let r=this.tensorManager.reserveTensorId();await this.tensorManager.ensureTensor(e,r,n,i,!1);let s=this.temporarySessionTensorIds.get(e);return s?s.push(r):this.temporarySessionTensorIds.set(e,[r]),r}uploadTensor(e,t){if(!We().shouldTransferToMLTensor)throw new Error("Trying to upload to a MLTensor while shouldTransferToMLTensor is false");Ie("verbose",()=>`[WebNN] uploadTensor {tensorId: ${e}, data: ${t.byteLength}}`),this.tensorManager.upload(e,t)}async downloadTensor(e,t){return this.tensorManager.download(e,t)}createMLTensorDownloader(e,t){return async()=>{let i=await this.tensorManager.download(e);return En(i,t)}}registerMLTensor(e,t,i,n){let r=$i.get(i);if(!r)throw new Error(`Unsupported ONNX data type: ${i}`);let s=this.tensorManager.registerTensor(e,t,r,n);return Ie("verbose",()=>`[WebNN] registerMLTensor {tensor: ${t}, dataType: ${r}, dimensions: ${n}} -> {tensorId: ${s}}`),s}registerMLConstant(e,t,i,n,r,s,a=!1){if(!s)throw new Error("External mounted files are not available.");let o=e;e.startsWith("./")&&(o=e.substring(2));let l=s.get(o);if(!l)throw new Error(`File with name ${o} not found in preloaded files.`);if(t+i>l.byteLength)throw new Error("Out of bounds: data offset and length exceed the external file data size.");let u=l.slice(t,t+i).buffer,d;switch(r.dataType){case"float32":d=new Float32Array(u);break;case"float16":d=typeof Float16Array<"u"&&Float16Array.from?new Float16Array(u):new Uint16Array(u);break;case"int32":d=new Int32Array(u);break;case"uint32":d=new Uint32Array(u);break;case"int64":if(a){let c=In(new Uint8Array(u),"int64");d=new Int32Array(c.buffer),r.dataType="int32"}else d=new BigInt64Array(u);break;case"uint64":d=new BigUint64Array(u);break;case"int8":d=new Int8Array(u);break;case"int4":case"uint4":case"uint8":d=new Uint8Array(u);break;default:throw new Error(`Unsupported data type: ${r.dataType} in creating WebNN Constant from external data.`)}return Ie("verbose",()=>`[WebNN] registerMLConstant {dataType: ${r.dataType}, shape: ${r.shape}}} ${a?"(Note: it was int64 data type and registered to int32 as workaround)":""}`),n.constant(r,d)}registerGraphInput(e){this.temporaryGraphInputs.push(e)}registerGraphOutput(e){this.temporaryGraphOutputs.push(e)}isGraphInput(e,t){let i=this.sessionGraphInputs.get(e);return i?i.includes(t):!1}isGraphOutput(e,t){let i=this.sessionGraphOutputs.get(e);return i?i.includes(t):!1}isGraphInputOutputTypeSupported(e,t,i=!0){let n=this.mlContextBySessionId.get(e),r=$i.get(Jt(t));return typeof r>"u"?!1:i?!!n?.opSupportLimits().input.dataTypes.includes(r):!!n?.opSupportLimits().output.dataTypes.includes(r)}flush(){}}}),Fn=k(()=>{}),Dn,Gi,ji,Os,Ms,Bn,Pn,Fs,Ds,bp=k(()=>{Wt(),Fn(),Dn=new Map([[64,250],[128,200],[256,200],[512,200],[2048,230],[4096,200],[8192,50],[16384,50],[32768,50],[65536,50],[131072,50],[262144,50],[524288,50],[1048576,50],[2097152,30],[4194304,20],[8388608,10],[12582912,10],[16777216,10],[26214400,15],[33554432,22],[44236800,2],[58982400,6],[67108864,6],[134217728,6],[167772160,6]]),Gi=[],ji=e=>Math.ceil(Number(e)/16)*16,Os=e=>{for(let t=0;t<Gi.length;t++){let i=Gi[t];if(e<=i)return i}return Math.ceil(e/16)*16},Ms=1,Bn=()=>Ms++,Pn=async(e,t,i,n)=>{let r=ji(i),s=e.device.createBuffer({size:r,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});try{let a=e.getCommandEncoder();e.endComputePass(),a.copyBufferToBuffer(t,0,s,0,r),e.flush(),await s.mapAsync(GPUMapMode.READ);let o=s.getMappedRange();if(n){let l=n();return l.set(new Uint8Array(o,0,i)),l}else return new Uint8Array(o.slice(0,i))}finally{s.destroy()}},Fs=class{constructor(e){this.backend=e,this.storageCache=new Map,this.freeBuffers=new Map,this.freeUniformBuffers=new Map,this.buffersPending=[],this.capturedPendingBuffers=new Map;for(let[t]of Dn)Gi.push(t),this.freeBuffers.set(t,[]),this.freeUniformBuffers.set(t,[]);this.sessionCount=0}upload(e,t){let i=t.buffer,n=t.byteOffset,r=t.byteLength,s=ji(r),a=this.storageCache.get(e);if(!a)throw new Error("gpu data for uploading does not exist");if(Number(a.originalSize)!==r)throw new Error(`inconsistent data size. gpu data size=${a.originalSize}, data size=${r}`);let o=this.backend.device.createBuffer({mappedAtCreation:!0,size:s,usage:GPUBufferUsage.MAP_WRITE|GPUBufferUsage.COPY_SRC}),l=o.getMappedRange();new Uint8Array(l).set(new Uint8Array(i,n,r)),o.unmap();let u=this.backend.device.createCommandEncoder();u.copyBufferToBuffer(o,0,a.gpuData.buffer,0,s),this.backend.device.queue.submit([u.finish()]),o.destroy(),Ie("verbose",()=>`[WebGPU] GpuDataManager.upload(id=${e})`)}memcpy(e,t){let i=this.storageCache.get(e);if(!i)throw new Error("source gpu data for memcpy does not exist");let n=this.storageCache.get(t);if(!n)throw new Error("destination gpu data for memcpy does not exist");if(i.originalSize!==n.originalSize)throw new Error("inconsistent source and destination gpu data size");let r=ji(i.originalSize),s=this.backend.getCommandEncoder();this.backend.endComputePass(),s.copyBufferToBuffer(i.gpuData.buffer,0,n.gpuData.buffer,0,r)}registerExternalBuffer(e,t,i){let n;if(i){if(n=i[0],e===i[1])return Ie("verbose",()=>`[WebGPU] GpuDataManager.registerExternalBuffer(size=${t}) => id=${n}, buffer is the same, skip.`),n;if(this.backend.capturedCommandList.has(this.backend.currentSessionId))throw new Error(`Registering a different external buffer under graph capture mode is not supported yet.
             Please use the previous external buffer!`)}else n=Bn();return this.storageCache.set(n,{gpuData:{id:n,type:0,buffer:e},originalSize:t}),Ie("verbose",()=>`[WebGPU] GpuDataManager.registerExternalBuffer(size=${t}) => id=${n}, registered.`),n}unregisterExternalBuffer(e){e!==void 0&&(this.storageCache.delete(e),Ie("verbose",()=>`[WebGPU] GpuDataManager.unregisterExternalBuffer() => id=${e}`))}create(e,t=GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_SRC|GPUBufferUsage.COPY_DST){let i=Os(e),n,r=(t&GPUBufferUsage.STORAGE)===GPUBufferUsage.STORAGE,s=(t&GPUBufferUsage.UNIFORM)===GPUBufferUsage.UNIFORM;if(r||s){let o=(r?this.freeBuffers:this.freeUniformBuffers).get(i);o?o.length>0?n=o.pop():n=this.backend.device.createBuffer({size:i,usage:t}):n=this.backend.device.createBuffer({size:i,usage:t})}else n=this.backend.device.createBuffer({size:i,usage:t});let a={id:Bn(),type:0,buffer:n};return this.storageCache.set(a.id,{gpuData:a,originalSize:Number(e)}),Ie("verbose",()=>`[WebGPU] GpuDataManager.create(size=${e}) => id=${a.id}`),a}get(e){return this.storageCache.get(e)?.gpuData}release(e){let t=typeof e=="bigint"?Number(e):e,i=this.storageCache.get(t);if(!i){if(this.storageCache.size===0)return 0;throw new Error("releasing data does not exist")}return Ie("verbose",()=>`[WebGPU] GpuDataManager.release(id=${t}), gpuDataId=${i.gpuData.id}`),this.storageCache.delete(t),this.buffersPending.push(i.gpuData.buffer),i.originalSize}async download(e,t){let i=this.storageCache.get(Number(e));if(!i)throw new Error("data does not exist");await Pn(this.backend,i.gpuData.buffer,i.originalSize,t)}refreshPendingBuffers(){if(this.buffersPending.length!==0)if(this.backend.sessionStatus==="default"){for(let e of this.buffersPending){let t=Dn.get(e.size);if((e.usage&GPUBufferUsage.STORAGE)===GPUBufferUsage.STORAGE){let i=this.freeBuffers.get(e.size)||[];t===void 0||i.length>=t?e.destroy():i.push(e)}else if((e.usage&GPUBufferUsage.UNIFORM)===GPUBufferUsage.UNIFORM){let i=this.freeUniformBuffers.get(e.size)||[];t===void 0||i.length>=t?e.destroy():i.push(e)}else e.destroy()}this.buffersPending=[]}else{let e=this.capturedPendingBuffers.get(this.backend.currentSessionId);e||(e=[],this.capturedPendingBuffers.set(this.backend.currentSessionId,e));for(let t of this.buffersPending)e.push(t);this.buffersPending=[]}}dispose(){this.freeBuffers.forEach(e=>{e.forEach(t=>{t.destroy()})}),this.freeUniformBuffers.forEach(e=>{e.forEach(t=>{t.destroy()})}),this.storageCache.forEach(e=>{e.gpuData.buffer.destroy()}),this.capturedPendingBuffers.forEach(e=>{e.forEach(t=>{t.destroy()})}),this.storageCache=new Map,this.freeBuffers=new Map,this.freeUniformBuffers=new Map,this.capturedPendingBuffers=new Map}onCreateSession(){this.sessionCount+=1}onReleaseSession(e){let t=this.capturedPendingBuffers.get(e);t&&(t.forEach(i=>{i.destroy()}),this.capturedPendingBuffers.delete(e)),this.sessionCount-=1,this.sessionCount===0&&(Ie("warning",()=>"[WebGPU] Clearing webgpu buffer cache"),this.storageCache.forEach(i=>{i.gpuData.buffer.destroy()}),this.storageCache=new Map)}},Ds=(...e)=>new Fs(...e)}),Bs,De,Xe=k(()=>{Bs=class{constructor(e){Object.assign(this,e)}get cacheKey(){return this.key||(this.key=Object.getOwnPropertyNames(this).sort().map(e=>`${this[e]}`).join(";")),this.key}},De=e=>new Bs(e)}),hi,Hi,at,_t,le,Qe,Nn,mi,Ht,se,xi,B,re,Ps,Vn,Ns,Vs,xe=k(()=>{_e(),$e(),hi=64,Hi=(e,t)=>{if(t===3)throw new Error("vec3 has same alignment as vec4, use vec4 instead");switch(Number(e)){case 10:return t>1?`vec${t}<f16>`:"f16";case 1:return t>1?`vec${t}<f32>`:"f32";case 6:return t>1?`vec${t}<i32>`:"i32";case 12:return t>1?`vec${t}<u32>`:"u32";case 7:if(t>1)throw new Error("currently not supported vecX of uint64 yet");return["vec2<u32>","i32"];case 13:if(t>1)throw new Error("currently not supported vecX of uint64 yet");return["vec2<u32>","u32"];case 9:if(t!==4)throw new Error("bool must be vec4");return["u32","vec4<bool>"];case 22:return"i32";case 21:return"u32";default:throw new Error(`Unknown data type: ${e}`)}},at=(e,t=1)=>{let i=Hi(e,t);return typeof i=="string"?i:i[0]},_t=(e,t=1)=>{let i=Hi(e,t);return typeof i=="string"?i:i[1]},le=(...e)=>{let t=[];return e.forEach(i=>{i.length!==0&&t.push({type:12,data:i},{type:12,data:M.computeStrides(i)})}),t},Qe=e=>e%4===0?4:e%2===0?2:1,Nn=(e="f32",t,i="0")=>!t||t===1?`${e}(${i})`:`vec${t}<${e}>(${i})`,mi=(e,t,i)=>e==="f32"?i:t===1?`f32(${i})`:`vec${t}<f32>(${i})`,Ht=(e,t)=>t===4?`(${e}.x + ${e}.y + ${e}.z + ${e}.w)`:t===2?`(${e}.x + ${e}.y)`:t===3?`(${e}.x + ${e}.y + ${e}.z)`:e,se=(e,t,i,n)=>e.startsWith("uniforms.")&&i>4?typeof t=="string"?n==="f16"?`${e}[(${t}) / 8][(${t}) % 8 / 4][(${t}) % 8 % 4]`:`${e}[(${t}) / 4][(${t}) % 4]`:n==="f16"?`${e}[${Math.floor(t/8)}][${Math.floor(t%8/4)}][${t%8%4}]`:`${e}[${Math.floor(t/4)}][${t%4}]`:i>1?`${e}[${t}]`:e,xi=(e,t,i,n,r)=>{let s=typeof i=="number",a=s?i:i.length,o=[...new Array(a).keys()],l=a<2?"u32":a<=4?`vec${a}<u32>`:`array<u32, ${a}>`,u=Hi(t,r),d=typeof u=="string"?u:u[1],c=typeof u=="string"?u:u[0],p={indices:l,value:d,storage:c,tensor:t},h=W=>typeof W=="string"?W:`${W}u`,m={offsetToIndices:!1,indicesToOffset:!1,broadcastedIndicesToOffset:!1,set:!1,setByIndices:!1,get:!1,getByIndices:!1},_=s?"uniforms.":"",$=`${_}${e}_shape`,w=`${_}${e}_strides`,g="";for(let W=0;W<a-1;W++)g+=`
    let dim${W} = current / ${se(w,W,a)};
    let rest${W} = current % ${se(w,W,a)};
    indices[${W}] = dim${W};
    current = rest${W};
    `;g+=`indices[${a-1}] = current;`;let T=a<2?"":`
  fn o2i_${e}(offset: u32) -> ${p.indices} {
    var indices: ${p.indices};
    var current = offset;
    ${g}
    return indices;
  }`,x=W=>(m.offsetToIndices=!0,a<2?W:`o2i_${e}(${W})`),I=[];if(a>=2)for(let W=a-1;W>=0;W--)I.push(`${se(w,W,a)} * (indices[${W}])`);let O=a<2?"":`
  fn i2o_${e}(indices: ${p.indices}) -> u32 {
    return ${I.join("+")};
  }`,z=W=>(m.indicesToOffset=!0,a<2?W:`i2o_${e}(${W})`),N=(...W)=>a===0?"0u":`${p.indices}(${W.map(h).join(",")})`,q=(W,ee)=>a<2?`${W}`:`${se(W,ee,a)}`,te=(W,ee,Se)=>a<2?`${W}=${Se};`:`${se(W,ee,a)}=${Se};`,ye={},de=(W,ee)=>{m.broadcastedIndicesToOffset=!0;let Se=`${ee.name}broadcastedIndicesTo${e}Offset`;if(Se in ye)return`${Se}(${W})`;let Le=[];for(let ct=a-1;ct>=0;ct--){let Nt=ee.indicesGet("outputIndices",ct+ee.rank-a);Le.push(`${q(w,ct)} * (${Nt} % ${q($,ct)})`)}return ye[Se]=`fn ${Se}(outputIndices: ${ee.type.indices}) -> u32 {
             return ${Le.length>0?Le.join("+"):"0u"};
           }`,`${Se}(${W})`},be=(W,ee)=>(()=>{if(p.storage===p.value)return`${e}[${W}]=${ee};`;if(p.storage==="vec2<u32>"&&p.value==="i32")return`${e}[${W}]=vec2<u32>(u32(${ee}), select(0u, 0xFFFFFFFFu, ${ee} < 0));`;if(p.storage==="vec2<u32>"&&p.value==="u32")return`${e}[${W}]=vec2<u32>(u32(${ee}), 0u);`;if(p.storage==="u32"&&p.value==="vec4<bool>")return`${e}[${W}]=dot(vec4<u32>(0x1, 0x100, 0x10000, 0x1000000), vec4<u32>(${ee}));`;throw new Error(`not supported combination of storage type ${p.storage} and value type ${p.value} yet`)})(),ne=W=>(()=>{if(p.storage===p.value)return`${e}[${W}]`;if(p.storage==="vec2<u32>"&&p.value==="i32")return`i32(${e}[${W}].x)`;if(p.storage==="vec2<u32>"&&p.value==="u32")return`u32(${e}[${W}].x)`;if(p.storage==="u32"&&p.value==="vec4<bool>")return`vec4<bool>(bool(${e}[${W}] & 0xFFu), bool(${e}[${W}] & 0xFF00u), bool(${e}[${W}] & 0xFF0000u), bool(${e}[${W}] & 0xFF000000u))`;throw new Error(`not supported combination of storage type ${p.storage} and value type ${p.value} yet`)})(),Te=a<2?"":`
  fn get_${e}ByIndices(indices: ${p.indices}) -> ${d} {
    return ${ne(`i2o_${e}(indices)`)};
  }`,he=a<2?"":(()=>{let W=o.map(Se=>`d${Se}: u32`).join(", "),ee=o.map(Se=>`d${Se}`).join(", ");return`
  fn get_${e}(${W}) -> ${d} {
    return get_${e}ByIndices(${N(ee)});
  }`})(),ae=(...W)=>{if(W.length!==a)throw new Error(`indices length must be ${a}`);let ee=W.map(h).join(",");return a===0?ne("0u"):a===1?ne(ee[0]):(m.get=!0,m.getByIndices=!0,m.indicesToOffset=!0,`get_${e}(${ee})`)},Oe=W=>a<2?ne(W):(m.getByIndices=!0,m.indicesToOffset=!0,`get_${e}ByIndices(${W})`),ce=a<2?"":`
  fn set_${e}ByIndices(indices: ${p.indices}, value: ${d}) {
    ${be(`i2o_${e}(indices)`,"value")}
  }`,Ge=a<2?"":(()=>{let W=o.map(Se=>`d${Se}: u32`).join(", "),ee=o.map(Se=>`d${Se}`).join(", ");return`
  fn set_${e}(${W}, value: ${d}) {
    set_${e}ByIndices(${N(ee)}, value);
  }`})();return{impl:()=>{let W=[],ee=!1;return m.offsetToIndices&&(W.push(T),ee=!0),m.indicesToOffset&&(W.push(O),ee=!0),m.broadcastedIndicesToOffset&&(Object.values(ye).forEach(Se=>W.push(Se)),ee=!0),m.set&&(W.push(Ge),ee=!0),m.setByIndices&&(W.push(ce),ee=!0),m.get&&(W.push(he),ee=!0),m.getByIndices&&(W.push(Te),ee=!0),!s&&ee&&W.unshift(`const ${$} = ${p.indices}(${i.join(",")});`,`const ${w} = ${p.indices}(${M.computeStrides(i).join(",")});`),W.join(`
`)},type:p,offsetToIndices:x,indicesToOffset:z,broadcastedIndicesToOffset:de,indices:N,indicesGet:q,indicesSet:te,set:(...W)=>{if(W.length!==a+1)throw new Error(`indices length must be ${a}`);let ee=W[a];if(typeof ee!="string")throw new Error("value must be string");let Se=W.slice(0,a).map(h).join(",");return a===0?be("0u",ee):a===1?be(Se[0],ee):(m.set=!0,m.setByIndices=!0,m.indicesToOffset=!0,`set_${e}(${Se}, ${ee})`)},setByOffset:be,setByIndices:(W,ee)=>a<2?be(W,ee):(m.setByIndices=!0,m.indicesToOffset=!0,`set_${e}ByIndices(${W}, ${ee});`),get:ae,getByOffset:ne,getByIndices:Oe,usage:n,name:e,strides:w,shape:$,rank:a}},B=(e,t,i,n=1)=>xi(e,t,i,"input",n),re=(e,t,i,n=1)=>xi(e,t,i,"output",n),Ps=(e,t,i)=>xi(e,t,i,"atomicOutput",1),Vn=(e,t,i,n=1)=>xi(e,t,i,"internal",n),Ns=class{constructor(e,t){this.normalizedDispatchGroup=e,this.limits=t,this.internalVariables=[],this.variables=[],this.uniforms=[],this.variableIndex=0}guardAgainstOutOfBoundsWorkgroupSizes(e){return`if (global_idx >= ${typeof e=="number"?`${e}u`:e}) { return; }`}mainStart(e=hi){let t=typeof e=="number"?e:e[0],i=typeof e=="number"?1:e[1],n=typeof e=="number"?1:e[2];if(t>this.limits.maxComputeWorkgroupSizeX||i>this.limits.maxComputeWorkgroupSizeY||n>this.limits.maxComputeWorkgroupSizeZ)throw new Error(`workgroup size [${t}, ${i}, ${n}] exceeds the maximum workgroup size [${this.limits.maxComputeWorkgroupSizeX}, ${this.limits.maxComputeWorkgroupSizeY}, ${this.limits.maxComputeWorkgroupSizeZ}].`);if(t*i*n>this.limits.maxComputeInvocationsPerWorkgroup)throw new Error(`workgroup size [${t}, ${i}, ${n}] exceeds the maximum workgroup invocations ${this.limits.maxComputeInvocationsPerWorkgroup}.`);let r=this.normalizedDispatchGroup[1]===1&&this.normalizedDispatchGroup[2]===1,s=r?`@builtin(global_invocation_id) global_id : vec3<u32>,
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
`)}get variablesInfo(){if(this.uniforms.length===0)return;let e=t=>[12,10,1,6][["u32","f16","f32","i32"].indexOf(t)];return this.uniforms.map(t=>[e(t.type),t.length??1])}},Vs=(e,t)=>new Ns(e,t)}),Ls,Ln,Us,qs,Ws,Gs,xt,js,Hs,Kt=k(()=>{_e(),$e(),Xe(),xe(),Ls=(e,t)=>{if(!e||e.length!==1)throw new Error("Transpose requires 1 input.");if(t.length!==0&&t.length!==e[0].dims.length)throw new Error(`perm size ${t.length} does not match input rank ${e[0].dims.length}`)},Ln=(e,t)=>t.length!==0?t:[...new Array(e).keys()].reverse(),Us=(e,t)=>M.sortBasedOnPerm(e,Ln(e.length,t)),qs=(e,t,i,n)=>{let r=`fn perm(i: ${n.type.indices}) -> ${i.type.indices} {
    var a: ${i.type.indices};`;for(let s=0;s<t;++s)r+=`a[${e[s]}]=i[${s}];`;return r+="return a;}"},Ws=(e,t)=>{let i=[],n=[];for(let r=0;r<e.length;++r)e[r]!==1&&i.push(e[r]),e[t[r]]!==1&&n.push(t[r]);return{newShape:i,newPerm:n}},Gs=(e,t)=>{let i=0;for(let n=0;n<e.length;++n)if(t[e[n]]!==1){if(e[n]<i)return!1;i=e[n]}return!0},xt=(e,t)=>{let i=e.dataType,n=e.dims.length,r=Ln(n,t),s=Us(e.dims,r),a=e.dims,o=s,l=n<2||Gs(r,e.dims),u;if(l)return u=m=>{let _=B("input",i,a,4),$=re("output",i,o,4);return`
  ${m.registerUniform("output_size","u32").declareVariables(_,$)}
  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    output[global_idx] = input[global_idx];
  }`},{name:"TransposeCopy",shaderCache:{inputDependencies:["type"]},getRunData:()=>{let m=M.size(s);return{outputs:[{dims:s,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(m/64/4)},programUniforms:[{type:12,data:Math.ceil(m/4)}]}},getShaderSource:u};let{newShape:d,newPerm:c}=Ws(e.dims,r),p=M.areEqual(c,[2,3,1]),h=M.areEqual(c,[3,1,2]);if(d.length===2||p||h){a=p?[d[0],d[1]*d[2]]:h?[d[0]*d[1],d[2]]:d,o=[a[1],a[0]];let m=16;return u=_=>{let $=B("a",i,a.length),w=re("output",i,o.length);return`
  ${_.registerUniform("output_size","u32").declareVariables($,w)}
  var<workgroup> tile : array<array<${w.type.value}, ${m+1}>, ${m}>;
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
      ${w.setByIndices(`${w.type.indices}(output_row, output_col)`,"tile[local_id.x][local_id.y]")}
    }
  }`},{name:"TransposeShared",shaderCache:{inputDependencies:["type"]},getRunData:()=>{let _=M.size(s);return{outputs:[{dims:s,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(o[1]/m),y:Math.ceil(o[0]/m)},programUniforms:[{type:12,data:_},...le(a,o)]}},getShaderSource:u}}return u=m=>{let _=B("a",i,a.length),$=re("output",i,o.length);return`
  ${m.registerUniform("output_size","u32").declareVariables(_,$)}

  ${qs(r,n,_,$)}

  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let indices = ${$.offsetToIndices("global_idx")};
    let aIndices = perm(indices);

    ${$.setByOffset("global_idx",_.getByIndices("aIndices"))}
  }`},{name:"Transpose",shaderCache:{hint:`${t}`,inputDependencies:["rank"]},getRunData:()=>{let m=M.size(s);return{outputs:[{dims:s,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(m/64)},programUniforms:[{type:12,data:m},...le(a,o)]}},getShaderSource:u}},js=(e,t)=>{Ls(e.inputs,t.perm),e.compute(xt(e.inputs[0],t.perm))},Hs=e=>De({perm:e.perm})}),Ks,Zs,Qs,Xs,Ys,Js,ea,ta,ia,na,At,ra,sa,aa,oa,la,ua,da,ca,pa,fa,vp=k(()=>{_e(),$e(),xe(),qn(),Kt(),Ks={max:"select(bestValue, candidate, candidate > bestValue)",min:"select(bestValue, candidate, candidate < bestValue)",mean:"bestValue + candidate",sum:"bestValue + candidate",prod:"bestValue * candidate",sumSquare:"bestValue + candidate * candidate",logSumExp:"bestValue + exp(candidate)",l1:"bestValue + abs(candidate)",l2:"bestValue + candidate * candidate",logSum:"bestValue + candidate"},Zs={max:"select(bestValue, candidate, candidate > bestValue)",min:"select(bestValue, candidate, candidate < bestValue)",mean:"bestValue + candidate",sum:"bestValue + candidate",prod:"bestValue * candidate",sumSquare:"bestValue + candidate",logSumExp:"bestValue + candidate",l1:"bestValue + candidate",l2:"bestValue + candidate",logSum:"bestValue + candidate"},Qs={max:"_A[offset]",min:"_A[offset]",mean:"0",sum:"0",prod:"1",sumSquare:"0",logSumExp:"0",l1:"0",l2:"0",logSum:"0"},Xs={max:"bestValue",min:"bestValue",sum:"bestValue",prod:"bestValue",sumSquare:"bestValue",logSumExp:"log(bestValue)",l1:"bestValue",l2:"sqrt(bestValue)",logSum:"log(bestValue)"},Ys=(e,t)=>{let i=[];for(let n=t-e;n<t;++n)i.push(n);return i},Js=(e,t)=>{let i=[],n=e.length;for(let s=0;s<n;s++)t.indexOf(s)===-1&&i.push(e[s]);let r=t.map(s=>e[s]);return[i,r]},ea=(e,t)=>{let i=e.length+t.length,n=[],r=0;for(let s=0;s<i;s++)t.indexOf(s)===-1?n.push(e[r++]):n.push(1);return n},ta=(e,t)=>{for(let i=0;i<e.length;++i)if(e[e.length-i-1]!==t-1-i)return!1;return!0},ia=(e,t)=>{let i=[];if(!ta(e,t)){for(let n=0;n<t;++n)e.indexOf(n)===-1&&i.push(n);e.forEach(n=>i.push(n))}return i},na=(e,t,i,n,r,s,a)=>{let o=i[0].dims,l=M.size(s),u=M.size(a),d=B("_A",i[0].dataType,o),c=re("output",r,s),p=64;l===1&&(p=256);let h=`
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

          var bestValue = f32(${Qs[n]});
          let Length = uniforms.reduceSize;
          for (var k = local_idx; k < Length; k = k + ${p}) {
           let candidate = f32(${d.getByOffset("offset + k")});
           bestValue = ${Ks[n]};
          }
          aBestValues[local_idx] = bestValue;
          workgroupBarrier();

         var reduceSize = min(Length, ${p}u);
         for (var currentSize = reduceSize / 2u; reduceSize > 1u;
             currentSize = reduceSize / 2u) {
           let interval = DIV_CEIL(reduceSize, 2u);
           if (local_idx < currentSize) {
            let candidate = aBestValues[local_idx + interval];
            bestValue = ${Zs[n]};
            aBestValues[local_idx] = bestValue;
           }
           reduceSize = interval;
           workgroupBarrier();
         }

         if (local_idx == 0u) {
          ${c.setByOffset("outputIndex",`${n==="mean"?`${c.type.storage}(bestValue / f32(uniforms.reduceSize))`:`${c.type.storage}(${Xs[n]})`}`)};
         }
        }`;return{name:e,shaderCache:{hint:`${t};${p}`,inputDependencies:["type"]},getShaderSource:m,getRunData:()=>({outputs:[{dims:s,dataType:r}],dispatchGroup:{x:l},programUniforms:[{type:12,data:u}]})}},At=(e,t,i,n)=>{let r=e.inputs.length===1?i:Un(e.inputs,i),s=r.axes;s.length===0&&!r.noopWithEmptyAxes&&(s=e.inputs[0].dims.map((h,m)=>m));let a=M.normalizeAxes(s,e.inputs[0].dims.length),o=a,l=e.inputs[0],u=ia(o,e.inputs[0].dims.length);u.length>0&&(l=e.compute(xt(e.inputs[0],u),{inputs:[0],outputs:[-1]})[0],o=Ys(o.length,l.dims.length));let[d,c]=Js(l.dims,o),p=d;r.keepDims&&(p=ea(d,a)),e.compute(na(t,r.cacheKey,[l],n,e.inputs[0].dataType,p,c),{inputs:[l]})},ra=(e,t)=>{At(e,"ReduceMeanShared",t,"mean")},sa=(e,t)=>{At(e,"ReduceL1Shared",t,"l1")},aa=(e,t)=>{At(e,"ReduceL2Shared",t,"l2")},oa=(e,t)=>{At(e,"ReduceLogSumExpShared",t,"logSumExp")},la=(e,t)=>{At(e,"ReduceMaxShared",t,"max")},ua=(e,t)=>{At(e,"ReduceMinShared",t,"min")},da=(e,t)=>{At(e,"ReduceProdShared",t,"prod")},ca=(e,t)=>{At(e,"ReduceSumShared",t,"sum")},pa=(e,t)=>{At(e,"ReduceSumSquareShared",t,"sumSquare")},fa=(e,t)=>{At(e,"ReduceLogSumShared",t,"logSum")}}),zt,ha,Ki,Un,Rt,ma,ga,_a,ya,wa,ba,va,$a,xa,Sa,Ot,ka,Ta,Ea,Ca,Ia,Aa,za,Ra,Oa,Ma,qn=k(()=>{_e(),$e(),Xe(),xe(),vp(),zt=e=>{if(!e||e.length===0||e.length>2)throw new Error("Reduce op requires 1 or 2 inputs.");if(e.length===2&&e[1].dims.length!==1)throw new Error("Invalid axes input dims.")},ha=e=>["","",`var value = ${e.getByIndices("input_indices")};`,""],Ki=(e,t,i,n,r,s,a=!1,o=!1)=>{let l=[],u=i[0].dims,d=u.length,c=M.normalizeAxes(r,d),p=!o&&c.length===0;u.forEach((_,$)=>{p||c.indexOf($)>=0?a&&l.push(1):l.push(_)});let h=l.length,m=M.size(l);return{name:e,shaderCache:t,getShaderSource:_=>{let $=[],w=B("_A",i[0].dataType,d),g=re("output",s,h),T=n(w,g,c),x=T[2];for(let I=0,O=0;I<d;I++)p||c.indexOf(I)>=0?(a&&O++,x=`for(var j${I}: u32 = 0; j${I} < ${u[I]}; j${I}++) {
                  ${T[2].includes("last_index")?`let last_index = j${I};`:""}
                  ${w.indicesSet("input_indices",I,`j${I}`)}
                  ${x}
                }`):($.push(`${w.indicesSet("input_indices",I,g.indicesGet("output_indices",O))};`),O++);return`

        ${_.registerUniform("output_size","u32").declareVariables(w,g)}

        ${_.mainStart()}
          ${_.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
          var input_indices: ${w.type.indices};
          let output_indices = ${g.offsetToIndices("global_idx")};

          ${$.join(`
`)}
          ${T[0]}       // init ops for reduce max/min
          ${T[1]}
          ${x}
          ${T[3]}
          ${T.length===4?g.setByOffset("global_idx","value"):T.slice(4).join(`
`)}
        }`},getRunData:()=>({outputs:[{dims:l,dataType:s}],dispatchGroup:{x:Math.ceil(m/64)},programUniforms:[{type:12,data:m},...le(u,l)]})}},Un=(e,t)=>{let i=[];return e[1].dims[0]>0&&e[1].getBigInt64Array().forEach(n=>i.push(Number(n))),De({axes:i,keepDims:t.keepDims,noopWithEmptyAxes:t.noopWithEmptyAxes})},Rt=(e,t,i,n)=>{let r=e.inputs,s=r.length===1?i:Un(r,i);e.compute(Ki(t,{hint:s.cacheKey,inputDependencies:["rank"]},[r[0]],s.noopWithEmptyAxes&&s.axes.length===0?ha:n,s.axes,r[0].dataType,s.keepDims,s.noopWithEmptyAxes),{inputs:[0]})},ma=(e,t)=>{zt(e.inputs),Rt(e,"ReduceLogSum",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += ${i.getByIndices("input_indices")};`,"value = log(value);"])},ga=(e,t)=>{zt(e.inputs),Rt(e,"ReduceL1",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += abs(${i.getByIndices("input_indices")});`,""])},_a=(e,t)=>{zt(e.inputs),Rt(e,"ReduceL2",t,(i,n)=>[`var t = ${n.type.value}(0); var value = ${n.type.value}(0);`,"",`t = ${i.getByIndices("input_indices")}; value += (t * t);`,"value = sqrt(value);"])},ya=(e,t)=>{zt(e.inputs),Rt(e,"ReduceLogSumExp",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += exp(${i.getByIndices("input_indices")});`,"value = log(value);"])},wa=(e,t)=>{zt(e.inputs),Rt(e,"ReduceMax",t,(i,n,r)=>{let s=[];for(let a=0;a<i.rank;a++)(r.indexOf(a)>=0||r.length===0)&&s.push(i.indicesSet("input_indices",a,0));return[`${s.join(`
`)}`,`var value = ${i.getByIndices("input_indices")};`,`value = max(value, ${i.getByIndices("input_indices")});`,""]})},ba=(e,t)=>{zt(e.inputs),Rt(e,"ReduceMean",t,(i,n,r)=>{let s=1;for(let a=0;a<i.rank;a++)(r.indexOf(a)>=0||r.length===0)&&(s*=e.inputs[0].dims[a]);return["var sum = f32(0);","",`sum += f32(${i.getByIndices("input_indices")});`,`let value = ${n.type.value}(sum / ${s});`]})},va=(e,t)=>{zt(e.inputs),Rt(e,"ReduceMin",t,(i,n,r)=>{let s=[];for(let a=0;a<i.rank;a++)(r.indexOf(a)>=0||r.length===0)&&s.push(`input_indices[${a}] = 0;`);return[`${s.join(`
`)}`,`var value = ${i.getByIndices("input_indices")};`,`value = min(value, ${i.getByIndices("input_indices")});`,""]})},$a=(e,t)=>{zt(e.inputs),Rt(e,"ReduceProd",t,(i,n)=>[`var value = ${n.type.storage}(1);`,"",`value *= ${i.getByIndices("input_indices")};`,""])},xa=(e,t)=>{zt(e.inputs),Rt(e,"ReduceSum",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += ${i.getByIndices("input_indices")};`,""])},Sa=(e,t)=>{zt(e.inputs),Rt(e,"ReduceSumSquare",t,(i,n)=>[`var t = ${n.type.value}(0); var value = ${n.type.value}(0);`,"",`t = ${i.getByIndices("input_indices")}; value += t * t;`,""])},Ot=(e,t,i)=>{if(t.length===0)return i;let n=1,r=1;for(let s=0;s<t.length;s++)t.indexOf(s)===-1?n*=e[s]:r*=e[s];return r<32&&n>1024},ka=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ba(e,t):ra(e,t)},Ta=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ga(e,t):sa(e,t)},Ea=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?_a(e,t):aa(e,t)},Ca=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ya(e,t):oa(e,t)},Ia=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?wa(e,t):la(e,t)},Aa=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?va(e,t):ua(e,t)},za=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?$a(e,t):da(e,t)},Ra=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?xa(e,t):ca(e,t)},Oa=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?Sa(e,t):pa(e,t)},Ma=(e,t)=>{Ot(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ma(e,t):fa(e,t)}}),Wn,Fa,Da,Gn,$p=k(()=>{_e(),Xe(),qn(),Wn=e=>{if(!e||e.length===0||e.length>2)throw new Error("ArgMinMaxOp op requires 1 or 2 inputs.");if(e[0].dataType!==1)throw new Error("Invalid input type.")},Fa=(e,t)=>{Wn(e.inputs);let i=(n,r,s)=>{let a=[];for(let o=0;o<n.rank;o++)(s.indexOf(o)>=0||s.length===0)&&a.push(`input_indices[${o}] = 0;`);return[`${a.join(`
`)}`,`var value = ${n.getByIndices("input_indices")};
var best_index : i32 = 0;`,`if (${n.getByIndices("input_indices")} ${t.selectLastIndex>0?"<=":"<"} value) {
         value = ${n.getByIndices("input_indices")};
         best_index = i32(last_index);
       }`,"",r.setByOffset("global_idx","best_index")]};e.compute(Ki("ArgMin",{hint:t.cacheKey,inputDependencies:["rank"]},[e.inputs[0]],i,[t.axis],7,t.keepDims),{inputs:[0]})},Da=(e,t)=>{Wn(e.inputs);let i=(n,r,s)=>{let a=[];for(let o=0;o<n.rank;o++)(s.indexOf(o)>=0||s.length===0)&&a.push(`input_indices[${o}] = 0;`);return[`${a.join(`
`)}`,`var value = ${n.getByIndices("input_indices")};
var best_index : i32 = 0;`,`if (${n.getByIndices("input_indices")} ${t.selectLastIndex>0?">=":">"} value) {
         value = ${n.getByIndices("input_indices")};
         best_index = i32(last_index);
       }`,"",r.setByOffset("global_idx","best_index")]};e.compute(Ki("argMax",{hint:t.cacheKey,inputDependencies:["rank"]},[e.inputs[0]],i,[t.axis],7,t.keepDims),{inputs:[0]})},Gn=e=>De(e)}),Ba,Zi,Pa,Na,Va,Si,La,Ua,jn=k(()=>{_e(),$e(),Fn(),xe(),Ba=(e,t)=>{let i=e[0],n=e[1],r=e[2],s=e[3],a=e[4],o=e[5];if(a&&o)throw new Error("Attention cannot have both past and attention_bias");if(i.dims.length!==3)throw new Error('Input "input" must have 3 dimensions');let l=i.dims[0],u=i.dims[1],d=i.dims[2];if(r.dims.length!==1)throw new Error('Input "bias" is expected to have 1 dimensions');if(n.dims.length!==2)throw new Error('Input "weights" is expected to have 2 dimensions');if(n.dims[0]!==d)throw new Error("Input 1 dimension 0 should have same length as dimension 2 of input 0");if(r.dims[0]!==n.dims[1])throw new Error('Input "bias" dimension 0 should have same length as dimension 1 of input "weights"');let c=r.dims[0]/3,p=c,h=p;if(t.qkvHiddenSizes.length>0){if(t.qkvHiddenSizes.length!==3)throw new Error("qkv_hidden_sizes attribute should have 3 elements");for(let T of t.qkvHiddenSizes)if(T%t.numHeads!==0)throw new Error("qkv_hidden_sizes should be divisible by num_heads");c=t.qkvHiddenSizes[0],p=t.qkvHiddenSizes[1],h=t.qkvHiddenSizes[2]}let m=u;if(c!==p)throw new Error("qkv_hidden_sizes first element should be same as the second");if(r.dims[0]!==c+p+h)throw new Error('Input "bias" dimension 0 should have same length as sum of Q/K/V hidden sizes');let _=0;if(a){if(p!==h)throw new Error('Input "past" expect k_hidden_size == v_hidden_size');if(a.dims.length!==5)throw new Error('Input "past" must have 5 dimensions');if(a.dims[0]!==2)throw new Error('Input "past" first dimension must be 2');if(a.dims[1]!==l)throw new Error('Input "past" second dimension must be batch_size');if(a.dims[2]!==t.numHeads)throw new Error('Input "past" third dimension must be num_heads');if(a.dims[4]!==p/t.numHeads)throw new Error('Input "past" fifth dimension must be k_hidden_size / num_heads');t.pastPresentShareBuffer||(_=a.dims[3])}let $=m+_,w=-1,g=0;if(s)throw new Error("Mask not supported");if(a)throw new Error("past is not supported");if(o){if(o.dims.length!==4)throw new Error('Input "attention_bias" must have 4 dimensions');if(o.dims[0]!==l||o.dims[1]!==t.numHeads||o.dims[2]!==u||o.dims[3]!==$)throw new Error('Expect "attention_bias" shape (batch_size, num_heads, sequence_length, total_sequence_length)')}return{batchSize:l,sequenceLength:u,pastSequenceLength:_,kvSequenceLength:m,totalSequenceLength:$,maxSequenceLength:w,inputHiddenSize:d,hiddenSize:c,vHiddenSize:h,headSize:Math.floor(c/t.numHeads),vHeadSize:Math.floor(h/t.numHeads),numHeads:t.numHeads,isUnidirectional:!1,pastPresentShareBuffer:!1,maskFilterValue:t.maskFilterValue,maskType:g,scale:t.scale,broadcastResPosBias:!1,passPastInKv:!1,qkvFormat:1}},Zi=(e,t,i)=>t&&e?`
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
    `,Pa=(e,t,i,n,r,s,a,o)=>{let l=Qe(a?1:s),u=64,d=s/l;d<u&&(u=32);let c=Math.ceil(s/l/u),p=[{type:12,data:t},{type:12,data:i},{type:12,data:n},{type:12,data:r},{type:12,data:d},{type:12,data:c}],h=at(e.dataType,l),m=_t(1,l),_=["type"];a&&_.push("type"),o&&_.push("type");let $=w=>{let g=re("x",e.dataType,e.dims,l),T=[g],x=a?B("seq_lens",a.dataType,a.dims):void 0;x&&T.push(x);let I=o?B("total_sequence_length_input",o.dataType,o.dims):void 0;I&&T.push(I);let O=_t(e.dataType),z=[{name:"batch_size",type:"u32"},{name:"num_heads",type:"u32"},{name:"past_sequence_length",type:"u32"},{name:"sequence_length",type:"u32"},{name:"total_sequence_length",type:"u32"},{name:"elements_per_thread",type:"u32"}];return`
  var<workgroup> thread_max: array<f32, ${u}>;
  var<workgroup> thread_sum: array<f32, ${u}>;
  ${w.registerUniforms(z).declareVariables(...T)}
  ${w.mainStart([u,1,1])}
    let batchIdx = workgroup_id.z / uniforms.num_heads;
    let headIdx = workgroup_id.z % uniforms.num_heads;
    let sequence_length = uniforms.sequence_length;
    var total_sequence_length = uniforms.total_sequence_length;
    ${Zi(x,I,!1)}
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
  }`};return{name:"AttentionProbsSoftmax",shaderCache:{hint:`${u};${h};${l}`,inputDependencies:_},getShaderSource:$,getRunData:()=>({outputs:[],dispatchGroup:{x:1,y:r,z:t*i},programUniforms:p})}},Na=(e,t,i,n,r,s,a,o,l)=>{let u=a+s.kvSequenceLength,d=[s.batchSize,s.numHeads,s.sequenceLength,u],c=e>1&&n,p=s.kvNumHeads?s.kvNumHeads:s.numHeads,h=c?[s.batchSize,p,u,s.headSize]:void 0,m=s.nReps?s.nReps:1,_=s.scale===0?1/Math.sqrt(s.headSize):s.scale,$=Qe(s.headSize),w=s.headSize/$,g=12,T={x:Math.ceil(u/g),y:Math.ceil(s.sequenceLength/g),z:s.batchSize*s.numHeads},x=[{type:12,data:s.sequenceLength},{type:12,data:w},{type:12,data:u},{type:12,data:s.numHeads},{type:12,data:s.headSize},{type:1,data:_},{type:12,data:a},{type:12,data:s.kvSequenceLength},{type:12,data:m}],I=c&&n&&M.size(n.dims)>0,O=["type","type"];I&&O.push("type"),r&&O.push("type"),o&&O.push("type"),l&&O.push("type");let z=[{dims:d,dataType:t.dataType,gpuDataType:0}];c&&z.push({dims:h,dataType:t.dataType,gpuDataType:0});let N=q=>{let te=B("q",t.dataType,t.dims,$),ye=B("key",i.dataType,i.dims,$),de=[te,ye];if(I){let ce=B("past_key",n.dataType,n.dims,$);de.push(ce)}r&&de.push(B("attention_bias",r.dataType,r.dims));let be=o?B("seq_lens",o.dataType,o.dims):void 0;be&&de.push(be);let ne=l?B("total_sequence_length_input",l.dataType,l.dims):void 0;ne&&de.push(ne);let Te=re("output",t.dataType,d),he=[Te];c&&he.push(re("present_key",t.dataType,h,$));let ae=_t(1,$),Oe=[{name:"M",type:"u32"},{name:"K",type:"u32"},{name:"N",type:"u32"},{name:"num_heads",type:"u32"},{name:"head_size",type:"u32"},{name:"alpha",type:"f32"},{name:"past_sequence_length",type:"u32"},{name:"kv_sequence_length",type:"u32"},{name:"n_reps",type:"u32"}];return`
  const TILE_SIZE = ${g}u;

  var<workgroup> tileQ: array<${te.type.storage}, ${g*g}>;
  var<workgroup> tileK: array<${te.type.storage}, ${g*g}>;
  ${q.registerUniforms(Oe).declareVariables(...de,...he)}
  ${q.mainStart([g,g,1])}
    // x holds the N and y holds the M
    let headIdx = workgroup_id.z % uniforms.num_heads;
    let kvHeadIdx = ${m===1?"headIdx":"headIdx / uniforms.n_reps"};
    let kv_num_heads = ${m===1?"uniforms.num_heads":"uniforms.num_heads / uniforms.n_reps"};
    let batchIdx = workgroup_id.z / uniforms.num_heads;
    let m = workgroup_id.y * TILE_SIZE;
    let n = workgroup_id.x * TILE_SIZE;
    let sequence_length = uniforms.M;
    var total_sequence_length = uniforms.N;
    ${Zi(be,ne,!0)}
    let absKvHeadIdx = batchIdx * kv_num_heads + kvHeadIdx;
    let qOffset = workgroup_id.z * uniforms.M * uniforms.K + m * uniforms.K;
    ${I&&c?"let pastKeyOffset = absKvHeadIdx * uniforms.past_sequence_length * uniforms.K;":""};
    let kOffset = absKvHeadIdx * uniforms.kv_sequence_length * uniforms.K;
    ${c?"let presentKeyOffset = absKvHeadIdx * uniforms.N * uniforms.K;":""}
    var value = ${ae}(0);
    for (var w: u32 = 0u; w < uniforms.K; w += TILE_SIZE) {
      if (global_id.y < uniforms.M && w + local_id.x < uniforms.K) {
        tileQ[TILE_SIZE * local_id.y + local_id.x] = q[qOffset + local_id.y * uniforms.K + w + local_id.x];
      }
      if (n + local_id.y < uniforms.N && w + local_id.x < uniforms.K) {
        var idx = TILE_SIZE * local_id.y + local_id.x;
      ${I&&c?`
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
          value += ${ae}(tileQ[TILE_SIZE * local_id.y + k] * tileK[TILE_SIZE * local_id.x + k]);
      }

      workgroupBarrier();
    }

    if (global_id.y < uniforms.M && global_id.x < total_sequence_length) {
      let headOffset = workgroup_id.z * uniforms.M * uniforms.N;
      let outputIdx = headOffset + global_id.y * uniforms.N + global_id.x;
      var sum: f32 = ${(()=>{switch($){case 1:return"value";case 2:return"value.x + value.y";case 4:return"value.x + value.y + value.z + value.w";default:throw new Error(`Unsupported components: ${$}`)}})()};
        output[outputIdx] = ${Te.type.value} (sum * uniforms.alpha) + ${r?"attention_bias[outputIdx]":"0.0"};
    }
  }`};return{name:"AttentionProbs",shaderCache:{hint:`${$};${r!==void 0};${n!==void 0};${e}`,inputDependencies:O},getRunData:()=>({outputs:z,dispatchGroup:T,programUniforms:x}),getShaderSource:N}},Va=(e,t,i,n,r,s,a=void 0,o=void 0)=>{let l=s+r.kvSequenceLength,u=r.nReps?r.nReps:1,d=r.vHiddenSize*u,c=e>1&&n,p=r.kvNumHeads?r.kvNumHeads:r.numHeads,h=c?[r.batchSize,p,l,r.headSize]:void 0,m=[r.batchSize,r.sequenceLength,d],_=12,$={x:Math.ceil(r.vHeadSize/_),y:Math.ceil(r.sequenceLength/_),z:r.batchSize*r.numHeads},w=[{type:12,data:r.sequenceLength},{type:12,data:l},{type:12,data:r.vHeadSize},{type:12,data:r.numHeads},{type:12,data:r.headSize},{type:12,data:d},{type:12,data:s},{type:12,data:r.kvSequenceLength},{type:12,data:u}],g=c&&n&&M.size(n.dims)>0,T=["type","type"];g&&T.push("type"),a&&T.push("type"),o&&T.push("type");let x=[{dims:m,dataType:t.dataType,gpuDataType:0}];c&&x.push({dims:h,dataType:t.dataType,gpuDataType:0});let I=O=>{let z=B("probs",t.dataType,t.dims),N=B("v",i.dataType,i.dims),q=[z,N];g&&q.push(B("past_value",n.dataType,n.dims));let te=a?B("seq_lens",a.dataType,a.dims):void 0;a&&q.push(te);let ye=o?B("total_sequence_length_input",o.dataType,o.dims):void 0;o&&q.push(ye);let de=[re("output",t.dataType,m)];c&&de.push(re("present_value",t.dataType,h));let be=[{name:"M",type:"u32"},{name:"K",type:"u32"},{name:"N",type:"u32"},{name:"num_heads",type:"u32"},{name:"head_size",type:"u32"},{name:"v_hidden_size",type:"u32"},{name:"past_sequence_length",type:"u32"},{name:"kv_sequence_length",type:"u32"},{name:"n_reps",type:"u32"}];return`
  const TILE_SIZE = ${_}u;
  var<workgroup> tileQ: array<${z.type.value}, ${_*_}>;
  var<workgroup> tileV: array<${z.type.value}, ${_*_}>;
  ${O.registerUniforms(be).declareVariables(...q,...de)}
  ${O.mainStart([_,_,1])}
   let headIdx = workgroup_id.z % uniforms.num_heads;
   let batchIdx = workgroup_id.z / uniforms.num_heads;
   let kvHeadIdx = ${u===1?"headIdx":"headIdx / uniforms.n_reps"};
   let kv_num_heads = ${u===1?"uniforms.num_heads":"uniforms.num_heads / uniforms.n_reps"};
   let m = global_id.y;
   let n = global_id.x;
   let sequence_length = uniforms.M;
   var total_sequence_length = uniforms.K;
   ${Zi(te,ye,!0)}
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
  }`};return{name:"AttentionScore",shaderCache:{hint:`${n!==void 0};${e}`,inputDependencies:T},getRunData:()=>({outputs:x,dispatchGroup:$,programUniforms:w}),getShaderSource:I}},Si=(e,t,i,n,r,s,a,o,l,u,d=void 0,c=void 0)=>{let p=Math.min(e.outputCount,1+(a?1:0)+(o?1:0)),h=p>1?u.pastSequenceLength:0,m=h+u.kvSequenceLength,_=l&&M.size(l.dims)>0?l:void 0,$=[t,i];p>1&&a&&M.size(a.dims)>0&&$.push(a),_&&$.push(_),d&&$.push(d),c&&$.push(c);let w=e.compute(Na(p,t,i,a,_,u,h,d,c),{inputs:$,outputs:p>1?[-1,1]:[-1]})[0];e.compute(Pa(w,u.batchSize,u.numHeads,h,u.sequenceLength,m,d,c),{inputs:d&&c?[w,d,c]:[w],outputs:[]});let g=[w,n];p>1&&o&&M.size(o.dims)>0&&g.push(o),d&&g.push(d),c&&g.push(c),e.compute(Va(p,w,n,o,u,h,d,c),{inputs:g,outputs:p>1?[0,2]:[0]})},La=(e,t)=>{let i=[t.batchSize,t.numHeads,t.sequenceLength,t.headSize],n=t.sequenceLength,r=t.inputHiddenSize,s=t.headSize,a=12,o={x:Math.ceil(t.headSize/a),y:Math.ceil(t.sequenceLength/a),z:t.batchSize*t.numHeads},l=[e.inputs[0],e.inputs[1],e.inputs[2]],u=[{type:12,data:n},{type:12,data:r},{type:12,data:s},{type:12,data:t.numHeads},{type:12,data:t.headSize},{type:12,data:t.hiddenSize},{type:12,data:t.hiddenSize+t.hiddenSize+t.vHiddenSize}],d=c=>{let p=re("output_q",l[0].dataType,i),h=re("output_k",l[0].dataType,i),m=re("output_v",l[0].dataType,i),_=B("input",l[0].dataType,l[0].dims),$=B("weight",l[1].dataType,l[1].dims),w=B("bias",l[2].dataType,l[2].dims),g=_.type.storage,T=[{name:"M",type:"u32"},{name:"K",type:"u32"},{name:"N",type:"u32"},{name:"num_heads",type:"u32"},{name:"head_size",type:"u32"},{name:"hidden_size",type:"u32"},{name:"ldb",type:"u32"}];return`
  const TILE_SIZE = ${a}u;
  var<workgroup> tileInput: array<${g}, ${a*a}>;
  var<workgroup> tileWeightQ: array<${g}, ${a*a}>;
  var<workgroup> tileWeightK: array<${g}, ${a*a}>;
  var<workgroup> tileWeightV: array<${g}, ${a*a}>;
  ${c.registerUniforms(T).declareVariables(_,$,w,p,h,m)}
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
  }`};return e.compute({name:"AttentionPrepare",shaderCache:{inputDependencies:["type","type","type"]},getRunData:()=>({outputs:[{dims:i,dataType:e.inputs[0].dataType,gpuDataType:0},{dims:i,dataType:e.inputs[0].dataType,gpuDataType:0},{dims:i,dataType:e.inputs[0].dataType,gpuDataType:0}],dispatchGroup:o,programUniforms:u}),getShaderSource:d},{inputs:l,outputs:[-1,-1,-1]})},Ua=(e,t)=>{let i=Ba(e.inputs,t),[n,r,s]=La(e,i);return Si(e,n,r,s,e.inputs[4],void 0,void 0,void 0,e.inputs[5],i)}}),qa,Wa,Ga,ja,xp=k(()=>{wt(),_e(),$e(),Xe(),xe(),qa=(e,t)=>{if(!e||e.length!==5)throw new Error("BatchNormalization requires 5 inputs");let i=(n,r,s)=>{let a=r.length;if(a!==n.length)throw new Error(`${s}: num dimensions != ${a}`);r.forEach((o,l)=>{if(o!==n[l])throw new Error(`${s}: dim[${l}] do not match`)})};if(e[0].dims.length>1){let n=t.format==="NHWC"?t.spatial?e[0].dims.slice(-1):e[0].dims.slice(-1).concat(e[0].dims.slice(1,e[0].dims.length-1)):e[0].dims.slice(1,t.spatial?2:void 0);i(e[1].dims,n,"Invalid input scale"),i(e[2].dims,n,"Invalid input B"),i(e[3].dims,n,"Invalid input mean"),i(e[4].dims,n,"Invalid input var")}else i(e[1].dims,[1],"Invalid input scale"),i(e[2].dims,[1],"Invalid input B"),i(e[3].dims,[1],"Invalid input mean"),i(e[4].dims,[1],"Invalid input var")},Wa=(e,t)=>{let{epsilon:i,spatial:n,format:r}=t,s=e[0].dims,a=n?Qe(s[s.length-1]):1,o=r==="NHWC"&&s.length>1?a:1,l=M.size(s)/a,u=n,d=u?s.length:s,c=B("x",e[0].dataType,e[0].dims,a),p=B("scale",e[1].dataType,e[1].dims,o),h=B("bias",e[2].dataType,e[2].dims,o),m=B("inputMean",e[3].dataType,e[3].dims,o),_=B("inputVar",e[4].dataType,e[4].dims,o),$=re("y",e[0].dataType,d,a),w=()=>{let T="";if(n)T=`let cOffset = ${s.length===1?"0u":r==="NHWC"?`outputIndices[${s.length-1}] / ${a}`:"outputIndices[1]"};`;else if(r==="NCHW")T=`
            ${$.indicesSet("outputIndices","0","0")}
            let cOffset = ${$.indicesToOffset("outputIndices")};`;else{T=`var cIndices = ${p.type.indices}(0);
                       cIndices[0] = outputIndices[${s.length-1}];`;for(let x=1;x<p.rank;x++)T+=`cIndices[${x}] = outputIndices[${x}];`;T+=`let cOffset = ${p.indicesToOffset("cIndices")};`}return T},g=T=>`
  const epsilon = ${i};
  ${T.registerUniform("outputSize","u32").declareVariables(c,p,h,m,_,$)}
  ${T.mainStart()}
  ${T.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
    var outputIndices = ${$.offsetToIndices(`global_idx * ${a}`)};
    ${w()}
    let scale = ${p.getByOffset("cOffset")};
    let bias = ${h.getByOffset("cOffset")};
    let inputMean = ${m.getByOffset("cOffset")};
    let inputVar = ${_.getByOffset("cOffset")};
    let x = ${c.getByOffset("global_idx")};
    let value = (x - inputMean) * inverseSqrt(inputVar + epsilon) * scale + bias;
    ${$.setByOffset("global_idx","value")}
  }`;return{name:"BatchNormalization",shaderCache:{hint:`${t.epsilon}_${t.format}_${n}_${a}`,inputDependencies:u?["rank","type","type","type","type"]:void 0},getShaderSource:g,getRunData:()=>({outputs:[{dims:e[0].dims,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:u?[{type:12,data:l},...le(s)]:[{type:12,data:l}]})}},Ga=e=>De(e),ja=(e,t)=>{let{inputs:i,outputCount:n}=e,r=Ga({...t,outputCount:n});if(oe.webgpu.validateInputContent&&qa(i,r),t.trainingMode)throw new Error("BatchNormalization trainingMode is not supported yet.");e.compute(Wa(i,r))}}),Ha,Ka,Za,Sp=k(()=>{$e(),xe(),Ha=e=>{if(e[0].dims.length!==3)throw new Error("input should have 3 dimensions");if(![320,640,1280].includes(e[0].dims[2]))throw new Error("number of channels should be 320, 640 or 1280");if(e[1].dims.length!==1)throw new Error("bias is expected to have 1 dimensions");if(e[0].dims[2]!==e[1].dims[0])throw new Error("last dimension of input and bias are not the same")},Ka=e=>{let t=e[0].dims,i=e[0].dims[2],n=M.size(t)/4,r=e[0].dataType,s=B("input",r,t,4),a=B("bias",r,[i],4),o=B("residual",r,t,4),l=re("output",r,t,4);return{name:"BiasAdd",getRunData:()=>({outputs:[{dims:t,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(n/64)}}),getShaderSource:u=>`
  const channels = ${i}u / 4;
  ${u.declareVariables(s,a,o,l)}

  ${u.mainStart()}
    ${u.guardAgainstOutOfBoundsWorkgroupSizes(n)}
    let value = ${s.getByOffset("global_idx")}
      + ${a.getByOffset("global_idx % channels")} + ${o.getByOffset("global_idx")};
    ${l.setByOffset("global_idx","value")}
  }`}},Za=e=>{Ha(e.inputs),e.compute(Ka(e.inputs))}}),Qa,Re,Xa,Ya,Ja,eo,to,io,no,ro,so,ao,oo,lo,uo,co,ki,po,Qi,fo,ho,mo,go,_o,yo,wo,bo,vo,$o,xo,So,ko,To,Eo,Co,Hn,Io,Kn,Zn,Ao,zo,Ro,Oo,Mo,Fo,Qn=k(()=>{_e(),$e(),Xe(),xe(),Qa=(e,t,i,n,r,s,a)=>{let o=Math.ceil(t/4),l="";typeof r=="string"?l=`${r}(a)`:l=r("a");let u=B("inputData",i,[o],4),d=re("outputData",n,[o],4),c=[{name:"vec_size",type:"u32"}];return a&&c.push(...a),`
      ${e.registerUniforms(c).declareVariables(u,d)}

  ${s??""}

  ${e.mainStart()}
    ${e.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.vec_size")}

    let a = ${u.getByOffset("global_idx")};
    ${d.setByOffset("global_idx",l)}
  }`},Re=(e,t,i,n,r,s=e.dataType,a,o)=>{let l=[{type:12,data:Math.ceil(M.size(e.dims)/4)}];return a&&l.push(...a),{name:t,shaderCache:{hint:r,inputDependencies:["type"]},getShaderSource:u=>Qa(u,M.size(e.dims),e.dataType,s,i,n,o),getRunData:u=>({outputs:[{dims:e.dims,dataType:s}],dispatchGroup:{x:Math.ceil(M.size(u[0].dims)/64/4)},programUniforms:l})}},Xa=e=>{e.compute(Re(e.inputs[0],"Abs","abs"))},Ya=e=>{e.compute(Re(e.inputs[0],"Acos","acos"))},Ja=e=>{e.compute(Re(e.inputs[0],"Acosh","acosh"))},eo=e=>{e.compute(Re(e.inputs[0],"Asin","asin"))},to=e=>{e.compute(Re(e.inputs[0],"Asinh","asinh"))},io=e=>{e.compute(Re(e.inputs[0],"Atan","atan"))},no=e=>{e.compute(Re(e.inputs[0],"Atanh","atanh"))},ro=e=>De(e),so=(e,t)=>{let i;switch(t.to){case 10:i="vec4<f16>";break;case 1:i="vec4<f32>";break;case 12:i="vec4<u32>";break;case 6:i="vec4<i32>";break;case 9:i="vec4<bool>";break;default:throw new RangeError(`not supported type (specified in attribute 'to' from 'Cast' operator): ${t.to}`)}e.compute(Re(e.inputs[0],"Cast",i,void 0,t.cacheKey,t.to))},ao=e=>{let t,i,n=e.length>=2&&e[1].data!==0,r=e.length>=3&&e[2].data!==0;switch(e[0].dataType){case 1:t=n?e[1].getFloat32Array()[0]:-34028234663852886e22,i=r?e[2].getFloat32Array()[0]:34028234663852886e22;break;case 10:t=n?e[1].getUint16Array()[0]:64511,i=r?e[2].getUint16Array()[0]:31743;break;default:throw new Error("Unsupport data type")}return De({min:t,max:i})},oo=(e,t)=>{let i=t||ao(e.inputs),n=_t(e.inputs[0].dataType);e.compute(Re(e.inputs[0],"Clip",r=>`clamp(${r}, vec4<${n}>(uniforms.min), vec4<${n}>(uniforms.max))`,void 0,i.cacheKey,void 0,[{type:e.inputs[0].dataType,data:i.min},{type:e.inputs[0].dataType,data:i.max}],[{name:"min",type:n},{name:"max",type:n}]),{inputs:[0]})},lo=e=>{e.compute(Re(e.inputs[0],"Ceil","ceil"))},uo=e=>{e.compute(Re(e.inputs[0],"Cos","cos"))},co=e=>{e.compute(Re(e.inputs[0],"Cosh","cosh"))},ki=e=>De(e),po=(e,t)=>{let i=_t(e.inputs[0].dataType);e.compute(Re(e.inputs[0],"Elu",n=>`elu_vf32(${n})`,`
  const elu_alpha_ = ${i}(${t.alpha});

  fn elu_f32(a: ${i}) -> ${i} {
  return select((exp(a) - 1.0) * elu_alpha_, a, a >= 0.0);
  }

  fn elu_vf32(v: vec4<${i}>) -> vec4<${i}> {
  return vec4(elu_f32(v.x), elu_f32(v.y), elu_f32(v.z), elu_f32(v.w));
  }`,t.cacheKey))},Qi=(e="f32")=>`
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
}`,fo=e=>{let t=_t(e.inputs[0].dataType);e.compute(Re(e.inputs[0],"Erf",i=>`erf_vf32(${i})`,Qi(t)))},ho=e=>{e.compute(Re(e.inputs[0],"Exp","exp"))},mo=e=>{e.compute(Re(e.inputs[0],"Floor","floor"))},go=e=>{let t=_t(e.inputs[0].dataType);e.compute(Re(e.inputs[0],"Gelu",i=>`0.5 * ${i} * (1.0 + erf_vf32(${i} * 0.7071067811865475))`,Qi(t)))},_o=(e,t)=>{let i=_t(e.inputs[0].dataType);e.compute(Re(e.inputs[0],"LeakyRelu",n=>`select(leaky_relu_alpha_ * ${n}, ${n}, ${n} >= vec4<${i}>(0.0))`,`const leaky_relu_alpha_ = ${i}(${t.alpha});`,t.cacheKey))},yo=e=>{e.compute(Re(e.inputs[0],"Not",t=>`!${t}`))},wo=e=>{e.compute(Re(e.inputs[0],"Neg",t=>`-${t}`))},bo=e=>{e.compute(Re(e.inputs[0],"Reciprocal",t=>`1.0/${t}`))},vo=e=>{let t=_t(e.inputs[0].dataType);e.compute(Re(e.inputs[0],"Relu",i=>`select(vec4<${t}>(0.0), ${i}, ${i} > vec4<${t}>(0.0))`))},$o=e=>{e.compute(Re(e.inputs[0],"Sigmoid",t=>`(1.0 / (1.0 + exp(-${t})))`))},xo=e=>De(e),So=(e,t)=>{let i=_t(e.inputs[0].dataType);e.compute(Re(e.inputs[0],"HardSigmoid",n=>`max(vec4<${i}>(0.0), min(vec4<${i}>(1.0), ${t.alpha} * ${n} + vec4<${i}>(${t.beta})))`,void 0,t.cacheKey))},ko=e=>{e.compute(Re(e.inputs[0],"Sin","sin"))},To=e=>{e.compute(Re(e.inputs[0],"Sinh","sinh"))},Eo=e=>{e.compute(Re(e.inputs[0],"Sqrt","sqrt"))},Co=e=>{e.compute(Re(e.inputs[0],"Tan","tan"))},Hn=e=>`sign(${e}) * (1 - exp(-2 * abs(${e}))) / (1 + exp(-2 * abs(${e})))`,Io=e=>{e.compute(Re(e.inputs[0],"Tanh",Hn))},Kn=(e="f32")=>`
const fast_gelu_a: ${e} = 0.5;
const fast_gelu_b: ${e} = 0.7978845608028654;
const fast_gelu_c: ${e} = 0.035677408136300125;

fn tanh_v(v: vec4<${e}>) -> vec4<${e}> {
  return ${Hn("v")};
}
`,Zn=e=>`(fast_gelu_a + fast_gelu_a * tanh_v(${e} * (fast_gelu_c * ${e} * ${e} + fast_gelu_b))) * ${e}`,Ao=e=>{let t=_t(e.inputs[0].dataType);e.compute(Re(e.inputs[0],"FastGelu",Zn,Kn(t),void 0,e.inputs[0].dataType))},zo=(e,t)=>{let i=_t(e.inputs[0].dataType);return e.compute(Re(e.inputs[0],"ThresholdedRelu",n=>`select(vec4<${i}>(0.0), ${n}, ${n} > thresholded_relu_alpha_)`,`const thresholded_relu_alpha_ = vec4<${i}>(${t.alpha});`,t.cacheKey)),0},Ro=e=>{e.compute(Re(e.inputs[0],"Log","log"))},Oo=(e,t)=>`
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
`,Mo=e=>`quick_gelu_impl(${e})`,Fo=(e,t)=>{let i=_t(e.inputs[0].dataType);e.compute(Re(e.inputs[0],"QuickGelu",Mo,Oo(i,t.alpha),t.cacheKey,e.inputs[0].dataType))}}),Do,Bo,Po,kp=k(()=>{$e(),xe(),Qn(),Do=e=>{if(e[0].dims.length!==3)throw new Error("input should have 3 dimensions");if(![2560,5120,10240].includes(e[0].dims[2]))throw new Error("hidden state should be 2560, 5120 or 10240");if(e[1].dims.length!==1)throw new Error("bias is expected to have 1 dimensions");if(e[0].dims[2]!==e[1].dims[0])throw new Error("last dimension of input and bias are not the same")},Bo=e=>{let t=e[0].dims.slice();t[2]=t[2]/2;let i=B("input",e[0].dataType,e[0].dims,4),n=B("bias",e[0].dataType,[e[0].dims[2]],4),r=re("output",e[0].dataType,t,4),s=M.size(t)/4,a=at(e[0].dataType);return{name:"BiasSplitGelu",getRunData:()=>({outputs:[{dims:t,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(s/64)}}),getShaderSource:o=>`
  const M_SQRT2 = sqrt(2.0);
  const halfChannels = ${e[0].dims[2]/4/2}u;

  ${o.declareVariables(i,n,r)}

  ${Qi(a)}

  ${o.mainStart()}
    ${o.guardAgainstOutOfBoundsWorkgroupSizes(s)}
    let biasIdx = global_idx % halfChannels;
    let batchIndex = global_idx / halfChannels;
    let inputOffset = biasIdx + batchIndex * halfChannels * 2;
    let valueLeft = input[inputOffset] + bias[biasIdx];
    let valueRight = input[inputOffset + halfChannels] + bias[biasIdx + halfChannels];
    let geluRight = valueRight * 0.5 * (erf_vf32(valueRight / M_SQRT2) + 1);

    ${r.setByOffset("global_idx","valueLeft * geluRight")}
  }`}},Po=e=>{Do(e.inputs),e.compute(Bo(e.inputs))}}),No,Vo,Mt,Lo,Uo,qo,Wo,Go,jo,Ho,Ko,Zo,Qo,Tp=k(()=>{_e(),$e(),xe(),No=(e,t,i,n,r,s,a,o,l,u,d,c)=>{let p,h;typeof o=="string"?p=h=(g,T)=>`${o}((${g}),(${T}))`:typeof o=="function"?p=h=o:(p=o.scalar,h=o.vector);let m=re("outputData",d,n.length,4),_=B("aData",l,t.length,4),$=B("bData",u,i.length,4),w;if(r)if(s){let g=M.size(t)===1,T=M.size(i)===1,x=t.length>0&&t[t.length-1]%4===0,I=i.length>0&&i[i.length-1]%4===0;g||T?w=m.setByOffset("global_idx",h(g?`${_.type.value}(${_.getByOffset("0")}.x)`:_.getByOffset("global_idx"),T?`${$.type.value}(${$.getByOffset("0")}.x)`:$.getByOffset("global_idx"))):w=`
            let outputIndices = ${m.offsetToIndices("global_idx * 4u")};
            let offsetA = ${_.broadcastedIndicesToOffset("outputIndices",m)};
            let offsetB = ${$.broadcastedIndicesToOffset("outputIndices",m)};
            ${m.setByOffset("global_idx",h(a||x?_.getByOffset("offsetA / 4u"):`${_.type.value}(${_.getByOffset("offsetA / 4u")}[offsetA % 4u])`,a||I?$.getByOffset("offsetB / 4u"):`${$.type.value}(${$.getByOffset("offsetB / 4u")}[offsetB % 4u])`))}
          `}else w=m.setByOffset("global_idx",h(_.getByOffset("global_idx"),$.getByOffset("global_idx")));else{if(!s)throw new Error("no necessary to use scalar implementation for element-wise binary op implementation.");let g=(T,x,I="")=>{let O=`aData[indexA${x}][componentA${x}]`,z=`bData[indexB${x}][componentB${x}]`;return`
            let outputIndices${x} = ${m.offsetToIndices(`global_idx * 4u + ${x}u`)};
            let offsetA${x} = ${_.broadcastedIndicesToOffset(`outputIndices${x}`,m)};
            let offsetB${x} = ${$.broadcastedIndicesToOffset(`outputIndices${x}`,m)};
            let indexA${x} = offsetA${x} / 4u;
            let indexB${x} = offsetB${x} / 4u;
            let componentA${x} = offsetA${x} % 4u;
            let componentB${x} = offsetB${x} % 4u;
            ${T}[${x}] = ${I}(${p(O,z)});
          `};d===9?w=`
            var data = vec4<u32>(0);
            ${g("data",0,"u32")}
            ${g("data",1,"u32")}
            ${g("data",2,"u32")}
            ${g("data",3,"u32")}
            outputData[global_idx] = dot(vec4<u32>(0x1, 0x100, 0x10000, 0x1000000), vec4<u32>(data));`:w=`
            ${g("outputData[global_idx]",0)}
            ${g("outputData[global_idx]",1)}
            ${g("outputData[global_idx]",2)}
            ${g("outputData[global_idx]",3)}
          `}return`
        ${e.registerUniform("vec_size","u32").declareVariables(_,$,m)}

        ${c??""}

        ${e.mainStart()}
        ${e.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.vec_size")}
        ${w}
      }`},Vo=(e,t,i,n,r,s,a=i.dataType)=>{let o=i.dims.map(_=>Number(_)??1),l=n.dims.map(_=>Number(_)??1),u=!M.areEqual(o,l),d=o,c=M.size(o),p=!1,h=!1,m=[u];if(u){let _=fi.calcShape(o,l,!1);if(!_)throw new Error("Can't perform binary op on the given tensors");d=_.slice(),c=M.size(d);let $=M.size(o)===1,w=M.size(l)===1,g=o.length>0&&o[o.length-1]%4===0,T=l.length>0&&l[l.length-1]%4===0;m.push($),m.push(w),m.push(g),m.push(T);let x=1;for(let I=1;I<d.length;I++){let O=o[o.length-I],z=l[l.length-I];if(O===z)x*=O;else break}x%4===0?(h=!0,p=!0):($||w||g||T)&&(p=!0)}else p=!0;return m.push(p),{name:e,shaderCache:{hint:t+m.map(_=>_.toString()).join("_"),inputDependencies:["rank","rank"]},getShaderSource:_=>No(_,o,l,d,p,u,h,r,i.dataType,n.dataType,a,s),getRunData:()=>({outputs:[{dims:d,dataType:a}],dispatchGroup:{x:Math.ceil(c/64/4)},programUniforms:[{type:12,data:Math.ceil(M.size(d)/4)},...le(o,l,d)]})}},Mt=(e,t,i,n,r,s)=>{e.compute(Vo(t,r??"",e.inputs[0],e.inputs[1],i,n,s))},Lo=e=>{Mt(e,"Add",(t,i)=>`${t}+${i}`)},Uo=e=>{Mt(e,"Div",(t,i)=>`${t}/${i}`)},qo=e=>{Mt(e,"Equal",{scalar:(t,i)=>`u32(${t}==${i})`,vector:(t,i)=>`vec4<u32>(${t}==${i})`},void 0,void 0,9)},Wo=e=>{Mt(e,"Mul",(t,i)=>`${t}*${i}`)},Go=e=>{let t=B("input",e.inputs[0].dataType,e.inputs[0].dims).type.value;Mt(e,"Pow",{scalar:(i,n)=>`pow_custom(${i},${n})`,vector:(i,n)=>`pow_vector_custom(${i},${n})`},`
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
      `)},jo=e=>{Mt(e,"Sub",(t,i)=>`${t}-${i}`)},Ho=e=>{Mt(e,"Greater",{scalar:(t,i)=>`u32(${t}>${i})`,vector:(t,i)=>`vec4<u32>(${t}>${i})`},void 0,void 0,9)},Ko=e=>{Mt(e,"Less",{scalar:(t,i)=>`u32(${t}<${i})`,vector:(t,i)=>`vec4<u32>(${t}<${i})`},void 0,void 0,9)},Zo=e=>{Mt(e,"GreaterOrEqual",{scalar:(t,i)=>`u32(${t}>=${i})`,vector:(t,i)=>`vec4<u32>(${t}>=${i})`},void 0,void 0,9)},Qo=e=>{Mt(e,"LessOrEqual",{scalar:(t,i)=>`u32(${t}<=${i})`,vector:(t,i)=>`vec4<u32>(${t}<=${i})`},void 0,void 0,9)}}),Xo,Yo,Jo,el,tl,il,Ep=k(()=>{_e(),$e(),Xe(),xe(),Xo=(e,t)=>{if(!e||e.length<1)throw new Error("too few inputs");let i=0,n=e[i],r=n.dataType,s=n.dims.length;e.forEach((a,o)=>{if(o!==i){if(a.dataType!==r)throw new Error("input tensors should be one type");if(a.dims.length!==s)throw new Error("input tensors should have the same shape");a.dims.forEach((l,u)=>{if(u!==t&&l!==n.dims[u])throw new Error("non concat dimensions must match")})}})},Yo=(e,t)=>`
  fn calculateInputIndex(index: u32) -> u32 {
    let sizeInConcatAxis = array<u32, ${e}u>(${t});
    for (var i: u32 = 0u; i < ${e}; i += 1u ) {
      if (index < sizeInConcatAxis[i]) {
        return i;
      }
    }
    return ${e}u;
  }`,Jo=(e,t)=>{let i=e.length,n=[];for(let r=0;r<i;++r){let s=t.setByOffset("global_idx",e[r].getByIndices("indices"));i===1?n.push(s):r===0?n.push(`if (inputIndex == ${r}u) { ${s} }`):r===i-1?n.push(`else { ${s} }`):n.push(`else if (inputIndex == ${r}) { ${s} }`)}return n.join(`
`)},el=(e,t,i,n)=>{let r=M.size(i),s=new Array(e.length),a=new Array(e.length),o=0,l=[],u=[],d=[{type:12,data:r}];for(let _=0;_<e.length;++_)o+=e[_].dims[t],s[_]=o,u.push(e[_].dims.length),a[_]=B(`input${_}`,n,u[_]),l.push("rank"),d.push({type:12,data:s[_]});for(let _=0;_<e.length;++_)d.push(...le(e[_].dims));d.push(...le(i));let c=re("output",n,i.length),p=c.indicesGet("indices",t),h=Array.from(Array(s.length).keys()).map(_=>`uniforms.sizeInConcatAxis${_}`).join(","),m=_=>`

  ${(()=>{_.registerUniform("outputSize","u32");for(let $=0;$<e.length;$++)_.registerUniform(`sizeInConcatAxis${$}`,"u32");return _.declareVariables(...a,c)})()}

  ${Yo(s.length,h)}

  ${_.mainStart()}
    ${_.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}

    var indices = ${c.offsetToIndices("global_idx")};

    let inputIndex = calculateInputIndex(${p});
    if (inputIndex != 0u) {
      let sizeInConcatAxis = array<u32, ${s.length}u>(${h});
      ${p} -= sizeInConcatAxis[inputIndex - 1u];
    }

    ${Jo(a,c)}
  }`;return{name:"Concat",shaderCache:{hint:`${t}`,inputDependencies:l},getRunData:()=>({outputs:[{dims:i,dataType:n}],dispatchGroup:{x:Math.ceil(r/64)},programUniforms:d}),getShaderSource:m}},tl=(e,t)=>{let i=e.inputs,n=i[0].dims,r=M.normalizeAxis(t.axis,n.length);Xo(i,r);let s=n.slice();s[r]=i.reduce((o,l)=>o+(l.dims.length>r?l.dims[r]:0),0);let a=i.filter(o=>M.size(o.dims)>0);e.compute(el(a,r,s,i[0].dataType),{inputs:a})},il=e=>De({axis:e.axis})}),ti,ii,ni,Xn,ri=k(()=>{_e(),$e(),ti=(e,t,i="f32")=>{switch(e.activation){case"Relu":return`value = max(value, ${t}(0.0));`;case"Sigmoid":return`value = (${t}(1.0) / (${t}(1.0) + exp(-value)));`;case"Clip":return`value = clamp(value, ${t}(${i}(uniforms.clip_min)), ${t}(${i}(uniforms.clip_max)));`;case"HardSigmoid":return`value = max(${t}(0.0), min(${t}(1.0), ${i}(uniforms.alpha) * value + ${i}(uniforms.beta)));`;case"LeakyRelu":return`value = select(${i}(uniforms.alpha) * value, value, value >= ${t}(0.0));`;case"Tanh":return`let e2x = exp(-2.0 * abs(value));
              value = sign(value) * (1.0 - e2x) / (1.0 + e2x);
        `;case"":return"";default:throw new Error(`Unsupported activation ${e.activation}`)}},ii=(e,t)=>{e.activation==="Clip"?t.push({type:1,data:e.clipMax},{type:1,data:e.clipMin}):e.activation==="HardSigmoid"?t.push({type:1,data:e.alpha},{type:1,data:e.beta}):e.activation==="LeakyRelu"&&t.push({type:1,data:e.alpha})},ni=(e,t)=>{e.activation==="Clip"?t.push({name:"clip_max",type:"f32"},{name:"clip_min",type:"f32"}):e.activation==="HardSigmoid"?t.push({name:"alpha",type:"f32"},{name:"beta",type:"f32"}):e.activation==="LeakyRelu"&&t.push({name:"alpha",type:"f32"})},Xn=e=>{let t=e?.activation||"";if(t==="HardSigmoid"){let[i,n]=e?.activation_params||[.2,.5];return{activation:t,alpha:i,beta:n}}else if(t==="Clip"){let[i,n]=e?.activation_params||[Ss,ks];return{activation:t,clipMax:n,clipMin:i}}else if(t==="LeakyRelu"){let[i]=e?.activation_params||[.01];return{activation:t,alpha:i}}return{activation:t}}}),dt,nl,Yn=k(()=>{dt=(e,t)=>{switch(e){case 1:return t;case 2:return`vec2<${t}>`;case 3:return`vec3<${t}>`;case 4:return`vec4<${t}>`;default:throw new Error(`${e}-component is not supported.`)}},nl=e=>`
      ${e?"value = value + getBiasByOutputCoords(coords);":""}
      `}),rl,Cp=k(()=>{rl=e=>`
fn getIndexFromCoords4D(coords : vec4<i32>, shape : vec4<i32>) -> i32 {
  return dot(coords, vec4<i32>(
      shape.y * shape.z * shape.w, shape.z * shape.w, shape.w, 1));
}
fn getOutputIndexFromCoords(coords : vec4<i32>) -> i32 {
  return dot(coords, vec4<i32>(
    i32(${e}.x), i32(${e}.y), i32(${e}.z), 1));
}
`}),Ti,Jn,er=k(()=>{_e(),$e(),xe(),ri(),Ti=(e,t,i,n,r)=>{let s=n-i;return`
      ${Array.from({length:i}).map((a,o)=>`
      if (${se(t.shape,o,t.rank)} != 1) {
        ${t.indicesSet(e,o,se(r,o+s,n))}
      } else {
        ${t.indicesSet(e,o,0)}
      }`).join("")}
`},Jn=(e,t,i,n,r=!1,s)=>{let a=e[0].dims,o=e[1].dims,l=a[a.length-2],u=o[o.length-1],d=a[a.length-1],c=Qe(u),p=Qe(d),h=Qe(l),m=M.size(i)/c/h,_=e.length>2,$=n?n.slice(0,-2):i.slice(0,-2),w=[M.size($),l,u],g=[{type:12,data:m},{type:12,data:l},{type:12,data:u},{type:12,data:d}];ii(t,g),g.push(...le($,a,o)),_&&g.push(...le(e[2].dims)),g.push(...le(w));let T=x=>{let I=Vn("batch_dims",e[0].dataType,$.length),O=B("a",e[0].dataType,a.length,p),z=B("b",e[1].dataType,o.length,c),N=re("output",e[0].dataType,w.length,c),q=at(N.type.tensor),te=ti(t,N.type.value,q),ye=[O,z],de="";if(_){let Te=r?c:1;ye.push(B("bias",e[2].dataType,e[2].dims.length,Te)),de=`${r?`value += bias[col / ${Te}];`:`value += ${N.type.value}(bias[row + i]);`}`}let be=[{name:"output_size",type:"u32"},{name:"M",type:"u32"},{name:"N",type:"u32"},{name:"K",type:"u32"}];ni(t,be);let ne=()=>{let Te=`var a_data: ${O.type.value};`;for(let he=0;he<p;he++)Te+=`
              let b_data${he} = b[(b_offset + (k + ${he}) * uniforms.N + col) / ${c}];`;for(let he=0;he<h;he++){Te+=`a_data = a[(a_offset + (row + ${he}) * uniforms.K + k) / ${p}];`;for(let ae=0;ae<p;ae++)Te+=`
            values[${he}] = fma(${z.type.value}(a_data${p===1?"":`[${ae}]`}), b_data${ae}, values[${he}]);
`}return Te};return`
  ${x.registerUniforms(be).registerInternalVariables(I).declareVariables(...ye,N)}
  ${x.mainStart()}
    ${x.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    let col = (global_idx % (uniforms.N / ${c})) * ${c};
    var index1 = global_idx / (uniforms.N / ${c});
    let stride1 = uniforms.M / ${h};
    let row = (index1 % stride1) * ${h};
    let batch = index1 / stride1;

    ${i.length===2?"":`let batch_indices = ${I.offsetToIndices("batch")};`}

    var a_indices: ${O.type.indices};
    ${Ti("a_indices",O,O.rank-2,I.rank,"batch_indices")}
    ${O.indicesSet("a_indices",O.rank-2,0)}
    ${O.indicesSet("a_indices",O.rank-1,0)}
    let a_offset = ${O.indicesToOffset("a_indices")};

    var b_indices: ${z.type.indices};
    ${Ti("b_indices",z,z.rank-2,I.rank,"batch_indices")}
    ${z.indicesSet("b_indices",z.rank-2,0)}
    ${z.indicesSet("b_indices",z.rank-1,0)}
    let b_offset = ${z.indicesToOffset("b_indices")};
    var values: array<${N.type.value}, ${h}>;
    for (var k: u32 = 0u; k < uniforms.K; k = k + ${p}) {
      ${ne()}
    }
    for (var i = 0u; i < ${h}u; i++) {
      var value = values[i];
      ${de}
      ${te}
      let cur_indices = ${N.type.indices}(batch, row + i, col);
      let offset = ${N.indicesToOffset("cur_indices")};
      ${N.setByOffset(`offset / ${c}`,"value")};
    }
  }
  `};return{name:"MatMulNaive",shaderCache:{hint:`${t.activation};${c};${p};${h};${r}`,inputDependencies:_?["rank","rank","rank"]:["rank","rank"]},getRunData:()=>({outputs:[{dims:s?s(i):i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(m/64)},programUniforms:g}),getShaderSource:T}}}),sl,al,tr,ir,ol,nr,ll,Xi,rr=k(()=>{_e(),$e(),xe(),ri(),er(),Yn(),sl=(e,t)=>e?`
        mm_Asub[inputRow][inputCol] = mm_readA(batch,
          kStart + inputRow,
          globalRowStart / innerElementSize + inputCol${t?", batchIndices":""});
        `:`
        mm_Asub[inputRow][inputCol] = mm_readA(batch,
          globalRow + innerRow,
          kStart / innerElementSize + inputCol${t?", batchIndices":""});
        `,al=(e,t)=>e?`
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
        }`,tr=(e,t,i="f32",n,r=!1,s=32,a=!1,o=32)=>{let l=t[1]*e[1],u=t[0]*e[0],d=r?l:s,c=r?s:l,p=d/t[0],h=s/t[1];if(!((r&&p===4&&e[1]===4||!r&&(p===3||p===4))&&d%t[0]===0&&s%t[1]===0&&e[0]===4))throw new Error(`If transposeA ${r} is true, innerElementSize ${p} and workPerThread[1] ${e[1]} must be 4.
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
          ${sl(r,n)}
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

          ${al(r,p)}
      }

      workgroupBarrier();
  }

  for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
      mm_write(batch, globalRow + innerRow, globalCol, acc[innerRow]);
  }
}`},ir=(e,t)=>e?`
            mm_Asub[inputRow][inputCol] = mm_readA(batch,
              kStart + inputRow,
              globalRowStart + inputCol${t?", batchIndices":""});
            `:`
            mm_Asub[inputRow][inputCol] = mm_readA(batch,
              globalRowStart + inputRow,
              kStart + inputCol${t?", batchIndices":""});
            `,ol=e=>e?"let ACached = mm_Asub[k][tileRow + innerRow];":"let ACached = mm_Asub[tileRow + innerRow][k];",nr=(e,t,i="f32",n,r=!1,s=32,a=!1,o=32,l=!1)=>{let u=e[1]*t[1],d=e[0]*t[0],c=r?u:s,p=r?s:u;if(!(p%t[1]===0&&c%t[0]===0&&s%t[1]===0))throw new Error(`tileAHight ${p} must be divisible by workgroupSize[1]${t[1]}, tileAWidth ${c} must be divisible by workgroupSize[0]${t[0]}, tileInner ${s} must be divisible by workgroupSize[1]${t[1]}`);let h=p/t[1],m=c/t[0],_=s/t[1],$=l?`
    let localRow = i32(localId.y);
    let localCol = i32(localId.x);
    let globalRowStart = i32(workgroupId.y) * ${u};
    let globalColStart = i32(workgroupId.x) * ${d};

    // Loop over shared dimension.
    for (var t = 0; t < num_tiles; t = t + 1) {
      // Load one tile of A into local memory.
      for (var inputRow = localRow; inputRow < ${p}; inputRow = inputRow + ${t[1]}) {
        for (var inputCol = localCol; inputCol < ${c}; inputCol = inputCol + ${t[0]}) {
          ${ir(r,n)}
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
      ${ir(r,n)}
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
      ${ol(r)}
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
`},ll=(e,t,i,n,r=!1)=>{let[s,a,o,l]=n,u=at(n[0].type.tensor);return`
    fn mm_readA(batch: i32, row: i32, colIn: i32, batchIndices: ${s.type.indices}) -> ${dt(e,u)} {
      var value = ${dt(e,u)}(0.0);
      let col = colIn * ${e};
      if(row < uniforms.dim_a_outer && col < uniforms.dim_inner)
      {
        var aIndices: ${a.type.indices};
        ${Ti("aIndices",a,a.rank-2,s.rank,"batchIndices")}
        ${a.indicesSet("aIndices",a.rank-2,"u32(row)")}
        ${a.indicesSet("aIndices",a.rank-1,"u32(colIn)")}
        value = ${a.getByIndices("aIndices")};
      }
      return value;
    }

    fn mm_readB(batch: i32, row: i32, colIn: i32, batchIndices: ${s.type.indices}) -> ${dt(e,u)} {
      var value = ${dt(e,u)}(0.0);
      let col = colIn * ${e};
      if(row < uniforms.dim_inner && col < uniforms.dim_b_outer)
      {
        var bIndices: ${o.type.indices};
        ${Ti("bIndices",o,o.rank-2,s.rank,"batchIndices")}
        ${o.indicesSet("bIndices",o.rank-2,"u32(row)")}
        ${o.indicesSet("bIndices",o.rank-1,"u32(colIn)")}
        value = ${o.getByIndices("bIndices")};
      }
      return value;
    }

    fn mm_write(batch: i32, row: i32, colIn: i32, valueIn: ${dt(e,u)}) {
      let col = colIn * ${e};
      if (row < uniforms.dim_a_outer && col < uniforms.dim_b_outer) {
        var value = valueIn;
        let coords = vec3<i32>(batch, row, colIn);
        ${t?`value = value + ${r?"bias[colIn]":`${dt(e,u)}(bias[row])`};`:""}
        ${i}
        ${l.setByIndices("vec3<u32>(coords)","value")}
      }
    }
    `},Xi=(e,t,i,n,r=!1,s)=>{let a=e[0].dims,o=e[1].dims,l=a.slice(0,-2),u=o.slice(0,-2),d=n?n.slice(0,-2):i.slice(0,-2),c=M.size(d),p=a[a.length-2],h=a[a.length-1],m=o[o.length-1],_=h%4===0&&m%4===0,$=p<=8?[4,1,1]:[4,4,1],w=[8,8,1],g=[Math.ceil(m/w[0]/$[0]),Math.ceil(p/w[1]/$[1]),Math.ceil(c/w[2]/$[2])],T=_?4:1,x=[...l,p,h/T],I=x.length,O=[...u,h,m/T],z=O.length,N=[c,p,m/T],q=[{type:6,data:p},{type:6,data:m},{type:6,data:h}];ii(t,q),q.push(...le(d,x,O));let te=["rank","rank"],ye=e.length>2;ye&&(q.push(...le(e[2].dims)),te.push("rank")),q.push(...le(N));let de=be=>{let ne=d.length,Te=Vn("batchDims",e[0].dataType,ne,1),he=at(e[0].dataType),ae=B("a",e[0].dataType,I,T),Oe=B("b",e[1].dataType,z,T),ce=re("result",e[0].dataType,N.length,T),Ge=[ae,Oe];if(ye){let ct=r?T:1;Ge.push(B("bias",e[2].dataType,e[2].dims.length,ct))}let W=[{name:"dim_a_outer",type:"i32"},{name:"dim_b_outer",type:"i32"},{name:"dim_inner",type:"i32"}];ni(t,W);let ee=at(ce.type.tensor),Se=ti(t,ce.type.value,ee),Le=ll(T,ye,Se,[Te,ae,Oe,ce],r);return`
  ${be.registerUniforms(W).registerInternalVariables(Te).declareVariables(...Ge,ce)}
  ${Le}
  ${_?tr($,w,he,Te):nr($,w,he,Te)}
                   `};return{name:"MatMul",shaderCache:{hint:`${$};${t.activation};${_};${r}`,inputDependencies:te},getRunData:()=>({outputs:[{dims:s?s(i):i,dataType:e[0].dataType}],dispatchGroup:{x:g[0],y:g[1],z:g[2]},programUniforms:q}),getShaderSource:de}}}),ul,dl,Ip=k(()=>{_e(),Wt(),xe(),ri(),Yn(),Cp(),rr(),ul=(e,t,i,n,r=!1,s,a=4,o=4,l=4,u="f32")=>{let d=q=>{switch(q){case 1:return"resData = x[xIndex];";case 3:return`resData = vec3<${u}>(x[xIndex], x[xIndex + 1], x[xIndex + 2]);`;case 4:return"resData = x[xIndex / 4];";default:throw new Error(`innerElementSize ${q} is not supported.`)}},c=q=>{switch(q){case 1:return"return w[row * i32(uniforms.w_shape[3]) + colIn];";case 4:return"return w[row * i32(uniforms.w_shape[3]) / 4 + colIn];";default:throw new Error(`innerElementSize ${q} is not supported.`)}},p=e?`
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
    `,m=e?"i32(uniforms.x_shape[1])":"i32(uniforms.x_shape[2])",_=e?"i32(uniforms.x_shape[2])":"i32(uniforms.x_shape[3])",$=e?"row":"col",w=e?"col":"row",g=`
    let inChannels = i32(uniforms.w_shape[2]);
    let outWidth = ${e?"i32(uniforms.result_shape[2])":"i32(uniforms.result_shape[3])"};
    let outRow = ${$} / outWidth;
    let outCol = ${$} % outWidth;

    let WRow = ${w} / (i32(uniforms.w_shape[1]) * inChannels);
    let WCol = ${w} / inChannels % i32(uniforms.w_shape[1]);
    let xRow = outRow * uniforms.stride[0] + uniforms.dilation[0] * WRow - uniforms.pad[0];
    let xCol = outCol * uniforms.stride[1] + uniforms.dilation[1] * WCol - uniforms.pad[1];
    let xCh = ${w} % inChannels;
    var resData = ${dt(a,u)}(0.0);
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
    return ${dt(a,u)}(0.0);`:n&&i?`
    let col = colIn * ${a};
    ${g}`:`
    let col = colIn * ${a};
    if (row < uniforms.dim_inner && col < uniforms.dim_b_outer) {
      ${g}
    }
    return ${dt(a,u)}(0.0);`,x=e?n&&i?c(o):`
    let col = colIn * ${o};
    if (row < uniforms.dim_inner && col < uniforms.dim_b_outer) {
      ${c(o)}
    }
    return ${dt(o,u)}(0.0);`:`
    let col = colIn * ${o};
    if (row < uniforms.dim_inner && col < uniforms.dim_a_outer) {
      ${c(o)}
    }
    return ${dt(o,u)}(0.0);`,I=dt(l,u),O=dt(e?a:o,u),z=dt(e?o:a,u),N=ti(s,I,u);return`
    fn mm_readA(batch: i32, row : i32, colIn : i32) -> ${O} {
      ${e?T:x}
    }

    fn mm_readB(batch: i32, row : i32, colIn : i32) -> ${z} {
      ${e?x:T}
    }

    fn mm_write(batch: i32, row : i32, colIn : i32, valueIn : ${I}) {
      let col = colIn * ${l};
      if (row < uniforms.dim_a_outer && col < uniforms.dim_b_outer)
      {
      var value = valueIn;
      let outWidth = ${e?"i32(uniforms.result_shape[2])":"i32(uniforms.result_shape[3])"};
      ${h}
      ${nl(r)}
      ${N}
      setOutputAtCoords(coords[0], coords[1], coords[2], coords[3], value);
      }
    }`},dl=(e,t,i,n,r,s,a,o,l)=>{let u=t.format==="NHWC",d=u?e[0].dims[3]:e[0].dims[1],c=i[0],p=u?i[2]:i[3],h=u?i[1]:i[2],m=u?i[3]:i[1],_=u&&(d%4===0||d%3===0)&&m%4===0,$=u?m:p*h,w=u?p*h:m,g=[8,8,1],T=n<=8?[4,1,1]:[4,4,1],x=[Math.ceil($/g[0]/T[0]),Math.ceil(w/g[1]/T[1]),Math.ceil(c/g[2]/T[2])];Ie("verbose",()=>`[conv2d_mm_webgpu] dispatch = ${x}`);let I=_?u&&d%4!==0?3:4:1,O=g[1]*T[1],z=g[0]*T[0],N=Math.max(g[0]*I,g[1]),q=n%O===0,te=r%z===0,ye=s%N===0,de=_?[I,4,4]:[1,1,1],be=[{type:6,data:n},{type:6,data:r},{type:6,data:s},{type:6,data:[t.pads[0],t.pads[1]]},{type:6,data:t.strides},{type:6,data:t.dilations}];ii(t,be),be.push(...le(e[0].dims,e[1].dims));let ne=["rank","rank"];a&&(be.push(...le(e[2].dims)),ne.push("rank")),be.push(...le(i));let Te=he=>{let ae=[{name:"dim_a_outer",type:"i32"},{name:"dim_b_outer",type:"i32"},{name:"dim_inner",type:"i32"},{name:"pad",type:"i32",length:2},{name:"stride",type:"i32",length:2},{name:"dilation",type:"i32",length:2}];ni(t,ae);let Oe=_?4:1,ce=at(e[0].dataType),Ge=`
      fn setOutputAtIndex(flatIndex : i32, value : ${_?`vec4<${ce}>`:ce}) {
        result[flatIndex] = ${_?`vec4<${ce}>`:ce}(value);
      }
      fn setOutputAtCoords(d0 : i32, d1 : i32, d2 : i32, d3 : i32, value : ${_?`vec4<${ce}>`:ce}) {
        let flatIndex = getOutputIndexFromCoords(vec4<i32>(d0, d1, d2, d3));
        setOutputAtIndex(flatIndex ${_?"/ 4":""}, value);
      }`,W=B("x",e[0].dataType,e[0].dims.length,I===3?1:I),ee=B("w",e[1].dataType,e[1].dims.length,Oe),Se=[W,ee],Le=re("result",e[0].dataType,i.length,Oe);if(a){let ct=B("bias",e[2].dataType,e[2].dims.length,Oe);Se.push(ct),Ge+=`
        fn getBiasByOutputCoords(coords : vec4<i32>) -> ${_?`vec4<${ce}>`:ce} {
          return bias[coords.${u?"w":"y"}${_?"/ 4":""}];
        }`}return`
        ${rl("uniforms.result_strides")}
        //struct Uniforms { xShape : vec4<i32>, wShape : vec4<i32>, outShape : vec4<i32>,
        //  outShapeStrides: vec3<i32>, filterDims : vec2<i32>, pad : vec2<i32>, stride : vec2<i32>,
        //  dilation : vec2<i32>, dimAOuter : i32, dimBOuter : i32, dimInner : i32 };
        ${he.registerUniforms(ae).declareVariables(...Se,Le)}
        ${Ge}
        ${ul(u,q,te,ye,a,t,de[0],de[1],de[2],ce)}
        ${_?tr(T,g,ce,void 0,!u,N):nr(T,g,ce,void 0,!u,N,!1,void 0,o)}`};return{name:"Conv2DMatMul",shaderCache:{hint:`${t.cacheKey};${I};${_};${q};${te};${ye};${O};${z};${N}`,inputDependencies:ne},getRunData:()=>({outputs:[{dims:l?l(i):i,dataType:e[0].dataType}],dispatchGroup:{x:x[0],y:x[1],z:x[2]},programUniforms:be}),getShaderSource:Te}}}),cl,sr,Ei,pl,ar,fl,hl,ml,Ap=k(()=>{_e(),Wt(),$e(),xe(),ri(),Yn(),cl=e=>{let t=1;for(let i=0;i<e.length;i++)t*=e[i];return t},sr=e=>typeof e=="number"?[e,e,e]:e,Ei=(e,t)=>t<=1?e:e+(e-1)*(t-1),pl=(e,t,i,n=1)=>{let r=Ei(t,n);return Math.floor((e[0]*(i-1)-i+r)/2)},ar=(e,t,i,n,r)=>{r==null&&(r=pl(e,t[0],n[0]));let s=[0,0,0,i];for(let a=0;a<3;a++)e[a]+2*r>=t[a]&&(s[a]=Math.trunc((e[a]-t[a]+2*r)/n[a]+1));return s},fl=(e,t,i,n,r,s,a,o,l,u)=>{let d,c,p,h;if(e==="VALID"&&(e=0),typeof e=="number"){d={top:e,bottom:e,left:e,right:e,front:e,back:e};let m=ar([t,i,n,1],[o,l,u],1,[r,s,a],e);c=m[0],p=m[1],h=m[2]}else if(Array.isArray(e)){if(!e.every((_,$,w)=>_===w[0]))throw Error(`Unsupported padding parameter: ${e}`);d={top:e[0],bottom:e[1],left:e[2],right:e[3],front:e[4],back:e[5]};let m=ar([t,i,n,1],[o,l,u],1,[r,s,a],e[0]);c=m[0],p=m[1],h=m[2]}else if(e==="SAME_UPPER"){c=Math.ceil(t/r),p=Math.ceil(i/s),h=Math.ceil(n/a);let m=(c-1)*r+o-t,_=(p-1)*s+l-i,$=(h-1)*a+u-n,w=Math.floor(m/2),g=m-w,T=Math.floor(_/2),x=_-T,I=Math.floor($/2),O=$-I;d={top:T,bottom:x,left:I,right:O,front:w,back:g}}else throw Error(`Unknown padding parameter: ${e}`);return{padInfo:d,outDepth:c,outHeight:p,outWidth:h}},hl=(e,t,i,n,r,s=!1,a="channelsLast")=>{let o,l,u,d,c;if(a==="channelsLast")[o,l,u,d,c]=e;else if(a==="channelsFirst")[o,c,l,u,d]=e;else throw new Error(`Unknown dataFormat ${a}`);let[p,,h,m,_]=t,[$,w,g]=sr(i),[T,x,I]=sr(n),O=Ei(h,T),z=Ei(m,x),N=Ei(_,I),{padInfo:q,outDepth:te,outHeight:ye,outWidth:de}=fl(r,l,u,d,$,w,g,O,z,N),be=s?p*c:p,ne=[0,0,0,0,0];return a==="channelsFirst"?ne=[o,be,te,ye,de]:a==="channelsLast"&&(ne=[o,te,ye,de,be]),{batchSize:o,dataFormat:a,inDepth:l,inHeight:u,inWidth:d,inChannels:c,outDepth:te,outHeight:ye,outWidth:de,outChannels:be,padInfo:q,strideDepth:$,strideHeight:w,strideWidth:g,filterDepth:h,filterHeight:m,filterWidth:_,effectiveFilterDepth:O,effectiveFilterHeight:z,effectiveFilterWidth:N,dilationDepth:T,dilationHeight:x,dilationWidth:I,inShape:e,outShape:ne,filterShape:t}},ml=(e,t,i,n,r,s)=>{let a=s==="channelsLast";a?e[0].dims[3]:e[0].dims[1];let o=[64,1,1],l={x:i.map(($,w)=>w)},u=[Math.ceil(cl(l.x.map($=>i[$]))/o[0]),1,1];Ie("verbose",()=>`[conv3d_naive_webgpu] dispatch = ${u}`);let d=1,c=M.size(i),p=[{type:12,data:c},{type:12,data:n},{type:12,data:r},{type:12,data:t.strides},{type:12,data:t.dilations}];ii(t,p),p.push(...le(e[0].dims,e[1].dims));let h=["rank","rank"],m=e.length===3;m&&(p.push(...le(e[2].dims)),h.push("rank")),p.push(...le(i));let _=$=>{let w=[{name:"output_size",type:"u32"},{name:"filter_dims",type:"u32",length:n.length},{name:"pads",type:"u32",length:r.length},{name:"strides",type:"u32",length:t.strides.length},{name:"dilations",type:"u32",length:t.dilations.length}];ni(t,w);let g=1,T=at(e[0].dataType),x=B("x",e[0].dataType,e[0].dims.length,d),I=B("W",e[1].dataType,e[1].dims.length,g),O=[x,I],z=re("result",e[0].dataType,i.length,g),N="";if(m){let ye=B("bias",e[2].dataType,e[2].dims.length,g);O.push(ye),N+=`
        fn getBiasByOutputCoords(coords : array<u32, 5>) -> ${T} {
          return bias[${a?se("coords",4,5):se("coords",1,5)}];
        }`}let q=dt(d,T),te=ti(t,q,T);return`
            ${N}
            fn getX(d0 : u32, d1 : u32, d2 : u32, d3 : u32, d4 : u32) -> f32 {
              let aIndices = array<u32, 5>(d0, d1, d2, d3, d4);
              return ${x.getByIndices("aIndices")};
            }
            fn getW(d0 : u32, d1 : u32, d2 : u32, d3 : u32, d4 : u32) -> f32 {
              let aIndices = array<u32, 5>(d0, d1, d2, d3, d4);
              return ${I.getByIndices("aIndices")};
            }
          ${$.registerUniforms(w).declareVariables(...O,z)}
          ${$.mainStart()}
          ${$.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
              let coords = ${z.offsetToIndices("global_idx")};
              let batch = ${se("coords",0,x.rank)};
              let d2 = ${a?se("coords",x.rank-1,x.rank):se("coords",1,x.rank)};
              let xFRCCorner = vec3<u32>(${a?se("coords",1,x.rank):se("coords",2,x.rank)},
              ${a?se("coords",2,x.rank):se("coords",3,x.rank)},
              ${a?se("coords",3,x.rank):se("coords",4,x.rank)}) * uniforms.strides - uniforms.pads;
              let xFCorner = xFRCCorner.x;
              let xRCorner = xFRCCorner.y;
              let xCCorner = xFRCCorner.z;
              let xShapeY = ${a?se("uniforms.x_shape",1,x.rank):se("uniforms.x_shape",2,x.rank)};
              let xShapeZ = ${a?se("uniforms.x_shape",2,x.rank):se("uniforms.x_shape",3,x.rank)};
              let xShapeW = ${a?se("uniforms.x_shape",3,x.rank):se("uniforms.x_shape",4,x.rank)};
              let xShapeU = ${a?se("uniforms.x_shape",4,x.rank):se("uniforms.x_shape",1,x.rank)};
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
              ${te}
              result[global_idx] = f32(value);
          }`};return{name:"Conv3DNaive",shaderCache:{hint:`${t.cacheKey};${a};${d};${m}`,inputDependencies:h},getRunData:()=>({outputs:[{dims:i,dataType:e[0].dataType}],dispatchGroup:{x:u[0],y:u[1],z:u[2]},programUniforms:p}),getShaderSource:_}}}),gl,_l,zp=k(()=>{_e(),$e(),xe(),ri(),gl=(e,t,i,n)=>{let r=e.length>2,s=r?"value += b[output_channel];":"",a=e[0].dims,o=e[1].dims,l=t.format==="NHWC",u=l?i[3]:i[1],d=u/t.group,c=l&&d>=4?Qe(u):1,p=M.size(i)/c,h=[{type:12,data:p},{type:12,data:t.dilations},{type:12,data:[t.strides[0],t.strides[1]]},{type:12,data:[t.pads[0],t.pads[1]]},{type:12,data:d}];ii(t,h),h.push(...le(a,[o[0],o[1],o[2],o[3]/c]));let m=r?["rank","rank","rank"]:["rank","rank"];h.push(...le([i[0],i[1],i[2],i[3]/c]));let _=$=>{let w=re("output",e[0].dataType,i.length,c),g=at(w.type.tensor),T=ti(t,w.type.value,g),x=B("x",e[0].dataType,a.length),I=B("w",e[1].dataType,o.length,c),O=[x,I];r&&O.push(B("b",e[2].dataType,e[2].dims,c));let z=[{name:"output_size",type:"u32"},{name:"dilations",type:"u32",length:t.dilations.length},{name:"strides",type:"u32",length:2},{name:"pads",type:"u32",length:2},{name:"output_channels_per_group",type:"u32"}];ni(t,z);let N=l?`
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
            let wVal = ${I.get("wHeight","wWidth","wInChannel","output_channel")};
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
            let wVal = ${I.get("output_channel","wInChannel","wHeight","wWidth")};
            value += xVal * wVal;
          }
        }
      }
      `;return`
  ${$.registerUniforms(z).declareVariables(...O,w)}

  ${$.mainStart()}
    ${$.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let outputIndices = ${w.offsetToIndices("global_idx")};
    let batch: u32 = outputIndices[0];
    let output_channel: u32 = outputIndices[${l?3:1}];
    let xRCCorner: vec2<u32> = vec2<u32>(outputIndices[${l?1:2}], outputIndices[${l?2:3}]) * uniforms.strides - uniforms.pads;
    let group_id: u32 = output_channel * ${c} / uniforms.output_channels_per_group;
    var in_channel_offset = group_id * uniforms.w_shape[${l?2:1}];

    var value: ${w.type.value} = ${w.type.value}(0);
    ${N}
    ${s}
    ${T}
    ${w.setByOffset("global_idx","value")}
  }`};return{name:"GroupedConv",shaderCache:{hint:`${t.cacheKey}_${c}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:n?n(i):i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:h}),getShaderSource:_}},_l=(e,t,i,n)=>{let r=e.length>2,s=Qe(i[3]),a=Qe(i[2]),o=M.size(i)/s/a,l=[e[0].dims[0],e[0].dims[1],e[0].dims[2],e[0].dims[3]/s],u=[e[1].dims[0],e[1].dims[1],e[1].dims[2],e[1].dims[3]/s],d=[i[0],i[1],i[2],i[3]/s],c=[{type:12,data:o},{type:6,data:[t.strides[0],t.strides[1]]},{type:6,data:[t.pads[0],t.pads[1]]}];ii(t,c),c.push(...le(l,u,d));let p=(a-1)*t.strides[1]+u[1],h=m=>{let _=re("output",e[0].dataType,d.length,s),$=at(_.type.tensor),w=ti(t,_.type.value,$),g=B("x",e[0].dataType,l.length,s),T=B("w",e[1].dataType,u.length,s),x=[g,T];r&&x.push(B("b",e[2].dataType,e[2].dims,s));let I=r?"value += b[output_channel];":"",O=[{name:"output_size",type:"u32"},{name:"strides",type:"i32",length:2},{name:"pads",type:"i32",length:2}];return ni(t,O),`
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
      ${I}
      ${w}
      ${_.set("batch","row","col + i","output_channel","value")};
    }
  }`};return{name:"GroupedConv-Vectorize",shaderCache:{hint:`${t.cacheKey};${s};${a};${p};${u[0]};${u[1]}`,inputDependencies:r?["rank","rank","type"]:["rank","rank"]},getRunData:()=>({outputs:[{dims:n?n(i):i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(o/64)},programUniforms:c}),getShaderSource:h}}}),yl,Yi,wl,Ji,or,lr,bl,vl,ur,Rp=k(()=>{$e(),Ip(),Ap(),rr(),zp(),ri(),er(),Kt(),yl=(e,t,i,n,r,s)=>{let a=e[0],o=e.slice(s?1:2,s?3:4),l=o.length,u=t[0],d=t.slice(2).map((p,h)=>p+(p-1)*(i[h]-1)),c=o.map((p,h)=>p+n[h]+n[h+l]).map((p,h)=>Math.floor((p-d[h]+r[h])/r[h]));return c.splice(0,0,a),c.splice(s?3:1,0,u),c},Yi=[2,3,1,0],wl=(e,t)=>{if(!e||e.length!==2&&e.length!==3)throw new Error("Conv requires 2 or 3 inputs");if(e[0].dims.length>5)throw new Error("greater than 5D is not supported");if(e[0].dims.length!==e[1].dims.length)throw new Error("filter does not have same dimension as input");let i=e[0].dims[t.format==="NHWC"?e[0].dims.length-1:1],n=e[1].dims[1]*t.group;if(i!==n)throw new Error("FILTER_IN_CHANNEL should be equal to DATA_CHANNEL");if(e.length===3&&(e[2].dims.length!==1||e[1].dims[0]!==e[2].dims[0]))throw new Error("invalid bias");let r=e[0].dims.length-2;if(t.dilations.length!==r)throw new Error(`dilations should be ${r}D`);if(t.strides.length!==r)throw new Error(`strides should be ${r}D`);if(t.pads.length!==r*2)throw new Error(`pads should be ${r*2}D`);if(t.kernelShape.length!==0&&t.kernelShape.length!==e[1].dims.length-2)throw new Error("invalid kernel shape")},Ji=(e,t)=>{let i=e.kernelShape.slice();i.length<t[1].dims.length-2&&i.push(...Array(t[1].dims.length-2-i.length).fill(0));for(let s=2;s<t[1].dims.length;++s)i[s-2]===0&&(i[s-2]=t[1].dims[s]);let n=e.pads.slice();Wi.adjustPadsBasedOnAutoPad(t[0].dims,e.strides,e.dilations,i,n,e.format==="NHWC",e.autoPad);let r=Object.assign({},e);return Object.assign(r,{kernelShape:i,pads:n}),r},or=e=>{let t=Xn(e),i=e.format,n=["NOTSET","VALID","SAME_UPPER","SAME_LOWER"][e.auto_pad],r=e.dilations,s=e.group,a=e.kernel_shape,o=e.pads,l=e.strides,u=e.w_is_const();return{autoPad:n,format:i,dilations:r,group:s,kernelShape:a,pads:o,strides:l,wIsConst:u,...t,cacheKey:`${e.format};${t.activation};`}},lr=(e,t,i,n)=>{let r=i.format==="NHWC",s=yl(t[0].dims,t[1].dims,i.dilations,i.pads,i.strides,r);if(i.group!==1){let O=[t[0]];if(r){let z=e.kernelCustomData.wT??e.compute(xt(t[1],Yi),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=z),O.push(z)}else O.push(t[1]);t.length===3&&O.push(t[2]),!e.adapterInfo.isArchitecture("ampere")&&r&&t[1].dims[0]===i.group&&t[1].dims[1]===1&&i.dilations[0]===1&&i.dilations[1]===1?e.compute(_l(O,i,s,n),{inputs:O}):e.compute(gl(O,i,s,n),{inputs:O});return}let a=t.length===3,o=t[0].dims[r?1:2],l=t[0].dims[r?2:3],u=t[0].dims[r?3:1],d=t[1].dims[2],c=t[1].dims[3],p=s[r?1:2],h=s[r?2:3],m=s[r?3:1],_=r&&d===o&&c===l&&i.pads[0]===0&&i.pads[1]===0;if(_||d===1&&c===1&&i.dilations[0]===1&&i.dilations[1]===1&&i.strides[0]===1&&i.strides[1]===1&&i.pads[0]===0&&i.pads[1]===0){let O=s[0],z,N,q,te=[];if(r){let be=e.kernelCustomData.wT??e.compute(xt(t[1],Yi),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];if(i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=be),_){let ne=o*l*u;z=t[0].reshape([1,O,ne]),N=be.reshape([1,ne,m]),q=[1,O,m]}else z=t[0].reshape([O,o*l,u]),N=be.reshape([1,u,m]),q=[O,p*h,m];te.push(z),te.push(N)}else z=t[0].reshape([O,u,o*l]),N=t[1].reshape([1,m,u]),q=[O,m,p*h],te.push(N),te.push(z);a&&te.push(t[2]);let ye=q[2],de=te[0].dims[te[0].dims.length-1];ye<8&&de<8?e.compute(Jn(te,i,s,q,r,n),{inputs:te}):e.compute(Xi(te,i,s,q,r,n),{inputs:te});return}let $=!0,w=e.kernelCustomData.wT??e.compute(xt(t[1],Yi),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=w);let g=[t[0],w];a&&g.push(t[2]);let T=r?p*h:m,x=r?m:p*h,I=d*c*u;e.compute(dl(g,i,s,T,x,I,a,$,n),{inputs:g})},bl=(e,t)=>{let i=t.format==="NHWC",n=[e.inputs[0].reshape(i?[e.inputs[0].dims[0],1,e.inputs[0].dims[1],e.inputs[0].dims[2]]:[e.inputs[0].dims[0],e.inputs[0].dims[1],1,e.inputs[0].dims[2]]),e.inputs[1].reshape([e.inputs[1].dims[0],e.inputs[1].dims[1],1,e.inputs[1].dims[2]])];e.inputs.length===3&&n.push(e.inputs[2]);let r=[0,t.pads[0],0,t.pads[1]],s=[1].concat(t.strides),a=[1].concat(t.dilations),o=[1].concat(t.kernelShape),l=Ji({...t,pads:r,strides:s,dilations:a,kernelShape:o},n);lr(e,n,l,u=>i?[u[0],u[2],u[3]]:[u[0],u[1],u[3]])},vl=(e,t,i)=>{let n=i.format==="NHWC"?"channelsLast":"channelsFirst",r=Ji(i,t),s=i.autoPad==="NOTSET"?i.pads:i.autoPad,a=hl(t[0].dims,t[1].dims,i.strides,i.dilations,s,!1,n);e.compute(ml(t,r,a.outShape,[a.filterDepth,a.filterHeight,a.filterWidth],[a.padInfo.front,a.padInfo.top,a.padInfo.left],n))},ur=(e,t)=>{if(wl(e.inputs,t),e.inputs[0].dims.length===3)bl(e,t);else if(e.inputs[0].dims.length===5)vl(e,e.inputs,t);else{let i=Ji(t,e.inputs);lr(e,e.inputs,i)}}}),$l,Op=k(()=>{_e(),Wt(),$e(),xe(),$l=(e,t,i)=>{let n=e.length>2,r=t.outputShape,s=t.format==="NHWC",a=t.group,o=e[1].dims,l=o[2]/a,u=o[3],d=s?Qe(l):1,c=s&&u===1&&l>=4,p=c?Math.floor(l/4)*4:Math.floor(l/d)*d,h=l-p,m=s?Qe(u):1,_=s?u===1?d:m:1,$=M.size(r)/m,w=[Math.ceil($/64),1,1];Ie("verbose",()=>`[conv2d_backprop_webgpu] dispatch = ${w}`);let g=["rank","rank"],T=[t.strides[0],t.strides[1]],x=[t.kernelShape[s?1:2],t.kernelShape[s?2:3]],I=[t.dilations[0],t.dilations[1]],O=[x[0]+(t.dilations[0]<=1?0:(t.kernelShape[s?1:2]-1)*(t.dilations[0]-1)),x[1]+(t.dilations[1]<=1?0:(t.kernelShape[s?2:3]-1)*(t.dilations[1]-1))],z=[O[0]-1-Math.floor((t.pads[0]+t.pads[2])/2),O[1]-1-Math.floor((t.pads[1]+t.pads[3])/2)],N=[{type:12,data:$},{type:12,data:T},{type:12,data:x},{type:12,data:I},{type:12,data:O},{type:6,data:z},{type:12,data:p},{type:12,data:l},{type:12,data:u},...le(e[0].dims,e[1].dims)];n&&(N.push(...le(e[2].dims)),g.push("rank")),N.push(...le(r));let q=te=>{let ye=[{name:"output_size",type:"u32"},{name:"strides",type:"u32",length:T.length},{name:"filter_dims",type:"u32",length:x.length},{name:"dilations",type:"u32",length:x.length},{name:"effective_filter_dims",type:"u32",length:O.length},{name:"pads",type:"i32",length:z.length},{name:"input_channels_per_group_int",type:"u32"},{name:"input_channels_per_group",type:"u32"},{name:"output_channels_per_group",type:"u32"}],de=at(e[0].dataType),be=s?1:2,ne=s?2:3,Te=s?3:1,he=B("W",e[1].dataType,e[1].dims.length,_),ae=B("Dy",e[0].dataType,e[0].dims.length,d),Oe=[ae,he];n&&Oe.push(B("bias",e[2].dataType,[r[Te]].length,m));let ce=re("result",e[0].dataType,r.length,m),Ge=()=>{let Se="";if(c)d===4?Se+=`
        let xValue = ${ae.getByOffset("x_offset")};
        let wValue = ${he.getByOffset("w_offset")};
        dotProd = dotProd + dot(xValue, wValue);
        x_offset += 1u;
        w_offset += 1u;`:d===2?Se+=`
          dotProd = dotProd + dot(vec4<${de}>(${ae.getByOffset("x_offset")}, ${ae.getByOffset("x_offset + 1u")}), vec4<${de}>(${he.getByOffset("w_offset")}, ${he.getByOffset("w_offset + 1u")}));
          x_offset += 2u;
          w_offset += 2u;`:d===1&&(Se+=`
          dotProd = dotProd + dot(vec4<${de}>(${ae.getByOffset("x_offset")}, ${ae.getByOffset("x_offset + 1u")}, ${ae.getByOffset("x_offset + 2u")}, ${ae.getByOffset("x_offset + 3u")}), vec4<${de}>(${he.getByOffset("w_offset")}, ${he.getByOffset("w_offset + 1u")}, ${he.getByOffset("w_offset + 2u")}, ${he.getByOffset("w_offset + 3u")}));
          x_offset += 4u;
          w_offset += 4u;`);else if(Se+=`
                  let xValue = ${s?ae.getByOffset(`${ae.indicesToOffset(`${ae.type.indices}(batch, idyR, idyC, inputChannel)`)} / ${d}`):ae.get("batch","inputChannel","idyR","idyC")};
        `,d===1)Se+=`
          let w_offset = ${he.indicesToOffset(`${he.type.indices}(u32(wRPerm), u32(wCPerm), inputChannel, wOutChannel)`)};
          let wValue = ${he.getByOffset(`w_offset / ${_}`)};
          dotProd = dotProd + xValue * wValue;`;else for(let Le=0;Le<d;Le++)Se+=`
            let wValue${Le} = ${he.getByOffset(`${he.indicesToOffset(`${he.type.indices}(u32(wRPerm), u32(wCPerm), inputChannel + ${Le}, wOutChannel)`)} / ${_}`)};
            dotProd = dotProd + xValue[${Le}] * wValue${Le};`;return Se},W=()=>{if(h===0)return"";if(!c)throw new Error(`packInputAs4 ${c} is not true.`);let Se="";if(d===1){Se+="dotProd = dotProd";for(let Le=0;Le<h;Le++)Se+=`
            + ${ae.getByOffset(`x_offset + ${Le}`)} * ${he.getByOffset(`w_offset + ${Le}`)}`;Se+=";"}else if(d===2){if(h!==2)throw new Error(`Invalid inputChannelsRemainder ${h}.`);Se+=`
          let xValue = ${ae.getByOffset("x_offset")};
          let wValue = ${he.getByOffset("w_offset")};
          dotProd = dotProd + dot(xValue, wValue);`}return Se},ee=`
            let outputIndices = ${ce.offsetToIndices(`global_idx * ${m}`)};
            let batch = ${ce.indicesGet("outputIndices",0)};
            let d1 = ${ce.indicesGet("outputIndices",Te)};
            let r = ${ce.indicesGet("outputIndices",be)};
            let c = ${ce.indicesGet("outputIndices",ne)};
            let dyCorner = vec2<i32>(i32(r), i32(c)) - uniforms.pads;
            let dyRCorner = dyCorner.x;
            let dyCCorner = dyCorner.y;
            let groupId = d1 / uniforms.output_channels_per_group;
            let wOutChannel = d1 - groupId * uniforms.output_channels_per_group;
            // Convolve dy(?, ?, d2) with w(:, :, d1, d2) to compute dx(xR, xC, d1).
            // ? = to be determined. : = across all values in that axis.
            var dotProd = ${ce.type.value}(0.0);
            var wR: u32 = 0;
            if (uniforms.dilations.x == 1) {
              // Minimum wR >= 0 that satisfies (dyRCorner + wR) % (uniforms.strides.x) == 0
              wR = u32(((dyRCorner + i32(uniforms.strides.x) - 1) / i32(uniforms.strides.x)) * i32(uniforms.strides.x) - dyRCorner);
            }
            for (; wR < uniforms.effective_filter_dims.x; wR = wR + 1) {
              if (wR % uniforms.dilations.x != 0) {
                continue;
              }
              let dyR = (${de}(dyRCorner) + ${de}(wR)) / ${de}(uniforms.strides[0]);
              let wRPerm = uniforms.filter_dims.x - 1 - wR / uniforms.dilations.x;
              if (dyR < 0.0 || dyR >= ${de}(uniforms.Dy_shape[${be}]) || fract(dyR) > 0.0 ||
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
                let dyC = (${de}(dyCCorner) + ${de}(wC)) / ${de}(uniforms.strides.y);
                let wCPerm = uniforms.filter_dims.y - 1 - wC / uniforms.dilations.y;
                if (dyC < 0.0 || dyC >= ${de}(uniforms.Dy_shape[${ne}]) ||
                    fract(dyC) > 0.0 || wCPerm < 0) {
                  continue;
                }
                let idyC: u32 = u32(dyC);
                var inputChannel = groupId * uniforms.input_channels_per_group;
                ${c?`
                var x_offset = ${ae.indicesToOffset(`${ae.type.indices}(batch, idyR, idyC, inputChannel)`)} / ${d};
                var w_offset = ${he.indicesToOffset(`${he.type.indices}(wRPerm, wCPerm, inputChannel, wOutChannel)`)} / ${_};
                  `:""}
                for (var d2: u32 = 0; d2 < uniforms.input_channels_per_group_int; d2 = d2 + ${c?4:d}) {
                  ${Ge()}
                  inputChannel = inputChannel + ${c?4:d};
                }
                ${W()}
                wC = wC + uniforms.strides.y - 1;
              }
              wR = wR + uniforms.strides[0] - 1;
            }
            let value = dotProd${n?` + bias[d1 / ${m}]`:""};
            ${ce.setByOffset("global_idx","value")};
          `;return`
    ${te.registerUniforms(ye).declareVariables(...Oe,ce)}
      ${te.mainStart()}
      ${te.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")};
    ${ee}}`};return{name:"ConvTranspose2D",shaderCache:{hint:`${t.cacheKey};${d}${_}${m}${c}${h}`,inputDependencies:g},getRunData:()=>({dispatchGroup:{x:w[0],y:w[1],z:w[2]},outputs:[{dims:i?i(r):r,dataType:e[0].dataType}],programUniforms:N}),getShaderSource:q}}}),xl,Sl,kl,dr,Tl,El,cr,Cl,Il,Mp=k(()=>{Op(),ri(),Kt(),xl=(e,t,i,n,r,s)=>(e-1)*t+i+(n-1)*r+1-s,Sl=(e,t,i,n,r)=>{let s=Math.floor(e/2);t==="SAME_UPPER"?(i[n]=s,i[r]=e-s):t==="SAME_LOWER"&&(i[n]=e-s,i[r]=s)},kl=(e,t,i,n,r,s,a,o,l,u)=>{let d=e.length-2,c=u.length===0;l.length<d&&l.push(...Array(d-l.length).fill(0));let p=e[0],h=t[o?3:1]*r;for(let m=0,_=e.length-d-(o?1:0);m<d;++m,++_){let $=e[_],w=c?$*a[m]:u[m],g=xl($,a[m],s[m],t[_],i[m],w);Sl(g,n,s,m,m+d),c&&u.push(a[m]*($-1)+l[m]+(t[_]-1)*i[m]+1-s[m]-s[m+d])}u.splice(0,0,p),u.splice(o?3:1,0,h)},dr=(e,t)=>{let i=e.kernelShape.slice();if(e.kernelShape.length===0||e.kernelShape.reduce((c,p)=>c*p,1)===0){i.length=0;for(let c=2;c<t[1].dims.length;++c)i.push(t[1].dims[c])}let n=e.format==="NHWC";i.splice(0,0,t[1].dims[0]),i.splice(n?3:1,0,t[1].dims[1]);let r=e.pads.slice(),s=e.outputShape.slice(),a=e.outputPadding.slice(),o=t[0].dims,l=e.dilations.slice();if(l.reduce((c,p)=>c+p,0)===0){let c=t[0].dims.length-2;l=new Array(c).fill(1)}let u=e.strides.slice();if(u.reduce((c,p)=>c+p,0)===0){let c=t[0].dims.length-2;u=new Array(c).fill(1)}kl(o,i,l,e.autoPad,e.group,r,u,n,a,s);let d=Object.assign({},e);return Object.assign(d,{kernelShape:i,pads:r,outputPadding:a,outputShape:s,dilations:l,strides:u}),d},Tl=e=>{let t=Xn(e),i=e.format,n=["NOTSET","VALID","SAME_UPPER","SAME_LOWER"][typeof e.autoPad>"u"?0:e.autoPad],r=e.dilations,s=e.group,a=e.kernelShape,o=e.pads,l=e.strides,u=e.wIsConst(),d=e.outputPadding,c=e.outputShape;return{autoPad:n,format:i,dilations:r,group:s,kernelShape:a,outputPadding:d,outputShape:c,pads:o,strides:l,wIsConst:u,...t,cacheKey:`${e.format};${t.activation};`}},El=(e,t)=>{if(!e||e.length!==2&&e.length!==3)throw new Error("Conv requires 2 or 3 inputs");if(e[0].dims.length!==4&&e[0].dims.length!==3)throw new Error("currently only support 2-dimensional conv");if(e[0].dims.length!==e[1].dims.length)throw new Error("filter does not have same dimension as input");let i=e[0].dims[t.format==="NHWC"?e[0].dims.length-1:1],n=e[1].dims[0];if(i!==n)throw new Error("FILTER_IN_CHANNEL should be equal to DATA_CHANNEL");let r=e[1].dims[1]*t.group;if(e.length===3&&(e[2].dims.length!==1||e[2].dims[0]!==r))throw new Error("invalid bias");let s=e[0].dims.length-2;if(t.dilations.reduce((a,o)=>a+o,0)>0&&t.dilations.length!==s)throw new Error(`dilations should be ${s}D`);if(t.strides.reduce((a,o)=>a+o,0)>0&&t.strides.length!==s)throw new Error(`strides should be ${s}D`);if(t.pads.reduce((a,o)=>a+o,0)>0&&t.pads.length!==s*2)throw new Error(`pads should be ${s*2}D`);if(t.outputPadding.length!==s&&t.outputPadding.length!==0)throw new Error(`output_padding should be ${s}D`);if(t.kernelShape.reduce((a,o)=>a+o,0)>0&&t.kernelShape.length!==0&&t.kernelShape.length!==e[1].dims.length-2)throw new Error("invalid kernel shape");if(t.outputShape.length!==0&&t.outputShape.length!==e[0].dims.length-2)throw new Error("invalid output shape")},cr=(e,t,i,n)=>{let r=e.kernelCustomData.wT??e.compute(xt(t[1],[2,3,0,1]),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=r);let s=[t[0],r];t.length===3&&s.push(t[2]),e.compute($l(s,i,n),{inputs:s})},Cl=(e,t)=>{let i=t.format==="NHWC",n=[e.inputs[0].reshape(i?[e.inputs[0].dims[0],1,e.inputs[0].dims[1],e.inputs[0].dims[2]]:[e.inputs[0].dims[0],e.inputs[0].dims[1],1,e.inputs[0].dims[2]]),e.inputs[1].reshape([e.inputs[1].dims[0],e.inputs[1].dims[1],1,e.inputs[1].dims[2]])];e.inputs.length===3&&n.push(e.inputs[2]);let r=t.kernelShape;(r.length===0||r[0]===0)&&(r=[e.inputs[1].dims[2]]);let s=t.dilations;(s.length===0||s[0]===0)&&(s=[1]);let a=t.strides;(a.length===0||a[0]===0)&&(a=[1]);let o=t.pads;o.length===0&&(o=[0,0]),o=[0,o[0],0,o[1]],a=[1].concat(a),s=[1].concat(s),r=[1].concat(r);let l=t.outputPadding;l=[0].concat(l);let u=dr({...t,pads:o,strides:a,dilations:s,kernelShape:r,outputPadding:l},n);cr(e,n,u,d=>i?[d[0],d[2],d[3]]:[d[0],d[1],d[3]])},Il=(e,t)=>{if(El(e.inputs,t),e.inputs[0].dims.length===3)Cl(e,t);else{let i=dr(t,e.inputs);cr(e,e.inputs,i)}}}),Al,zl,Rl,Fp=k(()=>{_e(),$e(),Xe(),xe(),Al=(e,t,i,n)=>{let r=M.size(t),s=t.length,a=B("input",e,s),o=re("output",e,s),l=i.dataType===6?i.getInt32Array()[0]:Number(i.getBigInt64Array()[0]),u=M.normalizeAxis(l,s),d=c=>{let p=` i32(${a.indicesGet("inputIndices","uniforms.axis")}) `,h=se("uniforms.input_shape","uniforms.axis",s),m=n.reverse?p+(n.exclusive?" + 1":""):"0",_=n.reverse?h:p+(n.exclusive?"":" + 1");return`
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
                }`};return{name:"CumSum",shaderCache:{hint:n.cacheKey,inputDependencies:["rank"]},getRunData:()=>({outputs:[{dims:t,dataType:e}],dispatchGroup:{x:Math.ceil(r/64)},programUniforms:[{type:12,data:r},{type:12,data:u},...le(t,t)]}),getShaderSource:d}},zl=(e,t)=>{let i=e.inputs[0].dims,n=e.inputs[0].dataType,r=e.inputs[1];e.compute(Al(n,i,r,t),{inputs:[0]})},Rl=e=>{let t=e.exclusive===1,i=e.reverse===1;return De({exclusive:t,reverse:i})}}),Ol,Ml,Fl,Dl,Bl,Dp=k(()=>{_e(),$e(),Xe(),xe(),Ol=e=>{if(!e||e.length!==1)throw new Error("DepthToSpace requires 1 input.");if(e[0].dims.length!==4)throw new Error("DepthToSpace requires 4D input.")},Ml=(e,t,i,n)=>{let r=[];r.push(`fn perm(i: ${n.type.indices}) -> ${i.type.indices} {
    var a: ${i.type.indices};`);for(let s=0;s<t;++s)r.push(i.indicesSet("a",e[s],`i[${s}]`));return r.push("return a;}"),r.join(`
`)},Fl=(e,t)=>{let i,n,r,s,a,o,l=t.format==="NHWC",u=t.blocksize,d=t.mode==="DCR";l?([i,n,r,s]=e.dims,a=d?[i,n,r,u,u,s/u**2]:[i,n,r,s/u**2,u,u],o=d?[0,1,3,2,4,5]:[0,1,4,2,5,3]):([i,n,r,s]=[e.dims[0],e.dims[2],e.dims[3],e.dims[1]],a=d?[i,u,u,s/u**2,n,r]:[i,s/u**2,u,u,n,r],o=d?[0,3,4,1,5,2]:[0,1,4,2,5,3]);let c=e.reshape(a),p=c.dims.length,h=e.dataType,m=B("a",h,p),_=re("output",h,p),$=w=>`
  ${w.registerUniform("output_size","u32").declareVariables(m,_)}

  ${Ml(o,p,m,_)}

  ${w.mainStart()}
    ${w.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let indices = ${_.offsetToIndices("global_idx")};
    let aIndices = perm(indices);

    ${_.setByOffset("global_idx",m.getByIndices("aIndices"))}
  }`;return{name:"DepthToSpace",shaderCache:{hint:`${e.dims};${t.blocksize};${t.mode}`,inputDependencies:["rank"]},getRunData:w=>{let g=l?[i,n*u,r*u,s/u**2]:[i,s/u**2,n*u,r*u],T=M.size(g),x=c.dims,I=M.sortBasedOnPerm(x,o);return{outputs:[{dims:g,dataType:w[0].dataType}],dispatchGroup:{x:Math.ceil(T/64)},programUniforms:[{type:12,data:T},...le(x,I)]}},getShaderSource:$}},Dl=(e,t)=>{Ol(e.inputs),e.compute(Fl(e.inputs[0],t))},Bl=e=>De({blocksize:e.blocksize,mode:e.mode,format:e.format})}),en,Ci,pr,Pl,Nl,Vl,Ll,fr,Ul,ql,Wl,Bp=k(()=>{_e(),$e(),Xe(),xe(),en="[a-zA-Z]|\\.\\.\\.",Ci="("+en+")+",pr="^"+Ci+"$",Pl="("+Ci+",)*"+Ci,Nl="^"+Pl+"$",Vl=class{constructor(e=-1){this.symbolToIndices=new Map,this.inputIndex=e}addSymbol(e,t){let i=this.symbolToIndices.get(e);i===void 0?i=[t]:i.push(t),this.symbolToIndices.set(e,i)}},Ll=class{constructor(e,t){this.equation=t,this.hasEllipsis=!1,this.symbolToInfo=new Map,this.lhs=new Array,this.outputDims=[];let[i,n]=t.includes("->")?t.split("->",2):[t,""];if(!i.match(RegExp(Nl)))throw new Error("Invalid LHS term");if(i.split(",").forEach((r,s)=>{let a=e[s].dims.slice();if(!r.match(RegExp(pr)))throw new Error("Invalid LHS term");let o=this.processTerm(r,!0,a,s);this.lhs.push(o)}),n==="")n+=[...this.symbolToInfo.entries()].filter(([r,s])=>s.count===1||r==="...").map(([r])=>r).join("");else if(!n.match(RegExp(Ci)))throw new Error("Invalid RHS");n.match(RegExp(en,"g"))?.forEach(r=>{if(r==="...")this.outputDims=this.outputDims.concat(this.ellipsisDims);else{let s=this.symbolToInfo.get(r);if(s===void 0)throw new Error("Invalid RHS symbol");this.outputDims.push(s.dimValue)}}),this.rhs=this.processTerm(n,!1,this.outputDims)}addSymbol(e,t,i){let n=this.symbolToInfo.get(e);if(n!==void 0){if(n.dimValue!==t&&n.count!==1)throw new Error("Dimension mismatch");n.count++,n.inputIndices.push(i)}else n={count:1,dimValue:t,inputIndices:[i]};this.symbolToInfo.set(e,n)}processTerm(e,t,i,n=-1){let r=i.length,s=!1,a=[],o=0;if(!e.match(RegExp(pr))&&!t&&e!=="")throw new Error("Invalid LHS term");let l=e.match(RegExp(en,"g")),u=new Vl(n);return l?.forEach((d,c)=>{if(d==="..."){if(s)throw new Error("Only one ellipsis is allowed per input term");s=!0;let p=r-l.length+1;if(p<0)throw new Error("Ellipsis out of bounds");if(a=i.slice(o,o+p),this.hasEllipsis){if(this.ellipsisDims.length!==a.length||this.ellipsisDims.toString()!==a.toString())throw new Error("Ellipsis dimensions mismatch")}else if(t)this.hasEllipsis=!0,this.ellipsisDims=a;else throw new Error("Ellipsis must be specified in the LHS");for(let h=0;h<a.length;h++){let m=String.fromCharCode(48+h);u.addSymbol(m,c+h),this.addSymbol(m,i[o++],n)}}else u.addSymbol(d,c+(this.hasEllipsis?this.ellipsisDims.length-1:0)),this.addSymbol(d,i[o++],n)}),u}},fr=e=>e+"_max",Ul=(e,t,i,n)=>{let r=e.map(u=>u.length).map((u,d)=>B(`input${d}`,t,u)),s=M.size(n),a=re("output",t,n.length),o=[...i.symbolToInfo.keys()].filter(u=>!i.rhs.symbolToIndices.has(u)),l=u=>{let d=[],c="var prod = 1.0;",p="var sum = 0.0;",h="sum += prod;",m=[],_=[],$=[],w=[],g=i.symbolToInfo.size===i.rhs.symbolToIndices.size;i.symbolToInfo.forEach((x,I)=>{if(i.rhs.symbolToIndices.has(I)){let O=i.rhs.symbolToIndices.get(I)?.[0];O!==void 0&&i.lhs.forEach((z,N)=>{if(x.inputIndices.includes(N)){let q=z.symbolToIndices.get(I);if(q===void 0)throw new Error("Invalid symbol error");q.forEach(te=>{d.push(`${r[N].indicesSet(`input${N}Indices`,te,a.indicesGet("outputIndices",O))}`)})}})}else i.lhs.forEach((O,z)=>{if(x.inputIndices.includes(z)){let N=O.symbolToIndices.get(I);if(N===void 0)throw new Error("Invalid symbol error");N.forEach(q=>{m.push(`${r[z].indicesSet(`input${z}Indices`,q,`${I}`)}`)}),w.push(`prod *= ${r[z].getByIndices(`input${z}Indices`)};`)}}),_.push(`for(var ${I}: u32 = 0; ${I} < uniforms.${fr(I)}; ${I}++) {`),$.push("}")});let T=g?[...d,`let sum = ${r.map((x,I)=>x.getByIndices(`input${I}Indices`)).join(" * ")};`]:[...d,p,..._,...m,c,...w,h,...$];return`
            ${u.registerUniforms(o.map(x=>({name:`${fr(x)}`,type:"u32"}))).registerUniform("outputSize","u32").declareVariables(...r,a)}

            ${u.mainStart()}
            ${u.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
            var outputIndices = ${a.offsetToIndices("global_idx")};
            ${r.map((x,I)=>`var input${I}Indices: ${r[I].type.indices};`).join(`
`)}
            ${T.join(`
`)};
            ${a.setByOffset("global_idx","sum")};
          }`};return{name:"Einsum",shaderCache:{hint:i.equation,inputDependencies:e.map(()=>"rank")},getRunData:()=>{let u=o.filter(c=>i.symbolToInfo.has(c)).map(c=>({type:12,data:i.symbolToInfo.get(c)?.dimValue||0}));u.push({type:12,data:s});let d=e.map((c,p)=>[...le(c)]).reduce((c,p)=>c.concat(p),u);return d.push(...le(n)),{outputs:[{dims:n,dataType:t}],dispatchGroup:{x:Math.ceil(s/64)},programUniforms:d}},getShaderSource:l}},ql=(e,t)=>{let i=new Ll(e.inputs,t.equation),n=i.outputDims,r=e.inputs.map((s,a)=>s.dims);e.compute(Ul(r,e.inputs[0].dataType,i,n))},Wl=e=>{let t=e.equation.replace(/\s+/g,"");return De({equation:t})}}),Gl,hr,jl,Hl,Kl,Pp=k(()=>{_e(),$e(),xe(),Gl=e=>{if(!e||e.length!==2)throw new Error("Expand requires 2 input.");let t=e[0].dims,i=Array.from(e[1].getBigInt64Array(),Number),n=i.length<t.length?0:i.length-t.length,r=t.length<i.length?0:t.length-i.length;for(;n<i.length&&r<t.length;++n,++r)if(i[n]!==t[r]&&i[n]!==1&&t[r]!==1)throw new Error("Expand requires shape to be broadcastable to input")},hr=(e,t)=>{let i=e.length-t.length,n=[];for(let r=0;r<i;++r)n.push(e[r]);for(let r=0;r<t.length;++r)n.push(t[r]===1?e[r+i]:t[r]);return n},jl=(e,t)=>e.length>t.length?hr(e,t):hr(t,e),Hl=e=>{let t=e[0].dims,i=Array.from(e[1].getBigInt64Array(),Number),n=jl(t,i),r=e[0].dataType,s=r===9||M.size(t)===1,a=r===9||t.length>0&&t[t.length-1]%4===0?4:1,o=s||n.length>0&&n[n.length-1]%4===0?4:1,l=Math.ceil(M.size(n)/o),u=c=>{let p=B("input",r,t.length,a),h=re("output",r,n.length,o),m;if(r===9){let _=($,w,g="")=>`
          let outputIndices${w} = ${h.offsetToIndices(`outputOffset + ${w}u`)};
          let offset${w} = ${p.broadcastedIndicesToOffset(`outputIndices${w}`,h)};
          let index${w} = offset${w} / 4u;
          let component${w} = offset${w} % 4u;
          ${$}[${w}] = ${g}(${p.getByOffset(`index${w}`)}[component${w}]);
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
    ${m}`},d=[{type:12,data:l},...le(t,n)];return{name:"Expand",shaderCache:{hint:`${n.length};${a}${o}`,inputDependencies:["rank"]},getShaderSource:u,getRunData:()=>({outputs:[{dims:n,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:d})}},Kl=e=>{Gl(e.inputs),e.compute(Hl(e.inputs),{inputs:[0]})}}),Zl,Ql,Np=k(()=>{_e(),$e(),xe(),Qn(),Zl=e=>{let t=e[0].dataType,i=M.size(e[0].dims),n=M.size(e[1].dims),r=n%4===0,s=a=>{let o=B("x",t,[1],4),l=B("bias",t,[1],4),u=re("y",t,[1],4),d=[{name:"output_vec_size",type:"u32"},{name:"bias_size",type:"u32"}],c=h=>`
      let bias${h}_offset: u32 = (global_idx * 4 + ${h}) % uniforms.bias_size;
      let bias${h} = ${l.getByOffset(`bias${h}_offset / 4`)}[bias${h}_offset % 4];`,p=r?`
      let bias = ${l.getByOffset("global_idx % (uniforms.bias_size / 4)")};`:`${c(0)}${c(1)}${c(2)}${c(3)}
      let bias = ${o.type.value}(bias0, bias1, bias2, bias3);`;return`${a.registerUniforms(d).declareVariables(o,l,u)}

    ${Kn(_t(t))}

    ${a.mainStart(hi)}
      ${a.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_vec_size")}

      let x = ${o.getByOffset("global_idx")};
      ${p}
      let x_in = x + bias;
      ${u.setByOffset("global_idx",Zn("x_in"))}
    }`};return{name:"FastGeluWithBias",shaderCache:{hint:`${r}`,inputDependencies:["type","type"]},getShaderSource:s,getRunData:a=>({outputs:[{dims:a[0].dims,dataType:a[0].dataType}],programUniforms:[{type:12,data:Math.ceil(i/4)},{type:12,data:n}],dispatchGroup:{x:Math.ceil(i/hi/4)}})}},Ql=e=>{e.inputs.length<2||M.size(e.inputs[1].dims)===0?Ao(e):e.compute(Zl(e.inputs))}}),Xl,Yl,Jl,eu,Vp=k(()=>{_e(),$e(),Xe(),xe(),Xl=e=>{if(!e||e.length!==2)throw new Error("Gather requires 2 inputs.")},Yl=(e,t)=>{let i=e[0].dims,n=e[1].dims,r=i.length,s=M.normalizeAxis(t.axis,r),a=i.slice(0);a.splice(s,1,...n);let o=i[s],l=e[0].dataType===9?4:1,u=Math.ceil(M.size(a)/l),d=[{type:12,data:u},{type:6,data:o},{type:12,data:s},...le(e[0].dims,e[1].dims,a)],c=p=>{let h=B("data",e[0].dataType,e[0].dims.length,l),m=B("inputIndices",e[1].dataType,e[1].dims.length),_=re("output",e[0].dataType,a.length,l),$=g=>{let T=n.length,x=`var indicesIndices${g}  = ${m.type.indices}(0);`;for(let I=0;I<T;I++)x+=`${T>1?`indicesIndices${g}[${I}]`:`indicesIndices${g}`} = ${a.length>1?`outputIndices${g}[uniforms.axis + ${I}]`:`outputIndices${g}`};`;x+=`
          var idx${g} = ${m.getByIndices(`indicesIndices${g}`)};
          if (idx${g} < 0) {
            idx${g} = idx${g} + uniforms.axisDimLimit;
          }
          var dataIndices${g} : ${h.type.indices};
        `;for(let I=0,O=0;I<r;I++)I===s?(x+=`${r>1?`dataIndices${g}[${I}]`:`dataIndices${g}`} = u32(idx${g});`,O+=T):(x+=`${r>1?`dataIndices${g}[${I}]`:`dataIndices${g}`} = ${a.length>1?`outputIndices${g}[${O}]`:`outputIndices${g}`};`,O++);return x},w;if(e[0].dataType===9){let g=(T,x,I="")=>`
          let outputIndices${x} = ${_.offsetToIndices(`outputOffset + ${x}u`)};
          ${$(x)};
          let offset${x} = ${h.indicesToOffset(`dataIndices${x}`)};
          let index${x} = offset${x} / 4u;
          let component${x} = offset${x} % 4u;
          ${T}[${x}] = ${I}(${h.getByOffset(`index${x}`)}[component${x}]);
        `;w=`
        let outputOffset = global_idx * ${l};
        var value = vec4<u32>(0);
        ${g("value",0,"u32")}
        ${g("value",1,"u32")}
        ${g("value",2,"u32")}
        ${g("value",3,"u32")}
        ${_.setByOffset("global_idx","value")}
      `}else w=`
      let outputIndices = ${_.offsetToIndices("global_idx")};
      ${$("")};
      let value = ${h.getByIndices("dataIndices")};
      ${_.setByOffset("global_idx","value")};
      `;return`
      ${p.registerUniform("outputSize","u32").registerUniform("axisDimLimit","i32").registerUniform("axis","u32").declareVariables(h,m,_)}
      ${p.mainStart()}
        ${p.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
        ${w}
      }`};return{name:"Gather",shaderCache:{hint:t.cacheKey,inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:a,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(u/64)},programUniforms:d}),getShaderSource:c}},Jl=e=>De({axis:e.axis}),eu=(e,t)=>{let i=e.inputs;Xl(i),e.compute(Yl(e.inputs,t))}}),tu,iu,nu,Lp=k(()=>{_e(),$e(),xe(),tu=(e,t,i,n,r,s,a,o,l)=>{let u=[{type:12,data:s},{type:12,data:n},{type:12,data:r},{type:12,data:i},{type:12,data:a},{type:12,data:o},{type:12,data:l}],d=[s];u.push(...le(t.dims,d));let c=p=>{let h=B("indices_data",t.dataType,t.dims.length),m=re("input_slice_offsets_data",12,1,1),_=[h,m],$=[{name:"output_size",type:"u32"},{name:"batch_dims",type:"u32"},{name:"input_dims",type:"u32",length:r.length},{name:"sizes_from_slice_dims_data",type:"u32",length:i.length},{name:"num_slices_per_batch",type:"u32"},{name:"input_batch_stride",type:"u32"},{name:"num_slice_dims",type:"u32"}];return`
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
  }`};return e.compute({name:"computeSliceOffsets",shaderCache:{hint:`${r.length}_${i.length}`,inputDependencies:["rank"]},getRunData:()=>({outputs:[{dims:d,dataType:e.inputs[1].dataType}],dispatchGroup:{x:Math.ceil(s/64)},programUniforms:u}),getShaderSource:c},{inputs:[t],outputs:[-1]})[0]},iu=(e,t)=>{let i=e.inputs,n=i[0].dims,r=i[0].dataType,s=i[1].dims,a=s[s.length-1],o=M.sizeToDimension(s,s.length-1),l=M.sizeFromDimension(n,t.batchDims+a),u=M.sizeToDimension(n,t.batchDims),d=M.sizeFromDimension(n,t.batchDims),c=o/u,p=new Array(a),h=l;for(let x=0;x<a;++x)p[a-1-x]=h,h*=n[t.batchDims+a-1-x];let m=tu(e,i[1],p,t.batchDims,n,o,c,d,a),_=t.batchDims+a;if(_>n.length)throw new Error("last dimension of indices must not be larger than rank of input tensor");let $=s.slice(0,-1).concat(n.slice(_)),w=M.size($),g=[{type:12,data:w},{type:12,data:l},...le(i[0].dims,m.dims,$)],T=x=>{let I=B("data",i[0].dataType,i[0].dims.length),O=B("slice_offsets",12,m.dims.length),z=re("output",i[0].dataType,$.length);return`
          ${x.registerUniform("output_size","u32").registerUniform("slice_size","u32").declareVariables(I,O,z)}
            ${x.mainStart()}
            ${x.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
          let slice_offset = slice_offsets[global_idx / uniforms.slice_size];
          output[global_idx] = data[u32(slice_offset) + global_idx % uniforms.slice_size];
        }`};e.compute({name:"GatherND",shaderCache:{hint:t.cacheKey,inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:$,dataType:r}],dispatchGroup:{x:Math.ceil(w/64)},programUniforms:g}),getShaderSource:T},{inputs:[i[0],m]})},nu=e=>({batchDims:e.batch_dims,cacheKey:""})}),ru,su,au,ou,Up=k(()=>{_e(),$e(),Xe(),xe(),ru=(e,t)=>{if(e.length<3||e.length>4)throw new Error("GatherBlockQuantized requires 3 or 4 inputs.");let i=M.normalizeAxis(t.quantizeAxis,e[0].dims.length),n=t.blockSize,r=e[0],s=e[2],a=e.length===4?e[3]:void 0;if(s.dims.length!==r.dims.length||!r.dims.map((o,l)=>l===i?Math.ceil(o/n)===s.dims[l]:o===s.dims[l]).reduce((o,l)=>o&&l,!0))throw new Error("Scales must have the same rank as the input tensor and the dims should match except on gatherAxis.");if(a){if(a.dataType!==r.dataType)throw new Error("Zero point must have the same data type as the input tensor.");if(a.dims.length!==s.dims.length||!a.dims.map((o,l)=>o===s.dims[l]).reduce((o,l)=>o&&l,!0))throw new Error("Zero point must have the same rank as the input tensor and the dims should match except on quantizeAxis.")}},su=(e,t)=>{let i=e[0].dims,n=e[1].dims,r=i.length,s=M.normalizeAxis(t.gatherAxis,r),a=M.normalizeAxis(t.quantizeAxis,r),o=i.slice(0);o.splice(s,1,...n);let l=M.size(o),u=e[2].dataType,d=e[0].dataType===22,c=[{type:12,data:l},{type:12,data:a},{type:12,data:s},{type:12,data:t.blockSize},...le(...e.map((h,m)=>h.dims),o)],p=h=>{let m=B("data",e[0].dataType,e[0].dims.length),_=B("inputIndices",e[1].dataType,e[1].dims.length),$=B("scales",e[2].dataType,e[2].dims.length),w=e.length>3?B("zeroPoint",e[3].dataType,e[3].dims.length):void 0,g=re("output",u,o.length),T=[m,_,$];w&&T.push(w);let x=[{name:"output_size",type:"u32"},{name:"quantize_axis",type:"u32"},{name:"gather_axis",type:"u32"},{name:"block_size",type:"u32"}];return`
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
        ${w?`
              let zero_point_indices = scale_indices;
              let zero_point_offset = ${w.indicesToOffset("zero_point_indices")};
              let zero_point_index = zero_point_offset % 8;
              let packed_4bit_zero_points = ${w.getByOffset("zero_point_offset / 8")};
              let packed_8bit_zero_points = (packed_4bit_zero_points >> (4 * (zero_point_index % 2))) & 0x0f0f0f0f;
              let zero_point_vec = ${d?"unpack4xI8":"unpack4xU8"}(u32(packed_8bit_zero_points));
              let zero_point = zero_point_vec[zero_point_index / 2];`:"var zero_point = 0"};
        let dequantized_data = ${_t(u)}(quantized_data - zero_point) * scale;
        ${g.setByOffset("global_idx","dequantized_data")};
    }`};return{name:"GatherBlockQuantized",shaderCache:{hint:`${t.cacheKey};${e.filter((h,m)=>m!==1).map(h=>h.dims.join("_")).join(";")}`,inputDependencies:Array.from({length:e.length},(h,m)=>"rank")},getRunData:()=>({outputs:[{dims:o,dataType:u}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:c}),getShaderSource:p}},au=(e,t)=>{let i=e.inputs;ru(i,t),e.compute(su(e.inputs,t))},ou=e=>De({blockSize:e.blockSize,gatherAxis:e.gatherAxis,quantizeAxis:e.quantizeAxis})}),lu,uu,du,cu,qp=k(()=>{_e(),$e(),Xe(),xe(),lu=e=>{if(!e||e.length!==2)throw new Error("GatherElements requires 2 inputs.");if(e[0].dims.length<1)throw new Error("GatherElements requires that the data input be rank >= 1.");if(e[0].dims.length!==e[1].dims.length)throw new Error(`GatherElements requires that the data input and
                     indices input tensors be of same rank.`)},uu=(e,t)=>{let i=e[0].dims,n=e[0].dataType,r=i.length,s=e[1].dims,a=e[1].dataType,o=M.normalizeAxis(t.axis,r),l=i[o],u=s.slice(0),d=M.size(u),c=B("input",n,r),p=B("indicesInput",a,s.length),h=re("output",n,u.length),m=[{type:12,data:d},{type:6,data:l},{type:12,data:o}];return m.push(...le(i,s,u)),{name:"GatherElements",shaderCache:{inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:u,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(d/64)},programUniforms:m}),getShaderSource:_=>`
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
  }`}},du=e=>De({axis:e.axis}),cu=(e,t)=>{let i=e.inputs;lu(i),e.compute(uu(e.inputs,t))}}),pu,fu,hu,mu,Wp=k(()=>{_e(),$e(),xe(),pu=e=>{if(!e)throw new Error("Input is missing");if(e.length<2||e.length>3)throw new Error("Invaid input number.");if(e.length===3&&e[2].dims.length>2)throw new Error("Invalid input shape of C");if(e[0].dataType!==e[1].dataType||e.length===3&&e[0].dataType!==e[2].dataType)throw new Error("Input types are mismatched")},fu=(e,t)=>{let i=e[0].dims.slice(),n=e[1].dims.slice(),[r,s,a]=xs.getShapeOfGemmResult(i,t.transA,n,t.transB,e.length===3?e[2].dims:void 0),o=[r,s];if(!o)throw new Error("Can't use gemm on the given tensors");let l=16,u=Math.ceil(s/l),d=Math.ceil(r/l),c=!0,p=M.size(o),h=[{type:12,data:c?u:p},{type:12,data:r},{type:12,data:s},{type:12,data:a},{type:1,data:t.alpha},{type:1,data:t.beta}],m=["type","type"];e.length===3&&(h.push(...le(e[2].dims)),m.push("rank")),h.push(...le(o));let _=w=>{let g="";t.transA&&t.transB?g="value += a[k * uniforms.M + m] * b[n * uniforms.K + k];":t.transA&&!t.transB?g="value += a[k * uniforms.M + m] * b[k * uniforms.N + n];":!t.transA&&t.transB?g="value += a[m * uniforms.K + k] * b[n * uniforms.K + k];":!t.transA&&!t.transB&&(g="value += a[m * uniforms.K + k] * b[k * uniforms.N + n];");let T=t.alpha===1?"":"value *= uniforms.alpha;",x=B("a",e[0].dataType,e[0].dims),I=B("b",e[1].dataType,e[1].dims),O=x.type.value,z=null,N=[x,I];e.length===3&&(z=B("c",e[2].dataType,e[2].dims.length),N.push(z));let q=re("output",e[0].dataType,o.length);N.push(q);let te=[{name:"output_size",type:"u32"},{name:"M",type:"u32"},{name:"N",type:"u32"},{name:"K",type:"u32"},{name:"alpha",type:"f32"},{name:"beta",type:"f32"}];return`
  ${w.registerUniforms(te).declareVariables(...N)}

  ${w.mainStart()}
    ${w.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let m = global_idx / uniforms.N;
    let n = global_idx % uniforms.N;

    var value = ${O}(0);
    for (var k: u32 = 0u; k < uniforms.K; k++) {
      ${g}
    }

    ${T}
    ${z!=null?`let cOffset = ${z.broadcastedIndicesToOffset("vec2(m, n)",q)}; value += ${O}(uniforms.beta) * ${z.getByOffset("cOffset")};`:""}
    output[global_idx] = value;
  }`},$=w=>{let g=B("a",e[0].dataType,e[0].dims),T=B("b",e[1].dataType,e[1].dims),x=null,I=[g,T];e.length===3&&(x=B("c",e[2].dataType,e[2].dims.length),I.push(x));let O=re("output",e[0].dataType,o.length);I.push(O);let z=[{name:"num_tile_n",type:"u32"},{name:"M",type:"u32"},{name:"N",type:"u32"},{name:"K",type:"u32"},{name:"alpha",type:"f32"},{name:"beta",type:"f32"}],N="",q="";t.transA&&t.transB?(q=`
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
      `,N="value += tile_a[k][local_id.y] * tile_b[local_id.x][k];"):t.transA&&!t.transB?(q=`
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
      `,N="value += tile_a[k][local_id.y] * tile_b[k][local_id.x];"):!t.transA&&t.transB?(q=`
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
      `,N="value += tile_a[local_id.y][k] * tile_b[local_id.x][k];"):!t.transA&&!t.transB&&(q=`
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
      `,N="value += tile_a[local_id.y][k] * tile_b[k][local_id.x];");let te=t.alpha===1?"":"value *= uniforms.alpha;";return`
  ${w.registerUniforms(z).declareVariables(...I)}
  var<workgroup> tile_a: array<array<${g.type.storage}, ${l}>, ${l}>;
  var<workgroup> tile_b: array<array<${T.type.storage}, ${l}>, ${l}>;
  ${w.mainStart([l,l,1])}
    let tile_col_start = (workgroup_index % uniforms.num_tile_n) * ${l};
    let tile_row_start = (workgroup_index / uniforms.num_tile_n) * ${l};
    let num_tiles = (uniforms.K - 1) / ${l} + 1;
    var k_start = 0u;
    var value = ${O.type.value}(0);
    for (var t: u32 = 0u; t < num_tiles; t++) {
      ${q}
      k_start = k_start + ${l};
      workgroupBarrier();

      for (var k: u32 = 0u; k < ${l}; k++) {
        ${N}
      }
      workgroupBarrier();
    }

    ${te}
    let m = tile_row_start + local_id.y;
    let n = tile_col_start + local_id.x;
    ${x!=null?`let cOffset = ${x.broadcastedIndicesToOffset("vec2(m, n)",O)}; value += ${O.type.value}(uniforms.beta) * ${x.getByOffset("cOffset")};`:""}
    if (m < uniforms.M && n < uniforms.N) {
      output[m * uniforms.N + n] = value;
    }
  }`};return c?{name:"GemmShared",shaderCache:{hint:`${t.cacheKey}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:o,dataType:e[0].dataType}],dispatchGroup:{x:u*d},programUniforms:h}),getShaderSource:$}:{name:"Gemm",shaderCache:{hint:`${t.cacheKey}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:o,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:h}),getShaderSource:_}},hu=e=>{let t=e.transA,i=e.transB,n=e.alpha,r=e.beta;return{transA:t,transB:i,alpha:n,beta:r,cacheKey:`${e.transA};${e.transB};${e.alpha===1}`}},mu=(e,t)=>{pu(e.inputs),e.compute(fu(e.inputs,t))}}),Pt,Gt,si,ai,gu,_u,yu,wu,bu,vu,$u,xu,Su,ku,Gp=k(()=>{_e(),$e(),Xe(),xe(),[Pt,Gt,si,ai]=[0,1,2,3],gu=e=>{if(e[0].dims.length!==4)throw new Error("only 4-D tensor is supported.");if(e[0].dims.length!==e[1].dims.length)throw new Error("input dimensions must be equal to grid dimensions");if(e[0].dims.length-2!==e[1].dims[e[1].dims.length-1])throw new Error(`last dimension of grid must be equal to ${e[0].dims.length-2}`);if(e[0].dims[0]!==e[1].dims[0])throw new Error("grid batch size must match input batch size")},_u=`
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
`,yu=e=>`
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
`,wu=e=>`
  fn gs_denormalize(n: f32, length: i32) -> f32 {
    ${e.alignCorners===0?`
    // alignCorners: false => [-1, 1] to [-0.5, length - 0.5]
    return ((n + 1.0) * f32(length) - 1.0) / 2.0;
    `:`
    // alignCorners: true => [-1, 1] to [0, length - 1]
    return (n + 1.0) / 2.0 * (f32(length - 1));
    `}
  }
`,bu=e=>`
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
`,vu=(e,t,i)=>`
  fn pixel_at_grid(r: i32, c: i32, H: i32, W: i32, batch: u32, channel: u32, border: vec4<f32>) -> ${t} {
     var pixel = ${t}(0);
     var indices = vec4<u32>(0);
     indices[${Pt}] = batch;
     indices[${Gt}] = channel;`+(()=>{switch(i.paddingMode){case"zeros":return`
          if (r >= 0 && r < H && c >=0 && c < W) {
            indices[${si}] = u32(r);
            indices[${ai}] = u32(c);
          } else {
            return ${t}(0);
          }
        `;case"border":return`
          indices[${si}] = u32(clamp(r, 0, H - 1));
          indices[${ai}] = u32(clamp(c, 0, W - 1));
        `;case"reflection":return`
          indices[${si}] = gs_reflect(r, border[1], border[3]);
          indices[${ai}] = gs_reflect(c, border[0], border[2]);
        `;default:throw new Error(`padding mode ${i.paddingMode} is not supported`)}})()+`
    return ${e.getByIndices("indices")};
  }
`,$u=(e,t,i)=>(()=>{switch(i.mode){case"nearest":return`
          let result = pixel_at_grid(i32(round(y)), i32(round(x)), H_in, W_in, indices[${Pt}], indices[${Gt}], border);
        `;case"bilinear":return`
          let x1 = i32(floor(x));
          let y1 = i32(floor(y));
          let x2 = x1 + 1;
          let y2 = y1 + 1;

          let p11 = pixel_at_grid(y1, x1, H_in, W_in, indices[${Pt}], indices[${Gt}], border);
          let p12 = pixel_at_grid(y1, x2, H_in, W_in, indices[${Pt}], indices[${Gt}], border);
          let p21 = pixel_at_grid(y2, x1, H_in, W_in, indices[${Pt}], indices[${Gt}], border);
          let p22 = pixel_at_grid(y2, x2, H_in, W_in, indices[${Pt}], indices[${Gt}], border);

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
              p[h][w] = pixel_at_grid(h + y0, w + x0, H_in, W_in, indices[${Pt}], indices[${Gt}], border);
            }
          }

          let dx = x - f32(x0 + 1);
          let dy = y - f32(y0 + 1);
          let result = gs_bicubic_interpolate(p, dx, dy);
        `;default:throw new Error(`mode ${i.mode} is not supported`)}})()+`${e.setByOffset("global_idx","result")}`,xu=(e,t)=>{let i=B("x",e[0].dataType,e[0].dims.length),n=[e[1].dims[0],e[1].dims[1],e[1].dims[2]],r=B("grid",e[1].dataType,n.length,2),s=[e[0].dims[0],e[0].dims[1],e[1].dims[1],e[1].dims[2]];t.format==="NHWC"&&(s=[e[0].dims[0],e[1].dims[1],e[1].dims[2],e[0].dims[3]],[Pt,Gt,si,ai]=[0,3,1,2]);let a=re("output",e[0].dataType,s.length),o=i.type.value,l=M.size(s),u=[{type:12,data:l},...le(e[0].dims,n,s)],d=c=>`
  ${c.registerUniform("output_size","u32").declareVariables(i,r,a)}
  ${_u}
  ${yu(o)}
  ${wu(t)}
  ${bu(t)}
  ${vu(i,o,t)}

  ${c.mainStart()}
    ${c.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
      let H_in = i32(uniforms.x_shape[${si}]);
      let W_in = i32(uniforms.x_shape[${ai}]);

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
      var grid_indices = vec3<u32>(indices[${Pt}], indices[${si}], indices[${ai}]);
      let nxy = ${r.getByIndices("grid_indices")};
      var x = gs_denormalize(f32(nxy[0]), W_in);
      var y = gs_denormalize(f32(nxy[1]), H_in);

      ${$u(a,o,t)}
  }`;return{name:"GridSample",shaderCache:{hint:`${t.cacheKey}`,inputDependencies:["type","type"]},getRunData:c=>{let p=M.size(s);return{outputs:[{dims:s,dataType:c[0].dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:u}},getShaderSource:d}},Su=(e,t)=>{gu(e.inputs),e.compute(xu(e.inputs,t))},ku=e=>De({alignCorners:e.align_corners,mode:e.mode,paddingMode:e.padding_mode,format:e.format})}),bt,Tu,Eu,mr,Cu,Ii,Iu,Au=k(()=>{_e(),$e(),Xe(),Fn(),jn(),xe(),Kt(),bt=(e,t)=>e.length>t&&e[t].dims.length>0?e[t]:void 0,Tu=(e,t)=>{let i=e[0],n=bt(e,1),r=bt(e,2),s=bt(e,3),a=bt(e,4),o=bt(e,5),l=bt(e,6),u=bt(e,7);if(i.dims.length!==3&&i.dims.length!==5)throw new Error("Input query is expected to have 3 or 5 dimensions");let d=i.dims[0],c=i.dims[1],p=i.dims.length===3?i.dims[2]:t.numHeads*i.dims[4],h=c,m=0,_=0,$=Math.floor(p/t.numHeads);if(l&&u&&M.size(l.dims)&&M.size(u.dims)){if(l.dims.length!==4)throw new Error('Input "past_key" is expected to have 4 dimensions');if(l.dims[0]!==d||l.dims[1]!==t.numHeads||l.dims[3]!==$)throw new Error('Input "past_key" shape (batch_size, num_heads, past_sequence_length, head_size)');if(u.dims[0]!==d||u.dims[1]!==t.numHeads||u.dims[3]!==$)throw new Error('Input "past_value" shape (batch_size, num_heads, past_sequence_length, head_size)');if(l.dims[2]!==u.dims[2])throw new Error('Input "past_key" and "past_value" shall have same dim 2 (past_sequence_length)');if(u.dims.length!==4)throw new Error('Input "past_value" is expected to have 4 dimensions');m=l.dims[2],_=l.dims[2]}else if(l&&M.size(l.dims)||u&&M.size(u.dims))throw new Error('Input "past_key" and "past_value" shall be both present or both absent');let w;if(n&&M.size(n.dims)>0){if(i.dims.length!==3)throw new Error('Input "query" is expected to have 3 dimensions when key is given');if(n.dims.length<3||n.dims.length>5)throw new Error('Input "key" is expected to have 3, 4, or 5 dimensions');if(i.dims[0]!==n.dims[0])throw new Error('Input "query" and "key" shall have same dim 0 (batch size)');if(n.dims.length===3){if(n.dims[2]!==i.dims[2])throw new Error('Input "query" and "key" shall have same dim 2 (hidden_size)');w=2,h=n.dims[1]}else if(n.dims.length===5){if(n.dims[2]!==t.numHeads||n.dims[3]!==2||n.dims[4]!==$)throw new Error('Expect "key" shape (batch_size, kv_sequence_length, num_heads, 2, head_size) for packed kv');if(r)throw new Error('Expect "value" be none when "key" has packed kv format.');w=5,h=n.dims[1]}else{if(n.dims[1]!==t.numHeads||n.dims[3]!==$)throw new Error('Expect "key" shape (batch_size, num_heads, kv_sequence_length, head_size) for past_key');w=0,h=n.dims[2]}}else{if(i.dims.length!==5)throw new Error('Input "query" is expected to have 5 dimensions when key is empty');if(i.dims[2]!==t.numHeads||i.dims[3]!==3)throw new Error('Expect "query" shape (batch_size, kv_sequence_length, num_heads, 3, head_size) for packed kv');w=3}if(s&&M.size(s.dims)>0){if(s.dims.length!==1)throw new Error('Input "bias" is expected to have 1 dimension');if(n&&n.dims.length===5&&n.dims[3]===2)throw new Error("bias is not allowed for packed kv.")}let g=m+h,T=0;if(a&&M.size(a.dims)>0){T=8;let z=a.dims;throw z.length===1?z[0]===d?T=1:z[0]===3*d+2&&(T=3):z.length===2&&z[0]===d&&z[1]===g&&(T=5),T===8?new Error('Input "key_padding_mask" shape shall be (batch_size) or (batch_size, total_sequence_length)'):new Error("Mask not supported")}let x=!1,I=p;if(r&&M.size(r.dims)>0){if(r.dims.length!==3&&r.dims.length!==4)throw new Error('Input "value" is expected to have 3 or 4 dimensions');if(i.dims[0]!==r.dims[0])throw new Error('Input "query" and "value" shall have same dim 0 (batch_size)');if(r.dims.length===3){if(h!==r.dims[1])throw new Error('Input "key" and "value" shall have the same dim 1 (kv_sequence_length)');I=r.dims[2]}else{if(h!==r.dims[2])throw new Error('Input "key" and "value" shall have the same dim 2 (kv_sequence_length)');I=r.dims[1]*r.dims[3],x=!0}}let O=!1;if(a&&M.size(a.dims)>0)throw new Error("Key padding mask is not supported");if(o&&M.size(o.dims)>0){if(o.dims.length!==4)throw new Error('Input "attention_bias" is expected to have 4 dimensions');if(o.dims[0]!==d||o.dims[1]!==t.numHeads||o.dims[2]!==c||o.dims[3]!==g)throw new Error('Expect "attention_bias" shape (batch_size, num_heads, sequence_length, total_sequence_length)')}return{batchSize:d,sequenceLength:c,pastSequenceLength:m,kvSequenceLength:h,totalSequenceLength:g,maxSequenceLength:_,inputHiddenSize:0,hiddenSize:p,vHiddenSize:I,headSize:$,vHeadSize:Math.floor(I/t.numHeads),numHeads:t.numHeads,isUnidirectional:!1,pastPresentShareBuffer:!1,maskFilterValue:t.maskFilterValue,maskType:T,scale:t.scale,broadcastResPosBias:O,passPastInKv:x,qkvFormat:w}},Eu=e=>De({...e}),mr=De({perm:[0,2,1,3]}),Cu=(e,t,i,n,r,s,a)=>{let o=[n,r,s],l=M.size(o),u=[{type:12,data:l},{type:12,data:a},{type:12,data:s}],d=c=>{let p=re("qkv_with_bias",t.dataType,o),h=B("qkv",t.dataType,o),m=B("bias",i.dataType,o),_=[{name:"output_size",type:"u32"},{name:"bias_offset",type:"u32"},{name:"hidden_size",type:"u32"}];return`
  ${c.registerUniforms(_).declareVariables(h,m,p)}
  ${c.mainStart()}
    ${c.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    let bias_offset_idx = (global_idx % uniforms.hidden_size) + uniforms.bias_offset;

    qkv_with_bias[global_idx] = qkv[global_idx] + bias[bias_offset_idx];
  }`};return e.compute({name:"MultiHeadAttentionAddBias",shaderCache:{inputDependencies:["type","type"]},getRunData:()=>({outputs:[{dims:o,dataType:t.dataType,gpuDataType:0}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:u}),getShaderSource:d},{inputs:[t,i],outputs:[-1]})[0]},Ii=(e,t,i,n,r,s,a,o)=>{let l=s;if(a&&M.size(a.dims)>0){if(n===1)throw new Error("AddBiasReshape is not implemented. Please export your model with packed QKV or KV");return l=Cu(e,s,a,t,n,i*r,o),l=l.reshape([t,n,i,r]),i===1||n===1?l:e.compute(xt(l,mr.perm),{inputs:[l],outputs:[-1]})[0]}else return s.dims.length===3&&(l=s.reshape([t,n,i,r])),i===1||n===1?l:e.compute(xt(l,mr.perm),{inputs:[l],outputs:[-1]})[0]},Iu=(e,t)=>{let i=Tu(e.inputs,t),n=e.inputs[0],r=bt(e.inputs,1),s=bt(e.inputs,2),a=bt(e.inputs,3),o=bt(e.inputs,4),l=bt(e.inputs,5),u=bt(e.inputs,6),d=bt(e.inputs,7);if(n.dims.length===5)throw new Error("Packed QKV is not implemented");if(r?.dims.length===5)throw new Error("Packed KV is not implemented");let c=r&&s&&r.dims.length===4&&s.dims.length===4,p=Ii(e,i.batchSize,i.numHeads,i.sequenceLength,i.headSize,n,a,0);if(c)return Si(e,p,r,s,o,void 0,u,d,l,i);if(!r||!s)throw new Error("key and value must be provided");let h=Ii(e,i.batchSize,i.numHeads,i.kvSequenceLength,i.headSize,r,a,i.hiddenSize),m=Ii(e,i.batchSize,i.numHeads,i.kvSequenceLength,i.vHeadSize,s,a,2*i.hiddenSize);Si(e,p,h,m,o,void 0,u,d,l,i)}}),zu,Ru,Ou,Mu,gr,Fu,Du,Bu=k(()=>{_e(),$e(),Xe(),xe(),zu=e=>{if(!e||e.length<1)throw new Error("too few inputs")},Ru=(e,t)=>{let i=[],n=t.numOutputs;return e[1].dims[0]>0&&(e[1].getBigInt64Array().forEach(r=>i.push(Number(r))),n=i.length),De({numOutputs:n,axis:t.axis,splitSizes:i})},Ou=e=>`
fn calculateOutputIndex(index: u32) -> u32 {
    for (var i: u32 = 0u; i < ${e}u; i += 1u ) {
    if (index < ${se("uniforms.size_in_split_axis","i",e)}) {
        return i;
    }
    }
    return ${e}u;
}`,Mu=e=>{let t=e.length,i=[];for(let n=0;n<t;++n){let r=e[n].setByIndices("indices","input[global_idx]");t===1?i.push(r):n===0?i.push(`if (output_number == ${n}u) { ${r} }`):n===t-1?i.push(`else { ${r} }`):i.push(`else if (output_number == ${n}) { ${r} }`)}return`
      fn writeBufferData(output_number: u32, indices: ${e[0].type.indices}, global_idx: u32) {
        ${i.join(`
`)}
      }`},gr=(e,t)=>{let i=e[0].dims,n=M.size(i),r=e[0].dataType,s=M.normalizeAxis(t.axis,i.length),a=new Array(t.numOutputs),o=B("input",r,i.length),l=new Array(t.numOutputs),u=[],d=[],c=0,p=[{type:12,data:n}];for(let m=0;m<t.numOutputs;m++){c+=t.splitSizes[m],l[m]=c;let _=i.slice();_[s]=t.splitSizes[m],d.push(_),a[m]=re(`output${m}`,r,_.length),u.push({dims:d[m],dataType:e[0].dataType})}p.push({type:12,data:l},...le(i,...d));let h=m=>`
  ${m.registerUniform("input_size","u32").registerUniform("size_in_split_axis","u32",l.length).declareVariables(o,...a)}
  ${Ou(l.length)}
  ${Mu(a)}

  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.input_size")}

    var indices = ${o.offsetToIndices("global_idx")};
    var index = ${o.indicesGet("indices",s)};
    let output_number = calculateOutputIndex(index);
    if (output_number != 0) {
      index -= ${se("uniforms.size_in_split_axis","output_number - 1u",l.length)};
      ${o.indicesSet("indices",s,"index")};
    }
    writeBufferData(output_number, indices, global_idx);
  }`;return{name:"Split",shaderCache:{hint:t.cacheKey,inputDependencies:["rank"]},getShaderSource:h,getRunData:()=>({outputs:u,dispatchGroup:{x:Math.ceil(n/64)},programUniforms:p})}},Fu=(e,t)=>{zu(e.inputs);let i=e.inputs.length===1?t:Ru(e.inputs,t);e.compute(gr(e.inputs,i),{inputs:[0]})},Du=e=>{let t=e.axis,i=e.splitSizes,n=e.numOutputs<0?i.length:e.numOutputs;if(n!==i.length)throw new Error("numOutputs and splitSizes length must be equal");return De({axis:t,numOutputs:n,splitSizes:i})}}),Pu,tn,Nu,Vu=k(()=>{_e(),$e(),Xe(),xe(),Pu=(e,t)=>{let[i,n,r,s]=e,{numHeads:a,rotaryEmbeddingDim:o}=t;if(i.dims.length!==3&&i.dims.length!==4)throw new Error(`Input 'x' is expected to have 3 or 4 dimensions, got ${i.dims.length}`);if(!M.areEqual(n.dims,[])&&!M.areEqual(n.dims,[1])&&n.dims.length!==2)throw new Error(`Input 'position_ids' is expected to have 0, 1, or 2 dimensions, got ${n.dims.length}`);if(r.dims.length!==2)throw new Error(`Input 'cos_cache' is expected to have 2 dimensions, got ${r.dims.length}`);if(s.dims.length!==2)throw new Error(`Input 'sin_cache' is expected to have 2 dimensions, got ${s.dims.length}`);if(!M.areEqual(r.dims,s.dims))throw new Error("Inputs 'cos_cache' and 'sin_cache' are expected to have the same shape");if(o>0&&a===0)throw new Error("num_heads must be provided if rotary_embedding_dim is specified");let l=i.dims[0],u=i.dims[i.dims.length-2],d=r.dims[0],c=M.sizeFromDimension(i.dims,1)/u,p=o===0?r.dims[1]*2:c/a;if(o>p)throw new Error("rotary_embedding_dim must be less than or equal to head_size");if(n.dims.length===2){if(l!==n.dims[0])throw new Error(`Input 'position_ids' dimension 0 should be of size batch_size, got ${n.dims[0]}`);if(u!==n.dims[1])throw new Error(`Input 'position_ids' dimension 1 should be of size sequence_length, got ${n.dims[1]}`)}if(p/2!==r.dims[1]&&o/2!==r.dims[1])throw new Error(`Input 'cos_cache' dimension 1 should be same as head_size / 2 or rotary_embedding_dim / 2, got ${r.dims[1]}`);if(u>d)throw new Error("Updating cos_cache and sin_cache in RotaryEmbedding is not currently supported")},tn=(e,t)=>{let{interleaved:i,numHeads:n,rotaryEmbeddingDim:r,scale:s}=t,a=e[0].dims[0],o=M.sizeFromDimension(e[0].dims,1),l=e[0].dims[e[0].dims.length-2],u=o/l,d=e[2].dims[1],c=r===0?d*2:u/n,p=new Array(a,l,u/c,c-d),h=M.computeStrides(p),m=[{type:1,data:s},{type:12,data:p},{type:12,data:h},...e[0].dims.length===3?new Array({type:12,data:[o,u,c,1]}):[],...e[0].dims.length===4?new Array({type:12,data:[o,c,l*c,1]}):[],...le(e[0].dims,e[1].dims,e[2].dims,e[3].dims,e[0].dims)],_=$=>{let w=B("input",e[0].dataType,e[0].dims.length),g=B("position_ids",e[1].dataType,e[1].dims.length),T=B("cos_cache",e[2].dataType,e[2].dims.length),x=B("sin_cache",e[3].dataType,e[3].dims.length),I=re("output",e[0].dataType,e[0].dims.length);return $.registerUniforms([{name:"scale",type:"f32"},{name:"global_shape",type:"u32",length:p.length},{name:"global_strides",type:"u32",length:h.length},{name:"input_output_strides",type:"u32",length:h.length}]),`
        ${$.declareVariables(w,g,T,x,I)}

        ${$.mainStart(hi)}
          let half_rotary_emb_dim = uniforms.${T.name}_shape[1];
          let bsnh = global_idx / uniforms.global_strides % uniforms.global_shape;
          let size = uniforms.global_shape[0] * uniforms.global_strides[0];
          ${$.guardAgainstOutOfBoundsWorkgroupSizes("size")}

          if (bsnh[3] < half_rotary_emb_dim) {
            let position_ids_idx =
                ${g.broadcastedIndicesToOffset("bsnh.xy",re("",g.type.tensor,2))};
            let position_id =
                u32(${g.getByOffset("position_ids_idx")}) + select(0, bsnh[1], position_ids_idx == 0);
            let i = dot(bsnh, uniforms.input_output_strides) + select(0, bsnh[3], ${i});
            let j = i + select(half_rotary_emb_dim, 1, ${i});
            let re = ${w.getByOffset("i")} * ${T.get("position_id","bsnh[3]")} -
                ${w.getByOffset("j")} * ${x.get("position_id","bsnh[3]")};
            ${I.setByOffset("i","re")}
            let im = ${w.getByOffset("i")} * ${x.get("position_id","bsnh[3]")} +
                ${w.getByOffset("j")} * ${T.get("position_id","bsnh[3]")};
            ${I.setByOffset("j","im")}
          } else {
            let k = dot(bsnh, uniforms.input_output_strides) + half_rotary_emb_dim;
            ${I.setByOffset("k",w.getByOffset("k"))}
          }
        }`};return{name:"RotaryEmbedding",shaderCache:{hint:De({interleaved:i}).cacheKey,inputDependencies:["rank","rank","rank","rank"]},getShaderSource:_,getRunData:()=>({outputs:[{dims:e[0].dims,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(M.size(p)/hi)},programUniforms:m})}},Nu=(e,t)=>{Pu(e.inputs,t),e.compute(tn(e.inputs,t))}}),Lu,Uu,_r,qu,Wu,jp=k(()=>{Xe(),_e(),jn(),Au(),Bu(),Kt(),Vu(),xe(),Lu=(e,t)=>{if(t.doRotary&&e.length<=7)throw new Error("cos_cache and sin_cache inputs are required if do_rotary is specified");let i=e[0],n=e[1],r=e[2],s=e[3],a=e[4];if(t.doRotary!==0&&e.length<=7)throw new Error("cos_cast and sin_cache are expected if do_rotary attribute is non-zero");if(t.localWindowSize!==-1)throw new Error("Local attention is not supported");if(t.softcap!==0)throw new Error("Softcap is not supported");if(t.rotaryInterleaved!==0)throw new Error("Rotary interleaved is not supported");if(t.smoothSoftmax)throw new Error("Smooth softmax is not supported");if(i.dims.length!==3&&i.dims.length!==5)throw new Error("Input query is expected to have 3 or 5 dimensions");let o=!1,l=i.dims[0],u=i.dims[1],d=i.dims.length===3?o?i.dims[2]/3:i.dims[2]:t.numHeads*i.dims[4],c=u,p=0,h=!n||n.dims.length===0,m=Math.floor(h?d/(t.numHeads+2*t.kvNumHeads):d/t.numHeads);h&&(d=m*t.numHeads);let _=s&&s.dims.length!==0,$=a&&a.dims.length!==0;if(_&&s.dims.length===4&&s.dims[0]===l&&s.dims[1]!==t.kvNumHeads&&s.dims[2]===t.kvNumHeads&&s.dims[3]===m)throw new Error("BSNH pastKey/pastValue is not supported");if(_&&$){if(s.dims.length!==4)throw new Error('Input "past_key" is expected to have 4 dimensions');if(a.dims.length!==4)throw new Error('Input "past_value" is expected to have 4 dimensions');p=s.dims[2]}else if(_||$)throw new Error('Input "past_key" and "past_value" shall be both present or both absent');let w=1;if(n&&n.dims.length>0){if(i.dims.length!==3)throw new Error('Input "query" is expected to have 3 dimensions when key is given');if(n.dims.length<3||n.dims.length>5)throw new Error('Input "key" is expected to have 3, 4, or 5 dimensions');if(i.dims[0]!==n.dims[0])throw new Error('Input "query" and "key" shall have same dim 0 (batch size)');if(n.dims.length===3){if(i.dims[2]%n.dims[2]!==0)throw new Error('Dimension 2 of "query" should be a multiple of "key"');c=n.dims[1]}else if(n.dims.length===5){if(n.dims[2]!==t.numHeads||n.dims[3]!==2||n.dims[4]!==m)throw new Error('Expect "key" shape (batch_size, kv_sequence_length, num_heads, 2, head_size) for packed kv');if(r)throw new Error('Expect "value" be none when "key" has packed kv format.');c=n.dims[1]}else{if(n.dims[1]!==t.numHeads||n.dims[3]!==m)throw new Error('Expect "key" shape (batch_size, num_heads, kv_sequence_length, head_size) for past_key');c=n.dims[2]}}else{if(i.dims.length!==3&&i.dims.length!==5)throw new Error('Input "query" is expected to have 3 or 5 dimensions when key is empty');if(i.dims.length===5&&(i.dims[2]!==t.numHeads||i.dims[3]!==3))throw new Error('Expect "query" shape (batch_size, kv_sequence_length, num_heads, 3, head_size) for packed kv');w=3}let g=0,T=!1,x=t.kvNumHeads?m*t.kvNumHeads:d;if(r&&r.dims.length>0){if(r.dims.length!==3&&r.dims.length!==4)throw new Error('Input "value" is expected to have 3 or 4 dimensions');if(i.dims[0]!==r.dims[0])throw new Error('Input "query" and "value" shall have same dim 0 (batch_size)');if(r.dims.length===3){if(c!==r.dims[1])throw new Error('Input "key" and "value" shall have the same dim 1 (kv_sequence_length)');x=r.dims[2]}else{if(c!==r.dims[2])throw new Error('Input "past_key" and "past_value" shall have the same dim 2 (kv_sequence_length)');x=r.dims[1]*r.dims[3],T=!0}}let I=e.length>4?e[5]:void 0;if(I&&I.dims.length!==1&&I.dims[0]!==l)throw new Error('Input "seqlens" is expected to have 1 dimension and the same dim 0 as batch_size');return{batchSize:l,sequenceLength:u,pastSequenceLength:p,kvSequenceLength:c,totalSequenceLength:-1,maxSequenceLength:-1,inputHiddenSize:0,hiddenSize:d,vHiddenSize:x,headSize:m,vHeadSize:Math.floor(x/t.kvNumHeads),numHeads:t.numHeads,kvNumHeads:t.kvNumHeads,nReps:t.numHeads/t.kvNumHeads,pastPresentShareBuffer:!1,maskType:g,scale:t.scale,broadcastResPosBias:!1,passPastInKv:T,qkvFormat:w}},Uu=De({perm:[0,2,1,3]}),_r=(e,t,i)=>{let n=t,r=i.kvNumHeads;return t.dims.length===3&&i.kvSequenceLength!==0&&(n=t.reshape([i.batchSize,i.kvSequenceLength,r,i.headSize]),n=e.compute(xt(n,Uu.perm),{inputs:[n],outputs:[-1]})[0]),n},qu=(e,t,i,n)=>{let r=7,s=["type","type"],a=[e*t],o=e*t,l=[{type:12,data:o},{type:12,data:t},{type:12,data:e}],u=d=>{let c=B("seq_lens",i.dataType,i.dims),p=B("total_seq_lens",n.dataType,n.dims),h=re("pos_ids",r,a),m=[{name:"output_size",type:"u32"},{name:"sequence_length",type:"u32"},{name:"batch_size",type:"u32"}];return`
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
  `};return{name:"GeneratePositionIds",shaderCache:{hint:`${e};${t}`,inputDependencies:s},getRunData:()=>({outputs:[{dims:a,dataType:r}],dispatchGroup:{x:Math.ceil(o/64)},programUniforms:l}),getShaderSource:u}},Wu=(e,t)=>{let i=Lu(e.inputs,t);if(e.inputs[0].dims.length===5)throw new Error("Packed QKV is not implemented");if(e.inputs[1]?.dims.length===5)throw new Error("Packed KV is not implemented");let n=e.inputs[0],r=e.inputs[1]&&e.inputs[1].dims.length>0?e.inputs[1]:void 0,s=e.inputs[2]&&e.inputs[2].dims.length>0?e.inputs[2]:void 0,a=e.inputs[3]&&e.inputs[3].dims.length!==0?e.inputs[3]:void 0,o=e.inputs[4]&&e.inputs[4].dims.length!==0?e.inputs[4]:void 0,l=e.inputs.length>4?e.inputs[5]:void 0,u=e.inputs.length>5?e.inputs[6]:void 0,d=i.kvNumHeads?i.kvNumHeads:i.numHeads,c=De({axis:2,numOutputs:3,splitSizes:[i.numHeads*i.headSize,d*i.headSize,d*i.headSize]}),[p,h,m]=!r&&!s?e.compute(gr([n],c),{inputs:[n],outputs:[-1,-1,-1]}):[n,r,s],_,$;if(t.doRotary){let x=e.compute(qu(i.batchSize,i.sequenceLength,l,u),{inputs:[l,u],outputs:[-1]})[0],I=e.inputs[7],O=e.inputs[8],z=De({interleaved:t.rotaryInterleaved!==0,numHeads:i.numHeads,rotaryEmbeddingDim:0,scale:t.scale}),N=[p,x,I,O],q=[-1];_=e.compute(tn(N,z),{inputs:N,outputs:q})[0],N.splice(0,1,h);let te=De({interleaved:t.rotaryInterleaved!==0,numHeads:i.kvNumHeads,rotaryEmbeddingDim:0,scale:t.scale});$=e.compute(tn(N,te),{inputs:N,outputs:q})[0]}let w=Ii(e,i.batchSize,i.numHeads,i.sequenceLength,i.headSize,t.doRotary?_:p,void 0,0),g=_r(e,t.doRotary?$:h,i),T=_r(e,m,i);Si(e,w,g,T,void 0,void 0,a,o,void 0,i,l,u)}}),yr,Gu,ju,Hu,Hp=k(()=>{_e(),$e(),Kt(),xe(),yr=(e,t,i,n,r,s,a,o)=>{let l=Qe(s),u=l===1?"f32":`vec${l}f`,d=l===1?"vec2f":`mat2x${l}f`,c=r*a,p=64;c===1&&(p=256);let h=[r,a,s/l],m=[r,a,2],_=["rank","type","type"],$=[];$.push(...le(h,m));let w=g=>{let T=B("x",t.dataType,3,l),x=B("scale",i.dataType,i.dims),I=B("bias",n.dataType,n.dims),O=re("output",1,3,2),z=[T,x,I,O];return`
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
      let sum_final = ${Ht("workgroup_shared[0][0]",l)} / f32(hight * ${l});
      let squared_sum_final = ${Ht("workgroup_shared[0][1]",l)} / f32(hight * ${l});

      let inv_std_dev = inverseSqrt(squared_sum_final - sum_final * sum_final + f32(${o}));
      let channel_scale = inv_std_dev * f32(scale[channel]);
      let channel_shift = f32(bias[channel]) - sum_final * channel_scale;
      output[workgroup_index] = vec2f(channel_scale, channel_shift);
    }
  }`};return e.compute({name:"InstanceNormComputeChannelScaleShift",shaderCache:{hint:`${l};${o};${p}`,inputDependencies:_},getRunData:()=>({outputs:[{dims:m,dataType:1}],dispatchGroup:{x:c},programUniforms:$}),getShaderSource:w},{inputs:[t,i,n],outputs:[-1]})[0]},Gu=(e,t,i)=>{let n=t[0].dims,r=n,s=2,a=n[0],o=n[1],l=M.sizeFromDimension(n,s),u=Qe(l),d=M.size(r)/u,c=yr(e,t[0],t[1],t[2],a,l,o,i.epsilon),p=[a,o,l/u],h=[a,o],m=["type","none"],_=$=>{let w=B("x",t[0].dataType,p.length,u),g=B("scale_shift",1,h.length,2),T=re("output",t[0].dataType,p.length,u),x=[w,g,T];return`
  ${$.registerUniform("output_size","u32").declareVariables(...x)}
  ${$.mainStart()}
  ${$.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
      let outputIndices = ${T.offsetToIndices("global_idx")};
      let batch = outputIndices[0];
      let channel = outputIndices[1];
      let scale_shift = ${g.getByIndices("vec2<u32>(batch, channel)")};
      let value = ${w.getByOffset("global_idx")} * ${T.type.value}(scale_shift.x) + ${T.type.value}(scale_shift.y);
      ${T.setByOffset("global_idx","value")};
  }`};e.compute({name:"InstanceNormalization",shaderCache:{hint:`${u}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:r,dataType:t[0].dataType}],dispatchGroup:{x:Math.ceil(d/64)},programUniforms:[{type:12,data:d},...le(p,h,p)]}),getShaderSource:_},{inputs:[t[0],c]})},ju=(e,t,i)=>{let n=t[0].dims,r=n,s=n[0],a=n[n.length-1],o=M.sizeFromDimension(n,1)/a,l=Qe(a),u=M.size(r)/l,d=[{type:12,data:o},{type:12,data:Math.floor(a/l)}],c=["type","type"],p=!1,h=[0,n.length-1];for(let w=0;w<n.length-2;w++)p=p||n[w+1]!==1,h.push(w+1);p=p&&n[n.length-1]!==1;let m=p?e.compute(xt(e.inputs[0],h),{inputs:[e.inputs[0]],outputs:[-1]})[0]:e.inputs[0].reshape(Array.from({length:n.length},(w,g)=>n[h[g]])),_=yr(e,m,t[1],t[2],s,o,a,i.epsilon),$=w=>{let g=at(t[0].dataType),T=l===1?"vec2f":`mat${l}x2f`,x=z=>{let N=z===0?"x":"y",q=l===1?"f32":`vec${l}f`;switch(l){case 1:return`${g}(${q}(scale.${N}))`;case 2:return`vec2<${g}>(${q}(scale[0].${N}, scale[1].${N}))`;case 4:return`vec4<${g}>(${q}(scale[0].${N}, scale[1].${N}, scale[2].${N}, scale[3].${N}))`;default:throw new Error(`Not supported compoents ${l}`)}},I=B("input",t[0].dataType,t[0].dims,l),O=re("output",t[0].dataType,r,l);return`
  @group(0) @binding(0) var<storage, read> input : array<${I.type.storage}>;
  @group(0) @binding(1) var<storage, read> scale_input : array<${T}>;
  @group(0) @binding(2) var<storage, read_write> output : array<${O.type.storage}>;
  struct Uniforms {H: u32, C : u32};
  @group(0) @binding(3) var<uniform> uniforms: Uniforms;

  ${w.mainStart()}
    let current_image_number = global_idx / (uniforms.C * uniforms.H);
    let current_channel_number = global_idx % uniforms.C;

    let scale_offset = current_image_number * uniforms.C + current_channel_number;
    let scale = scale_input[scale_offset];
    output[global_idx] = fma(input[global_idx], ${x(0)}, ${x(1)});
  }`};e.compute({name:"InstanceNormalizationNHWC",shaderCache:{hint:`${l}`,inputDependencies:c},getRunData:()=>({outputs:[{dims:r,dataType:t[0].dataType}],dispatchGroup:{x:Math.ceil(u/64)},programUniforms:d}),getShaderSource:$},{inputs:[t[0],_]})},Hu=(e,t)=>{t.format==="NHWC"?ju(e,e.inputs,t):Gu(e,e.inputs,t)}}),Ku,Zu,Qu,Kp=k(()=>{_e(),$e(),xe(),Ku=e=>{if(!e||e.length<2)throw new Error("layerNorm requires at least 2 inputs.")},Zu=(e,t,i)=>{let n=t.simplified,r=e[0].dims,s=e[1],a=!n&&e[2],o=r,l=M.normalizeAxis(t.axis,r.length),u=M.sizeToDimension(r,l),d=M.sizeFromDimension(r,l),c=M.size(s.dims),p=a?M.size(a.dims):0;if(c!==d||a&&p!==d)throw new Error(`Size of X.shape()[axis:] == ${d}.
       Size of scale and bias (if provided) must match this.
       Got scale size of ${c} and bias size of ${p}`);let h=[];for(let I=0;I<r.length;++I)I<l?h.push(r[I]):h.push(1);let m=Qe(d),_=["type","type"],$=[{type:12,data:u},{type:1,data:d},{type:12,data:Math.floor(d/m)},{type:1,data:t.epsilon}];a&&_.push("type");let w=i>1,g=i>2,T=I=>{let O=at(e[0].dataType),z=[B("x",e[0].dataType,e[0].dims,m),B("scale",s.dataType,s.dims,m)];a&&z.push(B("bias",a.dataType,a.dims,m)),z.push(re("output",e[0].dataType,o,m)),w&&z.push(re("mean_data_output",1,h)),g&&z.push(re("inv_std_output",1,h));let N=[{name:"norm_count",type:"u32"},{name:"norm_size",type:"f32"},{name:"norm_size_vectorized",type:"u32"},{name:"epsilon",type:"f32"}];return`
  ${I.registerUniforms(N).declareVariables(...z)}
  ${I.mainStart()}
    ${I.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.norm_count")}
    let offset = global_idx * uniforms.norm_size_vectorized;
    var mean_vector = ${Nn("f32",m)};
    var mean_square_vector = ${Nn("f32",m)};

    for (var h: u32 = 0u; h < uniforms.norm_size_vectorized; h++) {
      let value = ${mi(O,m,"x[h + offset]")};
      mean_vector += value;
      mean_square_vector += value * value;
    }
    let mean = ${Ht("mean_vector",m)} / uniforms.norm_size;
    let inv_std_dev = inverseSqrt(${Ht("mean_square_vector",m)} / uniforms.norm_size ${n?"":"- mean * mean"} + uniforms.epsilon);

    for (var j: u32 = 0; j < uniforms.norm_size_vectorized; j++) {
      let f32input = ${mi(O,m,"x[j + offset]")};
      let f32scale = ${mi(O,m,"scale[j]")};
      output[j + offset] = ${z[0].type.value}((f32input ${n?"":"- mean"}) * inv_std_dev * f32scale
        ${a?`+ ${mi(O,m,"bias[j]")}`:""}
      );
    }

    ${w?"mean_data_output[global_idx] = mean":""};
    ${g?"inv_std_output[global_idx] = inv_std_dev":""};
  }`},x=[{dims:o,dataType:e[0].dataType}];return w&&x.push({dims:h,dataType:1}),g&&x.push({dims:h,dataType:1}),{name:"LayerNormalization",shaderCache:{hint:`${m};${i};${n}`,inputDependencies:_},getRunData:()=>({outputs:x,dispatchGroup:{x:Math.ceil(u/64)},programUniforms:$}),getShaderSource:T}},Qu=(e,t)=>{Ku(e.inputs),e.compute(Zu(e.inputs,t,e.outputCount))}}),Xu,Yu,Zp=k(()=>{$e(),er(),rr(),Xu=e=>{if(!e||e.length!==2)throw new Error("MatMul requires 2 inputs.");if(e[0].dims[e[0].dims.length-1]!==e[1].dims[e[1].dims.length-2])throw new Error("shared dimension does not match.")},Yu=e=>{Xu(e.inputs);let t=fi.calcShape(e.inputs[0].dims,e.inputs[1].dims,!0);if(!t)throw new Error("Can't use matmul on the given tensors");let i=t[t.length-1],n=e.inputs[0].dims[e.inputs[0].dims.length-1];if(i<8&&n<8)e.compute(Jn(e.inputs,{activation:""},t));else{let r=t[t.length-2],s=M.size(e.inputs[0].dims.slice(0,-2)),a=M.size(e.inputs[1].dims.slice(0,-2));if(s!==1&&r===1&&a===1){let o=e.inputs[0].reshape([1,s,n]),l=e.inputs[1].reshape([1,n,i]),u=[1,s,i],d=[o,l];e.compute(Xi(d,{activation:""},t,u),{inputs:d})}else e.compute(Xi(e.inputs,{activation:""},t))}}}),Ju,ed,td,id,nd,Qp=k(()=>{_e(),$e(),Xe(),xe(),Ju=(e,t)=>{if(e.length<3||e.length>4)throw new Error("MatMulNBits requires 3 or 4 inputs");let i=e[0],n=i.dims.length;if(i.dims[n-1]!==t.k)throw new Error("The last dim of input shape does not match the k value");let r=Math.floor((t.k+t.blockSize-1)/t.blockSize),s=t.blockSize/8*t.bits,a=e[1];if(!M.areEqual(a.dims,[t.n,r,s]))throw new Error("The second inputs must be 3D tensor with shape N X nBlocksPerCol X blobSize");let o=e[2].dims;if(M.size(o)!==t.n*r)throw new Error("scales input size error.");if(e.length===4){let l=e[3].dims,u=t.n*(t.bits===8?r:Math.floor((r*t.bits+7)/8));if(M.size(l)!==u)throw new Error("zeroPoints input size error.")}},ed=(e,t)=>{let i=e[0].dims,n=i.length,r=i[n-2],s=t.k,a=t.n,o=i.slice(0,n-2),l=M.size(o),u=e[1].dims[2]/4,d=e[0].dataType,c=Qe(t.k),p=Qe(u),h=Qe(a),m=o.concat([r,a]),_=r>1&&a/h%2===0?2:1,$=M.size(m)/h/_,w=64,g=[],T=[l,r,s/c],x=M.convertShape(e[1].dims).slice();x.splice(-1,1,u/p),g.push(...le(T)),g.push(...le(x)),g.push(...le(e[2].dims)),e.length===4&&g.push(...le(M.convertShape(e[3].dims)));let I=[l,r,a/h];g.push(...le(I));let O=z=>{let N=T.length,q=B("a",e[0].dataType,N,c),te=B("b",12,x.length,p),ye=B("scales",e[2].dataType,e[2].dims.length),de=[q,te,ye],be=e.length===4?B("zero_points",12,e[3].dims.length):void 0;be&&de.push(be);let ne=I.length,Te=re("output",e[0].dataType,ne,h),he=at(e[0].dataType),ae=(()=>{switch(c){case 1:return`array<${he}, 8>`;case 2:return`mat4x2<${he}>`;case 4:return`mat2x4<${he}>`;default:throw new Error(`${c}-component is not supported.`)}})(),Oe=()=>{let W=`
          // reuse a data
            var input_offset = ${q.indicesToOffset(`${q.type.indices}(batch, row, word_offset)`)};
            var a_data: ${ae};
            for (var j: u32 = 0; j < ${8/c}; j++) {
              a_data[j] = ${q.getByOffset("input_offset")};
              input_offset++;
            }
          `;for(let ee=0;ee<h*_;ee++)W+=`
            b_value = ${p===1?`b${ee}_data`:`b${ee}_data[i]`};
            b_value_lower = unpack4xU8(b_value & b_mask);
            b_value_upper = unpack4xU8((b_value >> 4) & b_mask);
            b_quantized_values = ${ae}(${Array.from({length:4},(Se,Le)=>`${he}(b_value_lower[${Le}]), ${he}(b_value_upper[${Le}])`).join(", ")});
            b_dequantized_values = ${c===1?`${ae}(${Array.from({length:8},(Se,Le)=>`(b_quantized_values[${Le}] - ${be?`zero_point${ee}`:"zero_point"}) * scale${ee}`).join(", ")});`:`(b_quantized_values - ${ae}(${Array(8).fill(`${be?`zero_point${ee}`:"zero_point"}`).join(",")})) * scale${ee};`};
            workgroup_shared[local_id.x * ${_} + ${Math.floor(ee/h)}]${h>1?`[${ee%h}]`:""} += ${Array.from({length:8/c},(Se,Le)=>`${c===1?`a_data[${Le}] * b_dequantized_values[${Le}]`:`dot(a_data[${Le}], b_dequantized_values[${Le}])`}`).join(" + ")};
          `;return W},ce=()=>{let W=`
            var col_index = col * ${h};
            ${be?`
            let zero_point_bytes_per_col = (nBlocksPerCol + 1) / 2;
            var zero_point_byte_count: u32;
            var zero_point_word_index: u32;
            var zero_point_byte_offset: u32;
            let zero_point_nibble_offset: u32 = block & 0x1u;
            var zero_point_bits_offset: u32;
            var zero_point_word: u32;`:`
            // The default zero point is 8 for unsigned 4-bit quantization.
            let zero_point = ${he}(8);`}
            `;for(let ee=0;ee<h*_;ee++)W+=`
            let scale${ee} = ${ye.getByOffset("col_index * nBlocksPerCol + block")};
            ${be?`
            zero_point_byte_count = col_index * zero_point_bytes_per_col + (block >> 0x1u);
            zero_point_word_index = zero_point_byte_count >> 0x2u;
            zero_point_byte_offset = zero_point_byte_count & 0x3u;
            zero_point_bits_offset = (zero_point_byte_offset << 3) + (zero_point_nibble_offset << 2);
            zero_point_word = ${be.getByOffset("zero_point_word_index")} >> zero_point_bits_offset;
            let zero_point${ee} = ${he}((zero_point_word) & 0xFu);`:""}
            col_index += 1;`;return W},Ge=()=>{let W=`col_index = col * ${h};`;for(let ee=0;ee<h*_;ee++)W+=`
            let b${ee}_data = ${te.getByIndices(`${te.type.indices}(col_index, block, word)`)};
            col_index += 1;`;return W+=`
            var b_value: u32;
            let b_mask: u32 = 0x0F0F0F0Fu;
            var b_value_lower: vec4<u32>;
            var b_value_upper: vec4<u32>;
            var b_quantized_values: ${ae};
            var b_dequantized_values: ${ae};`,W};return`
        var<workgroup> workgroup_shared: array<${Te.type.value}, ${_*w}>;
        ${z.declareVariables(...de,Te)}
        ${z.mainStart([w,1,1])}
          let output_indices = ${Te.offsetToIndices(`(global_idx / ${w}) * ${_}`)};
          let col = output_indices[2];
          let row = output_indices[1];
          let batch = output_indices[0];
          let nBlocksPerCol = uniforms.b_shape[1];

          for (var block = local_id.x; block < nBlocksPerCol; block += ${w}) {
            //process one block
            var word_offset: u32 = block * ${t.blockSize/c};
            ${ce()}
            for (var word: u32 = 0; word < ${u}; word += ${p}) {
              ${Ge()}
              for (var i: u32 = 0; i < ${p}; i++) {
                ${Oe()}
                word_offset += ${8/c};
              }
            }
          }
          workgroupBarrier();

          if (local_id.x < ${_}) {
            var output_value: ${Te.type.value} = ${Te.type.value}(0);
            var workgroup_shared_offset: u32 = local_id.x;
            for (var b: u32 = 0u; b < ${w}u; b++) {
              output_value += workgroup_shared[workgroup_shared_offset];
              workgroup_shared_offset += ${_};
            }
            ${Te.setByIndices(`${Te.type.indices}(batch, row, col + local_id.x)`,"output_value")};
          }
        }`};return{name:"MatMulNBits",shaderCache:{hint:`${t.blockSize};${t.bits};${c};${p};${h};${_};${w}`,inputDependencies:Array(e.length).fill("rank")},getRunData:()=>({outputs:[{dims:m,dataType:d}],dispatchGroup:{x:$},programUniforms:g}),getShaderSource:O}},td=(e,t)=>{let i=e[0].dims,n=i.length,r=i[n-2],s=t.k,a=t.n,o=i.slice(0,n-2),l=M.size(o),u=e[1].dims[2]/4,d=e[0].dataType,c=Qe(t.k),p=Qe(u),h=o.concat([r,a]),m=128,_=a%8===0?8:a%4===0?4:1,$=m/_,w=$*p*8,g=w/c,T=w/t.blockSize,x=M.size(h)/_,I=[],O=[l,r,s/c],z=M.convertShape(e[1].dims).slice();z.splice(-1,1,u/p),I.push(...le(O)),I.push(...le(z)),I.push(...le(e[2].dims)),e.length===4&&I.push(...le(M.convertShape(e[3].dims)));let N=[l,r,a];I.push(...le(N));let q=te=>{let ye=O.length,de=B("a",e[0].dataType,ye,c),be=B("b",12,z.length,p),ne=B("scales",e[2].dataType,e[2].dims.length),Te=[de,be,ne],he=e.length===4?B("zero_points",12,e[3].dims.length):void 0;he&&Te.push(he);let ae=N.length,Oe=re("output",e[0].dataType,ae),ce=at(e[0].dataType),Ge=()=>{switch(c){case 1:return`
          let a_data0 = vec4<${ce}>(sub_a[word_offset], sub_a[word_offset + 1], sub_a[word_offset + 2], sub_a[word_offset + 3]);
          let a_data1 = vec4<${ce}>(sub_a[word_offset + 4], sub_a[word_offset + 5], sub_a[word_offset + 6], sub_a[word_offset + 7]);`;case 2:return`
          let a_data0 = vec4<${ce}>(sub_a[word_offset], sub_a[word_offset + 1]);
          let a_data1 = vec4<${ce}>(sub_a[word_offset + 2], sub_a[word_offset + 3]);`;case 4:return`
          let a_data0 = sub_a[word_offset];
          let a_data1 = sub_a[word_offset + 1];`;default:throw new Error(`${c}-component is not supported.`)}};return`
        var<workgroup> sub_a: array<${de.type.value}, ${g}>;
        var<workgroup> inter_results: array<array<${Oe.type.value}, ${$}>, ${_}>;
        ${te.declareVariables(...Te,Oe)}
        ${te.mainStart([$,_,1])}
          let output_indices = ${Oe.offsetToIndices(`workgroup_index * ${_}`)};
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
                sub_a[a_offset] = ${de.getByIndices(`${de.type.indices}(batch, row, a_col)`)};
              } else {
                sub_a[a_offset] = ${de.type.value}(0);
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
            let zero_point = ${ce}((zero_point_word) & 0xFu);`:`
            // The default zero point is 8 for unsigned 4-bit quantization.
            let zero_point = ${ce}(8);`}
            let scale = ${ne.getByOffset("b_row * n_blocks_per_col + block")};
            let b_data = ${be.getByIndices(`${be.type.indices}(b_row, block, 0)`)};
            var word_offset = local_id.x * ${t.blockSize/c};
            for (var i: u32 = 0; i < ${p}; i++) {
              ${Ge()}
              let b_value = ${p===1?"b_data":"b_data[i]"};
              let b_value_lower = unpack4xU8(b_value & 0x0F0F0F0Fu);
              let b_value_upper = unpack4xU8((b_value >> 4) & 0x0F0F0F0Fu);
              let b_quantized_values = mat2x4<${ce}>(${Array.from({length:4},(W,ee)=>`${ce}(b_value_lower[${ee}]), ${ce}(b_value_upper[${ee}])`).join(", ")});
              let b_dequantized_values = (b_quantized_values - mat2x4<${ce}>(${Array(8).fill("zero_point").join(",")})) * scale;
              inter_results[local_id.y][local_id.x] += ${Array.from({length:2},(W,ee)=>`${`dot(a_data${ee}, b_dequantized_values[${ee}])`}`).join(" + ")};
              word_offset += ${8/c};
            }
            workgroupBarrier();
          }

          if (local_idx < ${_}) {
            var output_value: ${Oe.type.value} = ${Oe.type.value}(0);
            for (var b = 0u; b < ${$}; b++) {
              output_value += inter_results[local_idx][b];
            }
            if (col + local_idx < uniforms.output_shape[2])
            {
              ${Oe.setByIndices(`${Oe.type.indices}(batch, row, col + local_idx)`,"output_value")}
            }
          }
        }`};return{name:"BlockwiseMatMulNBits32",shaderCache:{hint:`${t.blockSize};${c};${p};${$};${_}`,inputDependencies:Array(e.length).fill("rank")},getRunData:()=>({outputs:[{dims:h,dataType:d}],dispatchGroup:{x},programUniforms:I}),getShaderSource:q}},id=(e,t)=>{Ju(e.inputs,t),t.blockSize===32&&e.adapterInfo.isVendor("intel")&&e.adapterInfo.isArchitecture("gen-12lp")?e.compute(td(e.inputs,t)):e.compute(ed(e.inputs,t))},nd=e=>De(e)}),rd,sd,ad,od,ld,ud,dd,cd,pd,Xp=k(()=>{_e(),$e(),xe(),rd=e=>{if(!e||e.length<1)throw new Error("Too few inputs");if(e[0].dataType!==1&&e[0].dataType!==10)throw new Error("Input type must be float or float16.");if(e.length>=2){let t=e[0].dims.length*2===e[1].dims[0];if(e.length===4&&(t=e[3].dims[0]*2===e[1].dims[0]),!t)throw new Error("The pads should be a 1D tensor of shape [2 * input_rank] or [2 * num_axes].")}},sd=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
            k = i32(${e.indicesGet("indices",r)}) - ${se("uniforms.pads",r,i)};
            if (k < 0) {
              break;
            }
            if (k >= i32(${se("uniforms.x_shape",r,t)})) {
              break;
            }
            offset += k * i32(${se("uniforms.x_strides",r,t)});
        `;return`
          value = ${e.type.value}(uniforms.constant_value);
          for (var i = 0; i < 1; i++) {
            var offset = 0;
            var k = 0;
            ${n}
            value = x[offset];
          }
      `},ad=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
                k = i32(${e.indicesGet("indices",r)}) - ${se("uniforms.pads",r,i)};
                if (k < 0) {
                  k = -k;
                }
                {
                  let _2n_1 = 2 * (i32(${se("uniforms.x_shape",r,t)}) - 1);
                  k = k % _2n_1;
                  if(k >= i32(${se("uniforms.x_shape",r,t)})) {
                    k = _2n_1 - k;
                  }
                }
                offset += k * i32(${se("uniforms.x_strides",r,t)});
            `;return`
              var offset = 0;
              var k = 0;
              ${n}
              value = x[offset];
          `},od=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
                k = i32(${e.indicesGet("indices",r)}) - ${se("uniforms.pads",r,i)};
                if (k < 0) {
                  k = 0;
                }
                if (k >= i32(${se("uniforms.x_shape",r,t)})) {
                  k = i32(${se("uniforms.x_shape",r,t)}) - 1;
                }
                offset += k * i32(${se("uniforms.x_strides",r,t)});
            `;return`
              var offset = 0;
              var k = 0;
              ${n}
              value = x[offset];
          `},ld=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
                k = i32(${e.indicesGet("indices",r)}) - ${se("uniforms.pads",r,i)};
                if (k < 0)  {
                  k += i32(${se("uniforms.x_shape",r,t)}]);
                }
                if (k >= i32(${se("uniforms.x_shape",r,t)})) {
                  k -= i32(${se("uniforms.x_shape",r,t)});
                }
                offset += k * i32(${se("uniforms.x_strides",r,t)});
            `;return`
              var offset = 0;
              var k = 0;
              ${n}
              value = x[offset];
          `},ud=(e,t,i)=>{switch(i.mode){case 0:return sd(e,t,i.pads.length);case 1:return ad(e,t,i.pads.length);case 2:return od(e,t,i.pads.length);case 3:return ld(e,t,i.pads.length);default:throw new Error("Invalid mode")}},dd=(e,t)=>{let i=M.padShape(e[0].dims.slice(),t.pads),n=e[0].dims,r=M.size(i),s=[{type:12,data:r},{type:6,data:t.pads}],a=e.length>=3&&e[2].data;t.mode===0&&s.push({type:a?e[2].dataType:1,data:t.value}),s.push(...le(e[0].dims,i));let o=["rank"],l=u=>{let d=re("output",e[0].dataType,i.length),c=B("x",e[0].dataType,n.length),p=c.type.value,h=ud(d,n.length,t),m=[{name:"output_size",type:"u32"},{name:"pads",type:"i32",length:t.pads.length}];return t.mode===0&&m.push({name:"constant_value",type:a?p:"f32"}),`
            ${u.registerUniforms(m).declareVariables(c,d)}
            ${u.mainStart()}
            ${u.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

            let indices = ${d.offsetToIndices("global_idx")};

            var value = ${p}(0);
            ${h}
            output[global_idx] = value;
        }`};return{name:"Pad",shaderCache:{hint:`${t.mode}${a}`,inputDependencies:o},getRunData:()=>({outputs:[{dims:i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(M.size(i)/64)},programUniforms:s}),getShaderSource:l}},cd=(e,t)=>{if(e.length>1){let i=e[1].getBigInt64Array(),n=e.length>=3&&e[2].data?e[2].dataType===10?e[2].getUint16Array()[0]:e[2].getFloat32Array()[0]:0,r=e[0].dims.length,s=new Int32Array(2*r).fill(0);if(e.length>=4){let o=e[3].getBigInt64Array();for(let l=0;l<o.length;l++)s[Number(o[l])]=Number(i[l]),s[Number(o[l])+r]=Number(i[l+o.length])}else i.forEach((o,l)=>s[Number(l)]=Number(o));let a=[];return s.forEach(o=>a.push(o)),{mode:t.mode,value:n,pads:a}}else return t},pd=(e,t)=>{rd(e.inputs);let i=cd(e.inputs,t);e.compute(dd(e.inputs,i),{inputs:[0]})}}),Ai,wr,br,vr,$r,fd,hd,xr,Sr,md,gd,kr,_d,yd,Tr,wd,bd,vd,$d,Yp=k(()=>{wt(),_e(),$e(),xe(),Ai=e=>{if(oe.webgpu.validateInputContent&&(!e||e.length!==1))throw new Error("Pool ops requires 1 input.")},wr=(e,t,i)=>{let n=t.format==="NHWC",r=e.dims.slice();n&&r.splice(1,0,r.pop());let s=Object.hasOwnProperty.call(t,"dilations"),a=t.kernelShape.slice(),o=t.strides.slice(),l=s?t.dilations.slice():[],u=t.pads.slice();Wi.adjustPoolAttributes(i,r,a,o,l,u);let d=Wi.computePoolOutputShape(i,r,o,l,a,u,t.autoPad),c=Object.assign({},t);s?Object.assign(c,{kernelShape:a,strides:o,pads:u,dilations:l,cacheKey:t.cacheKey}):Object.assign(c,{kernelShape:a,strides:o,pads:u,cacheKey:t.cacheKey});let p=d.slice();return p.push(p.splice(1,1)[0]),[c,n?p:d]},br=(e,t)=>{let i=t.format==="NHWC",n=M.size(e),r=M.size(t.kernelShape),s=[{type:12,data:n},{type:12,data:r}],a=[{name:"outputSize",type:"u32"},{name:"kernelSize",type:"u32"}];if(t.kernelShape.length<=2){let o=t.kernelShape[t.kernelShape.length-1],l=t.strides[t.strides.length-1],u=t.pads[t.pads.length/2-1],d=t.pads[t.pads.length-1],c=!!(u+d);s.push({type:12,data:o},{type:12,data:l},{type:12,data:u},{type:12,data:d}),a.push({name:"kw",type:"u32"},{name:"sw",type:"u32"},{name:"pwStart",type:"u32"},{name:"pwEnd",type:"u32"});let p=!1;if(t.kernelShape.length===2){let h=t.kernelShape[t.kernelShape.length-2],m=t.strides[t.strides.length-2],_=t.pads[t.pads.length/2-2],$=t.pads[t.pads.length-2];p=!!(_+$),s.push({type:12,data:h},{type:12,data:m},{type:12,data:_},{type:12,data:$}),a.push({name:"kh",type:"u32"},{name:"sh",type:"u32"},{name:"phStart",type:"u32"},{name:"phEnd",type:"u32"})}return[s,a,!0,c,p]}else{if(i)throw new Error("Pooling with kernelShape.length > 2 is not supported for NHWC format.");let o=M.computeStrides(t.kernelShape);s.push({type:12,data:o},{type:12,data:t.pads},{type:12,data:t.strides}),a.push({name:"kernelStrides",type:"u32",length:o.length},{name:"pads",type:"u32",length:t.pads.length},{name:"strides",type:"u32",length:t.strides.length});let l=t.pads.reduce((u,d)=>u+d);return[s,a,!!l,!1,!1]}},vr=(e,t,i,n,r,s,a,o,l,u,d,c)=>{let p=r.format==="NHWC",h=t.type.value,m=re("output",t.type.tensor,n);if(r.kernelShape.length<=2){let _="",$="",w="",g=i-(p?2:1);if(d?_=`
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
                `,w=`
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
              ${w}
              ${a}

              output[global_idx] = value;
            }`}else{if(p)throw new Error("Pooling with kernelShape.length > 2 is not supported for NHWC format.");let _=r.kernelShape.length,$=r.pads.length,w="";return u?w=`
                if (xIndices[j] >= uniforms.x_shape[j]) {
                  pad++;
                  isPad = true;
                  break;
                }
              }
              if (!isPad) {
                let x_val = x[${t.indicesToOffset("xIndices")}];
                ${s}
              }`:w=`
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
                  offsets[j] = offset / ${se("uniforms.kernelStrides","j",_)};
                  offset -= offsets[j] * ${se("uniforms.kernelStrides","j",_)};
                }
                offsets[${_-1}] = offset;

                isPad = false;
                for (var j = ${i-_}u; j < ${i}u; j++) {
                  xIndices[j] = indices[j] * ${se("uniforms.strides",`j - ${i-_}u`,_)}
                    + offsets[j - ${i-_}u] - ${se("uniforms.pads","j - 2u",$)};
                  ${w}
              }
              ${a}

              output[global_idx] = value;
            }`}},$r=e=>`${e.format};${e.ceilMode};${e.autoPad};${e.kernelShape.length}`,fd=e=>`${$r(e)};${e.countIncludePad}`,hd=e=>`${$r(e)};${e.storageOrder};${e.dilations}`,xr=e=>({format:e.format,autoPad:["NOTSET","VALID","SAME_UPPER","SAME_LOWER"][e.auto_pad],ceilMode:e.ceil_mode,kernelShape:e.kernel_shape,strides:e.strides,pads:e.pads}),Sr=(e,t,i,n)=>{let[r,s]=wr(t,n,i),a=B("x",t.dataType,t.dims.length),o=a.type.value,l="value += x_val;",u="";r.countIncludePad?u+=`value /= ${o}(uniforms.kernelSize);`:u+=`value /= ${o}(i32(uniforms.kernelSize) - pad);`;let[d,c,p,h,m]=br(s,r);d.push(...le(t.dims,s));let _=["rank"];return{name:e,shaderCache:{hint:`${n.cacheKey};${p};${h};${m}`,inputDependencies:_},getRunData:()=>({outputs:[{dims:s,dataType:t.dataType}],dispatchGroup:{x:Math.ceil(M.size(s)/64)},programUniforms:d}),getShaderSource:$=>vr($,a,t.dims.length,s.length,r,l,u,0,c,p,h,m)}},md=e=>{let t=e.count_include_pad!==0,i=xr(e);if(i.ceilMode!==0)throw new Error("using ceil() in shape computation is not yet supported for AveragePool");let n={countIncludePad:t,...i,cacheKey:""};return{...n,cacheKey:fd(n)}},gd=(e,t)=>{Ai(e.inputs),e.compute(Sr("AveragePool",e.inputs[0],!1,t))},kr={autoPad:"",ceilMode:0,countIncludePad:!1,kernelShape:[],strides:[],pads:[],storageOrder:0,dilations:[]},_d=e=>{let t=e.format;return{format:t,...kr,cacheKey:t}},yd=(e,t)=>{Ai(e.inputs),e.compute(Sr("GlobalAveragePool",e.inputs[0],!0,t))},Tr=(e,t,i,n)=>{let[r,s]=wr(t,n,i),a=`
      value = max(x_val, value);
    `,o="",l=B("x",t.dataType,t.dims.length),u=["rank"],[d,c,p,h,m]=br(s,r);return d.push(...le(t.dims,s)),{name:e,shaderCache:{hint:`${n.cacheKey};${p};${h};${m}`,inputDependencies:u},getRunData:()=>({outputs:[{dims:s,dataType:t.dataType}],dispatchGroup:{x:Math.ceil(M.size(s)/64)},programUniforms:d}),getShaderSource:_=>vr(_,l,t.dims.length,s.length,r,a,o,t.dataType===10?-65504:-1e5,c,p,h,m)}},wd=(e,t)=>{Ai(e.inputs),e.compute(Tr("MaxPool",e.inputs[0],!1,t))},bd=e=>{let t=e.storage_order,i=e.dilations,n=xr(e);if(t!==0)throw new Error("column major storage order is not yet supported for MaxPool");if(n.ceilMode!==0)throw new Error("using ceil() in shape computation is not yet supported for MaxPool");let r={storageOrder:t,dilations:i,...n,cacheKey:""};return{...r,cacheKey:hd(r)}},vd=e=>{let t=e.format;return{format:t,...kr,cacheKey:t}},$d=(e,t)=>{Ai(e.inputs),e.compute(Tr("GlobalMaxPool",e.inputs[0],!0,t))}}),xd,Sd,kd,Td,Jp=k(()=>{_e(),$e(),Xe(),xe(),xd=(e,t)=>{if(e.length<2||e.length>3)throw new Error("DequantizeLinear requires 2 or 3 inputs.");if(e.length===3&&e[1].dims===e[2].dims)throw new Error("x-scale and x-zero-point must have the same shape.");if(e.length===3&&e[0].dataType!==e[2].dataType)throw new Error("x and x-zero-point must have the same data type.");if(e[0].dataType===6&&e.length>2)throw new Error("In the case of dequantizing int32 there is no zero point.");if(e[1].dims.length!==0&&e[1].dims.length!==1&&e[1].dims.length!==e[0].dims.length)throw new Error("scale input must be a scalar, a 1D tensor, or have the same rank as the input tensor.");if(e.length>2){if(e[0].dataType!==e[2].dataType)throw new Error("x and x-zero-point must have the same data type.");if(e[1].dims.length!==e[2].dims.length)throw new Error("scale and zero-point inputs must have the same rank.");if(!e[1].dims.map((i,n)=>i===e[2].dims[n]).reduce((i,n)=>i&&n,!0))throw new Error("scale and zero-point inputs must have the same shape.")}if(t.blockSize>0){if(e[1].dims.length===0||e[1].dims.length===1&&e[1].dims[0]===1)throw new Error("blockSize must be set only for block quantization.");if(!e[1].dims.map((r,s)=>s===t.axis||r===e[0].dims[s]).reduce((r,s)=>r&&s,!0))throw new Error("For block qunatization, scale input shape to match the input shape except for the axis");if(e[1].dims.length!==e[0].dims.length)throw new Error("For block qunatization the scale input rank must be the same as the x rank.");let i=e[0].dims[t.axis],n=e[1].dims[t.axis];if(t.blockSize<Math.ceil(i/n)||t.blockSize>Math.ceil(i/(n-1)-1))throw new Error("blockSize must be with in the range [ceil(dI / Si), ceil(dI / (Si - 1) - 1)].")}},Sd=(e,t)=>{let i=M.normalizeAxis(t.axis,e[0].dims.length),n=e[0].dataType,r=n===3,s=e[0].dims,a=e[1].dataType,o=M.size(s),l=n===3||n===2,u=l?[Math.ceil(M.size(e[0].dims)/4)]:e[0].dims,d=e[1].dims,c=e.length>2?e[2]:void 0,p=c?l?[Math.ceil(M.size(c.dims)/4)]:c.dims:void 0,h=d.length===0||d.length===1&&d[0]===1,m=h===!1&&d.length===1,_=Qe(o),$=h&&(!l||_===4),w=$?_:1,g=$&&!l?_:1,T=B("input",l?12:n,u.length,g),x=B("scale",a,d.length),I=c?B("zero_point",l?12:n,p.length):void 0,O=re("output",a,s.length,w),z=[T,x];I&&z.push(I);let N=[u,d];c&&N.push(p);let q=[{type:12,data:o/w},{type:12,data:i},{type:12,data:t.blockSize},...le(...N,s)],te=ye=>{let de=[{name:"output_size",type:"u32"},{name:"axis",type:"u32"},{name:"block_size",type:"u32"}];return`
      ${ye.registerUniforms(de).declareVariables(...z,O)}
      ${ye.mainStart()}
          ${ye.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
          let output_indices = ${O.offsetToIndices("global_idx")};

          // Set input x
          ${l?`
            let input = ${T.getByOffset("global_idx / 4")};
            let x_vec = ${r?"unpack4xI8(input)":"unpack4xU8(input)"};
            let x_value = ${w===1?"x_vec[global_idx % 4]":"x_vec"};`:`let x_value = ${T.getByOffset("global_idx")};`};

          // Set scale input
          ${h?`let scale_value= ${x.getByOffset("0")}`:m?`
            let scale_index = ${O.indicesGet("output_indices","uniforms.axis")};
            let scale_value= ${x.getByOffset("scale_index")};`:`
            var scale_indices: ${x.type.indices} = output_indices;
            let index = ${x.indicesGet("scale_indices","uniforms.axis")} / uniforms.block_size;
            ${x.indicesSet("scale_indices","uniforms.axis","index")};
            let scale_value= ${x.getByIndices("scale_indices")};`};

          // Set zero-point input
          ${I?h?l?`
                let zero_point_input = ${I.getByOffset("0")};
                let zero_point_vec =  ${r?"unpack4xI8(zero_point_input)":"unpack4xU8(zero_point_input)"};
                let zero_point_value= zero_point_vec[0]`:`let zero_point_value = ${I.getByOffset("0")}`:m?l?`
                let zero_point_index = ${O.indicesGet("output_indices","uniforms.axis")};
                let zero_point_input = ${I.getByOffset("zero_point_index / 4")};
                let zero_point_vec =  ${r?"unpack4xI8(zero_point_input)":"unpack4xU8(zero_point_input)"};
                let zero_point_value = zero_point_vec[zero_point_index % 4]`:`
                let zero_point_index = ${O.indicesGet("output_indices","uniforms.axis")};
                let zero_point_value = ${I.getByOffset("zero_point_index")};`:l?`
                let zero_point_offset = ${x.indicesToOffset("scale_indices")};
                let zero_point_input = ${I.getByOffset("zero_point_offset / 4")};
                let zero_point_vec = ${r?"unpack4xI8(zero_point_input)":"unpack4xU8(zero_point_input)"};
                let zero_point_value = zero_point_vec[zero_point_offset % 4];`:`let zero_point_value = ${I.getByIndices("scale_indices")};`:`let zero_point_value = ${l?r?"i32":"u32":T.type.value}(0);`};
      // Compute and write output
      ${O.setByOffset("global_idx",`${O.type.value}(x_value - zero_point_value) * scale_value`)};
      }`};return{name:"DequantizeLinear",shaderCache:{hint:t.cacheKey,inputDependencies:I?["rank","rank","rank"]:["rank","rank"]},getShaderSource:te,getRunData:()=>({outputs:[{dims:s,dataType:a}],dispatchGroup:{x:Math.ceil(o/w/64),y:1,z:1},programUniforms:q})}},kd=(e,t)=>{xd(e.inputs,t),e.compute(Sd(e.inputs,t))},Td=e=>De({axis:e.axis,blockSize:e.blockSize})}),Ed,Cd,Id,ef=k(()=>{wt(),_e(),xe(),Ed=(e,t,i)=>{let n=e===t,r=e<t&&i<0,s=e>t&&i>0;if(n||r||s)throw new Error("Range these inputs' contents are invalid.")},Cd=(e,t,i,n)=>{let r=Math.abs(Math.ceil((t-e)/i)),s=[r],a=r,o=[{type:12,data:a},{type:n,data:e},{type:n,data:i},...le(s)],l=u=>{let d=re("output",n,s.length),c=d.type.value,p=[{name:"outputSize",type:"u32"},{name:"start",type:c},{name:"delta",type:c}];return`
        ${u.registerUniforms(p).declareVariables(d)}
        ${u.mainStart()}
        ${u.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
        output[global_idx] = uniforms.start + ${c}(global_idx) * uniforms.delta;
      }`};return{name:"Range",shaderCache:{hint:`${n}`},getShaderSource:l,getRunData:()=>({outputs:[{dims:s,dataType:n}],dispatchGroup:{x:Math.ceil(a/64)},programUniforms:o})}},Id=e=>{let t=0,i=0,n=0;e.inputs[0].dataType===6?(t=e.inputs[0].getInt32Array()[0],i=e.inputs[1].getInt32Array()[0],n=e.inputs[2].getInt32Array()[0]):e.inputs[0].dataType===1&&(t=e.inputs[0].getFloat32Array()[0],i=e.inputs[1].getFloat32Array()[0],n=e.inputs[2].getFloat32Array()[0]),oe.webgpu.validateInputContent&&Ed(t,i,n),e.compute(Cd(t,i,n,e.inputs[0].dataType),{inputs:[]})}}),Ad,zd,Rd,Od,tf=k(()=>{_e(),$e(),Xe(),xe(),Ad=(e,t,i,n)=>{if(e!=="none"&&n!=="i32"&&n!=="u32"&&n!=="f32")throw new Error(`Input ${n} is not supported with reduction ${e}.`);let r=`{
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
                ${r}max(bitcast<f32>(oldValue), (${i}))${s}`;case"min":return n==="i32"||n==="u32"?`atomicMin(&${t}, bitcast<${n}>(${i}));`:`${r}min(bitcast<${n}>(oldValue), (${i}))${s}`;case"mul":return`${r}(bitcast<${n}>(oldValue) * (${i}))${s}`;default:throw new Error(`Reduction ${e} is not supported.`)}},zd=(e,t)=>{let i=e[0].dims,n=e[1].dims,r=i,s=1,a=Math.ceil(M.sizeToDimension(n,n.length-1)/s),o=n[n.length-1],l=M.sizeFromDimension(i,o),u=[{type:12,data:a},{type:12,data:o},{type:12,data:l},...le(e[1].dims,e[2].dims,r)],d=c=>{let p=B("indices",e[1].dataType,e[1].dims.length),h=B("updates",e[2].dataType,e[2].dims.length,s),m=t.reduction!=="none"&&t.reduction!==""?Ps("output",e[0].dataType,r.length):re("output",e[0].dataType,r.length,s);return`
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
    ${Ad(t.reduction,"output[data_offset + i]","value",m.type.value)}
  }

      }`};return{name:"ScatterND",shaderCache:{hint:`${t.cacheKey}_${t.reduction}`,inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:r,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(a/64)},programUniforms:u}),getShaderSource:d}},Rd=e=>De({reduction:e.reduction}),Od=(e,t)=>{e.compute(zd(e.inputs,t),{inputs:[e.inputs[1],e.inputs[2]],outputs:[]})}}),Md,Fd,Dd,Er,Bd,Pd,Nd,Vd,Ld,Ud,qd,Wd,Cr,Gd,jd,Hd,Kd,Zd,Qd,Xd,nf=k(()=>{_e(),$e(),Xe(),xe(),Md=(e,t)=>{if(e.every(i=>i>0||(()=>{throw new Error("Resize requires scales input values to be positive")})),e.length>0){if(t.mode==="linear"){if(!(e.length===2||e.length===3||e.length===4&&e[0]===1&&e[1]===1||e.length===4&&e[0]===1&&e[3]===1||e.length===5&&e[0]===1&&e[1]===1))throw new Error(`For linear mode, Resize requires scales to be 2D, 3D, 4D with either two outermost or one innermost and
            one outermost scale values equal to 1, or 5D with two outermost scale values equal to 1`)}else if(t.mode==="cubic"&&!(e.length===2||e.length===4&&e[0]===1&&e[1]===1||e.length===4&&e[0]===1&&e[3]===1))throw new Error("Resize requires scales input size to be 2 or 4 for cubic mode")}},Fd=(e,t,i)=>{t.every(r=>r>=0&&r<i||(()=>{throw new Error("Resize requires axes input values to be positive and less than rank")}));let n=new Array(i).fill(1);return t.forEach((r,s)=>n[r]=e[s]),n},Dd=(e,t,i,n,r,s)=>{let[a,o,l]=i>10?[1,2,3]:[-1,e.length>1?1:-1,-1],u=e[0].dims.length;if(a>0&&e.length>a&&e[a].dims.length>0)e[a].getFloat32Array().forEach(d=>s.push(d));else if(t.coordinateTransformMode==="tf_crop_and_resize")throw new Error("Resize requires RoI input to be specified when coordinateTransformMode is tfCropAndResize");if(o>0&&e.length>o&&e[o].dims.length===1&&e[o].dims[0]>0){if(e[o].getFloat32Array().forEach(d=>n.push(d)),n.length!==0&&n.length!==u&&i>=18&&n.length!==t.axes.length)throw new Error("Resize requires scales input size to be same as input rank or axes size for opset 18 and up");Md(n,t),t.axes.length>0&&Fd(n,t.axes,u).forEach((d,c)=>n[c]=d)}if(l>0&&e.length>l&&e[l].dims.length===1&&e[l].dims[0]>0&&(e[l].getBigInt64Array().forEach(d=>r.push(Number(d))),r.length!==0&&r.length!==u&&i>=18&&r.length!==t.axes.length))throw new Error("Resize requires sizes input size to be same as input rank or axes size for opset 18 and up");if(t.axes.length>0){if(n.length!==0&&n.length!==t.axes.length)throw new Error('Resize requires "scales" input size to be of axes rank when axes attributes is specified');if(r.length!==0&&r.length!==t.axes.length)throw new Error('Resize requires "sizes" input size to be of rank axes rank when axes attributes is specified')}if(typeof n<"u"&&typeof r<"u"&&n.length>0&&r.length>u)throw new Error("Resize requires only of scales or sizes to be specified")},Er=(e,t,i,n)=>`
  // The whole part and the fractional part are calculated separately due to inaccuracy of floating
  // point division. As an example, f32(21) / f32(7) may evaluate to 2.99... instead of 3, causing an
  // offset-by-one error later in floor().
  let big = (${e}) * (${t});
  let whole = ${n}(big / (${i}));
  let fract = ${n}(big % (${i})) / ${n}(${i});
  return whole + fract;
`,Bd=(e,t)=>`fn getOriginalCoordinateFromResizedCoordinate(xResized: u32, xScale: f32, lengthResized: u32,
     lengthOriginal: u32, roiStart: f32, roiEnd: f32) -> ${t} { `+(()=>{switch(e){case"asymmetric":return`
          if (xScale < 1.0 || floor(xScale) != xScale) {
            return ${t}(xResized) / ${t}(xScale);
          } else {
            ${Er("xResized","lengthOriginal","lengthResized",t)}
          }
        `;case"pytorch_half_pixel":return`if (lengthResized > 1) {
                    return (${t}(xResized) + 0.5) / ${t}(xScale) - 0.5;
                  } else {
                    return 0.0;
                  }`;case"tf_half_pixel_for_nn":return`return (${t}(xResized) + 0.5) / ${t}(xScale);`;case"align_corners":return`if (lengthResized == 1) {
                    return 0.0;
                  } else {
                    ${Er("xResized","lengthOriginal - 1","lengthResized - 1",t)}
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
                  return offset + ((${t}(xResized) + 0.5) / ${t}(xScale)) - 0.5;`;case"half_pixel":return`return ((${t}(xResized) + 0.5) / ${t}(xScale)) - 0.5;`;default:throw new Error(`Coordinate transform mode ${e} is not supported`)}})()+"}",Pd=(e,t,i)=>`fn getNearestPixelFromOriginal(xOriginal: ${i}, isDownSample: bool) -> ${i} {`+(()=>{switch(e){case"round_prefer_ceil":return"if (fract(xOriginal) == 0.5) {             return ceil(xOriginal);           } else {             return round(xOriginal);           }";case"floor":return"return floor(xOriginal);";case"ceil":return"return ceil(xOriginal);";case"round_prefer_floor":return"if (fract(xOriginal) == 0.5) {                     return floor(xOriginal);                   } else {                     return round(xOriginal);                   }";case"simple":default:if(t<11)return"if (isDownSample)                     {                       return ceil(xOriginal);                     } else {                       return xOriginal;                     }";throw new Error(`Nearest mode ${e} is not supported`)}})()+"}",Nd=(e,t,i)=>{let n=new Array(i).fill(0).concat(new Array(i).fill(1)),r=e.length===0?n:e.slice();return t.length>0?(t.forEach((s,a)=>{n[s]=r[a],n[a+i]=r[t.length+a]}),n):r},Vd=(e,t,i,n)=>{let r=[];if(i.length>0)if(n.length>0){if(e.forEach(s=>r.push(s)),Math.max(...n)>e.length)throw new Error("axes is out of bound");n.forEach((s,a)=>r[s]=i[a])}else i.forEach(s=>r.push(s));else{if(t.length===0)throw new Error("Resize requires either scales or sizes.");r=e.map((s,a)=>Math.round(s*t[a]))}return r},Ld=(e,t,i)=>{let n=(()=>{switch(i.keepAspectRatioPolicy){case"not_larger":return i.axes.length>0?Math.min(...i.axes.map(s=>t[s]),Number.MAX_VALUE):Math.min(...t,Number.MAX_VALUE);case"not_smaller":return i.axes.length>0?Math.max(...i.axes.map(s=>t[s]),Number.MIN_VALUE):Math.max(...t,Number.MIN_VALUE);default:throw new Error(`Keep aspect ratio policy ${i.keepAspectRatioPolicy} is not supported`)}})();t.fill(1,0,t.length);let r=e.slice();return i.axes.length>0?(i.axes.forEach(s=>t[s]=n),i.axes.forEach(s=>r[s]=Math.round(e[s]*t[s]))):(t.fill(n,0,t.length),r.forEach((s,a)=>r[a]=Math.round(s*t[a]))),r},Ud=(e,t,i,n,r)=>`
    fn calculateOriginalIndicesFromOutputIndices(output_indices: ${e.type.indices}) -> array<${e.type.value}, ${i.length}> {
      var original_indices: array<${e.type.value}, ${i.length}>;
      for (var i:u32 = 0; i < ${i.length}; i++) {
        var output_index = ${e.indicesGet("output_indices","i")};
        var scale = ${se("uniforms.scales","i",n)};
        var roi_low = ${se("uniforms.roi","i",r)};
        var roi_hi = ${se("uniforms.roi",`i + ${t.length}`,r)};
        if (scale == 1.0) {
          original_indices[i] = ${e.type.value}(output_index);
        } else {
          var input_shape_i = ${se("uniforms.input_shape","i",t.length)};
          var output_shape_i = ${se("uniforms.output_shape","i",i.length)};
          original_indices[i] = getOriginalCoordinateFromResizedCoordinate(output_index, scale, output_shape_i,
                                                                           input_shape_i, roi_low, roi_hi);
        }
      }
      return original_indices;
    }`,qd=(e,t,i,n,r,s,a)=>`
    fn calculateInputIndicesFromOutputIndices(output_indices: ${t.type.indices}) -> ${e.type.indices} {
      var input_indices: ${e.type.indices};
      for (var i:u32 = 0; i < ${n.length}; i++) {
        var output_index = ${t.indicesGet("output_indices","i")};
        var input_index: u32;
        var scale = ${se("uniforms.scales","i",r)};
        if (scale == 1.0) {
          input_index = output_index;
        } else {
          var roi_low = ${se("uniforms.roi","i",s)};
          var roi_hi = ${se("uniforms.roi",`i + ${i.length}`,s)};
          var input_shape_i = ${se("uniforms.input_shape","i",i.length)};
          var output_shape_i = ${se("uniforms.output_shape","i",n.length)};
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
    }`,Wd=(e,t)=>`
    fn checkInputIndices(input_indices: ${e.type.indices}) -> bool {
      for (var i:u32 = 0; i < ${t.length}; i++) {
        var input_index = ${e.indicesGet("input_indices","i")};
        if (input_index < 0 || input_index >= ${se("uniforms.input_shape","i",t.length)}) {
          return false;
        }
      }
      return true;
    }`,Cr=(e,t,i,n)=>e.rank>n?`
    ${e.indicesSet("input_indices",t,"channel")};
    ${e.indicesSet("input_indices",i,"batch")};
`:"",Gd=(e,t,i,n,r)=>{let[s,a,o,l]=i.length===2?[-1,0,1,-1]:[0,2,3,1],u=e.type.value;return`
    fn getInputValue(batch: u32, channel: u32, row: u32, col: u32) -> ${u} {
      var input_indices: ${e.type.indices};
      ${e.indicesSet("input_indices",a,`max(0, min(row, ${i[a]} - 1))`)};
      ${e.indicesSet("input_indices",o,`max(0, min(col, ${i[o]} - 1))`)};
      ${Cr(e,l,s,2)}
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
    }`},jd=(e,t,i,n,r,s,a,o,l,u)=>{let d=i.length===2,[c,p]=d?[0,1]:[2,3],h=e.type.value,m=_=>{let $=_===c?"row":"col";return`
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
    `},Hd=(e,t,i,n,r)=>{let[s,a,o,l,u]=i.length===3?[-1,0,1,2,-1]:[0,2,3,4,1],d=e.type.value;return`
    fn getInputValue(batch: u32, channel: u32, depth:u32, height: u32, width: u32) -> ${d} {
      var input_indices: ${e.type.indices};
      ${e.indicesSet("input_indices",a,`max(0, min(depth, ${i[a]} - 1))`)};
      ${e.indicesSet("input_indices",o,`max(0, min(height, ${i[o]} - 1))`)};
      ${e.indicesSet("input_indices",l,`max(0, min(width, ${i[l]} - 1))`)};
      ${Cr(e,u,s,3)}
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
    }`},Kd=(e,t,i,n,r,s)=>{let a=e.dims,o=Nd(s,t.axes,a.length),l=Vd(a,n,r,t.axes),u=n.slice();n.length===0&&(u=a.map((g,T)=>g===0?1:l[T]/g),t.keepAspectRatioPolicy!=="stretch"&&(l=Ld(a,u,t)));let d=re("output",e.dataType,l.length),c=B("input",e.dataType,a.length),p=M.size(l),h=a.length===l.length&&a.every((g,T)=>g===l[T]),m=t.coordinateTransformMode==="tf_crop_and_resize",_=t.extrapolationValue,$=c.type.value,w=g=>`
      ${h?"":`
      ${Bd(t.coordinateTransformMode,$)};
      ${(()=>{switch(t.mode){case"nearest":return`
              ${Wd(c,a)};
              ${Pd(t.nearestMode,i,$)};
              ${qd(c,d,a,l,u.length,o.length,m)};
              `;case"linear":return`
              ${Ud(d,a,l,u.length,o.length)};
              ${(()=>{if(a.length===2||a.length===4)return`${Gd(c,d,a,m,_)}`;if(a.length===3||a.length===5)return`${Hd(c,d,a,m,_)}`;throw Error("Linear mode only supports input dims 2, 3, 4 and 5 are supported in linear mode.")})()};
            `;case"cubic":return`
            ${(()=>{if(a.length===2||a.length===4)return`${jd(c,d,a,l,u,o,t.cubicCoeffA,m,t.extrapolationValue,t.excludeOutside)}`;throw Error("Cubic mode only supports input dims 2 and 4 are supported in linear mode.")})()};
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
      }`;return{name:"Resize",shaderCache:{hint:`${t.cacheKey}|${i}|${u.length>0?t.mode==="cubic"?u:u.length:""}|${r.length>0?r:""}|${o.length>0?o:""}|${h}|${t.mode==="nearest"?a.length:a}`,inputDependencies:["rank"]},getShaderSource:w,getRunData:()=>({outputs:[{dims:l,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:[{type:12,data:p},{type:1,data:u},{type:1,data:o},...le(a,l)]})}},Zd=e=>{let t=e.customDataBuffer;return new Uint32Array(t,t.byteOffset,1)[0]},Qd=(e,t)=>{let i=[],n=[],r=[],s=Zd(e);if(t.antialias!==0)throw Error("Only default value (0) for Antialias attribute is supported");Dd(e.inputs,t,s,i,n,r),e.compute(Kd(e.inputs[0],t,s,i,n,r),{inputs:[0]})},Xd=e=>{let t=e.antialias,i=e.axes,n=e.coordinateTransformMode,r=e.cubicCoeffA,s=e.excludeOutside!==0,a=e.extrapolationValue,o=e.keepAspectRatioPolicy,l=e.mode,u=e.nearestMode===""?"simple":e.nearestMode;return De({antialias:t,axes:i,coordinateTransformMode:n,cubicCoeffA:r,excludeOutside:s,extrapolationValue:a,keepAspectRatioPolicy:o,mode:l,nearestMode:u})}}),Yd,Jd,ec,rf=k(()=>{_e(),$e(),xe(),Yd=e=>{if(!e||e.length<3)throw new Error("layerNorm requires at least 3 inputs.");let t=e[0],i=e[1],n=e[2];if(t.dataType!==i.dataType||t.dataType!==n.dataType)throw new Error("All inputs must have the same data type");if(t.dims.length!==3&&t.dims.length!==2)throw new Error("Input must be 2D or 3D");if(i.dims.length!==3&&i.dims.length!==2)throw new Error("Skip must be 2D or 3D");let r=t.dims[t.dims.length-1],s=t.dims[t.dims.length-2];if(i.dims[i.dims.length-1]!==r)throw new Error("Skip must have the same hidden size as input");if(i.dims[i.dims.length-2]!==s)throw new Error("Skip must have the same sequence length as input");if(n.dims.length!==1)throw new Error("Gamma must be 1D");if(n.dims[n.dims.length-1]!==r)throw new Error("Gamma must have the same hidden size as input");if(e.length>3){let a=e[3];if(a.dims.length!==1)throw new Error("Beta must be 1D");if(a.dims[a.dims.length-1]!==r)throw new Error("Beta must have the same hidden size as input")}if(e.length>4){let a=e[4];if(a.dims.length!==1)throw new Error("Bias must be 1D");if(a.dims[a.dims.length-1]!==r)throw new Error("Bias must have the same hidden size as input")}},Jd=(e,t,i,n)=>{let r=t.simplified,s=e[0].dims,a=M.size(s),o=s,l=a,u=s.slice(-1)[0],d=n?s.slice(0,-1).concat(1):[],c=!r&&e.length>3,p=e.length>4,h=n&&i>1,m=n&&i>2,_=i>3,$=64,w=Qe(u),g=[{type:12,data:l},{type:12,data:w},{type:12,data:u},{type:1,data:t.epsilon}],T=I=>{let O=[{name:"output_size",type:"u32"},{name:"components",type:"u32"},{name:"hidden_size",type:"u32"},{name:"epsilon",type:"f32"}],z=[B("x",e[0].dataType,e[0].dims,w),B("skip",e[1].dataType,e[1].dims,w),B("gamma",e[2].dataType,e[2].dims,w)];c&&z.push(B("beta",e[3].dataType,e[3].dims,w)),p&&z.push(B("bias",e[4].dataType,e[4].dims,w)),z.push(re("output",e[0].dataType,o,w)),h&&z.push(re("mean_output",1,d)),m&&z.push(re("inv_std_output",1,d)),_&&z.push(re("input_skip_bias_sum",e[0].dataType,o,w));let N=at(e[0].dataType),q=at(1,w);return`

      ${I.registerUniforms(O).declareVariables(...z)}
      var<workgroup> sum_shared : array<${q}, ${$}>;
      var<workgroup> sum_squared_shared : array<${q}, ${$}>;

      ${I.mainStart([$,1,1])}
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
          let f32_value = ${mi(N,w,"value")};
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
        let mean = ${Ht("sum",w)} / f32(uniforms.hidden_size);
        let inv_std_dev = inverseSqrt(${Ht("square_sum",w)} / f32(uniforms.hidden_size) ${r?"":"- mean * mean"} + uniforms.epsilon);
        ${h?"mean_output[global_idx] = mean;":""}
        ${m?"inv_std_output[global_idx] = inv_std_dev;":""}

        for (var i: u32 = 0; i < stride; i++) {
          output[offset + i] = (output[offset + i] ${r?"":`- ${N}(mean)`}) *
            ${N}(inv_std_dev) * gamma[offset1d + i]
            ${c?"+ beta[offset1d + i]":""};
        }
      }`},x=[{dims:o,dataType:e[0].dataType}];return i>1&&x.push({dims:d,dataType:1}),i>2&&x.push({dims:d,dataType:1}),i>3&&x.push({dims:s,dataType:e[0].dataType}),{name:"SkipLayerNormalization",shaderCache:{hint:`${w};${h};${m};${_}`,inputDependencies:e.map((I,O)=>"type")},getShaderSource:T,getRunData:()=>({outputs:x,dispatchGroup:{x:Math.ceil(l/u)},programUniforms:g})}},ec=(e,t)=>{Yd(e.inputs);let i=[0];e.outputCount>1&&i.push(-3),e.outputCount>2&&i.push(-3),e.outputCount>3&&i.push(3),e.compute(Jd(e.inputs,t,e.outputCount,!1),{outputs:i})}}),tc,zi,ic,Ir,nc,rc,sc,ac,sf=k(()=>{_e(),$e(),Xe(),xe(),tc=(e,t)=>{if(!e||e.length<1)throw new Error("too few inputs");if(t.axes.length!==0){if(t.axes.length!==t.starts.length||t.axes.length!==t.ends.length)throw new Error("axes, starts and ends must have the same length")}else if(t.starts.length!==t.ends.length)throw new Error("starts and ends must have the same length");e.slice(1).forEach((i,n)=>{if(e[n+1].dataType!==6&&e[n+1].dataType!==7)throw new Error(`Input ${n} must be an array of int32 or int64`)})},zi=(e,t)=>{let i=[];if(e.length>t)if(e[t].dataType===7)e[t].getBigInt64Array().forEach(n=>i.push(Number(n)));else if(e[t].dataType===6)e[t].getInt32Array().forEach(n=>i.push(Number(n)));else throw new Error(`Input ${t} must be an array of int32 or int64`);return i},ic=(e,t)=>{if(e.length>1){let i=zi(e,1),n=zi(e,2),r=zi(e,3);return r.length===0&&(r=[...Array(e[0].dims.length).keys()]),De({starts:i,ends:n,axes:r})}else return t},Ir=(e,t,i,n,r)=>{let s=e;return e<0&&(s+=i[n[t]]),r[t]<0?Math.max(0,Math.min(s,i[n[t]]-1)):Math.max(0,Math.min(s,i[n[t]]))},nc=(e,t,i)=>`fn calculateInputIndices(output_indices: ${t.type.indices}) -> ${e.type.indices} {
          var input_indices: ${e.type.indices};
          var carry = 0u;
          for (var i = ${i.length-1}; i >= 0; i--) {
            let input_shape_i = ${se("uniforms.input_shape","i",i.length)};
            let steps_i = ${se("uniforms.steps","i",i.length)};
            let signs_i = ${se("uniforms.signs","i",i.length)};
            let starts_i = ${se("uniforms.starts","i",i.length)};
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
      }`,rc=(e,t)=>{let i=e[0].dims,n=M.size(i),r=t.axes.length>0?M.normalizeAxes(t.axes,i.length):[...Array(i.length).keys()],s=zi(e,4);s.forEach(w=>w!==0||(()=>{throw new Error("step cannot be 0")})),s.length===0&&(s=Array(r.length).fill(1));let a=t.starts.map((w,g)=>Ir(w,g,i,r,s)),o=t.ends.map((w,g)=>Ir(w,g,i,r,s));if(r.length!==a.length||r.length!==o.length)throw new Error("start, ends and axes should have the same number of elements");if(r.length!==i.length)for(let w=0;w<i.length;++w)r.includes(w)||(a.splice(w,0,0),o.splice(w,0,i[w]),s.splice(w,0,1));let l=s.map(w=>Math.sign(w));s.forEach((w,g,T)=>{if(w<0){let x=(o[g]-a[g])/w,I=a[g],O=I+x*s[g];a[g]=O,o[g]=I,T[g]=-w}});let u=i.slice(0);r.forEach((w,g)=>{u[w]=Math.ceil((o[w]-a[w])/s[w])});let d={dims:u,dataType:e[0].dataType},c=re("output",e[0].dataType,u.length),p=B("input",e[0].dataType,e[0].dims.length),h=M.size(u),m=[{name:"outputSize",type:"u32"},{name:"starts",type:"u32",length:a.length},{name:"signs",type:"i32",length:l.length},{name:"steps",type:"u32",length:s.length}],_=[{type:12,data:h},{type:12,data:a},{type:6,data:l},{type:12,data:s},...le(e[0].dims,u)],$=w=>`
      ${w.registerUniforms(m).declareVariables(p,c)}
        ${nc(p,c,i)}
        ${w.mainStart()}
          ${w.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
          let output_indices = ${c.offsetToIndices("global_idx")};
          let input_indices = calculateInputIndices(output_indices);
          ${c.setByOffset("global_idx",p.getByIndices("input_indices"))}
      }`;return{name:"Slice",shaderCache:{hint:`${l.length}_${a.length}_${s.length}`,inputDependencies:["rank"]},getShaderSource:$,getRunData:()=>({outputs:[d],dispatchGroup:{x:Math.ceil(n/64)},programUniforms:_})}},sc=(e,t)=>{tc(e.inputs,t);let i=ic(e.inputs,t);e.compute(rc(e.inputs,i),{inputs:[0]})},ac=e=>{let t=e.starts,i=e.ends,n=e.axes;return De({starts:t,ends:i,axes:n})}}),oc,lc,uc,dc,af=k(()=>{_e(),$e(),Xe(),Kt(),xe(),oc=e=>{if(!e||e.length!==1)throw new Error("Softmax op requires 1 input.")},lc=(e,t)=>{let i=e.inputs[0],n=i.dims,r=M.size(n),s=n.length,a=M.normalizeAxis(t.axis,s),o=a<n.length-1,l,u=[];o?(u=Array.from({length:s},(z,N)=>N),u[a]=s-1,u[s-1]=a,l=e.compute(xt(i,u),{inputs:[i],outputs:[-1]})[0]):l=i;let d=l.dims,c=d[s-1],p=r/c,h=Qe(c),m=c/h,_=64;p===1&&(_=256);let $=(z,N)=>N===4?`max(max(${z}.x, ${z}.y), max(${z}.z, ${z}.w))`:N===2?`max(${z}.x, ${z}.y)`:N===3?`max(max(${z}.x, ${z}.y), ${z}.z)`:z,w=B("x",l.dataType,l.dims,h),g=re("result",l.dataType,l.dims,h),T=w.type.value,x=at(l.dataType)==="f32"?`var threadMax = ${T}(-3.402823e+38f);`:`var threadMax = ${T}(-65504.0h);`,I=z=>`
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
      ${z.registerUniform("packedCols","i32").declareVariables(w,g)}
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
          rowSumShared = ${T}(${Ht("threadShared[0]",h)});
        }
        workgroupBarrier();

        // calculate final value for each element in the row
        for (var col = lindex; col < cols; col += wg) {
          var value = exp(getValue(row, col, row_stride) - rowMaxShared) / rowSumShared;
          // max operation protects against NaN since all values should be >=0
          value = max(value, ${T}(0.0));
          setValue(row, col, row_stride, value);
        }
      }`,O=e.compute({name:"Softmax",shaderCache:{hint:`${h};${_}`,inputDependencies:["type"]},getRunData:()=>({outputs:[{dims:d,dataType:l.dataType}],dispatchGroup:{x:p},programUniforms:[{type:6,data:m}]}),getShaderSource:I},{inputs:[l],outputs:[o?-1:0]})[0];o&&e.compute(xt(O,u),{inputs:[O]})},uc=(e,t)=>{oc(e.inputs),lc(e,t)},dc=e=>De({axis:e.axis})}),Ar,cc,pc,fc,hc,of=k(()=>{_e(),$e(),xe(),Ar=e=>Array.from(e.getBigInt64Array(),Number),cc=e=>{if(!e||e.length!==2)throw new Error("Tile requires 2 inputs.");if(e[0].dataType!==1&&e[0].dataType!==10&&e[0].dataType!==6&&e[0].dataType!==12)throw new Error("Tile only support float, float16, int32, and uint32 data types");if(e[1].dataType!==7)throw new Error("Tile `repeats` input should be of int64 data type");if(e[1].dims.length!==1)throw new Error("Tile `repeats` input should be 1-D");if(Ar(e[1]).length!==e[0].dims.length)throw new Error("Tile `repeats` input should have same number of elements as rank of input data tensor")},pc=(e,t)=>{let i=[];for(let n=0;n<e.length;++n)i.push(e[n]*t[n]);return i},fc=(e,t)=>{let i=e[0].dims,n=t??Ar(e[1]),r=pc(i,n),s=M.size(r),a=e[0].dataType,o=B("input",a,i.length),l=re("output",a,r.length),u=d=>`
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
    }`;return{name:"Tile",shaderCache:{hint:`${n}`,inputDependencies:["rank"]},getRunData:()=>({outputs:[{dims:r,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(s/64)},programUniforms:[{type:12,data:s},...le(e[0].dims,r)]}),getShaderSource:u}},hc=e=>{cc(e.inputs),e.compute(fc(e.inputs),{inputs:[0]})}}),mc,gc,_c,lf=k(()=>{_e(),$e(),xe(),mc=(e,t,i,n,r)=>{let s=re("output_data",r,i.length,4),a=B("a_data",t[1].dataType,t[1].dims.length,4),o=B("b_data",t[2].dataType,t[2].dims.length,4),l=B("c_data",t[0].dataType,t[0].dims.length,4),u,d=(c,p,h)=>`select(${p}, ${c}, ${h})`;if(!n)u=s.setByOffset("global_idx",d(a.getByOffset("global_idx"),o.getByOffset("global_idx"),l.getByOffset("global_idx")));else{let c=(p,h,m="")=>{let _=`a_data[index_a${h}][component_a${h}]`,$=`b_data[index_b${h}][component_b${h}]`,w=`bool(c_data[index_c${h}] & (0xffu << (component_c${h} * 8)))`;return`
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
            ${p}[${h}] = ${m}(${d(_,$,w)});
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
      }`},gc=e=>{let t=e[1].dims,i=e[2].dims,n=e[0].dims,r=e[1].dataType,s=!(M.areEqual(t,i)&&M.areEqual(i,n)),a=t,o=M.size(t);if(s){let u=fi.calcShape(fi.calcShape(t,i,!1),n,!1);if(!u)throw new Error("Can't perform where op on the given tensors");a=u,o=M.size(a)}let l=Math.ceil(o/4);return{name:"Where",shaderCache:{inputDependencies:["rank","rank","rank"]},getShaderSource:u=>mc(u,e,a,s,r),getRunData:()=>({outputs:[{dims:a,dataType:r}],dispatchGroup:{x:Math.ceil(o/64/4)},programUniforms:[{type:12,data:l},...le(n,t,i,a)]})}},_c=e=>{e.compute(gc(e.inputs))}}),yc,uf=k(()=>{$p(),jn(),xp(),Sp(),kp(),Tp(),Ep(),Rp(),Mp(),Fp(),Dp(),Bp(),Pp(),Np(),Vp(),Lp(),Up(),qp(),Wp(),Gp(),jp(),Hp(),Kp(),Zp(),Qp(),Au(),Xp(),Yp(),Jp(),ef(),tf(),qn(),nf(),Vu(),rf(),sf(),af(),Bu(),of(),Kt(),Qn(),lf(),yc=new Map([["Abs",[Xa]],["Acos",[Ya]],["Acosh",[Ja]],["Add",[Lo]],["ArgMax",[Da,Gn]],["ArgMin",[Fa,Gn]],["Asin",[eo]],["Asinh",[to]],["Atan",[io]],["Atanh",[no]],["Attention",[Ua]],["AveragePool",[gd,md]],["BatchNormalization",[ja]],["BiasAdd",[Za]],["BiasSplitGelu",[Po]],["Cast",[so,ro]],["Ceil",[lo]],["Clip",[oo]],["Concat",[tl,il]],["Conv",[ur,or]],["ConvTranspose",[Il,Tl]],["Cos",[uo]],["Cosh",[co]],["CumSum",[zl,Rl]],["DepthToSpace",[Dl,Bl]],["DequantizeLinear",[kd,Td]],["Div",[Uo]],["Einsum",[ql,Wl]],["Elu",[po,ki]],["Equal",[qo]],["Erf",[fo]],["Exp",[ho]],["Expand",[Kl]],["FastGelu",[Ql]],["Floor",[mo]],["FusedConv",[ur,or]],["Gather",[eu,Jl]],["GatherElements",[cu,du]],["GatherBlockQuantized",[au,ou]],["GatherND",[iu,nu]],["Gelu",[go]],["Gemm",[mu,hu]],["GlobalAveragePool",[yd,_d]],["GlobalMaxPool",[$d,vd]],["Greater",[Ho]],["GreaterOrEqual",[Zo]],["GridSample",[Su,ku]],["GroupQueryAttention",[Wu]],["HardSigmoid",[So,xo]],["InstanceNormalization",[Hu]],["LayerNormalization",[Qu]],["LeakyRelu",[_o,ki]],["Less",[Ko]],["LessOrEqual",[Qo]],["Log",[Ro]],["MatMul",[Yu]],["MatMulNBits",[id,nd]],["MaxPool",[wd,bd]],["Mul",[Wo]],["MultiHeadAttention",[Iu,Eu]],["Neg",[wo]],["Not",[yo]],["Pad",[pd]],["Pow",[Go]],["QuickGelu",[Fo,ki]],["Range",[Id]],["Reciprocal",[bo]],["ReduceMin",[Aa]],["ReduceMean",[ka]],["ReduceMax",[Ia]],["ReduceSum",[Ra]],["ReduceProd",[za]],["ReduceL1",[Ta]],["ReduceL2",[Ea]],["ReduceLogSum",[Ma]],["ReduceLogSumExp",[Ca]],["ReduceSumSquare",[Oa]],["Relu",[vo]],["Resize",[Qd,Xd]],["RotaryEmbedding",[Nu]],["ScatterND",[Od,Rd]],["Sigmoid",[$o]],["Sin",[ko]],["Sinh",[To]],["Slice",[sc,ac]],["SkipLayerNormalization",[ec]],["Split",[Fu,Du]],["Sqrt",[Eo]],["Softmax",[uc,dc]],["Sub",[jo]],["Tan",[Co]],["Tanh",[Io]],["ThresholdedRelu",[zo,ki]],["Tile",[hc]],["Transpose",[js,Hs]],["Where",[_c]]])}),wc,df=k(()=>{wt(),Wt(),xe(),wc=class{constructor(e){this.backend=e,this.repo=new Map,this.attributesBound=!1}getArtifact(e){return this.repo.get(e)}setArtifact(e,t){this.repo.set(e,t)}run(e,t,i,n,r){ue(e.programInfo.name);let s=this.backend.device,a=this.backend.getComputePassEncoder();this.backend.writeTimestamp(this.backend.pendingDispatchNumber*2);let o=[];for(let u of t)o.push({binding:o.length,resource:{buffer:u.buffer}});for(let u of i)o.push({binding:o.length,resource:{buffer:u.buffer}});r&&o.push({binding:o.length,resource:r});let l=s.createBindGroup({layout:e.computePipeline.getBindGroupLayout(0),entries:o,label:e.programInfo.name});if(this.backend.sessionStatus==="capturing"){let u={kernelId:this.backend.currentKernelId,computePipeline:e.computePipeline,bindGroup:l,dispatchGroup:n};this.backend.capturedCommandList.get(this.backend.currentSessionId).push(u)}a.setPipeline(e.computePipeline),a.setBindGroup(0,l),a.dispatchWorkgroups(...n),this.backend.writeTimestamp(this.backend.pendingDispatchNumber*2+1),this.backend.pendingDispatchNumber++,(this.backend.pendingDispatchNumber>=this.backend.maxDispatchNumber||this.backend.queryType==="at-passes")&&this.backend.endComputePass(),this.backend.pendingDispatchNumber>=this.backend.maxDispatchNumber&&this.backend.flush(),Pe(e.programInfo.name)}dispose(){}build(e,t){ue(e.name);let i=this.backend.device,n=[];[{feature:"shader-f16",extension:"f16"},{feature:"subgroups",extension:"subgroups"}].forEach(u=>{i.features.has(u.feature)&&n.push(`enable ${u.extension};`)});let r=Vs(t,this.backend.device.limits),s=e.getShaderSource(r),a=`${n.join(`
`)}
${r.additionalImplementations}
${s}`,o=i.createShaderModule({code:a,label:e.name});Ie("verbose",()=>`[WebGPU] ${e.name} shader code: ${a}`);let l=i.createComputePipeline({compute:{module:o,entryPoint:"main"},layout:"auto",label:e.name});return Pe(e.name),{programInfo:e,computePipeline:l,uniformVariablesInfo:r.variablesInfo}}normalizeDispatchGroupSize(e){let t=typeof e=="number"?e:e.x,i=typeof e=="number"?1:e.y||1,n=typeof e=="number"?1:e.z||1,r=this.backend.device.limits.maxComputeWorkgroupsPerDimension;if(t<=r&&i<=r&&n<=r)return[t,i,n];let s=t*i*n,a=Math.ceil(Math.sqrt(s));if(a>r){if(a=Math.ceil(Math.cbrt(s)),a>r)throw new Error("Total dispatch size exceeds WebGPU maximum.");return[a,a,a]}else return[a,a,1]}}}),bc={};L(bc,{WebGpuBackend:()=>Sc});var vc,$c,xc,Sc,cf=k(()=>{wt(),_e(),Wt(),Ts(),bp(),uf(),df(),vc=(e,t)=>{if(t.length!==e.length)throw new Error(`inputDependencies length ${t.length} is not equal to inputTensors length ${e.length}.`);let i=[];for(let n=0;n<e.length;++n){let r=e[n].dataType;switch(t[n]){case"none":{i.push("");break}case"type":{i.push(`${r}`);break}case"rank":{let s=e[n].dims.length;i.push(`${r};${s}`);break}case"dims":{let s=e[n].dims.join(",");i.push(`${r};${s}`);break}default:throw new Error(`unsupported input dependency: ${t[n]}`)}}return i.join("|")},$c=(e,t,i)=>{let n=e.name;return e.shaderCache?.hint&&(n+="["+e.shaderCache.hint+"]"),n+=":"+i+`:${vc(t,e.shaderCache?.inputDependencies??new Array(t.length).fill("dims"))}`,n},xc=class{constructor(e){e&&(this.architecture=e.architecture,this.vendor=e.vendor)}isArchitecture(e){return this.architecture===e}isVendor(e){return this.vendor===e}},Sc=class{constructor(){this.currentSessionId=null,this.currentKernelId=null,this.commandEncoder=null,this.computePassEncoder=null,this.maxDispatchNumber=16,this.pendingDispatchNumber=0,this.pendingKernels=[],this.pendingQueries=new Map,this.sessionStatus="default",this.capturedCommandList=new Map,this.capturedPendingKernels=new Map,this.sessionExternalDataMapping=new Map}get currentKernelCustomData(){if(this.currentKernelId===null)throw new Error("currentKernelCustomData(): currentKernelId is null. (should not happen)");let e=this.kernelCustomData.get(this.currentKernelId);return e||(e={},this.kernelCustomData.set(this.currentKernelId,e)),e}async initialize(e,t){this.env=e;let i=[],n={requiredLimits:{maxComputeWorkgroupStorageSize:t.limits.maxComputeWorkgroupStorageSize,maxComputeWorkgroupsPerDimension:t.limits.maxComputeWorkgroupsPerDimension,maxStorageBufferBindingSize:t.limits.maxStorageBufferBindingSize,maxBufferSize:t.limits.maxBufferSize,maxComputeInvocationsPerWorkgroup:t.limits.maxComputeInvocationsPerWorkgroup,maxComputeWorkgroupSizeX:t.limits.maxComputeWorkgroupSizeX,maxComputeWorkgroupSizeY:t.limits.maxComputeWorkgroupSizeY,maxComputeWorkgroupSizeZ:t.limits.maxComputeWorkgroupSizeZ},requiredFeatures:i},r=s=>t.features.has(s)&&i.push(s)&&!0;r("chromium-experimental-timestamp-query-inside-passes")||r("timestamp-query"),r("shader-f16"),r("subgroups"),this.device=await t.requestDevice(n),this.adapterInfo=new xc(t.info||await t.requestAdapterInfo()),this.gpuDataManager=Ds(this),this.programManager=new wc(this),this.kernels=new Map,this.kernelPersistentData=new Map,this.kernelCustomData=new Map,Tn(e.logLevel,!!e.debug),this.device.onuncapturederror=s=>{s.error instanceof GPUValidationError&&console.error(`An uncaught WebGPU validation error was raised: ${s.error.message}`)},Object.defineProperty(this.env.webgpu,"device",{value:this.device,writable:!1,enumerable:!0,configurable:!1}),Object.defineProperty(this.env.webgpu,"adapter",{value:t,writable:!1,enumerable:!0,configurable:!1}),this.setQueryType()}dispose(){typeof this.querySet<"u"&&this.querySet.destroy(),this.gpuDataManager.dispose()}getCommandEncoder(){return this.commandEncoder||(this.commandEncoder=this.device.createCommandEncoder()),this.commandEncoder}getComputePassEncoder(){if(!this.computePassEncoder){let e=this.getCommandEncoder(),t={};this.queryType==="at-passes"&&(t.timestampWrites={querySet:this.querySet,beginningOfPassWriteIndex:this.pendingDispatchNumber*2,endOfPassWriteIndex:this.pendingDispatchNumber*2+1}),this.computePassEncoder=e.beginComputePass(t)}return this.computePassEncoder}endComputePass(){this.computePassEncoder&&(this.computePassEncoder.end(),this.computePassEncoder=null)}flush(){if(!this.commandEncoder)return;ue(),this.endComputePass();let e;this.queryType!=="none"&&(this.commandEncoder.resolveQuerySet(this.querySet,0,this.pendingDispatchNumber*2,this.queryResolveBuffer,0),e=this.device.createBuffer({size:this.pendingDispatchNumber*2*8,usage:GPUBufferUsage.MAP_READ|GPUBufferUsage.COPY_DST}),this.pendingQueries.set(e,this.pendingKernels),this.pendingKernels=[],this.commandEncoder.copyBufferToBuffer(this.queryResolveBuffer,0,e,0,this.pendingDispatchNumber*2*8)),this.device.queue.submit([this.commandEncoder.finish()]),this.gpuDataManager.refreshPendingBuffers(),this.commandEncoder=null,this.pendingDispatchNumber=0,this.queryType!=="none"&&e.mapAsync(GPUMapMode.READ).then(()=>{let t=new BigUint64Array(e.getMappedRange()),i=this.pendingQueries.get(e);for(let n=0;n<t.length/2;n++){let r=i[n],s=r.kernelId,a=this.kernels.get(s),o=a.kernelType,l=a.kernelName,u=r.programName,d=r.inputTensorViews,c=r.outputTensorViews,p=t[n*2],h=t[n*2+1];typeof this.queryTimeBase>"u"&&(this.queryTimeBase=p);let m=Number(p-this.queryTimeBase),_=Number(h-this.queryTimeBase);if(!Number.isSafeInteger(m)||!Number.isSafeInteger(_))throw new RangeError("incorrect timestamp range");if(this.env.webgpu.profiling?.ondata)this.env.webgpu.profiling.ondata({version:1,inputsMetadata:d.map($=>({dims:$.dims,dataType:qt($.dataType)})),outputsMetadata:c.map($=>({dims:$.dims,dataType:qt($.dataType)})),kernelId:s,kernelType:o,kernelName:l,programName:u,startTime:m,endTime:_});else{let $="";d.forEach((g,T)=>{$+=`input[${T}]: [${g.dims}] | ${qt(g.dataType)}, `});let w="";c.forEach((g,T)=>{w+=`output[${T}]: [${g.dims}] | ${qt(g.dataType)}, `}),console.log(`[profiling] kernel "${s}|${o}|${l}|${u}" ${$}${w}start time: ${m} ns, execution time: ${_-m} ns`)}St("GPU",`${u}::${p}::${h}`)}e.unmap(),this.pendingQueries.delete(e)}),Pe()}run(e,t,i,n,r,s){ue(e.name);let a=[];for(let g=0;g<t.length;++g){let T=t[g].data;if(T===0)continue;let x=this.gpuDataManager.get(T);if(!x)throw new Error(`no GPU data for input: ${T}`);a.push(x)}let{outputs:o,dispatchGroup:l,programUniforms:u}=e.getRunData(t),d=i.length===0?o.map((g,T)=>T):i;if(d.length!==o.length)throw new Error(`Output size ${d.length} must be equal to ${o.length}.`);let c=[],p=[];for(let g=0;g<o.length;++g){if(!Number.isInteger(d[g])||d[g]<-3||d[g]>=s)throw new Error(`Invalid output index: ${d[g]}`);if(d[g]===-3)continue;let T=d[g]===-1,x=d[g]===-2,I=T||x?r(o[g].dataType,o[g].dims):n(d[g],o[g].dataType,o[g].dims);if(c.push(I),I.data===0)continue;let O=this.gpuDataManager.get(I.data);if(!O)throw new Error(`no GPU data for output: ${I.data}`);if(T&&this.temporaryData.push(O),x){let z=this.kernelPersistentData.get(this.currentKernelId);z||(z=[],this.kernelPersistentData.set(this.currentKernelId,z)),z.push(O)}p.push(O)}if(a.length!==t.length||p.length!==c.length){if(p.length===0)return Pe(e.name),c;throw new Error(`Program ${e.name} has zero-sized tensor(s) in inputs or outputs. This is not supported now.`)}let h;if(u){let g=0,T=[];u.forEach(z=>{let N=typeof z.data=="number"?[z.data]:z.data;if(N.length===0)return;let q=z.type===10?2:4,te,ye;z.type===10?(ye=N.length>4?16:N.length>2?8:N.length*q,te=N.length>4?16:q*N.length):(ye=N.length<=2?N.length*q:16,te=16),g=Math.ceil(g/ye)*ye,T.push(g);let de=z.type===10?8:4;g+=N.length>4?Math.ceil(N.length/de)*te:N.length*q});let x=16;g=Math.ceil(g/x)*x;let I=new ArrayBuffer(g);u.forEach((z,N)=>{let q=T[N],te=typeof z.data=="number"?[z.data]:z.data;if(z.type===6)new Int32Array(I,q,te.length).set(te);else if(z.type===12)new Uint32Array(I,q,te.length).set(te);else if(z.type===10)new Uint16Array(I,q,te.length).set(te);else if(z.type===1)new Float32Array(I,q,te.length).set(te);else throw new Error(`Unsupported uniform type: ${qt(z.type)}`)});let O=this.gpuDataManager.create(g,GPUBufferUsage.COPY_DST|GPUBufferUsage.UNIFORM);this.device.queue.writeBuffer(O.buffer,0,I,0,g),this.gpuDataManager.release(O.id),h={offset:0,size:g,buffer:O.buffer}}let m=this.programManager.normalizeDispatchGroupSize(l),_=m[1]===1&&m[2]===1,$=$c(e,t,_),w=this.programManager.getArtifact($);if(w||(w=this.programManager.build(e,m),this.programManager.setArtifact($,w),Ie("info",()=>`[artifact] key: ${$}, programName: ${e.name}`)),u&&w.uniformVariablesInfo){if(u.length!==w.uniformVariablesInfo.length)throw new Error(`Uniform variables count mismatch: expect ${w.uniformVariablesInfo.length}, got ${u.length} in program "${w.programInfo.name}".`);for(let g=0;g<u.length;g++){let T=u[g],x=T.type,I=typeof T.data=="number"?1:T.data.length,[O,z]=w.uniformVariablesInfo[g];if(x!==O||I!==z)throw new Error(`Uniform variable ${g} mismatch: expect type ${O} with size ${z}, got type ${x} with size ${I} in program "${w.programInfo.name}".`)}}if(Ie("info",()=>`[ProgramManager] run "${e.name}" (key=${$}) with ${m[0]}x${m[1]}x${m[2]}`),this.queryType!=="none"||this.sessionStatus==="capturing"){let g={kernelId:this.currentKernelId,programName:w.programInfo.name,inputTensorViews:t,outputTensorViews:c};this.pendingKernels.push(g),this.sessionStatus==="capturing"&&this.capturedPendingKernels.get(this.currentSessionId).push(g)}return this.programManager.run(w,a,p,m,h),Pe(e.name),c}upload(e,t){this.gpuDataManager.upload(e,t)}memcpy(e,t){this.gpuDataManager.memcpy(e,t)}async download(e,t){await this.gpuDataManager.download(e,t)}alloc(e){return this.gpuDataManager.create(e).id}free(e){return this.gpuDataManager.release(e)}createKernel(e,t,i,n){let r=yc.get(e);if(!r)throw new Error(`kernel not implemented: ${e}`);let s={kernelType:e,kernelName:n,kernelEntry:r[0],attributes:[r[1],i]};this.kernels.set(t,s)}releaseKernel(e){let t=this.kernelPersistentData.get(e);if(t){for(let i of t)this.gpuDataManager.release(i.id);this.kernelPersistentData.delete(e)}this.kernelCustomData.delete(e),this.kernels.delete(e)}computeKernel(e,t,i){let n=this.kernels.get(e);if(!n)throw new Error(`kernel not created: ${e}`);let r=n.kernelType,s=n.kernelName,a=n.kernelEntry,o=n.attributes;if(this.currentKernelId!==null)throw new Error(`kernel "[${r}] ${s}" is not allowed to be called recursively`);this.currentKernelId=e,o[0]&&(o[1]=o[0](o[1]),o[0]=void 0),Ie("info",()=>`[WebGPU] Start to run kernel "[${r}] ${s}"...`);let l=this.env.debug;this.temporaryData=[];try{return l&&this.device.pushErrorScope("validation"),a(t,o[1]),0}catch(u){return i.push(Promise.resolve(`[WebGPU] Kernel "[${r}] ${s}" failed. ${u}`)),1}finally{l&&i.push(this.device.popErrorScope().then(u=>u?`GPU validation error for kernel "[${r}] ${s}": ${u.message}`:null));for(let u of this.temporaryData)this.gpuDataManager.release(u.id);this.temporaryData=[],this.currentKernelId=null}}registerBuffer(e,t,i,n){let r=this.sessionExternalDataMapping.get(e);r||(r=new Map,this.sessionExternalDataMapping.set(e,r));let s=r.get(t),a=this.gpuDataManager.registerExternalBuffer(i,n,s);return r.set(t,[a,i]),a}unregisterBuffers(e){let t=this.sessionExternalDataMapping.get(e);t&&(t.forEach(i=>this.gpuDataManager.unregisterExternalBuffer(i[0])),this.sessionExternalDataMapping.delete(e))}getBuffer(e){let t=this.gpuDataManager.get(e);if(!t)throw new Error(`no GPU data for buffer: ${e}`);return t.buffer}createDownloader(e,t,i){return async()=>{let n=await Pn(this,e,t);return En(n.buffer,i)}}writeTimestamp(e){this.queryType==="inside-passes"&&this.computePassEncoder.writeTimestamp(this.querySet,e)}setQueryType(){this.queryType="none",(this.env.webgpu.profiling?.mode==="default"||(typeof this.env.trace>"u"?this.env.wasm.trace:this.env.trace))&&(this.device.features.has("chromium-experimental-timestamp-query-inside-passes")?this.queryType="inside-passes":this.device.features.has("timestamp-query")&&(this.queryType="at-passes"),this.queryType!=="none"&&typeof this.querySet>"u"&&(this.querySet=this.device.createQuerySet({type:"timestamp",count:this.maxDispatchNumber*2}),this.queryResolveBuffer=this.device.createBuffer({size:this.maxDispatchNumber*2*8,usage:GPUBufferUsage.COPY_SRC|GPUBufferUsage.QUERY_RESOLVE})))}captureBegin(){Ie("info","captureBegin"),this.capturedCommandList.get(this.currentSessionId)||this.capturedCommandList.set(this.currentSessionId,[]),this.capturedPendingKernels.get(this.currentSessionId)||this.capturedPendingKernels.set(this.currentSessionId,[]),this.flush(),this.sessionStatus="capturing"}captureEnd(){Ie("info","captureEnd"),this.flush(),this.sessionStatus="default"}replay(){Ie("info","replay"),this.sessionStatus="replaying";let e=this.capturedCommandList.get(this.currentSessionId),t=this.capturedPendingKernels.get(this.currentSessionId),i=e.length;this.pendingKernels=[];for(let n=0;n<i;n++){let r=this.getComputePassEncoder(),s=e[n];this.writeTimestamp(this.pendingDispatchNumber*2),r.setPipeline(s.computePipeline),r.setBindGroup(0,s.bindGroup),r.dispatchWorkgroups(...s.dispatchGroup),this.writeTimestamp(this.pendingDispatchNumber*2+1),this.pendingDispatchNumber++,this.queryType!=="none"&&this.pendingKernels.push(t[n]),(this.pendingDispatchNumber>=this.maxDispatchNumber||this.queryType==="at-passes")&&this.endComputePass(),this.pendingDispatchNumber>=this.maxDispatchNumber&&this.flush()}this.flush(),this.sessionStatus="default"}onCreateSession(){this.gpuDataManager.onCreateSession()}onReleaseSession(e){this.unregisterBuffers(e),this.capturedCommandList.has(e)&&this.capturedCommandList.delete(e),this.capturedPendingKernels.has(e)&&this.capturedPendingKernels.delete(e),this.gpuDataManager.onReleaseSession(e)}onRunStart(e){this.currentSessionId=e,this.setQueryType()}}}),kc={};L(kc,{init:()=>Ec});var nn,Tc,Ec,pf=k(()=>{_e(),Wt(),$e(),wp(),nn=class lp{constructor(t,i,n,r){this.module=t,this.dataType=i,this.data=n,this.dims=r}getFloat32Array(){if(this.dataType!==1)throw new Error("Invalid data type");let t=M.size(this.dims);return t===0?new Float32Array:new Float32Array(this.module.HEAP8.buffer,this.data,t)}getBigInt64Array(){if(this.dataType!==7)throw new Error("Invalid data type");let t=M.size(this.dims);return t===0?new BigInt64Array:new BigInt64Array(this.module.HEAP8.buffer,this.data,t)}getInt32Array(){if(this.dataType!==6)throw new Error("Invalid data type");let t=M.size(this.dims);return t===0?new Int32Array:new Int32Array(this.module.HEAP8.buffer,this.data,t)}getUint16Array(){if(this.dataType!==10&&this.dataType!==4)throw new Error("Invalid data type");let t=M.size(this.dims);return t===0?new Uint16Array:new Uint16Array(this.module.HEAP8.buffer,this.data,t)}reshape(t){if(M.size(t)!==M.size(this.dims))throw new Error("Invalid new shape");return new lp(this.module,this.dataType,this.data,t)}},Tc=class{constructor(e,t,i){this.module=e,this.backend=t,this.customDataOffset=0,this.customDataSize=0,this.adapterInfo=t.adapterInfo;let n=e.PTR_SIZE,r=i/e.PTR_SIZE,s=n===4?"i32":"i64";this.opKernelContext=Number(e.getValue(n*r++,s));let a=Number(e.getValue(n*r++,s));this.outputCount=Number(e.getValue(n*r++,s)),this.customDataOffset=Number(e.getValue(n*r++,"*")),this.customDataSize=Number(e.getValue(n*r++,s));let o=[];for(let l=0;l<a;l++){let u=Number(e.getValue(n*r++,s)),d=Number(e.getValue(n*r++,"*")),c=Number(e.getValue(n*r++,s)),p=[];for(let h=0;h<c;h++)p.push(Number(e.getValue(n*r++,s)));o.push(new nn(e,u,d,p))}this.inputs=o}get kernelCustomData(){return this.backend.currentKernelCustomData}get customDataBuffer(){return this.module.HEAPU8.subarray(this.customDataOffset,this.customDataOffset+this.customDataSize)}compute(e,t){let i=t?.inputs?.map(a=>typeof a=="number"?this.inputs[a]:a)??this.inputs,n=t?.outputs??[],r=(a,o,l)=>new nn(this.module,o,this.output(a,l),l),s=(a,o)=>{let l=ei(a,o);if(!l)throw new Error(`Unsupported data type: ${a}`);let u=l>0?this.backend.gpuDataManager.create(l).id:0;return new nn(this.module,a,u,o)};return this.backend.run(e,i,n,r,s,this.outputCount)}output(e,t){let i=this.module.stackSave();try{let n=this.module.PTR_SIZE,r=n===4?"i32":"i64",s=this.module.stackAlloc((1+t.length)*n);this.module.setValue(s,t.length,r);for(let a=0;a<t.length;a++)this.module.setValue(s+n*(a+1),t[a],r);return this.module._JsepOutput(this.opKernelContext,e,s)}catch(n){throw new Error(`Failed to generate kernel's output[${e}] with dims [${t}]. If you are running with pre-allocated output, please make sure the output type/dims are correct. Error: ${n}`)}finally{this.module.stackRestore(i)}}},Ec=async(e,t,i,n)=>{let r=t.jsepInit;if(!r)throw new Error("Failed to initialize JSEP. The WebAssembly module is not built with JSEP support.");if(e==="webgpu"){let s=(cf(),we(bc)).WebGpuBackend,a=new s;await a.initialize(i,n),r("webgpu",[a,o=>a.alloc(Number(o)),o=>a.free(o),(o,l,u,d=!1)=>{if(d)Ie("verbose",()=>`[WebGPU] jsepCopyGpuToGpu: src=${Number(o)}, dst=${Number(l)}, size=${Number(u)}`),a.memcpy(Number(o),Number(l));else{Ie("verbose",()=>`[WebGPU] jsepCopyCpuToGpu: dataOffset=${Number(o)}, gpuDataId=${Number(l)}, size=${Number(u)}`);let c=t.HEAPU8.subarray(Number(o>>>0),Number(o>>>0)+Number(u));a.upload(Number(l),c)}},async(o,l,u)=>{Ie("verbose",()=>`[WebGPU] jsepCopyGpuToCpu: gpuDataId=${o}, dataOffset=${l}, size=${u}`),await a.download(Number(o),()=>t.HEAPU8.subarray(Number(l)>>>0,Number(l+u)>>>0))},(o,l,u)=>a.createKernel(o,Number(l),u,t.UTF8ToString(t._JsepGetNodeName(Number(l)))),o=>a.releaseKernel(o),(o,l,u,d)=>{Ie("verbose",()=>`[WebGPU] jsepRun: sessionHandle=${u}, kernel=${o}, contextDataOffset=${l}`);let c=new Tc(t,a,Number(l));return a.computeKernel(Number(o),c,d)},()=>a.captureBegin(),()=>a.captureEnd(),()=>a.replay()])}else{let s=new Rs(i);r("webnn",[s,()=>s.reserveTensorId(),a=>s.releaseTensorId(a),async(a,o,l,u,d)=>s.ensureTensor(a,o,l,u,d),(a,o)=>{s.uploadTensor(a,o)},async(a,o)=>s.downloadTensor(a,o),(a,o)=>s.registerMLContext(a,o),!!i.trace])}}}),Cc,zr,Rr,Zt,Ic,Or,rn,Mr,Fr,Dr,Br,Pr,Nr,Ac=k(()=>{wt(),gp(),_p(),_e(),Yt(),vn(),gs(),Cc=(e,t)=>{We()._OrtInit(e,t)!==0&&Ve("Can't initialize onnxruntime.")},zr=async e=>{Cc(e.wasm.numThreads,qi(e.logLevel))},Rr=async(e,t)=>{We().asyncInit?.();let i=e.webgpu.adapter;if(t==="webgpu"){if(typeof navigator>"u"||!navigator.gpu)throw new Error("WebGPU is not supported in current environment");if(i){if(typeof i.limits!="object"||typeof i.features!="object"||typeof i.requestDevice!="function")throw new Error("Invalid GPU adapter set in `env.webgpu.adapter`. It must be a GPUAdapter object.")}else{let n=e.webgpu.powerPreference;if(n!==void 0&&n!=="low-power"&&n!=="high-performance")throw new Error(`Invalid powerPreference setting: "${n}"`);let r=e.webgpu.forceFallbackAdapter;if(r!==void 0&&typeof r!="boolean")throw new Error(`Invalid forceFallbackAdapter setting: "${r}"`);if(i=await navigator.gpu.requestAdapter({powerPreference:n,forceFallbackAdapter:r}),!i)throw new Error('Failed to get GPU adapter. You may need to enable flag "--enable-unsafe-webgpu" if you are using Chrome.')}}if(t==="webnn"&&(typeof navigator>"u"||!navigator.ml))throw new Error("WebNN is not supported in current environment");{let n=(pf(),we(kc)).init;t==="webgpu"&&await n("webgpu",We(),e,i),t==="webnn"&&await n("webnn",We(),e)}},Zt=new Map,Ic=e=>{let t=We(),i=t.stackSave();try{let n=t.PTR_SIZE,r=t.stackAlloc(2*n);t._OrtGetInputOutputCount(e,r,r+n)!==0&&Ve("Can't get session input/output count.");let s=n===4?"i32":"i64";return[Number(t.getValue(r,s)),Number(t.getValue(r+n,s))]}finally{t.stackRestore(i)}},Or=(e,t)=>{let i=We(),n=i.stackSave(),r=0;try{let s=i.PTR_SIZE,a=i.stackAlloc(2*s);i._OrtGetInputOutputMetadata(e,t,a,a+s)!==0&&Ve("Can't get session input/output metadata.");let o=Number(i.getValue(a,"*"));r=Number(i.getValue(a+s,"*"));let l=i.HEAP32[r/4];if(l===0)return[o,0];let u=i.HEAPU32[r/4+1],d=[];for(let c=0;c<u;c++){let p=Number(i.getValue(r+8+c*s,"*"));d.push(p!==0?i.UTF8ToString(p):Number(i.getValue(r+8+(c+u)*s,"*")))}return[o,l,d]}finally{i.stackRestore(n),r!==0&&i._OrtFree(r)}},rn=e=>{let t=We(),i=t._malloc(e.byteLength);if(i===0)throw new Error(`Can't create a session. failed to allocate a buffer of size ${e.byteLength}.`);return t.HEAPU8.set(e,i),[i,e.byteLength]},Mr=async(e,t)=>{let i,n,r=We();Array.isArray(e)?[i,n]=e:e.buffer===r.HEAPU8.buffer?[i,n]=[e.byteOffset,e.byteLength]:[i,n]=rn(e);let s=0,a=0,o=0,l=[],u=[],d=[];try{if([a,l]=await ms(t),t?.externalData&&r.mountExternalData){let x=[];for(let I of t.externalData){let O=typeof I=="string"?I:I.path;x.push(kn(typeof I=="string"?I:I.data).then(z=>{r.mountExternalData(O,z)}))}await Promise.all(x)}for(let x of t?.executionProviders??[])if((typeof x=="string"?x:x.name)==="webnn"){if(r.shouldTransferToMLTensor=!1,typeof x!="string"){let I=x,O=I?.context,z=I?.gpuDevice,N=I?.deviceType,q=I?.powerPreference;O?r.currentContext=O:z?r.currentContext=await r.webnnCreateMLContext(z):r.currentContext=await r.webnnCreateMLContext({deviceType:N,powerPreference:q})}else r.currentContext=await r.webnnCreateMLContext();break}s=await r._OrtCreateSession(i,n,a),r.webgpuOnCreateSession?.(s),s===0&&Ve("Can't create a session."),r.jsepOnCreateSession?.(),r.currentContext&&(r.webnnRegisterMLContext(s,r.currentContext),r.currentContext=void 0,r.shouldTransferToMLTensor=!0);let[c,p]=Ic(s),h=!!t?.enableGraphCapture,m=[],_=[],$=[],w=[],g=[];for(let x=0;x<c;x++){let[I,O,z]=Or(s,x);I===0&&Ve("Can't get an input name."),u.push(I);let N=r.UTF8ToString(I);m.push(N),$.push(O===0?{name:N,isTensor:!1}:{name:N,isTensor:!0,type:qt(O),shape:z})}for(let x=0;x<p;x++){let[I,O,z]=Or(s,x+c);I===0&&Ve("Can't get an output name."),d.push(I);let N=r.UTF8ToString(I);_.push(N),w.push(O===0?{name:N,isTensor:!1}:{name:N,isTensor:!0,type:qt(O),shape:z});{if(h&&t?.preferredOutputLocation===void 0){g.push("gpu-buffer");continue}let q=typeof t?.preferredOutputLocation=="string"?t.preferredOutputLocation:t?.preferredOutputLocation?.[N]??"cpu",te=r.webnnIsGraphOutput;if(q==="cpu"&&te&&te(s,N)){g.push("ml-tensor-cpu-output");continue}if(q!=="cpu"&&q!=="cpu-pinned"&&q!=="gpu-buffer"&&q!=="ml-tensor")throw new Error(`Not supported preferred output location: ${q}.`);if(h&&q!=="gpu-buffer")throw new Error(`Not supported preferred output location: ${q}. Only 'gpu-buffer' location is supported when enableGraphCapture is true.`);g.push(q)}}let T=null;return g.some(x=>x==="gpu-buffer"||x==="ml-tensor"||x==="ml-tensor-cpu-output")&&(o=r._OrtCreateBinding(s),o===0&&Ve("Can't create IO binding."),T={handle:o,outputPreferredLocations:g,outputPreferredLocationsEncoded:g.map(x=>x==="ml-tensor-cpu-output"?"ml-tensor":x).map(x=>Sn(x))}),Zt.set(s,[s,u,d,T,h,!1]),[s,m,_,$,w]}catch(c){throw u.forEach(p=>r._OrtFree(p)),d.forEach(p=>r._OrtFree(p)),o!==0&&r._OrtReleaseBinding(o)!==0&&Ve("Can't release IO binding."),s!==0&&r._OrtReleaseSession(s)!==0&&Ve("Can't release session."),c}finally{r._free(i),a!==0&&r._OrtReleaseSessionOptions(a)!==0&&Ve("Can't release session options."),l.forEach(c=>r._free(c)),r.unmountExternalData?.()}},Fr=e=>{let t=We(),i=Zt.get(e);if(!i)throw new Error(`cannot release session. invalid session id: ${e}`);let[n,r,s,a,o]=i;a&&(o&&t._OrtClearBoundOutputs(a.handle)!==0&&Ve("Can't clear bound outputs."),t._OrtReleaseBinding(a.handle)!==0&&Ve("Can't release IO binding.")),t.jsepOnReleaseSession?.(e),t.webnnOnReleaseSession?.(e),t.webgpuOnReleaseSession?.(e),r.forEach(l=>t._OrtFree(l)),s.forEach(l=>t._OrtFree(l)),t._OrtReleaseSession(n)!==0&&Ve("Can't release session."),Zt.delete(e)},Dr=async(e,t,i,n,r,s,a=!1)=>{if(!e){t.push(0);return}let o=We(),l=o.PTR_SIZE,u=e[0],d=e[1],c=e[3],p=c,h,m;if(u==="string"&&(c==="gpu-buffer"||c==="ml-tensor"))throw new Error("String tensor is not supported on GPU.");if(a&&c!=="gpu-buffer")throw new Error(`External buffer must be provided for input/output index ${s} when enableGraphCapture is true.`);if(c==="gpu-buffer"){let w=e[2].gpuBuffer;m=ei(Jt(u),d);{let g=o.jsepRegisterBuffer;if(!g)throw new Error('Tensor location "gpu-buffer" is not supported without using WebGPU.');h=g(n,s,w,m)}}else if(c==="ml-tensor"){let w=e[2].mlTensor;m=ei(Jt(u),d);let g=o.webnnRegisterMLTensor;if(!g)throw new Error('Tensor location "ml-tensor" is not supported without using WebNN.');h=g(n,w,Jt(u),d)}else{let w=e[2];if(Array.isArray(w)){m=l*w.length,h=o._malloc(m),i.push(h);for(let g=0;g<w.length;g++){if(typeof w[g]!="string")throw new TypeError(`tensor data at index ${g} is not a string`);o.setValue(h+g*l,It(w[g],i),"*")}}else{let g=o.webnnIsGraphInput,T=o.webnnIsGraphOutput;if(u!=="string"&&g&&T){let x=o.UTF8ToString(r);if(g(n,x)||T(n,x)){let I=Jt(u);m=ei(I,d),p="ml-tensor";let O=o.webnnCreateTemporaryTensor,z=o.webnnUploadTensor;if(!O||!z)throw new Error('Tensor location "ml-tensor" is not supported without using WebNN.');let N=await O(n,I,d);z(N,new Uint8Array(w.buffer,w.byteOffset,w.byteLength)),h=N}else m=w.byteLength,h=o._malloc(m),i.push(h),o.HEAPU8.set(new Uint8Array(w.buffer,w.byteOffset,m),h)}else m=w.byteLength,h=o._malloc(m),i.push(h),o.HEAPU8.set(new Uint8Array(w.buffer,w.byteOffset,m),h)}}let _=o.stackSave(),$=o.stackAlloc(4*d.length);try{d.forEach((g,T)=>o.setValue($+T*l,g,l===4?"i32":"i64"));let w=o._OrtCreateTensor(Jt(u),h,m,$,d.length,Sn(p));w===0&&Ve(`Can't create tensor for input/output. session=${n}, index=${s}.`),t.push(w)}finally{o.stackRestore(_)}},Br=async(e,t,i,n,r,s)=>{let a=We(),o=a.PTR_SIZE,l=Zt.get(e);if(!l)throw new Error(`cannot run inference. invalid session id: ${e}`);let u=l[0],d=l[1],c=l[2],p=l[3],h=l[4],m=l[5],_=t.length,$=n.length,w=0,g=[],T=[],x=[],I=[],O=a.stackSave(),z=a.stackAlloc(_*o),N=a.stackAlloc(_*o),q=a.stackAlloc($*o),te=a.stackAlloc($*o);try{[w,g]=ds(s),Ue("wasm prepareInputOutputTensor");for(let ne=0;ne<_;ne++)await Dr(i[ne],T,I,e,d[t[ne]],t[ne],h);for(let ne=0;ne<$;ne++)await Dr(r[ne],x,I,e,c[n[ne]],_+n[ne],h);je("wasm prepareInputOutputTensor");for(let ne=0;ne<_;ne++)a.setValue(z+ne*o,T[ne],"*"),a.setValue(N+ne*o,d[t[ne]],"*");for(let ne=0;ne<$;ne++)a.setValue(q+ne*o,x[ne],"*"),a.setValue(te+ne*o,c[n[ne]],"*");if(p&&!m){let{handle:ne,outputPreferredLocations:Te,outputPreferredLocationsEncoded:he}=p;if(d.length!==_)throw new Error(`input count from feeds (${_}) is expected to be always equal to model's input count (${d.length}).`);Ue("wasm bindInputsOutputs");for(let ae=0;ae<_;ae++){let Oe=t[ae];await a._OrtBindInput(ne,d[Oe],T[ae])!==0&&Ve(`Can't bind input[${ae}] for session=${e}.`)}for(let ae=0;ae<$;ae++){let Oe=n[ae];r[ae]?.[3]?a._OrtBindOutput(ne,c[Oe],x[ae],0)!==0&&Ve(`Can't bind pre-allocated output[${ae}] for session=${e}.`):a._OrtBindOutput(ne,c[Oe],0,he[Oe])!==0&&Ve(`Can't bind output[${ae}] to ${Te[ae]} for session=${e}.`)}je("wasm bindInputsOutputs"),Zt.set(e,[u,d,c,p,h,!0])}a.jsepOnRunStart?.(u),a.webnnOnRunStart?.(u);let ye;p?ye=await a._OrtRunWithBinding(u,p.handle,$,q,w):ye=await a._OrtRun(u,N,z,_,te,$,q,w),ye!==0&&Ve("failed to call OrtRun().");let de=[],be=[];Ue("wasm ProcessOutputTensor");for(let ne=0;ne<$;ne++){let Te=Number(a.getValue(q+ne*o,"*"));if(Te===x[ne]){de.push(r[ne]);continue}let he=a.stackSave(),ae=a.stackAlloc(4*o),Oe=!1,ce,Ge=0;try{a._OrtGetTensorData(Te,ae,ae+o,ae+2*o,ae+3*o)!==0&&Ve(`Can't access output tensor data on index ${ne}.`);let W=o===4?"i32":"i64",ee=Number(a.getValue(ae,W));Ge=a.getValue(ae+o,"*");let Se=a.getValue(ae+o*2,"*"),Le=Number(a.getValue(ae+o*3,W)),ct=[];for(let pt=0;pt<Le;pt++)ct.push(Number(a.getValue(Se+pt*o,W)));a._OrtFree(Se)!==0&&Ve("Can't free memory for tensor dims.");let Nt=ct.reduce((pt,nt)=>pt*nt,1);ce=qt(ee);let Mi=p?.outputPreferredLocations[n[ne]];if(ce==="string"){if(Mi==="gpu-buffer"||Mi==="ml-tensor")throw new Error("String tensor is not supported on GPU.");let pt=[];for(let nt=0;nt<Nt;nt++){let jt=a.getValue(Ge+nt*o,"*"),_f=a.getValue(Ge+(nt+1)*o,"*"),yf=nt===Nt-1?void 0:_f-jt;pt.push(a.UTF8ToString(jt,yf))}de.push([ce,ct,pt,"cpu"])}else if(Mi==="gpu-buffer"&&Nt>0){let pt=a.jsepGetBuffer;if(!pt)throw new Error('preferredLocation "gpu-buffer" is not supported without using WebGPU.');let nt=pt(Ge),jt=ei(ee,Nt);if(jt===void 0||!$n(ce))throw new Error(`Unsupported data type: ${ce}`);Oe=!0,de.push([ce,ct,{gpuBuffer:nt,download:a.jsepCreateDownloader(nt,jt,ce),dispose:()=>{a._OrtReleaseTensor(Te)!==0&&Ve("Can't release tensor.")}},"gpu-buffer"])}else if(Mi==="ml-tensor"&&Nt>0){let pt=a.webnnEnsureTensor,nt=a.webnnIsGraphInputOutputTypeSupported;if(!pt||!nt)throw new Error('preferredLocation "ml-tensor" is not supported without using WebNN.');if(ei(ee,Nt)===void 0||!xn(ce))throw new Error(`Unsupported data type: ${ce}`);if(!nt(e,ce,!1))throw new Error(`preferredLocation "ml-tensor" for ${ce} output is not supported by current WebNN Context.`);let jt=await pt(e,Ge,ee,ct,!1);Oe=!0,de.push([ce,ct,{mlTensor:jt,download:a.webnnCreateMLTensorDownloader(Ge,ce),dispose:()=>{a.webnnReleaseTensorId(Ge),a._OrtReleaseTensor(Te)}},"ml-tensor"])}else if(Mi==="ml-tensor-cpu-output"&&Nt>0){let pt=a.webnnCreateMLTensorDownloader(Ge,ce)(),nt=de.length;Oe=!0,be.push((async()=>{let jt=[nt,await pt];return a.webnnReleaseTensorId(Ge),a._OrtReleaseTensor(Te),jt})()),de.push([ce,ct,[],"cpu"])}else{let pt=Ui(ce),nt=new pt(Nt);new Uint8Array(nt.buffer,nt.byteOffset,nt.byteLength).set(a.HEAPU8.subarray(Ge,Ge+nt.byteLength)),de.push([ce,ct,nt,"cpu"])}}finally{a.stackRestore(he),ce==="string"&&Ge&&a._free(Ge),Oe||a._OrtReleaseTensor(Te)}}p&&!h&&(a._OrtClearBoundOutputs(p.handle)!==0&&Ve("Can't clear bound outputs."),Zt.set(e,[u,d,c,p,h,!1]));for(let[ne,Te]of await Promise.all(be))de[ne][2]=Te;return je("wasm ProcessOutputTensor"),de}finally{a.webnnOnRunEnd?.(u),a.stackRestore(O),T.forEach(ye=>a._OrtReleaseTensor(ye)),x.forEach(ye=>a._OrtReleaseTensor(ye)),I.forEach(ye=>a._free(ye)),w!==0&&a._OrtReleaseRunOptions(w),g.forEach(ye=>a._free(ye))}},Pr=e=>{let t=We(),i=Zt.get(e);if(!i)throw new Error("invalid session id");let n=i[0],r=t._OrtEndProfiling(n);r===0&&Ve("Can't get an profile file name."),t._OrtFree(r)},Nr=e=>{let t=[];for(let i of e){let n=i[2];!Array.isArray(n)&&"buffer"in n&&t.push(n.buffer)}return t}}),Qt,kt,gi,Ri,Oi,sn,Vr,an,oi,li,zc,Rc,Oc,Mc,Fc,Dc,Bc,Pc,Nc=k(()=>{wt(),Ac(),Yt(),_n(),Qt=()=>!!oe.wasm.proxy&&typeof document<"u",gi=!1,Ri=!1,Oi=!1,an=new Map,oi=(e,t)=>{let i=an.get(e);i?i.push(t):an.set(e,[t])},li=()=>{if(gi||!Ri||Oi||!kt)throw new Error("worker not ready")},zc=e=>{switch(e.data.type){case"init-wasm":gi=!1,e.data.err?(Oi=!0,Vr[1](e.data.err)):(Ri=!0,Vr[0]()),sn&&(URL.revokeObjectURL(sn),sn=void 0);break;case"init-ep":case"copy-from":case"create":case"release":case"run":case"end-profiling":{let t=an.get(e.data.type);e.data.err?t.shift()[1](e.data.err):t.shift()[0](e.data.out);break}}},Rc=async()=>{if(!Ri){if(gi)throw new Error("multiple calls to 'initWasm()' detected.");if(Oi)throw new Error("previous call to 'initWasm()' failed.");if(gi=!0,Qt())return new Promise((e,t)=>{kt?.terminate(),ss().then(([i,n])=>{try{kt=n,kt.onerror=s=>t(s),kt.onmessage=zc,Vr=[e,t];let r={type:"init-wasm",in:oe};if(!r.in.wasm.wasmPaths&&i){let s=fn();s&&(r.in.wasm.wasmPaths=s)}kt.postMessage(r),sn=i}catch(r){t(r)}},t)});try{await bn(oe.wasm),await zr(oe),Ri=!0}catch(e){throw Oi=!0,e}finally{gi=!1}}},Oc=async e=>{if(Qt())return li(),new Promise((t,i)=>{oi("init-ep",[t,i]);let n={type:"init-ep",in:{epName:e,env:oe}};kt.postMessage(n)});await Rr(oe,e)},Mc=async e=>Qt()?(li(),new Promise((t,i)=>{oi("copy-from",[t,i]);let n={type:"copy-from",in:{buffer:e}};kt.postMessage(n,[e.buffer])})):rn(e),Fc=async(e,t)=>{if(Qt()){if(t?.preferredOutputLocation)throw new Error('session option "preferredOutputLocation" is not supported for proxy.');return li(),new Promise((i,n)=>{oi("create",[i,n]);let r={type:"create",in:{model:e,options:{...t}}},s=[];e instanceof Uint8Array&&s.push(e.buffer),kt.postMessage(r,s)})}else return Mr(e,t)},Dc=async e=>{if(Qt())return li(),new Promise((t,i)=>{oi("release",[t,i]);let n={type:"release",in:e};kt.postMessage(n)});Fr(e)},Bc=async(e,t,i,n,r,s)=>{if(Qt()){if(i.some(a=>a[3]!=="cpu"))throw new Error("input tensor on GPU is not supported for proxy.");if(r.some(a=>a))throw new Error("pre-allocated output tensor is not supported for proxy.");return li(),new Promise((a,o)=>{oi("run",[a,o]);let l=i,u={type:"run",in:{sessionId:e,inputIndices:t,inputs:l,outputIndices:n,options:s}};kt.postMessage(u,Nr(l))})}else return Br(e,t,i,n,r,s)},Pc=async e=>{if(Qt())return li(),new Promise((t,i)=>{oi("end-profiling",[t,i]);let n={type:"end-profiling",in:e};kt.postMessage(n)});Pr(e)}}),Lr,Vc,Lc,ff=k(()=>{wt(),Nc(),_e(),ie(),gs(),Lr=(e,t)=>{switch(e.location){case"cpu":return[e.type,e.dims,e.data,"cpu"];case"gpu-buffer":return[e.type,e.dims,{gpuBuffer:e.gpuBuffer},"gpu-buffer"];case"ml-tensor":return[e.type,e.dims,{mlTensor:e.mlTensor},"ml-tensor"];default:throw new Error(`invalid data location: ${e.location} for ${t()}`)}},Vc=e=>{switch(e[3]){case"cpu":return new lt(e[0],e[2],e[1]);case"gpu-buffer":{let t=e[0];if(!$n(t))throw new Error(`not supported data type: ${t} for deserializing GPU tensor`);let{gpuBuffer:i,download:n,dispose:r}=e[2];return lt.fromGpuBuffer(i,{dataType:t,dims:e[1],download:n,dispose:r})}case"ml-tensor":{let t=e[0];if(!xn(t))throw new Error(`not supported data type: ${t} for deserializing MLTensor tensor`);let{mlTensor:i,download:n,dispose:r}=e[2];return lt.fromMLTensor(i,{dataType:t,dims:e[1],download:n,dispose:r})}default:throw new Error(`invalid data location: ${e[3]}`)}},Lc=class{async fetchModelAndCopyToWasmMemory(e){return Mc(await kn(e))}async loadModel(e,t){ue();let i;typeof e=="string"?i=await this.fetchModelAndCopyToWasmMemory(e):i=e,[this.sessionId,this.inputNames,this.outputNames,this.inputMetadata,this.outputMetadata]=await Fc(i,t),Pe()}async dispose(){return Dc(this.sessionId)}async run(e,t,i){ue();let n=[],r=[];Object.entries(e).forEach(c=>{let p=c[0],h=c[1],m=this.inputNames.indexOf(p);if(m===-1)throw new Error(`invalid input '${p}'`);n.push(h),r.push(m)});let s=[],a=[];Object.entries(t).forEach(c=>{let p=c[0],h=c[1],m=this.outputNames.indexOf(p);if(m===-1)throw new Error(`invalid output '${p}'`);s.push(h),a.push(m)});let o=n.map((c,p)=>Lr(c,()=>`input "${this.inputNames[r[p]]}"`)),l=s.map((c,p)=>c?Lr(c,()=>`output "${this.outputNames[a[p]]}"`):null),u=await Bc(this.sessionId,r,o,a,l,i),d={};for(let c=0;c<u.length;c++)d[this.outputNames[a[c]]]=s[c]??Vc(u[c]);return Pe(),d}startProfiling(){}endProfiling(){Pc(this.sessionId)}}}),Uc={};L(Uc,{OnnxruntimeWebAssemblyBackend:()=>qr,initializeFlags:()=>Ur,wasmBackend:()=>qc});var Ur,qr,qc,hf=k(()=>{wt(),Nc(),ff(),Ur=()=>{(typeof oe.wasm.initTimeout!="number"||oe.wasm.initTimeout<0)&&(oe.wasm.initTimeout=0);let e=oe.wasm.simd;if(typeof e!="boolean"&&e!==void 0&&e!=="fixed"&&e!=="relaxed"&&(console.warn(`Property "env.wasm.simd" is set to unknown value "${e}". Reset it to \`false\` and ignore SIMD feature checking.`),oe.wasm.simd=!1),typeof oe.wasm.proxy!="boolean"&&(oe.wasm.proxy=!1),typeof oe.wasm.trace!="boolean"&&(oe.wasm.trace=!1),typeof oe.wasm.numThreads!="number"||!Number.isInteger(oe.wasm.numThreads)||oe.wasm.numThreads<=0)if(typeof self<"u"&&!self.crossOriginIsolated)oe.wasm.numThreads=1;else{let t=typeof navigator>"u"?A("node:os").cpus().length:navigator.hardwareConcurrency;oe.wasm.numThreads=Math.min(4,Math.ceil((t||1)/2))}},qr=class{async init(e){Ur(),await Rc(),await Oc(e)}async createInferenceSessionHandler(e,t){let i=new Lc;return await i.loadModel(e,t),i}},qc=new qr}),Wc={};L(Wc,{InferenceSession:()=>ut,TRACE:()=>St,TRACE_EVENT_BEGIN:()=>Ue,TRACE_EVENT_END:()=>je,TRACE_FUNC_BEGIN:()=>ue,TRACE_FUNC_END:()=>Pe,Tensor:()=>lt,default:()=>gf,env:()=>oe,registerBackend:()=>V}),wt(),wt(),wt();var mf="1.23.0",gf=Ut;{let e=(hf(),we(Uc)).wasmBackend;V("webgpu",e,5),V("webnn",e,5),V("cpu",e,10),V("wasm",e,10)}return Object.defineProperty(oe.versions,"web",{value:mf,enumerable:!0}),we(Wc)})();/**
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
 */E.exports=b})(ap);var up=ap.exports,Yr={},dp={};Object.defineProperty(dp,"__esModule",{value:!0});var cn={},cp;Object.defineProperty(cn,"__esModule",{value:!0});cn.SileroLegacy=void 0;const Jc=wi;class Jr{constructor(f,b,v,S,y){this.ortInstance=f,this._session=b,this._h=v,this._c=S,this._sr=y,this.reset_state=()=>{const C=Array(128).fill(0);this._h=new this.ortInstance.Tensor("float32",C,[2,1,64]),this._c=new this.ortInstance.Tensor("float32",C,[2,1,64])},this.process=async C=>{const k={input:new this.ortInstance.Tensor("float32",C,[1,C.length]),h:this._h,c:this._c,sr:this._sr},L=await this._session.run(k);this._h=L.hn,this._c=L.cn;const[X]=L.output?.data;return{notSpeech:1-X,isSpeech:X}}}}cn.SileroLegacy=Jr;cp=Jr;Jr.new=async(E,f)=>{Jc.log.debug("initializing vad");const b=await f(),v=await E.InferenceSession.create(b),S=new E.Tensor("int64",[16000n]),y=Array(2*64).fill(0),C=new E.Tensor("float32",y,[2,1,64]),A=new E.Tensor("float32",y,[2,1,64]);return Jc.log.debug("vad is initialized"),new cp(E,v,C,A,S)};var pn={},pp;Object.defineProperty(pn,"__esModule",{value:!0});pn.SileroV5=void 0;const ep=wi;function fp(E){const f=Array(256).fill(0);return new E.Tensor("float32",f,[2,1,128])}class es{constructor(f,b,v,S){this._session=f,this._state=b,this._sr=v,this.ortInstance=S,this.reset_state=()=>{this._state=fp(this.ortInstance)},this.process=async y=>{const A={input:new this.ortInstance.Tensor("float32",y,[1,y.length]),state:this._state,sr:this._sr},k=await this._session.run(A);this._state=k.stateN;const[L]=k.output?.data;return{notSpeech:1-L,isSpeech:L}}}}pn.SileroV5=es;pp=es;es.new=async(E,f)=>{ep.log.debug("Loading VAD...");const b=await f(),v=await E.InferenceSession.create(b),S=new E.Tensor("int64",[16000n]),y=fp(E);return ep.log.debug("...finished loading VAD"),new pp(v,y,S,E)};(function(E){var f=et&&et.__createBinding||(Object.create?function(y,C,A,k){k===void 0&&(k=A);var L=Object.getOwnPropertyDescriptor(C,A);(!L||("get"in L?!C.__esModule:L.writable||L.configurable))&&(L={enumerable:!0,get:function(){return C[A]}}),Object.defineProperty(y,k,L)}:function(y,C,A,k){k===void 0&&(k=A),y[k]=C[A]}),b=et&&et.__exportStar||function(y,C){for(var A in y)A!=="default"&&!Object.prototype.hasOwnProperty.call(C,A)&&f(C,y,A)};Object.defineProperty(E,"__esModule",{value:!0}),E.SileroV5=E.SileroLegacy=void 0,b(dp,E);var v=cn;Object.defineProperty(E,"SileroLegacy",{enumerable:!0,get:function(){return v.SileroLegacy}});var S=pn;Object.defineProperty(E,"SileroV5",{enumerable:!0,get:function(){return S.SileroV5}})})(Yr);var Pi={};Object.defineProperty(Pi,"__esModule",{value:!0});Pi.Resampler=void 0;const Lf=wi;class Uf{constructor(f){this.options=f,this.process=b=>{const v=[];for(const S of b)for(this.inputBuffer.push(S);this.hasEnoughDataForFrame();){const y=this.generateOutputFrame();v.push(y)}return v},f.nativeSampleRate<16e3&&Lf.log.error("nativeSampleRate is too low. Should have 16000 = targetSampleRate <= nativeSampleRate"),this.inputBuffer=[]}async*stream(f){for(const b of f)for(this.inputBuffer.push(b);this.hasEnoughDataForFrame();)yield this.generateOutputFrame()}hasEnoughDataForFrame(){return this.inputBuffer.length*this.options.targetSampleRate/this.options.nativeSampleRate>=this.options.targetFrameSize}generateOutputFrame(){const f=new Float32Array(this.options.targetFrameSize);let b=0,v=0;for(;b<this.options.targetFrameSize;){let S=0,y=0;for(;v<Math.min(this.inputBuffer.length,(b+1)*this.options.nativeSampleRate/this.options.targetSampleRate);){const C=this.inputBuffer[v];C!==void 0&&(S+=C,y++),v++}f[b]=S/y,b++}return this.inputBuffer=this.inputBuffer.slice(v),f}}Pi.Resampler=Uf;(function(E){var f=et&&et.__createBinding||(Object.create?function(Y,J,V,H){H===void 0&&(H=V);var j=Object.getOwnPropertyDescriptor(J,V);(!j||("get"in j?!J.__esModule:j.writable||j.configurable))&&(j={enumerable:!0,get:function(){return J[V]}}),Object.defineProperty(Y,H,j)}:function(Y,J,V,H){H===void 0&&(H=V),Y[H]=J[V]}),b=et&&et.__setModuleDefault||(Object.create?function(Y,J){Object.defineProperty(Y,"default",{enumerable:!0,value:J})}:function(Y,J){Y.default=J}),v=et&&et.__importStar||function(Y){if(Y&&Y.__esModule)return Y;var J={};if(Y!=null)for(var V in Y)V!=="default"&&Object.prototype.hasOwnProperty.call(Y,V)&&f(J,Y,V);return b(J,Y),J};Object.defineProperty(E,"__esModule",{value:!0}),E.NonRealTimeVAD=E.defaultNonRealTimeVADOptions=void 0;const S=v(up),y=Bi,C=yi,A=Lt,k=ci,L=Yr,X=Pi;E.defaultNonRealTimeVADOptions={...A.defaultFrameProcessorOptions,modelURL:y.baseAssetPath+"silero_vad_legacy.onnx",modelFetcher:C.defaultModelFetcher};class we{static async new(J={}){const V={...E.defaultNonRealTimeVADOptions,...J};(0,A.validateOptions)(V),V.ortConfig!==void 0&&V.ortConfig(S);const H=()=>V.modelFetcher(V.modelURL),j=await L.SileroLegacy.new(S,H),K=new A.FrameProcessor(j.process,j.reset_state,{positiveSpeechThreshold:V.positiveSpeechThreshold,negativeSpeechThreshold:V.negativeSpeechThreshold,redemptionMs:V.redemptionMs,preSpeechPadMs:V.preSpeechPadMs,minSpeechMs:V.minSpeechMs,submitUserSpeechOnPause:V.submitUserSpeechOnPause},1536/16);return K.resume(),new this(H,S,V,K)}constructor(J,V,H,j){this.modelFetcher=J,this.ort=V,this.options=H,this.frameProcessor=j,this.frameSamples=1536}async*run(J,V){const H={nativeSampleRate:V,targetSampleRate:16e3,targetFrameSize:this.frameSamples},j=new X.Resampler(H);let K=0,R=0,D=0;for await(const U of j.stream(J)){const P=[];await this.frameProcessor.process(U,G=>{P.push(G)});for(const G of P)switch(G.msg){case k.Message.SpeechStart:K=D*this.frameSamples/16;break;case k.Message.SpeechEnd:R=(D+1)*this.frameSamples/16,yield{audio:G.audio,start:K,end:R};break}D++}const F=[];this.frameProcessor.endSegment(U=>{F.push(U)});for(const U of F)switch(U.msg){case k.Message.SpeechEnd:yield{audio:U.audio,start:K,end:D*this.frameSamples/16}}}}E.NonRealTimeVAD=we})(sp);var Vt={};Object.defineProperty(Vt,"__esModule",{value:!0});Vt.audioFileToArray=Vt.encodeWAV=Vt.arrayBufferToBase64=Vt.minFramesForTargetMS=void 0;function qf(E,f,b=16e3){return Math.ceil(E*b/1e3/f)}Vt.minFramesForTargetMS=qf;function Wf(E){const f=new Uint8Array(E),b=f.byteLength,v=new Array(b);for(var S=0;S<b;S++){const y=f[S];if(y===void 0)break;v[S]=String.fromCharCode(y)}return btoa(v.join(""))}Vt.arrayBufferToBase64=Wf;function Gf(E,f=3,b=16e3,v=1,S=32){var y=S/8,C=v*y,A=new ArrayBuffer(44+E.length*y),k=new DataView(A);return ln(k,0,"RIFF"),k.setUint32(4,36+E.length*y,!0),ln(k,8,"WAVE"),ln(k,12,"fmt "),k.setUint32(16,16,!0),k.setUint16(20,f,!0),k.setUint16(22,v,!0),k.setUint32(24,b,!0),k.setUint32(28,b*C,!0),k.setUint16(32,C,!0),k.setUint16(34,S,!0),ln(k,36,"data"),k.setUint32(40,E.length*y,!0),f===1?Hf(k,44,E):jf(k,44,E),A}Vt.encodeWAV=Gf;function jf(E,f,b){for(var v=0;v<b.length;v++,f+=4)E.setFloat32(f,b[v],!0)}function Hf(E,f,b){for(var v=0;v<b.length;v++,f+=2){var S=Math.max(-1,Math.min(1,b[v]));E.setInt16(f,S<0?S*32768:S*32767,!0)}}function ln(E,f,b){for(var v=0;v<b.length;v++)E.setUint8(f+v,b.charCodeAt(v))}async function Kf(E){const f=new OfflineAudioContext(1,1,44100),b=new FileReader;let v=null;if(await new Promise(C=>{b.addEventListener("loadend",A=>{const k=b.result;f.decodeAudioData(k,L=>{v=L,f.startRendering().then(X=>{console.log("Rendering completed successfully"),C()}).catch(X=>{console.error(`Rendering failed: ${X}`)})},L=>{console.log(`Error with decoding audio data: ${L}`)})}),b.readAsArrayBuffer(E)}),v===null)throw Error("some shit");let S=v,y=new Float32Array(S.length);for(let C=0;C<S.length;C++)for(let A=0;A<S.numberOfChannels;A++)y[C]+=S.getChannelData(A)[C];return{audio:y,sampleRate:S.sampleRate}}Vt.audioFileToArray=Kf;var hp={};(function(E){var f=et&&et.__createBinding||(Object.create?function(K,R,D,F){F===void 0&&(F=D);var U=Object.getOwnPropertyDescriptor(R,D);(!U||("get"in U?!R.__esModule:U.writable||U.configurable))&&(U={enumerable:!0,get:function(){return R[D]}}),Object.defineProperty(K,F,U)}:function(K,R,D,F){F===void 0&&(F=D),K[F]=R[D]}),b=et&&et.__setModuleDefault||(Object.create?function(K,R){Object.defineProperty(K,"default",{enumerable:!0,value:R})}:function(K,R){K.default=R}),v=et&&et.__importStar||function(K){if(K&&K.__esModule)return K;var R={};if(K!=null)for(var D in K)D!=="default"&&Object.prototype.hasOwnProperty.call(K,D)&&f(R,K,D);return b(R,K),R};Object.defineProperty(E,"__esModule",{value:!0}),E.AudioNodeVAD=E.MicVAD=E.getDefaultRealTimeVADOptions=E.ort=E.DEFAULT_MODEL=void 0;const S=v(up),y=yi,C=Lt,A=wi,k=ci,L=Yr,X=Pi;E.DEFAULT_MODEL="legacy",E.ort=S;const we="vad.worklet.bundle.min.js",Y="silero_vad_v5.onnx",J="silero_vad_legacy.onnx",V=K=>({...C.defaultFrameProcessorOptions,onFrameProcessed:(R,D)=>{},onVADMisfire:()=>{A.log.debug("VAD misfire")},onSpeechStart:()=>{A.log.debug("Detected speech start")},onSpeechEnd:()=>{A.log.debug("Detected speech end")},onSpeechRealStart:()=>{A.log.debug("Detected real speech start")},baseAssetPath:"./",onnxWASMBasePath:"./",model:K,workletOptions:{},getStream:async()=>await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:!0,autoGainControl:!0,noiseSuppression:!0}}),pauseStream:async R=>{R.getTracks().forEach(D=>{D.stop()})},resumeStream:async R=>await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:!0,autoGainControl:!0,noiseSuppression:!0}}),ortConfig:R=>{R.env.logLevel="error"},startOnLoad:!0});E.getDefaultRealTimeVADOptions=V;class H{static async new(R={}){const D={...(0,E.getDefaultRealTimeVADOptions)(R.model??E.DEFAULT_MODEL),...R};(0,C.validateOptions)(D);const F=new AudioContext,U=await j.new(F,D),P=new H(D,F,U);if(D.startOnLoad)try{await P.start()}catch(G){console.error("Error starting micVad",G)}return P}constructor(R,D,F,U=!1){this.options=R,this.audioContext=D,this.audioNodeVAD=F,this.listening=U,this.initialized=!1,this.pause=()=>{this.stream&&this.options.pauseStream(this.stream),this.audioNodeVAD.pause(),this.listening=!1},this.resume=async()=>{if(!this.stream){console.warn("Stream not initialized");return}this.stream=await this.options.resumeStream(this.stream),this.sourceNode&&this.sourceNode.disconnect(),this.sourceNode=new MediaStreamAudioSourceNode(this.audioContext,{mediaStream:this.stream}),this.audioNodeVAD.receive(this.sourceNode)},this.start=async()=>{this.initialized||(this.initialized=!0,this.stream=await this.options.getStream(),this.sourceNode=new MediaStreamAudioSourceNode(this.audioContext,{mediaStream:this.stream}),this.audioNodeVAD.receive(this.sourceNode)),this.stream?.active?(this.audioNodeVAD.start(),this.listening=!0):(await this.resume(),this.audioNodeVAD.start(),this.listening=!0)},this.destroy=()=>{this.listening&&this.pause(),this.stream?this.options.pauseStream(this.stream):console.warn("Stream not initialized"),this.sourceNode?this.sourceNode.disconnect():console.warn("Source node not initialized"),this.audioNodeVAD.destroy(),this.audioContext.close()},this.setOptions=P=>{this.audioNodeVAD.setFrameProcessorOptions(P)}}}E.MicVAD=H;class j{static async new(R,D={}){const F={...(0,E.getDefaultRealTimeVADOptions)(D.model??E.DEFAULT_MODEL),...D};(0,C.validateOptions)(F),E.ort.env.wasm.wasmPaths=F.onnxWASMBasePath,F.ortConfig!==void 0&&F.ortConfig(E.ort);const U=F.model==="v5"?Y:J,P=F.baseAssetPath+U,G=F.model==="v5"?L.SileroV5.new:L.SileroLegacy.new;let oe;try{oe=await G(E.ort,()=>(0,y.defaultModelFetcher)(P))}catch(Ce){throw console.error(`Encountered an error while loading model file ${P}`),Ce}const Ae=F.model==="v5"?512:1536,me=Ae/16,qe=new C.FrameProcessor(oe.process,oe.reset_state,{positiveSpeechThreshold:F.positiveSpeechThreshold,negativeSpeechThreshold:F.negativeSpeechThreshold,redemptionMs:F.redemptionMs,preSpeechPadMs:F.preSpeechPadMs,minSpeechMs:F.minSpeechMs,submitUserSpeechOnPause:F.submitUserSpeechOnPause},me),Ne=new j(R,F,qe,Ae,me);return await Ne.setupAudioNode(),Ne}constructor(R,D,F,U,P){this.ctx=R,this.options=D,this.frameSamples=U,this.msPerFrame=P,this.pause=()=>{this.frameProcessor.pause(this.handleFrameProcessorEvent)},this.start=()=>{this.frameProcessor.resume()},this.receive=G=>{G.connect(this.audioNode)},this.processFrame=async G=>{await this.frameProcessor.process(G,this.handleFrameProcessorEvent)},this.handleFrameProcessorEvent=G=>{switch(G.msg){case k.Message.FrameProcessed:this.options.onFrameProcessed(G.probs,G.frame);break;case k.Message.SpeechStart:this.options.onSpeechStart();break;case k.Message.SpeechRealStart:this.options.onSpeechRealStart();break;case k.Message.VADMisfire:this.options.onVADMisfire();break;case k.Message.SpeechEnd:this.options.onSpeechEnd(G.audio);break}},this.destroy=()=>{this.audioNode instanceof AudioWorkletNode&&this.audioNode.port.postMessage({message:k.Message.SpeechStop}),this.audioNode.disconnect(),this.gainNode?.disconnect()},this.setFrameProcessorOptions=G=>{this.frameProcessor.options={...this.frameProcessor.options,...G}},this.frameProcessor=F}async setupAudioNode(){if("audioWorklet"in this.ctx&&typeof AudioWorkletNode=="function")try{const U=this.options.baseAssetPath+we;await this.ctx.audioWorklet.addModule(U);const P=this.options.workletOptions??{};P.processorOptions={...P.processorOptions??{},frameSamples:this.frameSamples},this.audioNode=new AudioWorkletNode(this.ctx,"vad-helper-worklet",P),this.audioNode.port.onmessage=async G=>{switch(G.data?.message){case k.Message.AudioFrame:let oe=G.data.data;oe instanceof ArrayBuffer||(oe=new ArrayBuffer(G.data.data.byteLength),new Uint8Array(oe).set(new Uint8Array(G.data.data)));const Ae=new Float32Array(oe);await this.processFrame(Ae);break}};return}catch(U){console.log("AudioWorklet setup failed, falling back to ScriptProcessor",U)}this.resampler=new X.Resampler({nativeSampleRate:this.ctx.sampleRate,targetSampleRate:16e3,targetFrameSize:this.frameSamples??480});const D=4096;this.audioNode=this.ctx.createScriptProcessor(D,1,1),this.gainNode=this.ctx.createGain(),this.gainNode.gain.value=0;let F=!1;this.audioNode.onaudioprocess=async U=>{if(!F){F=!0;try{const P=U.inputBuffer.getChannelData(0);if(U.outputBuffer.getChannelData(0).fill(0),this.resampler){const oe=this.resampler.process(P);for(const Ae of oe)await this.processFrame(Ae)}}catch(P){console.error("Error processing audio:",P)}finally{F=!1}}},this.audioNode.connect(this.gainNode),this.gainNode.connect(this.ctx.destination)}}E.AudioNodeVAD=j})(hp);(function(E){Object.defineProperty(E,"__esModule",{value:!0}),E.getDefaultRealTimeVADOptions=E.MicVAD=E.DEFAULT_MODEL=E.AudioNodeVAD=E.utils=E.NonRealTimeVAD=E.Message=E.FrameProcessor=E.defaultModelFetcher=E.baseAssetPath=void 0;var f=Bi;Object.defineProperty(E,"baseAssetPath",{enumerable:!0,get:function(){return f.baseAssetPath}});var b=yi;Object.defineProperty(E,"defaultModelFetcher",{enumerable:!0,get:function(){return b.defaultModelFetcher}});var v=Lt;Object.defineProperty(E,"FrameProcessor",{enumerable:!0,get:function(){return v.FrameProcessor}});var S=ci;Object.defineProperty(E,"Message",{enumerable:!0,get:function(){return S.Message}});var y=sp;Object.defineProperty(E,"NonRealTimeVAD",{enumerable:!0,get:function(){return y.NonRealTimeVAD}});const C=Vt;E.utils={audioFileToArray:C.audioFileToArray,minFramesForTargetMS:C.minFramesForTargetMS,arrayBufferToBase64:C.arrayBufferToBase64,encodeWAV:C.encodeWAV};var A=hp;Object.defineProperty(E,"AudioNodeVAD",{enumerable:!0,get:function(){return A.AudioNodeVAD}}),Object.defineProperty(E,"DEFAULT_MODEL",{enumerable:!0,get:function(){return A.DEFAULT_MODEL}}),Object.defineProperty(E,"MicVAD",{enumerable:!0,get:function(){return A.MicVAD}}),Object.defineProperty(E,"getDefaultRealTimeVADOptions",{enumerable:!0,get:function(){return A.getDefaultRealTimeVADOptions}})})(Hr);(function(E){var f=et&&et.__createBinding||(Object.create?function(j,K,R,D){D===void 0&&(D=R);var F=Object.getOwnPropertyDescriptor(K,R);(!F||("get"in F?!K.__esModule:F.writable||F.configurable))&&(F={enumerable:!0,get:function(){return K[R]}}),Object.defineProperty(j,D,F)}:function(j,K,R,D){D===void 0&&(D=R),j[D]=K[R]}),b=et&&et.__setModuleDefault||(Object.create?function(j,K){Object.defineProperty(j,"default",{enumerable:!0,value:K})}:function(j,K){j.default=K}),v=et&&et.__importStar||function(j){if(j&&j.__esModule)return j;var K={};if(j!=null)for(var R in j)R!=="default"&&Object.prototype.hasOwnProperty.call(j,R)&&f(K,j,R);return b(K,j),K};Object.defineProperty(E,"__esModule",{value:!0}),E.useMicVAD=E.getDefaultReactRealTimeVADOptions=E.utils=void 0;const S=Hr,y=v(Z);var C=Hr;Object.defineProperty(E,"utils",{enumerable:!0,get:function(){return C.utils}});const A={userSpeakingThreshold:.6},k=j=>({...(0,S.getDefaultRealTimeVADOptions)(j),...A});E.getDefaultReactRealTimeVADOptions=k;const L=Object.keys(A),X=Object.keys((0,S.getDefaultRealTimeVADOptions)("v5")),we=(j,K)=>j.reduce((R,D)=>(R[D]=K[D],R),{});function Y(j){const K=j.model??S.DEFAULT_MODEL;j={...(0,E.getDefaultReactRealTimeVADOptions)(K),...j};const R=we(L,j),D=we(X,j);return[R,D]}function J(j){const K=y.default.useRef(j);return H(()=>{K.current=j}),y.default.useCallback((...R)=>K.current.apply(void 0,R),[])}function V(j){const[K,R]=Y(j),[D,F]=(0,y.useState)(!1),[U,P]=(0,y.useState)(!0),[G,oe]=(0,y.useState)(!1),[Ae,me]=(0,y.useState)(!1),[qe,Ne]=(0,y.useState)(null),Ce=J(R.onFrameProcessed);R.onFrameProcessed=J((it,ht)=>{const ot=it.isSpeech>K.userSpeakingThreshold;F(ot),Ce(it,ht)});const{onSpeechEnd:Ke,onSpeechStart:ze,onSpeechRealStart:Ye,onVADMisfire:tt}=R,ft=J(Ke),rt=J(ze),gt=J(tt),Ee=J(Ye);R.onSpeechEnd=ft,R.onSpeechStart=rt,R.onVADMisfire=gt,R.onSpeechRealStart=Ee,(0,y.useEffect)(()=>{let it,ht=!1;return(async()=>{try{if(it=await S.MicVAD.new(R),ht){it.destroy();return}}catch(Me){P(!1),Me instanceof Error?oe(Me.message):oe(String(Me));return}Ne(it),P(!1),R.startOnLoad&&(it?.start(),me(!0))})().catch(Me=>{console.log("Well that didn't work")}),function(){it?.destroy(),ht=!0,!U&&!G&&me(!1)}},[]);const st=()=>{!U&&!G&&(qe?.pause(),me(!1))},vt=()=>{!U&&!G&&(qe?.start(),me(!0))};return{listening:Ae,errored:G,loading:U,userSpeaking:D,pause:st,start:vt,toggle:()=>{Ae?st():vt()}}}E.useMicVAD=V;const H=typeof window<"u"&&typeof window.document<"u"&&typeof window.document.createElement<"u"?y.default.useLayoutEffect:y.default.useEffect})(np);const Zf="https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.28/dist/",Qf="https://cdn.jsdelivr.net/npm/onnxruntime-web@1.23.0/dist/";function mp(E){const f=E?.callbacks,b=E?.sharedStream,v=E?.sensitivity||{},S=Z.useRef(b);Z.useEffect(()=>{S.current=b,console.log("[useDemoVAD] Stream updated:",!!b)},[b]);const y=np.useMicVAD({startOnLoad:!1,baseAssetPath:Zf,onnxWASMBasePath:Qf,getStream:async()=>(console.log("[useDemoVAD] getStream called, streamRef.current:",!!S.current),S.current?(console.log("[useDemoVAD] Using shared stream"),S.current):(console.log("[useDemoVAD] Creating new stream"),await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:!0,noiseSuppression:!0,autoGainControl:!0,channelCount:1}}))),positiveSpeechThreshold:v.positiveSpeechThreshold??.98,negativeSpeechThreshold:v.negativeSpeechThreshold??.85,minSpeechMs:v.minSpeechMs??400,redemptionMs:v.redemptionMs??500,onSpeechStart:()=>{f?.onSpeechStart?.()},onSpeechEnd:C=>{f?.onSpeechEnd?.(C)},onVADMisfire:()=>{f?.onVADMisfire?.()},onFrameProcessed:(C,A)=>{const k=C.isSpeech;f?.onFrameProcessed?.(k,A)}});return{userSpeaking:y.userSpeaking,loading:y.loading,errored:y.errored,pause:y.pause,start:y.start}}const Gr=[{language:"English",code:"en",text:'Say "Hello Gemini" in your native language'},{language:"Spanish",code:"es",text:"Di 'Hola Géminis' en tu idioma nativo."},{language:"Chinese (Simplified)",code:"zh-Hans",text:'用你的母语说"你好，双子座"。'},{language:"Hindi",code:"hi",text:'अपनी मूल भाषा में "नमस्ते जेमिनी" कहिए।'},{language:"Arabic",code:"ar",text:'قل "مرحباً يا چيميني" بلغتك الأم.'},{language:"Portuguese",code:"pt",text:'Diga "Olá Gemini" na sua língua nativa.'},{language:"Bengali",code:"bn",text:"আপনার মাতৃভাষায় 'হ্যালো জেমিনি' বলুন।"},{language:"Russian",code:"ru",text:"Скажи «Привет, Джемини» на своём родном языке."},{language:"Japanese",code:"ja",text:"母国語で「こんにちは、ジェミニ」と言ってください。"},{language:"Punjabi",code:"pa",text:'ਆਪਣੀ ਮਾਂ ਬੋਲੀ ਵਿੱਚ "ਹੈਲੋ ਜੈਮਿਨੀ" ਕਹੋ।'},{language:"German",code:"de",text:'Sag "Hallo Gemini" in deiner Muttersprache.'},{language:"Javanese",code:"jv",text:"Ucapake 'Halo Gemini' nganggo basa ibumu."},{language:"Korean",code:"ko",text:'모국어로 "안녕하세요 제미나이"라고 말해 주세요.'},{language:"French",code:"fr",text:'Dis "Bonjour Gemini" dans ta langue maternelle.'},{language:"Turkish",code:"tr",text:'Ana dilinde "Merhaba Gemini" de.'},{language:"Vietnamese",code:"vi",text:'Nói "Chào Gemini" bằng tiếng mẹ đẻ của bạn.'},{language:"Italian",code:"it",text:`Di' "Ciao Gemini" nella tua lingua madre.`},{language:"Thai",code:"th",text:'พูดว่า "สวัสดี Gemini" ในภาษาแม่ของคุณ.'},{language:"Persian",code:"fa",text:"به زبان مادری خود بگویید 'سلام جِمینی'."},{language:"Polish",code:"pl",text:'Powiedz „Cześć Gemini" w swoim języku ojczystym.'},{language:"Ukrainian",code:"uk",text:"Скажи «Привіт, Дженімі» своєю рідною мовою."},{language:"Urdu",code:"ur",text:"اپنی مادری زبان میں 'ہیلو جیمنی' کہیں۔"},{language:"Indonesian",code:"id",text:"Ucapkan 'Halo Gemini' dalam bahasa ibumu."},{language:"Dutch",code:"nl",text:'Zeg "Hallo Gemini" in je moedertaal.'},{language:"Greek",code:"el",text:"Πες «Γεια σου Gemini» στη μητρική σου γλώσσα."},{language:"Czech",code:"cs",text:'Řekněte „Ahoj Gemini" ve svém rodném jazyce.'},{language:"Swedish",code:"sv",text:'Säg "Hej Gemini" på ditt modersmål.'},{language:"Romanian",code:"ro",text:'Spune "Salut Gemini" în limba ta maternă.'},{language:"Hebrew",code:"iw",text:`אמור "שלום ג'מיני" בשפת האם שלך.`},{language:"Swahili",code:"sw",text:"Sema 'Habari Gemini' kwa lugha yako ya asili."}];function Xf({intervalMs:E=3e3,onDismiss:f}){const[b,v]=Z.useState(0),[S,y]=Z.useState("in");Z.useEffect(()=>{const A=setInterval(()=>{y("out"),setTimeout(()=>{v(k=>(k+1)%Gr.length),y("in")},300)},E);return()=>clearInterval(A)},[E]);const C=Gr[b];return Q.jsxs("div",{className:"greeting-carousel",children:[Q.jsxs("div",{className:"greeting-carousel__content",children:[Q.jsx("div",{className:"greeting-carousel__icon",children:Q.jsxs("svg",{width:"48",height:"48",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",strokeLinecap:"round",strokeLinejoin:"round",children:[Q.jsx("path",{d:"M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"}),Q.jsx("path",{d:"M19 10v2a7 7 0 0 1-14 0v-2"}),Q.jsx("line",{x1:"12",x2:"12",y1:"19",y2:"22"})]})}),Q.jsxs("div",{className:`greeting-carousel__text greeting-carousel__text--${S}`,children:[Q.jsx("div",{className:"greeting-carousel__language",children:C.language}),Q.jsx("div",{className:"greeting-carousel__prompt",children:C.text})]},b),Q.jsx("div",{className:"greeting-carousel__progress",children:Gr.map((A,k)=>Q.jsx("div",{className:`greeting-carousel__dot ${k===b?"greeting-carousel__dot--active":""}`},k))})]}),f&&Q.jsx("button",{className:"greeting-carousel__dismiss",onClick:f,"aria-label":"Dismiss greeting prompt",children:"×"}),Q.jsx("style",{children:`
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
      `})]})}function Yf({schema:E,sectionIndex:f,wsUrl:b,onClose:v,connectionManager:S,status:y}){const[C,A]=Z.useState(S||null),k=Z.useRef(S||null),[L,X]=Z.useState(y||"Ready"),[we,Y]=Z.useState(null),[J,V]=Z.useState(!1),[H,j]=Z.useState(1),[K,R]=Z.useState(new Set),[D,F]=Z.useState({filled:0,total:12}),[U,P]=Z.useState(!1),[G,oe]=Z.useState(!1),[Ae,me]=Z.useState(!1),[qe,Ne]=Z.useState(!1),[Ce,Ke]=Z.useState(!1),ze=Z.useRef(!1),Ye=Z.useRef(null),tt=Z.useRef(!1),ft=Z.useRef({x:0,y:0}),rt=Z.useRef(null),[gt,Ee]=Z.useState(!1),st=Z.useRef(null),vt=Z.useRef(!1),Tt=450,it=Z.useRef(!1),ht=Z.useRef(Date.now()),ot=Z.useRef(null),Me=Z.useRef(0),yt=Z.useRef(!1),lt=6e3,Et=3;Z.useEffect(()=>{let ie=!0;async function fe(){try{console.log("[VoiceOverlay] 🎤 Creating shared audio stream...");const ke=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:!0,noiseSuppression:!0,autoGainControl:!0,channelCount:1,sampleRate:16e3}});ie?(rt.current=ke,Ee(!0),console.log("[VoiceOverlay] ✅ Shared stream ready (AEC enabled)")):ke.getTracks().forEach(Fe=>Fe.stop())}catch(ke){console.error("[VoiceOverlay] ❌ Failed to create shared stream:",ke)}}return fe(),()=>{ie=!1,rt.current&&(rt.current.getTracks().forEach(ke=>ke.stop()),rt.current=null)}},[]);const St=Z.useMemo(()=>({onSpeechStart:()=>{if(G)return;console.log("[VFF VAD] 🎤 User speech started - buffering audio..."),st.current=Date.now(),vt.current=!1,qe&&(console.log("[VoiceOverlay] 🌍 User speaking - hiding greeting carousel"),Ne(!1),ze.current=!0);const ie=C?.getAudioManager();ie&&ie.setVADActive(!0),setTimeout(()=>{const fe=st.current?Date.now()-st.current:0;st.current!==null&&fe>=Tt&&(console.log(`[VFF VAD] ✅ Valid speech detected (${fe}ms) - triggering barge-in`),vt.current=!0,C?.onVADSpeechStart())},Tt)},onSpeechEnd:ie=>{if(G||it.current)return;const fe=st.current?Date.now()-st.current:0,ke=C?.getAudioManager();ke&&ke.setVADActive(!1),vt.current?(console.log(`[VFF VAD] ✅ Valid turn detected (${fe}ms) - completing turn`),C?.onVADSpeechEnd(),Pe()):(console.log(`[VFF VAD] ⚠️ Turn too short (${fe}ms < ${Tt}ms) - no barge-in triggered, discarding`),je()),st.current=null,vt.current=!1},onVADMisfire:()=>{console.log("[VFF VAD] ⚠️ VAD misfire detected"),st.current=null}}),[G,C]),Be=Z.useMemo(()=>({sharedStream:gt?rt.current:null,callbacks:St}),[gt,St]),ue=mp(Be);Z.useEffect(()=>{if(S){k.current=S,A(S);return}if(k.current)return;const ie=ve.initWithSections(E,f),fe=Xr(ie.schema,ke=>{X(ke),Y(null)},"English",rt.current||void 0);return k.current=fe,A(fe),()=>{mt(),S||(k.current&&(k.current.disconnect(),k.current=null),A(null))}},[E,f,S]),Z.useEffect(()=>{y!==void 0&&X(y)},[y]),Z.useEffect(()=>{const ie=L.toLowerCase()==="connected"||L.toLowerCase().startsWith("connected ");ie&&!ze.current&&!qe&&(console.log("[VoiceOverlay] 🌍 Connection established - showing greeting carousel"),Ne(!0)),!ie&&ze.current&&(ze.current=!1)},[L,qe]),Z.useEffect(()=>{const ie=L.toLowerCase()==="connected"||L.toLowerCase().startsWith("connected ");ie&&!G&&!ue.loading&&!ue.errored?ue.start():!ie&&!ue.loading&&ue.pause()},[L,G,ue.loading,ue.errored,ue.start,ue.pause]),Z.useEffect(()=>{let ie=null,fe=!1;return window.vffOnTurnComplete=()=>{console.log("[VFF Watchdog] 📨 Backend signals turn complete (all chunks sent)"),fe=!0},window.vffOnAudioPlaybackStart=()=>{console.log("[VFF Watchdog] 🔊 Gemini started speaking - STOPPING timer"),fe=!1,qe&&(console.log("[VoiceOverlay] 🌍 Gemini speaking - hiding greeting carousel"),Ne(!1),ze.current=!0),ot.current&&(clearInterval(ot.current),ot.current=null)},window.vffOnAudioPlaybackEnd=()=>{ie&&clearTimeout(ie);let ke;yt.current?ke=100:fe?ke=200:ke=2e3,(yt.current||fe)&&console.log(`[VFF Watchdog] 🔊 Audio playback paused - debouncing ${ke}ms (turnComplete=${fe})`),ie=setTimeout(()=>{yt.current?(console.log("[VFF Watchdog] 🚪 Farewell complete (100ms audio silence) - ending Gemini session"),yt.current=!1,mt(),ue.pause(),C&&C.endGeminiSession(),X("Ready"),console.log("[VFF Watchdog] ✅ Gemini session closed, ready to reconnect")):(console.log("[VFF Watchdog] 🔊 Gemini finished speaking - STARTING timer"),fe=!1,je()),ie=null},ke)},()=>{ie&&clearTimeout(ie),delete window.vffOnAudioPlaybackEnd,delete window.vffOnAudioPlaybackStart,delete window.vffOnTurnComplete}},[C,ue]);const Pe=()=>{console.log("[VFF Watchdog] 🗣️ User turn complete - resetting escalation to 0"),Me.current=0,ht.current=Date.now()},Ue=()=>{if(Me.current>=Et){console.log(`[VFF Watchdog] ⏸️ Already at max escalation level ${Et} - waiting for farewell to complete`);return}Me.current++,console.log(`[VFF Watchdog] ⏱️ Inactivity timeout - escalation level ${Me.current}/${Et}`),ht.current=Date.now(),Me.current===1?Ft():Me.current===2?Ct():Me.current>=Et&&ut()},je=()=>{console.log("[VFF Watchdog] 🟢 Starting activity monitoring"),ot.current&&clearInterval(ot.current),Me.current=0,ht.current=Date.now(),ot.current=setInterval(()=>{Date.now()-ht.current>=lt&&Ue()},1e3)},mt=()=>{ot.current&&(clearInterval(ot.current),ot.current=null),Me.current=0},Ft=()=>{if(!C)return;console.log("[VFF Watchdog] 📝 Level 1: Field re-prompt");const ie=sessionStorage.getItem("vff_last_field_hint");if(ie)console.log("[VFF Watchdog] Re-prompting for last field:",ie),C.sendRecoveryPrompt(1,ie);else{const fe=sessionStorage.getItem("vff_state");if(!fe){C.sendRecoveryPrompt(1);return}const ke=JSON.parse(fe),Fe=Kr(ke);if(Fe){const Je=Zr(Fe);C.sendRecoveryPrompt(1,Je)}else C.sendRecoveryPrompt(1)}},Ct=()=>{C&&(console.log("[VFF Watchdog] 👋 Level 2: Are you still there?"),C.sendRecoveryPrompt(2))},ut=()=>{if(!C){console.warn("[VFF Watchdog] Cannot handle Level 3 - no connection manager");return}if(!(L.toLowerCase()==="connected"||L.toLowerCase().startsWith("connected ")||L.toLowerCase()==="switching_section")){console.warn("[VFF Watchdog] Cannot handle Level 3 - not connected (status: "+L+")"),mt(),ue.pause(),X("Ready");return}console.log("[VFF Watchdog] 🚪 Level 3: Closing Gemini session due to inactivity"),yt.current=!0,C.sendRecoveryPrompt(3),setTimeout(()=>{yt.current&&(console.log("[VFF Watchdog] ⏱️ Farewell timeout - forcing disconnect after 15s (audio silence detection failed)"),yt.current=!1,mt(),ue.pause(),C&&C.disconnect(),X("Ready"),console.log("[VFF Watchdog] ✅ Session closed (timeout fallback) and ready to reconnect"))},15e3)},pe=async()=>{if(C)try{if(Y(null),C.isPaused()){await C.resume(),V(!0);return}await C.connect(),await new Promise(ke=>setTimeout(ke,100));const ie=C.getStatus();ie==="connected"||ie==="switching_section"?(await C.startRecording(),!G&&!ue.loading&&!ue.errored?ue.start():ue.loading&&V(!0)):console.error("[VoiceOverlay] Connection status not active, status is:",ie)}catch(ie){console.error("[VoiceOverlay] Connection error:",ie),Y(ie instanceof Error?ie.message:"Connection failed"),X("Connection failed"),mt()}},ge=()=>{C&&(mt(),C.pause(),ue.pause())};Z.useEffect(()=>{if(J&&!ue.loading){if(ue.errored){V(!1);return}ue.start(),V(!1)}},[J,ue.loading,ue.errored,ue.start]);const Ze=async()=>{if(!G||!(L.toLowerCase()==="connected"||L.toLowerCase().startsWith("connected ")||L.toLowerCase()==="switching_section"||L.toLowerCase().startsWith("reconnecting")))return;me(!0);const fe=C?.getAudioManager();fe?.unmuteInput(),fe?.isSpeaking()&&fe.flushAudioQueue(),C?.sendActivityStart()},Dt=()=>{if(!G||!(L.toLowerCase()==="connected"||L.toLowerCase().startsWith("connected ")||L.toLowerCase()==="switching_section"||L.toLowerCase().startsWith("reconnecting")))return;me(!1),C?.getAudioManager()?.muteInput(),C?.sendActivityEnd()};Z.useEffect(()=>{if(!G)return;const ie=L.toLowerCase()==="connected"||L.toLowerCase().startsWith("connected ")||L.toLowerCase()==="switching_section"||L.toLowerCase().startsWith("reconnecting"),fe=Fe=>{if(Fe.code==="Space"){const Je=Fe.target;if(Je.tagName==="INPUT"||Je.tagName==="TEXTAREA")return;Fe.preventDefault(),!Fe.repeat&&ie&&Ze()}},ke=Fe=>{if(Fe.code==="Space"){const Je=Fe.target;if(Je.tagName==="INPUT"||Je.tagName==="TEXTAREA")return;Fe.preventDefault(),ie&&Dt()}};return window.addEventListener("keydown",fe),window.addEventListener("keyup",ke),()=>{window.removeEventListener("keydown",fe),window.removeEventListener("keyup",ke)}},[G,L]),Z.useEffect(()=>{const ie=ve.initWithSections(E,f);j(ie.current_section||1),R(ie.completed_sections||new Set);const fe=ve.getSectionFieldCount(ie);F(fe)},[E,f]),Z.useEffect(()=>{const ie=setInterval(()=>{const fe=ve.load();if(fe){const ke=ve.getSectionFieldCount(fe);if(F(ke),fe.current_section&&fe.current_section!==H&&j(fe.current_section),fe.completed_sections){const Fe=new Set(Array.from(K)),Je=new Set(Array.from(fe.completed_sections));(Fe.size!==Je.size||![...Fe].every(pi=>Je.has(pi)))&&R(Je)}}},1e3);return()=>clearInterval(ie)},[H,K]);const Bt=()=>{if(!confirm(`⚠️ Clear all form data?

This will delete all fields and reload the page.
This action cannot be undone.`))return;ve.clear(),document.querySelectorAll("input, textarea, select").forEach(fe=>{const ke=fe;if(ke.tagName==="INPUT"){const Fe=ke;Fe.type==="checkbox"||Fe.type==="radio"?Fe.checked=!1:Fe.type!=="submit"&&Fe.type!=="button"&&Fe.type!=="hidden"&&(Fe.value="")}else ke.tagName==="TEXTAREA"?ke.value="":ke.tagName==="SELECT"&&(ke.selectedIndex=0);ke.removeAttribute("data-vff-confirmed"),ke.style.outline="",ke.style.outlineOffset=""}),document.querySelectorAll(".vff-field-badge").forEach(fe=>fe.remove()),window.location.reload()};Z.useEffect(()=>{const ie=Ye.current;if(!ie)return;const fe=Je=>{if(!Je.target.closest(".vff-panel-header"))return;tt.current=!0;const Xt=ie.getBoundingClientRect();ft.current={x:Je.clientX-Xt.left,y:Je.clientY-Xt.top},Je.preventDefault()},ke=Je=>{if(!tt.current)return;const pi=Je.clientX-ft.current.x,Xt=Je.clientY-ft.current.y;ie.style.left=`${pi}px`,ie.style.top=`${Xt}px`,ie.style.right="auto"},Fe=()=>{tt.current=!1};return ie.addEventListener("mousedown",fe),document.addEventListener("mousemove",ke),document.addEventListener("mouseup",Fe),()=>{ie.removeEventListener("mousedown",fe),document.removeEventListener("mousemove",ke),document.removeEventListener("mouseup",Fe)}},[]);const Ut=L.toLowerCase()==="connected"||L.toLowerCase().startsWith("connected ")||L.toLowerCase()==="switching_section"||L.toLowerCase().startsWith("reconnecting"),wt=L.toLowerCase()==="paused";return L.toLowerCase().includes("warming"),L.toLowerCase(),E.fields.length,E.fields.filter(ie=>ie.required).length,Q.jsxs(Q.Fragment,{children:[qe&&Q.jsx(Xf,{intervalMs:3e3,onDismiss:()=>{console.log("[VoiceOverlay] 🌍 User dismissed greeting carousel"),Ne(!1),ze.current=!0}}),Q.jsxs("div",{ref:Ye,className:`vff-panel ${Ce?"collapsed":""}`,children:[Q.jsxs("div",{className:"vff-panel-header",children:[Q.jsx("span",{className:"vff-title",children:"🎤 Voice Form Filler"}),Q.jsxs("div",{style:{display:"flex",gap:"8px"},children:[Q.jsx("button",{className:"vff-collapse",onClick:()=>Ke(!Ce),"aria-label":Ce?"Expand":"Collapse",children:Ce?"▼":"▲"}),v&&Q.jsx("button",{className:"vff-close",onClick:v,"aria-label":"Close",children:"×"})]})]}),Q.jsxs("div",{className:"vff-panel-body",children:[Q.jsxs("div",{className:"vff-status",children:[Q.jsx("span",{className:"vff-status-icon",children:Ut?"🟢":"⚪"}),Q.jsx("span",{className:"vff-status-text",children:L}),ue.userSpeaking&&!G&&Q.jsxs("span",{className:"vff-vad-indicator",title:"Voice detected",children:[Q.jsx("span",{className:"vff-vad-light"}),Q.jsx("span",{className:"vff-vad-label",children:"Listening"})]})]}),Q.jsxs("div",{className:"vff-section-nav",children:[Q.jsxs("div",{className:"vff-section-display",onClick:()=>P(!U),children:[Q.jsxs("span",{className:"vff-section-label",children:["Section ",H," of ",f.total_sections,": ",f.sections[H-1]?.section_label]}),Q.jsx("span",{className:"vff-dropdown-arrow",children:U?"▲":"▼"})]}),Q.jsxs("div",{className:"vff-field-counter",children:["📊 ",D.filled," of ",D.total," fields completed"]}),U&&Q.jsx("div",{className:"vff-section-dropdown",children:f.sections.map(ie=>Q.jsxs("div",{className:`vff-section-item ${H===ie.section_number?"active":""}`,onClick:async()=>{if(C&&(P(!1),ie.section_number!==H))try{Y(null),j(ie.section_number),X("Reconnecting to section "+ie.section_number);const fe=ve.load();if(fe){const ke=ve.switchSection(fe,ie.section_number),Fe=ve.getSectionFieldCount(ke);F(Fe)}await C.switchSection(ie.section_number)}catch(fe){console.error("[VoiceOverlay] Section switch error:",fe),Y(fe instanceof Error?fe.message:"Section switch failed")}},children:[Q.jsx("span",{className:"vff-section-status",children:K.has(ie.section_number)?"✓":H===ie.section_number?"→":"○"}),Q.jsxs("span",{className:"vff-section-text",children:[ie.section_number,". ",ie.section_label]})]},ie.section_number))})]}),Q.jsxs("div",{className:"vff-controls",children:[!Ut&&!wt?Q.jsx("button",{className:"vff-button vff-connect",onClick:pe,children:"Connect to Voice"}):wt?Q.jsx("button",{className:"vff-button vff-resume",onClick:pe,children:"▶️ Resume"}):Q.jsx("button",{className:"vff-button vff-pause",onClick:ge,children:"⏸️ Pause"}),Q.jsx("button",{className:"vff-button vff-clear-form",onClick:Bt,children:"🗑️ Clear Form"})]}),we&&Q.jsx("div",{className:"vff-error",children:we})]}),Q.jsx("style",{children:`
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
			`})]})]})}function Jf({schema:E,sectionIndex:f,wsUrl:b,connectionManager:v,status:S}){const[y,C]=Z.useState(v||null),A=Z.useRef(v||null),[k,L]=Z.useState(S||"Ready"),[X,we]=Z.useState(null),[Y,J]=Z.useState(!1),[V,H]=Z.useState(!1),[j,K]=Z.useState(1),[R,D]=Z.useState(new Set),[F,U]=Z.useState({filled:0,total:12}),[P,G]=Z.useState(!1),[oe,Ae]=Z.useState(!1),me=Z.useRef(null),qe=Z.useRef(!1),Ne=450,Ce=Z.useRef(!1),Ke=Z.useRef(Date.now()),ze=Z.useRef(null),Ye=Z.useRef(0),tt=Z.useRef(!1),ft=6e3,rt=3,gt=Z.useMemo(()=>({onSpeechStart:()=>{if(P)return;if(Ce.current){console.log("[VFF VAD] 🔇 Speech detected during warmup - ignoring (calibrating...)");return}console.log("[VFF VAD] 🎤 User speech started - buffering audio..."),me.current=Date.now(),qe.current=!1;const pe=y?.getAudioManager();pe&&pe.setVADActive(!0),setTimeout(()=>{const ge=me.current?Date.now()-me.current:0;me.current!==null&&ge>=Ne&&(console.log(`[VFF VAD] ✅ Valid speech detected (${ge}ms) - triggering barge-in`),qe.current=!0,y?.onVADSpeechStart())},Ne)},onSpeechEnd:pe=>{if(P||Ce.current)return;const ge=me.current?Date.now()-me.current:0,Ze=y?.getAudioManager();Ze&&Ze.setVADActive(!1),qe.current?(console.log(`[VFF VAD] ✅ Valid turn detected (${ge}ms) - completing turn`),y?.onVADSpeechEnd(),st()):(console.log(`[VFF VAD] ⚠️ Turn too short (${ge}ms < ${Ne}ms) - no barge-in triggered, discarding`),ht()),me.current=null,qe.current=!1},onVADMisfire:()=>{console.log("[VFF VAD] ⚠️ VAD misfire detected"),me.current=null}}),[P,y]),Ee=mp({callbacks:gt});Z.useEffect(()=>{if(v){A.current=v,C(v);return}if(A.current)return;const pe=ve.initWithSections(E,f),ge=Xr(pe.schema,Ze=>{L(Ze),we(null)},"English");return A.current=ge,C(ge),()=>{it(),v||(A.current&&(A.current.disconnect(),A.current=null),C(null))}},[E,f,v]),Z.useEffect(()=>{S!==void 0&&L(S)},[S]),Z.useEffect(()=>{const pe=k.toLowerCase()==="connected"||k.toLowerCase().startsWith("connected ");pe&&!P&&!Ee.loading&&!Ee.errored?Ee.start():!pe&&!Ee.loading&&Ee.pause()},[k,P,Ee.loading,Ee.errored,Ee.start,Ee.pause]),Z.useEffect(()=>{let pe=null;return window.vffOnAudioPlaybackStart=()=>{console.log("[VFF Watchdog] 🔊 Gemini started speaking - pausing timer"),Ke.current=Date.now()},window.vffOnAudioPlaybackEnd=()=>{Ce.current&&(console.log("[VFF VAD] ✅ Warmup complete - VAD now active"),Ce.current=!1),pe&&clearTimeout(pe);const ge=tt.current?100:500;pe=setTimeout(()=>{tt.current?(console.log("[VFF Watchdog] 🚪 Farewell complete (100ms audio silence) - ending Gemini session"),tt.current=!1,it(),Ee.pause(),y&&y.endGeminiSession(),L("Ready"),console.log("[VFF Watchdog] ✅ Gemini session closed, ready to reconnect")):(console.log("[VFF Watchdog] 🔊 Gemini finished speaking - restarting timer"),ht()),pe=null},ge)},()=>{pe&&clearTimeout(pe),delete window.vffOnAudioPlaybackEnd,delete window.vffOnAudioPlaybackStart}},[]);const st=()=>{console.log("[VFF Watchdog] 🗣️ User turn complete - resetting escalation to 0"),Ye.current=0,Ke.current=Date.now()},vt=()=>{if(Ye.current>=rt){console.log(`[VFF Watchdog] ⏸️ Already at max escalation level ${rt} - waiting for farewell to complete`);return}Ye.current++,console.log(`[VFF Watchdog] ⏱️ Inactivity timeout - escalation level ${Ye.current}/${rt}`),Ke.current=Date.now(),Ye.current===1?ot():Ye.current===2?Me():Ye.current>=rt&&yt()},Tt=()=>{console.log("[VFF Watchdog] 🟢 Starting activity monitoring"),ze.current&&clearInterval(ze.current),Ye.current=0,Ke.current=Date.now(),ze.current=setInterval(()=>{Date.now()-Ke.current>=ft&&vt()},1e3)},it=()=>{ze.current&&(clearInterval(ze.current),ze.current=null),Ye.current=0},ht=()=>{Ke.current=Date.now()},ot=()=>{if(!y)return;console.log("[VFF Watchdog] 📝 Level 1: Field re-prompt");const pe=sessionStorage.getItem("vff_last_field_hint");if(pe)console.log("[VFF Watchdog] Re-prompting for last field:",pe),y.sendRecoveryPrompt(1,pe);else{const ge=sessionStorage.getItem("vff_state");if(!ge){y.sendRecoveryPrompt(1);return}const Ze=JSON.parse(ge),Dt=Kr(Ze);if(Dt){const Bt=Zr(Dt);y.sendRecoveryPrompt(1,Bt)}else y.sendRecoveryPrompt(1)}},Me=()=>{y&&(console.log("[VFF Watchdog] � Level 2: Are you still there?"),y.sendRecoveryPrompt(2))},yt=()=>{y&&(console.log("[VFF Watchdog] 🚪 Level 3: Closing session due to inactivity"),tt.current=!0,y.sendRecoveryPrompt(3),setTimeout(()=>{tt.current&&(console.log("[VFF Watchdog] ⏱️ Farewell timeout - forcing disconnect after 15s (audio silence detection failed)"),tt.current=!1,it(),Ee.pause(),y&&y.disconnect(),L("Ready"),console.log("[VFF Watchdog] ✅ Session closed (timeout fallback) and ready to reconnect"))},15e3))},lt=async()=>{if(y)try{if(we(null),y.isPaused()){await y.resume(),H(!0);return}await y.connect(),await new Promise(Ze=>setTimeout(Ze,100));const pe=y.getStatus();pe==="connected"||pe==="switching_section"?(await y.startRecording(),Ce.current=!0,console.log("[VFF VAD] 🔇 Warmup mode enabled - ignoring speech events until Gemini finishes greeting"),Tt(),!P&&!Ee.loading&&!Ee.errored?Ee.start():Ee.loading&&H(!0)):console.error("[VoiceOverlay] Connection status not active, status is:",pe)}catch(pe){console.error("[VoiceOverlay] Connection error:",pe),we(pe instanceof Error?pe.message:"Connection failed"),it()}},Et=()=>{y&&(it(),y.pause(),Ee.pause())};Z.useEffect(()=>{if(V&&!Ee.loading){if(Ee.errored){H(!1);return}Ee.start(),H(!1)}},[V,Ee.loading,Ee.errored,Ee.start]);const St=async()=>{const pe=!P;G(pe),y?.setPushToTalkMode(pe);const ge=k.toLowerCase()==="connected"||k.toLowerCase().startsWith("connected ")||k.toLowerCase()==="switching_section"||k.toLowerCase().startsWith("reconnecting");pe?(Ee.pause(),y?.getAudioManager()?.muteInput()):(ge&&!Ee.loading&&Ee.start(),y?.getAudioManager()?.unmuteInput())},Be=async()=>{if(!P||!(k.toLowerCase()==="connected"||k.toLowerCase().startsWith("connected ")||k.toLowerCase()==="switching_section"||k.toLowerCase().startsWith("reconnecting")))return;Ae(!0);const ge=y?.getAudioManager();ge?.unmuteInput(),ge?.isSpeaking()&&ge.flushAudioQueue(),y?.sendActivityStart()},ue=()=>{if(!P||!(k.toLowerCase()==="connected"||k.toLowerCase().startsWith("connected ")||k.toLowerCase()==="switching_section"||k.toLowerCase().startsWith("reconnecting")))return;Ae(!1),y?.getAudioManager()?.muteInput(),y?.sendActivityEnd()};Z.useEffect(()=>{const pe=ve.initWithSections(E,f);K(pe.current_section||1),D(pe.completed_sections||new Set);const ge=ve.getSectionFieldCount(pe);U(ge)},[E,f]),Z.useEffect(()=>{const pe=setInterval(()=>{const ge=ve.load();if(ge){const Ze=ve.getSectionFieldCount(ge);U(Ze)}},1e3);return()=>clearInterval(pe)},[]);const Pe=k.toLowerCase()==="connected"||k.toLowerCase().startsWith("connected "),Ue=k.toLowerCase()==="paused",je=k.toLowerCase().includes("warming"),mt=k.toLowerCase()==="ready",Ft=E.fields.length,Ct=E.fields.filter(pe=>pe.required).length,ut=Pe?"#10b981":Ue||je?"#f59e0b":mt?"#3b82f6":"#6b7280";return Q.jsxs(Q.Fragment,{children:[Q.jsxs("div",{className:"vff-fab",onClick:()=>J(!Y),children:[Q.jsx("div",{className:"vff-fab-pulse",style:{borderColor:ut}}),Ee.userSpeaking&&!P&&Q.jsx("div",{className:"vff-fab-vad-badge",children:Q.jsx("div",{className:"vff-fab-vad-dot"})}),Q.jsx("div",{className:"vff-fab-icon",style:{background:ut},children:"🎤"})]}),Y&&Q.jsxs("div",{className:"vff-panel-mobile",children:[Q.jsxs("div",{className:"vff-panel-header",children:[Q.jsx("span",{className:"vff-title",children:"Voice Form Filler"}),Q.jsx("button",{className:"vff-close",onClick:()=>J(!1),children:"×"})]}),Q.jsxs("div",{className:"vff-panel-body",children:[Q.jsxs("div",{className:"vff-status-compact",children:[Q.jsx("div",{className:"vff-status-dot",style:{background:ut}}),Q.jsx("span",{className:"vff-status-text",children:k})]}),(Pe||Ue)&&Q.jsx("div",{className:"vff-ptt-toggle-mobile",children:Q.jsxs("div",{className:"vff-toggle-label-row",children:[Q.jsx("span",{className:"vff-toggle-mode-label",children:"🎤 Auto"}),Q.jsxs("label",{className:"vff-toggle-switch",children:[Q.jsx("input",{type:"checkbox",checked:P,onChange:St,onKeyDown:pe=>{pe.code==="Space"&&pe.preventDefault()}}),Q.jsx("span",{className:"vff-toggle-slider"})]}),Q.jsx("span",{className:"vff-toggle-mode-label",children:"⌨️ PTT"})]})}),"						",P&&Pe&&Q.jsx("button",{className:`vff-action-btn vff-ptt-btn ${oe?"active":""}`,onTouchStart:Be,onTouchEnd:ue,onMouseDown:Be,onMouseUp:ue,onMouseLeave:ue,children:oe?"🔴 Speaking...":"⚫ Hold to Speak"}),!Pe&&!Ue?Q.jsx("button",{className:"vff-action-btn vff-connect-btn",onClick:lt,children:"🎙️ Connect"}):Ue?Q.jsx("button",{className:"vff-action-btn vff-resume-btn",onClick:lt,children:"▶️ Resume"}):Q.jsx("button",{className:"vff-action-btn vff-pause-btn",onClick:Et,children:"⏸️ Pause"}),X&&Q.jsx("div",{className:"vff-error-compact",children:X}),Q.jsxs("div",{className:"vff-info-compact",children:[Ft," fields · ",Ct," required"]})]})]}),Q.jsx("style",{children:`
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
			`})]})}function eh(){const E=Z.useRef(null),[f,b]=Z.useState(null),[v,S]=Z.useState(null),[y,C]=Z.useState(!1),[A,k]=Z.useState(!1),[L,X]=Z.useState(!1),[we,Y]=Z.useState(null),J=Z.useRef(null),[V,H]=Z.useState("Ready");Z.useEffect(()=>{const K=()=>{k(window.innerWidth<=768)};return K(),window.addEventListener("resize",K),()=>window.removeEventListener("resize",K)},[]),Z.useEffect(()=>{const K=R=>{if(L)return;const D=document.querySelectorAll("input, textarea, select");let F=!1;for(const U of D){const P=U;if(P.tagName==="INPUT"){const G=P;G.type==="checkbox"||G.type==="radio"?G.checked&&(F=!0):G.type!=="submit"&&G.type!=="button"&&G.type!=="hidden"&&G.value.trim()&&(F=!0)}else P.tagName==="TEXTAREA"?P.value.trim()&&(F=!0):P.tagName==="SELECT"&&P.selectedIndex>0&&(F=!0);if(F)break}F&&(R.preventDefault(),R.returnValue="")};return window.addEventListener("beforeunload",K),()=>window.removeEventListener("beforeunload",K)},[y,L]),Z.useEffect(()=>{(async()=>{try{const D=await(await fetch("./adult_intake_demo.html")).text(),U=new DOMParser().parseFromString(D,"text/html"),P=U.querySelector("style")?.textContent||"",G=U.querySelector(".clinic-header")?.outerHTML||"",oe=U.querySelector(".form-container")?.outerHTML||"";if(E.current){const Ce=document.createElement("style");Ce.textContent=P,document.head.appendChild(Ce),E.current.innerHTML=G+oe,C(!0)}const me=await(await fetch("./adult_intake_demo_schema.json")).json();me.form_metadata.url=window.location.href;const Ne=await(await fetch("./adult_intake_sections_index.json")).json();b(me),S(Ne),setTimeout(()=>{const Ce=document.querySelector("form");Ce&&(Ce.addEventListener("submit",Ke=>(Ke.preventDefault(),X(!0),window.location.href="thank-you.html",!1)),Ce.addEventListener("keydown",Ke=>{if(Ke.key==="Enter"){const ze=Ke.target;(ze.tagName==="INPUT"||ze.tagName==="TEXTAREA")&&(Ke.preventDefault(),ze.blur())}}))},100)}catch(R){console.error("Failed to load form, schema, or section index:",R)}})()},[]),Z.useEffect(()=>{if(!f||!v||J.current)return;const K=ve.initWithSections(f,v),R=Xr(K.schema,D=>{H(D)},"English");return J.current=R,Y(R),()=>{J.current&&(J.current.disconnect(),J.current=null),Y(null)}},[f,v]);const j="wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill";return Q.jsxs("div",{className:"demo-container",children:[Q.jsx("div",{ref:E,className:"form-content"}),y&&f&&v&&we&&(A?Q.jsx(Jf,{schema:f,sectionIndex:v,wsUrl:j,connectionManager:we,status:V}):Q.jsx(Yf,{schema:f,sectionIndex:v,wsUrl:j,connectionManager:we,status:V}))]})}jr.createRoot(document.getElementById("root")).render(Q.jsx(eh,{}));
