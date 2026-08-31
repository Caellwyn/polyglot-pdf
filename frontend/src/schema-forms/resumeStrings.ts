/**
 * Client-facing text for saving and resuming a form (bd polyglot-pdf-dft1).
 *
 * Follows the shape DisclaimerModal already uses: a Record keyed by the
 * language NAME the app selects, with an English fallback. That is where
 * translators already look, and a second mechanism would fragment the work.
 *
 * NEVER PIN THE LANGUAGE LIST. 18 today, growing toward ~90. Anything reading
 * these maps must fall back to English rather than assume a key exists, and
 * nothing may enumerate "the supported languages" from here.
 *
 * WHY THESE STRINGS EXIST. A client who closes the tab -- or steps away past
 * the 60-minute state expiry -- loses every answer today. Saving the PDF is
 * the recovery, so the prompt to save has to reach a client who is working by
 * voice in their own language, not just an English reader watching the screen.
 */

export interface ResumeStrings {
  /** The early, one-time nudge after the first section is done. */
  saveNudgeTitle: string;
  saveNudgeBody: string;
  saveNudgeAction: string;
  saveNudgeDismiss: string;

  /** The stronger prompt when the voice assistant is ending. */
  voiceEndingTitle: string;
  voiceEndingBody: string;

  /** The start-over / resume choice, and the upload control. */
  resumeTitle: string;
  resumeBody: string;
  resumeAction: string;
  startOverAction: string;
  dropHere: string;

  /** Outcomes of an upload. */
  resumeMismatch: string;
  resumeUnreadable: string;
  resumeSuccess: string;
}

const EN: ResumeStrings = {
  saveNudgeTitle: 'Save your form so you can come back to it',
  saveNudgeBody:
    'Save this form to your device now. If you close this page or stop for a while, you can open the saved file later and continue where you left off. Nothing is stored on our servers.',
  saveNudgeAction: 'Save my form',
  saveNudgeDismiss: 'Not now',

  voiceEndingTitle: 'The voice assistant is finishing',
  voiceEndingBody:
    'Save your form now so you do not lose your answers. You can still type your remaining answers, and you can still download and print your form.',

  resumeTitle: 'Continue a saved form',
  resumeBody:
    'If you saved this form before, open the saved file here and your answers will come back.',
  resumeAction: 'Continue my saved form',
  startOverAction: 'Start over',
  dropHere: 'Drop your saved PDF here, or choose a file',

  resumeMismatch:
    'That file does not match the form you were sent. Please choose the file you saved from this form.',
  resumeUnreadable:
    'We could not read that file. Please choose the PDF you saved from this form.',
  resumeSuccess: 'Your answers are back. You can carry on where you stopped.',
};

/**
 * Translations. English is the fallback for any language absent here, which is
 * how a newly-supported language degrades gracefully rather than rendering
 * blank text.
 */
export const RESUME_TRANSLATIONS: Record<string, ResumeStrings> = {
  English: EN,

  Spanish: {
    saveNudgeTitle: 'Guarde su formulario para poder volver a el',
    saveNudgeBody:
      'Guarde este formulario en su dispositivo ahora. Si cierra esta pagina o se detiene por un tiempo, puede abrir el archivo guardado mas tarde y continuar donde lo dejo. No se guarda nada en nuestros servidores.',
    saveNudgeAction: 'Guardar mi formulario',
    saveNudgeDismiss: 'Ahora no',
    voiceEndingTitle: 'El asistente de voz esta terminando',
    voiceEndingBody:
      'Guarde su formulario ahora para no perder sus respuestas. Todavia puede escribir las respuestas que faltan, y todavia puede descargar e imprimir su formulario.',
    resumeTitle: 'Continuar un formulario guardado',
    resumeBody:
      'Si guardo este formulario antes, abra el archivo guardado aqui y sus respuestas volveran.',
    resumeAction: 'Continuar mi formulario guardado',
    startOverAction: 'Empezar de nuevo',
    dropHere: 'Suelte aqui su PDF guardado, o elija un archivo',
    resumeMismatch:
      'Ese archivo no coincide con el formulario que le enviaron. Por favor elija el archivo que guardo de este formulario.',
    resumeUnreadable:
      'No pudimos leer ese archivo. Por favor elija el PDF que guardo de este formulario.',
    resumeSuccess: 'Sus respuestas han vuelto. Puede continuar donde se detuvo.',
  },

  Chinese: {
    saveNudgeTitle: '保存您的表格以便稍后继续',
    saveNudgeBody:
      '请立即将此表格保存到您的设备。如果您关闭此页面或暂停一段时间，稍后可以打开保存的文件，从中断的地方继续。我们的服务器不会存储任何内容。',
    saveNudgeAction: '保存我的表格',
    saveNudgeDismiss: '暂不',
    voiceEndingTitle: '语音助手即将结束',
    voiceEndingBody:
      '请立即保存表格，以免丢失您的答案。您仍然可以输入其余答案，也仍然可以下载和打印表格。',
    resumeTitle: '继续已保存的表格',
    resumeBody: '如果您之前保存过此表格，请在此打开保存的文件，您的答案将会恢复。',
    resumeAction: '继续我保存的表格',
    startOverAction: '重新开始',
    dropHere: '将保存的 PDF 拖放到此处，或选择文件',
    resumeMismatch: '该文件与发送给您的表格不符。请选择您从此表格保存的文件。',
    resumeUnreadable: '我们无法读取该文件。请选择您从此表格保存的 PDF。',
    resumeSuccess: '您的答案已恢复。您可以从停止的地方继续。',
  },

  Tagalog: {
    saveNudgeTitle: 'I-save ang inyong form para makabalik kayo dito',
    saveNudgeBody:
      'I-save ang form na ito sa inyong device ngayon. Kung isasara ninyo ang pahinang ito o titigil kayo saglit, mabubuksan ninyo ang na-save na file mamaya at maipagpapatuloy kung saan kayo tumigil. Walang naka-imbak sa aming mga server.',
    saveNudgeAction: 'I-save ang aking form',
    saveNudgeDismiss: 'Hindi ngayon',
    voiceEndingTitle: 'Natatapos na ang voice assistant',
    voiceEndingBody:
      'I-save ang inyong form ngayon para hindi mawala ang inyong mga sagot. Maaari pa rin kayong mag-type ng natitirang sagot, at maaari pa rin kayong mag-download at mag-print ng inyong form.',
    resumeTitle: 'Ipagpatuloy ang na-save na form',
    resumeBody:
      'Kung na-save ninyo ang form na ito dati, buksan ang na-save na file dito at babalik ang inyong mga sagot.',
    resumeAction: 'Ipagpatuloy ang aking na-save na form',
    startOverAction: 'Magsimula muli',
    dropHere: 'Ilagay dito ang na-save ninyong PDF, o pumili ng file',
    resumeMismatch:
      'Hindi tugma ang file na iyon sa form na ipinadala sa inyo. Pakipili ang file na na-save ninyo mula sa form na ito.',
    resumeUnreadable:
      'Hindi namin nabasa ang file na iyon. Pakipili ang PDF na na-save ninyo mula sa form na ito.',
    resumeSuccess: 'Bumalik na ang inyong mga sagot. Maaari na kayong magpatuloy.',
  },

  Arabic: {
    saveNudgeTitle: 'احفظ استمارتك حتى تتمكن من العودة إليها',
    saveNudgeBody:
      'احفظ هذه الاستمارة على جهازك الآن. إذا أغلقت هذه الصفحة أو توقفت لفترة، يمكنك فتح الملف المحفوظ لاحقاً ومتابعة ما توقفت عنده. لا يتم تخزين أي شيء على خوادمنا.',
    saveNudgeAction: 'احفظ استمارتي',
    saveNudgeDismiss: 'ليس الآن',
    voiceEndingTitle: 'المساعد الصوتي على وشك الانتهاء',
    voiceEndingBody:
      'احفظ استمارتك الآن حتى لا تفقد إجاباتك. لا يزال بإمكانك كتابة الإجابات المتبقية، ولا يزال بإمكانك تنزيل استمارتك وطباعتها.',
    resumeTitle: 'متابعة استمارة محفوظة',
    resumeBody:
      'إذا كنت قد حفظت هذه الاستمارة من قبل، افتح الملف المحفوظ هنا وستعود إجاباتك.',
    resumeAction: 'متابعة استمارتي المحفوظة',
    startOverAction: 'البدء من جديد',
    dropHere: 'أفلت ملف PDF المحفوظ هنا، أو اختر ملفاً',
    resumeMismatch:
      'هذا الملف لا يطابق الاستمارة التي أُرسلت إليك. يرجى اختيار الملف الذي حفظته من هذه الاستمارة.',
    resumeUnreadable:
      'لم نتمكن من قراءة هذا الملف. يرجى اختيار ملف PDF الذي حفظته من هذه الاستمارة.',
    resumeSuccess: 'عادت إجاباتك. يمكنك المتابعة من حيث توقفت.',
  },

  French: {
    saveNudgeTitle: 'Enregistrez votre formulaire pour pouvoir y revenir',
    saveNudgeBody:
      'Enregistrez ce formulaire sur votre appareil maintenant. Si vous fermez cette page ou vous arretez un moment, vous pourrez ouvrir le fichier enregistre plus tard et reprendre la ou vous en etiez. Rien n est conserve sur nos serveurs.',
    saveNudgeAction: 'Enregistrer mon formulaire',
    saveNudgeDismiss: 'Pas maintenant',
    voiceEndingTitle: 'L assistant vocal se termine',
    voiceEndingBody:
      'Enregistrez votre formulaire maintenant pour ne pas perdre vos reponses. Vous pouvez toujours saisir les reponses restantes, et vous pouvez toujours telecharger et imprimer votre formulaire.',
    resumeTitle: 'Continuer un formulaire enregistre',
    resumeBody:
      'Si vous avez deja enregistre ce formulaire, ouvrez le fichier enregistre ici et vos reponses reviendront.',
    resumeAction: 'Continuer mon formulaire enregistre',
    startOverAction: 'Recommencer',
    dropHere: 'Deposez ici votre PDF enregistre, ou choisissez un fichier',
    resumeMismatch:
      'Ce fichier ne correspond pas au formulaire qui vous a ete envoye. Veuillez choisir le fichier que vous avez enregistre depuis ce formulaire.',
    resumeUnreadable:
      'Nous n avons pas pu lire ce fichier. Veuillez choisir le PDF que vous avez enregistre depuis ce formulaire.',
    resumeSuccess: 'Vos reponses sont revenues. Vous pouvez reprendre ou vous vous etiez arrete.',
  },

  Korean: {
    saveNudgeTitle: '나중에 돌아올 수 있도록 양식을 저장하세요',
    saveNudgeBody:
      '지금 이 양식을 기기에 저장하세요. 이 페이지를 닫거나 잠시 중단하더라도 나중에 저장한 파일을 열어 중단한 곳부터 계속할 수 있습니다. 저희 서버에는 아무것도 저장되지 않습니다.',
    saveNudgeAction: '내 양식 저장',
    saveNudgeDismiss: '나중에',
    voiceEndingTitle: '음성 도우미가 종료됩니다',
    voiceEndingBody:
      '답변을 잃지 않도록 지금 양식을 저장하세요. 남은 답변은 직접 입력할 수 있으며, 양식을 다운로드하고 인쇄하는 것도 계속 가능합니다.',
    resumeTitle: '저장한 양식 계속하기',
    resumeBody: '이전에 이 양식을 저장하셨다면 여기에서 저장한 파일을 여세요. 답변이 복원됩니다.',
    resumeAction: '저장한 양식 계속하기',
    startOverAction: '처음부터 다시',
    dropHere: '저장한 PDF를 여기에 놓거나 파일을 선택하세요',
    resumeMismatch:
      '해당 파일은 받으신 양식과 일치하지 않습니다. 이 양식에서 저장한 파일을 선택해 주세요.',
    resumeUnreadable:
      '해당 파일을 읽을 수 없습니다. 이 양식에서 저장한 PDF를 선택해 주세요.',
    resumeSuccess: '답변이 복원되었습니다. 중단한 곳부터 계속하실 수 있습니다.',
  },

  German: {
    saveNudgeTitle: 'Speichern Sie Ihr Formular, um spater zurueckzukehren',
    saveNudgeBody:
      'Speichern Sie dieses Formular jetzt auf Ihrem Geraet. Wenn Sie diese Seite schliessen oder eine Pause machen, koennen Sie die gespeicherte Datei spaeter oeffnen und dort weitermachen, wo Sie aufgehoert haben. Auf unseren Servern wird nichts gespeichert.',
    saveNudgeAction: 'Mein Formular speichern',
    saveNudgeDismiss: 'Jetzt nicht',
    voiceEndingTitle: 'Der Sprachassistent wird beendet',
    voiceEndingBody:
      'Speichern Sie Ihr Formular jetzt, damit Ihre Antworten nicht verloren gehen. Sie koennen die restlichen Antworten weiterhin eingeben und Ihr Formular weiterhin herunterladen und drucken.',
    resumeTitle: 'Gespeichertes Formular fortsetzen',
    resumeBody:
      'Wenn Sie dieses Formular zuvor gespeichert haben, oeffnen Sie die gespeicherte Datei hier, und Ihre Antworten kommen zurueck.',
    resumeAction: 'Mein gespeichertes Formular fortsetzen',
    startOverAction: 'Neu beginnen',
    dropHere: 'Legen Sie Ihre gespeicherte PDF hier ab oder waehlen Sie eine Datei',
    resumeMismatch:
      'Diese Datei entspricht nicht dem Formular, das Ihnen gesendet wurde. Bitte waehlen Sie die Datei, die Sie aus diesem Formular gespeichert haben.',
    resumeUnreadable:
      'Wir konnten diese Datei nicht lesen. Bitte waehlen Sie die PDF, die Sie aus diesem Formular gespeichert haben.',
    resumeSuccess: 'Ihre Antworten sind zurueck. Sie koennen dort weitermachen, wo Sie aufgehoert haben.',
  },

  Portuguese: {
    saveNudgeTitle: 'Salve seu formulario para poder voltar a ele',
    saveNudgeBody:
      'Salve este formulario no seu dispositivo agora. Se voce fechar esta pagina ou parar por um tempo, podera abrir o arquivo salvo mais tarde e continuar de onde parou. Nada fica armazenado em nossos servidores.',
    saveNudgeAction: 'Salvar meu formulario',
    saveNudgeDismiss: 'Agora nao',
    voiceEndingTitle: 'O assistente de voz esta terminando',
    voiceEndingBody:
      'Salve seu formulario agora para nao perder suas respostas. Voce ainda pode digitar as respostas restantes e ainda pode baixar e imprimir seu formulario.',
    resumeTitle: 'Continuar um formulario salvo',
    resumeBody:
      'Se voce salvou este formulario antes, abra o arquivo salvo aqui e suas respostas voltarao.',
    resumeAction: 'Continuar meu formulario salvo',
    startOverAction: 'Comecar de novo',
    dropHere: 'Solte aqui o seu PDF salvo, ou escolha um arquivo',
    resumeMismatch:
      'Esse arquivo nao corresponde ao formulario que lhe foi enviado. Escolha o arquivo que voce salvou deste formulario.',
    resumeUnreadable:
      'Nao conseguimos ler esse arquivo. Escolha o PDF que voce salvou deste formulario.',
    resumeSuccess: 'Suas respostas voltaram. Voce pode continuar de onde parou.',
  },

  Hindi: {
    saveNudgeTitle: 'अपना फॉर्म सहेजें ताकि आप वापस आ सकें',
    saveNudgeBody:
      'इस फॉर्म को अभी अपने डिवाइस में सहेजें। यदि आप यह पेज बंद करते हैं या कुछ समय के लिए रुकते हैं, तो आप बाद में सहेजी गई फ़ाइल खोलकर वहीं से जारी रख सकते हैं। हमारे सर्वर पर कुछ भी संग्रहीत नहीं होता।',
    saveNudgeAction: 'मेरा फॉर्म सहेजें',
    saveNudgeDismiss: 'अभी नहीं',
    voiceEndingTitle: 'वॉइस सहायक समाप्त हो रहा है',
    voiceEndingBody:
      'अपने उत्तर खोने से बचने के लिए अभी अपना फॉर्म सहेजें। आप शेष उत्तर टाइप कर सकते हैं, और अपना फॉर्म डाउनलोड और प्रिंट भी कर सकते हैं।',
    resumeTitle: 'सहेजा गया फॉर्म जारी रखें',
    resumeBody:
      'यदि आपने पहले यह फॉर्म सहेजा था, तो सहेजी गई फ़ाइल यहाँ खोलें और आपके उत्तर वापस आ जाएँगे।',
    resumeAction: 'मेरा सहेजा गया फॉर्म जारी रखें',
    startOverAction: 'फिर से शुरू करें',
    dropHere: 'अपनी सहेजी गई PDF यहाँ छोड़ें, या फ़ाइल चुनें',
    resumeMismatch:
      'वह फ़ाइल आपको भेजे गए फॉर्म से मेल नहीं खाती। कृपया वही फ़ाइल चुनें जो आपने इस फॉर्म से सहेजी थी।',
    resumeUnreadable:
      'हम वह फ़ाइल नहीं पढ़ सके। कृपया वही PDF चुनें जो आपने इस फॉर्म से सहेजी थी।',
    resumeSuccess: 'आपके उत्तर वापस आ गए हैं। आप वहीं से जारी रख सकते हैं जहाँ रुके थे।',
  },

  Italian: {
    saveNudgeTitle: 'Salva il modulo per poterci tornare',
    saveNudgeBody:
      'Salva ora questo modulo sul tuo dispositivo. Se chiudi questa pagina o ti fermi per un po, potrai aprire il file salvato piu tardi e riprendere da dove avevi lasciato. Nulla viene conservato sui nostri server.',
    saveNudgeAction: 'Salva il mio modulo',
    saveNudgeDismiss: 'Non ora',
    voiceEndingTitle: 'L assistente vocale sta terminando',
    voiceEndingBody:
      'Salva ora il modulo per non perdere le tue risposte. Puoi ancora digitare le risposte rimanenti e puoi ancora scaricare e stampare il modulo.',
    resumeTitle: 'Continua un modulo salvato',
    resumeBody:
      'Se hai gia salvato questo modulo, apri qui il file salvato e le tue risposte torneranno.',
    resumeAction: 'Continua il mio modulo salvato',
    startOverAction: 'Ricomincia',
    dropHere: 'Trascina qui il PDF salvato, o scegli un file',
    resumeMismatch:
      'Quel file non corrisponde al modulo che ti e stato inviato. Scegli il file che hai salvato da questo modulo.',
    resumeUnreadable:
      'Non siamo riusciti a leggere quel file. Scegli il PDF che hai salvato da questo modulo.',
    resumeSuccess: 'Le tue risposte sono tornate. Puoi riprendere da dove ti eri fermato.',
  },

  Urdu: {
    saveNudgeTitle: 'اپنا فارم محفوظ کریں تاکہ آپ واپس آ سکیں',
    saveNudgeBody:
      'یہ فارم ابھی اپنے آلے میں محفوظ کریں۔ اگر آپ یہ صفحہ بند کر دیں یا کچھ دیر رک جائیں، تو آپ بعد میں محفوظ شدہ فائل کھول کر وہیں سے جاری رکھ سکتے ہیں۔ ہمارے سرورز پر کچھ محفوظ نہیں ہوتا۔',
    saveNudgeAction: 'میرا فارم محفوظ کریں',
    saveNudgeDismiss: 'ابھی نہیں',
    voiceEndingTitle: 'صوتی معاون ختم ہو رہا ہے',
    voiceEndingBody:
      'اپنے جوابات ضائع ہونے سے بچانے کے لیے ابھی اپنا فارم محفوظ کریں۔ آپ باقی جوابات ٹائپ کر سکتے ہیں، اور اپنا فارم ڈاؤن لوڈ اور پرنٹ بھی کر سکتے ہیں۔',
    resumeTitle: 'محفوظ شدہ فارم جاری رکھیں',
    resumeBody:
      'اگر آپ نے پہلے یہ فارم محفوظ کیا تھا، تو محفوظ شدہ فائل یہاں کھولیں اور آپ کے جوابات واپس آ جائیں گے۔',
    resumeAction: 'میرا محفوظ شدہ فارم جاری رکھیں',
    startOverAction: 'دوبارہ شروع کریں',
    dropHere: 'اپنی محفوظ شدہ PDF یہاں چھوڑیں، یا فائل منتخب کریں',
    resumeMismatch:
      'وہ فائل اس فارم سے مطابقت نہیں رکھتی جو آپ کو بھیجا گیا تھا۔ براہ کرم وہی فائل منتخب کریں جو آپ نے اس فارم سے محفوظ کی تھی۔',
    resumeUnreadable:
      'ہم وہ فائل نہیں پڑھ سکے۔ براہ کرم وہی PDF منتخب کریں جو آپ نے اس فارم سے محفوظ کی تھی۔',
    resumeSuccess: 'آپ کے جوابات واپس آ گئے ہیں۔ آپ وہیں سے جاری رکھ سکتے ہیں۔',
  },

  Persian: {
    saveNudgeTitle: 'فرم خود را ذخیره کنید تا بتوانید بازگردید',
    saveNudgeBody:
      'اکنون این فرم را در دستگاه خود ذخیره کنید. اگر این صفحه را ببندید یا مدتی متوقف شوید، می‌توانید بعداً فایل ذخیره‌شده را باز کنید و از همان‌جا ادامه دهید. هیچ چیزی روی سرورهای ما ذخیره نمی‌شود.',
    saveNudgeAction: 'ذخیره فرم من',
    saveNudgeDismiss: 'الان نه',
    voiceEndingTitle: 'دستیار صوتی در حال پایان است',
    voiceEndingBody:
      'اکنون فرم خود را ذخیره کنید تا پاسخ‌هایتان از بین نرود. همچنان می‌توانید پاسخ‌های باقی‌مانده را تایپ کنید و فرم خود را دانلود و چاپ کنید.',
    resumeTitle: 'ادامه یک فرم ذخیره‌شده',
    resumeBody:
      'اگر قبلاً این فرم را ذخیره کرده‌اید، فایل ذخیره‌شده را اینجا باز کنید تا پاسخ‌هایتان بازگردند.',
    resumeAction: 'ادامه فرم ذخیره‌شده من',
    startOverAction: 'شروع دوباره',
    dropHere: 'فایل PDF ذخیره‌شده را اینجا رها کنید یا یک فایل انتخاب کنید',
    resumeMismatch:
      'آن فایل با فرمی که برای شما ارسال شده مطابقت ندارد. لطفاً فایلی را انتخاب کنید که از این فرم ذخیره کرده‌اید.',
    resumeUnreadable:
      'نتوانستیم آن فایل را بخوانیم. لطفاً فایل PDF ذخیره‌شده از این فرم را انتخاب کنید.',
    resumeSuccess: 'پاسخ‌های شما بازگشتند. می‌توانید از همان‌جا که متوقف شدید ادامه دهید.',
  },

  Dutch: {
    saveNudgeTitle: 'Sla uw formulier op zodat u kunt terugkomen',
    saveNudgeBody:
      'Sla dit formulier nu op uw apparaat op. Als u deze pagina sluit of even stopt, kunt u het opgeslagen bestand later openen en verdergaan waar u was gebleven. Er wordt niets op onze servers bewaard.',
    saveNudgeAction: 'Mijn formulier opslaan',
    saveNudgeDismiss: 'Niet nu',
    voiceEndingTitle: 'De spraakassistent stopt',
    voiceEndingBody:
      'Sla uw formulier nu op zodat u uw antwoorden niet kwijtraakt. U kunt de resterende antwoorden nog typen en u kunt uw formulier nog downloaden en afdrukken.',
    resumeTitle: 'Een opgeslagen formulier voortzetten',
    resumeBody:
      'Als u dit formulier eerder heeft opgeslagen, open hier het opgeslagen bestand en uw antwoorden komen terug.',
    resumeAction: 'Mijn opgeslagen formulier voortzetten',
    startOverAction: 'Opnieuw beginnen',
    dropHere: 'Sleep hier uw opgeslagen PDF, of kies een bestand',
    resumeMismatch:
      'Dat bestand komt niet overeen met het formulier dat u is toegestuurd. Kies het bestand dat u van dit formulier heeft opgeslagen.',
    resumeUnreadable:
      'We konden dat bestand niet lezen. Kies de PDF die u van dit formulier heeft opgeslagen.',
    resumeSuccess: 'Uw antwoorden zijn terug. U kunt verder waar u was gestopt.',
  },

  Ukrainian: {
    saveNudgeTitle: 'Збережіть форму, щоб повернутися до неї',
    saveNudgeBody:
      'Збережіть цю форму на своєму пристрої зараз. Якщо ви закриєте цю сторінку або зробите перерву, ви зможете відкрити збережений файл пізніше й продовжити з того місця, де зупинилися. На наших серверах нічого не зберігається.',
    saveNudgeAction: 'Зберегти мою форму',
    saveNudgeDismiss: 'Не зараз',
    voiceEndingTitle: 'Голосовий помічник завершує роботу',
    voiceEndingBody:
      'Збережіть форму зараз, щоб не втратити відповіді. Ви все ще можете вписати решту відповідей, а також завантажити та роздрукувати форму.',
    resumeTitle: 'Продовжити збережену форму',
    resumeBody:
      'Якщо ви раніше зберігали цю форму, відкрийте збережений файл тут — і ваші відповіді повернуться.',
    resumeAction: 'Продовжити мою збережену форму',
    startOverAction: 'Почати спочатку',
    dropHere: 'Перетягніть сюди збережений PDF або виберіть файл',
    resumeMismatch:
      'Цей файл не збігається з формою, яку вам надіслали. Будь ласка, виберіть файл, збережений із цієї форми.',
    resumeUnreadable:
      'Не вдалося прочитати цей файл. Будь ласка, виберіть PDF, збережений із цієї форми.',
    resumeSuccess: 'Ваші відповіді повернулися. Можете продовжувати з того місця, де зупинилися.',
  },

  Russian: {
    saveNudgeTitle: 'Сохраните форму, чтобы вернуться к ней',
    saveNudgeBody:
      'Сохраните эту форму на своё устройство сейчас. Если вы закроете страницу или прервётесь, вы сможете позже открыть сохранённый файл и продолжить с того места, где остановились. На наших серверах ничего не хранится.',
    saveNudgeAction: 'Сохранить мою форму',
    saveNudgeDismiss: 'Не сейчас',
    voiceEndingTitle: 'Голосовой помощник завершает работу',
    voiceEndingBody:
      'Сохраните форму сейчас, чтобы не потерять ответы. Вы по-прежнему можете вписать оставшиеся ответы, а также скачать и распечатать форму.',
    resumeTitle: 'Продолжить сохранённую форму',
    resumeBody:
      'Если вы сохраняли эту форму раньше, откройте сохранённый файл здесь — и ваши ответы вернутся.',
    resumeAction: 'Продолжить мою сохранённую форму',
    startOverAction: 'Начать заново',
    dropHere: 'Перетащите сюда сохранённый PDF или выберите файл',
    resumeMismatch:
      'Этот файл не соответствует форме, которую вам отправили. Пожалуйста, выберите файл, сохранённый из этой формы.',
    resumeUnreadable:
      'Не удалось прочитать этот файл. Пожалуйста, выберите PDF, сохранённый из этой формы.',
    resumeSuccess: 'Ваши ответы вернулись. Можете продолжать с того места, где остановились.',
  },

  Swedish: {
    saveNudgeTitle: 'Spara ditt formular sa att du kan komma tillbaka',
    saveNudgeBody:
      'Spara det har formularet pa din enhet nu. Om du stanger sidan eller tar en paus kan du oppna den sparade filen senare och fortsatta dar du slutade. Ingenting lagras pa vara servrar.',
    saveNudgeAction: 'Spara mitt formular',
    saveNudgeDismiss: 'Inte nu',
    voiceEndingTitle: 'Rostassistenten avslutas',
    voiceEndingBody:
      'Spara ditt formular nu sa att du inte forlorar dina svar. Du kan fortfarande skriva in de svar som aterstar, och du kan fortfarande ladda ner och skriva ut ditt formular.',
    resumeTitle: 'Fortsatt ett sparat formular',
    resumeBody:
      'Om du sparade det har formularet tidigare, oppna den sparade filen har sa kommer dina svar tillbaka.',
    resumeAction: 'Fortsatt mitt sparade formular',
    startOverAction: 'Borja om',
    dropHere: 'Slapp din sparade PDF har, eller valj en fil',
    resumeMismatch:
      'Den filen matchar inte formularet som skickades till dig. Valj filen du sparade fran det har formularet.',
    resumeUnreadable:
      'Vi kunde inte lasa den filen. Valj den PDF du sparade fran det har formularet.',
    resumeSuccess: 'Dina svar ar tillbaka. Du kan fortsatta dar du slutade.',
  },

  Afrikaans: {
    saveNudgeTitle: 'Stoor jou vorm sodat jy kan terugkom',
    saveNudgeBody:
      'Stoor hierdie vorm nou op jou toestel. As jy hierdie bladsy toemaak of n ruk ophou, kan jy die gestoorde leer later oopmaak en voortgaan waar jy opgehou het. Niks word op ons bedieners gestoor nie.',
    saveNudgeAction: 'Stoor my vorm',
    saveNudgeDismiss: 'Nie nou nie',
    voiceEndingTitle: 'Die stemassistent is besig om te eindig',
    voiceEndingBody:
      'Stoor jou vorm nou sodat jy nie jou antwoorde verloor nie. Jy kan steeds die oorblywende antwoorde intik, en jy kan steeds jou vorm aflaai en druk.',
    resumeTitle: 'Gaan voort met n gestoorde vorm',
    resumeBody:
      'As jy hierdie vorm voorheen gestoor het, maak die gestoorde leer hier oop en jou antwoorde kom terug.',
    resumeAction: 'Gaan voort met my gestoorde vorm',
    startOverAction: 'Begin oor',
    dropHere: 'Los jou gestoorde PDF hier, of kies n leer',
    resumeMismatch:
      'Daardie leer stem nie ooreen met die vorm wat aan jou gestuur is nie. Kies asseblief die leer wat jy van hierdie vorm gestoor het.',
    resumeUnreadable:
      'Ons kon nie daardie leer lees nie. Kies asseblief die PDF wat jy van hierdie vorm gestoor het.',
    resumeSuccess: 'Jou antwoorde is terug. Jy kan voortgaan waar jy opgehou het.',
  },
};

/** Resolve strings for a language, falling back to English. */
export function resumeStrings(language: string | undefined): ResumeStrings {
  if (!language) return EN;
  return RESUME_TRANSLATIONS[language] ?? EN;
}
