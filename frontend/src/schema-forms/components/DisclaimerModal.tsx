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
const BUTTON_TRANSLATIONS: Record<string, { listenAgain: string; agree: string }> = {
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
  'Swedish': { listenAgain: 'Lyssna Igen', agree: 'Jag Godkänner' },
  'Afrikaans': { listenAgain: 'Luister Weer', agree: 'Ek Stem Saam' },
  'Quechua': { listenAgain: 'Wakmanta Uyariy', agree: 'Aceptani' },
};

// Translation data for disclaimer text
const DISCLAIMER_TRANSLATIONS: Record<string, { title: string; p1: string; p2: string; p3: string }> = {
  'English': {
    title: 'Important Notice',
    p1: 'This tool helps you fill out your form, but it does not provide legal advice.',
    p2: 'Please review all information carefully before submitting.',
    p3: 'For complex cases, consult an immigration attorney.'
  },
  'Spanish': {
    title: 'Aviso Importante',
    p1: 'Esta herramienta le ayuda a completar su formulario, pero no ofrece asesoramiento legal.',
    p2: 'Por favor, revise toda la información cuidadosamente antes de enviar.',
    p3: 'Para casos complejos, consulte a un abogado de inmigración.'
  },
  'Chinese': {
    title: '重要通知',
    p1: '此工具帮助您填写表格，但不提供法律建议。',
    p2: '提交前请仔细审查所有信息。',
    p3: '对于复杂案件，请咨询移民律师。'
  },
  'Tagalog': {
    title: 'Mahalagang Paunawa',
    p1: 'Ang tool na ito ay tumutulong sa iyo na punan ang iyong form, ngunit hindi ito nagbibigay ng legal na payo.',
    p2: 'Mangyaring suriin nang mabuti ang lahat ng impormasyon bago magsumite.',
    p3: 'Para sa mga kumplikadong kaso, kumunsulta sa isang abogado ng imigrasyon.'
  },
  'Arabic': {
    title: 'إشعار هام',
    p1: 'تساعدك هذه الأداة في ملء النموذج الخاص بك، ولكنها لا تقدم مشورة قانونية.',
    p2: 'يرجى مراجعة جميع المعلومات بعناية قبل التقديم.',
    p3: 'للحالات المعقدة، استشر محامي الهجرة.'
  },
  'French': {
    title: 'Avis Important',
    p1: 'Cet outil vous aide à remplir votre formulaire, mais il ne fournit pas de conseils juridiques.',
    p2: 'Veuillez vérifier attentivement toutes les informations avant de soumettre.',
    p3: 'Pour les cas complexes, consultez un avocat spécialisé en immigration.'
  },
  'Korean': {
    title: '중요 공지',
    p1: '이 도구는 양식 작성을 도와드리지만 법률 자문을 제공하지는 않습니다.',
    p2: '제출하기 전에 모든 정보를 주의 깊게 검토하십시오.',
    p3: '복잡한 경우에는 이민 변호사와 상담하십시오.'
  },
  'German': {
    title: 'Wichtiger Hinweis',
    p1: 'Dieses Tool hilft Ihnen beim Ausfüllen Ihres Formulars, bietet jedoch keine Rechtsberatung.',
    p2: 'Bitte überprüfen Sie alle Informationen sorgfältig vor dem Absenden.',
    p3: 'Bei komplexen Fällen konsultieren Sie einen Anwalt für Einwanderungsrecht.'
  },
  'Portuguese': {
    title: 'Aviso Importante',
    p1: 'Esta ferramenta ajuda você a preencher seu formulário, mas não fornece aconselhamento jurídico.',
    p2: 'Por favor, revise todas as informações cuidadosamente antes de enviar.',
    p3: 'Para casos complexos, consulte um advogado de imigração.'
  },
  'Hindi': {
    title: 'महत्वपूर्ण सूचना',
    p1: 'यह उपकरण आपको अपना फॉर्म भरने में मदद करता है, लेकिन यह कानूनी सलाह प्रदान नहीं करता है।',
    p2: 'कृपया जमा करने से पहले सभी जानकारी की सावधानीपूर्वक समीक्षा करें।',
    p3: 'जटिल मामलों के लिए, एक आव्रजन वकील से परामर्श करें।'
  },
  'Italian': {
    title: 'Avviso Importante',
    p1: 'Questo strumento ti aiuta a compilare il modulo, ma non fornisce consulenza legale.',
    p2: 'Si prega di rivedere attentamente tutte le informazioni prima di inviare.',
    p3: 'Per casi complessi, consultare un avvocato specializzato in immigrazione.'
  },
  'Urdu': {
    title: 'اہم نوٹس',
    p1: 'یہ ٹول آپ کو اپنا فارم پُر کرنے میں مدد کرتا ہے، لیکن یہ قانونی مشورہ فراہم نہیں کرتا ہے۔',
    p2: 'براہ کرم جمع کرنے سے پہلے تمام معلومات کا بغور جائزہ لیں۔',
    p3: 'پیچیدہ معاملات کے لیے، امیگریشن وکیل سے مشورہ کریں۔'
  },
  'Persian': {
    title: 'اطلاعیه مهم',
    p1: 'این ابزار به شما کمک می‌کند تا فرم خود را پر کنید، اما مشاوره حقوقی ارائه نمی‌دهد.',
    p2: 'لطفاً قبل از ارسال، تمام اطلاعات را با دقت بررسی کنید.',
    p3: 'برای موارد پیچیده، با یک وکیل مهاجرت مشورت کنید.'
  },
  'Dutch': {
    title: 'Belangrijke Mededeling',
    p1: 'Deze tool helpt u bij het invullen van uw formulier, maar geeft geen juridisch advies.',
    p2: 'Controleer alle informatie zorgvuldig voordat u deze indient.',
    p3: 'Raadpleeg voor complexe gevallen een immigratieadvocaat.'
  },
  'Ukrainian': {
    title: 'Важливе Повідомлення',
    p1: 'Цей інструмент допомагає вам заповнити форму, але не надає юридичних консультацій.',
    p2: 'Будь ласка, уважно перевірте всю інформацію перед відправленням.',
    p3: 'У складних випадках зверніться до імміграційного адвоката.'
  },
  'Swedish': {
    title: 'Viktigt Meddelande',
    p1: 'Detta verktyg hjälper dig att fylla i ditt formulär, men det ger inte juridisk rådgivning.',
    p2: 'Vänligen granska all information noggrant innan du skickar in.',
    p3: 'För komplexa fall, kontakta en immigrationsadvokat.'
  },
  'Afrikaans': {
    title: 'Belangrike Kennisgewing',
    p1: 'Hierdie instrument help u om u vorm in te vul, maar dit bied nie regsadvies nie.',
    p2: 'Gaan asseblief alle inligting noukeurig na voordat u dit indien.',
    p3: 'Vir ingewikkelde gevalle, raadpleeg \'n immigrasie-prokureur.'
  },
  'Quechua': {
    title: 'Ancha Chaniyuq Willakuy',
    p1: 'Kay yanapakuqmi formularioyki hunt\'ayta yanapasunki, ichaqa manam leymanta yuyaychayta qunchu.',
    p2: 'Ama hina kaspa, manaraq apachichkaspa tukuy willakuyta allinta qhaway.',
    p3: 'Sasa kasqanpiqa, huk inmigración abogadota tapukuy.'
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
