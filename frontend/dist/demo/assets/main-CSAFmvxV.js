var yf=Object.defineProperty;var wf=(S,f,w)=>f in S?yf(S,f,{enumerable:!0,configurable:!0,writable:!0,value:w}):S[f]=w;var Ge=(S,f,w)=>wf(S,typeof f!="symbol"?f+"":f,w);import{r as Y,a as bf,c as Ze}from"./vendor-react-CfsYHMYl.js";(function(){const f=document.createElement("link").relList;if(f&&f.supports&&f.supports("modulepreload"))return;for(const k of document.querySelectorAll('link[rel="modulepreload"]'))v(k);new MutationObserver(k=>{for(const b of k)if(b.type==="childList")for(const I of b.addedNodes)I.tagName==="LINK"&&I.rel==="modulepreload"&&v(I)}).observe(document,{childList:!0,subtree:!0});function w(k){const b={};return k.integrity&&(b.integrity=k.integrity),k.referrerPolicy&&(b.referrerPolicy=k.referrerPolicy),k.crossOrigin==="use-credentials"?b.credentials="include":k.crossOrigin==="anonymous"?b.credentials="omit":b.credentials="same-origin",b}function v(k){if(k.ep)return;k.ep=!0;const b=w(k);fetch(k.href,b)}})();var Yc={exports:{}},nn={};/**
 * @license React
 * react-jsx-runtime.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var vf=Y,$f=Symbol.for("react.element"),xf=Symbol.for("react.fragment"),Sf=Object.prototype.hasOwnProperty,kf=vf.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,Tf={key:!0,ref:!0,__self:!0,__source:!0};function Jc(S,f,w){var v,k={},b=null,I=null;w!==void 0&&(b=""+w),f.key!==void 0&&(b=""+f.key),f.ref!==void 0&&(I=f.ref);for(v in f)Sf.call(f,v)&&!Tf.hasOwnProperty(v)&&(k[v]=f[v]);if(S&&S.defaultProps)for(v in f=S.defaultProps,f)k[v]===void 0&&(k[v]=f[v]);return{$$typeof:$f,type:S,key:b,ref:I,props:k,_owner:kf.current}}nn.Fragment=xf;nn.jsx=Jc;nn.jsxs=Jc;Yc.exports=nn;var Q=Yc.exports,Ur={},Uc=bf;Ur.createRoot=Uc.createRoot,Ur.hydrateRoot=Uc.hydrateRoot;class ve{static init(f){const w=this.load();if(w&&w.schema.form_metadata.url===f.form_metadata.url&&Date.now()-w.last_updated<60*60*1e3)return w;const v={schema:f,current_values:{},last_updated:Date.now()};return this.save(v),v}static load(){try{const f=sessionStorage.getItem(this.STORAGE_KEY);if(!f)return null;const w=JSON.parse(f);return w.completed_sections&&Array.isArray(w.completed_sections)&&(w.completed_sections=new Set(w.completed_sections)),w}catch{return null}}static save(f){try{f.last_updated=Date.now();const w={...f,completed_sections:f.completed_sections?Array.from(f.completed_sections):void 0};sessionStorage.setItem(this.STORAGE_KEY,JSON.stringify(w))}catch{}}static updateFieldValue(f,w,v,k){const b=f.current_values[w]||{value:null,confirmed:!1},I=k?.confirmed!==void 0?k.confirmed:typeof b.confirmed=="boolean"?b.confirmed:!1,A={...f,current_values:{...f.current_values,[w]:{...b,value:v,confirmed:I,lastModified:Date.now()}}};return this.save(A),A}static markConfirmed(f,w){const v={...f,current_values:{...f.current_values}};for(const k of w)v.current_values[k]&&(v.current_values[k]={...v.current_values[k],confirmed:!0});return this.save(v),v}static getHandshakePayload(f,w="English"){const v={type:"handshake",schema:f.schema,current_values:f.current_values,fill_language:w};if(f.section_index){v.section_number=f.current_section,v.total_sections=f.section_index.total_sections;const k=f.section_index.sections.find(I=>I.section_number===f.current_section);k&&(v.section_label=k.section_label);const b=this.getSpokenNameMap(f);v.previous_spoken_names=Array.from(b.keys())}return v}static setSessionId(f,w){const v={...f,session_id:w};return this.save(v),v}static clear(){sessionStorage.removeItem(this.STORAGE_KEY)}static getUnconfirmedFields(f){return f.schema.fields.filter(w=>{const v=f.current_values[w.id];return!v||!v.confirmed}).map(w=>w.id)}static getCompletionPercentage(f){const w=f.schema.fields.length;if(w===0)return 100;const v=f.schema.fields.filter(k=>{const b=f.current_values[k.id];return b&&b.value!==null&&b.value!==""}).length;return Math.round(v/w*100)}static debug(f){}static initWithSections(f,w){const v=this.load();if(v&&v.full_schema&&v.section_index&&v.full_schema.form_metadata.url===f.form_metadata.url&&Date.now()-v.last_updated<60*60*1e3)return v;const b={schema:this.getSectionSchema(f,w,1),current_values:{},last_updated:Date.now(),current_section:1,completed_sections:new Set,section_index:w,full_schema:f};return this.save(b),b}static getSectionSchema(f,w,v){const k=w.sections.find(I=>I.section_number===v);if(!k)throw new Error(`Section ${v} not found in index`);const b=k.field_indices.map(I=>f.fields[I]);return{...f,fields:b}}static switchSection(f,w){if(!f.section_index||!f.full_schema)throw new Error("Cannot switch sections: section_index or full_schema not initialized");if(w<1||w>f.section_index.total_sections)throw new Error(`Invalid section number: ${w}`);const v=this.getSectionSchema(f.full_schema,f.section_index,w),k={...f,schema:v,current_section:w};return this.save(k),k}static completeSection(f,w){const v=f.completed_sections||new Set,k={...f,completed_sections:new Set([...v,w])};return this.save(k),k}static getSpokenNameMap(f){const w=new Map;if(!f.full_schema||!f.section_index||!f.completed_sections)return w;const v=new Set([...f.completed_sections,f.current_section||1]);for(const k of v){const b=f.section_index.sections.find(I=>I.section_number===k);if(b)for(const I of b.field_indices){const A=f.full_schema.fields[I];if(!A)continue;A.spoken_name&&w.set(A.spoken_name.toLowerCase(),A.id);const E=A.spoken_aliases;if(Array.isArray(E))for(const X of E)w.set(X.toLowerCase(),A.id)}}return w}static getSectionLabel(f,w){return f.section_index&&f.section_index.sections.find(k=>k.section_number===w)?.section_label||null}static findSectionByLabel(f,w){if(!f.section_index)return null;const v=w.toLowerCase().trim();return f.section_index.sections.find(b=>b.section_label.toLowerCase()===v)?.section_number||null}static getSectionFieldCount(f){if(!f.section_index||!f.current_section)return{filled:0,total:f.schema.fields.length};const w=f.section_index.sections.find(k=>k.section_number===f.current_section);return w?{filled:f.schema.fields.filter(k=>{const b=f.current_values[k.id];return b&&b.value!==null&&b.value!==""}).length,total:w.field_count}:{filled:0,total:f.schema.fields.length}}}Ge(ve,"STORAGE_KEY","web_form_state"),Ge(ve,"SECTION_KEY","vff_current_section"),Ge(ve,"COMPLETED_SECTIONS_KEY","vff_completed_sections"),Ge(ve,"SPOKEN_NAME_MAP_KEY","vff_spoken_name_map");function Ef(S,f){const{requiredOnly:w=!1,skipConfirmed:v=!0}=f||{};if(!S.schema||!S.schema.fields||S.schema.fields.length===0)return null;for(const k of S.schema.fields){if(w&&!k.required)continue;const b=S.current_values[k.id],I=b?.confirmed===!0;if(!(v&&I||b?.value!==null&&b?.value!==void 0&&b?.value!==""))return k}return null}function Cf(S){if(!S.schema||!S.schema.fields||S.schema.fields.length===0)return!0;if(S.schema.fields.some(w=>w.required)){for(const w of S.schema.fields)if(w.required&&!(S.current_values[w.id]?.confirmed===!0))return!1;return!0}else{for(const w of S.schema.fields)if(!(S.current_values[w.id]?.confirmed===!0))return!1;return!0}}function If(S,f){const w=f?`#${f}`:"",v=S.required?", required":"",k=S.options&&S.options.length>0?`, options: [${S.options.join(", ")}]`:"";return`Next field to fill is ${w}: '${S.name}' (type: ${S.type}${v}${k})`}function Af(S,f){if(!S.schema||!S.schema.fields)return null;const w=S.schema.fields.findIndex(v=>v.id===f);return w>=0?w+1:null}class qc{constructor(f,w={},v="English"){Ge(this,"ws",null);Ge(this,"state");Ge(this,"callbacks");Ge(this,"status","disconnected");Ge(this,"reconnectAttempts",0);Ge(this,"maxReconnectAttempts",5);Ge(this,"reconnectDelay",1e3);Ge(this,"reconnectTimer",null);Ge(this,"audioQueue",[]);Ge(this,"audioChunkCount",0);Ge(this,"isProcessingAudio",!1);Ge(this,"enableAutoReconnect",!1);Ge(this,"isSectionSwitching",!1);Ge(this,"connectedUrl","");Ge(this,"fillLanguage","English");this.state=ve.init(f),this.callbacks=w,this.fillLanguage=v}async connect(f="ws://localhost:8000/ws/fill",w=1e4){if(!(this.ws&&this.ws.readyState===WebSocket.OPEN))return this.connectedUrl=f,this.isSectionSwitching||this.setStatus("connecting"),new Promise((v,k)=>{const b=setTimeout(()=>{this.ws&&(this.ws.close(),this.ws=null),k(new Error(`Connection timeout after ${w}ms`))},w);try{this.ws=new WebSocket(f),this.ws.onopen=()=>{clearTimeout(b),this.handleOpen(),v()},this.ws.onmessage=I=>this.handleMessage(I),this.ws.onerror=I=>{clearTimeout(b),this.handleError(I),k(I)},this.ws.onclose=()=>{clearTimeout(b),this.handleClose()}}catch(I){clearTimeout(b),this.handleError(I),k(I)}})}disconnect(){this.reconnectTimer&&(clearTimeout(this.reconnectTimer),this.reconnectTimer=null),this.ws&&(this.ws.close(),this.ws=null),this.isSectionSwitching||this.setStatus("disconnected")}handleOpen(){if(this.reconnectAttempts=0,this.reconnectDelay=1e3,this.enableAutoReconnect=!0,this.isSectionSwitching)return;const f=ve.getHandshakePayload(this.state,this.fillLanguage);this.send(f)}async handleMessage(f){if(f.data instanceof ArrayBuffer||f.data instanceof Blob){await this.handleAudioFrame(f.data);return}try{const w=JSON.parse(f.data);switch(w.type){case"session_ready":this.handleSessionReady(w);break;case"field_update":this.handleFieldUpdate(w);break;case"form_updated":this.handleFormUpdated(w);break;case"form_state_ack":break;case"hint_ack":break;case"get_form_state":this.handleGetFormStateRequest(w);break;case"get_next_field_hint":this.handleGetNextFieldHintRequest(w);break;case"prepare_section_switch":this.handlePrepareSectionSwitchRequest(w);break;case"section_switched":this.handleSectionSwitched(w);break;case"switch_section":this.handleSwitchSectionRequest(w);break;case"get_field_value":this.handleGetFieldValueRequest(w);break;case"complete_section":this.handleCompleteSectionRequest(w);break;case"error":this.handleServerError(w);break;case"ai_response":break;case"turn_complete":window.vffOnTurnComplete&&window.vffOnTurnComplete();break;case"gemini_session_restarted":console.log("[WebFormConnection] ✅ Gemini session restarted successfully"),this.callbacks.onSessionRestarted&&this.callbacks.onSessionRestarted();break;default:break}}catch{}}handleSessionReady(f){const{session_id:w,ephemeral:v}=f;this.state=ve.setSessionId(this.state,w),this.setStatus("connected"),this.callbacks.onSessionReady&&this.callbacks.onSessionReady(w)}handleFieldUpdate(f){const{updates:w}=f;if(!w||typeof w!="object")return;const v=[];for(const[k,b]of Object.entries(w)){const I=this.state.schema.fields.find(A=>A.name===k||A.id===k);I&&(this.updateField(I.id,b,{confirmed:!0,emit:!1}),v.push({fieldId:I.id,value:b}))}this.callbacks.onFieldUpdate&&v.length>0&&this.callbacks.onFieldUpdate(v)}handleFormUpdated(f){const w=f&&f.data||{},v=w.form_state||{},k=w.applied_fields||[],b=w.request_next_field_hint||!1,I=w.request_id;if(!v||typeof v!="object")return;const A=new Set(k.map(j=>String(j))),E=A.size>0,X=[];for(const j of this.state.schema.fields){const ee=v[j.id]??v[j.name??""];if(ee===void 0)continue;const ie=A.has(j.id)||(j.name?A.has(j.name):!1);if(E&&!ie)continue;const J=this.state.current_values[j.id]?.value;(ie||!Object.is(J,ee))&&(this.updateField(j.id,ee,{confirmed:ie,emit:!1}),X.push({fieldId:j.id,value:ee}))}for(const[j,ee]of Object.entries(v)){if(this.state.schema.fields.some(N=>N.id===j||N.name===j))continue;const ie=j+"[]",J=this.state.schema.fields.find(N=>N.id===ie||N.name===ie);if(J){const N=A.has(j)||A.has(ie);if(E&&!N)continue;const Z=this.state.current_values[J.id]?.value;if(!(N||!Object.is(Z,ee)))continue;this.updateField(J.id,ee,{confirmed:N,emit:!1}),X.push({fieldId:J.id,value:ee})}}if(X.length&&this.callbacks.onFieldUpdate&&this.callbacks.onFieldUpdate(X),b&&I){const j=this.computeNextFieldHintString();j&&sessionStorage.setItem("vff_last_field_hint",j),this.send({type:"next_field_hint_response",request_id:I,hint:j})}}handleGetFormStateRequest(f){const w=f.request_id,v=f.field_ids||[],k={};if(v.length===0)for(const[b,I]of Object.entries(this.state.current_values))k[b]={value:I.value,confirmed:I.confirmed};else for(const b of v){let I=this.state.current_values[b];!I&&!b.endsWith("[]")&&(I=this.state.current_values[b+"[]"]),!I&&b.endsWith("[]")&&(I=this.state.current_values[b.slice(0,-2)]),I?k[b]={value:I.value,confirmed:I.confirmed}:k[b]={value:null,confirmed:!1}}this.send({type:"form_state_response",request_id:w,field_values:k})}handleGetNextFieldHintRequest(f){const w=f.request_id,v=this.computeNextFieldHintString();v&&sessionStorage.setItem("vff_last_field_hint",v),this.send({type:"next_field_hint_response",request_id:w,hint:v})}computeNextFieldHintString(){if(Cf(this.state))return null;const f=Ef(this.state,{skipConfirmed:!0});if(!f)return null;const w=Af(this.state,f.id);return If(f,w||void 0)}getNextFieldHint(){return this.computeNextFieldHintString()}async handleSwitchSectionRequest(f){const w=f.identifier;try{let v;if(typeof w=="number")v=w;else if(typeof w=="string"){const k=parseInt(w,10);if(!isNaN(k))v=k;else{const b=ve.load();if(b?.section_index){const I=w.toLowerCase(),A=b.section_index.sections.find(E=>E.section_label.toLowerCase()===I||E.section_id.toLowerCase()===I);A&&(v=A.section_number)}}}if(!v)return;await this.switchSection(v,this.connectedUrl)}catch{}}handlePrepareSectionSwitchRequest(f){const w=f.request_id,v=f.identifier;console.log("[WebFormConnection] handlePrepareSectionSwitchRequest START",{requestId:w,identifier:v});try{const k=ve.load();if(console.log("[WebFormConnection] Loaded state",{hasState:!!k,hasSectionIndex:!!k?.section_index}),!k||!k.section_index){console.log("[WebFormConnection] No state/section_index, sending null response"),this.send({type:"section_info_response",request_id:w,section_info:null});return}let b;if(typeof v=="number")b=v;else if(typeof v=="string"){const J=parseInt(v,10);if(!isNaN(J))b=J;else{const N=v.toLowerCase(),Z=k.section_index.sections.find(H=>H.section_label.toLowerCase()===N||H.section_id.toLowerCase()===N);Z&&(b=Z.section_number)}}if(console.log("[WebFormConnection] Parsed target number:",b),!b){console.log("[WebFormConnection] Invalid target number, sending null response"),this.send({type:"section_info_response",request_id:w,section_info:null});return}console.log("[WebFormConnection] Switching to section",b);const I=ve.switchSection(k,b);this.state=I,console.log("[WebFormConnection] Building section schema and values");const A=I.schema,E=new Set(A.fields.map(J=>J.id)),X={};for(const[J,N]of Object.entries(I.current_values))E.has(J)&&(X[J]=N);console.log("[WebFormConnection] Building previous spoken names");const j=ve.getSpokenNameMap(I),ee=Array.from(j.keys());console.log("[WebFormConnection] Computing initial field hint");const ie=this.computeNextFieldHintString();ie&&sessionStorage.setItem("vff_last_field_hint",ie),console.log("[WebFormConnection] Sending section_info_response",{requestId:w,sectionNumber:b,fieldCount:A.fields.length,valueCount:Object.keys(X).length}),this.send({type:"section_info_response",request_id:w,section_info:{schema:A,current_values:X,metadata:{section_number:b,total_sections:I.section_index.total_sections,section_label:ve.getSectionLabel(I,b)||"",previous_spoken_names:ee},initial_field_hint:ie}}),console.log("[WebFormConnection] handlePrepareSectionSwitchRequest COMPLETE")}catch(k){console.error("[WebFormConnection] Error preparing section switch:",k),this.send({type:"section_info_response",request_id:w,section_info:null})}}handleSectionSwitched(f){const w=f.section_number;console.log(`[WebFormConnection] Section switched confirmed: ${w}`),this.setStatus("connected")}handleGetFieldValueRequest(f){const w=f.request_id,v=f.spoken_name;try{const k=ve.load();if(!k){this.sendFieldValueResponse(w,null,!1);return}const I=ve.getSpokenNameMap(k).get(v.toLowerCase());if(!I){this.sendFieldValueResponse(w,null,!1);return}const A=k.current_values[I];A!=null&&String(A).trim()!==""?this.sendFieldValueResponse(w,A,!0):this.sendFieldValueResponse(w,null,!1)}catch{this.sendFieldValueResponse(w,null,!1)}}sendFieldValueResponse(f,w,v){this.send({type:"field_value_response",request_id:f,value:w,found:v})}async handleCompleteSectionRequest(f){try{const w=ve.load();if(!w||!w.current_section)throw new Error("Section state not initialized");const v=w.current_section,k=ve.completeSection(w,v);if(this.state=k,v>=k.section_index.total_sections){this.send({type:"section_completed",next_section:v,form_complete:!0});return}const b=v+1;await this.switchSection(b,this.connectedUrl),this.send({type:"section_completed",next_section:b,form_complete:!1})}catch(w){console.error("[WebFormConnection] Error completing section:",w),this.send({type:"section_completed",success:!1,error:w instanceof Error?w.message:String(w)})}}sendCompletionMessage(){this.send({type:"completion_message",message:"Say the following: 'The form is complete. if all fields are correct, please press submit.'"})}async handleAudioFrame(f){const w=f instanceof Blob?await f.arrayBuffer():f;this.audioChunkCount||(this.audioChunkCount=0),this.audioChunkCount++,this.audioChunkCount===1?console.log(`[WebFormConnection] 📥 First audio chunk received from server (${w.byteLength} bytes)`):this.audioChunkCount%10===0&&console.log(`[WebFormConnection] 📥 Audio chunk #${this.audioChunkCount} (${w.byteLength} bytes)`),this.audioQueue.push(w),this.isProcessingAudio||this.processAudioQueue()}async processAudioQueue(){for(this.isProcessingAudio=!0;this.audioQueue.length>0;){const f=this.audioQueue.shift();this.callbacks.onAudioData&&this.callbacks.onAudioData(f)}this.isProcessingAudio=!1}handleServerError(f){console.error("[WebFormConnection] Server error received:",{code:f.code,reason:f.reason,message:f.message,fullMessage:f});const w=f.message||f.reason||f.code||"Server error",v=new Error(w);this.callbacks.onError&&this.callbacks.onError(v)}handleError(f){this.isSectionSwitching||this.setStatus("error"),this.callbacks.onError&&f instanceof Error&&this.callbacks.onError(f)}handleClose(){if(!this.enableAutoReconnect){this.setStatus("disconnected");return}this.isSectionSwitching||(this.status!=="disconnected"&&this.reconnectAttempts<this.maxReconnectAttempts?this.attemptReconnect():this.setStatus("disconnected"))}attemptReconnect(){this.reconnectAttempts++,this.setStatus("reconnecting");const f=Math.min(this.reconnectDelay*Math.pow(2,this.reconnectAttempts-1),3e4);this.reconnectTimer=window.setTimeout(()=>{this.connect()},f)}async waitForBufferDrain(f=1e3){if(!this.ws)return;const w=Date.now();for(;this.ws.bufferedAmount>0;){if(Date.now()-w>f){console.warn("[WebFormConnection] Buffer drain timeout",{bufferedAmount:this.ws.bufferedAmount,waitedMs:Date.now()-w});break}await new Promise(v=>setTimeout(v,10))}this.ws.bufferedAmount===0&&console.log("[WebFormConnection] Buffer drained successfully",{waitedMs:Date.now()-w})}send(f){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.error("[WebFormConnection] send() called but WebSocket not open!",{hasWs:!!this.ws,readyState:this.ws?.readyState,message:f});return}if(f instanceof ArrayBuffer)this.ws.send(f);else{const w=JSON.stringify(f);console.log("[WebFormConnection] Sending JSON message",{type:f.type,size:w.length,readyState:this.ws.readyState,bufferedAmount:this.ws.bufferedAmount}),this.ws.send(w)}}sendAudio(f){this.send(f)}sendManualFieldUpdate(f,w,v){!this.ws||this.ws.readyState!==WebSocket.OPEN||this.send({type:"manual_field_update",field_id:f,field_name:w,value:v})}sendActivityStart(){!this.ws||this.ws.readyState!==WebSocket.OPEN||this.send({type:"vad_activity_start",timestamp:Date.now()})}sendActivityEnd(){!this.ws||this.ws.readyState!==WebSocket.OPEN||this.send({type:"vad_activity_end",timestamp:Date.now()})}sendPrompt(f){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.warn("[WebFormConnection] Cannot send prompt - not connected");return}console.log("[WebFormConnection] Sending prompt to Gemini:",f),this.send({type:"completion_message",message:f})}sendRecoveryPrompt(f,w){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.warn("[WebFormConnection] Cannot send recovery prompt - not connected");return}console.log(`[WebFormConnection] Sending recovery prompt level ${f}`,w?`with hint: ${w}`:""),this.send({type:"recovery_prompt",level:f,next_field_hint:w})}endGeminiSession(){if(!this.ws||this.ws.readyState!==WebSocket.OPEN){console.warn("[WebFormConnection] Cannot end Gemini session - not connected");return}console.log("[WebFormConnection] 🚪 Ending Gemini session (keeping WebSocket alive)"),this.send({type:"end_gemini_session"})}async changeFillLanguage(f){!this.ws||this.ws.readyState!==WebSocket.OPEN||(this.fillLanguage=f,this.send({type:"change_fill_language",language:f}))}updateField(f,w,v){const k=v?.confirmed,b=v?.emit??!1;this.state=ve.updateFieldValue(this.state,f,w,{confirmed:k}),b&&this.flushField(f)}flushField(f){if(!this.ws||this.ws.readyState!==WebSocket.OPEN)return;const w=this.state.current_values[f];w&&this.send({type:"form_state",fields:[{field_id:f,value:w.value,confirmed:!!w.confirmed}]})}setStatus(f){this.status!==f&&(this.status=f,this.callbacks.onStatusChange&&this.callbacks.onStatusChange(f))}getStatus(){return this.status}getState(){return this.state}getCompletionPercentage(){return ve.getCompletionPercentage(this.state)}reset(){this.disconnect(),ve.clear()}async startSection(f,w="ws://localhost:8000/ws/fill"){try{this.isSectionSwitching=!0,this.setStatus("switching_section"),this.ws&&this.ws.readyState===WebSocket.OPEN&&(this.disconnect(),await new Promise(j=>setTimeout(j,100)));let v=ve.load();if(!v||!v.section_index||!v.full_schema)throw new Error("Section index or full schema not initialized");v=ve.switchSection(v,f),this.state=v;const k=v.schema,b={},I=new Set(k.fields.map(j=>j.id));for(const[j,ee]of Object.entries(v.current_values))I.has(j)&&(b[j]=ee);const A=ve.getSpokenNameMap(v),E=Array.from(A.keys());await this.connect(w),this.isSectionSwitching=!1;const X=this.computeNextFieldHintString();this.send({type:"handshake",schema:k,current_values:b,fill_language:this.fillLanguage,section_number:f,total_sections:v.section_index.total_sections,section_label:ve.getSectionLabel(v,f)||"",previous_spoken_names:E,initial_field_hint:X})}catch(v){throw this.isSectionSwitching=!1,v}}async switchSection(f,w){const v=ve.load();if(!v||!v.section_index)throw new Error("Section index not initialized");let k;if(typeof f=="number")k=f;else{const ie=ve.findSectionByLabel(v,f);if(!ie)throw new Error(`Section not found: ${f}`);k=ie}if(k<1||k>v.section_index.total_sections)throw new Error(`Invalid section number: ${k} (must be 1-${v.section_index.total_sections})`);console.log("[WebFormConnection] Waiting for buffer to drain before section switch"),await this.waitForBufferDrain(1e3),this.setStatus("switching_section");const b=ve.switchSection(v,k);this.state=b;const I=b.schema,A=new Set(I.fields.map(ie=>ie.id)),E={};for(const[ie,J]of Object.entries(b.current_values))A.has(ie)&&(E[ie]=J);const X=ve.getSpokenNameMap(b),j=Array.from(X.keys()),ee=this.computeNextFieldHintString();console.log("[WebFormConnection] Sending section switch with embedded info",{sectionNumber:k,fieldCount:I.fields.length,valueCount:Object.keys(E).length}),this.send({type:"manual_section_switch",identifier:k.toString(),section_info:{schema:I,current_values:E,metadata:{section_number:k,total_sections:b.section_index.total_sections,section_label:ve.getSectionLabel(b,k)||"",previous_spoken_names:j},initial_field_hint:ee}})}async completeSection(f){if(!f)throw new Error("wsUrl is required for completeSection - must pass the connected backend URL");const w=ve.load();if(!w||!w.current_section||!w.section_index)throw new Error("Section state not initialized");const v=w.current_section,k=ve.completeSection(w,v);if(this.state=k,v>=k.section_index.total_sections){this.setStatus("connected");return}const b=v+1;await this.startSection(b,f)}getCurrentSection(){return this.state.current_section}getCompletedSections(){return this.state.completed_sections||new Set}}function Wc(S={}){const f=new Set,w=new Map,v=new Map,k=new Set;function b(M,B){if(w.has(M))return;const D=()=>{if(k.has(B))return;const q=Date.now(),V=v.get(B)||0;if(!(q-V<100)&&(v.set(B,q),f.has(B)&&A(M,B),S.onManualEdit)){const W=M.value;W&&W.trim()&&S.onManualEdit(B,W)}};M.addEventListener("blur",D),M.addEventListener("change",D),w.set(M,D)}function I(M){console.log("[VFF FieldManager] Setting up listeners on",M.length,"schema fields");for(const B of M){const D=B.id;if(!D)continue;let q=document.getElementById(D);if(!q){const V=document.querySelectorAll(`input[name="${D}"], textarea[name="${D}"], select[name="${D}"]`);if(V.length>0){V.forEach(W=>{b(W,D)});continue}}q&&b(q,D)}}function A(M,B){M.style.outline="",M.style.outlineOffset="";const D=M.parentElement?.querySelector(".vff-field-badge");D&&D.remove(),M.removeAttribute("data-vff-confirmed"),f.delete(B),console.log("[VFF FieldManager] Cleared AI confirmation for:",B)}S.schema?.fields&&I(S.schema.fields);function E(M){console.log("[VFF FieldManager] 📝 Applying",M.length,"field update(s)");const B={success:[],notFound:[],errors:[]};for(const D of M){k.add(D.fieldId);const q=D.value||"";let V=document.getElementById(D.fieldId);if(!V){const we=document.querySelectorAll(`input[name="${D.fieldId}"], textarea[name="${D.fieldId}"], select[name="${D.fieldId}"]`);if(we.length>0){const ce=we[0];if(we.length>1){if(ce.type==="radio"){J(we,q,D.fieldId),B.success.push(D.fieldId);continue}else if(ce.type==="checkbox"){ee(we,q,D.fieldId),B.success.push(D.fieldId);continue}}V=ce}if(!V){const ce=document.querySelector(`[role="combobox"][id="${D.fieldId}"], button[aria-haspopup="listbox"][id="${D.fieldId}"]`);if(ce){Z(ce,q,D.fieldId),B.success.push(D.fieldId);continue}}if(!V){console.warn("[VFF FieldManager] ❌ Field not found:",D.fieldId),B.notFound.push(D.fieldId);continue}}const W=V,se=W.type?.toLowerCase();if(V.tagName==="SELECT")X(V,q,D.fieldId);else if(se==="checkbox")j(W,q,D.fieldId);else if(se==="radio")N(W,q,D.fieldId);else if(V.tagName==="INPUT"||V.tagName==="TEXTAREA"){const we=String(q);V.value=we,V.dispatchEvent(new Event("input",{bubbles:!0})),V.dispatchEvent(new Event("change",{bubbles:!0}));const ce=we.substring(0,50);console.log("[VFF FieldManager] Updated text field:",D.fieldId,"→",ce)}V&&(V.setAttribute("data-vff-confirmed","true"),f.add(D.fieldId),H(V),b(V,D.fieldId),B.success.push(D.fieldId),setTimeout(()=>{k.delete(D.fieldId)},50))}console.log("[VFF FieldManager] 📊 Update summary:",{total:M.length,success:B.success.length,notFound:B.notFound.length,errors:B.errors.length}),B.notFound.length>0&&console.warn("[VFF FieldManager] ⚠️ Fields not found:",B.notFound),B.errors.length>0&&console.error("[VFF FieldManager] ❌ Errors:",B.errors),B.success.length>0&&console.log("[VFF FieldManager] ✅ Successfully updated:",B.success)}function X(M,B,D){let q=!1;for(let V=0;V<M.options.length;V++){const W=M.options[V];if(W.value===B||W.text===B){M.selectedIndex=V,q=!0,console.log("[VFF FieldManager] ✓ Exact match for select:",D,"→",W.text);break}}if(!q){const V=B.toLowerCase();for(let W=0;W<M.options.length;W++){const se=M.options[W],we=se.text.toLowerCase(),ce=se.value.toLowerCase();if(we.includes(V)||V.includes(we)||ce.includes(V)||V.includes(ce)){M.selectedIndex=W,q=!0,console.log("[VFF FieldManager] ≈ Fuzzy match for select:",D,"→",se.text);break}}}q||console.warn("[VFF FieldManager] ⚠️ No matching option found for:",B,"in",D),M.dispatchEvent(new Event("change",{bubbles:!0})),M.dispatchEvent(new Event("input",{bubbles:!0}))}function j(M,B,D){let q=!1;typeof B=="boolean"?q=B:typeof B=="string"&&(q=B==="true"||B==="True"||B==="1"||B==="yes"||B==="Yes"||B==="on"||B==="checked"),M.checked=q,M.dispatchEvent(new Event("change",{bubbles:!0})),M.dispatchEvent(new Event("input",{bubbles:!0})),console.log("[VFF FieldManager] ✓ Updated checkbox:",D,"→",q,`(from ${typeof B}: ${B})`)}function ee(M,B,D){const q=Array.isArray(B)?B:[B];console.log("[VFF FieldManager] 📋 Checkbox group:",D),console.log("  Requested values:",q);const V=[];for(const ce of M)V.push(ce.value||ie(ce));console.log("  Available checkboxes:",V);const W=[],se=[],we=new Map;for(const ce of q)we.set(String(ce),!1);for(const ce of M){const ze=ce.value||ie(ce);let Ee=null;const Ie=q.some(Ke=>{const Ne=String(Ke);if(ze===Ne||ze.toLowerCase()===Ne.toLowerCase())return Ee=Ne,!0;const Ye=Me=>Me.toLowerCase().replace(/[\/\-_,]/g," ").replace(/\s+/g," ").trim(),tt=Ye(ze),Je=Ye(Ne);return tt===Je||tt.includes(Je)||Je.includes(tt)?(Ee=Ne,!0):!1});Ie&&Ee&&(we.set(Ee,!0),W.push(ze)),ce.checked=Ie,Ie&&(ce.setAttribute("data-vff-confirmed","true"),f.add(D),H(ce),b(ce,D)),ce.dispatchEvent(new Event("change",{bubbles:!0})),ce.dispatchEvent(new Event("input",{bubbles:!0}))}for(const[ce,ze]of we.entries())ze||se.push(ce);console.log("[VFF FieldManager] ✅ Checkbox group result:",{fieldId:D,requested:q.length,matched:W.length,unmatched:se.length,total:M.length}),W.length>0&&console.log("  ✓ Matched & checked:",W),se.length>0&&(console.warn("  ⚠️ Could not match:",se),console.warn("  💡 Try one of:",V))}function ie(M){const B=document.querySelector(`label[for="${M.id}"]`);if(B)return B.textContent?.trim()||"";const D=M.closest("label");if(D){const V=D.cloneNode(!0),W=V.querySelector("input");return W&&W.remove(),V.textContent?.trim()||""}const q=M.nextSibling;return q&&q.nodeType===Node.TEXT_NODE?q.textContent?.trim()||"":M.value}function J(M,B,D){let q=!1;for(const V of M)if(V.value===B){V.checked=!0,q=!0,V.dispatchEvent(new Event("change",{bubbles:!0})),V.dispatchEvent(new Event("input",{bubbles:!0})),V.setAttribute("data-vff-confirmed","true"),f.add(D),H(V),b(V,D),console.log("[VFF FieldManager] ✓ Selected radio:",D,"→",B);break}if(!q){const V=B.toLowerCase();for(const W of M){const se=W.value.toLowerCase();if(se.includes(V)||V.includes(se)){W.checked=!0,q=!0,W.dispatchEvent(new Event("change",{bubbles:!0})),W.dispatchEvent(new Event("input",{bubbles:!0})),W.setAttribute("data-vff-confirmed","true"),f.add(D),H(W),b(W,D),console.log("[VFF FieldManager] ≈ Fuzzy match radio:",D,"→",W.value);break}}}q||console.warn("[VFF FieldManager] ⚠️ No matching radio option found for:",B,"in",D)}function N(M,B,D){M.value===B?(M.checked=!0,M.dispatchEvent(new Event("change",{bubbles:!0})),M.dispatchEvent(new Event("input",{bubbles:!0})),console.log("[VFF FieldManager] ✓ Selected single radio:",D)):console.warn("[VFF FieldManager] ⚠️ Radio value mismatch:",M.value,"!==",B)}function Z(M,B,D){console.warn("[VFF FieldManager] ⚠️ Combobox filling not fully supported yet:",D),console.log("[VFF FieldManager] Combobox should be filled with:",B),M.setAttribute("aria-valuenow",B),M.setAttribute("data-vff-value",B),M.click()}function H(M){if(M.style.outline="2px solid #10b981",M.style.outlineOffset="2px",M.parentElement?.querySelector(".vff-field-badge"))return;const D=document.createElement("span");D.className="vff-field-badge",D.textContent="✓",D.style.cssText=`
			position: absolute;
			top: 50%;
			right: 8px;
			transform: translateY(-50%);
			color: #10b981;
			font-weight: bold;
			font-size: 18px;
			pointer-events: none;
			z-index: 1000;
		`;const q=M.parentElement;q&&getComputedStyle(q).position==="static"&&(q.style.position="relative"),M.parentElement?.appendChild(D)}function te(){console.log("[VFF FieldManager] Destroying, cleaning up",w.size,"listeners");for(const[M,B]of w.entries())M.removeEventListener("blur",B),M.removeEventListener("change",B);document.querySelectorAll("[data-vff-confirmed]").forEach(M=>{M.removeAttribute("data-vff-confirmed"),M.style.outline="",M.style.outlineOffset=""}),document.querySelectorAll(".vff-field-badge").forEach(M=>{M.remove()}),w.clear(),f.clear(),v.clear()}return{applyUpdates:E,destroy:te}}const Ji=16e3,Vr=24e3;function Gc(S){const f={recordingContext:null,playbackContext:null,stream:S||null,workletNode:null,source:null};let w=!1,v=0,k=0,b=!1,I=null,A=null,E=!1,X=!1,j=!1;const ie=Math.ceil(600/1e3*Ji),J=[];let N=0;const Z=[];let H=!1,te=!1,M=0,B=[],D=!1,q=!1,V=0;const W=2.5,se=1.7,we=1.4,ce=45,ze=200;let Ee=0,Ie=0;const Ke=.9,Ne=.5,Ye=2e3;async function tt(L,K){if(!w)try{f.stream?console.log("[AudioManager] 🔗 Reusing existing microphone stream (shared with VAD)"):(f.stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,sampleRate:Ji,echoCancellation:!0,noiseSuppression:!0,autoGainControl:!0}}),console.log("[AudioManager] 🎤 Created new microphone stream")),f.recordingContext?(console.log("[AudioManager] ♻️ Reusing existing recording AudioContext"),f.recordingContext.state==="suspended"&&await f.recordingContext.resume()):(console.log("[AudioManager] 🎵 Creating AudioContext for recording (first time)"),f.recordingContext=new AudioContext({sampleRate:Ji})),f.source=f.recordingContext.createMediaStreamSource(f.stream),f.playbackContext?(console.log("[AudioManager] ♻️ Reusing existing playback AudioContext"),f.playbackContext.state==="suspended"&&await f.playbackContext.resume()):(console.log("[AudioManager] 🎵 Creating AudioContext for playback (eager initialization)"),f.playbackContext=new AudioContext({sampleRate:Vr}),v=0);const ye=!window.location.hostname.includes("localhost")&&!window.location.hostname.includes("127.0.0.1")?new URL("../shared/audio-processor.worklet.js",window.location.href).href:"/shared/audio-processor.worklet.js";console.log("[VFF Audio] Loading worklet from:",ye),await f.recordingContext.audioWorklet.addModule(ye),f.workletNode=new AudioWorkletNode(f.recordingContext,"voice-form-filler-audio-processor"),I=L,A=K||null,M=0,B=[],D=!1,V=0,Ee=0,Ie=0;const Ce=Date.now();f.workletNode.port.onmessage=lt=>{if(!w||!I)return;const{type:wt,pcmData:Ut,energy:ht}=lt.data;if(wt!=="audio")return;if(V=ht,M===0)if(Date.now()-Ce<Ye)B.push(V);else{const Rt=B.reduce((pi,ni)=>pi+ni,0);M=Math.max(Rt/B.length||Ne,Ne),V=M,A?.onCalibrationComplete&&A.onCalibrationComplete(M)}if(M>0){const qe=Date.now(),Rt=q?we:1,pi=M*W*Rt,ni=M*se;if(D)V<ni?Ie===0?Ie=qe:qe-Ie>=ze&&(D=!1,Ee=0,A?.onEnergyChange&&A.onEnergyChange(V,!1,"release")):Ie=0;else if(V>pi){if(Ee===0)Ee=qe;else if(qe-Ee>=ce){D=!0,Ie=0;const ri=q?"tts_bleed_guard":"attack";A?.onEnergyChange&&A.onEnergyChange(V,!0,ri)}}else Ee=0;if(!D&&V<ni){const ri=Ke*M+(1-Ke)*V;M=Math.max(ri,Ne)}}const Mt=new Int16Array(Ut);for(J.push(Mt),N+=Mt.length;N>ie;){const qe=J.shift();qe&&(N-=qe.length)}if(E){const qe=new Int16Array(Mt.length);I(qe.buffer)}else if(X)I(Ut);else if(j){b||(console.log("[AudioManager] 🔊 Sending warmup noise to Gemini (VAD inactive, warmup mode enabled)"),b=!0);const qe=new Int16Array(Mt.length);for(let Rt=0;Rt<qe.length;Rt++)qe[Rt]=Math.floor((Math.random()*2-1)*300);I(qe.buffer)}else{const qe=new Int16Array(Mt.length);I(qe.buffer)}},f.source.connect(f.workletNode),f.workletNode.connect(f.recordingContext.destination),w=!0}catch(he){throw console.error("[VFF Audio] Failed to start recording:",he),_t(),he}}function Je(){if(w){if(w=!1,I=null,f.workletNode){try{f.workletNode.disconnect(),f.workletNode.port.close()}catch{}f.workletNode=null}if(f.source){try{f.source.disconnect()}catch{}f.source=null}if(f.recordingContext){try{f.recordingContext.close()}catch{}f.recordingContext=null}f.stream&&(f.stream.getTracks().forEach(L=>L.stop()),f.stream=null)}}async function Me(L){try{if(k||(k=0),k++,k===1&&console.log(`[AudioManager] 🔊 Playing first audio chunk (${L.byteLength} bytes)`),H){console.log(`[AudioManager] 🚫 Discarding chunk #${k} (barge-in active)`);return}f.playbackContext||(console.log("[AudioManager] 🎵 Creating AudioContext for playback (lazy fallback)"),f.playbackContext=new AudioContext({sampleRate:Vr}),v=0);const K=f.playbackContext;K.state==="suspended"&&(console.log("[AudioManager] ⏸️ Resuming suspended AudioContext"),await K.resume());const he=Ve(L),ye=new Int16Array(he);if(ye.length===0){console.warn(`[AudioManager] ⚠️ Chunk #${k} decoded to 0 samples`);return}const Ce=new Float32Array(ye.length);for(let qe=0;qe<ye.length;qe++)Ce[qe]=ye[qe]/32768;const lt=K.createBuffer(1,Ce.length,Vr);lt.getChannelData(0).set(Ce);const wt=K.currentTime,Ut=Math.max(v,wt+.01),ht=K.createBufferSource();ht.buffer=lt,ht.connect(K.destination),ht.start(Ut),Z.push(ht);const Mt=!q;q=!0,Mt&&window.vffOnAudioPlaybackStart&&window.vffOnAudioPlaybackStart(),v=Ut+lt.duration,ht.onended=()=>{v<K.currentTime&&(v=K.currentTime);const qe=Z.indexOf(ht);qe>-1&&Z.splice(qe,1),Z.length===0&&(q=!1,!te&&window.vffOnAudioPlaybackEnd&&window.vffOnAudioPlaybackEnd())}}catch(K){q=!1,console.error("[VFF Audio] Playback failed:",K)}}function Ve(L){try{const K=new TextDecoder().decode(L);if(K.match(/^[A-Za-z0-9+/]+=*$/)){const he=atob(K),ye=new Uint8Array(he.length);for(let Ce=0;Ce<he.length;Ce++)ye[Ce]=he.charCodeAt(Ce);return ye.buffer}}catch{}return L}function Xe(){H=!0,te=!0,Z.forEach(L=>{try{L.stop(),L.disconnect()}catch{}}),Z.length=0,f.playbackContext&&(v=f.playbackContext.currentTime),q=!1,te=!1}function dt(){H=!1}function ct(){return w}function _t(){if(Je(),f.playbackContext){try{f.playbackContext.close()}catch{}f.playbackContext=null}v=0}function Re(){_t()}function st(){return q}function Tt(){return D}function We(){console.log("[AudioManager] Muting input - sending silence"),E=!0}function zt(){console.log("[AudioManager] Unmuting input - sending real audio"),E=!1}function at(){return f.stream}function yt(L){const K=X;if(X=L,L&&!K&&I){console.log(`[AudioManager] VAD activated - flushing ${N} samples (${(N/Ji*1e3).toFixed(0)}ms) from pre-buffer`);for(const he of J){const ye=new ArrayBuffer(he.byteLength);new Int16Array(ye).set(he),I(ye)}console.log("[AudioManager] Pre-buffer flushed, now sending live audio")}else!L&&K&&console.log("[AudioManager] VAD deactivated - sending silence")}function Te(L){j=L,console.log(`[AudioManager] VAD warmup mode ${L?"enabled":"disabled"}`)}return{startRecording:tt,stopRecording:Je,playAudio:Me,flushAudioQueue:Xe,resumePlayback:dt,isRecording:ct,isSpeaking:st,getUserSpeaking:Tt,muteInput:We,unmuteInput:zt,getStream:at,setVADActive:yt,setVADWarmupMode:Te,destroy:Re}}function Wr(){const S=window.__VFF_LOCAL_DEV,f=window.__VFF_BACKEND_URL,w=window.__VFF_DEBUG_METRICS;return{enabled:!!S,backendUrl:f||"ws://localhost:8000/ws/fill",debugMetrics:!!w||!!S}}function zf(){const S=Wr();return S.enabled?(console.log("[VFF Config] 🔧 LOCAL DEV MODE ENABLED"),console.log("[VFF Config] Backend URL:",S.backendUrl),console.log("[VFF Config] Debug Metrics:",S.debugMetrics),S.backendUrl):"wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill"}function Mf(){return"wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill"}function Rf(){return Wr().debugMetrics}function Of(){console.log(`
`+"=".repeat(60)),console.log("🔧 VOICE FORM FILLER - LOCAL DEVELOPMENT MODE"),console.log("=".repeat(60)),console.log(`
To test locally without deploying:`),console.log(`
1. Start backend:`),console.log("   cd backend"),console.log("   source venv/bin/activate  # or venv\\Scripts\\activate on Windows"),console.log("   uvicorn main:app --reload --port 8000"),console.log(`
2. Enable local dev in browser console:`),console.log("   window.__VFF_LOCAL_DEV = true"),console.log(`
3. Load bookmarklet (will connect to localhost:8000)`),console.log(`
4. Test VAD tuning changes:`),console.log("   - Edit backend/adapters/live_ai_gemini.py"),console.log("   - Backend auto-reloads (--reload flag)"),console.log("   - Reconnect bookmarklet to test"),console.log(`
Optional environment variables:`),console.log('   window.__VFF_BACKEND_URL = "ws://localhost:8000/ws/fill"  // Custom URL'),console.log("   window.__VFF_DEBUG_METRICS = true                          // Extra logging"),console.log(`
`+"=".repeat(60)+`
`)}typeof window<"u"&&Wr().enabled&&Of();class Df{constructor(){Ge(this,"sessionMetrics",null);Ge(this,"currentBargeIn",null);Ge(this,"lastBargeInTime",0);Ge(this,"BARGE_IN_GRACE_PERIOD_MS",150);Ge(this,"debugEnabled",!1)}startSession(f){this.debugEnabled=Rf(),this.sessionMetrics={sessionId:f,sessionStart:Date.now(),bargeIns:[],toolCalls:[],falseStarts:0,successfulBargeIns:0,timedOutBargeIns:0,hallucinatedToolCalls:0},this.currentBargeIn=null,this.lastBargeInTime=0,this.debugEnabled&&console.log("[VFF Metrics] 📊 Session started:",f,"(Debug mode: ON)")}recordMicActivity(){if(!this.sessionMetrics)return;const f=performance.now();this.currentBargeIn={timestamp:Date.now(),micActivityDetected:f,result:"pending"},console.log("[VFF Metrics] 🎤 Mic activity detected")}recordTTSPaused(){if(!this.sessionMetrics||!this.currentBargeIn)return;const f=performance.now();this.currentBargeIn.ttsPausedAt=f,this.currentBargeIn.bargeInLatency=f-this.currentBargeIn.micActivityDetected,console.log(`[VFF Metrics] 🔇 TTS paused - Barge-in latency: ${this.currentBargeIn.bargeInLatency.toFixed(1)}ms`,this.currentBargeIn.bargeInLatency<180?"✅":"⚠️ SLOW")}recordCancelSent(){if(!this.sessionMetrics||!this.currentBargeIn)return;const f=performance.now();this.currentBargeIn.cancelSentAt=f,console.log("[VFF Metrics] 📤 Cancel message sent to backend")}recordGeminiAck(){if(!this.sessionMetrics||!this.currentBargeIn)return;const f=performance.now();this.currentBargeIn.geminiAckAt=f,this.currentBargeIn.cancelSentAt&&(this.currentBargeIn.cancelAckLatency=f-this.currentBargeIn.cancelSentAt,console.log(`[VFF Metrics] ✅ Gemini acknowledged - Cancel latency: ${this.currentBargeIn.cancelAckLatency.toFixed(1)}ms`,this.currentBargeIn.cancelAckLatency<150?"✅":"⚠️ SLOW")),this.currentBargeIn.result="success",this.sessionMetrics.successfulBargeIns++,this.lastBargeInTime=f,this.sessionMetrics.bargeIns.push(this.currentBargeIn),this.currentBargeIn=null}recordBargeInTimeout(){!this.sessionMetrics||!this.currentBargeIn||(console.warn("[VFF Metrics] ⏱️ Barge-in timeout - Gemini did not acknowledge"),this.currentBargeIn.result="timeout",this.sessionMetrics.timedOutBargeIns++,this.sessionMetrics.bargeIns.push(this.currentBargeIn),this.currentBargeIn=null)}recordFalseStart(){!this.sessionMetrics||!this.currentBargeIn||(console.log("[VFF Metrics] 🔄 False start detected"),this.currentBargeIn.result="false_start",this.sessionMetrics.falseStarts++,this.sessionMetrics.bargeIns.push(this.currentBargeIn),this.currentBargeIn=null)}checkFalseStart(f,w){return w&&f?(console.warn("[VFF Metrics] ⚠️ FALSE START: Gemini speaking while user mic active!"),this.recordFalseStart(),!0):!1}recordToolCall(f,w){if(!this.sessionMetrics)return"accept";const v=performance.now(),k=v-this.lastBargeInTime,b=k<this.BARGE_IN_GRACE_PERIOD_MS,I={timestamp:Date.now(),toolName:f,callId:w,receivedAt:v,bargeInWindowActive:b,decision:"accepted"};return b?(I.decision="rejected_barge_in",I.rejectionReason=`Received ${k.toFixed(1)}ms after barge-in (< ${this.BARGE_IN_GRACE_PERIOD_MS}ms threshold)`,this.sessionMetrics.hallucinatedToolCalls++,this.sessionMetrics.toolCalls.push(I),console.warn("[VFF Metrics] 🚫 Tool call REJECTED (hallucination):",`${f} [${w.slice(0,8)}]`,`- ${I.rejectionReason}`),"reject"):(this.sessionMetrics.toolCalls.push(I),console.log("[VFF Metrics] ✅ Tool call ACCEPTED:",`${f} [${w.slice(0,8)}]`,`- ${k.toFixed(0)}ms after last barge-in`),"accept")}getStats(){if(!this.sessionMetrics)return null;const f=this.sessionMetrics.bargeIns,w=f.filter(E=>E.bargeInLatency!==void 0).map(E=>E.bargeInLatency),v=f.filter(E=>E.cancelAckLatency!==void 0).map(E=>E.cancelAckLatency),k=E=>E.length?E.reduce((X,j)=>X+j,0)/E.length:0,b=E=>{if(!E.length)return 0;const X=[...E].sort((ee,ie)=>ee-ie),j=Math.floor(X.length*.95);return X[j]},I=f.length,A=this.sessionMetrics.toolCalls.length;return{totalBargeIns:I,successfulBargeIns:this.sessionMetrics.successfulBargeIns,timedOutBargeIns:this.sessionMetrics.timedOutBargeIns,falseStarts:this.sessionMetrics.falseStarts,avgBargeInLatency:k(w),p95BargeInLatency:b(w),avgCancelAckLatency:k(v),p95CancelAckLatency:b(v),totalToolCalls:A,hallucinatedToolCalls:this.sessionMetrics.hallucinatedToolCalls,toolCallHallucinationRate:A?this.sessionMetrics.hallucinatedToolCalls/A*100:0,falseStartRate:I?this.sessionMetrics.falseStarts/I*100:0}}printSummary(){const f=this.getStats();if(!f){console.log("[VFF Metrics] No session data");return}console.log(`
`+"=".repeat(60)),console.log("📊 VAD TUNING METRICS SUMMARY"),console.log("=".repeat(60)),console.log(`
🎤 BARGE-IN PERFORMANCE:`),console.log(`   Total Barge-Ins: ${f.totalBargeIns}`),console.log(`   Successful: ${f.successfulBargeIns} (${(f.successfulBargeIns/f.totalBargeIns*100).toFixed(1)}%)`),console.log(`   Timeouts: ${f.timedOutBargeIns}`),console.log(`   False Starts: ${f.falseStarts} (${f.falseStartRate.toFixed(1)}%)`),console.log(`   Avg Latency: ${f.avgBargeInLatency.toFixed(1)}ms ${f.avgBargeInLatency<180?"✅":"⚠️"}`),console.log(`   P95 Latency: ${f.p95BargeInLatency.toFixed(1)}ms ${f.p95BargeInLatency<180?"✅ TARGET MET":"❌ EXCEEDS TARGET"}`),console.log(`
🔄 CANCEL ACKNOWLEDGMENT:`),console.log(`   Avg Latency: ${f.avgCancelAckLatency.toFixed(1)}ms ${f.avgCancelAckLatency<150?"✅":"⚠️"}`),console.log(`   P95 Latency: ${f.p95CancelAckLatency.toFixed(1)}ms ${f.p95CancelAckLatency<150?"✅ TARGET MET":"❌ EXCEEDS TARGET"}`),console.log(`
🛠️ TOOL CALL SAFETY:`),console.log(`   Total Tool Calls: ${f.totalToolCalls}`),console.log(`   Hallucinated (rejected): ${f.hallucinatedToolCalls}`),console.log(`   Hallucination Rate: ${f.toolCallHallucinationRate.toFixed(1)}% ${f.toolCallHallucinationRate<1?"✅ EXCELLENT":f.toolCallHallucinationRate<5?"⚠️ ACCEPTABLE":"❌ TOO HIGH"}`),console.log(`
`+"=".repeat(60)+`
`)}endSession(){this.sessionMetrics&&(console.log("[VFF Metrics] 📊 Session ended:",this.sessionMetrics.sessionId),this.printSummary(),this.sessionMetrics=null,this.currentBargeIn=null,this.lastBargeInTime=0)}exportData(){return this.sessionMetrics?{...this.sessionMetrics}:null}}const ti=new Df;typeof window<"u"&&(window.__VFF_METRICS__=ti);function Bf(S,f){console.log("[VFF Connection] 🔄 Restoring DOM from sessionStorage...");let w=0;for(const[v,k]of Object.entries(S.current_values)){const b=k.value;if(b==null||b==="")continue;let I=document.getElementById(v);if(!I){const A=document.querySelectorAll(`input[name="${v}"], textarea[name="${v}"], select[name="${v}"]`);A.length>0&&(I=A[0])}if(I){if(I.tagName==="SELECT")I.value=String(b);else if(I.tagName==="INPUT"){const A=I;A.type==="checkbox"?A.checked=!!b:A.value=String(b)}else I.tagName==="TEXTAREA"&&(I.value=String(b));w++}}console.log(`[VFF Connection] ✅ Restored ${w} fields from sessionStorage to DOM`)}function jc(S,f){console.log("[VFF Connection] 🔍 Scanning DOM for pre-filled values...");let w=0;for(const v of f.fields){const k=v.id;let b=document.getElementById(k);if(!b){const A=document.querySelectorAll(`input[name="${k}"], textarea[name="${k}"], select[name="${k}"]`);A.length>0&&(b=A[0])}if(!b)continue;let I=null;if(b.tagName==="SELECT")I=b.value||null;else if(b.tagName==="INPUT"){const A=b;A.type==="checkbox"?I=A.checked:A.type==="radio"?A.checked&&(I=A.value):I=A.value||null}else b.tagName==="TEXTAREA"&&(I=b.value||null);I!==null&&I!==""&&I!==!1&&(S.updateField(k,I,{confirmed:!0,emit:!1}),w++,console.log("[VFF Connection] ✓ Captured pre-filled:",k,"=",I))}console.log(`[VFF Connection] ✅ Captured ${w} pre-filled values from DOM`)}function Gr(S,f,w="English",v){const k=Ff();let b=null,I=null,A=null,E=w,X=!1,j=k,ee=!1;const ie=ve.init(S);Bf(ie),A=Gc(v),v&&console.log("[VFF Connection] 🔗 Audio manager using shared stream (VAD coordination)"),I=Wc({schema:S,onManualEdit:(N,Z)=>{console.log("[VFF Connection] 🖊️ Manual edit detected:",N,"=",Z);const H=ve.updateFieldValue(ie,N,Z,{confirmed:!0});if(Object.assign(ie,H),console.log("[VFF Connection] ✓ Updated sessionStorage for:",N),b){const M=S.fields.find(B=>B.id===N)?.name||N;b.sendManualFieldUpdate(N,M,Z),console.log("[VFF Connection] ✓ Notified Gemini about:",N)}}}),console.log("[VFF Connection] ✅ Field manager created - listening for manual edits");const J={onStatusChange:N=>{f(N)},onSessionReady:N=>{f("connected"),ti.startSession(N)},onSessionRestarted:()=>{console.log("[VFF Connection] ✅ Gemini session restarted - updating status"),f("connected")},onFieldUpdate:N=>{console.log("[VFF Connection] 📥 Tool call received: update_form_fields with",N.length,"field(s)"),N.forEach((te,M)=>{console.log(`  [${M+1}] fieldId:`,te.fieldId,"→ value:",te.value)});const Z=[],H=[];for(const te of N){const M=`field_${te.fieldId}_${Date.now()}`;if(ti.recordToolCall("update_form_fields",M)==="reject"){H.push(te);continue}Z.push(te)}H.length>0&&console.warn("[VFF Connection] ⚠️ Rejected",H.length,"hallucinated update(s):",H.map(te=>te.fieldId)),console.log("[VFF Connection] ✅ Accepted",Z.length,"update(s) for processing"),I&&Z.length>0&&I.applyUpdates(Z)},onAudioData:async N=>{A&&await A.playAudio(N)},onError:N=>{console.error("[VFF Connection] Error:",N),f("error")}};return{async connect(){if(b&&b.getStatus()==="connected"&&b){console.log("[VFF Connection] 🔄 WebSocket alive - restarting Gemini session");const Z=b.getNextFieldHint();try{f("reconnecting"),b.send({type:"restart_gemini_session",next_field_hint:Z}),console.log("[VFF Connection] ⏳ Gemini session restart requested",{nextFieldHint:Z});return}catch(H){console.error("[VFF Connection] Failed to restart Gemini:",H),f("disconnected")}}try{console.log("[VFF Connection] Attempting to connect to:",k),f("connecting"),A||(console.log("[VFF Connection] 🔄 Reinitializing audio manager (reconnect)"),A=Gc(v)),I||(console.log("[VFF Connection] 🔄 Reinitializing field manager (reconnect)"),I=Wc({schema:S,onManualEdit:(Z,H)=>{console.log("[VFF Connection] 🖊️ Manual edit detected:",Z,"=",H);const te=ve.updateFieldValue(ie,Z,H,{confirmed:!0});if(Object.assign(ie,te),console.log("[VFF Connection] ✓ Updated sessionStorage for:",Z),b){const B=S.fields.find(D=>D.id===Z)?.name||Z;b.sendManualFieldUpdate(Z,B,H),console.log("[VFF Connection] ✓ Notified Gemini about:",Z)}}})),b||(b=new qc(S,J,E)),jc(b,S);try{console.log("[VFF Connection] Trying localhost..."),await b.connect(k),j=k,console.log("[VFF Connection] ✅ Connected to localhost")}catch(Z){const H=Mf();console.log("[VFF Connection] Localhost failed, trying cloud:",H),console.log("[VFF Connection] Local error was:",Z),b.disconnect(),b=new qc(S,J,E),jc(b,S),await b.connect(H),j=H,console.log("[VFF Connection] ✅ Connected to cloud")}}catch(Z){throw console.error("[VFF Connection] Connection failed:",Z),console.error("[VFF Connection] Error details:",{message:Z instanceof Error?Z.message:String(Z),stack:Z instanceof Error?Z.stack:void 0,wsUrl:k}),f("error"),Z}},pause(){console.log("[VFF Connection] Pausing (keeping connection warm)..."),X=!0,A?.isRecording()&&A.stopRecording(),A&&A.flushAudioQueue(),f("paused")},async resume(){if(console.log("[VFF Connection] Resuming..."),!b||b.getStatus()!=="connected"){console.error("[VFF Connection] Cannot resume - not connected"),f("error");return}X=!1,f("connected"),A&&!A.isRecording()&&await this.startRecording(),console.log("[VFF Connection] Resumed successfully")},disconnect(){ti.endSession(),b&&(b.disconnect(),b=null),I&&(I.destroy(),I=null),A&&(A.destroy(),A=null),f("disconnected")},getStatus(){return b?.getStatus()??"disconnected"},sendAudio(N){b&&b.sendAudio(N)},sendActivityStart(){b&&b.sendActivityStart()},sendActivityEnd(){b&&b.sendActivityEnd()},sendPrompt(N){b&&b.sendPrompt(N)},sendRecoveryPrompt(N,Z){b&&b.sendRecoveryPrompt(N,Z)},endGeminiSession(){b&&b.endGeminiSession()},setPushToTalkMode(N){console.log(`[VFF Connection] Setting push-to-talk mode: ${N}`),ee=N},getFieldManager(){return I},getAudioManager(){return A},async startRecording(){if(console.log("[VFF Connection] startRecording called"),!A){console.error("[VFF Connection] Audio manager not initialized");return}console.log("[VFF Connection] Requesting microphone access..."),await A.startRecording(N=>{b&&b.getStatus()==="connected"&&b.sendAudio(N)},{onEnergyChange:(N,Z,H)=>{},onCalibrationComplete:N=>{console.log("[VFF Connection] 🎤 Audio calibration complete, baseline:",N)}})},stopRecording(){A&&A.stopRecording()},isRecording(){return A?.isRecording()??!1},isPaused(){return X},async changeFillLanguage(N){E=N,b&&b.getStatus()==="connected"?await b.changeFillLanguage(N):console.log("[VFF Connection] Language preference saved, will be used on next connect")},async startSection(N){if(!b)throw new Error("Connection not initialized");A?.isRecording()&&A.stopRecording(),await b.startSection(N,k),!X&&A&&await A.startRecording(Z=>{b&&b.sendAudio(Z)})},async switchSection(N){if(!b)throw new Error("Connection not initialized");A?.isRecording()&&A.stopRecording(),await b.switchSection(N,j),!X&&A&&await A.startRecording(Z=>{b&&b.sendAudio(Z)})},async completeSection(){if(!b)throw new Error("Connection not initialized");await b.completeSection(k)},getCurrentSection(){return b?.getCurrentSection()},getCompletedSections(){return b?.getCompletedSections()||new Set},onVADSpeechStart(){if(!A||ee)return;A.isSpeaking()&&(console.log("[VFF Connection] 🎤 VAD detected speech - interrupting Gemini"),ti.recordMicActivity(),A.flushAudioQueue(),ti.recordTTSPaused(),b&&b.sendActivityStart(),ti.recordCancelSent())},onVADSpeechEnd(){if(!A||ee)return;A.isSpeaking()||A.resumePlayback(),b&&b.sendActivityEnd(),console.log("[VFF Connection] 🎤 VAD speech ended - sent activity_end")}}}function Ff(){return zf()}var ep={},qr={},Ai={};Object.defineProperty(Ai,"__esModule",{value:!0});Ai.baseAssetPath=void 0;const Pf=typeof window<"u"&&typeof window.document<"u",Hc=Pf?window.document.currentScript:null;let tp="/";Hc&&(tp=Hc.src.replace(/#.*$/,"").replace(/\?.*$/,"").replace(/\/[^\/]+$/,"/"));Ai.baseAssetPath=tp;var di={};Object.defineProperty(di,"__esModule",{value:!0});di.defaultModelFetcher=void 0;const Nf=S=>fetch(S).then(f=>f.arrayBuffer());di.defaultModelFetcher=Nf;var At={},ci={};(function(S){Object.defineProperty(S,"__esModule",{value:!0}),S.log=S.LOG_PREFIX=void 0,S.LOG_PREFIX="[VAD]";const f=["error","debug","warn"];function w(k){return(...b)=>{console[k](S.LOG_PREFIX,...b)}}const v=f.reduce((k,b)=>(k[b]=w(b),k),{});S.log=v})(ci);var ii={};Object.defineProperty(ii,"__esModule",{value:!0});ii.Message=void 0;var Kc;(function(S){S.AudioFrame="AUDIO_FRAME",S.SpeechStart="SPEECH_START",S.VADMisfire="VAD_MISFIRE",S.SpeechEnd="SPEECH_END",S.SpeechStop="SPEECH_STOP",S.SpeechRealStart="SPEECH_REAL_START",S.FrameProcessed="FRAME_PROCESSED"})(Kc||(ii.Message=Kc={}));Object.defineProperty(At,"__esModule",{value:!0});At.FrameProcessor=At.validateOptions=At.defaultFrameProcessorOptions=void 0;const Ci=ci,ei=ii;At.defaultFrameProcessorOptions={positiveSpeechThreshold:.3,negativeSpeechThreshold:.25,preSpeechPadMs:800,redemptionMs:1400,minSpeechMs:400,submitUserSpeechOnPause:!1};function Vf(S){(S.positiveSpeechThreshold<0||S.positiveSpeechThreshold>1)&&Ci.log.error("positiveSpeechThreshold should be a number between 0 and 1"),(S.negativeSpeechThreshold<0||S.negativeSpeechThreshold>S.positiveSpeechThreshold)&&Ci.log.error("negativeSpeechThreshold should be between 0 and positiveSpeechThreshold"),S.preSpeechPadMs<0&&Ci.log.error("preSpeechPadMs should be positive"),S.redemptionMs<0&&Ci.log.error("redemptionMs should be positive"),S.minSpeechMs<0&&Ci.log.error("minSpeechMs should be positive")}At.validateOptions=Vf;const Zc=S=>{const f=S.reduce((v,k)=>(v.push(v.at(-1)+k.length),v),[0]),w=new Float32Array(f.at(-1));return S.forEach((v,k)=>{const b=f[k];w.set(v,b)}),w};class Lf{constructor(f,w,v,k){this.modelProcessFunc=f,this.modelResetFunc=w,this.options=v,this.msPerFrame=k,this.speaking=!1,this.redemptionCounter=0,this.speechFrameCount=0,this.active=!1,this.speechRealStartFired=!1,this.reset=()=>{this.speaking=!1,this.speechRealStartFired=!1,this.audioBuffer=[],this.modelResetFunc(),this.redemptionCounter=0,this.speechFrameCount=0},this.pause=b=>{this.active=!1,this.options.submitUserSpeechOnPause?this.endSegment(b):this.reset()},this.resume=()=>{this.active=!0},this.endSegment=b=>{const I=this.audioBuffer;this.audioBuffer=[];const A=this.speaking;if(this.reset(),A)if(I.reduce((X,j)=>j.isSpeech?X+1:X,0)>=this.minSpeechFrames){const X=Zc(I.map(j=>j.frame));b({msg:ei.Message.SpeechEnd,audio:X})}else b({msg:ei.Message.VADMisfire});return{}},this.process=async(b,I)=>{if(!this.active)return;const A=await this.modelProcessFunc(b),E=A.isSpeech>=this.options.positiveSpeechThreshold;if(I({probs:A,msg:ei.Message.FrameProcessed,frame:b}),this.audioBuffer.push({frame:b,isSpeech:E}),E&&(this.speechFrameCount++,this.redemptionCounter=0),E&&!this.speaking&&(this.speaking=!0,I({msg:ei.Message.SpeechStart})),this.speaking&&this.speechFrameCount===this.minSpeechFrames&&!this.speechRealStartFired&&(this.speechRealStartFired=!0,I({msg:ei.Message.SpeechRealStart})),A.isSpeech<this.options.negativeSpeechThreshold&&this.speaking&&++this.redemptionCounter>=this.redemptionFrames){this.redemptionCounter=0,this.speechFrameCount=0,this.speaking=!1,this.speechRealStartFired=!1;const X=this.audioBuffer;if(this.audioBuffer=[],X.reduce((ee,ie)=>ie.isSpeech?ee+1:ee,0)>=this.minSpeechFrames){const ee=Zc(X.map(ie=>ie.frame));I({msg:ei.Message.SpeechEnd,audio:ee})}else I({msg:ei.Message.VADMisfire})}if(!this.speaking){for(;this.audioBuffer.length>this.preSpeechPadFrames;)this.audioBuffer.shift();this.speechFrameCount=0}},this.audioBuffer=[],this.redemptionFrames=Math.floor(v.redemptionMs/this.msPerFrame),this.preSpeechPadFrames=Math.floor(v.preSpeechPadMs/this.msPerFrame),this.minSpeechFrames=Math.floor(v.minSpeechMs/this.msPerFrame),this.reset()}}At.FrameProcessor=Lf;var ip={};function ui(S){throw new Error('Could not dynamically require "'+S+'". Please configure the dynamicRequireTargets or/and ignoreDynamicRequires option of @rollup/plugin-commonjs appropriately for this require call to work.')}var np={exports:{}};/*!
 * ONNX Runtime Web v1.23.0
 * Copyright (c) Microsoft Corporation. All rights reserved.
 * Licensed under the MIT License.
 */(function(S,f){var w=(()=>{var v=Object.defineProperty,k=Object.getOwnPropertyDescriptor,b=Object.getOwnPropertyNames,I=Object.prototype.hasOwnProperty,A=(e=>typeof ui<"u"?ui:typeof Proxy<"u"?new Proxy(e,{get:(t,i)=>(typeof ui<"u"?ui:t)[i]}):e)(function(e){if(typeof ui<"u")return ui.apply(this,arguments);throw Error('Dynamic require of "'+e+'" is not supported')}),E=(e,t)=>()=>(e&&(t=e(e=0)),t),X=(e,t)=>{for(var i in t)v(e,i,{get:t[i],enumerable:!0})},j=(e,t,i,n)=>{if(t&&typeof t=="object"||typeof t=="function")for(let r of b(t))!I.call(e,r)&&r!==i&&v(e,r,{get:()=>t[r],enumerable:!(n=k(t,r))||n.enumerable});return e},ee=e=>j(v({},"__esModule",{value:!0}),e),ie,J,N,Z,H,te=E(()=>{ie=new Map,J=[],N=(e,t,i)=>{if(t&&typeof t.init=="function"&&typeof t.createInferenceSessionHandler=="function"){let n=ie.get(e);if(n===void 0)ie.set(e,{backend:t,priority:i});else{if(n.priority>i)return;if(n.priority===i&&n.backend!==t)throw new Error(`cannot register backend "${e}" using priority ${i}`)}if(i>=0){let r=J.indexOf(e);r!==-1&&J.splice(r,1);for(let s=0;s<J.length;s++)if(ie.get(J[s]).priority<=i){J.splice(s,0,e);return}J.push(e)}return}throw new TypeError("not a valid backend")},Z=async e=>{let t=ie.get(e);if(!t)return"backend not found.";if(t.initialized)return t.backend;if(t.aborted)return t.error;{let i=!!t.initPromise;try{return i||(t.initPromise=t.backend.init(e)),await t.initPromise,t.initialized=!0,t.backend}catch(n){return i||(t.error=`${n}`,t.aborted=!0),t.error}finally{delete t.initPromise}}},H=async e=>{let t=e.executionProviders||[],i=t.map(l=>typeof l=="string"?l:l.name),n=i.length===0?J:i,r,s=[],a=new Set;for(let l of n){let u=await Z(l);typeof u=="string"?s.push({name:l,err:u}):(r||(r=u),r===u&&a.add(l))}if(!r)throw new Error(`no available backend found. ERR: ${s.map(l=>`[${l.name}] ${l.err}`).join(", ")}`);for(let{name:l,err:u}of s)i.includes(l)&&console.warn(`removing requested execution provider "${l}" from session options because it is not available: ${u}`);let o=t.filter(l=>a.has(typeof l=="string"?l:l.name));return[r,new Proxy(e,{get:(l,u)=>u==="executionProviders"?o:Reflect.get(l,u)})]}}),M=E(()=>{te()}),B,D=E(()=>{B="1.23.0"}),q,V,W=E(()=>{D(),q="warning",V={wasm:{},webgl:{},webgpu:{},versions:{common:B},set logLevel(e){if(e!==void 0){if(typeof e!="string"||["verbose","info","warning","error","fatal"].indexOf(e)===-1)throw new Error(`Unsupported logging level: ${e}`);q=e}},get logLevel(){return q}},Object.defineProperty(V,"logLevel",{enumerable:!0})}),se,we=E(()=>{W(),se=V}),ce,ze,Ee=E(()=>{ce=(e,t)=>{let i=typeof document<"u"?document.createElement("canvas"):new OffscreenCanvas(1,1);i.width=e.dims[3],i.height=e.dims[2];let n=i.getContext("2d");if(n!=null){let r,s;t?.tensorLayout!==void 0&&t.tensorLayout==="NHWC"?(r=e.dims[2],s=e.dims[3]):(r=e.dims[3],s=e.dims[2]);let a=t?.format!==void 0?t.format:"RGB",o=t?.norm,l,u;o===void 0||o.mean===void 0?l=[255,255,255,255]:typeof o.mean=="number"?l=[o.mean,o.mean,o.mean,o.mean]:(l=[o.mean[0],o.mean[1],o.mean[2],0],o.mean[3]!==void 0&&(l[3]=o.mean[3])),o===void 0||o.bias===void 0?u=[0,0,0,0]:typeof o.bias=="number"?u=[o.bias,o.bias,o.bias,o.bias]:(u=[o.bias[0],o.bias[1],o.bias[2],0],o.bias[3]!==void 0&&(u[3]=o.bias[3]));let d=s*r,c=0,p=d,h=d*2,m=-1;a==="RGBA"?(c=0,p=d,h=d*2,m=d*3):a==="RGB"?(c=0,p=d,h=d*2):a==="RBG"&&(c=0,h=d,p=d*2);for(let _=0;_<s;_++)for(let $=0;$<r;$++){let y=(e.data[c++]-u[0])*l[0],g=(e.data[p++]-u[1])*l[1],T=(e.data[h++]-u[2])*l[2],x=m===-1?255:(e.data[m++]-u[3])*l[3];n.fillStyle="rgba("+y+","+g+","+T+","+x+")",n.fillRect($,_,1,1)}if("toDataURL"in i)return i.toDataURL();throw new Error("toDataURL is not supported")}else throw new Error("Can not access image data")},ze=(e,t)=>{let i=typeof document<"u"?document.createElement("canvas").getContext("2d"):new OffscreenCanvas(1,1).getContext("2d"),n;if(i!=null){let r,s,a;t?.tensorLayout!==void 0&&t.tensorLayout==="NHWC"?(r=e.dims[2],s=e.dims[1],a=e.dims[3]):(r=e.dims[3],s=e.dims[2],a=e.dims[1]);let o=t!==void 0&&t.format!==void 0?t.format:"RGB",l=t?.norm,u,d;l===void 0||l.mean===void 0?u=[255,255,255,255]:typeof l.mean=="number"?u=[l.mean,l.mean,l.mean,l.mean]:(u=[l.mean[0],l.mean[1],l.mean[2],255],l.mean[3]!==void 0&&(u[3]=l.mean[3])),l===void 0||l.bias===void 0?d=[0,0,0,0]:typeof l.bias=="number"?d=[l.bias,l.bias,l.bias,l.bias]:(d=[l.bias[0],l.bias[1],l.bias[2],0],l.bias[3]!==void 0&&(d[3]=l.bias[3]));let c=s*r;if(t!==void 0&&(t.format!==void 0&&a===4&&t.format!=="RGBA"||a===3&&t.format!=="RGB"&&t.format!=="BGR"))throw new Error("Tensor format doesn't match input tensor dims");let p=4,h=0,m=1,_=2,$=3,y=0,g=c,T=c*2,x=-1;o==="RGBA"?(y=0,g=c,T=c*2,x=c*3):o==="RGB"?(y=0,g=c,T=c*2):o==="RBG"&&(y=0,T=c,g=c*2),n=i.createImageData(r,s);for(let C=0;C<s*r;h+=p,m+=p,_+=p,$+=p,C++)n.data[h]=(e.data[y++]-d[0])*u[0],n.data[m]=(e.data[g++]-d[1])*u[1],n.data[_]=(e.data[T++]-d[2])*u[2],n.data[$]=x===-1?255:(e.data[x++]-d[3])*u[3]}else throw new Error("Can not access image data");return n}}),Ie,Ke,Ne,Ye,tt,Je,Me=E(()=>{zt(),Ie=(e,t)=>{if(e===void 0)throw new Error("Image buffer must be defined");if(t.height===void 0||t.width===void 0)throw new Error("Image height and width must be defined");if(t.tensorLayout==="NHWC")throw new Error("NHWC Tensor layout is not supported yet");let{height:i,width:n}=t,r=t.norm??{mean:255,bias:0},s,a;typeof r.mean=="number"?s=[r.mean,r.mean,r.mean,r.mean]:s=[r.mean[0],r.mean[1],r.mean[2],r.mean[3]??255],typeof r.bias=="number"?a=[r.bias,r.bias,r.bias,r.bias]:a=[r.bias[0],r.bias[1],r.bias[2],r.bias[3]??0];let o=t.format!==void 0?t.format:"RGBA",l=t.tensorFormat!==void 0&&t.tensorFormat!==void 0?t.tensorFormat:"RGB",u=i*n,d=l==="RGBA"?new Float32Array(u*4):new Float32Array(u*3),c=4,p=0,h=1,m=2,_=3,$=0,y=u,g=u*2,T=-1;o==="RGB"&&(c=3,p=0,h=1,m=2,_=-1),l==="RGBA"?T=u*3:l==="RBG"?($=0,g=u,y=u*2):l==="BGR"&&(g=0,y=u,$=u*2);for(let x=0;x<u;x++,p+=c,m+=c,h+=c,_+=c)d[$++]=(e[p]+a[0])/s[0],d[y++]=(e[h]+a[1])/s[1],d[g++]=(e[m]+a[2])/s[2],T!==-1&&_!==-1&&(d[T++]=(e[_]+a[3])/s[3]);return l==="RGBA"?new We("float32",d,[1,4,i,n]):new We("float32",d,[1,3,i,n])},Ke=async(e,t)=>{let i=typeof HTMLImageElement<"u"&&e instanceof HTMLImageElement,n=typeof ImageData<"u"&&e instanceof ImageData,r=typeof ImageBitmap<"u"&&e instanceof ImageBitmap,s=typeof e=="string",a,o=t??{},l=()=>{if(typeof document<"u")return document.createElement("canvas");if(typeof OffscreenCanvas<"u")return new OffscreenCanvas(1,1);throw new Error("Canvas is not supported")},u=d=>typeof HTMLCanvasElement<"u"&&d instanceof HTMLCanvasElement||d instanceof OffscreenCanvas?d.getContext("2d"):null;if(i){let d=l();d.width=e.width,d.height=e.height;let c=u(d);if(c!=null){let p=e.height,h=e.width;if(t!==void 0&&t.resizedHeight!==void 0&&t.resizedWidth!==void 0&&(p=t.resizedHeight,h=t.resizedWidth),t!==void 0){if(o=t,t.tensorFormat!==void 0)throw new Error("Image input config format must be RGBA for HTMLImageElement");o.tensorFormat="RGBA",o.height=p,o.width=h}else o.tensorFormat="RGBA",o.height=p,o.width=h;c.drawImage(e,0,0),a=c.getImageData(0,0,h,p).data}else throw new Error("Can not access image data")}else if(n){let d,c;if(t!==void 0&&t.resizedWidth!==void 0&&t.resizedHeight!==void 0?(d=t.resizedHeight,c=t.resizedWidth):(d=e.height,c=e.width),t!==void 0&&(o=t),o.format="RGBA",o.height=d,o.width=c,t!==void 0){let p=l();p.width=c,p.height=d;let h=u(p);if(h!=null)h.putImageData(e,0,0),a=h.getImageData(0,0,c,d).data;else throw new Error("Can not access image data")}else a=e.data}else if(r){if(t===void 0)throw new Error("Please provide image config with format for Imagebitmap");let d=l();d.width=e.width,d.height=e.height;let c=u(d);if(c!=null){let p=e.height,h=e.width;return c.drawImage(e,0,0,h,p),a=c.getImageData(0,0,h,p).data,o.height=p,o.width=h,Ie(a,o)}else throw new Error("Can not access image data")}else{if(s)return new Promise((d,c)=>{let p=l(),h=u(p);if(!e||!h)return c();let m=new Image;m.crossOrigin="Anonymous",m.src=e,m.onload=()=>{p.width=m.width,p.height=m.height,h.drawImage(m,0,0,p.width,p.height);let _=h.getImageData(0,0,p.width,p.height);o.height=p.height,o.width=p.width,d(Ie(_.data,o))}});throw new Error("Input data provided is not supported - aborted tensor creation")}if(a!==void 0)return Ie(a,o);throw new Error("Input data provided is not supported - aborted tensor creation")},Ne=(e,t)=>{let{width:i,height:n,download:r,dispose:s}=t,a=[1,n,i,4];return new We({location:"texture",type:"float32",texture:e,dims:a,download:r,dispose:s})},Ye=(e,t)=>{let{dataType:i,dims:n,download:r,dispose:s}=t;return new We({location:"gpu-buffer",type:i??"float32",gpuBuffer:e,dims:n,download:r,dispose:s})},tt=(e,t)=>{let{dataType:i,dims:n,download:r,dispose:s}=t;return new We({location:"ml-tensor",type:i??"float32",mlTensor:e,dims:n,download:r,dispose:s})},Je=(e,t,i)=>new We({location:"cpu-pinned",type:e,data:t,dims:i??[t.length]})}),Ve,Xe,dt,ct,_t=E(()=>{Ve=new Map([["float32",Float32Array],["uint8",Uint8Array],["int8",Int8Array],["uint16",Uint16Array],["int16",Int16Array],["int32",Int32Array],["bool",Uint8Array],["float64",Float64Array],["uint32",Uint32Array],["int4",Uint8Array],["uint4",Uint8Array]]),Xe=new Map([[Float32Array,"float32"],[Uint8Array,"uint8"],[Int8Array,"int8"],[Uint16Array,"uint16"],[Int16Array,"int16"],[Int32Array,"int32"],[Float64Array,"float64"],[Uint32Array,"uint32"]]),dt=!1,ct=()=>{if(!dt){dt=!0;let e=typeof BigInt64Array<"u"&&BigInt64Array.from,t=typeof BigUint64Array<"u"&&BigUint64Array.from,i=globalThis.Float16Array,n=typeof i<"u"&&i.from;e&&(Ve.set("int64",BigInt64Array),Xe.set(BigInt64Array,"int64")),t&&(Ve.set("uint64",BigUint64Array),Xe.set(BigUint64Array,"uint64")),n?(Ve.set("float16",i),Xe.set(i,"float16")):Ve.set("float16",Uint16Array)}}}),Re,st,Tt=E(()=>{zt(),Re=e=>{let t=1;for(let i=0;i<e.length;i++){let n=e[i];if(typeof n!="number"||!Number.isSafeInteger(n))throw new TypeError(`dims[${i}] must be an integer, got: ${n}`);if(n<0)throw new RangeError(`dims[${i}] must be a non-negative integer, got: ${n}`);t*=n}return t},st=(e,t)=>{switch(e.location){case"cpu":return new We(e.type,e.data,t);case"cpu-pinned":return new We({location:"cpu-pinned",data:e.data,type:e.type,dims:t});case"texture":return new We({location:"texture",texture:e.texture,type:e.type,dims:t});case"gpu-buffer":return new We({location:"gpu-buffer",gpuBuffer:e.gpuBuffer,type:e.type,dims:t});case"ml-tensor":return new We({location:"ml-tensor",mlTensor:e.mlTensor,type:e.type,dims:t});default:throw new Error(`tensorReshape: tensor location ${e.location} is not supported`)}}}),We,zt=E(()=>{Ee(),Me(),_t(),Tt(),We=class{constructor(e,t,i){ct();let n,r;if(typeof e=="object"&&"location"in e)switch(this.dataLocation=e.location,n=e.type,r=e.dims,e.location){case"cpu-pinned":{let a=Ve.get(n);if(!a)throw new TypeError(`unsupported type "${n}" to create tensor from pinned buffer`);if(!(e.data instanceof a))throw new TypeError(`buffer should be of type ${a.name}`);this.cpuData=e.data;break}case"texture":{if(n!=="float32")throw new TypeError(`unsupported type "${n}" to create tensor from texture`);this.gpuTextureData=e.texture,this.downloader=e.download,this.disposer=e.dispose;break}case"gpu-buffer":{if(n!=="float32"&&n!=="float16"&&n!=="int32"&&n!=="int64"&&n!=="uint32"&&n!=="uint8"&&n!=="bool"&&n!=="uint4"&&n!=="int4")throw new TypeError(`unsupported type "${n}" to create tensor from gpu buffer`);this.gpuBufferData=e.gpuBuffer,this.downloader=e.download,this.disposer=e.dispose;break}case"ml-tensor":{if(n!=="float32"&&n!=="float16"&&n!=="int32"&&n!=="int64"&&n!=="uint32"&&n!=="uint64"&&n!=="int8"&&n!=="uint8"&&n!=="bool"&&n!=="uint4"&&n!=="int4")throw new TypeError(`unsupported type "${n}" to create tensor from MLTensor`);this.mlTensorData=e.mlTensor,this.downloader=e.download,this.disposer=e.dispose;break}default:throw new Error(`Tensor constructor: unsupported location '${this.dataLocation}'`)}else{let a,o;if(typeof e=="string")if(n=e,o=i,e==="string"){if(!Array.isArray(t))throw new TypeError("A string tensor's data must be a string array.");a=t}else{let l=Ve.get(e);if(l===void 0)throw new TypeError(`Unsupported tensor type: ${e}.`);if(Array.isArray(t)){if(e==="float16"&&l===Uint16Array||e==="uint4"||e==="int4")throw new TypeError(`Creating a ${e} tensor from number array is not supported. Please use ${l.name} as data.`);e==="uint64"||e==="int64"?a=l.from(t,BigInt):a=l.from(t)}else if(t instanceof l)a=t;else if(t instanceof Uint8ClampedArray)if(e==="uint8")a=Uint8Array.from(t);else throw new TypeError("A Uint8ClampedArray tensor's data must be type of uint8");else if(e==="float16"&&t instanceof Uint16Array&&l!==Uint16Array)a=new globalThis.Float16Array(t.buffer,t.byteOffset,t.length);else throw new TypeError(`A ${n} tensor's data must be type of ${l}`)}else if(o=t,Array.isArray(e)){if(e.length===0)throw new TypeError("Tensor type cannot be inferred from an empty array.");let l=typeof e[0];if(l==="string")n="string",a=e;else if(l==="boolean")n="bool",a=Uint8Array.from(e);else throw new TypeError(`Invalid element type of data array: ${l}.`)}else if(e instanceof Uint8ClampedArray)n="uint8",a=Uint8Array.from(e);else{let l=Xe.get(e.constructor);if(l===void 0)throw new TypeError(`Unsupported type for tensor data: ${e.constructor}.`);n=l,a=e}if(o===void 0)o=[a.length];else if(!Array.isArray(o))throw new TypeError("A tensor's dims must be a number array");r=o,this.cpuData=a,this.dataLocation="cpu"}let s=Re(r);if(this.cpuData&&s!==this.cpuData.length&&!((n==="uint4"||n==="int4")&&Math.ceil(s/2)===this.cpuData.length))throw new Error(`Tensor's size(${s}) does not match data length(${this.cpuData.length}).`);this.type=n,this.dims=r,this.size=s}static async fromImage(e,t){return Ke(e,t)}static fromTexture(e,t){return Ne(e,t)}static fromGpuBuffer(e,t){return Ye(e,t)}static fromMLTensor(e,t){return tt(e,t)}static fromPinnedBuffer(e,t,i){return Je(e,t,i)}toDataURL(e){return ce(this,e)}toImageData(e){return ze(this,e)}get data(){if(this.ensureValid(),!this.cpuData)throw new Error("The data is not on CPU. Use `getData()` to download GPU data to CPU, or use `texture` or `gpuBuffer` property to access the GPU data directly.");return this.cpuData}get location(){return this.dataLocation}get texture(){if(this.ensureValid(),!this.gpuTextureData)throw new Error("The data is not stored as a WebGL texture.");return this.gpuTextureData}get gpuBuffer(){if(this.ensureValid(),!this.gpuBufferData)throw new Error("The data is not stored as a WebGPU buffer.");return this.gpuBufferData}get mlTensor(){if(this.ensureValid(),!this.mlTensorData)throw new Error("The data is not stored as a WebNN MLTensor.");return this.mlTensorData}async getData(e){switch(this.ensureValid(),this.dataLocation){case"cpu":case"cpu-pinned":return this.data;case"texture":case"gpu-buffer":case"ml-tensor":{if(!this.downloader)throw new Error("The current tensor is not created with a specified data downloader.");if(this.isDownloading)throw new Error("The current tensor is being downloaded.");try{this.isDownloading=!0;let t=await this.downloader();return this.downloader=void 0,this.dataLocation="cpu",this.cpuData=t,e&&this.disposer&&(this.disposer(),this.disposer=void 0),t}finally{this.isDownloading=!1}}default:throw new Error(`cannot get data from location: ${this.dataLocation}`)}}dispose(){if(this.isDownloading)throw new Error("The current tensor is being downloaded.");this.disposer&&(this.disposer(),this.disposer=void 0),this.cpuData=void 0,this.gpuTextureData=void 0,this.gpuBufferData=void 0,this.mlTensorData=void 0,this.downloader=void 0,this.isDownloading=void 0,this.dataLocation="none"}ensureValid(){if(this.dataLocation==="none")throw new Error("The tensor is disposed.")}reshape(e){if(this.ensureValid(),this.downloader||this.disposer)throw new Error("Cannot reshape a tensor that owns GPU resource.");return st(this,e)}}}),at,yt=E(()=>{zt(),at=We}),Te,L,K,he,ye,Ce,lt=E(()=>{W(),Te=(e,t)=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||console.timeStamp(`${e}::ORT::${t}`)},L=(e,t)=>{let i=new Error().stack?.split(/\r\n|\r|\n/g)||[],n=!1;for(let r=0;r<i.length;r++){if(n&&!i[r].includes("TRACE_FUNC")){let s=`FUNC_${e}::${i[r].trim().split(" ")[1]}`;t&&(s+=`::${t}`),Te("CPU",s);return}i[r].includes("TRACE_FUNC")&&(n=!0)}},K=e=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||L("BEGIN",e)},he=e=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||L("END",e)},ye=e=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||console.time(`ORT::${e}`)},Ce=e=>{(typeof V.trace>"u"?!V.wasm.trace:!V.trace)||console.timeEnd(`ORT::${e}`)}}),wt,Ut=E(()=>{te(),yt(),lt(),wt=class rp{constructor(t){this.handler=t}async run(t,i,n){K(),ye("InferenceSession.run");let r={},s={};if(typeof t!="object"||t===null||t instanceof at||Array.isArray(t))throw new TypeError("'feeds' must be an object that use input names as keys and OnnxValue as corresponding values.");let a=!0;if(typeof i=="object"){if(i===null)throw new TypeError("Unexpected argument[1]: cannot be null.");if(i instanceof at)throw new TypeError("'fetches' cannot be a Tensor");if(Array.isArray(i)){if(i.length===0)throw new TypeError("'fetches' cannot be an empty array.");a=!1;for(let u of i){if(typeof u!="string")throw new TypeError("'fetches' must be a string array or an object.");if(this.outputNames.indexOf(u)===-1)throw new RangeError(`'fetches' contains invalid output name: ${u}.`);r[u]=null}if(typeof n=="object"&&n!==null)s=n;else if(typeof n<"u")throw new TypeError("'options' must be an object.")}else{let u=!1,d=Object.getOwnPropertyNames(i);for(let c of this.outputNames)if(d.indexOf(c)!==-1){let p=i[c];(p===null||p instanceof at)&&(u=!0,a=!1,r[c]=p)}if(u){if(typeof n=="object"&&n!==null)s=n;else if(typeof n<"u")throw new TypeError("'options' must be an object.")}else s=i}}else if(typeof i<"u")throw new TypeError("Unexpected argument[1]: must be 'fetches' or 'options'.");for(let u of this.inputNames)if(typeof t[u]>"u")throw new Error(`input '${u}' is missing in 'feeds'.`);if(a)for(let u of this.outputNames)r[u]=null;let o=await this.handler.run(t,r,s),l={};for(let u in o)if(Object.hasOwnProperty.call(o,u)){let d=o[u];d instanceof at?l[u]=d:l[u]=new at(d.type,d.data,d.dims)}return Ce("InferenceSession.run"),he(),l}async release(){return this.handler.dispose()}static async create(t,i,n,r){K(),ye("InferenceSession.create");let s,a={};if(typeof t=="string"){if(s=t,typeof i=="object"&&i!==null)a=i;else if(typeof i<"u")throw new TypeError("'options' must be an object.")}else if(t instanceof Uint8Array){if(s=t,typeof i=="object"&&i!==null)a=i;else if(typeof i<"u")throw new TypeError("'options' must be an object.")}else if(t instanceof ArrayBuffer||typeof SharedArrayBuffer<"u"&&t instanceof SharedArrayBuffer){let d=t,c=0,p=t.byteLength;if(typeof i=="object"&&i!==null)a=i;else if(typeof i=="number"){if(c=i,!Number.isSafeInteger(c))throw new RangeError("'byteOffset' must be an integer.");if(c<0||c>=d.byteLength)throw new RangeError(`'byteOffset' is out of range [0, ${d.byteLength}).`);if(p=t.byteLength-c,typeof n=="number"){if(p=n,!Number.isSafeInteger(p))throw new RangeError("'byteLength' must be an integer.");if(p<=0||c+p>d.byteLength)throw new RangeError(`'byteLength' is out of range (0, ${d.byteLength-c}].`);if(typeof r=="object"&&r!==null)a=r;else if(typeof r<"u")throw new TypeError("'options' must be an object.")}else if(typeof n<"u")throw new TypeError("'byteLength' must be a number.")}else if(typeof i<"u")throw new TypeError("'options' must be an object.");s=new Uint8Array(d,c,p)}else throw new TypeError("Unexpected argument[0]: must be 'path' or 'buffer'.");let[o,l]=await H(a),u=await o.createInferenceSessionHandler(s,l);return Ce("InferenceSession.create"),he(),new rp(u)}startProfiling(){this.handler.startProfiling()}endProfiling(){this.handler.endProfiling()}get inputNames(){return this.handler.inputNames}get outputNames(){return this.handler.outputNames}get inputMetadata(){return this.handler.inputMetadata}get outputMetadata(){return this.handler.outputMetadata}}}),ht,Mt=E(()=>{Ut(),ht=wt}),qe=E(()=>{}),Rt=E(()=>{}),pi=E(()=>{}),ni=E(()=>{}),ri={};X(ri,{InferenceSession:()=>ht,TRACE:()=>Te,TRACE_EVENT_BEGIN:()=>ye,TRACE_EVENT_END:()=>Ce,TRACE_FUNC_BEGIN:()=>K,TRACE_FUNC_END:()=>he,Tensor:()=>at,env:()=>se,registerBackend:()=>N});var mt=E(()=>{M(),we(),Mt(),yt(),qe(),Rt(),lt(),pi(),ni()}),an=E(()=>{}),Zr={};X(Zr,{default:()=>Qr});var on,ln,Qr,hp=E(()=>{Ec(),qt(),fn(),on="ort-wasm-proxy-worker",ln=globalThis.self?.name===on,ln&&(self.onmessage=e=>{let{type:t,in:i}=e.data;try{switch(t){case"init-wasm":gn(i.wasm).then(()=>{Er(i).then(()=>{postMessage({type:t})},n=>{postMessage({type:t,err:n})})},n=>{postMessage({type:t,err:n})});break;case"init-ep":{let{epName:n,env:r}=i;Cr(r,n).then(()=>{postMessage({type:t})},s=>{postMessage({type:t,err:s})});break}case"copy-from":{let{buffer:n}=i,r=Qi(n);postMessage({type:t,out:r});break}case"create":{let{model:n,options:r}=i;Ar(n,r).then(s=>{postMessage({type:t,out:s})},s=>{postMessage({type:t,err:s})});break}case"release":zr(i),postMessage({type:t});break;case"run":{let{sessionId:n,inputIndices:r,inputs:s,outputIndices:a,options:o}=i;Rr(n,r,s,a,new Array(a.length).fill(null),o).then(l=>{l.some(u=>u[3]!=="cpu")?postMessage({type:t,err:"Proxy does not support non-cpu tensor location."}):postMessage({type:t,out:l},Dr([...s,...l]))},l=>{postMessage({type:t,err:l})});break}case"end-profiling":Or(i),postMessage({type:t});break;default:}}catch(n){postMessage({type:t,err:n})}}),Qr=ln?null:e=>new Worker(e??pt,{type:"classic",name:on})}),Xr,Yr,pt,un,Mi,Jr,es,dn,ts,cn,is,pn,ns,fn=E(()=>{an(),Xr=typeof location>"u"?void 0:location.origin,Yr=()=>typeof document<"u"?document.currentScript?.src:typeof self<"u"?self.location?.href:void 0,pt=Yr(),un=()=>{if(pt&&!pt.startsWith("blob:"))return pt.substring(0,pt.lastIndexOf("/")+1)},Mi=(e,t)=>{try{let i=t??pt;return(i?new URL(e,i):new URL(e)).origin===Xr}catch{return!1}},Jr=(e,t)=>{let i=t??pt;try{return(i?new URL(e,i):new URL(e)).href}catch{return}},es=(e,t)=>`${t??"./"}${e}`,dn=async e=>{let t=await(await fetch(e,{credentials:"same-origin"})).blob();return URL.createObjectURL(t)},ts=async e=>(await import(e)).default,cn=(hp(),ee(Zr)).default,is=async()=>{if(!pt)throw new Error("Failed to load proxy worker: cannot determine the script source URL.");if(Mi(pt))return[void 0,cn()];let e=await dn(pt);return[e,cn(e)]},pn=void 0,ns=async(e,t,i,n)=>{let r=pn&&!(e||t);if(r)if(pt)r=Mi(pt);else if(n&&!i)r=!0;else throw new Error("cannot determine the script source URL.");if(r)return[void 0,pn];{let s="ort-wasm-simd-threaded.jsep.mjs",a=e??Jr(s,t),o=i&&a&&!Mi(a,t),l=o?await dn(a):a??es(s,t);return[o?l:void 0,await ts(l)]}}}),hn,Ri,fi,mn,rs,ss,as,gn,Le,qt=E(()=>{fn(),Ri=!1,fi=!1,mn=!1,rs=()=>{if(typeof SharedArrayBuffer>"u")return!1;try{return typeof MessageChannel<"u"&&new MessageChannel().port1.postMessage(new SharedArrayBuffer(1)),WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,4,1,96,0,0,3,2,1,0,5,4,1,3,1,1,10,11,1,9,0,65,0,254,16,2,0,26,11]))}catch{return!1}},ss=()=>{try{return WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,4,1,96,0,0,3,2,1,0,10,30,1,28,0,65,0,253,15,253,12,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,253,186,1,26,11]))}catch{return!1}},as=()=>{try{return WebAssembly.validate(new Uint8Array([0,97,115,109,1,0,0,0,1,5,1,96,0,1,123,3,2,1,0,10,19,1,17,0,65,1,253,15,65,2,253,15,65,3,253,15,253,147,2,11]))}catch{return!1}},gn=async e=>{if(Ri)return Promise.resolve();if(fi)throw new Error("multiple calls to 'initializeWebAssembly()' detected.");if(mn)throw new Error("previous call to 'initializeWebAssembly()' failed.");fi=!0;let t=e.initTimeout,i=e.numThreads;if(e.simd!==!1){if(e.simd==="relaxed"){if(!as())throw new Error("Relaxed WebAssembly SIMD is not supported in the current environment.")}else if(!ss())throw new Error("WebAssembly SIMD is not supported in the current environment.")}let n=rs();i>1&&!n&&(typeof self<"u"&&!self.crossOriginIsolated&&console.warn("env.wasm.numThreads is set to "+i+", but this will not work unless you enable crossOriginIsolated mode. See https://web.dev/cross-origin-isolation-guide/ for more info."),console.warn("WebAssembly multi-threading is not supported in the current environment. Falling back to single-threading."),e.numThreads=i=1);let r=e.wasmPaths,s=typeof r=="string"?r:void 0,a=r?.mjs,o=a?.href??a,l=r?.wasm,u=l?.href??l,d=e.wasmBinary,[c,p]=await ns(o,s,i>1,!!d||!!u),h=!1,m=[];if(t>0&&m.push(new Promise(_=>{setTimeout(()=>{h=!0,_()},t)})),m.push(new Promise((_,$)=>{let y={numThreads:i};if(d)y.wasmBinary=d;else if(u||s)y.locateFile=g=>u??s+g;else if(o&&o.indexOf("blob:")!==0)y.locateFile=g=>new URL(g,o).href;else if(c){let g=un();g&&(y.locateFile=T=>g+T)}p(y).then(g=>{fi=!1,Ri=!0,hn=g,_(),c&&URL.revokeObjectURL(c)},g=>{fi=!1,mn=!0,$(g)})})),await Promise.race(m),h)throw new Error(`WebAssembly backend initializing failed due to timeout: ${t}ms`)},Le=()=>{if(Ri&&hn)return hn;throw new Error("WebAssembly is not initialized yet.")}}),bt,Oi,Fe,_n=E(()=>{qt(),bt=(e,t)=>{let i=Le(),n=i.lengthBytesUTF8(e)+1,r=i._malloc(n);return i.stringToUTF8(e,r,n),t.push(r),r},Oi=(e,t,i,n)=>{if(typeof e=="object"&&e!==null){if(i.has(e))throw new Error("Circular reference in options");i.add(e)}Object.entries(e).forEach(([r,s])=>{let a=t?t+r:r;if(typeof s=="object")Oi(s,a+".",i,n);else if(typeof s=="string"||typeof s=="number")n(a,s.toString());else if(typeof s=="boolean")n(a,s?"1":"0");else throw new Error(`Can't handle extra config type: ${typeof s}`)})},Fe=e=>{let t=Le(),i=t.stackSave();try{let n=t.PTR_SIZE,r=t.stackAlloc(2*n);t._OrtGetLastError(r,r+n);let s=Number(t.getValue(r,n===4?"i32":"i64")),a=t.getValue(r+n,"*"),o=a?t.UTF8ToString(a):"";throw new Error(`${e} ERROR_CODE: ${s}, ERROR_MESSAGE: ${o}`)}finally{t.stackRestore(i)}}}),os,mp=E(()=>{qt(),_n(),os=e=>{let t=Le(),i=0,n=[],r=e||{};try{if(e?.logSeverityLevel===void 0)r.logSeverityLevel=2;else if(typeof e.logSeverityLevel!="number"||!Number.isInteger(e.logSeverityLevel)||e.logSeverityLevel<0||e.logSeverityLevel>4)throw new Error(`log severity level is not valid: ${e.logSeverityLevel}`);if(e?.logVerbosityLevel===void 0)r.logVerbosityLevel=0;else if(typeof e.logVerbosityLevel!="number"||!Number.isInteger(e.logVerbosityLevel))throw new Error(`log verbosity level is not valid: ${e.logVerbosityLevel}`);e?.terminate===void 0&&(r.terminate=!1);let s=0;return e?.tag!==void 0&&(s=bt(e.tag,n)),i=t._OrtCreateRunOptions(r.logSeverityLevel,r.logVerbosityLevel,!!r.terminate,s),i===0&&Fe("Can't create run options."),e?.extra!==void 0&&Oi(e.extra,"",new WeakSet,(a,o)=>{let l=bt(a,n),u=bt(o,n);t._OrtAddRunConfigEntry(i,l,u)!==0&&Fe(`Can't set a run config entry: ${a} - ${o}.`)}),[i,n]}catch(s){throw i!==0&&t._OrtReleaseRunOptions(i),n.forEach(a=>t._free(a)),s}}}),ls,us,ds,hi,cs,ps,gp=E(()=>{qt(),_n(),ls=e=>{switch(e){case"disabled":return 0;case"basic":return 1;case"extended":return 2;case"layout":return 3;case"all":return 99;default:throw new Error(`unsupported graph optimization level: ${e}`)}},us=e=>{switch(e){case"sequential":return 0;case"parallel":return 1;default:throw new Error(`unsupported execution mode: ${e}`)}},ds=e=>{e.extra||(e.extra={}),e.extra.session||(e.extra.session={});let t=e.extra.session;t.use_ort_model_bytes_directly||(t.use_ort_model_bytes_directly="1"),e.executionProviders&&e.executionProviders.some(i=>(typeof i=="string"?i:i.name)==="webgpu")&&(e.enableMemPattern=!1)},hi=(e,t,i,n)=>{let r=bt(t,n),s=bt(i,n);Le()._OrtAddSessionConfigEntry(e,r,s)!==0&&Fe(`Can't set a session config entry: ${t} - ${i}.`)},cs=async(e,t,i)=>{for(let n of t){let r=typeof n=="string"?n:n.name,s=[];switch(r){case"webnn":if(r="WEBNN",typeof n!="string"){let d=n?.deviceType;d&&hi(e,"deviceType",d,i)}break;case"webgpu":if(r="JS",typeof n!="string"){let d=n;if(d?.preferredLayout){if(d.preferredLayout!=="NCHW"&&d.preferredLayout!=="NHWC")throw new Error(`preferredLayout must be either 'NCHW' or 'NHWC': ${d.preferredLayout}`);hi(e,"preferredLayout",d.preferredLayout,i)}}break;case"wasm":case"cpu":continue;default:throw new Error(`not supported execution provider: ${r}`)}let a=bt(r,i),o=s.length,l=0,u=0;if(o>0){l=Le()._malloc(o*Le().PTR_SIZE),i.push(l),u=Le()._malloc(o*Le().PTR_SIZE),i.push(u);for(let d=0;d<o;d++)Le().setValue(l+d*Le().PTR_SIZE,s[d][0],"*"),Le().setValue(u+d*Le().PTR_SIZE,s[d][1],"*")}await Le()._OrtAppendExecutionProvider(e,a,l,u,o)!==0&&Fe(`Can't append execution provider: ${r}.`)}},ps=async e=>{let t=Le(),i=0,n=[],r=e||{};ds(r);try{let s=ls(r.graphOptimizationLevel??"all"),a=us(r.executionMode??"sequential"),o=typeof r.logId=="string"?bt(r.logId,n):0,l=r.logSeverityLevel??2;if(!Number.isInteger(l)||l<0||l>4)throw new Error(`log severity level is not valid: ${l}`);let u=r.logVerbosityLevel??0;if(!Number.isInteger(u)||u<0||u>4)throw new Error(`log verbosity level is not valid: ${u}`);let d=typeof r.optimizedModelFilePath=="string"?bt(r.optimizedModelFilePath,n):0;if(i=t._OrtCreateSessionOptions(s,!!r.enableCpuMemArena,!!r.enableMemPattern,a,!!r.enableProfiling,0,o,l,u,d),i===0&&Fe("Can't create session options."),r.executionProviders&&await cs(i,r.executionProviders,n),r.enableGraphCapture!==void 0){if(typeof r.enableGraphCapture!="boolean")throw new Error(`enableGraphCapture must be a boolean value: ${r.enableGraphCapture}`);hi(i,"enableGraphCapture",r.enableGraphCapture.toString(),n)}if(r.freeDimensionOverrides)for(let[c,p]of Object.entries(r.freeDimensionOverrides)){if(typeof c!="string")throw new Error(`free dimension override name must be a string: ${c}`);if(typeof p!="number"||!Number.isInteger(p)||p<0)throw new Error(`free dimension override value must be a non-negative integer: ${p}`);let h=bt(c,n);t._OrtAddFreeDimensionOverride(i,h,p)!==0&&Fe(`Can't set a free dimension override: ${c} - ${p}.`)}return r.extra!==void 0&&Oi(r.extra,"",new WeakSet,(c,p)=>{hi(i,c,p,n)}),[i,n]}catch(s){throw i!==0&&t._OrtReleaseSessionOptions(i)!==0&&Fe("Can't release session options."),n.forEach(a=>t._free(a)),s}}}),Wt,Ot,Gt,Di,Bi,yn,wn,bn,ge=E(()=>{Wt=e=>{switch(e){case"int8":return 3;case"uint8":return 2;case"bool":return 9;case"int16":return 5;case"uint16":return 4;case"int32":return 6;case"uint32":return 12;case"float16":return 10;case"float32":return 1;case"float64":return 11;case"string":return 8;case"int64":return 7;case"uint64":return 13;case"int4":return 22;case"uint4":return 21;default:throw new Error(`unsupported data type: ${e}`)}},Ot=e=>{switch(e){case 3:return"int8";case 2:return"uint8";case 9:return"bool";case 5:return"int16";case 4:return"uint16";case 6:return"int32";case 12:return"uint32";case 10:return"float16";case 1:return"float32";case 11:return"float64";case 8:return"string";case 7:return"int64";case 13:return"uint64";case 22:return"int4";case 21:return"uint4";default:throw new Error(`unsupported data type: ${e}`)}},Gt=(e,t)=>{let i=[-1,4,1,1,2,2,4,8,-1,1,2,8,4,8,-1,-1,-1,-1,-1,-1,-1,.5,.5][e],n=typeof t=="number"?t:t.reduce((r,s)=>r*s,1);return i>0?Math.ceil(n*i):void 0},Di=e=>{switch(e){case"float16":return typeof Float16Array<"u"&&Float16Array.from?Float16Array:Uint16Array;case"float32":return Float32Array;case"uint8":return Uint8Array;case"int8":return Int8Array;case"uint16":return Uint16Array;case"int16":return Int16Array;case"int32":return Int32Array;case"bool":return Uint8Array;case"float64":return Float64Array;case"uint32":return Uint32Array;case"int64":return BigInt64Array;case"uint64":return BigUint64Array;default:throw new Error(`unsupported type: ${e}`)}},Bi=e=>{switch(e){case"verbose":return 0;case"info":return 1;case"warning":return 2;case"error":return 3;case"fatal":return 4;default:throw new Error(`unsupported logging level: ${e}`)}},yn=e=>e==="float32"||e==="float16"||e==="int32"||e==="int64"||e==="uint32"||e==="uint8"||e==="bool"||e==="uint4"||e==="int4",wn=e=>e==="float32"||e==="float16"||e==="int32"||e==="int64"||e==="uint32"||e==="uint64"||e==="int8"||e==="uint8"||e==="bool"||e==="uint4"||e==="int4",bn=e=>{switch(e){case"none":return 0;case"cpu":return 1;case"cpu-pinned":return 2;case"texture":return 3;case"gpu-buffer":return 4;case"ml-tensor":return 5;default:throw new Error(`unsupported data location: ${e}`)}}}),vn,fs=E(()=>{an(),vn=async e=>{if(typeof e=="string"){let t=await fetch(e);if(!t.ok)throw new Error(`failed to load external data file: ${e}`);let i=t.headers.get("Content-Length"),n=i?parseInt(i,10):0;if(n<1073741824)return new Uint8Array(await t.arrayBuffer());{if(!t.body)throw new Error(`failed to load external data file: ${e}, no response body.`);let r=t.body.getReader(),s;try{s=new ArrayBuffer(n)}catch(o){if(o instanceof RangeError){let l=Math.ceil(n/65536);s=new WebAssembly.Memory({initial:l,maximum:l}).buffer}else throw o}let a=0;for(;;){let{done:o,value:l}=await r.read();if(o)break;let u=l.byteLength;new Uint8Array(s,a,u).set(l),a+=u}return new Uint8Array(s,0,n)}}else return e instanceof Blob?new Uint8Array(await e.arrayBuffer()):e instanceof Uint8Array?e:new Uint8Array(e)}}),hs,ms,gs,_s,$n,ys,Ae,Dt=E(()=>{ge(),hs=["V","I","W","E","F"],ms=(e,t)=>{console.log(`[${hs[e]},${new Date().toISOString()}]${t}`)},$n=(e,t)=>{gs=e,_s=t},ys=(e,t)=>{let i=Bi(e),n=Bi(gs);i>=n&&ms(i,typeof t=="function"?t():t)},Ae=(...e)=>{_s&&ys(...e)}}),ws,si,O,Fi,bs,vs,$s,$e=E(()=>{ws=class{static calcMatMulShape(e,t){return e[1]!==t[0]?void 0:[e[0],t[1]]}},si=class{static calcShape(e,t,i=!1){let n=e.length,r=t.length;if(n===0)return t;if(r===0)return e;let s=Math.max(e.length,t.length),a=new Array(s);if(i){if(n<2||r<2)return;let o=ws.calcMatMulShape([e[n-2],e[n-1]],[t[r-2],t[r-1]]);if(o===void 0)return;[a[s-2],a[s-1]]=o}for(let o=i?3:1;o<=s;o++){let l=n-o<0?1:e[n-o],u=r-o<0?1:t[r-o];if(l!==u&&l>1&&u>1)return;let d=Math.max(l,u);if(l&&u)a[s-o]=Math.max(l,u);else{if(d>1)return;a[s-o]=0}}return a}static isValidBroadcast(e,t){let i=e.length,n=t.length;if(i>n)return!1;for(let r=1;r<=i;r++)if(e[i-r]!==1&&e[i-r]!==t[n-r])return!1;return!0}},O=class tn{static size(t){return tn.getSizeFromDimensionRange(t,0,t.length)}static convertShape(t,i=4){let n=t.length;if(n===0)return[];let r=new Array(n),s=n-1;for(;s>=0;){if(t[s]%i===0){r[s]=t[s]/i;break}if(i%t[s]!==0)throw new Error("cannot convert shape");r[s]=1,i/=t[s],s--}for(s--;s>=0;s--)r[s]=t[s];return r}static sizeFromDimension(t,i){if(i<0||i>t.length)throw new Error(`invalid dimension of ${i} for sizeFromDimension as Tensor has ${t.length} dimensions.`);return tn.getSizeFromDimensionRange(t,i,t.length)}static sizeToDimension(t,i){if(i<0||i>t.length)throw new Error(`invalid dimension of ${i} for sizeToDimension as Tensor has ${t.length} dimensions.`);return tn.getSizeFromDimensionRange(t,0,i)}static getSizeFromDimensionRange(t,i,n){let r=1;for(let s=i;s<n;s++){if(t[s]<0)throw new Error("cannot get valid size from specified dimension range. Most likely the range contains negative values in them.");r*=Number(t[s])}return r}static computeStrides(t){let i=t.length;if(i===0)return[];if(i===1)return[1];let n=new Array(i);n[i-1]=1,n[i-2]=t[i-1];for(let r=i-3;r>=0;--r)n[r]=n[r+1]*t[r+1];return n}static normalizeAxis(t,i){if(t<-i&&t>=i)throw new Error("unsupported axis for this operation.");return t<0?t+i:t}static normalizeAxes(t,i){return t.map(n=>this.normalizeAxis(n,i??t.length))}static sortBasedOnPerm(t,i){return i?i.map(n=>t[n]):t.slice().reverse()}static padShape(t,i){let n=t.length;return t.map((r,s)=>r+i[s]+i[s+n])}static areEqual(t,i){return t.length!==i.length?!1:t.every((n,r)=>n===i[r])}},Fi=class Ii{static adjustPoolAttributes(t,i,n,r,s,a){if(!t&&n.length!==i.length-2)throw new Error("length of specified kernel shapes should be 2 less than length of input dimensions");if(t)for(let o=0;o<i.length-2;o++)o>=n.length?n.push(i[o+2]):n[o]=i[o+2];for(let o=0;o<n.length;o++)if(o<r.length){if(r[o]<0)throw new Error("strides should be greater than or equal to 1")}else r.push(1);for(let o=0;o<n.length;o++)if(o<s.length){if(s[o]<0)throw new Error("dilations should be greater than or equal to 1")}else s.push(1);for(let o=0;o<n.length*2;o++)if(o<a.length){if(a[o]<0)throw new Error("pad should be greater than or equal to 1")}else a.push(0);for(let o=0;o<n.length;o++){if(n[o]<=0)throw new Error("kernel shapes need to be greater than 0");if(a[o]>=n[o]||a[o+n.length]>=n[o])throw new Error("pads should be smaller than kernel")}}static adjustPadsBasedOnAutoPad(t,i,n,r,s,a,o){if(o){if(s.length!==2*(t.length-2))throw new Error("length of pads should be twice the length of data dimensions");if(i.length!==t.length-2)throw new Error("length of strides should be the length of data dimensions");if(r.length!==t.length-2)throw new Error("length of kernel shapes should be the length of data dimensions");for(let l=0;l<t.length-2;l++)Ii.adjustPadAndReturnShape(t[l+(a?1:2)],i[l],n[l],r[l],s,l,l+t.length-2,o)}}static computePoolOutputShape(t,i,n,r,s,a,o){if(i.length<=0)throw new Error("input shape must be of size greater than 0");let l=[i[0],i[1]];return Ii.computeShapeHelper(t,i,l,n,r,s,a,o),l}static computeConvOutputShape(t,i,n,r,s,a,o){if(t.length<=0||i.length<=0)throw new Error("invalid input tensor dims or invalid filter tensor dims");let l=[t[0],i[0]];return Ii.computeShapeHelper(!1,t,l,n,r,s,a,o),l}static computeShapeHelper(t,i,n,r,s,a,o,l){if(t)for(let u=0;u<i.length-2;u++)n.push(1);else for(let u=0;u<i.length-2;u++)n.push(Ii.adjustPadAndReturnShape(i[u+2],r[u],s[u],a[u],o,u,u+i.length-2,l))}static adjustPadAndReturnShape(t,i,n,r,s,a,o,l){let u=n*(r-1)+1;if(l&&l!=="NOTSET")switch(l){case"VALID":return s[a]=0,s[o]=0,Math.floor((t-u)/i+1);case"SAME_LOWER":case"SAME_UPPER":if(n!==1)throw new Error("Dilation not supported for SAME_UPPER or SAME_LOWER");{let d=((t+i-1)/i-1)*i+r-t;return s[a]=Math.floor(l==="SAME_LOWER"?(d+1)/2:d/2),s[o]=d-s[a],Math.floor((t+d-r)/i+1)}default:throw new Error("Unsupported AutoPad type")}else return Math.floor((t+s[a]+s[o]-u)/i+1)}},bs=class{static getShapeOfGemmResult(e,t,i,n,r){if(e.length!==2||i.length!==2)throw new Error("shape need to be of size 2");let s,a,o;t?(s=e[1],a=e[0]):(s=e[0],a=e[1]);let l=-1;if(n?(o=i[0],l=1):(o=i[1],l=0),i[l]!==a)throw new Error("dimension mismatch");if(s<=0||o<=0||a<=0)throw new Error("invalid shape specified");if(r&&!si.isValidBroadcast(r,[s,o]))throw new Error("gemm: invalid bias shape for broadcast");return[s,o,a]}},vs=-34028234663852886e22,$s=34028234663852886e22}),xn,xs=E(()=>{ge(),xn=(e,t)=>new(Di(t))(e)}),Sn,kn,Tn,Ss,En,ks,Cn,In,An,Ts,Es,_p=E(()=>{ge(),Dt(),Sn=new Map([["float32",32],["float16",16],["int32",32],["uint32",32],["int64",64],["uint64",64],["int8",8],["uint8",8],["int4",4],["uint4",4]]),kn=(e,t)=>{if(t==="int32")return e;let i=Sn.get(t);if(!i)throw new Error(`WebNN backend does not support data type: ${t}`);let n=i/8;if(e.byteLength%n!==0)throw new Error(`Invalid Uint8Array length - must be a multiple of ${n}.`);let r=e.byteLength/n,s=new(Di(t))(e.buffer,e.byteOffset,r);switch(t){case"int64":case"uint64":{let a=new Int32Array(r);for(let o=0;o<r;o++){let l=s[o];if(l>2147483647n||l<-2147483648n)throw new Error("Can not convert int64 data to int32 - value out of range.");a[o]=Number(l)}return new Uint8Array(a.buffer)}case"int8":case"uint8":case"uint32":{if(t==="uint32"&&s.some(o=>o>2147483647))throw new Error("Can not convert uint32 data to int32 - value out of range.");let a=Int32Array.from(s,Number);return new Uint8Array(a.buffer)}default:throw new Error(`Unsupported data conversion from ${t} to 'int32'`)}},Tn=(e,t)=>{if(t==="int32")return e;if(e.byteLength%4!==0)throw new Error("Invalid Uint8Array length - must be a multiple of 4 (int32).");let i=e.byteLength/4,n=new Int32Array(e.buffer,e.byteOffset,i);switch(t){case"int64":{let r=BigInt64Array.from(n,BigInt);return new Uint8Array(r.buffer)}case"uint64":{if(n.some(s=>s<0))throw new Error("Can not convert int32 data to uin64 - negative value found.");let r=BigUint64Array.from(n,BigInt);return new Uint8Array(r.buffer)}case"int8":{if(n.some(s=>s<-128||s>127))throw new Error("Can not convert int32 data to int8 - value out of range.");let r=Int8Array.from(n,Number);return new Uint8Array(r.buffer)}case"uint8":{if(n.some(r=>r<0||r>255))throw new Error("Can not convert int32 data to uint8 - value out of range.");return Uint8Array.from(n,Number)}case"uint32":{if(n.some(s=>s<0))throw new Error("Can not convert int32 data to uint32 - negative value found.");let r=Uint32Array.from(n,Number);return new Uint8Array(r.buffer)}default:throw new Error(`Unsupported data conversion from 'int32' to ${t}`)}},Ss=1,En=()=>Ss++,ks=new Map([["int8","int32"],["uint8","int32"],["uint32","int32"],["int64","int32"]]),Cn=(e,t)=>{let i=Sn.get(e);if(!i)throw new Error(`WebNN backend does not support data type: ${e}`);return t.length>0?Math.ceil(t.reduce((n,r)=>n*r)*i/8):0},In=class{constructor(e){this.isDataConverted=!1;let{sessionId:t,context:i,tensor:n,dataType:r,shape:s,fallbackDataType:a}=e;this.sessionId=t,this.mlContext=i,this.mlTensor=n,this.dataType=r,this.tensorShape=s,this.fallbackDataType=a}get tensor(){return this.mlTensor}get type(){return this.dataType}get fallbackType(){return this.fallbackDataType}get shape(){return this.tensorShape}get byteLength(){return Cn(this.dataType,this.tensorShape)}destroy(){Ae("verbose",()=>"[WebNN] TensorWrapper.destroy"),this.mlTensor.destroy()}write(e){this.mlContext.writeTensor(this.mlTensor,e)}async read(e){if(this.fallbackDataType){let t=await this.mlContext.readTensor(this.mlTensor),i=Tn(new Uint8Array(t),this.dataType);if(e){(e instanceof ArrayBuffer?new Uint8Array(e):new Uint8Array(e.buffer,e.byteOffset,e.byteLength)).set(i);return}else return i.buffer}else return e?this.mlContext.readTensor(this.mlTensor,e):this.mlContext.readTensor(this.mlTensor)}canReuseTensor(e,t,i){return this.mlContext===e&&this.dataType===t&&this.tensorShape.length===i.length&&this.tensorShape.every((n,r)=>n===i[r])}setIsDataConverted(e){this.isDataConverted=e}},An=class{constructor(e,t){this.tensorManager=e,this.wrapper=t}get tensorWrapper(){return this.wrapper}releaseTensor(){this.tensorWrapper&&(this.tensorManager.releaseTensor(this.tensorWrapper),this.wrapper=void 0)}async ensureTensor(e,t,i,n){let r=this.tensorManager.getMLContext(e),s;if(!r.opSupportLimits().input.dataTypes.includes(t)){if(s=ks.get(t),!s||!r.opSupportLimits().input.dataTypes.includes(s))throw new Error(`WebNN backend does not support data type: ${t}`);Ae("verbose",()=>`[WebNN] TensorIdTracker.ensureTensor: fallback dataType from ${t} to ${s}`)}if(this.wrapper){if(this.wrapper.canReuseTensor(r,t,i))return this.wrapper.tensor;if(n){if(this.wrapper.byteLength!==Cn(t,i))throw new Error("Unable to copy data to tensor with different size.");this.activeUpload=new Uint8Array(await this.wrapper.read())}this.tensorManager.releaseTensor(this.wrapper)}let a=typeof MLTensorUsage>"u"?void 0:MLTensorUsage.READ|MLTensorUsage.WRITE;return this.wrapper=await this.tensorManager.getCachedTensor(e,t,i,a,!0,!0,s),n&&this.activeUpload&&(this.wrapper.write(this.activeUpload),this.activeUpload=void 0),this.wrapper.tensor}upload(e){let t=e;if(this.wrapper){if(this.wrapper.fallbackType)if(this.wrapper.fallbackType==="int32")t=kn(e,this.wrapper.type),this.wrapper.setIsDataConverted(!0);else throw new Error(`Unsupported fallback data type: ${this.wrapper.fallbackType}`);if(e.byteLength===this.wrapper.byteLength){this.wrapper.write(t);return}else Ae("verbose",()=>"Data size does not match tensor size. Releasing tensor."),this.releaseTensor()}this.activeUpload?this.activeUpload.set(t):this.activeUpload=new Uint8Array(t)}async download(e){if(this.activeUpload){let t=this.wrapper?.isDataConverted?Tn(this.activeUpload,this.wrapper?.type):this.activeUpload;if(e){e instanceof ArrayBuffer?new Uint8Array(e).set(t):new Uint8Array(e.buffer,e.byteOffset,e.byteLength).set(t);return}else return t.buffer}if(!this.wrapper)throw new Error("Tensor has not been created.");return e?this.wrapper.read(e):this.wrapper.read()}},Ts=class{constructor(e){this.backend=e,this.tensorTrackersById=new Map,this.freeTensors=[],this.externalTensors=new Set}getMLContext(e){let t=this.backend.getMLContext(e);if(!t)throw new Error("MLContext not found for session.");return t}reserveTensorId(){let e=En();return this.tensorTrackersById.set(e,new An(this)),e}releaseTensorId(e){let t=this.tensorTrackersById.get(e);t&&(this.tensorTrackersById.delete(e),t.tensorWrapper&&this.releaseTensor(t.tensorWrapper))}async ensureTensor(e,t,i,n,r){Ae("verbose",()=>`[WebNN] TensorManager.ensureTensor {tensorId: ${t}, dataType: ${i}, shape: ${n}, copyOld: ${r}}`);let s=this.tensorTrackersById.get(t);if(!s)throw new Error("Tensor not found.");return s.ensureTensor(e,i,n,r)}upload(e,t){let i=this.tensorTrackersById.get(e);if(!i)throw new Error("Tensor not found.");i.upload(t)}async download(e,t){Ae("verbose",()=>`[WebNN] TensorManager.download {tensorId: ${e}, dstBuffer: ${t?.byteLength}}`);let i=this.tensorTrackersById.get(e);if(!i)throw new Error("Tensor not found.");return i.download(t)}releaseTensorsForSession(e){for(let t of this.freeTensors)t.sessionId===e&&t.destroy();this.freeTensors=this.freeTensors.filter(t=>t.sessionId!==e)}registerTensor(e,t,i,n){let r=this.getMLContext(e),s=En(),a=new In({sessionId:e,context:r,tensor:t,dataType:i,shape:n});return this.tensorTrackersById.set(s,new An(this,a)),this.externalTensors.add(a),s}async getCachedTensor(e,t,i,n,r,s,a){let o=this.getMLContext(e);for(let[u,d]of this.freeTensors.entries())if(d.canReuseTensor(o,t,i)){Ae("verbose",()=>`[WebNN] Reusing tensor {dataType: ${t}, ${a?`fallbackDataType: ${a},`:""} shape: ${i}`);let c=this.freeTensors.splice(u,1)[0];return c.sessionId=e,c}Ae("verbose",()=>`[WebNN] MLContext.createTensor {dataType: ${t}, ${a?`fallbackDataType: ${a},`:""} shape: ${i}}`);let l=await o.createTensor({dataType:a??t,shape:i,dimensions:i,usage:n,writable:r,readable:s});return new In({sessionId:e,context:o,tensor:l,dataType:t,shape:i,fallbackDataType:a})}releaseTensor(e){this.externalTensors.has(e)&&this.externalTensors.delete(e),this.freeTensors.push(e)}},Es=(...e)=>new Ts(...e)}),mi,Cs,Is,yp=E(()=>{ge(),qt(),xs(),_p(),Dt(),mi=new Map([[1,"float32"],[10,"float16"],[6,"int32"],[12,"uint32"],[7,"int64"],[13,"uint64"],[22,"int4"],[21,"uint4"],[3,"int8"],[2,"uint8"],[9,"uint8"]]),Cs=(e,t)=>{if(e===t)return!0;if(e===void 0||t===void 0)return!1;let i=Object.keys(e).sort(),n=Object.keys(t).sort();return i.length===n.length&&i.every((r,s)=>r===n[s]&&e[r]===t[r])},Is=class{constructor(e){this.tensorManager=Es(this),this.mlContextBySessionId=new Map,this.sessionIdsByMLContext=new Map,this.mlContextCache=[],this.sessionGraphInputs=new Map,this.sessionGraphOutputs=new Map,this.temporaryGraphInputs=[],this.temporaryGraphOutputs=[],this.temporarySessionTensorIds=new Map,$n(e.logLevel,!!e.debug)}get currentSessionId(){if(this.activeSessionId===void 0)throw new Error("No active session");return this.activeSessionId}onRunStart(e){Ae("verbose",()=>`[WebNN] onRunStart {sessionId: ${e}}`),this.activeSessionId=e}onRunEnd(e){Ae("verbose",()=>`[WebNN] onRunEnd {sessionId: ${e}}`);let t=this.temporarySessionTensorIds.get(e);if(t){for(let i of t)Ae("verbose",()=>`[WebNN] releasing temporary tensor {tensorId: ${i}}`),this.tensorManager.releaseTensorId(i);this.temporarySessionTensorIds.delete(e),this.activeSessionId=void 0}}async createMLContext(e){if(e instanceof GPUDevice){let i=this.mlContextCache.findIndex(n=>n.gpuDevice===e);if(i!==-1)return this.mlContextCache[i].mlContext;{let n=await navigator.ml.createContext(e);return this.mlContextCache.push({gpuDevice:e,mlContext:n}),n}}else if(e===void 0){let i=this.mlContextCache.findIndex(n=>n.options===void 0&&n.gpuDevice===void 0);if(i!==-1)return this.mlContextCache[i].mlContext;{let n=await navigator.ml.createContext();return this.mlContextCache.push({mlContext:n}),n}}let t=this.mlContextCache.findIndex(i=>Cs(i.options,e));if(t!==-1)return this.mlContextCache[t].mlContext;{let i=await navigator.ml.createContext(e);return this.mlContextCache.push({options:e,mlContext:i}),i}}registerMLContext(e,t){this.mlContextBySessionId.set(e,t);let i=this.sessionIdsByMLContext.get(t);i||(i=new Set,this.sessionIdsByMLContext.set(t,i)),i.add(e),this.temporaryGraphInputs.length>0&&(this.sessionGraphInputs.set(e,this.temporaryGraphInputs),this.temporaryGraphInputs=[]),this.temporaryGraphOutputs.length>0&&(this.sessionGraphOutputs.set(e,this.temporaryGraphOutputs),this.temporaryGraphOutputs=[])}onReleaseSession(e){this.sessionGraphInputs.delete(e),this.sessionGraphOutputs.delete(e);let t=this.mlContextBySessionId.get(e);if(!t)return;this.tensorManager.releaseTensorsForSession(e),this.mlContextBySessionId.delete(e);let i=this.sessionIdsByMLContext.get(t);if(i.delete(e),i.size===0){this.sessionIdsByMLContext.delete(t);let n=this.mlContextCache.findIndex(r=>r.mlContext===t);n!==-1&&this.mlContextCache.splice(n,1)}}getMLContext(e){return this.mlContextBySessionId.get(e)}reserveTensorId(){return this.tensorManager.reserveTensorId()}releaseTensorId(e){Ae("verbose",()=>`[WebNN] releaseTensorId {tensorId: ${e}}`),this.tensorManager.releaseTensorId(e)}async ensureTensor(e,t,i,n,r){let s=mi.get(i);if(!s)throw new Error(`Unsupported ONNX data type: ${i}`);return this.tensorManager.ensureTensor(e??this.currentSessionId,t,s,n,r)}async createTemporaryTensor(e,t,i){Ae("verbose",()=>`[WebNN] createTemporaryTensor {onnxDataType: ${t}, shape: ${i}}`);let n=mi.get(t);if(!n)throw new Error(`Unsupported ONNX data type: ${t}`);let r=this.tensorManager.reserveTensorId();await this.tensorManager.ensureTensor(e,r,n,i,!1);let s=this.temporarySessionTensorIds.get(e);return s?s.push(r):this.temporarySessionTensorIds.set(e,[r]),r}uploadTensor(e,t){if(!Le().shouldTransferToMLTensor)throw new Error("Trying to upload to a MLTensor while shouldTransferToMLTensor is false");Ae("verbose",()=>`[WebNN] uploadTensor {tensorId: ${e}, data: ${t.byteLength}}`),this.tensorManager.upload(e,t)}async downloadTensor(e,t){return this.tensorManager.download(e,t)}createMLTensorDownloader(e,t){return async()=>{let i=await this.tensorManager.download(e);return xn(i,t)}}registerMLTensor(e,t,i,n){let r=mi.get(i);if(!r)throw new Error(`Unsupported ONNX data type: ${i}`);let s=this.tensorManager.registerTensor(e,t,r,n);return Ae("verbose",()=>`[WebNN] registerMLTensor {tensor: ${t}, dataType: ${r}, dimensions: ${n}} -> {tensorId: ${s}}`),s}registerMLConstant(e,t,i,n,r,s,a=!1){if(!s)throw new Error("External mounted files are not available.");let o=e;e.startsWith("./")&&(o=e.substring(2));let l=s.get(o);if(!l)throw new Error(`File with name ${o} not found in preloaded files.`);if(t+i>l.byteLength)throw new Error("Out of bounds: data offset and length exceed the external file data size.");let u=l.slice(t,t+i).buffer,d;switch(r.dataType){case"float32":d=new Float32Array(u);break;case"float16":d=typeof Float16Array<"u"&&Float16Array.from?new Float16Array(u):new Uint16Array(u);break;case"int32":d=new Int32Array(u);break;case"uint32":d=new Uint32Array(u);break;case"int64":if(a){let c=kn(new Uint8Array(u),"int64");d=new Int32Array(c.buffer),r.dataType="int32"}else d=new BigInt64Array(u);break;case"uint64":d=new BigUint64Array(u);break;case"int8":d=new Int8Array(u);break;case"int4":case"uint4":case"uint8":d=new Uint8Array(u);break;default:throw new Error(`Unsupported data type: ${r.dataType} in creating WebNN Constant from external data.`)}return Ae("verbose",()=>`[WebNN] registerMLConstant {dataType: ${r.dataType}, shape: ${r.shape}}} ${a?"(Note: it was int64 data type and registered to int32 as workaround)":""}`),n.constant(r,d)}registerGraphInput(e){this.temporaryGraphInputs.push(e)}registerGraphOutput(e){this.temporaryGraphOutputs.push(e)}isGraphInput(e,t){let i=this.sessionGraphInputs.get(e);return i?i.includes(t):!1}isGraphOutput(e,t){let i=this.sessionGraphOutputs.get(e);return i?i.includes(t):!1}isGraphInputOutputTypeSupported(e,t,i=!0){let n=this.mlContextBySessionId.get(e),r=mi.get(Wt(t));return typeof r>"u"?!1:i?!!n?.opSupportLimits().input.dataTypes.includes(r):!!n?.opSupportLimits().output.dataTypes.includes(r)}flush(){}}}),zn=E(()=>{}),Mn,Pi,Ni,As,zs,Rn,On,Ms,Rs,wp=E(()=>{Dt(),zn(),Mn=new Map([[64,250],[128,200],[256,200],[512,200],[2048,230],[4096,200],[8192,50],[16384,50],[32768,50],[65536,50],[131072,50],[262144,50],[524288,50],[1048576,50],[2097152,30],[4194304,20],[8388608,10],[12582912,10],[16777216,10],[26214400,15],[33554432,22],[44236800,2],[58982400,6],[67108864,6],[134217728,6],[167772160,6]]),Pi=[],Ni=e=>Math.ceil(Number(e)/16)*16,As=e=>{for(let t=0;t<Pi.length;t++){let i=Pi[t];if(e<=i)return i}return Math.ceil(e/16)*16},zs=1,Rn=()=>zs++,On=async(e,t,i,n)=>{let r=Ni(i),s=e.device.createBuffer({size:r,usage:GPUBufferUsage.COPY_DST|GPUBufferUsage.MAP_READ});try{let a=e.getCommandEncoder();e.endComputePass(),a.copyBufferToBuffer(t,0,s,0,r),e.flush(),await s.mapAsync(GPUMapMode.READ);let o=s.getMappedRange();if(n){let l=n();return l.set(new Uint8Array(o,0,i)),l}else return new Uint8Array(o.slice(0,i))}finally{s.destroy()}},Ms=class{constructor(e){this.backend=e,this.storageCache=new Map,this.freeBuffers=new Map,this.freeUniformBuffers=new Map,this.buffersPending=[],this.capturedPendingBuffers=new Map;for(let[t]of Mn)Pi.push(t),this.freeBuffers.set(t,[]),this.freeUniformBuffers.set(t,[]);this.sessionCount=0}upload(e,t){let i=t.buffer,n=t.byteOffset,r=t.byteLength,s=Ni(r),a=this.storageCache.get(e);if(!a)throw new Error("gpu data for uploading does not exist");if(Number(a.originalSize)!==r)throw new Error(`inconsistent data size. gpu data size=${a.originalSize}, data size=${r}`);let o=this.backend.device.createBuffer({mappedAtCreation:!0,size:s,usage:GPUBufferUsage.MAP_WRITE|GPUBufferUsage.COPY_SRC}),l=o.getMappedRange();new Uint8Array(l).set(new Uint8Array(i,n,r)),o.unmap();let u=this.backend.device.createCommandEncoder();u.copyBufferToBuffer(o,0,a.gpuData.buffer,0,s),this.backend.device.queue.submit([u.finish()]),o.destroy(),Ae("verbose",()=>`[WebGPU] GpuDataManager.upload(id=${e})`)}memcpy(e,t){let i=this.storageCache.get(e);if(!i)throw new Error("source gpu data for memcpy does not exist");let n=this.storageCache.get(t);if(!n)throw new Error("destination gpu data for memcpy does not exist");if(i.originalSize!==n.originalSize)throw new Error("inconsistent source and destination gpu data size");let r=Ni(i.originalSize),s=this.backend.getCommandEncoder();this.backend.endComputePass(),s.copyBufferToBuffer(i.gpuData.buffer,0,n.gpuData.buffer,0,r)}registerExternalBuffer(e,t,i){let n;if(i){if(n=i[0],e===i[1])return Ae("verbose",()=>`[WebGPU] GpuDataManager.registerExternalBuffer(size=${t}) => id=${n}, buffer is the same, skip.`),n;if(this.backend.capturedCommandList.has(this.backend.currentSessionId))throw new Error(`Registering a different external buffer under graph capture mode is not supported yet.
             Please use the previous external buffer!`)}else n=Rn();return this.storageCache.set(n,{gpuData:{id:n,type:0,buffer:e},originalSize:t}),Ae("verbose",()=>`[WebGPU] GpuDataManager.registerExternalBuffer(size=${t}) => id=${n}, registered.`),n}unregisterExternalBuffer(e){e!==void 0&&(this.storageCache.delete(e),Ae("verbose",()=>`[WebGPU] GpuDataManager.unregisterExternalBuffer() => id=${e}`))}create(e,t=GPUBufferUsage.STORAGE|GPUBufferUsage.COPY_SRC|GPUBufferUsage.COPY_DST){let i=As(e),n,r=(t&GPUBufferUsage.STORAGE)===GPUBufferUsage.STORAGE,s=(t&GPUBufferUsage.UNIFORM)===GPUBufferUsage.UNIFORM;if(r||s){let o=(r?this.freeBuffers:this.freeUniformBuffers).get(i);o?o.length>0?n=o.pop():n=this.backend.device.createBuffer({size:i,usage:t}):n=this.backend.device.createBuffer({size:i,usage:t})}else n=this.backend.device.createBuffer({size:i,usage:t});let a={id:Rn(),type:0,buffer:n};return this.storageCache.set(a.id,{gpuData:a,originalSize:Number(e)}),Ae("verbose",()=>`[WebGPU] GpuDataManager.create(size=${e}) => id=${a.id}`),a}get(e){return this.storageCache.get(e)?.gpuData}release(e){let t=typeof e=="bigint"?Number(e):e,i=this.storageCache.get(t);if(!i){if(this.storageCache.size===0)return 0;throw new Error("releasing data does not exist")}return Ae("verbose",()=>`[WebGPU] GpuDataManager.release(id=${t}), gpuDataId=${i.gpuData.id}`),this.storageCache.delete(t),this.buffersPending.push(i.gpuData.buffer),i.originalSize}async download(e,t){let i=this.storageCache.get(Number(e));if(!i)throw new Error("data does not exist");await On(this.backend,i.gpuData.buffer,i.originalSize,t)}refreshPendingBuffers(){if(this.buffersPending.length!==0)if(this.backend.sessionStatus==="default"){for(let e of this.buffersPending){let t=Mn.get(e.size);if((e.usage&GPUBufferUsage.STORAGE)===GPUBufferUsage.STORAGE){let i=this.freeBuffers.get(e.size)||[];t===void 0||i.length>=t?e.destroy():i.push(e)}else if((e.usage&GPUBufferUsage.UNIFORM)===GPUBufferUsage.UNIFORM){let i=this.freeUniformBuffers.get(e.size)||[];t===void 0||i.length>=t?e.destroy():i.push(e)}else e.destroy()}this.buffersPending=[]}else{let e=this.capturedPendingBuffers.get(this.backend.currentSessionId);e||(e=[],this.capturedPendingBuffers.set(this.backend.currentSessionId,e));for(let t of this.buffersPending)e.push(t);this.buffersPending=[]}}dispose(){this.freeBuffers.forEach(e=>{e.forEach(t=>{t.destroy()})}),this.freeUniformBuffers.forEach(e=>{e.forEach(t=>{t.destroy()})}),this.storageCache.forEach(e=>{e.gpuData.buffer.destroy()}),this.capturedPendingBuffers.forEach(e=>{e.forEach(t=>{t.destroy()})}),this.storageCache=new Map,this.freeBuffers=new Map,this.freeUniformBuffers=new Map,this.capturedPendingBuffers=new Map}onCreateSession(){this.sessionCount+=1}onReleaseSession(e){let t=this.capturedPendingBuffers.get(e);t&&(t.forEach(i=>{i.destroy()}),this.capturedPendingBuffers.delete(e)),this.sessionCount-=1,this.sessionCount===0&&(Ae("warning",()=>"[WebGPU] Clearing webgpu buffer cache"),this.storageCache.forEach(i=>{i.gpuData.buffer.destroy()}),this.storageCache=new Map)}},Rs=(...e)=>new Ms(...e)}),Os,Be,He=E(()=>{Os=class{constructor(e){Object.assign(this,e)}get cacheKey(){return this.key||(this.key=Object.getOwnPropertyNames(this).sort().map(e=>`${this[e]}`).join(";")),this.key}},Be=e=>new Os(e)}),ai,Vi,et,ot,de,je,Dn,oi,Pt,le,gi,F,oe,Ds,Bn,Bs,Fs,xe=E(()=>{ge(),$e(),ai=64,Vi=(e,t)=>{if(t===3)throw new Error("vec3 has same alignment as vec4, use vec4 instead");switch(Number(e)){case 10:return t>1?`vec${t}<f16>`:"f16";case 1:return t>1?`vec${t}<f32>`:"f32";case 6:return t>1?`vec${t}<i32>`:"i32";case 12:return t>1?`vec${t}<u32>`:"u32";case 7:if(t>1)throw new Error("currently not supported vecX of uint64 yet");return["vec2<u32>","i32"];case 13:if(t>1)throw new Error("currently not supported vecX of uint64 yet");return["vec2<u32>","u32"];case 9:if(t!==4)throw new Error("bool must be vec4");return["u32","vec4<bool>"];case 22:return"i32";case 21:return"u32";default:throw new Error(`Unknown data type: ${e}`)}},et=(e,t=1)=>{let i=Vi(e,t);return typeof i=="string"?i:i[0]},ot=(e,t=1)=>{let i=Vi(e,t);return typeof i=="string"?i:i[1]},de=(...e)=>{let t=[];return e.forEach(i=>{i.length!==0&&t.push({type:12,data:i},{type:12,data:O.computeStrides(i)})}),t},je=e=>e%4===0?4:e%2===0?2:1,Dn=(e="f32",t,i="0")=>!t||t===1?`${e}(${i})`:`vec${t}<${e}>(${i})`,oi=(e,t,i)=>e==="f32"?i:t===1?`f32(${i})`:`vec${t}<f32>(${i})`,Pt=(e,t)=>t===4?`(${e}.x + ${e}.y + ${e}.z + ${e}.w)`:t===2?`(${e}.x + ${e}.y)`:t===3?`(${e}.x + ${e}.y + ${e}.z)`:e,le=(e,t,i,n)=>e.startsWith("uniforms.")&&i>4?typeof t=="string"?n==="f16"?`${e}[(${t}) / 8][(${t}) % 8 / 4][(${t}) % 8 % 4]`:`${e}[(${t}) / 4][(${t}) % 4]`:n==="f16"?`${e}[${Math.floor(t/8)}][${Math.floor(t%8/4)}][${t%8%4}]`:`${e}[${Math.floor(t/4)}][${t%4}]`:i>1?`${e}[${t}]`:e,gi=(e,t,i,n,r)=>{let s=typeof i=="number",a=s?i:i.length,o=[...new Array(a).keys()],l=a<2?"u32":a<=4?`vec${a}<u32>`:`array<u32, ${a}>`,u=Vi(t,r),d=typeof u=="string"?u:u[1],c=typeof u=="string"?u:u[0],p={indices:l,value:d,storage:c,tensor:t},h=G=>typeof G=="string"?G:`${G}u`,m={offsetToIndices:!1,indicesToOffset:!1,broadcastedIndicesToOffset:!1,set:!1,setByIndices:!1,get:!1,getByIndices:!1},_=s?"uniforms.":"",$=`${_}${e}_shape`,y=`${_}${e}_strides`,g="";for(let G=0;G<a-1;G++)g+=`
    let dim${G} = current / ${le(y,G,a)};
    let rest${G} = current % ${le(y,G,a)};
    indices[${G}] = dim${G};
    current = rest${G};
    `;g+=`indices[${a-1}] = current;`;let T=a<2?"":`
  fn o2i_${e}(offset: u32) -> ${p.indices} {
    var indices: ${p.indices};
    var current = offset;
    ${g}
    return indices;
  }`,x=G=>(m.offsetToIndices=!0,a<2?G:`o2i_${e}(${G})`),C=[];if(a>=2)for(let G=a-1;G>=0;G--)C.push(`${le(y,G,a)} * (indices[${G}])`);let R=a<2?"":`
  fn i2o_${e}(indices: ${p.indices}) -> u32 {
    return ${C.join("+")};
  }`,z=G=>(m.indicesToOffset=!0,a<2?G:`i2o_${e}(${G})`),P=(...G)=>a===0?"0u":`${p.indices}(${G.map(h).join(",")})`,U=(G,ne)=>a<2?`${G}`:`${le(G,ne,a)}`,re=(G,ne,Se)=>a<2?`${G}=${Se};`:`${le(G,ne,a)}=${Se};`,_e={},pe=(G,ne)=>{m.broadcastedIndicesToOffset=!0;let Se=`${ne.name}broadcastedIndicesTo${e}Offset`;if(Se in _e)return`${Se}(${G})`;let Pe=[];for(let nt=a-1;nt>=0;nt--){let Ct=ne.indicesGet("outputIndices",nt+ne.rank-a);Pe.push(`${U(y,nt)} * (${Ct} % ${U($,nt)})`)}return _e[Se]=`fn ${Se}(outputIndices: ${ne.type.indices}) -> u32 {
             return ${Pe.length>0?Pe.join("+"):"0u"};
           }`,`${Se}(${G})`},be=(G,ne)=>(()=>{if(p.storage===p.value)return`${e}[${G}]=${ne};`;if(p.storage==="vec2<u32>"&&p.value==="i32")return`${e}[${G}]=vec2<u32>(u32(${ne}), select(0u, 0xFFFFFFFFu, ${ne} < 0));`;if(p.storage==="vec2<u32>"&&p.value==="u32")return`${e}[${G}]=vec2<u32>(u32(${ne}), 0u);`;if(p.storage==="u32"&&p.value==="vec4<bool>")return`${e}[${G}]=dot(vec4<u32>(0x1, 0x100, 0x10000, 0x1000000), vec4<u32>(${ne}));`;throw new Error(`not supported combination of storage type ${p.storage} and value type ${p.value} yet`)})(),ae=G=>(()=>{if(p.storage===p.value)return`${e}[${G}]`;if(p.storage==="vec2<u32>"&&p.value==="i32")return`i32(${e}[${G}].x)`;if(p.storage==="vec2<u32>"&&p.value==="u32")return`u32(${e}[${G}].x)`;if(p.storage==="u32"&&p.value==="vec4<bool>")return`vec4<bool>(bool(${e}[${G}] & 0xFFu), bool(${e}[${G}] & 0xFF00u), bool(${e}[${G}] & 0xFF0000u), bool(${e}[${G}] & 0xFF000000u))`;throw new Error(`not supported combination of storage type ${p.storage} and value type ${p.value} yet`)})(),ke=a<2?"":`
  fn get_${e}ByIndices(indices: ${p.indices}) -> ${d} {
    return ${ae(`i2o_${e}(indices)`)};
  }`,me=a<2?"":(()=>{let G=o.map(Se=>`d${Se}: u32`).join(", "),ne=o.map(Se=>`d${Se}`).join(", ");return`
  fn get_${e}(${G}) -> ${d} {
    return get_${e}ByIndices(${P(ne)});
  }`})(),ue=(...G)=>{if(G.length!==a)throw new Error(`indices length must be ${a}`);let ne=G.map(h).join(",");return a===0?ae("0u"):a===1?ae(ne[0]):(m.get=!0,m.getByIndices=!0,m.indicesToOffset=!0,`get_${e}(${ne})`)},De=G=>a<2?ae(G):(m.getByIndices=!0,m.indicesToOffset=!0,`get_${e}ByIndices(${G})`),fe=a<2?"":`
  fn set_${e}ByIndices(indices: ${p.indices}, value: ${d}) {
    ${be(`i2o_${e}(indices)`,"value")}
  }`,Ue=a<2?"":(()=>{let G=o.map(Se=>`d${Se}: u32`).join(", "),ne=o.map(Se=>`d${Se}`).join(", ");return`
  fn set_${e}(${G}, value: ${d}) {
    set_${e}ByIndices(${P(ne)}, value);
  }`})();return{impl:()=>{let G=[],ne=!1;return m.offsetToIndices&&(G.push(T),ne=!0),m.indicesToOffset&&(G.push(R),ne=!0),m.broadcastedIndicesToOffset&&(Object.values(_e).forEach(Se=>G.push(Se)),ne=!0),m.set&&(G.push(Ue),ne=!0),m.setByIndices&&(G.push(fe),ne=!0),m.get&&(G.push(me),ne=!0),m.getByIndices&&(G.push(ke),ne=!0),!s&&ne&&G.unshift(`const ${$} = ${p.indices}(${i.join(",")});`,`const ${y} = ${p.indices}(${O.computeStrides(i).join(",")});`),G.join(`
`)},type:p,offsetToIndices:x,indicesToOffset:z,broadcastedIndicesToOffset:pe,indices:P,indicesGet:U,indicesSet:re,set:(...G)=>{if(G.length!==a+1)throw new Error(`indices length must be ${a}`);let ne=G[a];if(typeof ne!="string")throw new Error("value must be string");let Se=G.slice(0,a).map(h).join(",");return a===0?be("0u",ne):a===1?be(Se[0],ne):(m.set=!0,m.setByIndices=!0,m.indicesToOffset=!0,`set_${e}(${Se}, ${ne})`)},setByOffset:be,setByIndices:(G,ne)=>a<2?be(G,ne):(m.setByIndices=!0,m.indicesToOffset=!0,`set_${e}ByIndices(${G}, ${ne});`),get:ue,getByOffset:ae,getByIndices:De,usage:n,name:e,strides:y,shape:$,rank:a}},F=(e,t,i,n=1)=>gi(e,t,i,"input",n),oe=(e,t,i,n=1)=>gi(e,t,i,"output",n),Ds=(e,t,i)=>gi(e,t,i,"atomicOutput",1),Bn=(e,t,i,n=1)=>gi(e,t,i,"internal",n),Bs=class{constructor(e,t){this.normalizedDispatchGroup=e,this.limits=t,this.internalVariables=[],this.variables=[],this.uniforms=[],this.variableIndex=0}guardAgainstOutOfBoundsWorkgroupSizes(e){return`if (global_idx >= ${typeof e=="number"?`${e}u`:e}) { return; }`}mainStart(e=ai){let t=typeof e=="number"?e:e[0],i=typeof e=="number"?1:e[1],n=typeof e=="number"?1:e[2];if(t>this.limits.maxComputeWorkgroupSizeX||i>this.limits.maxComputeWorkgroupSizeY||n>this.limits.maxComputeWorkgroupSizeZ)throw new Error(`workgroup size [${t}, ${i}, ${n}] exceeds the maximum workgroup size [${this.limits.maxComputeWorkgroupSizeX}, ${this.limits.maxComputeWorkgroupSizeY}, ${this.limits.maxComputeWorkgroupSizeZ}].`);if(t*i*n>this.limits.maxComputeInvocationsPerWorkgroup)throw new Error(`workgroup size [${t}, ${i}, ${n}] exceeds the maximum workgroup invocations ${this.limits.maxComputeInvocationsPerWorkgroup}.`);let r=this.normalizedDispatchGroup[1]===1&&this.normalizedDispatchGroup[2]===1,s=r?`@builtin(global_invocation_id) global_id : vec3<u32>,
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
`)}get variablesInfo(){if(this.uniforms.length===0)return;let e=t=>[12,10,1,6][["u32","f16","f32","i32"].indexOf(t)];return this.uniforms.map(t=>[e(t.type),t.length??1])}},Fs=(e,t)=>new Bs(e,t)}),Ps,Fn,Ns,Vs,Ls,Us,ft,qs,Ws,Nt=E(()=>{ge(),$e(),He(),xe(),Ps=(e,t)=>{if(!e||e.length!==1)throw new Error("Transpose requires 1 input.");if(t.length!==0&&t.length!==e[0].dims.length)throw new Error(`perm size ${t.length} does not match input rank ${e[0].dims.length}`)},Fn=(e,t)=>t.length!==0?t:[...new Array(e).keys()].reverse(),Ns=(e,t)=>O.sortBasedOnPerm(e,Fn(e.length,t)),Vs=(e,t,i,n)=>{let r=`fn perm(i: ${n.type.indices}) -> ${i.type.indices} {
    var a: ${i.type.indices};`;for(let s=0;s<t;++s)r+=`a[${e[s]}]=i[${s}];`;return r+="return a;}"},Ls=(e,t)=>{let i=[],n=[];for(let r=0;r<e.length;++r)e[r]!==1&&i.push(e[r]),e[t[r]]!==1&&n.push(t[r]);return{newShape:i,newPerm:n}},Us=(e,t)=>{let i=0;for(let n=0;n<e.length;++n)if(t[e[n]]!==1){if(e[n]<i)return!1;i=e[n]}return!0},ft=(e,t)=>{let i=e.dataType,n=e.dims.length,r=Fn(n,t),s=Ns(e.dims,r),a=e.dims,o=s,l=n<2||Us(r,e.dims),u;if(l)return u=m=>{let _=F("input",i,a,4),$=oe("output",i,o,4);return`
  ${m.registerUniform("output_size","u32").declareVariables(_,$)}
  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    output[global_idx] = input[global_idx];
  }`},{name:"TransposeCopy",shaderCache:{inputDependencies:["type"]},getRunData:()=>{let m=O.size(s);return{outputs:[{dims:s,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(m/64/4)},programUniforms:[{type:12,data:Math.ceil(m/4)}]}},getShaderSource:u};let{newShape:d,newPerm:c}=Ls(e.dims,r),p=O.areEqual(c,[2,3,1]),h=O.areEqual(c,[3,1,2]);if(d.length===2||p||h){a=p?[d[0],d[1]*d[2]]:h?[d[0]*d[1],d[2]]:d,o=[a[1],a[0]];let m=16;return u=_=>{let $=F("a",i,a.length),y=oe("output",i,o.length);return`
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
  }`},{name:"TransposeShared",shaderCache:{inputDependencies:["type"]},getRunData:()=>{let _=O.size(s);return{outputs:[{dims:s,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(o[1]/m),y:Math.ceil(o[0]/m)},programUniforms:[{type:12,data:_},...de(a,o)]}},getShaderSource:u}}return u=m=>{let _=F("a",i,a.length),$=oe("output",i,o.length);return`
  ${m.registerUniform("output_size","u32").declareVariables(_,$)}

  ${Vs(r,n,_,$)}

  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let indices = ${$.offsetToIndices("global_idx")};
    let aIndices = perm(indices);

    ${$.setByOffset("global_idx",_.getByIndices("aIndices"))}
  }`},{name:"Transpose",shaderCache:{hint:`${t}`,inputDependencies:["rank"]},getRunData:()=>{let m=O.size(s);return{outputs:[{dims:s,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(m/64)},programUniforms:[{type:12,data:m},...de(a,o)]}},getShaderSource:u}},qs=(e,t)=>{Ps(e.inputs,t.perm),e.compute(ft(e.inputs[0],t.perm))},Ws=e=>Be({perm:e.perm})}),Gs,js,Hs,Ks,Zs,Qs,Xs,Ys,Js,ea,vt,ta,ia,na,ra,sa,aa,oa,la,ua,da,bp=E(()=>{ge(),$e(),xe(),Nn(),Nt(),Gs={max:"select(bestValue, candidate, candidate > bestValue)",min:"select(bestValue, candidate, candidate < bestValue)",mean:"bestValue + candidate",sum:"bestValue + candidate",prod:"bestValue * candidate",sumSquare:"bestValue + candidate * candidate",logSumExp:"bestValue + exp(candidate)",l1:"bestValue + abs(candidate)",l2:"bestValue + candidate * candidate",logSum:"bestValue + candidate"},js={max:"select(bestValue, candidate, candidate > bestValue)",min:"select(bestValue, candidate, candidate < bestValue)",mean:"bestValue + candidate",sum:"bestValue + candidate",prod:"bestValue * candidate",sumSquare:"bestValue + candidate",logSumExp:"bestValue + candidate",l1:"bestValue + candidate",l2:"bestValue + candidate",logSum:"bestValue + candidate"},Hs={max:"_A[offset]",min:"_A[offset]",mean:"0",sum:"0",prod:"1",sumSquare:"0",logSumExp:"0",l1:"0",l2:"0",logSum:"0"},Ks={max:"bestValue",min:"bestValue",sum:"bestValue",prod:"bestValue",sumSquare:"bestValue",logSumExp:"log(bestValue)",l1:"bestValue",l2:"sqrt(bestValue)",logSum:"log(bestValue)"},Zs=(e,t)=>{let i=[];for(let n=t-e;n<t;++n)i.push(n);return i},Qs=(e,t)=>{let i=[],n=e.length;for(let s=0;s<n;s++)t.indexOf(s)===-1&&i.push(e[s]);let r=t.map(s=>e[s]);return[i,r]},Xs=(e,t)=>{let i=e.length+t.length,n=[],r=0;for(let s=0;s<i;s++)t.indexOf(s)===-1?n.push(e[r++]):n.push(1);return n},Ys=(e,t)=>{for(let i=0;i<e.length;++i)if(e[e.length-i-1]!==t-1-i)return!1;return!0},Js=(e,t)=>{let i=[];if(!Ys(e,t)){for(let n=0;n<t;++n)e.indexOf(n)===-1&&i.push(n);e.forEach(n=>i.push(n))}return i},ea=(e,t,i,n,r,s,a)=>{let o=i[0].dims,l=O.size(s),u=O.size(a),d=F("_A",i[0].dataType,o),c=oe("output",r,s),p=64;l===1&&(p=256);let h=`
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

          var bestValue = f32(${Hs[n]});
          let Length = uniforms.reduceSize;
          for (var k = local_idx; k < Length; k = k + ${p}) {
           let candidate = f32(${d.getByOffset("offset + k")});
           bestValue = ${Gs[n]};
          }
          aBestValues[local_idx] = bestValue;
          workgroupBarrier();

         var reduceSize = min(Length, ${p}u);
         for (var currentSize = reduceSize / 2u; reduceSize > 1u;
             currentSize = reduceSize / 2u) {
           let interval = DIV_CEIL(reduceSize, 2u);
           if (local_idx < currentSize) {
            let candidate = aBestValues[local_idx + interval];
            bestValue = ${js[n]};
            aBestValues[local_idx] = bestValue;
           }
           reduceSize = interval;
           workgroupBarrier();
         }

         if (local_idx == 0u) {
          ${c.setByOffset("outputIndex",`${n==="mean"?`${c.type.storage}(bestValue / f32(uniforms.reduceSize))`:`${c.type.storage}(${Ks[n]})`}`)};
         }
        }`;return{name:e,shaderCache:{hint:`${t};${p}`,inputDependencies:["type"]},getShaderSource:m,getRunData:()=>({outputs:[{dims:s,dataType:r}],dispatchGroup:{x:l},programUniforms:[{type:12,data:u}]})}},vt=(e,t,i,n)=>{let r=e.inputs.length===1?i:Pn(e.inputs,i),s=r.axes;s.length===0&&!r.noopWithEmptyAxes&&(s=e.inputs[0].dims.map((h,m)=>m));let a=O.normalizeAxes(s,e.inputs[0].dims.length),o=a,l=e.inputs[0],u=Js(o,e.inputs[0].dims.length);u.length>0&&(l=e.compute(ft(e.inputs[0],u),{inputs:[0],outputs:[-1]})[0],o=Zs(o.length,l.dims.length));let[d,c]=Qs(l.dims,o),p=d;r.keepDims&&(p=Xs(d,a)),e.compute(ea(t,r.cacheKey,[l],n,e.inputs[0].dataType,p,c),{inputs:[l]})},ta=(e,t)=>{vt(e,"ReduceMeanShared",t,"mean")},ia=(e,t)=>{vt(e,"ReduceL1Shared",t,"l1")},na=(e,t)=>{vt(e,"ReduceL2Shared",t,"l2")},ra=(e,t)=>{vt(e,"ReduceLogSumExpShared",t,"logSumExp")},sa=(e,t)=>{vt(e,"ReduceMaxShared",t,"max")},aa=(e,t)=>{vt(e,"ReduceMinShared",t,"min")},oa=(e,t)=>{vt(e,"ReduceProdShared",t,"prod")},la=(e,t)=>{vt(e,"ReduceSumShared",t,"sum")},ua=(e,t)=>{vt(e,"ReduceSumSquareShared",t,"sumSquare")},da=(e,t)=>{vt(e,"ReduceLogSumShared",t,"logSum")}}),$t,ca,Li,Pn,xt,pa,fa,ha,ma,ga,_a,ya,wa,ba,va,St,$a,xa,Sa,ka,Ta,Ea,Ca,Ia,Aa,za,Nn=E(()=>{ge(),$e(),He(),xe(),bp(),$t=e=>{if(!e||e.length===0||e.length>2)throw new Error("Reduce op requires 1 or 2 inputs.");if(e.length===2&&e[1].dims.length!==1)throw new Error("Invalid axes input dims.")},ca=e=>["","",`var value = ${e.getByIndices("input_indices")};`,""],Li=(e,t,i,n,r,s,a=!1,o=!1)=>{let l=[],u=i[0].dims,d=u.length,c=O.normalizeAxes(r,d),p=!o&&c.length===0;u.forEach((_,$)=>{p||c.indexOf($)>=0?a&&l.push(1):l.push(_)});let h=l.length,m=O.size(l);return{name:e,shaderCache:t,getShaderSource:_=>{let $=[],y=F("_A",i[0].dataType,d),g=oe("output",s,h),T=n(y,g,c),x=T[2];for(let C=0,R=0;C<d;C++)p||c.indexOf(C)>=0?(a&&R++,x=`for(var j${C}: u32 = 0; j${C} < ${u[C]}; j${C}++) {
                  ${T[2].includes("last_index")?`let last_index = j${C};`:""}
                  ${y.indicesSet("input_indices",C,`j${C}`)}
                  ${x}
                }`):($.push(`${y.indicesSet("input_indices",C,g.indicesGet("output_indices",R))};`),R++);return`

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
        }`},getRunData:()=>({outputs:[{dims:l,dataType:s}],dispatchGroup:{x:Math.ceil(m/64)},programUniforms:[{type:12,data:m},...de(u,l)]})}},Pn=(e,t)=>{let i=[];return e[1].dims[0]>0&&e[1].getBigInt64Array().forEach(n=>i.push(Number(n))),Be({axes:i,keepDims:t.keepDims,noopWithEmptyAxes:t.noopWithEmptyAxes})},xt=(e,t,i,n)=>{let r=e.inputs,s=r.length===1?i:Pn(r,i);e.compute(Li(t,{hint:s.cacheKey,inputDependencies:["rank"]},[r[0]],s.noopWithEmptyAxes&&s.axes.length===0?ca:n,s.axes,r[0].dataType,s.keepDims,s.noopWithEmptyAxes),{inputs:[0]})},pa=(e,t)=>{$t(e.inputs),xt(e,"ReduceLogSum",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += ${i.getByIndices("input_indices")};`,"value = log(value);"])},fa=(e,t)=>{$t(e.inputs),xt(e,"ReduceL1",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += abs(${i.getByIndices("input_indices")});`,""])},ha=(e,t)=>{$t(e.inputs),xt(e,"ReduceL2",t,(i,n)=>[`var t = ${n.type.value}(0); var value = ${n.type.value}(0);`,"",`t = ${i.getByIndices("input_indices")}; value += (t * t);`,"value = sqrt(value);"])},ma=(e,t)=>{$t(e.inputs),xt(e,"ReduceLogSumExp",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += exp(${i.getByIndices("input_indices")});`,"value = log(value);"])},ga=(e,t)=>{$t(e.inputs),xt(e,"ReduceMax",t,(i,n,r)=>{let s=[];for(let a=0;a<i.rank;a++)(r.indexOf(a)>=0||r.length===0)&&s.push(i.indicesSet("input_indices",a,0));return[`${s.join(`
`)}`,`var value = ${i.getByIndices("input_indices")};`,`value = max(value, ${i.getByIndices("input_indices")});`,""]})},_a=(e,t)=>{$t(e.inputs),xt(e,"ReduceMean",t,(i,n,r)=>{let s=1;for(let a=0;a<i.rank;a++)(r.indexOf(a)>=0||r.length===0)&&(s*=e.inputs[0].dims[a]);return["var sum = f32(0);","",`sum += f32(${i.getByIndices("input_indices")});`,`let value = ${n.type.value}(sum / ${s});`]})},ya=(e,t)=>{$t(e.inputs),xt(e,"ReduceMin",t,(i,n,r)=>{let s=[];for(let a=0;a<i.rank;a++)(r.indexOf(a)>=0||r.length===0)&&s.push(`input_indices[${a}] = 0;`);return[`${s.join(`
`)}`,`var value = ${i.getByIndices("input_indices")};`,`value = min(value, ${i.getByIndices("input_indices")});`,""]})},wa=(e,t)=>{$t(e.inputs),xt(e,"ReduceProd",t,(i,n)=>[`var value = ${n.type.storage}(1);`,"",`value *= ${i.getByIndices("input_indices")};`,""])},ba=(e,t)=>{$t(e.inputs),xt(e,"ReduceSum",t,(i,n)=>[`var value = ${n.type.storage}(0);`,"",`value += ${i.getByIndices("input_indices")};`,""])},va=(e,t)=>{$t(e.inputs),xt(e,"ReduceSumSquare",t,(i,n)=>[`var t = ${n.type.value}(0); var value = ${n.type.value}(0);`,"",`t = ${i.getByIndices("input_indices")}; value += t * t;`,""])},St=(e,t,i)=>{if(t.length===0)return i;let n=1,r=1;for(let s=0;s<t.length;s++)t.indexOf(s)===-1?n*=e[s]:r*=e[s];return r<32&&n>1024},$a=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?_a(e,t):ta(e,t)},xa=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?fa(e,t):ia(e,t)},Sa=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ha(e,t):na(e,t)},ka=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ma(e,t):ra(e,t)},Ta=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ga(e,t):sa(e,t)},Ea=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ya(e,t):aa(e,t)},Ca=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?wa(e,t):oa(e,t)},Ia=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?ba(e,t):la(e,t)},Aa=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?va(e,t):ua(e,t)},za=(e,t)=>{St(e.inputs[0].dims,t.axes,t.noopWithEmptyAxes)?pa(e,t):da(e,t)}}),Vn,Ma,Ra,Ln,vp=E(()=>{ge(),He(),Nn(),Vn=e=>{if(!e||e.length===0||e.length>2)throw new Error("ArgMinMaxOp op requires 1 or 2 inputs.");if(e[0].dataType!==1)throw new Error("Invalid input type.")},Ma=(e,t)=>{Vn(e.inputs);let i=(n,r,s)=>{let a=[];for(let o=0;o<n.rank;o++)(s.indexOf(o)>=0||s.length===0)&&a.push(`input_indices[${o}] = 0;`);return[`${a.join(`
`)}`,`var value = ${n.getByIndices("input_indices")};
var best_index : i32 = 0;`,`if (${n.getByIndices("input_indices")} ${t.selectLastIndex>0?"<=":"<"} value) {
         value = ${n.getByIndices("input_indices")};
         best_index = i32(last_index);
       }`,"",r.setByOffset("global_idx","best_index")]};e.compute(Li("ArgMin",{hint:t.cacheKey,inputDependencies:["rank"]},[e.inputs[0]],i,[t.axis],7,t.keepDims),{inputs:[0]})},Ra=(e,t)=>{Vn(e.inputs);let i=(n,r,s)=>{let a=[];for(let o=0;o<n.rank;o++)(s.indexOf(o)>=0||s.length===0)&&a.push(`input_indices[${o}] = 0;`);return[`${a.join(`
`)}`,`var value = ${n.getByIndices("input_indices")};
var best_index : i32 = 0;`,`if (${n.getByIndices("input_indices")} ${t.selectLastIndex>0?">=":">"} value) {
         value = ${n.getByIndices("input_indices")};
         best_index = i32(last_index);
       }`,"",r.setByOffset("global_idx","best_index")]};e.compute(Li("argMax",{hint:t.cacheKey,inputDependencies:["rank"]},[e.inputs[0]],i,[t.axis],7,t.keepDims),{inputs:[0]})},Ln=e=>Be(e)}),Oa,Ui,Da,Ba,Fa,_i,Pa,Na,Un=E(()=>{ge(),$e(),zn(),xe(),Oa=(e,t)=>{let i=e[0],n=e[1],r=e[2],s=e[3],a=e[4],o=e[5];if(a&&o)throw new Error("Attention cannot have both past and attention_bias");if(i.dims.length!==3)throw new Error('Input "input" must have 3 dimensions');let l=i.dims[0],u=i.dims[1],d=i.dims[2];if(r.dims.length!==1)throw new Error('Input "bias" is expected to have 1 dimensions');if(n.dims.length!==2)throw new Error('Input "weights" is expected to have 2 dimensions');if(n.dims[0]!==d)throw new Error("Input 1 dimension 0 should have same length as dimension 2 of input 0");if(r.dims[0]!==n.dims[1])throw new Error('Input "bias" dimension 0 should have same length as dimension 1 of input "weights"');let c=r.dims[0]/3,p=c,h=p;if(t.qkvHiddenSizes.length>0){if(t.qkvHiddenSizes.length!==3)throw new Error("qkv_hidden_sizes attribute should have 3 elements");for(let T of t.qkvHiddenSizes)if(T%t.numHeads!==0)throw new Error("qkv_hidden_sizes should be divisible by num_heads");c=t.qkvHiddenSizes[0],p=t.qkvHiddenSizes[1],h=t.qkvHiddenSizes[2]}let m=u;if(c!==p)throw new Error("qkv_hidden_sizes first element should be same as the second");if(r.dims[0]!==c+p+h)throw new Error('Input "bias" dimension 0 should have same length as sum of Q/K/V hidden sizes');let _=0;if(a){if(p!==h)throw new Error('Input "past" expect k_hidden_size == v_hidden_size');if(a.dims.length!==5)throw new Error('Input "past" must have 5 dimensions');if(a.dims[0]!==2)throw new Error('Input "past" first dimension must be 2');if(a.dims[1]!==l)throw new Error('Input "past" second dimension must be batch_size');if(a.dims[2]!==t.numHeads)throw new Error('Input "past" third dimension must be num_heads');if(a.dims[4]!==p/t.numHeads)throw new Error('Input "past" fifth dimension must be k_hidden_size / num_heads');t.pastPresentShareBuffer||(_=a.dims[3])}let $=m+_,y=-1,g=0;if(s)throw new Error("Mask not supported");if(a)throw new Error("past is not supported");if(o){if(o.dims.length!==4)throw new Error('Input "attention_bias" must have 4 dimensions');if(o.dims[0]!==l||o.dims[1]!==t.numHeads||o.dims[2]!==u||o.dims[3]!==$)throw new Error('Expect "attention_bias" shape (batch_size, num_heads, sequence_length, total_sequence_length)')}return{batchSize:l,sequenceLength:u,pastSequenceLength:_,kvSequenceLength:m,totalSequenceLength:$,maxSequenceLength:y,inputHiddenSize:d,hiddenSize:c,vHiddenSize:h,headSize:Math.floor(c/t.numHeads),vHeadSize:Math.floor(h/t.numHeads),numHeads:t.numHeads,isUnidirectional:!1,pastPresentShareBuffer:!1,maskFilterValue:t.maskFilterValue,maskType:g,scale:t.scale,broadcastResPosBias:!1,passPastInKv:!1,qkvFormat:1}},Ui=(e,t,i)=>t&&e?`
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
    `,Da=(e,t,i,n,r,s,a,o)=>{let l=je(a?1:s),u=64,d=s/l;d<u&&(u=32);let c=Math.ceil(s/l/u),p=[{type:12,data:t},{type:12,data:i},{type:12,data:n},{type:12,data:r},{type:12,data:d},{type:12,data:c}],h=et(e.dataType,l),m=ot(1,l),_=["type"];a&&_.push("type"),o&&_.push("type");let $=y=>{let g=oe("x",e.dataType,e.dims,l),T=[g],x=a?F("seq_lens",a.dataType,a.dims):void 0;x&&T.push(x);let C=o?F("total_sequence_length_input",o.dataType,o.dims):void 0;C&&T.push(C);let R=ot(e.dataType),z=[{name:"batch_size",type:"u32"},{name:"num_heads",type:"u32"},{name:"past_sequence_length",type:"u32"},{name:"sequence_length",type:"u32"},{name:"total_sequence_length",type:"u32"},{name:"elements_per_thread",type:"u32"}];return`
  var<workgroup> thread_max: array<f32, ${u}>;
  var<workgroup> thread_sum: array<f32, ${u}>;
  ${y.registerUniforms(z).declareVariables(...T)}
  ${y.mainStart([u,1,1])}
    let batchIdx = workgroup_id.z / uniforms.num_heads;
    let headIdx = workgroup_id.z % uniforms.num_heads;
    let sequence_length = uniforms.sequence_length;
    var total_sequence_length = uniforms.total_sequence_length;
    ${Ui(x,C,!1)}
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
        x[offset + i] = ${g.type.value}(${R}(1.0) / ${R}(seq_causal_length));
      }
    } else {
      for (var i: u32 = 0; i < uniforms.elements_per_thread && i + local_offset < seq_causal_length; i++) {
        var f32input = ${m}(x[offset + i]);
        x[offset + i] = ${g.type.value}(exp(f32input - max_value) / sum);
      }
    }
      ${a?`
        for (var total_seq_id: u32 = seq_causal_length; total_seq_id + local_offset < uniforms.total_sequence_length; total_seq_id++) {
          x[offset + total_seq_id] = ${g.type.value}(${R}(0));
        }`:""};
  }`};return{name:"AttentionProbsSoftmax",shaderCache:{hint:`${u};${h};${l}`,inputDependencies:_},getShaderSource:$,getRunData:()=>({outputs:[],dispatchGroup:{x:1,y:r,z:t*i},programUniforms:p})}},Ba=(e,t,i,n,r,s,a,o,l)=>{let u=a+s.kvSequenceLength,d=[s.batchSize,s.numHeads,s.sequenceLength,u],c=e>1&&n,p=s.kvNumHeads?s.kvNumHeads:s.numHeads,h=c?[s.batchSize,p,u,s.headSize]:void 0,m=s.nReps?s.nReps:1,_=s.scale===0?1/Math.sqrt(s.headSize):s.scale,$=je(s.headSize),y=s.headSize/$,g=12,T={x:Math.ceil(u/g),y:Math.ceil(s.sequenceLength/g),z:s.batchSize*s.numHeads},x=[{type:12,data:s.sequenceLength},{type:12,data:y},{type:12,data:u},{type:12,data:s.numHeads},{type:12,data:s.headSize},{type:1,data:_},{type:12,data:a},{type:12,data:s.kvSequenceLength},{type:12,data:m}],C=c&&n&&O.size(n.dims)>0,R=["type","type"];C&&R.push("type"),r&&R.push("type"),o&&R.push("type"),l&&R.push("type");let z=[{dims:d,dataType:t.dataType,gpuDataType:0}];c&&z.push({dims:h,dataType:t.dataType,gpuDataType:0});let P=U=>{let re=F("q",t.dataType,t.dims,$),_e=F("key",i.dataType,i.dims,$),pe=[re,_e];if(C){let fe=F("past_key",n.dataType,n.dims,$);pe.push(fe)}r&&pe.push(F("attention_bias",r.dataType,r.dims));let be=o?F("seq_lens",o.dataType,o.dims):void 0;be&&pe.push(be);let ae=l?F("total_sequence_length_input",l.dataType,l.dims):void 0;ae&&pe.push(ae);let ke=oe("output",t.dataType,d),me=[ke];c&&me.push(oe("present_key",t.dataType,h,$));let ue=ot(1,$),De=[{name:"M",type:"u32"},{name:"K",type:"u32"},{name:"N",type:"u32"},{name:"num_heads",type:"u32"},{name:"head_size",type:"u32"},{name:"alpha",type:"f32"},{name:"past_sequence_length",type:"u32"},{name:"kv_sequence_length",type:"u32"},{name:"n_reps",type:"u32"}];return`
  const TILE_SIZE = ${g}u;

  var<workgroup> tileQ: array<${re.type.storage}, ${g*g}>;
  var<workgroup> tileK: array<${re.type.storage}, ${g*g}>;
  ${U.registerUniforms(De).declareVariables(...pe,...me)}
  ${U.mainStart([g,g,1])}
    // x holds the N and y holds the M
    let headIdx = workgroup_id.z % uniforms.num_heads;
    let kvHeadIdx = ${m===1?"headIdx":"headIdx / uniforms.n_reps"};
    let kv_num_heads = ${m===1?"uniforms.num_heads":"uniforms.num_heads / uniforms.n_reps"};
    let batchIdx = workgroup_id.z / uniforms.num_heads;
    let m = workgroup_id.y * TILE_SIZE;
    let n = workgroup_id.x * TILE_SIZE;
    let sequence_length = uniforms.M;
    var total_sequence_length = uniforms.N;
    ${Ui(be,ae,!0)}
    let absKvHeadIdx = batchIdx * kv_num_heads + kvHeadIdx;
    let qOffset = workgroup_id.z * uniforms.M * uniforms.K + m * uniforms.K;
    ${C&&c?"let pastKeyOffset = absKvHeadIdx * uniforms.past_sequence_length * uniforms.K;":""};
    let kOffset = absKvHeadIdx * uniforms.kv_sequence_length * uniforms.K;
    ${c?"let presentKeyOffset = absKvHeadIdx * uniforms.N * uniforms.K;":""}
    var value = ${ue}(0);
    for (var w: u32 = 0u; w < uniforms.K; w += TILE_SIZE) {
      if (global_id.y < uniforms.M && w + local_id.x < uniforms.K) {
        tileQ[TILE_SIZE * local_id.y + local_id.x] = q[qOffset + local_id.y * uniforms.K + w + local_id.x];
      }
      if (n + local_id.y < uniforms.N && w + local_id.x < uniforms.K) {
        var idx = TILE_SIZE * local_id.y + local_id.x;
      ${C&&c?`
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
          value += ${ue}(tileQ[TILE_SIZE * local_id.y + k] * tileK[TILE_SIZE * local_id.x + k]);
      }

      workgroupBarrier();
    }

    if (global_id.y < uniforms.M && global_id.x < total_sequence_length) {
      let headOffset = workgroup_id.z * uniforms.M * uniforms.N;
      let outputIdx = headOffset + global_id.y * uniforms.N + global_id.x;
      var sum: f32 = ${(()=>{switch($){case 1:return"value";case 2:return"value.x + value.y";case 4:return"value.x + value.y + value.z + value.w";default:throw new Error(`Unsupported components: ${$}`)}})()};
        output[outputIdx] = ${ke.type.value} (sum * uniforms.alpha) + ${r?"attention_bias[outputIdx]":"0.0"};
    }
  }`};return{name:"AttentionProbs",shaderCache:{hint:`${$};${r!==void 0};${n!==void 0};${e}`,inputDependencies:R},getRunData:()=>({outputs:z,dispatchGroup:T,programUniforms:x}),getShaderSource:P}},Fa=(e,t,i,n,r,s,a=void 0,o=void 0)=>{let l=s+r.kvSequenceLength,u=r.nReps?r.nReps:1,d=r.vHiddenSize*u,c=e>1&&n,p=r.kvNumHeads?r.kvNumHeads:r.numHeads,h=c?[r.batchSize,p,l,r.headSize]:void 0,m=[r.batchSize,r.sequenceLength,d],_=12,$={x:Math.ceil(r.vHeadSize/_),y:Math.ceil(r.sequenceLength/_),z:r.batchSize*r.numHeads},y=[{type:12,data:r.sequenceLength},{type:12,data:l},{type:12,data:r.vHeadSize},{type:12,data:r.numHeads},{type:12,data:r.headSize},{type:12,data:d},{type:12,data:s},{type:12,data:r.kvSequenceLength},{type:12,data:u}],g=c&&n&&O.size(n.dims)>0,T=["type","type"];g&&T.push("type"),a&&T.push("type"),o&&T.push("type");let x=[{dims:m,dataType:t.dataType,gpuDataType:0}];c&&x.push({dims:h,dataType:t.dataType,gpuDataType:0});let C=R=>{let z=F("probs",t.dataType,t.dims),P=F("v",i.dataType,i.dims),U=[z,P];g&&U.push(F("past_value",n.dataType,n.dims));let re=a?F("seq_lens",a.dataType,a.dims):void 0;a&&U.push(re);let _e=o?F("total_sequence_length_input",o.dataType,o.dims):void 0;o&&U.push(_e);let pe=[oe("output",t.dataType,m)];c&&pe.push(oe("present_value",t.dataType,h));let be=[{name:"M",type:"u32"},{name:"K",type:"u32"},{name:"N",type:"u32"},{name:"num_heads",type:"u32"},{name:"head_size",type:"u32"},{name:"v_hidden_size",type:"u32"},{name:"past_sequence_length",type:"u32"},{name:"kv_sequence_length",type:"u32"},{name:"n_reps",type:"u32"}];return`
  const TILE_SIZE = ${_}u;
  var<workgroup> tileQ: array<${z.type.value}, ${_*_}>;
  var<workgroup> tileV: array<${z.type.value}, ${_*_}>;
  ${R.registerUniforms(be).declareVariables(...U,...pe)}
  ${R.mainStart([_,_,1])}
   let headIdx = workgroup_id.z % uniforms.num_heads;
   let batchIdx = workgroup_id.z / uniforms.num_heads;
   let kvHeadIdx = ${u===1?"headIdx":"headIdx / uniforms.n_reps"};
   let kv_num_heads = ${u===1?"uniforms.num_heads":"uniforms.num_heads / uniforms.n_reps"};
   let m = global_id.y;
   let n = global_id.x;
   let sequence_length = uniforms.M;
   var total_sequence_length = uniforms.K;
   ${Ui(re,_e,!0)}
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
  }`};return{name:"AttentionScore",shaderCache:{hint:`${n!==void 0};${e}`,inputDependencies:T},getRunData:()=>({outputs:x,dispatchGroup:$,programUniforms:y}),getShaderSource:C}},_i=(e,t,i,n,r,s,a,o,l,u,d=void 0,c=void 0)=>{let p=Math.min(e.outputCount,1+(a?1:0)+(o?1:0)),h=p>1?u.pastSequenceLength:0,m=h+u.kvSequenceLength,_=l&&O.size(l.dims)>0?l:void 0,$=[t,i];p>1&&a&&O.size(a.dims)>0&&$.push(a),_&&$.push(_),d&&$.push(d),c&&$.push(c);let y=e.compute(Ba(p,t,i,a,_,u,h,d,c),{inputs:$,outputs:p>1?[-1,1]:[-1]})[0];e.compute(Da(y,u.batchSize,u.numHeads,h,u.sequenceLength,m,d,c),{inputs:d&&c?[y,d,c]:[y],outputs:[]});let g=[y,n];p>1&&o&&O.size(o.dims)>0&&g.push(o),d&&g.push(d),c&&g.push(c),e.compute(Fa(p,y,n,o,u,h,d,c),{inputs:g,outputs:p>1?[0,2]:[0]})},Pa=(e,t)=>{let i=[t.batchSize,t.numHeads,t.sequenceLength,t.headSize],n=t.sequenceLength,r=t.inputHiddenSize,s=t.headSize,a=12,o={x:Math.ceil(t.headSize/a),y:Math.ceil(t.sequenceLength/a),z:t.batchSize*t.numHeads},l=[e.inputs[0],e.inputs[1],e.inputs[2]],u=[{type:12,data:n},{type:12,data:r},{type:12,data:s},{type:12,data:t.numHeads},{type:12,data:t.headSize},{type:12,data:t.hiddenSize},{type:12,data:t.hiddenSize+t.hiddenSize+t.vHiddenSize}],d=c=>{let p=oe("output_q",l[0].dataType,i),h=oe("output_k",l[0].dataType,i),m=oe("output_v",l[0].dataType,i),_=F("input",l[0].dataType,l[0].dims),$=F("weight",l[1].dataType,l[1].dims),y=F("bias",l[2].dataType,l[2].dims),g=_.type.storage,T=[{name:"M",type:"u32"},{name:"K",type:"u32"},{name:"N",type:"u32"},{name:"num_heads",type:"u32"},{name:"head_size",type:"u32"},{name:"hidden_size",type:"u32"},{name:"ldb",type:"u32"}];return`
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
  }`};return e.compute({name:"AttentionPrepare",shaderCache:{inputDependencies:["type","type","type"]},getRunData:()=>({outputs:[{dims:i,dataType:e.inputs[0].dataType,gpuDataType:0},{dims:i,dataType:e.inputs[0].dataType,gpuDataType:0},{dims:i,dataType:e.inputs[0].dataType,gpuDataType:0}],dispatchGroup:o,programUniforms:u}),getShaderSource:d},{inputs:l,outputs:[-1,-1,-1]})},Na=(e,t)=>{let i=Oa(e.inputs,t),[n,r,s]=Pa(e,i);return _i(e,n,r,s,e.inputs[4],void 0,void 0,void 0,e.inputs[5],i)}}),Va,La,Ua,qa,$p=E(()=>{mt(),ge(),$e(),He(),xe(),Va=(e,t)=>{if(!e||e.length!==5)throw new Error("BatchNormalization requires 5 inputs");let i=(n,r,s)=>{let a=r.length;if(a!==n.length)throw new Error(`${s}: num dimensions != ${a}`);r.forEach((o,l)=>{if(o!==n[l])throw new Error(`${s}: dim[${l}] do not match`)})};if(e[0].dims.length>1){let n=t.format==="NHWC"?t.spatial?e[0].dims.slice(-1):e[0].dims.slice(-1).concat(e[0].dims.slice(1,e[0].dims.length-1)):e[0].dims.slice(1,t.spatial?2:void 0);i(e[1].dims,n,"Invalid input scale"),i(e[2].dims,n,"Invalid input B"),i(e[3].dims,n,"Invalid input mean"),i(e[4].dims,n,"Invalid input var")}else i(e[1].dims,[1],"Invalid input scale"),i(e[2].dims,[1],"Invalid input B"),i(e[3].dims,[1],"Invalid input mean"),i(e[4].dims,[1],"Invalid input var")},La=(e,t)=>{let{epsilon:i,spatial:n,format:r}=t,s=e[0].dims,a=n?je(s[s.length-1]):1,o=r==="NHWC"&&s.length>1?a:1,l=O.size(s)/a,u=n,d=u?s.length:s,c=F("x",e[0].dataType,e[0].dims,a),p=F("scale",e[1].dataType,e[1].dims,o),h=F("bias",e[2].dataType,e[2].dims,o),m=F("inputMean",e[3].dataType,e[3].dims,o),_=F("inputVar",e[4].dataType,e[4].dims,o),$=oe("y",e[0].dataType,d,a),y=()=>{let T="";if(n)T=`let cOffset = ${s.length===1?"0u":r==="NHWC"?`outputIndices[${s.length-1}] / ${a}`:"outputIndices[1]"};`;else if(r==="NCHW")T=`
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
  }`;return{name:"BatchNormalization",shaderCache:{hint:`${t.epsilon}_${t.format}_${n}_${a}`,inputDependencies:u?["rank","type","type","type","type"]:void 0},getShaderSource:g,getRunData:()=>({outputs:[{dims:e[0].dims,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:u?[{type:12,data:l},...de(s)]:[{type:12,data:l}]})}},Ua=e=>Be(e),qa=(e,t)=>{let{inputs:i,outputCount:n}=e,r=Ua({...t,outputCount:n});if(se.webgpu.validateInputContent&&Va(i,r),t.trainingMode)throw new Error("BatchNormalization trainingMode is not supported yet.");e.compute(La(i,r))}}),Wa,Ga,ja,xp=E(()=>{$e(),xe(),Wa=e=>{if(e[0].dims.length!==3)throw new Error("input should have 3 dimensions");if(![320,640,1280].includes(e[0].dims[2]))throw new Error("number of channels should be 320, 640 or 1280");if(e[1].dims.length!==1)throw new Error("bias is expected to have 1 dimensions");if(e[0].dims[2]!==e[1].dims[0])throw new Error("last dimension of input and bias are not the same")},Ga=e=>{let t=e[0].dims,i=e[0].dims[2],n=O.size(t)/4,r=e[0].dataType,s=F("input",r,t,4),a=F("bias",r,[i],4),o=F("residual",r,t,4),l=oe("output",r,t,4);return{name:"BiasAdd",getRunData:()=>({outputs:[{dims:t,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(n/64)}}),getShaderSource:u=>`
  const channels = ${i}u / 4;
  ${u.declareVariables(s,a,o,l)}

  ${u.mainStart()}
    ${u.guardAgainstOutOfBoundsWorkgroupSizes(n)}
    let value = ${s.getByOffset("global_idx")}
      + ${a.getByOffset("global_idx % channels")} + ${o.getByOffset("global_idx")};
    ${l.setByOffset("global_idx","value")}
  }`}},ja=e=>{Wa(e.inputs),e.compute(Ga(e.inputs))}}),Ha,Oe,Ka,Za,Qa,Xa,Ya,Ja,eo,to,io,no,ro,so,ao,oo,yi,lo,qi,uo,co,po,fo,ho,mo,go,_o,yo,wo,bo,vo,$o,xo,So,ko,qn,To,Wn,Gn,Eo,Co,Io,Ao,zo,Mo,jn=E(()=>{ge(),$e(),He(),xe(),Ha=(e,t,i,n,r,s,a)=>{let o=Math.ceil(t/4),l="";typeof r=="string"?l=`${r}(a)`:l=r("a");let u=F("inputData",i,[o],4),d=oe("outputData",n,[o],4),c=[{name:"vec_size",type:"u32"}];return a&&c.push(...a),`
      ${e.registerUniforms(c).declareVariables(u,d)}

  ${s??""}

  ${e.mainStart()}
    ${e.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.vec_size")}

    let a = ${u.getByOffset("global_idx")};
    ${d.setByOffset("global_idx",l)}
  }`},Oe=(e,t,i,n,r,s=e.dataType,a,o)=>{let l=[{type:12,data:Math.ceil(O.size(e.dims)/4)}];return a&&l.push(...a),{name:t,shaderCache:{hint:r,inputDependencies:["type"]},getShaderSource:u=>Ha(u,O.size(e.dims),e.dataType,s,i,n,o),getRunData:u=>({outputs:[{dims:e.dims,dataType:s}],dispatchGroup:{x:Math.ceil(O.size(u[0].dims)/64/4)},programUniforms:l})}},Ka=e=>{e.compute(Oe(e.inputs[0],"Abs","abs"))},Za=e=>{e.compute(Oe(e.inputs[0],"Acos","acos"))},Qa=e=>{e.compute(Oe(e.inputs[0],"Acosh","acosh"))},Xa=e=>{e.compute(Oe(e.inputs[0],"Asin","asin"))},Ya=e=>{e.compute(Oe(e.inputs[0],"Asinh","asinh"))},Ja=e=>{e.compute(Oe(e.inputs[0],"Atan","atan"))},eo=e=>{e.compute(Oe(e.inputs[0],"Atanh","atanh"))},to=e=>Be(e),io=(e,t)=>{let i;switch(t.to){case 10:i="vec4<f16>";break;case 1:i="vec4<f32>";break;case 12:i="vec4<u32>";break;case 6:i="vec4<i32>";break;case 9:i="vec4<bool>";break;default:throw new RangeError(`not supported type (specified in attribute 'to' from 'Cast' operator): ${t.to}`)}e.compute(Oe(e.inputs[0],"Cast",i,void 0,t.cacheKey,t.to))},no=e=>{let t,i,n=e.length>=2&&e[1].data!==0,r=e.length>=3&&e[2].data!==0;switch(e[0].dataType){case 1:t=n?e[1].getFloat32Array()[0]:-34028234663852886e22,i=r?e[2].getFloat32Array()[0]:34028234663852886e22;break;case 10:t=n?e[1].getUint16Array()[0]:64511,i=r?e[2].getUint16Array()[0]:31743;break;default:throw new Error("Unsupport data type")}return Be({min:t,max:i})},ro=(e,t)=>{let i=t||no(e.inputs),n=ot(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Clip",r=>`clamp(${r}, vec4<${n}>(uniforms.min), vec4<${n}>(uniforms.max))`,void 0,i.cacheKey,void 0,[{type:e.inputs[0].dataType,data:i.min},{type:e.inputs[0].dataType,data:i.max}],[{name:"min",type:n},{name:"max",type:n}]),{inputs:[0]})},so=e=>{e.compute(Oe(e.inputs[0],"Ceil","ceil"))},ao=e=>{e.compute(Oe(e.inputs[0],"Cos","cos"))},oo=e=>{e.compute(Oe(e.inputs[0],"Cosh","cosh"))},yi=e=>Be(e),lo=(e,t)=>{let i=ot(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Elu",n=>`elu_vf32(${n})`,`
  const elu_alpha_ = ${i}(${t.alpha});

  fn elu_f32(a: ${i}) -> ${i} {
  return select((exp(a) - 1.0) * elu_alpha_, a, a >= 0.0);
  }

  fn elu_vf32(v: vec4<${i}>) -> vec4<${i}> {
  return vec4(elu_f32(v.x), elu_f32(v.y), elu_f32(v.z), elu_f32(v.w));
  }`,t.cacheKey))},qi=(e="f32")=>`
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
}`,uo=e=>{let t=ot(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Erf",i=>`erf_vf32(${i})`,qi(t)))},co=e=>{e.compute(Oe(e.inputs[0],"Exp","exp"))},po=e=>{e.compute(Oe(e.inputs[0],"Floor","floor"))},fo=e=>{let t=ot(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Gelu",i=>`0.5 * ${i} * (1.0 + erf_vf32(${i} * 0.7071067811865475))`,qi(t)))},ho=(e,t)=>{let i=ot(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"LeakyRelu",n=>`select(leaky_relu_alpha_ * ${n}, ${n}, ${n} >= vec4<${i}>(0.0))`,`const leaky_relu_alpha_ = ${i}(${t.alpha});`,t.cacheKey))},mo=e=>{e.compute(Oe(e.inputs[0],"Not",t=>`!${t}`))},go=e=>{e.compute(Oe(e.inputs[0],"Neg",t=>`-${t}`))},_o=e=>{e.compute(Oe(e.inputs[0],"Reciprocal",t=>`1.0/${t}`))},yo=e=>{let t=ot(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"Relu",i=>`select(vec4<${t}>(0.0), ${i}, ${i} > vec4<${t}>(0.0))`))},wo=e=>{e.compute(Oe(e.inputs[0],"Sigmoid",t=>`(1.0 / (1.0 + exp(-${t})))`))},bo=e=>Be(e),vo=(e,t)=>{let i=ot(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"HardSigmoid",n=>`max(vec4<${i}>(0.0), min(vec4<${i}>(1.0), ${t.alpha} * ${n} + vec4<${i}>(${t.beta})))`,void 0,t.cacheKey))},$o=e=>{e.compute(Oe(e.inputs[0],"Sin","sin"))},xo=e=>{e.compute(Oe(e.inputs[0],"Sinh","sinh"))},So=e=>{e.compute(Oe(e.inputs[0],"Sqrt","sqrt"))},ko=e=>{e.compute(Oe(e.inputs[0],"Tan","tan"))},qn=e=>`sign(${e}) * (1 - exp(-2 * abs(${e}))) / (1 + exp(-2 * abs(${e})))`,To=e=>{e.compute(Oe(e.inputs[0],"Tanh",qn))},Wn=(e="f32")=>`
const fast_gelu_a: ${e} = 0.5;
const fast_gelu_b: ${e} = 0.7978845608028654;
const fast_gelu_c: ${e} = 0.035677408136300125;

fn tanh_v(v: vec4<${e}>) -> vec4<${e}> {
  return ${qn("v")};
}
`,Gn=e=>`(fast_gelu_a + fast_gelu_a * tanh_v(${e} * (fast_gelu_c * ${e} * ${e} + fast_gelu_b))) * ${e}`,Eo=e=>{let t=ot(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"FastGelu",Gn,Wn(t),void 0,e.inputs[0].dataType))},Co=(e,t)=>{let i=ot(e.inputs[0].dataType);return e.compute(Oe(e.inputs[0],"ThresholdedRelu",n=>`select(vec4<${i}>(0.0), ${n}, ${n} > thresholded_relu_alpha_)`,`const thresholded_relu_alpha_ = vec4<${i}>(${t.alpha});`,t.cacheKey)),0},Io=e=>{e.compute(Oe(e.inputs[0],"Log","log"))},Ao=(e,t)=>`
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
`,zo=e=>`quick_gelu_impl(${e})`,Mo=(e,t)=>{let i=ot(e.inputs[0].dataType);e.compute(Oe(e.inputs[0],"QuickGelu",zo,Ao(i,t.alpha),t.cacheKey,e.inputs[0].dataType))}}),Ro,Oo,Do,Sp=E(()=>{$e(),xe(),jn(),Ro=e=>{if(e[0].dims.length!==3)throw new Error("input should have 3 dimensions");if(![2560,5120,10240].includes(e[0].dims[2]))throw new Error("hidden state should be 2560, 5120 or 10240");if(e[1].dims.length!==1)throw new Error("bias is expected to have 1 dimensions");if(e[0].dims[2]!==e[1].dims[0])throw new Error("last dimension of input and bias are not the same")},Oo=e=>{let t=e[0].dims.slice();t[2]=t[2]/2;let i=F("input",e[0].dataType,e[0].dims,4),n=F("bias",e[0].dataType,[e[0].dims[2]],4),r=oe("output",e[0].dataType,t,4),s=O.size(t)/4,a=et(e[0].dataType);return{name:"BiasSplitGelu",getRunData:()=>({outputs:[{dims:t,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(s/64)}}),getShaderSource:o=>`
  const M_SQRT2 = sqrt(2.0);
  const halfChannels = ${e[0].dims[2]/4/2}u;

  ${o.declareVariables(i,n,r)}

  ${qi(a)}

  ${o.mainStart()}
    ${o.guardAgainstOutOfBoundsWorkgroupSizes(s)}
    let biasIdx = global_idx % halfChannels;
    let batchIndex = global_idx / halfChannels;
    let inputOffset = biasIdx + batchIndex * halfChannels * 2;
    let valueLeft = input[inputOffset] + bias[biasIdx];
    let valueRight = input[inputOffset + halfChannels] + bias[biasIdx + halfChannels];
    let geluRight = valueRight * 0.5 * (erf_vf32(valueRight / M_SQRT2) + 1);

    ${r.setByOffset("global_idx","valueLeft * geluRight")}
  }`}},Do=e=>{Ro(e.inputs),e.compute(Oo(e.inputs))}}),Bo,Fo,kt,Po,No,Vo,Lo,Uo,qo,Wo,Go,jo,Ho,kp=E(()=>{ge(),$e(),xe(),Bo=(e,t,i,n,r,s,a,o,l,u,d,c)=>{let p,h;typeof o=="string"?p=h=(g,T)=>`${o}((${g}),(${T}))`:typeof o=="function"?p=h=o:(p=o.scalar,h=o.vector);let m=oe("outputData",d,n.length,4),_=F("aData",l,t.length,4),$=F("bData",u,i.length,4),y;if(r)if(s){let g=O.size(t)===1,T=O.size(i)===1,x=t.length>0&&t[t.length-1]%4===0,C=i.length>0&&i[i.length-1]%4===0;g||T?y=m.setByOffset("global_idx",h(g?`${_.type.value}(${_.getByOffset("0")}.x)`:_.getByOffset("global_idx"),T?`${$.type.value}(${$.getByOffset("0")}.x)`:$.getByOffset("global_idx"))):y=`
            let outputIndices = ${m.offsetToIndices("global_idx * 4u")};
            let offsetA = ${_.broadcastedIndicesToOffset("outputIndices",m)};
            let offsetB = ${$.broadcastedIndicesToOffset("outputIndices",m)};
            ${m.setByOffset("global_idx",h(a||x?_.getByOffset("offsetA / 4u"):`${_.type.value}(${_.getByOffset("offsetA / 4u")}[offsetA % 4u])`,a||C?$.getByOffset("offsetB / 4u"):`${$.type.value}(${$.getByOffset("offsetB / 4u")}[offsetB % 4u])`))}
          `}else y=m.setByOffset("global_idx",h(_.getByOffset("global_idx"),$.getByOffset("global_idx")));else{if(!s)throw new Error("no necessary to use scalar implementation for element-wise binary op implementation.");let g=(T,x,C="")=>{let R=`aData[indexA${x}][componentA${x}]`,z=`bData[indexB${x}][componentB${x}]`;return`
            let outputIndices${x} = ${m.offsetToIndices(`global_idx * 4u + ${x}u`)};
            let offsetA${x} = ${_.broadcastedIndicesToOffset(`outputIndices${x}`,m)};
            let offsetB${x} = ${$.broadcastedIndicesToOffset(`outputIndices${x}`,m)};
            let indexA${x} = offsetA${x} / 4u;
            let indexB${x} = offsetB${x} / 4u;
            let componentA${x} = offsetA${x} % 4u;
            let componentB${x} = offsetB${x} % 4u;
            ${T}[${x}] = ${C}(${p(R,z)});
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
      }`},Fo=(e,t,i,n,r,s,a=i.dataType)=>{let o=i.dims.map(_=>Number(_)??1),l=n.dims.map(_=>Number(_)??1),u=!O.areEqual(o,l),d=o,c=O.size(o),p=!1,h=!1,m=[u];if(u){let _=si.calcShape(o,l,!1);if(!_)throw new Error("Can't perform binary op on the given tensors");d=_.slice(),c=O.size(d);let $=O.size(o)===1,y=O.size(l)===1,g=o.length>0&&o[o.length-1]%4===0,T=l.length>0&&l[l.length-1]%4===0;m.push($),m.push(y),m.push(g),m.push(T);let x=1;for(let C=1;C<d.length;C++){let R=o[o.length-C],z=l[l.length-C];if(R===z)x*=R;else break}x%4===0?(h=!0,p=!0):($||y||g||T)&&(p=!0)}else p=!0;return m.push(p),{name:e,shaderCache:{hint:t+m.map(_=>_.toString()).join("_"),inputDependencies:["rank","rank"]},getShaderSource:_=>Bo(_,o,l,d,p,u,h,r,i.dataType,n.dataType,a,s),getRunData:()=>({outputs:[{dims:d,dataType:a}],dispatchGroup:{x:Math.ceil(c/64/4)},programUniforms:[{type:12,data:Math.ceil(O.size(d)/4)},...de(o,l,d)]})}},kt=(e,t,i,n,r,s)=>{e.compute(Fo(t,r??"",e.inputs[0],e.inputs[1],i,n,s))},Po=e=>{kt(e,"Add",(t,i)=>`${t}+${i}`)},No=e=>{kt(e,"Div",(t,i)=>`${t}/${i}`)},Vo=e=>{kt(e,"Equal",{scalar:(t,i)=>`u32(${t}==${i})`,vector:(t,i)=>`vec4<u32>(${t}==${i})`},void 0,void 0,9)},Lo=e=>{kt(e,"Mul",(t,i)=>`${t}*${i}`)},Uo=e=>{let t=F("input",e.inputs[0].dataType,e.inputs[0].dims).type.value;kt(e,"Pow",{scalar:(i,n)=>`pow_custom(${i},${n})`,vector:(i,n)=>`pow_vector_custom(${i},${n})`},`
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
      `)},qo=e=>{kt(e,"Sub",(t,i)=>`${t}-${i}`)},Wo=e=>{kt(e,"Greater",{scalar:(t,i)=>`u32(${t}>${i})`,vector:(t,i)=>`vec4<u32>(${t}>${i})`},void 0,void 0,9)},Go=e=>{kt(e,"Less",{scalar:(t,i)=>`u32(${t}<${i})`,vector:(t,i)=>`vec4<u32>(${t}<${i})`},void 0,void 0,9)},jo=e=>{kt(e,"GreaterOrEqual",{scalar:(t,i)=>`u32(${t}>=${i})`,vector:(t,i)=>`vec4<u32>(${t}>=${i})`},void 0,void 0,9)},Ho=e=>{kt(e,"LessOrEqual",{scalar:(t,i)=>`u32(${t}<=${i})`,vector:(t,i)=>`vec4<u32>(${t}<=${i})`},void 0,void 0,9)}}),Ko,Zo,Qo,Xo,Yo,Jo,Tp=E(()=>{ge(),$e(),He(),xe(),Ko=(e,t)=>{if(!e||e.length<1)throw new Error("too few inputs");let i=0,n=e[i],r=n.dataType,s=n.dims.length;e.forEach((a,o)=>{if(o!==i){if(a.dataType!==r)throw new Error("input tensors should be one type");if(a.dims.length!==s)throw new Error("input tensors should have the same shape");a.dims.forEach((l,u)=>{if(u!==t&&l!==n.dims[u])throw new Error("non concat dimensions must match")})}})},Zo=(e,t)=>`
  fn calculateInputIndex(index: u32) -> u32 {
    let sizeInConcatAxis = array<u32, ${e}u>(${t});
    for (var i: u32 = 0u; i < ${e}; i += 1u ) {
      if (index < sizeInConcatAxis[i]) {
        return i;
      }
    }
    return ${e}u;
  }`,Qo=(e,t)=>{let i=e.length,n=[];for(let r=0;r<i;++r){let s=t.setByOffset("global_idx",e[r].getByIndices("indices"));i===1?n.push(s):r===0?n.push(`if (inputIndex == ${r}u) { ${s} }`):r===i-1?n.push(`else { ${s} }`):n.push(`else if (inputIndex == ${r}) { ${s} }`)}return n.join(`
`)},Xo=(e,t,i,n)=>{let r=O.size(i),s=new Array(e.length),a=new Array(e.length),o=0,l=[],u=[],d=[{type:12,data:r}];for(let _=0;_<e.length;++_)o+=e[_].dims[t],s[_]=o,u.push(e[_].dims.length),a[_]=F(`input${_}`,n,u[_]),l.push("rank"),d.push({type:12,data:s[_]});for(let _=0;_<e.length;++_)d.push(...de(e[_].dims));d.push(...de(i));let c=oe("output",n,i.length),p=c.indicesGet("indices",t),h=Array.from(Array(s.length).keys()).map(_=>`uniforms.sizeInConcatAxis${_}`).join(","),m=_=>`

  ${(()=>{_.registerUniform("outputSize","u32");for(let $=0;$<e.length;$++)_.registerUniform(`sizeInConcatAxis${$}`,"u32");return _.declareVariables(...a,c)})()}

  ${Zo(s.length,h)}

  ${_.mainStart()}
    ${_.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}

    var indices = ${c.offsetToIndices("global_idx")};

    let inputIndex = calculateInputIndex(${p});
    if (inputIndex != 0u) {
      let sizeInConcatAxis = array<u32, ${s.length}u>(${h});
      ${p} -= sizeInConcatAxis[inputIndex - 1u];
    }

    ${Qo(a,c)}
  }`;return{name:"Concat",shaderCache:{hint:`${t}`,inputDependencies:l},getRunData:()=>({outputs:[{dims:i,dataType:n}],dispatchGroup:{x:Math.ceil(r/64)},programUniforms:d}),getShaderSource:m}},Yo=(e,t)=>{let i=e.inputs,n=i[0].dims,r=O.normalizeAxis(t.axis,n.length);Ko(i,r);let s=n.slice();s[r]=i.reduce((o,l)=>o+(l.dims.length>r?l.dims[r]:0),0);let a=i.filter(o=>O.size(o.dims)>0);e.compute(Xo(a,r,s,i[0].dataType),{inputs:a})},Jo=e=>Be({axis:e.axis})}),jt,Ht,Kt,Hn,Zt=E(()=>{ge(),$e(),jt=(e,t,i="f32")=>{switch(e.activation){case"Relu":return`value = max(value, ${t}(0.0));`;case"Sigmoid":return`value = (${t}(1.0) / (${t}(1.0) + exp(-value)));`;case"Clip":return`value = clamp(value, ${t}(${i}(uniforms.clip_min)), ${t}(${i}(uniforms.clip_max)));`;case"HardSigmoid":return`value = max(${t}(0.0), min(${t}(1.0), ${i}(uniforms.alpha) * value + ${i}(uniforms.beta)));`;case"LeakyRelu":return`value = select(${i}(uniforms.alpha) * value, value, value >= ${t}(0.0));`;case"Tanh":return`let e2x = exp(-2.0 * abs(value));
              value = sign(value) * (1.0 - e2x) / (1.0 + e2x);
        `;case"":return"";default:throw new Error(`Unsupported activation ${e.activation}`)}},Ht=(e,t)=>{e.activation==="Clip"?t.push({type:1,data:e.clipMax},{type:1,data:e.clipMin}):e.activation==="HardSigmoid"?t.push({type:1,data:e.alpha},{type:1,data:e.beta}):e.activation==="LeakyRelu"&&t.push({type:1,data:e.alpha})},Kt=(e,t)=>{e.activation==="Clip"?t.push({name:"clip_max",type:"f32"},{name:"clip_min",type:"f32"}):e.activation==="HardSigmoid"?t.push({name:"alpha",type:"f32"},{name:"beta",type:"f32"}):e.activation==="LeakyRelu"&&t.push({name:"alpha",type:"f32"})},Hn=e=>{let t=e?.activation||"";if(t==="HardSigmoid"){let[i,n]=e?.activation_params||[.2,.5];return{activation:t,alpha:i,beta:n}}else if(t==="Clip"){let[i,n]=e?.activation_params||[vs,$s];return{activation:t,clipMax:n,clipMin:i}}else if(t==="LeakyRelu"){let[i]=e?.activation_params||[.01];return{activation:t,alpha:i}}return{activation:t}}}),it,el,Kn=E(()=>{it=(e,t)=>{switch(e){case 1:return t;case 2:return`vec2<${t}>`;case 3:return`vec3<${t}>`;case 4:return`vec4<${t}>`;default:throw new Error(`${e}-component is not supported.`)}},el=e=>`
      ${e?"value = value + getBiasByOutputCoords(coords);":""}
      `}),tl,Ep=E(()=>{tl=e=>`
fn getIndexFromCoords4D(coords : vec4<i32>, shape : vec4<i32>) -> i32 {
  return dot(coords, vec4<i32>(
      shape.y * shape.z * shape.w, shape.z * shape.w, shape.w, 1));
}
fn getOutputIndexFromCoords(coords : vec4<i32>) -> i32 {
  return dot(coords, vec4<i32>(
    i32(${e}.x), i32(${e}.y), i32(${e}.z), 1));
}
`}),wi,Zn,Qn=E(()=>{ge(),$e(),xe(),Zt(),wi=(e,t,i,n,r)=>{let s=n-i;return`
      ${Array.from({length:i}).map((a,o)=>`
      if (${le(t.shape,o,t.rank)} != 1) {
        ${t.indicesSet(e,o,le(r,o+s,n))}
      } else {
        ${t.indicesSet(e,o,0)}
      }`).join("")}
`},Zn=(e,t,i,n,r=!1,s)=>{let a=e[0].dims,o=e[1].dims,l=a[a.length-2],u=o[o.length-1],d=a[a.length-1],c=je(u),p=je(d),h=je(l),m=O.size(i)/c/h,_=e.length>2,$=n?n.slice(0,-2):i.slice(0,-2),y=[O.size($),l,u],g=[{type:12,data:m},{type:12,data:l},{type:12,data:u},{type:12,data:d}];Ht(t,g),g.push(...de($,a,o)),_&&g.push(...de(e[2].dims)),g.push(...de(y));let T=x=>{let C=Bn("batch_dims",e[0].dataType,$.length),R=F("a",e[0].dataType,a.length,p),z=F("b",e[1].dataType,o.length,c),P=oe("output",e[0].dataType,y.length,c),U=et(P.type.tensor),re=jt(t,P.type.value,U),_e=[R,z],pe="";if(_){let ke=r?c:1;_e.push(F("bias",e[2].dataType,e[2].dims.length,ke)),pe=`${r?`value += bias[col / ${ke}];`:`value += ${P.type.value}(bias[row + i]);`}`}let be=[{name:"output_size",type:"u32"},{name:"M",type:"u32"},{name:"N",type:"u32"},{name:"K",type:"u32"}];Kt(t,be);let ae=()=>{let ke=`var a_data: ${R.type.value};`;for(let me=0;me<p;me++)ke+=`
              let b_data${me} = b[(b_offset + (k + ${me}) * uniforms.N + col) / ${c}];`;for(let me=0;me<h;me++){ke+=`a_data = a[(a_offset + (row + ${me}) * uniforms.K + k) / ${p}];`;for(let ue=0;ue<p;ue++)ke+=`
            values[${me}] = fma(${z.type.value}(a_data${p===1?"":`[${ue}]`}), b_data${ue}, values[${me}]);
`}return ke};return`
  ${x.registerUniforms(be).registerInternalVariables(C).declareVariables(..._e,P)}
  ${x.mainStart()}
    ${x.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    let col = (global_idx % (uniforms.N / ${c})) * ${c};
    var index1 = global_idx / (uniforms.N / ${c});
    let stride1 = uniforms.M / ${h};
    let row = (index1 % stride1) * ${h};
    let batch = index1 / stride1;

    ${i.length===2?"":`let batch_indices = ${C.offsetToIndices("batch")};`}

    var a_indices: ${R.type.indices};
    ${wi("a_indices",R,R.rank-2,C.rank,"batch_indices")}
    ${R.indicesSet("a_indices",R.rank-2,0)}
    ${R.indicesSet("a_indices",R.rank-1,0)}
    let a_offset = ${R.indicesToOffset("a_indices")};

    var b_indices: ${z.type.indices};
    ${wi("b_indices",z,z.rank-2,C.rank,"batch_indices")}
    ${z.indicesSet("b_indices",z.rank-2,0)}
    ${z.indicesSet("b_indices",z.rank-1,0)}
    let b_offset = ${z.indicesToOffset("b_indices")};
    var values: array<${P.type.value}, ${h}>;
    for (var k: u32 = 0u; k < uniforms.K; k = k + ${p}) {
      ${ae()}
    }
    for (var i = 0u; i < ${h}u; i++) {
      var value = values[i];
      ${pe}
      ${re}
      let cur_indices = ${P.type.indices}(batch, row + i, col);
      let offset = ${P.indicesToOffset("cur_indices")};
      ${P.setByOffset(`offset / ${c}`,"value")};
    }
  }
  `};return{name:"MatMulNaive",shaderCache:{hint:`${t.activation};${c};${p};${h};${r}`,inputDependencies:_?["rank","rank","rank"]:["rank","rank"]},getRunData:()=>({outputs:[{dims:s?s(i):i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(m/64)},programUniforms:g}),getShaderSource:T}}}),il,nl,Xn,Yn,rl,Jn,sl,Wi,er=E(()=>{ge(),$e(),xe(),Zt(),Qn(),Kn(),il=(e,t)=>e?`
        mm_Asub[inputRow][inputCol] = mm_readA(batch,
          kStart + inputRow,
          globalRowStart / innerElementSize + inputCol${t?", batchIndices":""});
        `:`
        mm_Asub[inputRow][inputCol] = mm_readA(batch,
          globalRow + innerRow,
          kStart / innerElementSize + inputCol${t?", batchIndices":""});
        `,nl=(e,t)=>e?`
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
        }`,Xn=(e,t,i="f32",n,r=!1,s=32,a=!1,o=32)=>{let l=t[1]*e[1],u=t[0]*e[0],d=r?l:s,c=r?s:l,p=d/t[0],h=s/t[1];if(!((r&&p===4&&e[1]===4||!r&&(p===3||p===4))&&d%t[0]===0&&s%t[1]===0&&e[0]===4))throw new Error(`If transposeA ${r} is true, innerElementSize ${p} and workPerThread[1] ${e[1]} must be 4.
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
          ${il(r,n)}
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

          ${nl(r,p)}
      }

      workgroupBarrier();
  }

  for (var innerRow = 0; innerRow < rowPerThread; innerRow = innerRow + 1) {
      mm_write(batch, globalRow + innerRow, globalCol, acc[innerRow]);
  }
}`},Yn=(e,t)=>e?`
            mm_Asub[inputRow][inputCol] = mm_readA(batch,
              kStart + inputRow,
              globalRowStart + inputCol${t?", batchIndices":""});
            `:`
            mm_Asub[inputRow][inputCol] = mm_readA(batch,
              globalRowStart + inputRow,
              kStart + inputCol${t?", batchIndices":""});
            `,rl=e=>e?"let ACached = mm_Asub[k][tileRow + innerRow];":"let ACached = mm_Asub[tileRow + innerRow][k];",Jn=(e,t,i="f32",n,r=!1,s=32,a=!1,o=32,l=!1)=>{let u=e[1]*t[1],d=e[0]*t[0],c=r?u:s,p=r?s:u;if(!(p%t[1]===0&&c%t[0]===0&&s%t[1]===0))throw new Error(`tileAHight ${p} must be divisible by workgroupSize[1]${t[1]}, tileAWidth ${c} must be divisible by workgroupSize[0]${t[0]}, tileInner ${s} must be divisible by workgroupSize[1]${t[1]}`);let h=p/t[1],m=c/t[0],_=s/t[1],$=l?`
    let localRow = i32(localId.y);
    let localCol = i32(localId.x);
    let globalRowStart = i32(workgroupId.y) * ${u};
    let globalColStart = i32(workgroupId.x) * ${d};

    // Loop over shared dimension.
    for (var t = 0; t < num_tiles; t = t + 1) {
      // Load one tile of A into local memory.
      for (var inputRow = localRow; inputRow < ${p}; inputRow = inputRow + ${t[1]}) {
        for (var inputCol = localCol; inputCol < ${c}; inputCol = inputCol + ${t[0]}) {
          ${Yn(r,n)}
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
      ${Yn(r,n)}
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
      ${rl(r)}
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
`},sl=(e,t,i,n,r=!1)=>{let[s,a,o,l]=n,u=et(n[0].type.tensor);return`
    fn mm_readA(batch: i32, row: i32, colIn: i32, batchIndices: ${s.type.indices}) -> ${it(e,u)} {
      var value = ${it(e,u)}(0.0);
      let col = colIn * ${e};
      if(row < uniforms.dim_a_outer && col < uniforms.dim_inner)
      {
        var aIndices: ${a.type.indices};
        ${wi("aIndices",a,a.rank-2,s.rank,"batchIndices")}
        ${a.indicesSet("aIndices",a.rank-2,"u32(row)")}
        ${a.indicesSet("aIndices",a.rank-1,"u32(colIn)")}
        value = ${a.getByIndices("aIndices")};
      }
      return value;
    }

    fn mm_readB(batch: i32, row: i32, colIn: i32, batchIndices: ${s.type.indices}) -> ${it(e,u)} {
      var value = ${it(e,u)}(0.0);
      let col = colIn * ${e};
      if(row < uniforms.dim_inner && col < uniforms.dim_b_outer)
      {
        var bIndices: ${o.type.indices};
        ${wi("bIndices",o,o.rank-2,s.rank,"batchIndices")}
        ${o.indicesSet("bIndices",o.rank-2,"u32(row)")}
        ${o.indicesSet("bIndices",o.rank-1,"u32(colIn)")}
        value = ${o.getByIndices("bIndices")};
      }
      return value;
    }

    fn mm_write(batch: i32, row: i32, colIn: i32, valueIn: ${it(e,u)}) {
      let col = colIn * ${e};
      if (row < uniforms.dim_a_outer && col < uniforms.dim_b_outer) {
        var value = valueIn;
        let coords = vec3<i32>(batch, row, colIn);
        ${t?`value = value + ${r?"bias[colIn]":`${it(e,u)}(bias[row])`};`:""}
        ${i}
        ${l.setByIndices("vec3<u32>(coords)","value")}
      }
    }
    `},Wi=(e,t,i,n,r=!1,s)=>{let a=e[0].dims,o=e[1].dims,l=a.slice(0,-2),u=o.slice(0,-2),d=n?n.slice(0,-2):i.slice(0,-2),c=O.size(d),p=a[a.length-2],h=a[a.length-1],m=o[o.length-1],_=h%4===0&&m%4===0,$=p<=8?[4,1,1]:[4,4,1],y=[8,8,1],g=[Math.ceil(m/y[0]/$[0]),Math.ceil(p/y[1]/$[1]),Math.ceil(c/y[2]/$[2])],T=_?4:1,x=[...l,p,h/T],C=x.length,R=[...u,h,m/T],z=R.length,P=[c,p,m/T],U=[{type:6,data:p},{type:6,data:m},{type:6,data:h}];Ht(t,U),U.push(...de(d,x,R));let re=["rank","rank"],_e=e.length>2;_e&&(U.push(...de(e[2].dims)),re.push("rank")),U.push(...de(P));let pe=be=>{let ae=d.length,ke=Bn("batchDims",e[0].dataType,ae,1),me=et(e[0].dataType),ue=F("a",e[0].dataType,C,T),De=F("b",e[1].dataType,z,T),fe=oe("result",e[0].dataType,P.length,T),Ue=[ue,De];if(_e){let nt=r?T:1;Ue.push(F("bias",e[2].dataType,e[2].dims.length,nt))}let G=[{name:"dim_a_outer",type:"i32"},{name:"dim_b_outer",type:"i32"},{name:"dim_inner",type:"i32"}];Kt(t,G);let ne=et(fe.type.tensor),Se=jt(t,fe.type.value,ne),Pe=sl(T,_e,Se,[ke,ue,De,fe],r);return`
  ${be.registerUniforms(G).registerInternalVariables(ke).declareVariables(...Ue,fe)}
  ${Pe}
  ${_?Xn($,y,me,ke):Jn($,y,me,ke)}
                   `};return{name:"MatMul",shaderCache:{hint:`${$};${t.activation};${_};${r}`,inputDependencies:re},getRunData:()=>({outputs:[{dims:s?s(i):i,dataType:e[0].dataType}],dispatchGroup:{x:g[0],y:g[1],z:g[2]},programUniforms:U}),getShaderSource:pe}}}),al,ol,Cp=E(()=>{ge(),Dt(),xe(),Zt(),Kn(),Ep(),er(),al=(e,t,i,n,r=!1,s,a=4,o=4,l=4,u="f32")=>{let d=U=>{switch(U){case 1:return"resData = x[xIndex];";case 3:return`resData = vec3<${u}>(x[xIndex], x[xIndex + 1], x[xIndex + 2]);`;case 4:return"resData = x[xIndex / 4];";default:throw new Error(`innerElementSize ${U} is not supported.`)}},c=U=>{switch(U){case 1:return"return w[row * i32(uniforms.w_shape[3]) + colIn];";case 4:return"return w[row * i32(uniforms.w_shape[3]) / 4 + colIn];";default:throw new Error(`innerElementSize ${U} is not supported.`)}},p=e?`
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
    var resData = ${it(a,u)}(0.0);
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
    return ${it(a,u)}(0.0);`:n&&i?`
    let col = colIn * ${a};
    ${g}`:`
    let col = colIn * ${a};
    if (row < uniforms.dim_inner && col < uniforms.dim_b_outer) {
      ${g}
    }
    return ${it(a,u)}(0.0);`,x=e?n&&i?c(o):`
    let col = colIn * ${o};
    if (row < uniforms.dim_inner && col < uniforms.dim_b_outer) {
      ${c(o)}
    }
    return ${it(o,u)}(0.0);`:`
    let col = colIn * ${o};
    if (row < uniforms.dim_inner && col < uniforms.dim_a_outer) {
      ${c(o)}
    }
    return ${it(o,u)}(0.0);`,C=it(l,u),R=it(e?a:o,u),z=it(e?o:a,u),P=jt(s,C,u);return`
    fn mm_readA(batch: i32, row : i32, colIn : i32) -> ${R} {
      ${e?T:x}
    }

    fn mm_readB(batch: i32, row : i32, colIn : i32) -> ${z} {
      ${e?x:T}
    }

    fn mm_write(batch: i32, row : i32, colIn : i32, valueIn : ${C}) {
      let col = colIn * ${l};
      if (row < uniforms.dim_a_outer && col < uniforms.dim_b_outer)
      {
      var value = valueIn;
      let outWidth = ${e?"i32(uniforms.result_shape[2])":"i32(uniforms.result_shape[3])"};
      ${h}
      ${el(r)}
      ${P}
      setOutputAtCoords(coords[0], coords[1], coords[2], coords[3], value);
      }
    }`},ol=(e,t,i,n,r,s,a,o,l)=>{let u=t.format==="NHWC",d=u?e[0].dims[3]:e[0].dims[1],c=i[0],p=u?i[2]:i[3],h=u?i[1]:i[2],m=u?i[3]:i[1],_=u&&(d%4===0||d%3===0)&&m%4===0,$=u?m:p*h,y=u?p*h:m,g=[8,8,1],T=n<=8?[4,1,1]:[4,4,1],x=[Math.ceil($/g[0]/T[0]),Math.ceil(y/g[1]/T[1]),Math.ceil(c/g[2]/T[2])];Ae("verbose",()=>`[conv2d_mm_webgpu] dispatch = ${x}`);let C=_?u&&d%4!==0?3:4:1,R=g[1]*T[1],z=g[0]*T[0],P=Math.max(g[0]*C,g[1]),U=n%R===0,re=r%z===0,_e=s%P===0,pe=_?[C,4,4]:[1,1,1],be=[{type:6,data:n},{type:6,data:r},{type:6,data:s},{type:6,data:[t.pads[0],t.pads[1]]},{type:6,data:t.strides},{type:6,data:t.dilations}];Ht(t,be),be.push(...de(e[0].dims,e[1].dims));let ae=["rank","rank"];a&&(be.push(...de(e[2].dims)),ae.push("rank")),be.push(...de(i));let ke=me=>{let ue=[{name:"dim_a_outer",type:"i32"},{name:"dim_b_outer",type:"i32"},{name:"dim_inner",type:"i32"},{name:"pad",type:"i32",length:2},{name:"stride",type:"i32",length:2},{name:"dilation",type:"i32",length:2}];Kt(t,ue);let De=_?4:1,fe=et(e[0].dataType),Ue=`
      fn setOutputAtIndex(flatIndex : i32, value : ${_?`vec4<${fe}>`:fe}) {
        result[flatIndex] = ${_?`vec4<${fe}>`:fe}(value);
      }
      fn setOutputAtCoords(d0 : i32, d1 : i32, d2 : i32, d3 : i32, value : ${_?`vec4<${fe}>`:fe}) {
        let flatIndex = getOutputIndexFromCoords(vec4<i32>(d0, d1, d2, d3));
        setOutputAtIndex(flatIndex ${_?"/ 4":""}, value);
      }`,G=F("x",e[0].dataType,e[0].dims.length,C===3?1:C),ne=F("w",e[1].dataType,e[1].dims.length,De),Se=[G,ne],Pe=oe("result",e[0].dataType,i.length,De);if(a){let nt=F("bias",e[2].dataType,e[2].dims.length,De);Se.push(nt),Ue+=`
        fn getBiasByOutputCoords(coords : vec4<i32>) -> ${_?`vec4<${fe}>`:fe} {
          return bias[coords.${u?"w":"y"}${_?"/ 4":""}];
        }`}return`
        ${tl("uniforms.result_strides")}
        //struct Uniforms { xShape : vec4<i32>, wShape : vec4<i32>, outShape : vec4<i32>,
        //  outShapeStrides: vec3<i32>, filterDims : vec2<i32>, pad : vec2<i32>, stride : vec2<i32>,
        //  dilation : vec2<i32>, dimAOuter : i32, dimBOuter : i32, dimInner : i32 };
        ${me.registerUniforms(ue).declareVariables(...Se,Pe)}
        ${Ue}
        ${al(u,U,re,_e,a,t,pe[0],pe[1],pe[2],fe)}
        ${_?Xn(T,g,fe,void 0,!u,P):Jn(T,g,fe,void 0,!u,P,!1,void 0,o)}`};return{name:"Conv2DMatMul",shaderCache:{hint:`${t.cacheKey};${C};${_};${U};${re};${_e};${R};${z};${P}`,inputDependencies:ae},getRunData:()=>({outputs:[{dims:l?l(i):i,dataType:e[0].dataType}],dispatchGroup:{x:x[0],y:x[1],z:x[2]},programUniforms:be}),getShaderSource:ke}}}),ll,tr,bi,ul,ir,dl,cl,pl,Ip=E(()=>{ge(),Dt(),$e(),xe(),Zt(),Kn(),ll=e=>{let t=1;for(let i=0;i<e.length;i++)t*=e[i];return t},tr=e=>typeof e=="number"?[e,e,e]:e,bi=(e,t)=>t<=1?e:e+(e-1)*(t-1),ul=(e,t,i,n=1)=>{let r=bi(t,n);return Math.floor((e[0]*(i-1)-i+r)/2)},ir=(e,t,i,n,r)=>{r==null&&(r=ul(e,t[0],n[0]));let s=[0,0,0,i];for(let a=0;a<3;a++)e[a]+2*r>=t[a]&&(s[a]=Math.trunc((e[a]-t[a]+2*r)/n[a]+1));return s},dl=(e,t,i,n,r,s,a,o,l,u)=>{let d,c,p,h;if(e==="VALID"&&(e=0),typeof e=="number"){d={top:e,bottom:e,left:e,right:e,front:e,back:e};let m=ir([t,i,n,1],[o,l,u],1,[r,s,a],e);c=m[0],p=m[1],h=m[2]}else if(Array.isArray(e)){if(!e.every((_,$,y)=>_===y[0]))throw Error(`Unsupported padding parameter: ${e}`);d={top:e[0],bottom:e[1],left:e[2],right:e[3],front:e[4],back:e[5]};let m=ir([t,i,n,1],[o,l,u],1,[r,s,a],e[0]);c=m[0],p=m[1],h=m[2]}else if(e==="SAME_UPPER"){c=Math.ceil(t/r),p=Math.ceil(i/s),h=Math.ceil(n/a);let m=(c-1)*r+o-t,_=(p-1)*s+l-i,$=(h-1)*a+u-n,y=Math.floor(m/2),g=m-y,T=Math.floor(_/2),x=_-T,C=Math.floor($/2),R=$-C;d={top:T,bottom:x,left:C,right:R,front:y,back:g}}else throw Error(`Unknown padding parameter: ${e}`);return{padInfo:d,outDepth:c,outHeight:p,outWidth:h}},cl=(e,t,i,n,r,s=!1,a="channelsLast")=>{let o,l,u,d,c;if(a==="channelsLast")[o,l,u,d,c]=e;else if(a==="channelsFirst")[o,c,l,u,d]=e;else throw new Error(`Unknown dataFormat ${a}`);let[p,,h,m,_]=t,[$,y,g]=tr(i),[T,x,C]=tr(n),R=bi(h,T),z=bi(m,x),P=bi(_,C),{padInfo:U,outDepth:re,outHeight:_e,outWidth:pe}=dl(r,l,u,d,$,y,g,R,z,P),be=s?p*c:p,ae=[0,0,0,0,0];return a==="channelsFirst"?ae=[o,be,re,_e,pe]:a==="channelsLast"&&(ae=[o,re,_e,pe,be]),{batchSize:o,dataFormat:a,inDepth:l,inHeight:u,inWidth:d,inChannels:c,outDepth:re,outHeight:_e,outWidth:pe,outChannels:be,padInfo:U,strideDepth:$,strideHeight:y,strideWidth:g,filterDepth:h,filterHeight:m,filterWidth:_,effectiveFilterDepth:R,effectiveFilterHeight:z,effectiveFilterWidth:P,dilationDepth:T,dilationHeight:x,dilationWidth:C,inShape:e,outShape:ae,filterShape:t}},pl=(e,t,i,n,r,s)=>{let a=s==="channelsLast";a?e[0].dims[3]:e[0].dims[1];let o=[64,1,1],l={x:i.map(($,y)=>y)},u=[Math.ceil(ll(l.x.map($=>i[$]))/o[0]),1,1];Ae("verbose",()=>`[conv3d_naive_webgpu] dispatch = ${u}`);let d=1,c=O.size(i),p=[{type:12,data:c},{type:12,data:n},{type:12,data:r},{type:12,data:t.strides},{type:12,data:t.dilations}];Ht(t,p),p.push(...de(e[0].dims,e[1].dims));let h=["rank","rank"],m=e.length===3;m&&(p.push(...de(e[2].dims)),h.push("rank")),p.push(...de(i));let _=$=>{let y=[{name:"output_size",type:"u32"},{name:"filter_dims",type:"u32",length:n.length},{name:"pads",type:"u32",length:r.length},{name:"strides",type:"u32",length:t.strides.length},{name:"dilations",type:"u32",length:t.dilations.length}];Kt(t,y);let g=1,T=et(e[0].dataType),x=F("x",e[0].dataType,e[0].dims.length,d),C=F("W",e[1].dataType,e[1].dims.length,g),R=[x,C],z=oe("result",e[0].dataType,i.length,g),P="";if(m){let _e=F("bias",e[2].dataType,e[2].dims.length,g);R.push(_e),P+=`
        fn getBiasByOutputCoords(coords : array<u32, 5>) -> ${T} {
          return bias[${a?le("coords",4,5):le("coords",1,5)}];
        }`}let U=it(d,T),re=jt(t,U,T);return`
            ${P}
            fn getX(d0 : u32, d1 : u32, d2 : u32, d3 : u32, d4 : u32) -> f32 {
              let aIndices = array<u32, 5>(d0, d1, d2, d3, d4);
              return ${x.getByIndices("aIndices")};
            }
            fn getW(d0 : u32, d1 : u32, d2 : u32, d3 : u32, d4 : u32) -> f32 {
              let aIndices = array<u32, 5>(d0, d1, d2, d3, d4);
              return ${C.getByIndices("aIndices")};
            }
          ${$.registerUniforms(y).declareVariables(...R,z)}
          ${$.mainStart()}
          ${$.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
              let coords = ${z.offsetToIndices("global_idx")};
              let batch = ${le("coords",0,x.rank)};
              let d2 = ${a?le("coords",x.rank-1,x.rank):le("coords",1,x.rank)};
              let xFRCCorner = vec3<u32>(${a?le("coords",1,x.rank):le("coords",2,x.rank)},
              ${a?le("coords",2,x.rank):le("coords",3,x.rank)},
              ${a?le("coords",3,x.rank):le("coords",4,x.rank)}) * uniforms.strides - uniforms.pads;
              let xFCorner = xFRCCorner.x;
              let xRCorner = xFRCCorner.y;
              let xCCorner = xFRCCorner.z;
              let xShapeY = ${a?le("uniforms.x_shape",1,x.rank):le("uniforms.x_shape",2,x.rank)};
              let xShapeZ = ${a?le("uniforms.x_shape",2,x.rank):le("uniforms.x_shape",3,x.rank)};
              let xShapeW = ${a?le("uniforms.x_shape",3,x.rank):le("uniforms.x_shape",4,x.rank)};
              let xShapeU = ${a?le("uniforms.x_shape",4,x.rank):le("uniforms.x_shape",1,x.rank)};
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
              ${re}
              result[global_idx] = f32(value);
          }`};return{name:"Conv3DNaive",shaderCache:{hint:`${t.cacheKey};${a};${d};${m}`,inputDependencies:h},getRunData:()=>({outputs:[{dims:i,dataType:e[0].dataType}],dispatchGroup:{x:u[0],y:u[1],z:u[2]},programUniforms:p}),getShaderSource:_}}}),fl,hl,Ap=E(()=>{ge(),$e(),xe(),Zt(),fl=(e,t,i,n)=>{let r=e.length>2,s=r?"value += b[output_channel];":"",a=e[0].dims,o=e[1].dims,l=t.format==="NHWC",u=l?i[3]:i[1],d=u/t.group,c=l&&d>=4?je(u):1,p=O.size(i)/c,h=[{type:12,data:p},{type:12,data:t.dilations},{type:12,data:[t.strides[0],t.strides[1]]},{type:12,data:[t.pads[0],t.pads[1]]},{type:12,data:d}];Ht(t,h),h.push(...de(a,[o[0],o[1],o[2],o[3]/c]));let m=r?["rank","rank","rank"]:["rank","rank"];h.push(...de([i[0],i[1],i[2],i[3]/c]));let _=$=>{let y=oe("output",e[0].dataType,i.length,c),g=et(y.type.tensor),T=jt(t,y.type.value,g),x=F("x",e[0].dataType,a.length),C=F("w",e[1].dataType,o.length,c),R=[x,C];r&&R.push(F("b",e[2].dataType,e[2].dims,c));let z=[{name:"output_size",type:"u32"},{name:"dilations",type:"u32",length:t.dilations.length},{name:"strides",type:"u32",length:2},{name:"pads",type:"u32",length:2},{name:"output_channels_per_group",type:"u32"}];Kt(t,z);let P=l?`
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
            let wVal = ${C.get("wHeight","wWidth","wInChannel","output_channel")};
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
            let wVal = ${C.get("output_channel","wInChannel","wHeight","wWidth")};
            value += xVal * wVal;
          }
        }
      }
      `;return`
  ${$.registerUniforms(z).declareVariables(...R,y)}

  ${$.mainStart()}
    ${$.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let outputIndices = ${y.offsetToIndices("global_idx")};
    let batch: u32 = outputIndices[0];
    let output_channel: u32 = outputIndices[${l?3:1}];
    let xRCCorner: vec2<u32> = vec2<u32>(outputIndices[${l?1:2}], outputIndices[${l?2:3}]) * uniforms.strides - uniforms.pads;
    let group_id: u32 = output_channel * ${c} / uniforms.output_channels_per_group;
    var in_channel_offset = group_id * uniforms.w_shape[${l?2:1}];

    var value: ${y.type.value} = ${y.type.value}(0);
    ${P}
    ${s}
    ${T}
    ${y.setByOffset("global_idx","value")}
  }`};return{name:"GroupedConv",shaderCache:{hint:`${t.cacheKey}_${c}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:n?n(i):i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:h}),getShaderSource:_}},hl=(e,t,i,n)=>{let r=e.length>2,s=je(i[3]),a=je(i[2]),o=O.size(i)/s/a,l=[e[0].dims[0],e[0].dims[1],e[0].dims[2],e[0].dims[3]/s],u=[e[1].dims[0],e[1].dims[1],e[1].dims[2],e[1].dims[3]/s],d=[i[0],i[1],i[2],i[3]/s],c=[{type:12,data:o},{type:6,data:[t.strides[0],t.strides[1]]},{type:6,data:[t.pads[0],t.pads[1]]}];Ht(t,c),c.push(...de(l,u,d));let p=(a-1)*t.strides[1]+u[1],h=m=>{let _=oe("output",e[0].dataType,d.length,s),$=et(_.type.tensor),y=jt(t,_.type.value,$),g=F("x",e[0].dataType,l.length,s),T=F("w",e[1].dataType,u.length,s),x=[g,T];r&&x.push(F("b",e[2].dataType,e[2].dims,s));let C=r?"value += b[output_channel];":"",R=[{name:"output_size",type:"u32"},{name:"strides",type:"i32",length:2},{name:"pads",type:"i32",length:2}];return Kt(t,R),`
  ${m.registerUniforms(R).declareVariables(...x,_)}
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
      ${C}
      ${y}
      ${_.set("batch","row","col + i","output_channel","value")};
    }
  }`};return{name:"GroupedConv-Vectorize",shaderCache:{hint:`${t.cacheKey};${s};${a};${p};${u[0]};${u[1]}`,inputDependencies:r?["rank","rank","type"]:["rank","rank"]},getRunData:()=>({outputs:[{dims:n?n(i):i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(o/64)},programUniforms:c}),getShaderSource:h}}}),ml,Gi,gl,ji,nr,rr,_l,yl,sr,zp=E(()=>{$e(),Cp(),Ip(),er(),Ap(),Zt(),Qn(),Nt(),ml=(e,t,i,n,r,s)=>{let a=e[0],o=e.slice(s?1:2,s?3:4),l=o.length,u=t[0],d=t.slice(2).map((p,h)=>p+(p-1)*(i[h]-1)),c=o.map((p,h)=>p+n[h]+n[h+l]).map((p,h)=>Math.floor((p-d[h]+r[h])/r[h]));return c.splice(0,0,a),c.splice(s?3:1,0,u),c},Gi=[2,3,1,0],gl=(e,t)=>{if(!e||e.length!==2&&e.length!==3)throw new Error("Conv requires 2 or 3 inputs");if(e[0].dims.length>5)throw new Error("greater than 5D is not supported");if(e[0].dims.length!==e[1].dims.length)throw new Error("filter does not have same dimension as input");let i=e[0].dims[t.format==="NHWC"?e[0].dims.length-1:1],n=e[1].dims[1]*t.group;if(i!==n)throw new Error("FILTER_IN_CHANNEL should be equal to DATA_CHANNEL");if(e.length===3&&(e[2].dims.length!==1||e[1].dims[0]!==e[2].dims[0]))throw new Error("invalid bias");let r=e[0].dims.length-2;if(t.dilations.length!==r)throw new Error(`dilations should be ${r}D`);if(t.strides.length!==r)throw new Error(`strides should be ${r}D`);if(t.pads.length!==r*2)throw new Error(`pads should be ${r*2}D`);if(t.kernelShape.length!==0&&t.kernelShape.length!==e[1].dims.length-2)throw new Error("invalid kernel shape")},ji=(e,t)=>{let i=e.kernelShape.slice();i.length<t[1].dims.length-2&&i.push(...Array(t[1].dims.length-2-i.length).fill(0));for(let s=2;s<t[1].dims.length;++s)i[s-2]===0&&(i[s-2]=t[1].dims[s]);let n=e.pads.slice();Fi.adjustPadsBasedOnAutoPad(t[0].dims,e.strides,e.dilations,i,n,e.format==="NHWC",e.autoPad);let r=Object.assign({},e);return Object.assign(r,{kernelShape:i,pads:n}),r},nr=e=>{let t=Hn(e),i=e.format,n=["NOTSET","VALID","SAME_UPPER","SAME_LOWER"][e.auto_pad],r=e.dilations,s=e.group,a=e.kernel_shape,o=e.pads,l=e.strides,u=e.w_is_const();return{autoPad:n,format:i,dilations:r,group:s,kernelShape:a,pads:o,strides:l,wIsConst:u,...t,cacheKey:`${e.format};${t.activation};`}},rr=(e,t,i,n)=>{let r=i.format==="NHWC",s=ml(t[0].dims,t[1].dims,i.dilations,i.pads,i.strides,r);if(i.group!==1){let R=[t[0]];if(r){let z=e.kernelCustomData.wT??e.compute(ft(t[1],Gi),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=z),R.push(z)}else R.push(t[1]);t.length===3&&R.push(t[2]),!e.adapterInfo.isArchitecture("ampere")&&r&&t[1].dims[0]===i.group&&t[1].dims[1]===1&&i.dilations[0]===1&&i.dilations[1]===1?e.compute(hl(R,i,s,n),{inputs:R}):e.compute(fl(R,i,s,n),{inputs:R});return}let a=t.length===3,o=t[0].dims[r?1:2],l=t[0].dims[r?2:3],u=t[0].dims[r?3:1],d=t[1].dims[2],c=t[1].dims[3],p=s[r?1:2],h=s[r?2:3],m=s[r?3:1],_=r&&d===o&&c===l&&i.pads[0]===0&&i.pads[1]===0;if(_||d===1&&c===1&&i.dilations[0]===1&&i.dilations[1]===1&&i.strides[0]===1&&i.strides[1]===1&&i.pads[0]===0&&i.pads[1]===0){let R=s[0],z,P,U,re=[];if(r){let be=e.kernelCustomData.wT??e.compute(ft(t[1],Gi),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];if(i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=be),_){let ae=o*l*u;z=t[0].reshape([1,R,ae]),P=be.reshape([1,ae,m]),U=[1,R,m]}else z=t[0].reshape([R,o*l,u]),P=be.reshape([1,u,m]),U=[R,p*h,m];re.push(z),re.push(P)}else z=t[0].reshape([R,u,o*l]),P=t[1].reshape([1,m,u]),U=[R,m,p*h],re.push(P),re.push(z);a&&re.push(t[2]);let _e=U[2],pe=re[0].dims[re[0].dims.length-1];_e<8&&pe<8?e.compute(Zn(re,i,s,U,r,n),{inputs:re}):e.compute(Wi(re,i,s,U,r,n),{inputs:re});return}let $=!0,y=e.kernelCustomData.wT??e.compute(ft(t[1],Gi),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=y);let g=[t[0],y];a&&g.push(t[2]);let T=r?p*h:m,x=r?m:p*h,C=d*c*u;e.compute(ol(g,i,s,T,x,C,a,$,n),{inputs:g})},_l=(e,t)=>{let i=t.format==="NHWC",n=[e.inputs[0].reshape(i?[e.inputs[0].dims[0],1,e.inputs[0].dims[1],e.inputs[0].dims[2]]:[e.inputs[0].dims[0],e.inputs[0].dims[1],1,e.inputs[0].dims[2]]),e.inputs[1].reshape([e.inputs[1].dims[0],e.inputs[1].dims[1],1,e.inputs[1].dims[2]])];e.inputs.length===3&&n.push(e.inputs[2]);let r=[0,t.pads[0],0,t.pads[1]],s=[1].concat(t.strides),a=[1].concat(t.dilations),o=[1].concat(t.kernelShape),l=ji({...t,pads:r,strides:s,dilations:a,kernelShape:o},n);rr(e,n,l,u=>i?[u[0],u[2],u[3]]:[u[0],u[1],u[3]])},yl=(e,t,i)=>{let n=i.format==="NHWC"?"channelsLast":"channelsFirst",r=ji(i,t),s=i.autoPad==="NOTSET"?i.pads:i.autoPad,a=cl(t[0].dims,t[1].dims,i.strides,i.dilations,s,!1,n);e.compute(pl(t,r,a.outShape,[a.filterDepth,a.filterHeight,a.filterWidth],[a.padInfo.front,a.padInfo.top,a.padInfo.left],n))},sr=(e,t)=>{if(gl(e.inputs,t),e.inputs[0].dims.length===3)_l(e,t);else if(e.inputs[0].dims.length===5)yl(e,e.inputs,t);else{let i=ji(t,e.inputs);rr(e,e.inputs,i)}}}),wl,Mp=E(()=>{ge(),Dt(),$e(),xe(),wl=(e,t,i)=>{let n=e.length>2,r=t.outputShape,s=t.format==="NHWC",a=t.group,o=e[1].dims,l=o[2]/a,u=o[3],d=s?je(l):1,c=s&&u===1&&l>=4,p=c?Math.floor(l/4)*4:Math.floor(l/d)*d,h=l-p,m=s?je(u):1,_=s?u===1?d:m:1,$=O.size(r)/m,y=[Math.ceil($/64),1,1];Ae("verbose",()=>`[conv2d_backprop_webgpu] dispatch = ${y}`);let g=["rank","rank"],T=[t.strides[0],t.strides[1]],x=[t.kernelShape[s?1:2],t.kernelShape[s?2:3]],C=[t.dilations[0],t.dilations[1]],R=[x[0]+(t.dilations[0]<=1?0:(t.kernelShape[s?1:2]-1)*(t.dilations[0]-1)),x[1]+(t.dilations[1]<=1?0:(t.kernelShape[s?2:3]-1)*(t.dilations[1]-1))],z=[R[0]-1-Math.floor((t.pads[0]+t.pads[2])/2),R[1]-1-Math.floor((t.pads[1]+t.pads[3])/2)],P=[{type:12,data:$},{type:12,data:T},{type:12,data:x},{type:12,data:C},{type:12,data:R},{type:6,data:z},{type:12,data:p},{type:12,data:l},{type:12,data:u},...de(e[0].dims,e[1].dims)];n&&(P.push(...de(e[2].dims)),g.push("rank")),P.push(...de(r));let U=re=>{let _e=[{name:"output_size",type:"u32"},{name:"strides",type:"u32",length:T.length},{name:"filter_dims",type:"u32",length:x.length},{name:"dilations",type:"u32",length:x.length},{name:"effective_filter_dims",type:"u32",length:R.length},{name:"pads",type:"i32",length:z.length},{name:"input_channels_per_group_int",type:"u32"},{name:"input_channels_per_group",type:"u32"},{name:"output_channels_per_group",type:"u32"}],pe=et(e[0].dataType),be=s?1:2,ae=s?2:3,ke=s?3:1,me=F("W",e[1].dataType,e[1].dims.length,_),ue=F("Dy",e[0].dataType,e[0].dims.length,d),De=[ue,me];n&&De.push(F("bias",e[2].dataType,[r[ke]].length,m));let fe=oe("result",e[0].dataType,r.length,m),Ue=()=>{let Se="";if(c)d===4?Se+=`
        let xValue = ${ue.getByOffset("x_offset")};
        let wValue = ${me.getByOffset("w_offset")};
        dotProd = dotProd + dot(xValue, wValue);
        x_offset += 1u;
        w_offset += 1u;`:d===2?Se+=`
          dotProd = dotProd + dot(vec4<${pe}>(${ue.getByOffset("x_offset")}, ${ue.getByOffset("x_offset + 1u")}), vec4<${pe}>(${me.getByOffset("w_offset")}, ${me.getByOffset("w_offset + 1u")}));
          x_offset += 2u;
          w_offset += 2u;`:d===1&&(Se+=`
          dotProd = dotProd + dot(vec4<${pe}>(${ue.getByOffset("x_offset")}, ${ue.getByOffset("x_offset + 1u")}, ${ue.getByOffset("x_offset + 2u")}, ${ue.getByOffset("x_offset + 3u")}), vec4<${pe}>(${me.getByOffset("w_offset")}, ${me.getByOffset("w_offset + 1u")}, ${me.getByOffset("w_offset + 2u")}, ${me.getByOffset("w_offset + 3u")}));
          x_offset += 4u;
          w_offset += 4u;`);else if(Se+=`
                  let xValue = ${s?ue.getByOffset(`${ue.indicesToOffset(`${ue.type.indices}(batch, idyR, idyC, inputChannel)`)} / ${d}`):ue.get("batch","inputChannel","idyR","idyC")};
        `,d===1)Se+=`
          let w_offset = ${me.indicesToOffset(`${me.type.indices}(u32(wRPerm), u32(wCPerm), inputChannel, wOutChannel)`)};
          let wValue = ${me.getByOffset(`w_offset / ${_}`)};
          dotProd = dotProd + xValue * wValue;`;else for(let Pe=0;Pe<d;Pe++)Se+=`
            let wValue${Pe} = ${me.getByOffset(`${me.indicesToOffset(`${me.type.indices}(u32(wRPerm), u32(wCPerm), inputChannel + ${Pe}, wOutChannel)`)} / ${_}`)};
            dotProd = dotProd + xValue[${Pe}] * wValue${Pe};`;return Se},G=()=>{if(h===0)return"";if(!c)throw new Error(`packInputAs4 ${c} is not true.`);let Se="";if(d===1){Se+="dotProd = dotProd";for(let Pe=0;Pe<h;Pe++)Se+=`
            + ${ue.getByOffset(`x_offset + ${Pe}`)} * ${me.getByOffset(`w_offset + ${Pe}`)}`;Se+=";"}else if(d===2){if(h!==2)throw new Error(`Invalid inputChannelsRemainder ${h}.`);Se+=`
          let xValue = ${ue.getByOffset("x_offset")};
          let wValue = ${me.getByOffset("w_offset")};
          dotProd = dotProd + dot(xValue, wValue);`}return Se},ne=`
            let outputIndices = ${fe.offsetToIndices(`global_idx * ${m}`)};
            let batch = ${fe.indicesGet("outputIndices",0)};
            let d1 = ${fe.indicesGet("outputIndices",ke)};
            let r = ${fe.indicesGet("outputIndices",be)};
            let c = ${fe.indicesGet("outputIndices",ae)};
            let dyCorner = vec2<i32>(i32(r), i32(c)) - uniforms.pads;
            let dyRCorner = dyCorner.x;
            let dyCCorner = dyCorner.y;
            let groupId = d1 / uniforms.output_channels_per_group;
            let wOutChannel = d1 - groupId * uniforms.output_channels_per_group;
            // Convolve dy(?, ?, d2) with w(:, :, d1, d2) to compute dx(xR, xC, d1).
            // ? = to be determined. : = across all values in that axis.
            var dotProd = ${fe.type.value}(0.0);
            var wR: u32 = 0;
            if (uniforms.dilations.x == 1) {
              // Minimum wR >= 0 that satisfies (dyRCorner + wR) % (uniforms.strides.x) == 0
              wR = u32(((dyRCorner + i32(uniforms.strides.x) - 1) / i32(uniforms.strides.x)) * i32(uniforms.strides.x) - dyRCorner);
            }
            for (; wR < uniforms.effective_filter_dims.x; wR = wR + 1) {
              if (wR % uniforms.dilations.x != 0) {
                continue;
              }
              let dyR = (${pe}(dyRCorner) + ${pe}(wR)) / ${pe}(uniforms.strides[0]);
              let wRPerm = uniforms.filter_dims.x - 1 - wR / uniforms.dilations.x;
              if (dyR < 0.0 || dyR >= ${pe}(uniforms.Dy_shape[${be}]) || fract(dyR) > 0.0 ||
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
                let dyC = (${pe}(dyCCorner) + ${pe}(wC)) / ${pe}(uniforms.strides.y);
                let wCPerm = uniforms.filter_dims.y - 1 - wC / uniforms.dilations.y;
                if (dyC < 0.0 || dyC >= ${pe}(uniforms.Dy_shape[${ae}]) ||
                    fract(dyC) > 0.0 || wCPerm < 0) {
                  continue;
                }
                let idyC: u32 = u32(dyC);
                var inputChannel = groupId * uniforms.input_channels_per_group;
                ${c?`
                var x_offset = ${ue.indicesToOffset(`${ue.type.indices}(batch, idyR, idyC, inputChannel)`)} / ${d};
                var w_offset = ${me.indicesToOffset(`${me.type.indices}(wRPerm, wCPerm, inputChannel, wOutChannel)`)} / ${_};
                  `:""}
                for (var d2: u32 = 0; d2 < uniforms.input_channels_per_group_int; d2 = d2 + ${c?4:d}) {
                  ${Ue()}
                  inputChannel = inputChannel + ${c?4:d};
                }
                ${G()}
                wC = wC + uniforms.strides.y - 1;
              }
              wR = wR + uniforms.strides[0] - 1;
            }
            let value = dotProd${n?` + bias[d1 / ${m}]`:""};
            ${fe.setByOffset("global_idx","value")};
          `;return`
    ${re.registerUniforms(_e).declareVariables(...De,fe)}
      ${re.mainStart()}
      ${re.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")};
    ${ne}}`};return{name:"ConvTranspose2D",shaderCache:{hint:`${t.cacheKey};${d}${_}${m}${c}${h}`,inputDependencies:g},getRunData:()=>({dispatchGroup:{x:y[0],y:y[1],z:y[2]},outputs:[{dims:i?i(r):r,dataType:e[0].dataType}],programUniforms:P}),getShaderSource:U}}}),bl,vl,$l,ar,xl,Sl,or,kl,Tl,Rp=E(()=>{Mp(),Zt(),Nt(),bl=(e,t,i,n,r,s)=>(e-1)*t+i+(n-1)*r+1-s,vl=(e,t,i,n,r)=>{let s=Math.floor(e/2);t==="SAME_UPPER"?(i[n]=s,i[r]=e-s):t==="SAME_LOWER"&&(i[n]=e-s,i[r]=s)},$l=(e,t,i,n,r,s,a,o,l,u)=>{let d=e.length-2,c=u.length===0;l.length<d&&l.push(...Array(d-l.length).fill(0));let p=e[0],h=t[o?3:1]*r;for(let m=0,_=e.length-d-(o?1:0);m<d;++m,++_){let $=e[_],y=c?$*a[m]:u[m],g=bl($,a[m],s[m],t[_],i[m],y);vl(g,n,s,m,m+d),c&&u.push(a[m]*($-1)+l[m]+(t[_]-1)*i[m]+1-s[m]-s[m+d])}u.splice(0,0,p),u.splice(o?3:1,0,h)},ar=(e,t)=>{let i=e.kernelShape.slice();if(e.kernelShape.length===0||e.kernelShape.reduce((c,p)=>c*p,1)===0){i.length=0;for(let c=2;c<t[1].dims.length;++c)i.push(t[1].dims[c])}let n=e.format==="NHWC";i.splice(0,0,t[1].dims[0]),i.splice(n?3:1,0,t[1].dims[1]);let r=e.pads.slice(),s=e.outputShape.slice(),a=e.outputPadding.slice(),o=t[0].dims,l=e.dilations.slice();if(l.reduce((c,p)=>c+p,0)===0){let c=t[0].dims.length-2;l=new Array(c).fill(1)}let u=e.strides.slice();if(u.reduce((c,p)=>c+p,0)===0){let c=t[0].dims.length-2;u=new Array(c).fill(1)}$l(o,i,l,e.autoPad,e.group,r,u,n,a,s);let d=Object.assign({},e);return Object.assign(d,{kernelShape:i,pads:r,outputPadding:a,outputShape:s,dilations:l,strides:u}),d},xl=e=>{let t=Hn(e),i=e.format,n=["NOTSET","VALID","SAME_UPPER","SAME_LOWER"][typeof e.autoPad>"u"?0:e.autoPad],r=e.dilations,s=e.group,a=e.kernelShape,o=e.pads,l=e.strides,u=e.wIsConst(),d=e.outputPadding,c=e.outputShape;return{autoPad:n,format:i,dilations:r,group:s,kernelShape:a,outputPadding:d,outputShape:c,pads:o,strides:l,wIsConst:u,...t,cacheKey:`${e.format};${t.activation};`}},Sl=(e,t)=>{if(!e||e.length!==2&&e.length!==3)throw new Error("Conv requires 2 or 3 inputs");if(e[0].dims.length!==4&&e[0].dims.length!==3)throw new Error("currently only support 2-dimensional conv");if(e[0].dims.length!==e[1].dims.length)throw new Error("filter does not have same dimension as input");let i=e[0].dims[t.format==="NHWC"?e[0].dims.length-1:1],n=e[1].dims[0];if(i!==n)throw new Error("FILTER_IN_CHANNEL should be equal to DATA_CHANNEL");let r=e[1].dims[1]*t.group;if(e.length===3&&(e[2].dims.length!==1||e[2].dims[0]!==r))throw new Error("invalid bias");let s=e[0].dims.length-2;if(t.dilations.reduce((a,o)=>a+o,0)>0&&t.dilations.length!==s)throw new Error(`dilations should be ${s}D`);if(t.strides.reduce((a,o)=>a+o,0)>0&&t.strides.length!==s)throw new Error(`strides should be ${s}D`);if(t.pads.reduce((a,o)=>a+o,0)>0&&t.pads.length!==s*2)throw new Error(`pads should be ${s*2}D`);if(t.outputPadding.length!==s&&t.outputPadding.length!==0)throw new Error(`output_padding should be ${s}D`);if(t.kernelShape.reduce((a,o)=>a+o,0)>0&&t.kernelShape.length!==0&&t.kernelShape.length!==e[1].dims.length-2)throw new Error("invalid kernel shape");if(t.outputShape.length!==0&&t.outputShape.length!==e[0].dims.length-2)throw new Error("invalid output shape")},or=(e,t,i,n)=>{let r=e.kernelCustomData.wT??e.compute(ft(t[1],[2,3,0,1]),{inputs:[1],outputs:[i.wIsConst?-2:-1]})[0];i.wIsConst&&!e.kernelCustomData.wT&&(e.kernelCustomData.wT=r);let s=[t[0],r];t.length===3&&s.push(t[2]),e.compute(wl(s,i,n),{inputs:s})},kl=(e,t)=>{let i=t.format==="NHWC",n=[e.inputs[0].reshape(i?[e.inputs[0].dims[0],1,e.inputs[0].dims[1],e.inputs[0].dims[2]]:[e.inputs[0].dims[0],e.inputs[0].dims[1],1,e.inputs[0].dims[2]]),e.inputs[1].reshape([e.inputs[1].dims[0],e.inputs[1].dims[1],1,e.inputs[1].dims[2]])];e.inputs.length===3&&n.push(e.inputs[2]);let r=t.kernelShape;(r.length===0||r[0]===0)&&(r=[e.inputs[1].dims[2]]);let s=t.dilations;(s.length===0||s[0]===0)&&(s=[1]);let a=t.strides;(a.length===0||a[0]===0)&&(a=[1]);let o=t.pads;o.length===0&&(o=[0,0]),o=[0,o[0],0,o[1]],a=[1].concat(a),s=[1].concat(s),r=[1].concat(r);let l=t.outputPadding;l=[0].concat(l);let u=ar({...t,pads:o,strides:a,dilations:s,kernelShape:r,outputPadding:l},n);or(e,n,u,d=>i?[d[0],d[2],d[3]]:[d[0],d[1],d[3]])},Tl=(e,t)=>{if(Sl(e.inputs,t),e.inputs[0].dims.length===3)kl(e,t);else{let i=ar(t,e.inputs);or(e,e.inputs,i)}}}),El,Cl,Il,Op=E(()=>{ge(),$e(),He(),xe(),El=(e,t,i,n)=>{let r=O.size(t),s=t.length,a=F("input",e,s),o=oe("output",e,s),l=i.dataType===6?i.getInt32Array()[0]:Number(i.getBigInt64Array()[0]),u=O.normalizeAxis(l,s),d=c=>{let p=` i32(${a.indicesGet("inputIndices","uniforms.axis")}) `,h=le("uniforms.input_shape","uniforms.axis",s),m=n.reverse?p+(n.exclusive?" + 1":""):"0",_=n.reverse?h:p+(n.exclusive?"":" + 1");return`
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
                }`};return{name:"CumSum",shaderCache:{hint:n.cacheKey,inputDependencies:["rank"]},getRunData:()=>({outputs:[{dims:t,dataType:e}],dispatchGroup:{x:Math.ceil(r/64)},programUniforms:[{type:12,data:r},{type:12,data:u},...de(t,t)]}),getShaderSource:d}},Cl=(e,t)=>{let i=e.inputs[0].dims,n=e.inputs[0].dataType,r=e.inputs[1];e.compute(El(n,i,r,t),{inputs:[0]})},Il=e=>{let t=e.exclusive===1,i=e.reverse===1;return Be({exclusive:t,reverse:i})}}),Al,zl,Ml,Rl,Ol,Dp=E(()=>{ge(),$e(),He(),xe(),Al=e=>{if(!e||e.length!==1)throw new Error("DepthToSpace requires 1 input.");if(e[0].dims.length!==4)throw new Error("DepthToSpace requires 4D input.")},zl=(e,t,i,n)=>{let r=[];r.push(`fn perm(i: ${n.type.indices}) -> ${i.type.indices} {
    var a: ${i.type.indices};`);for(let s=0;s<t;++s)r.push(i.indicesSet("a",e[s],`i[${s}]`));return r.push("return a;}"),r.join(`
`)},Ml=(e,t)=>{let i,n,r,s,a,o,l=t.format==="NHWC",u=t.blocksize,d=t.mode==="DCR";l?([i,n,r,s]=e.dims,a=d?[i,n,r,u,u,s/u**2]:[i,n,r,s/u**2,u,u],o=d?[0,1,3,2,4,5]:[0,1,4,2,5,3]):([i,n,r,s]=[e.dims[0],e.dims[2],e.dims[3],e.dims[1]],a=d?[i,u,u,s/u**2,n,r]:[i,s/u**2,u,u,n,r],o=d?[0,3,4,1,5,2]:[0,1,4,2,5,3]);let c=e.reshape(a),p=c.dims.length,h=e.dataType,m=F("a",h,p),_=oe("output",h,p),$=y=>`
  ${y.registerUniform("output_size","u32").declareVariables(m,_)}

  ${zl(o,p,m,_)}

  ${y.mainStart()}
    ${y.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let indices = ${_.offsetToIndices("global_idx")};
    let aIndices = perm(indices);

    ${_.setByOffset("global_idx",m.getByIndices("aIndices"))}
  }`;return{name:"DepthToSpace",shaderCache:{hint:`${e.dims};${t.blocksize};${t.mode}`,inputDependencies:["rank"]},getRunData:y=>{let g=l?[i,n*u,r*u,s/u**2]:[i,s/u**2,n*u,r*u],T=O.size(g),x=c.dims,C=O.sortBasedOnPerm(x,o);return{outputs:[{dims:g,dataType:y[0].dataType}],dispatchGroup:{x:Math.ceil(T/64)},programUniforms:[{type:12,data:T},...de(x,C)]}},getShaderSource:$}},Rl=(e,t)=>{Al(e.inputs),e.compute(Ml(e.inputs[0],t))},Ol=e=>Be({blocksize:e.blocksize,mode:e.mode,format:e.format})}),Hi,vi,lr,Dl,Bl,Fl,Pl,ur,Nl,Vl,Ll,Bp=E(()=>{ge(),$e(),He(),xe(),Hi="[a-zA-Z]|\\.\\.\\.",vi="("+Hi+")+",lr="^"+vi+"$",Dl="("+vi+",)*"+vi,Bl="^"+Dl+"$",Fl=class{constructor(e=-1){this.symbolToIndices=new Map,this.inputIndex=e}addSymbol(e,t){let i=this.symbolToIndices.get(e);i===void 0?i=[t]:i.push(t),this.symbolToIndices.set(e,i)}},Pl=class{constructor(e,t){this.equation=t,this.hasEllipsis=!1,this.symbolToInfo=new Map,this.lhs=new Array,this.outputDims=[];let[i,n]=t.includes("->")?t.split("->",2):[t,""];if(!i.match(RegExp(Bl)))throw new Error("Invalid LHS term");if(i.split(",").forEach((r,s)=>{let a=e[s].dims.slice();if(!r.match(RegExp(lr)))throw new Error("Invalid LHS term");let o=this.processTerm(r,!0,a,s);this.lhs.push(o)}),n==="")n+=[...this.symbolToInfo.entries()].filter(([r,s])=>s.count===1||r==="...").map(([r])=>r).join("");else if(!n.match(RegExp(vi)))throw new Error("Invalid RHS");n.match(RegExp(Hi,"g"))?.forEach(r=>{if(r==="...")this.outputDims=this.outputDims.concat(this.ellipsisDims);else{let s=this.symbolToInfo.get(r);if(s===void 0)throw new Error("Invalid RHS symbol");this.outputDims.push(s.dimValue)}}),this.rhs=this.processTerm(n,!1,this.outputDims)}addSymbol(e,t,i){let n=this.symbolToInfo.get(e);if(n!==void 0){if(n.dimValue!==t&&n.count!==1)throw new Error("Dimension mismatch");n.count++,n.inputIndices.push(i)}else n={count:1,dimValue:t,inputIndices:[i]};this.symbolToInfo.set(e,n)}processTerm(e,t,i,n=-1){let r=i.length,s=!1,a=[],o=0;if(!e.match(RegExp(lr))&&!t&&e!=="")throw new Error("Invalid LHS term");let l=e.match(RegExp(Hi,"g")),u=new Fl(n);return l?.forEach((d,c)=>{if(d==="..."){if(s)throw new Error("Only one ellipsis is allowed per input term");s=!0;let p=r-l.length+1;if(p<0)throw new Error("Ellipsis out of bounds");if(a=i.slice(o,o+p),this.hasEllipsis){if(this.ellipsisDims.length!==a.length||this.ellipsisDims.toString()!==a.toString())throw new Error("Ellipsis dimensions mismatch")}else if(t)this.hasEllipsis=!0,this.ellipsisDims=a;else throw new Error("Ellipsis must be specified in the LHS");for(let h=0;h<a.length;h++){let m=String.fromCharCode(48+h);u.addSymbol(m,c+h),this.addSymbol(m,i[o++],n)}}else u.addSymbol(d,c+(this.hasEllipsis?this.ellipsisDims.length-1:0)),this.addSymbol(d,i[o++],n)}),u}},ur=e=>e+"_max",Nl=(e,t,i,n)=>{let r=e.map(u=>u.length).map((u,d)=>F(`input${d}`,t,u)),s=O.size(n),a=oe("output",t,n.length),o=[...i.symbolToInfo.keys()].filter(u=>!i.rhs.symbolToIndices.has(u)),l=u=>{let d=[],c="var prod = 1.0;",p="var sum = 0.0;",h="sum += prod;",m=[],_=[],$=[],y=[],g=i.symbolToInfo.size===i.rhs.symbolToIndices.size;i.symbolToInfo.forEach((x,C)=>{if(i.rhs.symbolToIndices.has(C)){let R=i.rhs.symbolToIndices.get(C)?.[0];R!==void 0&&i.lhs.forEach((z,P)=>{if(x.inputIndices.includes(P)){let U=z.symbolToIndices.get(C);if(U===void 0)throw new Error("Invalid symbol error");U.forEach(re=>{d.push(`${r[P].indicesSet(`input${P}Indices`,re,a.indicesGet("outputIndices",R))}`)})}})}else i.lhs.forEach((R,z)=>{if(x.inputIndices.includes(z)){let P=R.symbolToIndices.get(C);if(P===void 0)throw new Error("Invalid symbol error");P.forEach(U=>{m.push(`${r[z].indicesSet(`input${z}Indices`,U,`${C}`)}`)}),y.push(`prod *= ${r[z].getByIndices(`input${z}Indices`)};`)}}),_.push(`for(var ${C}: u32 = 0; ${C} < uniforms.${ur(C)}; ${C}++) {`),$.push("}")});let T=g?[...d,`let sum = ${r.map((x,C)=>x.getByIndices(`input${C}Indices`)).join(" * ")};`]:[...d,p,..._,...m,c,...y,h,...$];return`
            ${u.registerUniforms(o.map(x=>({name:`${ur(x)}`,type:"u32"}))).registerUniform("outputSize","u32").declareVariables(...r,a)}

            ${u.mainStart()}
            ${u.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
            var outputIndices = ${a.offsetToIndices("global_idx")};
            ${r.map((x,C)=>`var input${C}Indices: ${r[C].type.indices};`).join(`
`)}
            ${T.join(`
`)};
            ${a.setByOffset("global_idx","sum")};
          }`};return{name:"Einsum",shaderCache:{hint:i.equation,inputDependencies:e.map(()=>"rank")},getRunData:()=>{let u=o.filter(c=>i.symbolToInfo.has(c)).map(c=>({type:12,data:i.symbolToInfo.get(c)?.dimValue||0}));u.push({type:12,data:s});let d=e.map((c,p)=>[...de(c)]).reduce((c,p)=>c.concat(p),u);return d.push(...de(n)),{outputs:[{dims:n,dataType:t}],dispatchGroup:{x:Math.ceil(s/64)},programUniforms:d}},getShaderSource:l}},Vl=(e,t)=>{let i=new Pl(e.inputs,t.equation),n=i.outputDims,r=e.inputs.map((s,a)=>s.dims);e.compute(Nl(r,e.inputs[0].dataType,i,n))},Ll=e=>{let t=e.equation.replace(/\s+/g,"");return Be({equation:t})}}),Ul,dr,ql,Wl,Gl,Fp=E(()=>{ge(),$e(),xe(),Ul=e=>{if(!e||e.length!==2)throw new Error("Expand requires 2 input.");let t=e[0].dims,i=Array.from(e[1].getBigInt64Array(),Number),n=i.length<t.length?0:i.length-t.length,r=t.length<i.length?0:t.length-i.length;for(;n<i.length&&r<t.length;++n,++r)if(i[n]!==t[r]&&i[n]!==1&&t[r]!==1)throw new Error("Expand requires shape to be broadcastable to input")},dr=(e,t)=>{let i=e.length-t.length,n=[];for(let r=0;r<i;++r)n.push(e[r]);for(let r=0;r<t.length;++r)n.push(t[r]===1?e[r+i]:t[r]);return n},ql=(e,t)=>e.length>t.length?dr(e,t):dr(t,e),Wl=e=>{let t=e[0].dims,i=Array.from(e[1].getBigInt64Array(),Number),n=ql(t,i),r=e[0].dataType,s=r===9||O.size(t)===1,a=r===9||t.length>0&&t[t.length-1]%4===0?4:1,o=s||n.length>0&&n[n.length-1]%4===0?4:1,l=Math.ceil(O.size(n)/o),u=c=>{let p=F("input",r,t.length,a),h=oe("output",r,n.length,o),m;if(r===9){let _=($,y,g="")=>`
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
    ${m}`},d=[{type:12,data:l},...de(t,n)];return{name:"Expand",shaderCache:{hint:`${n.length};${a}${o}`,inputDependencies:["rank"]},getShaderSource:u,getRunData:()=>({outputs:[{dims:n,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:d})}},Gl=e=>{Ul(e.inputs),e.compute(Wl(e.inputs),{inputs:[0]})}}),jl,Hl,Pp=E(()=>{ge(),$e(),xe(),jn(),jl=e=>{let t=e[0].dataType,i=O.size(e[0].dims),n=O.size(e[1].dims),r=n%4===0,s=a=>{let o=F("x",t,[1],4),l=F("bias",t,[1],4),u=oe("y",t,[1],4),d=[{name:"output_vec_size",type:"u32"},{name:"bias_size",type:"u32"}],c=h=>`
      let bias${h}_offset: u32 = (global_idx * 4 + ${h}) % uniforms.bias_size;
      let bias${h} = ${l.getByOffset(`bias${h}_offset / 4`)}[bias${h}_offset % 4];`,p=r?`
      let bias = ${l.getByOffset("global_idx % (uniforms.bias_size / 4)")};`:`${c(0)}${c(1)}${c(2)}${c(3)}
      let bias = ${o.type.value}(bias0, bias1, bias2, bias3);`;return`${a.registerUniforms(d).declareVariables(o,l,u)}

    ${Wn(ot(t))}

    ${a.mainStart(ai)}
      ${a.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_vec_size")}

      let x = ${o.getByOffset("global_idx")};
      ${p}
      let x_in = x + bias;
      ${u.setByOffset("global_idx",Gn("x_in"))}
    }`};return{name:"FastGeluWithBias",shaderCache:{hint:`${r}`,inputDependencies:["type","type"]},getShaderSource:s,getRunData:a=>({outputs:[{dims:a[0].dims,dataType:a[0].dataType}],programUniforms:[{type:12,data:Math.ceil(i/4)},{type:12,data:n}],dispatchGroup:{x:Math.ceil(i/ai/4)}})}},Hl=e=>{e.inputs.length<2||O.size(e.inputs[1].dims)===0?Eo(e):e.compute(jl(e.inputs))}}),Kl,Zl,Ql,Xl,Np=E(()=>{ge(),$e(),He(),xe(),Kl=e=>{if(!e||e.length!==2)throw new Error("Gather requires 2 inputs.")},Zl=(e,t)=>{let i=e[0].dims,n=e[1].dims,r=i.length,s=O.normalizeAxis(t.axis,r),a=i.slice(0);a.splice(s,1,...n);let o=i[s],l=e[0].dataType===9?4:1,u=Math.ceil(O.size(a)/l),d=[{type:12,data:u},{type:6,data:o},{type:12,data:s},...de(e[0].dims,e[1].dims,a)],c=p=>{let h=F("data",e[0].dataType,e[0].dims.length,l),m=F("inputIndices",e[1].dataType,e[1].dims.length),_=oe("output",e[0].dataType,a.length,l),$=g=>{let T=n.length,x=`var indicesIndices${g}  = ${m.type.indices}(0);`;for(let C=0;C<T;C++)x+=`${T>1?`indicesIndices${g}[${C}]`:`indicesIndices${g}`} = ${a.length>1?`outputIndices${g}[uniforms.axis + ${C}]`:`outputIndices${g}`};`;x+=`
          var idx${g} = ${m.getByIndices(`indicesIndices${g}`)};
          if (idx${g} < 0) {
            idx${g} = idx${g} + uniforms.axisDimLimit;
          }
          var dataIndices${g} : ${h.type.indices};
        `;for(let C=0,R=0;C<r;C++)C===s?(x+=`${r>1?`dataIndices${g}[${C}]`:`dataIndices${g}`} = u32(idx${g});`,R+=T):(x+=`${r>1?`dataIndices${g}[${C}]`:`dataIndices${g}`} = ${a.length>1?`outputIndices${g}[${R}]`:`outputIndices${g}`};`,R++);return x},y;if(e[0].dataType===9){let g=(T,x,C="")=>`
          let outputIndices${x} = ${_.offsetToIndices(`outputOffset + ${x}u`)};
          ${$(x)};
          let offset${x} = ${h.indicesToOffset(`dataIndices${x}`)};
          let index${x} = offset${x} / 4u;
          let component${x} = offset${x} % 4u;
          ${T}[${x}] = ${C}(${h.getByOffset(`index${x}`)}[component${x}]);
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
      }`};return{name:"Gather",shaderCache:{hint:t.cacheKey,inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:a,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(u/64)},programUniforms:d}),getShaderSource:c}},Ql=e=>Be({axis:e.axis}),Xl=(e,t)=>{let i=e.inputs;Kl(i),e.compute(Zl(e.inputs,t))}}),Yl,Jl,eu,Vp=E(()=>{ge(),$e(),xe(),Yl=(e,t,i,n,r,s,a,o,l)=>{let u=[{type:12,data:s},{type:12,data:n},{type:12,data:r},{type:12,data:i},{type:12,data:a},{type:12,data:o},{type:12,data:l}],d=[s];u.push(...de(t.dims,d));let c=p=>{let h=F("indices_data",t.dataType,t.dims.length),m=oe("input_slice_offsets_data",12,1,1),_=[h,m],$=[{name:"output_size",type:"u32"},{name:"batch_dims",type:"u32"},{name:"input_dims",type:"u32",length:r.length},{name:"sizes_from_slice_dims_data",type:"u32",length:i.length},{name:"num_slices_per_batch",type:"u32"},{name:"input_batch_stride",type:"u32"},{name:"num_slice_dims",type:"u32"}];return`
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
  }`};return e.compute({name:"computeSliceOffsets",shaderCache:{hint:`${r.length}_${i.length}`,inputDependencies:["rank"]},getRunData:()=>({outputs:[{dims:d,dataType:e.inputs[1].dataType}],dispatchGroup:{x:Math.ceil(s/64)},programUniforms:u}),getShaderSource:c},{inputs:[t],outputs:[-1]})[0]},Jl=(e,t)=>{let i=e.inputs,n=i[0].dims,r=i[0].dataType,s=i[1].dims,a=s[s.length-1],o=O.sizeToDimension(s,s.length-1),l=O.sizeFromDimension(n,t.batchDims+a),u=O.sizeToDimension(n,t.batchDims),d=O.sizeFromDimension(n,t.batchDims),c=o/u,p=new Array(a),h=l;for(let x=0;x<a;++x)p[a-1-x]=h,h*=n[t.batchDims+a-1-x];let m=Yl(e,i[1],p,t.batchDims,n,o,c,d,a),_=t.batchDims+a;if(_>n.length)throw new Error("last dimension of indices must not be larger than rank of input tensor");let $=s.slice(0,-1).concat(n.slice(_)),y=O.size($),g=[{type:12,data:y},{type:12,data:l},...de(i[0].dims,m.dims,$)],T=x=>{let C=F("data",i[0].dataType,i[0].dims.length),R=F("slice_offsets",12,m.dims.length),z=oe("output",i[0].dataType,$.length);return`
          ${x.registerUniform("output_size","u32").registerUniform("slice_size","u32").declareVariables(C,R,z)}
            ${x.mainStart()}
            ${x.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
          let slice_offset = slice_offsets[global_idx / uniforms.slice_size];
          output[global_idx] = data[u32(slice_offset) + global_idx % uniforms.slice_size];
        }`};e.compute({name:"GatherND",shaderCache:{hint:t.cacheKey,inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:$,dataType:r}],dispatchGroup:{x:Math.ceil(y/64)},programUniforms:g}),getShaderSource:T},{inputs:[i[0],m]})},eu=e=>({batchDims:e.batch_dims,cacheKey:""})}),tu,iu,nu,ru,Lp=E(()=>{ge(),$e(),He(),xe(),tu=(e,t)=>{if(e.length<3||e.length>4)throw new Error("GatherBlockQuantized requires 3 or 4 inputs.");let i=O.normalizeAxis(t.quantizeAxis,e[0].dims.length),n=t.blockSize,r=e[0],s=e[2],a=e.length===4?e[3]:void 0;if(s.dims.length!==r.dims.length||!r.dims.map((o,l)=>l===i?Math.ceil(o/n)===s.dims[l]:o===s.dims[l]).reduce((o,l)=>o&&l,!0))throw new Error("Scales must have the same rank as the input tensor and the dims should match except on gatherAxis.");if(a){if(a.dataType!==r.dataType)throw new Error("Zero point must have the same data type as the input tensor.");if(a.dims.length!==s.dims.length||!a.dims.map((o,l)=>o===s.dims[l]).reduce((o,l)=>o&&l,!0))throw new Error("Zero point must have the same rank as the input tensor and the dims should match except on quantizeAxis.")}},iu=(e,t)=>{let i=e[0].dims,n=e[1].dims,r=i.length,s=O.normalizeAxis(t.gatherAxis,r),a=O.normalizeAxis(t.quantizeAxis,r),o=i.slice(0);o.splice(s,1,...n);let l=O.size(o),u=e[2].dataType,d=e[0].dataType===22,c=[{type:12,data:l},{type:12,data:a},{type:12,data:s},{type:12,data:t.blockSize},...de(...e.map((h,m)=>h.dims),o)],p=h=>{let m=F("data",e[0].dataType,e[0].dims.length),_=F("inputIndices",e[1].dataType,e[1].dims.length),$=F("scales",e[2].dataType,e[2].dims.length),y=e.length>3?F("zeroPoint",e[3].dataType,e[3].dims.length):void 0,g=oe("output",u,o.length),T=[m,_,$];y&&T.push(y);let x=[{name:"output_size",type:"u32"},{name:"quantize_axis",type:"u32"},{name:"gather_axis",type:"u32"},{name:"block_size",type:"u32"}];return`
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
        let dequantized_data = ${ot(u)}(quantized_data - zero_point) * scale;
        ${g.setByOffset("global_idx","dequantized_data")};
    }`};return{name:"GatherBlockQuantized",shaderCache:{hint:`${t.cacheKey};${e.filter((h,m)=>m!==1).map(h=>h.dims.join("_")).join(";")}`,inputDependencies:Array.from({length:e.length},(h,m)=>"rank")},getRunData:()=>({outputs:[{dims:o,dataType:u}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:c}),getShaderSource:p}},nu=(e,t)=>{let i=e.inputs;tu(i,t),e.compute(iu(e.inputs,t))},ru=e=>Be({blockSize:e.blockSize,gatherAxis:e.gatherAxis,quantizeAxis:e.quantizeAxis})}),su,au,ou,lu,Up=E(()=>{ge(),$e(),He(),xe(),su=e=>{if(!e||e.length!==2)throw new Error("GatherElements requires 2 inputs.");if(e[0].dims.length<1)throw new Error("GatherElements requires that the data input be rank >= 1.");if(e[0].dims.length!==e[1].dims.length)throw new Error(`GatherElements requires that the data input and
                     indices input tensors be of same rank.`)},au=(e,t)=>{let i=e[0].dims,n=e[0].dataType,r=i.length,s=e[1].dims,a=e[1].dataType,o=O.normalizeAxis(t.axis,r),l=i[o],u=s.slice(0),d=O.size(u),c=F("input",n,r),p=F("indicesInput",a,s.length),h=oe("output",n,u.length),m=[{type:12,data:d},{type:6,data:l},{type:12,data:o}];return m.push(...de(i,s,u)),{name:"GatherElements",shaderCache:{inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:u,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(d/64)},programUniforms:m}),getShaderSource:_=>`
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
  }`}},ou=e=>Be({axis:e.axis}),lu=(e,t)=>{let i=e.inputs;su(i),e.compute(au(e.inputs,t))}}),uu,du,cu,pu,qp=E(()=>{ge(),$e(),xe(),uu=e=>{if(!e)throw new Error("Input is missing");if(e.length<2||e.length>3)throw new Error("Invaid input number.");if(e.length===3&&e[2].dims.length>2)throw new Error("Invalid input shape of C");if(e[0].dataType!==e[1].dataType||e.length===3&&e[0].dataType!==e[2].dataType)throw new Error("Input types are mismatched")},du=(e,t)=>{let i=e[0].dims.slice(),n=e[1].dims.slice(),[r,s,a]=bs.getShapeOfGemmResult(i,t.transA,n,t.transB,e.length===3?e[2].dims:void 0),o=[r,s];if(!o)throw new Error("Can't use gemm on the given tensors");let l=16,u=Math.ceil(s/l),d=Math.ceil(r/l),c=!0,p=O.size(o),h=[{type:12,data:c?u:p},{type:12,data:r},{type:12,data:s},{type:12,data:a},{type:1,data:t.alpha},{type:1,data:t.beta}],m=["type","type"];e.length===3&&(h.push(...de(e[2].dims)),m.push("rank")),h.push(...de(o));let _=y=>{let g="";t.transA&&t.transB?g="value += a[k * uniforms.M + m] * b[n * uniforms.K + k];":t.transA&&!t.transB?g="value += a[k * uniforms.M + m] * b[k * uniforms.N + n];":!t.transA&&t.transB?g="value += a[m * uniforms.K + k] * b[n * uniforms.K + k];":!t.transA&&!t.transB&&(g="value += a[m * uniforms.K + k] * b[k * uniforms.N + n];");let T=t.alpha===1?"":"value *= uniforms.alpha;",x=F("a",e[0].dataType,e[0].dims),C=F("b",e[1].dataType,e[1].dims),R=x.type.value,z=null,P=[x,C];e.length===3&&(z=F("c",e[2].dataType,e[2].dims.length),P.push(z));let U=oe("output",e[0].dataType,o.length);P.push(U);let re=[{name:"output_size",type:"u32"},{name:"M",type:"u32"},{name:"N",type:"u32"},{name:"K",type:"u32"},{name:"alpha",type:"f32"},{name:"beta",type:"f32"}];return`
  ${y.registerUniforms(re).declareVariables(...P)}

  ${y.mainStart()}
    ${y.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

    let m = global_idx / uniforms.N;
    let n = global_idx % uniforms.N;

    var value = ${R}(0);
    for (var k: u32 = 0u; k < uniforms.K; k++) {
      ${g}
    }

    ${T}
    ${z!=null?`let cOffset = ${z.broadcastedIndicesToOffset("vec2(m, n)",U)}; value += ${R}(uniforms.beta) * ${z.getByOffset("cOffset")};`:""}
    output[global_idx] = value;
  }`},$=y=>{let g=F("a",e[0].dataType,e[0].dims),T=F("b",e[1].dataType,e[1].dims),x=null,C=[g,T];e.length===3&&(x=F("c",e[2].dataType,e[2].dims.length),C.push(x));let R=oe("output",e[0].dataType,o.length);C.push(R);let z=[{name:"num_tile_n",type:"u32"},{name:"M",type:"u32"},{name:"N",type:"u32"},{name:"K",type:"u32"},{name:"alpha",type:"f32"},{name:"beta",type:"f32"}],P="",U="";t.transA&&t.transB?(U=`
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
      `,P="value += tile_a[k][local_id.y] * tile_b[local_id.x][k];"):t.transA&&!t.transB?(U=`
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
      `,P="value += tile_a[k][local_id.y] * tile_b[k][local_id.x];"):!t.transA&&t.transB?(U=`
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
      `,P="value += tile_a[local_id.y][k] * tile_b[local_id.x][k];"):!t.transA&&!t.transB&&(U=`
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
      `,P="value += tile_a[local_id.y][k] * tile_b[k][local_id.x];");let re=t.alpha===1?"":"value *= uniforms.alpha;";return`
  ${y.registerUniforms(z).declareVariables(...C)}
  var<workgroup> tile_a: array<array<${g.type.storage}, ${l}>, ${l}>;
  var<workgroup> tile_b: array<array<${T.type.storage}, ${l}>, ${l}>;
  ${y.mainStart([l,l,1])}
    let tile_col_start = (workgroup_index % uniforms.num_tile_n) * ${l};
    let tile_row_start = (workgroup_index / uniforms.num_tile_n) * ${l};
    let num_tiles = (uniforms.K - 1) / ${l} + 1;
    var k_start = 0u;
    var value = ${R.type.value}(0);
    for (var t: u32 = 0u; t < num_tiles; t++) {
      ${U}
      k_start = k_start + ${l};
      workgroupBarrier();

      for (var k: u32 = 0u; k < ${l}; k++) {
        ${P}
      }
      workgroupBarrier();
    }

    ${re}
    let m = tile_row_start + local_id.y;
    let n = tile_col_start + local_id.x;
    ${x!=null?`let cOffset = ${x.broadcastedIndicesToOffset("vec2(m, n)",R)}; value += ${R.type.value}(uniforms.beta) * ${x.getByOffset("cOffset")};`:""}
    if (m < uniforms.M && n < uniforms.N) {
      output[m * uniforms.N + n] = value;
    }
  }`};return c?{name:"GemmShared",shaderCache:{hint:`${t.cacheKey}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:o,dataType:e[0].dataType}],dispatchGroup:{x:u*d},programUniforms:h}),getShaderSource:$}:{name:"Gemm",shaderCache:{hint:`${t.cacheKey}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:o,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:h}),getShaderSource:_}},cu=e=>{let t=e.transA,i=e.transB,n=e.alpha,r=e.beta;return{transA:t,transB:i,alpha:n,beta:r,cacheKey:`${e.transA};${e.transB};${e.alpha===1}`}},pu=(e,t)=>{uu(e.inputs),e.compute(du(e.inputs,t))}}),Et,Bt,Qt,Xt,fu,hu,mu,gu,_u,yu,wu,bu,vu,$u,Wp=E(()=>{ge(),$e(),He(),xe(),[Et,Bt,Qt,Xt]=[0,1,2,3],fu=e=>{if(e[0].dims.length!==4)throw new Error("only 4-D tensor is supported.");if(e[0].dims.length!==e[1].dims.length)throw new Error("input dimensions must be equal to grid dimensions");if(e[0].dims.length-2!==e[1].dims[e[1].dims.length-1])throw new Error(`last dimension of grid must be equal to ${e[0].dims.length-2}`);if(e[0].dims[0]!==e[1].dims[0])throw new Error("grid batch size must match input batch size")},hu=`
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
`,mu=e=>`
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
`,gu=e=>`
  fn gs_denormalize(n: f32, length: i32) -> f32 {
    ${e.alignCorners===0?`
    // alignCorners: false => [-1, 1] to [-0.5, length - 0.5]
    return ((n + 1.0) * f32(length) - 1.0) / 2.0;
    `:`
    // alignCorners: true => [-1, 1] to [0, length - 1]
    return (n + 1.0) / 2.0 * (f32(length - 1));
    `}
  }
`,_u=e=>`
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
`,yu=(e,t,i)=>`
  fn pixel_at_grid(r: i32, c: i32, H: i32, W: i32, batch: u32, channel: u32, border: vec4<f32>) -> ${t} {
     var pixel = ${t}(0);
     var indices = vec4<u32>(0);
     indices[${Et}] = batch;
     indices[${Bt}] = channel;`+(()=>{switch(i.paddingMode){case"zeros":return`
          if (r >= 0 && r < H && c >=0 && c < W) {
            indices[${Qt}] = u32(r);
            indices[${Xt}] = u32(c);
          } else {
            return ${t}(0);
          }
        `;case"border":return`
          indices[${Qt}] = u32(clamp(r, 0, H - 1));
          indices[${Xt}] = u32(clamp(c, 0, W - 1));
        `;case"reflection":return`
          indices[${Qt}] = gs_reflect(r, border[1], border[3]);
          indices[${Xt}] = gs_reflect(c, border[0], border[2]);
        `;default:throw new Error(`padding mode ${i.paddingMode} is not supported`)}})()+`
    return ${e.getByIndices("indices")};
  }
`,wu=(e,t,i)=>(()=>{switch(i.mode){case"nearest":return`
          let result = pixel_at_grid(i32(round(y)), i32(round(x)), H_in, W_in, indices[${Et}], indices[${Bt}], border);
        `;case"bilinear":return`
          let x1 = i32(floor(x));
          let y1 = i32(floor(y));
          let x2 = x1 + 1;
          let y2 = y1 + 1;

          let p11 = pixel_at_grid(y1, x1, H_in, W_in, indices[${Et}], indices[${Bt}], border);
          let p12 = pixel_at_grid(y1, x2, H_in, W_in, indices[${Et}], indices[${Bt}], border);
          let p21 = pixel_at_grid(y2, x1, H_in, W_in, indices[${Et}], indices[${Bt}], border);
          let p22 = pixel_at_grid(y2, x2, H_in, W_in, indices[${Et}], indices[${Bt}], border);

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
              p[h][w] = pixel_at_grid(h + y0, w + x0, H_in, W_in, indices[${Et}], indices[${Bt}], border);
            }
          }

          let dx = x - f32(x0 + 1);
          let dy = y - f32(y0 + 1);
          let result = gs_bicubic_interpolate(p, dx, dy);
        `;default:throw new Error(`mode ${i.mode} is not supported`)}})()+`${e.setByOffset("global_idx","result")}`,bu=(e,t)=>{let i=F("x",e[0].dataType,e[0].dims.length),n=[e[1].dims[0],e[1].dims[1],e[1].dims[2]],r=F("grid",e[1].dataType,n.length,2),s=[e[0].dims[0],e[0].dims[1],e[1].dims[1],e[1].dims[2]];t.format==="NHWC"&&(s=[e[0].dims[0],e[1].dims[1],e[1].dims[2],e[0].dims[3]],[Et,Bt,Qt,Xt]=[0,3,1,2]);let a=oe("output",e[0].dataType,s.length),o=i.type.value,l=O.size(s),u=[{type:12,data:l},...de(e[0].dims,n,s)],d=c=>`
  ${c.registerUniform("output_size","u32").declareVariables(i,r,a)}
  ${hu}
  ${mu(o)}
  ${gu(t)}
  ${_u(t)}
  ${yu(i,o,t)}

  ${c.mainStart()}
    ${c.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
      let H_in = i32(uniforms.x_shape[${Qt}]);
      let W_in = i32(uniforms.x_shape[${Xt}]);

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
      var grid_indices = vec3<u32>(indices[${Et}], indices[${Qt}], indices[${Xt}]);
      let nxy = ${r.getByIndices("grid_indices")};
      var x = gs_denormalize(f32(nxy[0]), W_in);
      var y = gs_denormalize(f32(nxy[1]), H_in);

      ${wu(a,o,t)}
  }`;return{name:"GridSample",shaderCache:{hint:`${t.cacheKey}`,inputDependencies:["type","type"]},getRunData:c=>{let p=O.size(s);return{outputs:[{dims:s,dataType:c[0].dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:u}},getShaderSource:d}},vu=(e,t)=>{fu(e.inputs),e.compute(bu(e.inputs,t))},$u=e=>Be({alignCorners:e.align_corners,mode:e.mode,paddingMode:e.padding_mode,format:e.format})}),ut,xu,Su,cr,ku,$i,Tu,Eu=E(()=>{ge(),$e(),He(),zn(),Un(),xe(),Nt(),ut=(e,t)=>e.length>t&&e[t].dims.length>0?e[t]:void 0,xu=(e,t)=>{let i=e[0],n=ut(e,1),r=ut(e,2),s=ut(e,3),a=ut(e,4),o=ut(e,5),l=ut(e,6),u=ut(e,7);if(i.dims.length!==3&&i.dims.length!==5)throw new Error("Input query is expected to have 3 or 5 dimensions");let d=i.dims[0],c=i.dims[1],p=i.dims.length===3?i.dims[2]:t.numHeads*i.dims[4],h=c,m=0,_=0,$=Math.floor(p/t.numHeads);if(l&&u&&O.size(l.dims)&&O.size(u.dims)){if(l.dims.length!==4)throw new Error('Input "past_key" is expected to have 4 dimensions');if(l.dims[0]!==d||l.dims[1]!==t.numHeads||l.dims[3]!==$)throw new Error('Input "past_key" shape (batch_size, num_heads, past_sequence_length, head_size)');if(u.dims[0]!==d||u.dims[1]!==t.numHeads||u.dims[3]!==$)throw new Error('Input "past_value" shape (batch_size, num_heads, past_sequence_length, head_size)');if(l.dims[2]!==u.dims[2])throw new Error('Input "past_key" and "past_value" shall have same dim 2 (past_sequence_length)');if(u.dims.length!==4)throw new Error('Input "past_value" is expected to have 4 dimensions');m=l.dims[2],_=l.dims[2]}else if(l&&O.size(l.dims)||u&&O.size(u.dims))throw new Error('Input "past_key" and "past_value" shall be both present or both absent');let y;if(n&&O.size(n.dims)>0){if(i.dims.length!==3)throw new Error('Input "query" is expected to have 3 dimensions when key is given');if(n.dims.length<3||n.dims.length>5)throw new Error('Input "key" is expected to have 3, 4, or 5 dimensions');if(i.dims[0]!==n.dims[0])throw new Error('Input "query" and "key" shall have same dim 0 (batch size)');if(n.dims.length===3){if(n.dims[2]!==i.dims[2])throw new Error('Input "query" and "key" shall have same dim 2 (hidden_size)');y=2,h=n.dims[1]}else if(n.dims.length===5){if(n.dims[2]!==t.numHeads||n.dims[3]!==2||n.dims[4]!==$)throw new Error('Expect "key" shape (batch_size, kv_sequence_length, num_heads, 2, head_size) for packed kv');if(r)throw new Error('Expect "value" be none when "key" has packed kv format.');y=5,h=n.dims[1]}else{if(n.dims[1]!==t.numHeads||n.dims[3]!==$)throw new Error('Expect "key" shape (batch_size, num_heads, kv_sequence_length, head_size) for past_key');y=0,h=n.dims[2]}}else{if(i.dims.length!==5)throw new Error('Input "query" is expected to have 5 dimensions when key is empty');if(i.dims[2]!==t.numHeads||i.dims[3]!==3)throw new Error('Expect "query" shape (batch_size, kv_sequence_length, num_heads, 3, head_size) for packed kv');y=3}if(s&&O.size(s.dims)>0){if(s.dims.length!==1)throw new Error('Input "bias" is expected to have 1 dimension');if(n&&n.dims.length===5&&n.dims[3]===2)throw new Error("bias is not allowed for packed kv.")}let g=m+h,T=0;if(a&&O.size(a.dims)>0){T=8;let z=a.dims;throw z.length===1?z[0]===d?T=1:z[0]===3*d+2&&(T=3):z.length===2&&z[0]===d&&z[1]===g&&(T=5),T===8?new Error('Input "key_padding_mask" shape shall be (batch_size) or (batch_size, total_sequence_length)'):new Error("Mask not supported")}let x=!1,C=p;if(r&&O.size(r.dims)>0){if(r.dims.length!==3&&r.dims.length!==4)throw new Error('Input "value" is expected to have 3 or 4 dimensions');if(i.dims[0]!==r.dims[0])throw new Error('Input "query" and "value" shall have same dim 0 (batch_size)');if(r.dims.length===3){if(h!==r.dims[1])throw new Error('Input "key" and "value" shall have the same dim 1 (kv_sequence_length)');C=r.dims[2]}else{if(h!==r.dims[2])throw new Error('Input "key" and "value" shall have the same dim 2 (kv_sequence_length)');C=r.dims[1]*r.dims[3],x=!0}}let R=!1;if(a&&O.size(a.dims)>0)throw new Error("Key padding mask is not supported");if(o&&O.size(o.dims)>0){if(o.dims.length!==4)throw new Error('Input "attention_bias" is expected to have 4 dimensions');if(o.dims[0]!==d||o.dims[1]!==t.numHeads||o.dims[2]!==c||o.dims[3]!==g)throw new Error('Expect "attention_bias" shape (batch_size, num_heads, sequence_length, total_sequence_length)')}return{batchSize:d,sequenceLength:c,pastSequenceLength:m,kvSequenceLength:h,totalSequenceLength:g,maxSequenceLength:_,inputHiddenSize:0,hiddenSize:p,vHiddenSize:C,headSize:$,vHeadSize:Math.floor(C/t.numHeads),numHeads:t.numHeads,isUnidirectional:!1,pastPresentShareBuffer:!1,maskFilterValue:t.maskFilterValue,maskType:T,scale:t.scale,broadcastResPosBias:R,passPastInKv:x,qkvFormat:y}},Su=e=>Be({...e}),cr=Be({perm:[0,2,1,3]}),ku=(e,t,i,n,r,s,a)=>{let o=[n,r,s],l=O.size(o),u=[{type:12,data:l},{type:12,data:a},{type:12,data:s}],d=c=>{let p=oe("qkv_with_bias",t.dataType,o),h=F("qkv",t.dataType,o),m=F("bias",i.dataType,o),_=[{name:"output_size",type:"u32"},{name:"bias_offset",type:"u32"},{name:"hidden_size",type:"u32"}];return`
  ${c.registerUniforms(_).declareVariables(h,m,p)}
  ${c.mainStart()}
    ${c.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
    let bias_offset_idx = (global_idx % uniforms.hidden_size) + uniforms.bias_offset;

    qkv_with_bias[global_idx] = qkv[global_idx] + bias[bias_offset_idx];
  }`};return e.compute({name:"MultiHeadAttentionAddBias",shaderCache:{inputDependencies:["type","type"]},getRunData:()=>({outputs:[{dims:o,dataType:t.dataType,gpuDataType:0}],dispatchGroup:{x:Math.ceil(l/64)},programUniforms:u}),getShaderSource:d},{inputs:[t,i],outputs:[-1]})[0]},$i=(e,t,i,n,r,s,a,o)=>{let l=s;if(a&&O.size(a.dims)>0){if(n===1)throw new Error("AddBiasReshape is not implemented. Please export your model with packed QKV or KV");return l=ku(e,s,a,t,n,i*r,o),l=l.reshape([t,n,i,r]),i===1||n===1?l:e.compute(ft(l,cr.perm),{inputs:[l],outputs:[-1]})[0]}else return s.dims.length===3&&(l=s.reshape([t,n,i,r])),i===1||n===1?l:e.compute(ft(l,cr.perm),{inputs:[l],outputs:[-1]})[0]},Tu=(e,t)=>{let i=xu(e.inputs,t),n=e.inputs[0],r=ut(e.inputs,1),s=ut(e.inputs,2),a=ut(e.inputs,3),o=ut(e.inputs,4),l=ut(e.inputs,5),u=ut(e.inputs,6),d=ut(e.inputs,7);if(n.dims.length===5)throw new Error("Packed QKV is not implemented");if(r?.dims.length===5)throw new Error("Packed KV is not implemented");let c=r&&s&&r.dims.length===4&&s.dims.length===4,p=$i(e,i.batchSize,i.numHeads,i.sequenceLength,i.headSize,n,a,0);if(c)return _i(e,p,r,s,o,void 0,u,d,l,i);if(!r||!s)throw new Error("key and value must be provided");let h=$i(e,i.batchSize,i.numHeads,i.kvSequenceLength,i.headSize,r,a,i.hiddenSize),m=$i(e,i.batchSize,i.numHeads,i.kvSequenceLength,i.vHeadSize,s,a,2*i.hiddenSize);_i(e,p,h,m,o,void 0,u,d,l,i)}}),Cu,Iu,Au,zu,pr,Mu,Ru,Ou=E(()=>{ge(),$e(),He(),xe(),Cu=e=>{if(!e||e.length<1)throw new Error("too few inputs")},Iu=(e,t)=>{let i=[],n=t.numOutputs;return e[1].dims[0]>0&&(e[1].getBigInt64Array().forEach(r=>i.push(Number(r))),n=i.length),Be({numOutputs:n,axis:t.axis,splitSizes:i})},Au=e=>`
fn calculateOutputIndex(index: u32) -> u32 {
    for (var i: u32 = 0u; i < ${e}u; i += 1u ) {
    if (index < ${le("uniforms.size_in_split_axis","i",e)}) {
        return i;
    }
    }
    return ${e}u;
}`,zu=e=>{let t=e.length,i=[];for(let n=0;n<t;++n){let r=e[n].setByIndices("indices","input[global_idx]");t===1?i.push(r):n===0?i.push(`if (output_number == ${n}u) { ${r} }`):n===t-1?i.push(`else { ${r} }`):i.push(`else if (output_number == ${n}) { ${r} }`)}return`
      fn writeBufferData(output_number: u32, indices: ${e[0].type.indices}, global_idx: u32) {
        ${i.join(`
`)}
      }`},pr=(e,t)=>{let i=e[0].dims,n=O.size(i),r=e[0].dataType,s=O.normalizeAxis(t.axis,i.length),a=new Array(t.numOutputs),o=F("input",r,i.length),l=new Array(t.numOutputs),u=[],d=[],c=0,p=[{type:12,data:n}];for(let m=0;m<t.numOutputs;m++){c+=t.splitSizes[m],l[m]=c;let _=i.slice();_[s]=t.splitSizes[m],d.push(_),a[m]=oe(`output${m}`,r,_.length),u.push({dims:d[m],dataType:e[0].dataType})}p.push({type:12,data:l},...de(i,...d));let h=m=>`
  ${m.registerUniform("input_size","u32").registerUniform("size_in_split_axis","u32",l.length).declareVariables(o,...a)}
  ${Au(l.length)}
  ${zu(a)}

  ${m.mainStart()}
    ${m.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.input_size")}

    var indices = ${o.offsetToIndices("global_idx")};
    var index = ${o.indicesGet("indices",s)};
    let output_number = calculateOutputIndex(index);
    if (output_number != 0) {
      index -= ${le("uniforms.size_in_split_axis","output_number - 1u",l.length)};
      ${o.indicesSet("indices",s,"index")};
    }
    writeBufferData(output_number, indices, global_idx);
  }`;return{name:"Split",shaderCache:{hint:t.cacheKey,inputDependencies:["rank"]},getShaderSource:h,getRunData:()=>({outputs:u,dispatchGroup:{x:Math.ceil(n/64)},programUniforms:p})}},Mu=(e,t)=>{Cu(e.inputs);let i=e.inputs.length===1?t:Iu(e.inputs,t);e.compute(pr(e.inputs,i),{inputs:[0]})},Ru=e=>{let t=e.axis,i=e.splitSizes,n=e.numOutputs<0?i.length:e.numOutputs;if(n!==i.length)throw new Error("numOutputs and splitSizes length must be equal");return Be({axis:t,numOutputs:n,splitSizes:i})}}),Du,Ki,Bu,Fu=E(()=>{ge(),$e(),He(),xe(),Du=(e,t)=>{let[i,n,r,s]=e,{numHeads:a,rotaryEmbeddingDim:o}=t;if(i.dims.length!==3&&i.dims.length!==4)throw new Error(`Input 'x' is expected to have 3 or 4 dimensions, got ${i.dims.length}`);if(!O.areEqual(n.dims,[])&&!O.areEqual(n.dims,[1])&&n.dims.length!==2)throw new Error(`Input 'position_ids' is expected to have 0, 1, or 2 dimensions, got ${n.dims.length}`);if(r.dims.length!==2)throw new Error(`Input 'cos_cache' is expected to have 2 dimensions, got ${r.dims.length}`);if(s.dims.length!==2)throw new Error(`Input 'sin_cache' is expected to have 2 dimensions, got ${s.dims.length}`);if(!O.areEqual(r.dims,s.dims))throw new Error("Inputs 'cos_cache' and 'sin_cache' are expected to have the same shape");if(o>0&&a===0)throw new Error("num_heads must be provided if rotary_embedding_dim is specified");let l=i.dims[0],u=i.dims[i.dims.length-2],d=r.dims[0],c=O.sizeFromDimension(i.dims,1)/u,p=o===0?r.dims[1]*2:c/a;if(o>p)throw new Error("rotary_embedding_dim must be less than or equal to head_size");if(n.dims.length===2){if(l!==n.dims[0])throw new Error(`Input 'position_ids' dimension 0 should be of size batch_size, got ${n.dims[0]}`);if(u!==n.dims[1])throw new Error(`Input 'position_ids' dimension 1 should be of size sequence_length, got ${n.dims[1]}`)}if(p/2!==r.dims[1]&&o/2!==r.dims[1])throw new Error(`Input 'cos_cache' dimension 1 should be same as head_size / 2 or rotary_embedding_dim / 2, got ${r.dims[1]}`);if(u>d)throw new Error("Updating cos_cache and sin_cache in RotaryEmbedding is not currently supported")},Ki=(e,t)=>{let{interleaved:i,numHeads:n,rotaryEmbeddingDim:r,scale:s}=t,a=e[0].dims[0],o=O.sizeFromDimension(e[0].dims,1),l=e[0].dims[e[0].dims.length-2],u=o/l,d=e[2].dims[1],c=r===0?d*2:u/n,p=new Array(a,l,u/c,c-d),h=O.computeStrides(p),m=[{type:1,data:s},{type:12,data:p},{type:12,data:h},...e[0].dims.length===3?new Array({type:12,data:[o,u,c,1]}):[],...e[0].dims.length===4?new Array({type:12,data:[o,c,l*c,1]}):[],...de(e[0].dims,e[1].dims,e[2].dims,e[3].dims,e[0].dims)],_=$=>{let y=F("input",e[0].dataType,e[0].dims.length),g=F("position_ids",e[1].dataType,e[1].dims.length),T=F("cos_cache",e[2].dataType,e[2].dims.length),x=F("sin_cache",e[3].dataType,e[3].dims.length),C=oe("output",e[0].dataType,e[0].dims.length);return $.registerUniforms([{name:"scale",type:"f32"},{name:"global_shape",type:"u32",length:p.length},{name:"global_strides",type:"u32",length:h.length},{name:"input_output_strides",type:"u32",length:h.length}]),`
        ${$.declareVariables(y,g,T,x,C)}

        ${$.mainStart(ai)}
          let half_rotary_emb_dim = uniforms.${T.name}_shape[1];
          let bsnh = global_idx / uniforms.global_strides % uniforms.global_shape;
          let size = uniforms.global_shape[0] * uniforms.global_strides[0];
          ${$.guardAgainstOutOfBoundsWorkgroupSizes("size")}

          if (bsnh[3] < half_rotary_emb_dim) {
            let position_ids_idx =
                ${g.broadcastedIndicesToOffset("bsnh.xy",oe("",g.type.tensor,2))};
            let position_id =
                u32(${g.getByOffset("position_ids_idx")}) + select(0, bsnh[1], position_ids_idx == 0);
            let i = dot(bsnh, uniforms.input_output_strides) + select(0, bsnh[3], ${i});
            let j = i + select(half_rotary_emb_dim, 1, ${i});
            let re = ${y.getByOffset("i")} * ${T.get("position_id","bsnh[3]")} -
                ${y.getByOffset("j")} * ${x.get("position_id","bsnh[3]")};
            ${C.setByOffset("i","re")}
            let im = ${y.getByOffset("i")} * ${x.get("position_id","bsnh[3]")} +
                ${y.getByOffset("j")} * ${T.get("position_id","bsnh[3]")};
            ${C.setByOffset("j","im")}
          } else {
            let k = dot(bsnh, uniforms.input_output_strides) + half_rotary_emb_dim;
            ${C.setByOffset("k",y.getByOffset("k"))}
          }
        }`};return{name:"RotaryEmbedding",shaderCache:{hint:Be({interleaved:i}).cacheKey,inputDependencies:["rank","rank","rank","rank"]},getShaderSource:_,getRunData:()=>({outputs:[{dims:e[0].dims,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(O.size(p)/ai)},programUniforms:m})}},Bu=(e,t)=>{Du(e.inputs,t),e.compute(Ki(e.inputs,t))}}),Pu,Nu,fr,Vu,Lu,Gp=E(()=>{He(),ge(),Un(),Eu(),Ou(),Nt(),Fu(),xe(),Pu=(e,t)=>{if(t.doRotary&&e.length<=7)throw new Error("cos_cache and sin_cache inputs are required if do_rotary is specified");let i=e[0],n=e[1],r=e[2],s=e[3],a=e[4];if(t.doRotary!==0&&e.length<=7)throw new Error("cos_cast and sin_cache are expected if do_rotary attribute is non-zero");if(t.localWindowSize!==-1)throw new Error("Local attention is not supported");if(t.softcap!==0)throw new Error("Softcap is not supported");if(t.rotaryInterleaved!==0)throw new Error("Rotary interleaved is not supported");if(t.smoothSoftmax)throw new Error("Smooth softmax is not supported");if(i.dims.length!==3&&i.dims.length!==5)throw new Error("Input query is expected to have 3 or 5 dimensions");let o=!1,l=i.dims[0],u=i.dims[1],d=i.dims.length===3?o?i.dims[2]/3:i.dims[2]:t.numHeads*i.dims[4],c=u,p=0,h=!n||n.dims.length===0,m=Math.floor(h?d/(t.numHeads+2*t.kvNumHeads):d/t.numHeads);h&&(d=m*t.numHeads);let _=s&&s.dims.length!==0,$=a&&a.dims.length!==0;if(_&&s.dims.length===4&&s.dims[0]===l&&s.dims[1]!==t.kvNumHeads&&s.dims[2]===t.kvNumHeads&&s.dims[3]===m)throw new Error("BSNH pastKey/pastValue is not supported");if(_&&$){if(s.dims.length!==4)throw new Error('Input "past_key" is expected to have 4 dimensions');if(a.dims.length!==4)throw new Error('Input "past_value" is expected to have 4 dimensions');p=s.dims[2]}else if(_||$)throw new Error('Input "past_key" and "past_value" shall be both present or both absent');let y=1;if(n&&n.dims.length>0){if(i.dims.length!==3)throw new Error('Input "query" is expected to have 3 dimensions when key is given');if(n.dims.length<3||n.dims.length>5)throw new Error('Input "key" is expected to have 3, 4, or 5 dimensions');if(i.dims[0]!==n.dims[0])throw new Error('Input "query" and "key" shall have same dim 0 (batch size)');if(n.dims.length===3){if(i.dims[2]%n.dims[2]!==0)throw new Error('Dimension 2 of "query" should be a multiple of "key"');c=n.dims[1]}else if(n.dims.length===5){if(n.dims[2]!==t.numHeads||n.dims[3]!==2||n.dims[4]!==m)throw new Error('Expect "key" shape (batch_size, kv_sequence_length, num_heads, 2, head_size) for packed kv');if(r)throw new Error('Expect "value" be none when "key" has packed kv format.');c=n.dims[1]}else{if(n.dims[1]!==t.numHeads||n.dims[3]!==m)throw new Error('Expect "key" shape (batch_size, num_heads, kv_sequence_length, head_size) for past_key');c=n.dims[2]}}else{if(i.dims.length!==3&&i.dims.length!==5)throw new Error('Input "query" is expected to have 3 or 5 dimensions when key is empty');if(i.dims.length===5&&(i.dims[2]!==t.numHeads||i.dims[3]!==3))throw new Error('Expect "query" shape (batch_size, kv_sequence_length, num_heads, 3, head_size) for packed kv');y=3}let g=0,T=!1,x=t.kvNumHeads?m*t.kvNumHeads:d;if(r&&r.dims.length>0){if(r.dims.length!==3&&r.dims.length!==4)throw new Error('Input "value" is expected to have 3 or 4 dimensions');if(i.dims[0]!==r.dims[0])throw new Error('Input "query" and "value" shall have same dim 0 (batch_size)');if(r.dims.length===3){if(c!==r.dims[1])throw new Error('Input "key" and "value" shall have the same dim 1 (kv_sequence_length)');x=r.dims[2]}else{if(c!==r.dims[2])throw new Error('Input "past_key" and "past_value" shall have the same dim 2 (kv_sequence_length)');x=r.dims[1]*r.dims[3],T=!0}}let C=e.length>4?e[5]:void 0;if(C&&C.dims.length!==1&&C.dims[0]!==l)throw new Error('Input "seqlens" is expected to have 1 dimension and the same dim 0 as batch_size');return{batchSize:l,sequenceLength:u,pastSequenceLength:p,kvSequenceLength:c,totalSequenceLength:-1,maxSequenceLength:-1,inputHiddenSize:0,hiddenSize:d,vHiddenSize:x,headSize:m,vHeadSize:Math.floor(x/t.kvNumHeads),numHeads:t.numHeads,kvNumHeads:t.kvNumHeads,nReps:t.numHeads/t.kvNumHeads,pastPresentShareBuffer:!1,maskType:g,scale:t.scale,broadcastResPosBias:!1,passPastInKv:T,qkvFormat:y}},Nu=Be({perm:[0,2,1,3]}),fr=(e,t,i)=>{let n=t,r=i.kvNumHeads;return t.dims.length===3&&i.kvSequenceLength!==0&&(n=t.reshape([i.batchSize,i.kvSequenceLength,r,i.headSize]),n=e.compute(ft(n,Nu.perm),{inputs:[n],outputs:[-1]})[0]),n},Vu=(e,t,i,n)=>{let r=7,s=["type","type"],a=[e*t],o=e*t,l=[{type:12,data:o},{type:12,data:t},{type:12,data:e}],u=d=>{let c=F("seq_lens",i.dataType,i.dims),p=F("total_seq_lens",n.dataType,n.dims),h=oe("pos_ids",r,a),m=[{name:"output_size",type:"u32"},{name:"sequence_length",type:"u32"},{name:"batch_size",type:"u32"}];return`
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
  `};return{name:"GeneratePositionIds",shaderCache:{hint:`${e};${t}`,inputDependencies:s},getRunData:()=>({outputs:[{dims:a,dataType:r}],dispatchGroup:{x:Math.ceil(o/64)},programUniforms:l}),getShaderSource:u}},Lu=(e,t)=>{let i=Pu(e.inputs,t);if(e.inputs[0].dims.length===5)throw new Error("Packed QKV is not implemented");if(e.inputs[1]?.dims.length===5)throw new Error("Packed KV is not implemented");let n=e.inputs[0],r=e.inputs[1]&&e.inputs[1].dims.length>0?e.inputs[1]:void 0,s=e.inputs[2]&&e.inputs[2].dims.length>0?e.inputs[2]:void 0,a=e.inputs[3]&&e.inputs[3].dims.length!==0?e.inputs[3]:void 0,o=e.inputs[4]&&e.inputs[4].dims.length!==0?e.inputs[4]:void 0,l=e.inputs.length>4?e.inputs[5]:void 0,u=e.inputs.length>5?e.inputs[6]:void 0,d=i.kvNumHeads?i.kvNumHeads:i.numHeads,c=Be({axis:2,numOutputs:3,splitSizes:[i.numHeads*i.headSize,d*i.headSize,d*i.headSize]}),[p,h,m]=!r&&!s?e.compute(pr([n],c),{inputs:[n],outputs:[-1,-1,-1]}):[n,r,s],_,$;if(t.doRotary){let x=e.compute(Vu(i.batchSize,i.sequenceLength,l,u),{inputs:[l,u],outputs:[-1]})[0],C=e.inputs[7],R=e.inputs[8],z=Be({interleaved:t.rotaryInterleaved!==0,numHeads:i.numHeads,rotaryEmbeddingDim:0,scale:t.scale}),P=[p,x,C,R],U=[-1];_=e.compute(Ki(P,z),{inputs:P,outputs:U})[0],P.splice(0,1,h);let re=Be({interleaved:t.rotaryInterleaved!==0,numHeads:i.kvNumHeads,rotaryEmbeddingDim:0,scale:t.scale});$=e.compute(Ki(P,re),{inputs:P,outputs:U})[0]}let y=$i(e,i.batchSize,i.numHeads,i.sequenceLength,i.headSize,t.doRotary?_:p,void 0,0),g=fr(e,t.doRotary?$:h,i),T=fr(e,m,i);_i(e,y,g,T,void 0,void 0,a,o,void 0,i,l,u)}}),hr,Uu,qu,Wu,jp=E(()=>{ge(),$e(),Nt(),xe(),hr=(e,t,i,n,r,s,a,o)=>{let l=je(s),u=l===1?"f32":`vec${l}f`,d=l===1?"vec2f":`mat2x${l}f`,c=r*a,p=64;c===1&&(p=256);let h=[r,a,s/l],m=[r,a,2],_=["rank","type","type"],$=[];$.push(...de(h,m));let y=g=>{let T=F("x",t.dataType,3,l),x=F("scale",i.dataType,i.dims),C=F("bias",n.dataType,n.dims),R=oe("output",1,3,2),z=[T,x,C,R];return`
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
      let sum_final = ${Pt("workgroup_shared[0][0]",l)} / f32(hight * ${l});
      let squared_sum_final = ${Pt("workgroup_shared[0][1]",l)} / f32(hight * ${l});

      let inv_std_dev = inverseSqrt(squared_sum_final - sum_final * sum_final + f32(${o}));
      let channel_scale = inv_std_dev * f32(scale[channel]);
      let channel_shift = f32(bias[channel]) - sum_final * channel_scale;
      output[workgroup_index] = vec2f(channel_scale, channel_shift);
    }
  }`};return e.compute({name:"InstanceNormComputeChannelScaleShift",shaderCache:{hint:`${l};${o};${p}`,inputDependencies:_},getRunData:()=>({outputs:[{dims:m,dataType:1}],dispatchGroup:{x:c},programUniforms:$}),getShaderSource:y},{inputs:[t,i,n],outputs:[-1]})[0]},Uu=(e,t,i)=>{let n=t[0].dims,r=n,s=2,a=n[0],o=n[1],l=O.sizeFromDimension(n,s),u=je(l),d=O.size(r)/u,c=hr(e,t[0],t[1],t[2],a,l,o,i.epsilon),p=[a,o,l/u],h=[a,o],m=["type","none"],_=$=>{let y=F("x",t[0].dataType,p.length,u),g=F("scale_shift",1,h.length,2),T=oe("output",t[0].dataType,p.length,u),x=[y,g,T];return`
  ${$.registerUniform("output_size","u32").declareVariables(...x)}
  ${$.mainStart()}
  ${$.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
      let outputIndices = ${T.offsetToIndices("global_idx")};
      let batch = outputIndices[0];
      let channel = outputIndices[1];
      let scale_shift = ${g.getByIndices("vec2<u32>(batch, channel)")};
      let value = ${y.getByOffset("global_idx")} * ${T.type.value}(scale_shift.x) + ${T.type.value}(scale_shift.y);
      ${T.setByOffset("global_idx","value")};
  }`};e.compute({name:"InstanceNormalization",shaderCache:{hint:`${u}`,inputDependencies:m},getRunData:()=>({outputs:[{dims:r,dataType:t[0].dataType}],dispatchGroup:{x:Math.ceil(d/64)},programUniforms:[{type:12,data:d},...de(p,h,p)]}),getShaderSource:_},{inputs:[t[0],c]})},qu=(e,t,i)=>{let n=t[0].dims,r=n,s=n[0],a=n[n.length-1],o=O.sizeFromDimension(n,1)/a,l=je(a),u=O.size(r)/l,d=[{type:12,data:o},{type:12,data:Math.floor(a/l)}],c=["type","type"],p=!1,h=[0,n.length-1];for(let y=0;y<n.length-2;y++)p=p||n[y+1]!==1,h.push(y+1);p=p&&n[n.length-1]!==1;let m=p?e.compute(ft(e.inputs[0],h),{inputs:[e.inputs[0]],outputs:[-1]})[0]:e.inputs[0].reshape(Array.from({length:n.length},(y,g)=>n[h[g]])),_=hr(e,m,t[1],t[2],s,o,a,i.epsilon),$=y=>{let g=et(t[0].dataType),T=l===1?"vec2f":`mat${l}x2f`,x=z=>{let P=z===0?"x":"y",U=l===1?"f32":`vec${l}f`;switch(l){case 1:return`${g}(${U}(scale.${P}))`;case 2:return`vec2<${g}>(${U}(scale[0].${P}, scale[1].${P}))`;case 4:return`vec4<${g}>(${U}(scale[0].${P}, scale[1].${P}, scale[2].${P}, scale[3].${P}))`;default:throw new Error(`Not supported compoents ${l}`)}},C=F("input",t[0].dataType,t[0].dims,l),R=oe("output",t[0].dataType,r,l);return`
  @group(0) @binding(0) var<storage, read> input : array<${C.type.storage}>;
  @group(0) @binding(1) var<storage, read> scale_input : array<${T}>;
  @group(0) @binding(2) var<storage, read_write> output : array<${R.type.storage}>;
  struct Uniforms {H: u32, C : u32};
  @group(0) @binding(3) var<uniform> uniforms: Uniforms;

  ${y.mainStart()}
    let current_image_number = global_idx / (uniforms.C * uniforms.H);
    let current_channel_number = global_idx % uniforms.C;

    let scale_offset = current_image_number * uniforms.C + current_channel_number;
    let scale = scale_input[scale_offset];
    output[global_idx] = fma(input[global_idx], ${x(0)}, ${x(1)});
  }`};e.compute({name:"InstanceNormalizationNHWC",shaderCache:{hint:`${l}`,inputDependencies:c},getRunData:()=>({outputs:[{dims:r,dataType:t[0].dataType}],dispatchGroup:{x:Math.ceil(u/64)},programUniforms:d}),getShaderSource:$},{inputs:[t[0],_]})},Wu=(e,t)=>{t.format==="NHWC"?qu(e,e.inputs,t):Uu(e,e.inputs,t)}}),Gu,ju,Hu,Hp=E(()=>{ge(),$e(),xe(),Gu=e=>{if(!e||e.length<2)throw new Error("layerNorm requires at least 2 inputs.")},ju=(e,t,i)=>{let n=t.simplified,r=e[0].dims,s=e[1],a=!n&&e[2],o=r,l=O.normalizeAxis(t.axis,r.length),u=O.sizeToDimension(r,l),d=O.sizeFromDimension(r,l),c=O.size(s.dims),p=a?O.size(a.dims):0;if(c!==d||a&&p!==d)throw new Error(`Size of X.shape()[axis:] == ${d}.
       Size of scale and bias (if provided) must match this.
       Got scale size of ${c} and bias size of ${p}`);let h=[];for(let C=0;C<r.length;++C)C<l?h.push(r[C]):h.push(1);let m=je(d),_=["type","type"],$=[{type:12,data:u},{type:1,data:d},{type:12,data:Math.floor(d/m)},{type:1,data:t.epsilon}];a&&_.push("type");let y=i>1,g=i>2,T=C=>{let R=et(e[0].dataType),z=[F("x",e[0].dataType,e[0].dims,m),F("scale",s.dataType,s.dims,m)];a&&z.push(F("bias",a.dataType,a.dims,m)),z.push(oe("output",e[0].dataType,o,m)),y&&z.push(oe("mean_data_output",1,h)),g&&z.push(oe("inv_std_output",1,h));let P=[{name:"norm_count",type:"u32"},{name:"norm_size",type:"f32"},{name:"norm_size_vectorized",type:"u32"},{name:"epsilon",type:"f32"}];return`
  ${C.registerUniforms(P).declareVariables(...z)}
  ${C.mainStart()}
    ${C.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.norm_count")}
    let offset = global_idx * uniforms.norm_size_vectorized;
    var mean_vector = ${Dn("f32",m)};
    var mean_square_vector = ${Dn("f32",m)};

    for (var h: u32 = 0u; h < uniforms.norm_size_vectorized; h++) {
      let value = ${oi(R,m,"x[h + offset]")};
      mean_vector += value;
      mean_square_vector += value * value;
    }
    let mean = ${Pt("mean_vector",m)} / uniforms.norm_size;
    let inv_std_dev = inverseSqrt(${Pt("mean_square_vector",m)} / uniforms.norm_size ${n?"":"- mean * mean"} + uniforms.epsilon);

    for (var j: u32 = 0; j < uniforms.norm_size_vectorized; j++) {
      let f32input = ${oi(R,m,"x[j + offset]")};
      let f32scale = ${oi(R,m,"scale[j]")};
      output[j + offset] = ${z[0].type.value}((f32input ${n?"":"- mean"}) * inv_std_dev * f32scale
        ${a?`+ ${oi(R,m,"bias[j]")}`:""}
      );
    }

    ${y?"mean_data_output[global_idx] = mean":""};
    ${g?"inv_std_output[global_idx] = inv_std_dev":""};
  }`},x=[{dims:o,dataType:e[0].dataType}];return y&&x.push({dims:h,dataType:1}),g&&x.push({dims:h,dataType:1}),{name:"LayerNormalization",shaderCache:{hint:`${m};${i};${n}`,inputDependencies:_},getRunData:()=>({outputs:x,dispatchGroup:{x:Math.ceil(u/64)},programUniforms:$}),getShaderSource:T}},Hu=(e,t)=>{Gu(e.inputs),e.compute(ju(e.inputs,t,e.outputCount))}}),Ku,Zu,Kp=E(()=>{$e(),Qn(),er(),Ku=e=>{if(!e||e.length!==2)throw new Error("MatMul requires 2 inputs.");if(e[0].dims[e[0].dims.length-1]!==e[1].dims[e[1].dims.length-2])throw new Error("shared dimension does not match.")},Zu=e=>{Ku(e.inputs);let t=si.calcShape(e.inputs[0].dims,e.inputs[1].dims,!0);if(!t)throw new Error("Can't use matmul on the given tensors");let i=t[t.length-1],n=e.inputs[0].dims[e.inputs[0].dims.length-1];if(i<8&&n<8)e.compute(Zn(e.inputs,{activation:""},t));else{let r=t[t.length-2],s=O.size(e.inputs[0].dims.slice(0,-2)),a=O.size(e.inputs[1].dims.slice(0,-2));if(s!==1&&r===1&&a===1){let o=e.inputs[0].reshape([1,s,n]),l=e.inputs[1].reshape([1,n,i]),u=[1,s,i],d=[o,l];e.compute(Wi(d,{activation:""},t,u),{inputs:d})}else e.compute(Wi(e.inputs,{activation:""},t))}}}),Qu,Xu,Yu,Ju,ed,Zp=E(()=>{ge(),$e(),He(),xe(),Qu=(e,t)=>{if(e.length<3||e.length>4)throw new Error("MatMulNBits requires 3 or 4 inputs");let i=e[0],n=i.dims.length;if(i.dims[n-1]!==t.k)throw new Error("The last dim of input shape does not match the k value");let r=Math.floor((t.k+t.blockSize-1)/t.blockSize),s=t.blockSize/8*t.bits,a=e[1];if(!O.areEqual(a.dims,[t.n,r,s]))throw new Error("The second inputs must be 3D tensor with shape N X nBlocksPerCol X blobSize");let o=e[2].dims;if(O.size(o)!==t.n*r)throw new Error("scales input size error.");if(e.length===4){let l=e[3].dims,u=t.n*(t.bits===8?r:Math.floor((r*t.bits+7)/8));if(O.size(l)!==u)throw new Error("zeroPoints input size error.")}},Xu=(e,t)=>{let i=e[0].dims,n=i.length,r=i[n-2],s=t.k,a=t.n,o=i.slice(0,n-2),l=O.size(o),u=e[1].dims[2]/4,d=e[0].dataType,c=je(t.k),p=je(u),h=je(a),m=o.concat([r,a]),_=r>1&&a/h%2===0?2:1,$=O.size(m)/h/_,y=64,g=[],T=[l,r,s/c],x=O.convertShape(e[1].dims).slice();x.splice(-1,1,u/p),g.push(...de(T)),g.push(...de(x)),g.push(...de(e[2].dims)),e.length===4&&g.push(...de(O.convertShape(e[3].dims)));let C=[l,r,a/h];g.push(...de(C));let R=z=>{let P=T.length,U=F("a",e[0].dataType,P,c),re=F("b",12,x.length,p),_e=F("scales",e[2].dataType,e[2].dims.length),pe=[U,re,_e],be=e.length===4?F("zero_points",12,e[3].dims.length):void 0;be&&pe.push(be);let ae=C.length,ke=oe("output",e[0].dataType,ae,h),me=et(e[0].dataType),ue=(()=>{switch(c){case 1:return`array<${me}, 8>`;case 2:return`mat4x2<${me}>`;case 4:return`mat2x4<${me}>`;default:throw new Error(`${c}-component is not supported.`)}})(),De=()=>{let G=`
          // reuse a data
            var input_offset = ${U.indicesToOffset(`${U.type.indices}(batch, row, word_offset)`)};
            var a_data: ${ue};
            for (var j: u32 = 0; j < ${8/c}; j++) {
              a_data[j] = ${U.getByOffset("input_offset")};
              input_offset++;
            }
          `;for(let ne=0;ne<h*_;ne++)G+=`
            b_value = ${p===1?`b${ne}_data`:`b${ne}_data[i]`};
            b_value_lower = unpack4xU8(b_value & b_mask);
            b_value_upper = unpack4xU8((b_value >> 4) & b_mask);
            b_quantized_values = ${ue}(${Array.from({length:4},(Se,Pe)=>`${me}(b_value_lower[${Pe}]), ${me}(b_value_upper[${Pe}])`).join(", ")});
            b_dequantized_values = ${c===1?`${ue}(${Array.from({length:8},(Se,Pe)=>`(b_quantized_values[${Pe}] - ${be?`zero_point${ne}`:"zero_point"}) * scale${ne}`).join(", ")});`:`(b_quantized_values - ${ue}(${Array(8).fill(`${be?`zero_point${ne}`:"zero_point"}`).join(",")})) * scale${ne};`};
            workgroup_shared[local_id.x * ${_} + ${Math.floor(ne/h)}]${h>1?`[${ne%h}]`:""} += ${Array.from({length:8/c},(Se,Pe)=>`${c===1?`a_data[${Pe}] * b_dequantized_values[${Pe}]`:`dot(a_data[${Pe}], b_dequantized_values[${Pe}])`}`).join(" + ")};
          `;return G},fe=()=>{let G=`
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
            let zero_point = ${me}(8);`}
            `;for(let ne=0;ne<h*_;ne++)G+=`
            let scale${ne} = ${_e.getByOffset("col_index * nBlocksPerCol + block")};
            ${be?`
            zero_point_byte_count = col_index * zero_point_bytes_per_col + (block >> 0x1u);
            zero_point_word_index = zero_point_byte_count >> 0x2u;
            zero_point_byte_offset = zero_point_byte_count & 0x3u;
            zero_point_bits_offset = (zero_point_byte_offset << 3) + (zero_point_nibble_offset << 2);
            zero_point_word = ${be.getByOffset("zero_point_word_index")} >> zero_point_bits_offset;
            let zero_point${ne} = ${me}((zero_point_word) & 0xFu);`:""}
            col_index += 1;`;return G},Ue=()=>{let G=`col_index = col * ${h};`;for(let ne=0;ne<h*_;ne++)G+=`
            let b${ne}_data = ${re.getByIndices(`${re.type.indices}(col_index, block, word)`)};
            col_index += 1;`;return G+=`
            var b_value: u32;
            let b_mask: u32 = 0x0F0F0F0Fu;
            var b_value_lower: vec4<u32>;
            var b_value_upper: vec4<u32>;
            var b_quantized_values: ${ue};
            var b_dequantized_values: ${ue};`,G};return`
        var<workgroup> workgroup_shared: array<${ke.type.value}, ${_*y}>;
        ${z.declareVariables(...pe,ke)}
        ${z.mainStart([y,1,1])}
          let output_indices = ${ke.offsetToIndices(`(global_idx / ${y}) * ${_}`)};
          let col = output_indices[2];
          let row = output_indices[1];
          let batch = output_indices[0];
          let nBlocksPerCol = uniforms.b_shape[1];

          for (var block = local_id.x; block < nBlocksPerCol; block += ${y}) {
            //process one block
            var word_offset: u32 = block * ${t.blockSize/c};
            ${fe()}
            for (var word: u32 = 0; word < ${u}; word += ${p}) {
              ${Ue()}
              for (var i: u32 = 0; i < ${p}; i++) {
                ${De()}
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
        }`};return{name:"MatMulNBits",shaderCache:{hint:`${t.blockSize};${t.bits};${c};${p};${h};${_};${y}`,inputDependencies:Array(e.length).fill("rank")},getRunData:()=>({outputs:[{dims:m,dataType:d}],dispatchGroup:{x:$},programUniforms:g}),getShaderSource:R}},Yu=(e,t)=>{let i=e[0].dims,n=i.length,r=i[n-2],s=t.k,a=t.n,o=i.slice(0,n-2),l=O.size(o),u=e[1].dims[2]/4,d=e[0].dataType,c=je(t.k),p=je(u),h=o.concat([r,a]),m=128,_=a%8===0?8:a%4===0?4:1,$=m/_,y=$*p*8,g=y/c,T=y/t.blockSize,x=O.size(h)/_,C=[],R=[l,r,s/c],z=O.convertShape(e[1].dims).slice();z.splice(-1,1,u/p),C.push(...de(R)),C.push(...de(z)),C.push(...de(e[2].dims)),e.length===4&&C.push(...de(O.convertShape(e[3].dims)));let P=[l,r,a];C.push(...de(P));let U=re=>{let _e=R.length,pe=F("a",e[0].dataType,_e,c),be=F("b",12,z.length,p),ae=F("scales",e[2].dataType,e[2].dims.length),ke=[pe,be,ae],me=e.length===4?F("zero_points",12,e[3].dims.length):void 0;me&&ke.push(me);let ue=P.length,De=oe("output",e[0].dataType,ue),fe=et(e[0].dataType),Ue=()=>{switch(c){case 1:return`
          let a_data0 = vec4<${fe}>(sub_a[word_offset], sub_a[word_offset + 1], sub_a[word_offset + 2], sub_a[word_offset + 3]);
          let a_data1 = vec4<${fe}>(sub_a[word_offset + 4], sub_a[word_offset + 5], sub_a[word_offset + 6], sub_a[word_offset + 7]);`;case 2:return`
          let a_data0 = vec4<${fe}>(sub_a[word_offset], sub_a[word_offset + 1]);
          let a_data1 = vec4<${fe}>(sub_a[word_offset + 2], sub_a[word_offset + 3]);`;case 4:return`
          let a_data0 = sub_a[word_offset];
          let a_data1 = sub_a[word_offset + 1];`;default:throw new Error(`${c}-component is not supported.`)}};return`
        var<workgroup> sub_a: array<${pe.type.value}, ${g}>;
        var<workgroup> inter_results: array<array<${De.type.value}, ${$}>, ${_}>;
        ${re.declareVariables(...ke,De)}
        ${re.mainStart([$,_,1])}
          let output_indices = ${De.offsetToIndices(`workgroup_index * ${_}`)};
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
                sub_a[a_offset] = ${pe.getByIndices(`${pe.type.indices}(batch, row, a_col)`)};
              } else {
                sub_a[a_offset] = ${pe.type.value}(0);
              }
            }
            workgroupBarrier();

            // each thread process one block
            let b_row = col + local_id.y;
            let block = tile * ${T} + local_id.x;
            ${me?`
            let zero_point_bytes_per_col = (n_blocks_per_col + 1) / 2;
            let zero_point_byte_count = b_row * zero_point_bytes_per_col + (block >> 0x1u);
            let zero_point_word_index = zero_point_byte_count >> 0x2u;
            let zero_point_byte_offset = zero_point_byte_count & 0x3u;
            let zero_point_nibble_offset: u32 = block & 0x1u;
            let zero_point_bits_offset = (zero_point_byte_offset << 3) + (zero_point_nibble_offset << 2);
            let zero_point_word = ${me.getByOffset("zero_point_word_index")} >> zero_point_bits_offset;
            let zero_point = ${fe}((zero_point_word) & 0xFu);`:`
            // The default zero point is 8 for unsigned 4-bit quantization.
            let zero_point = ${fe}(8);`}
            let scale = ${ae.getByOffset("b_row * n_blocks_per_col + block")};
            let b_data = ${be.getByIndices(`${be.type.indices}(b_row, block, 0)`)};
            var word_offset = local_id.x * ${t.blockSize/c};
            for (var i: u32 = 0; i < ${p}; i++) {
              ${Ue()}
              let b_value = ${p===1?"b_data":"b_data[i]"};
              let b_value_lower = unpack4xU8(b_value & 0x0F0F0F0Fu);
              let b_value_upper = unpack4xU8((b_value >> 4) & 0x0F0F0F0Fu);
              let b_quantized_values = mat2x4<${fe}>(${Array.from({length:4},(G,ne)=>`${fe}(b_value_lower[${ne}]), ${fe}(b_value_upper[${ne}])`).join(", ")});
              let b_dequantized_values = (b_quantized_values - mat2x4<${fe}>(${Array(8).fill("zero_point").join(",")})) * scale;
              inter_results[local_id.y][local_id.x] += ${Array.from({length:2},(G,ne)=>`${`dot(a_data${ne}, b_dequantized_values[${ne}])`}`).join(" + ")};
              word_offset += ${8/c};
            }
            workgroupBarrier();
          }

          if (local_idx < ${_}) {
            var output_value: ${De.type.value} = ${De.type.value}(0);
            for (var b = 0u; b < ${$}; b++) {
              output_value += inter_results[local_idx][b];
            }
            if (col + local_idx < uniforms.output_shape[2])
            {
              ${De.setByIndices(`${De.type.indices}(batch, row, col + local_idx)`,"output_value")}
            }
          }
        }`};return{name:"BlockwiseMatMulNBits32",shaderCache:{hint:`${t.blockSize};${c};${p};${$};${_}`,inputDependencies:Array(e.length).fill("rank")},getRunData:()=>({outputs:[{dims:h,dataType:d}],dispatchGroup:{x},programUniforms:C}),getShaderSource:U}},Ju=(e,t)=>{Qu(e.inputs,t),t.blockSize===32&&e.adapterInfo.isVendor("intel")&&e.adapterInfo.isArchitecture("gen-12lp")?e.compute(Yu(e.inputs,t)):e.compute(Xu(e.inputs,t))},ed=e=>Be(e)}),td,id,nd,rd,sd,ad,od,ld,ud,Qp=E(()=>{ge(),$e(),xe(),td=e=>{if(!e||e.length<1)throw new Error("Too few inputs");if(e[0].dataType!==1&&e[0].dataType!==10)throw new Error("Input type must be float or float16.");if(e.length>=2){let t=e[0].dims.length*2===e[1].dims[0];if(e.length===4&&(t=e[3].dims[0]*2===e[1].dims[0]),!t)throw new Error("The pads should be a 1D tensor of shape [2 * input_rank] or [2 * num_axes].")}},id=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
            k = i32(${e.indicesGet("indices",r)}) - ${le("uniforms.pads",r,i)};
            if (k < 0) {
              break;
            }
            if (k >= i32(${le("uniforms.x_shape",r,t)})) {
              break;
            }
            offset += k * i32(${le("uniforms.x_strides",r,t)});
        `;return`
          value = ${e.type.value}(uniforms.constant_value);
          for (var i = 0; i < 1; i++) {
            var offset = 0;
            var k = 0;
            ${n}
            value = x[offset];
          }
      `},nd=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
                k = i32(${e.indicesGet("indices",r)}) - ${le("uniforms.pads",r,i)};
                if (k < 0) {
                  k = -k;
                }
                {
                  let _2n_1 = 2 * (i32(${le("uniforms.x_shape",r,t)}) - 1);
                  k = k % _2n_1;
                  if(k >= i32(${le("uniforms.x_shape",r,t)})) {
                    k = _2n_1 - k;
                  }
                }
                offset += k * i32(${le("uniforms.x_strides",r,t)});
            `;return`
              var offset = 0;
              var k = 0;
              ${n}
              value = x[offset];
          `},rd=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
                k = i32(${e.indicesGet("indices",r)}) - ${le("uniforms.pads",r,i)};
                if (k < 0) {
                  k = 0;
                }
                if (k >= i32(${le("uniforms.x_shape",r,t)})) {
                  k = i32(${le("uniforms.x_shape",r,t)}) - 1;
                }
                offset += k * i32(${le("uniforms.x_strides",r,t)});
            `;return`
              var offset = 0;
              var k = 0;
              ${n}
              value = x[offset];
          `},sd=(e,t,i)=>{let n="";for(let r=t-1;r>=0;--r)n+=`
                k = i32(${e.indicesGet("indices",r)}) - ${le("uniforms.pads",r,i)};
                if (k < 0)  {
                  k += i32(${le("uniforms.x_shape",r,t)}]);
                }
                if (k >= i32(${le("uniforms.x_shape",r,t)})) {
                  k -= i32(${le("uniforms.x_shape",r,t)});
                }
                offset += k * i32(${le("uniforms.x_strides",r,t)});
            `;return`
              var offset = 0;
              var k = 0;
              ${n}
              value = x[offset];
          `},ad=(e,t,i)=>{switch(i.mode){case 0:return id(e,t,i.pads.length);case 1:return nd(e,t,i.pads.length);case 2:return rd(e,t,i.pads.length);case 3:return sd(e,t,i.pads.length);default:throw new Error("Invalid mode")}},od=(e,t)=>{let i=O.padShape(e[0].dims.slice(),t.pads),n=e[0].dims,r=O.size(i),s=[{type:12,data:r},{type:6,data:t.pads}],a=e.length>=3&&e[2].data;t.mode===0&&s.push({type:a?e[2].dataType:1,data:t.value}),s.push(...de(e[0].dims,i));let o=["rank"],l=u=>{let d=oe("output",e[0].dataType,i.length),c=F("x",e[0].dataType,n.length),p=c.type.value,h=ad(d,n.length,t),m=[{name:"output_size",type:"u32"},{name:"pads",type:"i32",length:t.pads.length}];return t.mode===0&&m.push({name:"constant_value",type:a?p:"f32"}),`
            ${u.registerUniforms(m).declareVariables(c,d)}
            ${u.mainStart()}
            ${u.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}

            let indices = ${d.offsetToIndices("global_idx")};

            var value = ${p}(0);
            ${h}
            output[global_idx] = value;
        }`};return{name:"Pad",shaderCache:{hint:`${t.mode}${a}`,inputDependencies:o},getRunData:()=>({outputs:[{dims:i,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(O.size(i)/64)},programUniforms:s}),getShaderSource:l}},ld=(e,t)=>{if(e.length>1){let i=e[1].getBigInt64Array(),n=e.length>=3&&e[2].data?e[2].dataType===10?e[2].getUint16Array()[0]:e[2].getFloat32Array()[0]:0,r=e[0].dims.length,s=new Int32Array(2*r).fill(0);if(e.length>=4){let o=e[3].getBigInt64Array();for(let l=0;l<o.length;l++)s[Number(o[l])]=Number(i[l]),s[Number(o[l])+r]=Number(i[l+o.length])}else i.forEach((o,l)=>s[Number(l)]=Number(o));let a=[];return s.forEach(o=>a.push(o)),{mode:t.mode,value:n,pads:a}}else return t},ud=(e,t)=>{td(e.inputs);let i=ld(e.inputs,t);e.compute(od(e.inputs,i),{inputs:[0]})}}),xi,mr,gr,_r,yr,dd,cd,wr,br,pd,fd,vr,hd,md,$r,gd,_d,yd,wd,Xp=E(()=>{mt(),ge(),$e(),xe(),xi=e=>{if(se.webgpu.validateInputContent&&(!e||e.length!==1))throw new Error("Pool ops requires 1 input.")},mr=(e,t,i)=>{let n=t.format==="NHWC",r=e.dims.slice();n&&r.splice(1,0,r.pop());let s=Object.hasOwnProperty.call(t,"dilations"),a=t.kernelShape.slice(),o=t.strides.slice(),l=s?t.dilations.slice():[],u=t.pads.slice();Fi.adjustPoolAttributes(i,r,a,o,l,u);let d=Fi.computePoolOutputShape(i,r,o,l,a,u,t.autoPad),c=Object.assign({},t);s?Object.assign(c,{kernelShape:a,strides:o,pads:u,dilations:l,cacheKey:t.cacheKey}):Object.assign(c,{kernelShape:a,strides:o,pads:u,cacheKey:t.cacheKey});let p=d.slice();return p.push(p.splice(1,1)[0]),[c,n?p:d]},gr=(e,t)=>{let i=t.format==="NHWC",n=O.size(e),r=O.size(t.kernelShape),s=[{type:12,data:n},{type:12,data:r}],a=[{name:"outputSize",type:"u32"},{name:"kernelSize",type:"u32"}];if(t.kernelShape.length<=2){let o=t.kernelShape[t.kernelShape.length-1],l=t.strides[t.strides.length-1],u=t.pads[t.pads.length/2-1],d=t.pads[t.pads.length-1],c=!!(u+d);s.push({type:12,data:o},{type:12,data:l},{type:12,data:u},{type:12,data:d}),a.push({name:"kw",type:"u32"},{name:"sw",type:"u32"},{name:"pwStart",type:"u32"},{name:"pwEnd",type:"u32"});let p=!1;if(t.kernelShape.length===2){let h=t.kernelShape[t.kernelShape.length-2],m=t.strides[t.strides.length-2],_=t.pads[t.pads.length/2-2],$=t.pads[t.pads.length-2];p=!!(_+$),s.push({type:12,data:h},{type:12,data:m},{type:12,data:_},{type:12,data:$}),a.push({name:"kh",type:"u32"},{name:"sh",type:"u32"},{name:"phStart",type:"u32"},{name:"phEnd",type:"u32"})}return[s,a,!0,c,p]}else{if(i)throw new Error("Pooling with kernelShape.length > 2 is not supported for NHWC format.");let o=O.computeStrides(t.kernelShape);s.push({type:12,data:o},{type:12,data:t.pads},{type:12,data:t.strides}),a.push({name:"kernelStrides",type:"u32",length:o.length},{name:"pads",type:"u32",length:t.pads.length},{name:"strides",type:"u32",length:t.strides.length});let l=t.pads.reduce((u,d)=>u+d);return[s,a,!!l,!1,!1]}},_r=(e,t,i,n,r,s,a,o,l,u,d,c)=>{let p=r.format==="NHWC",h=t.type.value,m=oe("output",t.type.tensor,n);if(r.kernelShape.length<=2){let _="",$="",y="",g=i-(p?2:1);if(d?_=`
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
                  offsets[j] = offset / ${le("uniforms.kernelStrides","j",_)};
                  offset -= offsets[j] * ${le("uniforms.kernelStrides","j",_)};
                }
                offsets[${_-1}] = offset;

                isPad = false;
                for (var j = ${i-_}u; j < ${i}u; j++) {
                  xIndices[j] = indices[j] * ${le("uniforms.strides",`j - ${i-_}u`,_)}
                    + offsets[j - ${i-_}u] - ${le("uniforms.pads","j - 2u",$)};
                  ${y}
              }
              ${a}

              output[global_idx] = value;
            }`}},yr=e=>`${e.format};${e.ceilMode};${e.autoPad};${e.kernelShape.length}`,dd=e=>`${yr(e)};${e.countIncludePad}`,cd=e=>`${yr(e)};${e.storageOrder};${e.dilations}`,wr=e=>({format:e.format,autoPad:["NOTSET","VALID","SAME_UPPER","SAME_LOWER"][e.auto_pad],ceilMode:e.ceil_mode,kernelShape:e.kernel_shape,strides:e.strides,pads:e.pads}),br=(e,t,i,n)=>{let[r,s]=mr(t,n,i),a=F("x",t.dataType,t.dims.length),o=a.type.value,l="value += x_val;",u="";r.countIncludePad?u+=`value /= ${o}(uniforms.kernelSize);`:u+=`value /= ${o}(i32(uniforms.kernelSize) - pad);`;let[d,c,p,h,m]=gr(s,r);d.push(...de(t.dims,s));let _=["rank"];return{name:e,shaderCache:{hint:`${n.cacheKey};${p};${h};${m}`,inputDependencies:_},getRunData:()=>({outputs:[{dims:s,dataType:t.dataType}],dispatchGroup:{x:Math.ceil(O.size(s)/64)},programUniforms:d}),getShaderSource:$=>_r($,a,t.dims.length,s.length,r,l,u,0,c,p,h,m)}},pd=e=>{let t=e.count_include_pad!==0,i=wr(e);if(i.ceilMode!==0)throw new Error("using ceil() in shape computation is not yet supported for AveragePool");let n={countIncludePad:t,...i,cacheKey:""};return{...n,cacheKey:dd(n)}},fd=(e,t)=>{xi(e.inputs),e.compute(br("AveragePool",e.inputs[0],!1,t))},vr={autoPad:"",ceilMode:0,countIncludePad:!1,kernelShape:[],strides:[],pads:[],storageOrder:0,dilations:[]},hd=e=>{let t=e.format;return{format:t,...vr,cacheKey:t}},md=(e,t)=>{xi(e.inputs),e.compute(br("GlobalAveragePool",e.inputs[0],!0,t))},$r=(e,t,i,n)=>{let[r,s]=mr(t,n,i),a=`
      value = max(x_val, value);
    `,o="",l=F("x",t.dataType,t.dims.length),u=["rank"],[d,c,p,h,m]=gr(s,r);return d.push(...de(t.dims,s)),{name:e,shaderCache:{hint:`${n.cacheKey};${p};${h};${m}`,inputDependencies:u},getRunData:()=>({outputs:[{dims:s,dataType:t.dataType}],dispatchGroup:{x:Math.ceil(O.size(s)/64)},programUniforms:d}),getShaderSource:_=>_r(_,l,t.dims.length,s.length,r,a,o,t.dataType===10?-65504:-1e5,c,p,h,m)}},gd=(e,t)=>{xi(e.inputs),e.compute($r("MaxPool",e.inputs[0],!1,t))},_d=e=>{let t=e.storage_order,i=e.dilations,n=wr(e);if(t!==0)throw new Error("column major storage order is not yet supported for MaxPool");if(n.ceilMode!==0)throw new Error("using ceil() in shape computation is not yet supported for MaxPool");let r={storageOrder:t,dilations:i,...n,cacheKey:""};return{...r,cacheKey:cd(r)}},yd=e=>{let t=e.format;return{format:t,...vr,cacheKey:t}},wd=(e,t)=>{xi(e.inputs),e.compute($r("GlobalMaxPool",e.inputs[0],!0,t))}}),bd,vd,$d,xd,Yp=E(()=>{ge(),$e(),He(),xe(),bd=(e,t)=>{if(e.length<2||e.length>3)throw new Error("DequantizeLinear requires 2 or 3 inputs.");if(e.length===3&&e[1].dims===e[2].dims)throw new Error("x-scale and x-zero-point must have the same shape.");if(e.length===3&&e[0].dataType!==e[2].dataType)throw new Error("x and x-zero-point must have the same data type.");if(e[0].dataType===6&&e.length>2)throw new Error("In the case of dequantizing int32 there is no zero point.");if(e[1].dims.length!==0&&e[1].dims.length!==1&&e[1].dims.length!==e[0].dims.length)throw new Error("scale input must be a scalar, a 1D tensor, or have the same rank as the input tensor.");if(e.length>2){if(e[0].dataType!==e[2].dataType)throw new Error("x and x-zero-point must have the same data type.");if(e[1].dims.length!==e[2].dims.length)throw new Error("scale and zero-point inputs must have the same rank.");if(!e[1].dims.map((i,n)=>i===e[2].dims[n]).reduce((i,n)=>i&&n,!0))throw new Error("scale and zero-point inputs must have the same shape.")}if(t.blockSize>0){if(e[1].dims.length===0||e[1].dims.length===1&&e[1].dims[0]===1)throw new Error("blockSize must be set only for block quantization.");if(!e[1].dims.map((r,s)=>s===t.axis||r===e[0].dims[s]).reduce((r,s)=>r&&s,!0))throw new Error("For block qunatization, scale input shape to match the input shape except for the axis");if(e[1].dims.length!==e[0].dims.length)throw new Error("For block qunatization the scale input rank must be the same as the x rank.");let i=e[0].dims[t.axis],n=e[1].dims[t.axis];if(t.blockSize<Math.ceil(i/n)||t.blockSize>Math.ceil(i/(n-1)-1))throw new Error("blockSize must be with in the range [ceil(dI / Si), ceil(dI / (Si - 1) - 1)].")}},vd=(e,t)=>{let i=O.normalizeAxis(t.axis,e[0].dims.length),n=e[0].dataType,r=n===3,s=e[0].dims,a=e[1].dataType,o=O.size(s),l=n===3||n===2,u=l?[Math.ceil(O.size(e[0].dims)/4)]:e[0].dims,d=e[1].dims,c=e.length>2?e[2]:void 0,p=c?l?[Math.ceil(O.size(c.dims)/4)]:c.dims:void 0,h=d.length===0||d.length===1&&d[0]===1,m=h===!1&&d.length===1,_=je(o),$=h&&(!l||_===4),y=$?_:1,g=$&&!l?_:1,T=F("input",l?12:n,u.length,g),x=F("scale",a,d.length),C=c?F("zero_point",l?12:n,p.length):void 0,R=oe("output",a,s.length,y),z=[T,x];C&&z.push(C);let P=[u,d];c&&P.push(p);let U=[{type:12,data:o/y},{type:12,data:i},{type:12,data:t.blockSize},...de(...P,s)],re=_e=>{let pe=[{name:"output_size",type:"u32"},{name:"axis",type:"u32"},{name:"block_size",type:"u32"}];return`
      ${_e.registerUniforms(pe).declareVariables(...z,R)}
      ${_e.mainStart()}
          ${_e.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.output_size")}
          let output_indices = ${R.offsetToIndices("global_idx")};

          // Set input x
          ${l?`
            let input = ${T.getByOffset("global_idx / 4")};
            let x_vec = ${r?"unpack4xI8(input)":"unpack4xU8(input)"};
            let x_value = ${y===1?"x_vec[global_idx % 4]":"x_vec"};`:`let x_value = ${T.getByOffset("global_idx")};`};

          // Set scale input
          ${h?`let scale_value= ${x.getByOffset("0")}`:m?`
            let scale_index = ${R.indicesGet("output_indices","uniforms.axis")};
            let scale_value= ${x.getByOffset("scale_index")};`:`
            var scale_indices: ${x.type.indices} = output_indices;
            let index = ${x.indicesGet("scale_indices","uniforms.axis")} / uniforms.block_size;
            ${x.indicesSet("scale_indices","uniforms.axis","index")};
            let scale_value= ${x.getByIndices("scale_indices")};`};

          // Set zero-point input
          ${C?h?l?`
                let zero_point_input = ${C.getByOffset("0")};
                let zero_point_vec =  ${r?"unpack4xI8(zero_point_input)":"unpack4xU8(zero_point_input)"};
                let zero_point_value= zero_point_vec[0]`:`let zero_point_value = ${C.getByOffset("0")}`:m?l?`
                let zero_point_index = ${R.indicesGet("output_indices","uniforms.axis")};
                let zero_point_input = ${C.getByOffset("zero_point_index / 4")};
                let zero_point_vec =  ${r?"unpack4xI8(zero_point_input)":"unpack4xU8(zero_point_input)"};
                let zero_point_value = zero_point_vec[zero_point_index % 4]`:`
                let zero_point_index = ${R.indicesGet("output_indices","uniforms.axis")};
                let zero_point_value = ${C.getByOffset("zero_point_index")};`:l?`
                let zero_point_offset = ${x.indicesToOffset("scale_indices")};
                let zero_point_input = ${C.getByOffset("zero_point_offset / 4")};
                let zero_point_vec = ${r?"unpack4xI8(zero_point_input)":"unpack4xU8(zero_point_input)"};
                let zero_point_value = zero_point_vec[zero_point_offset % 4];`:`let zero_point_value = ${C.getByIndices("scale_indices")};`:`let zero_point_value = ${l?r?"i32":"u32":T.type.value}(0);`};
      // Compute and write output
      ${R.setByOffset("global_idx",`${R.type.value}(x_value - zero_point_value) * scale_value`)};
      }`};return{name:"DequantizeLinear",shaderCache:{hint:t.cacheKey,inputDependencies:C?["rank","rank","rank"]:["rank","rank"]},getShaderSource:re,getRunData:()=>({outputs:[{dims:s,dataType:a}],dispatchGroup:{x:Math.ceil(o/y/64),y:1,z:1},programUniforms:U})}},$d=(e,t)=>{bd(e.inputs,t),e.compute(vd(e.inputs,t))},xd=e=>Be({axis:e.axis,blockSize:e.blockSize})}),Sd,kd,Td,Jp=E(()=>{mt(),ge(),xe(),Sd=(e,t,i)=>{let n=e===t,r=e<t&&i<0,s=e>t&&i>0;if(n||r||s)throw new Error("Range these inputs' contents are invalid.")},kd=(e,t,i,n)=>{let r=Math.abs(Math.ceil((t-e)/i)),s=[r],a=r,o=[{type:12,data:a},{type:n,data:e},{type:n,data:i},...de(s)],l=u=>{let d=oe("output",n,s.length),c=d.type.value,p=[{name:"outputSize",type:"u32"},{name:"start",type:c},{name:"delta",type:c}];return`
        ${u.registerUniforms(p).declareVariables(d)}
        ${u.mainStart()}
        ${u.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
        output[global_idx] = uniforms.start + ${c}(global_idx) * uniforms.delta;
      }`};return{name:"Range",shaderCache:{hint:`${n}`},getShaderSource:l,getRunData:()=>({outputs:[{dims:s,dataType:n}],dispatchGroup:{x:Math.ceil(a/64)},programUniforms:o})}},Td=e=>{let t=0,i=0,n=0;e.inputs[0].dataType===6?(t=e.inputs[0].getInt32Array()[0],i=e.inputs[1].getInt32Array()[0],n=e.inputs[2].getInt32Array()[0]):e.inputs[0].dataType===1&&(t=e.inputs[0].getFloat32Array()[0],i=e.inputs[1].getFloat32Array()[0],n=e.inputs[2].getFloat32Array()[0]),se.webgpu.validateInputContent&&Sd(t,i,n),e.compute(kd(t,i,n,e.inputs[0].dataType),{inputs:[]})}}),Ed,Cd,Id,Ad,ef=E(()=>{ge(),$e(),He(),xe(),Ed=(e,t,i,n)=>{if(e!=="none"&&n!=="i32"&&n!=="u32"&&n!=="f32")throw new Error(`Input ${n} is not supported with reduction ${e}.`);let r=`{
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
                ${r}max(bitcast<f32>(oldValue), (${i}))${s}`;case"min":return n==="i32"||n==="u32"?`atomicMin(&${t}, bitcast<${n}>(${i}));`:`${r}min(bitcast<${n}>(oldValue), (${i}))${s}`;case"mul":return`${r}(bitcast<${n}>(oldValue) * (${i}))${s}`;default:throw new Error(`Reduction ${e} is not supported.`)}},Cd=(e,t)=>{let i=e[0].dims,n=e[1].dims,r=i,s=1,a=Math.ceil(O.sizeToDimension(n,n.length-1)/s),o=n[n.length-1],l=O.sizeFromDimension(i,o),u=[{type:12,data:a},{type:12,data:o},{type:12,data:l},...de(e[1].dims,e[2].dims,r)],d=c=>{let p=F("indices",e[1].dataType,e[1].dims.length),h=F("updates",e[2].dataType,e[2].dims.length,s),m=t.reduction!=="none"&&t.reduction!==""?Ds("output",e[0].dataType,r.length):oe("output",e[0].dataType,r.length,s);return`
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
    ${Ed(t.reduction,"output[data_offset + i]","value",m.type.value)}
  }

      }`};return{name:"ScatterND",shaderCache:{hint:`${t.cacheKey}_${t.reduction}`,inputDependencies:["rank","rank"]},getRunData:()=>({outputs:[{dims:r,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(a/64)},programUniforms:u}),getShaderSource:d}},Id=e=>Be({reduction:e.reduction}),Ad=(e,t)=>{e.compute(Cd(e.inputs,t),{inputs:[e.inputs[1],e.inputs[2]],outputs:[]})}}),zd,Md,Rd,xr,Od,Dd,Bd,Fd,Pd,Nd,Vd,Ld,Sr,Ud,qd,Wd,Gd,jd,Hd,Kd,tf=E(()=>{ge(),$e(),He(),xe(),zd=(e,t)=>{if(e.every(i=>i>0||(()=>{throw new Error("Resize requires scales input values to be positive")})),e.length>0){if(t.mode==="linear"){if(!(e.length===2||e.length===3||e.length===4&&e[0]===1&&e[1]===1||e.length===4&&e[0]===1&&e[3]===1||e.length===5&&e[0]===1&&e[1]===1))throw new Error(`For linear mode, Resize requires scales to be 2D, 3D, 4D with either two outermost or one innermost and
            one outermost scale values equal to 1, or 5D with two outermost scale values equal to 1`)}else if(t.mode==="cubic"&&!(e.length===2||e.length===4&&e[0]===1&&e[1]===1||e.length===4&&e[0]===1&&e[3]===1))throw new Error("Resize requires scales input size to be 2 or 4 for cubic mode")}},Md=(e,t,i)=>{t.every(r=>r>=0&&r<i||(()=>{throw new Error("Resize requires axes input values to be positive and less than rank")}));let n=new Array(i).fill(1);return t.forEach((r,s)=>n[r]=e[s]),n},Rd=(e,t,i,n,r,s)=>{let[a,o,l]=i>10?[1,2,3]:[-1,e.length>1?1:-1,-1],u=e[0].dims.length;if(a>0&&e.length>a&&e[a].dims.length>0)e[a].getFloat32Array().forEach(d=>s.push(d));else if(t.coordinateTransformMode==="tf_crop_and_resize")throw new Error("Resize requires RoI input to be specified when coordinateTransformMode is tfCropAndResize");if(o>0&&e.length>o&&e[o].dims.length===1&&e[o].dims[0]>0){if(e[o].getFloat32Array().forEach(d=>n.push(d)),n.length!==0&&n.length!==u&&i>=18&&n.length!==t.axes.length)throw new Error("Resize requires scales input size to be same as input rank or axes size for opset 18 and up");zd(n,t),t.axes.length>0&&Md(n,t.axes,u).forEach((d,c)=>n[c]=d)}if(l>0&&e.length>l&&e[l].dims.length===1&&e[l].dims[0]>0&&(e[l].getBigInt64Array().forEach(d=>r.push(Number(d))),r.length!==0&&r.length!==u&&i>=18&&r.length!==t.axes.length))throw new Error("Resize requires sizes input size to be same as input rank or axes size for opset 18 and up");if(t.axes.length>0){if(n.length!==0&&n.length!==t.axes.length)throw new Error('Resize requires "scales" input size to be of axes rank when axes attributes is specified');if(r.length!==0&&r.length!==t.axes.length)throw new Error('Resize requires "sizes" input size to be of rank axes rank when axes attributes is specified')}if(typeof n<"u"&&typeof r<"u"&&n.length>0&&r.length>u)throw new Error("Resize requires only of scales or sizes to be specified")},xr=(e,t,i,n)=>`
  // The whole part and the fractional part are calculated separately due to inaccuracy of floating
  // point division. As an example, f32(21) / f32(7) may evaluate to 2.99... instead of 3, causing an
  // offset-by-one error later in floor().
  let big = (${e}) * (${t});
  let whole = ${n}(big / (${i}));
  let fract = ${n}(big % (${i})) / ${n}(${i});
  return whole + fract;
`,Od=(e,t)=>`fn getOriginalCoordinateFromResizedCoordinate(xResized: u32, xScale: f32, lengthResized: u32,
     lengthOriginal: u32, roiStart: f32, roiEnd: f32) -> ${t} { `+(()=>{switch(e){case"asymmetric":return`
          if (xScale < 1.0 || floor(xScale) != xScale) {
            return ${t}(xResized) / ${t}(xScale);
          } else {
            ${xr("xResized","lengthOriginal","lengthResized",t)}
          }
        `;case"pytorch_half_pixel":return`if (lengthResized > 1) {
                    return (${t}(xResized) + 0.5) / ${t}(xScale) - 0.5;
                  } else {
                    return 0.0;
                  }`;case"tf_half_pixel_for_nn":return`return (${t}(xResized) + 0.5) / ${t}(xScale);`;case"align_corners":return`if (lengthResized == 1) {
                    return 0.0;
                  } else {
                    ${xr("xResized","lengthOriginal - 1","lengthResized - 1",t)}
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
                  return offset + ((${t}(xResized) + 0.5) / ${t}(xScale)) - 0.5;`;case"half_pixel":return`return ((${t}(xResized) + 0.5) / ${t}(xScale)) - 0.5;`;default:throw new Error(`Coordinate transform mode ${e} is not supported`)}})()+"}",Dd=(e,t,i)=>`fn getNearestPixelFromOriginal(xOriginal: ${i}, isDownSample: bool) -> ${i} {`+(()=>{switch(e){case"round_prefer_ceil":return"if (fract(xOriginal) == 0.5) {             return ceil(xOriginal);           } else {             return round(xOriginal);           }";case"floor":return"return floor(xOriginal);";case"ceil":return"return ceil(xOriginal);";case"round_prefer_floor":return"if (fract(xOriginal) == 0.5) {                     return floor(xOriginal);                   } else {                     return round(xOriginal);                   }";case"simple":default:if(t<11)return"if (isDownSample)                     {                       return ceil(xOriginal);                     } else {                       return xOriginal;                     }";throw new Error(`Nearest mode ${e} is not supported`)}})()+"}",Bd=(e,t,i)=>{let n=new Array(i).fill(0).concat(new Array(i).fill(1)),r=e.length===0?n:e.slice();return t.length>0?(t.forEach((s,a)=>{n[s]=r[a],n[a+i]=r[t.length+a]}),n):r},Fd=(e,t,i,n)=>{let r=[];if(i.length>0)if(n.length>0){if(e.forEach(s=>r.push(s)),Math.max(...n)>e.length)throw new Error("axes is out of bound");n.forEach((s,a)=>r[s]=i[a])}else i.forEach(s=>r.push(s));else{if(t.length===0)throw new Error("Resize requires either scales or sizes.");r=e.map((s,a)=>Math.round(s*t[a]))}return r},Pd=(e,t,i)=>{let n=(()=>{switch(i.keepAspectRatioPolicy){case"not_larger":return i.axes.length>0?Math.min(...i.axes.map(s=>t[s]),Number.MAX_VALUE):Math.min(...t,Number.MAX_VALUE);case"not_smaller":return i.axes.length>0?Math.max(...i.axes.map(s=>t[s]),Number.MIN_VALUE):Math.max(...t,Number.MIN_VALUE);default:throw new Error(`Keep aspect ratio policy ${i.keepAspectRatioPolicy} is not supported`)}})();t.fill(1,0,t.length);let r=e.slice();return i.axes.length>0?(i.axes.forEach(s=>t[s]=n),i.axes.forEach(s=>r[s]=Math.round(e[s]*t[s]))):(t.fill(n,0,t.length),r.forEach((s,a)=>r[a]=Math.round(s*t[a]))),r},Nd=(e,t,i,n,r)=>`
    fn calculateOriginalIndicesFromOutputIndices(output_indices: ${e.type.indices}) -> array<${e.type.value}, ${i.length}> {
      var original_indices: array<${e.type.value}, ${i.length}>;
      for (var i:u32 = 0; i < ${i.length}; i++) {
        var output_index = ${e.indicesGet("output_indices","i")};
        var scale = ${le("uniforms.scales","i",n)};
        var roi_low = ${le("uniforms.roi","i",r)};
        var roi_hi = ${le("uniforms.roi",`i + ${t.length}`,r)};
        if (scale == 1.0) {
          original_indices[i] = ${e.type.value}(output_index);
        } else {
          var input_shape_i = ${le("uniforms.input_shape","i",t.length)};
          var output_shape_i = ${le("uniforms.output_shape","i",i.length)};
          original_indices[i] = getOriginalCoordinateFromResizedCoordinate(output_index, scale, output_shape_i,
                                                                           input_shape_i, roi_low, roi_hi);
        }
      }
      return original_indices;
    }`,Vd=(e,t,i,n,r,s,a)=>`
    fn calculateInputIndicesFromOutputIndices(output_indices: ${t.type.indices}) -> ${e.type.indices} {
      var input_indices: ${e.type.indices};
      for (var i:u32 = 0; i < ${n.length}; i++) {
        var output_index = ${t.indicesGet("output_indices","i")};
        var input_index: u32;
        var scale = ${le("uniforms.scales","i",r)};
        if (scale == 1.0) {
          input_index = output_index;
        } else {
          var roi_low = ${le("uniforms.roi","i",s)};
          var roi_hi = ${le("uniforms.roi",`i + ${i.length}`,s)};
          var input_shape_i = ${le("uniforms.input_shape","i",i.length)};
          var output_shape_i = ${le("uniforms.output_shape","i",n.length)};
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
    }`,Ld=(e,t)=>`
    fn checkInputIndices(input_indices: ${e.type.indices}) -> bool {
      for (var i:u32 = 0; i < ${t.length}; i++) {
        var input_index = ${e.indicesGet("input_indices","i")};
        if (input_index < 0 || input_index >= ${le("uniforms.input_shape","i",t.length)}) {
          return false;
        }
      }
      return true;
    }`,Sr=(e,t,i,n)=>e.rank>n?`
    ${e.indicesSet("input_indices",t,"channel")};
    ${e.indicesSet("input_indices",i,"batch")};
`:"",Ud=(e,t,i,n,r)=>{let[s,a,o,l]=i.length===2?[-1,0,1,-1]:[0,2,3,1],u=e.type.value;return`
    fn getInputValue(batch: u32, channel: u32, row: u32, col: u32) -> ${u} {
      var input_indices: ${e.type.indices};
      ${e.indicesSet("input_indices",a,`max(0, min(row, ${i[a]} - 1))`)};
      ${e.indicesSet("input_indices",o,`max(0, min(col, ${i[o]} - 1))`)};
      ${Sr(e,l,s,2)}
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
    }`},qd=(e,t,i,n,r,s,a,o,l,u)=>{let d=i.length===2,[c,p]=d?[0,1]:[2,3],h=e.type.value,m=_=>{let $=_===c?"row":"col";return`
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
    `},Wd=(e,t,i,n,r)=>{let[s,a,o,l,u]=i.length===3?[-1,0,1,2,-1]:[0,2,3,4,1],d=e.type.value;return`
    fn getInputValue(batch: u32, channel: u32, depth:u32, height: u32, width: u32) -> ${d} {
      var input_indices: ${e.type.indices};
      ${e.indicesSet("input_indices",a,`max(0, min(depth, ${i[a]} - 1))`)};
      ${e.indicesSet("input_indices",o,`max(0, min(height, ${i[o]} - 1))`)};
      ${e.indicesSet("input_indices",l,`max(0, min(width, ${i[l]} - 1))`)};
      ${Sr(e,u,s,3)}
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
    }`},Gd=(e,t,i,n,r,s)=>{let a=e.dims,o=Bd(s,t.axes,a.length),l=Fd(a,n,r,t.axes),u=n.slice();n.length===0&&(u=a.map((g,T)=>g===0?1:l[T]/g),t.keepAspectRatioPolicy!=="stretch"&&(l=Pd(a,u,t)));let d=oe("output",e.dataType,l.length),c=F("input",e.dataType,a.length),p=O.size(l),h=a.length===l.length&&a.every((g,T)=>g===l[T]),m=t.coordinateTransformMode==="tf_crop_and_resize",_=t.extrapolationValue,$=c.type.value,y=g=>`
      ${h?"":`
      ${Od(t.coordinateTransformMode,$)};
      ${(()=>{switch(t.mode){case"nearest":return`
              ${Ld(c,a)};
              ${Dd(t.nearestMode,i,$)};
              ${Vd(c,d,a,l,u.length,o.length,m)};
              `;case"linear":return`
              ${Nd(d,a,l,u.length,o.length)};
              ${(()=>{if(a.length===2||a.length===4)return`${Ud(c,d,a,m,_)}`;if(a.length===3||a.length===5)return`${Wd(c,d,a,m,_)}`;throw Error("Linear mode only supports input dims 2, 3, 4 and 5 are supported in linear mode.")})()};
            `;case"cubic":return`
            ${(()=>{if(a.length===2||a.length===4)return`${qd(c,d,a,l,u,o,t.cubicCoeffA,m,t.extrapolationValue,t.excludeOutside)}`;throw Error("Cubic mode only supports input dims 2 and 4 are supported in linear mode.")})()};
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
      }`;return{name:"Resize",shaderCache:{hint:`${t.cacheKey}|${i}|${u.length>0?t.mode==="cubic"?u:u.length:""}|${r.length>0?r:""}|${o.length>0?o:""}|${h}|${t.mode==="nearest"?a.length:a}`,inputDependencies:["rank"]},getShaderSource:y,getRunData:()=>({outputs:[{dims:l,dataType:e.dataType}],dispatchGroup:{x:Math.ceil(p/64)},programUniforms:[{type:12,data:p},{type:1,data:u},{type:1,data:o},...de(a,l)]})}},jd=e=>{let t=e.customDataBuffer;return new Uint32Array(t,t.byteOffset,1)[0]},Hd=(e,t)=>{let i=[],n=[],r=[],s=jd(e);if(t.antialias!==0)throw Error("Only default value (0) for Antialias attribute is supported");Rd(e.inputs,t,s,i,n,r),e.compute(Gd(e.inputs[0],t,s,i,n,r),{inputs:[0]})},Kd=e=>{let t=e.antialias,i=e.axes,n=e.coordinateTransformMode,r=e.cubicCoeffA,s=e.excludeOutside!==0,a=e.extrapolationValue,o=e.keepAspectRatioPolicy,l=e.mode,u=e.nearestMode===""?"simple":e.nearestMode;return Be({antialias:t,axes:i,coordinateTransformMode:n,cubicCoeffA:r,excludeOutside:s,extrapolationValue:a,keepAspectRatioPolicy:o,mode:l,nearestMode:u})}}),Zd,Qd,Xd,nf=E(()=>{ge(),$e(),xe(),Zd=e=>{if(!e||e.length<3)throw new Error("layerNorm requires at least 3 inputs.");let t=e[0],i=e[1],n=e[2];if(t.dataType!==i.dataType||t.dataType!==n.dataType)throw new Error("All inputs must have the same data type");if(t.dims.length!==3&&t.dims.length!==2)throw new Error("Input must be 2D or 3D");if(i.dims.length!==3&&i.dims.length!==2)throw new Error("Skip must be 2D or 3D");let r=t.dims[t.dims.length-1],s=t.dims[t.dims.length-2];if(i.dims[i.dims.length-1]!==r)throw new Error("Skip must have the same hidden size as input");if(i.dims[i.dims.length-2]!==s)throw new Error("Skip must have the same sequence length as input");if(n.dims.length!==1)throw new Error("Gamma must be 1D");if(n.dims[n.dims.length-1]!==r)throw new Error("Gamma must have the same hidden size as input");if(e.length>3){let a=e[3];if(a.dims.length!==1)throw new Error("Beta must be 1D");if(a.dims[a.dims.length-1]!==r)throw new Error("Beta must have the same hidden size as input")}if(e.length>4){let a=e[4];if(a.dims.length!==1)throw new Error("Bias must be 1D");if(a.dims[a.dims.length-1]!==r)throw new Error("Bias must have the same hidden size as input")}},Qd=(e,t,i,n)=>{let r=t.simplified,s=e[0].dims,a=O.size(s),o=s,l=a,u=s.slice(-1)[0],d=n?s.slice(0,-1).concat(1):[],c=!r&&e.length>3,p=e.length>4,h=n&&i>1,m=n&&i>2,_=i>3,$=64,y=je(u),g=[{type:12,data:l},{type:12,data:y},{type:12,data:u},{type:1,data:t.epsilon}],T=C=>{let R=[{name:"output_size",type:"u32"},{name:"components",type:"u32"},{name:"hidden_size",type:"u32"},{name:"epsilon",type:"f32"}],z=[F("x",e[0].dataType,e[0].dims,y),F("skip",e[1].dataType,e[1].dims,y),F("gamma",e[2].dataType,e[2].dims,y)];c&&z.push(F("beta",e[3].dataType,e[3].dims,y)),p&&z.push(F("bias",e[4].dataType,e[4].dims,y)),z.push(oe("output",e[0].dataType,o,y)),h&&z.push(oe("mean_output",1,d)),m&&z.push(oe("inv_std_output",1,d)),_&&z.push(oe("input_skip_bias_sum",e[0].dataType,o,y));let P=et(e[0].dataType),U=et(1,y);return`

      ${C.registerUniforms(R).declareVariables(...z)}
      var<workgroup> sum_shared : array<${U}, ${$}>;
      var<workgroup> sum_squared_shared : array<${U}, ${$}>;

      ${C.mainStart([$,1,1])}
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
          let bias_value = ${p?"bias[offset1d + i]":P+"(0.0)"};
          let input_value = x[offset + i];
          let value = input_value + skip_value + bias_value;
          ${_?"input_skip_bias_sum[offset + i] = value;":""}
          output[offset + i] = value;
          let f32_value = ${oi(P,y,"value")};
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
        let mean = ${Pt("sum",y)} / f32(uniforms.hidden_size);
        let inv_std_dev = inverseSqrt(${Pt("square_sum",y)} / f32(uniforms.hidden_size) ${r?"":"- mean * mean"} + uniforms.epsilon);
        ${h?"mean_output[global_idx] = mean;":""}
        ${m?"inv_std_output[global_idx] = inv_std_dev;":""}

        for (var i: u32 = 0; i < stride; i++) {
          output[offset + i] = (output[offset + i] ${r?"":`- ${P}(mean)`}) *
            ${P}(inv_std_dev) * gamma[offset1d + i]
            ${c?"+ beta[offset1d + i]":""};
        }
      }`},x=[{dims:o,dataType:e[0].dataType}];return i>1&&x.push({dims:d,dataType:1}),i>2&&x.push({dims:d,dataType:1}),i>3&&x.push({dims:s,dataType:e[0].dataType}),{name:"SkipLayerNormalization",shaderCache:{hint:`${y};${h};${m};${_}`,inputDependencies:e.map((C,R)=>"type")},getShaderSource:T,getRunData:()=>({outputs:x,dispatchGroup:{x:Math.ceil(l/u)},programUniforms:g})}},Xd=(e,t)=>{Zd(e.inputs);let i=[0];e.outputCount>1&&i.push(-3),e.outputCount>2&&i.push(-3),e.outputCount>3&&i.push(3),e.compute(Qd(e.inputs,t,e.outputCount,!1),{outputs:i})}}),Yd,Si,Jd,kr,ec,tc,ic,nc,rf=E(()=>{ge(),$e(),He(),xe(),Yd=(e,t)=>{if(!e||e.length<1)throw new Error("too few inputs");if(t.axes.length!==0){if(t.axes.length!==t.starts.length||t.axes.length!==t.ends.length)throw new Error("axes, starts and ends must have the same length")}else if(t.starts.length!==t.ends.length)throw new Error("starts and ends must have the same length");e.slice(1).forEach((i,n)=>{if(e[n+1].dataType!==6&&e[n+1].dataType!==7)throw new Error(`Input ${n} must be an array of int32 or int64`)})},Si=(e,t)=>{let i=[];if(e.length>t)if(e[t].dataType===7)e[t].getBigInt64Array().forEach(n=>i.push(Number(n)));else if(e[t].dataType===6)e[t].getInt32Array().forEach(n=>i.push(Number(n)));else throw new Error(`Input ${t} must be an array of int32 or int64`);return i},Jd=(e,t)=>{if(e.length>1){let i=Si(e,1),n=Si(e,2),r=Si(e,3);return r.length===0&&(r=[...Array(e[0].dims.length).keys()]),Be({starts:i,ends:n,axes:r})}else return t},kr=(e,t,i,n,r)=>{let s=e;return e<0&&(s+=i[n[t]]),r[t]<0?Math.max(0,Math.min(s,i[n[t]]-1)):Math.max(0,Math.min(s,i[n[t]]))},ec=(e,t,i)=>`fn calculateInputIndices(output_indices: ${t.type.indices}) -> ${e.type.indices} {
          var input_indices: ${e.type.indices};
          var carry = 0u;
          for (var i = ${i.length-1}; i >= 0; i--) {
            let input_shape_i = ${le("uniforms.input_shape","i",i.length)};
            let steps_i = ${le("uniforms.steps","i",i.length)};
            let signs_i = ${le("uniforms.signs","i",i.length)};
            let starts_i = ${le("uniforms.starts","i",i.length)};
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
      }`,tc=(e,t)=>{let i=e[0].dims,n=O.size(i),r=t.axes.length>0?O.normalizeAxes(t.axes,i.length):[...Array(i.length).keys()],s=Si(e,4);s.forEach(y=>y!==0||(()=>{throw new Error("step cannot be 0")})),s.length===0&&(s=Array(r.length).fill(1));let a=t.starts.map((y,g)=>kr(y,g,i,r,s)),o=t.ends.map((y,g)=>kr(y,g,i,r,s));if(r.length!==a.length||r.length!==o.length)throw new Error("start, ends and axes should have the same number of elements");if(r.length!==i.length)for(let y=0;y<i.length;++y)r.includes(y)||(a.splice(y,0,0),o.splice(y,0,i[y]),s.splice(y,0,1));let l=s.map(y=>Math.sign(y));s.forEach((y,g,T)=>{if(y<0){let x=(o[g]-a[g])/y,C=a[g],R=C+x*s[g];a[g]=R,o[g]=C,T[g]=-y}});let u=i.slice(0);r.forEach((y,g)=>{u[y]=Math.ceil((o[y]-a[y])/s[y])});let d={dims:u,dataType:e[0].dataType},c=oe("output",e[0].dataType,u.length),p=F("input",e[0].dataType,e[0].dims.length),h=O.size(u),m=[{name:"outputSize",type:"u32"},{name:"starts",type:"u32",length:a.length},{name:"signs",type:"i32",length:l.length},{name:"steps",type:"u32",length:s.length}],_=[{type:12,data:h},{type:12,data:a},{type:6,data:l},{type:12,data:s},...de(e[0].dims,u)],$=y=>`
      ${y.registerUniforms(m).declareVariables(p,c)}
        ${ec(p,c,i)}
        ${y.mainStart()}
          ${y.guardAgainstOutOfBoundsWorkgroupSizes("uniforms.outputSize")}
          let output_indices = ${c.offsetToIndices("global_idx")};
          let input_indices = calculateInputIndices(output_indices);
          ${c.setByOffset("global_idx",p.getByIndices("input_indices"))}
      }`;return{name:"Slice",shaderCache:{hint:`${l.length}_${a.length}_${s.length}`,inputDependencies:["rank"]},getShaderSource:$,getRunData:()=>({outputs:[d],dispatchGroup:{x:Math.ceil(n/64)},programUniforms:_})}},ic=(e,t)=>{Yd(e.inputs,t);let i=Jd(e.inputs,t);e.compute(tc(e.inputs,i),{inputs:[0]})},nc=e=>{let t=e.starts,i=e.ends,n=e.axes;return Be({starts:t,ends:i,axes:n})}}),rc,sc,ac,oc,sf=E(()=>{ge(),$e(),He(),Nt(),xe(),rc=e=>{if(!e||e.length!==1)throw new Error("Softmax op requires 1 input.")},sc=(e,t)=>{let i=e.inputs[0],n=i.dims,r=O.size(n),s=n.length,a=O.normalizeAxis(t.axis,s),o=a<n.length-1,l,u=[];o?(u=Array.from({length:s},(z,P)=>P),u[a]=s-1,u[s-1]=a,l=e.compute(ft(i,u),{inputs:[i],outputs:[-1]})[0]):l=i;let d=l.dims,c=d[s-1],p=r/c,h=je(c),m=c/h,_=64;p===1&&(_=256);let $=(z,P)=>P===4?`max(max(${z}.x, ${z}.y), max(${z}.z, ${z}.w))`:P===2?`max(${z}.x, ${z}.y)`:P===3?`max(max(${z}.x, ${z}.y), ${z}.z)`:z,y=F("x",l.dataType,l.dims,h),g=oe("result",l.dataType,l.dims,h),T=y.type.value,x=et(l.dataType)==="f32"?`var threadMax = ${T}(-3.402823e+38f);`:`var threadMax = ${T}(-65504.0h);`,C=z=>`
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
          rowSumShared = ${T}(${Pt("threadShared[0]",h)});
        }
        workgroupBarrier();

        // calculate final value for each element in the row
        for (var col = lindex; col < cols; col += wg) {
          var value = exp(getValue(row, col, row_stride) - rowMaxShared) / rowSumShared;
          // max operation protects against NaN since all values should be >=0
          value = max(value, ${T}(0.0));
          setValue(row, col, row_stride, value);
        }
      }`,R=e.compute({name:"Softmax",shaderCache:{hint:`${h};${_}`,inputDependencies:["type"]},getRunData:()=>({outputs:[{dims:d,dataType:l.dataType}],dispatchGroup:{x:p},programUniforms:[{type:6,data:m}]}),getShaderSource:C},{inputs:[l],outputs:[o?-1:0]})[0];o&&e.compute(ft(R,u),{inputs:[R]})},ac=(e,t)=>{rc(e.inputs),sc(e,t)},oc=e=>Be({axis:e.axis})}),Tr,lc,uc,dc,cc,af=E(()=>{ge(),$e(),xe(),Tr=e=>Array.from(e.getBigInt64Array(),Number),lc=e=>{if(!e||e.length!==2)throw new Error("Tile requires 2 inputs.");if(e[0].dataType!==1&&e[0].dataType!==10&&e[0].dataType!==6&&e[0].dataType!==12)throw new Error("Tile only support float, float16, int32, and uint32 data types");if(e[1].dataType!==7)throw new Error("Tile `repeats` input should be of int64 data type");if(e[1].dims.length!==1)throw new Error("Tile `repeats` input should be 1-D");if(Tr(e[1]).length!==e[0].dims.length)throw new Error("Tile `repeats` input should have same number of elements as rank of input data tensor")},uc=(e,t)=>{let i=[];for(let n=0;n<e.length;++n)i.push(e[n]*t[n]);return i},dc=(e,t)=>{let i=e[0].dims,n=t??Tr(e[1]),r=uc(i,n),s=O.size(r),a=e[0].dataType,o=F("input",a,i.length),l=oe("output",a,r.length),u=d=>`
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
    }`;return{name:"Tile",shaderCache:{hint:`${n}`,inputDependencies:["rank"]},getRunData:()=>({outputs:[{dims:r,dataType:e[0].dataType}],dispatchGroup:{x:Math.ceil(s/64)},programUniforms:[{type:12,data:s},...de(e[0].dims,r)]}),getShaderSource:u}},cc=e=>{lc(e.inputs),e.compute(dc(e.inputs),{inputs:[0]})}}),pc,fc,hc,of=E(()=>{ge(),$e(),xe(),pc=(e,t,i,n,r)=>{let s=oe("output_data",r,i.length,4),a=F("a_data",t[1].dataType,t[1].dims.length,4),o=F("b_data",t[2].dataType,t[2].dims.length,4),l=F("c_data",t[0].dataType,t[0].dims.length,4),u,d=(c,p,h)=>`select(${p}, ${c}, ${h})`;if(!n)u=s.setByOffset("global_idx",d(a.getByOffset("global_idx"),o.getByOffset("global_idx"),l.getByOffset("global_idx")));else{let c=(p,h,m="")=>{let _=`a_data[index_a${h}][component_a${h}]`,$=`b_data[index_b${h}][component_b${h}]`,y=`bool(c_data[index_c${h}] & (0xffu << (component_c${h} * 8)))`;return`
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
      }`},fc=e=>{let t=e[1].dims,i=e[2].dims,n=e[0].dims,r=e[1].dataType,s=!(O.areEqual(t,i)&&O.areEqual(i,n)),a=t,o=O.size(t);if(s){let u=si.calcShape(si.calcShape(t,i,!1),n,!1);if(!u)throw new Error("Can't perform where op on the given tensors");a=u,o=O.size(a)}let l=Math.ceil(o/4);return{name:"Where",shaderCache:{inputDependencies:["rank","rank","rank"]},getShaderSource:u=>pc(u,e,a,s,r),getRunData:()=>({outputs:[{dims:a,dataType:r}],dispatchGroup:{x:Math.ceil(o/64/4)},programUniforms:[{type:12,data:l},...de(n,t,i,a)]})}},hc=e=>{e.compute(fc(e.inputs))}}),mc,lf=E(()=>{vp(),Un(),$p(),xp(),Sp(),kp(),Tp(),zp(),Rp(),Op(),Dp(),Bp(),Fp(),Pp(),Np(),Vp(),Lp(),Up(),qp(),Wp(),Gp(),jp(),Hp(),Kp(),Zp(),Eu(),Qp(),Xp(),Yp(),Jp(),ef(),Nn(),tf(),Fu(),nf(),rf(),sf(),Ou(),af(),Nt(),jn(),of(),mc=new Map([["Abs",[Ka]],["Acos",[Za]],["Acosh",[Qa]],["Add",[Po]],["ArgMax",[Ra,Ln]],["ArgMin",[Ma,Ln]],["Asin",[Xa]],["Asinh",[Ya]],["Atan",[Ja]],["Atanh",[eo]],["Attention",[Na]],["AveragePool",[fd,pd]],["BatchNormalization",[qa]],["BiasAdd",[ja]],["BiasSplitGelu",[Do]],["Cast",[io,to]],["Ceil",[so]],["Clip",[ro]],["Concat",[Yo,Jo]],["Conv",[sr,nr]],["ConvTranspose",[Tl,xl]],["Cos",[ao]],["Cosh",[oo]],["CumSum",[Cl,Il]],["DepthToSpace",[Rl,Ol]],["DequantizeLinear",[$d,xd]],["Div",[No]],["Einsum",[Vl,Ll]],["Elu",[lo,yi]],["Equal",[Vo]],["Erf",[uo]],["Exp",[co]],["Expand",[Gl]],["FastGelu",[Hl]],["Floor",[po]],["FusedConv",[sr,nr]],["Gather",[Xl,Ql]],["GatherElements",[lu,ou]],["GatherBlockQuantized",[nu,ru]],["GatherND",[Jl,eu]],["Gelu",[fo]],["Gemm",[pu,cu]],["GlobalAveragePool",[md,hd]],["GlobalMaxPool",[wd,yd]],["Greater",[Wo]],["GreaterOrEqual",[jo]],["GridSample",[vu,$u]],["GroupQueryAttention",[Lu]],["HardSigmoid",[vo,bo]],["InstanceNormalization",[Wu]],["LayerNormalization",[Hu]],["LeakyRelu",[ho,yi]],["Less",[Go]],["LessOrEqual",[Ho]],["Log",[Io]],["MatMul",[Zu]],["MatMulNBits",[Ju,ed]],["MaxPool",[gd,_d]],["Mul",[Lo]],["MultiHeadAttention",[Tu,Su]],["Neg",[go]],["Not",[mo]],["Pad",[ud]],["Pow",[Uo]],["QuickGelu",[Mo,yi]],["Range",[Td]],["Reciprocal",[_o]],["ReduceMin",[Ea]],["ReduceMean",[$a]],["ReduceMax",[Ta]],["ReduceSum",[Ia]],["ReduceProd",[Ca]],["ReduceL1",[xa]],["ReduceL2",[Sa]],["ReduceLogSum",[za]],["ReduceLogSumExp",[ka]],["ReduceSumSquare",[Aa]],["Relu",[yo]],["Resize",[Hd,Kd]],["RotaryEmbedding",[Bu]],["ScatterND",[Ad,Id]],["Sigmoid",[wo]],["Sin",[$o]],["Sinh",[xo]],["Slice",[ic,nc]],["SkipLayerNormalization",[Xd]],["Split",[Mu,Ru]],["Sqrt",[So]],["Softmax",[ac,oc]],["Sub",[qo]],["Tan",[ko]],["Tanh",[To]],["ThresholdedRelu",[Co,yi]],["Tile",[cc]],["Transpose",[qs,Ws]],["Where",[hc]]])}),gc,uf=E(()=>{mt(),Dt(),xe(),gc=class{constructor(e){this.backend=e,this.repo=new Map,this.attributesBound=!1}getArtifact(e){return this.repo.get(e)}setArtifact(e,t){this.repo.set(e,t)}run(e,t,i,n,r){K(e.programInfo.name);let s=this.backend.device,a=this.backend.getComputePassEncoder();this.backend.writeTimestamp(this.backend.pendingDispatchNumber*2);let o=[];for(let u of t)o.push({binding:o.length,resource:{buffer:u.buffer}});for(let u of i)o.push({binding:o.length,resource:{buffer:u.buffer}});r&&o.push({binding:o.length,resource:r});let l=s.createBindGroup({layout:e.computePipeline.getBindGroupLayout(0),entries:o,label:e.programInfo.name});if(this.backend.sessionStatus==="capturing"){let u={kernelId:this.backend.currentKernelId,computePipeline:e.computePipeline,bindGroup:l,dispatchGroup:n};this.backend.capturedCommandList.get(this.backend.currentSessionId).push(u)}a.setPipeline(e.computePipeline),a.setBindGroup(0,l),a.dispatchWorkgroups(...n),this.backend.writeTimestamp(this.backend.pendingDispatchNumber*2+1),this.backend.pendingDispatchNumber++,(this.backend.pendingDispatchNumber>=this.backend.maxDispatchNumber||this.backend.queryType==="at-passes")&&this.backend.endComputePass(),this.backend.pendingDispatchNumber>=this.backend.maxDispatchNumber&&this.backend.flush(),he(e.programInfo.name)}dispose(){}build(e,t){K(e.name);let i=this.backend.device,n=[];[{feature:"shader-f16",extension:"f16"},{feature:"subgroups",extension:"subgroups"}].forEach(u=>{i.features.has(u.feature)&&n.push(`enable ${u.extension};`)});let r=Fs(t,this.backend.device.limits),s=e.getShaderSource(r),a=`${n.join(`
`)}
${r.additionalImplementations}
${s}`,o=i.createShaderModule({code:a,label:e.name});Ae("verbose",()=>`[WebGPU] ${e.name} shader code: ${a}`);let l=i.createComputePipeline({compute:{module:o,entryPoint:"main"},layout:"auto",label:e.name});return he(e.name),{programInfo:e,computePipeline:l,uniformVariablesInfo:r.variablesInfo}}normalizeDispatchGroupSize(e){let t=typeof e=="number"?e:e.x,i=typeof e=="number"?1:e.y||1,n=typeof e=="number"?1:e.z||1,r=this.backend.device.limits.maxComputeWorkgroupsPerDimension;if(t<=r&&i<=r&&n<=r)return[t,i,n];let s=t*i*n,a=Math.ceil(Math.sqrt(s));if(a>r){if(a=Math.ceil(Math.cbrt(s)),a>r)throw new Error("Total dispatch size exceeds WebGPU maximum.");return[a,a,a]}else return[a,a,1]}}}),_c={};X(_c,{WebGpuBackend:()=>vc});var yc,wc,bc,vc,df=E(()=>{mt(),ge(),Dt(),xs(),wp(),lf(),uf(),yc=(e,t)=>{if(t.length!==e.length)throw new Error(`inputDependencies length ${t.length} is not equal to inputTensors length ${e.length}.`);let i=[];for(let n=0;n<e.length;++n){let r=e[n].dataType;switch(t[n]){case"none":{i.push("");break}case"type":{i.push(`${r}`);break}case"rank":{let s=e[n].dims.length;i.push(`${r};${s}`);break}case"dims":{let s=e[n].dims.join(",");i.push(`${r};${s}`);break}default:throw new Error(`unsupported input dependency: ${t[n]}`)}}return i.join("|")},wc=(e,t,i)=>{let n=e.name;return e.shaderCache?.hint&&(n+="["+e.shaderCache.hint+"]"),n+=":"+i+`:${yc(t,e.shaderCache?.inputDependencies??new Array(t.length).fill("dims"))}`,n},bc=class{constructor(e){e&&(this.architecture=e.architecture,this.vendor=e.vendor)}isArchitecture(e){return this.architecture===e}isVendor(e){return this.vendor===e}},vc=class{constructor(){this.currentSessionId=null,this.currentKernelId=null,this.commandEncoder=null,this.computePassEncoder=null,this.maxDispatchNumber=16,this.pendingDispatchNumber=0,this.pendingKernels=[],this.pendingQueries=new Map,this.sessionStatus="default",this.capturedCommandList=new Map,this.capturedPendingKernels=new Map,this.sessionExternalDataMapping=new Map}get currentKernelCustomData(){if(this.currentKernelId===null)throw new Error("currentKernelCustomData(): currentKernelId is null. (should not happen)");let e=this.kernelCustomData.get(this.currentKernelId);return e||(e={},this.kernelCustomData.set(this.currentKernelId,e)),e}async initialize(e,t){this.env=e;let i=[],n={requiredLimits:{maxComputeWorkgroupStorageSize:t.limits.maxComputeWorkgroupStorageSize,maxComputeWorkgroupsPerDimension:t.limits.maxComputeWorkgroupsPerDimension,maxStorageBufferBindingSize:t.limits.maxStorageBufferBindingSize,maxBufferSize:t.limits.maxBufferSize,maxComputeInvocationsPerWorkgroup:t.limits.maxComputeInvocationsPerWorkgroup,maxComputeWorkgroupSizeX:t.limits.maxComputeWorkgroupSizeX,maxComputeWorkgroupSizeY:t.limits.maxComputeWorkgroupSizeY,maxComputeWorkgroupSizeZ:t.limits.maxComputeWorkgroupSizeZ},requiredFeatures:i},r=s=>t.features.has(s)&&i.push(s)&&!0;r("chromium-experimental-timestamp-query-inside-passes")||r("timestamp-query"),r("shader-f16"),r("subgroups"),this.device=await t.requestDevice(n),this.adapterInfo=new bc(t.info||await t.requestAdapterInfo()),this.gpuDataManager=Rs(this),this.programManager=new gc(this),this.kernels=new Map,this.kernelPersistentData=new Map,this.kernelCustomData=new Map,$n(e.logLevel,!!e.debug),this.device.onuncapturederror=s=>{s.error instanceof GPUValidationError&&console.error(`An uncaught WebGPU validation error was raised: ${s.error.message}`)},Object.defineProperty(this.env.webgpu,"device",{value:this.device,writable:!1,enumerable:!0,configurable:!1}),Object.defineProperty(this.env.webgpu,"adapter",{value:t,writable:!1,enumerable:!0,configurable:!1}),this.setQueryType()}dispose(){typeof this.querySet<"u"&&this.querySet.destroy(),this.gpuDataManager.dispose()}getCommandEncoder(){return this.commandEncoder||(this.commandEncoder=this.device.createCommandEncoder()),this.commandEncoder}getComputePassEncoder(){if(!this.computePassEncoder){let e=this.getCommandEncoder(),t={};this.queryType==="at-passes"&&(t.timestampWrites={querySet:this.querySet,beginningOfPassWriteIndex:this.pendingDispatchNumber*2,endOfPassWriteIndex:this.pendingDispatchNumber*2+1}),this.computePassEncoder=e.beginComputePass(t)}return this.computePassEncoder}endComputePass(){this.computePassEncoder&&(this.computePassEncoder.end(),this.computePassEncoder=null)}flush(){if(!this.commandEncoder)return;K(),this.endComputePass();let e;this.queryType!=="none"&&(this.commandEncoder.resolveQuerySet(this.querySet,0,this.pendingDispatchNumber*2,this.queryResolveBuffer,0),e=this.device.createBuffer({size:this.pendingDispatchNumber*2*8,usage:GPUBufferUsage.MAP_READ|GPUBufferUsage.COPY_DST}),this.pendingQueries.set(e,this.pendingKernels),this.pendingKernels=[],this.commandEncoder.copyBufferToBuffer(this.queryResolveBuffer,0,e,0,this.pendingDispatchNumber*2*8)),this.device.queue.submit([this.commandEncoder.finish()]),this.gpuDataManager.refreshPendingBuffers(),this.commandEncoder=null,this.pendingDispatchNumber=0,this.queryType!=="none"&&e.mapAsync(GPUMapMode.READ).then(()=>{let t=new BigUint64Array(e.getMappedRange()),i=this.pendingQueries.get(e);for(let n=0;n<t.length/2;n++){let r=i[n],s=r.kernelId,a=this.kernels.get(s),o=a.kernelType,l=a.kernelName,u=r.programName,d=r.inputTensorViews,c=r.outputTensorViews,p=t[n*2],h=t[n*2+1];typeof this.queryTimeBase>"u"&&(this.queryTimeBase=p);let m=Number(p-this.queryTimeBase),_=Number(h-this.queryTimeBase);if(!Number.isSafeInteger(m)||!Number.isSafeInteger(_))throw new RangeError("incorrect timestamp range");if(this.env.webgpu.profiling?.ondata)this.env.webgpu.profiling.ondata({version:1,inputsMetadata:d.map($=>({dims:$.dims,dataType:Ot($.dataType)})),outputsMetadata:c.map($=>({dims:$.dims,dataType:Ot($.dataType)})),kernelId:s,kernelType:o,kernelName:l,programName:u,startTime:m,endTime:_});else{let $="";d.forEach((g,T)=>{$+=`input[${T}]: [${g.dims}] | ${Ot(g.dataType)}, `});let y="";c.forEach((g,T)=>{y+=`output[${T}]: [${g.dims}] | ${Ot(g.dataType)}, `}),console.log(`[profiling] kernel "${s}|${o}|${l}|${u}" ${$}${y}start time: ${m} ns, execution time: ${_-m} ns`)}Te("GPU",`${u}::${p}::${h}`)}e.unmap(),this.pendingQueries.delete(e)}),he()}run(e,t,i,n,r,s){K(e.name);let a=[];for(let g=0;g<t.length;++g){let T=t[g].data;if(T===0)continue;let x=this.gpuDataManager.get(T);if(!x)throw new Error(`no GPU data for input: ${T}`);a.push(x)}let{outputs:o,dispatchGroup:l,programUniforms:u}=e.getRunData(t),d=i.length===0?o.map((g,T)=>T):i;if(d.length!==o.length)throw new Error(`Output size ${d.length} must be equal to ${o.length}.`);let c=[],p=[];for(let g=0;g<o.length;++g){if(!Number.isInteger(d[g])||d[g]<-3||d[g]>=s)throw new Error(`Invalid output index: ${d[g]}`);if(d[g]===-3)continue;let T=d[g]===-1,x=d[g]===-2,C=T||x?r(o[g].dataType,o[g].dims):n(d[g],o[g].dataType,o[g].dims);if(c.push(C),C.data===0)continue;let R=this.gpuDataManager.get(C.data);if(!R)throw new Error(`no GPU data for output: ${C.data}`);if(T&&this.temporaryData.push(R),x){let z=this.kernelPersistentData.get(this.currentKernelId);z||(z=[],this.kernelPersistentData.set(this.currentKernelId,z)),z.push(R)}p.push(R)}if(a.length!==t.length||p.length!==c.length){if(p.length===0)return he(e.name),c;throw new Error(`Program ${e.name} has zero-sized tensor(s) in inputs or outputs. This is not supported now.`)}let h;if(u){let g=0,T=[];u.forEach(z=>{let P=typeof z.data=="number"?[z.data]:z.data;if(P.length===0)return;let U=z.type===10?2:4,re,_e;z.type===10?(_e=P.length>4?16:P.length>2?8:P.length*U,re=P.length>4?16:U*P.length):(_e=P.length<=2?P.length*U:16,re=16),g=Math.ceil(g/_e)*_e,T.push(g);let pe=z.type===10?8:4;g+=P.length>4?Math.ceil(P.length/pe)*re:P.length*U});let x=16;g=Math.ceil(g/x)*x;let C=new ArrayBuffer(g);u.forEach((z,P)=>{let U=T[P],re=typeof z.data=="number"?[z.data]:z.data;if(z.type===6)new Int32Array(C,U,re.length).set(re);else if(z.type===12)new Uint32Array(C,U,re.length).set(re);else if(z.type===10)new Uint16Array(C,U,re.length).set(re);else if(z.type===1)new Float32Array(C,U,re.length).set(re);else throw new Error(`Unsupported uniform type: ${Ot(z.type)}`)});let R=this.gpuDataManager.create(g,GPUBufferUsage.COPY_DST|GPUBufferUsage.UNIFORM);this.device.queue.writeBuffer(R.buffer,0,C,0,g),this.gpuDataManager.release(R.id),h={offset:0,size:g,buffer:R.buffer}}let m=this.programManager.normalizeDispatchGroupSize(l),_=m[1]===1&&m[2]===1,$=wc(e,t,_),y=this.programManager.getArtifact($);if(y||(y=this.programManager.build(e,m),this.programManager.setArtifact($,y),Ae("info",()=>`[artifact] key: ${$}, programName: ${e.name}`)),u&&y.uniformVariablesInfo){if(u.length!==y.uniformVariablesInfo.length)throw new Error(`Uniform variables count mismatch: expect ${y.uniformVariablesInfo.length}, got ${u.length} in program "${y.programInfo.name}".`);for(let g=0;g<u.length;g++){let T=u[g],x=T.type,C=typeof T.data=="number"?1:T.data.length,[R,z]=y.uniformVariablesInfo[g];if(x!==R||C!==z)throw new Error(`Uniform variable ${g} mismatch: expect type ${R} with size ${z}, got type ${x} with size ${C} in program "${y.programInfo.name}".`)}}if(Ae("info",()=>`[ProgramManager] run "${e.name}" (key=${$}) with ${m[0]}x${m[1]}x${m[2]}`),this.queryType!=="none"||this.sessionStatus==="capturing"){let g={kernelId:this.currentKernelId,programName:y.programInfo.name,inputTensorViews:t,outputTensorViews:c};this.pendingKernels.push(g),this.sessionStatus==="capturing"&&this.capturedPendingKernels.get(this.currentSessionId).push(g)}return this.programManager.run(y,a,p,m,h),he(e.name),c}upload(e,t){this.gpuDataManager.upload(e,t)}memcpy(e,t){this.gpuDataManager.memcpy(e,t)}async download(e,t){await this.gpuDataManager.download(e,t)}alloc(e){return this.gpuDataManager.create(e).id}free(e){return this.gpuDataManager.release(e)}createKernel(e,t,i,n){let r=mc.get(e);if(!r)throw new Error(`kernel not implemented: ${e}`);let s={kernelType:e,kernelName:n,kernelEntry:r[0],attributes:[r[1],i]};this.kernels.set(t,s)}releaseKernel(e){let t=this.kernelPersistentData.get(e);if(t){for(let i of t)this.gpuDataManager.release(i.id);this.kernelPersistentData.delete(e)}this.kernelCustomData.delete(e),this.kernels.delete(e)}computeKernel(e,t,i){let n=this.kernels.get(e);if(!n)throw new Error(`kernel not created: ${e}`);let r=n.kernelType,s=n.kernelName,a=n.kernelEntry,o=n.attributes;if(this.currentKernelId!==null)throw new Error(`kernel "[${r}] ${s}" is not allowed to be called recursively`);this.currentKernelId=e,o[0]&&(o[1]=o[0](o[1]),o[0]=void 0),Ae("info",()=>`[WebGPU] Start to run kernel "[${r}] ${s}"...`);let l=this.env.debug;this.temporaryData=[];try{return l&&this.device.pushErrorScope("validation"),a(t,o[1]),0}catch(u){return i.push(Promise.resolve(`[WebGPU] Kernel "[${r}] ${s}" failed. ${u}`)),1}finally{l&&i.push(this.device.popErrorScope().then(u=>u?`GPU validation error for kernel "[${r}] ${s}": ${u.message}`:null));for(let u of this.temporaryData)this.gpuDataManager.release(u.id);this.temporaryData=[],this.currentKernelId=null}}registerBuffer(e,t,i,n){let r=this.sessionExternalDataMapping.get(e);r||(r=new Map,this.sessionExternalDataMapping.set(e,r));let s=r.get(t),a=this.gpuDataManager.registerExternalBuffer(i,n,s);return r.set(t,[a,i]),a}unregisterBuffers(e){let t=this.sessionExternalDataMapping.get(e);t&&(t.forEach(i=>this.gpuDataManager.unregisterExternalBuffer(i[0])),this.sessionExternalDataMapping.delete(e))}getBuffer(e){let t=this.gpuDataManager.get(e);if(!t)throw new Error(`no GPU data for buffer: ${e}`);return t.buffer}createDownloader(e,t,i){return async()=>{let n=await On(this,e,t);return xn(n.buffer,i)}}writeTimestamp(e){this.queryType==="inside-passes"&&this.computePassEncoder.writeTimestamp(this.querySet,e)}setQueryType(){this.queryType="none",(this.env.webgpu.profiling?.mode==="default"||(typeof this.env.trace>"u"?this.env.wasm.trace:this.env.trace))&&(this.device.features.has("chromium-experimental-timestamp-query-inside-passes")?this.queryType="inside-passes":this.device.features.has("timestamp-query")&&(this.queryType="at-passes"),this.queryType!=="none"&&typeof this.querySet>"u"&&(this.querySet=this.device.createQuerySet({type:"timestamp",count:this.maxDispatchNumber*2}),this.queryResolveBuffer=this.device.createBuffer({size:this.maxDispatchNumber*2*8,usage:GPUBufferUsage.COPY_SRC|GPUBufferUsage.QUERY_RESOLVE})))}captureBegin(){Ae("info","captureBegin"),this.capturedCommandList.get(this.currentSessionId)||this.capturedCommandList.set(this.currentSessionId,[]),this.capturedPendingKernels.get(this.currentSessionId)||this.capturedPendingKernels.set(this.currentSessionId,[]),this.flush(),this.sessionStatus="capturing"}captureEnd(){Ae("info","captureEnd"),this.flush(),this.sessionStatus="default"}replay(){Ae("info","replay"),this.sessionStatus="replaying";let e=this.capturedCommandList.get(this.currentSessionId),t=this.capturedPendingKernels.get(this.currentSessionId),i=e.length;this.pendingKernels=[];for(let n=0;n<i;n++){let r=this.getComputePassEncoder(),s=e[n];this.writeTimestamp(this.pendingDispatchNumber*2),r.setPipeline(s.computePipeline),r.setBindGroup(0,s.bindGroup),r.dispatchWorkgroups(...s.dispatchGroup),this.writeTimestamp(this.pendingDispatchNumber*2+1),this.pendingDispatchNumber++,this.queryType!=="none"&&this.pendingKernels.push(t[n]),(this.pendingDispatchNumber>=this.maxDispatchNumber||this.queryType==="at-passes")&&this.endComputePass(),this.pendingDispatchNumber>=this.maxDispatchNumber&&this.flush()}this.flush(),this.sessionStatus="default"}onCreateSession(){this.gpuDataManager.onCreateSession()}onReleaseSession(e){this.unregisterBuffers(e),this.capturedCommandList.has(e)&&this.capturedCommandList.delete(e),this.capturedPendingKernels.has(e)&&this.capturedPendingKernels.delete(e),this.gpuDataManager.onReleaseSession(e)}onRunStart(e){this.currentSessionId=e,this.setQueryType()}}}),$c={};X($c,{init:()=>Sc});var Zi,xc,Sc,cf=E(()=>{ge(),Dt(),$e(),yp(),Zi=class sp{constructor(t,i,n,r){this.module=t,this.dataType=i,this.data=n,this.dims=r}getFloat32Array(){if(this.dataType!==1)throw new Error("Invalid data type");let t=O.size(this.dims);return t===0?new Float32Array:new Float32Array(this.module.HEAP8.buffer,this.data,t)}getBigInt64Array(){if(this.dataType!==7)throw new Error("Invalid data type");let t=O.size(this.dims);return t===0?new BigInt64Array:new BigInt64Array(this.module.HEAP8.buffer,this.data,t)}getInt32Array(){if(this.dataType!==6)throw new Error("Invalid data type");let t=O.size(this.dims);return t===0?new Int32Array:new Int32Array(this.module.HEAP8.buffer,this.data,t)}getUint16Array(){if(this.dataType!==10&&this.dataType!==4)throw new Error("Invalid data type");let t=O.size(this.dims);return t===0?new Uint16Array:new Uint16Array(this.module.HEAP8.buffer,this.data,t)}reshape(t){if(O.size(t)!==O.size(this.dims))throw new Error("Invalid new shape");return new sp(this.module,this.dataType,this.data,t)}},xc=class{constructor(e,t,i){this.module=e,this.backend=t,this.customDataOffset=0,this.customDataSize=0,this.adapterInfo=t.adapterInfo;let n=e.PTR_SIZE,r=i/e.PTR_SIZE,s=n===4?"i32":"i64";this.opKernelContext=Number(e.getValue(n*r++,s));let a=Number(e.getValue(n*r++,s));this.outputCount=Number(e.getValue(n*r++,s)),this.customDataOffset=Number(e.getValue(n*r++,"*")),this.customDataSize=Number(e.getValue(n*r++,s));let o=[];for(let l=0;l<a;l++){let u=Number(e.getValue(n*r++,s)),d=Number(e.getValue(n*r++,"*")),c=Number(e.getValue(n*r++,s)),p=[];for(let h=0;h<c;h++)p.push(Number(e.getValue(n*r++,s)));o.push(new Zi(e,u,d,p))}this.inputs=o}get kernelCustomData(){return this.backend.currentKernelCustomData}get customDataBuffer(){return this.module.HEAPU8.subarray(this.customDataOffset,this.customDataOffset+this.customDataSize)}compute(e,t){let i=t?.inputs?.map(a=>typeof a=="number"?this.inputs[a]:a)??this.inputs,n=t?.outputs??[],r=(a,o,l)=>new Zi(this.module,o,this.output(a,l),l),s=(a,o)=>{let l=Gt(a,o);if(!l)throw new Error(`Unsupported data type: ${a}`);let u=l>0?this.backend.gpuDataManager.create(l).id:0;return new Zi(this.module,a,u,o)};return this.backend.run(e,i,n,r,s,this.outputCount)}output(e,t){let i=this.module.stackSave();try{let n=this.module.PTR_SIZE,r=n===4?"i32":"i64",s=this.module.stackAlloc((1+t.length)*n);this.module.setValue(s,t.length,r);for(let a=0;a<t.length;a++)this.module.setValue(s+n*(a+1),t[a],r);return this.module._JsepOutput(this.opKernelContext,e,s)}catch(n){throw new Error(`Failed to generate kernel's output[${e}] with dims [${t}]. If you are running with pre-allocated output, please make sure the output type/dims are correct. Error: ${n}`)}finally{this.module.stackRestore(i)}}},Sc=async(e,t,i,n)=>{let r=t.jsepInit;if(!r)throw new Error("Failed to initialize JSEP. The WebAssembly module is not built with JSEP support.");if(e==="webgpu"){let s=(df(),ee(_c)).WebGpuBackend,a=new s;await a.initialize(i,n),r("webgpu",[a,o=>a.alloc(Number(o)),o=>a.free(o),(o,l,u,d=!1)=>{if(d)Ae("verbose",()=>`[WebGPU] jsepCopyGpuToGpu: src=${Number(o)}, dst=${Number(l)}, size=${Number(u)}`),a.memcpy(Number(o),Number(l));else{Ae("verbose",()=>`[WebGPU] jsepCopyCpuToGpu: dataOffset=${Number(o)}, gpuDataId=${Number(l)}, size=${Number(u)}`);let c=t.HEAPU8.subarray(Number(o>>>0),Number(o>>>0)+Number(u));a.upload(Number(l),c)}},async(o,l,u)=>{Ae("verbose",()=>`[WebGPU] jsepCopyGpuToCpu: gpuDataId=${o}, dataOffset=${l}, size=${u}`),await a.download(Number(o),()=>t.HEAPU8.subarray(Number(l)>>>0,Number(l+u)>>>0))},(o,l,u)=>a.createKernel(o,Number(l),u,t.UTF8ToString(t._JsepGetNodeName(Number(l)))),o=>a.releaseKernel(o),(o,l,u,d)=>{Ae("verbose",()=>`[WebGPU] jsepRun: sessionHandle=${u}, kernel=${o}, contextDataOffset=${l}`);let c=new xc(t,a,Number(l));return a.computeKernel(Number(o),c,d)},()=>a.captureBegin(),()=>a.captureEnd(),()=>a.replay()])}else{let s=new Is(i);r("webnn",[s,()=>s.reserveTensorId(),a=>s.releaseTensorId(a),async(a,o,l,u,d)=>s.ensureTensor(a,o,l,u,d),(a,o)=>{s.uploadTensor(a,o)},async(a,o)=>s.downloadTensor(a,o),(a,o)=>s.registerMLContext(a,o),!!i.trace])}}}),kc,Er,Cr,Vt,Tc,Ir,Qi,Ar,zr,Mr,Rr,Or,Dr,Ec=E(()=>{mt(),mp(),gp(),ge(),qt(),_n(),fs(),kc=(e,t)=>{Le()._OrtInit(e,t)!==0&&Fe("Can't initialize onnxruntime.")},Er=async e=>{kc(e.wasm.numThreads,Bi(e.logLevel))},Cr=async(e,t)=>{Le().asyncInit?.();let i=e.webgpu.adapter;if(t==="webgpu"){if(typeof navigator>"u"||!navigator.gpu)throw new Error("WebGPU is not supported in current environment");if(i){if(typeof i.limits!="object"||typeof i.features!="object"||typeof i.requestDevice!="function")throw new Error("Invalid GPU adapter set in `env.webgpu.adapter`. It must be a GPUAdapter object.")}else{let n=e.webgpu.powerPreference;if(n!==void 0&&n!=="low-power"&&n!=="high-performance")throw new Error(`Invalid powerPreference setting: "${n}"`);let r=e.webgpu.forceFallbackAdapter;if(r!==void 0&&typeof r!="boolean")throw new Error(`Invalid forceFallbackAdapter setting: "${r}"`);if(i=await navigator.gpu.requestAdapter({powerPreference:n,forceFallbackAdapter:r}),!i)throw new Error('Failed to get GPU adapter. You may need to enable flag "--enable-unsafe-webgpu" if you are using Chrome.')}}if(t==="webnn"&&(typeof navigator>"u"||!navigator.ml))throw new Error("WebNN is not supported in current environment");{let n=(cf(),ee($c)).init;t==="webgpu"&&await n("webgpu",Le(),e,i),t==="webnn"&&await n("webnn",Le(),e)}},Vt=new Map,Tc=e=>{let t=Le(),i=t.stackSave();try{let n=t.PTR_SIZE,r=t.stackAlloc(2*n);t._OrtGetInputOutputCount(e,r,r+n)!==0&&Fe("Can't get session input/output count.");let s=n===4?"i32":"i64";return[Number(t.getValue(r,s)),Number(t.getValue(r+n,s))]}finally{t.stackRestore(i)}},Ir=(e,t)=>{let i=Le(),n=i.stackSave(),r=0;try{let s=i.PTR_SIZE,a=i.stackAlloc(2*s);i._OrtGetInputOutputMetadata(e,t,a,a+s)!==0&&Fe("Can't get session input/output metadata.");let o=Number(i.getValue(a,"*"));r=Number(i.getValue(a+s,"*"));let l=i.HEAP32[r/4];if(l===0)return[o,0];let u=i.HEAPU32[r/4+1],d=[];for(let c=0;c<u;c++){let p=Number(i.getValue(r+8+c*s,"*"));d.push(p!==0?i.UTF8ToString(p):Number(i.getValue(r+8+(c+u)*s,"*")))}return[o,l,d]}finally{i.stackRestore(n),r!==0&&i._OrtFree(r)}},Qi=e=>{let t=Le(),i=t._malloc(e.byteLength);if(i===0)throw new Error(`Can't create a session. failed to allocate a buffer of size ${e.byteLength}.`);return t.HEAPU8.set(e,i),[i,e.byteLength]},Ar=async(e,t)=>{let i,n,r=Le();Array.isArray(e)?[i,n]=e:e.buffer===r.HEAPU8.buffer?[i,n]=[e.byteOffset,e.byteLength]:[i,n]=Qi(e);let s=0,a=0,o=0,l=[],u=[],d=[];try{if([a,l]=await ps(t),t?.externalData&&r.mountExternalData){let x=[];for(let C of t.externalData){let R=typeof C=="string"?C:C.path;x.push(vn(typeof C=="string"?C:C.data).then(z=>{r.mountExternalData(R,z)}))}await Promise.all(x)}for(let x of t?.executionProviders??[])if((typeof x=="string"?x:x.name)==="webnn"){if(r.shouldTransferToMLTensor=!1,typeof x!="string"){let C=x,R=C?.context,z=C?.gpuDevice,P=C?.deviceType,U=C?.powerPreference;R?r.currentContext=R:z?r.currentContext=await r.webnnCreateMLContext(z):r.currentContext=await r.webnnCreateMLContext({deviceType:P,powerPreference:U})}else r.currentContext=await r.webnnCreateMLContext();break}s=await r._OrtCreateSession(i,n,a),r.webgpuOnCreateSession?.(s),s===0&&Fe("Can't create a session."),r.jsepOnCreateSession?.(),r.currentContext&&(r.webnnRegisterMLContext(s,r.currentContext),r.currentContext=void 0,r.shouldTransferToMLTensor=!0);let[c,p]=Tc(s),h=!!t?.enableGraphCapture,m=[],_=[],$=[],y=[],g=[];for(let x=0;x<c;x++){let[C,R,z]=Ir(s,x);C===0&&Fe("Can't get an input name."),u.push(C);let P=r.UTF8ToString(C);m.push(P),$.push(R===0?{name:P,isTensor:!1}:{name:P,isTensor:!0,type:Ot(R),shape:z})}for(let x=0;x<p;x++){let[C,R,z]=Ir(s,x+c);C===0&&Fe("Can't get an output name."),d.push(C);let P=r.UTF8ToString(C);_.push(P),y.push(R===0?{name:P,isTensor:!1}:{name:P,isTensor:!0,type:Ot(R),shape:z});{if(h&&t?.preferredOutputLocation===void 0){g.push("gpu-buffer");continue}let U=typeof t?.preferredOutputLocation=="string"?t.preferredOutputLocation:t?.preferredOutputLocation?.[P]??"cpu",re=r.webnnIsGraphOutput;if(U==="cpu"&&re&&re(s,P)){g.push("ml-tensor-cpu-output");continue}if(U!=="cpu"&&U!=="cpu-pinned"&&U!=="gpu-buffer"&&U!=="ml-tensor")throw new Error(`Not supported preferred output location: ${U}.`);if(h&&U!=="gpu-buffer")throw new Error(`Not supported preferred output location: ${U}. Only 'gpu-buffer' location is supported when enableGraphCapture is true.`);g.push(U)}}let T=null;return g.some(x=>x==="gpu-buffer"||x==="ml-tensor"||x==="ml-tensor-cpu-output")&&(o=r._OrtCreateBinding(s),o===0&&Fe("Can't create IO binding."),T={handle:o,outputPreferredLocations:g,outputPreferredLocationsEncoded:g.map(x=>x==="ml-tensor-cpu-output"?"ml-tensor":x).map(x=>bn(x))}),Vt.set(s,[s,u,d,T,h,!1]),[s,m,_,$,y]}catch(c){throw u.forEach(p=>r._OrtFree(p)),d.forEach(p=>r._OrtFree(p)),o!==0&&r._OrtReleaseBinding(o)!==0&&Fe("Can't release IO binding."),s!==0&&r._OrtReleaseSession(s)!==0&&Fe("Can't release session."),c}finally{r._free(i),a!==0&&r._OrtReleaseSessionOptions(a)!==0&&Fe("Can't release session options."),l.forEach(c=>r._free(c)),r.unmountExternalData?.()}},zr=e=>{let t=Le(),i=Vt.get(e);if(!i)throw new Error(`cannot release session. invalid session id: ${e}`);let[n,r,s,a,o]=i;a&&(o&&t._OrtClearBoundOutputs(a.handle)!==0&&Fe("Can't clear bound outputs."),t._OrtReleaseBinding(a.handle)!==0&&Fe("Can't release IO binding.")),t.jsepOnReleaseSession?.(e),t.webnnOnReleaseSession?.(e),t.webgpuOnReleaseSession?.(e),r.forEach(l=>t._OrtFree(l)),s.forEach(l=>t._OrtFree(l)),t._OrtReleaseSession(n)!==0&&Fe("Can't release session."),Vt.delete(e)},Mr=async(e,t,i,n,r,s,a=!1)=>{if(!e){t.push(0);return}let o=Le(),l=o.PTR_SIZE,u=e[0],d=e[1],c=e[3],p=c,h,m;if(u==="string"&&(c==="gpu-buffer"||c==="ml-tensor"))throw new Error("String tensor is not supported on GPU.");if(a&&c!=="gpu-buffer")throw new Error(`External buffer must be provided for input/output index ${s} when enableGraphCapture is true.`);if(c==="gpu-buffer"){let y=e[2].gpuBuffer;m=Gt(Wt(u),d);{let g=o.jsepRegisterBuffer;if(!g)throw new Error('Tensor location "gpu-buffer" is not supported without using WebGPU.');h=g(n,s,y,m)}}else if(c==="ml-tensor"){let y=e[2].mlTensor;m=Gt(Wt(u),d);let g=o.webnnRegisterMLTensor;if(!g)throw new Error('Tensor location "ml-tensor" is not supported without using WebNN.');h=g(n,y,Wt(u),d)}else{let y=e[2];if(Array.isArray(y)){m=l*y.length,h=o._malloc(m),i.push(h);for(let g=0;g<y.length;g++){if(typeof y[g]!="string")throw new TypeError(`tensor data at index ${g} is not a string`);o.setValue(h+g*l,bt(y[g],i),"*")}}else{let g=o.webnnIsGraphInput,T=o.webnnIsGraphOutput;if(u!=="string"&&g&&T){let x=o.UTF8ToString(r);if(g(n,x)||T(n,x)){let C=Wt(u);m=Gt(C,d),p="ml-tensor";let R=o.webnnCreateTemporaryTensor,z=o.webnnUploadTensor;if(!R||!z)throw new Error('Tensor location "ml-tensor" is not supported without using WebNN.');let P=await R(n,C,d);z(P,new Uint8Array(y.buffer,y.byteOffset,y.byteLength)),h=P}else m=y.byteLength,h=o._malloc(m),i.push(h),o.HEAPU8.set(new Uint8Array(y.buffer,y.byteOffset,m),h)}else m=y.byteLength,h=o._malloc(m),i.push(h),o.HEAPU8.set(new Uint8Array(y.buffer,y.byteOffset,m),h)}}let _=o.stackSave(),$=o.stackAlloc(4*d.length);try{d.forEach((g,T)=>o.setValue($+T*l,g,l===4?"i32":"i64"));let y=o._OrtCreateTensor(Wt(u),h,m,$,d.length,bn(p));y===0&&Fe(`Can't create tensor for input/output. session=${n}, index=${s}.`),t.push(y)}finally{o.stackRestore(_)}},Rr=async(e,t,i,n,r,s)=>{let a=Le(),o=a.PTR_SIZE,l=Vt.get(e);if(!l)throw new Error(`cannot run inference. invalid session id: ${e}`);let u=l[0],d=l[1],c=l[2],p=l[3],h=l[4],m=l[5],_=t.length,$=n.length,y=0,g=[],T=[],x=[],C=[],R=a.stackSave(),z=a.stackAlloc(_*o),P=a.stackAlloc(_*o),U=a.stackAlloc($*o),re=a.stackAlloc($*o);try{[y,g]=os(s),ye("wasm prepareInputOutputTensor");for(let ae=0;ae<_;ae++)await Mr(i[ae],T,C,e,d[t[ae]],t[ae],h);for(let ae=0;ae<$;ae++)await Mr(r[ae],x,C,e,c[n[ae]],_+n[ae],h);Ce("wasm prepareInputOutputTensor");for(let ae=0;ae<_;ae++)a.setValue(z+ae*o,T[ae],"*"),a.setValue(P+ae*o,d[t[ae]],"*");for(let ae=0;ae<$;ae++)a.setValue(U+ae*o,x[ae],"*"),a.setValue(re+ae*o,c[n[ae]],"*");if(p&&!m){let{handle:ae,outputPreferredLocations:ke,outputPreferredLocationsEncoded:me}=p;if(d.length!==_)throw new Error(`input count from feeds (${_}) is expected to be always equal to model's input count (${d.length}).`);ye("wasm bindInputsOutputs");for(let ue=0;ue<_;ue++){let De=t[ue];await a._OrtBindInput(ae,d[De],T[ue])!==0&&Fe(`Can't bind input[${ue}] for session=${e}.`)}for(let ue=0;ue<$;ue++){let De=n[ue];r[ue]?.[3]?a._OrtBindOutput(ae,c[De],x[ue],0)!==0&&Fe(`Can't bind pre-allocated output[${ue}] for session=${e}.`):a._OrtBindOutput(ae,c[De],0,me[De])!==0&&Fe(`Can't bind output[${ue}] to ${ke[ue]} for session=${e}.`)}Ce("wasm bindInputsOutputs"),Vt.set(e,[u,d,c,p,h,!0])}a.jsepOnRunStart?.(u),a.webnnOnRunStart?.(u);let _e;p?_e=await a._OrtRunWithBinding(u,p.handle,$,U,y):_e=await a._OrtRun(u,P,z,_,re,$,U,y),_e!==0&&Fe("failed to call OrtRun().");let pe=[],be=[];ye("wasm ProcessOutputTensor");for(let ae=0;ae<$;ae++){let ke=Number(a.getValue(U+ae*o,"*"));if(ke===x[ae]){pe.push(r[ae]);continue}let me=a.stackSave(),ue=a.stackAlloc(4*o),De=!1,fe,Ue=0;try{a._OrtGetTensorData(ke,ue,ue+o,ue+2*o,ue+3*o)!==0&&Fe(`Can't access output tensor data on index ${ae}.`);let G=o===4?"i32":"i64",ne=Number(a.getValue(ue,G));Ue=a.getValue(ue+o,"*");let Se=a.getValue(ue+o*2,"*"),Pe=Number(a.getValue(ue+o*3,G)),nt=[];for(let rt=0;rt<Pe;rt++)nt.push(Number(a.getValue(Se+rt*o,G)));a._OrtFree(Se)!==0&&Fe("Can't free memory for tensor dims.");let Ct=nt.reduce((rt,Qe)=>rt*Qe,1);fe=Ot(ne);let Ei=p?.outputPreferredLocations[n[ae]];if(fe==="string"){if(Ei==="gpu-buffer"||Ei==="ml-tensor")throw new Error("String tensor is not supported on GPU.");let rt=[];for(let Qe=0;Qe<Ct;Qe++){let Ft=a.getValue(Ue+Qe*o,"*"),gf=a.getValue(Ue+(Qe+1)*o,"*"),_f=Qe===Ct-1?void 0:gf-Ft;rt.push(a.UTF8ToString(Ft,_f))}pe.push([fe,nt,rt,"cpu"])}else if(Ei==="gpu-buffer"&&Ct>0){let rt=a.jsepGetBuffer;if(!rt)throw new Error('preferredLocation "gpu-buffer" is not supported without using WebGPU.');let Qe=rt(Ue),Ft=Gt(ne,Ct);if(Ft===void 0||!yn(fe))throw new Error(`Unsupported data type: ${fe}`);De=!0,pe.push([fe,nt,{gpuBuffer:Qe,download:a.jsepCreateDownloader(Qe,Ft,fe),dispose:()=>{a._OrtReleaseTensor(ke)!==0&&Fe("Can't release tensor.")}},"gpu-buffer"])}else if(Ei==="ml-tensor"&&Ct>0){let rt=a.webnnEnsureTensor,Qe=a.webnnIsGraphInputOutputTypeSupported;if(!rt||!Qe)throw new Error('preferredLocation "ml-tensor" is not supported without using WebNN.');if(Gt(ne,Ct)===void 0||!wn(fe))throw new Error(`Unsupported data type: ${fe}`);if(!Qe(e,fe,!1))throw new Error(`preferredLocation "ml-tensor" for ${fe} output is not supported by current WebNN Context.`);let Ft=await rt(e,Ue,ne,nt,!1);De=!0,pe.push([fe,nt,{mlTensor:Ft,download:a.webnnCreateMLTensorDownloader(Ue,fe),dispose:()=>{a.webnnReleaseTensorId(Ue),a._OrtReleaseTensor(ke)}},"ml-tensor"])}else if(Ei==="ml-tensor-cpu-output"&&Ct>0){let rt=a.webnnCreateMLTensorDownloader(Ue,fe)(),Qe=pe.length;De=!0,be.push((async()=>{let Ft=[Qe,await rt];return a.webnnReleaseTensorId(Ue),a._OrtReleaseTensor(ke),Ft})()),pe.push([fe,nt,[],"cpu"])}else{let rt=Di(fe),Qe=new rt(Ct);new Uint8Array(Qe.buffer,Qe.byteOffset,Qe.byteLength).set(a.HEAPU8.subarray(Ue,Ue+Qe.byteLength)),pe.push([fe,nt,Qe,"cpu"])}}finally{a.stackRestore(me),fe==="string"&&Ue&&a._free(Ue),De||a._OrtReleaseTensor(ke)}}p&&!h&&(a._OrtClearBoundOutputs(p.handle)!==0&&Fe("Can't clear bound outputs."),Vt.set(e,[u,d,c,p,h,!1]));for(let[ae,ke]of await Promise.all(be))pe[ae][2]=ke;return Ce("wasm ProcessOutputTensor"),pe}finally{a.webnnOnRunEnd?.(u),a.stackRestore(R),T.forEach(_e=>a._OrtReleaseTensor(_e)),x.forEach(_e=>a._OrtReleaseTensor(_e)),C.forEach(_e=>a._free(_e)),y!==0&&a._OrtReleaseRunOptions(y),g.forEach(_e=>a._free(_e))}},Or=e=>{let t=Le(),i=Vt.get(e);if(!i)throw new Error("invalid session id");let n=i[0],r=t._OrtEndProfiling(n);r===0&&Fe("Can't get an profile file name."),t._OrtFree(r)},Dr=e=>{let t=[];for(let i of e){let n=i[2];!Array.isArray(n)&&"buffer"in n&&t.push(n.buffer)}return t}}),Lt,gt,li,ki,Ti,Xi,Br,Yi,Yt,Jt,Cc,Ic,Ac,zc,Mc,Rc,Oc,Dc,Bc=E(()=>{mt(),Ec(),qt(),fn(),Lt=()=>!!se.wasm.proxy&&typeof document<"u",li=!1,ki=!1,Ti=!1,Yi=new Map,Yt=(e,t)=>{let i=Yi.get(e);i?i.push(t):Yi.set(e,[t])},Jt=()=>{if(li||!ki||Ti||!gt)throw new Error("worker not ready")},Cc=e=>{switch(e.data.type){case"init-wasm":li=!1,e.data.err?(Ti=!0,Br[1](e.data.err)):(ki=!0,Br[0]()),Xi&&(URL.revokeObjectURL(Xi),Xi=void 0);break;case"init-ep":case"copy-from":case"create":case"release":case"run":case"end-profiling":{let t=Yi.get(e.data.type);e.data.err?t.shift()[1](e.data.err):t.shift()[0](e.data.out);break}}},Ic=async()=>{if(!ki){if(li)throw new Error("multiple calls to 'initWasm()' detected.");if(Ti)throw new Error("previous call to 'initWasm()' failed.");if(li=!0,Lt())return new Promise((e,t)=>{gt?.terminate(),is().then(([i,n])=>{try{gt=n,gt.onerror=s=>t(s),gt.onmessage=Cc,Br=[e,t];let r={type:"init-wasm",in:se};if(!r.in.wasm.wasmPaths&&i){let s=un();s&&(r.in.wasm.wasmPaths=s)}gt.postMessage(r),Xi=i}catch(r){t(r)}},t)});try{await gn(se.wasm),await Er(se),ki=!0}catch(e){throw Ti=!0,e}finally{li=!1}}},Ac=async e=>{if(Lt())return Jt(),new Promise((t,i)=>{Yt("init-ep",[t,i]);let n={type:"init-ep",in:{epName:e,env:se}};gt.postMessage(n)});await Cr(se,e)},zc=async e=>Lt()?(Jt(),new Promise((t,i)=>{Yt("copy-from",[t,i]);let n={type:"copy-from",in:{buffer:e}};gt.postMessage(n,[e.buffer])})):Qi(e),Mc=async(e,t)=>{if(Lt()){if(t?.preferredOutputLocation)throw new Error('session option "preferredOutputLocation" is not supported for proxy.');return Jt(),new Promise((i,n)=>{Yt("create",[i,n]);let r={type:"create",in:{model:e,options:{...t}}},s=[];e instanceof Uint8Array&&s.push(e.buffer),gt.postMessage(r,s)})}else return Ar(e,t)},Rc=async e=>{if(Lt())return Jt(),new Promise((t,i)=>{Yt("release",[t,i]);let n={type:"release",in:e};gt.postMessage(n)});zr(e)},Oc=async(e,t,i,n,r,s)=>{if(Lt()){if(i.some(a=>a[3]!=="cpu"))throw new Error("input tensor on GPU is not supported for proxy.");if(r.some(a=>a))throw new Error("pre-allocated output tensor is not supported for proxy.");return Jt(),new Promise((a,o)=>{Yt("run",[a,o]);let l=i,u={type:"run",in:{sessionId:e,inputIndices:t,inputs:l,outputIndices:n,options:s}};gt.postMessage(u,Dr(l))})}else return Rr(e,t,i,n,r,s)},Dc=async e=>{if(Lt())return Jt(),new Promise((t,i)=>{Yt("end-profiling",[t,i]);let n={type:"end-profiling",in:e};gt.postMessage(n)});Or(e)}}),Fr,Fc,Pc,pf=E(()=>{mt(),Bc(),ge(),an(),fs(),Fr=(e,t)=>{switch(e.location){case"cpu":return[e.type,e.dims,e.data,"cpu"];case"gpu-buffer":return[e.type,e.dims,{gpuBuffer:e.gpuBuffer},"gpu-buffer"];case"ml-tensor":return[e.type,e.dims,{mlTensor:e.mlTensor},"ml-tensor"];default:throw new Error(`invalid data location: ${e.location} for ${t()}`)}},Fc=e=>{switch(e[3]){case"cpu":return new at(e[0],e[2],e[1]);case"gpu-buffer":{let t=e[0];if(!yn(t))throw new Error(`not supported data type: ${t} for deserializing GPU tensor`);let{gpuBuffer:i,download:n,dispose:r}=e[2];return at.fromGpuBuffer(i,{dataType:t,dims:e[1],download:n,dispose:r})}case"ml-tensor":{let t=e[0];if(!wn(t))throw new Error(`not supported data type: ${t} for deserializing MLTensor tensor`);let{mlTensor:i,download:n,dispose:r}=e[2];return at.fromMLTensor(i,{dataType:t,dims:e[1],download:n,dispose:r})}default:throw new Error(`invalid data location: ${e[3]}`)}},Pc=class{async fetchModelAndCopyToWasmMemory(e){return zc(await vn(e))}async loadModel(e,t){K();let i;typeof e=="string"?i=await this.fetchModelAndCopyToWasmMemory(e):i=e,[this.sessionId,this.inputNames,this.outputNames,this.inputMetadata,this.outputMetadata]=await Mc(i,t),he()}async dispose(){return Rc(this.sessionId)}async run(e,t,i){K();let n=[],r=[];Object.entries(e).forEach(c=>{let p=c[0],h=c[1],m=this.inputNames.indexOf(p);if(m===-1)throw new Error(`invalid input '${p}'`);n.push(h),r.push(m)});let s=[],a=[];Object.entries(t).forEach(c=>{let p=c[0],h=c[1],m=this.outputNames.indexOf(p);if(m===-1)throw new Error(`invalid output '${p}'`);s.push(h),a.push(m)});let o=n.map((c,p)=>Fr(c,()=>`input "${this.inputNames[r[p]]}"`)),l=s.map((c,p)=>c?Fr(c,()=>`output "${this.outputNames[a[p]]}"`):null),u=await Oc(this.sessionId,r,o,a,l,i),d={};for(let c=0;c<u.length;c++)d[this.outputNames[a[c]]]=s[c]??Fc(u[c]);return he(),d}startProfiling(){}endProfiling(){Dc(this.sessionId)}}}),Nc={};X(Nc,{OnnxruntimeWebAssemblyBackend:()=>Nr,initializeFlags:()=>Pr,wasmBackend:()=>Vc});var Pr,Nr,Vc,ff=E(()=>{mt(),Bc(),pf(),Pr=()=>{(typeof se.wasm.initTimeout!="number"||se.wasm.initTimeout<0)&&(se.wasm.initTimeout=0);let e=se.wasm.simd;if(typeof e!="boolean"&&e!==void 0&&e!=="fixed"&&e!=="relaxed"&&(console.warn(`Property "env.wasm.simd" is set to unknown value "${e}". Reset it to \`false\` and ignore SIMD feature checking.`),se.wasm.simd=!1),typeof se.wasm.proxy!="boolean"&&(se.wasm.proxy=!1),typeof se.wasm.trace!="boolean"&&(se.wasm.trace=!1),typeof se.wasm.numThreads!="number"||!Number.isInteger(se.wasm.numThreads)||se.wasm.numThreads<=0)if(typeof self<"u"&&!self.crossOriginIsolated)se.wasm.numThreads=1;else{let t=typeof navigator>"u"?A("node:os").cpus().length:navigator.hardwareConcurrency;se.wasm.numThreads=Math.min(4,Math.ceil((t||1)/2))}},Nr=class{async init(e){Pr(),await Ic(),await Ac(e)}async createInferenceSessionHandler(e,t){let i=new Pc;return await i.loadModel(e,t),i}},Vc=new Nr}),Lc={};X(Lc,{InferenceSession:()=>ht,TRACE:()=>Te,TRACE_EVENT_BEGIN:()=>ye,TRACE_EVENT_END:()=>Ce,TRACE_FUNC_BEGIN:()=>K,TRACE_FUNC_END:()=>he,Tensor:()=>at,default:()=>mf,env:()=>se,registerBackend:()=>N}),mt(),mt(),mt();var hf="1.23.0",mf=ri;{let e=(ff(),ee(Nc)).wasmBackend;N("webgpu",e,5),N("webnn",e,5),N("cpu",e,10),N("wasm",e,10)}return Object.defineProperty(se.versions,"web",{value:hf,enumerable:!0}),ee(Lc)})();/**
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
 */S.exports=w})(np);var ap=np.exports,jr={},op={};Object.defineProperty(op,"__esModule",{value:!0});var rn={},lp;Object.defineProperty(rn,"__esModule",{value:!0});rn.SileroLegacy=void 0;const Qc=ci;class Hr{constructor(f,w,v,k,b){this.ortInstance=f,this._session=w,this._h=v,this._c=k,this._sr=b,this.reset_state=()=>{const I=Array(128).fill(0);this._h=new this.ortInstance.Tensor("float32",I,[2,1,64]),this._c=new this.ortInstance.Tensor("float32",I,[2,1,64])},this.process=async I=>{const E={input:new this.ortInstance.Tensor("float32",I,[1,I.length]),h:this._h,c:this._c,sr:this._sr},X=await this._session.run(E);this._h=X.hn,this._c=X.cn;const[j]=X.output?.data;return{notSpeech:1-j,isSpeech:j}}}}rn.SileroLegacy=Hr;lp=Hr;Hr.new=async(S,f)=>{Qc.log.debug("initializing vad");const w=await f(),v=await S.InferenceSession.create(w),k=new S.Tensor("int64",[16000n]),b=Array(2*64).fill(0),I=new S.Tensor("float32",b,[2,1,64]),A=new S.Tensor("float32",b,[2,1,64]);return Qc.log.debug("vad is initialized"),new lp(S,v,I,A,k)};var sn={},up;Object.defineProperty(sn,"__esModule",{value:!0});sn.SileroV5=void 0;const Xc=ci;function dp(S){const f=Array(256).fill(0);return new S.Tensor("float32",f,[2,1,128])}class Kr{constructor(f,w,v,k){this._session=f,this._state=w,this._sr=v,this.ortInstance=k,this.reset_state=()=>{this._state=dp(this.ortInstance)},this.process=async b=>{const A={input:new this.ortInstance.Tensor("float32",b,[1,b.length]),state:this._state,sr:this._sr},E=await this._session.run(A);this._state=E.stateN;const[X]=E.output?.data;return{notSpeech:1-X,isSpeech:X}}}}sn.SileroV5=Kr;up=Kr;Kr.new=async(S,f)=>{Xc.log.debug("Loading VAD...");const w=await f(),v=await S.InferenceSession.create(w),k=new S.Tensor("int64",[16000n]),b=dp(S);return Xc.log.debug("...finished loading VAD"),new up(v,b,k,S)};(function(S){var f=Ze&&Ze.__createBinding||(Object.create?function(b,I,A,E){E===void 0&&(E=A);var X=Object.getOwnPropertyDescriptor(I,A);(!X||("get"in X?!I.__esModule:X.writable||X.configurable))&&(X={enumerable:!0,get:function(){return I[A]}}),Object.defineProperty(b,E,X)}:function(b,I,A,E){E===void 0&&(E=A),b[E]=I[A]}),w=Ze&&Ze.__exportStar||function(b,I){for(var A in b)A!=="default"&&!Object.prototype.hasOwnProperty.call(I,A)&&f(I,b,A)};Object.defineProperty(S,"__esModule",{value:!0}),S.SileroV5=S.SileroLegacy=void 0,w(op,S);var v=rn;Object.defineProperty(S,"SileroLegacy",{enumerable:!0,get:function(){return v.SileroLegacy}});var k=sn;Object.defineProperty(S,"SileroV5",{enumerable:!0,get:function(){return k.SileroV5}})})(jr);var zi={};Object.defineProperty(zi,"__esModule",{value:!0});zi.Resampler=void 0;const Uf=ci;class qf{constructor(f){this.options=f,this.process=w=>{const v=[];for(const k of w)for(this.inputBuffer.push(k);this.hasEnoughDataForFrame();){const b=this.generateOutputFrame();v.push(b)}return v},f.nativeSampleRate<16e3&&Uf.log.error("nativeSampleRate is too low. Should have 16000 = targetSampleRate <= nativeSampleRate"),this.inputBuffer=[]}async*stream(f){for(const w of f)for(this.inputBuffer.push(w);this.hasEnoughDataForFrame();)yield this.generateOutputFrame()}hasEnoughDataForFrame(){return this.inputBuffer.length*this.options.targetSampleRate/this.options.nativeSampleRate>=this.options.targetFrameSize}generateOutputFrame(){const f=new Float32Array(this.options.targetFrameSize);let w=0,v=0;for(;w<this.options.targetFrameSize;){let k=0,b=0;for(;v<Math.min(this.inputBuffer.length,(w+1)*this.options.nativeSampleRate/this.options.targetSampleRate);){const I=this.inputBuffer[v];I!==void 0&&(k+=I,b++),v++}f[w]=k/b,w++}return this.inputBuffer=this.inputBuffer.slice(v),f}}zi.Resampler=qf;(function(S){var f=Ze&&Ze.__createBinding||(Object.create?function(ie,J,N,Z){Z===void 0&&(Z=N);var H=Object.getOwnPropertyDescriptor(J,N);(!H||("get"in H?!J.__esModule:H.writable||H.configurable))&&(H={enumerable:!0,get:function(){return J[N]}}),Object.defineProperty(ie,Z,H)}:function(ie,J,N,Z){Z===void 0&&(Z=N),ie[Z]=J[N]}),w=Ze&&Ze.__setModuleDefault||(Object.create?function(ie,J){Object.defineProperty(ie,"default",{enumerable:!0,value:J})}:function(ie,J){ie.default=J}),v=Ze&&Ze.__importStar||function(ie){if(ie&&ie.__esModule)return ie;var J={};if(ie!=null)for(var N in ie)N!=="default"&&Object.prototype.hasOwnProperty.call(ie,N)&&f(J,ie,N);return w(J,ie),J};Object.defineProperty(S,"__esModule",{value:!0}),S.NonRealTimeVAD=S.defaultNonRealTimeVADOptions=void 0;const k=v(ap),b=Ai,I=di,A=At,E=ii,X=jr,j=zi;S.defaultNonRealTimeVADOptions={...A.defaultFrameProcessorOptions,modelURL:b.baseAssetPath+"silero_vad_legacy.onnx",modelFetcher:I.defaultModelFetcher};class ee{static async new(J={}){const N={...S.defaultNonRealTimeVADOptions,...J};(0,A.validateOptions)(N),N.ortConfig!==void 0&&N.ortConfig(k);const Z=()=>N.modelFetcher(N.modelURL),H=await X.SileroLegacy.new(k,Z),te=new A.FrameProcessor(H.process,H.reset_state,{positiveSpeechThreshold:N.positiveSpeechThreshold,negativeSpeechThreshold:N.negativeSpeechThreshold,redemptionMs:N.redemptionMs,preSpeechPadMs:N.preSpeechPadMs,minSpeechMs:N.minSpeechMs,submitUserSpeechOnPause:N.submitUserSpeechOnPause},1536/16);return te.resume(),new this(Z,k,N,te)}constructor(J,N,Z,H){this.modelFetcher=J,this.ort=N,this.options=Z,this.frameProcessor=H,this.frameSamples=1536}async*run(J,N){const Z={nativeSampleRate:N,targetSampleRate:16e3,targetFrameSize:this.frameSamples},H=new j.Resampler(Z);let te=0,M=0,B=0;for await(const q of H.stream(J)){const V=[];await this.frameProcessor.process(q,W=>{V.push(W)});for(const W of V)switch(W.msg){case E.Message.SpeechStart:te=B*this.frameSamples/16;break;case E.Message.SpeechEnd:M=(B+1)*this.frameSamples/16,yield{audio:W.audio,start:te,end:M};break}B++}const D=[];this.frameProcessor.endSegment(q=>{D.push(q)});for(const q of D)switch(q.msg){case E.Message.SpeechEnd:yield{audio:q.audio,start:te,end:B*this.frameSamples/16}}}}S.NonRealTimeVAD=ee})(ip);var It={};Object.defineProperty(It,"__esModule",{value:!0});It.audioFileToArray=It.encodeWAV=It.arrayBufferToBase64=It.minFramesForTargetMS=void 0;function Wf(S,f,w=16e3){return Math.ceil(S*w/1e3/f)}It.minFramesForTargetMS=Wf;function Gf(S){const f=new Uint8Array(S),w=f.byteLength,v=new Array(w);for(var k=0;k<w;k++){const b=f[k];if(b===void 0)break;v[k]=String.fromCharCode(b)}return btoa(v.join(""))}It.arrayBufferToBase64=Gf;function jf(S,f=3,w=16e3,v=1,k=32){var b=k/8,I=v*b,A=new ArrayBuffer(44+S.length*b),E=new DataView(A);return en(E,0,"RIFF"),E.setUint32(4,36+S.length*b,!0),en(E,8,"WAVE"),en(E,12,"fmt "),E.setUint32(16,16,!0),E.setUint16(20,f,!0),E.setUint16(22,v,!0),E.setUint32(24,w,!0),E.setUint32(28,w*I,!0),E.setUint16(32,I,!0),E.setUint16(34,k,!0),en(E,36,"data"),E.setUint32(40,S.length*b,!0),f===1?Kf(E,44,S):Hf(E,44,S),A}It.encodeWAV=jf;function Hf(S,f,w){for(var v=0;v<w.length;v++,f+=4)S.setFloat32(f,w[v],!0)}function Kf(S,f,w){for(var v=0;v<w.length;v++,f+=2){var k=Math.max(-1,Math.min(1,w[v]));S.setInt16(f,k<0?k*32768:k*32767,!0)}}function en(S,f,w){for(var v=0;v<w.length;v++)S.setUint8(f+v,w.charCodeAt(v))}async function Zf(S){const f=new OfflineAudioContext(1,1,44100),w=new FileReader;let v=null;if(await new Promise(I=>{w.addEventListener("loadend",A=>{const E=w.result;f.decodeAudioData(E,X=>{v=X,f.startRendering().then(j=>{console.log("Rendering completed successfully"),I()}).catch(j=>{console.error(`Rendering failed: ${j}`)})},X=>{console.log(`Error with decoding audio data: ${X}`)})}),w.readAsArrayBuffer(S)}),v===null)throw Error("some shit");let k=v,b=new Float32Array(k.length);for(let I=0;I<k.length;I++)for(let A=0;A<k.numberOfChannels;A++)b[I]+=k.getChannelData(A)[I];return{audio:b,sampleRate:k.sampleRate}}It.audioFileToArray=Zf;var cp={};(function(S){var f=Ze&&Ze.__createBinding||(Object.create?function(te,M,B,D){D===void 0&&(D=B);var q=Object.getOwnPropertyDescriptor(M,B);(!q||("get"in q?!M.__esModule:q.writable||q.configurable))&&(q={enumerable:!0,get:function(){return M[B]}}),Object.defineProperty(te,D,q)}:function(te,M,B,D){D===void 0&&(D=B),te[D]=M[B]}),w=Ze&&Ze.__setModuleDefault||(Object.create?function(te,M){Object.defineProperty(te,"default",{enumerable:!0,value:M})}:function(te,M){te.default=M}),v=Ze&&Ze.__importStar||function(te){if(te&&te.__esModule)return te;var M={};if(te!=null)for(var B in te)B!=="default"&&Object.prototype.hasOwnProperty.call(te,B)&&f(M,te,B);return w(M,te),M};Object.defineProperty(S,"__esModule",{value:!0}),S.AudioNodeVAD=S.MicVAD=S.getDefaultRealTimeVADOptions=S.ort=S.DEFAULT_MODEL=void 0;const k=v(ap),b=di,I=At,A=ci,E=ii,X=jr,j=zi;S.DEFAULT_MODEL="legacy",S.ort=k;const ee="vad.worklet.bundle.min.js",ie="silero_vad_v5.onnx",J="silero_vad_legacy.onnx",N=te=>({...I.defaultFrameProcessorOptions,onFrameProcessed:(M,B)=>{},onVADMisfire:()=>{A.log.debug("VAD misfire")},onSpeechStart:()=>{A.log.debug("Detected speech start")},onSpeechEnd:()=>{A.log.debug("Detected speech end")},onSpeechRealStart:()=>{A.log.debug("Detected real speech start")},baseAssetPath:"./",onnxWASMBasePath:"./",model:te,workletOptions:{},getStream:async()=>await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:!0,autoGainControl:!0,noiseSuppression:!0}}),pauseStream:async M=>{M.getTracks().forEach(B=>{B.stop()})},resumeStream:async M=>await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:!0,autoGainControl:!0,noiseSuppression:!0}}),ortConfig:M=>{M.env.logLevel="error"},startOnLoad:!0});S.getDefaultRealTimeVADOptions=N;class Z{static async new(M={}){const B={...(0,S.getDefaultRealTimeVADOptions)(M.model??S.DEFAULT_MODEL),...M};(0,I.validateOptions)(B);const D=new AudioContext,q=await H.new(D,B),V=new Z(B,D,q);if(B.startOnLoad)try{await V.start()}catch(W){console.error("Error starting micVad",W)}return V}constructor(M,B,D,q=!1){this.options=M,this.audioContext=B,this.audioNodeVAD=D,this.listening=q,this.initialized=!1,this.pause=()=>{this.stream&&this.options.pauseStream(this.stream),this.audioNodeVAD.pause(),this.listening=!1},this.resume=async()=>{if(!this.stream){console.warn("Stream not initialized");return}this.stream=await this.options.resumeStream(this.stream),this.sourceNode&&this.sourceNode.disconnect(),this.sourceNode=new MediaStreamAudioSourceNode(this.audioContext,{mediaStream:this.stream}),this.audioNodeVAD.receive(this.sourceNode)},this.start=async()=>{this.initialized||(this.initialized=!0,this.stream=await this.options.getStream(),this.sourceNode=new MediaStreamAudioSourceNode(this.audioContext,{mediaStream:this.stream}),this.audioNodeVAD.receive(this.sourceNode)),this.stream?.active?(this.audioNodeVAD.start(),this.listening=!0):(await this.resume(),this.audioNodeVAD.start(),this.listening=!0)},this.destroy=()=>{this.listening&&this.pause(),this.stream?this.options.pauseStream(this.stream):console.warn("Stream not initialized"),this.sourceNode?this.sourceNode.disconnect():console.warn("Source node not initialized"),this.audioNodeVAD.destroy(),this.audioContext.close()},this.setOptions=V=>{this.audioNodeVAD.setFrameProcessorOptions(V)}}}S.MicVAD=Z;class H{static async new(M,B={}){const D={...(0,S.getDefaultRealTimeVADOptions)(B.model??S.DEFAULT_MODEL),...B};(0,I.validateOptions)(D),S.ort.env.wasm.wasmPaths=D.onnxWASMBasePath,D.ortConfig!==void 0&&D.ortConfig(S.ort);const q=D.model==="v5"?ie:J,V=D.baseAssetPath+q,W=D.model==="v5"?X.SileroV5.new:X.SileroLegacy.new;let se;try{se=await W(S.ort,()=>(0,b.defaultModelFetcher)(V))}catch(Ie){throw console.error(`Encountered an error while loading model file ${V}`),Ie}const we=D.model==="v5"?512:1536,ce=we/16,ze=new I.FrameProcessor(se.process,se.reset_state,{positiveSpeechThreshold:D.positiveSpeechThreshold,negativeSpeechThreshold:D.negativeSpeechThreshold,redemptionMs:D.redemptionMs,preSpeechPadMs:D.preSpeechPadMs,minSpeechMs:D.minSpeechMs,submitUserSpeechOnPause:D.submitUserSpeechOnPause},ce),Ee=new H(M,D,ze,we,ce);return await Ee.setupAudioNode(),Ee}constructor(M,B,D,q,V){this.ctx=M,this.options=B,this.frameSamples=q,this.msPerFrame=V,this.pause=()=>{this.frameProcessor.pause(this.handleFrameProcessorEvent)},this.start=()=>{this.frameProcessor.resume()},this.receive=W=>{W.connect(this.audioNode)},this.processFrame=async W=>{await this.frameProcessor.process(W,this.handleFrameProcessorEvent)},this.handleFrameProcessorEvent=W=>{switch(W.msg){case E.Message.FrameProcessed:this.options.onFrameProcessed(W.probs,W.frame);break;case E.Message.SpeechStart:this.options.onSpeechStart();break;case E.Message.SpeechRealStart:this.options.onSpeechRealStart();break;case E.Message.VADMisfire:this.options.onVADMisfire();break;case E.Message.SpeechEnd:this.options.onSpeechEnd(W.audio);break}},this.destroy=()=>{this.audioNode instanceof AudioWorkletNode&&this.audioNode.port.postMessage({message:E.Message.SpeechStop}),this.audioNode.disconnect(),this.gainNode?.disconnect()},this.setFrameProcessorOptions=W=>{this.frameProcessor.options={...this.frameProcessor.options,...W}},this.frameProcessor=D}async setupAudioNode(){if("audioWorklet"in this.ctx&&typeof AudioWorkletNode=="function")try{const q=this.options.baseAssetPath+ee;await this.ctx.audioWorklet.addModule(q);const V=this.options.workletOptions??{};V.processorOptions={...V.processorOptions??{},frameSamples:this.frameSamples},this.audioNode=new AudioWorkletNode(this.ctx,"vad-helper-worklet",V),this.audioNode.port.onmessage=async W=>{switch(W.data?.message){case E.Message.AudioFrame:let se=W.data.data;se instanceof ArrayBuffer||(se=new ArrayBuffer(W.data.data.byteLength),new Uint8Array(se).set(new Uint8Array(W.data.data)));const we=new Float32Array(se);await this.processFrame(we);break}};return}catch(q){console.log("AudioWorklet setup failed, falling back to ScriptProcessor",q)}this.resampler=new j.Resampler({nativeSampleRate:this.ctx.sampleRate,targetSampleRate:16e3,targetFrameSize:this.frameSamples??480});const B=4096;this.audioNode=this.ctx.createScriptProcessor(B,1,1),this.gainNode=this.ctx.createGain(),this.gainNode.gain.value=0;let D=!1;this.audioNode.onaudioprocess=async q=>{if(!D){D=!0;try{const V=q.inputBuffer.getChannelData(0);if(q.outputBuffer.getChannelData(0).fill(0),this.resampler){const se=this.resampler.process(V);for(const we of se)await this.processFrame(we)}}catch(V){console.error("Error processing audio:",V)}finally{D=!1}}},this.audioNode.connect(this.gainNode),this.gainNode.connect(this.ctx.destination)}}S.AudioNodeVAD=H})(cp);(function(S){Object.defineProperty(S,"__esModule",{value:!0}),S.getDefaultRealTimeVADOptions=S.MicVAD=S.DEFAULT_MODEL=S.AudioNodeVAD=S.utils=S.NonRealTimeVAD=S.Message=S.FrameProcessor=S.defaultModelFetcher=S.baseAssetPath=void 0;var f=Ai;Object.defineProperty(S,"baseAssetPath",{enumerable:!0,get:function(){return f.baseAssetPath}});var w=di;Object.defineProperty(S,"defaultModelFetcher",{enumerable:!0,get:function(){return w.defaultModelFetcher}});var v=At;Object.defineProperty(S,"FrameProcessor",{enumerable:!0,get:function(){return v.FrameProcessor}});var k=ii;Object.defineProperty(S,"Message",{enumerable:!0,get:function(){return k.Message}});var b=ip;Object.defineProperty(S,"NonRealTimeVAD",{enumerable:!0,get:function(){return b.NonRealTimeVAD}});const I=It;S.utils={audioFileToArray:I.audioFileToArray,minFramesForTargetMS:I.minFramesForTargetMS,arrayBufferToBase64:I.arrayBufferToBase64,encodeWAV:I.encodeWAV};var A=cp;Object.defineProperty(S,"AudioNodeVAD",{enumerable:!0,get:function(){return A.AudioNodeVAD}}),Object.defineProperty(S,"DEFAULT_MODEL",{enumerable:!0,get:function(){return A.DEFAULT_MODEL}}),Object.defineProperty(S,"MicVAD",{enumerable:!0,get:function(){return A.MicVAD}}),Object.defineProperty(S,"getDefaultRealTimeVADOptions",{enumerable:!0,get:function(){return A.getDefaultRealTimeVADOptions}})})(qr);(function(S){var f=Ze&&Ze.__createBinding||(Object.create?function(H,te,M,B){B===void 0&&(B=M);var D=Object.getOwnPropertyDescriptor(te,M);(!D||("get"in D?!te.__esModule:D.writable||D.configurable))&&(D={enumerable:!0,get:function(){return te[M]}}),Object.defineProperty(H,B,D)}:function(H,te,M,B){B===void 0&&(B=M),H[B]=te[M]}),w=Ze&&Ze.__setModuleDefault||(Object.create?function(H,te){Object.defineProperty(H,"default",{enumerable:!0,value:te})}:function(H,te){H.default=te}),v=Ze&&Ze.__importStar||function(H){if(H&&H.__esModule)return H;var te={};if(H!=null)for(var M in H)M!=="default"&&Object.prototype.hasOwnProperty.call(H,M)&&f(te,H,M);return w(te,H),te};Object.defineProperty(S,"__esModule",{value:!0}),S.useMicVAD=S.getDefaultReactRealTimeVADOptions=S.utils=void 0;const k=qr,b=v(Y);var I=qr;Object.defineProperty(S,"utils",{enumerable:!0,get:function(){return I.utils}});const A={userSpeakingThreshold:.6},E=H=>({...(0,k.getDefaultRealTimeVADOptions)(H),...A});S.getDefaultReactRealTimeVADOptions=E;const X=Object.keys(A),j=Object.keys((0,k.getDefaultRealTimeVADOptions)("v5")),ee=(H,te)=>H.reduce((M,B)=>(M[B]=te[B],M),{});function ie(H){const te=H.model??k.DEFAULT_MODEL;H={...(0,S.getDefaultReactRealTimeVADOptions)(te),...H};const M=ee(X,H),B=ee(j,H);return[M,B]}function J(H){const te=b.default.useRef(H);return Z(()=>{te.current=H}),b.default.useCallback((...M)=>te.current.apply(void 0,M),[])}function N(H){const[te,M]=ie(H),[B,D]=(0,b.useState)(!1),[q,V]=(0,b.useState)(!0),[W,se]=(0,b.useState)(!1),[we,ce]=(0,b.useState)(!1),[ze,Ee]=(0,b.useState)(null),Ie=J(M.onFrameProcessed);M.onFrameProcessed=J((Re,st)=>{const Tt=Re.isSpeech>te.userSpeakingThreshold;D(Tt),Ie(Re,st)});const{onSpeechEnd:Ke,onSpeechStart:Ne,onSpeechRealStart:Ye,onVADMisfire:tt}=M,Je=J(Ke),Me=J(Ne),Ve=J(tt),Xe=J(Ye);M.onSpeechEnd=Je,M.onSpeechStart=Me,M.onVADMisfire=Ve,M.onSpeechRealStart=Xe,(0,b.useEffect)(()=>{let Re,st=!1;return(async()=>{try{if(Re=await k.MicVAD.new(M),st){Re.destroy();return}}catch(We){V(!1),We instanceof Error?se(We.message):se(String(We));return}Ee(Re),V(!1),M.startOnLoad&&(Re?.start(),ce(!0))})().catch(We=>{console.log("Well that didn't work")}),function(){Re?.destroy(),st=!0,!q&&!W&&ce(!1)}},[]);const dt=()=>{!q&&!W&&(ze?.pause(),ce(!1))},ct=()=>{!q&&!W&&(ze?.start(),ce(!0))};return{listening:we,errored:W,loading:q,userSpeaking:B,pause:dt,start:ct,toggle:()=>{we?dt():ct()}}}S.useMicVAD=N;const Z=typeof window<"u"&&typeof window.document<"u"&&typeof window.document.createElement<"u"?b.default.useLayoutEffect:b.default.useEffect})(ep);function Qf(){return"https://storage.googleapis.com/voice-form-filler-474017-bookmarklet/vad-assets/vad-web/"}function Xf(){return"https://storage.googleapis.com/voice-form-filler-474017-bookmarklet/vad-assets/onnxruntime/"}const Yf=Qf(),Jf=Xf();function pp(S){const f=S?.callbacks,w=S?.sharedStream,v=S?.sensitivity||{},k=Y.useRef(w);Y.useEffect(()=>{k.current=w,console.log("[useDemoVAD] Stream updated:",!!w)},[w]);const b=ep.useMicVAD({startOnLoad:!1,baseAssetPath:Yf,onnxWASMBasePath:Jf,getStream:async()=>(console.log("[useDemoVAD] getStream called, streamRef.current:",!!k.current),k.current?(console.log("[useDemoVAD] Using shared stream"),k.current):(console.log("[useDemoVAD] Creating new stream"),await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:!0,noiseSuppression:!0,autoGainControl:!0,channelCount:1}}))),positiveSpeechThreshold:v.positiveSpeechThreshold??.98,negativeSpeechThreshold:v.negativeSpeechThreshold??.85,minSpeechMs:v.minSpeechMs??400,redemptionMs:v.redemptionMs??500,onSpeechStart:()=>{f?.onSpeechStart?.()},onSpeechEnd:I=>{f?.onSpeechEnd?.(I)},onVADMisfire:()=>{f?.onVADMisfire?.()},onFrameProcessed:(I,A)=>{const E=I.isSpeech;f?.onFrameProcessed?.(E,A)}});return{userSpeaking:b.userSpeaking,loading:b.loading,errored:b.errored,pause:b.pause,start:b.start}}const Lr=[{language:"English",code:"en",text:'Say "Hello Gemini" in your native language'},{language:"Spanish",code:"es",text:"Di 'Hola Géminis' en tu idioma nativo."},{language:"Chinese (Simplified)",code:"zh-Hans",text:'用你的母语说"你好，双子座"。'},{language:"Hindi",code:"hi",text:'अपनी मूल भाषा में "नमस्ते जेमिनी" कहिए।'},{language:"Arabic",code:"ar",text:'قل "مرحباً يا چيميني" بلغتك الأم.'},{language:"Portuguese",code:"pt",text:'Diga "Olá Gemini" na sua língua nativa.'},{language:"Bengali",code:"bn",text:"আপনার মাতৃভাষায় 'হ্যালো জেমিনি' বলুন।"},{language:"Russian",code:"ru",text:"Скажи «Привет, Джемини» на своём родном языке."},{language:"Japanese",code:"ja",text:"母国語で「こんにちは、ジェミニ」と言ってください。"},{language:"Punjabi",code:"pa",text:'ਆਪਣੀ ਮਾਂ ਬੋਲੀ ਵਿੱਚ "ਹੈਲੋ ਜੈਮਿਨੀ" ਕਹੋ।'},{language:"German",code:"de",text:'Sag "Hallo Gemini" in deiner Muttersprache.'},{language:"Javanese",code:"jv",text:"Ucapake 'Halo Gemini' nganggo basa ibumu."},{language:"Korean",code:"ko",text:'모국어로 "안녕하세요 제미나이"라고 말해 주세요.'},{language:"French",code:"fr",text:'Dis "Bonjour Gemini" dans ta langue maternelle.'},{language:"Turkish",code:"tr",text:'Ana dilinde "Merhaba Gemini" de.'},{language:"Vietnamese",code:"vi",text:'Nói "Chào Gemini" bằng tiếng mẹ đẻ của bạn.'},{language:"Italian",code:"it",text:`Di' "Ciao Gemini" nella tua lingua madre.`},{language:"Thai",code:"th",text:'พูดว่า "สวัสดี Gemini" ในภาษาแม่ของคุณ.'},{language:"Persian",code:"fa",text:"به زبان مادری خود بگویید 'سلام جِمینی'."},{language:"Polish",code:"pl",text:'Powiedz „Cześć Gemini" w swoim języku ojczystym.'},{language:"Ukrainian",code:"uk",text:"Скажи «Привіт, Дженімі» своєю рідною мовою."},{language:"Urdu",code:"ur",text:"اپنی مادری زبان میں 'ہیلو جیمنی' کہیں۔"},{language:"Indonesian",code:"id",text:"Ucapkan 'Halo Gemini' dalam bahasa ibumu."},{language:"Dutch",code:"nl",text:'Zeg "Hallo Gemini" in je moedertaal.'},{language:"Greek",code:"el",text:"Πες «Γεια σου Gemini» στη μητρική σου γλώσσα."},{language:"Czech",code:"cs",text:'Řekněte „Ahoj Gemini" ve svém rodném jazyce.'},{language:"Swedish",code:"sv",text:'Säg "Hej Gemini" på ditt modersmål.'},{language:"Romanian",code:"ro",text:'Spune "Salut Gemini" în limba ta maternă.'},{language:"Hebrew",code:"iw",text:`אמור "שלום ג'מיני" בשפת האם שלך.`},{language:"Swahili",code:"sw",text:"Sema 'Habari Gemini' kwa lugha yako ya asili."}];function fp({intervalMs:S=3e3,onDismiss:f}){const[w,v]=Y.useState(0),[k,b]=Y.useState("in");Y.useEffect(()=>{const A=setInterval(()=>{b("out"),setTimeout(()=>{v(E=>(E+1)%Lr.length),b("in")},300)},S);return()=>clearInterval(A)},[S]);const I=Lr[w];return Q.jsxs("div",{className:"greeting-carousel",children:[Q.jsxs("div",{className:"greeting-carousel__content",children:[Q.jsx("div",{className:"greeting-carousel__icon",children:Q.jsxs("svg",{width:"48",height:"48",viewBox:"0 0 24 24",fill:"none",stroke:"currentColor",strokeWidth:"2",strokeLinecap:"round",strokeLinejoin:"round",children:[Q.jsx("path",{d:"M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"}),Q.jsx("path",{d:"M19 10v2a7 7 0 0 1-14 0v-2"}),Q.jsx("line",{x1:"12",x2:"12",y1:"19",y2:"22"})]})}),Q.jsxs("div",{className:`greeting-carousel__text greeting-carousel__text--${k}`,children:[Q.jsx("div",{className:"greeting-carousel__language",children:I.language}),Q.jsx("div",{className:"greeting-carousel__prompt",children:I.text})]},w),Q.jsx("div",{className:"greeting-carousel__progress",children:Lr.map((A,E)=>Q.jsx("div",{className:`greeting-carousel__dot ${E===w?"greeting-carousel__dot--active":""}`},E))})]}),f&&Q.jsx("button",{className:"greeting-carousel__dismiss",onClick:f,"aria-label":"Dismiss greeting prompt",children:"×"}),Q.jsx("style",{children:`
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
      `})]})}function eh({schema:S,sectionIndex:f,wsUrl:w,onClose:v,connectionManager:k,status:b,sharedStream:I,streamError:A}){const[E,X]=Y.useState(k||null),j=Y.useRef(k||null),[ee,ie]=Y.useState(b||"Ready"),[J,N]=Y.useState(null),[Z,H]=Y.useState(1),[te,M]=Y.useState(new Set),[B,D]=Y.useState({filled:0,total:12}),[q,V]=Y.useState(!1),[W,se]=Y.useState(!1),[we,ce]=Y.useState(!1),[ze,Ee]=Y.useState(!1),[Ie,Ke]=Y.useState(!1),Ne=Y.useRef(!1),Ye=Y.useRef(null),tt=Y.useRef(!1),Je=Y.useRef({x:0,y:0}),Me=Y.useRef(I||null),Ve=Y.useRef(null),Xe=Y.useRef(!1),dt=450;Y.useEffect(()=>{Me.current=I||null,console.log("[VoiceOverlay] 🔗 Using shared stream from parent:",!!I)},[I]);const ct=Y.useMemo(()=>({onSpeechStart:()=>{if(W)return;console.log("[VFF VAD] 🎤 User speech started - buffering audio..."),Ve.current=Date.now(),Xe.current=!1,ze&&(console.log("[VoiceOverlay] 🌍 User speaking - hiding greeting carousel"),Ee(!1),Ne.current=!0);const L=E?.getAudioManager();L&&L.setVADActive(!0),setTimeout(()=>{const K=Ve.current?Date.now()-Ve.current:0;Ve.current!==null&&K>=dt&&(console.log(`[VFF VAD] ✅ Valid speech detected (${K}ms) - triggering barge-in`),Xe.current=!0,E?.onVADSpeechStart())},dt)},onSpeechEnd:L=>{if(W)return;const K=Ve.current?Date.now()-Ve.current:0,he=E?.getAudioManager();he&&he.setVADActive(!1),Xe.current?(console.log(`[VFF VAD] ✅ Valid turn detected (${K}ms) - completing turn`),E?.onVADSpeechEnd()):console.log(`[VFF VAD] ⚠️ Turn too short (${K}ms < ${dt}ms) - no barge-in triggered, discarding`),Ve.current=null,Xe.current=!1},onVADMisfire:()=>{console.log("[VFF VAD] ⚠️ VAD misfire detected"),Ve.current=null}}),[W,E]),_t=Y.useMemo(()=>({sharedStream:Me.current,callbacks:ct}),[ct,I]),Re=pp(_t);Y.useEffect(()=>{if(k){j.current=k,X(k);return}if(j.current)return;const L=ve.initWithSections(S,f),K=Gr(L.schema,he=>{ie(he),N(null)},"English",I||void 0);return j.current=K,X(K),()=>{k||(j.current&&(j.current.disconnect(),j.current=null),X(null))}},[S,f,k]),Y.useEffect(()=>{b!==void 0&&ie(b)},[b]),Y.useEffect(()=>{const L=ee.toLowerCase()==="connected"||ee.toLowerCase().startsWith("connected ");L&&!Ne.current&&!ze&&(console.log("[VoiceOverlay] 🌍 Connection established - showing greeting carousel"),Ee(!0)),!L&&Ne.current&&(Ne.current=!1)},[ee,ze]),Y.useEffect(()=>{const K=(ee.toLowerCase()==="connected"||ee.toLowerCase().startsWith("connected "))&&!W&&!Re.loading&&!Re.errored;K&&!Re.userSpeaking?(console.log("[VoiceOverlay] 🎙️ Starting VAD (conditions met)"),Re.start()):!K&&Re.userSpeaking&&(console.log("[VoiceOverlay] ⏸️ Pausing VAD (conditions not met)"),Re.pause()),Re.errored&&N(`Voice detection error: ${Re.errored}`)},[ee,W,Re.loading,Re.errored,Re.userSpeaking,Re.start,Re.pause]),Y.useEffect(()=>(window.vffOnAudioPlaybackStart=()=>{ze&&(console.log("[VoiceOverlay] 🌍 Gemini speaking - hiding greeting carousel"),Ee(!1),Ne.current=!0)},()=>{delete window.vffOnAudioPlaybackStart}),[ze]);const st=async()=>{if(E)try{if(N(null),E.isPaused()){await E.resume();return}await E.connect();const L=5e3,K=Date.now();for(;Date.now()-K<L;){const ye=E.getStatus();if(ye==="connected"||ye==="switching_section"){console.log("[VoiceOverlay] ✅ Connection active, starting recording"),await E.startRecording();break}await new Promise(lt=>setTimeout(lt,50))}const he=E.getStatus();he!=="connected"&&he!=="switching_section"&&(console.error("[VoiceOverlay] ❌ Connection timeout, final status:",he),N("Connection timed out - please try again"))}catch(L){console.error("[VoiceOverlay] Connection error:",L),N(L instanceof Error?L.message:"Connection failed"),ie("Connection failed")}},Tt=()=>{E&&(E.pause(),Re.pause())},We=async()=>{if(!W||!(ee.toLowerCase()==="connected"||ee.toLowerCase().startsWith("connected ")||ee.toLowerCase()==="switching_section"||ee.toLowerCase().startsWith("reconnecting")))return;ce(!0);const K=E?.getAudioManager();K?.unmuteInput(),K?.isSpeaking()&&K.flushAudioQueue(),E?.sendActivityStart()},zt=()=>{if(!W||!(ee.toLowerCase()==="connected"||ee.toLowerCase().startsWith("connected ")||ee.toLowerCase()==="switching_section"||ee.toLowerCase().startsWith("reconnecting")))return;ce(!1),E?.getAudioManager()?.muteInput(),E?.sendActivityEnd()};Y.useEffect(()=>{if(!W)return;const L=ee.toLowerCase()==="connected"||ee.toLowerCase().startsWith("connected ")||ee.toLowerCase()==="switching_section"||ee.toLowerCase().startsWith("reconnecting"),K=ye=>{if(ye.code==="Space"){const Ce=ye.target;if(Ce.tagName==="INPUT"||Ce.tagName==="TEXTAREA")return;ye.preventDefault(),!ye.repeat&&L&&We()}},he=ye=>{if(ye.code==="Space"){const Ce=ye.target;if(Ce.tagName==="INPUT"||Ce.tagName==="TEXTAREA")return;ye.preventDefault(),L&&zt()}};return window.addEventListener("keydown",K),window.addEventListener("keyup",he),()=>{window.removeEventListener("keydown",K),window.removeEventListener("keyup",he)}},[W,ee]),Y.useEffect(()=>{const L=ve.initWithSections(S,f);H(L.current_section||1),M(L.completed_sections||new Set);const K=ve.getSectionFieldCount(L);D(K)},[S,f]),Y.useEffect(()=>{const L=setInterval(()=>{const K=ve.load();if(K){const he=ve.getSectionFieldCount(K);if(D(he),K.current_section&&K.current_section!==Z&&H(K.current_section),K.completed_sections){const ye=new Set(Array.from(te)),Ce=new Set(Array.from(K.completed_sections));(ye.size!==Ce.size||![...ye].every(lt=>Ce.has(lt)))&&M(Ce)}}},1e3);return()=>clearInterval(L)},[Z,te]);const at=()=>{if(!confirm(`⚠️ Clear all form data?

This will delete all fields and reload the page.
This action cannot be undone.`))return;ve.clear(),document.querySelectorAll("input, textarea, select").forEach(K=>{const he=K;if(he.tagName==="INPUT"){const ye=he;ye.type==="checkbox"||ye.type==="radio"?ye.checked=!1:ye.type!=="submit"&&ye.type!=="button"&&ye.type!=="hidden"&&(ye.value="")}else he.tagName==="TEXTAREA"?he.value="":he.tagName==="SELECT"&&(he.selectedIndex=0);he.removeAttribute("data-vff-confirmed"),he.style.outline="",he.style.outlineOffset=""}),document.querySelectorAll(".vff-field-badge").forEach(K=>K.remove()),window.location.reload()};Y.useEffect(()=>{const L=Ye.current;if(!L)return;const K=Ce=>{if(!Ce.target.closest(".vff-panel-header"))return;tt.current=!0;const wt=L.getBoundingClientRect();Je.current={x:Ce.clientX-wt.left,y:Ce.clientY-wt.top},Ce.preventDefault()},he=Ce=>{if(!tt.current)return;const lt=Ce.clientX-Je.current.x,wt=Ce.clientY-Je.current.y;L.style.left=`${lt}px`,L.style.top=`${wt}px`,L.style.right="auto"},ye=()=>{tt.current=!1};return L.addEventListener("mousedown",K),document.addEventListener("mousemove",he),document.addEventListener("mouseup",ye),()=>{L.removeEventListener("mousedown",K),document.removeEventListener("mousemove",he),document.removeEventListener("mouseup",ye)}},[]);const yt=ee.toLowerCase()==="connected"||ee.toLowerCase().startsWith("connected ")||ee.toLowerCase()==="switching_section"||ee.toLowerCase().startsWith("reconnecting"),Te=ee.toLowerCase()==="paused";return ee.toLowerCase().includes("warming"),ee.toLowerCase(),S.fields.length,S.fields.filter(L=>L.required).length,Q.jsxs(Q.Fragment,{children:[ze&&Q.jsx(fp,{intervalMs:3e3,onDismiss:()=>{console.log("[VoiceOverlay] 🌍 User dismissed greeting carousel"),Ee(!1),Ne.current=!0}}),Q.jsxs("div",{ref:Ye,className:`vff-panel ${Ie?"collapsed":""}`,children:[Q.jsxs("div",{className:"vff-panel-header",children:[Q.jsx("span",{className:"vff-title",children:"🎤 Voice Form Filler"}),Q.jsxs("div",{style:{display:"flex",gap:"8px"},children:[Q.jsx("button",{className:"vff-collapse",onClick:()=>Ke(!Ie),"aria-label":Ie?"Expand":"Collapse",children:Ie?"▼":"▲"}),v&&Q.jsx("button",{className:"vff-close",onClick:v,"aria-label":"Close",children:"×"})]})]}),Q.jsxs("div",{className:"vff-panel-body",children:[Q.jsxs("div",{className:"vff-status",children:[Q.jsx("span",{className:"vff-status-icon",children:yt?"🟢":"⚪"}),Q.jsx("span",{className:"vff-status-text",children:ee}),Re.userSpeaking&&!W&&Q.jsxs("span",{className:"vff-vad-indicator",title:"Voice detected",children:[Q.jsx("span",{className:"vff-vad-light"}),Q.jsx("span",{className:"vff-vad-label",children:"Listening"})]})]}),Q.jsxs("div",{className:"vff-section-nav",children:[Q.jsxs("div",{className:"vff-section-display",onClick:()=>V(!q),children:[Q.jsxs("span",{className:"vff-section-label",children:["Section ",Z," of ",f.total_sections,": ",f.sections[Z-1]?.section_label]}),Q.jsx("span",{className:"vff-dropdown-arrow",children:q?"▲":"▼"})]}),Q.jsxs("div",{className:"vff-field-counter",children:["📊 ",B.filled," of ",B.total," fields completed"]}),q&&Q.jsx("div",{className:"vff-section-dropdown",children:f.sections.map(L=>Q.jsxs("div",{className:`vff-section-item ${Z===L.section_number?"active":""}`,onClick:async()=>{if(E&&(V(!1),L.section_number!==Z))try{N(null),H(L.section_number),ie("Reconnecting to section "+L.section_number);const K=ve.load();if(K){const he=ve.switchSection(K,L.section_number),ye=ve.getSectionFieldCount(he);D(ye)}await E.switchSection(L.section_number)}catch(K){console.error("[VoiceOverlay] Section switch error:",K),N(K instanceof Error?K.message:"Section switch failed")}},children:[Q.jsx("span",{className:"vff-section-status",children:te.has(L.section_number)?"✓":Z===L.section_number?"→":"○"}),Q.jsxs("span",{className:"vff-section-text",children:[L.section_number,". ",L.section_label]})]},L.section_number))})]}),Q.jsxs("div",{className:"vff-controls",children:[!yt&&!Te?Q.jsx("button",{className:"vff-button vff-connect",onClick:st,children:"Connect to Voice"}):Te?Q.jsx("button",{className:"vff-button vff-resume",onClick:st,children:"▶️ Resume"}):Q.jsx("button",{className:"vff-button vff-pause",onClick:Tt,children:"⏸️ Pause"}),Q.jsx("button",{className:"vff-button vff-clear-form",onClick:at,children:"🗑️ Clear Form"})]}),(J||A)&&Q.jsxs("div",{className:"vff-error",children:[A&&Q.jsxs("div",{children:[Q.jsx("strong",{children:"🎤 Microphone Error:"})," ",A]}),J&&Q.jsx("div",{children:J})]})]}),Q.jsx("style",{children:`
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
			`})]})]})}function th({schema:S,sectionIndex:f,wsUrl:w,connectionManager:v,status:k,sharedStream:b,streamError:I}){const[A,E]=Y.useState(v||null),X=Y.useRef(v||null),[j,ee]=Y.useState(k||"Ready"),[ie,J]=Y.useState(null),[N,Z]=Y.useState(!1),[H,te]=Y.useState(1),[M,B]=Y.useState(new Set),[D,q]=Y.useState({filled:0,total:12}),[V,W]=Y.useState(!1),[se,we]=Y.useState(!1),[ce,ze]=Y.useState(!1),Ee=Y.useRef(!1),Ie=Y.useRef(b||null),Ke=Y.useRef(null),Ne=Y.useRef(!1),Ye=450;Y.useEffect(()=>{Ie.current=b||null,console.log("[VoiceOverlayMobile] 🔗 Using shared stream from parent:",!!b)},[b]);const tt=Y.useMemo(()=>({onSpeechStart:()=>{if(V)return;console.log("[VFF VAD] 🎤 User speech started - buffering audio..."),Ke.current=Date.now(),Ne.current=!1,ce&&(console.log("[VoiceOverlayMobile] 🌍 User speaking - hiding greeting carousel"),ze(!1),Ee.current=!0);const Te=A?.getAudioManager();Te&&Te.setVADActive(!0),setTimeout(()=>{const L=Ke.current?Date.now()-Ke.current:0;Ke.current!==null&&L>=Ye&&(console.log(`[VFF VAD] ✅ Valid speech detected (${L}ms) - triggering barge-in`),Ne.current=!0,A?.onVADSpeechStart())},Ye)},onSpeechEnd:Te=>{if(V)return;const L=Ke.current?Date.now()-Ke.current:0,K=A?.getAudioManager();K&&K.setVADActive(!1),Ne.current?(console.log(`[VFF VAD] ✅ Valid turn detected (${L}ms) - completing turn`),A?.onVADSpeechEnd()):console.log(`[VFF VAD] ⚠️ Turn too short (${L}ms < ${Ye}ms) - no barge-in triggered, discarding`),Ke.current=null,Ne.current=!1},onVADMisfire:()=>{console.log("[VFF VAD] ⚠️ VAD misfire detected"),Ke.current=null}}),[V,A]),Je=Y.useMemo(()=>({sharedStream:Ie.current,callbacks:tt}),[tt,b]),Me=pp(Je);Y.useEffect(()=>{if(v){X.current=v,E(v);return}if(X.current)return;const Te=ve.initWithSections(S,f),L=Gr(Te.schema,K=>{ee(K),J(null)},"English",b||void 0);return X.current=L,E(L),()=>{v||(X.current&&(X.current.disconnect(),X.current=null),E(null))}},[S,f,v]),Y.useEffect(()=>{k!==void 0&&ee(k)},[k]),Y.useEffect(()=>{const Te=j.toLowerCase()==="connected"||j.toLowerCase().startsWith("connected ");Te&&!Ee.current&&!ce&&(console.log("[VoiceOverlayMobile] 🌍 Connected - showing greeting carousel"),ze(!0)),!Te&&Ee.current&&(Ee.current=!1)},[j,ce]),Y.useEffect(()=>{const L=(j.toLowerCase()==="connected"||j.toLowerCase().startsWith("connected "))&&!V&&!Me.loading&&!Me.errored;L&&!Me.userSpeaking?(console.log("[VoiceOverlayMobile] 🎙️ Starting VAD (conditions met)"),Me.start()):!L&&Me.userSpeaking&&(console.log("[VoiceOverlayMobile] ⏸️ Pausing VAD (conditions not met)"),Me.pause()),Me.errored&&J(`Voice detection error: ${Me.errored}`)},[j,V,Me.loading,Me.errored,Me.userSpeaking,Me.start,Me.pause]),Y.useEffect(()=>(window.vffOnAudioPlaybackStart=()=>{ce&&(console.log("[VoiceOverlayMobile] 🌍 Gemini speaking - hiding greeting carousel"),ze(!1),Ee.current=!0)},()=>{delete window.vffOnAudioPlaybackStart}),[ce]);const Ve=async()=>{if(A)try{if(J(null),A.isPaused()){await A.resume();return}await A.connect();const Te=5e3,L=Date.now();for(;Date.now()-L<Te;){const he=A.getStatus();if(he==="connected"||he==="switching_section"){console.log("[VoiceOverlayMobile] ✅ Connection active, starting recording"),await A.startRecording();break}await new Promise(Ce=>setTimeout(Ce,50))}const K=A.getStatus();K!=="connected"&&K!=="switching_section"&&(console.error("[VoiceOverlayMobile] ❌ Connection timeout, final status:",K),J("Connection timed out - please try again"))}catch(Te){console.error("[VoiceOverlay] Connection error:",Te),J(Te instanceof Error?Te.message:"Connection failed")}},Xe=()=>{A&&(A.pause(),Me.pause())},dt=async()=>{const Te=!V;W(Te),A?.setPushToTalkMode(Te),j.toLowerCase()==="connected"||j.toLowerCase().startsWith("connected ")||j.toLowerCase()==="switching_section"||j.toLowerCase().startsWith("reconnecting"),Te?(Me.pause(),A?.getAudioManager()?.muteInput()):A?.getAudioManager()?.unmuteInput()},ct=async()=>{if(!V||!(j.toLowerCase()==="connected"||j.toLowerCase().startsWith("connected ")||j.toLowerCase()==="switching_section"||j.toLowerCase().startsWith("reconnecting")))return;we(!0);const L=A?.getAudioManager();L?.unmuteInput(),L?.isSpeaking()&&L.flushAudioQueue(),A?.sendActivityStart()},_t=()=>{if(!V||!(j.toLowerCase()==="connected"||j.toLowerCase().startsWith("connected ")||j.toLowerCase()==="switching_section"||j.toLowerCase().startsWith("reconnecting")))return;we(!1),A?.getAudioManager()?.muteInput(),A?.sendActivityEnd()};Y.useEffect(()=>{const Te=ve.initWithSections(S,f);te(Te.current_section||1),B(Te.completed_sections||new Set);const L=ve.getSectionFieldCount(Te);q(L)},[S,f]),Y.useEffect(()=>{const Te=setInterval(()=>{const L=ve.load();if(L){const K=ve.getSectionFieldCount(L);q(K)}},1e3);return()=>clearInterval(Te)},[]);const Re=j.toLowerCase()==="connected"||j.toLowerCase().startsWith("connected "),st=j.toLowerCase()==="paused",Tt=j.toLowerCase().includes("warming"),We=j.toLowerCase()==="ready",zt=S.fields.length,at=S.fields.filter(Te=>Te.required).length,yt=Re?"#10b981":st||Tt?"#f59e0b":We?"#3b82f6":"#6b7280";return Q.jsxs(Q.Fragment,{children:[ce&&Q.jsx(fp,{intervalMs:3e3,onDismiss:()=>{console.log("[VoiceOverlayMobile] 🌍 User dismissed greeting carousel"),ze(!1),Ee.current=!0}}),Q.jsxs("div",{className:"vff-fab",onClick:()=>Z(!N),children:[Q.jsx("div",{className:"vff-fab-pulse",style:{borderColor:yt}}),Me.userSpeaking&&!V&&Q.jsx("div",{className:"vff-fab-vad-badge",children:Q.jsx("div",{className:"vff-fab-vad-dot"})}),Q.jsx("div",{className:"vff-fab-icon",style:{background:yt},children:"🎤"})]}),N&&Q.jsxs("div",{className:"vff-panel-mobile",children:[Q.jsxs("div",{className:"vff-panel-header",children:[Q.jsx("span",{className:"vff-title",children:"Voice Form Filler"}),Q.jsx("button",{className:"vff-close",onClick:()=>Z(!1),children:"×"})]}),Q.jsxs("div",{className:"vff-panel-body",children:[Q.jsxs("div",{className:"vff-status-compact",children:[Q.jsx("div",{className:"vff-status-dot",style:{background:yt}}),Q.jsx("span",{className:"vff-status-text",children:j})]}),(Re||st)&&Q.jsx("div",{className:"vff-ptt-toggle-mobile",children:Q.jsxs("div",{className:"vff-toggle-label-row",children:[Q.jsx("span",{className:"vff-toggle-mode-label",children:"🎤 Auto"}),Q.jsxs("label",{className:"vff-toggle-switch",children:[Q.jsx("input",{type:"checkbox",checked:V,onChange:dt,onKeyDown:Te=>{Te.code==="Space"&&Te.preventDefault()}}),Q.jsx("span",{className:"vff-toggle-slider"})]}),Q.jsx("span",{className:"vff-toggle-mode-label",children:"⌨️ PTT"})]})}),"						",V&&Re&&Q.jsx("button",{className:`vff-action-btn vff-ptt-btn ${se?"active":""}`,onTouchStart:ct,onTouchEnd:_t,onMouseDown:ct,onMouseUp:_t,onMouseLeave:_t,children:se?"🔴 Speaking...":"⚫ Hold to Speak"}),!Re&&!st?Q.jsx("button",{className:"vff-action-btn vff-connect-btn",onClick:Ve,children:"🎙️ Connect"}):st?Q.jsx("button",{className:"vff-action-btn vff-resume-btn",onClick:Ve,children:"▶️ Resume"}):Q.jsx("button",{className:"vff-action-btn vff-pause-btn",onClick:Xe,children:"⏸️ Pause"}),(ie||I)&&Q.jsxs("div",{className:"vff-error-compact",children:[I&&Q.jsxs("div",{children:[Q.jsx("strong",{children:"🎤 Mic Error:"})," ",I]}),ie&&Q.jsx("div",{children:ie})]}),Q.jsxs("div",{className:"vff-info-compact",children:[zt," fields · ",at," required"]})]})]}),Q.jsx("style",{children:`
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
			`})]})}function ih(){const S=Y.useRef(null),[f,w]=Y.useState(null),[v,k]=Y.useState(null),[b,I]=Y.useState(!1),[A,E]=Y.useState(!1),[X,j]=Y.useState(!1),[ee,ie]=Y.useState(null),J=Y.useRef(null),[N,Z]=Y.useState("Ready"),[H,te]=Y.useState(null),[M,B]=Y.useState(null),[D,q]=Y.useState(!1);Y.useEffect(()=>{const W=()=>{E(window.innerWidth<=768)};return W(),window.addEventListener("resize",W),()=>window.removeEventListener("resize",W)},[]),Y.useEffect(()=>{let W=!0;async function se(){try{console.log("[AdultIntakeDemo] 🎤 Creating shared audio stream early...");const we=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:!0,noiseSuppression:!0,autoGainControl:!0,channelCount:1,sampleRate:16e3}});W?(te(we),q(!0),console.log("[AdultIntakeDemo] ✅ Shared stream ready (AEC enabled)")):we.getTracks().forEach(ce=>ce.stop())}catch(we){if(console.error("[AdultIntakeDemo] ❌ Failed to create shared stream:",we),W){const ce=we instanceof Error?we.message:"Microphone access denied";B(ce),q(!0)}}}return se(),()=>{W=!1,H&&(console.log("[AdultIntakeDemo] 🧹 Cleaning up shared stream"),H.getTracks().forEach(we=>we.stop()))}},[]),Y.useEffect(()=>{const W=se=>{if(X)return;const we=document.querySelectorAll("input, textarea, select");let ce=!1;for(const ze of we){const Ee=ze;if(Ee.tagName==="INPUT"){const Ie=Ee;Ie.type==="checkbox"||Ie.type==="radio"?Ie.checked&&(ce=!0):Ie.type!=="submit"&&Ie.type!=="button"&&Ie.type!=="hidden"&&Ie.value.trim()&&(ce=!0)}else Ee.tagName==="TEXTAREA"?Ee.value.trim()&&(ce=!0):Ee.tagName==="SELECT"&&Ee.selectedIndex>0&&(ce=!0);if(ce)break}ce&&(se.preventDefault(),se.returnValue="")};return window.addEventListener("beforeunload",W),()=>window.removeEventListener("beforeunload",W)},[b,X]),Y.useEffect(()=>{(async()=>{try{const we=await(await fetch("./adult_intake_demo.html")).text(),ze=new DOMParser().parseFromString(we,"text/html"),Ee=ze.querySelector("style")?.textContent||"",Ie=ze.querySelector(".clinic-header")?.outerHTML||"",Ke=ze.querySelector(".form-container")?.outerHTML||"";if(S.current){const Me=document.createElement("style");Me.textContent=Ee,document.head.appendChild(Me),S.current.innerHTML=Ie+Ke,I(!0)}const Ye=await(await fetch("./adult_intake_demo_schema.json")).json();Ye.form_metadata.url=window.location.href;const Je=await(await fetch("./adult_intake_sections_index.json")).json();w(Ye),k(Je),setTimeout(()=>{const Me=document.querySelector("form");Me&&(Me.addEventListener("submit",Ve=>(Ve.preventDefault(),j(!0),window.location.href="thank-you.html",!1)),Me.addEventListener("keydown",Ve=>{if(Ve.key==="Enter"){const Xe=Ve.target;(Xe.tagName==="INPUT"||Xe.tagName==="TEXTAREA")&&(Ve.preventDefault(),Xe.blur())}}))},100)}catch(se){console.error("Failed to load form, schema, or section index:",se)}})()},[]),Y.useEffect(()=>{if(!f||!v||!D||J.current)return;const W=ve.initWithSections(f,v),se=Gr(W.schema,we=>{Z(we)},"English",H||void 0);return J.current=se,ie(se),()=>{J.current&&(J.current.disconnect(),J.current=null),ie(null)}},[f,v,D,H]);const V="wss://voice-form-filler-773443099751.us-central1.run.app/ws/fill";return Q.jsxs("div",{className:"demo-container",children:[Q.jsx("div",{ref:S,className:"form-content"}),b&&f&&v&&ee&&D&&(A?Q.jsx(th,{schema:f,sectionIndex:v,wsUrl:V,connectionManager:ee,sharedStream:H,streamError:M,status:N}):Q.jsx(eh,{schema:f,sectionIndex:v,wsUrl:V,connectionManager:ee,status:N,sharedStream:H,streamError:M}))]})}Ur.createRoot(document.getElementById("root")).render(Q.jsx(ih,{}));
