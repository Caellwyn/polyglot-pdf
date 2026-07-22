/**
 * DisclaimerModal - Mandatory disclaimer acceptance flow
 *
 * Features:
 * - Non-dismissible modal (no X button, no outside click, no ESC key)
 * - Displays disclaimer text in English
 * - "Listen Again" button triggers Gemini to re-read disclaimer
 * - "I Agree" button logs agreement and proceeds to form
 * - Button text translated to user's selected language
 */

import React, { useEffect } from 'react';
import './DisclaimerModal.css';

export interface DisclaimerModalProps {
  isOpen: boolean;
  selectedLanguage: string;
  onListenAgain: () => void;
  onAgree: () => void;
}

// Translation data for button text
export const BUTTON_TRANSLATIONS: Record<string, { listenAgain: string; agree: string }> = {
  'English': { listenAgain: 'Listen Again', agree: 'I Agree' },
  'Spanish': { listenAgain: 'Escuchar de Nuevo', agree: 'Estoy de Acuerdo' },
  'Chinese': { listenAgain: '再听一次', agree: '我同意' },
  'Tagalog': { listenAgain: 'Pakinggan Muli', agree: 'Sumasang-ayon Ako' },
  'Arabic': { listenAgain: 'استمع مرة أخرى', agree: 'أوافق' },
  'French': { listenAgain: 'Écouter à Nouveau', agree: 'J\'accepte' },
  'Korean': { listenAgain: '다시 듣기', agree: '동의합니다' },
  'German': { listenAgain: 'Nochmal Anhören', agree: 'Ich Stimme Zu' },
  'Portuguese': { listenAgain: 'Ouvir Novamente', agree: 'Eu Concordo' },
  'Hindi': { listenAgain: 'फिर से सुनें', agree: 'मैं सहमत हूं' },
  'Italian': { listenAgain: 'Ascolta di Nuovo', agree: 'Accetto' },
  'Urdu': { listenAgain: 'دوبارہ سنیں', agree: 'میں متفق ہوں' },
  'Persian': { listenAgain: 'دوباره گوش کنید', agree: 'موافقم' },
  'Dutch': { listenAgain: 'Opnieuw Beluisteren', agree: 'Ik Ga Akkoord' },
  'Ukrainian': { listenAgain: 'Послухати Знову', agree: 'Я Погоджуюсь' },
  'Russian': { listenAgain: 'Прослушать Снова', agree: 'Принимаю' },
  'Swedish': { listenAgain: 'Lyssna Igen', agree: 'Jag Godkänner' },
  'Afrikaans': { listenAgain: 'Luister Weer', agree: 'Ek Stem Saam' },
};

// Translation data for disclaimer text
export const DISCLAIMER_TRANSLATIONS: Record<string, { title: string; p1: string; p2: string; p3: string; fullText: string }> = {
  'English': {
    title: 'Important Notice',
    p1: 'This is an Important Notice about the limits of this AI tool. This is an Artificial Intelligence (AI) tool designed to help you with language and form data entry only. This tool is not a lawyer, and it is not a certified translator. The AI cannot give you legal advice, immigration advice, or professional help. It helps you fill out a form; it does not tell you how to answer. Using this app does not create a lawyer-client relationship.',
    p2: 'The form created by this AI is only a DRAFT (a first copy). It is not a certified, official, or sworn translation. Government offices (like USCIS) may require your final form to be reviewed and signed by a certified human professional (like an attorney or certified interpreter). We strongly advise you to have a qualified professional check your final form before you submit it.',
    p3: 'Finally, AI tools make mistakes. There may be errors, wrong translations, or missing information. You must check every single answer on the English form before you submit it. You are responsible for every answer and all final information on your form. We are not responsible for errors made by the AI.',
    fullText: 'This is an Important Notice about the limits of this AI tool. This is an Artificial Intelligence (AI) tool designed to help you with language and form data entry only. This tool is not a lawyer, and it is not a certified translator. The AI cannot give you legal advice, immigration advice, or professional help. It helps you fill out a form; it does not tell you how to answer. Using this app does not create a lawyer-client relationship. The form created by this AI is only a DRAFT (a first copy). It is not a certified, official, or sworn translation. Government offices (like USCIS) may require your final form to be reviewed and signed by a certified human professional (like an attorney or certified interpreter). We strongly advise you to have a qualified professional check your final form before you submit it. Finally, AI tools make mistakes. There may be errors, wrong translations, or missing information. You must check every single answer on the English form before you submit it. You are responsible for every answer and all final information on your form. We are not responsible for errors made by the AI.'
  },
  'Spanish': {
    title: 'Aviso Importante',
    p1: 'Este es un Aviso Importante sobre los límites de esta herramienta de IA. Esta es una herramienta de Inteligencia Artificial (IA) diseñada solo para ayudarle con el idioma y el ingreso de datos en formularios. Esta herramienta no es un abogado y no es un traductor certificado. La IA no puede darle asesoramiento legal, asesoramiento de inmigración o ayuda profesional. Le ayuda a completar un formulario; no le dice cómo responder. El uso de esta aplicación no crea una relación abogado-cliente.',
    p2: 'El formulario creado por esta IA es solo un BORRADOR (una primera copia). No es una traducción certificada, oficial o jurada. Las oficinas gubernamentales (como USCIS) pueden requerir que su formulario final sea revisado y firmado por un profesional humano certificado (como un abogado o un intérprete certificado). Le recomendamos encarecidamente que un profesional calificado revise su formulario final antes de enviarlo.',
    p3: 'Finalmente, las herramientas de IA cometen errores. Puede haber errores, traducciones incorrectas o información faltante. Debe verificar cada respuesta en el formulario en inglés antes de enviarlo. Usted es responsable de cada respuesta y de toda la información final en su formulario. No somos responsables de los errores cometidos por la IA.',
    fullText: 'Este es un Aviso Importante sobre los límites de esta herramienta de IA. Esta es una herramienta de Inteligencia Artificial (IA) diseñada solo para ayudarle con el idioma y el ingreso de datos en formularios. Esta herramienta no es un abogado y no es un traductor certificado. La IA no puede darle asesoramiento legal, asesoramiento de inmigración o ayuda profesional. Le ayuda a completar un formulario; no le dice cómo responder. El uso de esta aplicación no crea una relación abogado-cliente. El formulario creado por esta IA es solo un BORRADOR (una primera copia). No es una traducción certificada, oficial o jurada. Las oficinas gubernamentales (como USCIS) pueden requerir que su formulario final sea revisado y firmado por un profesional humano certificado (como un abogado o un intérprete certificado). Le recomendamos encarecidamente que un profesional calificado revise su formulario final antes de enviarlo. Finalmente, las herramientas de IA cometen errores. Puede haber errores, traducciones incorrectas o información faltante. Debe verificar cada respuesta en el formulario en inglés antes de enviarlo. Usted es responsable de cada respuesta y de toda la información final en su formulario. No somos responsables de los errores cometidos por la IA.'
  },
  'Chinese': {
    title: '重要通知',
    p1: '这是关于此 AI 工具限制的重要通知。这是一个人工智能 (AI) 工具，仅旨在帮助您进行语言和表单数据输入。此工具不是律师，也不是经过认证的翻译员。AI 无法为您提供法律建议、移民建议或专业帮助。它帮助您填写表格；它不会告诉您如何回答。使用此应用程序不会建立律师-客户关系。',
    p2: '此 AI 创建的表格仅为草稿（初稿）。它不是经过认证、官方或宣誓的翻译。政府办公室（如 USCIS）可能要求您的最终表格由经过认证的人类专业人员（如律师或认证口译员）进行审查和签署。我们强烈建议您在提交之前让合格的专业人员检查您的最终表格。',
    p3: '最后，AI 工具会犯错。可能会有错误、错误的翻译或遗漏的信息。您必须在提交之前检查英文表格上的每一个答案。您对表格上的每一个答案和所有最终信息负责。我们不对 AI 造成的错误负责。',
    fullText: '这是关于此 AI 工具限制的重要通知。这是一个人工智能 (AI) 工具，仅旨在帮助您进行语言和表单数据输入。此工具不是律师，也不是经过认证的翻译员。AI 无法为您提供法律建议、移民建议或专业帮助。它帮助您填写表格；它不会告诉您如何回答。使用此应用程序不会建立律师-客户关系。此 AI 创建的表格仅为草稿（初稿）。它不是经过认证、官方或宣誓的翻译。政府办公室（如 USCIS）可能要求您的最终表格由经过认证的人类专业人员（如律师或认证口译员）进行审查和签署。我们强烈建议您在提交之前让合格的专业人员检查您的最终表格。最后，AI 工具会犯错。可能会有错误、错误的翻译或遗漏的信息。您必须在提交之前检查英文表格上的每一个答案。您对表格上的每一个答案和所有最终信息负责。我们不对 AI 造成的错误负责。'
  },
  'Tagalog': {
    title: 'Mahalagang Paunawa',
    p1: 'Ito ay isang Mahalagang Paunawa tungkol sa mga limitasyon ng AI tool na ito. Ito ay isang Artificial Intelligence (AI) tool na idinisenyo upang tulungan ka sa wika at paglalagay ng data sa form lamang. Ang tool na ito ay hindi abogado, at hindi ito sertipikadong tagasalin. Ang AI ay hindi makakapagbigay sa iyo ng legal na payo, payo sa imigrasyon, o propesyonal na tulong. Tinutulungan ka nitong punan ang isang form; hindi nito sinasabi sa iyo kung paano sumagot. Ang paggamit ng app na ito ay hindi lumilikha ng relasyon sa pagitan ng abogado at kliyente.',
    p2: 'Ang form na ginawa ng AI na ito ay DRAFT lamang (isang unang kopya). Ito ay hindi isang sertipikado, opisyal, o sinumpaang pagsasalin. Maaaring hilingin ng mga opisina ng gobyerno (tulad ng USCIS) na ang iyong huling form ay suriin at lagdaan ng isang sertipikadong propesyonal na tao (tulad ng isang abogado o sertipikadong interpreter). Mahigpit naming ipinapayo sa iyo na ipasuri ang iyong huling form sa isang kwalipikadong propesyonal bago mo ito isumite.',
    p3: 'Sa huli, nagkakamali ang mga AI tool. Maaaring may mga error, maling pagsasalin, o nawawalang impormasyon. Dapat mong suriin ang bawat solong sagot sa English form bago mo ito isumite. Ikaw ang responsable para sa bawat sagot at lahat ng huling impormasyon sa iyong form. Hindi kami responsable para sa mga error na ginawa ng AI.',
    fullText: 'Ito ay isang Mahalagang Paunawa tungkol sa mga limitasyon ng AI tool na ito. Ito ay isang Artificial Intelligence (AI) tool na idinisenyo upang tulungan ka sa wika at paglalagay ng data sa form lamang. Ang tool na ito ay hindi abogado, at hindi ito sertipikadong tagasalin. Ang AI ay hindi makakapagbigay sa iyo ng legal na payo, payo sa imigrasyon, o propesyonal na tulong. Tinutulungan ka nitong punan ang isang form; hindi nito sinasabi sa iyo kung paano sumagot. Ang paggamit ng app na ito ay hindi lumilikha ng relasyon sa pagitan ng abogado at kliyente. Ang form na ginawa ng AI na ito ay DRAFT lamang (isang unang kopya). Ito ay hindi isang sertipikado, opisyal, o sinumpaang pagsasalin. Maaaring hilingin ng mga opisina ng gobyerno (tulad ng USCIS) na ang iyong huling form ay suriin at lagdaan ng isang sertipikadong propesyonal na tao (tulad ng isang abogado o sertipikadong interpreter). Mahigpit naming ipinapayo sa iyo na ipasuri ang iyong huling form sa isang kwalipikadong propesyonal bago mo ito isumite. Sa huli, nagkakamali ang mga AI tool. Maaaring may mga error, maling pagsasalin, o nawawalang impormasyon. Dapat mong suriin ang bawat solong sagot sa English form bago mo ito isumite. Ikaw ang responsable para sa bawat sagot at lahat ng huling impormasyon sa iyong form. Hindi kami responsable para sa mga error na ginawa ng AI.'
  },
  'Arabic': {
    title: 'إشعار هام',
    p1: 'هذا إشعار هام حول حدود أداة الذكاء الاصطناعي هذه. هذه أداة ذكاء اصطناعي (AI) مصممة لمساعدتك في اللغة وإدخال بيانات النموذج فقط. هذه الأداة ليست محامياً، وليست مترجماً معتمداً. لا يمكن للذكاء الاصطناعي أن يقدم لك مشورة قانونية أو مشورة بشأن الهجرة أو مساعدة مهنية. إنها تساعدك في ملء النموذج؛ ولا تخبرك بكيفية الإجابة. استخدام هذا التطبيق لا ينشئ علاقة محامي وموكل.',
    p2: 'النموذج الذي تم إنشاؤه بواسطة هذا الذكاء الاصطناعي هو مجرد مسودة (نسخة أولى). إنها ليست ترجمة معتمدة أو رسمية أو محلفة. قد تطلب المكاتب الحكومية (مثل USCIS) مراجعة نموذجك النهائي وتوقيعه من قبل محترف بشري معتمد (مثل محامٍ أو مترجم معتمد). ننصحك بشدة بأن يقوم محترف مؤهل بفحص نموذجك النهائي قبل تقديمه.',
    p3: 'أخيراً، أدوات الذكاء الاصطناعي ترتكب أخطاء. قد تكون هناك أخطاء أو ترجمات خاطئة أو معلومات مفقودة. يجب عليك التحقق من كل إجابة في النموذج الإنجليزي قبل تقديمه. أنت مسؤول عن كل إجابة وجميع المعلومات النهائية في نموذجك. نحن لسنا مسؤولين عن الأخطاء التي يرتكبها الذكاء الاصطناعي.',
    fullText: 'هذا إشعار هام حول حدود أداة الذكاء الاصطناعي هذه. هذه أداة ذكاء اصطناعي (AI) مصممة لمساعدتك في اللغة وإدخال بيانات النموذج فقط. هذه الأداة ليست محامياً، وليست مترجماً معتمداً. لا يمكن للذكاء الاصطناعي أن يقدم لك مشورة قانونية أو مشورة بشأن الهجرة أو مساعدة مهنية. إنها تساعدك في ملء النموذج؛ ولا تخبرك بكيفية الإجابة. استخدام هذا التطبيق لا ينشئ علاقة محامي وموكل. النموذج الذي تم إنشاؤه بواسطة هذا الذكاء الاصطناعي هو مجرد مسودة (نسخة أولى). إنها ليست ترجمة معتمدة أو رسمية أو محلفة. قد تطلب المكاتب الحكومية (مثل USCIS) مراجعة نموذجك النهائي وتوقيعه من قبل محترف بشري معتمد (مثل محامٍ أو مترجم معتمد). ننصحك بشدة بأن يقوم محترف مؤهل بفحص نموذجك النهائي قبل تقديمه. أخيراً، أدوات الذكاء الاصطناعي ترتكب أخطاء. قد تكون هناك أخطاء أو ترجمات خاطئة أو معلومات مفقودة. يجب عليك التحقق من كل إجابة في النموذج الإنجليزي قبل تقديمه. أنت مسؤول عن كل إجابة وجميع المعلومات النهائية في نموذجك. نحن لسنا مسؤولين عن الأخطاء التي يرتكبها الذكاء الاصطناعي.'
  },
  'French': {
    title: 'Avis Important',
    p1: 'Ceci est un avis important concernant les limites de cet outil d\'IA. Il s\'agit d\'un outil d\'Intelligence Artificielle (IA) conçu uniquement pour vous aider avec la langue et la saisie de données de formulaire. Cet outil n\'est pas un avocat et n\'est pas un traducteur certifié. L\'IA ne peut pas vous donner de conseils juridiques, de conseils en immigration ou d\'aide professionnelle. Elle vous aide à remplir un formulaire ; elle ne vous dit pas comment répondre. L\'utilisation de cette application ne crée pas de relation avocat-client.',
    p2: 'Le formulaire créé par cette IA n\'est qu\'un BROUILLON (une première copie). Ce n\'est pas une traduction certifiée, officielle ou assermentée. Les bureaux gouvernementaux (comme l\'USCIS) peuvent exiger que votre formulaire final soit examiné et signé par un professionnel humain certifié (comme un avocat ou un interprète certifié). Nous vous conseillons vivement de faire vérifier votre formulaire final par un professionnel qualifié avant de le soumettre.',
    p3: 'Enfin, les outils d\'IA font des erreurs. Il peut y avoir des erreurs, de mauvaises traductions ou des informations manquantes. Vous devez vérifier chaque réponse sur le formulaire en anglais avant de le soumettre. Vous êtes responsable de chaque réponse et de toutes les informations finales sur votre formulaire. Nous ne sommes pas responsables des erreurs commises par l\'IA.',
    fullText: 'Ceci est un avis important concernant les limites de cet outil d\'IA. Il s\'agit d\'un outil d\'Intelligence Artificielle (IA) conçu uniquement pour vous aider avec la langue et la saisie de données de formulaire. Cet outil n\'est pas un avocat et n\'est pas un traducteur certifié. L\'IA ne peut pas vous donner de conseils juridiques, de conseils en immigration ou d\'aide professionnelle. Elle vous aide à remplir un formulaire ; elle ne vous dit pas comment répondre. L\'utilisation de cette application ne crée pas de relation avocat-client. Le formulaire créé par cette IA n\'est qu\'un BROUILLON (une première copie). Ce n\'est pas une traduction certifiée, officielle ou assermentée. Les bureaux gouvernementaux (comme l\'USCIS) peuvent exiger que votre formulaire final soit examiné et signé par un professionnel humain certifié (comme un avocat ou un interprète certifié). Nous vous conseillons vivement de faire vérifier votre formulaire final par un professionnel qualifié avant de le soumettre. Enfin, les outils d\'IA font des erreurs. Il peut y avoir des erreurs, de mauvaises traductions ou des informations manquantes. Vous devez vérifier chaque réponse sur le formulaire en anglais avant de le soumettre. Vous êtes responsable de chaque réponse et de toutes les informations finales sur votre formulaire. Nous ne sommes pas responsables des erreurs commises par l\'IA.'
  },
  'Korean': {
    title: '중요 공지',
    p1: '이 AI 도구의 한계에 대한 중요 공지입니다. 이것은 언어 및 양식 데이터 입력만을 돕기 위해 설계된 인공 지능(AI) 도구입니다. 이 도구는 변호사가 아니며 공인 번역가가 아닙니다. AI는 법률 자문, 이민 자문 또는 전문적인 도움을 제공할 수 없습니다. 양식 작성을 도와줄 뿐, 답변 방법을 알려주지는 않습니다. 이 앱을 사용한다고 해서 변호사-의뢰인 관계가 형성되는 것은 아닙니다.',
    p2: '이 AI가 작성한 양식은 초안(첫 번째 사본)일 뿐입니다. 공인, 공식 또는 선서 번역이 아닙니다. 관공서(예: USCIS)에서는 최종 양식을 공인된 인간 전문가(예: 변호사 또는 공인 통역사)가 검토하고 서명하도록 요구할 수 있습니다. 제출하기 전에 자격을 갖춘 전문가에게 최종 양식을 확인받는 것을 강력히 권장합니다.',
    p3: '마지막으로, AI 도구는 실수를 합니다. 오류, 잘못된 번역 또는 누락된 정보가 있을 수 있습니다. 제출하기 전에 영어 양식의 모든 답변을 확인해야 합니다. 양식의 모든 답변과 모든 최종 정보에 대한 책임은 귀하에게 있습니다. 당사는 AI가 범한 오류에 대해 책임을 지지 않습니다.',
    fullText: '이 AI 도구의 한계에 대한 중요 공지입니다. 이것은 언어 및 양식 데이터 입력만을 돕기 위해 설계된 인공 지능(AI) 도구입니다. 이 도구는 변호사가 아니며 공인 번역가가 아닙니다. AI는 법률 자문, 이민 자문 또는 전문적인 도움을 제공할 수 없습니다. 양식 작성을 도와줄 뿐, 답변 방법을 알려주지는 않습니다. 이 앱을 사용한다고 해서 변호사-의뢰인 관계가 형성되는 것은 아닙니다. 이 AI가 작성한 양식은 초안(첫 번째 사본)일 뿐입니다. 공인, 공식 또는 선서 번역이 아닙니다. 관공서(예: USCIS)에서는 최종 양식을 공인된 인간 전문가(예: 변호사 또는 공인 통역사)가 검토하고 서명하도록 요구할 수 있습니다. 제출하기 전에 자격을 갖춘 전문가에게 최종 양식을 확인받는 것을 강력히 권장합니다. 마지막으로, AI 도구는 실수를 합니다. 오류, 잘못된 번역 또는 누락된 정보가 있을 수 있습니다. 제출하기 전에 영어 양식의 모든 답변을 확인해야 합니다. 양식의 모든 답변과 모든 최종 정보에 대한 책임은 귀하에게 있습니다. 당사는 AI가 범한 오류에 대해 책임을 지지 않습니다.'
  },
  'German': {
    title: 'Wichtiger Hinweis',
    p1: 'Dies ist ein wichtiger Hinweis zu den Grenzen dieses KI-Tools. Dies ist ein Werkzeug der Künstlichen Intelligenz (KI), das Ihnen nur bei der Sprache und der Eingabe von Formulardaten helfen soll. Dieses Tool ist kein Anwalt und kein zertifizierter Übersetzer. Die KI kann Ihnen keine Rechtsberatung, Einwanderungsberatung oder professionelle Hilfe geben. Sie hilft Ihnen beim Ausfüllen eines Formulars; sie sagt Ihnen nicht, wie Sie antworten sollen. Durch die Nutzung dieser App entsteht kein Anwalt-Mandanten-Verhältnis.',
    p2: 'Das von dieser KI erstellte Formular ist nur ein ENTWURF (eine erste Kopie). Es ist keine beglaubigte, offizielle oder vereidigte Übersetzung. Regierungsstellen (wie USCIS) können verlangen, dass Ihr endgültiges Formular von einem zertifizierten menschlichen Fachmann (wie einem Anwalt oder zertifizierten Dolmetscher) überprüft und unterzeichnet wird. Wir raten Ihnen dringend, Ihr endgültiges Formular vor dem Absenden von einem qualifizierten Fachmann überprüfen zu lassen.',
    p3: 'Schließlich machen KI-Tools Fehler. Es kann Fehler, falsche Übersetzungen oder fehlende Informationen geben. Sie müssen jede einzelne Antwort auf dem englischen Formular überprüfen, bevor Sie es absenden. Sie sind für jede Antwort und alle endgültigen Informationen auf Ihrem Formular verantwortlich. Wir sind nicht verantwortlich für Fehler, die von der KI gemacht werden.',
    fullText: 'Dies ist ein wichtiger Hinweis zu den Grenzen dieses KI-Tools. Dies ist ein Werkzeug der Künstlichen Intelligenz (KI), das Ihnen nur bei der Sprache und der Eingabe von Formulardaten helfen soll. Dieses Tool ist kein Anwalt und kein zertifizierter Übersetzer. Die KI kann Ihnen keine Rechtsberatung, Einwanderungsberatung oder professionelle Hilfe geben. Sie hilft Ihnen beim Ausfüllen eines Formulars; sie sagt Ihnen nicht, wie Sie antworten sollen. Durch die Nutzung dieser App entsteht kein Anwalt-Mandanten-Verhältnis. Das von dieser KI erstellte Formular ist nur ein ENTWURF (eine erste Kopie). Es ist keine beglaubigte, offizielle oder vereidigte Übersetzung. Regierungsstellen (wie USCIS) können verlangen, dass Ihr endgültiges Formular von einem zertifizierten menschlichen Fachmann (wie einem Anwalt oder zertifizierten Dolmetscher) überprüft und unterzeichnet wird. Wir raten Ihnen dringend, Ihr endgültiges Formular vor dem Absenden von einem qualifizierten Fachmann überprüfen zu lassen. Schließlich machen KI-Tools Fehler. Es kann Fehler, falsche Übersetzungen oder fehlende Informationen geben. Sie müssen jede einzelne Antwort auf dem englischen Formular überprüfen, bevor Sie es absenden. Sie sind für jede Antwort und alle endgültigen Informationen auf Ihrem Formular verantwortlich. Wir sind nicht verantwortlich für Fehler, die von der KI gemacht werden.'
  },
  'Portuguese': {
    title: 'Aviso Importante',
    p1: 'Este é um Aviso Importante sobre os limites desta ferramenta de IA. Esta é uma ferramenta de Inteligência Artificial (IA) projetada para ajudá-lo apenas com o idioma e a entrada de dados em formulários. Esta ferramenta não é um advogado e não é um tradutor certificado. A IA não pode lhe dar aconselhamento jurídico, aconselhamento de imigração ou ajuda profissional. Ela ajuda você a preencher um formulário; não lhe diz como responder. O uso deste aplicativo não cria uma relação advogado-cliente.',
    p2: 'O formulário criado por esta IA é apenas um RASCUNHO (uma primeira cópia). Não é uma tradução certificada, oficial ou juramentada. Repartições governamentais (como o USCIS) podem exigir que seu formulário final seja revisado e assinado por um profissional humano certificado (como um advogado ou intérprete certificado). Aconselhamos vivamente que você peça a um profissional qualificado para verificar seu formulário final antes de enviá-lo.',
    p3: 'Finalmente, ferramentas de IA cometem erros. Pode haver erros, traduções erradas ou informações ausentes. Você deve verificar cada resposta no formulário em inglês antes de enviá-lo. Você é responsável por cada resposta e todas as informações finais em seu formulário. Não somos responsáveis por erros cometidos pela IA.',
    fullText: 'Este é um Aviso Importante sobre os limites desta ferramenta de IA. Esta é uma ferramenta de Inteligência Artificial (IA) projetada para ajudá-lo apenas com o idioma e a entrada de dados em formulários. Esta ferramenta não é um advogado e não é um tradutor certificado. A IA não pode lhe dar aconselhamento jurídico, aconselhamento de imigração ou ajuda profissional. Ela ajuda você a preencher um formulário; não lhe diz como responder. O uso deste aplicativo não cria uma relação advogado-cliente. O formulário criado por esta IA é apenas um RASCUNHO (uma primeira cópia). Não é uma tradução certificada, oficial ou juramentada. Repartições governamentais (como o USCIS) podem exigir que seu formulário final seja revisado e assinado por um profissional humano certificado (como um advogado ou intérprete certificado). Aconselhamos vivamente que você peça a um profissional qualificado para verificar seu formulário final antes de enviá-lo. Finalmente, ferramentas de IA cometem erros. Pode haver erros, traduções erradas ou informações ausentes. Você deve verificar cada resposta no formulário em inglês antes de enviá-lo. Você é responsável por cada resposta e todas as informações finais em seu formulário. Não somos responsáveis por erros cometidos pela IA.'
  },
  'Hindi': {
    title: 'महत्वपूर्ण सूचना',
    p1: 'यह इस AI उपकरण की सीमाओं के बारे में एक महत्वपूर्ण सूचना है। यह एक आर्टिफिशियल इंटेलिजेंस (AI) उपकरण है जिसे केवल भाषा और फॉर्म डेटा प्रविष्टि में आपकी सहायता करने के लिए डिज़ाइन किया गया है। यह उपकरण वकील नहीं है, और यह प्रमाणित अनुवादक नहीं है। AI आपको कानूनी सलाह, आव्रजन सलाह या पेशेवर मदद नहीं दे सकता है। यह आपको फॉर्म भरने में मदद करता है; यह आपको यह नहीं बताता कि उत्तर कैसे देना है। इस ऐप का उपयोग करने से वकील-ग्राहक संबंध नहीं बनता है।',
    p2: 'इस AI द्वारा बनाया गया फॉर्म केवल एक ड्राफ्ट (पहली प्रति) है। यह प्रमाणित, आधिकारिक या शपथ पत्र अनुवाद नहीं है। सरकारी कार्यालयों (जैसे USCIS) को आपके अंतिम फॉर्म की समीक्षा और हस्ताक्षर एक प्रमाणित मानव पेशेवर (जैसे वकील या प्रमाणित दुभाषिया) द्वारा किए जाने की आवश्यकता हो सकती है। हम आपको दृढ़ता से सलाह देते हैं कि जमा करने से पहले अपने अंतिम फॉर्म की जांच किसी योग्य पेशेवर से करवाएं।',
    p3: 'अंत में, AI उपकरण गलतियाँ करते हैं। त्रुटियां, गलत अनुवाद या गुम जानकारी हो सकती है। जमा करने से पहले आपको अंग्रेजी फॉर्म पर हर एक उत्तर की जांच करनी चाहिए। आप अपने फॉर्म पर हर उत्तर और सभी अंतिम जानकारी के लिए जिम्मेदार हैं। हम AI द्वारा की गई गलतियों के लिए जिम्मेदार नहीं हैं।',
    fullText: 'यह इस AI उपकरण की सीमाओं के बारे में एक महत्वपूर्ण सूचना है। यह एक आर्टिफिशियल इंटेलिजेंस (AI) उपकरण है जिसे केवल भाषा और फॉर्म डेटा प्रविष्टि में आपकी सहायता करने के लिए डिज़ाइन किया गया है। यह उपकरण वकील नहीं है, और यह प्रमाणित अनुवादक नहीं है। AI आपको कानूनी सलाह, आव्रजन सलाह या पेशेवर मदद नहीं दे सकता है। यह आपको फॉर्म भरने में मदद करता है; यह आपको यह नहीं बताता कि उत्तर कैसे देना है। इस ऐप का उपयोग करने से वकील-ग्राहक संबंध नहीं बनता है। इस AI द्वारा बनाया गया फॉर्म केवल एक ड्राफ्ट (पहली प्रति) है। यह प्रमाणित, आधिकारिक या शपथ पत्र अनुवाद नहीं है। सरकारी कार्यालयों (जैसे USCIS) को आपके अंतिम फॉर्म की समीक्षा और हस्ताक्षर एक प्रमाणित मानव पेशेवर (जैसे वकील या प्रमाणित दुभाषिया) द्वारा किए जाने की आवश्यकता हो सकती है। हम आपको दृढ़ता से सलाह देते हैं कि जमा करने से पहले अपने अंतिम फॉर्म की जांच किसी योग्य पेशेवर से करवाएं। अंत में, AI उपकरण गलतियाँ करते हैं। त्रुटियां, गलत अनुवाद या गुम जानकारी हो सकती है। जमा करने से पहले आपको अंग्रेजी फॉर्म पर हर एक उत्तर की जांच करनी चाहिए। आप अपने फॉर्म पर हर उत्तर और सभी अंतिम जानकारी के लिए जिम्मेदार हैं। हम AI द्वारा की गई गलतियों के लिए जिम्मेदार नहीं हैं।'
  },
  'Italian': {
    title: 'Avviso Importante',
    p1: 'Questo è un Avviso Importante sui limiti di questo strumento di IA. Questo è uno strumento di Intelligenza Artificiale (IA) progettato per aiutarti solo con la lingua e\'inserimento dei dati nei moduli. Questo strumento non è un avvocato e non è un traduttore certificato. L\'IA non può darti consulenza legale, consulenza sull\'immigrazione o aiuto professionale. Ti aiuta a compilare un modulo; non ti dice come rispondere. L\'uso di questa app non crea un rapporto avvocato-cliente.',
    p2: 'Il modulo creato da questa IA è solo una BOZZA (una prima copia). Non è una traduzione certificata, ufficiale o giurata. Gli uffici governativi (come l\'USCIS) potrebbero richiedere che il tuo modulo finale sia rivisto e firmato da un professionista umano certificato (come un avvocato o un interprete certificato). Ti consigliamo vivamente di far controllare il tuo modulo finale da un professionista qualificato prima di inviarlo.',
    p3: 'Infine, gli strumenti di IA commettono errori. Potrebbero esserci errori, traduzioni sbagliate o informazioni mancanti. Devi controllare ogni singola risposta sul modulo in inglese prima di inviarlo. Sei responsabile di ogni risposta e di tutte le informazioni finali sul tuo modulo. Non siamo responsabili per errori commessi dall\'IA.',
    fullText: 'Questo è un Avviso Importante sui limiti di questo strumento di IA. Questo è uno strumento di Intelligenza Artificiale (IA) progettato per aiutarti solo con la lingua e\'inserimento dei dati nei moduli. Questo strumento non è un avvocato e non è un traduttore certificato. L\'IA non può darti consulenza legale, consulenza sull\'immigrazione o aiuto professionale. Ti aiuta a compilare un modulo; non ti dice come rispondere. L\'uso di questa app non crea un rapporto avvocato-cliente. Il modulo creato da questa IA è solo una BOZZA (una prima copia). Non è una traduzione certificata, ufficiale o giurata. Gli uffici governativi (come l\'USCIS) potrebbero richiedere che il tuo modulo finale sia rivisto e firmato da un professionista umano certificato (come un avvocato o un interprete certificato). Ti consigliamo vivamente di far controllare il tuo modulo finale da un professionista qualificato prima di inviarlo. Infine, gli strumenti di IA commettono errori. Potrebbero esserci errori, traduzioni sbagliate o informazioni mancanti. Devi controllare ogni singola risposta sul modulo in inglese prima di inviarlo. Sei responsabile di ogni risposta e di tutte le informazioni finali sul tuo modulo. Non siamo responsabili per errori commessi dall\'IA.'
  },
  'Urdu': {
    title: 'اہم نوٹس',
    p1: 'یہ اس AI ٹول کی حدود کے بارے میں ایک اہم نوٹس ہے۔ یہ ایک مصنوعی ذہانت (AI) ٹول ہے جو صرف زبان اور فارم ڈیٹا کے اندراج میں آپ کی مدد کے لیے ڈیزائن کیا گیا ہے۔ یہ ٹول وکیل نہیں ہے، اور یہ کوئی سند یافتہ مترجم نہیں ہے۔ AI آپ کو قانونی مشورہ، امیگریشن کا مشورہ، یا پیشہ ورانہ مدد نہیں دے سکتا۔ یہ آپ کو فارم پُر کرنے میں مدد کرتا ہے؛ یہ آپ کو یہ نہیں بتاتا کہ جواب کیسے دینا ہے۔ اس ایپ کو استعمال کرنے سے وکیل اور مؤکل کا رشتہ قائم نہیں ہوتا ہے۔',
    p2: 'اس AI کا بنایا ہوا فارم صرف ایک مسودہ (پہلی کاپی) ہے۔ یہ کوئی سند یافتہ، سرکاری، یا حلفیہ ترجمہ نہیں ہے۔ سرکاری دفاتر (جیسے USCIS) کو آپ کے حتمی فارم کا جائزہ لینے اور دستخط کرنے کے لیے کسی سند یافتہ انسانی پیشہ ور (جیسے وکیل یا سند یافتہ ترجمان) کی ضرورت ہو سکتی ہے۔ ہم آپ کو سختی سے مشورہ دیتے ہیں کہ جمع کرنے سے پہلے اپنے حتمی فارم کو کسی اہل پیشہ ور سے چیک کروا لیں۔',
    p3: 'آخر میں، AI ٹولز غلطیاں کرتے ہیں۔ غلطیاں، غلط ترجمے، یا گمشدہ معلومات ہو سکتی ہیں۔ جمع کرنے سے پہلے آپ کو انگریزی فارم پر ہر ایک جواب کو چیک کرنا چاہیے۔ آپ اپنے فارم پر ہر جواب اور تمام حتمی معلومات کے ذمہ دار ہیں۔ ہم AI کی طرف سے کی گئی غلطیوں کے ذمہ دار نہیں ہیں۔',
    fullText: 'یہ اس AI ٹول کی حدود کے بارے میں ایک اہم نوٹس ہے۔ یہ ایک مصنوعی ذہانت (AI) ٹول ہے جو صرف زبان اور فارم ڈیٹا کے اندراج میں آپ کی مدد کے لیے ڈیزائن کیا گیا ہے۔ یہ ٹول وکیل نہیں ہے، اور یہ کوئی سند یافتہ مترجم نہیں ہے۔ AI آپ کو قانونی مشورہ، امیگریشن کا مشورہ، یا پیشہ ورانہ مدد نہیں دے سکتا۔ یہ آپ کو فارم پُر کرنے میں مدد کرتا ہے؛ یہ آپ کو یہ نہیں بتاتا کہ جواب کیسے دینا ہے۔ اس ایپ کو استعمال کرنے سے وکیل اور مؤکل کا رشتہ قائم نہیں ہوتا ہے۔ اس AI کا بنایا ہوا فارم صرف ایک مسودہ (پہلی کاپی) ہے۔ یہ کوئی سند یافتہ، سرکاری، یا حلفیہ ترجمہ نہیں ہے۔ سرکاری دفاتر (جیسے USCIS) کو آپ کے حتمی فارم کا جائزہ لینے اور دستخط کرنے کے لیے کسی سند یافتہ انسانی پیشہ ور (جیسے وکیل یا سند یافتہ ترجمان) کی ضرورت ہو سکتی ہے۔ ہم آپ کو سختی سے مشورہ دیتے ہیں کہ جمع کرنے سے پہلے اپنے حتمی فارم کو کسی اہل پیشہ ور سے چیک کروا لیں۔ آخر میں، AI ٹولز غلطیاں کرتے ہیں۔ غلطیاں، غلط ترجمے، یا گمشدہ معلومات ہو سکتی ہیں۔ جمع کرنے سے پہلے آپ کو انگریزی فارم پر ہر ایک جواب کو چیک کرنا چاہیے۔ آپ اپنے فارم پر ہر جواب اور تمام حتمی معلومات کے ذمہ دار ہیں۔ ہم AI کی طرف سے کی گئی غلطیوں کے ذمہ دار نہیں ہیں۔'
  },
  'Persian': {
    title: 'اطلاعیه مهم',
    p1: 'این یک اطلاعیه مهم در مورد محدودیت‌های این ابزار هوش مصنوعی است. این یک ابزار هوش مصنوعی (AI) است که فقط برای کمک به شما در زبان و ورود داده‌های فرم طراحی شده است. این ابزار وکیل نیست و مترجم رسمی نیست. هوش مصنوعی نمی‌تواند به شما مشاوره حقوقی، مشاوره مهاجرتی یا کمک حرفه‌ای بدهد. این به شما کمک می‌کند تا فرم را پر کنید؛ به شما نمی‌گوید چگونه پاسخ دهید. استفاده از این برنامه رابطه وکیل و موکل ایجاد نمی‌کند.',
    p2: 'فرم ایجاد شده توسط این هوش مصنوعی فقط یک پیش‌نویس (یک کپی اولیه) است. این یک ترجمه رسمی، قانونی یا سوگند خورده نیست. دفاتر دولتی (مانند USCIS) ممکن است نیاز داشته باشند که فرم نهایی شما توسط یک متخصص انسانی تایید شده (مانند وکیل یا مترجم رسمی) بررسی و امضا شود. ما اکیداً به شما توصیه می‌کنیم که قبل از ارسال، فرم نهایی خود را توسط یک متخصص واجد شرایط بررسی کنید.',
    p3: 'در نهایت، ابزارهای هوش مصنوعی اشتباه می‌کنند. ممکن است خطا، ترجمه اشتباه یا اطلاعات از قلم افتاده وجود داشته باشد. شما باید قبل از ارسال، تک تک پاسخ‌های فرم انگلیسی را بررسی کنید. شما مسئول هر پاسخ و تمام اطلاعات نهایی در فرم خود هستید. ما مسئول خطاهای ایجاد شده توسط هوش مصنوعی نیستیم.',
    fullText: 'این یک اطلاعیه مهم در مورد محدودیت‌های این ابزار هوش مصنوعی است. این یک ابزار هوش مصنوعی (AI) است که فقط برای کمک به شما در زبان و ورود داده‌های فرم طراحی شده است. این ابزار وکیل نیست و مترجم رسمی نیست. هوش مصنوعی نمی‌تواند به شما مشاوره حقوقی، مشاوره مهاجرتی یا کمک حرفه‌ای بدهد. این به شما کمک می‌کند تا فرم را پر کنید؛ به شما نمی‌گوید چگونه پاسخ دهید. استفاده از این برنامه رابطه وکیل و موکل ایجاد نمی‌کند. فرم ایجاد شده توسط این هوش مصنوعی فقط یک پیش‌نویس (یک کپی اولیه) است. این یک ترجمه رسمی، قانونی یا سوگند خورده نیست. دفاتر دولتی (مانند USCIS) ممکن است نیاز داشته باشند که فرم نهایی شما توسط یک متخصص انسانی تایید شده (مانند وکیل یا مترجم رسمی) بررسی و امضا شود. ما اکیداً به شما توصیه می‌کنیم که قبل از ارسال، فرم نهایی خود را توسط یک متخصص واجد شرایط بررسی کنید. در نهایت، ابزارهای هوش مصنوعی اشتباه می‌کنند. ممکن است خطا، ترجمه اشتباه یا اطلاعات از قلم افتاده وجود داشته باشد. شما باید قبل از ارسال، تک تک پاسخ‌های فرم انگلیسی را بررسی کنید. شما مسئول هر پاسخ و تمام اطلاعات نهایی در فرم خود هستید. ما مسئول خطاهای ایجاد شده توسط هوش مصنوعی نیستیم.'
  },
  'Dutch': {
    title: 'Belangrijke Mededeling',
    p1: 'Dit is een belangrijke mededeling over de beperkingen van deze AI-tool. Dit is een tool voor kunstmatige intelligentie (AI) die uitsluitend is ontworpen om u te helpen met taal en het invoeren van formuliergegevens. Deze tool is geen advocaat en geen beëdigd vertaler. De AI kan u geen juridisch advies, immigratieadvies of professionele hulp geven. Het helpt u bij het invullen van een formulier; het vertelt u niet hoe u moet antwoorden. Het gebruik van deze app creëert geen advocaat-cliëntrelatie.',
    p2: 'Het formulier dat door deze AI is gemaakt, is slechts een CONCEPT (een eerste kopie). Het is geen beëdigde, officiële of gezworen vertaling. Overheidskantoren (zoals USCIS) kunnen vereisen dat uw definitieve formulier wordt beoordeeld en ondertekend door een gecertificeerde menselijke professional (zoals een advocaat of beëdigd tolk). Wij raden u ten zeerste aan om uw definitieve formulier door een gekwalificeerde professional te laten controleren voordat u het indient.',
    p3: 'Ten slotte maken AI-tools fouten. Er kunnen fouten, verkeerde vertalingen of ontbrekende informatie zijn. U moet elk afzonderlijk antwoord op het Engelse formulier controleren voordat u het indient. U bent verantwoordelijk voor elk antwoord en alle definitieve informatie op uw formulier. Wij zijn niet verantwoordelijk voor fouten gemaakt door de AI.',
    fullText: 'Dit is een belangrijke mededeling over de beperkingen van deze AI-tool. Dit is een tool voor kunstmatige intelligentie (AI) die uitsluitend is ontworpen om u te helpen met taal en het invoeren van formuliergegevens. Deze tool is geen advocaat en geen beëdigd vertaler. De AI kan u geen juridisch advies, immigratieadvies of professionele hulp geven. Het helpt u bij het invullen van een formulier; het vertelt u niet hoe u moet antwoorden. Het gebruik van deze app creëert geen advocaat-cliëntrelatie. Het formulier dat door deze AI is gemaakt, is slechts een CONCEPT (een eerste kopie). Het is geen beëdigde, officiële of gezworen vertaling. Overheidskantoren (zoals USCIS) kunnen vereisen dat uw definitieve formulier wordt beoordeeld en ondertekend door een gecertificeerde menselijke professional (zoals een advocaat of beëdigd tolk). Wij raden u ten zeerste aan om uw definitieve formulier door een gekwalificeerde professional te laten controleren voordat u het indient. Ten slotte maken AI-tools fouten. Er kunnen fouten, verkeerde vertalingen of ontbrekende informatie zijn. U moet elk afzonderlijk antwoord op het Engelse formulier controleren voordat u het indient. U bent verantwoordelijk voor elk antwoord en alle definitieve informatie op uw formulier. Wij zijn niet verantwoordelijk voor fouten gemaakt door de AI.'
  },
  'Ukrainian': {
    title: 'Важливе Повідомлення',
    p1: 'Це важливе повідомлення про обмеження цього інструменту ШІ. Це інструмент штучного інтелекту (ШІ), розроблений лише для допомоги вам з мовою та введенням даних у форму. Цей інструмент не є юристом і не є сертифікованим перекладачем. ШІ не може надавати вам юридичні консультації, консультації з імміграції або професійну допомогу. Він допомагає вам заповнити форму; він не каже вам, як відповідати. Використання цього додатка не створює відносин адвокат-клієнт.',
    p2: 'Форма, створена цим ШІ, є лише ЧЕРНОВИКОМ (першою копією). Це не сертифікований, офіційний або присяжний переклад. Урядові установи (наприклад, USCIS) можуть вимагати, щоб вашу остаточну форму перевірив і підписав сертифікований фахівець (наприклад, адвокат або сертифікований перекладач). Ми наполегливо рекомендуємо вам попросити кваліфікованого фахівця перевірити вашу остаточну форму перед її відправленням.',
    p3: 'Нарешті, інструменти ШІ роблять помилки. Можуть бути помилки, неправильні переклади або відсутня інформація. Ви повинні перевірити кожну відповідь у англійській формі перед її відправленням. Ви несете відповідальність за кожну відповідь і всю остаточну інформацію у вашій формі. Ми не несемо відповідальності за помилки, зроблені ШІ.',
    fullText: 'Це важливе повідомлення про обмеження цього інструменту ШІ. Це інструмент штучного інтелекту (ШІ), розроблений лише для допомоги вам з мовою та введенням даних у форму. Цей інструмент не є юристом і не є сертифікованим перекладачем. ШІ не може надавати вам юридичні консультації, консультації з імміграції або професійну допомогу. Він допомагає вам заповнити форму; він не каже вам, як відповідати. Використання цього додатка не створює відносин адвокат-клієнт. Форма, створена цим ШІ, є лише ЧЕРНОВИКОМ (першою копією). Це не сертифікований, офіційний або присяжний переклад. Урядові установи (наприклад, USCIS) можуть вимагати, щоб вашу остаточну форму перевірив і підписав сертифікований фахівець (наприклад, адвокат або сертифікований перекладач). Ми наполегливо рекомендуємо вам попросити кваліфікованого фахівця перевірити вашу остаточну форму перед її відправленням. Нарешті, інструменти ШІ роблять помилки. Можуть бути помилки, неправильні переклади або відсутня інформація. Ви повинні перевірити кожну відповідь у англійській формі перед її відправленням. Ви несете відповідальність за кожну відповідь і всю остаточну інформацію у вашій формі. Ми не несемо відповідальності за помилки, зроблені ШІ.'
  },
  'Russian': {
    title: 'Важное Уведомление',
    p1: 'Это важное уведомление об ограничениях этого ИИ-инструмента. Это инструмент искусственного интеллекта (ИИ), созданный только для того, чтобы помочь вам с языком и вводом данных в форму. Этот инструмент не является юристом и не является сертифицированным переводчиком. ИИ не может давать вам юридические консультации, консультации по иммиграции или профессиональную помощь. Он помогает вам заполнить форму; он не говорит вам, как отвечать. Использование этого приложения не создаёт отношений адвокат-клиент.',
    p2: 'Форма, созданная этим ИИ, является только ЧЕРНОВИКОМ (первой копией). Это не сертифицированный, официальный или присяжный перевод. Государственные учреждения (например, USCIS) могут требовать, чтобы вашу окончательную форму проверил и подписал сертифицированный специалист (например, адвокат или сертифицированный переводчик). Мы настоятельно рекомендуем вам попросить квалифицированного специалиста проверить вашу окончательную форму перед её отправкой.',
    p3: 'Наконец, ИИ-инструменты допускают ошибки. Могут быть ошибки, неправильные переводы или отсутствующая информация. Вы должны проверить каждый ответ в английской форме перед её отправкой. Вы несёте ответственность за каждый ответ и всю окончательную информацию в вашей форме. Мы не несём ответственности за ошибки, допущенные ИИ.',
    fullText: 'Это важное уведомление об ограничениях этого ИИ-инструмента. Это инструмент искусственного интеллекта (ИИ), созданный только для того, чтобы помочь вам с языком и вводом данных в форму. Этот инструмент не является юристом и не является сертифицированным переводчиком. ИИ не может давать вам юридические консультации, консультации по иммиграции или профессиональную помощь. Он помогает вам заполнить форму; он не говорит вам, как отвечать. Использование этого приложения не создаёт отношений адвокат-клиент. Форма, созданная этим ИИ, является только ЧЕРНОВИКОМ (первой копией). Это не сертифицированный, официальный или присяжный перевод. Государственные учреждения (например, USCIS) могут требовать, чтобы вашу окончательную форму проверил и подписал сертифицированный специалист (например, адвокат или сертифицированный переводчик). Мы настоятельно рекомендуем вам попросить квалифицированного специалиста проверить вашу окончательную форму перед её отправкой. Наконец, ИИ-инструменты допускают ошибки. Могут быть ошибки, неправильные переводы или отсутствующая информация. Вы должны проверить каждый ответ в английской форме перед её отправкой. Вы несёте ответственность за каждый ответ и всю окончательную информацию в вашей форме. Мы не несём ответственности за ошибки, допущенные ИИ.'
  },
  'Swedish': {
    title: 'Viktigt Meddelande',
    p1: 'Detta är ett viktigt meddelande om begränsningarna för detta AI-verktyg. Detta är ett verktyg för artificiell intelligens (AI) som endast är utformat för att hjälpa dig med språk och inmatning av formulärdata. Detta verktyg är inte en advokat och det är inte en certifierad översättare. AI:n kan inte ge dig juridisk rådgivning, immigrationsrådgivning eller professionell hjälp. Det hjälper dig att fylla i ett formulär; det talar inte om för dig hur du ska svara. Användning av denna app skapar inte en advokat-klientrelation.',
    p2: 'Formuläret som skapas av denna AI är endast ett UTKAST (en första kopia). Det är inte en certifierad, officiell eller edsvuren översättning. Statliga kontor (som USCIS) kan kräva att ditt slutliga formulär granskas och undertecknas av en certifierad mänsklig yrkesutövare (som en advokat eller certifierad tolk). Vi rekommenderar starkt att du låter en kvalificerad yrkesutövare kontrollera ditt slutliga formulär innan du skickar in det.',
    p3: 'Slutligen gör AI-verktyg misstag. Det kan finnas fel, felaktiga översättningar eller saknad information. Du måste kontrollera varenda svar på det engelska formuläret innan du skickar in det. Du ansvarar för varje svar och all slutlig information på ditt formulär. Vi ansvarar inte för fel som görs av AI:n.',
    fullText: 'Detta är ett viktigt meddelande om begränsningarna för detta AI-verktyg. Detta är ett verktyg för artificiell intelligens (AI) som endast är utformat för att hjälpa dig med språk och inmatning av formulärdata. Detta verktyg är inte en advokat och det är inte en certifierad översättare. AI:n kan inte ge dig juridisk rådgivning, immigrationsrådgivning eller professionell hjälp. Det hjälper dig att fylla i ett formulär; det talar inte om för dig hur du ska svara. Användning av denna app skapar inte en advokat-klientrelation. Formuläret som skapas av denna AI är endast ett UTKAST (en första kopia). Det är inte en certifierad, officiell eller edsvuren översättning. Statliga kontor (som USCIS) kan kräva att ditt slutliga formulär granskas och undertecknas av en certifierad mänsklig yrkesutövare (som en advokat eller certifierad tolk). Vi rekommenderar starkt att du låter en kvalificerad yrkesutövare kontrollera ditt slutliga formulär innan du skickar in det. Slutligen gör AI-verktyg misstag. Det kan finnas fel, felaktiga översättningar eller saknad information. Du måste kontrollera varenda svar på det engelska formuläret innan du skickar in det. Du ansvarar för varje svar och all slutlig information på ditt formulär. Vi ansvarar inte för fel som görs av AI:n.'
  },
  'Afrikaans': {
    title: 'Belangrike Kennisgewing',
    p1: 'Hierdie is \'n Belangrike Kennisgewing oor die beperkings van hierdie AI-instrument. Dit is \'n Kunsmatige Intelligensie (AI) instrument wat ontwerp is om u slegs met taal en vormdata-invoer te help. Hierdie instrument is nie \'n prokureur nie, en dit is nie \'n gesertifiseerde vertaler nie. Die AI kan u nie regsadvies, immigrasie-advies of professionele hulp gee nie. Dit help u om \'n vorm in te vul; dit sê nie vir u hoe om te antwoord nie. Die gebruik van hierdie app skep nie \'n prokureur-kliënt verhouding nie.',
    p2: 'Die vorm wat deur hierdie AI geskep is, is slegs \'n KONSEP (\'n eerste kopie). Dit is nie \'n gesertifiseerde, amptelike of beëdigde vertaling nie. Regeringskantore (soos USCIS) mag vereis dat u finale vorm deur \'n gesertifiseerde menslike professionele persoon (soos \'n prokureur of gesertifiseerde tolk) hersien en onderteken word. Ons raai u sterk aan om \'n gekwalifiseerde professionele persoon u finale vorm te laat nagaan voordat u dit indien.',
    p3: 'Ten slotte maak AI-instrumente foute. Daar kan foute, verkeerde vertalings of ontbrekende inligting wees. U moet elke enkele antwoord op die Engelse vorm nagaan voordat u dit indien. U is verantwoordelik vir elke antwoord en alle finale inligting op u vorm. Ons is nie verantwoordelik vir foute wat deur die AI gemaak word nie.',
    fullText: 'Hierdie is \'n Belangrike Kennisgewing oor die beperkings van hierdie AI-instrument. Dit is \'n Kunsmatige Intelligensie (AI) instrument wat ontwerp is om u slegs met taal en vormdata-invoer te help. Hierdie instrument is nie \'n prokureur nie, en dit is nie \'n gesertifiseerde vertaler nie. Die AI kan u nie regsadvies, immigrasie-advies of professionele hulp gee nie. Dit help u om \'n vorm in te vul; dit sê nie vir u hoe om te antwoord nie. Die gebruik van hierdie app skep nie \'n prokureur-kliënt verhouding nie. Die vorm wat deur hierdie AI geskep is, is slegs \'n KONSEP (\'n eerste kopie). Dit is nie \'n gesertifiseerde, amptelike of beëdigde vertaling nie. Regeringskantore (soos USCIS) mag vereis dat u finale vorm deur \'n gesertifiseerde menslike professionele persoon (soos \'n prokureur of gesertifiseerde tolk) hersien en onderteken word. Ons raai u sterk aan om \'n gekwalifiseerde professionele persoon u finale vorm te laat nagaan voordat u dit indien. Ten slotte maak AI-instrumente foute. Daar kan foute, verkeerde vertalings of ontbrekende inligting wees. U moet elke enkele antwoord op die Engelse vorm nagaan voordat u dit indien. U is verantwoordelik vir elke antwoord en alle finale inligting op u vorm. Ons is nie verantwoordelik vir foute wat deur die AI gemaak word nie.'
  },
};

export function DisclaimerModal({ isOpen, selectedLanguage, onListenAgain, onAgree }: DisclaimerModalProps) {
  // Prevent ESC key from closing modal
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    document.addEventListener('keydown', handleKeyDown, true);
    return () => document.removeEventListener('keydown', handleKeyDown, true);
  }, [isOpen]);

  // Prevent scroll on body when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  // Get button text in user's language, fallback to English
  const buttons = BUTTON_TRANSLATIONS[selectedLanguage] || BUTTON_TRANSLATIONS['English'];

  // Get disclaimer text in user's language, fallback to English
  const text = DISCLAIMER_TRANSLATIONS[selectedLanguage] || DISCLAIMER_TRANSLATIONS['English'];

  return (
    <div
      className="disclaimer-modal-overlay"
      onClick={(e) => e.stopPropagation()} // Prevent any click from closing
    >
      <div
        className="disclaimer-modal-content"
        role="dialog"
        aria-modal="true"
        aria-labelledby="disclaimer-title"
      >
        <h2 id="disclaimer-title" className="disclaimer-modal-title">
          {text.title}
        </h2>

        <div className="disclaimer-modal-text">
          <p>
            {text.p1}
          </p>
          <p>
            {text.p2}
          </p>
          <p>
            {text.p3}
          </p>
        </div>

        <div className="disclaimer-modal-buttons">
          <button
            className="disclaimer-modal-button disclaimer-modal-button--secondary"
            onClick={onListenAgain}
            type="button"
          >
            {buttons.listenAgain}
          </button>
          <button
            className="disclaimer-modal-button disclaimer-modal-button--primary"
            onClick={onAgree}
            type="button"
          >
            {buttons.agree}
          </button>
        </div>
      </div>
    </div>
  );
}
