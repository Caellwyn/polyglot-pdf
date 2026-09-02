/**
 * OVERLAY_TRANSLATIONS - UI copy for the voice-overlay control panel.
 *
 * The overlay panel (Hold to Talk, Pause/Resume/Reconnect, Clear Form, the
 * input-mode toggle, the field counter, the clear-form confirm dialog) was
 * hardcoded English, so a Spanish-session user saw an all-English control box
 * (bd polyglot-pdf-ibxz, tester bug 3, 2026-07-15). This mirrors the
 * DisclaimerModal / connectionTimeoutTranslations house pattern: an inline
 * per-language map keyed by the SPOKEN_LANGUAGES `name`
 * (frontend/src/shared/languages.ts), falling back to English for unknown keys.
 *
 * Used by BOTH frontend/src/demo/VoiceOverlay.tsx and VoiceOverlayMobile.tsx
 * (the overlays are deliberate near-duplicates; translate via this one module).
 *
 * `fieldsCompleted` is a template with {filled} and {total} placeholders --
 * render it through formatFieldsCompleted() so word order stays free per
 * language.
 *
 * NOTE (same caveat as bd polyglot-pdf-jf6w.1): the non-English strings are a
 * first machine-generated draft and should be reviewed by a native/fluent
 * speaker before real users rely on them. English is authoritative until then.
 */

export interface OverlayStrings {
  holdToTalk: string;       // PTT button, idle state, desktop (icon added in JSX)
  tapHoldToTalk: string;    // PTT button, idle state, mobile (no spacebar hint)
  recording: string;        // PTT button, held state
  reconnect: string;
  resume: string;
  pause: string;
  // Manual/voice mode toggle (bd polyglot-pdf-wurj8). Action-labelled like
  // pause/resume above -- each string is what the click SWITCHES TO, so only
  // one is ever shown. Keep them short: narrow control box.
  switchToManual: string;  // shown while in VOICE mode
  switchToVoice: string;   // shown while in MANUAL mode
  clearForm: string;
  clearFormConfirm: string; // confirm() dialog body
  fieldsCompleted: string;  // template: {filled} / {total}
  fieldsRequiredInfo: string; // mobile info line template: {count} / {required}
  micErrorLabel: string;    // prefix for stream errors
}

export const OVERLAY_TRANSLATIONS: Record<string, OverlayStrings> = {
  'English': {
    holdToTalk: 'Hold to Talk (or Spacebar)',
    tapHoldToTalk: 'Tap & Hold to Talk',
    recording: 'Recording...',
    reconnect: 'Reconnect',
    resume: 'Resume',
    pause: 'Pause',
    switchToManual: 'Quiet Mode',
    switchToVoice: 'Voice Mode',
    clearForm: 'Clear Form',
    clearFormConfirm: 'Clear all form data?\n\nThis will delete all fields and reload the page.\nThis action cannot be undone.',
    fieldsCompleted: '{filled} of {total} fields completed',
    fieldsRequiredInfo: '{count} fields · {required} required',
    micErrorLabel: 'Microphone Error:',
  },
  'Spanish': {
    holdToTalk: 'Mantenga presionado para hablar (o barra espaciadora)',
    tapHoldToTalk: 'Mantenga presionado para hablar',
    recording: 'Grabando...',
    reconnect: 'Reconectar',
    resume: 'Reanudar',
    pause: 'Pausar',
    switchToManual: 'Modo silencio',
    switchToVoice: 'Modo de voz',
    clearForm: 'Borrar formulario',
    clearFormConfirm: '¿Borrar todos los datos del formulario?\n\nEsto eliminará todos los campos y recargará la página.\nEsta acción no se puede deshacer.',
    fieldsCompleted: '{filled} de {total} campos completados',
    fieldsRequiredInfo: '{count} campos · {required} obligatorios',
    micErrorLabel: 'Error de micrófono:',
  },
  'Chinese': {
    holdToTalk: '按住说话（或空格键）',
    tapHoldToTalk: '按住说话',
    recording: '录音中...',
    reconnect: '重新连接',
    resume: '继续',
    pause: '暂停',
    switchToManual: '静音模式',
    switchToVoice: '语音模式',
    clearForm: '清除表格',
    clearFormConfirm: '清除所有表格数据？\n\n这将删除所有字段并重新加载页面。\n此操作无法撤销。',
    fieldsCompleted: '已完成 {filled} / {total} 个字段',
    fieldsRequiredInfo: '{count} 个字段 · {required} 个必填',
    micErrorLabel: '麦克风错误：',
  },
  'Tagalog': {
    holdToTalk: 'Pindutin nang matagal para magsalita (o Spacebar)',
    tapHoldToTalk: 'Pindutin nang matagal para magsalita',
    recording: 'Nagre-record...',
    reconnect: 'Kumonekta Muli',
    resume: 'Ituloy',
    pause: 'I-pause',
    switchToManual: 'Tahimik na Mode',
    switchToVoice: 'Voice Mode',
    clearForm: 'Burahin ang Form',
    clearFormConfirm: 'Burahin ang lahat ng datos ng form?\n\nBubura nito ang lahat ng field at ire-reload ang pahina.\nHindi na ito maibabalik.',
    fieldsCompleted: '{filled} sa {total} na field ang tapos na',
    fieldsRequiredInfo: '{count} field · {required} kailangan',
    micErrorLabel: 'Error sa Mikropono:',
  },
  'Arabic': {
    holdToTalk: 'اضغط مع الاستمرار للتحدث (أو مفتاح المسافة)',
    tapHoldToTalk: 'اضغط مع الاستمرار للتحدث',
    recording: 'جارٍ التسجيل...',
    reconnect: 'إعادة الاتصال',
    resume: 'استئناف',
    pause: 'إيقاف مؤقت',
    switchToManual: 'الوضع الصامت',
    switchToVoice: 'الوضع الصوتي',
    clearForm: 'مسح النموذج',
    clearFormConfirm: 'هل تريد مسح جميع بيانات النموذج؟\n\nسيؤدي هذا إلى حذف جميع الحقول وإعادة تحميل الصفحة.\nلا يمكن التراجع عن هذا الإجراء.',
    fieldsCompleted: 'اكتمل {filled} من {total} حقول',
    fieldsRequiredInfo: '{count} حقول · {required} مطلوبة',
    micErrorLabel: 'خطأ في الميكروفون:',
  },
  'French': {
    holdToTalk: "Maintenez pour parler (ou barre d'espace)",
    tapHoldToTalk: 'Appuyez et maintenez pour parler',
    recording: 'Enregistrement...',
    reconnect: 'Reconnecter',
    resume: 'Reprendre',
    pause: 'Pause',
    switchToManual: 'Mode silencieux',
    switchToVoice: 'Mode vocal',
    clearForm: 'Effacer le formulaire',
    clearFormConfirm: 'Effacer toutes les données du formulaire ?\n\nCela supprimera tous les champs et rechargera la page.\nCette action est irréversible.',
    fieldsCompleted: '{filled} champs remplis sur {total}',
    fieldsRequiredInfo: '{count} champs · {required} obligatoires',
    micErrorLabel: 'Erreur de microphone :',
  },
  'Korean': {
    holdToTalk: '누른 채로 말하기 (또는 스페이스바)',
    tapHoldToTalk: '길게 눌러 말하기',
    recording: '녹음 중...',
    reconnect: '다시 연결',
    resume: '계속하기',
    pause: '일시정지',
    switchToManual: '조용한 모드',
    switchToVoice: '음성 모드',
    clearForm: '양식 지우기',
    clearFormConfirm: '모든 양식 데이터를 지우시겠습니까?\n\n모든 필드가 삭제되고 페이지가 새로고침됩니다.\n이 작업은 되돌릴 수 없습니다.',
    fieldsCompleted: '{total}개 중 {filled}개 필드 완료',
    fieldsRequiredInfo: '필드 {count}개 · 필수 {required}개',
    micErrorLabel: '마이크 오류:',
  },
  'German': {
    holdToTalk: 'Zum Sprechen gedrückt halten (oder Leertaste)',
    tapHoldToTalk: 'Zum Sprechen gedrückt halten',
    recording: 'Aufnahme...',
    reconnect: 'Neu verbinden',
    resume: 'Fortsetzen',
    pause: 'Pause',
    switchToManual: 'Stiller Modus',
    switchToVoice: 'Sprachmodus',
    clearForm: 'Formular löschen',
    clearFormConfirm: 'Alle Formulardaten löschen?\n\nDadurch werden alle Felder gelöscht und die Seite neu geladen.\nDiese Aktion kann nicht rückgängig gemacht werden.',
    fieldsCompleted: '{filled} von {total} Feldern ausgefüllt',
    fieldsRequiredInfo: '{count} Felder · {required} erforderlich',
    micErrorLabel: 'Mikrofonfehler:',
  },
  'Portuguese': {
    holdToTalk: 'Segure para falar (ou barra de espaço)',
    tapHoldToTalk: 'Toque e segure para falar',
    recording: 'Gravando...',
    reconnect: 'Reconectar',
    resume: 'Retomar',
    pause: 'Pausar',
    switchToManual: 'Modo silencioso',
    switchToVoice: 'Modo de voz',
    clearForm: 'Limpar formulário',
    clearFormConfirm: 'Limpar todos os dados do formulário?\n\nIsso excluirá todos os campos e recarregará a página.\nEsta ação não pode ser desfeita.',
    fieldsCompleted: '{filled} de {total} campos preenchidos',
    fieldsRequiredInfo: '{count} campos · {required} obrigatórios',
    micErrorLabel: 'Erro de microfone:',
  },
  'Hindi': {
    holdToTalk: 'बोलने के लिए दबाए रखें (या स्पेसबार)',
    tapHoldToTalk: 'बोलने के लिए दबाकर रखें',
    recording: 'रिकॉर्डिंग...',
    reconnect: 'फिर से कनेक्ट करें',
    resume: 'जारी रखें',
    pause: 'रोकें',
    switchToManual: 'शांत मोड',
    switchToVoice: 'वॉइस मोड',
    clearForm: 'फ़ॉर्म साफ़ करें',
    clearFormConfirm: 'फ़ॉर्म का सारा डेटा साफ़ करें?\n\nइससे सभी फ़ील्ड हट जाएँगे और पेज फिर से लोड होगा।\nयह क्रिया पूर्ववत नहीं की जा सकती।',
    fieldsCompleted: '{total} में से {filled} फ़ील्ड पूरे हुए',
    fieldsRequiredInfo: '{count} फ़ील्ड · {required} आवश्यक',
    micErrorLabel: 'माइक्रोफ़ोन त्रुटि:',
  },
  'Italian': {
    holdToTalk: 'Tieni premuto per parlare (o barra spaziatrice)',
    tapHoldToTalk: 'Tieni premuto per parlare',
    recording: 'Registrazione...',
    reconnect: 'Riconnetti',
    resume: 'Riprendi',
    pause: 'Pausa',
    switchToManual: 'Modalità silenziosa',
    switchToVoice: 'Modalità vocale',
    clearForm: 'Cancella modulo',
    clearFormConfirm: 'Cancellare tutti i dati del modulo?\n\nQuesto eliminerà tutti i campi e ricaricherà la pagina.\nQuesta azione non può essere annullata.',
    fieldsCompleted: '{filled} campi completati su {total}',
    fieldsRequiredInfo: '{count} campi · {required} obbligatori',
    micErrorLabel: 'Errore del microfono:',
  },
  'Urdu': {
    holdToTalk: 'بولنے کے لیے دبائے رکھیں (یا اسپیس بار)',
    tapHoldToTalk: 'بولنے کے لیے دبائے رکھیں',
    recording: 'ریکارڈنگ جاری ہے...',
    reconnect: 'دوبارہ جڑیں',
    resume: 'جاری رکھیں',
    pause: 'روکیں',
    switchToManual: 'خاموش موڈ',
    switchToVoice: 'صوتی موڈ',
    clearForm: 'فارم صاف کریں',
    clearFormConfirm: 'فارم کا تمام ڈیٹا صاف کریں؟\n\nاس سے تمام خانے حذف ہو جائیں گے اور صفحہ دوبارہ لوڈ ہوگا۔\nیہ عمل واپس نہیں ہو سکتا۔',
    fieldsCompleted: '{total} میں سے {filled} خانے مکمل',
    fieldsRequiredInfo: '{count} خانے · {required} لازمی',
    micErrorLabel: 'مائیکروفون کی خرابی:',
  },
  'Persian': {
    holdToTalk: 'برای صحبت نگه دارید (یا کلید فاصله)',
    tapHoldToTalk: 'برای صحبت نگه دارید',
    recording: 'در حال ضبط...',
    reconnect: 'اتصال مجدد',
    resume: 'ادامه',
    pause: 'توقف',
    switchToManual: 'حالت بی‌صدا',
    switchToVoice: 'حالت صوتی',
    clearForm: 'پاک کردن فرم',
    clearFormConfirm: 'همه داده‌های فرم پاک شود؟\n\nاین کار همه فیلدها را حذف و صفحه را دوباره بارگذاری می‌کند.\nاین عمل قابل بازگشت نیست.',
    fieldsCompleted: '{filled} از {total} فیلد تکمیل شد',
    fieldsRequiredInfo: '{count} فیلد · {required} الزامی',
    micErrorLabel: 'خطای میکروفون:',
  },
  'Dutch': {
    holdToTalk: 'Ingedrukt houden om te spreken (of spatiebalk)',
    tapHoldToTalk: 'Houd ingedrukt om te spreken',
    recording: 'Opnemen...',
    reconnect: 'Opnieuw verbinden',
    resume: 'Hervatten',
    pause: 'Pauzeren',
    switchToManual: 'Stille modus',
    switchToVoice: 'Spraakmodus',
    clearForm: 'Formulier wissen',
    clearFormConfirm: 'Alle formuliergegevens wissen?\n\nDit verwijdert alle velden en herlaadt de pagina.\nDeze actie kan niet ongedaan worden gemaakt.',
    fieldsCompleted: '{filled} van {total} velden ingevuld',
    fieldsRequiredInfo: '{count} velden · {required} verplicht',
    micErrorLabel: 'Microfoonfout:',
  },
  'Ukrainian': {
    holdToTalk: 'Утримуйте, щоб говорити (або пробіл)',
    tapHoldToTalk: 'Натисніть і утримуйте, щоб говорити',
    recording: 'Запис...',
    reconnect: 'Повторне підключення',
    resume: 'Продовжити',
    pause: 'Пауза',
    switchToManual: 'Тихий режим',
    switchToVoice: 'Голосовий режим',
    clearForm: 'Очистити форму',
    clearFormConfirm: 'Очистити всі дані форми?\n\nЦе видалить усі поля та перезавантажить сторінку.\nЦю дію неможливо скасувати.',
    fieldsCompleted: 'Заповнено {filled} з {total} полів',
    fieldsRequiredInfo: "{count} полів · {required} обов'язкових",
    micErrorLabel: 'Помилка мікрофона:',
  },
  'Russian': {
    holdToTalk: 'Удерживайте, чтобы говорить (или пробел)',
    tapHoldToTalk: 'Нажмите и удерживайте, чтобы говорить',
    recording: 'Запись...',
    reconnect: 'Переподключиться',
    resume: 'Продолжить',
    pause: 'Пауза',
    switchToManual: 'Тихий режим',
    switchToVoice: 'Голосовой режим',
    clearForm: 'Очистить форму',
    clearFormConfirm: 'Очистить все данные формы?\n\nЭто удалит все поля и перезагрузит страницу.\nЭто действие нельзя отменить.',
    fieldsCompleted: 'Заполнено {filled} из {total} полей',
    fieldsRequiredInfo: '{count} полей · {required} обязательных',
    micErrorLabel: 'Ошибка микрофона:',
  },
  'Swedish': {
    holdToTalk: 'Håll ned för att tala (eller mellanslag)',
    tapHoldToTalk: 'Håll ned för att tala',
    recording: 'Spelar in...',
    reconnect: 'Återanslut',
    resume: 'Fortsätt',
    pause: 'Paus',
    switchToManual: 'Tyst läge',
    switchToVoice: 'Röstläge',
    clearForm: 'Rensa formulär',
    clearFormConfirm: 'Rensa alla formulärdata?\n\nDetta raderar alla fält och laddar om sidan.\nÅtgärden kan inte ångras.',
    fieldsCompleted: '{filled} av {total} fält ifyllda',
    fieldsRequiredInfo: '{count} fält · {required} obligatoriska',
    micErrorLabel: 'Mikrofonfel:',
  },
  'Afrikaans': {
    holdToTalk: 'Hou in om te praat (of spasiebalk)',
    tapHoldToTalk: 'Hou in om te praat',
    recording: 'Neem op...',
    reconnect: 'Herkoppel',
    resume: 'Hervat',
    pause: 'Onderbreek',
    switchToManual: 'Stil modus',
    switchToVoice: 'Stemmodus',
    clearForm: 'Vee vorm uit',
    clearFormConfirm: 'Vee alle vormdata uit?\n\nDit sal alle velde uitvee en die bladsy herlaai.\nHierdie aksie kan nie ontdoen word nie.',
    fieldsCompleted: '{filled} van {total} velde voltooi',
    fieldsRequiredInfo: '{count} velde · {required} verplig',
    micErrorLabel: 'Mikrofoonfout:',
  },
};

/** Resolve the overlay strings for a spoken-language name, English fallback. */
export function getOverlayStrings(language: string | null | undefined): OverlayStrings {
  return OVERLAY_TRANSLATIONS[language || ''] || OVERLAY_TRANSLATIONS['English'];
}

/** Render the fieldsCompleted template with its {filled}/{total} placeholders. */
export function formatFieldsCompleted(
  strings: OverlayStrings, filled: number, total: number
): string {
  return strings.fieldsCompleted
    .replace('{filled}', String(filled))
    .replace('{total}', String(total));
}
