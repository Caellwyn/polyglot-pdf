/**
 * VERIFY_FIELD_TRANSLATIONS - copy for the explicit field-verification modal
 * (bd polyglot-pdf-96um6).
 *
 * "Verified" is load-bearing in this product's audit record: the firm reviews a
 * draft and the applicant undertakes review
 * (docs/standards/confirmation-and-audit.md). Typing no longer produces that
 * claim (bd polyglot-pdf-uum5g), so this modal is the KEYBOARD-ONLY way to make
 * it -- Enter on a filled field, then Enter or space on the focused checkbox.
 *
 * Mirrors the DisclaimerModal / ConnectionTimeoutModal house pattern: an inline
 * per-language map keyed by the SPOKEN_LANGUAGES `name`
 * (frontend/src/shared/languages.ts), with a fallback to English for any unknown
 * key. Adding a language upstream and missing it here fails
 * verifyFieldTranslations.test.ts rather than silently rendering English.
 *
 * Keys:
 * - title:        short headline naming the act ("Verify this answer")
 * - checkboxLabel: the assertion the user is making. This is the sentence the
 *                 audit record rests on, so it says what they are confirming --
 *                 that the value is correct -- not merely "OK".
 * - confirmButton: primary action.
 * - cancelButton:  dismiss WITHOUT verifying. The typed value is kept either way;
 *                 the modal never discards input (a mis-pressed Enter must not
 *                 cost the user their typing).
 * - fieldLabelPrefix: precedes the field's own name, so the modal says WHICH
 *                 field is being verified. The field name itself is not
 *                 translated -- it comes from the form kit.
 *
 * TRANSLATION STATUS: as with the sibling maps, the non-English strings are a
 * machine-generated first draft pending native-speaker review. ENGLISH IS
 * AUTHORITATIVE until then. Do not represent these as reviewed.
 *
 * SIZING NOTE: several of these run substantially longer than the English (the
 * German and Ukrainian checkbox labels are ~1.6x), and the modal must work in
 * the CROWDED PDF view. The CSS must wrap rather than assume English width.
 */

export interface VerifyFieldCopy {
  title: string;
  checkboxLabel: string;
  confirmButton: string;
  cancelButton: string;
  fieldLabelPrefix: string;
}

export const VERIFY_FIELD_TRANSLATIONS: Record<string, VerifyFieldCopy> = {
  'English': {
    title: 'Verify this answer',
    checkboxLabel: 'I have checked this answer and it is correct',
    confirmButton: 'Verify',
    cancelButton: 'Not yet',
    fieldLabelPrefix: 'Field',
  },
  'Spanish': {
    title: 'Verifique esta respuesta',
    checkboxLabel: 'He revisado esta respuesta y es correcta',
    confirmButton: 'Verificar',
    cancelButton: 'Todavía no',
    fieldLabelPrefix: 'Campo',
  },
  'Chinese': {
    title: '核对此答案',
    checkboxLabel: '我已核对此答案，确认无误',
    confirmButton: '确认',
    cancelButton: '暂不',
    fieldLabelPrefix: '字段',
  },
  'Tagalog': {
    title: 'Tiyakin ang sagot na ito',
    checkboxLabel: 'Nasuri ko na ang sagot na ito at tama ito',
    confirmButton: 'Tiyakin',
    cancelButton: 'Hindi pa',
    fieldLabelPrefix: 'Patlang',
  },
  'Arabic': {
    title: 'تحقق من هذه الإجابة',
    checkboxLabel: 'لقد راجعت هذه الإجابة وهي صحيحة',
    confirmButton: 'تحقق',
    cancelButton: 'ليس بعد',
    fieldLabelPrefix: 'الحقل',
  },
  'French': {
    title: 'Vérifiez cette réponse',
    checkboxLabel: "J'ai vérifié cette réponse et elle est correcte",
    confirmButton: 'Vérifier',
    cancelButton: 'Pas encore',
    fieldLabelPrefix: 'Champ',
  },
  'Korean': {
    title: '이 답변 확인',
    checkboxLabel: '이 답변을 확인했으며 정확합니다',
    confirmButton: '확인',
    cancelButton: '나중에',
    fieldLabelPrefix: '항목',
  },
  'German': {
    title: 'Diese Antwort bestätigen',
    checkboxLabel: 'Ich habe diese Antwort geprüft und sie ist korrekt',
    confirmButton: 'Bestätigen',
    cancelButton: 'Noch nicht',
    fieldLabelPrefix: 'Feld',
  },
  'Portuguese': {
    title: 'Verifique esta resposta',
    checkboxLabel: 'Verifiquei esta resposta e ela está correta',
    confirmButton: 'Verificar',
    cancelButton: 'Ainda não',
    fieldLabelPrefix: 'Campo',
  },
  'Hindi': {
    title: 'इस उत्तर की पुष्टि करें',
    checkboxLabel: 'मैंने इस उत्तर की जाँच कर ली है और यह सही है',
    confirmButton: 'पुष्टि करें',
    cancelButton: 'अभी नहीं',
    fieldLabelPrefix: 'फ़ील्ड',
  },
  'Italian': {
    title: 'Verifica questa risposta',
    checkboxLabel: 'Ho controllato questa risposta ed è corretta',
    confirmButton: 'Verifica',
    cancelButton: 'Non ancora',
    fieldLabelPrefix: 'Campo',
  },
  'Urdu': {
    title: 'اس جواب کی تصدیق کریں',
    checkboxLabel: 'میں نے اس جواب کو جانچ لیا ہے اور یہ درست ہے',
    confirmButton: 'تصدیق کریں',
    cancelButton: 'ابھی نہیں',
    fieldLabelPrefix: 'خانہ',
  },
  'Persian': {
    title: 'این پاسخ را تأیید کنید',
    checkboxLabel: 'این پاسخ را بررسی کرده‌ام و صحیح است',
    confirmButton: 'تأیید',
    cancelButton: 'هنوز نه',
    fieldLabelPrefix: 'فیلد',
  },
  'Dutch': {
    title: 'Controleer dit antwoord',
    checkboxLabel: 'Ik heb dit antwoord gecontroleerd en het is juist',
    confirmButton: 'Bevestigen',
    cancelButton: 'Nog niet',
    fieldLabelPrefix: 'Veld',
  },
  'Ukrainian': {
    title: 'Підтвердьте цю відповідь',
    checkboxLabel: 'Я перевірив цю відповідь, і вона правильна',
    confirmButton: 'Підтвердити',
    cancelButton: 'Ще ні',
    fieldLabelPrefix: 'Поле',
  },
  'Russian': {
    title: 'Подтвердите этот ответ',
    checkboxLabel: 'Я проверил этот ответ, и он верный',
    confirmButton: 'Подтвердить',
    cancelButton: 'Ещё нет',
    fieldLabelPrefix: 'Поле',
  },
  'Swedish': {
    title: 'Bekräfta detta svar',
    checkboxLabel: 'Jag har kontrollerat detta svar och det är korrekt',
    confirmButton: 'Bekräfta',
    cancelButton: 'Inte än',
    fieldLabelPrefix: 'Fält',
  },
  'Afrikaans': {
    title: 'Bevestig hierdie antwoord',
    checkboxLabel: 'Ek het hierdie antwoord nagegaan en dit is korrek',
    confirmButton: 'Bevestig',
    cancelButton: 'Nog nie',
    fieldLabelPrefix: 'Veld',
  },
};

/** English fallback for an unknown language key, matching the sibling maps. */
export function getVerifyFieldCopy(language: string): VerifyFieldCopy {
  return VERIFY_FIELD_TRANSLATIONS[language] ?? VERIFY_FIELD_TRANSLATIONS['English'];
}
