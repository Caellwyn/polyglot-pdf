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
 * - budgetExhaustedTitle / budgetExhaustedMessage (bd polyglot-pdf-cke6v): the
 *   link's SPEND CEILING is used up. Terminal and NOT recoverable, so this
 *   variant offers no button -- the copy's whole job is to say what happened
 *   and what still works (typing, download, print, save; all true because
 *   retrieval never redeems the link).
 *
 *   ALL 18 rows -- English included -- are lifted from resumeStrings.ts's
 *   voiceEnding pair, which carries this message in the same languages and has
 *   already been through the kit translation pipeline. Reusing reviewed copy
 *   beats inventing 18 drafts in an immigration-intake context.
 *
 *   English is NOT authored separately here, deliberately (Opus cross-surface
 *   r1). It was, and it diverged: it said "your answers are safe" while the 17
 *   translations said "save now so you do not lose your answers" -- opposite
 *   instructions to clients in the same state -- and only English named the
 *   cause and the new-link remedy. One string could not be fixed by
 *   translating the richer English into 17 languages without machine-
 *   translating an immigration-intake message, so English moved instead.
 *
 *   WHAT THIS COPY STILL DOES NOT SAY: that the SPEND CEILING is the cause, or
 *   that the firm can issue a new link. Both are real losses and both need a
 *   copy+translation pass, not an English-only edit -- bd polyglot-pdf-7cy2f.
 *   The title also still reads "is finishing" for a state that has already
 *   finished; same bead.
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
  budgetExhaustedTitle: string;
  budgetExhaustedMessage: string;
}

export const CONNECTION_TIMEOUT_TRANSLATIONS: Record<string, ConnectionTimeoutCopy> = {
  'English': {
    title: 'Connection Timed Out',
    message: 'The connection was lost. Your progress is saved. Click below to reconnect and continue where you left off.',
    reconnectButton: 'Reconnect',
    cancelButton: 'Not Now',
    reconnectingTitle: 'Reconnecting...',
    reconnectingMessage: 'Please wait -- we are having trouble reaching the AI assistant. Your progress is saved and we will reconnect you automatically.',
    budgetExhaustedTitle: 'The voice assistant is finishing',
    budgetExhaustedMessage: 'Save your form now so you do not lose your answers. You can still type your remaining answers, and you can still download and print your form.',
  },
  'Spanish': {
    title: 'Se Agotó el Tiempo de Conexión',
    message: 'Se perdió la conexión. Su progreso está guardado. Haga clic abajo para reconectarse y continuar donde lo dejó.',
    reconnectButton: 'Reconectar',
    cancelButton: 'Ahora No',
    reconnectingTitle: 'Reconectando...',
    reconnectingMessage: 'Por favor espere: estamos teniendo problemas para conectar con el asistente de IA. Su progreso está guardado y lo reconectaremos automaticamente.',
    budgetExhaustedTitle: 'El asistente de voz esta terminando',
    budgetExhaustedMessage: 'Guarde su formulario ahora para no perder sus respuestas. Todavia puede escribir las respuestas que faltan, y todavia puede descargar e imprimir su formulario.',
  },
  'Chinese': {
    title: '连接已超时',
    message: '连接已断开。您的进度已保存。点击下方重新连接，从您离开的地方继续。',
    reconnectButton: '重新连接',
    cancelButton: '暂不',
    reconnectingTitle: '正在重新连接...',
    reconnectingMessage: '请稍候 -- 我们暂时无法连接到 AI 助手。您的进度已保存，我们会自动为您重新连接。',
    budgetExhaustedTitle: '语音助手即将结束',
    budgetExhaustedMessage: '请立即保存表格，以免丢失您的答案。您仍然可以输入其余答案，也仍然可以下载和打印表格。',
  },
  'Tagalog': {
    title: 'Nag-time Out ang Koneksyon',
    message: 'Nawala ang koneksyon. Naka-save ang iyong progreso. I-click sa ibaba para kumonekta muli at magpatuloy kung saan ka tumigil.',
    reconnectButton: 'Kumonekta Muli',
    cancelButton: 'Hindi Ngayon',
    reconnectingTitle: 'Kumokonekta Muli...',
    reconnectingMessage: 'Mangyaring maghintay -- nahihirapan kaming maabot ang AI assistant. Naka-save ang iyong progreso at awtomatiko ka naming ikokonekta muli.',
    budgetExhaustedTitle: 'Natatapos na ang voice assistant',
    budgetExhaustedMessage: 'I-save ang inyong form ngayon para hindi mawala ang inyong mga sagot. Maaari pa rin kayong mag-type ng natitirang sagot, at maaari pa rin kayong mag-download at mag-print ng inyong form.',
  },
  'Arabic': {
    title: 'انتهت مهلة الاتصال',
    message: 'تم فقدان الاتصال. تم حفظ تقدمك. انقر أدناه لإعادة الاتصال ومتابعة ما توقفت عنده.',
    reconnectButton: 'إعادة الاتصال',
    cancelButton: 'ليس الآن',
    reconnectingTitle: 'جارٍ إعادة الاتصال...',
    reconnectingMessage: 'يرجى الانتظار -- نواجه مشكلة في الوصول إلى المساعد الذكي. تم حفظ تقدمك وسنعيد الاتصال تلقائيًا.',
    budgetExhaustedTitle: 'المساعد الصوتي على وشك الانتهاء',
    budgetExhaustedMessage: 'احفظ استمارتك الآن حتى لا تفقد إجاباتك. لا يزال بإمكانك كتابة الإجابات المتبقية، ولا يزال بإمكانك تنزيل استمارتك وطباعتها.',
  },
  'French': {
    title: 'Délai de Connexion Dépassé',
    message: 'La connexion a été perdue. Votre progression est enregistrée. Cliquez ci-dessous pour vous reconnecter et continuer où vous en étiez.',
    reconnectButton: 'Se Reconnecter',
    cancelButton: 'Pas Maintenant',
    reconnectingTitle: 'Reconnexion...',
    reconnectingMessage: 'Veuillez patienter -- nous avons des difficultes a joindre l\'assistant IA. Votre progression est enregistree et nous vous reconnecterons automatiquement.',
    budgetExhaustedTitle: 'L assistant vocal se termine',
    budgetExhaustedMessage: 'Enregistrez votre formulaire maintenant pour ne pas perdre vos reponses. Vous pouvez toujours saisir les reponses restantes, et vous pouvez toujours telecharger et imprimer votre formulaire.',
  },
  'Korean': {
    title: '연결 시간 초과',
    message: '연결이 끊어졌습니다. 진행 상황은 저장되었습니다. 아래를 클릭하여 다시 연결하고 중단한 곳에서 계속하세요.',
    reconnectButton: '다시 연결',
    cancelButton: '나중에',
    reconnectingTitle: '다시 연결 중...',
    reconnectingMessage: '잠시만 기다려 주세요 -- AI 어시스턴트에 연결하는 데 문제가 있습니다. 진행 상황은 저장되었으며 자동으로 다시 연결됩니다.',
    budgetExhaustedTitle: '음성 도우미가 종료됩니다',
    budgetExhaustedMessage: '답변을 잃지 않도록 지금 양식을 저장하세요. 남은 답변은 직접 입력할 수 있으며, 양식을 다운로드하고 인쇄하는 것도 계속 가능합니다.',
  },
  'German': {
    title: 'Verbindung Unterbrochen',
    message: 'Die Verbindung wurde unterbrochen. Ihr Fortschritt ist gespeichert. Klicken Sie unten, um die Verbindung wiederherzustellen und dort fortzufahren, wo Sie aufgehört haben.',
    reconnectButton: 'Erneut Verbinden',
    cancelButton: 'Jetzt Nicht',
    reconnectingTitle: 'Verbindung wird wiederhergestellt...',
    reconnectingMessage: 'Bitte warten -- wir haben Probleme, den KI-Assistenten zu erreichen. Ihr Fortschritt ist gespeichert und wir verbinden Sie automatisch wieder.',
    budgetExhaustedTitle: 'Der Sprachassistent wird beendet',
    budgetExhaustedMessage: 'Speichern Sie Ihr Formular jetzt, damit Ihre Antworten nicht verloren gehen. Sie koennen die restlichen Antworten weiterhin eingeben und Ihr Formular weiterhin herunterladen und drucken.',
  },
  'Portuguese': {
    title: 'Tempo de Conexão Esgotado',
    message: 'A conexão foi perdida. Seu progresso está salvo. Clique abaixo para reconectar e continuar de onde parou.',
    reconnectButton: 'Reconectar',
    cancelButton: 'Agora Não',
    reconnectingTitle: 'Reconectando...',
    reconnectingMessage: 'Aguarde -- estamos com dificuldade para conectar ao assistente de IA. Seu progresso esta salvo e vamos reconectar voce automaticamente.',
    budgetExhaustedTitle: 'O assistente de voz esta terminando',
    budgetExhaustedMessage: 'Salve seu formulario agora para nao perder suas respostas. Voce ainda pode digitar as respostas restantes e ainda pode baixar e imprimir seu formulario.',
  },
  'Hindi': {
    title: 'कनेक्शन समय समाप्त',
    message: 'कनेक्शन टूट गया। आपकी प्रगति सहेजी गई है। फिर से कनेक्ट करने और जहां आपने छोड़ा था वहां जारी रखने के लिए नीचे क्लिक करें।',
    reconnectButton: 'फिर से कनेक्ट करें',
    cancelButton: 'अभी नहीं',
    reconnectingTitle: 'फिर से कनेक्ट हो रहा है...',
    reconnectingMessage: 'कृपया प्रतीक्षा करें -- हमें AI सहायक तक पहुंचने में समस्या हो रही है। आपकी प्रगति सहेजी गई है और हम आपको स्वचालित रूप से फिर से कनेक्ट कर देंगे।',
    budgetExhaustedTitle: 'वॉइस सहायक समाप्त हो रहा है',
    budgetExhaustedMessage: 'अपने उत्तर खोने से बचने के लिए अभी अपना फॉर्म सहेजें। आप शेष उत्तर टाइप कर सकते हैं, और अपना फॉर्म डाउनलोड और प्रिंट भी कर सकते हैं।',
  },
  'Italian': {
    title: 'Connessione Scaduta',
    message: 'La connessione è stata persa. I tuoi progressi sono salvati. Clicca qui sotto per riconnetterti e continuare da dove avevi lasciato.',
    reconnectButton: 'Riconnetti',
    cancelButton: 'Non Ora',
    reconnectingTitle: 'Riconnessione...',
    reconnectingMessage: 'Attendere prego -- stiamo riscontrando problemi a raggiungere l\'assistente IA. I tuoi progressi sono salvati e ti riconnetteremo automaticamente.',
    budgetExhaustedTitle: 'L assistente vocale sta terminando',
    budgetExhaustedMessage: 'Salva ora il modulo per non perdere le tue risposte. Puoi ancora digitare le risposte rimanenti e puoi ancora scaricare e stampare il modulo.',
  },
  'Urdu': {
    title: 'کنکشن کا وقت ختم',
    message: 'کنکشن منقطع ہو گیا۔ آپ کی پیش رفت محفوظ ہے۔ دوبارہ منسلک ہونے اور جہاں آپ نے چھوڑا تھا وہاں سے جاری رکھنے کے لیے نیچے کلک کریں۔',
    reconnectButton: 'دوبارہ منسلک کریں',
    cancelButton: 'ابھی نہیں',
    reconnectingTitle: 'دوبارہ منسلک ہو رہا ہے...',
    reconnectingMessage: 'براہ کرم انتظار کریں -- ہمیں AI اسسٹنٹ تک پہنچنے میں دشواری ہو رہی ہے۔ آپ کی پیش رفت محفوظ ہے اور ہم آپ کو خودکار طور پر دوبارہ منسلک کر دیں گے۔',
    budgetExhaustedTitle: 'صوتی معاون ختم ہو رہا ہے',
    budgetExhaustedMessage: 'اپنے جوابات ضائع ہونے سے بچانے کے لیے ابھی اپنا فارم محفوظ کریں۔ آپ باقی جوابات ٹائپ کر سکتے ہیں، اور اپنا فارم ڈاؤن لوڈ اور پرنٹ بھی کر سکتے ہیں۔',
  },
  'Persian': {
    title: 'مهلت اتصال به پایان رسید',
    message: 'اتصال قطع شد. پیشرفت شما ذخیره شده است. برای اتصال مجدد و ادامه از جایی که متوقف شدید، روی دکمه زیر کلیک کنید.',
    reconnectButton: 'اتصال مجدد',
    cancelButton: 'الان نه',
    reconnectingTitle: 'در حال اتصال مجدد...',
    reconnectingMessage: 'لطفا صبر کنید -- در برقراری ارتباط با دستیار هوش مصنوعی مشکل داریم. پیشرفت شما ذخیره شده است و به طور خودکار شما را دوباره متصل می‌کنیم.',
    budgetExhaustedTitle: 'دستیار صوتی در حال پایان است',
    budgetExhaustedMessage: 'اکنون فرم خود را ذخیره کنید تا پاسخ‌هایتان از بین نرود. همچنان می‌توانید پاسخ‌های باقی‌مانده را تایپ کنید و فرم خود را دانلود و چاپ کنید.',
  },
  'Dutch': {
    title: 'Verbinding Verlopen',
    message: 'De verbinding is verbroken. Uw voortgang is opgeslagen. Klik hieronder om opnieuw verbinding te maken en verder te gaan waar u was gebleven.',
    reconnectButton: 'Opnieuw Verbinden',
    cancelButton: 'Niet Nu',
    reconnectingTitle: 'Opnieuw verbinden...',
    reconnectingMessage: 'Even geduld -- we hebben moeite om de AI-assistent te bereiken. Uw voortgang is opgeslagen en we verbinden u automatisch opnieuw.',
    budgetExhaustedTitle: 'De spraakassistent stopt',
    budgetExhaustedMessage: 'Sla uw formulier nu op zodat u uw antwoorden niet kwijtraakt. U kunt de resterende antwoorden nog typen en u kunt uw formulier nog downloaden en afdrukken.',
  },
  'Ukrainian': {
    title: 'Час Очікування Зʼєднання Вичерпано',
    message: 'Зʼєднання втрачено. Ваш прогрес збережено. Натисніть нижче, щоб повторно підключитися та продовжити з того місця, де ви зупинилися.',
    reconnectButton: 'Підключитися Знову',
    cancelButton: 'Не Зараз',
    reconnectingTitle: 'Повторне підключення...',
    reconnectingMessage: 'Будь ласка, зачекайте -- у нас виникли труднощі зі звʼязком з AI-помічником. Ваш прогрес збережено, і ми автоматично підключимо вас знову.',
    budgetExhaustedTitle: 'Голосовий помічник завершує роботу',
    budgetExhaustedMessage: 'Збережіть форму зараз, щоб не втратити відповіді. Ви все ще можете вписати решту відповідей, а також завантажити та роздрукувати форму.',
  },
  'Russian': {
    title: 'Время Ожидания Соединения Истекло',
    message: 'Соединение потеряно. Ваш прогресс сохранён. Нажмите ниже, чтобы переподключиться и продолжить с того места, где вы остановились.',
    reconnectButton: 'Подключиться Снова',
    cancelButton: 'Не Сейчас',
    reconnectingTitle: 'Переподключение...',
    reconnectingMessage: 'Пожалуйста, подождите -- у нас возникли трудности со связью с ИИ-помощником. Ваш прогресс сохранён, и мы автоматически подключим вас снова.',
    budgetExhaustedTitle: 'Голосовой помощник завершает работу',
    budgetExhaustedMessage: 'Сохраните форму сейчас, чтобы не потерять ответы. Вы по-прежнему можете вписать оставшиеся ответы, а также скачать и распечатать форму.',
  },
  'Swedish': {
    title: 'Anslutningen Tog Slut',
    message: 'Anslutningen förlorades. Dina framsteg är sparade. Klicka nedan för att återansluta och fortsätta där du slutade.',
    reconnectButton: 'Återanslut',
    cancelButton: 'Inte Nu',
    reconnectingTitle: 'Återansluter...',
    reconnectingMessage: 'Vänligen vänta -- vi har problem att nå AI-assistenten. Dina framsteg är sparade och vi återansluter dig automatiskt.',
    budgetExhaustedTitle: 'Rostassistenten avslutas',
    budgetExhaustedMessage: 'Spara ditt formular nu sa att du inte forlorar dina svar. Du kan fortfarande skriva in de svar som aterstar, och du kan fortfarande ladda ner och skriva ut ditt formular.',
  },
  'Afrikaans': {
    title: 'Verbinding Het Uitgetel',
    message: 'Die verbinding is verloor. Jou vordering is gestoor. Klik hieronder om weer te verbind en voort te gaan waar jy opgehou het.',
    reconnectButton: 'Herverbind',
    cancelButton: 'Nie Nou Nie',
    reconnectingTitle: 'Herverbind tans...',
    reconnectingMessage: 'Wag asseblief -- ons het probleme om die KI-assistent te bereik. Jou vordering is gestoor en ons sal jou outomaties herverbind.',
    budgetExhaustedTitle: 'Die stemassistent is besig om te eindig',
    budgetExhaustedMessage: 'Stoor jou vorm nou sodat jy nie jou antwoorde verloor nie. Jy kan steeds die oorblywende antwoorde intik, en jy kan steeds jou vorm aflaai en druk.',
  },
};
