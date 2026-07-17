/**
 * CONNECTION_TIMEOUT_TRANSLATIONS - copy for the connection-timeout modal.
 *
 * The modal appears when the voice connection drops in a way the app cannot
 * silently auto-recover from, and offers a "reconnect" button that resumes the
 * session where the user left off (the restore engine already exists; see the
 * jf6w epic). The copy must render in the language the user chose at form start,
 * so this mirrors the DisclaimerModal house pattern: an inline per-language map
 * keyed by the SPOKEN_LANGUAGES `name` (frontend/src/shared/languages.ts), with
 * a fallback to English for any unknown key.
 *
 * Keys:
 * - title:              short headline ("Connection Timed Out")
 * - message:            one-sentence explanation + reassurance that progress is kept
 * - reconnectButton:    primary action label
 * - cancelButton:       secondary action label (dismiss / stay on the form)
 * - reconnectingTitle:  headline for the TRANSIENT auto-reconnect state (bd
 *                       polyglot-pdf-ppfy) -- shown while the app is silently
 *                       reconnecting after a spontaneous AI-session drop (e.g. a
 *                       Gemini 1011). No button; it auto-clears on recovery.
 * - reconnectingMessage: reassurance shown during that transient reconnect.
 *
 * NOTE (bd polyglot-pdf-jf6w.1): the non-English strings are a first machine-
 * generated draft and should be reviewed by a native/fluent speaker before they
 * ship to real users -- an immigration intake context is unforgiving of a
 * mistranslated recovery prompt. English is authoritative until then.
 */

export interface ConnectionTimeoutCopy {
  title: string;
  message: string;
  reconnectButton: string;
  cancelButton: string;
  reconnectingTitle: string;
  reconnectingMessage: string;
}

export const CONNECTION_TIMEOUT_TRANSLATIONS: Record<string, ConnectionTimeoutCopy> = {
  'English': {
    title: 'Connection Timed Out',
    message: 'The connection was lost. Your progress is saved. Click below to reconnect and continue where you left off.',
    reconnectButton: 'Reconnect',
    cancelButton: 'Not Now',
    reconnectingTitle: 'Reconnecting...',
    reconnectingMessage: 'Please wait -- we are having trouble reaching the AI assistant. Your progress is saved and we will reconnect you automatically.',
  },
  'Spanish': {
    title: 'Se Agotó el Tiempo de Conexión',
    message: 'Se perdió la conexión. Su progreso está guardado. Haga clic abajo para reconectarse y continuar donde lo dejó.',
    reconnectButton: 'Reconectar',
    cancelButton: 'Ahora No',
    reconnectingTitle: 'Reconectando...',
    reconnectingMessage: 'Por favor espere: estamos teniendo problemas para conectar con el asistente de IA. Su progreso está guardado y lo reconectaremos automaticamente.',
  },
  'Chinese': {
    title: '连接已超时',
    message: '连接已断开。您的进度已保存。点击下方重新连接，从您离开的地方继续。',
    reconnectButton: '重新连接',
    cancelButton: '暂不',
    reconnectingTitle: '正在重新连接...',
    reconnectingMessage: '请稍候 -- 我们暂时无法连接到 AI 助手。您的进度已保存，我们会自动为您重新连接。',
  },
  'Tagalog': {
    title: 'Nag-time Out ang Koneksyon',
    message: 'Nawala ang koneksyon. Naka-save ang iyong progreso. I-click sa ibaba para kumonekta muli at magpatuloy kung saan ka tumigil.',
    reconnectButton: 'Kumonekta Muli',
    cancelButton: 'Hindi Ngayon',
    reconnectingTitle: 'Kumokonekta Muli...',
    reconnectingMessage: 'Mangyaring maghintay -- nahihirapan kaming maabot ang AI assistant. Naka-save ang iyong progreso at awtomatiko ka naming ikokonekta muli.',
  },
  'Arabic': {
    title: 'انتهت مهلة الاتصال',
    message: 'تم فقدان الاتصال. تم حفظ تقدمك. انقر أدناه لإعادة الاتصال ومتابعة ما توقفت عنده.',
    reconnectButton: 'إعادة الاتصال',
    cancelButton: 'ليس الآن',
    reconnectingTitle: 'جارٍ إعادة الاتصال...',
    reconnectingMessage: 'يرجى الانتظار -- نواجه مشكلة في الوصول إلى المساعد الذكي. تم حفظ تقدمك وسنعيد الاتصال تلقائيًا.',
  },
  'French': {
    title: 'Délai de Connexion Dépassé',
    message: 'La connexion a été perdue. Votre progression est enregistrée. Cliquez ci-dessous pour vous reconnecter et continuer où vous en étiez.',
    reconnectButton: 'Se Reconnecter',
    cancelButton: 'Pas Maintenant',
    reconnectingTitle: 'Reconnexion...',
    reconnectingMessage: 'Veuillez patienter -- nous avons des difficultes a joindre l\'assistant IA. Votre progression est enregistree et nous vous reconnecterons automatiquement.',
  },
  'Korean': {
    title: '연결 시간 초과',
    message: '연결이 끊어졌습니다. 진행 상황은 저장되었습니다. 아래를 클릭하여 다시 연결하고 중단한 곳에서 계속하세요.',
    reconnectButton: '다시 연결',
    cancelButton: '나중에',
    reconnectingTitle: '다시 연결 중...',
    reconnectingMessage: '잠시만 기다려 주세요 -- AI 어시스턴트에 연결하는 데 문제가 있습니다. 진행 상황은 저장되었으며 자동으로 다시 연결됩니다.',
  },
  'German': {
    title: 'Verbindung Unterbrochen',
    message: 'Die Verbindung wurde unterbrochen. Ihr Fortschritt ist gespeichert. Klicken Sie unten, um die Verbindung wiederherzustellen und dort fortzufahren, wo Sie aufgehört haben.',
    reconnectButton: 'Erneut Verbinden',
    cancelButton: 'Jetzt Nicht',
    reconnectingTitle: 'Verbindung wird wiederhergestellt...',
    reconnectingMessage: 'Bitte warten -- wir haben Probleme, den KI-Assistenten zu erreichen. Ihr Fortschritt ist gespeichert und wir verbinden Sie automatisch wieder.',
  },
  'Portuguese': {
    title: 'Tempo de Conexão Esgotado',
    message: 'A conexão foi perdida. Seu progresso está salvo. Clique abaixo para reconectar e continuar de onde parou.',
    reconnectButton: 'Reconectar',
    cancelButton: 'Agora Não',
    reconnectingTitle: 'Reconectando...',
    reconnectingMessage: 'Aguarde -- estamos com dificuldade para conectar ao assistente de IA. Seu progresso esta salvo e vamos reconectar voce automaticamente.',
  },
  'Hindi': {
    title: 'कनेक्शन समय समाप्त',
    message: 'कनेक्शन टूट गया। आपकी प्रगति सहेजी गई है। फिर से कनेक्ट करने और जहां आपने छोड़ा था वहां जारी रखने के लिए नीचे क्लिक करें।',
    reconnectButton: 'फिर से कनेक्ट करें',
    cancelButton: 'अभी नहीं',
    reconnectingTitle: 'फिर से कनेक्ट हो रहा है...',
    reconnectingMessage: 'कृपया प्रतीक्षा करें -- हमें AI सहायक तक पहुंचने में समस्या हो रही है। आपकी प्रगति सहेजी गई है और हम आपको स्वचालित रूप से फिर से कनेक्ट कर देंगे।',
  },
  'Italian': {
    title: 'Connessione Scaduta',
    message: 'La connessione è stata persa. I tuoi progressi sono salvati. Clicca qui sotto per riconnetterti e continuare da dove avevi lasciato.',
    reconnectButton: 'Riconnetti',
    cancelButton: 'Non Ora',
    reconnectingTitle: 'Riconnessione...',
    reconnectingMessage: 'Attendere prego -- stiamo riscontrando problemi a raggiungere l\'assistente IA. I tuoi progressi sono salvati e ti riconnetteremo automaticamente.',
  },
  'Urdu': {
    title: 'کنکشن کا وقت ختم',
    message: 'کنکشن منقطع ہو گیا۔ آپ کی پیش رفت محفوظ ہے۔ دوبارہ منسلک ہونے اور جہاں آپ نے چھوڑا تھا وہاں سے جاری رکھنے کے لیے نیچے کلک کریں۔',
    reconnectButton: 'دوبارہ منسلک کریں',
    cancelButton: 'ابھی نہیں',
    reconnectingTitle: 'دوبارہ منسلک ہو رہا ہے...',
    reconnectingMessage: 'براہ کرم انتظار کریں -- ہمیں AI اسسٹنٹ تک پہنچنے میں دشواری ہو رہی ہے۔ آپ کی پیش رفت محفوظ ہے اور ہم آپ کو خودکار طور پر دوبارہ منسلک کر دیں گے۔',
  },
  'Persian': {
    title: 'مهلت اتصال به پایان رسید',
    message: 'اتصال قطع شد. پیشرفت شما ذخیره شده است. برای اتصال مجدد و ادامه از جایی که متوقف شدید، روی دکمه زیر کلیک کنید.',
    reconnectButton: 'اتصال مجدد',
    cancelButton: 'الان نه',
    reconnectingTitle: 'در حال اتصال مجدد...',
    reconnectingMessage: 'لطفا صبر کنید -- در برقراری ارتباط با دستیار هوش مصنوعی مشکل داریم. پیشرفت شما ذخیره شده است و به طور خودکار شما را دوباره متصل می‌کنیم.',
  },
  'Dutch': {
    title: 'Verbinding Verlopen',
    message: 'De verbinding is verbroken. Uw voortgang is opgeslagen. Klik hieronder om opnieuw verbinding te maken en verder te gaan waar u was gebleven.',
    reconnectButton: 'Opnieuw Verbinden',
    cancelButton: 'Niet Nu',
    reconnectingTitle: 'Opnieuw verbinden...',
    reconnectingMessage: 'Even geduld -- we hebben moeite om de AI-assistent te bereiken. Uw voortgang is opgeslagen en we verbinden u automatisch opnieuw.',
  },
  'Ukrainian': {
    title: 'Час Очікування Зʼєднання Вичерпано',
    message: 'Зʼєднання втрачено. Ваш прогрес збережено. Натисніть нижче, щоб повторно підключитися та продовжити з того місця, де ви зупинилися.',
    reconnectButton: 'Підключитися Знову',
    cancelButton: 'Не Зараз',
    reconnectingTitle: 'Повторне підключення...',
    reconnectingMessage: 'Будь ласка, зачекайте -- у нас виникли труднощі зі звʼязком з AI-помічником. Ваш прогрес збережено, і ми автоматично підключимо вас знову.',
  },
  'Swedish': {
    title: 'Anslutningen Tog Slut',
    message: 'Anslutningen förlorades. Dina framsteg är sparade. Klicka nedan för att återansluta och fortsätta där du slutade.',
    reconnectButton: 'Återanslut',
    cancelButton: 'Inte Nu',
    reconnectingTitle: 'Återansluter...',
    reconnectingMessage: 'Vänligen vänta -- vi har problem att nå AI-assistenten. Dina framsteg är sparade och vi återansluter dig automatiskt.',
  },
  'Afrikaans': {
    title: 'Verbinding Het Uitgetel',
    message: 'Die verbinding is verloor. Jou vordering is gestoor. Klik hieronder om weer te verbind en voort te gaan waar jy opgehou het.',
    reconnectButton: 'Herverbind',
    cancelButton: 'Nie Nou Nie',
    reconnectingTitle: 'Herverbind tans...',
    reconnectingMessage: 'Wag asseblief -- ons het probleme om die KI-assistent te bereik. Jou vordering is gestoor en ons sal jou outomaties herverbind.',
  },
};
